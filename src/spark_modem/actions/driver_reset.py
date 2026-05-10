"""driver_reset -- modprobe -r qmi_wwan && modprobe qmi_wwan. Verify is DEFERRED.

Plan 04-03 (Phase 4) introduces this destructive action. RECOVERY_SPEC §6.4:
when ≥75% of the fleet is QMI-hung AND at least one hung modem has actionable
signal AND no thermal warning is active AND we are past the 3600 s cooldown,
the engine plans a single global driver_reset.

Per CONTEXT A-03: two ``subproc.run`` calls in sequence:
  1. ``["modprobe", "-r", "qmi_wwan"]``
  2. ``["modprobe", "qmi_wwan"]``

Idempotent at the invocation level (A-05): a second back-to-back run finds
the module already removed/loaded, so the second invocation is a no-op.
auto-handles dependencies (cdc_wdm, cdc_ncm) via libkmod.

Per PATTERNS correction #1: ``ActionContext`` does NOT have a ``runner`` field.
This module imports ``run`` from ``spark_modem.subproc.runner`` directly. SP-04
lint passes because ``subproc.runner`` is the sanctioned subprocess wrapper
module.

Per PATTERNS Cross-Cutting #10: dispatcher signature requires ``WhoModem``,
but driver_reset is host-scoped -- the engine constructs a synthetic
``WhoModem(usb_path="host", cdc_wdm=None)`` for the registry call. The
action's body uses ``who`` only for the ActionResult.who field.

Stderr classifier (PITFALLS §1.1, kmod tools/modprobe.c lines 731 / 816 / 876):
  - ``"in use"`` (case-insensitive) on unload -> module is currently in use;
    do NOT attempt load (would just re-fire). Returns
    ``failure_reason="driver_reset:module_in_use"``.
  - ``"not found"`` / ``"module not in kernel"`` / other unload non-zero exit
    codes -> already-removed (idempotency, A-05); PROCEED to load.
  - load non-zero -> ``failure_reason=f"driver_reset:load_exit_{exit_code}"``.

verify() returns ``VerifyResult.deferred(detail="next_cycle_observation")``
unconditionally (A-04) -- the module is reloading, in-line read-back is
impossible. The next-cycle observation surfaces the actual outcome.

CAP_SYS_MODULE preallocated by Plan 03-08 U-01.
"""

from __future__ import annotations

from spark_modem.actions.context import ActionContext
from spark_modem.actions.result import ActionResult, VerifyResult
from spark_modem.subproc.runner import run as subproc_run
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind

_UNLOAD_ARGV = ["modprobe", "-r", "qmi_wwan"]
_LOAD_ARGV = ["modprobe", "qmi_wwan"]


async def execute(who: WhoModem, ctx: ActionContext) -> ActionResult:
    start = ctx.clock.monotonic()
    timeout_s = float(ctx.config.modprobe_timeout_seconds)

    cp_unload = await subproc_run(_UNLOAD_ARGV, timeout_s=timeout_s)
    if cp_unload.exit_code != 0:
        stderr_lc = cp_unload.stderr.lower()
        if b"in use" in stderr_lc:
            return ActionResult(
                kind=ActionKind.DRIVER_RESET,
                who=who,
                succeeded=False,
                duration_seconds=ctx.clock.monotonic() - start,
                failure_reason="driver_reset:module_in_use",
                dry_run=False,
            )
        # 'not found' / 'module not in kernel' / other non-zero -> proceed
        # to load for idempotency (A-05). Falling through.

    cp_load = await subproc_run(_LOAD_ARGV, timeout_s=timeout_s)
    if cp_load.exit_code != 0:
        return ActionResult(
            kind=ActionKind.DRIVER_RESET,
            who=who,
            succeeded=False,
            duration_seconds=ctx.clock.monotonic() - start,
            failure_reason=f"driver_reset:load_exit_{cp_load.exit_code}",
            dry_run=False,
        )

    return ActionResult(
        kind=ActionKind.DRIVER_RESET,
        who=who,
        succeeded=True,
        duration_seconds=ctx.clock.monotonic() - start,
        failure_reason=None,
        dry_run=False,
    )


async def verify(who: WhoModem, ctx: ActionContext) -> VerifyResult:
    """Deferred -- next-cycle observation surfaces the actual outcome (A-04)."""
    del who, ctx
    return VerifyResult.deferred(detail="next_cycle_observation")
