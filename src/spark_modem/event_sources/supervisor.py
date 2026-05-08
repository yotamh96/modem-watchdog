"""Producer-task supervisor with bounded backoff + WakeSignal wire enum (E-01/E-02).

This module owns three exports:

  * ``WakeSignal`` (E-02) — closed StrEnum on the cycle scheduler's
    ``event_queue``. Producers ``put_nowait(WakeSignal.UDEV)`` etc.; the
    scheduler treats every wake signal as "do a full re-observation pass."
    Per ADR-0002 the queue carries only opaque sentinels — never state.

  * ``Sleeper`` (Protocol, runtime_checkable) — small async sleep seam so
    tests can advance ``FakeClock`` without real wall-clock waiting
    (PITFALLS §14.1). Production wires a one-line adapter that calls
    ``asyncio.sleep``.

  * ``restart_on_crash`` (E-01) — wraps each producer factory with bounded
    backoff and ``CancelledError`` passthrough. Catches ``Exception`` only
    — never ``BaseException`` — so SIGTERM-driven TaskGroup cancellation
    propagates cleanly. Mirrors the per-task isolation pattern from
    ``observer/orchestrator.py:_probe_one`` at producer-task scope.

Pitfall 15 envelope: ``(1, 2, 4, 8, 60)`` capped — chronic-crash producer
uses ~1.7% CPU at the 60s cap and emits one ``event_source_crashed`` log
per minute. Attempt counter resets after a clean run that lasted longer
than ``reset_after_uptime_s`` (default 300s) so transient crashes don't
accumulate forever.

Anti-patterns explicitly NOT used here (CLAUDE.md):
  * No ``MonitorObserver``, no ``signal.signal``, no ``subprocess`` —
    this module supervises producers; producers themselves talk to udev /
    rtnetlink / asyncinotify / kmsg in their own modules.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


class WakeSignal(StrEnum):
    """Opaque wake sentinels on ``CycleScheduler.event_queue`` (E-02).

    Closed enum — pydantic validation rejects any value outside this set
    when wake signals enter the wire boundary (T-03-01-05).

    Per ADR-0002, the cycle is the source of truth: a wake signal causes
    a full re-observation pass, never partial state mutation. Producers
    must never piggyback state onto the queue.
    """

    UDEV = "udev"
    RTNETLINK = "rtnetlink"
    ZAO_LOG = "zao_log"
    EVENTS_LOG_ROTATED = "events_log_rotated"
    KMSG = "kmsg"


@runtime_checkable
class Sleeper(Protocol):
    """Async sleep seam (PITFALLS §14.1).

    Production wires a tiny adapter:
        class _AsyncioSleeper:
            async def sleep(self, delay: float) -> None:
                await asyncio.sleep(delay)

    Tests inject ``tests.fakes.sleeper.FakeSleeper`` which advances a
    ``FakeClock`` and yields control without real wall-clock waiting.
    """

    async def sleep(self, delay: float) -> None: ...


@runtime_checkable
class ClockProto(Protocol):
    """Minimal monotonic-clock surface (ADR-0007).

    Co-located here (not imported from ``daemon/cycle_scheduler``) so
    ``event_sources/`` and ``daemon/`` stay free of import cycles. Same
    shape as the orchestrator's ``ClockProto`` and the cycle scheduler's
    — duck-typed compatibility, not nominal subtyping.
    """

    def monotonic(self) -> float: ...
    def wall_clock_iso(self) -> str: ...


@runtime_checkable
class EventLogWriterProto(Protocol):
    """Minimal event-log surface used by the supervisor.

    Plan 03-06 lands the ``EventSourceCrashed`` Event variant + structured
    emission via this writer. For Plan 03-01 the parameter is plumbed (so
    callers can pre-wire it) but the supervisor only logs via
    ``logger.exception``; the structured emission comes online in 03-06.
    Threat T-03-01-06 documents this acceptance.
    """

    def append(self, event: object) -> None: ...


# Default Pitfall-15 envelope: 1s -> 2s -> 4s -> 8s -> 60s cap.
_DEFAULT_BACKOFFS: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 60.0)
# Default uptime threshold for attempt-counter reset (5 minutes).
_DEFAULT_RESET_AFTER_UPTIME_S: float = 300.0


async def restart_on_crash(
    name: str,
    factory: Callable[[], Awaitable[None]],
    *,
    sleeper: Sleeper,
    event_logger: EventLogWriterProto,
    clock: ClockProto,
    backoffs: tuple[float, ...] = _DEFAULT_BACKOFFS,
    reset_after_uptime_s: float = _DEFAULT_RESET_AFTER_UPTIME_S,
) -> None:
    """Re-enter ``factory()`` on Exception with bounded backoff.

    Loop semantics:
      * ``factory()`` returns cleanly -> supervisor exits silently
        (uncommon; producers normally loop forever — clean return is
        treated as intentional shutdown).
      * ``factory()`` raises ``CancelledError`` -> re-raised; TaskGroup
        cancellation passthrough.
      * ``factory()`` raises any other ``Exception`` -> log via
        ``logger.exception`` with the source ``name``, sleep for the
        next backoff in the envelope, re-enter factory.

    Pitfall 15: if the most-recent factory run lasted longer than
    ``reset_after_uptime_s``, reset the attempt counter to 0 before
    selecting the next backoff. Chronic-crash producers can't accumulate
    attempts forever; transient crashes still see escalation.

    Plan 03-06 wires structured ``EventSourceCrashed`` emission via
    ``event_logger.append`` in the ``except Exception`` block.
    """
    # Local import to avoid circular import on package init.
    from spark_modem.wire.events import EventSourceCrashed  # noqa: PLC0415

    attempt = 0
    while True:
        start_monotonic = clock.monotonic()
        try:
            await factory()
            # Producer returned cleanly — uncommon (producers loop
            # forever). Treat as intentional shutdown.
            return
        except asyncio.CancelledError:
            # Passthrough: TaskGroup cancellation must propagate.
            raise
        except Exception as exc:  # supervisor catches all Exception to self-heal (E-01)
            uptime = clock.monotonic() - start_monotonic
            logger.exception("event_source_crashed source=%s uptime=%.1fs", name, uptime)
            # Pitfall 15: long clean run before crash -> reset attempt counter.
            if uptime >= reset_after_uptime_s:
                attempt = 0
            delay = backoffs[min(attempt, len(backoffs) - 1)]
            # Issue #7 / Open Question 2 RESOLVED: emit structured event so
            # events.jsonl carries every supervisor-caught crash, not just
            # the logger.exception line. T-03-06-07: error_message capped at
            # 200 chars to prevent log-injection / path-leak.
            try:
                msg = str(exc)[:200]
                event_logger.append(
                    EventSourceCrashed(
                        ts_iso=clock.wall_clock_iso(),
                        source=name,
                        error_class=type(exc).__name__,
                        error_message=msg,
                        restart_attempt=attempt + 1,
                        backoff_seconds=delay,
                    )
                )
            except Exception:  # NFR-11: never let crash-event emission crash the supervisor
                logger.exception(
                    "event_source_crashed: failed to append structured event source=%s",
                    name,
                )
            attempt += 1
            await sleeper.sleep(delay)
