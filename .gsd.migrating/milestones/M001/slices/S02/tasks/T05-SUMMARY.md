---
id: T05
parent: S02
milestone: M001
provides:
  - PolicyContext + ClockProto (Protocol) so engine never imports production clock module (purity §1)
  - CycleResult + StateTransition records (frozen slots dataclasses)
  - transitions.transition pure function with `match prior.state:` (CLAUDE.md anti-pattern enforcement)
  - decision_table._DECISION_TABLE (20 rows -- 13 ActionKind, 5 skip:reason; 5 §4 categories the IssueCategory enum encodes)
  - select_top_priority_issue (RECOVERY_SPEC §5 priority order)
  - 6 pure gate functions (disconnected, maintenance, signal, same_action_backoff, ladder_backoff, exhausted)
  - engine.run_cycle: Diag x ModemState[] x GlobalsState x PolicyContext -> CycleResult
  - tools/check_spec.py CI gate (every §4 row referenced by spec-tests file)
  - tests/test_recovery_spec.py parametrized over all_table_rows()
  - 96 tests across the policy package (55 unit + 21 engine + 20 spec)
  - tests/conftest.py `settings` fixture for cross-module test sharing
requires: []
affects: []
key_files: []
key_decisions: []
patterns_established: []
observability_surfaces: []
drill_down_paths: []
duration: ~25min
verification_result: passed
completed_at: 2026-05-06
blocker_discovered: false
---
# T05: 02-core-daemon-laptop-testable 05

**# Phase 2 Plan 05: Policy Engine Summary**

## What Happened

# Phase 2 Plan 05: Policy Engine Summary

**Pure-function policy engine implementing RECOVERY_SPEC §8 atomic cycle ordering -- the load-bearing core of the daemon's "decide" seam, with zero kernel/network coupling enforced by mypy + grep + lint.**

## Performance

- **Duration:** ~25 minutes
- **Started:** 2026-05-06T16:25Z (after 02-03 completed)
- **Completed:** 2026-05-06T16:42Z
- **Tasks:** 2
- **Files created:** 15
- **Files modified:** 1 (`tests/conftest.py` -- added `settings` fixture)

## Sub-modules

| File | Role | Inputs | Outputs |
|------|------|--------|---------|
| `policy/transitions.py` | State-shape pure transition | `(ModemState, ModemSnapshot, PolicyContext)` | new `ModemState` (state / present / rf_blocked / recovering_level) |
| `policy/decision_table.py` | RECOVERY_SPEC §4 mapping + §5 priority | `IssueCategory`, `IssueDetail` | `ActionKind | "skip:reason" | None` |
| `policy/gates.py` | RECOVERY_SPEC §6 gate predicates | `(ModemState, ActionKind, ClockProto, Settings)` | `bool` (True = skip) |
| `policy/engine.py` | RECOVERY_SPEC §8 cycle orchestrator | `(Diag, dict[usb_path, ModemState], GlobalsState, PolicyContext)` | `CycleResult(plans, transitions, new_states, new_globals)` |
| `policy/context.py` | Pure-data context + ClockProto | -- | `PolicyContext` dataclass |
| `policy/result.py` | Wire result types | -- | `CycleResult`, `StateTransition` |

## Gates implemented

| Gate | Source spec | Pass-through | Skip |
|------|-------------|--------------|------|
| `gate_disconnected` | §6.5 | `state.present=True` | `state.present=False` (hard skip, reason `skip:disconnected`) |
| `gate_maintenance` | C-01 | maintenance off OR cheap action during window | maintenance on + destructive action (hard skip, `skip:maintenance`) |
| `gate_signal` | §6.1 | cheap action OR `state.rf_blocked=False` | destructive + `state.rf_blocked=True` (soft skip; `suppressed_by_signal_gate=True`) |
| `gate_same_action_backoff` | §6.2 / FR-25 | `last_action_monotonic=None` OR elapsed >= 300s | elapsed < 300s (soft skip; `suppressed_by_backoff=True`) |
| `gate_ladder_backoff` | §6.3 / FR-25.1 | cheap action OR no prior action OR elapsed >= 90s | destructive + elapsed < 90s (soft skip; `suppressed_by_backoff=True`) |
| `gate_exhausted` | §6.6 | state != exhausted OR cheap action (set_apn / fix_raw_ip) | exhausted + ladder action (hard skip, `skip:exhausted`) |

