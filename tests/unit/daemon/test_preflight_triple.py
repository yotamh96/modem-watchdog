"""Unit tests for daemon.preflight_triple — X-03 known-fleet triple gate.

The X-03 daemon preflight refuses to start when the local (firmware, SDK,
libqmi) triple is not in the known-fleet index baked into the .deb at
``/etc/spark-modem-watchdog/known-fleet/<box-id>/triple.json``. Tests inject
``known_fleet_dir`` (tmp_path) and ``local_triple`` (skip the sysfs/qmicli
probe) so they run hardware-free on Windows dev hosts.

Sister module ``tests/unit/daemon/test_preflight.py`` covers the FR-60
binary check. The ``--skip-preflight`` CLI flag bypass is exercised at the
integration level (``tests/integration/test_daemon_preflight_triple.py``)
since the bypass lives in ``daemon/main.py``, not this module.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from spark_modem.daemon.preflight_triple import (
    UnknownFleetTriple,
    _load_known_triples,
    preflight_check_known_fleet_triple,
)
from spark_modem.qmi.version import FleetTriple

_LOCAL = FleetTriple(
    em7421_firmware="SWI9X30C_02.38.00.00",
    zao_sdk="2.1.0",
    libqmi="1.30.6",
)


def _write_triple(box_dir: Path, triple: FleetTriple, *, schema_version: int = 1) -> None:
    box_dir.mkdir(parents=True, exist_ok=True)
    (box_dir / "triple.json").write_text(
        json.dumps(
            {
                "schema_version": schema_version,
                "em7421_firmware": triple.em7421_firmware,
                "zao_sdk": triple.zao_sdk,
                "libqmi": triple.libqmi,
            }
        )
    )


def test_unknown_fleet_triple_is_runtimeerror() -> None:
    """UnknownFleetTriple subclasses RuntimeError (matches PreflightFailed shape)."""
    assert issubclass(UnknownFleetTriple, RuntimeError)


async def test_empty_known_dir_raises(tmp_path: Path) -> None:
    """Empty known_fleet_dir → UnknownFleetTriple ('empty or missing')."""
    with pytest.raises(UnknownFleetTriple, match="empty or missing"):
        await preflight_check_known_fleet_triple(
            known_fleet_dir=tmp_path,
            local_triple=_LOCAL,
        )


async def test_missing_known_dir_raises(tmp_path: Path) -> None:
    """Non-existent known_fleet_dir → UnknownFleetTriple ('empty or missing')."""
    bogus = tmp_path / "does_not_exist"
    with pytest.raises(UnknownFleetTriple, match="empty or missing"):
        await preflight_check_known_fleet_triple(
            known_fleet_dir=bogus,
            local_triple=_LOCAL,
        )


async def test_matching_triple_passes(tmp_path: Path) -> None:
    """Local triple matches a known triple → no raise."""
    _write_triple(tmp_path / "box-01", _LOCAL)
    await preflight_check_known_fleet_triple(
        known_fleet_dir=tmp_path,
        local_triple=_LOCAL,
    )  # no raise


async def test_mismatching_triple_raises(tmp_path: Path) -> None:
    """Local triple does NOT match the single known triple → UnknownFleetTriple."""
    other = FleetTriple(em7421_firmware="OTHER_FW", zao_sdk="9.9.9", libqmi="2.0.0")
    _write_triple(tmp_path / "box-01", other)
    with pytest.raises(UnknownFleetTriple, match="unknown fleet triple"):
        await preflight_check_known_fleet_triple(
            known_fleet_dir=tmp_path,
            local_triple=_LOCAL,
        )


async def test_multiple_entries_one_match_passes(tmp_path: Path) -> None:
    """Multiple known triples, one matches → no raise."""
    _write_triple(tmp_path / "box-01", FleetTriple(em7421_firmware="X", zao_sdk="Y", libqmi="Z"))
    _write_triple(tmp_path / "box-02", _LOCAL)
    _write_triple(tmp_path / "box-03", FleetTriple(em7421_firmware="A", zao_sdk="B", libqmi="C"))
    await preflight_check_known_fleet_triple(
        known_fleet_dir=tmp_path,
        local_triple=_LOCAL,
    )  # no raise


async def test_malformed_triple_skipped_other_match_passes(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Malformed triple.json is skipped (logger warning); other matches still considered."""
    # Malformed: missing required field (em7421_firmware / zao_sdk / libqmi all absent).
    (tmp_path / "box-bad").mkdir()
    (tmp_path / "box-bad" / "triple.json").write_text('{"schema_version": 1}')
    # Valid match
    _write_triple(tmp_path / "box-ok", _LOCAL)
    await preflight_check_known_fleet_triple(
        known_fleet_dir=tmp_path,
        local_triple=_LOCAL,
    )  # no raise
    # And the bad file was warned about.
    assert any("skipping malformed known-fleet entry" in r.message for r in caplog.records)


async def test_malformed_triple_only_raises(tmp_path: Path) -> None:
    """All candidates malformed → falls into empty-or-missing branch (UnknownFleetTriple)."""
    (tmp_path / "box-bad").mkdir()
    (tmp_path / "box-bad" / "triple.json").write_text("{not json at all}")
    with pytest.raises(UnknownFleetTriple, match="empty or missing"):
        await preflight_check_known_fleet_triple(
            known_fleet_dir=tmp_path,
            local_triple=_LOCAL,
        )


def test_nested_triple_json_not_picked_up(tmp_path: Path) -> None:
    """_load_known_triples walks ONLY direct <box-id>/triple.json — not deeper."""
    # Verify _load_known_triples only walks direct subdirs, not deeper.
    deep = tmp_path / "box-01" / "subdir" / "deeper"
    deep.mkdir(parents=True)
    (deep / "triple.json").write_text(
        json.dumps(
            {
                "em7421_firmware": "X",
                "zao_sdk": "Y",
                "libqmi": "Z",
            }
        )
    )
    triples = _load_known_triples(tmp_path)
    # ``box-01`` itself has no triple.json directly, just a subdir tree.
    assert triples == []
