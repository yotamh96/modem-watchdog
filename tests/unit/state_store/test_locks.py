"""Unit tests for locks.py — 3-layer locking model (ADR-0012).

Platform notes:
  - PerModemLockTable and globals_lock tests are platform-independent (asyncio).
  - acquire_flock / acquire_flock_async tests require POSIX (fcntl). On Windows
    the flock tests are marked skipif(not IS_POSIX). The daemon never runs on
    Windows; the skip is a dev-host accommodation.

Tests cover:
  - PerModemLockTable: lazy creation, per-key isolation, concurrency, snapshot.
  - globals_lock(): singleton across calls.
  - acquire_flock(): exclusive lock, PID write, contention raises StateStoreLocked,
    release lets second acquire succeed, blocking acquire waits.
  - acquire_flock_async: asyncio context manager yielding AsyncFlockHandle.
"""

from __future__ import annotations

import asyncio
import os
import platform
import threading
from pathlib import Path

import pytest

import spark_modem.state_store.locks as locks_mod
from spark_modem.state_store.errors import StateStoreLocked
from spark_modem.state_store.locks import (
    AsyncFlockHandle,
    PerModemLockTable,
    acquire_flock,
    acquire_flock_async,
    globals_lock,
)

IS_POSIX = platform.system() != "Windows"

# ---------------------------------------------------------------------------
# PerModemLockTable tests (asyncio, platform-independent)
# ---------------------------------------------------------------------------


def test_per_modem_lock_table_starts_empty() -> None:
    table = PerModemLockTable()
    assert table.usb_paths() == ()


def test_per_modem_lock_table_creates_lock_lazily() -> None:
    table = PerModemLockTable()
    lock = table.get("2-3.1.1")
    assert isinstance(lock, asyncio.Lock)


def test_per_modem_lock_table_same_key_same_instance() -> None:
    table = PerModemLockTable()
    lock_a = table.get("2-3.1.1")
    lock_b = table.get("2-3.1.1")
    assert lock_a is lock_b


def test_per_modem_lock_table_different_keys_different_instances() -> None:
    table = PerModemLockTable()
    lock_a = table.get("2-3.1.1")
    lock_b = table.get("2-3.1.2")
    assert lock_a is not lock_b


async def test_per_modem_lock_table_serializes_same_key() -> None:
    """Two coroutines on the same key must serialize."""
    table = PerModemLockTable()
    order: list[str] = []

    async def task_a() -> None:
        async with table.get("2-3.1.1"):
            order.append("a-start")
            await asyncio.sleep(0.01)
            order.append("a-end")

    async def task_b() -> None:
        # Give task_a a head start.
        await asyncio.sleep(0)
        async with table.get("2-3.1.1"):
            order.append("b-start")

    await asyncio.gather(task_a(), task_b())
    # task_b must not start before task_a ends.
    assert order == ["a-start", "a-end", "b-start"]


async def test_per_modem_lock_table_different_keys_do_not_block() -> None:
    """Two coroutines on different keys run in parallel."""
    table = PerModemLockTable()
    order: list[str] = []

    async def task_a() -> None:
        async with table.get("2-3.1.1"):
            order.append("a-start")
            await asyncio.sleep(0.01)
            order.append("a-end")

    async def task_b() -> None:
        await asyncio.sleep(0)
        async with table.get("2-3.1.2"):
            order.append("b-start")
            await asyncio.sleep(0)
            order.append("b-end")

    await asyncio.gather(task_a(), task_b())
    # b-start should appear before a-end (parallel execution).
    assert order.index("b-start") < order.index("a-end")


def test_per_modem_lock_table_usb_paths_snapshot() -> None:
    table = PerModemLockTable()
    table.get("2-3.1.3")
    table.get("2-3.1.1")
    table.get("2-3.1.2")
    assert table.usb_paths() == ("2-3.1.1", "2-3.1.2", "2-3.1.3")


# ---------------------------------------------------------------------------
# globals_lock() singleton test (asyncio, platform-independent)
# ---------------------------------------------------------------------------


def test_globals_lock_is_singleton() -> None:
    """globals_lock() must return the same asyncio.Lock instance on every call."""
    # Reset singleton so this test is isolated.
    locks_mod._GLOBALS_LOCK_SINGLETON = None  # type: ignore[attr-defined]

    lock_a = globals_lock()
    lock_b = globals_lock()
    assert lock_a is lock_b
    assert isinstance(lock_a, asyncio.Lock)


