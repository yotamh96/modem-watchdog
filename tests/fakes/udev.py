"""FakeUdevMonitor — test seam for udev_producer tests.

Mirrors the surface of ``pyudev.Monitor`` + ``pyudev.Device`` that
``run_udev_producer`` touches. Tests use ``inject_device(...)`` to push
events; production code never imports from this module.

Same dual-surface pattern as ``tests.fakes.zao_log.FixtureZaoTailer``:
the production-facing methods (``filter_by`` / ``set_receive_buffer_size``
/ ``start`` / ``fileno`` / ``poll``) match pyudev.Monitor's surface;
``inject_device`` / ``set_fileno`` are test-only mutators.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass
class FakeUdevDevice:
    """Mirror of the subset of ``pyudev.Device`` the producer reads.

    The producer only inspects ``action`` (set by udev to ``add`` /
    ``remove`` / ``bind`` / ``unbind`` / ``change`` / ...) and the
    ``ID_VENDOR_ID`` udev property. Everything else is unused.
    """

    action: str
    id_vendor_id: str | None
    sys_name: str = ""

    def get(self, key: str, default: str | None = None) -> str | None:
        """pyudev.Device exposes ``.get(key, default=None)`` for udev properties."""
        if key == "ID_VENDOR_ID":
            return self.id_vendor_id
        return default


class FakeUdevMonitor:
    """Captures filter_by / set_receive_buffer_size / start calls; yields injected devices.

    Matches the slice of ``pyudev.Monitor`` that ``run_udev_producer``
    touches: ``filter_by(subsystem=...)`` (called once),
    ``set_receive_buffer_size(n_bytes)`` (called once with 4 MiB per
    PITFALLS §7.3), ``start()`` (called once), ``fileno()`` (returned
    fd is what ``loop.add_reader`` watches), and ``poll(timeout=0)``
    (drained in a tight loop on each readable callback per PITFALLS §7.1).
    """

    def __init__(self) -> None:
        self._queue: deque[FakeUdevDevice] = deque()
        self._fileno: int = -1
        self.filter_calls: list[dict[str, str]] = []
        self.receive_buffer_size_calls: list[int] = []
        self.started: bool = False

    def filter_by(self, **kwargs: str) -> None:
        self.filter_calls.append(dict(kwargs))

    def set_receive_buffer_size(self, n_bytes: int) -> None:
        self.receive_buffer_size_calls.append(n_bytes)

    def start(self) -> None:
        self.started = True

    def fileno(self) -> int:
        return self._fileno

    def set_fileno(self, fd: int) -> None:
        """Test helper — wire to a real pipe pair if loop.add_reader is exercised."""
        self._fileno = fd

    def poll(self, timeout: float = 0) -> FakeUdevDevice | None:
        """Non-blocking poll mirroring ``pyudev.Monitor.poll(timeout=0)``.

        Returns one device or None when the queue is empty (the producer's
        on_readable callback uses None as the drain-loop terminator per
        PITFALLS §7.1).
        """
        del timeout  # signature parity with pyudev.Monitor.poll
        return self._queue.popleft() if self._queue else None

    def inject_device(self, device: FakeUdevDevice) -> None:
        """Push a device for the next ``poll()`` call to return."""
        self._queue.append(device)
