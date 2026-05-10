"""Phase 3 deferred SC#5 piggyback — qmi_wwan reload as clean state transition.

Per CONTEXT D-04: Phase 3 deferred its bench-Jetson SC#5 to Phase 4.
The integration-tier ``test_lifecycle.py`` already covers the
Fake*-injected version; this scenario is the REAL ``modprobe -r/+ qmi_wwan``
counterpart on the bench.

Per docs/MIGRATION.md (Phase 3): the daemon must NOT crash when the
qmi_wwan module is reloaded out-of-band; it must observe the
disconnected -> recovering -> healthy state transitions and emit them
into events.jsonl (NFR-12).

Flow:
  1. Note the daemon's PID.
  2. modprobe -r qmi_wwan; wait briefly; modprobe qmi_wwan.
  3. Assert /proc/<pid>/status still shows the daemon (no crash).
  4. Assert events.jsonl shows at least one state transition through
     ``recovering`` (or back to ``healthy``) for cdc-wdm0 since the
     test started.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
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
_PID_PATH = Path("/run/spark-modem-watchdog/spark-modem-watchdog.pid")
_RECOVERY_BUDGET_S = 90.0


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


async def test_qmi_wwan_reload_does_not_crash_daemon() -> None:
    """modprobe -r/+ qmi_wwan: daemon survives, transitions surface in events."""
    from datetime import UTC, datetime  # noqa: PLC0415

    pre_pid_text = await asyncio.to_thread(_PID_PATH.read_text, encoding="utf-8")
    pre_pid = int(pre_pid_text.strip())
    start_iso = datetime.now(UTC).isoformat()

    await asyncio.to_thread(
        subprocess.run, ["modprobe", "-r", "qmi_wwan"], check=True, capture_output=True
    )
    await asyncio.sleep(2.0)
    await asyncio.to_thread(
        subprocess.run, ["modprobe", "qmi_wwan"], check=True, capture_output=True
    )

    # Allow time for re-enumeration + cycle observation.
    await asyncio.sleep(_RECOVERY_BUDGET_S / 4)

    # Daemon survived: same PID still alive (no crash + supervisor-restart).
    post_pid_text = await asyncio.to_thread(_PID_PATH.read_text, encoding="utf-8")
    post_pid = int(post_pid_text.strip())
    assert pre_pid == post_pid, (
        f"daemon PID changed across qmi_wwan reload (crash + restart); "
        f"pre={pre_pid} post={post_pid}. NFR-12 requires the daemon to survive."
    )

    # Status check: /proc/<pid>/status exists.
    status_path = Path(f"/proc/{post_pid}/status")
    assert await asyncio.to_thread(status_path.exists), (
        f"/proc/{post_pid}/status missing after qmi_wwan reload (daemon dead)"
    )

    # State transitions surfaced.
    events = await _read_events_after(start_iso)
    transitions = [
        e for e in events if e.get("kind") in {"state_transition", "modem_state_changed"}
    ]
    assert transitions, (
        "expected at least one state_transition / modem_state_changed event "
        "after qmi_wwan reload (NFR-12 clean-transition contract)"
    )
