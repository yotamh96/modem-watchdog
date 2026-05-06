"""FixtureInventory - reads inventory JSON snapshots for hardware-free tests.

Phase 2 production code uses `SysfsInventory` (Plan 02-04) walking
`/sys/bus/usb/devices/` to discover Sierra modems. This fake reads a JSON
snapshot of that scan from a fixture file so policy / observer / cycle-driver
tests can run on a developer laptop without sysfs.

Plan 02-04 promoted `_FixtureModemDescriptor` to the production
`spark_modem.inventory.descriptor.ModemDescriptor` type; this fake imports
that type directly so production code and tests share one shape.
"""

from __future__ import annotations

import json
from pathlib import Path

from spark_modem.inventory.descriptor import ModemDescriptor


class FixtureInventory:
    """Reads tests/fixtures/inventory/<scenario>.json and returns descriptors.

    Implements the `scan() -> list[ModemDescriptor]` surface of
    `InventorySource` (Plan 02-04). The JSON shape is::

        {"modems": [{"line": 1, "cdc_wdm": "cdc-wdm0", "usb_path": "2-3.1.1", ...}]}
    """

    def __init__(self, fixture_path: Path) -> None:
        self._path = Path(fixture_path)

    async def scan(self) -> list[ModemDescriptor]:
        """Load the fixture and return a list of validated ModemDescriptors."""
        raw = json.loads(self._path.read_bytes())
        modems = raw.get("modems", [])
        return [ModemDescriptor.model_validate(m) for m in modems]
