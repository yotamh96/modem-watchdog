"""SysfsInventory - Phase 2 implementation of InventorySource via sysfs walk.

Reads /sys/bus/usb/devices/ for VID:PID 1199:9091 (Sierra EM7421) entries.
Phase 3 swaps in a UdevInventory backed by pyudev.Monitor; observer/
does not change.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from spark_modem.inventory.descriptor import ModemDescriptor
from spark_modem.inventory.netns import derive_ns

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
          - `ns`        -- derived via inventory/netns.derive_ns (E-05);
            None on the bench Jetson single-namespace case
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
            if line is None:
                # WR-05: usb_path tail is non-numeric or out of range; the
                # Zao FR-10 gate keys on `line` so silently mapping multiple
                # modems to line=1 would conflate two distinct USB devices.
                # Skip the descriptor; the next cycle re-scans.
                continue
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
                    ns=derive_ns(resolved),  # E-05; None on single-namespace
                    iface=iface,
                )
            )
        return descriptors

    @staticmethod
    def _line_from_usb_path(usb_path: str) -> int | None:
        """Map '2-3.1.1' -> 1 (the last dotted component is the line index).

        On the production Jetson the four modems sit at 2-3.1.1..4.
        Phase 3 may surface a more sophisticated mapping; Phase 2 uses
        the trailing component.

        WR-05: returns ``None`` when the trailing component is non-numeric
        or out of [_LINE_MIN, _LINE_MAX].  ``scan()`` then skips the
        descriptor.  Previously the function returned ``_LINE_MIN`` (=1)
        for both shapes, which would conflate two distinct USB devices on
        the same Zao line if two malformed/foreign entries somehow matched
        VID:PID — the Zao FR-10 gate keys on `line`, so a silent collision
        is a correctness bug for the gate.
        """
        tail = usb_path.rsplit(".", 1)[-1]
        try:
            value = int(tail)
        except ValueError:
            return None
        return value if _LINE_MIN <= value <= _LINE_MAX else None

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
