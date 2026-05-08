"""SIGTERM choreography — strict 8-step ordered teardown (L-02).

CONTEXT.md L-02 verbatim step list (each step bounded by the deadline
budget; per-step try/except so single-step failure does not skip later
steps — NFR-11):

    1. Cancel CycleDriver.run_one_cycle task
    2. Cancel the 5 event-source producer tasks
    3. await webhook_poster.drain(budget_seconds=3.0)
    4. Final state_store.save_modem_state(...) for any in-flight
    5. Emit DaemonStopped event with reason=SIGTERM
    6. webhook_poster.stop()
    7. Close UDS metrics socket + unlink(metrics_socket_path)
    8. Touch /run/.../clean-shutdown marker
    9. Close PID lock fd
   10. Return 0

Steps 9 + 10 are owned by the caller (``daemon/main.py``); the
choreography ends after step 8 so the caller's ``finally`` arm can
release the PID lock and asyncio.run cleanup can drive the loop to
exit.

Several pairs of steps are NOT commutative:
  * webhook drain (step 3) MUST come AFTER cycle cancel (step 1) so
    the drain sees any final-cycle transitions enqueued during the
    last action-execute.
  * webhook drain MUST come BEFORE metrics socket close (step 7) so
    drain emits ``webhook_delivery_total`` increments while the
    registry is still scrapeable.
  * clean-shutdown marker (step 8) MUST come AFTER all event emission
    (step 5) so its ``cycle_count`` reflects all events written this
    run.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from spark_modem.daemon.lifecycle import write_clean_shutdown_marker
from spark_modem.wire.enums import DaemonStopReason
from spark_modem.wire.events import DaemonStopped

logger = logging.getLogger(__name__)

# Step 3 max budget (W-01) — the 3.0s ceiling holds even when the larger
# choreography deadline allows more time. PITFALLS §4.5 reasoning:
# webhook drain is best-effort; spending more than 3 s on it eats the
# state-flush + marker-write budget.
_DRAIN_HARD_CAP_S: float = 3.0


class _ClockProto(Protocol):
    """Monotonic + wall-clock surface (ADR-0007)."""

    def monotonic(self) -> float: ...
    def wall_clock_iso(self) -> str: ...


class _WebhookPosterProto(Protocol):
    """Subset of WebhookPoster the choreography touches.

    drain() is async (W-01); stop() is sync (closes httpx client cleanly).
    """

    async def drain(self, *, budget_seconds: float = 3.0) -> None: ...

    def stop(self) -> None: ...


class _EventLogWriterProto(Protocol):
    def append(self, event: object) -> None: ...


class SigtermChoreography:
    """Execute the 8-step SIGTERM teardown within a deadline budget (L-02).

    Each step wrapped in try/except so a single-step failure does not
    skip later steps (NFR-11). The entire choreography never raises
    — it's the LAST coroutine the daemon runs before exit.

    Step 4 (final state-store flush) is parameterised via
    ``state_flush`` since the per-cycle state-write atomicity contract
    (RECOVERY_SPEC §8) means the cycle owns its own commits; the
    choreography simply gives any pending commit a chance to finish.
    A None ``state_flush`` is acceptable when the cycle driver guarantees
    no half-flushed state exists at cancel time.
    """

    def __init__(
        self,
        *,
        cycle_driver_task: asyncio.Task[object],
        producer_tasks: list[asyncio.Task[object]],
        webhook_poster: _WebhookPosterProto,
        event_logger: _EventLogWriterProto,
        metrics_socket_path: Path,
        run_dir: Path,
        clock: _ClockProto,
        boot_monotonic: float,
        cycle_count_ref: list[int],
        state_flush: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._cycle_driver_task = cycle_driver_task
        self._producer_tasks = list(producer_tasks)
        self._webhook_poster = webhook_poster
        self._event_logger = event_logger
        self._metrics_socket_path = metrics_socket_path
        self._run_dir = run_dir
        self._clock = clock
        self._boot_monotonic = boot_monotonic
        self._cycle_count_ref = cycle_count_ref
        self._state_flush = state_flush

    async def execute(self, *, deadline_seconds: float = 5.0) -> None:
        """Run the 8-step choreography within ``deadline_seconds``.

        Total deadline 5 s by default (FR-53). Each step bounded; a step
        that raises is logged and the choreography continues with the
        remaining steps (NFR-11).
        """
        deadline = self._clock.monotonic() + deadline_seconds

        # Step 1: cancel the cycle driver and await its cleanup.
        try:
            self._cycle_driver_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._cycle_driver_task
        except Exception:  # belt-and-suspenders
            logger.exception("sigterm step 1 (cancel cycle driver) failed")

        # Step 2: cancel all 5 event-source producer tasks. supervisor's
        # restart_on_crash wrapper passes CancelledError through cleanly.
        try:
            for t in self._producer_tasks:
                t.cancel()
            for t in self._producer_tasks:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await t
        except Exception:
            logger.exception("sigterm step 2 (cancel producers) failed")

        # Step 3: webhook drain — bounded by min(deadline_remaining, 3.0).
        try:
            remaining = max(0.0, deadline - self._clock.monotonic())
            budget = min(_DRAIN_HARD_CAP_S, remaining)
            await self._webhook_poster.drain(budget_seconds=budget)
        except Exception:
            logger.exception("sigterm step 3 (webhook drain) failed")

        # Step 4: final state flush — best-effort, contractually a no-op
        # when the cycle driver guarantees atomic per-cycle writes.
        if self._state_flush is not None:
            try:
                await self._state_flush()
            except Exception:
                logger.exception("sigterm step 4 (state flush) failed")

        # Step 5: emit DaemonStopped(reason=SIGTERM, uptime_seconds, cycle_count).
        try:
            uptime = max(0.0, self._clock.monotonic() - self._boot_monotonic)
            self._event_logger.append(
                DaemonStopped(
                    ts_iso=self._clock.wall_clock_iso(),
                    reason=DaemonStopReason.SIGTERM,
                    uptime_seconds=uptime,
                )
            )
        except Exception:
            logger.exception("sigterm step 5 (emit DaemonStopped) failed")

        # Step 6: stop the webhook poster (closes httpx client cleanly).
        try:
            self._webhook_poster.stop()
        except Exception:
            logger.exception("sigterm step 6 (webhook stop) failed")

        # Step 7: close UDS metrics socket; unlink path (PITFALLS §13.3).
        # The metrics server lifecycle is owned by the caller; we just
        # unlink the socket file so it doesn't linger across restarts.
        try:
            with contextlib.suppress(FileNotFoundError, OSError):
                self._metrics_socket_path.unlink()
        except Exception:
            logger.exception("sigterm step 7 (metrics socket unlink) failed")

        # Step 8: clean-shutdown marker. Atomic per CLAUDE.md invariant #5.
        try:
            uptime = max(0.0, self._clock.monotonic() - self._boot_monotonic)
            write_clean_shutdown_marker(
                run_dir=self._run_dir,
                uptime_seconds=uptime,
                cycle_count=self._cycle_count_ref[0],
                exit_reason="sigterm",
            )
        except Exception:
            logger.exception("sigterm step 8 (clean-shutdown marker) failed")
