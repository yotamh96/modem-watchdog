"""Unit tests for ZaoLogParser - the Phase 2 file-read RASCOW_STAT parser.

The Phase 2 parser walks the log file backwards to find the most recent
contiguous RASCOW_STAT block; observer/ in plan 02-04 calls
`zao.is_line_active(line_idx)` before QMI-probing each modem (FR-10).

These tests exercise the five fixture scenarios under
`tests/fixtures/zao_log/` plus the missing-file path and the runtime_checkable
Protocol surface (parser AND test fake satisfy ZaoLogTailer).
"""

from __future__ import annotations

from pathlib import Path

from spark_modem.zao_log.parser import ZaoLogParser
from spark_modem.zao_log.protocol import ZaoLogTailer
from spark_modem.zao_log.snapshot import ZaoSnapshot
from tests.fakes.zao_log import FixtureZaoTailer

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "zao_log"


def test_all_lines_active() -> None:
    """All four lines reported active in the latest block."""
    parser = ZaoLogParser(_FIXTURES / "all_lines_active.log")
    snap = parser.snapshot()
    assert snap.active_lines == frozenset({1, 2, 3, 4})
    assert snap.unknown_reason is None
    assert snap.last_block_iso == "2026-05-06T10:00:01+00:00"
    for line in (1, 2, 3, 4):
        assert parser.is_line_active(line) is True
    assert parser.is_line_active(5) is False


def test_two_lines_active() -> None:
    """Lines 1+3 active, lines 2+4 inactive."""
    parser = ZaoLogParser(_FIXTURES / "two_lines_active.log")
    snap = parser.snapshot()
    assert snap.active_lines == frozenset({1, 3})
    assert snap.unknown_reason is None
    assert parser.is_line_active(1) is True
    assert parser.is_line_active(2) is False
    assert parser.is_line_active(3) is True
    assert parser.is_line_active(4) is False


def test_no_lines_active() -> None:
    """Block exists; every status=inactive => empty active_lines."""
    parser = ZaoLogParser(_FIXTURES / "no_lines_active.log")
    snap = parser.snapshot()
    assert snap.active_lines == frozenset()
    assert snap.unknown_reason is None
    # The block was found, so last_block_iso is set even with no actives.
    assert snap.last_block_iso == "2026-05-06T10:02:00+00:00"
    assert parser.is_line_active(1) is False


def test_stale_returns_unknown() -> None:
    """File present but no RASCOW_STAT line => unknown(zao_log_no_rascow_stat)."""
    parser = ZaoLogParser(_FIXTURES / "stale.log")
    snap = parser.snapshot()
    assert snap.unknown_reason == "zao_log_no_rascow_stat"
    assert snap.active_lines == frozenset()
    assert snap.last_block_iso is None
    assert parser.is_line_active(1) is False


def test_missing_file_returns_unknown() -> None:
    """Missing file => unknown(zao_log_missing); never raises."""
    parser = ZaoLogParser(_FIXTURES / "does_not_exist.log")
    snap = parser.snapshot()
    assert snap.unknown_reason == "zao_log_missing"
    assert snap.active_lines == frozenset()
    assert parser.is_line_active(1) is False


def test_multiple_blocks_uses_last() -> None:
    """Two RASCOW blocks present; parser returns the LATER one (10:00:31)."""
    parser = ZaoLogParser(_FIXTURES / "multiple_blocks_use_last.log")
    snap = parser.snapshot()
    # Later block (10:00:31): line 1 inactive, 2 active, 3 active, 4 inactive.
    assert snap.active_lines == frozenset({2, 3})
    assert snap.unknown_reason is None
    assert snap.last_block_iso is not None
    assert snap.last_block_iso.startswith("2026-05-06T10:00:31")
    # Earlier block (10:00:00) had ALL lines active; verify we didn't pick that.
    assert snap.active_lines != frozenset({1, 2, 3, 4})


def test_protocol_satisfied_by_parser() -> None:
    """ZaoLogParser satisfies the runtime_checkable ZaoLogTailer Protocol."""
    parser = ZaoLogParser(Path("/tmp/x"))
    assert isinstance(parser, ZaoLogTailer)


def test_protocol_satisfied_by_fixture_tailer() -> None:
    """tests.fakes.zao_log.FixtureZaoTailer also satisfies the Protocol.

    Ensures observer/ in plan 02-04 can use the same call surface for
    production (ZaoLogParser) and tests (FixtureZaoTailer) without branching.
    """
    fake = FixtureZaoTailer(active_lines={1, 2})
    assert isinstance(fake, ZaoLogTailer)


def test_zao_snapshot_unknown_factory() -> None:
    """ZaoSnapshot.unknown(reason=...) constructs a do-not-gate snapshot."""
    snap = ZaoSnapshot.unknown(reason="x")
    assert snap.is_line_active(1) is False
    assert snap.unknown_reason == "x"
    assert snap.active_lines == frozenset()
    assert snap.last_block_iso is None
    assert snap.log_age_seconds is None
