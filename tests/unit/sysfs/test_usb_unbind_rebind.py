"""Tests for ``spark_modem.sysfs.usb_unbind_rebind`` and the ActionContext.target field.

Plan 04-02 Task 1 RED gate.

Per CONTEXT A-02 / A-06 / PITFALLS §1.6:
  - child-port (default): the modem's leaf bus-port path (e.g. ``"2-3.1.1"``)
    is written verbatim to ``/sys/bus/usb/drivers/usb/{unbind,bind}``.
  - parent-hub: the parent hub bus-port path (``"2-3.1"``, computed via
    ``usb_path.rsplit('.', 1)[0]``) is written instead. Re-fires the
    Sierra EM7421 boot transition for IssueDetail.SIERRA_BOOTLOADER.

The 6 sysfs-helper tests + 2 ActionContext-default tests live together for
cohesion -- there is no tests/unit/actions/test_context.py to host the
ActionContext defaults today, and the sysfs root + target field are
introduced together in this plan.
"""

from __future__ import annotations

import errno
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from spark_modem.actions.context import ActionContext
from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.sysfs import unbind_rebind
from tests.fakes.clock import FakeClock
from tests.fakes.runner import FakeRunner
from tests.unit.actions._helpers import (
    RecordingEventLogger,
    make_carrier_table,
    make_settings,
)


def _populate_sysfs(tmp_path: Path) -> tuple[Path, Path]:
    """Pre-create ``<tmp>/bus/usb/drivers/usb/{unbind,bind}`` empty files."""
    drivers_usb = tmp_path / "bus" / "usb" / "drivers" / "usb"
    drivers_usb.mkdir(parents=True, exist_ok=True)
    unbind = drivers_usb / "unbind"
    bind = drivers_usb / "bind"
    unbind.write_text("", encoding="ascii")
    bind.write_text("", encoding="ascii")
    return unbind, bind


@pytest.mark.asyncio
async def test_unbind_rebind_writes_usb_path_to_unbind_then_bind_child_port(
    tmp_path: Path,
) -> None:
    """child-port (default) writes the leaf usb_path to BOTH unbind and bind."""
    unbind, bind = _populate_sysfs(tmp_path)

    await unbind_rebind(
        "2-3.1.1",
        target="child-port",
        sysfs_root=tmp_path,
        rebind_delay_seconds=0.0,
    )

    assert unbind.read_text(encoding="ascii") == "2-3.1.1"
    assert bind.read_text(encoding="ascii") == "2-3.1.1"


@pytest.mark.asyncio
async def test_unbind_rebind_parent_hub_strips_leaf_segment(tmp_path: Path) -> None:
    """parent-hub variant writes ``usb_path.rsplit('.', 1)[0]`` (the parent hub)."""
    unbind, bind = _populate_sysfs(tmp_path)

    await unbind_rebind(
        "2-3.1.1",
        target="parent-hub",
        sysfs_root=tmp_path,
        rebind_delay_seconds=0.0,
    )

    assert unbind.read_text(encoding="ascii") == "2-3.1"
    assert bind.read_text(encoding="ascii") == "2-3.1"


@pytest.mark.asyncio
async def test_unbind_rebind_sleeps_between_writes(tmp_path: Path) -> None:
    """``asyncio.sleep`` is awaited exactly once between unbind and bind.

    Records call order via a side-effect monkey-patched onto Path.write_text
    so we can assert ordering: write(unbind) -> sleep -> write(bind).
    """
    _populate_sysfs(tmp_path)

    call_order: list[tuple[str, Any]] = []
    sleep_args: list[float] = []

    real_write_text = Path.write_text

    def recording_write_text(self: Path, *args: Any, **kwargs: Any) -> int:
        call_order.append(("write", self.name))
        return real_write_text(self, *args, **kwargs)

    async def recording_sleep(seconds: float) -> None:
        call_order.append(("sleep", seconds))
        sleep_args.append(seconds)

    with (
        patch.object(Path, "write_text", recording_write_text),
        patch("spark_modem.sysfs.usb_unbind_rebind.asyncio.sleep", recording_sleep),
    ):
        await unbind_rebind(
            "2-3.1.1",
            target="child-port",
            sysfs_root=tmp_path,
            rebind_delay_seconds=0.5,
        )

    # Filter to only events from the helper (write_text on unbind/bind +
    # the asyncio.sleep). Other tmp_path setup writes happen BEFORE the
    # patches are applied so they do not appear here.
    relevant = [evt for evt in call_order if evt[0] != "write" or evt[1] in ("unbind", "bind")]
    assert relevant == [
        ("write", "unbind"),
        ("sleep", 0.5),
        ("write", "bind"),
    ]
    assert sleep_args == [0.5]


