"""Tests for actions.modem_reset -- ladder rung 2 destructive action.

Per CONTEXT A-01: modem_reset is a POLICY distinction, not a protocol
distinction. It issues the SAME ``--dms-set-operating-mode=reset`` qmicli
verb as soft_reset. The Phase 4 difference is engine-side: signal-gated
(gate_signal in Phase 4 wires from Settings), ladder rung 2 (vs rung 1),
and longer expected outage envelope (~30-60 s vs ~5 s).

The five paths covered here:

  1. Happy path -- argv shape + ActionResult.kind == MODEM_RESET.
  2. proxy_died classification -- failure_reason starts with ``modem_reset:``
     (NOT ``soft_reset:`` -- the prefix is the executed kind, not the
     QMI verb).
  3. timeout classification -- failure_reason == ``modem_reset:timeout``.
  4. verify() returns VerifyResult.deferred(detail="next_cycle_observation")
     unconditionally (A-04 -- modem is rebooting; in-line read-back impossible).
  5. Dispatcher registration -- ActionKind.MODEM_RESET appears in
     ``actions.dispatcher.registered_kinds()``.
"""

from __future__ import annotations

import pytest

from spark_modem.actions import dispatcher, modem_reset
from spark_modem.subproc.result import CompletedProcess
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind
from tests.fakes.runner import FakeRunner
from tests.unit.actions._helpers import base_argv, make_ctx, ok


def _who() -> WhoModem:
    return WhoModem(usb_path="2-3.1.1", cdc_wdm="cdc-wdm0")


def _argv() -> list[str]:
    # Same QMI verb as soft_reset -- A-01: policy distinction, not protocol.
    return [*base_argv(), "--dms-set-operating-mode=reset"]


@pytest.mark.asyncio
async def test_modem_reset_invokes_dms_set_operating_mode_reset() -> None:
    """Happy path: argv shape matches; ActionResult is succeeded MODEM_RESET."""
    runner = FakeRunner()
    runner.register(_argv(), ok(_argv()))
    ctx, _logger, _clock = make_ctx(runner)
    result = await modem_reset.execute(_who(), ctx)
    assert any(
        "--dms-set-operating-mode=reset" in arg for call in runner.calls for arg in call
    )
    assert result.kind == ActionKind.MODEM_RESET
    assert result.succeeded is True
    assert result.failure_reason is None
    assert result.dry_run is False


@pytest.mark.asyncio
async def test_modem_reset_classifies_proxy_died() -> None:
    """PROXY_DIED stderr -> failure_reason starts with 'modem_reset:'.

    Note the prefix is the EXECUTED kind (modem_reset), not the QMI verb
    or the analog action (soft_reset). This is what lets the policy engine
    and replay harness disambiguate the two ladder rungs from the failure
    record alone.
    """
    runner = FakeRunner()
    runner.register(
        _argv(),
        CompletedProcess.make(
            argv=_argv(),
            exit_code=1,
            stdout=b"",
            # Canonical libqmi proxy-died signature (PITFALLS §1.1) --
            # matches the same pattern QmiWrapper.classify shorts on.
            stderr=b"error: couldn't open the QMI device: Proxy unavailable",
            duration_monotonic=0.01,
            timed_out=False,
        ),
    )
    ctx, _logger, _clock = make_ctx(runner)
    result = await modem_reset.execute(_who(), ctx)
    assert result.succeeded is False
    assert result.failure_reason is not None
    assert result.failure_reason.startswith("modem_reset:")
    # Exact failure suffix is the QmiErrorReason.PROXY_DIED enum value.
    assert result.failure_reason == "modem_reset:proxy_died"


@pytest.mark.asyncio
async def test_modem_reset_classifies_timeout() -> None:
    """timed_out=True -> failure_reason == 'modem_reset:timeout'."""
    runner = FakeRunner()
    runner.register(
        _argv(),
        CompletedProcess.make(
            argv=_argv(),
            exit_code=124,
            stdout=b"",
            stderr=b"",
            duration_monotonic=15.0,
            timed_out=True,
        ),
    )
    ctx, _logger, _clock = make_ctx(runner)
    result = await modem_reset.execute(_who(), ctx)
    assert result.succeeded is False
    assert result.failure_reason == "modem_reset:timeout"


@pytest.mark.asyncio
async def test_modem_reset_verify_returns_deferred() -> None:
    """verify() does NO qmicli call -- returns deferred immediately (A-04)."""
    runner = FakeRunner()  # nothing registered; verify must not call run()
    ctx, _logger, _clock = make_ctx(runner)
    result = await modem_reset.verify(_who(), ctx)
    assert result.status == "deferred"
    assert result.detail == "next_cycle_observation"
    assert runner.calls == []


def test_modem_reset_registered_in_dispatcher() -> None:
    """Plan 04-01 unblocks MODEM_RESET in actions.dispatcher._REGISTRY."""
    assert ActionKind.MODEM_RESET in dispatcher.registered_kinds()
    assert dispatcher.is_registered(ActionKind.MODEM_RESET) is True
