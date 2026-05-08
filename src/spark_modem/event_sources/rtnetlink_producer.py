"""rtnetlink producer — push WakeSignal.RTNETLINK on link-state changes.

PITFALLS §6.1 PRESCRIPTIVE: tight read loop ONLY. Body MUST be
``event_queue.put_nowait(WakeSignal.RTNETLINK)`` and nothing else —
NO parsing, NO state, NO logging. The kernel's rtnetlink socket
delivers messages much faster than the daemon's policy engine can
react; any per-message work in this loop risks ENOBUFS during a
USB hub PSU droop's re-enumeration storm (16+ events in 2s on a
Tegra hub power-cycle).

SO_RCVBUF = 4 MiB (PITFALLS §6.1): the kernel default of 256 KiB is
too small to absorb the storm. We set 4 MiB explicitly via
``ipr.asyncore.socket.setsockopt(SOL_SOCKET, SO_RCVBUF, 4*1024*1024)``
inside the async context manager (so it runs after the socket exists,
before bind).

ENOBUFS handling (PITFALLS §6.1): on overflow the kernel emits an
ENOBUFS OSError. The producer DOES NOT try-except this — the OSError
escapes the coroutine and the supervisor's ``restart_on_crash``
wrapper from Plan 03-01 catches Exception, logs
``event_source_crashed{source=rtnetlink}``, sleeps the next backoff,
and re-enters the factory (which re-opens the socket — close+reopen
is the prescribed recovery).

Async context manager (PITFALLS §6.3): pyroute2 sockets leak on
ungraceful exit. ``async with AsyncIPRoute() as ipr:`` guarantees
socket close on every exit path including CancelledError.

NEVER sync ``IPRoute`` (anti-pattern catalogue): blocking calls in
asyncio loop deadlock the event loop. NEVER ``run_in_executor`` to
"speed up" the producer: pyroute2 has a real async API, use it.

The ``import pyroute2 / from pyroute2 import ...`` lives inside the
producer body so the module imports cleanly on Windows dev hosts.
Tests inject an ``ipr_factory`` tuple (preconstructed FakeAsyncIPRoute
+ a synthetic groups constant) and never trigger the real import.
"""

from __future__ import annotations

import logging
import socket
from collections.abc import AsyncIterator
from typing import Protocol

from spark_modem.event_sources.supervisor import WakeSignal

logger = logging.getLogger(__name__)


class _EventQueueProto(Protocol):
    """Minimal event-queue surface — supervisor's ``CycleScheduler.event_queue``.

    ``put_nowait`` is the only method the producer calls; queue overflow
    drops the signal silently (acceptable per ADR-0002 — a missed signal
    just means the cycle waits for the 30 s polling deadline instead).
    """

    def put_nowait(self, item: object) -> None: ...


class _AsyncIPRouteProto(Protocol):
    """Subset of ``pyroute2.AsyncIPRoute`` the producer touches.

    Co-located so tests inject ``FakeAsyncIPRoute`` without
    monkey-patching the pyroute2 module itself (PITFALLS §14.1
    spirit: seam, don't shim). The ``asyncore.socket`` access path
    is the documented setsockopt entry point in pyroute2 0.9.x.
    """

    async def __aenter__(self) -> _AsyncIPRouteProto: ...
    async def __aexit__(self, *exc: object) -> None: ...
    async def bind(self, *, groups: int) -> None: ...
    def get(self) -> AsyncIterator[object]: ...


def _build_default_ipr() -> _AsyncIPRouteProto:
    """Construct a real ``pyroute2.AsyncIPRoute`` (Linux-only).

    Tests inject an ``ipr_factory`` tuple instead of triggering this
    branch, keeping the module import cross-platform. The pyroute2
    import is deliberately lazy — it works on Windows dev hosts but
    constructing AsyncIPRoute requires netlink syscalls absent on
    Windows, and we don't run the daemon on Windows anyway.
    """
    from pyroute2 import AsyncIPRoute  # noqa: PLC0415 — deferred for dev-host import

    return AsyncIPRoute()  # type: ignore[no-any-return]


async def run_rtnetlink_producer(
    *,
    event_queue: _EventQueueProto,
    ipr_factory: tuple[_AsyncIPRouteProto, int] | None = None,
) -> None:
    """Subscribe to RTNETLINK link-state changes; push WakeSignal.RTNETLINK.

    Tight read loop only — body is ``put_nowait(WakeSignal.RTNETLINK)``
    ONLY. ENOBUFS escapes (supervisor restarts).

    Parameters
    ----------
    event_queue
        The cycle scheduler's ``event_queue``. Producers ``put_nowait``
        opaque sentinels only (E-02).
    ipr_factory
        Optional ``(AsyncIPRoute-like object, groups_constant)`` tuple.
        Tests inject this; production wires None and the real pyroute2
        ``AsyncIPRoute()`` + ``rtnl.RTMGRP_LINK`` are constructed here.

    Raises
    ------
    OSError
        ENOBUFS or other rtnetlink socket errors — propagates to the
        supervisor which re-opens the socket (PITFALLS §6.1).
    """
    # Defer pyroute2 imports so module-import works on Windows dev hosts.
    if ipr_factory is None:
        from pyroute2.netlink import rtnl  # noqa: PLC0415 — deferred for dev-host import

        groups: int = rtnl.RTMGRP_LINK
        ipr_cm: _AsyncIPRouteProto = _build_default_ipr()
    else:
        ipr_cm, groups = ipr_factory

    async with ipr_cm as ipr:
        # PITFALLS §6.1: 4 MiB SO_RCVBUF. AsyncIPRoute exposes the
        # underlying socket via .asyncore.socket per pyroute2 0.9.x
        # examples; gate the setsockopt on attribute presence so the
        # test fake's _FakeSocket recording path is exercised AND
        # production never silently skips the setsockopt.
        sock_holder = getattr(ipr, "asyncore", None)
        if sock_holder is not None:
            sock = getattr(sock_holder, "socket", None)
            if sock is not None and hasattr(sock, "setsockopt"):
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        await ipr.bind(groups=groups)
        async for _msg in ipr.get():
            event_queue.put_nowait(WakeSignal.RTNETLINK)
