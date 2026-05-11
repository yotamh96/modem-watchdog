---
phase: 05-bench-field-shadow
plan: 04
subsystem: daemon
tags: [daemon, preflight, fleet-triple, phase-5, x-03, last-config-error]

# Dependency graph
requires:
  - phase: 05-bench-field-shadow
    provides: Plan 05-02 FleetTriple wire shape + compute_fleet_triple orchestrator + QmiVersionDetectionFailed — directly imported by the X-03 preflight to compute the local triple
  - phase: 03-linux-event-sources-lifecycle
    provides: daemon/preflight.py PreflightFailed/write_last_config_error/exit-78 contract — analog copied verbatim for the new check
  - phase: 03-linux-event-sources-lifecycle
    provides: daemon/main.py _production_main scaffold with FR-60 preflight slot + acquire_pid_lock surface
  - phase: 02-cycle-and-recovery
    provides: SysfsInventory + QmiWrapper + subproc.runner.run pattern (SP-04 anchor)
provides:
  - UnknownFleetTriple exception class — RuntimeError subclass; matches PreflightFailed shape (N818 noqa)
  - _load_known_triples(known_fleet_dir: Path) -> list[FleetTriple] — walks <box-id>/triple.json one level deep; skips + warns on malformed entries; never raises
  - _compute_local_triple(*, zao_log_path) async helper — probes SysfsInventory + first descriptor's QmiWrapper.dms_get_revision + Zao log banner via compute_fleet_triple; raises UnknownFleetTriple on no-modems or QmiVersionDetectionFailed
  - preflight_check_known_fleet_triple(*, known_fleet_dir, zao_log_path, local_triple=None) async function — X-03 gate. local_triple=None triggers the production probe path; tests inject directly.
  - daemon/main.py wiring — preflight_check_known_fleet_triple slotted between FR-60 preflight_check (Step 3) and acquire_pid_lock (Step 5); shares --skip-preflight bypass with FR-60 check
affects:
  - 05-06 (.deb install — ships /etc/spark-modem-watchdog/known-fleet/ directory via debian/install; this plan validates against an injected dir, the .deb supplies the real one)
  - 06+ (cutover) — daemon now refuses to start on an undocumented box without an operator first running spark-modem ctl capture-fleet-fixture and shipping the triple.json via dpkg

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "X-03 daemon preflight gate — refuses to start on unknown (firmware, SDK, libqmi) triple; same exit-code-78 + last-config-error marker + boot-classifier loop as the existing FR-60 binary check (preflight.py analog)"
    - "Test-injection seam via local_triple parameter — production path probes sysfs+qmicli+Zao log; tests pass local_triple directly so the unit suite runs hardware-free on Windows dev hosts (mirrors Plan 05-02's _FakeWrapper duck-typing decision)"
    - "Read-only daemon contract against /etc/spark-modem-watchdog/known-fleet/ — daemon NEVER writes the known-fleet index (dpkg-managed); grep against the module body returns zero write paths (write_bytes / write_text / atomic_write_bytes / open(..., 'w') all absent)"
    - "One-level-deep directory walk for triple.json — _load_known_triples only picks up <known-fleet>/<box-id>/triple.json, NEVER <known-fleet>/.../subdir/triple.json; pinned by test_nested_triple_json_not_picked_up"
    - "Malformed-entry skip-and-warn pattern — JSONDecodeError + KeyError + ValidationError (caught as ValueError via pydantic exception hierarchy) all downgrade to logger.warning; other valid entries still considered (test_malformed_triple_skipped_other_match_passes)"

key-files:
  created:
    - src/spark_modem/daemon/preflight_triple.py (167 LOC — UnknownFleetTriple + _load_known_triples + _compute_local_triple + preflight_check_known_fleet_triple + module docstring documenting the X-03 contract + dpkg-managed read-only invariant)
    - tests/unit/daemon/test_preflight_triple.py (150 LOC, 9 tests — RuntimeError subclass + empty/missing/matching/mismatching/multi-entry/malformed-skip/malformed-only/nested cases)
    - tests/integration/test_daemon_preflight_triple.py (~200 LOC, 3 tests — unknown-triple exits-78-with-marker / skip-preflight bypass / matching-triple proceeds-past-preflight)
  modified:
    - src/spark_modem/daemon/main.py (+18 LOC — UnknownFleetTriple + preflight_check_known_fleet_triple import block; Step-3.5 X-03 preflight block immediately after the FR-60 block and before classify_prior_run/acquire_pid_lock)
    - .planning/ROADMAP.md (2 checkboxes — 05-03 + 05-04 flipped to [x])

