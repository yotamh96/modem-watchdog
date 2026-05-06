"""Tests for actions.sim_power_on -- qmicli --uim-sim-power-on=1."""

from __future__ import annotations

from pathlib import Path

import pytest

from spark_modem.actions import sim_power_on
from spark_modem.subproc.result import CompletedProcess
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind
from tests.fakes.runner import FakeRunner
from tests.unit.actions._helpers import base_argv, make_ctx, ok

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "qmicli"


def _read_fixture(intent: str, scenario: str, version: str = "1.30") -> bytes:
    return (_FIXTURES / intent / version / f"{scenario}.txt").read_bytes()


def _who() -> WhoModem:
    return WhoModem(usb_path="2-3.1.1", cdc_wdm="cdc-wdm0")


def _argv() -> list[str]:
    return [*base_argv(), "--uim-sim-power-on=1"]


@pytest.mark.asyncio
async def test_sim_power_on_invokes_uim_sim_power_on_1() -> None:
    """argv must contain --uim-sim-power-on=1."""
    runner = FakeRunner()
    runner.register(_argv(), ok(_argv()))
    ctx, _logger, _clock = make_ctx(runner)
    await sim_power_on.execute(_who(), ctx)
    assert any("--uim-sim-power-on=1" in arg for call in runner.calls for arg in call)


@pytest.mark.asyncio
async def test_sim_power_on_succeeds_with_canned_success() -> None:
    runner = FakeRunner()
    runner.register(_argv(), ok(_argv()))
    ctx, _logger, _clock = make_ctx(runner)
    result = await sim_power_on.execute(_who(), ctx)
    assert result.succeeded is True
    assert result.kind == ActionKind.SIM_POWER_ON
    assert result.failure_reason is None


@pytest.mark.asyncio
async def test_sim_power_on_fails_on_qmi_error() -> None:
    runner = FakeRunner()
    runner.register(
        _argv(),
        CompletedProcess.make(
            argv=_argv(),
            exit_code=1,
            stdout=b"",
            stderr=b"sim power-on failed",
            duration_monotonic=0.01,
            timed_out=False,
        ),
    )
    ctx, _logger, _clock = make_ctx(runner)
    result = await sim_power_on.execute(_who(), ctx)
    assert result.succeeded is False
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("sim_power_on:")


@pytest.mark.asyncio
async def test_sim_power_on_verify_ok_when_card_ready() -> None:
    runner = FakeRunner()
    card_argv = [*base_argv(), "--uim-get-card-status"]
    runner.register(card_argv, ok(card_argv, _read_fixture("get_sim_state", "ready")))
    ctx, _logger, _clock = make_ctx(runner)
    result = await sim_power_on.verify(_who(), ctx)
    assert result.status == "ok"
