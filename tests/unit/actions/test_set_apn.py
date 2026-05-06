"""Tests for actions.set_apn -- read-then-write APN with carrier-table lookup.

Covers FR-30 (lookup), FR-31 (skip when match), FR-32 (verify reads back),
and the QMI error paths (serving_system error, get_profile error,
modify_profile error, no_carrier).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from spark_modem.actions import set_apn
from spark_modem.subproc.result import CompletedProcess
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind
from tests.fakes.runner import FakeRunner
from tests.unit.actions._helpers import base_argv, make_ctx, ok

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "qmicli"


def _read_fixture(intent: str, scenario: str, version: str = "1.30") -> bytes:
    return (_FIXTURES / intent / version / f"{scenario}.txt").read_bytes()


def _who() -> WhoModem:
    return WhoModem(usb_path="2-3.1.1", cdc_wdm="cdc-wdm0")


def _serving_argv() -> list[str]:
    return [*base_argv(), "--nas-get-serving-system"]


def _profile_argv() -> list[str]:
    return [*base_argv(), "--wds-get-profile-settings=3gpp,1"]


def _modify_argv(apn: str, ip_family: int = 4) -> list[str]:
    return [
        *base_argv(),
        f"--wds-modify-profile=3gpp,1,apn={apn},ip-family={ip_family}",
    ]


@pytest.mark.asyncio
async def test_set_apn_writes_when_apn_differs() -> None:
    """Carrier table -> 'internet'; profile-1 has 'internet' fixture too --
    so we override the profile fixture to a non-matching APN by registering
    a custom CompletedProcess. Asserts modify-profile WAS recorded.
    """
    runner = FakeRunner()
    # serving_system: 425/03 -> Pelephone (matches default carrier table)
    runner.register(
        _serving_argv(), ok(_serving_argv(), _read_fixture("get_serving_system", "registered_home"))
    )
    # profile-1: APN='internetg' (mismatch with carrier table 'internet')
    profile_stdout = (
        b"# libqmi_version: 1.30\n"
        b"[/dev/cdc-wdm0] Profile settings retrieved:\n"
        b"\tProfile index: '1'\n"
        b"\tAPN: 'internetg'\n"
        b"\tIP family: 'ipv4'\n"
    )
    runner.register(_profile_argv(), ok(_profile_argv(), profile_stdout))
    # modify-profile: success
    modify_argv = _modify_argv("internet")
    runner.register(modify_argv, ok(modify_argv))

    ctx, _logger, _clock = make_ctx(runner)
    result = await set_apn.execute(_who(), ctx)
    assert result.succeeded is True
    assert result.kind == ActionKind.SET_APN
    assert result.failure_reason is None
    # FakeRunner recorded the modify-profile call
    assert any(
        "--wds-modify-profile=3gpp,1,apn=internet,ip-family=4" in arg
        for call in runner.calls
        for arg in call
    )


@pytest.mark.asyncio
async def test_set_apn_skips_write_when_apn_matches() -> None:
    """profile-1 already 'internet' -- no modify-profile call recorded."""
    runner = FakeRunner()
    runner.register(
        _serving_argv(), ok(_serving_argv(), _read_fixture("get_serving_system", "registered_home"))
    )
    runner.register(
        _profile_argv(),
        ok(_profile_argv(), _read_fixture("get_profile_settings", "profile1_internet")),
    )
    # NOTE: deliberately NOT registering modify-profile; FakeRunner would
    # raise KeyError if it were called.

    ctx, _logger, _clock = make_ctx(runner)
    result = await set_apn.execute(_who(), ctx)
    assert result.succeeded is True
    assert result.failure_reason is None
    # No modify call in argv list
    assert not any("--wds-modify-profile" in arg for call in runner.calls for arg in call)


@pytest.mark.asyncio
async def test_set_apn_fails_when_no_carrier_match() -> None:
    """Synthesise a serving_system fixture with mcc=000/mnc=00 -> no entry."""
    serving_stdout = (
        b"# libqmi_version: 1.30\n"
        b"[/dev/cdc-wdm0] Successfully got serving system:\n"
        b"\tRegistration state: 'registered'\n"
        b"\tRoaming status: 'off'\n"
        b"\tCurrent PLMN:\n"
        b"\t\tMCC: '000'\n"
        b"\t\tMNC: '00'\n"
        b"\t\tDescription: 'Test'\n"
    )
    runner = FakeRunner()
    runner.register(_serving_argv(), ok(_serving_argv(), serving_stdout))

    ctx, _logger, _clock = make_ctx(runner)
    result = await set_apn.execute(_who(), ctx)
    assert result.succeeded is False
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("no_carrier:")
    assert "000" in result.failure_reason
    assert "00" in result.failure_reason


@pytest.mark.asyncio
async def test_set_apn_fails_on_serving_system_qmi_error() -> None:
    """Proxy unavailable on nas-get-serving-system -> failure_reason proxy_died."""
    runner = FakeRunner()
    runner.register(
        _serving_argv(),
        CompletedProcess.make(
            argv=_serving_argv(),
            exit_code=1,
            stdout=b"",
            stderr=b"error: couldn't open the QMI device: proxy unavailable\n",
            duration_monotonic=0.01,
            timed_out=False,
        ),
    )
    ctx, _logger, _clock = make_ctx(runner)
    result = await set_apn.execute(_who(), ctx)
    assert result.succeeded is False
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("serving_system:")
    assert "proxy_died" in result.failure_reason


@pytest.mark.asyncio
async def test_set_apn_fails_on_get_profile_error() -> None:
    """get-profile-settings non-zero exit -> failure_reason starts with get_profile."""
    runner = FakeRunner()
    runner.register(
        _serving_argv(), ok(_serving_argv(), _read_fixture("get_serving_system", "registered_home"))
    )
    runner.register(
        _profile_argv(),
        CompletedProcess.make(
            argv=_profile_argv(),
            exit_code=1,
            stdout=b"",
            stderr=b"unhelpful",
            duration_monotonic=0.01,
            timed_out=False,
        ),
    )
    ctx, _logger, _clock = make_ctx(runner)
    result = await set_apn.execute(_who(), ctx)
    assert result.succeeded is False
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("get_profile:")


@pytest.mark.asyncio
async def test_set_apn_fails_on_modify_profile_error() -> None:
    """modify-profile non-zero exit -> failure_reason starts with modify_profile."""
    runner = FakeRunner()
    runner.register(
        _serving_argv(), ok(_serving_argv(), _read_fixture("get_serving_system", "registered_home"))
    )
    profile_stdout = (
        b"# libqmi_version: 1.30\n"
        b"[/dev/cdc-wdm0] Profile settings retrieved:\n"
        b"\tProfile index: '1'\n"
        b"\tAPN: 'wrong'\n"
    )
    runner.register(_profile_argv(), ok(_profile_argv(), profile_stdout))
    modify_argv = _modify_argv("internet")
    runner.register(
        modify_argv,
        CompletedProcess.make(
            argv=modify_argv,
            exit_code=1,
            stdout=b"",
            stderr=b"profile mod failed",
            duration_monotonic=0.01,
            timed_out=False,
        ),
    )
    ctx, _logger, _clock = make_ctx(runner)
    result = await set_apn.execute(_who(), ctx)
    assert result.succeeded is False
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("modify_profile:")


@pytest.mark.asyncio
async def test_set_apn_verify_returns_ok_after_match() -> None:
    """verify() re-reads serving_system + profile-1 and matches carrier table."""
    runner = FakeRunner()
    runner.register(
        _serving_argv(), ok(_serving_argv(), _read_fixture("get_serving_system", "registered_home"))
    )
    runner.register(
        _profile_argv(),
        ok(_profile_argv(), _read_fixture("get_profile_settings", "profile1_internet")),
    )
    ctx, _logger, _clock = make_ctx(runner)
    result = await set_apn.verify(_who(), ctx)
    assert result.status == "ok"
