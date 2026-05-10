"""Property-test: each destructive action is genuinely re-runnable (FR-27 / SC#1).

Hypothesis-driven idempotency proof against fakes (FakeRunner +
``tmp_path`` sysfs_root). The HIL scenario
``tests/hil/scenarios/test_destructive_actions.py`` is the bench-Jetson
real-hardware counterpart; this file provides the fast property-test
feedback loop.

For each of ``modem_reset``, ``usb_reset``, and ``driver_reset``:

  Run ``execute(who, ctx)`` twice in a row against the SAME ActionContext.
  Assert:

    1. Both invocations return the same ``ActionKind`` (the executed kind).
    2. Both invocations return the same ``succeeded`` value (so the
       outcome is reproducible for downstream consumers).
    3. The second invocation is observable -- the underlying primitive
       (FakeRunner.calls / sysfs file content / fake_run accumulator) was
       exercised TWICE, never short-circuited.

The third assertion is what distinguishes "idempotent" (re-runnable, both
runs do the work, end-state identical) from "single-flight" (second run
returns immediately because the first one already happened). Per CONTEXT
A-05 verbatim: "back-to-back invocations both run; per-modem flock
serializes them; end-state is identical".

NOTE: ``driver_reset`` uses ``patch`` instead of FakeRunner because the
production code imports ``run`` from ``spark_modem.subproc.runner``
directly (ActionContext has no ``runner`` field; PATTERNS correction #1).
The ``test_driver_reset.py`` unit tests use the same patch shape.

Hypothesis adds confidence that the idempotency property holds for any
``usb_path`` / ``target`` permutation -- not just the canonical
``2-3.1.1 / cdc-wdm0`` happy-path the unit tests pin.
"""

from __future__ import annotations

import dataclasses
import errno
from pathlib import Path
from typing import Any, Literal, cast
from unittest.mock import patch

import hypothesis
import hypothesis.strategies as st
import pytest

from spark_modem.actions import driver_reset, modem_reset, usb_reset
from spark_modem.subproc.result import CompletedProcess
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind
from tests.fakes.runner import FakeRunner
from tests.unit.actions._helpers import base_argv, make_ctx, ok

# ----- modem_reset ------------------------------------------------------


def _modem_reset_argv() -> list[str]:
    """Same QMI verb as soft_reset (CONTEXT A-01: policy distinction)."""
    return [*base_argv(), "--dms-set-operating-mode=reset"]


@hypothesis.given(usb_leaf=st.integers(min_value=1, max_value=4))
@hypothesis.settings(max_examples=10, deadline=None)
async def test_modem_reset_back_to_back_idempotent(usb_leaf: int) -> None:
    """Two back-to-back ``modem_reset.execute(who, ctx)`` calls produce
    identical observable end-state. FakeRunner's argv->result map returns
    the same canned response for every call of the same argv, which is
    precisely the idempotent contract the bench Jetson exhibits (the
    second qmicli reset finds the modem already rebooting / online and
    returns the same ack).
    """
    runner = FakeRunner()
    runner.register(_modem_reset_argv(), ok(_modem_reset_argv()))
    ctx, _logger, _clock = make_ctx(runner)
    who = WhoModem(usb_path=f"2-3.1.{usb_leaf}", cdc_wdm="cdc-wdm0")

    r1 = await modem_reset.execute(who, ctx)
    r2 = await modem_reset.execute(who, ctx)

    assert r1.kind == r2.kind == ActionKind.MODEM_RESET
    assert r1.succeeded == r2.succeeded is True
    assert r1.failure_reason == r2.failure_reason is None
    # Idempotency-vs-single-flight discriminator: BOTH calls actually ran.
    assert len(runner.calls) == 2


# ----- usb_reset --------------------------------------------------------


