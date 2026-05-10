"""Tests for actions.usb_reset -- destructive USB driver unbind+rebind via sysfs.

Plan 04-02 Task 2.

Per CONTEXT A-02 / A-06:
  - usb_reset is sysfs file I/O, NOT subprocess. No qmicli call. The action
    body delegates to ``spark_modem.sysfs.unbind_rebind``.
  - Two variants selected via ``ctx.target``: ``"child-port"`` (default,
    leaf usb_path) and ``"parent-hub"`` (parent hub, usb_path.rsplit('.', 1)[0]).
  - verify() is DEFERRED (A-04) -- modem is re-enumerating; in-line
    read-back impossible.
  - Failure semantics: any OSError from the sysfs write is caught and
    surfaced as ``failure_reason="usb_reset:sysfs_write_error:<errno>"``.

The 8 paths covered here:
  1. Happy path child-port -- ActionResult.kind == USB_RESET, succeeded=True.
  2. parent-hub variant -- writes "2-3.1" (NOT "2-3.1.1") to unbind file.
  3. ENOENT (FileNotFoundError) -- failure_reason ends with ":2".
  4. EACCES (PermissionError, POSIX-only) -- failure_reason ends with ":13".
  5. EBUSY -- failure_reason ends with ":16".
  6. verify() returns deferred(detail="next_cycle_observation").
  7. ActionKind.USB_RESET registered in dispatcher.registered_kinds().
  8. The action does NOT issue a qmicli call (FakeRunner.calls stays empty).
"""

from __future__ import annotations

import dataclasses
import errno
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from spark_modem.actions import dispatcher, usb_reset
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind
from tests.fakes.runner import FakeRunner
from tests.unit.actions._helpers import make_ctx


def _who() -> WhoModem:
    return WhoModem(usb_path="2-3.1.1", cdc_wdm="cdc-wdm0")


def _populate_sysfs(tmp_path: Path) -> Path:
    """Pre-create ``<tmp>/bus/usb/drivers/usb/{unbind,bind}`` files; return the dir."""
    drivers_usb = tmp_path / "bus" / "usb" / "drivers" / "usb"
    drivers_usb.mkdir(parents=True, exist_ok=True)
    (drivers_usb / "unbind").write_text("", encoding="ascii")
    (drivers_usb / "bind").write_text("", encoding="ascii")
    return drivers_usb


@pytest.mark.asyncio
async def test_usb_reset_default_target_is_child_port(tmp_path: Path) -> None:
    """child-port (default) writes the leaf usb_path; succeeded=True."""
    runner = FakeRunner()
    ctx, _logger, _clock = make_ctx(runner, sysfs_root=tmp_path)
    drivers_usb = _populate_sysfs(tmp_path)

    # Use a no-delay sleep so the test stays fast.
    async def no_sleep(_seconds: float) -> None:
        return None

    with patch("spark_modem.sysfs.usb_unbind_rebind.asyncio.sleep", no_sleep):
        result = await usb_reset.execute(_who(), ctx)

    assert result.kind == ActionKind.USB_RESET
    assert result.succeeded is True
    assert result.failure_reason is None
    assert result.dry_run is False
    assert (drivers_usb / "unbind").read_text(encoding="ascii") == "2-3.1.1"
    assert (drivers_usb / "bind").read_text(encoding="ascii") == "2-3.1.1"
    # Crucially: NO qmicli call was made (sysfs file I/O only, A-02).
    assert runner.calls == []


@pytest.mark.asyncio
async def test_usb_reset_parent_hub_target_strips_leaf(tmp_path: Path) -> None:
    """parent-hub variant writes ``usb_path.rsplit('.', 1)[0]`` to unbind file."""
    runner = FakeRunner()
    base_ctx, _logger, _clock = make_ctx(runner, sysfs_root=tmp_path)
    ctx = dataclasses.replace(base_ctx, target="parent-hub")
    drivers_usb = _populate_sysfs(tmp_path)

    async def no_sleep(_seconds: float) -> None:
        return None

    with patch("spark_modem.sysfs.usb_unbind_rebind.asyncio.sleep", no_sleep):
        result = await usb_reset.execute(_who(), ctx)

    assert result.succeeded is True
    assert (drivers_usb / "unbind").read_text(encoding="ascii") == "2-3.1"
    assert (drivers_usb / "bind").read_text(encoding="ascii") == "2-3.1"


