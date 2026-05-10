"""USB driver unbind/rebind via sysfs file writes.

CAP_SYS_ADMIN preallocated by Plan 03-08 U-01 in the systemd unit; tests
inject ``tmp_path`` so unit tests never touch /sys.

Per CONTEXT A-02 / A-06 / PITFALLS §1.6:
  - child-port (default): writes the modem's leaf bus-port path
    (e.g. ``"2-3.1.1"``) to ``/sys/bus/usb/drivers/usb/{unbind,bind}``.
    Recovers SC#4 QMI-hung modems.
  - parent-hub: writes the parent hub bus-port (``usb_path.rsplit('.', 1)[0]``,
    e.g. ``"2-3.1"``) to the same files. Re-fires the Sierra EM7421 boot
    transition for IssueDetail.SIERRA_BOOTLOADER -- a child-port reset
    alone may not unstick a modem stuck in bootloader mode (1199:9051).

File I/O only; SP-04 lint untouched (no subprocess, no qmicli). The
caller (``actions/usb_reset.py``) is responsible for catching OSError and
wrapping it into ``ActionResult.failure_reason``.

Reference: LWN.net /Articles/143397/ "Manual driver binding and unbinding".
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal


async def unbind_rebind(
    usb_path: str,
    *,
    target: Literal["child-port", "parent-hub"] = "child-port",
    sysfs_root: Path | None = None,
    rebind_delay_seconds: float = 0.5,
) -> None:
    """Write ``usb_path`` to drivers/usb/unbind, sleep, then write to drivers/usb/bind.

    Args:
      usb_path: bus-port path of the modem (e.g. ``"2-3.1.1"``).
      target: ``"child-port"`` writes ``usb_path`` verbatim;
        ``"parent-hub"`` strips the leaf segment and writes the parent
        hub path (PITFALLS §1.6).
      sysfs_root: sysfs root override; defaults to ``Path("/sys")`` in
        production. Tests pass ``tmp_path``.
      rebind_delay_seconds: wall-clock delay between unbind and bind
        writes. Conservative default 0.5s for child-port; callers may
        pass 1.0s for parent-hub re-enumeration windows.

    Raises:
      OSError: any underlying file-write failure (FileNotFoundError /
        PermissionError / EBUSY / etc.). Caller wraps into
        ``ActionResult.failure_reason`` at the actions/usb_reset.py
        boundary.
    """
    root = sysfs_root if sysfs_root is not None else Path("/sys")
    payload = usb_path if target == "child-port" else usb_path.rsplit(".", 1)[0]
    unbind_path = root / "bus" / "usb" / "drivers" / "usb" / "unbind"
    bind_path = root / "bus" / "usb" / "drivers" / "usb" / "bind"
    unbind_path.write_text(payload, encoding="ascii")
    await asyncio.sleep(rebind_delay_seconds)
    bind_path.write_text(payload, encoding="ascii")
