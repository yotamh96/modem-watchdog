---
phase: 01-foundations-adrs
plan: 05
type: execute
wave: 3
depends_on: [01, 03]
files_modified:
  - src/spark_modem/subproc/__init__.py
  - src/spark_modem/subproc/runner.py
  - src/spark_modem/subproc/result.py
  - src/spark_modem/subproc/errors.py
  - tests/unit/subproc/__init__.py
  - tests/unit/subproc/test_result.py
  - tests/unit/subproc/test_runner_argv_invariants.py
  - tests/unit/subproc/test_runner_locale.py
  - tests/unit/subproc/test_runner_timeout.py
  - tests/unit/subproc/test_runner_signals.py
  - tests/unit/subproc/test_runner_data_errors.py
autonomous: true
requirements:
  - FR-64
  - FR-72
  - FR-73
  - NFR-31
  - NFR-32
tags:
  - python
  - asyncio
  - subprocess
  - tdd

must_haves:
  truths:
    - "src/spark_modem/subproc/runner.py exports `async def run(argv, *, timeout, stdin=None, env=None) -> CompletedProcess` — the SINGLE async subprocess entrypoint for the daemon"
    - "argv must be a list[str]; passing a str (would invoke shell semantics) raises TypeError before spawning"
    - "Spawn always sets LC_ALL=C and LANG=C in the child env unless caller explicitly overrides via env=, closing PITFALLS §1.3 locale drift"
    - "Spawn always sets start_new_session=True so SIGKILL drains the process group, not just the bare PID (cpython#127049)"
    - "On timeout: SIGTERM, wait 2 seconds, SIGKILL, communicate-drain, return CompletedProcess with timed_out=True"
    - "Non-zero exit codes are returned as data in CompletedProcess, NOT raised — 'all errors are data' for the policy engine"
    - "Genuine runtime breakage (binary not on PATH → FileNotFoundError; OSError on spawn; non-list argv → TypeError) raises exceptions"
    - "scripts/lint_no_subprocess.sh detects any new subprocess call outside src/spark_modem/subproc/ — re-verified at the end of this plan"
    - "ruff check, ruff format --check, mypy --strict are green on src/spark_modem/subproc/ and tests/unit/subproc/"
    - "Total subproc unit-test wall time <5s on a developer laptop (uses sleep/echo/cat/false binaries; no GUI/network)"
  artifacts:
    - path: "src/spark_modem/subproc/runner.py"
      provides: "Single async subprocess runner: list-form argv, LC_ALL=C, start_new_session, two-stage shutdown"
      contains: "async def run"
    - path: "src/spark_modem/subproc/result.py"
      provides: "CompletedProcess dataclass: argv, exit_code, stdout, stderr, duration_monotonic, timed_out"
      contains: "class CompletedProcess"
    - path: "src/spark_modem/subproc/errors.py"
      provides: "SubprocSpawnError (binary missing / OSError-on-spawn — the rare genuine-failure path)"
      contains: "class SubprocSpawnError"
    - path: "tests/unit/subproc/test_runner_argv_invariants.py"
      provides: "Tests for SP-03 invariants: list-form argv, LC_ALL=C, start_new_session"
      contains: "TypeError"
    - path: "tests/unit/subproc/test_runner_timeout.py"
      provides: "Tests for the two-stage shutdown: SIGTERM->2s->SIGKILL, communicate drains, timed_out=True returned"
      contains: "timed_out"
  key_links:
    - from: "src/spark_modem/subproc/runner.py run()"
      to: "asyncio.create_subprocess_exec"
      via: "single call site (the WHOLE point of SP-04 — this is the only place this name appears)"
      pattern: "create_subprocess_exec"
    - from: "src/spark_modem/subproc/runner.py run()"
      to: "asyncio.timeout"
      via: "context manager around proc.communicate (NOT wait_for around communicate; cpython#139373)"
      pattern: "asyncio\\.timeout"
    - from: "scripts/lint_no_subprocess.sh"
      to: "src/spark_modem/subproc/"
      via: "the only directory exempt from the SP-04 grep gate"
      pattern: "src/spark_modem/subproc/"
---

