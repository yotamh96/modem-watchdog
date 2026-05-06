"""Tests for qmi/parsers/*: each fixture under tests/fixtures/qmicli/<intent>/<libqmi-version>/
is parametrized into a test that asserts the matching parser returns the
expected typed result. Plus dedicated tests for the version-header utility,
RegistrationState enum mapping, and UNEXPECTED_OUTPUT error path.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from spark_modem.qmi.errors import QmiError, QmiErrorReason
from spark_modem.qmi.parsers._header import libqmi_version_of, strip_header
from spark_modem.qmi.parsers.get_current_settings import (
    GetCurrentSettingsResult,
    parse_get_current_settings,
)
from spark_modem.qmi.parsers.get_data_session import (
    GetDataSessionResult,
    parse_get_data_session,
)
from spark_modem.qmi.parsers.get_operating_mode import (
    GetOperatingModeResult,
    parse_get_operating_mode,
)
from spark_modem.qmi.parsers.get_profile_settings import (
    GetProfileSettingsResult,
    parse_get_profile_settings,
)
from spark_modem.qmi.parsers.get_serving_system import (
    GetServingSystemResult,
    parse_get_serving_system,
)
from spark_modem.qmi.parsers.get_signal import GetSignalResult, parse_get_signal
from spark_modem.qmi.parsers.get_sim_state import GetSimStateResult, parse_get_sim_state
from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.subproc.result import CompletedProcess
from spark_modem.wire.enums import RegistrationState

# ---- header utility ---------------------------------------------------------


def test_libqmi_version_header_extracted() -> None:
    assert libqmi_version_of(b"# libqmi_version: 1.30\nbody\n") == "1.30"
    assert libqmi_version_of(b"# libqmi_version: 1.32\n[/dev/cdc-wdm0]\n") == "1.32"


def test_libqmi_version_absent_returns_none() -> None:
    """Production qmicli stdout has no header; library must return None."""
    assert libqmi_version_of(b"normal stdout\n") is None
    assert libqmi_version_of(b"") is None


def test_strip_header_removes_first_line_when_present() -> None:
    """Round-trip: strip removes the version line; absent header passes through."""
    body_with = b"# libqmi_version: 1.30\nLTE:\n\tRSSI: '-65 dBm'\n"
    body_without = b"LTE:\n\tRSSI: '-65 dBm'\n"
    assert strip_header(body_with) == body_without
    assert strip_header(body_without) == body_without


def test_strip_header_handles_lone_header_line() -> None:
    """If the body is *only* the header (no trailing newline+body), return b''."""
    assert strip_header(b"# libqmi_version: 1.30") == b""


# ---- per-intent fixture parametrization -------------------------------------

_FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "qmicli"


def _fixture_id(p: Path) -> str:
    return str(p.relative_to(_FIXTURES_ROOT)).replace("\\", "/")


def _signal_fixtures() -> list[Path]:
    return sorted((_FIXTURES_ROOT / "get_signal").rglob("*.txt"))


def _serving_fixtures() -> list[Path]:
    return sorted((_FIXTURES_ROOT / "get_serving_system").rglob("*.txt"))


def _sim_fixtures() -> list[Path]:
    return sorted((_FIXTURES_ROOT / "get_sim_state").rglob("*.txt"))


def _data_session_fixtures() -> list[Path]:
    return sorted((_FIXTURES_ROOT / "get_data_session").rglob("*.txt"))


def _profile_fixtures() -> list[Path]:
    return sorted((_FIXTURES_ROOT / "get_profile_settings").rglob("*.txt"))


def _opmode_fixtures() -> list[Path]:
    return sorted((_FIXTURES_ROOT / "get_operating_mode").rglob("*.txt"))


def _current_settings_fixtures() -> list[Path]:
    return sorted((_FIXTURES_ROOT / "get_current_settings").rglob("*.txt"))


# Per-fixture expected values keyed by fixture filename stem.
_SIGNAL_EXPECTED: dict[str, dict[str, Any]] = {
    "lte_strong": {"rssi_dbm": -65, "rsrp_dbm": -94, "rsrq_db": -9.0, "snr_db": 8.4},
    "lte_weak": {"rssi_dbm": -105, "rsrp_dbm": -118, "rsrq_db": -19.0, "snr_db": -3.1},
    # NR5G_present has no NR5G RSSI; LTE follows so RSSI/RSRP come from LTE.
    "nr5g_present": {"rssi_dbm": -65, "rsrp_dbm": -72, "rsrq_db": -12.0, "snr_db": 15.0},
}


@pytest.mark.parametrize(
    "fixture_path",
    _signal_fixtures(),
    ids=[_fixture_id(p) for p in _signal_fixtures()],
)
def test_parse_get_signal_fixtures(fixture_path: Path) -> None:
    raw = fixture_path.read_bytes()
    # Header utility independently agrees on the version (sanity check on layout).
    assert libqmi_version_of(raw) is not None, fixture_path

    result = parse_get_signal(raw)
    assert isinstance(result, GetSignalResult), result

    expected = _SIGNAL_EXPECTED[fixture_path.stem]
    # NR5G fixture: parser sees NR5G first, but RSSI is NR5G-absent and LTE
    # carries it; the regex finds the first match for each key in document
    # order. Verify only the keys present in the expected dict.
    assert result.rssi_dbm == expected["rssi_dbm"], (fixture_path, result)
    # RSRP: parser .search finds the first occurrence; for NR5G fixture
    # NR5G appears first and contains RSRP, so result.rsrp_dbm should be
    # the NR5G value.
    assert result.rsrp_dbm == expected["rsrp_dbm"], (fixture_path, result)
    assert result.rsrq_db == expected["rsrq_db"], (fixture_path, result)
    assert result.snr_db == expected["snr_db"], (fixture_path, result)


def test_parse_get_signal_unexpected_output_returns_qmierror() -> None:
    err = parse_get_signal(b"random garbage\n")
    assert isinstance(err, QmiError)
    assert err.reason is QmiErrorReason.UNEXPECTED_OUTPUT


_SERVING_EXPECTED: dict[str, dict[str, Any]] = {
    "registered_home": {
        "registration_state": RegistrationState.REGISTERED_HOME,
        "mcc": "425",
        "mnc": "03",
        "description": "Pelephone",
    },
    "not_registered_searching": {
        "registration_state": RegistrationState.NOT_REGISTERED_SEARCHING,
        "mcc": None,
        "mnc": None,
        "description": None,
    },
}


@pytest.mark.parametrize(
    "fixture_path",
    _serving_fixtures(),
    ids=[_fixture_id(p) for p in _serving_fixtures()],
)
def test_parse_get_serving_system_fixtures(fixture_path: Path) -> None:
    raw = fixture_path.read_bytes()
    result = parse_get_serving_system(raw)
    assert isinstance(result, GetServingSystemResult), result
    expected = _SERVING_EXPECTED[fixture_path.stem]
    assert result.registration_state == expected["registration_state"]
    assert result.mcc == expected["mcc"]
    assert result.mnc == expected["mnc"]
    assert result.description == expected["description"]


def test_get_serving_system_registered_home_maps_to_enum() -> None:
    """Dedicated regression test pinning the enum value (RECOVERY_SPEC §4)."""
    raw = (_FIXTURES_ROOT / "get_serving_system" / "1.30" / "registered_home.txt").read_bytes()
    result = parse_get_serving_system(raw)
    assert isinstance(result, GetServingSystemResult)
    assert result.registration_state is RegistrationState.REGISTERED_HOME


def test_get_serving_system_missing_field_returns_qmierror() -> None:
    """If Registration state line is absent, parser must surface MISSING_FIELD."""
    body = (
        b"# libqmi_version: 1.30\n"
        b"[/dev/cdc-wdm0] Successfully got serving system:\n"
        b"\tCS: 'detached'\n"
    )
    err = parse_get_serving_system(body)
    assert isinstance(err, QmiError)
    assert err.reason is QmiErrorReason.MISSING_FIELD
    assert err.field == "registration_state"


def test_get_serving_system_unexpected_output_returns_qmierror() -> None:
    err = parse_get_serving_system(b"unrelated\n")
    assert isinstance(err, QmiError)
    assert err.reason is QmiErrorReason.UNEXPECTED_OUTPUT


_SIM_EXPECTED: dict[str, dict[str, str | None]] = {
    "ready": {
        "card_state": "present",
        "app_state": "ready",
        "iccid": "8997201700123456789",
        "imsi": "425030123456789",
    },
    "sim_app_detected": {
        "card_state": "present",
        "app_state": "detected",
        "iccid": "8997201700123456789",
        "imsi": "425030123456789",
    },
    "sim_power_down": {
        "card_state": "power_down",
        "app_state": None,
        "iccid": None,
        "imsi": None,
    },
}


@pytest.mark.parametrize(
    "fixture_path",
    _sim_fixtures(),
    ids=[_fixture_id(p) for p in _sim_fixtures()],
)
def test_parse_get_sim_state_fixtures(fixture_path: Path) -> None:
    raw = fixture_path.read_bytes()
    result = parse_get_sim_state(raw)
    assert isinstance(result, GetSimStateResult), result
    expected = _SIM_EXPECTED[fixture_path.stem]
    assert result.card_state == expected["card_state"]
    assert result.app_state == expected["app_state"]
    assert result.iccid == expected["iccid"]
    assert result.imsi == expected["imsi"]


def test_get_sim_state_missing_card_state_returns_qmierror() -> None:
    body = b"# libqmi_version: 1.30\nSuccessfully got card status\nSlot [1]:\n"
    err = parse_get_sim_state(body)
    assert isinstance(err, QmiError)
    assert err.reason is QmiErrorReason.MISSING_FIELD
    assert err.field == "card_state"


_DATA_SESSION_EXPECTED: dict[str, str] = {
    "connected": "connected",
    "disconnected": "disconnected",
}


@pytest.mark.parametrize(
    "fixture_path",
    _data_session_fixtures(),
    ids=[_fixture_id(p) for p in _data_session_fixtures()],
)
def test_parse_get_data_session_fixtures(fixture_path: Path) -> None:
    raw = fixture_path.read_bytes()
    result = parse_get_data_session(raw)
    assert isinstance(result, GetDataSessionResult), result
    assert result.connection_status == _DATA_SESSION_EXPECTED[fixture_path.stem]


_PROFILE_EXPECTED: dict[str, dict[str, Any]] = {
    "profile1_internet": {"profile_index": 1, "apn": "internet", "ip_family": 4},
}


@pytest.mark.parametrize(
    "fixture_path",
    _profile_fixtures(),
    ids=[_fixture_id(p) for p in _profile_fixtures()],
)
def test_parse_get_profile_settings_fixtures(fixture_path: Path) -> None:
    raw = fixture_path.read_bytes()
    result = parse_get_profile_settings(raw)
    assert isinstance(result, GetProfileSettingsResult), result
    expected = _PROFILE_EXPECTED[fixture_path.stem]
    assert result.profile_index == expected["profile_index"]
    assert result.apn == expected["apn"]
    assert result.ip_family == expected["ip_family"]


def test_get_profile_settings_missing_index_returns_qmierror() -> None:
    body = b"# libqmi_version: 1.30\nProfile settings retrieved:\n\tAPN: 'internet'\n"
    err = parse_get_profile_settings(body)
    assert isinstance(err, QmiError)
    assert err.reason is QmiErrorReason.MISSING_FIELD
    assert err.field == "profile_index"


_OPMODE_EXPECTED: dict[str, str] = {
    "online": "online",
    "low_power": "low_power",
}


@pytest.mark.parametrize(
    "fixture_path",
    _opmode_fixtures(),
    ids=[_fixture_id(p) for p in _opmode_fixtures()],
)
def test_parse_get_operating_mode_fixtures(fixture_path: Path) -> None:
    raw = fixture_path.read_bytes()
    result = parse_get_operating_mode(raw)
    assert isinstance(result, GetOperatingModeResult), result
    assert result.mode == _OPMODE_EXPECTED[fixture_path.stem]


def test_get_operating_mode_missing_mode_returns_qmierror() -> None:
    body = b"# libqmi_version: 1.30\nOperating mode retrieved:\n\tHW restricted: 'no'\n"
    err = parse_get_operating_mode(body)
    assert isinstance(err, QmiError)
    assert err.reason is QmiErrorReason.MISSING_FIELD
    assert err.field == "mode"


_CURRENT_SETTINGS_EXPECTED: dict[str, dict[str, str | None]] = {
    "raw_ip_y": {"ipv4": "10.69.92.156", "raw_ip": "Y"},
    "raw_ip_n": {"ipv4": "10.69.92.156", "raw_ip": "N"},
}


@pytest.mark.parametrize(
    "fixture_path",
    _current_settings_fixtures(),
    ids=[_fixture_id(p) for p in _current_settings_fixtures()],
)
def test_parse_get_current_settings_fixtures(fixture_path: Path) -> None:
    raw = fixture_path.read_bytes()
    result = parse_get_current_settings(raw)
    assert isinstance(result, GetCurrentSettingsResult), result
    expected = _CURRENT_SETTINGS_EXPECTED[fixture_path.stem]
    assert result.ipv4 == expected["ipv4"]
    assert result.raw_ip == expected["raw_ip"]


# ---- proxy_error fixture cross-checks the wrapper.classify() short-circuit --


def test_proxy_died_fixture_signature_round_trips_through_classify() -> None:
    """The proxy_died.txt fixture content fed as stderr must classify as PROXY_DIED."""
    raw = (_FIXTURES_ROOT / "proxy_error" / "proxy_died.txt").read_bytes()
    # The fixture has the version-header on line 1 + the qmicli error line 2.
    # We feed only the qmicli line as stderr (production stderr never has the
    # # libqmi_version header).
    stderr_only = strip_header(raw)
    cp = CompletedProcess.make(
        argv=["qmicli", "--device-open-proxy", "--device=/dev/cdc-wdm0", "--nas-get-signal-info"],
        exit_code=1,
        stdout=b"",
        stderr=stderr_only,
        duration_monotonic=0.05,
        timed_out=False,
    )
    err = QmiWrapper.classify(cp)
    assert err is not None
    assert err.reason is QmiErrorReason.PROXY_DIED


# ---- extra='ignore' boundary regression (PITFALLS §1.2) ---------------------


@pytest.mark.parametrize(
    ("parser_fn", "fixture_path"),
    [
        (parse_get_signal, _FIXTURES_ROOT / "get_signal" / "1.32" / "nr5g_present.txt"),
        (
            parse_get_serving_system,
            _FIXTURES_ROOT / "get_serving_system" / "1.30" / "registered_home.txt",
        ),
    ],
    ids=["get_signal-nr5g-1.32", "get_serving_system-extra-fields-1.30"],
)
def test_parsers_absorb_unknown_libqmi_fields(
    parser_fn: Callable[[bytes], Any],
    fixture_path: Path,
) -> None:
    """Newer libqmi sections (NR5G in 1.32) and extra fields (Selected
    network, Radio interfaces, Data service capabilities) must not raise --
    extra='ignore' on the result models is the contract.
    """
    raw = fixture_path.read_bytes()
    result = parser_fn(raw)
    # Either result type or a typed QmiError; never an exception.
    assert result is not None
