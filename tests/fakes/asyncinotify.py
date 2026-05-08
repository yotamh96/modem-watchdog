"""FakeAsyncinotify -- test seam for asyncinotify producer tests.

PITFALLS §8.1/§8.2/§8.3 prescribe the dual-mode logrotate handling
(create vs copytruncate) and the parent-dir watch for files absent at
startup. This fake yields canned event sequences so producers can be
exercised without touching real inotify FDs (which the Windows dev host
doesn't have).

Used by:
  - tests/unit/event_sources/test_asyncinotify_producer.py (Plan 03-04)
  - tests/unit/zao_log/test_inotify_tailer_dual_mode.py (Plan 03-04)
  - tests/integration/test_lifecycle.py (Plan 03-06; conftest selects
    real Inotify on Linux runners and Fake on Windows skip-path)

Surface mirrors asyncinotify's ``Inotify`` class:
  - ``add_watch(path, mask)`` returns an opaque watch handle.
  - ``rm_watch(handle)`` removes a watch (no-op for the fake; tests
    verify rm_watch was called via a separate counter if they care).
  - ``__aiter__`` / ``__anext__`` async-iterate over queued events.
  - ``__aenter__`` / ``__aexit__`` async context manager (asyncinotify
    pattern; PITFALLS §8.4: watch-FD cleanup on shutdown).

Test-only mutator surface (not on production Protocol):
  - ``inject_event(mask, path)`` queues a synthetic event for the next
    ``__anext__`` pull (production Inotify never exposes this).
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import IntFlag
from pathlib import Path
from types import TracebackType
from typing import Self


class FakeMask(IntFlag):
    """Mirrors ``asyncinotify.Mask`` members the daemon uses (PITFALLS §8).

    Real ``asyncinotify.Mask`` is a much wider IntFlag; we expose only
    the members Phase 3 producer tests actually exercise. Adding more
    here is cheap as new producers (Plans 03-04..03-06) need them.
    """

    MODIFY = 1
    MOVE_SELF = 2
    DELETE_SELF = 4
    CLOSE_WRITE = 8
    CREATE = 16
    MOVED_TO = 32


@dataclass(frozen=True)
class FakeInotifyEvent:
    """Mirrors the shape of ``asyncinotify.Event`` consumed by producers."""

    mask: FakeMask
    path: Path | None
    watch: object  # opaque watch handle returned by add_watch


class FakeAsyncinotify:
    """Async-iterable fake of ``asyncinotify.Inotify``.

    Tests use ``inject_event()`` to push synthetic events that the next
    ``__anext__`` pull will return. ``close()`` causes the iterator to
    raise ``StopAsyncIteration`` once the queue is drained.
    """

    def __init__(self) -> None:
        self._queue: deque[FakeInotifyEvent] = deque()
        self._watches: list[tuple[Path, FakeMask]] = []
        self._closed: bool = False

    @property
    def watches(self) -> list[tuple[Path, FakeMask]]:
        """Defensive copy of the (path, mask) tuples currently being watched."""
        return list(self._watches)

    def add_watch(self, path: Path, mask: FakeMask) -> object:
        """Register a watch and return an opaque handle.

        Production ``asyncinotify.Inotify.add_watch`` returns a
        ``Watch`` instance that can be passed back to ``rm_watch``. We
        return an ``object()`` sentinel — sufficient for identity
        comparisons in tests.
        """
        handle = object()
        self._watches.append((Path(path), mask))
        return handle

    def rm_watch(self, handle: object) -> None:
        """No-op for the fake. Tests verify rm_watch via a counter if needed."""
        del handle

    def inject_event(
        self,
        mask: FakeMask,
        path: Path | None,
        watch: object | None = None,
    ) -> None:
        """Queue an event for the next ``__anext__`` pull."""
        self._queue.append(FakeInotifyEvent(mask=mask, path=path, watch=watch or object()))

    def close(self) -> None:
        """Mark the fake closed; the async iterator stops once drained."""
        self._closed = True

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        del exc_type, exc_val, exc_tb
        self.close()

    def __aiter__(self) -> AsyncIterator[FakeInotifyEvent]:
        return self

    async def __anext__(self) -> FakeInotifyEvent:
        while not self._queue:
            if self._closed:
                raise StopAsyncIteration
            await asyncio.sleep(0)  # yield; tests inject between awaits
        return self._queue.popleft()
