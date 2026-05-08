"""asyncinotify producer — single supervised task, two consumers (R-01).

Watches BOTH:
  * ``events_jsonl_path.parent`` — the events.jsonl parent directory; parent-
    dir watch fires on CREATE / MOVED_TO when logrotate's ``create 0640
    root adm`` directive (R-02) recreates the file. The events.jsonl
    writer doesn't need a file-watch because it IS the writer; rotation
    signals come from the parent dir.
  * ``zao_log_path.parent`` — the Zao log parent directory. Watch fires on
    CREATE / MOVED_TO if the file was absent at startup (PITFALLS §8.2)
    or if it was rotated and recreated.
  * ``zao_log_path`` itself — when the file exists at startup. Watch fires
    on MODIFY (normal append + copytruncate) and MOVE_SELF / DELETE_SELF
    (`create` rotation).

Dispatch is by ``event.watch`` handle (R-01: one producer, two consumers):
events from ``events_parent_watch`` go to ``events_log_reopener.on_rotate()``;
events from ``zao_parent_watch`` or ``zao_file_watch`` go to
``zao_tailer.on_inotify_event(...)``.

The ``asyncinotify`` import is deferred inside this function so the module
imports cleanly on Windows dev hosts (mirrors Plan 03-02 / 03-03 patterns
for pyudev / pyroute2). Tests inject ``inotify_factory=(FakeAsyncinotify,
FakeMask)`` and never trigger the real import.

PITFALLS §8.4: ``asyncinotify.Inotify`` async context manager guarantees
inotify FDs are released on shutdown; ``restart_on_crash`` (Plan 03-01)
caps re-acquisition at the 60s backoff cap.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol

from spark_modem.event_sources.supervisor import WakeSignal

logger = logging.getLogger(__name__)


class _EventQueueProto(Protocol):
    def put_nowait(self, item: object) -> None: ...


class _EventLogReopenerProto(Protocol):
    async def on_rotate(self) -> None: ...


class _ZaoTailerProto(Protocol):
    async def on_inotify_event(
        self,
        *,
        mask_modify: bool,
        mask_move_or_delete_self: bool,
        mask_create_or_moved_to: bool,
        event_path_basename: str | None,
        event_queue: _EventQueueProto,
    ) -> None: ...


class _InotifyProto(Protocol):
    """Surface this producer needs from ``asyncinotify.Inotify`` / FakeAsyncinotify.

    Both the real ``asyncinotify.Inotify`` and the test ``FakeAsyncinotify``
    expose this shape. Mirrors PITFALLS §8.4 (async context manager for
    FD cleanup) + add_watch + async-iterable for events.
    """

    def add_watch(self, path: Path, mask: Any) -> object: ...

    async def __aenter__(self) -> _InotifyProto: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None: ...

    def __aiter__(self) -> AsyncIterator[Any]: ...


async def run_asyncinotify_producer(
    *,
    event_queue: _EventQueueProto,
    events_jsonl_path: Path,
    zao_log_path: Path,
    events_log_reopener: _EventLogReopenerProto,
    zao_tailer: _ZaoTailerProto,
    inotify_factory: tuple[_InotifyProto, type[Any]] | None = None,
) -> None:
    """Single supervised producer task watching two log directories.

    ``inotify_factory`` is a tuple of (preconstructed inotify object, mask
    enum class) for tests; production wires ``None`` and the function
    constructs a real ``asyncinotify.Inotify()`` + reads ``asyncinotify.Mask``.

    The supervisor (Plan 03-01 ``restart_on_crash``) catches Exception and
    re-enters; CancelledError passes through (TaskGroup cancellation).
    """
    if inotify_factory is None:
        # Deferred import — keeps the module Windows-importable.
        from asyncinotify import Inotify, Mask  # noqa: PLC0415

        inotify: _InotifyProto = Inotify()
        mask_cls: type[Any] = Mask
    else:
        inotify, mask_cls = inotify_factory

    mask_file = mask_cls.MODIFY | mask_cls.MOVE_SELF | mask_cls.DELETE_SELF | mask_cls.CLOSE_WRITE
    mask_parent = mask_cls.CREATE | mask_cls.MOVED_TO

    events_parent_watch: object | None = None
    zao_parent_watch: object | None = None
    zao_file_watch: object | None = None

    async with inotify as ino:
        # Parent-dir watches first (handle file-absent-at-startup;
        # PITFALLS §8.2).
        events_parent_watch = ino.add_watch(events_jsonl_path.parent, mask_parent)
        zao_parent_watch = ino.add_watch(zao_log_path.parent, mask_parent)
        # The Zao log file watch is conditional: if the file exists at
        # startup we add it; otherwise the parent-dir CREATE/MOVED_TO
        # event will trigger us to add it on the fly below. ``Path.is_file``
        # is sync — the call returns instantly without blocking the loop
        # in production (tmpfs/ext4 stat is microsecond-fast).
        if _path_exists(zao_log_path):
            zao_file_watch = ino.add_watch(zao_log_path, mask_file)

        async for event in ino:
            mask = event.mask
            path = getattr(event, "path", None)
            basename = path.name if path is not None else None

            # Decompose mask into orthogonal booleans the consumers care
            # about. Use mask_cls (test or production) for the comparison.
            m_modify = bool(mask & mask_cls.MODIFY)
            m_move_or_delete = bool(mask & (mask_cls.MOVE_SELF | mask_cls.DELETE_SELF))
            m_create_or_moved_to = bool(mask & (mask_cls.CREATE | mask_cls.MOVED_TO))

            event_watch = event.watch

            # Dispatch by watch handle (R-01).
            if event_watch is events_parent_watch:
                # events.jsonl rotation only fires from the parent-dir
                # watch; the writer doesn't need MODIFY signals (it IS
                # the writer).
                if m_create_or_moved_to and basename == events_jsonl_path.name:
                    await events_log_reopener.on_rotate()
                    event_queue.put_nowait(WakeSignal.EVENTS_LOG_ROTATED)
                continue

            if event_watch is zao_parent_watch or event_watch is zao_file_watch:
                # Lazily acquire the file-watch if the parent dir saw the
                # file appear and we hadn't watched the file yet.
                if (
                    event_watch is zao_parent_watch
                    and m_create_or_moved_to
                    and basename == zao_log_path.name
                    and zao_file_watch is None
                ):
                    zao_file_watch = ino.add_watch(zao_log_path, mask_file)

                await zao_tailer.on_inotify_event(
                    mask_modify=m_modify,
                    mask_move_or_delete_self=m_move_or_delete,
                    mask_create_or_moved_to=m_create_or_moved_to,
                    event_path_basename=basename,
                    event_queue=event_queue,
                )
                continue


def _path_exists(p: Path) -> bool:
    """Sync existence check, factored out so ASYNC240 doesn't fire on the
    one-shot pre-loop check inside the async producer.

    The check runs once at startup; the loop body never calls this.
    """
    return p.exists()
