"""Unit tests for UdevInventory — Phase 3 InventorySource impl via composition.

UdevInventory delegates the sysfs walk to SysfsInventory (composition,
not inheritance — the walk shape is shared, only the wake-trigger
mechanism is event-driven). This test file pins the Protocol satisfaction
+ delegation contract; the underlying sysfs walk semantics are covered
by tests/unit/inventory/test_sysfs.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from spark_modem.inventory.descriptor import ModemDescriptor
from spark_modem.inventory.protocol import InventorySource
from spark_modem.inventory.udev import UdevInventory


def test_satisfies_inventory_source_protocol() -> None:
    """UdevInventory passes runtime-checkable InventorySource isinstance."""
    inv = UdevInventory()
    assert isinstance(inv, InventorySource)


async def test_scan_returns_descriptors_via_delegate(tmp_path: Path) -> None:
    """scan() returns whatever the SysfsInventory delegate returns (empty default)."""
    inv = UdevInventory(sysfs_root_override=tmp_path)
    result = await inv.scan()
    assert result == []


async def test_scan_passes_sysfs_root_override(tmp_path: Path) -> None:
    """sysfs_root_override flows into the delegated SysfsInventory.

    Materialise a fake Sierra modem under tmp_path; UdevInventory.scan()
    must find it (proving the override reached the delegate).
    Skipped on Windows because of symlink/permission semantics, mirroring
    the SysfsInventory test pattern.
    """
    if sys.platform == "win32":
        pytest.skip("Symlink-and-permission-heavy sysfs simulation; production target is Linux")

    dev_dir = tmp_path / "bus" / "usb" / "devices" / "2-3.1.1"
    dev_dir.mkdir(parents=True)
    (dev_dir / "idVendor").write_text("1199\n", encoding="ascii")
    (dev_dir / "idProduct").write_text("9091\n", encoding="ascii")
    intf = dev_dir / "intf"
    (intf / "usbmisc" / "cdc-wdm0").mkdir(parents=True)
    (intf / "net" / "wwan0").mkdir(parents=True)

    inv = UdevInventory(sysfs_root_override=tmp_path)
    result = await inv.scan()

    assert len(result) == 1
    assert isinstance(result[0], ModemDescriptor)
    assert result[0].usb_path == "2-3.1.1"
    assert result[0].cdc_wdm == "cdc-wdm0"
    assert result[0].iface == "wwan0"
    # Single-namespace bench Jetson: ns is None (no /sys/.../device/ns/net link).
    assert result[0].ns is None
