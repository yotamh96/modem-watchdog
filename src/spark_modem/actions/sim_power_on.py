"""sim_power_on -- qmicli --uim-sim-power-on=1.

Re-energises the SIM application; recovers SIM_POWER_DOWN /
SIM_APP_DETECTED states (RECOVERY_SPEC §4 sim/sim_power_down).

This action is NOT idempotent in the read-then-write sense -- the SIM
power-on call is the cheap recovery itself, and qmicli accepts re-issuing
it on an already-powered SIM (returns immediately). The verify step
re-reads card_state to confirm the SIM is no longer power_down.
"""

from __future__ import annotations

from spark_modem.actions.context import ActionContext
from spark_modem.actions.result import ActionResult, VerifyResult
from spark_modem.actions.verify import verify_sim_state_not_power_down
from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind


async def execute(who: WhoModem, ctx: ActionContext) -> ActionResult:
    start = ctx.clock.monotonic()
    cp = await ctx.qmi.uim_sim_power_on(slot=1)
    err = QmiWrapper.classify(cp)
    if err is not None:
        return ActionResult(
            kind=ActionKind.SIM_POWER_ON,
            who=who,
            succeeded=False,
            duration_seconds=ctx.clock.monotonic() - start,
            failure_reason=f"sim_power_on:{err.reason.value}",
            dry_run=False,
        )
    return ActionResult(
        kind=ActionKind.SIM_POWER_ON,
        who=who,
        succeeded=True,
        duration_seconds=ctx.clock.monotonic() - start,
        failure_reason=None,
        dry_run=False,
    )


async def verify(who: WhoModem, ctx: ActionContext) -> VerifyResult:
    del who
    return await verify_sim_state_not_power_down(ctx.qmi)
