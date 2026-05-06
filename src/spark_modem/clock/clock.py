"""Clock helpers (ADR-0007).

Durations and backoffs use monotonic(); ISO-8601 stamps use wall_clock_iso().
Never call time.monotonic() or time.time() directly outside this module —
the indirection lets policy/ (Phase 2) accept a Clock Protocol stub for tests.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, tzinfo


def monotonic() -> float:
    """time.monotonic() — for durations, backoffs, and rate limits.

    ADR-0007: NTP step on the Jetson can wedge wall-clock backoff; never
    use time.time() for arithmetic.
    """
    return time.monotonic()


def elapsed_since(t0_monotonic: float) -> float:
    """Convenience: monotonic() - t0_monotonic, never negative.

    Returns 0.0 if t0 is in the future (clock skew shouldn't happen with
    monotonic; this is belt-and-suspenders).
    """
    return max(0.0, monotonic() - t0_monotonic)


def wall_clock_iso(*, tz: tzinfo | None = None) -> str:
    """Wall-clock ISO-8601 stamp with timezone — for log lines and events.

    Uses datetime.now(tz). Default tz is UTC; ISO-8601 is the on-the-wire
    format for events.jsonl and webhook payloads. ISO stamps are
    operator-readable; durations are not — different concerns.
    """
    return datetime.now(tz if tz is not None else UTC).isoformat()
