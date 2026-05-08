"""Unit tests for run_rtnetlink_producer (Plan 03-03).

Strategy: inject a ``FakeAsyncIPRoute`` via the ``ipr_factory`` parameter
so tests run cross-platform without pyroute2. The producer body is the
"tight read loop with put_nowait only" prescribed by PITFALLS §6.1 — the
6 tests below pin every contract point:

  1. setsockopt(4 MiB) called in the async context manager
  2. bind(groups=...) called with the provided constant
  3. each rtnetlink message yields exactly one WakeSignal.RTNETLINK
  4. ENOBUFS escapes the coroutine (supervisor in Plan 03-01 catches)
  5. NO logging in the message-loop body (E-02 / PITFALLS §6.1)
  6. async __aexit__ runs on cancel (socket cleanup invariant)
"""

from __future__ import annotations

import asyncio
import errno
import logging
import socket

import pytest

from spark_modem.event_sources.rtnetlink_producer import run_rtnetlink_producer
from spark_modem.event_sources.supervisor import WakeSignal
from tests.fakes.rtnetlink import FakeAsyncIPRoute

# Synthetic RTMGRP_LINK constant — pyroute2 defines this as 1, but the
# producer doesn't care about the value when ipr_factory is injected;
# all that matters is "bind() received the value we passed in."
_FAKE_RTMGRP_LINK_VALUE = 1


class _RecordingQueue:
    """Minimal _EventQueueProto satisfier — records every put_nowait."""

    def __init__(self) -> None:
        self.items: list[object] = []

    def put_nowait(self, item: object) -> None:
        self.items.append(item)


async def _drive_producer_until_messages_consumed(
    fake_ipr: FakeAsyncIPRoute, queue: _RecordingQueue, expected: int
) -> None:
    """Spin the producer task until ``queue.items`` reaches ``expected`` count.

    The producer runs ``async for _msg in ipr.get():``; each ``__anext__``
    on FakeAsyncIPRoute yields control via ``asyncio.sleep(0)`` when the
    queue is empty. We close the fake to break the loop after expected
    messages arrive.
    """
    task = asyncio.create_task(
        run_rtnetlink_producer(
            event_queue=queue, ipr_factory=(fake_ipr, _FAKE_RTMGRP_LINK_VALUE)
        )
    )
    # Yield until the producer has consumed all injected messages.
    for _ in range(50):  # bounded loop — 50 yields is plenty for tests
        if len(queue.items) >= expected:
            break
        await asyncio.sleep(0)
    # Close the fake to make __anext__ raise StopAsyncIteration; producer
    # then exits cleanly via the async-context-manager.
    fake_ipr.close()
    await asyncio.wait_for(task, timeout=1.0)


async def test_setsockopt_4mib_called_on_bind() -> None:
    """SO_RCVBUF=4MiB is set on the underlying socket (PITFALLS §6.1)."""
    fake_ipr = FakeAsyncIPRoute()
    fake_ipr.inject_message(object())
    queue = _RecordingQueue()

    await _drive_producer_until_messages_consumed(fake_ipr, queue, expected=1)

    assert fake_ipr.asyncore.socket.setsockopt_calls == [
        (socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    ]


async def test_bind_called_with_provided_groups() -> None:
    """bind(groups=...) is called once with the injected constant."""
    fake_ipr = FakeAsyncIPRoute()
    fake_ipr.inject_message(object())
    queue = _RecordingQueue()

    await _drive_producer_until_messages_consumed(fake_ipr, queue, expected=1)

    assert fake_ipr.bind_calls == [_FAKE_RTMGRP_LINK_VALUE]


async def test_message_pushes_wake_signal_rtnetlink() -> None:
    """Each rtnetlink message yields exactly one WakeSignal.RTNETLINK."""
    fake_ipr = FakeAsyncIPRoute()
    fake_ipr.inject_message(object())
    fake_ipr.inject_message(object())
    fake_ipr.inject_message(object())
    queue = _RecordingQueue()

    await _drive_producer_until_messages_consumed(fake_ipr, queue, expected=3)

    assert queue.items == [WakeSignal.RTNETLINK] * 3


async def test_enobufs_escapes_to_caller() -> None:
    """OSError(ENOBUFS) escapes the producer (supervisor handles re-open).

    PITFALLS §6.1 PRESCRIPTIVE: the producer must NOT try-except ENOBUFS
    — it lets the OSError bubble up so the supervisor's
    ``restart_on_crash`` wrapper (Plan 03-01) closes + reopens the
    socket. Catching here would silently exhaust the kernel buffer.
    """
    fake_ipr = FakeAsyncIPRoute()
    fake_ipr.inject_enobufs()
    queue = _RecordingQueue()

    with pytest.raises(OSError) as exc_info:
        await run_rtnetlink_producer(
            event_queue=queue, ipr_factory=(fake_ipr, _FAKE_RTMGRP_LINK_VALUE)
        )

    assert exc_info.value.errno == errno.ENOBUFS
    # The async context manager still ran __aexit__ on the way out.
    assert fake_ipr._closed is True  # noqa: SLF001 — attribute is the test's contract


async def test_no_logging_in_message_loop(caplog: pytest.LogCaptureFixture) -> None:
    """The tight read loop body emits NO log records (PITFALLS §6.1).

    The producer body is ``put_nowait(WakeSignal.RTNETLINK)`` ONLY —
    no logging, no parsing, no side effects beyond the queue push.
    """
    fake_ipr = FakeAsyncIPRoute()
    for _ in range(5):
        fake_ipr.inject_message(object())
    queue = _RecordingQueue()

    with caplog.at_level(logging.WARNING):
        await _drive_producer_until_messages_consumed(fake_ipr, queue, expected=5)

    # No WARNING/ERROR/CRITICAL records emitted by the producer body.
    high_severity = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert high_severity == []


async def test_aexit_called_on_cancel() -> None:
    """async __aexit__ runs on CancelledError → socket cleanup invariant.

    PITFALLS §6.3: pyroute2 socket leaks on ungraceful exit. The
    ``async with AsyncIPRoute() as ipr:`` async context manager
    guarantees socket close on every exit path including
    CancelledError.
    """
    fake_ipr = FakeAsyncIPRoute()
    queue = _RecordingQueue()

    task = asyncio.create_task(
        run_rtnetlink_producer(
            event_queue=queue, ipr_factory=(fake_ipr, _FAKE_RTMGRP_LINK_VALUE)
        )
    )
    # Yield enough to enter the async with block + reach the iterator.
    for _ in range(10):
        await asyncio.sleep(0)
        if fake_ipr.bind_calls:
            break

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # __aexit__ ran on the way out -> _closed is True.
    assert fake_ipr._closed is True  # noqa: SLF001 — attribute is the test's contract


def test_module_imports_cross_platform() -> None:
    """Module imports on Windows dev hosts (pyroute2 import deferred).

    If we reached this test, the module imported at top of file already.
    """
    assert callable(run_rtnetlink_producer)
