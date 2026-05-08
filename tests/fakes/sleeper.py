"""FakeSleeper -- advances a FakeClock and yields control (PITFALLS §14.1).

Production code wires a tiny adapter that calls ``asyncio.sleep``; tests use
this fake so FakeClock-driven backoffs are observed deterministically without
real wall-clock waiting.

Mirrors the calls-list defensive-copy pattern from ``tests/fakes/runner.py``.
"""

from __future__ import annotations

import asyncio


class FakeSleeper:
    """Async sleep that advances an injected FakeClock and yields control.

    Records each requested delay so tests can assert backoff envelopes.

    Why a custom fake (instead of monkey-patching ``asyncio.sleep``):
      The supervisor under test takes a Sleeper Protocol and never reaches
      into asyncio.sleep directly. Tests inject this fake; production wires
      a tiny adapter around real ``asyncio.sleep``. PITFALLS §14.1 prescribes
      this seam so FakeClock-driven tests don't hang on real wall-clock
      sleeps.
    """

    def __init__(self, clock: object) -> None:
        # ``clock`` is duck-typed against the FakeClock surface (advance method).
        self._clock = clock
        self._calls: list[float] = []

    @property
    def calls(self) -> list[float]:
        """Return a defensive copy of the recorded delay list."""
        return list(self._calls)

    async def sleep(self, delay: float) -> None:
        """Record `delay`, advance the FakeClock, then yield control."""
        self._calls.append(delay)
        # FakeClock.advance moves both monotonic and wall clocks forward.
        advance = getattr(self._clock, "advance", None)
        if advance is not None:
            advance(delay)
        # Yield once so other coroutines (the supervisor's loop) progress.
        await asyncio.sleep(0)
