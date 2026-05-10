"""usb_reset -- destructive USB unbind+rebind via sysfs. Verify is DEFERRED.

Plan 04-02 (Phase 4) introduces this destructive action. RECOVERY_SPEC §4.1
escalation ladder rung 3: when soft_reset and modem_reset have been
exhausted (or for SC#4 QMI-channel-hung modems where USB-side recovery is
the canonical fix), the engine promotes to usb_reset.

Per CONTEXT A-02: file I/O ONLY. No qmicli, no subprocess. The action
delegates to ``spark_modem.sysfs.unbind_rebind`` which writes the modem's
bus-port path to ``/sys/bus/usb/drivers/usb/{unbind,bind}``. SP-04 lint
scope is unchanged because file writes are not subprocess invocations.

Per CONTEXT A-06 / PITFALLS §1.6: two variants selected via ``ctx.target``:
  - "child-port" (default): unbinds and rebinds the modem's leaf bus-port
    (e.g. ``"2-3.1.1"``). Recovers SC#4 QMI-hung modems.
  - "parent-hub": unbinds and rebinds the parent USB hub
    (``usb_path.rsplit('.', 1)[0]``). Re-fires the Sierra EM7421 boot
    transition for IssueDetail.SIERRA_BOOTLOADER (1199:9051 stuck-in-
    bootloader); a child-port reset alone may not unstick the modem.

verify() returns ``VerifyResult.deferred(detail="next_cycle_observation")``
unconditionally (CONTEXT A-04) -- the modem is re-enumerating, in-line
read-back is impossible. The next-cycle observation surfaces the actual
outcome to the policy engine.

Failure surface: any OSError from the sysfs write is caught and surfaced
as ``failure_reason="usb_reset:sysfs_write_error:<errno>"``. The errno
integer (EBUSY=16, EACCES=13, ENOENT=2, ENODEV=19, ...) is part of the
public POSIX surface; operators use it for diagnosis.

CAP_SYS_ADMIN preallocated by Plan 03-08 U-01.
"""

from __future__ import annotations

from spark_modem.actions.context import ActionContext
from spark_modem.actions.result import ActionResult, VerifyResult
from spark_modem.sysfs import unbind_rebind
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind


async def execute(who: WhoModem, ctx: ActionContext) -> ActionResult:
    start = ctx.clock.monotonic()
    try:
        await unbind_rebind(
            who.usb_path,
            target=ctx.target,
            sysfs_root=ctx.sysfs_root,
        )
    except OSError as exc:
        return ActionResult(
            kind=ActionKind.USB_RESET,
            who=who,
            succeeded=False,
            duration_seconds=ctx.clock.monotonic() - start,
            failure_reason=f"usb_reset:sysfs_write_error:{exc.errno}",
            dry_run=False,
        )
    return ActionResult(
        kind=ActionKind.USB_RESET,
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
