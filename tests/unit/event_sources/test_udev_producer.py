"""Unit tests for run_udev_producer + the on_readable callback factory.

Strategy:
  * Tests #2..#5 invoke ``_make_on_readable`` directly (cross-platform,
    no real fd, no event loop). This is the producer's classification
    + drain logic — the tight read-loop terminator is monitor.poll()
    returning None (PITFALLS §7.1).
  * Tests #1 + #6 wire a FakeUdevMonitor through ``run_udev_producer``
    via the loop-injected ``monitor`` parameter (still cross-platform —
    the ``loop.add_reader(-1, on_readable)`` path is exercised on POSIX
    only via skipif).
"""

from __future__ import annotations

import asyncio
import sys
from collections import deque

import pytest

from spark_modem.event_sources.supervisor import WakeSignal
from spark_modem.event_sources.udev_producer import (
    _make_on_readable,
    run_udev_producer,
)
from tests.fakes.udev import FakeUdevDevice, FakeUdevMonitor


class _RecordingQueue:
    """Minimal _EventQueueProto satisfier — records every put_nowait."""

    def __init__(self) -> None:
        self.items: list[object] = []

    def put_nowait(self, item: object) -> None:
        self.items.append(item)


def test_sierra_vid_match_pushes_wake_signal() -> None:
    """A bind event for VID=1199 pushes one WakeSignal.UDEV."""
    queue = _RecordingQueue()
    monitor = FakeUdevMonitor()
    monitor.inject_device(FakeUdevDevice(action="bind", id_vendor_id="1199"))

    on_readable = _make_on_readable(monitor=monitor, event_queue=queue, sierra_vid="1199")
    on_readable()

    assert queue.items == [WakeSignal.UDEV]


def test_non_sierra_vid_does_not_push() -> None:
    """A device with a non-Sierra VID does not push a wake signal."""
    queue = _RecordingQueue()
    monitor = FakeUdevMonitor()
    monitor.inject_device(FakeUdevDevice(action="add", id_vendor_id="abcd"))

    on_readable = _make_on_readable(monitor=monitor, event_queue=queue, sierra_vid="1199")
    on_readable()

    assert queue.items == []


def test_non_matching_action_does_not_push() -> None:
    """A `change` action does not push (only add/remove/bind/unbind do)."""
    queue = _RecordingQueue()
    monitor = FakeUdevMonitor()
    monitor.inject_device(FakeUdevDevice(action="change", id_vendor_id="1199"))

    on_readable = _make_on_readable(monitor=monitor, event_queue=queue, sierra_vid="1199")
    on_readable()

    assert queue.items == []


def test_drains_multiple_events_per_callback() -> None:
    """One on_readable invocation drains the entire pending queue (PITFALLS §7.1)."""
    queue = _RecordingQueue()
    monitor = FakeUdevMonitor()
    for action in ("add", "bind", "remove", "unbind", "add"):
        monitor.inject_device(FakeUdevDevice(action=action, id_vendor_id="1199"))

    on_readable = _make_on_readable(monitor=monitor, event_queue=queue, sierra_vid="1199")
    on_readable()

    assert queue.items == [WakeSignal.UDEV] * 5


def test_mixed_devices_filtered_correctly() -> None:
    """Mix of matching + non-matching devices: only matches push wake signals.

    Drain loop must terminate on monitor.poll() returning None — never
    on a non-matching device (otherwise the kernel buffer fills).
    """
    queue = _RecordingQueue()
    monitor = FakeUdevMonitor()
    # Sierra add (push), foreign add (skip), Sierra change (skip), Sierra remove (push)
    monitor.inject_device(FakeUdevDevice(action="add", id_vendor_id="1199"))
    monitor.inject_device(FakeUdevDevice(action="add", id_vendor_id="abcd"))
    monitor.inject_device(FakeUdevDevice(action="change", id_vendor_id="1199"))
    monitor.inject_device(FakeUdevDevice(action="remove", id_vendor_id="1199"))

    on_readable = _make_on_readable(monitor=monitor, event_queue=queue, sierra_vid="1199")
    on_readable()

    assert queue.items == [WakeSignal.UDEV, WakeSignal.UDEV]


@pytest.mark.skipif(sys.platform == "win32", reason="loop.add_reader requires POSIX fd")
async def test_run_udev_producer_wires_add_reader_and_cleans_up() -> None:
    """run_udev_producer adds a reader on the monitor fd and removes it on cancel.

    Uses an os.pipe() pair: the read end's fd is what FakeUdevMonitor.fileno()
    returns; the producer should add_reader(read_fd, on_readable) and remove it
    on CancelledError. We don't actually send events over the pipe — we just
    verify the lifecycle (add_reader / remove_reader bracketing the await).
    """
    import os

    read_fd, write_fd = os.pipe()
    try:
        monitor = FakeUdevMonitor()
        monitor.set_fileno(read_fd)
        queue: asyncio.Queue[object] = asyncio.Queue()

        # Track loop.add_reader / loop.remove_reader calls.
        loop = asyncio.get_running_loop()
        added_fds: list[int] = []
        removed_fds: list[int] = []

        original_add_reader = loop.add_reader
        original_remove_reader = loop.remove_reader

        def recording_add_reader(fd: int, callback: object, *args: object) -> None:
            added_fds.append(fd)
            original_add_reader(fd, callback, *args)  # type: ignore[arg-type]

        def recording_remove_reader(fd: int) -> bool:
            removed_fds.append(fd)
            return original_remove_reader(fd)

        loop.add_reader = recording_add_reader  # type: ignore[method-assign]
        loop.remove_reader = recording_remove_reader  # type: ignore[method-assign]

        try:
            task = asyncio.create_task(
                run_udev_producer(event_queue=queue, monitor=monitor)
            )
            # Yield once so the producer reaches add_reader + asyncio.Future().
            await asyncio.sleep(0)
            assert added_fds == [read_fd]
            assert removed_fds == []

            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

            assert removed_fds == [read_fd]
        finally:
            loop.add_reader = original_add_reader  # type: ignore[method-assign]
            loop.remove_reader = original_remove_reader  # type: ignore[method-assign]
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_drain_terminates_on_empty_queue() -> None:
    """Empty queue: on_readable does nothing; drain loop exits via None."""
    queue = _RecordingQueue()
    monitor = FakeUdevMonitor()
    # No devices injected.

    on_readable = _make_on_readable(monitor=monitor, event_queue=queue, sierra_vid="1199")
    on_readable()  # Must not hang or raise.

    assert queue.items == []


def test_device_without_id_vendor_id_property_does_not_push() -> None:
    """A device whose ID_VENDOR_ID is missing (None) is treated as non-matching."""
    queue = _RecordingQueue()
    monitor = FakeUdevMonitor()
    monitor.inject_device(FakeUdevDevice(action="bind", id_vendor_id=None))

    on_readable = _make_on_readable(monitor=monitor, event_queue=queue, sierra_vid="1199")
    on_readable()

    assert queue.items == []


def test_module_imports_cross_platform() -> None:
    """The udev_producer module must import on Windows dev hosts (pyudev import deferred)."""
    # If we reach this point the import already succeeded at module import time.
    from spark_modem.event_sources import udev_producer

    assert callable(udev_producer.run_udev_producer)
    assert callable(udev_producer._make_on_readable)


# Suppress unused-import warning for `deque` if any platform skips the async test.
_ = deque
