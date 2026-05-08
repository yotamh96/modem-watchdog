"""FakePIDLock — asyncio.Lock-backed fake for cross-platform daemon tests.

Production uses ``fcntl.flock`` (POSIX-only) per Phase 1's
``state_store/locks.py``. This fake gives lifecycle tests a uniform
API surface that doesn't depend on POSIX flock — Windows dev hosts
exercise the choreography + sighup tests without skipping. Linux
integration tests use the real flock-based primitive.

PidLockHeldError mirrors the production exception so tests can
``from tests.fakes.pidlock import PidLockHeldError`` without depending
on the production module.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Iterator


class PidLockHeldError(RuntimeError):
    """Mirror of ``daemon.lifecycle.PidLockHeldError`` for cross-platform tests.

    Tests that use ``FakePIDLock`` import this name from the fake module
    so they can exercise the held-lock branch without depending on the
    production primitive's POSIX-only fcntl.flock.
    """

    def __init__(self, lock_path: str = "/fake/lock") -> None:
        super().__init__(f"PID lock {lock_path!r} held (FakePIDLock)")
        self.lock_path = lock_path


class FakePIDLock:
    """asyncio.Lock-backed PID-lock fake.

    ``acquire()`` returns a context manager that raises
    ``PidLockHeldError`` if already locked (matches non-blocking real
    flock semantics from ``state_store.locks.acquire_flock``).

    Production uses ``daemon.lifecycle.acquire_pid_lock`` against a real
    flock file; this fake is for cross-platform unit tests where the
    flock layer is out of scope.
    """

    def __init__(self) -> None:
        self._locked = False

    @contextlib.contextmanager
    def acquire(self) -> Iterator[int]:
        """Context manager: yields a sentinel fd; raises if already held."""
        if self._locked:
            raise PidLockHeldError()
        self._locked = True
        try:
            yield -1  # sentinel fd (no real fd in the fake)
        finally:
            self._locked = False

    @property
    def locked(self) -> bool:
        return self._locked


# `asyncio` import retained as a hint that real production tests may
# extend the fake with an asyncio.Lock for serialization scenarios; the
# current fake is purely sync-context-manager.
_ = asyncio
