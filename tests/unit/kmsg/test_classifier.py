"""Tests for spark_modem.kmsg.classifier (Plan 03-05).

Pins the closed-enum contract (E-03 LOCKED at 5 host-level IssueDetail
values + UNKNOWN). Adding a 6th regex requires touching:
  - IssueDetail enum (Plan 03-01 Task 2 already extended it)
  - KMSG_PATTERNS table size
  - this test file's count assertion

Forcing the developer to update the count assertion is the contract gate
that makes accidental enum additions visible — CONTEXT.md "Deferred
Ideas" routes growth through ADR or Phase 4 follow-up.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from spark_modem.kmsg.classifier import KMSG_PATTERNS, classify
from spark_modem.wire.enums import IssueDetail

_FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures" / "kmsg"


def test_classify_returns_unknown_on_unrecognized_line() -> None:
    """Lines that match no regex map to UNKNOWN (E-03 fallback)."""
    assert classify("totally unrelated kernel log line") == IssueDetail.UNKNOWN


@pytest.mark.parametrize(
    ("fixture_name", "expected"),
    [
        ("usb_overcurrent.log", IssueDetail.USB_OVERCURRENT),
        ("usb_enum_failure.log", IssueDetail.USB_ENUM_FAILURE),
        ("thermal_throttle.log", IssueDetail.THERMAL_THROTTLE),
        ("qmi_wwan_probe_fail.log", IssueDetail.QMI_WWAN_PROBE_FAIL),
        ("tegra_hub_psu_droop.log", IssueDetail.TEGRA_HUB_PSU_DROOP),
    ],
)
def test_classify_fixture(fixture_name: str, expected: IssueDetail) -> None:
    """Each one-line fixture classifies to the expected IssueDetail value."""
    content = (_FIXTURES_DIR / fixture_name).read_text(encoding="utf-8").strip()
    assert classify(content) == expected


def test_kmsg_patterns_table_size_locked_at_5() -> None:
    """Catalog size is 5 (E-03 LOCKED).

    Adding a 6th regex requires deliberate edit here, which forces the
    developer to also update the IssueDetail enum and the test file.
    Per CONTEXT.md Deferred Ideas, catalog growth lands via ADR or
    Phase 4 follow-up — never as a silent one-line edit.
    """
    assert len(KMSG_PATTERNS) == 5


def test_classify_returns_first_match_when_overlapping() -> None:
    """Deterministic order: first matching pattern wins.

    Construct a synthetic line that contains BOTH the
    'device not accepting address' substring AND the 'over-current ... on
    port' substring. KMSG_PATTERNS lists USB_ENUM_FAILURE first (per the
    table order in the source), so it MUST win. This pins the iteration
    order behavior; reordering the table without thinking through this
    is the kind of change a reviewer should notice.
    """
    line = "usb 1-3: device not accepting address; over-current change on port 1"
    assert classify(line) == IssueDetail.USB_ENUM_FAILURE


def test_unknown_value_distinct_from_other_values() -> None:
    """UNKNOWN is the fallback — never a value any pattern maps to.

    W-04 closed-enum discipline: UNKNOWN means "I have no opinion;
    forensic preservation only." If any KMSG_PATTERNS entry mapped to
    UNKNOWN, the producer would emit Issues for unclassified lines —
    exactly the v1 free-form-detail regression we're avoiding.
    """
    pattern_targets = {detail for _pattern, detail in KMSG_PATTERNS}
    assert IssueDetail.UNKNOWN not in pattern_targets
