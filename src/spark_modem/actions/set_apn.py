"""set_apn -- write profile #1 APN if it differs from the carrier-table value.

FR-30: APN selection by (MCC, MNC) lookup in the carrier table.
FR-31: profile #1 written ONLY when desired APN differs from current
       (read-then-write idempotency).
FR-32: post-write APN verification (read profile back).
FR-33 / NFR-42: new MCC/MNC entries addable without code release.

Sequence:
  1. nas_get_serving_system  -> current (mcc, mnc)
  2. carrier_table.lookup    -> expected APN (or no_carrier failure)
  3. wds_get_profile_settings(1) -> current profile-1 APN
  4. if current == expected: succeed (no write)
  5. wds_modify_profile(1, apn=expected, ip_family=4) -> write
  6. (verify in verify())
"""

from __future__ import annotations

from spark_modem.actions.context import ActionContext
from spark_modem.actions.result import ActionResult, VerifyResult
from spark_modem.actions.verify import verify_apn_equals
from spark_modem.qmi.parsers.get_profile_settings import (
    GetProfileSettingsResult,
    parse_get_profile_settings,
)
from spark_modem.qmi.parsers.get_serving_system import (
    GetServingSystemResult,
    parse_get_serving_system,
)
from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind


async def execute(who: WhoModem, ctx: ActionContext) -> ActionResult:  # noqa: PLR0911
    """Idempotent profile-1 APN write.

    Eight return points reflect the eight distinct outcomes of the
    read-then-write flow (each qmicli error / parse error / lookup miss
    / match-no-write / write-failure / success). Splitting into helpers
    would obscure the strict cycle ordering documented at the top of
    this module.
    """
    start = ctx.clock.monotonic()

    # Step 1: discover current MCC/MNC.
    cp = await ctx.qmi.nas_get_serving_system()
    err = QmiWrapper.classify(cp)
    if err is not None:
        return _fail(who, ctx, start, f"serving_system:{err.reason.value}")
    ss = parse_get_serving_system(cp.stdout)
    if not isinstance(ss, GetServingSystemResult):
        return _fail(who, ctx, start, f"serving_system_parse:{ss.reason.value}")
    if ss.mcc is None or ss.mnc is None:
        return _fail(who, ctx, start, "no_mcc_mnc")

    # Step 2: lookup carrier table.
    entry = ctx.carrier_table.lookup(ss.mcc, ss.mnc)
    if entry is None:
        return _fail(who, ctx, start, f"no_carrier:{ss.mcc}/{ss.mnc}")

    # Step 3: read profile-1; FR-31 -- skip write when match.
    cp = await ctx.qmi.wds_get_profile_settings(profile_index=1)
    err = QmiWrapper.classify(cp)
    if err is not None:
        return _fail(who, ctx, start, f"get_profile:{err.reason.value}")
    prof = parse_get_profile_settings(cp.stdout)
    if isinstance(prof, GetProfileSettingsResult) and prof.apn == entry.apn:
        return _ok(who, ctx, start)

    # Step 4: write profile-1.
    cp = await ctx.qmi.wds_modify_profile(profile_index=1, apn=entry.apn, ip_family=4)
    err = QmiWrapper.classify(cp)
    if err is not None:
        return _fail(who, ctx, start, f"modify_profile:{err.reason.value}")

    return _ok(who, ctx, start)


async def verify(who: WhoModem, ctx: ActionContext) -> VerifyResult:
    """Re-discover MCC/MNC, look up expected APN, verify profile-1 == expected."""
    del who
    cp = await ctx.qmi.nas_get_serving_system()
    err = QmiWrapper.classify(cp)
    if err is not None:
        return VerifyResult.failed(detail=f"serving_system:{err.reason.value}")
    ss = parse_get_serving_system(cp.stdout)
    if not isinstance(ss, GetServingSystemResult):
        return VerifyResult.failed(detail=f"serving_system_parse:{ss.reason.value}")
    if ss.mcc is None or ss.mnc is None:
        return VerifyResult.failed(detail="no_mcc_mnc_for_verify")
    entry = ctx.carrier_table.lookup(ss.mcc, ss.mnc)
    if entry is None:
        return VerifyResult.failed(detail=f"no_carrier_for_verify:{ss.mcc}/{ss.mnc}")
    return await verify_apn_equals(ctx.qmi, entry.apn)


def _ok(who: WhoModem, ctx: ActionContext, start: float) -> ActionResult:
    return ActionResult(
        kind=ActionKind.SET_APN,
        who=who,
        succeeded=True,
        duration_seconds=ctx.clock.monotonic() - start,
        failure_reason=None,
        dry_run=False,
    )


def _fail(who: WhoModem, ctx: ActionContext, start: float, reason: str) -> ActionResult:
    return ActionResult(
        kind=ActionKind.SET_APN,
        who=who,
        succeeded=False,
        duration_seconds=ctx.clock.monotonic() - start,
        failure_reason=reason,
        dry_run=False,
    )