key-decisions:
  - "UnknownFleetTriple subclasses RuntimeError (NOT PreflightFailed) — matches the shape per CONTEXT.md X-03 and follows Plan 05-02's QmiVersionDetectionFailed convention; different module + different framing means inheritance from PreflightFailed would conflate exit-code semantics. Compose at the call site in daemon/main.py with a sibling try/except block, not via an inheritance chain."
  - "Test-injection via local_triple: FleetTriple | None = None — production callers pass None and the function calls _compute_local_triple which hits sysfs + qmicli + Zao log; tests pass local_triple directly. Avoids any need to monkeypatch SysfsInventory / QmiWrapper / compute_fleet_triple in unit tests; mirrors Plan 05-02's wrapper: object duck-typing decision."
  - "_load_known_triples is pure I/O (sync, not async) — pathlib operations on local filesystem are fast and the directory has at most ~10 entries (1 per fleet box). Wrapping in asyncio.to_thread would be over-engineering; the production preflight path runs once at startup, before READY=1, so blocking the event loop for ~1ms is acceptable."
  - "ValidationError from pydantic FleetTriple construction caught as ValueError (its parent class) in the same except tuple as JSONDecodeError + KeyError — keeps the skip-and-warn branch single-pathed; ValidationError is a ValueError subclass so the same handler runs for missing-required-field + bad-value-type cases."
  - "Step 3.5 placement in _production_main — preflight_check_known_fleet_triple runs AFTER FR-60 preflight_check and BEFORE classify_prior_run + acquire_pid_lock. RESEARCH Q4 §307-321 reason: failure must not leave a stale PID lock (lock not yet held); failure must not lose the boot classifier's view of the prior run (classifier runs next; this preflight is just another way to mark CONFIG_INVALID on this boot)."
  - "Same --skip-preflight guard shared with FR-60 — wrapped inside the existing if not args.skip_preflight: block (preserves spark-modem-watchdog --laptop --skip-preflight workflow on non-Jetson dev hosts). Verified by test_skip_preflight_bypasses_triple_check (Task 2 Test 2)."

patterns-established:
  - "X-03 preflight is the final gate in the X-* deliverable family (X-01 fixture tree, X-02 capture verb, X-03 known-fleet gate) — the (capture-verb, daemon-preflight) pair forms a complete fleet-coverage loop: engineer captures a triple.json via the Plan 05-03 ctl verb, ships it via dpkg in Plan 05-06, and the daemon refuses to start until that ship completes"
  - "Plan 05-04 closes the X-* chain end-to-end on the dev host — integration test (`test_matching_triple_passes_preflight`) verifies the round-trip: write triple.json via dict-shaped JSON → _load_known_triples loads it → preflight matches local_triple → daemon proceeds. The contract between Plan 05-03's emit and Plan 05-04's consume is now byte-pinned."

requirements-completed:
  - X-03

# Metrics
duration: ~6min
completed: 2026-05-11
---

# Phase 5 Plan 04: X-03 Daemon Preflight (preflight_check_known_fleet_triple) Summary

**Shipped the X-03 daemon preflight gate: daemon refuses to start when the local (em7421_firmware, zao_sdk, libqmi) triple is not in the dpkg-managed known-fleet index — final gate of the X-* deliverable family, locking the contract between Plan 05-03's capture verb and the daemon's startup path.**

## Performance

- **Duration:** ~6 min wall-clock (4 commits across 5m 42s of git activity)
- **Started:** 2026-05-11T08:59:16Z (record_start_time before Task 1 RED)
- **Completed:** 2026-05-11T09:04:59Z (after Task 2 GREEN)
- **Tasks:** 2/2 complete (each RED+GREEN pair = 4 task-level commits)
- **Files modified:** 5 (3 created, 2 modified)

## Accomplishments

