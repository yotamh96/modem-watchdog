"""Unit tests for atomic.py + paths.py + errors.py.

Tests cover:
  - atomic_write_bytes: atomicity, no tmp remnants, overwrite, mode, dir fsync,
    interruption simulation, random nonce, and the text wrapper.
  - paths.py: env-var overrides, safe usb_path validation.
  - errors.py: structured attributes on exception classes.

Platform note: directory fsync (step 6 of the atomic-write recipe) is a POSIX-only
operation. Tests that verify dir-fsync are skipped on Windows. The production target
is always Linux (Jetson Orin NX); the Windows skip is a dev-host accommodation.
"""

from __future__ import annotations

import os
import platform
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from spark_modem.state_store.atomic import atomic_write_bytes, atomic_write_text
from spark_modem.state_store.errors import (
    AtomicWriteFailed,
    StateStoreError,
    StateStoreLocked,
    UsbPathMismatch,
)
from spark_modem.state_store.paths import (
    globals_path,
    identity_map_path,
    lockfile_for_modem,
    pid_lockfile,
    run_dir,
    state_by_usb_dir,
    state_file_for_modem,
    state_root,
    state_store_lockfile,
)

IS_POSIX = platform.system() != "Windows"


# ---------------------------------------------------------------------------
# paths.py tests
# ---------------------------------------------------------------------------


def test_state_file_for_modem_path(tmp_path: Path) -> None:
    """state_file_for_modem returns state/by-usb/<usb_path>.json."""
    p = state_file_for_modem("2-3.1.1", root=tmp_path)
    assert p == tmp_path / "state" / "by-usb" / "2-3.1.1.json"


