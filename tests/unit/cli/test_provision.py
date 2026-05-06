"""Tests for spark_modem.cli.provision — Phase-2 stub."""

from __future__ import annotations

from argparse import Namespace

import pytest

from spark_modem.cli import provision as provision_cmd


async def test_provision_print_phase2_stub_message(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Phase 2 returns 0 with a clear stub message naming the device + apn."""
    args = Namespace(device="cdc-wdm0", apn="internet", dry_run=False)
    rc = await provision_cmd.run(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "production runner not wired in Phase 2" in out
    assert "device=cdc-wdm0" in out
    assert "apn=internet" in out
