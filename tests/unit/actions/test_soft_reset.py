"""Tests for actions.soft_reset -- single dms-set-operating-mode=reset call.

The soft-reset effect is observed next-cycle (the modem is rebooting),
so verify() returns VerifyResult.deferred() unconditionally.
"""

from __future__ import annotations

import pytest

from spark_modem.actions import soft_reset
from spark_modem.subproc.result import CompletedProcess
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind
from tests.fakes.runner import FakeRunner
from tests.unit.actions._helpers import base_argv, make_ctx, ok


def _who() -> WhoModem:
    return WhoModem(usb_path="2-3.1.1", cdc_wdm="cdc-wdm0")


def _argv() -> list[str]:
    return [*base_argv(), "--dms-set-operating-mode=reset"]


@pytest.mark.asyncio
async def test_soft_reset_invokes_dms_set_operating_mode_reset() -> None:
    runner = FakeRunner()
    runner.register(_argv(), ok(_argv()))
    ctx, _logger, _clock = make_ctx(runner)
    await soft_reset.execute(_who(), ctx)
    assert any("--dms-set-operating-mode=reset" in arg for call in runner.calls for arg in call)


@pytest.mark.asyncio
async def test_soft_reset_succeeded_on_canned_success() -> None:
    runner = FakeRunner()
    runner.register(_argv(), ok(_argv()))
    ctx, _logger, _clock = make_ctx(runner)
    result = await soft_reset.execute(_who(), ctx)
    assert result.succeeded is True
    assert result.kind == ActionKind.SOFT_RESET


@pytest.mark.asyncio
async def test_soft_reset_fails_on_qmi_error() -> None:
    runner = FakeRunner()
    runner.register(
        _argv(),
        CompletedProcess.make(
            argv=_argv(),
            exit_code=1,
            stdout=b"",
            stderr=b"reset failed",
            duration_monotonic=0.01,
            timed_out=False,
        ),
    )
    ctx, _logger, _clock = make_ctx(runner)
    result = await soft_reset.execute(_who(), ctx)
    assert result.succeeded is False
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("soft_reset:")


@pytest.mark.asyncio
async def test_soft_reset_verify_returns_deferred() -> None:
    """verify() does NO qmicli call -- returns deferred immediately."""
    runner = FakeRunner()  # nothing registered; verify must not call run()
    ctx, _logger, _clock = make_ctx(runner)
    result = await soft_reset.verify(_who(), ctx)
    assert result.status == "deferred"
    assert "next_cycle" in result.detail
    assert runner.calls == []
