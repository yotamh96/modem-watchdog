"""set_operating_mode -- DMS set operating mode (idempotent: read-then-write).

Used to push out of low_power / offline. The Phase 2 target is always
``online`` -- the policy engine selects this action only when the
observed mode is NOT online (RECOVERY_SPEC §4 qmi/operating_mode_*).

Idempotent: reads ``dms-get-operating-mode`` first; if already 'online'
the action is a no-op (FR-31).
"""

from __future__ import annotations

from spark_modem.actions.context import ActionContext
from spark_modem.actions.result import ActionResult, VerifyResult
from spark_modem.actions.verify import verify_operating_mode_equals
from spark_modem.qmi.parsers.get_operating_mode import (
    GetOperatingModeResult,
    parse_get_operating_mode,
)
from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind

_TARGET_MODE = "online"


async def execute(who: WhoModem, ctx: ActionContext) -> ActionResult:
    start = ctx.clock.monotonic()
    cp = await ctx.qmi.dms_get_operating_mode()
    err = QmiWrapper.classify(cp)
    if err is not None:
        return _fail(who, ctx, start, f"get_op_mode:{err.reason.value}")
    op = parse_get_operating_mode(cp.stdout)
    # parse_get_operating_mode lowercases; compare lowercased.
    if isinstance(op, GetOperatingModeResult) and op.mode == _TARGET_MODE:
        return _ok(who, ctx, start)
    cp = await ctx.qmi.dms_set_operating_mode(_TARGET_MODE)
    err = QmiWrapper.classify(cp)
    if err is not None:
        return _fail(who, ctx, start, f"set_op_mode:{err.reason.value}")
    return _ok(who, ctx, start)


async def verify(who: WhoModem, ctx: ActionContext) -> VerifyResult:
    del who
    return await verify_operating_mode_equals(ctx.qmi, _TARGET_MODE)


def _ok(who: WhoModem, ctx: ActionContext, start: float) -> ActionResult:
    return ActionResult(
        kind=ActionKind.SET_OPERATING_MODE,
        who=who,
        succeeded=True,
        duration_seconds=ctx.clock.monotonic() - start,
        failure_reason=None,
        dry_run=False,
    )


def _fail(who: WhoModem, ctx: ActionContext, start: float, reason: str) -> ActionResult:
    return ActionResult(
        kind=ActionKind.SET_OPERATING_MODE,
        who=who,
        succeeded=False,
        duration_seconds=ctx.clock.monotonic() - start,
        failure_reason=reason,
        dry_run=False,
    )
