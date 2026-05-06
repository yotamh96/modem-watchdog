"""Tests for SP-03 invariant 4: two-stage shutdown and cpython#139373 regression.

The runner MUST:
  - Return within a bounded wall time after timeout fires.
  - Return timed_out=True and a negative exit_code (signal-killed).
  - Recover stdout that the child emitted BEFORE the timeout (cpython#139373).
  - Set kill_signal=9 (SIGKILL) when the child ignores SIGTERM.

asyncio.timeout() context manager is used, NOT wait_for around communicate
(cpython#139373: wait_for cancels mid-communicate and the in-flight stdout is lost).
"""

from __future__ import annotations

import sys
import time

import pytest

from spark_modem.subproc.runner import run

_SKIP_WIN = pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "Requires POSIX process control (SIGTERM/SIGKILL/start_new_session); "
        "production target is Jetson (Linux/aarch64)"
    ),
)


@_SKIP_WIN
async def test_timeout_returns_timed_out_true() -> None:
    """A process that sleeps past the timeout returns timed_out=True."""
    result = await run(["/bin/sh", "-c", "sleep 5"], timeout_s=0.2)
    assert result.timed_out is True, "Expected timed_out=True for a long-sleeping process"


@_SKIP_WIN
async def test_timeout_exit_code_is_negative() -> None:
    """After timeout+SIGKILL, the exit_code is negative (signal-killed)."""
    result = await run(["/bin/sh", "-c", "sleep 5"], timeout_s=0.2)
    assert result.timed_out is True
    # Killed by signal -> exit_code < 0 (Python asyncio convention: -signal_number)
    assert result.exit_code < 0, (
        f"Expected negative exit_code after signal kill, got: {result.exit_code}"
    )


@_SKIP_WIN
async def test_timeout_wall_time_bounded() -> None:
    """Total wall time is <= timeout_s + 2s SIGTERM grace + 0.5s slop."""
    timeout_s = 0.2
    max_allowed_s = timeout_s + 2.0 + 0.5  # grace + slop
    wall_start = time.monotonic()
    result = await run(["/bin/sh", "-c", "sleep 5"], timeout_s=timeout_s)
    wall_elapsed = time.monotonic() - wall_start

    assert result.timed_out is True
    assert wall_elapsed < max_allowed_s, (
        f"Wall time {wall_elapsed:.2f}s exceeded {max_allowed_s:.2f}s"
    )


@_SKIP_WIN
async def test_timeout_recovers_pre_timeout_stdout() -> None:
    """cpython#139373 regression: stdout emitted before the timeout is returned.

    The child emits 'early' to stdout, then sleeps forever. The runner must
    return the pre-death stdout in the CompletedProcess, not discard it.
    """
    # Script: print 'early', flush, then sleep (simulating a slow command that
    # prints progress before hanging).
    script = "printf 'early\\n'; exec sleep 60"
    result = await run(["/bin/sh", "-c", script], timeout_s=0.3)

    assert result.timed_out is True
    # The pre-timeout stdout must be present (cpython#139373 would lose it).
    assert b"early" in result.stdout, (
        f"Expected 'early' in stdout (cpython#139373 regression), got: {result.stdout!r}"
    )


@_SKIP_WIN
async def test_sigkill_used_when_child_ignores_sigterm() -> None:
    """When the child traps SIGTERM and continues, SIGKILL is used after grace period.

    kill_signal should be set to SIGKILL (9) in the returned CompletedProcess.
    """
    # Script traps SIGTERM and keeps sleeping; runner should escalate to SIGKILL.
    script = "trap '' TERM; sleep 60"
    result = await run(["/bin/sh", "-c", script], timeout_s=0.2)

    assert result.timed_out is True
    # The two-stage shutdown should have escalated to SIGKILL.
    assert result.kill_signal == 9, (
        f"Expected kill_signal=9 (SIGKILL) when child ignores SIGTERM, got: {result.kill_signal!r}"
    )
