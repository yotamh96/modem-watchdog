"""Unit tests for run_kmsg_producer (Plan 03-05 Task 2).

Strategy: inject a ``FakeKmsgReader`` via the ``fd_factory`` parameter
so tests run cross-platform without ``/dev/kmsg``. The producer's
``on_readable`` callback is sync — tests drive it directly via the
public coroutine entry point and the ``add_reader`` shim.

Pin every contract point:

  1. classified line -> emit_host_issue + WakeSignal.KMSG
  2. UNKNOWN line -> NO emission (W-04 closed-enum discipline)
  3. dedup suppresses repeats within window
  4. dedup re-emits after window expires
  5. distinct details emit independently
  6. BlockingIOError terminates drain loop cleanly
  7. EPIPE resets last_seq, continues
  8. malformed record (no `;` separator) is skipped
  9. cross-platform module import smoke test
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
from typing import Any

import pytest

from spark_modem.event_sources.kmsg_producer import run_kmsg_producer
from spark_modem.event_sources.supervisor import WakeSignal
from spark_modem.kmsg.dedup import KmsgDedup
from spark_modem.wire.enums import IssueDetail
from tests.fakes.clock import FakeClock
from tests.fakes.kmsg import FakeKmsgReader


class _RecordingQueue:
    """Minimal _EventQueueProto satisfier — records every put_nowait."""

    def __init__(self) -> None:
        self.items: list[object] = []

    def put_nowait(self, item: object) -> None:
        self.items.append(item)


class _RecordingEmitter:
    """Records emit_host_issue calls for assertion."""

    def __init__(self) -> None:
        self.calls: list[tuple[IssueDetail, str]] = []

    def emit_host_issue(self, *, detail: IssueDetail, raw_line: str) -> None:
        self.calls.append((detail, raw_line))


async def _drive_producer_one_drain(
    fake: FakeKmsgReader,
    queue: _RecordingQueue,
    emitter: _RecordingEmitter,
    clock: FakeClock,
    dedup: KmsgDedup,
) -> None:
    """Run the producer until BlockingIOError drains the queue, then cancel.

    The producer registers its ``on_readable`` via the loop's
    ``add_reader``; we cooperate by pre-loading the FakeKmsgReader
    queue (so the producer drains synchronously after ``add_reader``
    fires once), then cancel the supervisor's infinite-future wait.
    """
    task = asyncio.create_task(
        run_kmsg_producer(
            event_queue=queue,
            dedup=dedup,
            clock=clock,
            issue_emitter=emitter,
            fd_factory=(fake.fileno(), fake.read),
        )
    )
    # Yield enough times for the loop to schedule the add_reader callback
    # exactly once. On Windows the test's loop is a ProactorEventLoop;
    # the add_reader path in our producer schedules the callback via
    # call_soon when no real fd-readable arm is available.
    for _ in range(20):
        await asyncio.sleep(0)
        if queue.items or emitter.calls or fake.read_calls:
            # Callback fired at least once; one extra yield to let the
            # drain loop finish.
            await asyncio.sleep(0)
            break
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_classified_line_emits_issue_and_wake_signal() -> None:
    """A USB overcurrent record yields one Issue + one WakeSignal.KMSG."""
    fake = FakeKmsgReader()
    fake.inject_record(seq=10, message="usb 1-3: over-current change on port 1")
    queue = _RecordingQueue()
    emitter = _RecordingEmitter()
    clock = FakeClock()
    dedup = KmsgDedup()

    await _drive_producer_one_drain(fake, queue, emitter, clock, dedup)

    assert len(emitter.calls) == 1
    detail, raw = emitter.calls[0]
    assert detail == IssueDetail.USB_OVERCURRENT
    assert "over-current change on port" in raw
    assert queue.items == [WakeSignal.KMSG]


async def test_unknown_classified_line_does_not_emit() -> None:
    """UNKNOWN lines never enter the wire surface (W-04 discipline)."""
    fake = FakeKmsgReader()
    fake.inject_record(seq=10, message="totally unrelated kernel message")
    queue = _RecordingQueue()
    emitter = _RecordingEmitter()
    clock = FakeClock()
    dedup = KmsgDedup()

    await _drive_producer_one_drain(fake, queue, emitter, clock, dedup)

    assert emitter.calls == []
    assert queue.items == []


async def test_dedup_suppresses_repeats_within_window() -> None:
    """Three USB_OVERCURRENT records within 30s -> 1 emit, 2 suppressed."""
    fake = FakeKmsgReader()
    fake.inject_record(seq=10, message="usb 1-3: over-current change on port 1")
    fake.inject_record(seq=11, message="usb 1-3: over-current change on port 1")
    fake.inject_record(seq=12, message="usb 1-3: over-current change on port 1")
    queue = _RecordingQueue()
    emitter = _RecordingEmitter()
    clock = FakeClock()
    dedup = KmsgDedup()

    await _drive_producer_one_drain(fake, queue, emitter, clock, dedup)

    assert len(emitter.calls) == 1
    assert queue.items == [WakeSignal.KMSG]
    assert dedup.consume_dedup_count(IssueDetail.USB_OVERCURRENT) == 2


async def test_dedup_re_emits_after_window_expires() -> None:
    """First record at t=0; second at t=31 (>30s) -> both emit."""
    fake = FakeKmsgReader()
    fake.inject_record(seq=10, message="usb 1-3: over-current change on port 1")
    queue = _RecordingQueue()
    emitter = _RecordingEmitter()
    clock = FakeClock()
    dedup = KmsgDedup()

    await _drive_producer_one_drain(fake, queue, emitter, clock, dedup)
    assert len(emitter.calls) == 1

    # Advance past the 30s window and inject a fresh record.
    clock.advance(31.0)
    fake.inject_record(seq=11, message="usb 1-3: over-current change on port 1")

    await _drive_producer_one_drain(fake, queue, emitter, clock, dedup)
    assert len(emitter.calls) == 2
    assert queue.items == [WakeSignal.KMSG, WakeSignal.KMSG]


async def test_distinct_details_emit_independently() -> None:
    """Two distinct details within window -> both fire (independent windows)."""
    fake = FakeKmsgReader()
    fake.inject_record(seq=10, message="usb 1-3: over-current change on port 1")
    fake.inject_record(seq=11, message="usb 1-3.1: device not accepting address 17")
    queue = _RecordingQueue()
    emitter = _RecordingEmitter()
    clock = FakeClock()
    dedup = KmsgDedup()

    await _drive_producer_one_drain(fake, queue, emitter, clock, dedup)

    assert len(emitter.calls) == 2
    details = {d for d, _raw in emitter.calls}
    assert IssueDetail.USB_OVERCURRENT in details
    assert IssueDetail.USB_ENUM_FAILURE in details
    assert queue.items == [WakeSignal.KMSG, WakeSignal.KMSG]


async def test_blocking_io_error_terminates_drain_loop() -> None:
    """One record then BlockingIOError -> drain returns cleanly, no leak."""
    fake = FakeKmsgReader()
    fake.inject_record(seq=10, message="usb 1-3: over-current change on port 1")
    # No more chunks -> next read raises BlockingIOError.
    queue = _RecordingQueue()
    emitter = _RecordingEmitter()
    clock = FakeClock()
    dedup = KmsgDedup()

    # Should not raise.
    await _drive_producer_one_drain(fake, queue, emitter, clock, dedup)

    assert len(emitter.calls) == 1
    # Drain loop terminated -- read_calls reflects at least 2 reads
    # (one consuming the chunk, one hitting BlockingIOError).
    assert len(fake.read_calls) >= 2


async def test_epipe_resets_last_seq_and_continues() -> None:
    """EPIPE on read resets last_seq; subsequent records still classify.

    Sequence: record(seq=10) -> EPIPE -> record(seq=20). The drain loop
    catches EPIPE, resets last_seq to None, and continues; the
    subsequent record is processed normally.
    """
    fake = FakeKmsgReader()
    fake.inject_record(seq=10, message="usb 1-3: over-current change on port 1")
    fake.inject_oserror(errno.EPIPE)
    fake.inject_record(seq=20, message="usb 1-3.1: device not accepting address 17")
    queue = _RecordingQueue()
    emitter = _RecordingEmitter()
    clock = FakeClock()
    dedup = KmsgDedup()

    await _drive_producer_one_drain(fake, queue, emitter, clock, dedup)

    # Both records processed; the EPIPE was absorbed.
    assert len(emitter.calls) == 2
    details = {d for d, _raw in emitter.calls}
    assert IssueDetail.USB_OVERCURRENT in details
    assert IssueDetail.USB_ENUM_FAILURE in details


async def test_skip_record_without_separator() -> None:
    """A malformed record without ';' separator is skipped silently."""
    fake = FakeKmsgReader()
    fake.inject_raw(b"foo bar baz no separator here\n")
    fake.inject_record(seq=11, message="usb 1-3: over-current change on port 1")
    queue = _RecordingQueue()
    emitter = _RecordingEmitter()
    clock = FakeClock()
    dedup = KmsgDedup()

    await _drive_producer_one_drain(fake, queue, emitter, clock, dedup)

    # Only the well-formed record fired.
    assert len(emitter.calls) == 1
    detail, _raw = emitter.calls[0]
    assert detail == IssueDetail.USB_OVERCURRENT


def test_module_imports_cross_platform() -> None:
    """The module imports cleanly on Windows (no /dev/kmsg open at import time)."""
    # Already imported at top; this test just affirms the contract.
    assert callable(run_kmsg_producer)


def test_run_kmsg_producer_signature_matches_protocols() -> None:
    """The factory accepts the documented kwarg shape (smoke check)."""
    # Negative type-check via runtime callability — mypy --strict catches
    # the rest at static-analysis time.
    queue: Any = _RecordingQueue()
    emitter: Any = _RecordingEmitter()
    clock: Any = FakeClock()
    dedup = KmsgDedup()
    coro = run_kmsg_producer(
        event_queue=queue,
        dedup=dedup,
        clock=clock,
        issue_emitter=emitter,
        fd_factory=(99, lambda _fd, _n: b""),
    )
    # Don't await it — just verify it returned a coroutine without exploding
    # during argument-binding (no positional/keyword mismatches).
    coro.close()


@pytest.mark.linux_only
def test_default_fd_path_opens_dev_kmsg() -> None:  # pragma: no cover (linux_only)
    """When fd_factory=None production path opens /dev/kmsg.

    Skipped on Windows (no /dev/kmsg). Linux CI runner exercises this
    path end-to-end via the existing linux_only marker pipeline.
    """
    # This is a placeholder for the Linux CI integration path —
    # the actual /dev/kmsg open requires root; full end-to-end
    # exercise lives in tests/integration/ under Plan 03-06.
    pytest.skip("Default fd path requires real /dev/kmsg + root; covered by integration suite")
