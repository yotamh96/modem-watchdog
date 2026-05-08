"""Tests for event_sources.supervisor — WakeSignal + restart_on_crash (E-01/E-02).

Eight cases covering:
  1. WakeSignal closed-enum shape (5 lowercase-snake_case values).
  2. StrEnum str() returns the .value (E-02 wire-serialization guarantee).
  3. CancelledError passthrough (TaskGroup-cancellation semantics).
  4. Backoff envelope (1, 2, 4, 8, 60, 60) cap at 60s.
  5. Uptime-reset (>=300s clean run resets attempt counter — Pitfall 15).
  6. No reset on short uptime (<300s preserves escalation).
  7. Clean factory return -> supervisor exits silently.
  8. Crash logged via logger.exception with source name and "event_source_crashed".
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

import pytest

from spark_modem.event_sources.supervisor import (
    Sleeper,
    WakeSignal,
    restart_on_crash,
)
from tests.fakes.clock import FakeClock
from tests.fakes.sleeper import FakeSleeper


class _RecordingEventLogger:
    """Minimal EventLogWriterProto satisfier for tests."""

    def __init__(self) -> None:
        self.events: list[object] = []

    def append(self, event: object) -> None:
        self.events.append(event)


# ---------------------------------------------------------------------------
# WakeSignal contract tests
# ---------------------------------------------------------------------------


def test_wake_signal_has_five_closed_members() -> None:
    """E-02: WakeSignal has exactly the 5 locked sources as StrEnum values."""
    values = frozenset(s.value for s in WakeSignal)
    assert values == frozenset({"udev", "rtnetlink", "zao_log", "events_log_rotated", "kmsg"})


def test_wake_signal_str_repr_uses_value() -> None:
    """StrEnum guarantee — str(member) == member.value (JSON serialization)."""
    assert str(WakeSignal.UDEV) == "udev"
    assert str(WakeSignal.RTNETLINK) == "rtnetlink"
    assert str(WakeSignal.KMSG) == "kmsg"


# ---------------------------------------------------------------------------
# restart_on_crash behavior
# ---------------------------------------------------------------------------


def _make_factory_that_raises(
    exc: type[BaseException], *, max_calls: int | None = None
) -> tuple[Callable[[], Awaitable[None]], list[int]]:
    """Build a factory that raises `exc` each call; returns (factory, call_counter).

    If max_calls is set, after that many calls the factory awaits forever
    (so the supervisor's outer cancel can stop it without further re-entries).
    """
    counter = [0]

    async def factory() -> None:
        counter[0] += 1
        if max_calls is not None and counter[0] > max_calls:
            await asyncio.Future()  # never returns
        raise exc("synthetic crash")

    return factory, counter


async def test_supervisor_passes_through_cancelled_error() -> None:
    """CancelledError MUST escape — TaskGroup cancellation must propagate."""
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    event_logger = _RecordingEventLogger()
    started = asyncio.Event()

    async def factory() -> None:
        started.set()
        await asyncio.Future()  # forever

    task = asyncio.create_task(
        restart_on_crash(
            "udev_producer",
            factory,
            sleeper=sleeper,
            event_logger=event_logger,
            clock=clock,
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_supervisor_backoff_envelope_1_2_4_8_60() -> None:
    """6 crashes through the envelope: backoffs are [1, 2, 4, 8, 60, 60]."""
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    event_logger = _RecordingEventLogger()
    factory, counter = _make_factory_that_raises(RuntimeError, max_calls=6)

    task = asyncio.create_task(
        restart_on_crash(
            "rtnetlink_producer",
            factory,
            sleeper=sleeper,
            event_logger=event_logger,
            clock=clock,
        )
    )

    # Drive until 6 attempts have completed and the 6th sleep was recorded.
    # Each iteration: factory raises -> log -> sleeper.sleep -> back to factory.
    for _ in range(200):
        await asyncio.sleep(0)
        if len(sleeper.calls) >= 6:
            break

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert sleeper.calls[:6] == [1.0, 2.0, 4.0, 8.0, 60.0, 60.0]
    assert counter[0] >= 6


async def test_supervisor_resets_attempt_after_long_uptime() -> None:
    """Pitfall 15: factory ran >=300s before crashing -> next backoff = 1.0 (reset)."""
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    event_logger = _RecordingEventLogger()

    crash_count = [0]

    async def factory() -> None:
        crash_count[0] += 1
        if crash_count[0] == 1:
            # First call: simulate 30s of uptime, then crash → backoff escalates
            clock.advance(30.0)
            raise RuntimeError("first crash @ 30s")
        if crash_count[0] == 2:
            # Second call: simulate 350s of uptime (>300s), then crash → reset
            clock.advance(350.0)
            raise RuntimeError("second crash @ 350s")
        # Subsequent calls: hang so test can stop here
        await asyncio.Future()

    task = asyncio.create_task(
        restart_on_crash(
            "zao_log_producer",
            factory,
            sleeper=sleeper,
            event_logger=event_logger,
            clock=clock,
        )
    )

    for _ in range(200):
        await asyncio.sleep(0)
        if len(sleeper.calls) >= 2:
            break

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # First crash @ 30s uptime → attempt 0 backoff = 1.0
    # Second crash @ 350s uptime → reset, attempt 0 again → backoff = 1.0
    assert sleeper.calls[0] == 1.0
    assert sleeper.calls[1] == 1.0


async def test_supervisor_does_not_reset_after_short_uptime() -> None:
    """<300s uptime preserves attempt escalation — second backoff is 2.0, not 1.0."""
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    event_logger = _RecordingEventLogger()

    crash_count = [0]

    async def factory() -> None:
        crash_count[0] += 1
        if crash_count[0] <= 2:
            clock.advance(30.0)  # short uptime each time
            raise RuntimeError(f"crash #{crash_count[0]}")
        await asyncio.Future()

    task = asyncio.create_task(
        restart_on_crash(
            "kmsg_producer",
            factory,
            sleeper=sleeper,
            event_logger=event_logger,
            clock=clock,
        )
    )

    for _ in range(200):
        await asyncio.sleep(0)
        if len(sleeper.calls) >= 2:
            break

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert sleeper.calls[:2] == [1.0, 2.0]


async def test_supervisor_returns_silently_on_factory_clean_return() -> None:
    """Factory returns without raising -> supervisor exits without retry."""
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    event_logger = _RecordingEventLogger()
    call_count = [0]

    async def factory() -> None:
        call_count[0] += 1
        # Clean exit (no return needed; falling off the function ends it).

    await restart_on_crash(
        "events_log_reopener",
        factory,
        sleeper=sleeper,
        event_logger=event_logger,
        clock=clock,
    )
    assert call_count[0] == 1
    assert sleeper.calls == []


async def test_supervisor_logs_via_logger_exception_on_crash(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Crash emits ERROR-level log including the source name and the marker."""
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    event_logger = _RecordingEventLogger()

    crash_count = [0]

    async def factory() -> None:
        crash_count[0] += 1
        if crash_count[0] == 1:
            raise RuntimeError("synthetic boom")
        await asyncio.Future()

    caplog.set_level(logging.ERROR, logger="spark_modem.event_sources.supervisor")
    task = asyncio.create_task(
        restart_on_crash(
            "udev_producer",
            factory,
            sleeper=sleeper,
            event_logger=event_logger,
            clock=clock,
        )
    )

    for _ in range(50):
        await asyncio.sleep(0)
        if sleeper.calls:
            break

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    matching = [
        r
        for r in caplog.records
        if r.levelno >= logging.ERROR and "event_source_crashed" in r.getMessage()
    ]
    assert matching, "expected at least one ERROR log with 'event_source_crashed'"
    # The producer name must show up in the log message (formatted from %s).
    assert any("udev_producer" in r.getMessage() for r in matching)


def test_sleeper_protocol_is_runtime_checkable() -> None:
    """Sleeper Protocol is runtime_checkable; FakeSleeper satisfies it."""
    clock = FakeClock()
    sleeper = FakeSleeper(clock)
    assert isinstance(sleeper, Sleeper)
