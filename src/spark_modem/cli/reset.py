"""spark-modem reset --action=<kind> --modem=cdc-wdmN — single action via dispatcher.

Routes to ``actions.dispatcher`` (FR-25 "runnable individually via CLI").
At Plan 04-01 commit time, the registry covers the six Phase-2 cheap
actions plus the Phase-4 ``modem_reset``. Plans 04-02 / 04-03 add
``usb_reset`` / ``driver_reset``; the CLI guards remain a generic
"is not registered" rejection until each lands.

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
    print(f"reset: would dispatch action={kind.value} modem={args.modem} dry_run={args.dry_run}")
    return 0
