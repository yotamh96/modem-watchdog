"""FR-28 / FR-28.1 dry-run gate tests.

dry_run=True must:
  - Skip execute() AND verify() entirely (no FakeRunner.run calls).
  - Return an ActionResult with succeeded=True, dry_run=True,
    verify_result.status == 'deferred'.
  - Still emit an ActionPlanned event with dry_run=True (so audit trail
    is preserved even when no side effect occurred).
"""

from __future__ import annotations

import pytest

from spark_modem.actions.dispatcher import execute_and_verify
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind
from spark_modem.wire.events import ActionExecuted, ActionFailed, ActionPlanned
from tests.fakes.runner import FakeRunner
from tests.unit.actions._helpers import make_ctx


def _who() -> WhoModem:
    return WhoModem(usb_path="2-3.1.1", cdc_wdm="cdc-wdm0")


@pytest.mark.asyncio
async def test_dry_run_short_circuits_qmicli() -> None:
    """dry_run=True must NOT call FakeRunner.run -- zero recorded calls."""
    runner = FakeRunner()  # Note: NO argv registered
    ctx, _logger, _clock = make_ctx(runner)
    result = await execute_and_verify(ActionKind.SET_APN, _who(), ctx, dry_run=True)
    assert result.dry_run is True
    assert result.succeeded is True
    assert result.verify_result is not None
    assert result.verify_result.status == "deferred"
    # FakeRunner raises KeyError on unregistered argv; if any call leaked
    # through we'd see a non-empty calls list.
    assert runner.calls == []


@pytest.mark.asyncio
async def test_dry_run_still_emits_action_planned_event() -> None:
    """Even in dry-run, ActionPlanned is appended with dry_run=True."""
    runner = FakeRunner()
    ctx, logger, _clock = make_ctx(runner)
    await execute_and_verify(ActionKind.FIX_RAW_IP, _who(), ctx, dry_run=True)
    planned = [e for e in logger.appended if isinstance(e, ActionPlanned)]
    assert len(planned) == 1
    assert planned[0].dry_run is True
    assert planned[0].action == ActionKind.FIX_RAW_IP


@pytest.mark.asyncio
async def test_dry_run_emits_no_executed_or_failed_events() -> None:
    """dry-run emits ActionPlanned only -- never ActionExecuted/ActionFailed."""
    runner = FakeRunner()
    ctx, logger, _clock = make_ctx(runner)
    await execute_and_verify(ActionKind.SOFT_RESET, _who(), ctx, dry_run=True)
    assert all(not isinstance(e, ActionExecuted) for e in logger.appended)
    assert all(not isinstance(e, ActionFailed) for e in logger.appended)
    assert sum(1 for e in logger.appended if isinstance(e, ActionPlanned)) == 1
