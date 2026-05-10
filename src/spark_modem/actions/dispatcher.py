"""The single execute_and_verify entry point used by both CLI and cycle.

Phase 2 ships only cheap actions in ``_REGISTRY``. Phase 4 adds destructive
actions (modem_reset, usb_reset, driver_reset) by appending entries -- no
other dispatcher code changes. The signal-quality gate (Phase 4) layers
on top via the policy engine before the dispatcher is called; the
dispatcher itself remains action-kind-agnostic.

Dry-run gate (FR-28 / FR-28.1): when ``dry_run=True``, the dispatcher
emits an ActionPlanned event with ``dry_run=True`` and returns a
succeeded ActionResult with ``dry_run=True`` and a deferred
VerifyResult -- no execute() / verify() functions are invoked, no
qmicli calls happen, no sysfs writes happen.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from spark_modem.actions import (
    fix_autosuspend,
    fix_raw_ip,
    modem_reset,
    set_apn,
    set_operating_mode,
    sim_power_on,
    soft_reset,
    usb_reset,
)
from spark_modem.actions.context import ActionContext
from spark_modem.actions.result import ActionResult, VerifyResult
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind
from spark_modem.wire.enums import ActionResult as ActionResultEnum
from spark_modem.wire.events import ActionExecuted, ActionFailed, ActionPlanned

ExecuteFn = Callable[[WhoModem, ActionContext], Awaitable[ActionResult]]
VerifyFn = Callable[[WhoModem, ActionContext], Awaitable[VerifyResult]]


_REGISTRY: dict[ActionKind, tuple[ExecuteFn, VerifyFn]] = {
    ActionKind.SET_APN: (set_apn.execute, set_apn.verify),
    ActionKind.FIX_RAW_IP: (fix_raw_ip.execute, fix_raw_ip.verify),
    ActionKind.SIM_POWER_ON: (sim_power_on.execute, sim_power_on.verify),
    ActionKind.SOFT_RESET: (soft_reset.execute, soft_reset.verify),
    ActionKind.SET_OPERATING_MODE: (set_operating_mode.execute, set_operating_mode.verify),
    ActionKind.FIX_AUTOSUSPEND: (fix_autosuspend.execute, fix_autosuspend.verify),
    ActionKind.MODEM_RESET: (modem_reset.execute, modem_reset.verify),
    ActionKind.USB_RESET: (usb_reset.execute, usb_reset.verify),
}


async def execute_and_verify(
    kind: ActionKind,
    who: WhoModem,
    ctx: ActionContext,
    *,
    dry_run: bool = False,
) -> ActionResult:
    """FR-22: dispatch to the registered execute() then verify() if succeeded.

    FR-28 dry-run gate: when ``dry_run=True``, returns an ActionResult
    with succeeded=True, dry_run=True, verify_result=VerifyResult.deferred(),
    and emits an ActionPlanned event WITHOUT executing.
    """
    if kind not in _REGISTRY:
        return ActionResult(
            kind=kind,
            who=who,
            succeeded=False,
            duration_seconds=0.0,
            failure_reason=f"action_kind_not_registered:{kind.value}",
        )

    # Emit ActionPlanned event before execution (FR-40, NFR-20).
    ctx.event_logger.append(
        ActionPlanned(
            ts_iso=ctx.clock.wall_clock_iso(),
            usb_path=who.usb_path,
            action=kind,
            reason=f"dispatcher:{kind.value}",
            dry_run=dry_run,
        )
    )

    if dry_run:
        return ActionResult(
            kind=kind,
            who=who,
            succeeded=True,
            duration_seconds=0.0,
            verify_result=VerifyResult.deferred(detail="dry_run"),
            dry_run=True,
        )

    fn_exec, fn_verify = _REGISTRY[kind]
    result = await fn_exec(who, ctx)

    if result.succeeded:
        verify = await fn_verify(who, ctx)
        result = result.with_verify(verify)

    # Emit ActionExecuted (succeeded) or ActionFailed.
    if result.succeeded:
        ctx.event_logger.append(
            ActionExecuted(
                ts_iso=ctx.clock.wall_clock_iso(),
                usb_path=who.usb_path,
                action=kind,
                result=ActionResultEnum.SUCCESS,
                duration_seconds=result.duration_seconds,
            )
        )
    else:
        ctx.event_logger.append(
            ActionFailed(
                ts_iso=ctx.clock.wall_clock_iso(),
                usb_path=who.usb_path,
                action=kind,
                failure_reason=result.failure_reason or "unknown",
            )
        )

    return result


def is_registered(kind: ActionKind) -> bool:
    """True iff ``kind`` has an entry in ``_REGISTRY``."""
    return kind in _REGISTRY


def registered_kinds() -> frozenset[ActionKind]:
    """Snapshot of every ActionKind currently registered."""
    return frozenset(_REGISTRY.keys())
