"""Tests for spark_modem.kmsg.dedup (Plan 03-05).

Mirrors tests/unit/webhook/test_dedup.py but for the per-IssueDetail
30s window contract (PITFALLS §13.2). All times are ``now_monotonic``
(CLAUDE.md invariant #4) — caller passes the value; module never reads
``time.time()`` directly.

Window default 30.0s LOCKED per CONTEXT.md E-03.
"""

from __future__ import annotations

from spark_modem.kmsg.dedup import KmsgDedup
from spark_modem.wire.enums import IssueDetail


def test_first_call_emits() -> None:
    """Fresh dedup table: first call returns True (emit)."""
    dedup = KmsgDedup()
    assert dedup.should_emit(IssueDetail.USB_OVERCURRENT, now_monotonic=100.0) is True


def test_second_call_within_window_does_not_emit() -> None:
    """A repeat within the 30s window is suppressed."""
    dedup = KmsgDedup()
    dedup.should_emit(IssueDetail.USB_OVERCURRENT, now_monotonic=100.0)
    assert dedup.should_emit(IssueDetail.USB_OVERCURRENT, now_monotonic=110.0) is False


def test_repeat_count_accumulates_within_window() -> None:
    """5 calls in window: 1 emits, 4 are suppressed; consume returns 4."""
    dedup = KmsgDedup()
    assert dedup.should_emit(IssueDetail.USB_OVERCURRENT, now_monotonic=100.0) is True
    assert dedup.should_emit(IssueDetail.USB_OVERCURRENT, now_monotonic=101.0) is False
    assert dedup.should_emit(IssueDetail.USB_OVERCURRENT, now_monotonic=102.0) is False
    assert dedup.should_emit(IssueDetail.USB_OVERCURRENT, now_monotonic=103.0) is False
    assert dedup.should_emit(IssueDetail.USB_OVERCURRENT, now_monotonic=104.0) is False
    assert dedup.consume_dedup_count(IssueDetail.USB_OVERCURRENT) == 4


def test_consume_dedup_count_clears_to_zero() -> None:
    """A second consume returns 0 (the count was popped)."""
    dedup = KmsgDedup()
    dedup.should_emit(IssueDetail.USB_OVERCURRENT, now_monotonic=100.0)
    dedup.should_emit(IssueDetail.USB_OVERCURRENT, now_monotonic=110.0)
    assert dedup.consume_dedup_count(IssueDetail.USB_OVERCURRENT) == 1
    assert dedup.consume_dedup_count(IssueDetail.USB_OVERCURRENT) == 0


def test_window_reopens_after_30s() -> None:
    """At exactly the 30s boundary, the window has elapsed; emit re-fires.

    Implementation uses ``now_monotonic < expires`` so at the exact
    boundary the comparison is False and a fresh window opens.
    """
    dedup = KmsgDedup()
    dedup.should_emit(IssueDetail.USB_OVERCURRENT, now_monotonic=100.0)
    assert dedup.should_emit(IssueDetail.USB_OVERCURRENT, now_monotonic=130.0) is True


def test_distinct_details_have_independent_windows() -> None:
    """Each IssueDetail has its own window — distinct keys, distinct expirations."""
    dedup = KmsgDedup()
    assert dedup.should_emit(IssueDetail.USB_OVERCURRENT, now_monotonic=100.0) is True
    # Within the USB_OVERCURRENT window, but USB_ENUM_FAILURE has its own
    # never-opened window, so the call emits.
    assert dedup.should_emit(IssueDetail.USB_ENUM_FAILURE, now_monotonic=110.0) is True


def test_default_window_30_seconds() -> None:
    """Default window is exactly 30.0s (E-03 LOCKED)."""
    dedup = KmsgDedup()
    # Open the window at t=0
    assert dedup.should_emit(IssueDetail.USB_OVERCURRENT, now_monotonic=0.0) is True
    # Just before 30s: still suppressed
    assert dedup.should_emit(IssueDetail.USB_OVERCURRENT, now_monotonic=29.99) is False
    # At exactly 30s: window has elapsed; emit re-fires
    assert dedup.should_emit(IssueDetail.USB_OVERCURRENT, now_monotonic=30.0) is True


def test_consume_for_unknown_key_returns_zero() -> None:
    """Reading a never-suppressed detail returns 0; no KeyError."""
    dedup = KmsgDedup()
    assert dedup.consume_dedup_count(IssueDetail.USB_OVERCURRENT) == 0


def test_custom_window_seconds_honored() -> None:
    """An explicit window_seconds=N overrides the default."""
    dedup = KmsgDedup(window_seconds=5.0)
    assert dedup.should_emit(IssueDetail.USB_OVERCURRENT, now_monotonic=0.0) is True
    assert dedup.should_emit(IssueDetail.USB_OVERCURRENT, now_monotonic=4.99) is False
    assert dedup.should_emit(IssueDetail.USB_OVERCURRENT, now_monotonic=5.0) is True
