"""Unit tests for SysfsInventory + the InventorySource Protocol surface.

Production target is Linux/aarch64; sysfs symlink semantics differ on
Windows so tests that materialise a fake sysfs tree are skipped on win32.
The non-tree tests (empty root, line derivation, Protocol isinstance)
run on every platform.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from spark_modem.inventory.descriptor import ModemDescriptor
from spark_modem.inventory.protocol import InventorySource
from spark_modem.inventory.sysfs import SysfsInventory
from tests.fakes.inventory import FixtureInventory

_FIXTURE_INVENTORY_FOUR = (
    Path(__file__).resolve().parents[2] / "fixtures" / "inventory" / "four_modems.json"
)

_SKIP_WIN_SYSFS = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Symlink-and-permission-heavy sysfs simulation; production target is Linux",
)


def _materialise_sierra_modem(
    *,
    sysfs_root: Path,
    usb_path: str,
    cdc_wdm_name: str,
    iface_name: str = "wwan0",
    vid: str = "1199",
    pid: str = "9091",
) -> None:
    """Create a Sierra-shaped sysfs tree under <sysfs_root>/bus/usb/devices/<usb_path>/."""
    dev_dir = sysfs_root / "bus" / "usb" / "devices" / usb_path
    dev_dir.mkdir(parents=True, exist_ok=True)
    (dev_dir / "idVendor").write_text(f"{vid}\n", encoding="ascii")
    (dev_dir / "idProduct").write_text(f"{pid}\n", encoding="ascii")
    # Children: <dev>/intf/usbmisc/cdc-wdmN and <dev>/intf/net/wwanN
    intf = dev_dir / "intf"
    (intf / "usbmisc" / cdc_wdm_name).mkdir(parents=True, exist_ok=True)
    (intf / "net" / iface_name).mkdir(parents=True, exist_ok=True)


async def test_empty_root_returns_empty_list(tmp_path: Path) -> None:
    """Pointing SysfsInventory at a tmp_path with no /bus/usb/devices/ -> []."""
    inv = SysfsInventory(sysfs_root_override=tmp_path)
    result = await inv.scan()
    assert result == []


@_SKIP_WIN_SYSFS
async def test_finds_four_em7421_modems(tmp_path: Path) -> None:
    """A 4-modem Sierra sysfs tree yields 4 descriptors keyed by usb_path."""
    for idx in range(1, 5):
        _materialise_sierra_modem(
            sysfs_root=tmp_path,
            usb_path=f"2-3.1.{idx}",
            cdc_wdm_name=f"cdc-wdm{idx - 1}",
        )
    inv = SysfsInventory(sysfs_root_override=tmp_path)

    result = await inv.scan()
    assert len(result) == 4
    for descriptor in result:
        assert isinstance(descriptor, ModemDescriptor)
    by_usb = {d.usb_path: d for d in result}
    for idx in range(1, 5):
        usb_path = f"2-3.1.{idx}"
        assert usb_path in by_usb
        assert by_usb[usb_path].cdc_wdm == f"cdc-wdm{idx - 1}"
        assert by_usb[usb_path].line == idx
        assert by_usb[usb_path].iface == "wwan0"
        assert by_usb[usb_path].ns is None


@_SKIP_WIN_SYSFS
async def test_skips_non_sierra_vendor(tmp_path: Path) -> None:
    """A non-Sierra VID device must not appear in the result."""
    _materialise_sierra_modem(
        sysfs_root=tmp_path,
        usb_path="2-3.1.1",
        cdc_wdm_name="cdc-wdm0",
    )
    # Non-Sierra device under a different usb_path
    _materialise_sierra_modem(
        sysfs_root=tmp_path,
        usb_path="2-1.1",
        cdc_wdm_name="cdc-wdm9",
        vid="0bda",  # Realtek
        pid="0001",
    )
    inv = SysfsInventory(sysfs_root_override=tmp_path)

    result = await inv.scan()
    assert len(result) == 1
    assert result[0].usb_path == "2-3.1.1"


@_SKIP_WIN_SYSFS
async def test_skips_modem_without_cdc_wdm(tmp_path: Path) -> None:
    """Sierra VID:PID device without a cdc-wdmN child is omitted (caller retries)."""
    dev_dir = tmp_path / "bus" / "usb" / "devices" / "2-3.1.1"
    dev_dir.mkdir(parents=True, exist_ok=True)
    (dev_dir / "idVendor").write_text("1199\n", encoding="ascii")
    (dev_dir / "idProduct").write_text("9091\n", encoding="ascii")
    # NOTE: no usbmisc/cdc-wdm* directory created.
    inv = SysfsInventory(sysfs_root_override=tmp_path)

    result = await inv.scan()
    assert result == []


def test_line_from_usb_path() -> None:
    """The line index is derived from the trailing dotted component."""
    assert SysfsInventory._line_from_usb_path("2-3.1.1") == 1
    assert SysfsInventory._line_from_usb_path("2-3.1.4") == 4
    assert SysfsInventory._line_from_usb_path("2-3.1") == 1  # degenerate fallback
    assert SysfsInventory._line_from_usb_path("foo") == 1
    assert SysfsInventory._line_from_usb_path("2-3.1.0") == 1  # 0 out of range -> 1


def test_fixture_inventory_satisfies_protocol() -> None:
    """FixtureInventory satisfies the runtime_checkable InventorySource Protocol."""
    inv = FixtureInventory(_FIXTURE_INVENTORY_FOUR)
    assert isinstance(inv, InventorySource)


def test_sysfs_inventory_satisfies_protocol(tmp_path: Path) -> None:
    """SysfsInventory satisfies the runtime_checkable InventorySource Protocol."""
    inv = SysfsInventory(sysfs_root_override=tmp_path)
    assert isinstance(inv, InventorySource)