- **`UnknownFleetTriple`** RuntimeError subclass at `src/spark_modem/daemon/preflight_triple.py:53` — matches PreflightFailed shape (N818 noqa); composed at the call site in `daemon/main.py` rather than via inheritance.
- **`_load_known_triples(known_fleet_dir)`** at `preflight_triple.py:64` — walks `<box-id>/triple.json` one level deep; skips + warns on `JSONDecodeError`/`KeyError`/`ValueError` (pydantic ValidationError absorbed as ValueError subclass); never raises; returns `[]` on missing directory (caller handles).
- **`_compute_local_triple(*, zao_log_path)`** at `preflight_triple.py:97` — production probe path: SysfsInventory().scan() → first descriptor's QmiWrapper.dms_get_revision → `compute_fleet_triple` (Plan 05-02) → translates `QmiVersionDetectionFailed` to `UnknownFleetTriple`; raises if no Sierra modems found on sysfs.
- **`preflight_check_known_fleet_triple(*, known_fleet_dir, zao_log_path, local_triple=None)`** at `preflight_triple.py:121` — X-03 gate. `local_triple=None` triggers production probe path; tests pass `local_triple` directly. Empty/missing index AND no-match cases both raise `UnknownFleetTriple` with operator-actionable messages including local triple values and the remedy command (`spark-modem ctl capture-fleet-fixture --out=/tmp/fixture`).
- **Daemon wiring at `daemon/main.py:222-234`** — Step-3.5 X-03 preflight block immediately after the FR-60 block (Step 3) and before `classify_prior_run` (Step 4) / `acquire_pid_lock` (Step 5). Failure path mirrors FR-60: `write_last_config_error` + `logger.error(...)` + `return 78` (EX_CONFIG). Boot classifier reads marker on next boot and emits `DaemonRestart(reason=CONFIG_INVALID)`.
- **Same `--skip-preflight` bypass** — wrapped inside the same `if not args.skip_preflight:` guard so `spark-modem-watchdog --laptop --skip-preflight` still works on non-Jetson dev hosts.
- **READY=1 is never reached on triple mismatch** — _production_main returns 78 BEFORE acquiring the PID lock, BEFORE constructing `SdNotifyLifecycle`, and therefore BEFORE the placeholder `READY=1` wiring Plan 03-09 will land. The systemd unit (`Type=notify`) marks the boot as failed because READY was never sent. Verified end-to-end by `test_unknown_triple_exits_78_and_writes_marker`.
- **PID lock leakage prevented** — the new preflight slots BEFORE `acquire_pid_lock`; failure exits cleanly without ever holding the lock (T-05-04-06 mitigated).
- **Daemon NEVER writes to `/etc/spark-modem-watchdog/known-fleet/`** — grep against the module body returns zero code-level write paths (T-05-04-05 mitigated).
- 12 new tests across 2 files (9 unit + 3 integration), all green in 0.65s.
- Full repo regression: **2030 passed / 90 skipped in 21.68s** (up from 2018; well under M7 ≤30s budget).
- `ruff check` + `mypy --strict` clean on all changed source files; SP-04 invariant preserved (`grep -rEn 'create_subprocess_exec|subprocess.run' src/spark_modem/daemon/preflight_triple.py` returns 0 matches).

## Final placement of X-03 preflight block

`daemon/main.py` startup order BEFORE this plan (unchanged Step numbers from Phase 3):

```
Step 1   argparse                            (line ~183)
Step 2   build Settings                      (lines 187-199)
Step 3   FR-60 preflight (preflight_check)   (lines 205-215)
Step 4   classify_prior_run                  (line 218)
Step 5   acquire_pid_lock                    (line 223)
```

After this plan:

```
Step 1   argparse                                                 (line ~183)
Step 2   build Settings                                           (lines 187-199)
Step 3   FR-60 preflight (preflight_check)                        (lines 205-215)
Step 3.5 X-03 preflight (preflight_check_known_fleet_triple)      (lines 217-228)  ← NEW
Step 4   classify_prior_run                                       (line 231 was 218)
Step 5   acquire_pid_lock                                         (line 236 was 223)
```

The two preflight blocks are structurally identical (both gated on `if not args.skip_preflight:`, both catching their respective exception class, both calling `write_last_config_error` + `logger.error` + `return 78`). No other changes to main.py — the existing FR-60 block, PID lock acquisition, sd_notify wiring, and TaskGroup placeholder all remain unchanged.

## Test-injection adjustments for `_production_main` args shape