def _populate_sysfs(tmp_path: Path) -> Path:
    drivers_usb = tmp_path / "bus" / "usb" / "drivers" / "usb"
    drivers_usb.mkdir(parents=True, exist_ok=True)
    (drivers_usb / "unbind").write_text("", encoding="ascii")
    (drivers_usb / "bind").write_text("", encoding="ascii")
    return drivers_usb


@hypothesis.given(
    usb_leaf=st.integers(min_value=1, max_value=4),
    target=st.sampled_from(["child-port", "parent-hub"]),
)
@hypothesis.settings(
    max_examples=8,
    deadline=None,
    # tmp_path is function-scoped; hypothesis warns it isn't reset between
    # generated examples. That's OK here -- the test OVERWRITES the
    # unbind/bind files on every run (idempotent at the file-I/O layer);
    # cross-example contamination is impossible because the second run's
    # writes are the same content as the first run's.
    suppress_health_check=[hypothesis.HealthCheck.function_scoped_fixture],
)
async def test_usb_reset_back_to_back_idempotent(
    usb_leaf: int, target: str, tmp_path: Path
) -> None:
    """Two back-to-back ``usb_reset.execute(who, ctx)`` calls produce
    identical observable end-state. The sysfs ``unbind``/``bind`` files
    end up with the SAME content after both runs (the second write
    overwrites the first to the same value -- idempotent at the file-I/O
    layer).
    """
    runner = FakeRunner()
    base_ctx, _logger, _clock = make_ctx(runner, sysfs_root=tmp_path)
    # Cast: hypothesis.strategies.sampled_from(list[str]) widens to str;
    # ActionContext.target is Literal["child-port", "parent-hub"]. The
    # strategy bounds guarantee runtime safety.
    ctx = dataclasses.replace(base_ctx, target=cast(Literal["child-port", "parent-hub"], target))
    drivers_usb = _populate_sysfs(tmp_path)
    who = WhoModem(usb_path=f"2-3.1.{usb_leaf}", cdc_wdm="cdc-wdm0")

    async def no_sleep(_seconds: float) -> None:
        return None

    with patch("spark_modem.sysfs.usb_unbind_rebind.asyncio.sleep", no_sleep):
        r1 = await usb_reset.execute(who, ctx)
        r2 = await usb_reset.execute(who, ctx)

    assert r1.kind == r2.kind == ActionKind.USB_RESET
    assert r1.succeeded == r2.succeeded is True
    assert r1.failure_reason == r2.failure_reason is None
    # End-state identical: the sysfs files contain the expected bus-port
    # path string regardless of how many runs preceded the read.
    expected = (
        f"2-3.1.{usb_leaf}"
        if target == "child-port"
        else "2-3.1"  # parent-hub strips the leaf segment
    )
    assert (drivers_usb / "unbind").read_text(encoding="ascii") == expected
    assert (drivers_usb / "bind").read_text(encoding="ascii") == expected


@hypothesis.given(usb_leaf=st.integers(min_value=1, max_value=4))
@hypothesis.settings(
    max_examples=8,
    deadline=None,
    suppress_health_check=[hypothesis.HealthCheck.function_scoped_fixture],
)
async def test_usb_reset_failure_is_idempotent_too(usb_leaf: int, tmp_path: Path) -> None:
    """When the sysfs primitive errors (ENOENT here -- unbind file
    missing), BOTH back-to-back runs return the SAME failure shape.
    Idempotency of failure cases matters because the policy engine's
    ladder progression keys off the failure_reason prefix.
    """
    runner = FakeRunner()
    ctx, _logger, _clock = make_ctx(runner, sysfs_root=tmp_path)
    # Deliberately NOT calling _populate_sysfs -- ENOENT path.
    who = WhoModem(usb_path=f"2-3.1.{usb_leaf}", cdc_wdm="cdc-wdm0")

    r1 = await usb_reset.execute(who, ctx)
    r2 = await usb_reset.execute(who, ctx)

    assert r1.kind == r2.kind == ActionKind.USB_RESET
    assert r1.succeeded == r2.succeeded is False
    assert r1.failure_reason == r2.failure_reason
    assert r1.failure_reason is not None
    assert r1.failure_reason.startswith("usb_reset:sysfs_write_error:")
    assert r1.failure_reason.endswith(f":{errno.ENOENT}")  # ":2"