@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX-only default-path semantics (/sys absent)"
)
@pytest.mark.asyncio
async def test_unbind_rebind_default_sysfs_root_is_slash_sys() -> None:
    """Default sysfs_root is /sys.

    On the dev laptop / non-root POSIX host, writing to
    /sys/bus/usb/drivers/usb/unbind is rejected with OSError (EACCES /
    EPERM / ENOENT depending on host). We assert the OSError type, NOT a
    successful write -- this proves the default is /sys and not silently
    swallowed.
    """
    with pytest.raises(OSError):
        await unbind_rebind(
            "2-3.1.1",
            target="child-port",
            rebind_delay_seconds=0.0,
        )


@pytest.mark.asyncio
async def test_unbind_rebind_raises_oserror_on_unbind_failure(tmp_path: Path) -> None:
    """No pre-created unbind file -> FileNotFoundError propagates to caller."""
    # Don't pre-create -- bus/usb/drivers/usb/unbind is missing entirely.
    with pytest.raises(OSError) as exc_info:
        await unbind_rebind(
            "2-3.1.1",
            target="child-port",
            sysfs_root=tmp_path,
            rebind_delay_seconds=0.0,
        )
    # FileNotFoundError is a subclass of OSError with errno=ENOENT.
    assert exc_info.value.errno == errno.ENOENT


@pytest.mark.asyncio
async def test_unbind_rebind_raises_oserror_on_bind_failure(tmp_path: Path) -> None:
    """Bind write fails -> OSError propagates (simulating kernel EBUSY).

    On a real /sys, the bind / unbind files are kernel-special; writing
    to them returns EBUSY / ENODEV / EACCES depending on state. tmp_path
    cannot replicate that semantic via a missing file (Path.write_text
    creates the file on demand for regular files), so we monkey-patch
    ``Path.write_text`` to raise OSError(EBUSY) on the bind path only.
    The unbind path's write succeeds; the bind path's write trips.
    """
    drivers_usb = tmp_path / "bus" / "usb" / "drivers" / "usb"
    drivers_usb.mkdir(parents=True, exist_ok=True)
    (drivers_usb / "unbind").write_text("", encoding="ascii")
    (drivers_usb / "bind").write_text("", encoding="ascii")

    real_write_text = Path.write_text

    def selective_write_text(self: Path, *args: Any, **kwargs: Any) -> int:
        if self.name == "bind":
            raise OSError(errno.EBUSY, "Device or resource busy")
        return real_write_text(self, *args, **kwargs)

    with (
        patch.object(Path, "write_text", selective_write_text),
        pytest.raises(OSError) as exc_info,
    ):
        await unbind_rebind(
            "2-3.1.1",
            target="child-port",
            sysfs_root=tmp_path,
            rebind_delay_seconds=0.0,
        )
    assert exc_info.value.errno == errno.EBUSY
    # The unbind side DID succeed (proves the helper got past the unbind
    # write before tripping on bind).
    assert (drivers_usb / "unbind").read_text(encoding="ascii") == "2-3.1.1"


# --- ActionContext.target field tests --------------------------------------


def _make_ctx(target: str | None = None) -> ActionContext:
    runner = FakeRunner()
    qmi = QmiWrapper(runner=runner, device="/dev/cdc-wdm0")
    kwargs: dict[str, Any] = {
        "qmi": qmi,
        "clock": FakeClock(),
        "config": make_settings(),
        "carrier_table": make_carrier_table(),
        "event_logger": RecordingEventLogger(),
    }
    if target is not None:
        kwargs["target"] = target
    return ActionContext(**kwargs)


def test_action_context_default_target_is_child_port() -> None:
    """ActionContext constructed without ``target`` defaults to ``"child-port"``."""
    ctx = _make_ctx()
    assert ctx.target == "child-port"


def test_action_context_target_can_be_parent_hub() -> None:
    """ActionContext accepts ``target="parent-hub"`` for the SIERRA_BOOTLOADER variant."""
    ctx = _make_ctx(target="parent-hub")
    assert ctx.target == "parent-hub"
