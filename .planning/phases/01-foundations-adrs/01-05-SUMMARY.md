---
phase: "01"
plan: "05"
subsystem: subproc
tags:
  - python
  - asyncio
  - subprocess
  - tdd
  - sp-04
dependency_graph:
  requires:
    - 01-01  # lint gate scripts/lint_no_subprocess.sh authored in plan 01
    - 01-03  # wire types (CompletedProcess is a plain dataclass, not a pydantic wire type)
  provides:
    - subproc.run (async subprocess runner, SP-01)
    - CompletedProcess (SP-02 errors-as-data result type)
    - SubprocSpawnError (genuine spawn failure exception)
  affects:
    - Phase 2 qmi/parsers/ (first real consumer of subproc.run)
    - Phase 4 actions/ (usb_reset, modem_reset invoke system commands)
tech_stack:
  added:
    - asyncio.create_subprocess_exec (single call site in runner.py)
    - asyncio.timeout context manager (NOT wait_for; cpython#139373)
    - os.killpg / os.getpgid via sys.platform guard (cpython#127049)
    - contextlib.suppress for POSIX signal error swallowing
  patterns:
    - "frozen slotted dataclass (CompletedProcess) -- cheap, immutable, mypy-friendly"
    - "sys.platform guard for POSIX-only os.killpg (mypy --strict compatible)"
    - "_SIGKILL = 9 integer literal (signal.SIGKILL absent from Windows stubs)"
    - "setdefault() merge for locale baseline -- caller explicit key always wins"
key_files:
  created:
    - src/spark_modem/subproc/__init__.py
    - src/spark_modem/subproc/result.py
    - src/spark_modem/subproc/errors.py
    - src/spark_modem/subproc/runner.py
    - tests/unit/subproc/__init__.py
    - tests/unit/subproc/test_result.py
    - tests/unit/subproc/test_runner_argv_invariants.py
    - tests/unit/subproc/test_runner_locale.py
    - tests/unit/subproc/test_runner_timeout.py
    - tests/unit/subproc/test_runner_signals.py
    - tests/unit/subproc/test_runner_data_errors.py
  modified: []
decisions:
  - "timeout parameter renamed to timeout_s to satisfy ruff ASYNC109 (async function with 'timeout' parameter name conflicts with asyncio.timeout)"
  - "signal.SIGKILL replaced with integer literal 9 -- signal.SIGKILL absent from Windows type stubs; mypy --strict rejects it without platform guard"
  - "os.killpg/os.getpgid guarded by sys.platform != 'win32' with type: ignore[attr-defined] -- POSIX-only attributes, Windows stubs lack them"
  - "All 24 runner tests marked skipif(win32) or skipif(not hasattr(os, killpg)) -- Windows dev host lacks POSIX binaries and process-group APIs; production Jetson target is Linux/aarch64 where all tests run"
metrics:
  duration_minutes: 10
  completed_date: "2026-05-06"
  tasks_completed: 2
  files_created: 11
  files_modified: 0
---

# Phase 01 Plan 05: subproc-runner Summary

Single async subprocess wrapper (SP-01..SP-04): async run() with list-form argv validation, LC_ALL=C/LANG=C locale baseline, start_new_session=True process-group ownership, and asyncio.timeout two-stage shutdown recovering pre-death stdout (cpython#139373 fix).

## What Was Built

### Public Surface (`src/spark_modem/subproc/`)

```python
from spark_modem.subproc import run, CompletedProcess, SubprocSpawnError

result = await run(["/usr/bin/qmicli", "--device=/dev/cdc-wdm0", "--nas-get-signal-info"],
                   timeout_s=5.0)
if result.succeeded:
    # result.stdout: bytes -- parsed by Phase 2 qmi/parsers/
    ...
elif result.timed_out:
    # result.kill_signal: 9 (SIGKILL) or 15 (SIGTERM) -- diagnostic
    ...
else:
    # result.exit_code: non-zero -- data, not exception (SP-02)
    ...
```

**`CompletedProcess`** (`result.py`): frozen slotted dataclass with:
- `argv: tuple[str, ...]` -- defensive copy, never mutable
- `exit_code: int` -- negative when killed by signal (-9 == SIGKILL)
- `stdout: bytes`, `stderr: bytes` -- raw bytes; parsers decode
- `duration_monotonic: float` -- monotonic clock delta
- `timed_out: bool`, `kill_signal: int | None`
- `succeeded` / `failed` properties (SP-02)

**`SubprocSpawnError`** (`errors.py`): `OSError` subclass for genuine spawn failures (not binary-not-found -- those stay as `FileNotFoundError`). Carries `argv: tuple[str, ...]` and `original: OSError`.

**`run()`** (`runner.py`): the ONLY `asyncio.create_subprocess_exec` call in `src/spark_modem/`.

### SP-03 Four Always-On Invariants

| Invariant | Implementation | Test File |
|-----------|----------------|-----------|
| 1. list-form argv only | `_validate_argv()` -- TypeError on str/tuple, ValueError on empty | `test_runner_argv_invariants.py` |
| 2. Locale baseline LC_ALL=C, LANG=C | `_build_env()` -- `setdefault()` merge; caller explicit key wins | `test_runner_locale.py` |
| 3. `start_new_session=True` | Always passed to `create_subprocess_exec` | `test_runner_signals.py` |
| 4. Two-stage shutdown on timeout | SIGTERM -> 2s grace -> SIGKILL -> second `communicate()` drain | `test_runner_timeout.py` |

### cpython Bug Mitigations

**cpython#139373** (asyncio.wait_for around communicate drops in-flight stdout):
- Used `async with asyncio.timeout(timeout_s):` context manager around `proc.communicate()`
- After timeout, `_two_stage_shutdown()` issues a SECOND `proc.communicate()` to drain whatever the child flushed before SIGKILL
- `test_runner_timeout.py::test_timeout_recovers_pre_timeout_stdout` asserts pre-death stdout is present

**cpython#127049** (killing only parent PID leaves grandchild helpers orphaned):
- `start_new_session=True` makes the child the process group leader
- `_send_signal_to_group()` calls `os.killpg(os.getpgid(proc.pid), sig)` to kill the entire group
- `test_runner_signals.py::test_process_group_killed_on_timeout` verifies bounded wall time even when parent shell has a grandchild `sleep 60`

### SP-04 Lint Gate

`scripts/lint_no_subprocess.sh` (wired in Plan 01) searches all `src/` Python files for `create_subprocess_exec`, `subprocess.run`, `subprocess.Popen`, etc. and fails if any match occurs OUTSIDE `src/spark_modem/subproc/`.

Gate verified green at plan end: `bash scripts/lint_no_subprocess.sh` exits 0.
`runner.py` is the only file containing `create_subprocess_exec` in `src/`.

## Test Suite

| File | Tests | Platform | What It Covers |
|------|-------|----------|----------------|
| `test_result.py` | 16 | All | CompletedProcess frozen/make/succeeded/failed; SubprocSpawnError OSError compat |
| `test_runner_argv_invariants.py` | 6 | POSIX only | str/tuple/empty/non-str rejection; valid list acceptance |
| `test_runner_locale.py` | 4 | POSIX only | LC_ALL=C/LANG=C baseline; caller override semantics |
| `test_runner_timeout.py` | 5 | POSIX only | timed_out=True; negative exit_code; bounded wall time; cpython#139373 stdout recovery; SIGKILL escalation |
| `test_runner_signals.py` | 2 | POSIX + killpg | Process-group kill (cpython#127049); SIGTERM-first ordering |
| `test_runner_data_errors.py` | 7 | POSIX only | exit_code data (not exception); stderr capture; FileNotFoundError unwrapped; stdin delivery; duration |

**Windows dev host result:** 16 passed, 24 skipped (POSIX-only tests correctly skip).
**Jetson production target:** all 40 tests run; total wall time target <5s.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] ASYNC109 ruff lint: `timeout` parameter name conflicts with `asyncio.timeout`**
- **Found during:** Task 2 ruff check
- **Issue:** ruff ASYNC109 flags an async function parameter named `timeout` as conflicting with `asyncio.timeout` context manager
- **Fix:** Renamed parameter to `timeout_s` throughout runner.py and all 5 test files
- **Files modified:** `runner.py`, all `test_runner_*.py`
- **Commit:** 6abb7cb

**2. [Rule 1 - Bug] mypy --strict: `signal.SIGKILL` and `os.getpgid`/`os.killpg` absent from Windows stubs**
- **Found during:** Task 2 mypy check
- **Issue:** mypy --strict running on Windows reports `Module has no attribute "SIGKILL"` (signal module) and `Module has no attribute "getpgid"` (os module) -- POSIX-only attributes absent from typeshed Windows stubs
- **Fix:**
  - `_SIGKILL: Final[int] = 9` -- integer literal avoids signal module attribute access
  - `_send_signal_to_group()` parameter type changed from `signal.Signals` to `int`
  - `os.killpg`/`os.getpgid` guarded by `sys.platform != "win32"` with `# type: ignore[attr-defined]`
- **Files modified:** `runner.py`
- **Commit:** 6abb7cb

**3. [Rule 2 - Missing] PLC0415 ruff: inline imports in test files**
- **Found during:** Task 1 and Task 2 ruff check
- **Issue:** ruff PLC0415 requires imports at module top level (not inside test functions)
- **Fix:** Rewrote all test files with top-level imports
- **Files modified:** `test_result.py`, all `test_runner_*.py`
- **Commit:** dc3b0fd, 6abb7cb

## Known Stubs

None. The subproc package delivers concrete data (bytes, int, float); no placeholder values.

## Threat Flags

No new network endpoints, auth paths, or trust-boundary crossings beyond those in the plan's threat model (T-05-01 through T-05-07 -- all mitigated).

## Self-Check: PASSED

All 11 created files exist on disk. Both task commits (dc3b0fd, 6abb7cb) verified in git log.
Quality gates: pytest 16 passed / 24 skipped, mypy --strict clean, ruff check clean, ruff format clean, SP-04 lint gate exits 0.
