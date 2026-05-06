"""InventorySource - observer-facing seam for FR-2 modem discovery.

Phase 2 implementation: SysfsInventory (sysfs-pull once per cycle).
Phase 3 implementation: UdevInventory (event-driven via pyudev.Monitor).
Both satisfy this Protocol; observer/ never changes.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from spark_modem.inventory.descriptor import ModemDescriptor


@runtime_checkable
class InventorySource(Protocol):
    """Observer-facing seam: returns the current list of attached modems."""

    async def scan(self) -> list[ModemDescriptor]: ...
