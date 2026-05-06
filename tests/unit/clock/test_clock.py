"""Tests for spark_modem.clock — ADR-0007 monotonic + wall-clock helpers."""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from spark_modem.clock import elapsed_since, monotonic, wall_clock_iso


def test_monotonic_returns_float() -> None:
    value = monotonic()
    assert isinstance(value, float)


def test_monotonic_non_decreasing() -> None:
    t1 = monotonic()
    t2 = monotonic()
    assert t2 >= t1


def test_monotonic_independent_of_wall_clock() -> None:
    """Patching time.time should not affect monotonic()."""
    t_before = time.monotonic()
    with patch("time.time", return_value=0.0):  # far-past wall clock
        t_mono = monotonic()
    t_after = time.monotonic()
    # monotonic value should be in the expected range regardless of time.time mock
    assert t_before <= t_mono <= t_after + 1.0


def test_wall_clock_iso_is_string() -> None:
    iso = wall_clock_iso()
    assert isinstance(iso, str)


def test_wall_clock_iso_matches_pattern() -> None:
    iso = wall_clock_iso()
    pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(Z|[+-]\d{2}:\d{2})"
    assert re.match(pattern, iso), f"ISO string {iso!r} does not match expected pattern"


def test_wall_clock_iso_parseable() -> None:
    iso = wall_clock_iso()
    dt = datetime.fromisoformat(iso)
    assert dt.tzinfo is not None


def test_wall_clock_iso_default_utc() -> None:
    iso = wall_clock_iso()
    dt = datetime.fromisoformat(iso)
    # UTC is represented as +00:00
    assert dt.utcoffset() == timedelta(0)


def test_wall_clock_iso_honors_tz() -> None:
    tz = timezone(timedelta(hours=3))
    iso = wall_clock_iso(tz=tz)
    dt = datetime.fromisoformat(iso)
    assert dt.utcoffset() == timedelta(hours=3)


def test_elapsed_since_non_negative() -> None:
    t0 = monotonic()
    elapsed = elapsed_since(t0)
    assert elapsed >= 0.0


def test_elapsed_since_future_clamp() -> None:
    """elapsed_since on a future monotonic should return 0.0 (belt-and-suspenders)."""
    far_future = monotonic() + 1_000_000.0
    result = elapsed_since(far_future)
    assert result == 0.0
