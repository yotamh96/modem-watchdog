"""Single async subprocess runner -- the SP-04 anchor module.

The ONLY place create_subprocess_exec / os.killpg appear in src/spark_modem/.
scripts/lint_no_subprocess.sh enforces this; no other module is allowed to spawn.

SP-03 invariants (all always-on):
  1. list-form argv only            (FR-64 / NFR-31; TypeError on str/tuple)
  2. LC_ALL=C, LANG=C baseline      (PITFALLS §1.3 -- locale drift prevention)
  3. start_new_session=True         (cpython#127049 -- kill the whole process group)
  4. two-stage shutdown on timeout  (SIGTERM -> 2s -> SIGKILL -> drain)

asyncio.timeout() (context manager) -- NOT wait_for around communicate.
cpython#139373: wait_for cancels mid-communicate and the in-flight stdout is
lost. The two-stage drain is critical: after SIGKILL, a SECOND proc.communicate()
is issued to recover whatever the child flushed before dying.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
import time
from typing import Final

from spark_modem.subproc.errors import SubprocSpawnError
from spark_modem.subproc.result import CompletedProcess

# PITFALLS §1.3 -- locale baseline prevents qmicli/ip output surprises.
_LOCALE_BASELINE: Final[dict[str, str]] = {"LC_ALL": "C", "LANG": "C"}

# SP-03 step 4 -- wait this long after SIGTERM before escalating to SIGKILL.
_SIGTERM_GRACE_SECONDS: Final[float] = 2.0

# Hard upper bound on the post-SIGKILL communicate() drain (WR-004).
# Worst-case run() duration is timeout_s + _SIGTERM_GRACE_SECONDS + _SIGKILL_DRAIN_SECONDS.
# Matches _SIGTERM_GRACE_SECONDS so M5 (P99 cycle ≤10s) has a deterministic budget.
_SIGKILL_DRAIN_SECONDS: Final[float] = 2.0

# STACK §"qmicli subprocess" -- chatty 5G output; stdout buffer ~1 MiB.
_STDOUT_LIMIT: Final[int] = 1024 * 1024

# POSIX signal numbers used in two-stage shutdown.  On Windows these attributes
# may not exist on the signal module, so we use integer literals which are
# portable in os.killpg() calls on POSIX and in proc.send_signal() on Windows.
# SIGTERM = 15, SIGKILL = 9 (POSIX-standard; not available on Windows signal module).
_SIGTERM: Final[int] = int(signal.SIGTERM)  # always defined (signal.SIGTERM exists on Windows)
_SIGKILL: Final[int] = 9  # signal.SIGKILL absent from Windows signal stubs


def _validate_argv(argv: object) -> list[str]:
    """SP-03 invariant 1: list-form argv only. Strict -- no tuple, no str.

    Raises:
        TypeError: if argv is not a list[str] (includes str, tuple, etc.)
        ValueError: if argv is an empty list, argv[0] is empty, or any
                    element contains a NUL byte (POSIX execve rejects NUL).
    """
    if not isinstance(argv, list):
        raise TypeError(
            f"subproc.run: argv must be a list[str]; got {type(argv).__name__} "
            f"(value={argv!r}). Pass arguments as a list to prevent shell injection "
            f"(FR-64 / NFR-31)."
        )
    if not argv:
        raise ValueError("subproc.run: argv must not be empty.")
    for i, a in enumerate(argv):
        if not isinstance(a, str):
            raise TypeError(f"subproc.run: argv[{i}] must be str; got {type(a).__name__} ({a!r}).")
        if "\x00" in a:
            raise ValueError(
                f"subproc.run: argv[{i}] contains a NUL byte; "
                "POSIX execve(2) rejects NUL in arguments."
            )
    if not argv[0]:
        raise ValueError(
            "subproc.run: argv[0] (the executable) must be a non-empty string; "
            "an empty string produces a confusing ENOENT from the kernel."
        )
    return list(argv)  # defensive copy


def _build_env(caller_env: dict[str, str] | None) -> dict[str, str]:
    """Merge caller env over the locale baseline.

    If the caller did not pass an env=, we inherit os.environ and overlay the
    locale baseline (so non-locale env vars like PATH and HOME come from the
    parent process, and locale is forced to C).

    If the caller DID pass an env=, we treat it as authoritative for the keys
    it sets, but still inject LC_ALL=C and LANG=C for any key the caller did
    not explicitly set. An explicit ``env={"LC_ALL": "en_US.UTF-8"}`` wins.
    """
    merged = dict(os.environ) if caller_env is None else dict(caller_env)
    for k, v in _LOCALE_BASELINE.items():
        merged.setdefault(k, v)
    return merged


async def run(
    argv: list[str],
    *,
    timeout_s: float,
    stdin: bytes | None = None,
    env: dict[str, str] | None = None,
) -> CompletedProcess:
    """Run argv as a subprocess and return a CompletedProcess.

    Per SP-02 'all errors are data', this function returns CompletedProcess
    for any terminating outcome. It raises ONLY on genuinely-broken-runtime
    conditions:
      - argv not a list       -> TypeError
      - argv is empty         -> ValueError
      - binary not on PATH    -> FileNotFoundError (un-wrapped; standard idiom)
      - other OSError on spawn -> SubprocSpawnError (subclass of OSError)

    Args:
        argv: Command and arguments as a list of strings. Must be list[str];
              str or tuple raises TypeError before spawn (FR-64 / NFR-31).
        timeout_s: Wall-clock seconds before the two-stage shutdown fires.
        stdin: Bytes to write to the child's stdin pipe, or None for DEVNULL.
        env: Override environment for the child. The locale baseline
             (LC_ALL=C, LANG=C) is injected for any key the caller doesn't set.
             None means inherit os.environ + locale baseline.

    Returns:
        CompletedProcess with argv, exit_code, stdout, stderr,
        duration_monotonic, timed_out, and kill_signal.
    """
    argv_list = _validate_argv(argv)
    merged_env = _build_env(env)
    start_monotonic = time.monotonic()

    # Spawn -- SP-03 invariant 3: start_new_session=True so we own the process group.
    try:
        # NOTE: this is the ONLY create_subprocess_exec call in src/spark_modem/.
        # SP-04 lint gate (scripts/lint_no_subprocess.sh) excludes this directory.
        proc = await asyncio.create_subprocess_exec(
            *argv_list,
            stdin=asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env,
            start_new_session=True,
            limit=_STDOUT_LIMIT,
        )
    except FileNotFoundError:
        # Standard idiom: caller catches FileNotFoundError to detect 'binary missing'.
        # Do NOT wrap in SubprocSpawnError -- FileNotFoundError is its own contract.
        raise
    except OSError as e:
        raise SubprocSpawnError(argv_list, e) from e

    timed_out = False
    kill_signal_used: int | None = None
    stdout = b""
    stderr = b""

    try:
        # SP-03 invariant 4 -- asyncio.timeout() context manager, NOT wait_for.
        # cpython#139373: wait_for cancels mid-communicate, in-flight stdout is lost.
        async with asyncio.timeout(timeout_s):
            stdout, stderr = await proc.communicate(input=stdin)
    except TimeoutError:
        # Two-stage shutdown: SIGTERM, wait grace, SIGKILL, drain.
        timed_out = True
        stdout, stderr = await _two_stage_shutdown(proc)
        # Determine which signal actually reaped the process.
        if proc.returncode is not None and proc.returncode < 0:
            kill_signal_used = -proc.returncode
        else:
            # Unusual: proc reaped with non-negative returncode despite timeout.
            kill_signal_used = None

    duration = time.monotonic() - start_monotonic

    # exit_code: positive on normal exit, negative (-signal_number) when killed.
    exit_code = proc.returncode if proc.returncode is not None else -1

    return CompletedProcess.make(
        argv=argv_list,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_monotonic=duration,
        timed_out=timed_out,
        kill_signal=kill_signal_used,
    )


async def _two_stage_shutdown(
    proc: asyncio.subprocess.Process,
) -> tuple[bytes, bytes]:
    """SP-03 invariant 4: SIGTERM -> wait 2s -> SIGKILL -> drain communicate.

    Returns whatever stdout/stderr the child managed to emit before death.

    Process-group kill via os.killpg (start_new_session=True made the child
    the group leader; cpython#127049 -- bare PID kill misses orphan grandchildren).

    On platforms without os.killpg (Windows), falls back to proc.terminate()
    and proc.kill() for the same effect on a single process. Production target
    is Jetson (Linux/aarch64) where os.killpg is always available.
    """
    # Stage 1: SIGTERM the whole process group.
    _send_signal_to_group(proc, _SIGTERM)

    # Stage 2: wait up to grace seconds for orderly exit.
    with contextlib.suppress(TimeoutError):
        async with asyncio.timeout(_SIGTERM_GRACE_SECONDS):
            await proc.wait()

    # Stage 3: SIGKILL if still alive.
    if proc.returncode is None:
        _send_signal_to_group(proc, _SIGKILL)

    # Stage 4: drain communicate -- SECOND call. This is the cpython#139373
    # recovery: whatever the child flushed before death is now in the pipe
    # buffer; communicate() drains it without passing stdin again (the original
    # communicate already wrote stdin to the (now closed) pipe end).
    # Bounded by _SIGKILL_DRAIN_SECONDS so M5 (P99 cycle ≤10s) has a hard
    # upper bound: timeout_s + _SIGTERM_GRACE_SECONDS + _SIGKILL_DRAIN_SECONDS.
    try:
        async with asyncio.timeout(_SIGKILL_DRAIN_SECONDS):
            drained_out, drained_err = await proc.communicate()
    except (BrokenPipeError, ConnectionResetError, TimeoutError):
        drained_out, drained_err = b"", b""
    return drained_out or b"", drained_err or b""


def _send_signal_to_group(proc: asyncio.subprocess.Process, sig: int) -> None:
    """Send sig to the process group of proc (POSIX) or to proc directly (Windows).

    POSIX: os.killpg kills the group leader and all children -- required when
    start_new_session=True (cpython#127049).
    Windows: no process groups; proc.send_signal() for single-process compat.

    os.killpg and os.getpgid are POSIX-only and absent from Windows stubs, so
    we access them via sys.platform guard rather than direct attribute access.
    """
    if proc.pid is None or proc.returncode is not None:
        return  # Already gone.

    if sys.platform != "win32":
        # POSIX path: kill the whole process group so qmicli's helper children
        # are also reaped (cpython#127049).
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(os.getpgid(proc.pid), sig)  # type: ignore[attr-defined]
    else:
        # Non-POSIX fallback (Windows dev host only -- not a production path).
        with contextlib.suppress(ProcessLookupError, PermissionError):
            proc.send_signal(sig)
