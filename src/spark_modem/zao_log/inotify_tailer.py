"""ZaoLogInotifyTailer — inotify-driven Zao log reader (R-04 / FR-43.1).

Replaces parser.py at runtime; parser.py stays as the test/replay helper.
Satisfies the existing ``ZaoLogTailer`` Protocol (``is_line_active`` +
``snapshot``) so observer/ doesn't change.

Handles BOTH rotation modes per PITFALLS §8.1:

  * `create` mode (logrotate creates a fresh file, the old inode is gone):
    asyncinotify reports ``IN_MOVE_SELF`` / ``IN_DELETE_SELF`` on the
    file watch, then ``IN_CREATE`` / ``IN_MOVED_TO`` on the parent-dir
    watch. The tailer resets to "unknown" on move/delete, re-parses on
    create.
  * `copytruncate` mode (logrotate keeps the inode, copies content out,
    truncates to 0): asyncinotify reports only ``IN_MODIFY``. We compare
    ``st.st_size`` against ``self._last_offset`` — a shrink means
    truncation; reset offset and re-parse.
  * Opportunistic inode compare: every MODIFY also checks ``st.st_ino``
    against the cached inode. If it changed, treat as rotation
    (defensive against missed move/delete events).

The actual RASCOW_STAT parsing is delegated to ``ZaoLogParser`` which
already walks the file backwards and extracts the latest block. We don't
need byte-precise offset tracking because ``ZaoLogParser.snapshot()`` is
idempotent against the current file contents.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

from spark_modem.zao_log.parser import ZaoLogParser
from spark_modem.zao_log.snapshot import ZaoSnapshot

logger = logging.getLogger(__name__)


class _EventQueueProto(Protocol):
    """Minimal event-queue surface — just put_nowait."""

    def put_nowait(self, item: object) -> None: ...


class ZaoLogInotifyTailer:
    """ZaoLogTailer Protocol satisfier; inotify-driven (R-04).

    The asyncinotify producer (Plan 03-04 ``event_sources/
    asyncinotify_producer.py``) calls ``on_inotify_event`` for each event
    affecting the log path or its parent directory. ``is_line_active`` /
    ``snapshot`` is the Protocol surface the observer reads (FR-10).
    """

    def __init__(self, *, log_path: Path) -> None:
        self._log_path = log_path
        # Reuse the Phase 2 parser's regex + block-walking logic; only the
        # "where does raw come from" changes (inotify-driven re-parse vs
        # cycle-driven file read).
        self._parser = ZaoLogParser(log_path)
        self._last_offset: int = 0
        self._last_inode: int | None = None
        # Initialize from current state if file exists; otherwise wait for
        # the parent-dir CREATE/MOVED_TO event to arrive (PITFALLS §8.2).
        self._snapshot: ZaoSnapshot = ZaoSnapshot.unknown(reason="zao_log_missing")
        try:
            st = log_path.stat()
        except FileNotFoundError:
            return
        else:
            self._last_inode = st.st_ino
            self._last_offset = st.st_size
            self._snapshot = self._parser.snapshot()

    def is_line_active(self, line_idx: int) -> bool:
        """FR-10 gate; delegates to the cached snapshot."""
        return self._snapshot.is_line_active(line_idx)

    def snapshot(self) -> ZaoSnapshot:
        """Return the current cached snapshot (last parsed RASCOW_STAT block)."""
        return self._snapshot

    async def on_inotify_event(
        self,
        *,
        mask_modify: bool,
        mask_move_or_delete_self: bool,
        mask_create_or_moved_to: bool,
        event_path_basename: str | None,
        event_queue: _EventQueueProto,
    ) -> None:
        """Handle one inotify event from the asyncinotify producer.

        The caller has already extracted three orthogonal mask booleans +
        the event basename so this method is decoupled from
        ``asyncinotify.Mask`` specifics — Windows tests use ``FakeMask``
        and production uses real ``Mask``; both produce the same booleans.
        """
        if mask_move_or_delete_self:
            # `create` mode rotation: file moved out from under us, or
            # explicitly deleted. Reset offset; the parent-dir CREATE/
            # MOVED_TO event will follow shortly.
            self._last_offset = 0
            self._snapshot = ZaoSnapshot.unknown(reason="zao_log_missing")
            event_queue.put_nowait(_zao_wake_signal())
            return

        if mask_create_or_moved_to and event_path_basename == self._log_path.name:
            # File reappeared after `create` mode rotation. Re-stat and
            # re-parse from the top.
            try:
                st = self._log_path.stat()
            except FileNotFoundError:
                return
            self._last_inode = st.st_ino
            self._last_offset = st.st_size
            self._snapshot = self._parser.snapshot()
            event_queue.put_nowait(_zao_wake_signal())
            return

        if mask_modify:
            # MODIFY can mean: normal append (st_size grew), or copytruncate
            # (st_size shrank below last_offset), or — defensively —
            # missed-rotation followed by re-creation (inode changed).
            try:
                st = self._log_path.stat()
            except FileNotFoundError:
                # File vanished between event and stat; wait for the
                # parent-dir CREATE/MOVED_TO event.
                return

            if st.st_size < self._last_offset:
                # COPYTRUNCATE detected (PITFALLS §8.1): same inode,
                # smaller content. Reset offset, full re-read.
                self._last_offset = 0
                logger.info(
                    "zao_log copytruncate detected path=%s",
                    self._log_path,
                )

            if self._last_inode is not None and st.st_ino != self._last_inode:
                # Opportunistic inode change — defensive for the case where
                # an IN_MOVE_SELF was missed. Reset offset, re-read.
                logger.info(
                    "zao_log inode changed path=%s old=%d new=%d",
                    self._log_path,
                    self._last_inode,
                    st.st_ino,
                )
                self._last_inode = st.st_ino
                self._last_offset = 0

            # Re-parse — the parser walks the file backwards and extracts
            # the latest RASCOW_STAT block; snapshot() is idempotent
            # against the current file contents.
            self._snapshot = self._parser.snapshot()
            self._last_offset = st.st_size
            event_queue.put_nowait(_zao_wake_signal())


def _zao_wake_signal() -> object:
    """Deferred WakeSignal import to avoid circular import event_sources <-> zao_log."""
    from spark_modem.event_sources.supervisor import WakeSignal  # noqa: PLC0415

    return WakeSignal.ZAO_LOG
