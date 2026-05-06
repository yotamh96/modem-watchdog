"""FakeClock -- instance-method clock for deterministic asyncio tests.

Mirrors the surface of the module-level functions in
`spark_modem.clock.clock` (monotonic / elapsed_since / wall_clock_iso) but as
instance methods so a single FakeClock can be parameterized into multiple
units under test without monkeypatching the module.

Tests advance time via `advance(seconds)` -- no wall-clock waiting, no
asyncio.sleep races.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, tzinfo


class FakeClock:
    """Deterministic, asyncio-compatible clock for tests.

    Call `advance(seconds)` to move both the monotonic and wall clocks forward
    by an exact amount. The default starting wall clock is 2026-01-01T00:00:00+00:00
    so tests can reason about ISO stamps without referencing the real date.
    """

    def __init__(
        self,
        *,
        start_monotonic: float = 0.0,
        start_wall: datetime | None = None,
    ) -> None:
        self._monotonic = start_monotonic
        self._wall = start_wall if start_wall is not None else datetime(2026, 1, 1, tzinfo=UTC)

    def monotonic(self) -> float:
        """Return the current monotonic clock value (seconds)."""
        return self._monotonic

    def elapsed_since(self, t0_monotonic: float) -> float:
        """Return max(0, monotonic - t0_monotonic) -- defensive vs. clock skew."""
        return max(0.0, self._monotonic - t0_monotonic)

    def wall_clock_iso(self, *, tz: tzinfo | None = None) -> str:
        """Return the wall-clock value as an ISO-8601 string.

        If tz is None, the configured wall datetime is returned as-is (its own
        tzinfo wins). Otherwise the wall datetime is converted to tz.
        """
        target = self._wall if tz is None else self._wall.astimezone(tz)
        return target.isoformat()

    def unix_seconds(self) -> int:
        """Return Unix wall-clock seconds derived from the fake wall clock.

        Tracks ``advance(seconds)`` so tests that exercise the
        ``X-Spark-Timestamp`` header (CR-01 fix) see deterministic values.
        """
        return int(self._wall.timestamp())

    def advance(self, seconds: float) -> None:
        """Move both clocks forward by `seconds`. Negative values raise ValueError."""
        if seconds < 0:
            raise ValueError(f"FakeClock.advance: seconds must be >= 0; got {seconds}")
        self._monotonic += seconds
        self._wall = self._wall + timedelta(seconds=seconds)