`_production_main` reads only `args.skip_preflight` directly — the outer `main()` dispatches `args.laptop` before reaching production main. The integration test's `_make_args` helper sets both `skip_preflight` (test parameter) and `laptop=False` (defensive default) on a vanilla `argparse.Namespace`. No additional fields were required; all 3 integration tests pass.

## Confirmation: ZERO writes to /etc/spark-modem-watchdog/known-fleet/

```text
$ grep -rEn 'write_bytes|write_text|atomic_write_bytes|open\(.*['\"]w['\"]' \
    src/spark_modem/daemon/preflight_triple.py
# Returns: only docstring matches (anti-pattern documentation), zero code-level writes
```

Daemon is read-only against the known-fleet directory by design (dpkg-managed; Plan 05-06 ships it). T-05-04-05 mitigated.

## Task Commits

Each task followed the RED → GREEN cycle (no REFACTOR needed):

1. **Task 1 RED:** add failing tests for `preflight_check_known_fleet_triple` — `3cfe990` (test)
2. **Task 1 GREEN:** implement `preflight_check_known_fleet_triple` module — `3849261` (feat)
3. **Task 2 RED:** add failing integration tests for daemon main.py wiring — `6ac7296` (test)
4. **Task 2 GREEN:** wire `preflight_check_known_fleet_triple` into `_production_main` — `16dc6b3` (feat)

## Files Created/Modified

### Created (3)

- **`src/spark_modem/daemon/preflight_triple.py`** (167 LOC). Module docstring documents X-03 contract, exit-code-78 + last-config-error marker semantics, dpkg-managed read-only invariant, and one-level-deep directory walk. Exports `UnknownFleetTriple`, `preflight_check_known_fleet_triple`; private helpers `_load_known_triples` + `_compute_local_triple`. Module constants `_KNOWN_FLEET_DIR` (`/etc/spark-modem-watchdog/known-fleet`) + `_DEFAULT_ZAO_LOG_PATH` (`/var/log/zao-remote-endpoint.log`).
- **`tests/unit/daemon/test_preflight_triple.py`** (150 LOC, 9 tests). Cases: RuntimeError subclass; empty-dir raises (`empty or missing`); missing-dir raises (`empty or missing`); matching triple passes; mismatching triple raises (`unknown fleet triple`); multi-entry one-match passes; malformed entry skipped + warned; all-malformed raises (falls into empty branch); nested triple.json NOT picked up. `_LOCAL` constant + `_write_triple` helper share the FleetTriple shape across tests.
- **`tests/integration/test_daemon_preflight_triple.py`** (~200 LOC, 3 tests). Cases: unknown-triple exits 78 + marker contains either branch's message; `--skip-preflight` bypasses the triple check (assert called["triple_check"] == 0); matching-triple proceeds past preflight to PID lock acquisition (sentinel exception from `acquire_pid_lock`). `patched_environment` fixture monkeypatches `build_default_settings` (binds Settings paths to tmp_path) + `preflight_check` (FR-60 no-op stub).

### Modified (2)

- **`src/spark_modem/daemon/main.py`** (+18 LOC). Added `UnknownFleetTriple` + `preflight_check_known_fleet_triple` import block (alphabetised with the existing preflight imports); added Step-3.5 X-03 preflight block immediately after the FR-60 block; added structured logger.error line for the unknown-triple case.
- **`.planning/ROADMAP.md`** (2 checkboxes). Flipped both `05-03-PLAN.md` (missed by 05-03's executor — see ROADMAP NOTE in this plan's prompt) AND `05-04-PLAN.md` to `[x]`. `gsd-sdk query roadmap.update-plan-progress 05 05-04 complete` returned `updated: false / no matching checkbox found` because Phase 5's roadmap uses plain bullet shape, not the per-plan checkbox shape the CLI recognises (orchestrator predicted this); direct edit per the prompt's fallback.

## Decisions Made

- **`UnknownFleetTriple` subclasses `RuntimeError` directly (not `PreflightFailed`).** Matches the shape per CONTEXT.md X-03 and follows Plan 05-02's `QmiVersionDetectionFailed` convention. Different module + different framing (X-03 vs FR-60) — inheritance would conflate the call-site try/except pattern. `daemon/main.py` composes them with sibling try/except blocks.

