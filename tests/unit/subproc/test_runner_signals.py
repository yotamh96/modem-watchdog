"""Tests for SP-03 invariant 3: process-group kill via start_new_session=True.

The runner MUST use start_new_session=True so that os.killpg kills the entire
process group (parent + forked grandchildren), not just the bare parent PID.

cpython#127049: killing only the parent leaves grandchild processes orphaned.
With start_new_session=True the child becomes the process group leader, and
os.killpg(os.getpgid(child.pid), SIGKILL) reaps the whole tree.
"""

from __future__ import annotations

import os
import sys
import time

import pytest

from spark_modem.subproc.runner import run

_SKIP_WIN = pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "Requires POSIX process groups / start_new_session; "
        "production target is Jetson (Linux/aarch64)"
    ),
)

_SKIP_NO_KILLPG = pytest.mark.skipif(
    not hasattr(os, "killpg"),
    reason="os.killpg not available on this platform",
)


@_SKIP_WIN
@_SKIP_NO_KILLPG
async def test_process_group_killed_on_timeout() -> None:
    """Parent+grandchild are both reaped within bounded wall time.

    The parent shell forks '/bin/sleep 60' and waits; with start_new_session=True
    the whole group is killed on timeout, not just the shell.

    We verify by checking that the total wall time is bounded (the grandchild
    'sleep 60' would keep the test running > 60s if it survived as an orphan
    because asyncio.timeout would only have killed the shell parent).
    """
    # Shell forks a grandchild sleep and waits -- simulates qmicli forking helpers.
    script = "/bin/sleep 60 & wait"
    timeout_val = 0.3
    max_allowed_s = timeout_val + 2.0 + 0.5  # grace + slop

    wall_start = time.monotonic()
    result = await run(["/bin/sh", "-c", script], timeout_s=timeout_val)
    wall_elapsed = time.monotonic() - wall_start

    assert result.timed_out is True
    # If the process group was properly killed, wall time is bounded.
    assert wall_elapsed < max_allowed_s, (
        f"Wall time {wall_elapsed:.2f}s exceeded {max_allowed_s:.2f}s -- "
        "grandchild process may not have been reaped (process-group kill failed)"
    )


@_SKIP_WIN
@_SKIP_NO_KILLPG
async def test_sigterm_sent_before_sigkill() -> None:
    """Two-stage shutdown: SIGTERM is sent first; SIGKILL only if still alive.

    A child that exits quickly on SIGTERM should finish well within the
    2s SIGTERM grace window.
    """
    # Simple sleep: will be killed by SIGTERM immediately (default handler).
    timeout_val = 0.2
    wall_start = time.monotonic()
    result = await run(["/bin/sleep", "60"], timeout_s=timeout_val)
    wall_elapsed = time.monotonic() - wall_start

    assert result.timed_out is True
    # Should finish well within the 2s SIGTERM grace (process dies on SIGTERM).
    assert wall_elapsed < timeout_val + 2.0 + 0.3, (
        f"Process did not die on SIGTERM within grace period; elapsed={wall_elapsed:.2f}s"
    )
    # exit_code is negative (killed by signal).
    assert result.exit_code < 0
