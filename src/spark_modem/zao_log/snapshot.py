"""ZaoSnapshot - last RASCOW_STAT block as a frozen wire-style record.

ADR-0003: Zao's RASCOW_STAT log line is the AUTHORITATIVE source for
"is line N currently bonding?". The daemon never QMI-probes a line that
ZaoSnapshot.is_line_active(line) reports as True (FR-10).
"""

from __future__ import annotations

from pydantic import Field

from spark_modem.wire._base import BaseWire


class ZaoSnapshot(BaseWire):
    """Most recent RASCOW_STAT block parsed from the Zao log.

    ADR-0003: this is the authoritative source for "is line N bonding?".
    Daemon never QMI-probes a line where is_line_active(line) is True.
    """

    # Line indices currently reported as 'active' by Zao. Empty set means
    # no line is bonding under Zao (e.g. log fresh but Zao still booting).
    active_lines: frozenset[int] = Field(default_factory=frozenset)

    # ISO-8601 wall stamp of the parsed block; None when log empty/unknown.
    last_block_iso: str | None = None

    # Seconds between block timestamp and the moment we parsed it; None
    # when log empty/unknown. Computed by the parser using wall clock at
    # parse time (ADR-0007: ISO/wall arithmetic OK for diagnostics; durations
    # in policy/ use monotonic).
    log_age_seconds: float | None = None

    # Set when the log file is missing or unparseable. Observer treats
    # `unknown()` as "do not gate" (FR-10 honours Zao when known; Phase 3
    # adds inotify so 'unknown' becomes rare).
    unknown_reason: str | None = None

    def is_line_active(self, line_idx: int) -> bool:
        """FR-10 gate: True iff Zao is currently bonding this line."""
        return line_idx in self.active_lines

    @classmethod
    def unknown(cls, *, reason: str) -> ZaoSnapshot:
        """Construct an 'unknown' snapshot for missing/unparseable logs.

        Observer/ in plan 02-04 treats unknown_reason as a defensive signal:
        when set, the daemon should skip QMI probing rather than risk
        racing with Zao on an indeterminate-state line (T-02-03-04).
        """
        return cls(
            active_lines=frozenset(),
            last_block_iso=None,
            log_age_seconds=None,
            unknown_reason=reason,
        )