def test_state_file_for_modem_rejects_slash(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid usb_path"):
        state_file_for_modem("2-3.1.1/evil", root=tmp_path)


def test_state_file_for_modem_rejects_dotdot(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid usb_path"):
        state_file_for_modem("../evil", root=tmp_path)


def test_state_file_for_modem_rejects_empty(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid usb_path"):
        state_file_for_modem("", root=tmp_path)


def test_state_root_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SPARK_MODEM_STATE_ROOT", str(tmp_path))
    assert state_root() == tmp_path


def test_run_dir_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SPARK_MODEM_RUN_DIR", str(tmp_path))
    assert run_dir() == tmp_path


def test_lockfile_for_modem(tmp_path: Path) -> None:
    p = lockfile_for_modem("2-3.1.1", run=tmp_path)
    assert p.name == "modem-2-3.1.1.lock"
    assert p.parent == tmp_path


def test_pid_lockfile_separate_from_state_lock(tmp_path: Path) -> None:
    pid = pid_lockfile(run=tmp_path)
    state = state_store_lockfile(run=tmp_path)
    assert pid != state
    assert pid.name == "lock"
    assert state.name == "state.lock"


def test_identity_map_path(tmp_path: Path) -> None:
    p = identity_map_path(root=tmp_path)
    assert p == tmp_path / "identity.json"


def test_globals_path(tmp_path: Path) -> None:
    p = globals_path(root=tmp_path)
    assert p == tmp_path / "globals.json"


def test_state_by_usb_dir(tmp_path: Path) -> None:
    p = state_by_usb_dir(root=tmp_path)
    assert p == tmp_path / "state" / "by-usb"


# ---------------------------------------------------------------------------
# errors.py tests
# ---------------------------------------------------------------------------


def test_usb_path_mismatch_attributes() -> None:
    exc = UsbPathMismatch(
        file_usb_path="2-3.1.1",
        sysfs_usb_path="2-3.1.2",
        cdc_wdm="cdc-wdm0",
        file_path="/var/lib/.../2-3.1.1.json",
    )
    assert exc.file_usb_path == "2-3.1.1"
    assert exc.sysfs_usb_path == "2-3.1.2"
    assert exc.cdc_wdm == "cdc-wdm0"
    assert isinstance(exc, StateStoreError)


def test_state_store_locked_attributes() -> None:
    exc = StateStoreLocked(holder_pid=1234, lock_path="/run/spark/state.lock")
    assert exc.holder_pid == 1234
    assert exc.lock_path == "/run/spark/state.lock"
    assert isinstance(exc, StateStoreError)


def test_state_store_locked_unknown_holder() -> None:
    exc = StateStoreLocked(holder_pid=None, lock_path="/run/spark/state.lock")
    assert exc.holder_pid is None
    assert "unknown" in str(exc).lower()


def test_atomic_write_failed_attributes() -> None:
    cause = OSError("disk full")
    exc = AtomicWriteFailed(
        target_path="/var/lib/.../2-3.1.1.json",
        reason="OSError",
        original_exception=cause,
    )
    assert exc.target_path == "/var/lib/.../2-3.1.1.json"
    assert exc.original_exception is cause
    assert isinstance(exc, StateStoreError)


# ---------------------------------------------------------------------------
# atomic.py tests
# ---------------------------------------------------------------------------


def test_atomic_write_bytes_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "a.json"
    atomic_write_bytes(target, b'{"key": "val"}')
    assert target.exists()
    assert target.read_bytes() == b'{"key": "val"}'


def test_atomic_write_bytes_no_tmp_remnants(tmp_path: Path) -> None:
    target = tmp_path / "a.json"
    atomic_write_bytes(target, b"hello")
    siblings = list(tmp_path.iterdir())
    assert siblings == [target], f"Unexpected siblings: {siblings}"


def test_atomic_write_bytes_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "a.json"
    target.write_bytes(b"old content")
    atomic_write_bytes(target, b"new content")
    assert target.read_bytes() == b"new content"


@pytest.mark.skipif(not IS_POSIX, reason="file mode bits only meaningful on POSIX")
def test_atomic_write_bytes_file_mode(tmp_path: Path) -> None:
    """Default mode is 0o640; umask doesn't widen it (POSIX only)."""
    target = tmp_path / "a.json"
    atomic_write_bytes(target, b"data")
    mode = stat.S_IMODE(target.stat().st_mode)
    # We verify bits: world-write (0o002) and world-read (0o004) are NOT set.
    assert not (mode & 0o002), "world-write bit must not be set"
    assert not (mode & 0o004), "world-read bit must not be set"


@pytest.mark.skipif(not IS_POSIX, reason="directory fsync is POSIX-only")
def test_atomic_write_bytes_fsync_called_twice(tmp_path: Path) -> None:
    """os.fsync is called once for the temp fd and once for the directory fd (POSIX only)."""
    target = tmp_path / "a.json"
    fsync_calls: list[int] = []

    real_fsync = os.fsync

    def spy_fsync(fd: int) -> None:
        fsync_calls.append(fd)
        real_fsync(fd)

    with patch("os.fsync", side_effect=spy_fsync):
        atomic_write_bytes(target, b"data")

    assert len(fsync_calls) == 2, f"Expected 2 fsync calls, got {len(fsync_calls)}"


def test_atomic_write_bytes_interruption_leaves_target_unchanged(tmp_path: Path) -> None:
    """If os.fsync raises, the target file is unchanged (atomicity preserved)."""
    target = tmp_path / "a.json"
    target.write_bytes(b"original")

    def boom(fd: int) -> None:
        raise OSError("simulated disk error")

    with pytest.raises(AtomicWriteFailed), patch("os.fsync", side_effect=boom):
        atomic_write_bytes(target, b"new content")

    # Target unchanged; no .tmp remnants.
    assert target.read_bytes() == b"original"
    tmp_files = [f for f in tmp_path.iterdir() if f != target]
    assert tmp_files == [], f"Unexpected tmp files remain: {tmp_files}"


def test_atomic_write_bytes_random_nonce(tmp_path: Path) -> None:
    """Two consecutive writes use different nonces — tmp filenames never collide."""
    seen_tmp_names: list[str] = []
    real_open = os.open

    def spy_open(path: str, flags: int, mode: int = 0o666) -> int:
        if ".tmp." in path:
            seen_tmp_names.append(path)
        return real_open(path, flags, mode)

    target = tmp_path / "a.json"
    with patch("os.open", side_effect=spy_open):
        atomic_write_bytes(target, b"first")
        atomic_write_bytes(target, b"second")

    assert len(seen_tmp_names) == 2
    assert seen_tmp_names[0] != seen_tmp_names[1], "Nonces must differ between writes"


def test_atomic_write_text_wraps_bytes(tmp_path: Path) -> None:
    target = tmp_path / "hello.json"
    atomic_write_text(target, '{"msg": "hello"}', encoding="utf-8")
    assert target.read_text(encoding="utf-8") == '{"msg": "hello"}'


def test_atomic_write_bytes_missing_parent_raises(tmp_path: Path) -> None:
    target = tmp_path / "nonexistent" / "a.json"
    with pytest.raises(AtomicWriteFailed, match="parent directory"):
        atomic_write_bytes(target, b"data")
