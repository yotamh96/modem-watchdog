"""Tests for tests.fakes.clock.FakeClock."""

from __future__ import annotations

import pytest

from tests.fakes.clock import FakeClock


def test_advance_increments_monotonic_exactly() -> None:
    clock = FakeClock()
    assert clock.monotonic() == 0.0
    clock.advance(5.0)
    assert clock.monotonic() == 5.0
    clock.advance(2.5)
    assert clock.monotonic() == 7.5
    assert clock.elapsed_since(5.0) == 2.5


def test_wall_clock_iso_default_starts_2026_and_is_utc() -> None:
    clock = FakeClock()
    iso = clock.wall_clock_iso()
    assert iso.startswith("2026-01-01")
    assert iso.endswith("+00:00")


def test_advance_negative_raises_value_error() -> None:
    clock = FakeClock()
    with pytest.raises(ValueError) as excinfo:
        clock.advance(-1.0)
    assert "seconds must be >= 0" in str(excinfo.value)
