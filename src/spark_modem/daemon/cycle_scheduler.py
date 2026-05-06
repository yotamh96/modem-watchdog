"""30s monotonic timer for the cycle loop (Plan 02-10).

Phase 2 ships only the sleep arm; Phase 3 wires the event_queue arm
(udev / rtnetlink / inotify producers).  ``CycleScheduler`` keeps the
timer + drift accounting in one place so ``daemon/main.py`` can wrap
it in ``asyncio.wait`` per RESEARCH §3.5.

ADR-0007: every duration arithmetic uses ``time.monotonic()`` (via the
injected ``ClockProto``).  ``time.time()`` is reserved for ISO-8601
stamps and never appears in this module.
"""

from __future__ import annotations

from typing import Protocol


class ClockProto(Protocol):
    """Minimal monotonic-clock surface satisfied by ``FakeClock`` and
    ``cli.clients._CliClock``.
    """

    def monotonic(self) -> float: ...


class CycleScheduler:
    """30s monotonic deadline tracker with overrun detection (M-02).

    The cycle driver invokes ``next_deadline()`` to know when to wake,
    ``advance()`` after each cycle to schedule the next deadline, and
    ``overran(now)`` to detect a cycle that took longer than one
    interval.  The Phase 2 cycle driver in plan 02-10 calls these in the
    canonical pattern from RESEARCH §3.5.
    """

    def __init__(self, *, interval_seconds: float = 30.0, clock: ClockProto) -> None:
        if interval_seconds <= 0:
            raise ValueError(
                f"interval_seconds must be > 0; got {interval_seconds}",
            )
        self._interval = interval_seconds
        self._clock = clock
        self._next_deadline_monotonic: float = clock.monotonic() + interval_seconds

    def next_deadline(self) -> float:
        """Monotonic deadline at which the next cycle should wake."""
        return self._next_deadline_monotonic

    def expected_for_drift(self) -> float:
        """Deadline this cycle was scheduled for, BEFORE ``advance()``.

        Used by the driver to compute
        ``cycle_drift = now_monotonic - expected_for_drift()`` at the
        wake-up boundary BEFORE cycle work begins (O-03).
        """
        return self._next_deadline_monotonic

    def overran(self, now_mono: float) -> bool:
        """True iff this cycle's wake came significantly later than the deadline.

        ``significantly later`` = more than one full interval past the
        scheduled wake.  The driver logs ``cycle_overran`` when this is
        True; the next cycle is started immediately (no queueing).
        """
        return now_mono > self._next_deadline_monotonic + self._interval

    def advance(self) -> None:
        """Schedule the next deadline.

        Catches up if multiple intervals were skipped (cycle work took
        >2 intervals) -- the next deadline is ALWAYS strictly ahead of
        ``now`` to avoid back-to-back hot-loops (PITFALLS §9.3).
        """
        now = self._clock.monotonic()
        self._next_deadline_monotonic += self._interval
        while self._next_deadline_monotonic <= now:
            self._next_deadline_monotonic += self._interval
