"""Unit tests for daemon.lifecycle.acquire_pid_lock (POSIX flock semantics).

Module-level skipif on Windows: production target is Linux/aarch64 and
the underlying ``state_store.locks.acquire_flock`` requires fcntl.flock.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX flock semantics")

from spark_modem.daemon.lifecycle import (  # noqa: E402  — module-level skipif above
    PidLockHeldError,
    acquire_pid_lock,
)


def test_acquire_returns_fd(tmp_path: Path) -> None:
    """acquire_pid_lock yields an open fd > 0."""
    with acquire_pid_lock(run_dir=tmp_path) as fd:
        assert isinstance(fd, int)
        assert fd > 0


def test_second_acquire_raises_pid_lock_held_error(tmp_path: Path) -> None:
    """Two concurrent acquires on the same run_dir → PidLockHeldError."""
    with (
        acquire_pid_lock(run_dir=tmp_path),
        pytest.raises(PidLockHeldError),
        acquire_pid_lock(run_dir=tmp_path),
    ):
        pytest.fail("second acquire should have raised PidLockHeldError")


def test_release_allows_subsequent_acquire(tmp_path: Path) -> None:
    """After the first acquire context exits, a second acquire succeeds."""
    with acquire_pid_lock(run_dir=tmp_path):
        pass  # release on context exit
    with acquire_pid_lock(run_dir=tmp_path) as fd:
        assert fd > 0
