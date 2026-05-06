"""Tests for tests.fakes.inventory.FixtureInventory."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.fakes.inventory import FixtureInventory

_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "inventory" / "four_modems.json"


async def test_scan_loads_four_modems_from_fixture() -> None:
    inv = FixtureInventory(_FIXTURE_PATH)
    modems = await inv.scan()
    assert len(modems) == 4
    assert modems[0].usb_path == "2-3.1.1"
    assert modems[0].cdc_wdm == "cdc-wdm0"
    assert modems[0].line == 1
    assert modems[3].usb_path == "2-3.1.4"
    assert modems[3].iface == "wwan0"


async def test_scan_rejects_extra_fields(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "modems": [
                    {
                        "line": 1,
                        "cdc_wdm": "cdc-wdm0",
                        "usb_path": "2-3.1.1",
                        "extra_field": "should_be_rejected",
                    }
                ]
            }
        )
    )
    inv = FixtureInventory(bad)
    with pytest.raises(Exception) as excinfo:
        await inv.scan()
    # pydantic v2 raises ValidationError; we check via class name to avoid
    # importing the symbol just for the assertion.
    assert "ValidationError" in type(excinfo.value).__name__


async def test_scan_returns_empty_when_no_modems_key(tmp_path: Path) -> None:
    empty = tmp_path / "empty.json"
    empty.write_text("{}")
    inv = FixtureInventory(empty)
    modems = await inv.scan()
    assert modems == []
