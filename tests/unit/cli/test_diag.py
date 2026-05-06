"""Tests for spark_modem.cli.diag — laptop-mode diagnosis."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from spark_modem.cli import diag as diag_cmd

FIXTURE_QMICLI_DIR = "tests/fixtures/qmicli"
FIXTURE_INVENTORY = "tests/fixtures/inventory/four_modems.json"


def _make_args(**kwargs: object) -> Namespace:
    base: dict[str, object] = {
        "qmi_fixture_dir": FIXTURE_QMICLI_DIR,
        "inventory_fixture": FIXTURE_INVENTORY,
        "json": False,
        "explain": False,
    }
    base.update(kwargs)
    return Namespace(**base)


async def test_diag_with_qmi_fixture_dir_emits_diag_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--json` emits a valid Diag with 4 modems matching the inventory fixture."""
    args = _make_args(json=True)
    rc = await diag_cmd.run(args)
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert "per_modem" in parsed
    assert set(parsed["per_modem"].keys()) == {"2-3.1.1", "2-3.1.2", "2-3.1.3", "2-3.1.4"}
    assert parsed["cycle_id"] == 0
    assert isinstance(parsed["ts_iso"], str)


async def test_diag_explain_emits_human_readable_text(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--explain` emits per-modem text including modem id and issues= field."""
    args = _make_args(explain=True)
    rc = await diag_cmd.run(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "modem 2-3.1.1" in out
    assert "issues=" in out


async def test_diag_default_format_is_compact_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No `--json`, no `--explain` → compact (single-line) JSON."""
    args = _make_args()
    rc = await diag_cmd.run(args)
    assert rc == 0
    out = capsys.readouterr().out.strip()
    parsed = json.loads(out)
    assert "per_modem" in parsed
    # Compact output has no indentation newlines between fields.
    assert "\n  " not in out


async def test_diag_without_fixture_dir_returns_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Missing `--qmi-fixture-dir` is a Phase-2 hard error (laptop mode)."""
    args = _make_args(qmi_fixture_dir=None, json=True)
    rc = await diag_cmd.run(args)
    assert rc == 2
    err = capsys.readouterr().err
    assert "qmi-fixture-dir" in err


async def test_diag_default_inventory_fixture_used_when_unspecified(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--inventory-fixture` defaults to the canonical four_modems.json."""
    args = _make_args(json=True, inventory_fixture=None)
    rc = await diag_cmd.run(args)
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert len(parsed["per_modem"]) == 4


async def test_diag_uses_inventory_fixture_with_two_modems(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Custom `--inventory-fixture` overrides the default."""
    custom = tmp_path / "two.json"
    custom.write_text(
        json.dumps(
            {
                "modems": [
                    {
                        "line": 1,
                        "cdc_wdm": "cdc-wdm0",
                        "usb_path": "2-3.1.1",
                        "ns": "line1",
                        "iface": "wwan0",
                    },
                    {
                        "line": 2,
                        "cdc_wdm": "cdc-wdm1",
                        "usb_path": "2-3.1.2",
                        "ns": "line2",
                        "iface": "wwan0",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    args = _make_args(json=True, inventory_fixture=str(custom))
    rc = await diag_cmd.run(args)
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert set(parsed["per_modem"].keys()) == {"2-3.1.1", "2-3.1.2"}
