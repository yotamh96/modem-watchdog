"""Tests for actions.verify shared helpers (post-action read-backs).

Each helper does ONE qmicli call + parse, classifies, and returns
VerifyResult.ok or VerifyResult.failed. Tests register canned qmicli
output and assert the resulting VerifyResult shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from spark_modem.actions.verify import (
    verify_apn_equals,
    verify_operating_mode_equals,
    verify_raw_ip_y,
    verify_sim_state_not_power_down,
)
from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.subproc.result import CompletedProcess
from tests.fakes.runner import FakeRunner
from tests.unit.actions._helpers import base_argv, device, ok

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "qmicli"


def _read_fixture(intent: str, scenario: str, version: str = "1.30") -> bytes:
    return (_FIXTURES / intent / version / f"{scenario}.txt").read_bytes()


def _make_qmi(runner: FakeRunner) -> QmiWrapper:
    return QmiWrapper(runner=runner, device=device())


@pytest.mark.asyncio
async def test_verify_apn_equals_returns_ok_when_match() -> None:
    """profile-1 APN='internet'; expected='internet' -> ok."""
    runner = FakeRunner()
    argv = [*base_argv(), "--wds-get-profile-settings=3gpp,1"]
    runner.register(argv, ok(argv, _read_fixture("get_profile_settings", "profile1_internet")))
    qmi = _make_qmi(runner)
    result = await verify_apn_equals(qmi, "internet")
    assert result.status == "ok"
    assert "apn=internet" in result.detail


@pytest.mark.asyncio
async def test_verify_apn_equals_returns_failed_when_mismatch() -> None:
    """profile-1 APN='internet'; expected='internetg' -> failed."""
    runner = FakeRunner()
    argv = [*base_argv(), "--wds-get-profile-settings=3gpp,1"]
    runner.register(argv, ok(argv, _read_fixture("get_profile_settings", "profile1_internet")))
    qmi = _make_qmi(runner)
    result = await verify_apn_equals(qmi, "internetg")
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_verify_apn_equals_failed_on_qmi_error() -> None:
    """Non-zero exit on get-profile-settings -> verify failed with qmi_error detail."""
    runner = FakeRunner()
    argv = [*base_argv(), "--wds-get-profile-settings=3gpp,1"]
    runner.register(
        argv,
        CompletedProcess.make(
            argv=argv,
            exit_code=1,
            stdout=b"",
            stderr=b"unhelpful error",
            duration_monotonic=0.01,
            timed_out=False,
        ),
    )
    qmi = _make_qmi(runner)
    result = await verify_apn_equals(qmi, "internet")
    assert result.status == "failed"
    assert "qmi_error" in result.detail


@pytest.mark.asyncio
async def test_verify_raw_ip_y_returns_ok() -> None:
    runner = FakeRunner()
    argv = [*base_argv(), "--wds-get-current-settings"]
    runner.register(argv, ok(argv, _read_fixture("get_current_settings", "raw_ip_y")))
    qmi = _make_qmi(runner)
    result = await verify_raw_ip_y(qmi)
    assert result.status == "ok"
    assert "raw_ip=Y" in result.detail


@pytest.mark.asyncio
async def test_verify_raw_ip_y_returns_failed_on_n() -> None:
    runner = FakeRunner()
    argv = [*base_argv(), "--wds-get-current-settings"]
    runner.register(argv, ok(argv, _read_fixture("get_current_settings", "raw_ip_n")))
    qmi = _make_qmi(runner)
    result = await verify_raw_ip_y(qmi)
    assert result.status == "failed"
    assert "raw_ip" in result.detail


@pytest.mark.asyncio
async def test_verify_operating_mode_online_returns_ok() -> None:
    runner = FakeRunner()
    argv = [*base_argv(), "--dms-get-operating-mode"]
    runner.register(argv, ok(argv, _read_fixture("get_operating_mode", "online")))
    qmi = _make_qmi(runner)
    result = await verify_operating_mode_equals(qmi, "online")
    assert result.status == "ok"


@pytest.mark.asyncio
async def test_verify_operating_mode_failed_when_low_power() -> None:
    runner = FakeRunner()
    argv = [*base_argv(), "--dms-get-operating-mode"]
    runner.register(argv, ok(argv, _read_fixture("get_operating_mode", "low_power")))
    qmi = _make_qmi(runner)
    result = await verify_operating_mode_equals(qmi, "online")
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_verify_sim_state_not_power_down_passes_on_ready() -> None:
    runner = FakeRunner()
    argv = [*base_argv(), "--uim-get-card-status"]
    runner.register(argv, ok(argv, _read_fixture("get_sim_state", "ready")))
    qmi = _make_qmi(runner)
    result = await verify_sim_state_not_power_down(qmi)
    assert result.status == "ok"
    # ready fixture parses to card_state='present' (the slot card-state line)
    assert "card_state=" in result.detail


@pytest.mark.asyncio
async def test_verify_sim_state_not_power_down_fails_on_power_down() -> None:
    runner = FakeRunner()
    argv = [*base_argv(), "--uim-get-card-status"]
    runner.register(argv, ok(argv, _read_fixture("get_sim_state", "sim_power_down")))
    qmi = _make_qmi(runner)
    result = await verify_sim_state_not_power_down(qmi)
    assert result.status == "failed"