Hard skips short-circuit and produce a definitive `skip:<reason>` in `PlannedAction.reason`. Soft skips accumulate into the `suppressed_by_*` flag trio so the events log can show partial-skip causes (e.g. "would have been usb_reset; suppressed_by_signal_gate=True"). Counter bump only fires when ALL gates pass and `dry_run=False`.

## RECOVERY_SPEC §8 atomic ordering (engine.run_cycle)

For each modem:

1. `transition(prior, snap, ctx)` -> new `ModemState` shape (state/present/rf_blocked/recovering_level only)
2. `new_streak = (prior.healthy_streak + 1) if new_state.state == "healthy" else 0`
3. **Decay check:** if `new_streak >= ctx.config.healthy_streak_decay_k` (default 10), set `decayed_counters = {}` and `new_streak = 0`
4. `select_top_priority_issue(snap.issues)` -> highest-priority `Issue` (RECOVERY_SPEC §5: config > sim > datapath > registration > qmi)
5. `lookup_action(issue.category, issue.detail)` -> `ActionKind | "skip:reason" | None`
6. `_apply_gates_to_action` -> `(PlannedAction, would_execute: bool)`; gates run in §6 order
7. **Counter bump:** if `would_execute=True`, `new_counters[action] += 1`
8. **StateTransition record:** if `new_state.state != prior.state`, append a `StateTransition(usb_path, from_state, to_state, cause, new_modem_state)` for the events.jsonl writer

Steps 1-7 are entirely in-memory. The cycle driver in plan 02-10 calls `run_cycle`, dispatches `result.plans` (where `would_execute`-marked plans actually invoke `actions/`), then atomically persists `result.new_states` and `result.new_globals` in a single `state_store.save_modem_state` per modem. **A crash between selection and write is safe**: actions are idempotent, counters were not yet bumped on disk, next cycle re-reads pre-action state.

## Phase 4 hooks left open

- **`_global_driver_reset_eligible`** always returns False. Phase 4 wires the real RECOVERY_SPEC §6.4 check: `>=75% of expected modems with qmi_channel_hung issue AND >=1 has actionable signal AND elapsed since last driver_reset >= 3600s`. Phase 2's placeholder ensures the per-modem path runs and the early-return shape is in place; the replay harness (plan 02-10) classifies v1 driver_reset traces against this engine without needing to enable the placeholder.
- **Signal-quality thresholds** are module constants `_RSRP_FLOOR_DBM=-110`, `_RSRQ_FLOOR_DB=-15`, `_SNR_FLOOR_DB=0` in `transitions.py`. Phase 4 may promote them to `Settings` fields if operations needs per-fleet tuning.
- **Per-action timestamps for FR-25.** Today both same-action and ladder backoff gates read `state.last_action_monotonic` (single per-modem timestamp). Phase 4 may split into `last_action_monotonic_per_kind: dict[ActionKind, float]` so a soft_reset doesn't extend the modem_reset backoff window. Phase 2 ships the simpler model; behavior is conservative (more skips, never fewer).
- **Recovering ladder rung selection.** The `transition` function preserves `recovering_level` when the modem is still degraded; the actual rung-bump (level 1 -> 2 -> 3) lives in Phase 4's destructive action path because soft_reset is the only Phase-2 ladder rung.
- **Maintenance-window source.** `PolicyContext.maintenance_active: bool` is a flag the cycle driver computes from `GlobalsState.maintenance` (added in plan 02-09 per C-02). Phase 2 ships the predicate plumbing; the dual-clock expiry check is plan 02-09 territory.

