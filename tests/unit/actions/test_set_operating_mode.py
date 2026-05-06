"""Tests for actions.set_operating_mode -- DMS set/get operating mode."""

from __future__ import annotations

from pathlib import Path

import pytest

from spark_modem.actions import set_operating_mode
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


def _get_argv() -> list[str]:
    return [*base_argv(), "--dms-get-operating-mode"]


def _set_argv(mode: str = "online") -> list[str]:
    return [*base_argv(), f"--dms-set-operating-mode={mode}"]


@pytest.mark.asyncio
async def test_set_operating_mode_writes_when_low_power() -> None:
    runner = FakeRunner()
    runner.register(_get_argv(), ok(_get_argv(), _read_fixture("get_operating_mode", "low_power")))
    runner.register(_set_argv("online"), ok(_set_argv("online")))
    ctx, _logger, _clock = make_ctx(runner)
    result = await set_operating_mode.execute(_who(), ctx)
    assert result.succeeded is True
    assert result.kind == ActionKind.SET_OPERATING_MODE
    assert any("--dms-set-operating-mode=online" in arg for call in runner.calls for arg in call)


@pytest.mark.asyncio
async def test_set_operating_mode_skips_when_already_online() -> None:
    runner = FakeRunner()
    runner.register(_get_argv(), ok(_get_argv(), _read_fixture("get_operating_mode", "online")))
    # NOT registering --dms-set-operating-mode=online; FakeRunner KeyError if called.
    ctx, _logger, _clock = make_ctx(runner)
    result = await set_operating_mode.execute(_who(), ctx)
    assert result.succeeded is True
    assert not any(
        "--dms-set-operating-mode=online" in arg for call in runner.calls for arg in call
    )


@pytest.mark.asyncio
async def test_set_operating_mode_fails_on_get_error() -> None:
    runner = FakeRunner()
    runner.register(
        _get_argv(),
        CompletedProcess.make(
            argv=_get_argv(),
            exit_code=1,
            stdout=b"",
            stderr=b"unhelpful",
            duration_monotonic=0.01,
            timed_out=False,
        ),
    )
    ctx, _logger, _clock = make_ctx(runner)
    result = await set_operating_mode.execute(_who(), ctx)
    assert result.succeeded is False
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("get_op_mode:")


@pytest.mark.asyncio
async def test_set_operating_mode_fails_on_set_error() -> None:
    runner = FakeRunner()
    runner.register(_get_argv(), ok(_get_argv(), _read_fixture("get_operating_mode", "low_power")))
    runner.register(
        _set_argv("online"),
        CompletedProcess.make(
            argv=_set_argv("online"),
            exit_code=1,
            stdout=b"",
            stderr=b"set failed",
            duration_monotonic=0.01,
            timed_out=False,
        ),
    )
    ctx, _logger, _clock = make_ctx(runner)
    result = await set_operating_mode.execute(_who(), ctx)
    assert result.succeeded is False
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("set_op_mode:")


@pytest.mark.asyncio
async def test_set_operating_mode_verify_returns_ok_when_online() -> None:
    runner = FakeRunner()
    runner.register(_get_argv(), ok(_get_argv(), _read_fixture("get_operating_mode", "online")))
    ctx, _logger, _clock = make_ctx(runner)
    result = await set_operating_mode.verify(_who(), ctx)
    assert result.status == "ok"