- **Test-injection via `local_triple: FleetTriple | None = None` parameter.** Production callers pass `None` and `_compute_local_triple` hits sysfs + qmicli + Zao log; tests pass `local_triple` directly. Eliminates the need to monkeypatch `SysfsInventory` / `QmiWrapper` / `compute_fleet_triple` in unit tests. Direct echo of Plan 05-02's `wrapper: object` duck-typing decision.

- **`_load_known_triples` is sync (not async).** Pathlib operations on local filesystem are fast (~1ms); directory has at most ~10 entries (1 per fleet box); production preflight runs ONCE at startup before READY=1. Wrapping in `asyncio.to_thread` would be over-engineering. ASYNC240 not triggered because the function is plain sync `def`, not `async def`.

- **`ValidationError` caught as `ValueError`** in the malformed-entry except tuple. Pydantic's `ValidationError` is a `ValueError` subclass, so the existing `(json.JSONDecodeError, KeyError, ValueError)` catch tuple absorbs it without needing a pydantic-specific import. Keeps the skip-and-warn branch single-pathed.

- **Step 3.5 placement: AFTER FR-60 preflight, BEFORE classify_prior_run + acquire_pid_lock.** RESEARCH Q4 §307-321: failure must not leave a stale PID lock (lock not yet held); failure must not lose the boot classifier's view of the prior run (classifier just hasn't run yet — this preflight is another way to mark CONFIG_INVALID on the current boot). The marker that this preflight writes will be read by the NEXT boot's classifier.

- **Same `--skip-preflight` guard shared with FR-60** — wrapped inside the existing `if not args.skip_preflight:` block. Single flag toggles both gates; preserves the laptop / dev workflow. Verified by `test_skip_preflight_bypasses_triple_check`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Test file ruff lints: N818 + PLC0415 on `_Sentinel` / inline `import contextlib`**

- **Found during:** Task 2 GREEN (post-implementation ruff sweep on `tests/integration/test_daemon_preflight_triple.py`)
- **Issue:** The plan-text Task 2 §622-630 used `class _Sentinel(Exception): pass` and `import contextlib` inside the test functions. Ruff `N818` flagged the exception name (should end in `Error`), and `PLC0415` flagged the two inline imports (should be at module top).
- **Fix:** Renamed both occurrences of `_Sentinel` → `_SentinelError`; hoisted `import contextlib` to the module's top-of-file import block (between `argparse` and `json` alphabetically).
- **Files modified:** `tests/integration/test_daemon_preflight_triple.py`.
- **Verification:** `ruff check tests/integration/test_daemon_preflight_triple.py` exits 0; 3/3 tests still pass.
- **Committed in:** `16dc6b3` (Task 2 GREEN, alongside the daemon main.py wiring).

**2. [Rule 2 — Critical] `monkeypatch` on `daemon_main.build_default_settings`, not env vars**

