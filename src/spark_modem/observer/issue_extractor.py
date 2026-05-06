"""Issue extractor - turns QMI parser output into a list of typed Issues.

Maps to RECOVERY_SPEC §4 issue identifiers per IssueCategory / IssueDetail.
``extract_issues`` is a pure function (no I/O); ``probe_modem_to_snapshot``
DOES do I/O (qmicli queries through QmiWrapper) and routes the parsed
results through ``extract_issues`` to produce a single ModemSnapshot.

Cross-source detections (apn_mismatch, qmi_channel_hung) are NOT done here
-- they require the carrier table or fleet-wide aggregation that lives in
plan 02-05 (policy/). The observer surfaces only per-modem facts.
"""

from __future__ import annotations

from typing import Protocol

from spark_modem.inventory.descriptor import ModemDescriptor
from spark_modem.qmi.errors import QmiError, QmiErrorReason
from spark_modem.qmi.parsers.get_current_settings import (
    GetCurrentSettingsResult,
    parse_get_current_settings,
)
from spark_modem.qmi.parsers.get_data_session import (
    GetDataSessionResult,
    parse_get_data_session,
)
from spark_modem.qmi.parsers.get_operating_mode import (
    GetOperatingModeResult,
    parse_get_operating_mode,
)
from spark_modem.qmi.parsers.get_profile_settings import (
    GetProfileSettingsResult,
    parse_get_profile_settings,
)
from spark_modem.qmi.parsers.get_serving_system import (
    GetServingSystemResult,
    parse_get_serving_system,
)
from spark_modem.qmi.parsers.get_signal import GetSignalResult, parse_get_signal
from spark_modem.qmi.parsers.get_sim_state import (
    GetSimStateResult,
    parse_get_sim_state,
)
from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.subproc.result import CompletedProcess
from spark_modem.wire.diag import (
    Issue,
    ModemSnapshot,
    SignalSnapshot,
    WhoModem,
)
from spark_modem.wire.enums import IssueCategory, IssueDetail, RegistrationState


class ClockProto(Protocol):
    """Subset of the Clock surface this module needs (test-shimmable)."""

    def monotonic(self) -> float: ...
    def wall_clock_iso(self) -> str: ...


async def probe_modem_to_snapshot(
    modem: ModemDescriptor,
    qmi: QmiWrapper,
    clock: ClockProto,
) -> ModemSnapshot:
    """Run all qmicli queries for one modem and build a ModemSnapshot.

    I/O lives here (qmicli invocations). Issue extraction is pure
    (``extract_issues``). Within-modem queries run sequentially because
    qmicli holds a per-device lock; the TaskGroup in
    ``observer/orchestrator`` parallelises ACROSS modems (ARCH §4.3).
    """
    del clock  # reserved for last_action_monotonic in policy/; unused here.

    cp_signal = await qmi.nas_get_signal_info()
    cp_serving = await qmi.nas_get_serving_system()
    cp_sim = await qmi.uim_get_card_status()
    cp_data = await qmi.wds_get_packet_service_status()
    cp_profile = await qmi.wds_get_profile_settings(profile_index=1)
    cp_settings = await qmi.wds_get_current_settings()
    cp_op = await qmi.dms_get_operating_mode()

    sig = _safe_parse_signal(cp_signal)
    ss = _safe_parse_serving(cp_serving)
    sim = _safe_parse_sim(cp_sim)
    data = _safe_parse_data(cp_data)
    prof = _safe_parse_profile(cp_profile)
    cur = _safe_parse_current(cp_settings)
    op = _safe_parse_op(cp_op)

    signal_snap = (
        SignalSnapshot(
            rssi_dbm=sig.rssi_dbm,
            rsrp_dbm=sig.rsrp_dbm,
            rsrq_db=sig.rsrq_db,
            snr_db=sig.snr_db,
        )
        if isinstance(sig, GetSignalResult)
        else SignalSnapshot()
    )

    registration = ss.registration_state if isinstance(ss, GetServingSystemResult) else None
    mcc = ss.mcc if isinstance(ss, GetServingSystemResult) else None
    mnc = ss.mnc if isinstance(ss, GetServingSystemResult) else None
    sim_state = sim.app_state if isinstance(sim, GetSimStateResult) else None
    operating_mode = op.mode if isinstance(op, GetOperatingModeResult) else None

    issues = extract_issues(
        modem=modem,
        signal=signal_snap,
        registration=registration,
        sim=sim,
        data=data,
        profile=prof,
        current=cur,
        operating=op,
    )

    return ModemSnapshot(
        usb_path=modem.usb_path,
        cdc_wdm=modem.cdc_wdm,
        operating_mode=operating_mode,
        sim_state=sim_state,
        registration=registration,
        mcc=mcc,
        mnc=mnc,
        signal=signal_snap,
        issues=issues,
    )


