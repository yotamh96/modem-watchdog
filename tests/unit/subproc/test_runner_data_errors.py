"""Tests for SP-02 'all errors are data' model.

Non-zero exit codes and stderr output are data in CompletedProcess, NOT
exceptions. Only genuine runtime breakage (binary not on PATH, spawn OSError)
raises an exception.

Also tests: stdin delivery, duration_monotonic, binary-not-found.
"""

from __future__ import annotations

import sys

import pytest

from spark_modem.subproc.runner import run

_SKIP_WIN = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Requires POSIX binaries (/bin/false, /bin/cat etc.); production target is Jetson",
)


@_SKIP_WIN
async def test_nonzero_exit_returns_data_not_exception() -> None:
    """run(['/bin/false'], ...) returns CompletedProcess with exit_code=1, not exception."""
    result = await run(["/bin/false"], timeout_s=1.0)
    assert result.exit_code == 1
    assert result.timed_out is False
    assert result.failed is True
    assert result.succeeded is False


@_SKIP_WIN
async def test_stderr_and_exit_code_captured() -> None:
    """exit code 7 and stderr 'bad\\n' are captured as data."""
    result = await run(
        ["/bin/sh", "-c", "echo bad >&2; exit 7"],
        timeout_s=1.0,
    )
    assert result.exit_code == 7
    assert result.stderr == b"bad\n"
    assert result.stdout == b""
    assert result.timed_out is False


@_SKIP_WIN
async def test_missing_binary_raises_filenotfounderror() -> None:
    """run(['/this/binary/does/not/exist'], ...) raises FileNotFoundError (unwrapped)."""
    with pytest.raises(FileNotFoundError):
        await run(["/this/binary/does/not/exist"], timeout_s=1.0)


@_SKIP_WIN
async def test_stdin_delivered_to_cat() -> None:
    """stdin bytes are delivered to the child; cat echoes them back on stdout."""
    result = await run(["/bin/cat"], timeout_s=1.0, stdin=b"piped data")
    assert result.succeeded
    assert result.stdout == b"piped data"


@_SKIP_WIN
async def test_stdin_ignored_by_echo() -> None:
    """echo ignores stdin; the call still succeeds without error."""
    result = await run(["/bin/echo", "hello"], timeout_s=1.0, stdin=b"unused")
    assert result.succeeded
    assert result.stdout == b"hello\n"


@_SKIP_WIN
async def test_duration_monotonic_positive() -> None:
    """duration_monotonic is >= 0 and < 1.0 for a fast command like echo."""
    result = await run(["/bin/echo", "timing"], timeout_s=1.0)
    assert result.duration_monotonic >= 0
    assert result.duration_monotonic < 1.0, (
        f"Expected duration < 1.0s for echo, got: {result.duration_monotonic:.3f}s"
    )


@_SKIP_WIN
async def test_stdout_captured_as_bytes() -> None:
    """stdout is returned as raw bytes (no decode); stderr likewise."""
    result = await run(["/bin/echo", "bytes-check"], timeout_s=1.0)
    assert isinstance(result.stdout, bytes)
    assert isinstance(result.stderr, bytes)
    assert result.stdout == b"bytes-check\n"
