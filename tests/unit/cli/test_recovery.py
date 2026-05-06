"""Tests for spark_modem.cli.recovery — Diag fixture → ranked plans."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from spark_modem.cli import recovery as recovery_cmd
from spark_modem.wire.diag import (
    Diag,
    Issue,
    ModemSnapshot,
    SignalSnapshot,
    WhoModem,
)
from spark_modem.wire.enums import IssueCategory, IssueDetail, RegistrationState


def _make_diag_one_apn_empty() -> Diag:
    """Build a Diag with one modem that has an apn_empty issue → set_apn plan."""
    return Diag(
        ts_iso="2026-05-06T00:00:00+00:00",
        cycle_id=0,
        per_modem={
            "2-3.1.1": ModemSnapshot(
                usb_path="2-3.1.1",
                cdc_wdm="cdc-wdm0",
                operating_mode="online",
                sim_state="ready",
                registration=RegistrationState.REGISTERED_HOME,
                signal=SignalSnapshot(
                    rssi_dbm=-65,
                    rsrp_dbm=-94,
                    rsrq_db=-9.0,
                    snr_db=8.4,
                ),
                issues=[
                    Issue(
                        category=IssueCategory.CONFIG,
                        detail=IssueDetail.APN_EMPTY,
                        who=WhoModem(usb_path="2-3.1.1", cdc_wdm="cdc-wdm0"),
                        description="",
                    )
                ],
            )
        },
    )


def _make_args(diag_path: Path, **kwargs: object) -> Namespace:
    base: dict[str, object] = {
        "diag_fixture": str(diag_path),
        "qmi_fixture_dir": None,
        "action": None,
        "explain": False,
        "json": False,
        "dry_run": False,
    }
    base.update(kwargs)
    return Namespace(**base)


async def test_recovery_with_diag_fixture_emits_plans_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Default output is a compact JSON list of PlannedAction dicts."""
    diag_path = tmp_path / "diag.json"
    diag_path.write_bytes(_make_diag_one_apn_empty().model_dump_json().encode("utf-8"))
    rc = await recovery_cmd.run(_make_args(diag_path))
    assert rc == 0
    out = capsys.readouterr().out
    plans = json.loads(out)
    assert isinstance(plans, list)
    assert len(plans) == 1
    assert plans[0]["kind"] == "set_apn"


async def test_recovery_json_includes_transitions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--json` emits a {plans, transitions} object."""
    diag_path = tmp_path / "diag.json"
    diag_path.write_bytes(_make_diag_one_apn_empty().model_dump_json().encode("utf-8"))
    rc = await recovery_cmd.run(_make_args(diag_path, json=True))
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "plans" in payload
    assert "transitions" in payload
    assert isinstance(payload["plans"], list)
    assert isinstance(payload["transitions"], list)


async def test_recovery_explain_emits_per_plan_lines(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--explain` emits human-readable text including kind= and signal_gate=."""
    diag_path = tmp_path / "diag.json"
    diag_path.write_bytes(_make_diag_one_apn_empty().model_dump_json().encode("utf-8"))
    rc = await recovery_cmd.run(_make_args(diag_path, explain=True))
    assert rc == 0
    out = capsys.readouterr().out
    assert "kind=set_apn" in out
    assert "signal_gate=" in out


async def test_recovery_dry_run_marks_suppressed_dry_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--dry-run` flips Settings.dry_run; every plan carries suppressed_by_dry_run=True."""
    diag_path = tmp_path / "diag.json"
    diag_path.write_bytes(_make_diag_one_apn_empty().model_dump_json().encode("utf-8"))
    rc = await recovery_cmd.run(_make_args(diag_path, dry_run=True))
    assert rc == 0
    plans = json.loads(capsys.readouterr().out)
    assert all(p["suppressed_by_dry_run"] for p in plans)


async def test_recovery_without_diag_fixture_returns_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Missing `--diag-fixture` is a Phase-2 hard error."""
    args = _make_args(tmp_path / "missing.json")
    args.diag_fixture = None
    rc = await recovery_cmd.run(args)
    assert rc == 2
    assert "diag-fixture" in capsys.readouterr().err


async def test_recovery_with_unparseable_diag_returns_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Corrupt JSON in the Diag fixture is reported and exits 2, not raises."""
    bad = tmp_path / "bad.json"
    bad.write_bytes(b"{not valid json")
    rc = await recovery_cmd.run(_make_args(bad))
    assert rc == 2
    assert "failed to parse" in capsys.readouterr().err
