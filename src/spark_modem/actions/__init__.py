"""actions/ -- cheap recovery actions + dispatcher.

Phase 2 ships only cheap actions (set_apn / fix_raw_ip / sim_power_on /
soft_reset / set_operating_mode / fix_autosuspend). Destructive actions
(modem_reset, usb_reset, driver_reset) land in Phase 4 by adding entries
to ``dispatcher._REGISTRY`` -- no dispatcher code changes.

Every action exposes ``async def execute(who, ctx) -> ActionResult`` and
``async def verify(who, ctx) -> VerifyResult``. The dispatcher's
``execute_and_verify(kind, who, ctx, *, dry_run=False)`` is the SINGLE
entry point used by both the cycle driver (plan 02-10) and the CLI
(plan 02-09).
"""

from __future__ import annotations
