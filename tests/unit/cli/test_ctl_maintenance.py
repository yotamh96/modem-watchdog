"""Tests for spark_modem.cli.ctl.maintenance — duration parser + dual-clock expiry."""

from __future__ import annotations

import json
from argparse import Namespace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from spark_modem.cli import main as cli_main
from spark_modem.cli.ctl import maintenance as ctl_maint
from spark_modem.cli.ctl.maintenance import (
    MAX_DURATION_SECONDS,
    parse_duration,
)
from spark_modem.state_store.store import StateStore
from spark_modem.wire.globals import GlobalsState
from spark_modem.wire.maintenance import MaintenanceWindow


def test_parse_duration_h_m_s() -> None:
    assert parse_duration("2h") == 7200
    assert parse_duration("30m") == 1800
    assert parse_duration("300s") == 300
    assert parse_duration(" 8H ") == 28800


def test_parse_duration_invalid_format_raises_value_error() -> None:
    with pytest.raises(ValueError, match="invalid duration"):
        parse_duration("two hours")
    with pytest.raises(ValueError, match="invalid duration"):
        parse_duration("h2")
    with pytest.raises(ValueError, match="invalid duration"):
        parse_duration("")


def test_max_duration_seconds_is_8_hours() -> None:
    assert MAX_DURATION_SECONDS == 28800
    assert MAX_DURATION_SECONDS == 8 * 3600


def test_run_on_via_main_rejects_missing_duration() -> None:
    """argparse requires --duration; missing it → SystemExit(2)."""
    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["ctl", "maintenance", "on"])
    assert exc_info.value.code == 2


async def test_run_on_rejects_duration_above_8h(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--duration=9h` exceeds the 8h hard cap → exit 2."""
    monkeypatch.setenv("SPARK_MODEM_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("SPARK_MODEM_RUN_DIR", str(tmp_path / "run"))
    args = Namespace(duration="9h")
    rc = await ctl_maint.run_on(args)
    assert rc == 2
    err = capsys.readouterr().err
    assert "8h cap" in err or "28800" in err


async def test_run_on_rejects_zero_duration(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPARK_MODEM_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("SPARK_MODEM_RUN_DIR", str(tmp_path / "run"))
    args = Namespace(duration="0s")
    rc = await ctl_maint.run_on(args)
    assert rc == 2
    assert "must be > 0" in capsys.readouterr().err


async def test_run_on_rejects_invalid_duration_format(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPARK_MODEM_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("SPARK_MODEM_RUN_DIR", str(tmp_path / "run"))
    args = Namespace(duration="forever")
    rc = await ctl_maint.run_on(args)
    assert rc == 2
    assert "invalid duration" in capsys.readouterr().err


async def test_run_on_writes_maintenance_to_globals(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`maintenance on --duration=2h` persists a MaintenanceWindow in globals.json."""
    monkeypatch.setenv("SPARK_MODEM_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("SPARK_MODEM_RUN_DIR", str(tmp_path / "run"))

    args = Namespace(duration="2h")
    rc = await ctl_maint.run_on(args)
    assert rc == 0

    # Read back through StateStore (separate instance — exercises persistence).
    store = StateStore()
    load = await store.load_globals()
    m = load.state.maintenance
    assert m is not None
    assert m.active is True
    assert m.scope == "destructive"
    assert m.max_duration_seconds == MAX_DURATION_SECONDS
    # 2h = 7200s; expires_monotonic - started_monotonic should equal that.
    assert abs((m.expires_monotonic - m.started_monotonic) - 7200) < 1e-3


async def test_run_off_clears_maintenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPARK_MODEM_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("SPARK_MODEM_RUN_DIR", str(tmp_path / "run"))

    # Write an active window first.
    await ctl_maint.run_on(Namespace(duration="1h"))
    rc = await ctl_maint.run_off(Namespace())
    assert rc == 0

    store = StateStore()
    load = await store.load_globals()
    assert load.state.maintenance is None


async def test_run_off_when_no_window_is_noop(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPARK_MODEM_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("SPARK_MODEM_RUN_DIR", str(tmp_path / "run"))
    rc = await ctl_maint.run_off(Namespace())
    assert rc == 0
    assert "no active window" in capsys.readouterr().out


async def test_run_status_reports_inactive_when_not_set(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPARK_MODEM_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("SPARK_MODEM_RUN_DIR", str(tmp_path / "run"))

    rc = await ctl_maint.run_status(Namespace())
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {"active": False}


async def test_run_status_reports_dual_clock_expired_correctly(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Monotonic-only past expiry triggers the dual-clock OR check."""
    monkeypatch.setenv("SPARK_MODEM_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("SPARK_MODEM_RUN_DIR", str(tmp_path / "run"))

    # Write a window where monotonic has already expired but ISO is in the future.
    far_future_iso = (datetime.now(UTC) + timedelta(hours=24)).isoformat()
    expired_window = MaintenanceWindow(
        active=True,
        scope="destructive",
        started_iso="2026-05-06T00:00:00+00:00",
        started_monotonic=0.0,
        expires_iso=far_future_iso,
        expires_monotonic=0.0,  # monotonic in the past — clock has moved well past 0
        max_duration_seconds=MAX_DURATION_SECONDS,
    )
    store = StateStore()
    new_globals = GlobalsState(maintenance=expired_window)
    await store.save_globals(new_globals)

    rc = await ctl_maint.run_status(Namespace())
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["expired_now"] is True
    assert out["active"] is False  # !expired_now
