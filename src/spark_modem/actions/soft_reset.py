"""soft_reset -- single qmicli reset call. Verify is DEFERRED (next-cycle).

The soft-reset effect is the modem coming back online with a fresh
registration / SIM session. We CANNOT verify inline because the modem
is rebooting. ``verify()`` returns ``VerifyResult.deferred()`` and the
next-cycle observation surfaces the result.

Implementation: ``--dms-set-operating-mode=reset``. On Sierra firmware
(EM7421) this is the canonical single-pass reset that is NOT a
destructive modem_reset (which Phase 4 will register separately with
a signal-quality gate).
"""

from __future__ import annotations

from spark_modem.actions.context import ActionContext
from spark_modem.actions.result import ActionResult, VerifyResult
from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind


async def execute(who: WhoModem, ctx: ActionContext) -> ActionResult:
    start = ctx.clock.monotonic()
    cp = await ctx.qmi.dms_set_operating_mode("reset")
    err = QmiWrapper.classify(cp)
    if err is not None:
        return ActionResult(
            kind=ActionKind.SOFT_RESET,
            who=who,
            succeeded=False,
            duration_seconds=ctx.clock.monotonic() - start,
            failure_reason=f"soft_reset:{err.reason.value}",
            dry_run=False,
        )
    return ActionResult(
        kind=ActionKind.SOFT_RESET,
        who=who,
        succeeded=True,
        duration_seconds=ctx.clock.monotonic() - start,
        failure_reason=None,
        dry_run=False,
    )


async def verify(who: WhoModem, ctx: ActionContext) -> VerifyResult:
    """Deferred -- next-cycle observation surfaces the actual outcome."""
    del who, ctx
    return VerifyResult.deferred(detail="next_cycle_observation")