- **Found during:** Task 2 RED (writing the `patched_environment` fixture)
- **Issue:** Plan-text Task 2 §556-577 used `monkeypatch.setenv("SPARK_MODEM_RUN_DIR", ...)` and similar to bind paths to tmp_path. `build_default_settings` (`src/spark_modem/cli/clients.py:98`) HARDCODES `state_root="/tmp/spark-modem-cli"` (not read from env), so the env vars would be ignored — and the test would write `last-config-error` into `/tmp/spark-modem-cli/run/` on POSIX (or fail outright on Windows where `/tmp` doesn't resolve).
- **Fix:** Used `monkeypatch.setattr(daemon_main, "build_default_settings", fake_build_default_settings)` where `fake_build_default_settings` constructs a `Settings` instance bound to `tmp_path` (state_root + run_dir + events_log_path all under the test's tmp_path). This is the cleanest seam — the `daemon_main` module imports `build_default_settings` at module load time, so `setattr` on the module-level binding swaps the symbol cleanly.
- **Files modified:** `tests/integration/test_daemon_preflight_triple.py` (`patched_environment` fixture).
- **Verification:** 3/3 integration tests pass; `last-config-error` lands in the test's tmp_path/run/ directory; no `/tmp/spark-modem-cli` writes.
- **Committed in:** `6ac7296` (Task 2 RED, applied at test-authoring time).

---

**Total deviations:** 2 auto-fixed (1 Rule 2 critical, 1 Rule 3 blocking lint). No scope creep; no architectural decisions; Rule 4 did not fire.

**Impact on plan:** Deviation 1 is mechanical lint cleanup; Deviation 2 is a small but important seam change (module-attr patch vs env-var patch). The plan-text's env-var approach would have silently written to `/tmp/spark-modem-cli` on POSIX and failed on Windows — Plan 05-02's deviation log called this drift pattern out exactly: "plan text describes the contract, real code defines it; when they disagree the real code wins."

## Issues Encountered

- **`PreToolUse:Edit` hook noise on Edit-after-Edit on the same file:** the hook flagged each Edit on `main.py`, `test_daemon_preflight_triple.py`, and `ROADMAP.md` after they were already read in the session. Same friction Plans 05-02 + 05-03 SUMMARYs documented. Every Edit succeeded.
- **No active git pre-commit hook on this Windows dev host:** `.git/hooks/pre-commit` absent so ruff/mypy/SP-04 lint did not run automatically. Ran them manually after each task GREEN.

## TDD Gate Compliance

All 2 tasks are `type="auto" tdd="true"`. Plan-level type is `execute` (not `tdd`), so plan-level RED→GREEN→REFACTOR gates do not apply, but each task followed the RED → GREEN cycle:

| Task | RED commit | GREEN commit | REFACTOR |
| ---- | ---------- | ------------ | -------- |
| 1    | `3cfe990` (test) | `3849261` (feat) | not needed |
| 2    | `6ac7296` (test) | `16dc6b3` (feat) | not needed (lint fixes folded into GREEN) |

RED-phase failure verification:

- Task 1 RED: `ModuleNotFoundError: No module named 'spark_modem.daemon.preflight_triple'`
- Task 2 RED: `AttributeError: module 'spark_modem.daemon.main' has no attribute 'preflight_check_known_fleet_triple'`

## Verification Summary

| Check | Status |
| ----- | ------ |
| `pytest tests/unit/daemon/test_preflight_triple.py tests/integration/test_daemon_preflight_triple.py -q` (plan scope) | **12 passed in 0.65s** |
| `pytest tests/integration/test_lifecycle.py -q` (no regression to lifecycle suite) | 6 skipped (POSIX-only on Windows; expected) |
| `pytest -q` (full repo suite — M7 ≤30s budget) | **2030 passed, 90 skipped in 21.68s** (M7 30s budget preserved) |
| `ruff check src/spark_modem/daemon/preflight_triple.py src/spark_modem/daemon/main.py tests/unit/daemon/test_preflight_triple.py tests/integration/test_daemon_preflight_triple.py` | All checks passed |
| `mypy --strict src/spark_modem/daemon/preflight_triple.py src/spark_modem/daemon/main.py` | Success: no issues found in 2 source files |
| `bash scripts/lint_no_subprocess.sh` (SP-04 invariant) | exit 0; 0 violations |
| `grep -rEn 'create_subprocess_exec\|subprocess\.run' src/spark_modem/daemon/preflight_triple.py` | 0 matches |
| `grep -c "async def preflight_check_known_fleet_triple" src/spark_modem/daemon/preflight_triple.py` | 1 |
| `grep -c "class UnknownFleetTriple" src/spark_modem/daemon/preflight_triple.py` | 1 |
| `grep -c "preflight_check_known_fleet_triple" src/spark_modem/daemon/main.py` | 2 (import + call) |
| `grep -n "preflight_check_known_fleet_triple\|preflight_check[^_]" src/spark_modem/daemon/main.py` | line 52 (preflight_check import) BEFORE line 57 (preflight_check_known_fleet_triple import); line 212 (preflight_check call) BEFORE line 228 (preflight_check_known_fleet_triple call) — ordering invariant satisfied |

## Threat Surface Scan

The plan's `<threat_model>` covers six threats (T-05-04-01 .. T-05-04-06). Disposition verification:

- **T-05-04-01 (DoS via corrupted/missing known-fleet):** mitigated — empty-dir + missing-dir + all-malformed paths all raise structured `UnknownFleetTriple` with operator-actionable messages (test_empty_known_dir_raises, test_missing_known_dir_raises, test_malformed_triple_only_raises). Plan 05-06 will ship an example fixture so the post-install state is never literally empty.
- **T-05-04-02 (Tampering — operator hand-edits triple.json):** accepted; operator with sudo can also `--skip-preflight`. Out of Phase 5 scope.
- **T-05-04-03 (Information disclosure — firmware/SDK leak in journalctl):** accepted; version strings are not PII (per Plan 05-02 T-05-02-04).
- **T-05-04-04 (Daemon-startup regression — `--skip-preflight` workflow broken):** mitigated — new check gated by same `if not args.skip_preflight:` block; pinned by `test_skip_preflight_bypasses_triple_check`.
- **T-05-04-05 (Privilege escalation — daemon writes to /etc/spark-modem-watchdog/known-fleet/):** mitigated — grep returns 0 write-path references in the module body (docstring matches only). Daemon is read-only by design.
- **T-05-04-06 (PID lock leakage on preflight failure):** mitigated — preflight slots BEFORE `acquire_pid_lock`; failure exits cleanly without holding the lock. Implicitly verified by `test_unknown_triple_exits_78_and_writes_marker` (marker written; `acquire_pid_lock` monkeypatched out and never invoked).

No new threat surface beyond plan dispositions. No `threat_flag` entries needed — the new module is internal preflight; no network endpoints, no auth paths, no new trust boundaries.

## Known Stubs

None. The preflight is a complete X-03 deliverable. The production path (when `local_triple=None`) calls `_compute_local_triple` which hits SysfsInventory + QmiWrapper + Zao log via `compute_fleet_triple` (Plan 05-02); on a dev host without modems it cleanly raises `UnknownFleetTriple("no Sierra modems found on sysfs; ...")` — not a stub, but the documented dev-host behavior. All test cases inject `local_triple` directly to exercise the gate logic without hardware.

The `/etc/spark-modem-watchdog/known-fleet/` directory does NOT exist on a dev host; Plan 05-06 (`debian/spark-modem-watchdog.install` modification) will ship it via dpkg. Until then, a non-test-mode daemon would hit the "empty or missing" branch — which is the correct behavior, just unfortunate UX for an out-of-band dev install. Documented behavior, not a stub.

## Next Phase Readiness

- **Plan 05-06 (.deb install)** can now ship `/etc/spark-modem-watchdog/known-fleet/` via `debian/spark-modem-watchdog.install` (or `.dirs`) knowing the daemon will read its `<box-id>/triple.json` files at startup and fail closed on mismatch. The contract is one-level-deep `<box-id>/triple.json`.
- **Phase 6 (cutover)** can rely on the X-03 gate to prevent v2 from starting on an undocumented box. The operator workflow becomes: capture fixture via `spark-modem ctl capture-fleet-fixture` → commit `triple.json` to `tests/fixtures/fleet/<box-id>/` → next .deb release ships it under `/etc/spark-modem-watchdog/known-fleet/` → daemon starts cleanly.
- **No blockers.** The X-* deliverable family (X-01 capture verb, X-02 PII redaction, X-03 daemon gate) is complete end-to-end on dev host; remaining Phase 5 plans are .deb install (05-06), operator docs (05-07), and manual soak workflow (05-08).

## Self-Check

Verifying SUMMARY claims against actual repo state.

**Files created — all present:**

- `S:/spark/modem-watchdog/src/spark_modem/daemon/preflight_triple.py` — FOUND
- `S:/spark/modem-watchdog/tests/unit/daemon/test_preflight_triple.py` — FOUND
- `S:/spark/modem-watchdog/tests/integration/test_daemon_preflight_triple.py` — FOUND

**Files modified — both present and contain the new symbols:**

- `S:/spark/modem-watchdog/src/spark_modem/daemon/main.py` — FOUND; `grep -c "preflight_check_known_fleet_triple" = 2`
- `S:/spark/modem-watchdog/.planning/ROADMAP.md` — FOUND; 05-03 and 05-04 lines both checked

**Commits cited — all present in git log:**

- `3cfe990` — FOUND (test: RED for Task 1)
- `3849261` — FOUND (feat: GREEN for Task 1)
- `6ac7296` — FOUND (test: RED for Task 2)
- `16dc6b3` — FOUND (feat: GREEN for Task 2)

## Self-Check: PASSED

---
*Phase: 05-bench-field-shadow*
*Completed: 2026-05-11*