# ---------------------------------------------------------------------------
# flock tests — POSIX only
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not IS_POSIX, reason="fcntl / flock is POSIX-only")
def test_acquire_flock_creates_file_and_acquires(tmp_path: Path) -> None:
    lock_path = tmp_path / "test.lock"
    with acquire_flock(lock_path):
        assert lock_path.exists()


@pytest.mark.skipif(not IS_POSIX, reason="fcntl / flock is POSIX-only")
def test_acquire_flock_writes_pid(tmp_path: Path) -> None:
    lock_path = tmp_path / "test.lock"
    with acquire_flock(lock_path, write_pid=True):
        content = lock_path.read_text(encoding="ascii").strip()
        assert content == str(os.getpid())


@pytest.mark.skipif(not IS_POSIX, reason="fcntl / flock is POSIX-only")
def test_acquire_flock_contention_raises_state_store_locked(tmp_path: Path) -> None:
    """A second non-blocking acquire while first is held raises StateStoreLocked."""
    lock_path = tmp_path / "test.lock"
    with acquire_flock(lock_path):  # noqa: SIM117 — three levels; inner is what raises
        with pytest.raises(StateStoreLocked) as excinfo:
            with acquire_flock(lock_path):
                pass
    assert excinfo.value.lock_path == str(lock_path)


@pytest.mark.skipif(not IS_POSIX, reason="fcntl / flock is POSIX-only")
def test_acquire_flock_release_allows_second_acquire(tmp_path: Path) -> None:
    """After the first context manager exits, a second acquire succeeds."""
    lock_path = tmp_path / "test.lock"
    with acquire_flock(lock_path):
        pass
    # Should not raise.
    with acquire_flock(lock_path):
        assert lock_path.exists()


@pytest.mark.skipif(not IS_POSIX, reason="fcntl / flock is POSIX-only")
def test_acquire_flock_blocking_waits_for_release(tmp_path: Path) -> None:
    """blocking=True waits for the holder to release; completes within 1s."""
    lock_path = tmp_path / "test.lock"
    results: list[str] = []
    ready_event = threading.Event()

    def holder() -> None:
        with acquire_flock(lock_path, blocking=False):
            results.append("holder-acquired")
            ready_event.set()
            # Hold for 100 ms.
            threading.Event().wait(timeout=0.1)
        results.append("holder-released")

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    ready_event.wait(timeout=2.0)

    # Now try blocking acquire — should wait until holder exits.
    with acquire_flock(lock_path, blocking=True):
        results.append("waiter-acquired")

    t.join(timeout=2.0)
    assert results == ["holder-acquired", "holder-released", "waiter-acquired"]


@pytest.mark.skipif(not IS_POSIX, reason="fcntl / flock is POSIX-only")
async def test_acquire_flock_async_returns_handle(tmp_path: Path) -> None:
    """acquire_flock_async is a context manager that yields AsyncFlockHandle."""
    lock_path = tmp_path / "async.lock"
    async with acquire_flock_async(lock_path) as handle:
        assert isinstance(handle, AsyncFlockHandle)
    # After exit the lock file should exist and be re-acquirable.
    assert lock_path.exists()


@pytest.mark.skipif(not IS_POSIX, reason="fcntl / flock is POSIX-only")
async def test_acquire_flock_async_context_manager(tmp_path: Path) -> None:
    """acquire_flock_async releases the flock on context-manager exit."""
    lock_path = tmp_path / "async.lock"
    async with acquire_flock_async(lock_path):
        assert lock_path.exists()
    # After exit, a second acquire should succeed.
    async with acquire_flock_async(lock_path):
        pass


@pytest.mark.skipif(not IS_POSIX, reason="fcntl / flock is POSIX-only")
async def test_acquire_flock_async_contention_raises(tmp_path: Path) -> None:
    """async non-blocking acquire raises StateStoreLocked when flock is held."""
    lock_path = tmp_path / "async.lock"
    async with acquire_flock_async(lock_path, blocking=False):
        with pytest.raises(StateStoreLocked):
            async with acquire_flock_async(lock_path, blocking=False):
                pass
