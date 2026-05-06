"""Tests for SP-03 invariant 2: locale baseline (LC_ALL=C, LANG=C).

The runner MUST inject LC_ALL=C and LANG=C into the child's environment
unless the caller explicitly overrides them via env=.
"""

from __future__ import annotations

import sys

import pytest

from spark_modem.subproc.runner import run

_SKIP_WIN = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Requires /usr/bin/env POSIX binary; production target is Jetson (Linux/aarch64)",
)


def _parse_env_output(stdout: bytes) -> dict[str, str]:
    """Parse `env` output (KEY=VALUE lines) into a dict."""
    result: dict[str, str] = {}
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            result[key] = value
    return result


@_SKIP_WIN
async def test_locale_baseline_injected() -> None:
    """LC_ALL=C and LANG=C appear in the child environment by default."""
    result = await run(["/usr/bin/env"], timeout_s=2.0)
    assert result.succeeded, f"env failed: {result.stderr!r}"
    env = _parse_env_output(result.stdout)
    assert env.get("LC_ALL") == "C", f"LC_ALL not set to C; got: {env.get('LC_ALL')!r}"
    assert env.get("LANG") == "C", f"LANG not set to C; got: {env.get('LANG')!r}"


@_SKIP_WIN
async def test_caller_lc_all_override_wins() -> None:
    """Caller-provided env with LC_ALL=en_US.UTF-8 overrides the baseline."""
    result = await run(
        ["/usr/bin/env"],
        timeout_s=2.0,
        env={"LC_ALL": "en_US.UTF-8", "PATH": "/usr/bin:/bin"},
    )
    assert result.succeeded, f"env failed: {result.stderr!r}"
    env = _parse_env_output(result.stdout)
    assert env.get("LC_ALL") == "en_US.UTF-8", (
        f"Expected LC_ALL=en_US.UTF-8, got: {env.get('LC_ALL')!r}"
    )


@_SKIP_WIN
async def test_caller_env_without_lang_gets_baseline_lang() -> None:
    """Caller env without LANG still gets LANG=C injected by the runner."""
    # Provide env without LANG -- runner should inject LANG=C.
    result = await run(
        ["/usr/bin/env"],
        timeout_s=2.0,
        env={"LC_ALL": "en_US.UTF-8", "PATH": "/usr/bin:/bin"},
    )
    assert result.succeeded, f"env failed: {result.stderr!r}"
    env = _parse_env_output(result.stdout)
    # LANG should have the baseline value since caller didn't set it.
    assert env.get("LANG") == "C", f"Expected LANG=C (baseline), got: {env.get('LANG')!r}"


@_SKIP_WIN
async def test_caller_lang_override_wins() -> None:
    """Caller-provided LANG takes precedence over the baseline."""
    result = await run(
        ["/usr/bin/env"],
        timeout_s=2.0,
        env={"LANG": "en_US.UTF-8", "PATH": "/usr/bin:/bin"},
    )
    assert result.succeeded, f"env failed: {result.stderr!r}"
    env = _parse_env_output(result.stdout)
    assert env.get("LANG") == "en_US.UTF-8", (
        f"Expected LANG=en_US.UTF-8 (caller override), got: {env.get('LANG')!r}"
    )
    # LC_ALL not in caller env -> should get baseline C
    assert env.get("LC_ALL") == "C", f"Expected LC_ALL=C (baseline), got: {env.get('LC_ALL')!r}"
