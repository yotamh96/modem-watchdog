"""modem_reset -- ladder rung 2 destructive action; deferred-verify.

RECOVERY_SPEC §4.1 escalation ladder rung 2: when soft_reset has been
exhausted (counter at MAX_SOFT) and the issue category is REGISTRATION
or DATAPATH/SESSION_DISCONNECTED, the engine promotes to modem_reset.

Per Phase 4 CONTEXT A-01 ("modem_reset is a policy distinction, not a
protocol distinction"), this action issues the SAME qmicli verb as
soft_reset -- ``--dms-set-operating-mode=reset``. Sierra firmware
(EM7421) does not expose a "harder" DMS reset variant; the difference
between the two ladder rungs is operational:

  - Signal-gated: gate_signal in the policy engine refuses modem_reset
    when RSRP/RSRQ/SNR fall below the configured floors (FR-23).
    soft_reset is NOT signal-gated.
  - Ladder rung: rung 2 vs rung 1 (RECOVERY_SPEC §4.1).
  - Expected outage envelope: ~30-60 s vs ~5 s.

verify() returns ``VerifyResult.deferred(detail="next_cycle_observation")``
unconditionally (CONTEXT A-04) -- the modem is rebooting, in-line
read-back is impossible. The next-cycle observation surfaces the actual
outcome to the policy engine.

Plan 04-01 ships the action; signal-gating + ladder progression land
in Plan 04-04.
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
            kind=ActionKind.MODEM_RESET,
            who=who,
            succeeded=False,
            duration_seconds=ctx.clock.monotonic() - start,
            failure_reason=f"modem_reset:{err.reason.value}",
            dry_run=False,
        )
    return ActionResult(
        kind=ActionKind.MODEM_RESET,
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
