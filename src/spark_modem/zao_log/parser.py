"""ZaoLogParser - Phase 2 file-read implementation of ZaoLogTailer.

Walks the log file backwards to find the most recent contiguous RASCOW_STAT
block. Phase 3's inotify implementation accumulates lines incrementally
and exposes the same Protocol surface (`zao_log.protocol.ZaoLogTailer`);
observer/ never branches on the backend.

The Phase 2 cycle cost is bounded by logrotate (FR-43): the production log
is rotated daily and capped at 100 MiB, so reading the entire file once per
cycle is acceptable. Phase 3's incremental reader replaces this on Linux.

Threat model (T-02-03-01..04):
  - Untrusted text crosses Zao->parser. ascii decode with errors="replace"
    plus a strict regex tolerates malformed lines without raising.
  - Missing/unparseable file -> ZaoSnapshot.unknown(reason=<canonical>).
  - unknown_reason carries only canonical strings, never raw log content
    (T-02-03-03).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from spark_modem.zao_log.snapshot import ZaoSnapshot

# Regex captures the ISO-8601 timestamp prefix and the line=N status=K fields.
# Tolerates the optional fractional-second suffix and either Z or +HH:MM TZ.
_RASCOW_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z))"
    r".*RASCOW_STAT.*\bline=(?P<line>\d+)\b.*\bstatus=(?P<status>\w+)\b"
)


class ZaoLogParser:
    """Reads the entire Zao log on demand and returns the latest block.

    Satisfies `spark_modem.zao_log.protocol.ZaoLogTailer`. Phase 2 file-read
    fallback; Phase 3 swaps in an inotify-backed tailer behind the same
    Protocol surface.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def is_line_active(self, line_idx: int) -> bool:
        """FR-10 gate: True iff Zao is currently bonding `line_idx`."""
        return self.snapshot().is_line_active(line_idx)

    def snapshot(self) -> ZaoSnapshot:
        """Read the log file and return the most recent RASCOW_STAT block.

        Returns ZaoSnapshot.unknown() with a canonical reason on:
          - missing file (zao_log_missing)
          - I/O error (zao_log_io_error:<errno>)
          - file present but no RASCOW_STAT block (zao_log_no_rascow_stat)
        """
        try:
            raw = self._path.read_bytes()
        except FileNotFoundError:
            return ZaoSnapshot.unknown(reason="zao_log_missing")
        except OSError as exc:
            # Canonical error string: only embeds errno (an int), never path
            # or raw log content (T-02-03-03).
            return ZaoSnapshot.unknown(reason=f"zao_log_io_error:{exc.errno}")
        return self._parse_bytes(raw)

    @staticmethod
    def _parse_bytes(raw: bytes) -> ZaoSnapshot:
        """Walk `raw` backwards; return the latest contiguous RASCOW_STAT block.

        A "block" is a contiguous run of RASCOW_STAT lines that share the
        timestamp prefix (Zao emits the block in a burst). Walking from EOF
        upward, the first RASCOW line encountered fixes `block_ts`; subsequent
        RASCOW lines with the same `ts` extend the block; any non-RASCOW line
        OR a RASCOW line with a different `ts` ends the block.
        """
        # ascii decode with errors="replace" tolerates malformed lines without
        # raising (T-02-03-01).
        text = raw.decode("ascii", errors="replace")
        lines = text.splitlines()
        collected: list[tuple[str, int, str]] = []  # (ts, line, status)
        block_ts: str | None = None
        for line in reversed(lines):
            m = _RASCOW_RE.match(line)
            if m is None:
                if block_ts is not None:
                    # block already captured; non-RASCOW line ends the run
                    break
                continue  # haven't seen any RASCOW yet; keep scanning back
            ts = m.group("ts")
            if block_ts is None:
                block_ts = ts
            elif ts != block_ts:
                # different timestamp => different block; stop
                break
            collected.append((ts, int(m.group("line")), m.group("status").lower()))

        if not collected:
            return ZaoSnapshot.unknown(reason="zao_log_no_rascow_stat")

        active = frozenset(line for _ts, line, status in collected if status == "active")
        assert block_ts is not None  # collected non-empty implies block_ts set
        log_age = ZaoLogParser._compute_age_seconds(block_ts)
        return ZaoSnapshot(
            active_lines=active,
            last_block_iso=block_ts,
            log_age_seconds=log_age,
            unknown_reason=None,
        )

    @staticmethod
    def _compute_age_seconds(ts_iso: str) -> float | None:
        """Compute seconds between block timestamp and parse-time wall clock.

        ADR-0007: ISO/wall arithmetic is acceptable for diagnostics; durations
        in policy/ must use monotonic. Clamped to >=0 so an NTP-step backwards
        does not produce a negative log_age.
        """
        try:
            normalized = ts_iso.replace("Z", "+00:00")
            ts = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        now = datetime.now(UTC)
        return max(0.0, (now - ts).total_seconds())
