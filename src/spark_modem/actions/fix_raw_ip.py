"""fix_raw_ip -- set raw_ip=Y when current settings report N.

Reads ``wds-get-current-settings`` first; if raw_ip is already 'Y' the
action is a no-op (FR-31 idempotency). Otherwise writes via the typed
``QmiWrapper.wds_set_ip_family(family=4)`` method, which preserves the
typed boundary so actions/ never reaches into the wrapper's private
runner attribute.
"""

from __future__ import annotations

from spark_modem.actions.context import ActionContext
from spark_modem.actions.result import ActionResult, VerifyResult
from spark_modem.actions.verify import verify_raw_ip_y
from spark_modem.qmi.parsers.get_current_settings import (
    GetCurrentSettingsResult,
    parse_get_current_settings,
)
from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind


async def execute(who: WhoModem, ctx: ActionContext) -> ActionResult:
    start = ctx.clock.monotonic()

    # Read first; if already Y, no-op.
    cp = await ctx.qmi.wds_get_current_settings()
    err = QmiWrapper.classify(cp)
    if err is not None:
        return _fail(who, ctx, start, f"get_settings:{err.reason.value}")
    cur = parse_get_current_settings(cp.stdout)
    if isinstance(cur, GetCurrentSettingsResult) and cur.raw_ip == "Y":
        return _ok(who, ctx, start)

    # Write: forces raw-IP mode for IPv4 via the typed wrapper method.
    cp = await ctx.qmi.wds_set_ip_family(family=4)
    err = QmiWrapper.classify(cp)
    if err is not None:
        return _fail(who, ctx, start, f"set_ip_family:{err.reason.value}")

    return _ok(who, ctx, start)


async def verify(who: WhoModem, ctx: ActionContext) -> VerifyResult:
    del who
    return await verify_raw_ip_y(ctx.qmi)


def _ok(who: WhoModem, ctx: ActionContext, start: float) -> ActionResult:
    return ActionResult(
        kind=ActionKind.FIX_RAW_IP,
        who=who,
        succeeded=True,
        duration_seconds=ctx.clock.monotonic() - start,
        failure_reason=None,
        dry_run=False,
    )


def _fail(who: WhoModem, ctx: ActionContext, start: float, reason: str) -> ActionResult:
    return ActionResult(
        kind=ActionKind.FIX_RAW_IP,
        who=who,
        succeeded=False,
        duration_seconds=ctx.clock.monotonic() - start,
        failure_reason=reason,
        dry_run=False,
    )
