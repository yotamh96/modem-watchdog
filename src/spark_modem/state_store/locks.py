"""3-layer locking model (ADR-0012).

Layer 1 (in-process, asyncio):
  - PerModemLockTable: dict[usb_path, asyncio.Lock] lazily populated.
  - globals_lock(): a singleton asyncio.Lock for the GlobalsState file.
  Single-key APIs only (acquire one modem at a time; never compose).

Layer 2 (cross-process, advisory flocks — POSIX only):
  - acquire_flock(/run/.../state.lock)         — state-store flock
  - acquire_flock(/run/.../modem-<usb>.lock)   — per-modem flock
  Daemon and CLI take the same flocks. CLI mutating commands take the
  same flocks the daemon does (CLAUDE.md invariant #12).

Layer 3 (PID lock, separate file):
  - PID lock at /run/.../lock — owned by the daemon's main process; SEPARATE
  from the flocks above. Implementation lands in Phase 3 (sd_notify lifecycle).

LOCK ACQUISITION ORDER (mandatory, enforced at every StateStore call site):
  1. asyncio.Lock first (in-process serialization).
  2. flock second (cross-process serialization).
  Releasing happens in reverse order on context-manager exit.
  This order is documented at every acquisition site in store.py to
  prevent ABBA between the daemon (asyncio.Lock + flock) and a CLI mutator
  (flock only).

Note: fcntl is POSIX-only. The daemon never runs on Windows; flock helpers
are available on Linux/macOS only. Tests on Windows skip the flock subset.
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import os
import sys
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

from spark_modem.state_store.errors import StateStoreLocked

# fcntl is POSIX-only. Import unconditionally so mypy can resolve attributes
# on Linux (where it ships as a builtin). On Windows the import fails at
# runtime — the _FCNTL_AVAILABLE guard turns flock helpers into no-ops.
if sys.platform != "win32":
    import fcntl

    _FCNTL_AVAILABLE = True
else:
    _FCNTL_AVAILABLE = False

# ---------------------------------------------------------------------------
# Layer 1: in-process asyncio locks
# ---------------------------------------------------------------------------


class PerModemLockTable:
    """Lazily-populated per-modem asyncio.Lock cache.

    Thread-safe within a single asyncio event loop (all access from async
    coroutines running on the same loop). The dict is never accessed from
    multiple threads simultaneously in production.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def get(self, usb_path: str) -> asyncio.Lock:
        """Return the asyncio.Lock for usb_path, creating it if absent."""
        lock = self._locks.get(usb_path)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[usb_path] = lock
        return lock

    def usb_paths(self) -> tuple[str, ...]:
        """Sorted snapshot of currently-known usb_paths (deterministic ordering)."""
        return tuple(sorted(self._locks.keys()))


# Singleton globals asyncio.Lock — module-level so all consumers see the same instance.
# Reset to None in tests that need isolation.
_GLOBALS_LOCK_SINGLETON: asyncio.Lock | None = None


def globals_lock() -> asyncio.Lock:
    """The single asyncio.Lock guarding GlobalsState and IdentityMap writes."""
    global _GLOBALS_LOCK_SINGLETON  # noqa: PLW0603
    if _GLOBALS_LOCK_SINGLETON is None:
        _GLOBALS_LOCK_SINGLETON = asyncio.Lock()
    return _GLOBALS_LOCK_SINGLETON


# ---------------------------------------------------------------------------
# Layer 2: cross-process flocks (POSIX only)
# ---------------------------------------------------------------------------


def _read_pid_from(path: Path) -> int | None:
    """Read a PID written into a lock file by the holder; None on failure."""
    try:
        text = path.read_text(encoding="ascii", errors="ignore").strip()
        return int(text) if text else None
    except (OSError, ValueError):
        return None


@contextlib.contextmanager
def acquire_flock(
    path: Path | str,
    *,
    blocking: bool = False,
    write_pid: bool = True,
) -> Iterator[int]:
    """Acquire an exclusive flock on ``path`` (POSIX only).

    Args:
        path:      Lock file path; created with mode 0o640 if absent.
        blocking:  If False (default), raises :class:`StateStoreLocked` on
                   contention. If True, blocks until the lock is available.
        write_pid: If True, writes the current PID into the lock file after
                   acquiring so ``cat <path>`` reveals the holder.

    Yields the open file descriptor. Caller must not close it.

    Raises:
        StateStoreLocked: when blocking=False and the lock is held by another.
        ImportError: on non-POSIX systems (fcntl unavailable).
    """
    if not _FCNTL_AVAILABLE:
        raise ImportError("fcntl is not available on this platform (POSIX only)")

    path_p = Path(path)
    path_p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path_p), os.O_CREAT | os.O_RDWR, 0o640)
    try:
        flags = fcntl.LOCK_EX  # type: ignore[name-defined]
        if not blocking:
            flags |= fcntl.LOCK_NB  # type: ignore[name-defined]
        try:
            fcntl.flock(fd, flags)  # type: ignore[name-defined]
        except OSError as e:
            if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                holder_pid = _read_pid_from(path_p)
                raise StateStoreLocked(
                    holder_pid=holder_pid,
                    lock_path=str(path_p),
                ) from e
            raise
        if write_pid:
            # Truncate and write PID so operators can identify the holder.
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.fsync(fd)
        yield fd
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)  # type: ignore[name-defined]
        with contextlib.suppress(OSError):
            os.close(fd)


