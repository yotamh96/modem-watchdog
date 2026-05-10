"""Unit tests for policy.decision_table -- (category, detail) -> action.

Covers RECOVERY_SPEC §4 mapping completeness and §5 priority ordering.
The plan-level CI gate `tools/check_spec.py` enforces every row appears
in `tests/test_recovery_spec.py`; these tests cover the in-memory shape.
"""

from __future__ import annotations

from spark_modem.policy.decision_table import (
    SKIP_REQUIRES_HUMAN,
    all_table_rows,
    lookup_action,
    select_top_priority_issue,
)
from spark_modem.wire.diag import Issue, WhoModem
from spark_modem.wire.enums import ActionKind, IssueCategory, IssueDetail


def _issue(
    category: IssueCategory,
    detail: IssueDetail,
) -> Issue:
    return Issue(
        category=category,
        detail=detail,
        who=WhoModem(usb_path="2-3.1.1", cdc_wdm="cdc-wdm0"),
    )


def test_every_decision_table_row_resolves() -> None:
    """Every (category, detail) pair has a non-None action or skip:reason."""
    rows = all_table_rows()
    # Plan 04-02 adds (qmi, sierra_bootloader) -> usb_reset, bringing the
    # row count from >=18 (Plan 04-01) to >=19. Per PATTERNS correction #4:
    # IssueCategory.ENUMERATION does NOT exist; SIERRA_BOOTLOADER lives
    # under IssueCategory.QMI because the modem is observed via QMI failures
    # when stuck in bootloader.
    assert len(rows) >= 19, f"expected >=19 rows; got {len(rows)}"
    for cat, detail in rows:
        result = lookup_action(cat, detail)
        assert result is not None, f"({cat}, {detail}) returned None"


def test_decision_table_has_sierra_bootloader_row() -> None:
    """Plan 04-02 / A-06: (qmi, sierra_bootloader) -> usb_reset.

    The parent-hub variant (per PITFALLS §1.6) is selected via
    ``ActionContext.target="parent-hub"``, which in turn is set either by
    the operator-explicit CLI flag (``spark-modem reset --target=parent-hub``)
    or by future engine logic that infers the variant from the IssueDetail.
    The decision-table row itself just routes to USB_RESET; variant
    selection happens at the action-execution boundary.

    Per PATTERNS correction #4: IssueCategory.ENUMERATION does not exist.
    SIERRA_BOOTLOADER is observed via QMI failures (the modem stuck in
    bootloader does not respond to QMI), so the row lives under
    IssueCategory.QMI -- consistent with the existing decision-table layout.
    """
    assert (
        lookup_action(IssueCategory.QMI, IssueDetail.SIERRA_BOOTLOADER)
        == ActionKind.USB_RESET
    )


def test_apn_empty_maps_to_set_apn() -> None:
    """RECOVERY_SPEC §4: config/apn_empty -> set_apn."""
    assert lookup_action(IssueCategory.CONFIG, IssueDetail.APN_EMPTY) == ActionKind.SET_APN


def test_apn_mismatch_maps_to_set_apn() -> None:
    """RECOVERY_SPEC §4: config/apn_mismatch -> set_apn."""
    assert lookup_action(IssueCategory.CONFIG, IssueDetail.APN_MISMATCH) == ActionKind.SET_APN


def test_sim_app_detected_maps_to_soft_reset() -> None:
    """RECOVERY_SPEC §4: sim/sim_app_detected -> soft_reset."""
    assert (
        lookup_action(IssueCategory.SIM, IssueDetail.SIM_APP_DETECTED)
        == ActionKind.SOFT_RESET
    )


def test_sim_pin_required_maps_to_skip_requires_human() -> None:
    """RECOVERY_SPEC §4: sim/sim_app_pin_required -> skip:requires_human."""
    assert (
        lookup_action(IssueCategory.SIM, IssueDetail.SIM_APP_PIN_REQUIRED)
        == SKIP_REQUIRES_HUMAN
    )


def test_sim_puk_required_maps_to_skip_requires_human() -> None:
    """RECOVERY_SPEC §4: sim/sim_app_puk_required -> skip:requires_human."""
    assert (
        lookup_action(IssueCategory.SIM, IssueDetail.SIM_APP_PUK_REQUIRED)
        == SKIP_REQUIRES_HUMAN
    )


