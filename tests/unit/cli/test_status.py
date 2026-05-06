"""Tests for spark_modem.cli.status — read status.json and re-validate it."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from spark_modem.cli import status as status_cmd
from spark_modem.wire.status import (
    StatusCycleSummary,
    StatusModemSummary,
    StatusReport,
)


async def test_status_missing_file_returns_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Missing status.json → exit 2 with stderr message."""
    args = Namespace(state_root=str(tmp_path))
    rc = await status_cmd.run(args)
    assert rc == 2
    assert "does not exist" in capsys.readouterr().err


async def test_status_prints_valid_status_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Valid status.json round-trips through StatusReport and prints indented JSON."""
    report = StatusReport(
        last_modified="2026-05-06T00:00:00+00:00",
        cycle_index=42,
        cycle=StatusCycleSummary(n=42, duration_seconds=1.5, next_at_iso=None),
        summary=StatusModemSummary(expected_modems=4, healthy=4),
        modems=[],
    )
    target = tmp_path / "status.json"
    target.write_bytes(report.model_dump_json(by_alias=True).encode("utf-8"))

    args = Namespace(state_root=str(tmp_path))
    rc = await status_cmd.run(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert '"cycle_index": 42' in out


async def test_status_corrupt_file_returns_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Unparseable status.json → exit 2."""
    target = tmp_path / "status.json"
    target.write_bytes(b"{not valid json")
    args = Namespace(state_root=str(tmp_path))
    rc = await status_cmd.run(args)
    assert rc == 2
    assert "failed to parse" in capsys.readouterr().err
