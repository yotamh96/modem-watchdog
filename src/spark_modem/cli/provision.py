"""spark-modem provision --device --apn — write profile #1 directly.

Phase 2 stub: production execution requires a SubprocRunner injection
path that lands with the cycle driver in plan 02-10 and the production
sysfs/zao integration in Phase 3. This handler prints a clear stub
message and returns 0 so operators can verify the CLI surface is wired
without attempting a hardware-touching call.
"""

from __future__ import annotations

import argparse


async def run(args: argparse.Namespace) -> int:
    print(
        "provision: production runner not wired in Phase 2; "
        f"target device={args.device} apn={args.apn} dry_run={args.dry_run}; "
        "use 'spark-modem reset --action=set_apn' once plan 02-10 lands."
    )
    return 0
