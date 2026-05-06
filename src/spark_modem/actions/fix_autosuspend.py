"""fix_autosuspend -- write 'on' to /sys/.../power/control to disable USB autosuspend.

The USB device's ``power/control`` sysfs file is a regular file; writing
'on' disables runtime autosuspend (kernel default for USB modems is
'auto', which can pause the EM7421 mid-session and produce
SESSION_DISCONNECTED). This is NOT a subprocess call -- ``Path.write_text``
keeps SP-04 lint clean (no qmicli involvement at all).

The target path is computed as
``sysfs_root/bus/usb/devices/<usb_path>/power/control``. ``sysfs_root``
defaults to ``/sys`` in production; tests pass ``tmp_path`` so the
test never writes to /sys.
"""

from __future__ import annotations

from pathlib import Path

from spark_modem.actions.context import ActionContext
from spark_modem.actions.result import ActionResult, VerifyResult
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind


async def execute(who: WhoModem, ctx: ActionContext) -> ActionResult:
    start = ctx.clock.monotonic()
    target = _power_control_path(ctx.sysfs_root, who.usb_path)
    try:
        target.write_text("on", encoding="ascii")
    except OSError as exc:
        return ActionResult(
            kind=ActionKind.FIX_AUTOSUSPEND,
            who=who,
            succeeded=False,
            duration_seconds=ctx.clock.monotonic() - start,
            failure_reason=f"sysfs_write_error:{exc.errno}",
            dry_run=False,
        )
    return ActionResult(
        kind=ActionKind.FIX_AUTOSUSPEND,
        who=who,
        succeeded=True,
        duration_seconds=ctx.clock.monotonic() - start,
        failure_reason=None,
        dry_run=False,
    )


async def verify(who: WhoModem, ctx: ActionContext) -> VerifyResult:
    target = _power_control_path(ctx.sysfs_root, who.usb_path)
    try:
        content = target.read_text(encoding="ascii").strip()
    except OSError as exc:
        return VerifyResult.failed(detail=f"sysfs_read_error:{exc.errno}")
    if content == "on":
        return VerifyResult.ok(detail="power_control=on")
    return VerifyResult.failed(detail=f"power_control={content!r}")


def _power_control_path(sysfs_root: Path, usb_path: str) -> Path:
    return sysfs_root / "bus" / "usb" / "devices" / usb_path / "power" / "control"
