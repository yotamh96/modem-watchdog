"""FakeKmsgReader — test seam for ``event_sources.kmsg_producer``.

Exposes a ``(fd, read_fn)`` pair compatible with the producer's
``fd_factory`` injection. ``read_fn`` (the bound ``read`` method) pops
from an internal deque of bytes; raises ``BlockingIOError`` when the
deque is empty (mirrors ``os.read`` on an ``O_NONBLOCK`` fd that has
been drained).

PITFALLS §14.1 spirit: seam, don't shim — the producer takes a
factory argument so tests inject a Fake without monkey-patching
``os.read`` or opening real ``/dev/kmsg``.

Production-shape methods:
  * ``fileno() -> int`` — sentinel value; tests never invoke
    ``loop.add_reader`` with this fd.
  * ``read(fd, nbytes) -> bytes`` — drains the chunk queue; raises
    ``BlockingIOError`` when empty.

Test-only mutators:
  * ``inject_record(*, priority, seq, ts_us, message)`` — pushes one
    formatted ``<pri>,<seq>,<ts>,<flags>;<msg>`` record.
  * ``inject_raw(raw)`` — pushes raw bytes (e.g. malformed records).
  * ``inject_oserror(errno_value)`` — next ``read`` raises OSError.

Same dual-surface convention as ``tests/fakes/asyncinotify.py`` and
``tests/fakes/rtnetlink.py`` (production shape + test-only mutators).
"""

from __future__ import annotations

import os
from collections import deque


class _ErrorSentinel:
    """Marker pushed onto the chunk queue to trigger an OSError on read."""

    __slots__ = ("errno_value",)

    def __init__(self, errno_value: int) -> None:
        self.errno_value = errno_value


class FakeKmsgReader:
    """Records ``read`` calls; pops canned bytes / OSErrors from a deque."""

    def __init__(self) -> None:
        # Each item is either ``bytes`` (regular chunk) or ``_ErrorSentinel``
        # (raise OSError on next read).
        self._chunks: deque[bytes | _ErrorSentinel] = deque()
        self._fileno: int = 99  # sentinel; tests don't use loop.add_reader
        self.read_calls: list[int] = []

    def fileno(self) -> int:
        """Return the sentinel fd value."""
        return self._fileno

    def inject_record(
        self,
        *,
        priority: int = 6,
        seq: int,
        ts_us: int = 0,
        message: str,
    ) -> None:
        """Push one ``/dev/kmsg``-formatted record onto the queue.

        The kernel format is ``<priority>,<seq>,<ts_us>,<flags>;<message>\\n``.
        Tests use this for the common case of a single classifiable line.
        """
        record = f"{priority},{seq},{ts_us},-;{message}\n"
        self._chunks.append(record.encode("utf-8"))

    def inject_raw(self, raw: bytes) -> None:
        """Push arbitrary bytes onto the queue (e.g. malformed records)."""
        self._chunks.append(raw)

    def inject_oserror(self, errno_value: int) -> None:
        """Push a sentinel that makes the next ``read`` raise ``OSError``.

        Used to exercise ENOBUFS / EPIPE recovery paths without needing
        a real kernel-fd surface.
        """
        self._chunks.append(_ErrorSentinel(errno_value))

    def read(self, fd: int, nbytes: int) -> bytes:
        """Compatible with ``os.read(fd, nbytes)`` — pops the next chunk.

        Records every call's nbytes. Raises ``BlockingIOError`` when the
        queue is empty (mirrors ``os.read`` on an O_NONBLOCK fd). Raises
        ``OSError`` when the next item is an ``_ErrorSentinel``.
        """
        del fd  # signature parity only — sentinel value, not used
        self.read_calls.append(nbytes)
        if not self._chunks:
            raise BlockingIOError("no data")
        item = self._chunks.popleft()
        if isinstance(item, _ErrorSentinel):
            raise OSError(item.errno_value, os.strerror(item.errno_value))
        return item
