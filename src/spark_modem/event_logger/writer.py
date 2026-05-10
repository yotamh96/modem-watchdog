"""EventLogWriter — single-writer sync JSON Lines append.

Design (CONTEXT.md §"Claude's Discretion" — event_logger/ writer shape):
  - Sync append-with-flush; async queue deferred to Phase 2 if needed.
  - Single writer; O_APPEND so concurrent writers are kernel-serialized
    at line boundaries.
  - One os.write per append() of the full newline-terminated JSON bytes —
    on Linux, write(2) of <PIPE_BUF (4096) bytes is atomic. We don't enforce
    the size limit here; events are typically <500 bytes.
  - Caller serializes via spark_modem.wire.EventAdapter.dump_json.

Phase 3 logrotate (FR-43.1) closes this writer on MOVE_SELF / DELETE_SELF
inotify event and constructs a new one for the freshly-rotated file.
"""

from __future__ import annotations

import contextlib
import os
from collections import deque
from pathlib import Path
from types import TracebackType
from typing import Self

from spark_modem.state_store.atomic import _fsync_directory
from spark_modem.wire.events import (
    ActionExecuted,
    ActionFailed,
    ActionPlanned,
    ActionSkipped,
    DaemonStarted,
    DaemonStopped,
    Event,
    EventAdapter,
    EventSourceCrashed,
    MaintenanceWindowEnded,
    MaintenanceWindowStarted,
    SchemaDowngradePending,
    SimSwapped,
    StateTransition,
    UsbPathMismatch,
    WebhookDropped,
)

_MODE = 0o640

# R-03: in-memory buffer cap during the reopen window. 1000 events x ~500 B
# per event = ~500 KiB worst case — bounded memory cost. Overflow is silent
# at the deque level (oldest dropped) and observable via reopen_overflow_count.
_REOPEN_BUFFER_MAX = 1000

# Concrete types that make up the Event discriminated union.
# Used for isinstance checks in append() so callers get a clear TypeError
# rather than a pydantic ValidationError on bogus input.
#
# Plan 04-05 / B-04: ActionSkipped (Phase 4) added; pre-existing gaps for
# SimSwapped + EventSourceCrashed (Phase 3) closed at the same time so the
# tuple covers the full Event union -- a future variant addition that
# forgets this list would surface as a TypeError on first append (Rule 2:
# auto-add missing critical functionality at the wire boundary).
_EVENT_TYPES: tuple[type, ...] = (
    ActionExecuted,
    ActionFailed,
    ActionPlanned,
    ActionSkipped,
    DaemonStarted,
    DaemonStopped,
    EventSourceCrashed,
    MaintenanceWindowEnded,
    MaintenanceWindowStarted,
    SchemaDowngradePending,
    SimSwapped,
    StateTransition,
    UsbPathMismatch,
    WebhookDropped,
)


class EventLogClosedError(RuntimeError):
    """Append attempted on a closed writer."""


class EventLogWriter:
    """Single-writer JSON Lines append for events.jsonl.

    Use as a context manager:
        with EventLogWriter("/var/log/spark-modem-watchdog/events.jsonl") as w:
            w.append(event)

    Or own the lifetime explicitly: writer = EventLogWriter(path); ... ; writer.close().
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        parent = self._path.parent
        # Track whether we're creating the directory for the first time so we
        # can fsync it. Without this, a power loss between mkdir and the first
        # append can lose the events.jsonl file on remount (FR-43 / FR-43.1).
        parent_existed = parent.exists()
        parent.mkdir(parents=True, exist_ok=True)
        self._fd: int | None = os.open(
            str(self._path),
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            _MODE,
        )
        if not parent_existed:
            # Fsync the newly-created directory so its entry is durable before
            # the first append. On Windows _fsync_directory is a no-op (the
            # daemon never runs there; this is a dev-host accommodation).
            _fsync_directory(parent, self._path)
        # Phase 3 R-03: in-memory buffer catches writes during the reopen
        # window (microseconds in the happy path; defense for the
        # pathological disk-full / EPERM case). deque(maxlen=1000) silently
        # drops oldest on overflow; reopen_overflow_count tracks drops so
        # Plan 03-06 metrics integration can surface
        # events_dropped_total{reason="reopen_overflow"}.
        self._reopen_buffer: deque[bytes] = deque(maxlen=_REOPEN_BUFFER_MAX)
        self._reopening: bool = False
        self._reopen_overflow_count: int = 0

    def append(self, event: Event) -> None:
        """Serialize and write one newline-terminated JSON line.

        Raises:
          EventLogClosedError if the writer was closed.
          TypeError if `event` is not an Event-union member.

        During the reopen window (``self._reopening`` True, set by
        ``EventLogReopener``), the line is buffered to ``_reopen_buffer``
        instead of written; ``reopen()`` flushes the buffer to the new fd.
        """
        fd = self._fd
        if fd is None and not self._reopening:
            raise EventLogClosedError(f"writer for {self._path!s} is closed")
        if not isinstance(event, _EVENT_TYPES):
            raise TypeError(f"expected an Event union member, got {type(event).__name__!r}")
        line = EventAdapter.dump_json(event) + b"\n"
        if self._reopening:
            # Buffer until reopen completes. deque(maxlen=1000) silently drops
            # oldest on overflow; track count so Plan 03-06 metrics integration
            # can surface it (R-03 overflow case).
            if len(self._reopen_buffer) >= _REOPEN_BUFFER_MAX:
                self._reopen_overflow_count += 1
            self._reopen_buffer.append(line)
            return
        # fd is not None here (the early-return above handles fd is None).
        assert fd is not None
        os.write(fd, line)

    def reopen(self) -> None:
        """Close the current fd, reopen at the same path, flush buffered writes.

        Called by the asyncinotify dispatcher (Plan 03-04
        ``event_logger/inotify_reopener.py``) when logrotate moves the inode
        out from under us. R-03: the reopen window is microseconds in the
        happy path (single coroutine, no awaits between detect and reopen);
        the buffer is defense for the pathological case of disk-full / EPERM
        on the new fd.

        After reopen completes, ``_reopening`` is cleared and subsequent
        appends route directly to the new fd again.
        """
        self._reopening = True
        try:
            old_fd = self._fd
            self._fd = None
            if old_fd is not None:
                with contextlib.suppress(OSError):
                    os.close(old_fd)
            # Re-open at the same path; logrotate `create 0640 root adm`
            # has already created it (R-02), but O_CREAT defends against the
            # race where asyncinotify fires before the create.
            self._fd = os.open(
                str(self._path),
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                _MODE,
            )
            # Flush buffered writes in FIFO order.
            while self._reopen_buffer:
                buffered = self._reopen_buffer.popleft()
                os.write(self._fd, buffered)
        finally:
            self._reopening = False

    @property
    def reopen_overflow_count(self) -> int:
        """Count of buffered writes dropped due to deque(maxlen=1000) overflow.

        Plan 03-06 wires this into ``events_dropped_total{reason="reopen_overflow"}``.
        """
        return self._reopen_overflow_count

    def fileno(self) -> int:
        fd = self._fd
        if fd is None:
            raise EventLogClosedError(f"writer for {self._path!s} is closed")
        return fd

    def close(self) -> None:
        fd = self._fd
        self._fd = None
        if fd is not None:
            with contextlib.suppress(OSError):
                os.close(fd)

    # Context-manager protocol.
    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()
