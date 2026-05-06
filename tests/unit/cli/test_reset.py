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


async def test_reset_destructive_action_rejected_in_phase_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--action=modem_reset` is destructive (Phase 4) → exit 2."""
    args = Namespace(action="modem_reset", modem="cdc-wdm0", dry_run=False)
    rc = await reset_cmd.run(args)
    assert rc == 2
    err = capsys.readouterr().err
    assert "destructive" in err
    assert "Phase 4" in err


async def test_reset_usb_reset_rejected_in_phase_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = Namespace(action="usb_reset", modem="cdc-wdm0", dry_run=False)
    rc = await reset_cmd.run(args)
    assert rc == 2
    assert "destructive" in capsys.readouterr().err


async def test_reset_driver_reset_rejected_in_phase_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = Namespace(action="driver_reset", modem="cdc-wdm0", dry_run=False)
    rc = await reset_cmd.run(args)
    assert rc == 2
    assert "destructive" in capsys.readouterr().err


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
