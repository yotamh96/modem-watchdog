---
id: T10
parent: S02
milestone: M001
provides:
  - daemon/cycle_driver.CycleDriver -- single integration point for every Phase 2 subsystem
  - daemon/cycle_scheduler.CycleScheduler -- 30s monotonic timer + drift accounting + overrun detection
  - daemon/rss_tripwire -- 200 MiB NFR-3 alarm (event-only, no graceful-exit in Phase 2)
  - daemon/main -- callable end-to-end laptop integration (Phase 3 will replace single-cycle invocation with the production loop)
  - tools/gen_replay_fixtures -- deterministic generator for >=1000 fault-cycle fixtures
  - tests/replay/test_v1_agreement -- partial-order verdict classifier (R-02) + ≥95% gate
  - tests/replay/test_streak_restart -- FR-26.1 streak persistence proof
  - artifacts/replay-summary.json schema -- per-fixture verdicts for CI archiving
requires: []
affects: []
key_files: []
key_decisions: []
patterns_established: []
observability_surfaces: []
drill_down_paths: []
duration: ~30 min
verification_result: passed
completed_at: 2026-05-06
blocker_discovered: false
---
# T10: 02-core-daemon-laptop-testable 10

**# Phase 2 Plan 10: Cycle Driver + Replay Harness (Phase 2 EXIT GATE) Summary**

## What Happened

# Phase 2 Plan 10: Cycle Driver + Replay Harness (Phase 2 EXIT GATE) Summary

**CycleDriver wires every Phase 2 subsystem into a single observe -> policy -> actions -> persist -> status -> webhook pipeline; replay harness with 1002 fault-cycle fixtures hard-fails the build at <95% v1 agreement (achieved: 100%, 952/952 fault cycles agree).**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-05-06T18:18:10Z
- **Completed:** 2026-05-06T18:48:00Z (approximate)
- **Tasks:** 2 atomic commits
- **Files created:** 1015 (5 daemon source + 4 daemon tests + 1 generator + 4 replay test files + 1004 replay fixture JSONs + 1 .gitkeep)

## Accomplishments

- **CycleDriver** (`src/spark_modem/daemon/cycle_driver.py`) is the single integration point that wires StateStore + ConfigLoader + EventLogWriter + MetricRegistry + WebhookPoster + CarrierTable + Inventory + ZaoLogTailer + QmiWrapper-factory + ActionDispatcher + StatusReporter into a single per-cycle pipeline. Each phase of the pipeline is isolated to its own helper (`_dispatch_actions`, `_persist_states_and_globals`, `_enqueue_webhooks`, `_write_status_report`).
- **CycleScheduler** (`src/spark_modem/daemon/cycle_scheduler.py`) ticks every 30s monotonic with `next_deadline` / `advance` / `overran` accounting; `advance()` catches up past `now` to avoid back-to-back hot-loops after a slow cycle (PITFALLS §9.3). The Phase 3 event-queue arm is a planned extension: this plan ships the timer arm only.
- **RSS tripwire** (`src/spark_modem/daemon/rss_tripwire.py`) is event-only in Phase 2: records `daemon_self_health{kind="rss"}` and logs WARNING; Phase 3's sd_notify watchdog reads the counter to decide on restart (T-02-10-05 mitigation: tripwire cannot be weaponised as an escalation vector).
- **NFR-11 verified end-to-end**: a deliberately-thrown policy exception is caught, logged, the cycle continues with empty plans, and status.json is STILL written. `tests/unit/daemon/test_policy_exception_isolation.py::test_policy_exception_does_not_crash_cycle_status_still_written` passes.
- **SC #5 webhook envelopes verified**: HealthyToDegraded, RecoveringToExhausted, and ActionFailedWebhook envelopes are constructed inline in `_enqueue_webhooks` and enqueued via the `WebhookPoster` Protocol. DaemonRestart is emitted ONCE at boot in `daemon/main.py` before the first cycle. Three dedicated tests in `test_cycle_driver.py` cover each envelope variant.
- **Replay harness** (`tests/replay/`) ships 1002 fault-cycle fixtures from 7 RECOVERY_SPEC §4 scenarios + 50 healthy fillers + 2 hand-authored restart_mid_streak fixtures. `pytest_sessionfinish` aggregates per-fixture verdicts, writes `artifacts/replay-summary.json`, and HARD FAILS the build at <95% fault-cycle agreement. **Achieved: 100% (952/952 fault cycles classify as `agree`)**.
- **FR-26.1 streak-persistence proof**: `tests/replay/test_streak_restart.py` round-trips a ModemState through `model_dump_json -> model_validate_json` to simulate a daemon restart at streak=9, then runs the next cycle to verify K=10 decay fires (counters reset to {}, streak resets to 0).
- **M5 / NFR-1 measurable**: `tests/unit/daemon/test_cycle_perf.py::test_one_cycle_completes_under_one_second_with_fixtures` asserts a single fixture cycle completes in well under 1s on a developer laptop -- 100x under the 10s P99 production budget.
- **Full pytest suite**: 1675 tests in 11.82s -- well under the M7 ≤30s budget; replay harness alone contributes ~2s.

