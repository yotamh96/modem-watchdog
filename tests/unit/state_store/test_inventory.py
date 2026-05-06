"""Unit tests for inventory.py — sysfs walker + cross-check helper.

Tests cover:
  - cross_check_inventory: consistent state passes, usb_path mismatch raises,
    vanished modem raises.
  - walk_sysfs_for_qmi_modems: fake-sysfs tree, empty tree, non-Sierra VID excluded.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from spark_modem.state_store.errors import UsbPathMismatch
from spark_modem.state_store.inventory import (
    SIERRA_VID,
    cross_check_inventory,
    walk_sysfs_for_qmi_modems,
)

# ---------------------------------------------------------------------------
# Helper: build a minimal fake-sysfs tree
# ---------------------------------------------------------------------------


def _make_sierra_device(
    devices_dir: Path,
    usb_path: str,
    cdc_wdm: str,
    vid: str = SIERRA_VID,
) -> None:
    """Create a fake sysfs USB device entry for a Sierra QMI modem."""
    dev_dir = devices_dir / usb_path
    qmi_dir = dev_dir / "qmi" / cdc_wdm
    qmi_dir.mkdir(parents=True, exist_ok=True)
    (dev_dir / "idVendor").write_text(vid)
    (dev_dir / "idProduct").write_text("9091")


# ---------------------------------------------------------------------------
# cross_check_inventory tests
# ---------------------------------------------------------------------------


def test_cross_check_consistent_state_returns_none() -> None:
    """Consistent (file_usb_path == sysfs_usb_path) returns None silently."""
    result = cross_check_inventory(
        file_usb_path="2-3.1.1",
        sysfs_usb_path="2-3.1.1",
        cdc_wdm="cdc-wdm0",
    )
    assert result is None


def test_cross_check_usb_path_mismatch_raises() -> None:
    """file_usb_path != sysfs_usb_path raises UsbPathMismatch."""
    with pytest.raises(UsbPathMismatch) as excinfo:
        cross_check_inventory(
            file_usb_path="2-3.1.1",
            sysfs_usb_path="2-3.1.2",
            cdc_wdm="cdc-wdm0",
        )
    exc = excinfo.value
    assert exc.file_usb_path == "2-3.1.1"
    assert exc.sysfs_usb_path == "2-3.1.2"
    assert exc.cdc_wdm == "cdc-wdm0"


def test_cross_check_vanished_modem_raises() -> None:
    """sysfs_usb_path=None (modem vanished) raises UsbPathMismatch."""
    with pytest.raises(UsbPathMismatch) as excinfo:
        cross_check_inventory(
            file_usb_path="2-3.1.1",
            sysfs_usb_path=None,
            cdc_wdm=None,
        )
    exc = excinfo.value
    assert exc.file_usb_path == "2-3.1.1"
    assert exc.sysfs_usb_path is None


def test_cross_check_stale_cdc_wdm_raises() -> None:
    """expected_cdc_wdm provided and != cdc_wdm raises UsbPathMismatch."""
    with pytest.raises(UsbPathMismatch):
        cross_check_inventory(
            file_usb_path="2-3.1.1",
            sysfs_usb_path="2-3.1.1",
            cdc_wdm="cdc-wdm0",
            expected_cdc_wdm="cdc-wdm1",
        )


def test_cross_check_expected_cdc_wdm_matches_passes() -> None:
    """expected_cdc_wdm == cdc_wdm is consistent; returns None."""
    result = cross_check_inventory(
        file_usb_path="2-3.1.1",
        sysfs_usb_path="2-3.1.1",
        cdc_wdm="cdc-wdm0",
        expected_cdc_wdm="cdc-wdm0",
    )
    assert result is None


# ---------------------------------------------------------------------------
# walk_sysfs_for_qmi_modems tests
# ---------------------------------------------------------------------------


def test_walk_sysfs_returns_sierra_qmi_modems(tmp_path: Path) -> None:
    """Walker returns {usb_path: cdc_wdm} for Sierra-VID QMI modems."""
    sysfs_root = tmp_path / "sys"
    devices_dir = sysfs_root / "bus" / "usb" / "devices"
    _make_sierra_device(devices_dir, "2-3.1.1", "cdc-wdm0")
    _make_sierra_device(devices_dir, "2-3.1.2", "cdc-wdm1")

    result = walk_sysfs_for_qmi_modems(sysfs_root)
    assert result == {"2-3.1.1": "cdc-wdm0", "2-3.1.2": "cdc-wdm1"}


def test_walk_sysfs_empty_tree_returns_empty(tmp_path: Path) -> None:
    """Walker returns {} when no Sierra QMI modems exist."""
    sysfs_root = tmp_path / "sys"
    sysfs_root.mkdir()
    result = walk_sysfs_for_qmi_modems(sysfs_root)
    assert result == {}


def test_walk_sysfs_non_sierra_vid_excluded(tmp_path: Path) -> None:
    """Non-Sierra VID devices are excluded."""
    sysfs_root = tmp_path / "sys"
    devices_dir = sysfs_root / "bus" / "usb" / "devices"
    _make_sierra_device(devices_dir, "2-3.1.1", "cdc-wdm0", vid="12d1")  # Huawei
    _make_sierra_device(devices_dir, "2-3.1.2", "cdc-wdm1", vid=SIERRA_VID)

    result = walk_sysfs_for_qmi_modems(sysfs_root)
    assert "2-3.1.1" not in result
    assert result == {"2-3.1.2": "cdc-wdm1"}


def test_walk_sysfs_hardware_free(tmp_path: Path) -> None:
    """Walker never reads /sys directly; accepts configurable sysfs_root."""
    # If we pass a non-existent root, it returns {} without OSError.
    result = walk_sysfs_for_qmi_modems(tmp_path / "nonexistent" / "sys")
    assert result == {}


def test_walk_sysfs_device_without_qmi_excluded(tmp_path: Path) -> None:
    """A Sierra device without a qmi/ subdirectory is excluded."""
    sysfs_root = tmp_path / "sys"
    devices_dir = sysfs_root / "bus" / "usb" / "devices"
    # Device with idVendor but no qmi/ directory.
    dev_dir = devices_dir / "2-3.1.1"
    dev_dir.mkdir(parents=True, exist_ok=True)
    (dev_dir / "idVendor").write_text(SIERRA_VID)

    result = walk_sysfs_for_qmi_modems(sysfs_root)
    assert result == {}