## Decision table coverage vs RECOVERY_SPEC §4

| Coverage | Count |
|----------|-------|
| Rows in `_DECISION_TABLE` (this plan) | 20 |
| RECOVERY_SPEC §4 rows in the canonical 5 categories (config / sim / datapath / registration / qmi) | 20 |
| RECOVERY_SPEC §4 rows in OTHER categories (enumeration / power / thermal / zao) | 7 |
| Total RECOVERY_SPEC §4 rows | 27 |

The 7 rows the plan does NOT cover are categories the `IssueCategory` enum (Phase 1 wire/enums.py) does not currently encode -- they are observed by Phase 3's `dmesg`/udev plumbing (FR-14) and re-classified into one of the existing categories at the observer boundary. From CLAUDE.md hardware target list, these are:

- `enumeration / enumeration_missing` -- Phase 3 (dmesg + udev)
- `enumeration / enumeration_overcurrent` -- Phase 3 (dmesg)
- `power / autosuspend_on` -- Phase 3 (sysfs read; observer re-classifies as datapath)
- `thermal / thermal_warn` -- Phase 3 (dmesg; informational only, no action per spec)
- `thermal / thermal_critical` -- Phase 3 (dmesg)
- `zao / zao_unit_inactive` -- Phase 2 zao_log/ provides the observation; observer re-classifies (plan 02-04)
- `zao / zao_log_stale` -- Phase 2 zao_log/ provides the observation; observer logs and falls back to direct probing (FR-12)

These will be added as additional rows OR re-classified into existing categories upstream when Phase 3 lands the dmesg/udev event sources. The contract `tools/check_spec.py` enforces is "every row in `_DECISION_TABLE` has a test"; growing the table later just adds new spec-test parametrize cases.

## Task Commits

1. **Task 1: PolicyContext + transitions + gates + decision table + 4 unit-test files** -- `ccf5493` (feat)
2. **Task 2: engine.run_cycle + spec-as-tests + tools/check_spec.py + conftest settings fixture** -- `e448aa8` (feat)

(Plan-level metadata commit will follow this SUMMARY.)

## Files Created/Modified

**Created:**
- `src/spark_modem/policy/__init__.py` -- package marker + module-layout docstring
- `src/spark_modem/policy/context.py` -- `PolicyContext` + `ClockProto` Protocol
- `src/spark_modem/policy/result.py` -- `CycleResult` + `StateTransition` frozen dataclasses
- `src/spark_modem/policy/transitions.py` -- `transition()` with `match prior.state:` + `is_signal_below_gate()` + module-level RF thresholds
- `src/spark_modem/policy/decision_table.py` -- 20-row `_DECISION_TABLE`, `select_top_priority_issue`, `lookup_action`, `all_table_rows`
- `src/spark_modem/policy/gates.py` -- 6 pure gate functions
- `src/spark_modem/policy/engine.py` -- `run_cycle` orchestrator + `_apply_gates_to_action` + `_global_driver_reset_eligible` placeholder
- `tests/unit/policy/__init__.py` -- test package marker
- `tests/unit/policy/test_transitions.py` -- 14 tests (state-machine arms + rf_blocked thresholds + match-statement enforcement)
- `tests/unit/policy/test_decision_table.py` -- 16 tests (all rows resolve + priority order + skip-reason canonicalisation)
- `tests/unit/policy/test_gates.py` -- 19 tests (all 6 gates, all action kinds, threshold boundaries)
- `tests/unit/policy/test_streak.py` -- 6 tests (FR-26.1 round-trip across model_dump_json)
- `tests/unit/policy/test_engine.py` -- 21 tests (decision-table -> PlannedAction round-trip, dry-run, maintenance, decay at K=10, pure-function determinism, no-IO-imports regex)
- `tests/test_recovery_spec.py` -- 20 parametrized tests (one per `_DECISION_TABLE` row) + Coverage manifest docstring for `check_spec.py`
- `tools/check_spec.py` -- CI gate substring-matching enum values