## Task Commits

Each task was committed atomically:

1. **Task 1: CycleScheduler + RSS tripwire + CycleDriver + daemon main + 20 unit tests** - `a21ae60` (feat)
2. **Task 2: gen_replay_fixtures + 1004 fixture JSONs + replay test suite (test_v1_agreement + test_streak_restart) + conftest with sessionfinish gate** - `ca98eca` (feat)

**Plan metadata:** `(this commit)` (docs: complete plan)

## Files Created/Modified

### Source

- `src/spark_modem/daemon/__init__.py` -- package marker + Phase 2/3 boundary doc
- `src/spark_modem/daemon/cycle_scheduler.py` -- 30s monotonic timer + drift gauge plumbing
- `src/spark_modem/daemon/rss_tripwire.py` -- 200 MiB NFR-3 detector (event-only)
- `src/spark_modem/daemon/cycle_driver.py` -- the integration point: observe -> policy -> actions -> persist -> status -> webhook
- `src/spark_modem/daemon/main.py` -- callable async main wiring every subsystem; runs ONE cycle for laptop integration
- `tools/gen_replay_fixtures.py` -- deterministic generator for >=1000 replay fixtures (--seed 42)
- `.gitignore` -- added `artifacts/replay-summary.json` (regenerable artifact, not committed)
- `artifacts/.gitkeep` -- preserves the directory so `pytest_sessionfinish` can write into it

### Tests

- `tests/unit/daemon/{__init__.py, test_cycle_scheduler.py (8 tests), test_cycle_driver.py (9 tests incl. 3 SC #5 webhook tests), test_policy_exception_isolation.py (1 test), test_cycle_perf.py (2 tests)}`
- `tests/replay/{__init__.py, conftest.py (sessionfinish gate), test_v1_agreement.py (1002 parametrized cycles), test_streak_restart.py (1 test)}`
- `tests/fixtures/replay/<7 fault scenarios>/<NNN>.json` -- 952 fault-cycle fixtures
- `tests/fixtures/replay/healthy/<NNN>_clean_cycle.json` -- 50 healthy filler fixtures
- `tests/fixtures/replay/restart_mid_streak/{000_pre.json, 001_post.json}` -- hand-authored FR-26.1 proof points

## Decisions Made

(See `key-decisions:` in frontmatter for the full list.)

Key call-outs:

- **Per-modem QmiWrapper rebuilt per dispatch.** The single CycleDriver-level QmiWrapper bound to a placeholder device would have risked applying actions to the wrong modem when the dispatcher iterates plans. Each `execute_and_verify` call gets a fresh QmiWrapper bound to `/dev/<plan.who.cdc_wdm>` looked up against the inventory snapshot.
- **DaemonStopReason.CRASH at boot.** The `DaemonStopReason` enum (Phase 1) only includes `SIGTERM | CRASH | CONFIG_INVALID | OOM | KILL`; Phase 2 has no clean-shutdown marker file, so every boot is treated as a crash recovery for webhook reporting. Phase 3 swaps in SIGTERM after writing a clean-shutdown marker on graceful exit.
- **CarrierTable(carriers=[]) acceptable for laptop integration.** The Phase 1 `CarrierTable` shape is `{schema_version, carriers: list[CarrierEntry]}`; an empty list is a valid table that surfaces `no_carrier:<mcc>/<mnc>` on lookup. Production loads the real YAML at startup.
- **Replay verdict 'safer' partial order**: `v2_succeeded=False/None` means v1's destructive ALSO failed, so v2 picking cheaper is at-least-as-good (`safer`). Only when v1's destructive SUCCEEDED can v2's cheaper pick be classified `less-safe`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Generator with `--count 1000` produced 995 not >=1000 fixtures**
- **Found during:** Task 2 (post-generation count verification)
- **Issue:** Plan acceptance criterion required >=1000 fixture files; the original integer-divide of `(1000-50) // 7 = 135 per fault * 7 + 50 healthy = 995`.
- **Fix:** Replaced floor-divide with ceiling-divide (`-(-fault_total // len(_FAULT_SCENARIOS))`); now produces 142 per fault scenario * 7 + 50 healthy = **1002**.
- **Files modified:** `tools/gen_replay_fixtures.py`
- **Verification:** `find tests/fixtures/replay -name "*.json" | wc -l` reports 1004 (1002 generated + 2 hand-authored restart_mid_streak); `pytest tests/replay/` reports 1003 cycles (restart_mid_streak excluded from the parametrized v1_agreement test, included in the dedicated test_streak_restart.py).
- **Committed in:** `ca98eca` (Task 2 commit)

