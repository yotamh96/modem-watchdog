"""Sysfs inventory walker + cross-check helper.

ADR-0009: state files are keyed by usb_path. cdc-wdmN can renumber
across boots (PITFALLS §3.1) — the walker resolves the current
(usb_path -> cdc_wdm) mapping from /sys/bus/usb/devices/. The
cross-check refuses to load a state file whose usb_path doesn't
match what sysfs reports.

S-02: on mismatch, the daemon refuses to start. Phase 1 raises
UsbPathMismatch via StateStore.cross_check_inventory_for(); Phase 2/3
wires the sd_notify STATUS=usb_path_mismatch + non-zero exit.

Hardware-free design: walk_sysfs_for_qmi_modems accepts a configurable
``sysfs_root`` so tests can pass a tmp_path-backed fake tree instead of
``Path('/sys')``. The production caller passes ``Path('/sys')``.
"""

from __future__ import annotations

from pathlib import Path

from spark_modem.state_store.errors import UsbPathMismatch

SIERRA_VID = "1199"
"""Sierra Wireless USB Vendor ID (EM7421 and family).

The walker matches on VID only, not VID:PID, because the PID can vary
across firmware revisions (PITFALLS §1.6 — match VID not VID:PID pair).
"""


def walk_sysfs_for_qmi_modems(sysfs_root: Path) -> dict[str, str]:
    """Walk ``<sysfs_root>/bus/usb/devices/`` and return ``{usb_path: cdc_wdm}``.

    Only Sierra Wireless devices (``idVendor == "1199"``) that have a
    ``qmi/cdc-wdmN`` child directory are included. The result is keyed by
    the device's directory name (i.e. its USB topology path, e.g. ``"2-3.1.1"``).

    Hardware-free when ``sysfs_root`` is a tmp_path-backed fake tree;
    production callers pass ``Path('/sys')``.
    """
    result: dict[str, str] = {}
    usb_devices_dir = sysfs_root / "bus" / "usb" / "devices"
    if not usb_devices_dir.is_dir():
        return result

    for dev_dir in usb_devices_dir.iterdir():
        if not dev_dir.is_dir():
            continue
        id_vendor_file = dev_dir / "idVendor"
        if not id_vendor_file.is_file():
            continue
        try:
            vid = id_vendor_file.read_text().strip()
        except OSError:
            continue
        if vid != SIERRA_VID:
            continue
        qmi_dir = dev_dir / "qmi"
        if not qmi_dir.is_dir():
            continue
        for cdc in qmi_dir.iterdir():
            if cdc.is_dir() and cdc.name.startswith("cdc-wdm"):
                result[dev_dir.name] = cdc.name
                break
    return result


def cross_check_inventory(
    *,
    file_usb_path: str,
    sysfs_usb_path: str | None,
    cdc_wdm: str | None,
    expected_cdc_wdm: str | None = None,
    file_path: str = "<unknown>",
) -> None:
    """Compare a persisted state file's identity against current sysfs topology.

    Raises :class:`~spark_modem.state_store.errors.UsbPathMismatch` when:
      - ``sysfs_usb_path`` is None (the file references a modem that vanished),
      - ``file_usb_path != sysfs_usb_path`` (topology changed),
      - ``expected_cdc_wdm`` is provided AND ``cdc_wdm != expected_cdc_wdm``
        (the cdc-wdm renumbered between boot 1 and boot 2 — the file's
        recorded cdc-wdm is stale).

    Returns ``None`` silently on full consistency.

    This is a pure function (no I/O, no subprocess) — it composes with the
    results of :func:`walk_sysfs_for_qmi_modems` and whatever was read from
    the persisted state file.
    """
    if sysfs_usb_path is None:
        raise UsbPathMismatch(
            file_usb_path=file_usb_path,
            sysfs_usb_path=None,
            cdc_wdm=cdc_wdm,
            file_path=file_path,
        )
    if file_usb_path != sysfs_usb_path:
        raise UsbPathMismatch(
            file_usb_path=file_usb_path,
            sysfs_usb_path=sysfs_usb_path,
            cdc_wdm=cdc_wdm,
            file_path=file_path,
        )
    if expected_cdc_wdm is not None and cdc_wdm != expected_cdc_wdm:
        raise UsbPathMismatch(
            file_usb_path=file_usb_path,
            sysfs_usb_path=sysfs_usb_path,
            cdc_wdm=cdc_wdm,
            file_path=file_path,
        )