@pytest.mark.asyncio
async def test_usb_reset_returns_failure_on_oserror_enoent(tmp_path: Path) -> None:
    """No pre-created unbind file -> ENOENT -> failure_reason ends with ':2'."""
    runner = FakeRunner()
    ctx, _logger, _clock = make_ctx(runner, sysfs_root=tmp_path)
    # Deliberately NOT calling _populate_sysfs -- unbind file is missing.

    result = await usb_reset.execute(_who(), ctx)

    assert result.succeeded is False
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("usb_reset:sysfs_write_error:")
    assert result.failure_reason.endswith(f":{errno.ENOENT}")  # ":2"
    assert result.dry_run is False


@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX-only chmod semantics required for EACCES"
)
@pytest.mark.asyncio
async def test_usb_reset_returns_failure_on_eacces(tmp_path: Path) -> None:
    """Read-only unbind file -> EACCES -> failure_reason ends with ':13'."""
    runner = FakeRunner()
    ctx, _logger, _clock = make_ctx(runner, sysfs_root=tmp_path)
    drivers_usb = _populate_sysfs(tmp_path)
    # POSIX: 0o400 = read-only; subsequent write_text raises PermissionError.
    (drivers_usb / "unbind").chmod(0o400)

    try:
        result = await usb_reset.execute(_who(), ctx)
    finally:
        # Restore permissions so tmp_path teardown can delete the file.
        (drivers_usb / "unbind").chmod(0o600)

    assert result.succeeded is False
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("usb_reset:sysfs_write_error:")
    assert result.failure_reason.endswith(f":{errno.EACCES}")  # ":13"


@pytest.mark.asyncio
async def test_usb_reset_returns_failure_on_ebusy(tmp_path: Path) -> None:
    """Monkey-patched OSError(EBUSY) -> failure_reason ends with ':16'."""
    runner = FakeRunner()
    ctx, _logger, _clock = make_ctx(runner, sysfs_root=tmp_path)
    _populate_sysfs(tmp_path)

    real_write_text = Path.write_text

    def busy_write_text(self: Path, *args: Any, **kwargs: Any) -> int:
        if self.name == "unbind":
            raise OSError(errno.EBUSY, "Device or resource busy")
        return real_write_text(self, *args, **kwargs)

    with patch.object(Path, "write_text", busy_write_text):
        result = await usb_reset.execute(_who(), ctx)

    assert result.succeeded is False
    assert result.failure_reason is not None
    assert result.failure_reason.endswith(f":{errno.EBUSY}")  # ":16"


@pytest.mark.asyncio
async def test_usb_reset_verify_is_deferred(tmp_path: Path) -> None:
    """verify() returns VerifyResult.deferred(detail='next_cycle_observation')."""
    runner = FakeRunner()
    ctx, _logger, _clock = make_ctx(runner, sysfs_root=tmp_path)

    result = await usb_reset.verify(_who(), ctx)

    assert result.status == "deferred"
    assert result.detail == "next_cycle_observation"
    # verify() must not invoke qmicli.
    assert runner.calls == []


def test_usb_reset_registered_in_dispatcher() -> None:
    """Plan 04-02 unblocks USB_RESET in actions.dispatcher._REGISTRY."""
    assert ActionKind.USB_RESET in dispatcher.registered_kinds()
    assert dispatcher.is_registered(ActionKind.USB_RESET) is True


@pytest.mark.asyncio
async def test_usb_reset_uses_short_rebind_delay_under_test(tmp_path: Path) -> None:
    """The action invokes asyncio.sleep at most once with the configured delay.

    Pins the action's delegation contract to ``unbind_rebind`` -- exactly one
    sleep happens between the two writes. The default delay is 0.5s in
    sysfs/usb_unbind_rebind.py; the action passes it through.
    """
    runner = FakeRunner()
    ctx, _logger, _clock = make_ctx(runner, sysfs_root=tmp_path)
    _populate_sysfs(tmp_path)

    sleep_calls: list[float] = []

    async def recording_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    with patch("spark_modem.sysfs.usb_unbind_rebind.asyncio.sleep", recording_sleep):
        result = await usb_reset.execute(_who(), ctx)

    assert result.succeeded is True
    # One and only one sleep between unbind and bind.
    assert len(sleep_calls) == 1
    # Value matches the helper's default unless action overrides.
    assert sleep_calls[0] == 0.5
