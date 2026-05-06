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
from pathlib import Path
from types import TracebackType
from typing import Self

from spark_modem.state_store.atomic import _fsync_directory
from spark_modem.wire.events import (
    ActionExecuted,
    ActionFailed,
    ActionPlanned,
    DaemonStarted,
    DaemonStopped,
    Event,
    EventAdapter,
    MaintenanceWindowEnded,
    MaintenanceWindowStarted,
    SchemaDowngradePending,
    StateTransition,
    UsbPathMismatch,
    WebhookDropped,
)

_MODE = 0o640

# Concrete types that make up the Event discriminated union.
# Used for isinstance checks in append() so callers get a clear TypeError
# rather than a pydantic ValidationError on bogus input.
_EVENT_TYPES: tuple[type, ...] = (
    ActionExecuted,
    ActionFailed,
    ActionPlanned,
    DaemonStarted,
    DaemonStopped,
    MaintenanceWindowEnded,
    MaintenanceWindowStarted,
    SchemaDowngradePending,
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

    def append(self, event: Event) -> None:
        """Serialize and write one newline-terminated JSON line.

        Raises:
          EventLogClosedError if the writer was closed.
          TypeError if `event` is not an Event-union member.
        """
        fd = self._fd
        if fd is None:
            raise EventLogClosedError(f"writer for {self._path!s} is closed")
        if not isinstance(event, _EVENT_TYPES):
            raise TypeError(f"expected an Event union member, got {type(event).__name__!r}")
        line = EventAdapter.dump_json(event)  # bytes, no trailing newline
        os.write(fd, line + b"\n")

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
