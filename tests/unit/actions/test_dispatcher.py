"""Tests for actions.dispatcher: registry shape + execute_and_verify routing.

Critical assertions:
  - registered_kinds() returns EXACTLY eight kinds (six Phase-2 cheap +
    Phase-4 MODEM_RESET (Plan 04-01) + Phase-4 USB_RESET (Plan 04-02)).
    Plan 04-03 will rename the test to _nine_kinds when DRIVER_RESET lands.
  - MODEM_RESET (04-01) and USB_RESET (this plan, 04-02) are registered;
    DRIVER_RESET remains unregistered until Plan 04-03.
  - Unknown kind -> failure ActionResult, no execute() invocation. Plan
    04-02 rotates the probe from USB_RESET (now registered) to DRIVER_RESET
    (still unregistered).
  - Successful dispatch emits ActionPlanned + ActionExecuted via event_logger.
"""

from __future__ import annotations

import pytest

from spark_modem.actions.dispatcher import (
    execute_and_verify,
    is_registered,
    registered_kinds,
)
from spark_modem.subproc.result import CompletedProcess
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind
from spark_modem.wire.events import ActionExecuted, ActionFailed, ActionPlanned
from tests.fakes.runner import FakeRunner
from tests.unit.actions._helpers import (
    base_argv,
    make_ctx,
    ok,
)


def _who() -> WhoModem:
    return WhoModem(usb_path="2-3.1.1", cdc_wdm="cdc-wdm0")


def test_registered_kinds_has_exactly_eight_kinds() -> None:
    """The registry must contain EXACTLY eight kinds at Plan 04-02 commit time.

    Phase 2 shipped the six cheap actions. Plan 04-01 appended MODEM_RESET
    (7); Plan 04-02 (this plan) appends USB_RESET (8). Plan 04-03 will rename
    this test to _nine_kinds when DRIVER_RESET lands. Wave ordering
    (sequential 04-01 -> 04-02 -> 04-03) guarantees the assertion is correct
    at each plan's commit time.

    The frozenset comparison still catches the historical duplicate-SET_APN
    silent-overwrite bug (plus any future shape regression) -- a single
    silent drop would produce an unequal frozenset before the len check fires.
    """
    expected = frozenset(
        {
            ActionKind.SET_APN,
            ActionKind.FIX_RAW_IP,
            ActionKind.SIM_POWER_ON,
            ActionKind.SOFT_RESET,
            ActionKind.SET_OPERATING_MODE,
            ActionKind.FIX_AUTOSUSPEND,
            ActionKind.MODEM_RESET,
            ActionKind.USB_RESET,
        }
    )
    assert registered_kinds() == expected
    assert len(registered_kinds()) == 8


def test_destructive_actions_partially_registered_phase4_02() -> None:
    """Plan 04-02 ships USB_RESET; DRIVER_RESET still pending until Plan 04-03.

    Plan 04-03 will flip DRIVER_RESET to True; this test name and body will
    update one final time at that plan's commit (Plan 04-01 Task 2 note --
    intentional rename across the three plans).
    """
    assert is_registered(ActionKind.MODEM_RESET) is True
    assert ActionKind.MODEM_RESET in registered_kinds()
    assert is_registered(ActionKind.USB_RESET) is True
    assert ActionKind.USB_RESET in registered_kinds()
    # Plan 04-03 lands DRIVER_RESET.
    assert is_registered(ActionKind.DRIVER_RESET) is False


@pytest.mark.asyncio
async def test_dispatch_unknown_kind_returns_failure() -> None:
    """Passing a non-registered kind must return a failure ActionResult.

    No execute() should be invoked; failure_reason carries the canonical
    'action_kind_not_registered:<kind>' string.

    Probe with DRIVER_RESET because Plan 04-02 just registered USB_RESET;
    DRIVER_RESET remains unregistered until Plan 04-03. Once all three
    destructive kinds are registered (post-04-03) the assertion path will
    pivot to a synthetic kind via dynamic ActionKind iteration.
    """
    runner = FakeRunner()
    ctx, _logger, _clock = make_ctx(runner)
    result = await execute_and_verify(ActionKind.DRIVER_RESET, _who(), ctx)
    assert result.succeeded is False
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("action_kind_not_registered")
    assert "driver_reset" in result.failure_reason
    # Nothing should have been spawned by the FakeRunner.
    assert runner.calls == []


@pytest.mark.asyncio
async def test_dispatch_emits_action_planned_event() -> None:
    """Even when the kind is known, ActionPlanned is emitted before execute().

    Use SOFT_RESET because its execute() needs only a single canned response;
    avoids tangling this dispatcher-level test with set_apn's multi-step flow.
    """
    runner = FakeRunner()
    ctx, logger, _clock = make_ctx(runner)
    soft_argv = [*base_argv(), "--dms-set-operating-mode=reset"]
    runner.register(soft_argv, ok(soft_argv))

    await execute_and_verify(ActionKind.SOFT_RESET, _who(), ctx)

    planned = [e for e in logger.appended if isinstance(e, ActionPlanned)]
    assert len(planned) == 1
    assert planned[0].usb_path == "2-3.1.1"
    assert planned[0].action == ActionKind.SOFT_RESET
    assert planned[0].dry_run is False


@pytest.mark.asyncio
async def test_dispatch_emits_action_executed_event_on_success() -> None:
    """Successful execute() (with deferred verify) emits ActionExecuted."""
    runner = FakeRunner()
    ctx, logger, _clock = make_ctx(runner)
    soft_argv = [*base_argv(), "--dms-set-operating-mode=reset"]
    runner.register(soft_argv, ok(soft_argv))

    result = await execute_and_verify(ActionKind.SOFT_RESET, _who(), ctx)

    assert result.succeeded is True
    executed = [e for e in logger.appended if isinstance(e, ActionExecuted)]
    assert len(executed) == 1
    assert executed[0].action == ActionKind.SOFT_RESET
    assert executed[0].usb_path == "2-3.1.1"


@pytest.mark.asyncio
async def test_dispatch_emits_action_failed_event_on_failure() -> None:
    """A failed execute() (here: classify-detected error) emits ActionFailed.

    Trigger by registering a non-zero-exit CompletedProcess for the soft-reset
    argv -- the classify() short-circuit returns a NON_ZERO_EXIT QmiError,
    soft_reset.execute() fails with failure_reason='soft_reset:non_zero_exit'.
    """
    runner = FakeRunner()
    ctx, logger, _clock = make_ctx(runner)
    soft_argv = [*base_argv(), "--dms-set-operating-mode=reset"]
    runner.register(
        soft_argv,
        CompletedProcess.make(
            argv=soft_argv,
            exit_code=1,
            stdout=b"",
            stderr=b"some failure",
            duration_monotonic=0.01,
            timed_out=False,
        ),
    )

    result = await execute_and_verify(ActionKind.SOFT_RESET, _who(), ctx)
    assert result.succeeded is False
    failed = [e for e in logger.appended if isinstance(e, ActionFailed)]
    assert len(failed) == 1
    assert failed[0].action == ActionKind.SOFT_RESET
    assert failed[0].failure_reason.startswith("soft_reset:")
