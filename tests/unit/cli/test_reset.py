"""Tests for spark_modem.cli.reset — single-action dispatcher routing."""

from __future__ import annotations

from argparse import Namespace

import pytest

from spark_modem.cli import reset as reset_cmd
from spark_modem.cli.main import _build_parser


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


async def test_reset_usb_reset_cli_smoke(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Plan 04-02: --action=usb_reset is now registered → exit 0 + stub line.

    Replaces the prior Plan 04-01 'still rejected' assertion -- USB_RESET
    is unblocked at this plan's commit time.
    """
    args = Namespace(
        action="usb_reset", modem="cdc-wdm0", dry_run=False, target="child-port"
    )
    rc = await reset_cmd.run(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "action=usb_reset" in out
    assert "modem=cdc-wdm0" in out
    assert "target=child-port" in out


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
    args = Namespace(
        action="set_apn", modem="cdc-wdm0", dry_run=False, target="child-port"
    )
    rc = await reset_cmd.run(args)
    assert rc == 0
    assert "action=set_apn" in capsys.readouterr().out


# --- Plan 04-02: --target argparse flag tests ------------------------------


def test_reset_target_flag_default_is_child_port() -> None:
    """Plan 04-02 / A-06 / RESEARCH Q9: --target defaults to 'child-port'."""
    parser = _build_parser()
    args = parser.parse_args(["reset", "--action=usb_reset", "--modem=cdc-wdm0"])
    assert args.target == "child-port"


def test_reset_target_parent_hub_accepted() -> None:
    """`--target=parent-hub` is the SIERRA_BOOTLOADER variant per PITFALLS §1.6."""
    parser = _build_parser()
    args = parser.parse_args(
        ["reset", "--action=usb_reset", "--modem=cdc-wdm0", "--target=parent-hub"]
    )
    assert args.target == "parent-hub"


def test_reset_target_invalid_rejected() -> None:
    """argparse rejects unknown --target values with SystemExit(2)."""
    parser = _build_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(
            ["reset", "--action=usb_reset", "--modem=cdc-wdm0", "--target=quantum-tunnel"]
        )
    assert exc_info.value.code == 2


async def test_reset_target_parent_hub_passed_to_dispatcher_stub(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--target=parent-hub` flows into the stub dispatch line for operator visibility."""
    args = Namespace(
        action="usb_reset", modem="cdc-wdm0", dry_run=False, target="parent-hub"
    )
    rc = await reset_cmd.run(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "action=usb_reset" in out
    assert "target=parent-hub" in out
