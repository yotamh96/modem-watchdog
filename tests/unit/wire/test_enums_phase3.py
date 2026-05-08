"""Phase 3 IssueDetail extension contract tests (D-03 / E-03).

The 5+1 host-level values are LOCKED per CONTEXT.md E-03; this test
file is the contract gate. Phase 4 may add more values (Phase 4
destructive-action gating reads from this set), but these six MUST
remain.

Threat T-03-01-02 mitigation: closed-enum discipline (W-04) — the
contract test gates any free-form string entering ``Issue.detail``.
"""

from __future__ import annotations

from spark_modem.wire.enums import IssueDetail

_PHASE3_HOST_VALUES = frozenset(
    {
        "usb_overcurrent",
        "usb_enum_failure",
        "thermal_throttle",
        "qmi_wwan_probe_fail",
        "tegra_hub_psu_droop",
        "unknown",
    }
)


def test_phase3_host_values_present() -> None:
    """E-03: All five host-level values + UNKNOWN fallback must exist."""
    actual = {member.value for member in IssueDetail}
    missing = _PHASE3_HOST_VALUES - actual
    assert not missing, f"Phase 3 IssueDetail values missing: {missing}"


def test_usb_overcurrent_distinct_from_enumeration_overcurrent() -> None:
    """Closed-enum discipline (W-04) — host-level vs. per-modem are DIFFERENT.

    Conflating these would let a hub-PSU droop suppress per-modem
    usb_reset decisions in Phase 4 incorrectly. USB_OVERCURRENT is
    classified from kmsg (host-wide); ENUMERATION_OVERCURRENT is a
    per-modem enumeration-time event from sysfs/qmicli.
    """
    assert IssueDetail.USB_OVERCURRENT != IssueDetail.ENUMERATION_OVERCURRENT
    assert IssueDetail.USB_OVERCURRENT.value == "usb_overcurrent"
    assert IssueDetail.ENUMERATION_OVERCURRENT.value == "enumeration_overcurrent"


def test_unknown_is_kmsg_fallback_value() -> None:
    """E-03 fallback semantics: classifier returns UNKNOWN when no regex matches.

    The raw kmsg line is preserved in a separate forensic field —
    never enters the ``detail`` field (T-03-01-02 information-disclosure
    mitigation).
    """
    assert IssueDetail.UNKNOWN.value == "unknown"
