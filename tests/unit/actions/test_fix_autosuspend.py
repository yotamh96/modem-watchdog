"""Tests for actions.fix_autosuspend -- write 'on' to power/control sysfs.

Cross-platform: tests use tmp_path so they run on Windows dev hosts too
(no /sys access). The action's only side effect is the file write.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from spark_modem.actions import fix_autosuspend
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind
from tests.fakes.runner import FakeRunner
from tests.unit.actions._helpers import make_ctx


def _who() -> WhoModem:
    return WhoModem(usb_path="2-3.1.1", cdc_wdm="cdc-wdm0")


def _make_sysfs_tree(root: Path, *, initial_content: str = "auto") -> Path:
    """Create tmp_path/bus/usb/devices/2-3.1.1/power/control with initial_content."""
    target = root / "bus" / "usb" / "devices" / "2-3.1.1" / "power"
    target.mkdir(parents=True, exist_ok=True)
    (target / "control").write_text(initial_content, encoding="ascii")
    return target / "control"


@pytest.mark.asyncio
async def test_fix_autosuspend_writes_on_to_power_control(tmp_path: Path) -> None:
    """After execute(), power/control file contains 'on'."""
    target = _make_sysfs_tree(tmp_path, initial_content="auto")
    runner = FakeRunner()  # not used by fix_autosuspend
    ctx, _logger, _clock = make_ctx(runner, sysfs_root=tmp_path)
    result = await fix_autosuspend.execute(_who(), ctx)
    assert result.succeeded is True
    assert result.kind == ActionKind.FIX_AUTOSUSPEND
    assert target.read_text(encoding="ascii") == "on"
    # No subprocess invocations
    assert runner.calls == []


@pytest.mark.asyncio
async def test_fix_autosuspend_verify_reads_back_on(tmp_path: Path) -> None:
    """verify() reads back 'on' -> VerifyResult.ok."""
    _make_sysfs_tree(tmp_path, initial_content="on")
    runner = FakeRunner()
    ctx, _logger, _clock = make_ctx(runner, sysfs_root=tmp_path)
    result = await fix_autosuspend.verify(_who(), ctx)
    assert result.status == "ok"


@pytest.mark.asyncio
async def test_fix_autosuspend_verify_failed_when_auto(tmp_path: Path) -> None:
    """verify() reads back 'auto' -> VerifyResult.failed."""
    _make_sysfs_tree(tmp_path, initial_content="auto")
    runner = FakeRunner()
    ctx, _logger, _clock = make_ctx(runner, sysfs_root=tmp_path)
    result = await fix_autosuspend.verify(_who(), ctx)
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_fix_autosuspend_fails_when_path_missing(tmp_path: Path) -> None:
    """power/control parent dir absent -> sysfs_write_error failure."""
    # Deliberately do NOT create the sysfs tree.
    runner = FakeRunner()
    ctx, _logger, _clock = make_ctx(runner, sysfs_root=tmp_path)
    result = await fix_autosuspend.execute(_who(), ctx)
    assert result.succeeded is False
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("sysfs_write_error:")


@pytest.mark.asyncio
async def test_fix_autosuspend_verify_failed_when_path_missing(tmp_path: Path) -> None:
    """verify() returns sysfs_read_error when target file absent."""
    runner = FakeRunner()
    ctx, _logger, _clock = make_ctx(runner, sysfs_root=tmp_path)
    result = await fix_autosuspend.verify(_who(), ctx)
    assert result.status == "failed"
    assert "sysfs_read_error" in result.detail