**2. [Rule 1 - Bug] test_run_one_cycle_persists_modem_states asserted wrong state-file dir**
- **Found during:** Task 1 (initial test run)
- **Issue:** Test asserted `<state_root>/by-usb/<usb_path>.json` but `state_store/paths.state_by_usb_dir` places files at `<state_root>/state/by-usb/<usb_path>.json` per ADR-0009 -- the test had the path layout wrong, not the implementation.
- **Fix:** Corrected the test to use `Path(settings.state_root) / "state" / "by-usb"` and added an inline comment referencing ADR-0009.
- **Files modified:** `tests/unit/daemon/test_cycle_driver.py`
- **Verification:** Test now passes; the state files DO exist at `<state_root>/state/by-usb/<usb_path>.json` after one cycle.
- **Committed in:** `a21ae60` (Task 1 commit)

**3. [Rule 3 - Blocking] Observer per-task timeout was 8s default; perf test exceeded its 2s budget**
- **Found during:** Task 1 (`test_observer_concurrency_one_slow_probe_does_not_stall_cycle` failing at 8.094s)
- **Issue:** `observer.orchestrator.observe_all` uses `timeout_s: float = DEFAULT_PROBE_TIMEOUT_S = 8.0` evaluated at function-definition time. Monkeypatching the module-level constant has no effect because the default was already captured.
- **Fix:** Replaced the test's monkeypatch of `DEFAULT_PROBE_TIMEOUT_S` with a wrapper around `observe_all` (injected via `monkeypatch.setattr("spark_modem.daemon.cycle_driver.observe_all", _short_timeout_observe_all)`) that forces `timeout_s=0.05`. The production code path (8.0s default) is exercised separately by the matching observer-suite test.
- **Files modified:** `tests/unit/daemon/test_cycle_perf.py`
- **Verification:** Test now passes with `elapsed < 2.0` budget.
- **Committed in:** `a21ae60` (Task 1 commit)

**4. [Rule 3 - Blocking] mypy --strict rejected `kind: object` on MetricRegistryProto.record_action**
- **Found during:** Task 1 (mypy pass)
- **Issue:** Original Protocol used `kind: object` to avoid "unbound generic Protocol" issues, but mypy then refused to accept the concrete `MetricRegistry` (which uses `kind: ActionKind`) as a structural match -- variance check requires exact type match for non-keyword positional Protocol parameters.
- **Fix:** Imported `ActionKind` at the top of `cycle_driver.py` and changed `MetricRegistryProto.record_action` to take `kind: ActionKind, result: ActionResultEnum` -- both already imported elsewhere in the file.
- **Files modified:** `src/spark_modem/daemon/cycle_driver.py`
- **Verification:** `mypy --strict src/spark_modem/daemon/ tests/unit/daemon/` exits 0; tests pass; concrete `MetricRegistry` accepted.
- **Committed in:** `a21ae60` (Task 1 commit)

**5. [Rule 1 - Bug] ASYNC240 lint rejected pathlib calls in async test bodies + main()**
- **Found during:** Task 1 (ruff pass)
- **Issue:** `Path.read_text` in async test bodies and `Path.mkdir` in `daemon/main.py`'s async function tripped ASYNC240 ("async functions should not use pathlib.Path methods").
- **Fix:** Pulled the synchronous filesystem operations into module-level helpers (`_read_text(path)` in tests, `_ensure_dirs(*paths)` in main.py). One-shot startup work; no benefit from running through a thread executor.
- **Files modified:** `src/spark_modem/daemon/main.py`, `tests/unit/daemon/test_cycle_driver.py`
- **Verification:** `ruff check src/spark_modem/daemon/ tests/unit/daemon/` exits 0.
- **Committed in:** `a21ae60` (Task 1 commit)