# Per-parser type-safe _safe_parse helpers. mypy --strict cannot infer the
# correct return type from a single generic helper because each parser has a
# distinct success type, so we keep them separate.


def _classify_or_none(cp: CompletedProcess) -> QmiError | None:
    return QmiWrapper.classify(cp)


def _safe_parse_signal(cp: CompletedProcess) -> GetSignalResult | QmiError:
    err = _classify_or_none(cp)
    if err is not None:
        return err
    return parse_get_signal(cp.stdout)


def _safe_parse_serving(cp: CompletedProcess) -> GetServingSystemResult | QmiError:
    err = _classify_or_none(cp)
    if err is not None:
        return err
    return parse_get_serving_system(cp.stdout)


def _safe_parse_sim(cp: CompletedProcess) -> GetSimStateResult | QmiError:
    err = _classify_or_none(cp)
    if err is not None:
        return err
    return parse_get_sim_state(cp.stdout)


def _safe_parse_data(cp: CompletedProcess) -> GetDataSessionResult | QmiError:
    err = _classify_or_none(cp)
    if err is not None:
        return err
    return parse_get_data_session(cp.stdout)


def _safe_parse_profile(cp: CompletedProcess) -> GetProfileSettingsResult | QmiError:
    err = _classify_or_none(cp)
    if err is not None:
        return err
    return parse_get_profile_settings(cp.stdout)


def _safe_parse_current(cp: CompletedProcess) -> GetCurrentSettingsResult | QmiError:
    err = _classify_or_none(cp)
    if err is not None:
        return err
    return parse_get_current_settings(cp.stdout)


def _safe_parse_op(cp: CompletedProcess) -> GetOperatingModeResult | QmiError:
    err = _classify_or_none(cp)
    if err is not None:
        return err
    return parse_get_operating_mode(cp.stdout)