<objective>
Build the **single** async subprocess wrapper that every domain module (qmi parsers in Phase 2, ip / InfraCtrl invocations in Phase 4, journalctl in support-bundle in Phase 2) uses to run external commands. After this plan, ANY `subprocess.run`, `subprocess.Popen`, `os.system`, or `asyncio.create_subprocess_exec` outside `src/spark_modem/subproc/` is a CI failure (Plan 01's `scripts/lint_no_subprocess.sh` is the gate; this plan is the *only* directory exempt).

Purpose: Closes FR-64 (never `exec` a string built from external data; list-form argv only). Closes NFR-31 (all subprocess calls pass arguments as a list). Closes NFR-32 (external text inputs parsed by validators that reject unexpected types — pairs with the `extra='ignore'` qmicli parser boundary in Phase 2). Implements CONTEXT.md SP-01 (one generic async runner), SP-02 ("all errors are data"), SP-03 (4 always-on spawn invariants), SP-04 (the lint gate, wired in Plan 01, here verified). Closes FR-72 (Protocol seam for SubprocessRunner — Phase 2 may declare a `Protocol` against this concrete class). Wires FR-73 (pure-function policy engine: the runner returns CompletedProcess data, never raises on non-zero exit; the policy never `try/except`s subprocess outcomes — it inspects the data).

Output: `src/spark_modem/subproc/` complete with 4 source files and 6 test files. Tests cover all 4 SP-03 spawn invariants, the SP-02 errors-as-data model, and the cpython#139373 cancellation-lost-stdout regression. Hardware-free, runs in <5s.

This plan is TDD: every behavior gets a test first; the test files define the contract before the runner implementation.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/01-foundations-adrs/01-CONTEXT.md
@.planning/research/STACK.md
@.planning/research/PITFALLS.md
@.planning/research/SUMMARY.md
@CLAUDE.md
@scripts/lint_no_subprocess.sh
@pyproject.toml

<interfaces>
<!-- This plan creates the subproc/ package — the ONLY directory in src/spark_modem/ -->
<!-- where create_subprocess_exec / fcntl / os.kill / os.killpg may appear. -->

From CONTEXT.md SP-01..SP-04 (full):

SP-01: ONE generic async runner in subproc/runner.py:
  async def run(
      argv: list[str],
      *,
      timeout: float,
      stdin: bytes | None = None,
      env: dict[str, str] | None = None,
  ) -> CompletedProcess

  Per-tool parsing (qmicli, ip, InfraCtrl, journalctl) lives in domain modules
  (qmi/parsers/, observer/zao/), not in subproc/. subproc/ owns spawn discipline;
  domain modules own argv composition and output parsing.

SP-02: "All errors are data" — run() returns a CompletedProcess for any terminating
  outcome including non-zero exit, timeout, and stderr-detected proxy_died. Caller
  decides whether non-zero is fatal. Exceptions are reserved for genuinely-broken-
  runtime conditions:
    - binary not on PATH → FileNotFoundError
    - OSError on spawn   → wrapped in SubprocSpawnError (or re-raised)
    - argv not a list    → TypeError

SP-03: Spawn invariants — all four always-on, no per-call opt-out:
  - list-form argv only — TypeError on str/tuple
  - locale baseline — LC_ALL=C, LANG=C in spawned env unless caller's env= overrides
  - start_new_session=True — kill the process group on SIGKILL drain
  - two-stage shutdown on timeout — SIGTERM → wait 2s → SIGKILL → communicate drain
  - asyncio.timeout() (context manager), NOT wait_for around communicate (cpython#139373)

SP-04: Lint gate — scripts/lint_no_subprocess.sh enforces "no create_subprocess_exec
  outside src/spark_modem/subproc/" (Plan 01 wired this; Plan 05 is the *only*
  directory the gate exempts).

From STACK.md §"qmicli subprocess" recipe:
  - create_subprocess_exec + proc.communicate(timeout=...) + two-stage shutdown
  - start_new_session=True (kill the process group, not bare PID — cpython#127049)
  - limit=1024*1024 for chatty 5G output (§5.4)

From PITFALLS.md §1.3 (locale): bash and qmicli both honor LC_*; LC_ALL=C strips
  most surprises. Set LANG=C as belt-and-suspenders.

From PITFALLS.md §5.1 (cpython#139373): asyncio.wait_for around proc.communicate()
  drops stdout on cancellation. Use `async with asyncio.timeout(t):` around an
  awaited communicate; on timeout, SIGTERM, wait 2s, SIGKILL, then a SECOND
  communicate to drain whatever the child managed to flush before death.

From CLAUDE.md anti-patterns:
  - subprocess.run sync — never (this whole package replaces it)
  - run_in_executor to "speed up" qmicli — never; we're already async-native
  - signal.signal from asyncio — never; for the runner's own kills we use os.killpg
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: result.py + errors.py + tests for the dataclass</name>
  <files>src/spark_modem/subproc/__init__.py, src/spark_modem/subproc/result.py, src/spark_modem/subproc/errors.py, tests/unit/subproc/__init__.py, tests/unit/subproc/test_result.py</files>
  <read_first>
    - .planning/phases/01-foundations-adrs/01-CONTEXT.md §"SP. Subprocess wrapper" SP-01..SP-04
    - .planning/research/STACK.md §"qmicli subprocess" (recipe)
    - CLAUDE.md §"Anti-patterns" (the full list of sins SP-04 catches)
    - scripts/lint_no_subprocess.sh (verify the regex catches everything we care about)
  </read_first>
  <behavior>
    CompletedProcess (test_result.py):
    - Test: CompletedProcess(argv=["/bin/echo", "hi"], exit_code=0, stdout=b"hi\n", stderr=b"", duration_monotonic=0.01, timed_out=False) constructs.
    - Test: dataclass is frozen — assigning to fields after construction raises (frozen=True; FrozenInstanceError).
    - Test: argv is read back as a tuple, NOT the original mutable list (defensive copy).
    - Test: `succeeded` property returns True iff exit_code == 0 AND not timed_out.
    - Test: `failed` property is the inverse.
    - Test: `__repr__` redacts stdin (we don't store stdin in the result; the result represents the *outcome*, and stdin would inflate the log line).

    SubprocSpawnError (test_result.py):
    - Test: SubprocSpawnError(argv, original_exception) carries the argv and the original (chained via `__cause__`).
    - Test: subclass of OSError so existing OSError handlers catch it; carries `.argv` for diagnostics.
  </behavior>
  <action>
    1. Create `src/spark_modem/subproc/__init__.py` with a one-line docstring, no exports yet (Task 2 fills the public surface).

    2. Write `tests/unit/subproc/__init__.py` (one-line docstring) and `tests/unit/subproc/test_result.py` (TDD RED).

    3. Implement `src/spark_modem/subproc/result.py`:
    ```python
    """CompletedProcess: the result type returned by subproc.runner.run().

    SP-02 'all errors are data' model: every terminating outcome (success, non-zero
    exit, timeout, stderr-detected proxy_died) is a CompletedProcess instance.
    Genuinely-broken-runtime conditions raise (see errors.py).
    """

    from __future__ import annotations

    from dataclasses import dataclass, field


    @dataclass(frozen=True, slots=True)
    class CompletedProcess:
        """Result of subproc.runner.run().

        Frozen + slots — cheap to allocate, immutable, mypy-friendly. argv is
        defensively copied to a tuple at construction (caller's list isn't
        retained).
        """

        argv: tuple[str, ...]
        exit_code: int  # negative if killed by signal (e.g. -9 == SIGKILL)
        stdout: bytes
        stderr: bytes
        duration_monotonic: float
        timed_out: bool

        # Optional: what signal we sent during two-stage shutdown (None on success).
        # Useful for diagnostics; doesn't affect the data flow.
        kill_signal: int | None = None

        @classmethod
        def make(
            cls,
            argv: list[str] | tuple[str, ...],
            *,
            exit_code: int,
            stdout: bytes,
            stderr: bytes,
            duration_monotonic: float,
            timed_out: bool = False,
            kill_signal: int | None = None,
        ) -> "CompletedProcess":
            return cls(
                argv=tuple(argv),
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_monotonic=duration_monotonic,
                timed_out=timed_out,
                kill_signal=kill_signal,
            )

        @property
        def succeeded(self) -> bool:
            return self.exit_code == 0 and not self.timed_out

        @property
        def failed(self) -> bool:
            return not self.succeeded
    ```

    4. Implement `src/spark_modem/subproc/errors.py`:
    ```python
    """Exceptions raised by subproc.runner.run() — only on genuine runtime breakage.

    SP-02 boundary: non-zero exit codes and timeouts are NOT exceptions; they are
    fields on CompletedProcess. Exceptions are reserved for cases where the
    subprocess didn't actually run (binary missing, OSError on spawn, malformed
    argv).
    """

    from __future__ import annotations


    class SubprocSpawnError(OSError):
        """Spawn failed with an OSError that's not a 'binary not found' case.

        FileNotFoundError (binary not on PATH) is intentionally NOT wrapped —
        callers can catch FileNotFoundError directly, which is the standard
        Python idiom for 'binary missing'.
        """

        def __init__(self, argv: list[str] | tuple[str, ...], original: OSError) -> None:
            self.argv = tuple(argv)
            self.original = original
            super().__init__(
                original.errno if hasattr(original, "errno") else None,
                f"spawn failed for argv={list(self.argv)!r}: {original!r}",
            )
    ```

    5. Run pytest — test_result.py turns GREEN.
  </action>
  <verify>
    <automated>
      cd S:/spark/modem-watchdog && \
      .venv/bin/pytest tests/unit/subproc/test_result.py -q && \
      .venv/bin/ruff check src/spark_modem/subproc/result.py src/spark_modem/subproc/errors.py tests/unit/subproc/test_result.py && \
      .venv/bin/ruff format --check src/spark_modem/subproc/result.py src/spark_modem/subproc/errors.py && \
      .venv/bin/mypy --strict src/spark_modem/subproc/result.py src/spark_modem/subproc/errors.py && \
      .venv/bin/python -c "from spark_modem.subproc.result import CompletedProcess; from spark_modem.subproc.errors import SubprocSpawnError; cp = CompletedProcess.make(['/bin/echo', 'hi'], exit_code=0, stdout=b'hi\n', stderr=b'', duration_monotonic=0.01, timed_out=False); assert cp.succeeded; assert cp.argv == ('/bin/echo', 'hi'); print('result/errors: OK')"
    </automated>
  </verify>
  <done>
    `CompletedProcess` is a frozen, slotted dataclass with a defensive-copy `argv: tuple[str, ...]` and `succeeded`/`failed` properties. `SubprocSpawnError` is an OSError subclass carrying the failing argv. All tests pass; mypy --strict and ruff are green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: runner.py — async run() with all four SP-03 invariants + comprehensive tests</name>
  <files>src/spark_modem/subproc/runner.py, src/spark_modem/subproc/__init__.py, tests/unit/subproc/test_runner_argv_invariants.py, tests/unit/subproc/test_runner_locale.py, tests/unit/subproc/test_runner_timeout.py, tests/unit/subproc/test_runner_signals.py, tests/unit/subproc/test_runner_data_errors.py</files>
  <read_first>
    - src/spark_modem/subproc/result.py and errors.py (just written)
    - .planning/phases/01-foundations-adrs/01-CONTEXT.md §"SP. Subprocess wrapper" SP-03 (the four spawn invariants in detail)
    - .planning/research/PITFALLS.md §5.1 (cpython#139373 — asyncio.timeout, NOT wait_for around communicate)
    - .planning/research/PITFALLS.md §1.3 (locale)
    - .planning/research/STACK.md §"qmicli subprocess" recipe
    - CLAUDE.md §"Anti-patterns" (subprocess.run sync; gather(return_exceptions=True); run_in_executor to "speed up" qmicli)
  </read_first>
  <behavior>
    test_runner_argv_invariants.py:
    - Test (list-form argv only): `await run("ls /tmp", timeout=1)` raises TypeError before spawn. The error message names the offending type (str).
    - Test: `await run(("ls", "/tmp"), timeout=1)` raises TypeError (tuple is not a list — strict, no auto-coercion).
    - Test: `await run([], timeout=1)` raises ValueError (empty argv).
    - Test: `await run(["/bin/echo", 42], timeout=1)` raises TypeError (non-str element).
    - Test: `await run(["/bin/echo", "hi"], timeout=1.0)` succeeds with stdout=b"hi\n", exit_code=0.

    test_runner_locale.py:
    - Test: `await run(["/usr/bin/env"], timeout=1.0)` includes both `LC_ALL=C` and `LANG=C` in the child's environment (parse stdout for the keys).
    - Test: caller-provided env with `env={"LC_ALL": "en_US.UTF-8"}` overrides the baseline (the spawned process sees `LC_ALL=en_US.UTF-8`).
    - Test: caller-provided env with no `LANG` key still gets the baseline `LANG=C` injected (we merge, not replace, unless the caller explicitly sets a key).

    test_runner_timeout.py — the cpython#139373 regression test:
    - Test: `await run(["/bin/sh", "-c", "sleep 5"], timeout=0.2)` returns within ~2.5s (0.2s grace + 2s SIGTERM-wait + ~0.3s slop) with timed_out=True, exit_code is negative (signal-killed). Total wall time < 3s.
    - Test: stdout/stderr that the child emitted BEFORE the timeout are returned in the result (cpython#139373 — the lost-stdout bug). Use a script that emits "early\n" to stdout, then sleeps, to demonstrate.
    - Test: kill_signal field is set to SIGKILL (9) when the child ignores SIGTERM (the test script traps SIGTERM and continues sleeping; SIGKILL drains it).

    test_runner_signals.py — process-group kill (cpython#127049 / start_new_session):
    - Test: `await run(["/bin/sh", "-c", "/bin/sleep 60 & wait"], timeout=0.2)` — the parent shell forks a child sleep(60). On timeout, killing only the parent leaves sleep(60) orphaned. With start_new_session=True we kill the whole group; the orphan-detection in the test (poll for `pgrep sleep` after run completes) reports zero orphan sleeps. (Implementation detail: pgrep may not be available in the test environment; alternatively assert the child group leader's PID was reaped.)
    - Test: signal received by the child is SIGTERM first; if the child traps it and continues, SIGKILL follows after 2s.

    test_runner_data_errors.py — SP-02 "all errors are data":
    - Test: `await run(["/bin/false"], timeout=1)` returns CompletedProcess with exit_code=1, timed_out=False. NO exception raised.
    - Test: `await run(["/bin/sh", "-c", "echo bad >&2; exit 7"], timeout=1)` returns CompletedProcess with exit_code=7, stderr=b"bad\n", stdout=b"".
    - Test: `await run(["/this/binary/does/not/exist"], timeout=1)` raises FileNotFoundError (NOT wrapped). The error message includes the missing argv[0].
    - Test: `await run(["/bin/echo", "hello"], timeout=1, stdin=b"unused")` — stdin is delivered to the child even though echo ignores it. Verify with a `cat` test that does consume stdin.
    - Test: `await run(["/bin/cat"], timeout=1, stdin=b"piped data")` returns stdout=b"piped data".
    - Test: duration_monotonic is positive and consistent with reality (>= 0; for echo, < 1.0).
  </behavior>
  <action>
    1. Write all 5 test files (TDD RED). Use a small helper `_skip_if_not_posix` to skip on non-POSIX dev hosts (Windows lacks `/bin/echo`, `start_new_session`, etc.). Production target is Jetson — POSIX is the deployment reality.

    2. Implement `src/spark_modem/subproc/runner.py`:
    ```python
    """Single async subprocess runner — the SP-04 anchor module.

    The ONLY place create_subprocess_exec / os.killpg / fcntl appear in src/spark_modem/.
    scripts/lint_no_subprocess.sh enforces this; no other module is allowed to spawn.

    SP-03 invariants (all always-on):
      1. list-form argv only            (FR-64 / NFR-31; TypeError on str)
      2. LC_ALL=C, LANG=C baseline      (PITFALLS §1.3)
      3. start_new_session=True         (cpython#127049 — kill the group)
      4. two-stage shutdown on timeout  (SIGTERM → 2s → SIGKILL → drain)

    asyncio.timeout() (context manager) — NOT wait_for around communicate
    (cpython#139373: wait_for cancels mid-communicate and the inflight stdout
    is lost). The two-stage drain is critical: after SIGKILL, we issue a
    SECOND communicate to recover whatever the child flushed before dying.
    """

    from __future__ import annotations

    import asyncio
    import os
    import signal
    import time
    from typing import Final

    from spark_modem.subproc.errors import SubprocSpawnError
    from spark_modem.subproc.result import CompletedProcess

    # PITFALLS §1.3 — locale baseline.
    _LOCALE_BASELINE: Final[dict[str, str]] = {"LC_ALL": "C", "LANG": "C"}

    # SP-03 step 4 — wait this long after SIGTERM before escalating to SIGKILL.
    _SIGTERM_GRACE_SECONDS: Final[float] = 2.0

    # STACK §"qmicli subprocess" — chatty 5G output; stdout buffer ~1 MiB.
    _STDOUT_LIMIT: Final[int] = 1024 * 1024


    def _validate_argv(argv: object) -> list[str]:
        """SP-03 invariant 1: list-form argv only. Strict — no tuple, no str."""
        if not isinstance(argv, list):
            raise TypeError(
                f"subproc.run: argv must be a list[str]; got {type(argv).__name__} "
                f"(value={argv!r}). Pass arguments as a list to prevent shell injection (FR-64)."
            )
        if not argv:
            raise ValueError("subproc.run: argv must not be empty.")
        for i, a in enumerate(argv):
            if not isinstance(a, str):
                raise TypeError(
                    f"subproc.run: argv[{i}] must be str; got {type(a).__name__} ({a!r})."
                )
        return list(argv)  # defensive copy


    def _build_env(caller_env: dict[str, str] | None) -> dict[str, str]:
        """Merge caller env over baseline; baseline supplies LC_ALL=C, LANG=C.

        If the caller didn't pass an env=, we inherit os.environ and overlay the
        locale baseline (so non-locale env vars like PATH and HOME come from the
        parent — the daemon process — and locale comes from us).

        If the caller DID pass an env=, we treat it as authoritative for the keys
        it sets, but still inject LC_ALL=C and LANG=C for any key the caller
        didn't explicitly set. This means an explicit `env={"LC_ALL": "..."}` wins.
        """
        if caller_env is None:
            merged = dict(os.environ)
        else:
            merged = dict(caller_env)
        for k, v in _LOCALE_BASELINE.items():
            merged.setdefault(k, v)
        return merged


    async def run(
        argv: list[str],
        *,
        timeout: float,
        stdin: bytes | None = None,
        env: dict[str, str] | None = None,
    ) -> CompletedProcess:
        """Run argv as a subprocess and return a CompletedProcess.

        Per SP-02 'all errors are data', this function returns CompletedProcess
        for any terminating outcome. It raises ONLY on genuinely-broken-runtime
        conditions:
          - argv not a list       → TypeError
          - argv is empty         → ValueError
          - binary not on PATH    → FileNotFoundError (un-wrapped; standard idiom)
          - other OSError on spawn → SubprocSpawnError (subclass of OSError)
        """
        argv_list = _validate_argv(argv)
        merged_env = _build_env(env)
        start_monotonic = time.monotonic()

        # Spawn — SP-03 invariant 3: start_new_session=True so we own the group.
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
            # Standard idiom: caller catches FileNotFoundError to detect "binary missing".
            raise
        except OSError as e:
            raise SubprocSpawnError(argv_list, e) from e

        timed_out = False
        kill_signal_used: int | None = None

        try:
            # SP-03 invariant 4 — asyncio.timeout() context manager, NOT wait_for.
            # cpython#139373: wait_for cancels mid-communicate, stdout is lost.
            async with asyncio.timeout(timeout):
                stdout, stderr = await proc.communicate(input=stdin)
        except TimeoutError:
            # Two-stage shutdown: SIGTERM, wait, SIGKILL, drain.
            timed_out = True
            stdout, stderr = await _two_stage_shutdown(proc)
            # Determine which signal actually drained it.
            if proc.returncode is not None and proc.returncode < 0:
                kill_signal_used = -proc.returncode
            else:
                # Unusual: proc reaped with non-negative returncode despite timeout.
                kill_signal_used = None

        duration = time.monotonic() - start_monotonic

        # exit_code: positive on normal exit, negative (-signal) when killed.
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
        """SP-03 invariant 4: SIGTERM → wait 2s → SIGKILL → drain communicate.

        Returns whatever stdout/stderr the child managed to emit before death.
        Process-group kill via os.killpg (start_new_session=True made the child
        the group leader; cpython#127049 — bare PID kill misses orphan grandchildren).
        """
        # Stage 1: SIGTERM the whole process group.
        if proc.pid is not None and proc.returncode is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass  # Already gone or not ours; fine.

        # Stage 2: wait up to grace seconds for orderly exit.
        try:
            async with asyncio.timeout(_SIGTERM_GRACE_SECONDS):
                await proc.wait()
        except TimeoutError:
            pass  # Will SIGKILL below.

        # Stage 3: SIGKILL if still alive.
        if proc.returncode is None and proc.pid is not None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

        # Stage 4: drain communicate — SECOND call. This is the cpython#139373
        # recovery: whatever the child flushed before death is now in the pipe
        # buffer; communicate() drains it. We don't pass stdin again (the original
        # communicate already wrote stdin to the closed pipe).
        try:
            # No timeout here — the process is already dead or dying; communicate
            # will return as soon as the OS reaps the pipes.
            stdout, stderr = await proc.communicate()
        except (BrokenPipeError, ConnectionResetError):
            stdout, stderr = b"", b""
        return stdout or b"", stderr or b""
    ```

    3. Update `src/spark_modem/subproc/__init__.py` to export the public surface:
    ```python
    """subproc — the single async subprocess wrapper (SP-01..SP-04)."""

    from spark_modem.subproc.errors import SubprocSpawnError
    from spark_modem.subproc.result import CompletedProcess
    from spark_modem.subproc.runner import run

    __all__ = ["CompletedProcess", "SubprocSpawnError", "run"]
    ```

    4. Run pytest. Verify the SP-04 lint gate STILL passes after these additions (subproc/runner.py contains `create_subprocess_exec` but is exempt because it's under `src/spark_modem/subproc/`).

    Mark process-group / orphan-kill tests as `@pytest.mark.skipif(sys.platform == "win32" or not hasattr(os, "killpg"), reason="POSIX-only")` so non-POSIX dev hosts don't false-fail. The Jetson production target is POSIX — gates run there.
  </action>
  <verify>
    <automated>
      cd S:/spark/modem-watchdog && \
      .venv/bin/pytest tests/unit/subproc/ -q --tb=short && \
      .venv/bin/ruff check src/spark_modem/subproc/ tests/unit/subproc/ && \
      .venv/bin/ruff format --check src/spark_modem/subproc/ tests/unit/subproc/ && \
      .venv/bin/mypy --strict src/spark_modem/subproc/ && \
      bash scripts/lint_no_subprocess.sh && \
      .venv/bin/python -c "import asyncio; from spark_modem.subproc import run, CompletedProcess, SubprocSpawnError; cp = asyncio.run(run(['/bin/echo', 'sp-05-OK'], timeout=2.0)); assert cp.succeeded; assert cp.stdout == b'sp-05-OK\n'; assert cp.exit_code == 0; print('runner: end-to-end OK')" && \
      .venv/bin/python -c "import asyncio; from spark_modem.subproc import run; raised = False
      try: asyncio.run(run('ls /tmp', timeout=1))
      except TypeError as e: raised = True
      assert raised, 'TypeError not raised on str argv'
      print('argv-as-string rejection: OK')" && \
      time .venv/bin/pytest tests/unit/subproc/ -q --no-header
    </automated>
  </verify>
  <done>
    `subproc.run` is the single async subprocess entrypoint. All 4 SP-03 invariants enforced: list-form argv (TypeError on str), LC_ALL=C/LANG=C baseline (with caller-override semantics), start_new_session=True, two-stage shutdown (SIGTERM → 2s → SIGKILL → drain via second communicate). SP-02 errors-as-data: non-zero exit and timeouts return CompletedProcess; FileNotFoundError + SubprocSpawnError + TypeError + ValueError are the only exceptions. cpython#139373 covered (asyncio.timeout context manager, NOT wait_for; second-communicate after kill recovers in-flight stdout). All tests pass; total wall time <5s. SP-04 lint gate still green: subproc/runner.py is the ONLY place `create_subprocess_exec` appears in src/.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| External text → argv | Any caller composing argv from external data (qmicli output, Zao log, config) must not interpolate strings into a single shell command. The list-form rule (FR-64 / NFR-31) prevents it at the type level. |
| Spawned child → daemon | Child writes stdout/stderr; daemon reads them as bytes and parses with pydantic (Phase 2 qmi/parsers/). Locale baseline LC_ALL=C strips most parser-confusing surprises (PITFALLS §1.3). |
| Process group ownership | start_new_session=True makes the child a group leader; the daemon's `os.killpg` reliably reaps the whole tree on timeout (cpython#127049). |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-05-01 | T (Tampering) / I (Injection) | argv composition by callers (Phase 2+) | mitigate | The runner accepts ONLY list[str]; passing a str (the shell-injection vector) raises TypeError before spawn. Callers physically cannot pass a shell command line. (FR-64 / NFR-31.) |
| T-05-02 | E (Elevation) | environment variable inheritance | mitigate | Locale baseline (LC_ALL=C, LANG=C) is always injected — predictable parse output, defeats locale-spoofing tricks (PITFALLS §1.3). Other env vars inherit from os.environ; daemon runs as root (NFR-30) with a minimal env via systemd's PrivateTmp + ProtectSystem (Phase 2 wires the unit). |
| T-05-03 | D (DoS) | a child that ignores SIGTERM | mitigate | SP-03 stage 4 — SIGTERM, wait 2s, SIGKILL, drain. The two-stage shutdown bounds runaway children. start_new_session=True ensures os.killpg reaps the entire group, not just the parent (cpython#127049). |
| T-05-04 | I (Information disclosure) | stdout/stderr leaking sensitive data | accept | The runner returns raw bytes; callers (Phase 2 parsers) decide what to log. ICCID/IMSI may appear in qmicli output but only flow into typed wire shapes (Plan 03 Identity model). The runner itself does no logging. |
| T-05-05 | T | a child that emits stdout then ignores SIGTERM | mitigate | cpython#139373 regression: the runner's two-stage shutdown does a SECOND `proc.communicate()` after SIGKILL — pre-death stdout/stderr are recovered. tests/unit/subproc/test_runner_timeout.py asserts this property. |
| T-05-06 | T | empty or malformed argv | mitigate | _validate_argv raises ValueError on empty argv and TypeError on non-str elements before spawn. |
| T-05-07 | E | a binary outside expected paths | accept | Plan 05 doesn't restrict argv[0] — callers (Phase 2+) compose paths. NFR-30 limits the attack surface (daemon is root; the binary set is qmicli, ip, etc.). FR-60 (refuse to start without qmicli/ip on PATH) is wired in Plan 02 (the postinst smoke test verifies bundled python; Phase 2's preflight verifies external binaries). |
</threat_model>

<verification>
End-to-end check after both tasks complete:

1. `pytest tests/unit/subproc/ -q` — all tests pass; total wall time <5s on developer laptop.
2. `mypy --strict src/spark_modem/subproc/` — zero errors.
3. `ruff check src/spark_modem/subproc/ tests/unit/subproc/` and `ruff format --check ...` — clean.
4. `bash scripts/lint_no_subprocess.sh` — exits 0. The runner's `create_subprocess_exec` is exempt because it lives under `src/spark_modem/subproc/`.
5. End-to-end smoke: `python -c "import asyncio; from spark_modem.subproc import run; cp = asyncio.run(run(['/bin/echo', 'OK'], timeout=2)); assert cp.succeeded; assert cp.stdout == b'OK\n'"`.
6. argv-as-str rejection: `python -c "import asyncio; from spark_modem.subproc import run; raised=False
   try: asyncio.run(run('ls', timeout=1))
   except TypeError: raised = True
   assert raised"`.
7. SP-04 boundary regression test: introduce a probe `print(asyncio.create_subprocess_exec)` in `src/spark_modem/wire/_base.py` — `bash scripts/lint_no_subprocess.sh` must exit 1; remove the probe — must exit 0. (Optional manual verification; the gate is automatic in CI.)
</verification>

<success_criteria>
- FR-64: never `exec` a string built from external data; subproc.run rejects str argv with TypeError before spawn. NFR-31 closed (all subprocess calls use list-form argv — by construction; no other module spawns).
- NFR-32: external text inputs parsed by validators that reject unexpected types — pairs with the qmicli `extra='ignore'` parser boundary in Phase 2; subproc.run delivers raw bytes, parsers handle types.
- SP-01..SP-04 fully implemented:
  - SP-01: ONE `run(argv, *, timeout, stdin=None, env=None)` entrypoint.
  - SP-02: errors-as-data (non-zero exit + timeout return CompletedProcess; only genuine breakage raises).
  - SP-03: list-form argv + LC_ALL=C/LANG=C + start_new_session + two-stage shutdown — all always-on.
  - SP-04: lint gate (Plan 01) re-verified at end of this plan; subproc/runner.py is the only exempt location.
- cpython#139373 covered: asyncio.timeout context manager + post-kill second-communicate recovers in-flight stdout.
- cpython#127049 covered: start_new_session=True + os.killpg kills the group, not bare PID.
- FR-72 surface: Phase 2 may declare `class SubprocessRunner(Protocol): async def run(...)` against this concrete class for test isolation.
- FR-73 surface: the policy engine consumes CompletedProcess as data; never `try/except`s subprocess outcomes.
</success_criteria>

<output>
After completion, create `.planning/phases/01-foundations-adrs/01-05-SUMMARY.md` covering: subproc public surface, the four SP-03 invariants in code, the cpython#139373 / cpython#127049 mitigations and how the test suite exercises them, total subproc unit-test wall time, and a note that the SP-04 lint gate remains green. Reference Plan 01 (lint gate) and Phase 2 (qmi/parsers/ — the first Real consumer of subproc.run).
</output>