def test_not_registered_searching_maps_to_soft_reset() -> None:
    """RECOVERY_SPEC §4: registration/not_registered_searching -> soft_reset (rung 1)."""
    assert (
        lookup_action(IssueCategory.REGISTRATION, IssueDetail.NOT_REGISTERED_SEARCHING)
        == ActionKind.SOFT_RESET
    )


def test_qmi_channel_hung_maps_to_usb_reset() -> None:
    """RECOVERY_SPEC §4: qmi/qmi_channel_hung -> usb_reset."""
    assert (
        lookup_action(IssueCategory.QMI, IssueDetail.QMI_CHANNEL_HUNG)
        == ActionKind.USB_RESET
    )


def test_priority_ordering_config_beats_sim() -> None:
    """RECOVERY_SPEC §5: config (priority 1) wins over sim (priority 2)."""
    issues = [
        _issue(IssueCategory.SIM, IssueDetail.SIM_APP_DETECTED),
        _issue(IssueCategory.CONFIG, IssueDetail.APN_EMPTY),
    ]
    top = select_top_priority_issue(issues)
    assert top is not None
    assert top.category == IssueCategory.CONFIG


def test_priority_ordering_sim_beats_registration() -> None:
    """RECOVERY_SPEC §5: sim (2) wins over registration (4)."""
    issues = [
        _issue(IssueCategory.REGISTRATION, IssueDetail.NOT_REGISTERED_SEARCHING),
        _issue(IssueCategory.SIM, IssueDetail.SIM_APP_DETECTED),
    ]
    top = select_top_priority_issue(issues)
    assert top is not None
    assert top.category == IssueCategory.SIM


def test_priority_ordering_datapath_beats_qmi() -> None:
    """RECOVERY_SPEC §5: datapath (3) wins over qmi (5)."""
    issues = [
        _issue(IssueCategory.QMI, IssueDetail.QMI_TIMEOUT),
        _issue(IssueCategory.DATAPATH, IssueDetail.RAW_IP_OFF),
    ]
    top = select_top_priority_issue(issues)
    assert top is not None
    assert top.category == IssueCategory.DATAPATH


def test_select_top_priority_returns_none_for_empty_issues() -> None:
    """Empty issues list -> None (no action this cycle)."""
    assert select_top_priority_issue([]) is None


def test_unknown_combination_returns_none() -> None:
    """Cross-category combinations the spec doesn't cover -> None."""
    # CONFIG category + a QMI-only detail is nonsense -- not in the table
    assert lookup_action(IssueCategory.CONFIG, IssueDetail.QMI_TIMEOUT) is None


def test_skip_reasons_are_canonical_strings() -> None:
    """Skip reasons must start with 'skip:' for engine.run_cycle to detect.

    Note: ActionKind is a StrEnum -- isinstance(x, str) is True for both
    ActionKind values and skip:reason plain strings.  Discriminate by
    excluding ActionKind explicitly.
    """
    skip_results: list[str] = []
    for cat, detail in all_table_rows():
        v = lookup_action(cat, detail)
        if isinstance(v, str) and not isinstance(v, ActionKind):
            skip_results.append(v)
    assert len(skip_results) >= 4, f"expected >=4 skip:reason entries; got {skip_results}"
    for s in skip_results:
        assert s.startswith("skip:"), f"skip reason {s!r} must start with 'skip:'"


def test_session_disconnected_maps_to_modem_reset() -> None:
    """RECOVERY_SPEC §4: datapath/session_disconnected -> modem_reset."""
    assert (
        lookup_action(IssueCategory.DATAPATH, IssueDetail.SESSION_DISCONNECTED)
        == ActionKind.MODEM_RESET
    )


def test_operating_mode_offline_maps_to_modem_reset() -> None:
    """RECOVERY_SPEC §4: qmi/operating_mode_offline -> modem_reset."""
    assert (
        lookup_action(IssueCategory.QMI, IssueDetail.OPERATING_MODE_OFFLINE)
        == ActionKind.MODEM_RESET
    )
