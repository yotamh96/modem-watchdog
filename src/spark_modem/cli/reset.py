"""spark-modem reset --action=<kind> --modem=cdc-wdmN — single action via dispatcher.

Routes to ``actions.dispatcher`` (FR-25 "runnable individually via CLI").
At Plan 04-02 commit time, the registry covers the six Phase-2 cheap
actions plus the Phase-4 ``modem_reset`` (Plan 04-01) and ``usb_reset``
(this plan). Plan 04-03 adds ``driver_reset``; the CLI guard remains
a generic "is not registered" rejection until then.

The Plan 04-02 ``--target`` flag selects the usb_reset variant:
``child-port`` (default; leaf bus-port unbind+rebind) or ``parent-hub``
(parent hub unbind+rebind for Sierra EM7421 stuck-in-bootloader per
PITFALLS §1.6 / A-06). Other action kinds ignore the flag.

The full execution path (runner injection + state-store + carrier-table)
lands with the cycle driver in plan 02-10. Today's ``reset`` CLI
validates the action kind and prints a stub success message; the
integration test in plan 02-10 exercises the full path end-to-end.
"""

from __future__ import annotations

import argparse
import sys

from spark_modem.actions.dispatcher import is_registered, registered_kinds
from spark_modem.wire.enums import ActionKind


async def run(args: argparse.Namespace) -> int:
    try:
        kind = ActionKind(args.action)
    except ValueError:
        valid = sorted(k.value for k in registered_kinds())
        print(
            f"reset: unknown action {args.action!r}; valid: {valid}",
            file=sys.stderr,
        )
        return 2

    if not is_registered(kind):
        valid = sorted(k.value for k in registered_kinds())
        print(
            f"reset: action {kind.value} is not registered; valid: {valid}",
            file=sys.stderr,
        )
        return 2

    # Production execution requires a runner + state-store + carrier-table
    # context which is set up by the daemon main (plan 02-10). For Phase 2
    # the CLI prints a stub success — the integration test in plan 02-10
    # exercises the full path.
    target = getattr(args, "target", "child-port")
    print(
        f"reset: would dispatch action={kind.value} modem={args.modem} "
        f"dry_run={args.dry_run} target={target}"
    )
    return 0
