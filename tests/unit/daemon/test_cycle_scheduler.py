"""Tests for CycleScheduler — 30s monotonic timer + drift accounting."""

from __future__ import annotations

import pytest

from spark_modem.daemon.cycle_scheduler import CycleScheduler
from tests.fakes.clock import FakeClock


def test_initial_deadline_is_interval_after_start() -> None:
    """First ``next_deadline`` is ``start_monotonic + interval_seconds``."""
    clock = FakeClock(start_monotonic=100.0)
    scheduler = CycleScheduler(interval_seconds=30.0, clock=clock)

    assert scheduler.next_deadline() == pytest.approx(130.0)


def test_advance_increments_by_interval() -> None:
    """One ``advance()`` moves the deadline by exactly one interval."""
    clock = FakeClock(start_monotonic=0.0)
    scheduler = CycleScheduler(interval_seconds=30.0, clock=clock)

    scheduler.advance()

    assert scheduler.next_deadline() == pytest.approx(60.0)


def test_advance_catches_up_when_skipped() -> None:
    """Skipping multiple intervals (cycle work too long) advances past now.

    PITFALLS §9.3: never schedule a back-to-back hot-loop.  After cycle
    work that took >2 intervals, ``advance()`` keeps adding intervals
    until ``next_deadline > now``.
    """
    clock = FakeClock(start_monotonic=0.0)
    scheduler = CycleScheduler(interval_seconds=30.0, clock=clock)
    # Cycle work simulated to take 75s — 2.5 intervals.
    clock.advance(75.0)

    scheduler.advance()

    # Initial deadline 30s + interval = 60s; 60s <= 75s now, so add more.
    # 60 + 30 = 90s > 75s now → 90s is the next deadline.
    assert scheduler.next_deadline() > clock.monotonic()
    assert scheduler.next_deadline() == pytest.approx(90.0)


def test_overran_returns_true_after_interval_and_a_half() -> None:
    """``overran`` triggers when ``now`` is more than one interval past
    the scheduled deadline (``deadline + interval``)."""
    clock = FakeClock(start_monotonic=0.0)
    scheduler = CycleScheduler(interval_seconds=30.0, clock=clock)
    # Deadline is at 30; we wake up at 30 + 30 + 1 = 61s — past one full
    # interval beyond the deadline.
    assert scheduler.overran(now_mono=61.0) is True


def test_overran_returns_false_within_one_interval() -> None:
    """``overran`` is False for a wake within one interval of the deadline."""
    clock = FakeClock(start_monotonic=0.0)
    scheduler = CycleScheduler(interval_seconds=30.0, clock=clock)
    # Deadline 30s; we wake up at 50s — only 20s past, well within one
    # interval — not an overrun.
    assert scheduler.overran(now_mono=50.0) is False


def test_constructor_rejects_zero_interval() -> None:
    """``interval_seconds=0`` raises ``ValueError`` (degenerate timer)."""
    clock = FakeClock()
    with pytest.raises(ValueError, match="interval_seconds must be > 0"):
        CycleScheduler(interval_seconds=0, clock=clock)


def test_constructor_rejects_negative_interval() -> None:
    """``interval_seconds < 0`` raises ``ValueError``."""
    clock = FakeClock()
    with pytest.raises(ValueError, match="interval_seconds must be > 0"):
        CycleScheduler(interval_seconds=-1.0, clock=clock)


def test_expected_for_drift_is_pre_advance_deadline() -> None:
    """``expected_for_drift`` returns the deadline BEFORE the next advance.

    The driver computes ``cycle_drift = now - expected_for_drift()`` at
    the wake-up boundary BEFORE calling ``advance()`` (O-03).
    """
    clock = FakeClock(start_monotonic=0.0)
    scheduler = CycleScheduler(interval_seconds=30.0, clock=clock)

    # Initial expected_for_drift == 30 (the first deadline).
    assert scheduler.expected_for_drift() == pytest.approx(30.0)

    # After one advance, expected_for_drift moves to 60.
    scheduler.advance()
    assert scheduler.expected_for_drift() == pytest.approx(60.0)
