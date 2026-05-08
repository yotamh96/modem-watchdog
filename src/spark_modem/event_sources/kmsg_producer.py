"""kmsg producer — non-blocking ``/dev/kmsg`` reader (E-03 / FR-14).

CLAUDE.md anti-pattern: blocking ``read()`` on ``/dev/kmsg`` from the
asyncio loop is FORBIDDEN. ``/dev/kmsg`` is a streaming device — a naive
``read()`` blocks until the next kernel message arrives, freezing the
entire event loop. We open with ``O_RDONLY|O_NONBLOCK`` + ``lseek(SEEK_END)``
+ ``loop.add_reader``, then drain the kernel queue inside the readable
callback until ``BlockingIOError``.

Pipeline per E-03:
  1. ``on_readable`` callback drains the kernel queue with non-blocking
     ``os.read(fd, 8192)`` until ``BlockingIOError`` (no more data).
  2. Parse ``<priority>,<seq>,<ts>,<flags>;<message>`` header.
  3. ``classify(message_line) -> IssueDetail``.
  4. ``dedup.should_emit(detail, now_monotonic=...)`` -> bool.
  5. If emit: ``issue_emitter.emit_host_issue(detail=, raw_line=)`` +
     ``event_queue.put_nowait(WakeSignal.KMSG)``.

UNKNOWN-classified lines are dropped (no Issue emitted) — W-04 closed-
enum discipline. The raw line stays in the daemon's logger only, never
on the wire.

EPIPE on ring-buffer wrap (PITFALLS §5 / RESEARCH.md Pattern 5): the
kernel's ring buffer has a finite size; a slow reader falls behind
and the next read returns EPIPE. We reset ``last_seq`` to None and
keep draining — sequence-gap counting resumes on the next record.

The module imports cleanly on Windows dev hosts: ``/dev/kmsg`` is
opened lazily inside ``run_kmsg_producer``, never at import time.
Tests inject an ``fd_factory`` tuple ``(fd, read_fn)`` and never
trigger the real ``os.open``.
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import logging
import os
from collections.abc import Callable
from typing import Final, Protocol

from spark_modem.event_sources.supervisor import WakeSignal
from spark_modem.kmsg.classifier import classify
from spark_modem.kmsg.dedup import KmsgDedup
from spark_modem.wire.enums import IssueDetail

logger = logging.getLogger(__name__)

_KMSG_DEV: Final[str] = "/dev/kmsg"
_READ_CHUNK_BYTES: Final[int] = 8192
# kmsg header shape: ``<priority>,<sequence>,<timestamp_us>,<flags>;<msg>``.
# We only need the sequence (field index 1) for gap detection — the
# header must contain at least priority + sequence to be parseable.
_KMSG_HEADER_MIN_FIELDS: Final[int] = 2


class _EventQueueProto(Protocol):
    """Minimal event-queue surface — supervisor's ``CycleScheduler.event_queue``.

    ``put_nowait`` is the only method the producer calls; queue overflow
    drops the signal silently (acceptable per ADR-0002 — a missed signal
    just means the cycle waits for the 30 s polling deadline instead).
    """

    def put_nowait(self, item: object) -> None: ...


class _ClockProto(Protocol):
    """Minimal monotonic-clock surface (CLAUDE.md invariant #4).

    Co-located so the producer doesn't import the production clock
    module — keeps tests simple via ``FakeClock`` injection.
    """

    def monotonic(self) -> float: ...


class _IssueEmitterProto(Protocol):
    """Emits an Issue(who=WhoHost, category=host, detail=...) into the cycle.

    Plan 03-06 wires the production emitter (probably an extension of
    the existing event_logger writer + a host-issue accumulator on the
    cycle driver). Plan 03-05 just defines the surface and tests with
    a recording fake.
    """

    def emit_host_issue(self, *, detail: IssueDetail, raw_line: str) -> None: ...


def _open_kmsg() -> int:
    """Open ``/dev/kmsg`` in non-blocking mode; skip historical buffer."""
    fd = os.open(_KMSG_DEV, os.O_RDONLY | os.O_NONBLOCK)
    os.lseek(fd, 0, os.SEEK_END)
    return fd


def _parse_kmsg_record(chunk: bytes) -> tuple[int | None, str | None]:
    """Parse ``<priority>,<seq>,<ts>,<flags>;<message>`` — return ``(seq, line)``.

    Kernel guarantees one full record per ``read()`` (no partial
    records). Continuation lines after the message are ignored — the
    classifier only inspects the message field. Returns ``(None, None)``
    for malformed records (no separator); the caller skips and
    continues.
    """
    try:
        text = chunk.decode("utf-8", errors="replace")
    except UnicodeDecodeError:
        return None, None
    header, sep, payload = text.partition(";")
    if not sep:
        return None, None  # malformed — no separator
    fields = header.split(",")
    seq: int | None = None
    if len(fields) >= _KMSG_HEADER_MIN_FIELDS:
        try:
            seq = int(fields[1])
        except ValueError:
            seq = None
    line = payload.split("\n", 1)[0]
    return seq, line


async def run_kmsg_producer(
    *,
    event_queue: _EventQueueProto,
    dedup: KmsgDedup,
    clock: _ClockProto,
    issue_emitter: _IssueEmitterProto,
    fd_factory: tuple[int, Callable[[int, int], bytes]] | None = None,
) -> None:
    """Read ``/dev/kmsg`` in non-blocking mode; classify; dedup; emit.

    Parameters
    ----------
    event_queue
        The cycle scheduler's ``event_queue``. Producers ``put_nowait``
        opaque sentinels only (E-02).
    dedup
        ``KmsgDedup`` instance shared across cycles. Per-detail 30s
        sliding window; ``consume_dedup_count`` returns the suppressed
        count for Plan 03-06's metric surface.
    clock
        Monotonic-clock source. ``KmsgDedup.should_emit`` requires
        ``now_monotonic`` (CLAUDE.md invariant #4).
    issue_emitter
        Plan 03-05 takes a Protocol; Plan 03-06 wires the production
        emitter. Tests inject a recording fake.
    fd_factory
        Optional ``(fd, read_fn)`` tuple. Tests inject this; production
        wires None and ``/dev/kmsg`` is opened lazily inside the
        function.

    The supervisor (``restart_on_crash`` from Plan 03-01) wraps this
    coroutine; OSError outside EPIPE escapes and triggers a re-entry
    with bounded backoff (E-01).
    """
    loop = asyncio.get_running_loop()
    if fd_factory is None:
        fd = _open_kmsg()
        read_fn: Callable[[int, int], bytes] = os.read
    else:
        fd, read_fn = fd_factory

    last_seq: int | None = None
    sequence_gaps_total: int = 0  # local self-health counter (Plan 03-06 wires Prom)

    def on_readable() -> None:
        nonlocal last_seq, sequence_gaps_total
        while True:
            try:
                chunk = read_fn(fd, _READ_CHUNK_BYTES)
            except BlockingIOError:
                return
            except OSError as exc:
                if exc.errno == errno.EPIPE:
                    # Reader fell behind; ring buffer wrapped (PITFALLS).
                    # Reset last_seq and continue draining — the next
                    # successful read picks up at the new position.
                    last_seq = None
                    continue
                raise
            if not chunk:
                return
            seq, line = _parse_kmsg_record(chunk)
            if line is None:
                continue  # malformed record — skip
            if seq is not None and last_seq is not None and seq > last_seq + 1:
                sequence_gaps_total += 1
            if seq is not None:
                last_seq = seq
            detail = classify(line)
            if detail is IssueDetail.UNKNOWN:
                # W-04 closed-enum discipline: don't emit Issues for
                # unclassified lines. Raw line preserved in logs for
                # forensic but never enters the wire detail field.
                continue
            if dedup.should_emit(detail, now_monotonic=clock.monotonic()):
                issue_emitter.emit_host_issue(detail=detail, raw_line=line)
                event_queue.put_nowait(WakeSignal.KMSG)

    # In tests the injected fd is a sentinel value not registered with
    # the OS event loop — call_soon ensures on_readable fires once.
    # In production the real fd is registered with loop.add_reader and
    # the kernel signals readability whenever new ring-buffer data
    # arrives.
    if fd_factory is None:
        loop.add_reader(fd, on_readable)
    else:
        # Test path: schedule one drain pass via call_soon; tests
        # inject all expected records up front, the drain consumes
        # them in one pass, then BlockingIOError terminates the loop.
        loop.call_soon(on_readable)

    try:
        await asyncio.Future()  # supervisor cancels via CancelledError
    finally:
        if fd_factory is None:
            with contextlib.suppress(OSError):
                loop.remove_reader(fd)
            with contextlib.suppress(OSError):
                os.close(fd)
        # Tests own the injected fd lifecycle — don't close it here.
