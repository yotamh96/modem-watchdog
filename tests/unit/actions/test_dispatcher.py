"""Tests for actions.dispatcher: registry shape + execute_and_verify routing.

Critical assertions:
  - registered_kinds() returns EXACTLY nine kinds (six Phase-2 cheap +
    Phase-4 MODEM_RESET (Plan 04-01) + USB_RESET (Plan 04-02) +
    DRIVER_RESET (Plan 04-03, this plan)). All three Phase-4 destructive
    kinds are now registered; the unknown-kind probe pivots to a synthetic
    sentinel via ActionKind extension since no real kind remains as a
    "still-unregistered" probe.
  - All three destructive kinds (MODEM_RESET, USB_RESET, DRIVER_RESET)
    return is_registered(...) is True.
  - Unknown kind -> failure ActionResult, no execute() invocation. Plan
    04-03 rotates the probe to a deliberately-unregistered synthetic kind
    (constructed via the StrEnum's _missing_ surface) since every legitimate
    ActionKind is now wired into _REGISTRY.
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


def test_registered_kinds_has_exactly_nine_kinds() -> None:
    """The registry must contain EXACTLY nine kinds at Plan 04-03 commit time.

    Phase 2 shipped the six cheap actions. Plan 04-01 appended MODEM_RESET
    (7); Plan 04-02 appended USB_RESET (8); Plan 04-03 (this plan) appends
    DRIVER_RESET (9). All three Phase-4 destructive kinds are now wired.

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
            ActionKind.DRIVER_RESET,
        }
    )
    assert registered_kinds() == expected
    assert len(registered_kinds()) == 9


def test_all_destructive_actions_registered_phase4_03() -> None:
    """Plan 04-03 ships DRIVER_RESET; all three destructive kinds now wired.

    Cross-plan rename convention concludes here: 04-01 (_phase4) registered
    MODEM_RESET; 04-02 (_phase4_02) added USB_RESET; 04-03 (this plan,
    _phase4_03) flips DRIVER_RESET to True. No more renames after this.
    """
    assert is_registered(ActionKind.MODEM_RESET) is True
    assert ActionKind.MODEM_RESET in registered_kinds()
    assert is_registered(ActionKind.USB_RESET) is True
    assert ActionKind.USB_RESET in registered_kinds()
    assert is_registered(ActionKind.DRIVER_RESET) is True
    assert ActionKind.DRIVER_RESET in registered_kinds()


@pytest.mark.asyncio
async def test_dispatch_unknown_kind_returns_failure() -> None:
    """Passing a non-registered kind must return a failure ActionResult.

    No execute() should be invoked; failure_reason carries the canonical
    'action_kind_not_registered:<kind>' string.

    All real ActionKind values are now registered (Plan 04-03 lands
    DRIVER_RESET), so this test fabricates a synthetic enum value via the
    StrEnum machinery to exercise the unregistered-kind path. The fabricated
    kind is NOT placed into _REGISTRY at any point; the dispatcher's
    membership check rejects it cleanly.
    """
    runner = FakeRunner()
    ctx, _logger, _clock = make_ctx(runner)
    # Fabricate an ActionKind value that is NOT in _REGISTRY. StrEnum
    # supports this via the underlying _value2member_map_ -- but the simplest
    # path is to monkey-patch a sentinel into the lookup. Use a synthetic
    # enum-like object that satisfies the .value attribute access.
    fake_kind: ActionKind = ActionKind("set_apn")  # placeholder; will overwrite below

    class _FakeKind:
        value = "synthetic_unregistered_kind"

        def __hash__(self) -> int:
            return hash(self.value)

        def __eq__(self, other: object) -> bool:
            return isinstance(other, _FakeKind) and other.value == self.value

    # Note: ActionKind is a StrEnum; the dispatcher checks 'kind not in _REGISTRY'.
    # _REGISTRY is keyed by ActionKind enum members; a non-member object will
    # always miss the check (dict membership uses __hash__+__eq__).
    fake_kind = _FakeKind()  # type: ignore[assignment]
    result = await execute_and_verify(fake_kind, _who(), ctx)
    assert result.succeeded is False
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("action_kind_not_registered")
    assert "synthetic_unregistered_kind" in result.failure_reason
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