**Modified:**
- `tests/conftest.py` -- added `settings` fixture (constructs default `Settings` for cross-module tests)

## Verification

- `python -m mypy --strict src/spark_modem/policy/ tests/unit/policy/ tools/check_spec.py` -- 0 issues across 14 source files
- `python -m ruff check src/spark_modem/policy/ tests/unit/policy/ tools/check_spec.py tests/test_recovery_spec.py` -- All checks passed
- `python -m pytest tests/unit/policy/ tests/test_recovery_spec.py -q` -- 96 passed
- `python -m pytest -q` (full suite) -- 446 passed, 41 skipped (no regressions; the 41 skips are all Windows-host POSIX-only tests, same as prior to this plan)
- `python tools/check_spec.py` -- "all 20 rows covered."
- `bash scripts/lint_no_subprocess.sh` -- exit 0
- `grep -E "^(import|from) " src/spark_modem/policy/ --include='*.py' -r | grep -E "subprocess|httpx|asyncio"` -- empty (purity invariant verified)
- `grep "match prior.state:" src/spark_modem/policy/transitions.py` -- 1 match (CLAUDE.md anti-pattern enforcement)

## Decisions Made

1. **transitions.py is pure shape only -- the engine owns counter + streak management.** A common alternative is to fold the streak update into `transition()` itself, but that mixes two concerns: the state-machine arrow (clean and unit-testable) and the engine's atomic ordering (which spans multiple stages of §8). Keeping them separate makes the engine's §8 ordering legible as a literal numbered sequence.
2. **ClockProto in context.py, shared by gates.py.** The plan suggested gates.py define its own ClockProto. Sharing one Protocol means a single edit to extend the surface (e.g. add `now_iso_with_tz()`) propagates uniformly. Both protocols are `Protocol`, so structural typing makes any conforming object accepted.
3. **Decision table uses str literals for skip:reason rather than a sealed enum.** The set of skip:reasons is intentionally open (Phase 4 may add `skip:carrier_throttled`, etc.). Strings starting with `skip:` are easier to extend without churning the enum + every test that imports it. The convention is enforced by `test_skip_reasons_are_canonical_strings`.
4. **`tools/check_spec.py` substring-matches enum values.** Parametrize ids are computed at test collection time, not file content. A "Coverage manifest" docstring block in `tests/test_recovery_spec.py` makes the coverage auditable by reading the file -- and by `check_spec.py` reading the same text. Adding a new row to `_DECISION_TABLE` requires adding the manifest line; the gate fails fast.
5. **Hard-skip vs soft-skip gates have different return semantics.** Hard skips (disconnected/maintenance/exhausted) return `(PlannedAction(reason="skip:..."), False)` and short-circuit. Soft skips (signal/backoff/ladder/dry_run) accumulate into `suppressed_by_*` flags. This is observable in events.jsonl: a hard-skipped action shows the canonical reason; a soft-skipped action shows `skip:gate_failed` + the suppressed_* flag trio for diagnostic inspection.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test `test_skip_reasons_are_canonical_strings` initially false-positive on ActionKind values**
- **Found during:** Task 1 first pytest run
- **Issue:** `ActionKind` is a `StrEnum`, so `isinstance(v, str)` is True for both ActionKind variants and skip:reason plain strings. The naive filter included `ActionKind.SET_APN` etc. and the assertion `s.startswith("skip:")` failed.
- **Fix:** Discriminate via `isinstance(v, str) and not isinstance(v, ActionKind)` before treating `v` as a skip-reason candidate.
- **Files modified:** `tests/unit/policy/test_decision_table.py` (in-task)
- **Committed in:** `ccf5493` (Task 1 commit)

