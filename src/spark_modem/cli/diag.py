"""spark-modem diag — read-only modem diagnosis.

With ``--qmi-fixture-dir=PATH`` the QMI calls go through ``FixtureRunner``
(``cli.clients``) so the diag CLI runs hardware-free on a developer laptop
(FR-51 + SC#2). Without it, the cycle driver in plan 02-10 owns the
production runner injection.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from spark_modem.cli.clients import (
    FixtureRunner,
    _CliClock,
    _InventoryFromFile,
    _NoZaoTailer,
)
from spark_modem.cli.explain import format_diag_explain
from spark_modem.inventory.descriptor import ModemDescriptor
from spark_modem.observer.diag_builder import build_diag
from spark_modem.observer.orchestrator import observe_all
from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.zao_log.snapshot import ZaoSnapshot

_DEFAULT_INVENTORY = Path("tests/fixtures/inventory/four_modems.json")


async def run(args: argparse.Namespace) -> int:
    if args.qmi_fixture_dir is None:
        print(
            "diag: --qmi-fixture-dir is required in Phase 2 (laptop mode)",
            file=sys.stderr,
        )
        return 2

    fixture_dir = Path(args.qmi_fixture_dir)
    inventory_path = (
        Path(args.inventory_fixture)
        if args.inventory_fixture is not None
        else _DEFAULT_INVENTORY
    )

    inventory = _InventoryFromFile(inventory_path)
    modems = await inventory.scan()
    runner = FixtureRunner(fixture_dir=fixture_dir)

    def qmi_factory(m: ModemDescriptor) -> QmiWrapper:
        return QmiWrapper(runner=runner, device=f"/dev/{m.cdc_wdm}")

    clock = _CliClock()
    zao = _NoZaoTailer()
    snapshots = await observe_all(modems, qmi_factory, zao, clock)
    diag_obj = build_diag(
        snapshots,
        ZaoSnapshot.unknown(reason="cli-mode"),
        cycle_id=0,
        clock=clock,
    )

    if args.json:
        print(diag_obj.model_dump_json(indent=2))
    elif args.explain:
        print(format_diag_explain(diag_obj))
    else:
        print(diag_obj.model_dump_json())
    return 0
