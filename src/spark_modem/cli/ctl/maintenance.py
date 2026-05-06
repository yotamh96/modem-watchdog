"""ctl maintenance on/off/status — dual-clock expiry per C-02.

Field shape persisted at ``globals.json`` (Phase 2 plan 02-07 added the
``maintenance: MaintenanceWindow | None`` field on ``GlobalsState``)::

    {
      "maintenance": {
        "active": true,
        "scope": "destructive",
        "started_iso": "2026-05-06T00:00:00+00:00",
        "started_monotonic": 1234.5,
        "expires_iso":   "2026-05-06T02:00:00+00:00",
        "expires_monotonic": 8434.5,
        "max_duration_seconds": 28800
      }
    }

Hard 8-hour cap (FR-50.2 + C-02): rejected at the CLI before any state
mutation. ``MaintenanceWindow.max_duration_seconds`` is also bounded
``<= 28800`` at Pydantic-validation time, so a hand-edited globals.json
with a larger value fails ``load_globals``.

Lock surface (CLAUDE.md §12 / Claude's Discretion in CONTEXT.md):
``StateStore.save_globals`` acquires the existing state-store flock —
no new lock surface; the daemon and CLI mutator serialize on the same
flock.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime, timedelta

from spark_modem.cli.clients import _CliClock
from spark_modem.state_store.store import StateStore
from spark_modem.wire.maintenance import MaintenanceWindow

MAX_DURATION_SECONDS: int = 28800  # 8h hard cap (FR-50.2 + C-02)

_DURATION_RE = re.compile(r"^(\d+)([hms])$")


def parse_duration(s: str) -> int:
    """Parse '2h' / '30m' / '300s' → seconds. Raises ValueError on bad input."""
    m = _DURATION_RE.match(s.strip().lower())
    if not m:
        raise ValueError(
            f"invalid duration: {s!r} (expected like '2h', '30m', '300s')"
        )
    n = int(m.group(1))
    unit = m.group(2)
    if unit == "h":
        return n * 3600
    if unit == "m":
        return n * 60
    return n


async def run_on(args: argparse.Namespace) -> int:
    """Enable a maintenance window with --duration (mandatory; max 8h)."""
    try:
        duration_s = parse_duration(args.duration)
    except ValueError as exc:
        print(f"maintenance on: {exc}", file=sys.stderr)
        return 2
    if duration_s <= 0:
        print("maintenance on: --duration must be > 0", file=sys.stderr)
        return 2
    if duration_s > MAX_DURATION_SECONDS:
        print(
            f"maintenance on: --duration > {MAX_DURATION_SECONDS}s "
            f"({MAX_DURATION_SECONDS // 3600}h cap)",
            file=sys.stderr,
        )
        return 2

    store = StateStore()
    clock = _CliClock()
    now_mono = clock.monotonic()
    now_wall = datetime.now(UTC)
    expires_wall = now_wall + timedelta(seconds=duration_s)
    window = MaintenanceWindow(
        active=True,
        scope="destructive",
        started_iso=now_wall.isoformat(),
        started_monotonic=now_mono,
        expires_iso=expires_wall.isoformat(),
        expires_monotonic=now_mono + duration_s,
        max_duration_seconds=MAX_DURATION_SECONDS,
    )
    # Read globals, set maintenance, write back. StateStore.save_globals
    # acquires the state-store flock automatically (no new lock surface).
    load = await store.load_globals()
    new_globals = load.state.model_copy(update={"maintenance": window})
    await store.save_globals(new_globals)
    print(f"maintenance on: window expires at {window.expires_iso}")
    return 0


async def run_off(args: argparse.Namespace) -> int:
    """Disable any active maintenance window."""
    del args
    store = StateStore()
    load = await store.load_globals()
    if load.state.maintenance is None or not load.state.maintenance.active:
        print("maintenance off: no active window")
        return 0
    new_globals = load.state.model_copy(update={"maintenance": None})
    await store.save_globals(new_globals)
    print("maintenance off")
    return 0


async def run_status(args: argparse.Namespace) -> int:
    """Print maintenance window status as JSON; dual-clock expiry check."""
    del args
    store = StateStore()
    load = await store.load_globals()
    m = load.state.maintenance
    if m is None or not m.active:
        print(json.dumps({"active": False}))
        return 0
    # Dual-clock check: either wall OR monotonic past expiry → expired.
    clock = _CliClock()
    now_mono = clock.monotonic()
    now_wall_iso = datetime.now(UTC).isoformat()
    expired = (
        now_mono >= m.expires_monotonic
        or now_wall_iso >= m.expires_iso
    )
    print(
        json.dumps(
            {
                "active": not expired,
                "scope": m.scope,
                "started_iso": m.started_iso,
                "expires_iso": m.expires_iso,
                "expired_now": expired,
            }
        )
    )
    return 0