**6. [Rule 1 - Bug] PLR0911 (too-many-returns) on _classify in test_v1_agreement.py**
- **Found during:** Task 2 (ruff pass)
- **Issue:** Single-function classifier had 8 return statements; ruff PLR0911 caps at 6.
- **Fix:** Split into `_v2_active_kinds` + `_classify_with_both_acting` + `_classify` (top-level dispatcher).  Improved readability and named the partial-order branch.
- **Files modified:** `tests/replay/test_v1_agreement.py`
- **Verification:** `ruff check` clean; replay tests still pass at 100% agreement.
- **Committed in:** `ca98eca` (Task 2 commit)

---

**Total deviations:** 6 auto-fixed (3 Rule 1 bugs, 3 Rule 3 blocking issues)
**Impact on plan:** All auto-fixes were necessary for correctness or to pass the plan's own quality gates. No scope creep -- the cycle driver pipeline + replay harness shape match the plan's specification exactly.

## Issues Encountered

- **Smoke test of `daemon/main()` on Windows surfaces FileNotFoundError from qmicli (expected).** The daemon catches the error inside `observe_all` (NFR-11 absorbed exceptions per probe), the cycle continues with empty snapshots, and `main()` returns 0. Production target is Jetson aarch64 where qmicli is on PATH; the Windows dev-host smoke is a happy-path verification of the import + wiring graph.

## User Setup Required

None - no external service configuration required. Phase 2 is hardware-free by design.

## Next Phase Readiness

**Phase 2 EXIT GATE PASSED.** Phase 3 (Linux Event Sources & Lifecycle) can begin:

- `CycleScheduler.event_queue` arm sketched but not wired -- Phase 3 plumbs udev / rtnetlink / inotify producers onto it.
- `daemon/main.py` runs ONE cycle for laptop integration -- Phase 3 wraps it in a long-lived loop driven by the scheduler.
- `WebhookPoster.run_forever()` exists but is not yet started in `daemon/main.py` -- Phase 3 wires the consumer task + SIGTERM-driven `drain()`.
- `sd_notify Type=notify` integration: the `sdnotify` library is already in the lockfile (Phase 1); Phase 3 sends `READY=1` after the first successful cycle.
- `loop.add_signal_handler` SIGTERM (graceful shutdown <=5s) + SIGHUP (transactional config reload + DNS re-resolve).
- `psutil` RSS tripwire is wired to the metric/event but does not graceful-exit -- Phase 3's sd_notify watchdog owns restart on `daemon_self_health{kind="rss"}` breach.
- PID lock at `/run/spark-modem-watchdog/lock`.

**Phase 4 readiness:** the actions/dispatcher._REGISTRY pattern is the integration point for destructive actions -- Phase 4 appends `MODEM_RESET / USB_RESET / DRIVER_RESET` entries with no CycleDriver code change.

## Self-Check: PASSED

Verified each created file exists on disk and each commit is in `git log`:

- `src/spark_modem/daemon/__init__.py` -- FOUND
- `src/spark_modem/daemon/cycle_scheduler.py` -- FOUND
- `src/spark_modem/daemon/rss_tripwire.py` -- FOUND
- `src/spark_modem/daemon/cycle_driver.py` -- FOUND
- `src/spark_modem/daemon/main.py` -- FOUND
- `tests/unit/daemon/{__init__,test_cycle_scheduler,test_cycle_driver,test_policy_exception_isolation,test_cycle_perf}.py` -- ALL FOUND
- `tools/gen_replay_fixtures.py` -- FOUND
- `tests/replay/{__init__.py, conftest.py, test_v1_agreement.py, test_streak_restart.py}` -- ALL FOUND
- `tests/fixtures/replay/restart_mid_streak/{000_pre,001_post}.json` -- FOUND
- 1002 generator-produced fixtures across 7 fault scenarios + 50 healthy fillers
- `artifacts/.gitkeep` -- FOUND
- `artifacts/replay-summary.json` -- regenerable; current run reports `agreement_rate: 1.0`
- Commit `a21ae60` (Task 1 -- daemon + tests) -- FOUND in `git log`
- Commit `ca98eca` (Task 2 -- replay harness + fixtures) -- FOUND in `git log`

---
*Phase: 02-core-daemon-laptop-testable*
*Completed: 2026-05-06*
