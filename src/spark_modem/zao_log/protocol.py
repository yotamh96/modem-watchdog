"""ZaoLogTailer - observer-facing seam for FR-10 gating.

Phase 2 implementation: ZaoLogParser (file-read fallback in parser.py).
Phase 3 implementation: inotify-backed ZaoLogInotifyTailer.
Both satisfy this Protocol; observer/ never changes.

The test fake `tests.fakes.zao_log.FixtureZaoTailer` also satisfies this
Protocol (verified via runtime_checkable isinstance assertions in
tests/unit/zao_log/test_parser.py).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from spark_modem.zao_log.snapshot import ZaoSnapshot


@runtime_checkable
class ZaoLogTailer(Protocol):
    """Surface the observer (plan 02-04) consumes for the FR-10 gate."""

    def is_line_active(self, line_idx: int) -> bool:
        """Return True iff Zao is currently bonding `line_idx`."""
        ...

    def snapshot(self) -> ZaoSnapshot:
        """Return the most recent parsed RASCOW_STAT block (or unknown)."""
        ...
