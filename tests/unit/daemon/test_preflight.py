"""Unit tests for daemon.preflight — FR-60 PATH check + last-config-error IO."""

from __future__ import annotations

from pathlib import Path

import pytest

from spark_modem.daemon.preflight import (
    PreflightFailed,
    preflight_check,
    write_last_config_error,
)
from spark_modem.subproc import runner as subproc_runner

# ---------------------------------------------------------------------------
# PATH-check tests
# ---------------------------------------------------------------------------


async def test_qmicli_missing_raises_preflight_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """qmicli absent from PATH → PreflightFailed."""

    async def fake_run(argv: list[str], *, timeout_s: float, **_kw: object) -> object:
        del timeout_s
        if argv[0] == "qmicli":
            raise FileNotFoundError("qmicli not found")
        return object()  # ip --version succeeds; not reached for qmicli case

    monkeypatch.setattr(subproc_runner, "run", fake_run)
    with pytest.raises(PreflightFailed, match="qmicli"):
        await preflight_check()


async def test_ip_missing_raises_preflight_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ip absent from PATH → PreflightFailed."""

    async def fake_run(argv: list[str], *, timeout_s: float, **_kw: object) -> object:
        del timeout_s
        if argv[0] == "ip":
            raise FileNotFoundError("ip not found")
        return object()

    monkeypatch.setattr(subproc_runner, "run", fake_run)
    with pytest.raises(PreflightFailed, match="ip"):
        await preflight_check()


async def test_both_present_returns_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both binaries present → preflight returns without raising."""
    calls: list[list[str]] = []

    async def fake_run(argv: list[str], *, timeout_s: float, **_kw: object) -> object:
        del timeout_s
        calls.append(list(argv))
        return object()

    monkeypatch.setattr(subproc_runner, "run", fake_run)
    await preflight_check()  # must not raise
    # Both binaries were probed in the canonical order.
    assert ["qmicli", "--version"] in calls
    assert ["ip", "--version"] in calls


# ---------------------------------------------------------------------------
# last-config-error atomic write
# ---------------------------------------------------------------------------


def test_write_last_config_error_atomic(tmp_path: Path) -> None:
    """write_last_config_error places the message bytes at run_dir/last-config-error."""
    write_last_config_error(run_dir=tmp_path, message="webhook_url invalid")
    target = tmp_path / "last-config-error"
    assert target.exists()
    assert target.read_text(encoding="utf-8") == "webhook_url invalid"
