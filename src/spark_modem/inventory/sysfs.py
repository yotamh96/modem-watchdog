"""SysfsInventory - Phase 2 implementation of InventorySource via sysfs walk.

Reads /sys/bus/usb/devices/ for VID:PID 1199:9091 (Sierra EM7421) entries.
Phase 3 swaps in a UdevInventory backed by pyudev.Monitor; observer/
does not change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from spark_modem.inventory.descriptor import ModemDescriptor

_SIERRA_VID: Final[str] = "1199"
_EM7421_PID: Final[str] = "9091"

# Zao line index range (FR-2 / ModemDescriptor): 1..99 inclusive.
_LINE_MIN: Final[int] = 1
_LINE_MAX: Final[int] = 99


class SysfsInventory:
    """Walks /sys/bus/usb/devices/ for VID:PID 1199:9091 (Sierra EM7421)."""

    def __init__(self, *, sysfs_root_override: Path | None = None) -> None:
        self._sysfs_root = sysfs_root_override or Path("/sys")

    async def scan(self) -> list[ModemDescriptor]:
        """Return a list of ModemDescriptors for every Sierra EM7421 attached.

        Walks `<sysfs_root>/bus/usb/devices/` for entries whose `idVendor`
        is `1199` and `idProduct` is `9091`. For each match, derives:

          - `usb_path`  -- the entry's basename (e.g. `2-3.1.1`)
          - `cdc_wdm`   -- found by walking the entry's children to find a
            `cdc-wdmN` under any `usbmisc/` directory
          - `iface`     -- corresponding `wwanN` net interface
          - `ns`        -- None (Phase 3 derives from netns)
          - `line`      -- derived from the trailing component of `usb_path`

        Modems whose `cdc_wdm` device has not yet enumerated are skipped;
        the next cycle re-scans.
        """
        usb_devices_dir = self._sysfs_root / "bus" / "usb" / "devices"
        if not usb_devices_dir.is_dir():
            return []
        descriptors: list[ModemDescriptor] = []
        for entry in sorted(usb_devices_dir.iterdir()):
            if not entry.is_dir() and not entry.is_symlink():
                continue
            resolved = entry.resolve()
            vid_file = resolved / "idVendor"
            pid_file = resolved / "idProduct"
            if not (vid_file.exists() and pid_file.exists()):
                continue
            vid = vid_file.read_text(encoding="ascii").strip().lower()
            pid = pid_file.read_text(encoding="ascii").strip().lower()
            if vid != _SIERRA_VID or pid != _EM7421_PID:
                continue
            usb_path = entry.name
            line = self._line_from_usb_path(usb_path)
            cdc_wdm = self._find_cdc_wdm(resolved)
            iface = self._find_wwan_iface(resolved)
            if cdc_wdm is None:
                # Not yet enumerated -- caller retries next cycle.
                continue
            descriptors.append(
                ModemDescriptor(
                    line=line,
                    cdc_wdm=cdc_wdm,
                    usb_path=usb_path,
                    ns=None,  # Phase 3 derives from netns
                    iface=iface,
                )
            )
        return descriptors

    @staticmethod
    def _line_from_usb_path(usb_path: str) -> int:
        """Map '2-3.1.1' -> 1 (the last dotted component is the line index).

        On the production Jetson the four modems sit at 2-3.1.1..4.
        Phase 3 may surface a more sophisticated mapping; Phase 2 uses
        the trailing component. Out-of-range or non-numeric tails
        degenerate to 1 so the descriptor still validates (line >= 1).
        """
        tail = usb_path.rsplit(".", 1)[-1]
        try:
            value = int(tail)
        except ValueError:
            return _LINE_MIN
        return value if _LINE_MIN <= value <= _LINE_MAX else _LINE_MIN

    @staticmethod
    def _find_cdc_wdm(resolved: Path) -> str | None:
        """Search children for a cdc-wdmN node and return the basename.

        sysfs layout (paraphrased):
          <usb_dev>/<intf>/usbmisc/cdc-wdm0/
          <usb_dev>/<intf>/net/wwan0/
        """
        for misc in resolved.rglob("usbmisc/cdc-wdm*"):
            if misc.is_dir() or misc.is_symlink():
                return misc.name
        return None

    @staticmethod
    def _find_wwan_iface(resolved: Path) -> str | None:
        """Search children for a wwanN net interface and return its basename."""
        for net in resolved.rglob("net/wwan*"):
            if net.is_dir() or net.is_symlink():
                return net.name
        return None