**2. [Rule 2 - Missing Critical Functionality] Coverage manifest in spec-tests file**
- **Found during:** Task 2 verification (`python tools/check_spec.py` exit 1 with 20 missing rows)
- **Issue:** The plan-as-written has `tools/check_spec.py` substring-search the spec-tests file for enum values, but the parametrize ids are computed at runtime by `[_row_id(row) for row in all_table_rows()]` -- they don't appear as text in the file. The CI gate is the load-bearing acceptance criterion; without coverage proof it can't fire.
- **Fix:** Added a "Coverage manifest" docstring block listing every `category / detail` pair. `check_spec.py` continues to substring-match exactly as planned; the manifest gives it surface to match against. Adding a new `_DECISION_TABLE` row REQUIRES a manifest line edit -- this is the auditable contract.
- **Files modified:** `tests/test_recovery_spec.py`
- **Committed in:** `e448aa8` (Task 2 commit)

**3. [Rule 1 - Lint Fix] Module-level signal-quality threshold constants**
- **Found during:** Task 1 ruff check
- **Issue:** Ruff `PLR2004` flagged `-110`, `-15`, `0` as magic values in `is_signal_below_gate`. Inline `# noqa` was rejected; the cleaner fix is module-level `Final` constants.
- **Fix:** Added `_RSRP_FLOOR_DBM`, `_RSRQ_FLOOR_DB`, `_SNR_FLOOR_DB` at top of `transitions.py` with `Final` typing. Also collapsed the third return into a direct `return ... and ...` per `SIM103`.
- **Side benefit:** The constants are easier to grep-for if Phase 4 promotes them to Settings.
- **Files modified:** `src/spark_modem/policy/transitions.py` (in-task)
- **Committed in:** `ccf5493` (Task 1 commit)

**4. [Rule 1 - Lint Fix] Ruff N802 -- test name capitalization**
- **Found during:** Task 2 ruff check
- **Issue:** `test_run_cycle_decay_fires_at_K_consecutive_healthy` and `test_run_cycle_decay_does_not_fire_below_K` had a capital K (the symbolic name of the constant). Ruff `N802` requires snake_case.
- **Fix:** Renamed to `..._fires_at_k_consecutive_healthy` and `..._does_not_fire_below_k`. The K is still in the docstring.
- **Files modified:** `tests/unit/policy/test_engine.py` (in-task)
- **Committed in:** `e448aa8` (Task 2 commit)

---

**Total deviations:** 4 auto-fixed (1 bug, 1 missing critical functionality, 2 lint-driven refactors)
**Impact on plan:** Zero scope change. All four are mechanical fixes to land what the plan specified. The Coverage manifest deviation is the only one that affects the durable contract (it makes the CI gate actually usable); the others are intra-implementation polish.

## Threat surface scan

The plan's `<threat_model>` enumerates T-02-05-01..05. Implementation honors all five:

- **T-02-05-01 (Elevation -- pure-function boundary):** Verified by (a) `grep -E "^(import|from) " src/spark_modem/policy/ -r | grep -E "subprocess|httpx|asyncio"` empty, (b) `test_engine_imports_no_io_modules` regex check on `engine.py` source, (c) `bash scripts/lint_no_subprocess.sh` exit 0, (d) mypy --strict resolves all imports without policy/ touching kernel modules.
- **T-02-05-02 (Tampering -- counter decay timing):** Streak update + decay check + counter reset + state-shape are computed in-memory in one pass and returned as a frozen `new_states` dict. The cycle driver in plan 02-10 will persist via `state_store.save_modem_state()` in a single atomic write per modem.
- **T-02-05-03 (DoS -- engine input validation):** Wire models validate at the parse boundary (BaseWire frozen + extra='forbid'). `match prior.state:` is exhaustive over the 5-state Literal -- mypy --strict catches missing arms.
- **T-02-05-04 (Info disclosure -- PlannedAction.reason):** Reason strings are canonical: `action_planned:<kind>`, `skip:<reason>`. No PII embedded; ICCID/IMSI live in identity.json (Phase 1) and are redacted in support bundles (plan 02-09).
- **T-02-05-05 (Repudiation -- StateTransition record):** Every state change produces a `StateTransition` record consumed by `event_logger.append()` in plan 02-10's cycle driver. NFR-20 satisfied: every transition logged as a single JSON line.

