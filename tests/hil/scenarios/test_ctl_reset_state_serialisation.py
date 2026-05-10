"""Phase 3 deferred SC#4 piggyback — concurrent ctl reset-state flock serialisation.

Per CONTEXT D-04: Phase 3 deferred its bench-Jetson SC#4 to Phase 4.
The integration-tier ``test_lifecycle.py`` already covers the
single-process flock contention version; this scenario is the REAL
two-PROCESS counterpart on the bench (true cross-process flock per
ADR-0012).

Per FR-61.1 / ADR-0012: two simultaneous ``spark-modem ctl reset-state
--modem=cdc-wdm0`` invocations MUST serialise on the per-modem flock --
no lost update; the streak / counters reset atomically; the second
caller sees the first caller's reset has already happened (idempotent).

Flow:
  1. Read pre-state ``state/by-usb/2-3.1.1.json`` (counters dict + streak).
  2. Spawn TWO ``spark-modem ctl reset-state --modem=cdc-wdm0``
     subprocesses concurrently via ``asyncio.gather``.
  3. Wait for both to complete; assert both exited 0.
  4. Read post-state; assert counters == {} and streak == 0 (one reset
     happened; the second was a no-op against an already-reset state).
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

_CTL_BIN = "/opt/spark-modem-watchdog/python/bin/spark-modem"
_STATE_PATH = Path("/var/lib/spark-modem-watchdog/state/by-usb/2-3.1.1.json")


async def _read_state() -> dict[str, object]:
    if not await asyncio.to_thread(_STATE_PATH.exists):
        return {}
    raw = await asyncio.to_thread(_STATE_PATH.read_text, encoding="utf-8")
    parsed: dict[str, object] = json.loads(raw)
    return parsed


async def _run_ctl_reset_state() -> subprocess.CompletedProcess[bytes]:
    return await asyncio.to_thread(
        subprocess.run,
        [_CTL_BIN, "ctl", "reset-state", "--modem=cdc-wdm0"],
        check=False,
        capture_output=True,
        timeout=15.0,
    )


async def test_concurrent_ctl_reset_state_serialises_via_flock() -> None:
    """Two concurrent ctl reset-state calls: both succeed; final state is reset."""
    # Concurrent invocation -- asyncio.gather + asyncio.to_thread spawns
    # two real subprocesses; the kernel's POSIX advisory flock on
    # state/by-usb/2-3.1.1.json.lock serialises them.
    r1, r2 = await asyncio.gather(_run_ctl_reset_state(), _run_ctl_reset_state())

    assert r1.returncode == 0, f"first ctl reset-state failed: {r1.stderr.decode(errors='replace')}"
    assert r2.returncode == 0, (
        f"second ctl reset-state failed (lost-update / lock contention?): "
        f"{r2.stderr.decode(errors='replace')}"
    )

    # Idempotent end-state: counters cleared, streak zero.
    post = await _read_state()
    counters = post.get("counters", {})
    streak = post.get("healthy_streak", -1)
    assert counters == {}, (
        f"per-modem counters dict should be {{}} after reset-state; got {counters!r} "
        f"(lost-update via lock-bypass would leave stale values)"
    )
    assert streak == 0, (
        f"healthy_streak should be 0 after reset-state; got {streak!r} "
        f"(lost-update via lock-bypass would leave stale values)"
    )
