"""Atomic file writes — temp + fsync + rename + directory fsync.

FR-62: every persistent file write is atomic. CLAUDE.md §"Critical
invariants" #5: temp + rename + directory fsync; never partial-write.

Recipe (PITFALLS §3.x; POSIX semantics):
  1. Open <target>.tmp.<nonce> with O_CREAT|O_WRONLY|O_EXCL, mode=0o640.
  2. Write all bytes.
  3. os.fsync(fd_temp).
  4. Close fd_temp.
  5. os.replace(temp, target) — atomic on POSIX (same filesystem).
  6. os.fsync(directory_fd) — durability across crash; rename is durable
     only after the dir's metadata is sync'd.
  7. Close directory_fd.

The nonce (secrets.token_hex) ensures concurrent writers never collide
on the same .tmp filename (T-04-01; vanishingly improbable but insured).
"""

from __future__ import annotations

import contextlib
import os
import secrets
from pathlib import Path

from spark_modem.state_store.errors import AtomicWriteFailed

_DEFAULT_MODE = 0o640


def _write_and_fsync_temp(
    tmp_path: Path,
    data: bytes,
    mode: int,
    target_path: Path,
) -> AtomicWriteFailed | None:
    """Open a temp file, write data, fsync, and close it.

    Returns an AtomicWriteFailed if anything goes wrong; None on success.
    The fd is always closed before returning so the caller can safely delete
    the tmp file on failure (Windows requires no open handles before unlink).
    """
    fd_temp: int | None = None
    write_error: AtomicWriteFailed | None = None
    try:
        fd_temp = os.open(
            str(tmp_path),
            os.O_CREAT | os.O_WRONLY | os.O_EXCL,
            mode,
        )
        written = os.write(fd_temp, data)
        if written != len(data):
            write_error = AtomicWriteFailed(
                target_path=str(target_path),
                reason=f"short write: {written} of {len(data)} bytes",
            )
        else:
            try:
                os.fsync(fd_temp)
            except OSError as e:
                write_error = AtomicWriteFailed(
                    target_path=str(target_path),
                    reason=f"OSError during temp fsync: {e!r}",
                    original_exception=e,
                )
    except OSError as e:
        write_error = AtomicWriteFailed(
            target_path=str(target_path),
            reason=f"OSError during temp write: {e!r}",
            original_exception=e,
        )
    finally:
        # Always close before returning — on Windows the file cannot be deleted
        # or renamed while any handle is open.
        if fd_temp is not None:
            with contextlib.suppress(OSError):
                os.close(fd_temp)
    return write_error


def _fsync_directory(target_dir: Path, target_path: Path) -> None:
    """Fsync the directory containing the target file (POSIX-only).

    On POSIX, ``os.rename`` / ``os.replace`` is durable only after the
    directory's metadata is synced. On Windows, opening a directory fd raises
    ``PermissionError`` — we skip the step there since the daemon never runs
    on Windows (Jetson Orin NX / Linux is the sole production target).
    """
    if not hasattr(os, "O_DIRECTORY"):
        # Windows: no directory-fd support; skip.
        return
    dir_fd: int | None = None
    try:
        dir_fd = os.open(str(target_dir), os.O_RDONLY)
        os.fsync(dir_fd)
    except OSError as e:
        raise AtomicWriteFailed(
            target_path=str(target_path),
            reason=f"OSError during directory fsync: {e!r}",
            original_exception=e,
        ) from e
    finally:
        if dir_fd is not None:
            with contextlib.suppress(OSError):
                os.close(dir_fd)


def atomic_write_bytes(
    target: Path | str,
    data: bytes,
    *,
    mode: int = _DEFAULT_MODE,
) -> None:
    """Write ``data`` to ``target`` atomically. Never leaves a partial file.

    On any failure, raises :class:`AtomicWriteFailed` and ensures the target
    file (if it existed before) is unchanged.

    ``mode`` is passed directly to ``os.open`` — set it to 0o640 (default) for
    state files so only root can read/write them and the group can read.
    """
    target_path = Path(target)
    target_dir = target_path.parent
    if not target_dir.is_dir():
        raise AtomicWriteFailed(
            target_path=str(target_path),
            reason=f"parent directory {str(target_dir)!r} does not exist",
        )

    nonce = secrets.token_hex(8)
    tmp_path = target_dir / f".{target_path.name}.tmp.{nonce}"

    # Steps 1-4: write + fsync the temp file; fd closed before we touch tmp_path again.
    write_error = _write_and_fsync_temp(tmp_path, data, mode, target_path)
    if write_error is not None:
        with contextlib.suppress(OSError):
            tmp_path.unlink()
        raise write_error

    # Step 5: atomic replace.
    # os.replace() works on both POSIX (atomic rename) and Windows (replace).
    try:
        tmp_path.replace(target_path)
    except OSError as e:
        with contextlib.suppress(OSError):
            tmp_path.unlink()
        raise AtomicWriteFailed(
            target_path=str(target_path),
            reason=f"OSError during replace: {e!r}",
            original_exception=e,
        ) from e

    # Step 6: directory fsync (POSIX only).
    _fsync_directory(target_dir, target_path)


def atomic_write_text(
    target: Path | str,
    text: str,
    *,
    mode: int = _DEFAULT_MODE,
    encoding: str = "utf-8",
) -> None:
    """Convenience wrapper for :func:`atomic_write_bytes` with text input."""
    atomic_write_bytes(target, text.encode(encoding), mode=mode)