def extract_issues(  # noqa: PLR0912 - one branch per RECOVERY_SPEC §4 row by design
    *,
    modem: ModemDescriptor,
    signal: SignalSnapshot,
    registration: RegistrationState | None,
    sim: GetSimStateResult | QmiError,
    data: GetDataSessionResult | QmiError,
    profile: GetProfileSettingsResult | QmiError,
    current: GetCurrentSettingsResult | QmiError,
    operating: GetOperatingModeResult | QmiError,
) -> list[Issue]:
    """Pure function: ModemSnapshot fields -> list[Issue] per RECOVERY_SPEC §4.

    The full §4 decision-table coverage lives here; the policy engine in
    plan 02-05 maps Issue -> ActionKind. This function only DETECTS issues;
    it does not decide actions.

    Cross-source detections (apn_mismatch, qmi_channel_hung) live in
    policy/ -- they require the carrier table or fleet-wide aggregation
    not available to the observer.
    """
    del signal  # signal-quality is gated in policy/; observer surfaces it via SignalSnapshot
    who = WhoModem(usb_path=modem.usb_path, cdc_wdm=modem.cdc_wdm)
    issues: list[Issue] = []

    # --- config (priority 1) -------------------------------------------
    if isinstance(profile, GetProfileSettingsResult) and (profile.apn is None or profile.apn == ""):
        issues.append(
            Issue(
                category=IssueCategory.CONFIG,
                detail=IssueDetail.APN_EMPTY,
                who=who,
                description="profile-1 APN is empty",
            )
        )
        # apn_mismatch detection requires carrier-table lookup; that lives
        # in policy/decision_table.py (cross-source; observer reports the
        # raw fact; policy decides the mismatch).

    # --- sim (priority 2) ----------------------------------------------
    if isinstance(sim, GetSimStateResult):
        if sim.card_state == "absent":
            issues.append(
                Issue(category=IssueCategory.SIM, detail=IssueDetail.SIM_CARD_ABSENT, who=who)
            )
        elif sim.card_state == "error":
            issues.append(
                Issue(category=IssueCategory.SIM, detail=IssueDetail.SIM_CARD_ERROR, who=who)
            )
        elif sim.card_state == "power_down":
            issues.append(
                Issue(category=IssueCategory.SIM, detail=IssueDetail.SIM_POWER_DOWN, who=who)
            )
        elif sim.card_state == "unreadable":
            issues.append(
                Issue(category=IssueCategory.SIM, detail=IssueDetail.SIM_CARD_UNREADABLE, who=who)
            )
        if sim.app_state == "detected":
            issues.append(
                Issue(category=IssueCategory.SIM, detail=IssueDetail.SIM_APP_DETECTED, who=who)
            )
        elif sim.app_state == "pin_required":
            issues.append(
                Issue(category=IssueCategory.SIM, detail=IssueDetail.SIM_APP_PIN_REQUIRED, who=who)
            )
        elif sim.app_state == "puk_required":
            issues.append(
                Issue(category=IssueCategory.SIM, detail=IssueDetail.SIM_APP_PUK_REQUIRED, who=who)
            )
        elif sim.app_state == "unreadable":
            issues.append(
                Issue(category=IssueCategory.SIM, detail=IssueDetail.SIM_APP_UNREADABLE, who=who)
            )

    # --- datapath (priority 3) -----------------------------------------
    if isinstance(current, GetCurrentSettingsResult) and current.raw_ip == "N":
        issues.append(
            Issue(category=IssueCategory.DATAPATH, detail=IssueDetail.RAW_IP_OFF, who=who)
        )
    # WR-06 (Phase 2 review): only the literal "disconnected" status surfaces
    # SESSION_DISCONNECTED.  libqmi has emitted intermediate states such as
    # "limited" or "flow-controlled" since 1.30, but the policy decision-table
    # has no actionable response to those (they are transient and self-clear
    # within a cycle or two).  The behaviour is pinned by
    # tests/unit/observer/test_orchestrator.py
    # ::test_extract_issues_intermediate_data_states_do_not_surface so a
    # future libqmi change that introduces yet another intermediate state
    # does not silently drift into / out of the issue stream.
    if isinstance(data, GetDataSessionResult) and data.connection_status == "disconnected":
        issues.append(
            Issue(
                category=IssueCategory.DATAPATH,
                detail=IssueDetail.SESSION_DISCONNECTED,
                who=who,
            )
        )

    # --- registration (priority 4) -------------------------------------
    if registration == RegistrationState.NOT_REGISTERED_SEARCHING:
        issues.append(
            Issue(
                category=IssueCategory.REGISTRATION,
                detail=IssueDetail.NOT_REGISTERED_SEARCHING,
                who=who,
            )
        )
    elif registration == RegistrationState.NOT_REGISTERED_IDLE:
        issues.append(
            Issue(
                category=IssueCategory.REGISTRATION,
                detail=IssueDetail.NOT_REGISTERED_IDLE,
                who=who,
            )
        )
    elif registration == RegistrationState.NOT_REGISTERED_DENIED:
        issues.append(
            Issue(
                category=IssueCategory.REGISTRATION,
                detail=IssueDetail.DENIED,
                who=who,
            )
        )

    # --- qmi (priority 5) ----------------------------------------------
    if isinstance(sim, QmiError) and sim.reason == QmiErrorReason.PROXY_DIED:
        issues.append(Issue(category=IssueCategory.QMI, detail=IssueDetail.QMI_PROXY_DIED, who=who))
    if isinstance(sim, QmiError) and sim.reason == QmiErrorReason.TIMEOUT:
        issues.append(Issue(category=IssueCategory.QMI, detail=IssueDetail.QMI_TIMEOUT, who=who))
    # qmi_channel_hung is detected by policy/ when >=75% of modems report
    # qmi failures -- observer surfaces the per-modem fact only.
    if isinstance(operating, GetOperatingModeResult):
        if operating.mode == "offline":
            issues.append(
                Issue(
                    category=IssueCategory.QMI,
                    detail=IssueDetail.OPERATING_MODE_OFFLINE,
                    who=who,
                )
            )
        elif operating.mode == "low_power":
            issues.append(
                Issue(
                    category=IssueCategory.QMI,
                    detail=IssueDetail.OPERATING_MODE_LOW_POWER,
                    who=who,
                )
            )

    return issues
