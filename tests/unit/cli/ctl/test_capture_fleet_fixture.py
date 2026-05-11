"""Tests for ``spark-modem ctl capture-fleet-fixture`` (Phase 5 X-01 / X-02).

Build the per-box fleet-fixture directory tree against injected fixtures;
exercise ADR-0009 usb_path keying; verify PII redaction at capture time;
pin the QMICLI_CAPTURE_VERBS list at exactly 7 entries (X-02 lock).

Fixture-subprocess pattern: monkeypatch ``subproc_runner.run`` to return
canned bytes per verb-arg; the production code path is exercised end-to-end
except for the actual qmicli invocation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from spark_modem.cli.ctl.capture_fleet_fixture import (
    QMICLI_CAPTURE_VERBS,
    build_fleet_fixture,
)
from spark_modem.cli.main import _build_parser
from spark_modem.inventory.descriptor import ModemDescriptor
from spark_modem.qmi.version import FleetTriple
from spark_modem.subproc import runner as subproc_runner
from spark_modem.subproc.result import CompletedProcess

_USB_PATH_RE = re.compile(r"^\d+-\d+(\.\d+)+$")
_REDACTED_RE = re.compile(rb"<redacted:[0-9a-f]{8}>")


def _make_descriptors() -> list[ModemDescriptor]:
    return [
        ModemDescriptor(
            line=1, cdc_wdm="cdc-wdm0", usb_path="2-3.1.1", ns=None, iface="wwan0"
        ),
        ModemDescriptor(
            line=2, cdc_wdm="cdc-wdm1", usb_path="2-3.1.2", ns=None, iface="wwan1"
        ),
    ]


def _fixture_bytes(relpath: str) -> bytes:
    return Path(f"tests/fixtures/qmicli/{relpath}").read_bytes()


@pytest.fixture
def _patched_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch ``subproc_runner.run`` to return canned per-verb fixtures.

    Substitutions vs. plan-text (Plan 05-03 Task 2 §765-773): the plan
    referenced ``get_signal/1.30/lte_strong.txt`` (exists), ``get_serving_system/
    1.30/registered.txt`` (does NOT exist — real name is ``registered_home.txt``),
    ``get_current_settings/1.30/connected.txt`` (does NOT exist — real name is
    ``raw_ip_y.txt``), and ``get_profile_settings/1.30/default.txt`` (does NOT
    exist — real name is ``profile1_internet.txt``). Real fixture names below.
    """
    verb_to_fixture = {
        "--dms-get-revision": _fixture_bytes("get_revision/1.30/standard.txt"),
        "--dms-get-operating-mode": _fixture_bytes("get_operating_mode/1.30/online.txt"),
        "--uim-get-card-status": _fixture_bytes(
            "uim_get_card_status/1.30/with_iccid.txt"
        ),
        "--nas-get-signal-info": _fixture_bytes("get_signal/1.30/lte_strong.txt"),
        "--nas-get-serving-system": _fixture_bytes(
            "get_serving_system/1.30/registered_home.txt"
        ),
        "--wds-get-current-settings": _fixture_bytes(
            "get_current_settings/1.30/raw_ip_y.txt"
        ),
        "--wds-get-profile-settings": _fixture_bytes(
            "get_profile_settings/1.30/profile1_internet.txt"
        ),
        "--version": _fixture_bytes("version/1.30/standard.txt"),
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
            stdout=b"# stub stdout\n",
            stderr=b"",
            duration_monotonic=0.0,
        )

    monkeypatch.setattr(subproc_runner, "run", fake_run)


