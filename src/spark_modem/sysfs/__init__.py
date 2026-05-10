"""sysfs file-I/O helpers (no subprocess; no qmicli).

Plan 04-02 (Phase 4) introduces this package as the leaf for any sysfs-only
recovery action. Today it hosts the USB driver unbind/rebind helper used
by ``actions/usb_reset.py``; future plans may add additional sysfs-only
write helpers here.

Per CONTEXT A-02: file I/O only via ``Path.write_text`` -- no subprocess,
no qmicli. SP-04 lint scope is unchanged because file writes are not
subprocess invocations.
"""

from __future__ import annotations

from spark_modem.sysfs.usb_unbind_rebind import unbind_rebind

__all__ = ["unbind_rebind"]
