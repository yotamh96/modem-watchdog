"""Phase 3 deferred WatchdogSec piggyback — WatchdogSec=90s actual-fire.

Per CONTEXT D-04 + STATE.md "Deferred Items": Phase 3 deferred the
real-hardware verification of WatchdogSec=90s actual-fire to Phase 4.
The unit-test tier (Plan 03-08 ``test_unit_file_audit.py``) already
asserts ``WatchdogSec=90s`` is in the unit file; the integration tier
(Plan 03-09 ``test_lifecycle.py``) already exercises the cycle-end
sd_notify(WATCHDOG=1) path with fakes; this scenario is the REAL
``systemctl status`` "Result: watchdog" counterpart on the bench Jetson.

Per FR-75 / NFR-13 / Plan 03-06 Issue #5: when the daemon's cycle is
deliberately wedged (e.g. a qmicli child is SIGSTOP'd indefinitely),
sd_notify(WATCHDOG=1) is NOT sent at the expected cadence; systemd's
WatchdogSec=90s elapses; systemd kills + restarts the daemon; the
restart classifies the prior shutdown as "watchdog" (Result=watchdog).

This test is OPT-IN via ``BENCH_JETSON_DESTRUCTIVE_TESTS_OK=true`` --
it deliberately wedges the daemon for ~90 s; nightly runs should not
be exposed to that risk by default.

Flow:
  1. Note current daemon PID.
  2. Find qmicli child of daemon (``pgrep -P <pid> qmicli``).
  3. SIGSTOP the qmicli process (cycle is wedged in qmicli I/O wait).
  4. Wait 100 s (slightly past WatchdogSec=90 s).
  5. Assert daemon was restarted (PID changed).
  6. Assert ``systemctl show -p Result spark-modem-watchdog`` shows
     "watchdog" was the last shutdown reason.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
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
    pytest.mark.skipif(
        os.environ.get("BENCH_JETSON_DESTRUCTIVE_TESTS_OK") != "true",
        reason=(
            "WatchdogSec actual-fire test wedges the daemon for ~90 s; "
            "opt-in via BENCH_JETSON_DESTRUCTIVE_TESTS_OK=true."
        ),
    ),
    pytest.mark.asyncio,
]

_PID_PATH = Path("/run/spark-modem-watchdog/spark-modem-watchdog.pid")
_WATCHDOG_BUDGET_S = 100.0  # WatchdogSec=90 s + 10 s margin for restart


async def _find_qmicli_child(daemon_pid: int) -> int | None:
    cp = await asyncio.to_thread(
        subprocess.run,
        ["pgrep", "-P", str(daemon_pid), "qmicli"],
        check=False,
        capture_output=True,
    )
    if cp.returncode != 0:
        return None
    pid_text = cp.stdout.decode(errors="replace").strip().split("\n")[0]
    if not pid_text:
        return None
    return int(pid_text)


async def test_watchdog_90s_fires_when_cycle_wedged() -> None:
    """SIGSTOP qmicli child -> WatchdogSec=90s elapses -> systemd restarts daemon."""
    pre_pid_text = await asyncio.to_thread(_PID_PATH.read_text, encoding="utf-8")
    pre_pid = int(pre_pid_text.strip())

    # Find a qmicli child and SIGSTOP it. If none is running this very
    # instant, retry briefly -- the cycle observes modems regularly.
    qmicli_pid: int | None = None
    for _ in range(10):
        qmicli_pid = await _find_qmicli_child(pre_pid)
        if qmicli_pid is not None:
            break
        await asyncio.sleep(0.5)
    assert qmicli_pid is not None, (
        f"could not find qmicli child of daemon PID {pre_pid} after 5 s of polling"
    )

    try:
        os.kill(qmicli_pid, signal.SIGSTOP)
        # Wait for WatchdogSec elapse + systemd restart.
        await asyncio.sleep(_WATCHDOG_BUDGET_S)

        # Daemon should be restarted (new PID); the wedged qmicli child
        # is killed by systemd's KillMode=mixed when the daemon process
        # tree is taken down.
        post_pid_text = await asyncio.to_thread(_PID_PATH.read_text, encoding="utf-8")
        post_pid = int(post_pid_text.strip())
        assert post_pid != pre_pid, (
            f"daemon PID did not change after WatchdogSec elapse "
            f"(pre={pre_pid}, post={post_pid}); WatchdogSec=90s did NOT fire "
            f"(NFR-13 / FR-75 violation)"
        )

        # Verify systemctl reports "watchdog" as the last shutdown reason.
        cp = await asyncio.to_thread(
            subprocess.run,
            ["systemctl", "show", "-p", "Result", "spark-modem-watchdog"],
            check=True,
            capture_output=True,
        )
        result_line = cp.stdout.decode(errors="replace").strip()
        assert "watchdog" in result_line.lower(), (
            f"expected systemctl show Result=watchdog after WatchdogSec fire; got {result_line!r}"
        )
    finally:
        # Best-effort cleanup -- the wedged qmicli is normally taken
        # down by systemd KillMode=mixed during daemon restart, but if
        # for some reason it survived, SIGKILL it now.
        with contextlib.suppress(ProcessLookupError):
            os.kill(qmicli_pid, signal.SIGKILL)
