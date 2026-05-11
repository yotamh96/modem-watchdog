"""Audit a soak window for S-01 #2 violations.

S-01 #2 (Phase 5 CONTEXT.md): Zero "action planned on a Zao-active line"
(ADR-0003: never QMI-probe or recovery-act on a Zao-active line).

For each ``action_planned`` event in events.jsonl, this audit finds the
contemporaneous Zao RASCOW_STAT snapshot (the latest block whose
timestamp is <= event.ts_iso) and checks whether the modem's line was
active. If yes -> violation.

The event-side modem identity is ``usb_path`` (e.g. ``2-3.1.1``). The
Zao log keys by ``line`` (1..4). The audit derives ``line`` from the
trailing dotted segment of ``usb_path`` (``2-3.1.N`` -> N) since the
production events.jsonl does NOT carry a ``line`` field on
ActionPlanned (see src/spark_modem/wire/events.py).

Outputs a JSON report at --out and exits non-zero when violations are
found.

## Subprocess discipline

This is a ``tools/`` script (NOT under ``src/spark_modem/``); SP-04 lint
scope excludes anything outside ``src/`` (see
``scripts/lint_no_subprocess.sh:11``). Direct ``subprocess.run`` is
acceptable here, though this script does not need it.

## Exit codes

- ``0`` -- no violations / clean soak window.
- ``1`` -- violations found.
- ``2`` -- operational error (bad input path, etc.).
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

# NOTE: tools/ is SP-04-exempt and audit-only. We deliberately do NOT
# import ``read_events_with_rotated_siblings`` from
# ``spark_modem.cli.ctl.history`` because that function yields validated
# pydantic ``Event`` objects (via ``EventAdapter.validate_json``), and
# the audit operates over raw dicts so the Event union can evolve
# without breaking the audit. We read events.jsonl directly as JSONL.


def _read_events_as_raw_dicts(events_log: Path) -> Iterator[dict[str, object]]:
    """Yield events from events.jsonl + rotated siblings as raw dicts.

    Bypasses pydantic validation deliberately: the audit's value
    proposition is that it does NOT break when the Event union shape
    evolves. Corrupt lines are skipped silently (matches the
    ``history.py`` corrupt-line convention) and non-dict JSON values
    are also skipped defensively. Rotated siblings (``.1``, ``.2.gz``,
    ...) are iterated oldest-first.

    Raises nothing on FileNotFoundError of the primary path -- the
    caller has already validated ``args.events.exists()``.
    """
    # Build candidate list: primary + .1, .1.gz, .2, .2.gz, ...
    candidates: list[Path] = [events_log]
    for i in range(1, 10):
        sib = events_log.with_suffix(f".jsonl.{i}")
        if sib.is_file():
            candidates.append(sib)
        sibgz = events_log.with_suffix(f".jsonl.{i}.gz")
        if sibgz.is_file():
            candidates.append(sibgz)

    # Oldest-first: rotated siblings are older than the primary.
    for path in reversed(candidates):
        if not path.is_file():
            continue
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rb") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    yield obj


# RASCOW_STAT block timestamp + line/status regex (parser-local;
# the production zao_log parser is bound to a latest-snapshot-only
# API surface, but the audit needs a forward walk).
_RASCOW_TS_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z))"
    r".*RASCOW_STAT.*\bline=(\d+).*\bstatus=(\w+)"
)


# usb_path -> line number: the trailing dotted segment of e.g. ``2-3.1.1``.
# Bench hardware always wires lines 1..4 to ``2-3.1.{1..4}`` (CLAUDE.md
# "Hardware target"). The audit refuses to fabricate a line for paths
# that don't match the expected pattern.
_USB_PATH_LINE_RE = re.compile(r"\.(\d+)$")


# Defensive size cap on Zao log reads (Phase 5 WR-01). The audit needs every
# RASCOW_STAT block in the window, but the read path was previously unbounded
# (`Path.read_text()`); a pathological / accidentally-uncompressed multi-GiB
# log would consume RAM. The production zao_log/version.py uses a 64 KiB cap
# for banner detection; here we keep the full file but stream it, and refuse
# files larger than 1 GiB with a clear operator-visible error.
_MAX_ZAO_LOG_BYTES = 1 * 1024 * 1024 * 1024  # 1 GiB


def _derive_line_from_usb_path(usb_path: str) -> int | None:
    """Derive the Zao line (1..4) from the trailing segment of usb_path.

    Returns None for malformed paths (the audit classifies such events
    as ``unknown_line_derivation`` rather than fabricating a line).
    """
    m = _USB_PATH_LINE_RE.search(usb_path)
    if m is None:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


@dataclass
class _ZaoBlock:
    ts_iso: str
    active_lines: frozenset[int]


def _parse_zao_blocks(zao_log: Path) -> list[_ZaoBlock]:
    """Parse the Zao log into a sorted list of RASCOW_STAT blocks.

    Each block carries the active-line set at its wallclock. Lines with
    status='active' contribute to active_lines; everything else (inactive,
    unknown, etc.) is ignored. Forward walk; result sorted by ts_iso
    ascending (file order; Zao appends chronologically).

    Phase 5 WR-01: stats the file up-front and refuses files larger than
    ``_MAX_ZAO_LOG_BYTES`` (1 GiB). For files within the cap, streams
    the read line-by-line instead of loading the whole file into memory
    so a multi-MiB Zao log does not balloon RSS during an audit run.
    """
    try:
        size = zao_log.stat().st_size
    except FileNotFoundError:
        return []
    if size > _MAX_ZAO_LOG_BYTES:
        raise RuntimeError(
            f"Zao log {zao_log} is {size} bytes (cap {_MAX_ZAO_LOG_BYTES}); "
            "rotate or pre-filter before auditing"
        )
    blocks: list[_ZaoBlock] = []
    current_ts: str | None = None
    current_lines: set[int] = set()
    try:
        with zao_log.open("r", encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                # rstrip the newline (and any trailing \r on CRLF-encoded inputs);
                # _RASCOW_TS_RE is line-anchored via .match() and unaffected by
                # leading whitespace per the existing fixture shape.
                m = _RASCOW_TS_RE.match(raw_line.rstrip("\r\n"))
                if m is None:
                    continue
                ts, line_str, status = m.groups()
                if current_ts is None:
                    current_ts = ts
                elif ts != current_ts:
                    blocks.append(
                        _ZaoBlock(ts_iso=current_ts, active_lines=frozenset(current_lines))
                    )
                    current_ts = ts
                    current_lines = set()
                if status.lower() == "active":
                    current_lines.add(int(line_str))
    except FileNotFoundError:
        # Race between stat() and open() — treat as absent for the audit.
        return []
    if current_ts is not None:
        blocks.append(_ZaoBlock(ts_iso=current_ts, active_lines=frozenset(current_lines)))
    return blocks


def _find_contemporaneous_block(blocks: list[_ZaoBlock], event_ts: str) -> _ZaoBlock | None:
    """Return the latest block with ts_iso <= event_ts, or None.

    String comparison is sound here because both sides are normalised
    ISO-8601 with the same zone offset shape (Phase 2 emits +00:00;
    Zao emits +00:00 in production). For mixed offsets the operator
    would normalise upstream before running the audit.
    """
    latest: _ZaoBlock | None = None
    for b in blocks:
        if b.ts_iso <= event_ts:
            latest = b
        else:
            break
    return latest


@dataclass
class _AuditResult:
    violations: int = 0
    details: list[dict[str, object]] = field(default_factory=list)
    unknown_no_zao_snapshot: int = 0


def _audit(
    events_path: Path,
    zao_log: Path,
    since_iso: str | None,
) -> _AuditResult:
    result = _AuditResult()
    blocks = _parse_zao_blocks(zao_log)
    for raw_event in _read_events_as_raw_dicts(events_path):
        if raw_event.get("kind") != "action_planned":
            continue
        ts = raw_event.get("ts_iso")
        if not isinstance(ts, str):
            continue
        if since_iso is not None and ts < since_iso:
            continue
        usb_path = raw_event.get("usb_path")
        if not isinstance(usb_path, str):
            continue
        line = _derive_line_from_usb_path(usb_path)
        if line is None:
            # Malformed usb_path; record as unknown rather than fabricate.
            result.unknown_no_zao_snapshot += 1
            result.details.append(
                {
                    "ts_iso": ts,
                    "usb_path": usb_path,
                    "line": None,
                    "classification": "unknown_line_derivation",
                }
            )
            continue
        block = _find_contemporaneous_block(blocks, ts)
        if block is None:
            result.unknown_no_zao_snapshot += 1
            result.details.append(
                {
                    "ts_iso": ts,
                    "usb_path": usb_path,
                    "line": line,
                    "classification": "no_zao_snapshot_for_cycle",
                }
            )
            continue
        if line in block.active_lines:
            result.violations += 1
            result.details.append(
                {
                    "ts_iso": ts,
                    "usb_path": usb_path,
                    "line": line,
                    "zao_block_ts": block.ts_iso,
                    "zao_active_lines": sorted(block.active_lines),
                    "classification": "violation",
                }
            )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit a soak window for S-01 #2 violations (action planned on Zao-active line)."
        ),
    )
    parser.add_argument(
        "--events",
        type=Path,
        required=True,
        help="Path to events.jsonl (rotated siblings auto-discovered)",
    )
    parser.add_argument(
        "--zao-log",
        type=Path,
        required=True,
        help="Path to Zao remote-endpoint log",
    )
    parser.add_argument(
        "--since-iso",
        type=str,
        default=None,
        help="Optional ISO-8601 lower bound; events older are skipped",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output JSON report path",
    )
    args = parser.parse_args(argv)

    if not args.events.exists():
        print(f"audit_soak_zao: events path not found: {args.events}", file=sys.stderr)
        return 2

    result = _audit(args.events, args.zao_log, args.since_iso)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "violations": result.violations,
                "unknown_no_zao_snapshot": result.unknown_no_zao_snapshot,
                "details": result.details,
            },
            indent=2,
        )
        + "\n"
    )

    return 1 if result.violations > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
