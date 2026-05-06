"""FixtureInventory -- reads inventory JSON snapshots for hardware-free tests.

Phase 2 production code uses `SysfsInventory` (Plan 02-04) walking
`/sys/bus/usb/devices/` to discover Sierra modems. This fake reads a JSON
snapshot of that scan from a fixture file so policy / observer / cycle-driver
tests can run on a developer laptop without sysfs.

The fixture-only `_FixtureModemDescriptor` shape mirrors the (line, cdc_wdm,
usb_path, ns, iface) five-tuple that FR-2 mandates. When Plan 02-04 lands
production `inventory/protocol.py`, this fake will be updated to import that
production type directly; until then, plan ordering is decoupled by carrying
a local pydantic-validated shape.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class _FixtureModemDescriptor(BaseModel):
    """Fixture-only ModemDescriptor shape (Plan 02-04 promotes this to production).

    Fields mirror FR-2's five-tuple. `ns` and `iface` are nullable because
    Phase 2 fixtures may represent modems that have not yet been brought up
    on a netns / wwan interface.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    line: int = Field(ge=1)
    cdc_wdm: str = Field(pattern=r"^cdc-wdm\d+$")
    usb_path: str = Field(min_length=1, max_length=64)
    ns: str | None = None
    iface: str | None = None


class FixtureInventory:
    """Reads tests/fixtures/inventory/<scenario>.json and returns descriptors.

    Implements the `scan() -> list[ModemDescriptor]` surface of
    `InventorySource` (Plan 02-04). The JSON shape is::

        {"modems": [{"line": 1, "cdc_wdm": "cdc-wdm0", "usb_path": "2-3.1.1", ...}]}
    """

    def __init__(self, fixture_path: Path) -> None:
        self._path = Path(fixture_path)

    async def scan(self) -> list[_FixtureModemDescriptor]:
        """Load the fixture and return a list of validated descriptors."""
        raw = json.loads(self._path.read_bytes())
        modems = raw.get("modems", [])
        return [_FixtureModemDescriptor.model_validate(m) for m in modems]
