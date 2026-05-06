"""ctl history --modem= --since= — read events.jsonl + rotated siblings.

C-03 / FR-50.1: filter by modem (``usb_path`` canonical) and ``--since``
(``1h`` / ``30m`` / ``300s``). The events.jsonl is the single source of
truth (no separate transitions log); ``ctl history`` is the operator-
facing replay surface (RUNBOOK.md §"replay events.jsonl").

Phase 3 logrotate creates ``events.jsonl.1``, ``events.jsonl.2.gz``,
etc.; this reader supports both compressed-gzip and plain-text rotated
siblings. Files that do not exist are silently skipped (rotation is
configuration-driven).

Corrupt JSONL lines are skipped, not raised — events.jsonl is append-
only and a partial last-line write across daemon-crash is the canonical
recovery case (atomic-append guarantees per-line atomicity, but a SIGKILL
mid-write could leave a truncated final line).
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from spark_modem.wire.events import Event, EventAdapter

_DURATION_RE = re.compile(r"^(\d+)([hms])$")

_DEFAULT_EVENTS_LOG = Path("/var/log/spark-modem-watchdog/events.jsonl")


def parse_since(s: str) -> float:
    """Parse '2h' / '30m' / '300s' → seconds (float). Raises on bad input."""
    m = _DURATION_RE.match(s.strip().lower())
    if not m:
        raise ValueError(f"invalid --since: {s!r}")
    n = int(m.group(1))
    unit = m.group(2)
    if unit == "h":
        return float(n * 3600)
    if unit == "m":
        return float(n * 60)
    return float(n)


def _candidate_paths(events_log_path: Path) -> list[Path]:
    """Return [primary, .1, .1.gz, .2, .2.gz, ...] in newest-first order."""
    candidates: list[Path] = [events_log_path]
    for i in range(1, 10):
        # logrotate renames events.jsonl → events.jsonl.1 (no .gz initially).
        sib = events_log_path.with_suffix(f".jsonl.{i}")
        if sib.is_file():
            candidates.append(sib)
        # Compressed siblings produced by logrotate's compress/delaycompress.
        sibgz = events_log_path.with_suffix(f".jsonl.{i}.gz")
        if sibgz.is_file():
            candidates.append(sibgz)
    return candidates


def _open_events_path(path: Path) -> Iterator[bytes]:
    """Iterate over lines in a path; transparently handles .gz."""
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as fh:
            yield from fh
    else:
        with path.open("rb") as fh:
            yield from fh


def read_events_with_rotated_siblings(events_log_path: Path) -> Iterable[Event]:
    """Yield events from events.jsonl + rotated siblings.

    Output order: oldest-first (chronologically), so consumers can pipe
    through filter_events() without re-sorting. Corrupt lines are
    skipped silently — events.jsonl integrity is the writer's
    responsibility (FR-40 atomic-append).
    """
    candidates = _candidate_paths(events_log_path)
    # Reverse → oldest first. (.gz tend to be older than .N which is older than primary.)
    for path in reversed(candidates):
        if not path.is_file():
            continue
        for raw_line in _open_events_path(path):
            line = raw_line.strip()
            if not line:
                continue
            try:
                yield EventAdapter.validate_json(line)
            except (ValidationError, ValueError):
                # Corrupt lines (truncated last line, schema drift) are
                # skipped, not raised. events.jsonl is append-only by
                # design; a single bad line should not abort replay.
                continue


def _event_modem_id(event: Event) -> str | None:
    """Return the modem identity field of the event variant, if any."""
    # Variants carry usb_path under different field names:
    #   ActionPlanned/ActionExecuted/ActionFailed/StateTransition/UsbPathMismatch
    #     → ``usb_path`` (or ``file_usb_path`` for UsbPathMismatch)
    #   WebhookDropped → ``modem_usb_path``
    if hasattr(event, "usb_path"):
        usb_path = event.usb_path
        return usb_path if isinstance(usb_path, str) else None
    if hasattr(event, "modem_usb_path"):
        modem_usb_path = event.modem_usb_path
        return modem_usb_path if isinstance(modem_usb_path, str) else None
    if hasattr(event, "file_usb_path"):
        file_usb_path = event.file_usb_path
        return file_usb_path if isinstance(file_usb_path, str) else None
    return None


def filter_events(
    events: Iterable[Event],
    *,
    modem: str | None,
    since_seconds: float | None,
) -> list[Event]:
    """Filter by modem identity and a max age.

    Modem matching is canonical-by-``usb_path``. ``cdc-wdmN`` aliasing
    requires the daemon's identity map (Phase 3); without it, callers
    pass the canonical ``usb_path`` (e.g. ``2-3.1.1``).

    Events without a modem field (DaemonStarted, DaemonStopped) are
    excluded when ``modem`` is set.
    """
    # WR-02: compare cutoff and event timestamps as datetimes (NOT
    # lexicographic strings).  Lexicographic ISO ordering only works when
    # both sides are in the same canonical form (UTC '+00:00').  Events
    # written by a future writer with a different timezone offset would
    # sort incorrectly as strings even though the instants compare
    # correctly as datetimes.
    cutoff_dt: datetime | None = None
    if since_seconds is not None:
        cutoff_dt = datetime.now(UTC) - timedelta(seconds=since_seconds)
    out: list[Event] = []
    for event in events:
        if cutoff_dt is not None:
            try:
                event_dt = datetime.fromisoformat(event.ts_iso)
            except ValueError:
                # Skip events with an unparseable ts_iso rather than
                # silently include or exclude them.  Defensive: events.jsonl
                # is pydantic-validated upstream, so this is unreachable
                # in normal operation.
                continue
            if event_dt < cutoff_dt:
                continue
        if modem is not None:
            event_modem_id = _event_modem_id(event)
            if event_modem_id is None or event_modem_id != modem:
                continue
        out.append(event)
    return out


async def run(args: argparse.Namespace) -> int:
    events_log = (
        Path(args.events_log)
        if getattr(args, "events_log", None) is not None
        else _DEFAULT_EVENTS_LOG
    )
    since_seconds: float | None = None
    if args.since is not None:
        try:
            since_seconds = parse_since(args.since)
        except ValueError as exc:
            print(f"ctl history: {exc}", file=sys.stderr)
            return 2
    events = list(read_events_with_rotated_siblings(events_log))
    events = filter_events(events, modem=args.modem, since_seconds=since_seconds)
    for ev in events:
        print(json.dumps(ev.model_dump(mode="json")))
    return 0
