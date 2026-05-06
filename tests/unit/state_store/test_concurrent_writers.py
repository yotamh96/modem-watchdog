"""Regression tests for daemon-vs-CLI lost-update prevention (WARN-3).

These tests simulate a CLI mutator holding the per-modem flock while the daemon
attempts to save. Using threading.Thread (not multiprocessing) to acquire the
flock from a non-asyncio context (the simulated CLI mutator side), then calling
store.save_modem_state from the asyncio event loop.

Platform note: flock is POSIX-only (fcntl). All tests in this file skip on Windows.

Tests:
  - Non-blocking save raises StateStoreLocked when flock is held.
  - Blocking save waits for release (within 1s) and completes.
  - Same pattern for save_globals against the state-store lock.

Closes must_have: "regression test simulating a CLI mutator holding the per-modem
flock; asserts StateStore.save_modem_state surfaces StateStoreLocked (non-blocking)
or waits (blocking) — daemon-vs-CLI lost-update prevention is wired, not just
exposed as a primitive."
"""

from __future__ import annotations

import asyncio
import contextlib
import errno
import os
import platform
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from spark_modem.state_store.errors import StateStoreLocked
from spark_modem.state_store.store import StateStore
from spark_modem.wire.globals import GlobalsState
from spark_modem.wire.state import ModemState

if TYPE_CHECKING or sys.platform != "win32":
    import fcntl

IS_POSIX = platform.system() != "Windows"

# All tests in this file are POSIX-only.
pytestmark = pytest.mark.skipif(not IS_POSIX, reason="flock is POSIX-only")


def _make_store(tmp_path: Path) -> StateStore:
    return StateStore(
        state_root_override=tmp_path / "state",
        run_dir_override=tmp_path / "run",
    )


def _modem_state() -> ModemState:
    return ModemState(
        state="unknown",
        present=True,
        rf_blocked=False,
        recovering_level=None,
        healthy_streak=0,
        counters={},
        last_action_monotonic=None,
        last_state_transition_iso=None,
    )


def _hold_flock(lock_path: Path, ready: threading.Event, release: threading.Event) -> None:
    """Thread target: acquire lock_path exclusively, signal ready, wait for release."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o640)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[name-defined]
    except OSError as e:
        if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
            os.close(fd)
            return
        raise
    try:
        ready.set()
        release.wait(timeout=5.0)
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)  # type: ignore[name-defined]
        with contextlib.suppress(OSError):
            os.close(fd)


# ---------------------------------------------------------------------------
# Per-modem flock — non-blocking (StateStoreLocked)
# ---------------------------------------------------------------------------


async def test_save_modem_state_non_blocking_raises_when_flock_held(
    tmp_path: Path,
) -> None:
    """Non-blocking save raises StateStoreLocked when CLI mutator holds the flock."""
    store = _make_store(tmp_path)
    # Ensure the run dir exists before the thread starts.
    (tmp_path / "run").mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "run" / "modem-2-3.1.1.lock"

    ready = threading.Event()
    release = threading.Event()
    holder = threading.Thread(target=_hold_flock, args=(lock_path, ready, release), daemon=True)
    holder.start()
    ready.wait(timeout=2.0)

    try:
        with pytest.raises(StateStoreLocked) as excinfo:
            await store.save_modem_state("2-3.1.1", _modem_state(), wait_for_flock=False)
        assert excinfo.value.lock_path == str(lock_path)
    finally:
        release.set()
        holder.join(timeout=2.0)


# ---------------------------------------------------------------------------
# Per-modem flock — blocking (waits for release)
# ---------------------------------------------------------------------------


async def test_save_modem_state_blocking_waits_for_flock_release(
    tmp_path: Path,
) -> None:
    """Blocking save waits for the CLI holder to release; completes within 1s."""
    store = _make_store(tmp_path)
    (tmp_path / "run").mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "run" / "modem-2-3.1.1.lock"

    ready = threading.Event()
    release = threading.Event()
    holder = threading.Thread(target=_hold_flock, args=(lock_path, ready, release), daemon=True)
    holder.start()
    ready.wait(timeout=2.0)

    # Release the CLI holder after 100ms.
    async def _release_after_delay() -> None:
        await asyncio.sleep(0.1)
        release.set()

    task = asyncio.ensure_future(_release_after_delay())

    # Blocking save — must complete within 1s once holder releases.
    async with asyncio.timeout(1.0):
        await store.save_modem_state("2-3.1.1", _modem_state(), wait_for_flock=True)

    await task
    holder.join(timeout=2.0)

    # State file must exist after save.
    by_usb = tmp_path / "state" / "state" / "by-usb"
    assert (by_usb / "2-3.1.1.json").exists()


# ---------------------------------------------------------------------------
# State-store flock (globals) — non-blocking
# ---------------------------------------------------------------------------


async def test_save_globals_non_blocking_raises_when_flock_held(
    tmp_path: Path,
) -> None:
    """Non-blocking save_globals raises StateStoreLocked when CLI mutator holds state.lock."""
    store = _make_store(tmp_path)
    (tmp_path / "run").mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "run" / "state.lock"

    ready = threading.Event()
    release = threading.Event()
    holder = threading.Thread(target=_hold_flock, args=(lock_path, ready, release), daemon=True)
    holder.start()
    ready.wait(timeout=2.0)

    try:
        with pytest.raises(StateStoreLocked) as excinfo:
            await store.save_globals(GlobalsState(), wait_for_flock=False)
        assert excinfo.value.lock_path == str(lock_path)
    finally:
        release.set()
        holder.join(timeout=2.0)


# ---------------------------------------------------------------------------
# State-store flock (globals) — blocking
# ---------------------------------------------------------------------------


async def test_save_globals_blocking_waits_for_flock_release(tmp_path: Path) -> None:
    """Blocking save_globals waits for the holder to release; completes within 1s."""
    store = _make_store(tmp_path)
    (tmp_path / "run").mkdir(parents=True, exist_ok=True)
    lock_path = tmp_path / "run" / "state.lock"

    ready = threading.Event()
    release = threading.Event()
    holder = threading.Thread(target=_hold_flock, args=(lock_path, ready, release), daemon=True)
    holder.start()
    ready.wait(timeout=2.0)

    async def _release_after_delay() -> None:
        await asyncio.sleep(0.1)
        release.set()

    task = asyncio.ensure_future(_release_after_delay())

    async with asyncio.timeout(1.0):
        await store.save_globals(GlobalsState(), wait_for_flock=True)

    await task
    holder.join(timeout=2.0)

    state_dir = tmp_path / "state"
    assert (state_dir / "globals.json").exists()