No new security-relevant surface introduced beyond the threat register.

## Threat Flags

None. Implementation surface is fully covered by the existing register.

## Issues Encountered

The four lint/test tweaks documented under "Deviations" were the only friction. No design surprises -- the plan's pseudocode for `engine.run_cycle` translated cleanly to Python with the corrections noted (typed `Issue` params instead of `# type: ignore`, dry_run flag handling clarified to suppress AFTER soft-skip flags so reason strings remain coherent, inline import lifted to top of test_streak.py).

## User Setup Required

None.

## Next Plan Readiness

- **Plan 02-04 (observer/) unblocked.** It can now `from spark_modem.policy.engine import run_cycle` in plan 02-10's cycle driver. The observer's job is to produce the `Diag` snapshot the engine consumes; their interface is fully decoupled.
- **Plan 02-06 (actions/) unblocked.** It implements the cheap-action set whose `ActionKind` values appear in `PlannedAction.kind`. The dispatcher in 02-06 is the consumer of the engine's `result.plans` (filtered by `suppressed_by_*` flags).
- **Plan 02-07 (status_reporter/prom.py) unblocked.** The `modem_state_value{modem}` integer-encoded gauge maps directly onto `result.new_states[usb_path].state` via `state_to_int(...)` (Phase 1 wire helper).
- **Plan 02-08 (webhook/) unblocked.** State transitions trigger webhooks: `result.transitions` filtered to `(healthy -> degraded)` and `(recovering -> exhausted)` produce `HealthyToDegraded` and `RecoveringToExhausted` envelopes (Phase 1 wire/webhook.py).
- **Plan 02-10 (cycle driver + replay harness) unblocked.** The driver:
  1. Builds `PolicyContext(clock=Clock(), config=settings, maintenance_active=globals_state.maintenance.is_active(), expected_modem_count=4)`.
  2. Calls `result = run_cycle(diag, prior_states, globals_state, ctx)`.
  3. For each `plan in result.plans` where `not (plan.suppressed_by_*  any)`, calls `actions.dispatcher.execute_and_verify(plan.kind, plan.who, action_ctx)`.
  4. Atomically persists `result.new_states[usb_path]` and `result.new_globals` per modem via `state_store.save_modem_state` (Phase 1).
  5. Emits each `result.transitions` entry as an `events.jsonl` `state_transition` line.
- **Phase 4 (destructive actions + HIL) unblocked at the policy layer.** The decision table already lists `MODEM_RESET / USB_RESET / DRIVER_RESET` for the relevant rows; Phase 4 just registers their `actions/` implementations and flips `_global_driver_reset_eligible` to a real predicate.

## Self-Check: PASSED

All 15 created files exist on disk:

```
src/spark_modem/policy/__init__.py        -- present
src/spark_modem/policy/context.py         -- present
src/spark_modem/policy/result.py          -- present
src/spark_modem/policy/transitions.py     -- present
src/spark_modem/policy/decision_table.py  -- present
src/spark_modem/policy/gates.py           -- present
src/spark_modem/policy/engine.py          -- present
tests/unit/policy/__init__.py             -- present
tests/unit/policy/test_transitions.py     -- present
tests/unit/policy/test_decision_table.py  -- present
tests/unit/policy/test_gates.py           -- present
tests/unit/policy/test_streak.py          -- present
tests/unit/policy/test_engine.py          -- present
tests/test_recovery_spec.py               -- present
tools/check_spec.py                       -- present
```

Both task commits present in `git log`:
- `ccf5493` (Task 1) -- present
- `e448aa8` (Task 2) -- present

The modified file `tests/conftest.py` was confirmed updated (Read after Edit).

---
*Phase: 02-core-daemon-laptop-testable*
*Completed: 2026-05-06*
