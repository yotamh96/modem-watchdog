"""Tests for actions.driver_reset -- destructive driver unload+reload via modprobe.

Plan 04-03 Task 2.

Per CONTEXT A-03 and PATTERNS correction #1:
  - driver_reset issues TWO subproc.run calls in sequence:
    ["modprobe", "-r", "qmi_wwan"] then ["modprobe", "qmi_wwan"].
  - The action imports `run` from `spark_modem.subproc.runner` directly --
    ActionContext does NOT have a `runner` field.
  - Two-stage stderr classifier (PITFALLS §1.1, kmod tools/modprobe.c):
      * "in use" -> failure_reason "driver_reset:module_in_use" without
        attempting load (skips the load entirely; future cycles re-fire).
      * "not found" / other unload non-zero -> proceed to load (idempotency,
        per A-05; second run finds module already removed, safe to load).
      * load non-zero -> failure_reason "driver_reset:load_exit_<code>".
  - verify() returns VerifyResult.deferred(detail="next_cycle_observation").
  - WhoModem(usb_path="host", cdc_wdm=None) -- driver_reset is host-scoped;
    PATTERNS Cross-Cutting #10 prescribes a synthetic WhoModem placeholder
    for the dispatcher signature.

The 7 paths covered here:
  1. Happy path -- both modprobe calls succeed, ActionResult.succeeded=True;
     argv ordering captured (unload before load).
  2. Unload "in use" -> module_in_use failure; load NOT attempted.
  3. Unload "not found" (idempotent re-run) -> proceeds to load; success.
  4. Load fails (exit 2) -> driver_reset:load_exit_2.
  5. Both calls use ctx.config.modprobe_timeout_seconds (default 30).
  6. verify() returns deferred(detail="next_cycle_observation").
  7. ActionResult.who carries the synthetic host placeholder unchanged.

The dispatcher contract test rename (_eight_kinds -> _nine_kinds) lives in
test_dispatcher.py; the partial-registration test rename + DRIVER_RESET flip
also lives there.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from spark_modem.actions import dispatcher, driver_reset
from spark_modem.subproc.result import CompletedProcess
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind
from tests.fakes.runner import FakeRunner
from tests.unit.actions._helpers import make_ctx


def _host_who() -> WhoModem:
    """Synthetic host placeholder for the host-scoped action (PATTERNS X-#10)."""
    return WhoModem(usb_path="host", cdc_wdm=None)


_UNLOAD = ["modprobe", "-r", "qmi_wwan"]
_LOAD = ["modprobe", "qmi_wwan"]


def _ok(argv: list[str]) -> CompletedProcess:
    return CompletedProcess.make(
        argv=argv,
        exit_code=0,
        stdout=b"",
        stderr=b"",
        duration_monotonic=0.01,
        timed_out=False,
    )


def _fail(argv: list[str], *, exit_code: int, stderr: bytes) -> CompletedProcess:
    return CompletedProcess.make(
        argv=argv,
        exit_code=exit_code,
        stdout=b"",
        stderr=stderr,
        duration_monotonic=0.01,
        timed_out=False,
    )


@pytest.mark.asyncio
async def test_driver_reset_invokes_modprobe_remove_then_load() -> None:
    """Happy path: unload then load; both succeed; argv order preserved."""
    ctx, _logger, _clock = make_ctx(FakeRunner())
    calls: list[tuple[list[str], dict[str, Any]]] = []

    async def fake_run(argv: list[str], **kwargs: Any) -> CompletedProcess:
        calls.append((list(argv), dict(kwargs)))
        return _ok(argv)

    with patch("spark_modem.actions.driver_reset.subproc_run", fake_run):
        result = await driver_reset.execute(_host_who(), ctx)

    assert result.kind == ActionKind.DRIVER_RESET
    assert result.succeeded is True
    assert result.failure_reason is None
    assert result.dry_run is False
    # Argv ordering: unload BEFORE load.
    assert [c[0] for c in calls] == [_UNLOAD, _LOAD]


@pytest.mark.asyncio
async def test_driver_reset_returns_module_in_use_on_unload_in_use() -> None:
    """Unload stderr contains 'in use' -> module_in_use; load NOT attempted."""
    ctx, _logger, _clock = make_ctx(FakeRunner())
    calls: list[list[str]] = []

    async def fake_run(argv: list[str], **kwargs: Any) -> CompletedProcess:
        calls.append(list(argv))
        if argv == _UNLOAD:
            return _fail(
                argv,
                exit_code=1,
                stderr=b"modprobe: ERROR: Module qmi_wwan is in use.\n",
            )
        return _ok(argv)

    with patch("spark_modem.actions.driver_reset.subproc_run", fake_run):
        result = await driver_reset.execute(_host_who(), ctx)

    assert result.succeeded is False
    assert result.failure_reason == "driver_reset:module_in_use"
    # Load must NOT have been attempted.
    assert calls == [_UNLOAD]


@pytest.mark.asyncio
async def test_driver_reset_proceeds_to_load_on_unload_module_not_found() -> None:
    """Unload 'not found' (already-removed) -> proceed to load; overall success."""
    ctx, _logger, _clock = make_ctx(FakeRunner())
    calls: list[list[str]] = []

    async def fake_run(argv: list[str], **kwargs: Any) -> CompletedProcess:
        calls.append(list(argv))
        if argv == _UNLOAD:
            return _fail(
                argv,
                exit_code=1,
                stderr=b"modprobe: FATAL: Module qmi_wwan not found.\n",
            )
        return _ok(argv)

    with patch("spark_modem.actions.driver_reset.subproc_run", fake_run):
        result = await driver_reset.execute(_host_who(), ctx)

    # Idempotent: the second invocation found the module already removed,
    # so the load proceeds and the action overall succeeds.
    assert result.succeeded is True
    assert result.failure_reason is None
    assert calls == [_UNLOAD, _LOAD]


@pytest.mark.asyncio
async def test_driver_reset_returns_load_failure_on_load_exit_nonzero() -> None:
    """Unload OK, load returns non-zero exit -> driver_reset:load_exit_<code>."""
    ctx, _logger, _clock = make_ctx(FakeRunner())

    async def fake_run(argv: list[str], **kwargs: Any) -> CompletedProcess:
        if argv == _UNLOAD:
            return _ok(argv)
        return _fail(argv, exit_code=2, stderr=b"some error")

    with patch("spark_modem.actions.driver_reset.subproc_run", fake_run):
        result = await driver_reset.execute(_host_who(), ctx)

    assert result.succeeded is False
    assert result.failure_reason == "driver_reset:load_exit_2"


@pytest.mark.asyncio
async def test_driver_reset_uses_modprobe_timeout_from_settings() -> None:
    """Both subproc.run calls receive timeout_s = ctx.config.modprobe_timeout_seconds."""
    ctx, _logger, _clock = make_ctx(FakeRunner())
    timeouts: list[float] = []

    async def fake_run(argv: list[str], **kwargs: Any) -> CompletedProcess:
        timeouts.append(kwargs["timeout_s"])
        return _ok(argv)

    with patch("spark_modem.actions.driver_reset.subproc_run", fake_run):
        await driver_reset.execute(_host_who(), ctx)

    expected = float(ctx.config.modprobe_timeout_seconds)
    assert expected == 30.0  # default sanity
    assert timeouts == [expected, expected]


@pytest.mark.asyncio
async def test_driver_reset_verify_is_deferred() -> None:
    """verify() returns VerifyResult.deferred(detail='next_cycle_observation')."""
    ctx, _logger, _clock = make_ctx(FakeRunner())

    result = await driver_reset.verify(_host_who(), ctx)

    assert result.status == "deferred"
    assert result.detail == "next_cycle_observation"


@pytest.mark.asyncio
async def test_driver_reset_uses_synthetic_whomodem_for_host_action() -> None:
    """Result.who carries the host placeholder (usb_path='host', cdc_wdm=None)."""
    ctx, _logger, _clock = make_ctx(FakeRunner())

    async def fake_run(argv: list[str], **kwargs: Any) -> CompletedProcess:
        return _ok(argv)

    who = _host_who()
    with patch("spark_modem.actions.driver_reset.subproc_run", fake_run):
        result = await driver_reset.execute(who, ctx)

    assert result.who.usb_path == "host"
    assert result.who.cdc_wdm is None


def test_driver_reset_registered_in_dispatcher() -> None:
    """Plan 04-03 unblocks DRIVER_RESET in actions.dispatcher._REGISTRY."""
    assert ActionKind.DRIVER_RESET in dispatcher.registered_kinds()
    assert dispatcher.is_registered(ActionKind.DRIVER_RESET) is True
