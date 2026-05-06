"""Tests for actions.fix_raw_ip -- read-then-write raw_ip via wds_set_ip_family."""

from __future__ import annotations

from pathlib import Path

import pytest

from spark_modem.actions import fix_raw_ip
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


def _settings_argv() -> list[str]:
    return [*base_argv(), "--wds-get-current-settings"]


def _set_ip_argv(family: int = 4) -> list[str]:
    return [*base_argv(), f"--wds-set-ip-family={family}"]


@pytest.mark.asyncio
async def test_fix_raw_ip_writes_when_n() -> None:
    """raw_ip=N -> --wds-set-ip-family=4 invocation recorded.

    Proves the call routed through QmiWrapper.wds_set_ip_family rather
    than reaching into ctx.qmi._runner directly.
    """
    runner = FakeRunner()
    runner.register(
        _settings_argv(), ok(_settings_argv(), _read_fixture("get_current_settings", "raw_ip_n"))
    )
    runner.register(_set_ip_argv(4), ok(_set_ip_argv(4)))
    ctx, _logger, _clock = make_ctx(runner)
    result = await fix_raw_ip.execute(_who(), ctx)
    assert result.succeeded is True
    assert result.kind == ActionKind.FIX_RAW_IP
    # Argv with --wds-set-ip-family=4 must be recorded.
    assert any("--wds-set-ip-family=4" in arg for call in runner.calls for arg in call)


@pytest.mark.asyncio
async def test_fix_raw_ip_skips_when_y() -> None:
    """raw_ip=Y -> NO --wds-set-ip-family call recorded."""
    runner = FakeRunner()
    runner.register(
        _settings_argv(), ok(_settings_argv(), _read_fixture("get_current_settings", "raw_ip_y"))
    )
    # NOT registering set-ip-family; FakeRunner KeyError if called.
    ctx, _logger, _clock = make_ctx(runner)
    result = await fix_raw_ip.execute(_who(), ctx)
    assert result.succeeded is True
    assert not any("--wds-set-ip-family" in arg for call in runner.calls for arg in call)


@pytest.mark.asyncio
async def test_fix_raw_ip_fails_on_get_settings_error() -> None:
    runner = FakeRunner()
    runner.register(
        _settings_argv(),
        CompletedProcess.make(
            argv=_settings_argv(),
            exit_code=1,
            stdout=b"",
            stderr=b"unhelpful",
            duration_monotonic=0.01,
            timed_out=False,
        ),
    )
    ctx, _logger, _clock = make_ctx(runner)
    result = await fix_raw_ip.execute(_who(), ctx)
    assert result.succeeded is False
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("get_settings:")


@pytest.mark.asyncio
async def test_fix_raw_ip_fails_on_set_ip_family_error() -> None:
    runner = FakeRunner()
    runner.register(
        _settings_argv(), ok(_settings_argv(), _read_fixture("get_current_settings", "raw_ip_n"))
    )
    runner.register(
        _set_ip_argv(4),
        CompletedProcess.make(
            argv=_set_ip_argv(4),
            exit_code=1,
            stdout=b"",
            stderr=b"set fail",
            duration_monotonic=0.01,
            timed_out=False,
        ),
    )
    ctx, _logger, _clock = make_ctx(runner)
    result = await fix_raw_ip.execute(_who(), ctx)
    assert result.succeeded is False
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("set_ip_family:")


@pytest.mark.asyncio
async def test_fix_raw_ip_verify_ok_after_y() -> None:
    runner = FakeRunner()
    runner.register(
        _settings_argv(), ok(_settings_argv(), _read_fixture("get_current_settings", "raw_ip_y"))
    )
    ctx, _logger, _clock = make_ctx(runner)
    result = await fix_raw_ip.verify(_who(), ctx)
    assert result.status == "ok"
