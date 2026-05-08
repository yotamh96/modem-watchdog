"""udev producer — push WakeSignal.UDEV on Sierra-VID USB events.

Per E-02 (CONTEXT.md): the producer body emits opaque WakeSignal
sentinels only — NO sysfs reads, NO parsing, NO state derivation.
The cycle is the source of truth (ADR-0002); a wake signal triggers
a full re-observation pass which then walks sysfs through
``UdevInventory.scan()``.

PITFALLS §7.1 PRESCRIPTIVE: NEVER ``pyudev.MonitorObserver`` — the
observer thread crashes silently under bulk events (pyudev #194,
#363, #402). Single-threaded ``loop.add_reader(monitor.fileno(),
on_readable)`` is the only allowed path.

PITFALLS §7.2: react on ``bind`` (driver attached) for cdc-wdm —
sysfs is not fully populated on ``add``. The producer forwards
``add`` / ``remove`` / ``bind`` / ``unbind`` as wake signals; the
cycle's re-observation handles transient EAGAIN/ENOENT by retrying
on the next cycle.

PITFALLS §7.3: 4 MiB ``set_receive_buffer_size`` absorbs USB hub
re-enumeration storms (16 events on a hub power-cycle become a
single coalesced cycle wake — coalescing is in
``CycleScheduler.event_queue``, ADR-0002).

The ``import pyudev`` lives inside ``_build_default_monitor()`` so
the module imports cleanly on Windows dev hosts (pyudev wraps
``libudev.so.1``, Linux-only). Tests inject a FakeUdevMonitor and
never trigger the import.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Final, Protocol

from spark_modem.event_sources.supervisor import WakeSignal

logger = logging.getLogger(__name__)

_SIERRA_VID: Final[str] = "1199"
_MATCHING_ACTIONS: Final[frozenset[str]] = frozenset({"add", "remove", "bind", "unbind"})
_RCVBUF_BYTES: Final[int] = 4 * 1024 * 1024  # PITFALLS §7.3


class _EventQueueProto(Protocol):
    """Minimal event-queue surface — supervisor's ``CycleScheduler.event_queue``.

    ``put_nowait`` is the only method the producer calls; queue overflow
    drops the signal silently (acceptable per ADR-0002 — a missed signal
    just means the cycle waits for the 30 s polling deadline instead).
    """

    def put_nowait(self, item: object) -> None: ...


class _MonitorProto(Protocol):
    """Subset of ``pyudev.Monitor`` + ``pyudev.Device`` the producer touches.

    Co-located so test code can inject ``FakeUdevMonitor`` without
    monkey-patching the pyudev module itself (PITFALLS §14.1 spirit:
    seam, don't shim).
    """

    def filter_by(self, **kwargs: str) -> None: ...
    def set_receive_buffer_size(self, n_bytes: int) -> None: ...
    def start(self) -> None: ...
    def fileno(self) -> int: ...
    def poll(self, timeout: float = 0) -> object: ...


def _build_default_monitor() -> _MonitorProto:
    """Construct a real ``pyudev.Monitor`` (Linux-only).

    Tests inject a FakeUdevMonitor instead of triggering this branch,
    keeping the module import cross-platform. The pyudev import is
    deliberately lazy — it raises ``OSError: cannot find libudev`` on
    Windows, which only matters when the daemon actually runs (and the
    daemon only runs on Linux).
    """
    import pyudev  # noqa: PLC0415 — deferred to keep module Windows-importable

    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by(subsystem="usb")
    monitor.set_receive_buffer_size(_RCVBUF_BYTES)
    monitor.start()
    return monitor  # type: ignore[no-any-return]


def _make_on_readable(
    *,
    monitor: _MonitorProto,
    event_queue: _EventQueueProto,
    sierra_vid: str,
) -> Callable[[], None]:
    """Build the ``on_readable`` callback bound to monitor + queue + VID.

    Factored out as a module-level closure factory so unit tests can
    invoke the classification + drain logic directly without going
    through ``loop.add_reader`` (which requires a real POSIX fd).

    The callback drains the kernel queue in a tight loop terminated
    only by ``monitor.poll(timeout=0)`` returning ``None`` — PITFALLS
    §7.1 prescriptive pattern.
    """

    def on_readable() -> None:
        # Drain the kernel queue; only None terminates the loop.
        while True:
            device = monitor.poll(timeout=0)
            if device is None:
                break
            action = getattr(device, "action", None)
            vid: str | None = None
            getter = getattr(device, "get", None)
            if callable(getter):
                vid_raw = getter("ID_VENDOR_ID")
                if isinstance(vid_raw, str):
                    vid = vid_raw
            if action in _MATCHING_ACTIONS and vid == sierra_vid:
                event_queue.put_nowait(WakeSignal.UDEV)

    return on_readable


async def run_udev_producer(
    *,
    event_queue: _EventQueueProto,
    sierra_vid: str = _SIERRA_VID,
    monitor: _MonitorProto | None = None,
) -> None:
    """Subscribe to USB add/remove/bind/unbind for Sierra-VID modems.

    Pushes ``WakeSignal.UDEV`` on every matching event. NEVER reads
    sysfs (E-02 — state derives from cycle re-observation).

    Parameters
    ----------
    event_queue
        The cycle scheduler's ``event_queue``. Producers ``put_nowait``
        opaque sentinels only.
    sierra_vid
        VID hex string to match (defaults to ``"1199"`` — Sierra
        Wireless / EM7421).
    monitor
        Optional pre-built monitor (tests inject a FakeUdevMonitor).
        Production wires None; ``_build_default_monitor`` then
        constructs a real ``pyudev.Monitor`` on Linux.

    The coroutine sleeps forever after wiring ``loop.add_reader``;
    the supervisor cancels via ``CancelledError`` on shutdown, at
    which point ``loop.remove_reader`` runs in the ``finally`` arm.
    """
    loop = asyncio.get_running_loop()
    mon = monitor if monitor is not None else _build_default_monitor()

    on_readable = _make_on_readable(
        monitor=mon,
        event_queue=event_queue,
        sierra_vid=sierra_vid,
    )

    fd = mon.fileno()
    loop.add_reader(fd, on_readable)
    try:
        # Sleep forever; supervisor cancels via CancelledError.
        await asyncio.Future()
    finally:
        loop.remove_reader(fd)
