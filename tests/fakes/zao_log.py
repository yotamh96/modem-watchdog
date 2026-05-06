"""FixtureZaoTailer -- canned ZaoLogTailer satisfier for Phase 2 tests.

Phase 2 ships a file-read fallback for the Zao log (RASCOW_STAT-only,
`spark_modem.zao_log.parser.ZaoLogParser`). Phase 3 swaps in an inotify-backed
implementation behind the same surface. Tests use this fixture tailer to
control which lines appear "active" without parsing real Zao log files.

Satisfies `spark_modem.zao_log.protocol.ZaoLogTailer` (is_line_active +
snapshot). The observer asks `zao.is_line_active(line_idx)` before
QMI-probing each line (ADR-0003 / FR-10). Returning True from this fake
represents Zao currently bonding that line; the observer must then skip
QMI probing.
"""

from __future__ import annotations

from spark_modem.zao_log.snapshot import ZaoSnapshot


class FixtureZaoTailer:
    """Returns canned is_line_active(line) answers from an in-memory set.

    Implements the ZaoLogTailer Protocol surface used by observer/ in
    plan 02-04 -- both `is_line_active(line)` and `snapshot()` are present
    so production code can swap ZaoLogParser <-> FixtureZaoTailer freely.
    """

    def __init__(self, *, active_lines: set[int] | None = None) -> None:
        self._active_lines: set[int] = set(active_lines) if active_lines is not None else set()

    def is_line_active(self, line_idx: int) -> bool:
        """Return True iff `line_idx` is in the configured active-line set."""
        return line_idx in self._active_lines

    def snapshot(self) -> ZaoSnapshot:
        """Return a synthetic ZaoSnapshot reflecting the configured active set.

        Mirrors the ZaoLogParser surface so observer/ can call either
        backend uniformly. Carries no last_block_iso / log_age_seconds --
        the fake is not parsing a real log -- but the active_lines set
        is the load-bearing field for the FR-10 gate.
        """
        return ZaoSnapshot(
            active_lines=frozenset(self._active_lines),
            last_block_iso=None,
            log_age_seconds=None,
            unknown_reason=None,
        )

    def set_active(self, lines: set[int]) -> None:
        """Replace the active-line set with `lines` (defensive copy)."""
        self._active_lines = set(lines)
