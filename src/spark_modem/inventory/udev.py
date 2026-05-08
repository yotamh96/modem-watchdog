"""UdevInventory — InventorySource backed by sysfs walk (E-05).

Phase 3 swaps ``SysfsInventory`` → ``UdevInventory`` at daemon wiring
time (Plan 03-06). The wake signal pushed by the udev producer
(Plan 03-02 Task 1) triggers a cycle re-observation; this inventory's
``scan()`` does the on-demand sysfs walk.

Composition over inheritance: holds a ``SysfsInventory`` and delegates
``scan()``. The Phase-3 change is that ``ModemDescriptor.ns`` is now
populated by ``inventory/netns.derive_ns`` (which ``sysfs.py`` calls at
descriptor-construction time — single-source for the netns derivation).

The producer-side udev wake-signal handling lives in
``event_sources/udev_producer.py`` (orthogonal); this class is the
on-demand sysfs reader that runs on every cycle re-observation. The
observer/cycle_driver doesn't change between Phase 2's SysfsInventory
and Phase 3's UdevInventory — both satisfy the same Protocol.
"""

from __future__ import annotations

from pathlib import Path

from spark_modem.inventory.descriptor import ModemDescriptor
from spark_modem.inventory.sysfs import SysfsInventory


class UdevInventory:
    """InventorySource Protocol satisfier for the event-driven daemon.

    Composition: holds a SysfsInventory and delegates ``scan()``. Future
    Phase 3+ enhancements (e.g. caching across cycles, netns-aware
    scoping) can extend this class without touching SysfsInventory's
    polling-friendly shape.
    """

    def __init__(self, *, sysfs_root_override: Path | None = None) -> None:
        self._delegate = SysfsInventory(sysfs_root_override=sysfs_root_override)

    async def scan(self) -> list[ModemDescriptor]:
        """Return the current list of attached modems via the sysfs delegate."""
        return await self._delegate.scan()