async def test_build_fleet_fixture_creates_expected_tree(
    tmp_path: Path,
    _patched_runner: None,
) -> None:
    out = tmp_path / "box-01"
    zao_log = Path("tests/fixtures/zao_log/version/banner_present.txt")

    await build_fleet_fixture(
        out_path=out,
        descriptors=_make_descriptors(),
        zao_log_path=zao_log,
        box_id="box-01",
    )

    assert (out / "triple.json").is_file()
    assert (out / "zao-log-sample.txt").is_file()
    assert (out / "qmi").is_dir()
    for descriptor in _make_descriptors():
        modem_dir = out / "qmi" / descriptor.usb_path
        assert modem_dir.is_dir(), f"missing per-modem dir {descriptor.usb_path}"
        for verb_name, _ in QMICLI_CAPTURE_VERBS:
            assert (modem_dir / f"{verb_name}.txt").is_file(), (
                f"missing {verb_name}.txt"
            )


async def test_triple_json_deserializes_to_fleet_triple(
    tmp_path: Path,
    _patched_runner: None,
) -> None:
    out = tmp_path / "box-01"
    await build_fleet_fixture(
        out_path=out,
        descriptors=_make_descriptors(),
        zao_log_path=Path("tests/fixtures/zao_log/version/banner_present.txt"),
    )

    data = json.loads((out / "triple.json").read_text())
    triple = FleetTriple(
        em7421_firmware=data["em7421_firmware"],
        zao_sdk=data["zao_sdk"],
        libqmi=data["libqmi"],
    )
    assert triple.em7421_firmware == "SWI9X30C_02.38.00.00"
    assert triple.libqmi == "1.30.6"
    assert triple.zao_sdk == "2.1.0"


async def test_modem_subdirs_match_usb_path_shape(
    tmp_path: Path,
    _patched_runner: None,
) -> None:
    out = tmp_path / "box-01"
    await build_fleet_fixture(
        out_path=out,
        descriptors=_make_descriptors(),
        zao_log_path=Path("tests/fixtures/zao_log/version/banner_present.txt"),
    )
    for subdir in (out / "qmi").iterdir():
        assert _USB_PATH_RE.match(subdir.name), (
            f"ADR-0009 violation: {subdir.name} does not match usb_path shape"
        )


async def test_uim_capture_redacts_pii(
    tmp_path: Path,
    _patched_runner: None,
) -> None:
    out = tmp_path / "box-01"
    await build_fleet_fixture(
        out_path=out,
        descriptors=_make_descriptors(),
        zao_log_path=Path("tests/fixtures/zao_log/version/banner_present.txt"),
    )
    for descriptor in _make_descriptors():
        uim = (
            out / "qmi" / descriptor.usb_path / "uim_get_card_status.txt"
        ).read_bytes()
        assert _REDACTED_RE.search(uim) is not None, (
            "no redaction token in uim_get_card_status.txt"
        )
        assert b"8997201700123456789" not in uim, "raw ICCID survived redaction"
        assert b"425010012345678" not in uim, "raw IMSI survived redaction"


def test_argparse_capture_fleet_fixture_resolves() -> None:
    parser = _build_parser()
    args = parser.parse_args(["ctl", "capture-fleet-fixture", "--out", "/tmp/x"])
    assert args.out == "/tmp/x"
    # func is the dispatch hook
    assert args.func.__module__ == "spark_modem.cli.ctl.capture_fleet_fixture"


def test_argparse_requires_out() -> None:
    parser = _build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["ctl", "capture-fleet-fixture"])
    assert exc_info.value.code == 2  # argparse's standard "missing argument" exit


def test_qmicli_capture_verbs_list_is_locked_at_7() -> None:
    # Phase 5 X-02 locks this set; modification is a deliberate enum
    # change and pinned by this test (frozenset comparison catches
    # both addition and removal).
    verb_names = frozenset(name for name, _ in QMICLI_CAPTURE_VERBS)
    assert verb_names == frozenset(
        {
            "dms_get_revision",
            "dms_get_operating_mode",
            "uim_get_card_status",
            "nas_get_signal_info",
            "nas_get_serving_system",
            "wds_get_current_settings",
            "wds_get_profile_settings",
        }
    )
    assert len(QMICLI_CAPTURE_VERBS) == 7
