"""Tests for spark_modem.cli.reset — single-action dispatcher routing."""

from __future__ import annotations

from argparse import Namespace

import pytest

from spark_modem.cli import reset as reset_cmd


async def test_reset_unknown_action_returns_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Unknown action kind → exit 2 with the valid Phase-2 list in stderr."""
    args = Namespace(action="bogus_action", modem="cdc-wdm0", dry_run=False)
    rc = await reset_cmd.run(args)
    assert rc == 2
    err = capsys.readouterr().err
    assert "unknown action" in err
    # All six Phase-2 cheap actions appear in the suggestion list.
    for valid in ("set_apn", "fix_raw_ip", "sim_power_on", "soft_reset"):
        assert valid in err


async def test_reset_unknown_action_still_rejected(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Regression: argparse-level unknown action still returns 2.

    This covers the OTHER rejection branch (the ActionKind() ValueError
    catch), distinct from the is_registered() guard. Plan 04-01 only
    rewrites the latter; the former must continue to fire on truly-unknown
    kinds.
    """
    args = Namespace(action="quantum_tunnel", modem="cdc-wdm0", dry_run=False)
    rc = await reset_cmd.run(args)
    assert rc == 2
    err = capsys.readouterr().err
    assert "unknown action" in err


async def test_reset_modem_reset_cli_smoke(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Plan 04-01: --action=modem_reset is now registered → exit 0 + stub line."""
    args = Namespace(action="modem_reset", modem="cdc-wdm0", dry_run=False)
    rc = await reset_cmd.run(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "action=modem_reset" in out
    assert "modem=cdc-wdm0" in out


async def test_reset_usb_reset_still_rejected(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Plan 04-02 lands USB_RESET; until then the new 'is not registered'
    branch fires on this kind."""
    args = Namespace(action="usb_reset", modem="cdc-wdm0", dry_run=False)
    rc = await reset_cmd.run(args)
    assert rc == 2
    err = capsys.readouterr().err
    assert "is not registered" in err
    assert "usb_reset" in err


async def test_reset_driver_reset_still_rejected(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Plan 04-03 lands DRIVER_RESET; until then the new 'is not registered'
    branch fires on this kind."""
    args = Namespace(action="driver_reset", modem="cdc-wdm0", dry_run=False)
    rc = await reset_cmd.run(args)
    assert rc == 2
    err = capsys.readouterr().err
    assert "is not registered" in err
    assert "driver_reset" in err


async def test_reset_cheap_action_dispatch_stub_message(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--action=soft_reset` is registered → exit 0 with a stub success message."""
    args = Namespace(action="soft_reset", modem="cdc-wdm0", dry_run=True)
    rc = await reset_cmd.run(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "action=soft_reset" in out
    assert "modem=cdc-wdm0" in out
    assert "dry_run=True" in out


async def test_reset_set_apn_dispatch_stub_message(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = Namespace(action="set_apn", modem="cdc-wdm0", dry_run=False)
    rc = await reset_cmd.run(args)
    assert rc == 0
    assert "action=set_apn" in capsys.readouterr().out
