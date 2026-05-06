"""Shared verify helpers: post-action read-back via qmicli.

Every helper does ONE qmicli call + parse, classifies the result, and
returns ``VerifyResult.ok`` (post-condition observed) or
``VerifyResult.failed`` (read-back error or value mismatch). Helpers do
not raise; "all errors are data" (Phase 1 SP-02 carry-forward).

Per-action verify() functions in this package call one of these helpers
to keep the read-back logic in one place.
"""

from __future__ import annotations

from spark_modem.actions.result import VerifyResult
from spark_modem.qmi.parsers.get_current_settings import (
    GetCurrentSettingsResult,
    parse_get_current_settings,
)
from spark_modem.qmi.parsers.get_operating_mode import (
    GetOperatingModeResult,
    parse_get_operating_mode,
)
from spark_modem.qmi.parsers.get_profile_settings import (
    GetProfileSettingsResult,
    parse_get_profile_settings,
)
from spark_modem.qmi.parsers.get_sim_state import (
    GetSimStateResult,
    parse_get_sim_state,
)
from spark_modem.qmi.wrapper import QmiWrapper


async def verify_apn_equals(qmi: QmiWrapper, expected_apn: str) -> VerifyResult:
    """Read profile-1 APN and compare to expected.

    Returns VerifyResult.ok when the read-back APN equals expected_apn;
    VerifyResult.failed otherwise (qmicli error, parse error, or
    APN mismatch).
    """
    cp = await qmi.wds_get_profile_settings(profile_index=1)
    err = QmiWrapper.classify(cp)
    if err is not None:
        return VerifyResult.failed(detail=f"qmi_error:{err.reason.value}")
    result = parse_get_profile_settings(cp.stdout)
    if not isinstance(result, GetProfileSettingsResult):
        return VerifyResult.failed(detail=f"parse_error:{result.reason.value}")
    if result.apn == expected_apn:
        return VerifyResult.ok(detail=f"apn={expected_apn}")
    return VerifyResult.failed(detail=f"apn={result.apn!r}!={expected_apn!r}")


async def verify_raw_ip_y(qmi: QmiWrapper) -> VerifyResult:
    """Read current settings and confirm raw_ip == 'Y'."""
    cp = await qmi.wds_get_current_settings()
    err = QmiWrapper.classify(cp)
    if err is not None:
        return VerifyResult.failed(detail=f"qmi_error:{err.reason.value}")
    result = parse_get_current_settings(cp.stdout)
    if not isinstance(result, GetCurrentSettingsResult):
        return VerifyResult.failed(detail=f"parse_error:{result.reason.value}")
    if result.raw_ip == "Y":
        return VerifyResult.ok(detail="raw_ip=Y")
    return VerifyResult.failed(detail=f"raw_ip={result.raw_ip!r}")


async def verify_sim_state_not_power_down(qmi: QmiWrapper) -> VerifyResult:
    """Read SIM state and confirm card_state is not 'power_down'.

    The verify-time check is "not power_down" rather than "== ready"
    because uim_sim_power_on is sometimes followed by transient
    intermediate states ('detected', 'init', etc.) before reaching
    'ready'; the action succeeded as long as the card is no longer
    parked in power_down.
    """
    cp = await qmi.uim_get_card_status()
    err = QmiWrapper.classify(cp)
    if err is not None:
        return VerifyResult.failed(detail=f"qmi_error:{err.reason.value}")
    result = parse_get_sim_state(cp.stdout)
    if not isinstance(result, GetSimStateResult):
        return VerifyResult.failed(detail=f"parse_error:{result.reason.value}")
    if result.card_state and result.card_state != "power_down":
        return VerifyResult.ok(detail=f"card_state={result.card_state}")
    return VerifyResult.failed(detail=f"card_state={result.card_state!r}")


async def verify_operating_mode_equals(
    qmi: QmiWrapper,
    expected_mode: str,
) -> VerifyResult:
    """Read operating mode and compare to expected (case-insensitive)."""
    cp = await qmi.dms_get_operating_mode()
    err = QmiWrapper.classify(cp)
    if err is not None:
        return VerifyResult.failed(detail=f"qmi_error:{err.reason.value}")
    result = parse_get_operating_mode(cp.stdout)
    if not isinstance(result, GetOperatingModeResult):
        return VerifyResult.failed(detail=f"parse_error:{result.reason.value}")
    # parse_get_operating_mode lowercases the value; compare lowercased.
    if result.mode == expected_mode.lower():
        return VerifyResult.ok(detail=f"mode={expected_mode}")
    return VerifyResult.failed(detail=f"mode={result.mode!r}!={expected_mode!r}")