def _enter_flock_for_async(
    path: Path | str,
    blocking: bool,
    write_pid: bool,
) -> AsyncFlockHandle:
    """Open and flock the path; return a handle that owns the fd.

    Called from a worker thread via asyncio.to_thread so the event loop
    is not blocked by the potentially-waiting flock syscall.

    On non-POSIX systems (Windows dev host), returns a no-op handle.
    The daemon never runs on Windows; this is a dev-host accommodation
    so unit tests that exercise the asyncio.Lock layer work without fcntl.
    """
    if not _FCNTL_AVAILABLE:
        # No-op on Windows; sentinel fd=-1 skipped by _release_flock_fd.
        return AsyncFlockHandle(-1, Path(path))

    path_p = Path(path)
    path_p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path_p), os.O_CREAT | os.O_RDWR, 0o640)
    try:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)  # type: ignore[name-defined]
        fcntl.flock(fd, flags)  # type: ignore[name-defined]
    except OSError as e:
        with contextlib.suppress(OSError):
            os.close(fd)
        if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
            raise StateStoreLocked(
                holder_pid=_read_pid_from(path_p),
                lock_path=str(path_p),
            ) from e
        raise

    if write_pid:
        with contextlib.suppress(OSError):
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.fsync(fd)

    return AsyncFlockHandle(fd, path_p)


def _release_flock_fd(fd: int) -> None:
    """Unlock and close an fd (run from a worker thread).

    fd=-1 is the no-op sentinel used on non-POSIX systems.
    """
    if fd < 0:
        return  # no-op sentinel (Windows dev host)
    with contextlib.suppress(OSError):
        fcntl.flock(fd, fcntl.LOCK_UN)  # type: ignore[name-defined]
    with contextlib.suppress(OSError):
        os.close(fd)


class AsyncFlockHandle:
    """Handle returned by :func:`acquire_flock_async`.

    Supports both ``async with`` and explicit ``await handle.release()``.
    The flock is released and the fd closed on context exit.
    """

    def __init__(self, fd: int, path: Path) -> None:
        self._fd: int | None = fd
        self._path = path

    async def release(self) -> None:
        """Release the flock and close the fd.

        fd=-1 is the no-op sentinel (Windows dev host); _release_flock_fd
        returns immediately for negative fds.

        Idempotent: a second call is a no-op. This prevents a double-close
        race if release() is called concurrently or __aexit__ races with an
        explicit release() call (the "public API owns the lifetime" pattern
        documented in the class docstring).
        """
        fd = self._fd
        if fd is None:
            return  # already released — no-op
        self._fd = None
        await asyncio.to_thread(_release_flock_fd, fd)

    async def __aenter__(self) -> AsyncFlockHandle:
        return self

    async def __aexit__(self, *_excinfo: object) -> None:
        await self.release()


@contextlib.asynccontextmanager
async def acquire_flock_async(
    path: Path | str,
    *,
    blocking: bool = False,
    write_pid: bool = True,
) -> AsyncIterator[AsyncFlockHandle]:
    """Asyncio-friendly exclusive flock — wraps the blocking acquire in to_thread.

    Use as an async context manager::

        async with acquire_flock_async(path) as handle:
            ...  # flock held here; released on exit

    Converting to @asynccontextmanager eliminates the cancellation-leak window
    that existed with the old ``async with await acquire_flock_async(path)``
    pattern: if the caller is cancelled between the to_thread call returning and
    the coroutine resuming, the finally block in the context manager guarantees
    the handle is released regardless.

    Args:
        path:      Lock file path.
        blocking:  If False (default), raises StateStoreLocked on contention.
        write_pid: Write holder PID to file for operational debugging.

    Lock acquisition order (mandatory — see module docstring):
      asyncio.Lock first, flock second.
    """
    handle = await asyncio.to_thread(_enter_flock_for_async, path, blocking, write_pid)
    try:
        yield handle
    finally:
        await handle.release()
