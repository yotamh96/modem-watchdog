"""Tests for actions.dispatcher: registry shape + execute_and_verify routing.

Critical assertions:
  - registered_kinds() returns EXACTLY the six cheap actions (catches the
    duplicate-SET_APN bug planted in the planning text).
  - Destructive actions (MODEM_RESET / USB_RESET / DRIVER_RESET) are NOT
    registered (Phase 4 lands those).
  - Unknown kind -> failure ActionResult, no execute() invocation.
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


def test_registered_kinds_has_exactly_six_cheap_actions() -> None:
    """The registry must contain EXACTLY the six cheap-action kinds.

    This catches the deliberate duplicate-SET_APN bug planted in the plan
    text -- a duplicate would still produce six dict entries by overwrite,
    but would silently drop one of the other six. The frozenset comparison
    asserts the precise set.
    """
    expected = frozenset(
        {
            ActionKind.SET_APN,
            ActionKind.FIX_RAW_IP,
            ActionKind.SIM_POWER_ON,
            ActionKind.SOFT_RESET,
            ActionKind.SET_OPERATING_MODE,
            ActionKind.FIX_AUTOSUSPEND,
        }
    )
    assert registered_kinds() == expected
    assert len(registered_kinds()) == 6


def test_destructive_actions_not_registered() -> None:
    """MODEM_RESET / USB_RESET / DRIVER_RESET land in Phase 4 -- not here."""
    for kind in (ActionKind.MODEM_RESET, ActionKind.USB_RESET, ActionKind.DRIVER_RESET):
        assert is_registered(kind) is False
        assert kind not in registered_kinds()


@pytest.mark.asyncio
async def test_dispatch_unknown_kind_returns_failure() -> None:
    """Passing a non-registered kind must return a failure ActionResult.

    No execute() should be invoked; failure_reason carries the canonical
    'action_kind_not_registered:<kind>' string.
    """
    runner = FakeRunner()
    ctx, _logger, _clock = make_ctx(runner)
    result = await execute_and_verify(ActionKind.MODEM_RESET, _who(), ctx)
    assert result.succeeded is False
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("action_kind_not_registered")
    assert "modem_reset" in result.failure_reason
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
