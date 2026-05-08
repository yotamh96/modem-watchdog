"""FakeAsyncIPRoute -- test seam for rtnetlink_producer tests.

Mirrors the slice of ``pyroute2.AsyncIPRoute`` that
``run_rtnetlink_producer`` touches: async context manager
(``__aenter__`` / ``__aexit__``), ``bind(groups=...)``, and
``get()`` returning an async iterator over messages. Tests use
``inject_message(...)`` to push msgs and ``inject_enobufs()`` to
push an OSError that should escape the producer (PITFALLS §6.1
prescriptive — the supervisor's ``restart_on_crash`` wrapper from
Plan 03-01 catches it and re-opens the socket).

Same dual-surface pattern as ``tests.fakes.zao_log.FixtureZaoTailer``
and ``tests.fakes.udev.FakeUdevMonitor``: production-facing methods
match the pyroute2 surface; ``inject_*`` mutators are test-only.
"""

from __future__ import annotations

import asyncio
import errno
from collections import deque
from collections.abc import AsyncIterator
from typing import Self


class _FakeSocket:
    """Mirror of the ``setsockopt`` slice ``run_rtnetlink_producer`` touches."""

    def __init__(self) -> None:
        self.setsockopt_calls: list[tuple[int, int, int]] = []

    def setsockopt(self, level: int, opt: int, value: int) -> None:
        self.setsockopt_calls.append((level, opt, value))


class _FakeAsyncoreHolder:
    """Mirror of pyroute2's ``ipr.asyncore.socket`` access path.

    AsyncIPRoute exposes the underlying socket via ``.asyncore.socket``
    so callers can ``setsockopt(SOL_SOCKET, SO_RCVBUF, 4 MiB)`` per
    PITFALLS §6.1.
    """

    def __init__(self) -> None:
        self.socket = _FakeSocket()


class FakeAsyncIPRoute:
    """Async context manager + async iterator over injected rtnetlink msgs.

    The producer pattern (RESEARCH.md Pattern 3, PITFALLS §6.1) is:

        async with AsyncIPRoute() as ipr:
            ipr.asyncore.socket.setsockopt(SOL_SOCKET, SO_RCVBUF, 4*MiB)
            await ipr.bind(groups=rtnl.RTMGRP_LINK)
            async for _msg in ipr.get():
                event_queue.put_nowait(WakeSignal.RTNETLINK)

    Tests mirror that shape via ``inject_message`` (push a msg) and
    ``inject_enobufs`` (push an OSError(ENOBUFS) the iterator raises
    when reached). ``close()`` causes ``__anext__`` to raise
    ``StopAsyncIteration`` if the queue is empty — useful for the
    ``await asyncio.sleep(0)`` busy-yield path.
    """

    def __init__(self) -> None:
        self.asyncore = _FakeAsyncoreHolder()
        self._queue: deque[object | OSError] = deque()
        self.bind_calls: list[int] = []
        self._closed: bool = False

    # async-context-manager surface
    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc: object) -> None:
        del exc
        self._closed = True

    async def bind(self, *, groups: int) -> None:
        self.bind_calls.append(groups)

    def get(self) -> AsyncIterator[object]:
        """Return an async iterator over pending messages.

        Mirrors ``pyroute2.AsyncIPRoute.get()`` which returns an
        async-iterable. Each ``__anext__`` either returns the next
        injected message, raises an injected OSError, or yields control
        (``await asyncio.sleep(0)``) until something is injected or the
        fake is closed.
        """
        return _FakeMsgIter(self)

    # test-only mutators
    def inject_message(self, msg: object) -> None:
        """Push a message for the next ``__anext__`` call to yield."""
        self._queue.append(msg)

    def inject_enobufs(self) -> None:
        """Push an OSError(ENOBUFS) the next ``__anext__`` call will raise.

        Per PITFALLS §6.1 the producer MUST let this escape — the
        supervisor's ``restart_on_crash`` wrapper handles socket
        re-open + ``event_source_resubscribed`` emission downstream.
        """
        self._queue.append(OSError(errno.ENOBUFS, "ENOBUFS"))

    def close(self) -> None:
        """Test helper — signal the iterator to terminate via StopAsyncIteration."""
        self._closed = True


class _FakeMsgIter:
    """Async iterator over FakeAsyncIPRoute's queue.

    Yields each item; raises OSError if the item is an OSError;
    raises StopAsyncIteration when the parent is closed and the queue
    is empty.
    """

    def __init__(self, parent: FakeAsyncIPRoute) -> None:
        self._parent = parent

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> object:
        # Busy-yield until something is injected or the parent closes.
        while not self._parent._queue:  # noqa: SLF001 - tight coupling to parent fake
            if self._parent._closed:  # noqa: SLF001 - tight coupling to parent fake
                raise StopAsyncIteration
            await asyncio.sleep(0)
        item = self._parent._queue.popleft()  # noqa: SLF001 - tight coupling to parent fake
        if isinstance(item, OSError):
            raise item
        return item
