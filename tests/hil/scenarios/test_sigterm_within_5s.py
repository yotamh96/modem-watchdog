"""Phase 3 deferred SC#3 piggyback — SIGTERM ≤5 s with real flock release.

Per CONTEXT D-04: Phase 3 deferred its bench-Jetson SC#3 to Phase 4.
The integration-tier ``test_lifecycle.py`` already covers the
``asyncio.Event.set()``-driven version; this scenario is the REAL
``systemctl stop`` counterpart on the bench.

Per FR-53 / Plan 03-06 SigtermChoreography: when SIGTERM is received,
the daemon must complete the 8-step shutdown choreography (cancel
cycle, cancel producers, drain webhook queue, emit DaemonStopped, write
clean-shutdown marker, release flocks) within a deadline budget of 5 s.

Flow:
  1. Note current daemon PID.
  2. ``systemctl stop spark-modem-watchdog`` (sends SIGTERM via Type=notify).
  3. Measure wall-clock time until ``systemctl is-active`` returns
     "inactive".
  4. Assert elapsed <= 5 s.
  5. Assert events.jsonl contains a daemon_stopped event with
     ``reason="sigterm"``.
  6. ``systemctl start`` to restore service.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.hil,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="HIL bench Jetson is Linux/aarch64; tests touch /dev/cdc-wdm and /dev/kmsg.",
    ),
    pytest.mark.asyncio,
]

_EVENTS_PATH = Path("/var/log/spark-modem-watchdog/events.jsonl")
_SIGTERM_BUDGET_S = 5.0


async def _read_events_after(start_iso: str) -> list[dict[str, object]]:
    if not await asyncio.to_thread(_EVENTS_PATH.exists):
        return []
    raw = await asyncio.to_thread(_EVENTS_PATH.read_text, encoding="utf-8")
    out: list[dict[str, object]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(ev, dict):
            ts = ev.get("ts_iso", "")
            if isinstance(ts, str) and ts >= start_iso:
                out.append(ev)
    return out


async def _is_active() -> bool:
    cp = await asyncio.to_thread(
        subprocess.run,
        ["systemctl", "is-active", "spark-modem-watchdog"],
        check=False,
        capture_output=True,
    )
    return cp.stdout.strip() == b"active"


async def test_sigterm_completes_within_5s() -> None:
    """systemctl stop completes within 5 s; daemon_stopped event emitted."""
    from datetime import UTC, datetime  # noqa: PLC0415

    start_iso = datetime.now(UTC).isoformat()

    try:
        # systemctl stop is synchronous from the operator's view; the
        # default systemd TimeoutStopSec is 90 s, but our unit declares
        # WatchdogSec=90s + the daemon's 5 s deadline budget bounds the
        # actual exit time tightly. We measure both via stopwatch.
        t0 = time.monotonic()
        await asyncio.to_thread(
            subprocess.run,
            ["systemctl", "stop", "spark-modem-watchdog"],
            check=True,
            capture_output=True,
            timeout=15.0,  # generous wall-clock cap
        )
        elapsed = time.monotonic() - t0

        assert elapsed <= _SIGTERM_BUDGET_S, (
            f"systemctl stop took {elapsed:.2f}s > {_SIGTERM_BUDGET_S}s "
            f"budget (FR-53 SIGTERM choreography deadline breach)"
        )
        # Sanity: service is now inactive.
        assert not await _is_active(), "service still active after systemctl stop returned"

        events = await _read_events_after(start_iso)
        daemon_stopped = [
            e for e in events if e.get("kind") == "daemon_stopped" and e.get("reason") == "sigterm"
        ]
        assert daemon_stopped, (
            "expected daemon_stopped{reason=sigterm} event in events.jsonl "
            "after systemctl stop (FR-53 audit trail)"
        )
    finally:
        # Restore service so subsequent scenarios have a daemon to test.
        await asyncio.to_thread(
            subprocess.run,
            ["systemctl", "start", "spark-modem-watchdog"],
            check=False,
            capture_output=True,
            timeout=30.0,
        )