# ----- driver_reset -----------------------------------------------------


_UNLOAD_ARGV = ["modprobe", "-r", "qmi_wwan"]
_LOAD_ARGV = ["modprobe", "qmi_wwan"]


def _ok_cp(argv: list[str]) -> CompletedProcess:
    return CompletedProcess.make(
        argv=argv,
        exit_code=0,
        stdout=b"",
        stderr=b"",
        duration_monotonic=0.01,
        timed_out=False,
    )


@hypothesis.given(usb_leaf=st.integers(min_value=1, max_value=4))
@hypothesis.settings(max_examples=8, deadline=None)
async def test_driver_reset_back_to_back_idempotent(usb_leaf: int) -> None:
    """Two back-to-back ``driver_reset.execute(who, ctx)`` calls produce
    identical observable end-state. ``driver_reset`` is host-scoped (not
    per-modem); the synthetic WhoModem placeholder per PATTERNS X-#10
    just carries through to ActionResult.who.

    Per A-05: ``modprobe -r qmi_wwan`` then ``modprobe qmi_wwan`` on the
    second run finds the module already removed-then-loaded, so the
    primitive is a no-op the second time. The action's overall outcome
    (succeeded=True, failure_reason=None) MUST match between runs.
    """
    ctx, _logger, _clock = make_ctx(FakeRunner())
    who = WhoModem(usb_path=f"2-3.1.{usb_leaf}", cdc_wdm="cdc-wdm0")
    calls: list[list[str]] = []

    async def fake_run(argv: list[str], **kwargs: Any) -> CompletedProcess:
        del kwargs
        calls.append(list(argv))
        return _ok_cp(argv)

    with patch("spark_modem.actions.driver_reset.subproc_run", fake_run):
        r1 = await driver_reset.execute(who, ctx)
        r2 = await driver_reset.execute(who, ctx)

    assert r1.kind == r2.kind == ActionKind.DRIVER_RESET
    assert r1.succeeded == r2.succeeded is True
    assert r1.failure_reason == r2.failure_reason is None
    # Idempotency-vs-single-flight discriminator: 4 modprobe calls total
    # (2 unload + 2 load), in strict alternation.
    assert calls == [_UNLOAD_ARGV, _LOAD_ARGV, _UNLOAD_ARGV, _LOAD_ARGV]


@pytest.mark.asyncio
async def test_driver_reset_module_in_use_failure_is_idempotent() -> None:
    """When unload reports 'in use', BOTH back-to-back runs return the
    same canonical ``driver_reset:module_in_use`` failure_reason. The
    policy engine's ladder reads this prefix verbatim.
    """
    ctx, _logger, _clock = make_ctx(FakeRunner())
    who = WhoModem(usb_path="2-3.1.1", cdc_wdm="cdc-wdm0")

    async def fake_run(argv: list[str], **kwargs: Any) -> CompletedProcess:
        del kwargs
        if argv == _UNLOAD_ARGV:
            return CompletedProcess.make(
                argv=argv,
                exit_code=1,
                stdout=b"",
                stderr=b"modprobe: ERROR: Module qmi_wwan is in use.\n",
                duration_monotonic=0.01,
                timed_out=False,
            )
        return _ok_cp(argv)

    with patch("spark_modem.actions.driver_reset.subproc_run", fake_run):
        r1 = await driver_reset.execute(who, ctx)
        r2 = await driver_reset.execute(who, ctx)

    assert r1.failure_reason == r2.failure_reason == "driver_reset:module_in_use"
    assert r1.succeeded == r2.succeeded is False
