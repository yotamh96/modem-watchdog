"""Tests for SP-03 invariant 1: list-form argv enforcement.

The runner MUST reject:
  - str (would invoke shell semantics)
  - tuple (not a list -- strict, no auto-coercion)
  - empty list
  - list containing non-str elements

And MUST accept a valid list[str].
"""

from __future__ import annotations

import sys

import pytest

from spark_modem.subproc.runner import run

# All runner tests require an asyncio event loop; pytest-asyncio mode=auto handles it.
# POSIX-only tests are skipped on Windows via the skip marker below.
_SKIP_WIN = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Requires POSIX binaries (/bin/echo etc.); production target is Jetson (Linux/aarch64)",
)


@_SKIP_WIN
async def test_str_argv_raises_typeerror() -> None:
    """run('ls /tmp', ...) raises TypeError before any spawn."""
    with pytest.raises(TypeError, match="list\\[str\\]"):
        await run("ls /tmp", timeout_s=1)  # type: ignore[arg-type]


@_SKIP_WIN
async def test_tuple_argv_raises_typeerror() -> None:
    """run(('ls', '/tmp'), ...) raises TypeError -- tuple is not accepted."""
    with pytest.raises(TypeError, match="list\\[str\\]"):
        await run(("ls", "/tmp"), timeout_s=1)  # type: ignore[arg-type]


@_SKIP_WIN
async def test_empty_argv_raises_valueerror() -> None:
    """run([], ...) raises ValueError (empty argv)."""
    with pytest.raises(ValueError, match="empty"):
        await run([], timeout_s=1)


@_SKIP_WIN
async def test_nonstr_element_raises_typeerror() -> None:
    """run(['/bin/echo', 42], ...) raises TypeError on the non-str element."""
    with pytest.raises(TypeError, match="str"):
        await run(["/bin/echo", 42], timeout_s=1)  # type: ignore[list-item]


@_SKIP_WIN
async def test_valid_argv_succeeds() -> None:
    """run(['/bin/echo', 'hi'], timeout_s=1.0) returns exit_code=0 and correct stdout."""
    result = await run(["/bin/echo", "hi"], timeout_s=1.0)
    assert result.exit_code == 0
    assert result.stdout == b"hi\n"
    assert result.succeeded is True


@_SKIP_WIN
async def test_argv_stored_as_tuple_in_result() -> None:
    """The returned CompletedProcess stores argv as a tuple (defensive copy)."""
    result = await run(["/bin/echo", "tuple-check"], timeout_s=1.0)
    assert isinstance(result.argv, tuple)
    assert result.argv == ("/bin/echo", "tuple-check")
