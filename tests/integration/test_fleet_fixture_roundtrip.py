"""Integration test for the X-01 / X-02 fleet-fixture capture pipeline.

Uses Wave 1 fixtures and the patched ``subproc_runner.run`` pattern from
``tests/unit/cli/ctl/test_capture_fleet_fixture.py``; "integration" here means
we exercise the full ``build_fleet_fixture`` orchestration end-to-end (triple
synthesis + Zao log sample + per-modem capture + idempotent re-capture),
not just isolated helpers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

from spark_modem.cli.ctl.capture_fleet_fixture import (  # noqa: E402
    build_fleet_fixture,
)
from spark_modem.inventory.descriptor import ModemDescriptor  # noqa: E402
from spark_modem.qmi.version import FleetTriple  # noqa: E402
from spark_modem.subproc import runner as subproc_runner  # noqa: E402
from spark_modem.subproc.result import CompletedProcess  # noqa: E402


def _descriptors() -> list[ModemDescriptor]:
    return [
        ModemDescriptor(
            line=1, cdc_wdm="cdc-wdm0", usb_path="2-3.1.1", ns=None, iface="wwan0"
        ),
    ]


@pytest.fixture
def _patched_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch ``subproc_runner.run`` to satisfy the firmware + libqmi probes.

    Only the two verbs actually consumed by ``compute_fleet_triple``
    (``--version`` for libqmi, ``--dms-get-revision`` for firmware) need real
    fixture content; every other capture verb degrades to a generic stub
    (``# stub`` body) — the integration tests don't assert on those.
    """
    verb_to_fixture = {
        "--dms-get-revision": Path(
            "tests/fixtures/qmicli/get_revision/1.30/standard.txt"
        ).read_bytes(),
        "--version": Path(
            "tests/fixtures/qmicli/version/1.30/standard.txt"
        ).read_bytes(),
    }

    async def fake_run(
        argv: list[str],
        *,
        timeout_s: float,
        stdin: bytes | None = None,
        env: dict[str, str] | None = None,
    ) -> CompletedProcess:
        del timeout_s, stdin, env
        for arg in argv:
            key = arg.split("=", 1)[0]
            if key in verb_to_fixture:
                return CompletedProcess.make(
                    argv=argv,
                    exit_code=0,
                    stdout=verb_to_fixture[key],
                    stderr=b"",
                    duration_monotonic=0.0,
                )
        return CompletedProcess.make(
            argv=argv,
            exit_code=0,
            stdout=b"# stub\n",
            stderr=b"",
            duration_monotonic=0.0,
        )

    monkeypatch.setattr(subproc_runner, "run", fake_run)


async def test_triple_json_roundtrips_via_fleet_triple(
    tmp_path: Path,
    _patched_runner: None,
) -> None:
    out = tmp_path / "box-01"
    await build_fleet_fixture(
        out_path=out,
        descriptors=_descriptors(),
        zao_log_path=Path("tests/fixtures/zao_log/version/banner_present.txt"),
        box_id="box-01",
    )

    raw = json.loads((out / "triple.json").read_text())
    triple = FleetTriple(
        em7421_firmware=raw["em7421_firmware"],
        zao_sdk=raw["zao_sdk"],
        libqmi=raw["libqmi"],
    )
    # Round-trip: re-serialize → re-parse → values stable
    re_json = triple.model_dump_json()
    re_triple = FleetTriple.model_validate_json(re_json)
    assert re_triple == triple

    # And the values are what we expect from the fixtures.
    assert triple.em7421_firmware == "SWI9X30C_02.38.00.00"
    assert triple.libqmi == "1.30.6"
    assert triple.zao_sdk == "2.1.0"


async def test_zao_log_sample_contains_only_rascow_stat_lines(
    tmp_path: Path,
    _patched_runner: None,
) -> None:
    out = tmp_path / "box-01"
    await build_fleet_fixture(
        out_path=out,
        descriptors=_descriptors(),
        zao_log_path=Path("tests/fixtures/zao_log/version/banner_present.txt"),
    )
    sample = (out / "zao-log-sample.txt").read_bytes()
    # Empty sample is also acceptable (fixture has 2 RASCOW lines).
    for line in sample.splitlines():
        if not line.strip():
            continue
        assert b"RASCOW_STAT" in line, f"non-RASCOW line in sample: {line!r}"


async def test_capture_is_idempotent(
    tmp_path: Path,
    _patched_runner: None,
) -> None:
    out = tmp_path / "box-01"
    zao = Path("tests/fixtures/zao_log/version/banner_present.txt")
    await build_fleet_fixture(out_path=out, descriptors=_descriptors(), zao_log_path=zao)
    first_triple = (out / "triple.json").read_text()
    # Capture again into the same out dir.
    await build_fleet_fixture(out_path=out, descriptors=_descriptors(), zao_log_path=zao)
    second_triple = (out / "triple.json").read_text()
    # The em7421_firmware / zao_sdk / libqmi fields are identical;
    # first_seen_iso differs (it's ``datetime.now()``). Parse and compare
    # the identity fields only.
    a = json.loads(first_triple)
    b = json.loads(second_triple)
    assert a["em7421_firmware"] == b["em7421_firmware"]
    assert a["zao_sdk"] == b["zao_sdk"]
    assert a["libqmi"] == b["libqmi"]
