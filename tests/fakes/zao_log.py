"""FixtureZaoTailer -- canned is_line_active answers for Phase 2 tests.

Phase 2 ships a file-read fallback for the Zao log (RASCOW_STAT-only). Phase 3
swaps in an inotify-backed implementation behind the same surface. Tests use
this fixture tailer to control which lines appear "active" without parsing
real Zao log files.

The observer asks `zao.is_line_active(line_idx)` before QMI-probing each line
(ADR-0003 / FR-10). Returning True from this fake represents Zao currently
bonding that line; the observer must then skip QMI probing.
"""

from __future__ import annotations


class FixtureZaoTailer:
    """Returns canned is_line_active(line) answers from an in-memory set."""

    def __init__(self, *, active_lines: set[int] | None = None) -> None:
        self._active_lines: set[int] = set(active_lines) if active_lines is not None else set()

    def is_line_active(self, line_idx: int) -> bool:
        """Return True iff `line_idx` is in the configured active-line set."""
        return line_idx in self._active_lines

    def set_active(self, lines: set[int]) -> None:
        """Replace the active-line set with `lines` (defensive copy)."""
        self._active_lines = set(lines)
