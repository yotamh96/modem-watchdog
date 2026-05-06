"""Tests for webhook.dedup.DedupTable — per-(modem, kind) coalescing."""

from __future__ import annotations

from spark_modem.webhook.dedup import DedupTable


def test_first_call_not_deduped() -> None:
    """First call opens the window; not deduped."""
    table = DedupTable(window_seconds=60.0)
    assert table.is_deduped("2-3.1.1", "healthy_to_degraded", now_monotonic=0.0) is False


def test_second_call_within_window_deduped() -> None:
    """A second call within the window is suppressed."""
    table = DedupTable(window_seconds=60.0)
    table.is_deduped("2-3.1.1", "healthy_to_degraded", now_monotonic=0.0)
    assert table.is_deduped("2-3.1.1", "healthy_to_degraded", now_monotonic=30.0) is True


def test_call_after_window_expires_not_deduped() -> None:
    """Once the window has elapsed, the next call opens a fresh window."""
    table = DedupTable(window_seconds=60.0)
    table.is_deduped("2-3.1.1", "healthy_to_degraded", now_monotonic=0.0)
    assert table.is_deduped("2-3.1.1", "healthy_to_degraded", now_monotonic=61.0) is False


def test_consume_dedup_count_returns_suppressed_count() -> None:
    """Three calls within the window: first opens, next two are suppressed."""
    table = DedupTable(window_seconds=60.0)
    assert table.is_deduped("2-3.1.1", "healthy_to_degraded", now_monotonic=0.0) is False
    assert table.is_deduped("2-3.1.1", "healthy_to_degraded", now_monotonic=10.0) is True
    assert table.is_deduped("2-3.1.1", "healthy_to_degraded", now_monotonic=20.0) is True
    assert table.consume_dedup_count("2-3.1.1", "healthy_to_degraded") == 2


def test_consume_dedup_count_resets_to_zero() -> None:
    """Consuming the count clears the accumulator."""
    table = DedupTable(window_seconds=60.0)
    table.is_deduped("2-3.1.1", "healthy_to_degraded", now_monotonic=0.0)
    table.is_deduped("2-3.1.1", "healthy_to_degraded", now_monotonic=10.0)
    assert table.consume_dedup_count("2-3.1.1", "healthy_to_degraded") == 1
    assert table.consume_dedup_count("2-3.1.1", "healthy_to_degraded") == 0


def test_per_modem_per_kind_isolation() -> None:
    """Windows are independent per (modem_usb_path, kind) tuple."""
    table = DedupTable(window_seconds=60.0)
    # Open three independent windows in the same instant.
    assert table.is_deduped("2-3.1.1", "healthy_to_degraded", now_monotonic=0.0) is False
    assert table.is_deduped("2-3.1.2", "healthy_to_degraded", now_monotonic=0.0) is False
    assert table.is_deduped("2-3.1.1", "recovering_to_exhausted", now_monotonic=0.0) is False

    # Each one is independently deduped on the second call.
    assert table.is_deduped("2-3.1.1", "healthy_to_degraded", now_monotonic=10.0) is True
    assert table.is_deduped("2-3.1.2", "healthy_to_degraded", now_monotonic=10.0) is True
    assert table.is_deduped("2-3.1.1", "recovering_to_exhausted", now_monotonic=10.0) is True

    # And independently consumed.
    assert table.consume_dedup_count("2-3.1.1", "healthy_to_degraded") == 1
    assert table.consume_dedup_count("2-3.1.2", "healthy_to_degraded") == 1
    assert table.consume_dedup_count("2-3.1.1", "recovering_to_exhausted") == 1


def test_window_reopens_with_zero_count() -> None:
    """A new window after expiry starts with zero suppressed count."""
    table = DedupTable(window_seconds=60.0)
    table.is_deduped("2-3.1.1", "healthy_to_degraded", now_monotonic=0.0)
    table.is_deduped("2-3.1.1", "healthy_to_degraded", now_monotonic=10.0)
    table.is_deduped("2-3.1.1", "healthy_to_degraded", now_monotonic=20.0)
    # Consume mid-stream; window still active.
    assert table.consume_dedup_count("2-3.1.1", "healthy_to_degraded") == 2

    # Past expiry, fresh window opens, and the suppressed count is 0.
    assert table.is_deduped("2-3.1.1", "healthy_to_degraded", now_monotonic=80.0) is False
    assert table.consume_dedup_count("2-3.1.1", "healthy_to_degraded") == 0


def test_consume_for_unknown_key_returns_zero() -> None:
    """Reading a never-suppressed key just returns 0; no KeyError."""
    table = DedupTable(window_seconds=60.0)
    assert table.consume_dedup_count("2-3.1.1", "healthy_to_degraded") == 0


def test_zero_window_disables_dedup() -> None:
    """A window of 0s never deduplicates; every call opens a fresh window."""
    table = DedupTable(window_seconds=0.0)
    assert table.is_deduped("2-3.1.1", "x", now_monotonic=0.0) is False
    assert table.is_deduped("2-3.1.1", "x", now_monotonic=0.0) is False
    assert table.consume_dedup_count("2-3.1.1", "x") == 0
