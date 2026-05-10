---
phase: 04-destructive-actions-hil
plan: 04
subsystem: policy
tags: [pydantic-settings, ladder, recovery-spec, RELOAD_DATA, ADR-0006, ADR-0008]

# Dependency graph
requires:
  - phase: 02-core-daemon-laptop-testable
    provides: policy/ pure-function package (engine, gates, transitions, decision_table); ModemState 5+2 wire shape; per-action counters
  - phase: 04-destructive-actions-hil
    provides: 04-01 modem_reset action (rung 2); 04-02 usb_reset action (rung 3); 04-03 driver_reset action + 4 RELOAD_DATA Settings fields + _global_driver_reset_eligible 4-gate predicate
provides:
  - "policy/ladder.py: pure-function select_rung(base, counters, config) for RECOVERY_SPEC §4.1 escalation ladder"
  - "ModemState.last_action_monotonic_by_kind: per-kind monotonic timestamp dict (FR-25 / FR-25.1)"
  - "Re-keyed gate_same_action_backoff (per-kind) and gate_ladder_backoff (MAX over destructive kinds) reading the new dict"
  - "is_signal_below_gate(snap, config) — RECOVERY_SPEC §6.1 thresholds migrate from module Final constants to RELOAD_DATA Settings"
  - "6 new RELOAD_DATA Settings fields: signal_rsrp_floor_dbm, signal_rsrq_floor_db, signal_snr_floor_db, max_soft, max_modem, max_usb"
  - "Engine integrates ladder.select_rung() between decision_table.lookup_action and gate evaluation; emits skip:exhausted PlannedAction when all rungs at ceiling"
  - "Atomic per-kind timestamp bump alongside counter bump in ONE model_copy per cycle (RECOVERY_SPEC §8 / CLAUDE.md invariant 8)"
  - "Plan 04-03's getattr defensive reads in _global_driver_reset_eligible removed — direct ctx.config.signal_*_floor_* reads"
affects: [04-05-action-skipped-event, 04-07-hil-scenario-suite, phase-05-bench-shadow]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure-function ladder rung selector module (policy/ladder.py mirrors policy/transitions.py + policy/decision_table.py purity discipline)"
    - "Additive ModemState field with default_factory=dict for Phase 2 backwards-compat"
    - "Per-kind backoff dict keyed by ActionKind (replaces single global timestamp)"
    - "Atomic same-clock-read bump of legacy + new timestamp fields in one model_copy"
    - "Settings-migrated thresholds via PolicyContext.config (was module Final constants)"

key-files:
  created:
    - "src/spark_modem/policy/ladder.py — pure-function select_rung()"
    - "tests/unit/policy/test_ladder.py — 9 progression scenario + override tests"
  modified:
    - "src/spark_modem/wire/state.py — add last_action_monotonic_by_kind field"
    - "src/spark_modem/policy/gates.py — re-key both backoff gates on per-kind dict"
    - "src/spark_modem/policy/transitions.py — drop 3 Final constants; is_signal_below_gate(snap, config) signature; transition() threads ctx.config"
    - "src/spark_modem/policy/engine.py — wire select_rung; atomic per-kind timestamp bump; remove getattr defensive reads"
    - "src/spark_modem/config/settings.py — add 6 RELOAD_DATA fields (3 signal floors + 3 ladder ceilings)"
    - "src/spark_modem/policy/decision_table.py — ruff-format reflow only"
    - "tests/unit/wire/test_state.py — 3 new tests (default empty dict, Phase 2 JSON load, populated round-trip)"
    - "tests/unit/policy/test_gates.py — fixtures re-key; 4 new per-kind discrimination tests"
    - "tests/unit/policy/test_transitions.py — migrate 2 boundary tests + 4 new Settings-driven tests"
    - "tests/unit/policy/test_engine.py — 5 new tests: ladder integration, atomic bump (back-compat lock), no-bump on skip, Phase 2 state replay"
    - "tests/unit/config/test_settings.py — 11 new tests for the 6 new fields"
    - "tests/unit/policy/test_engine_driver_reset.py — 1 integration test pinning Settings-driven floors"

key-decisions:
  - "select_rung signature uses base parameter (not category) — engine has already done lookup_action() so the BASE ActionKind is in hand; passing it preserves DATAPATH base-rung-2 semantics ((DATAPATH, SESSION_DISCONNECTED) -> base MODEM_RESET; ladder starts at MODEM, never walks back to SOFT)"
  - "Legacy ModemState.last_action_monotonic preserved on the wire shape AND bumped atomically — back-compat contract for Phase 2 state-file replay; locked by test_engine_atomically_bumps_legacy_and_per_kind_timestamps; future engineer must NOT delete the legacy bump as dead code"
  - "Non-ladder ActionKinds (SET_APN, FIX_RAW_IP, SIM_POWER_ON, FIX_AUTOSUSPEND, SET_OPERATING_MODE, DRIVER_RESET) pass through select_rung unchanged — only the destructive triplet (SOFT/MODEM/USB_RESET) escalates"
  - "Engine collapses ladder dispatch into one isinstance check — `action_or_skip = select_rung(...)` rebinds on top of the lookup_action result; the existing isinstance(ActionKind|str) Step-6 dispatch handles both shapes; ruff PLR0912 satisfied without extracting a helper"
  - "test_engine_ladder_yields_skip_exhausted_when_all_rungs_full assertion shape: counters in new_state must EQUAL prior counters (no new bump) AND last_action_monotonic_by_kind must stay empty — proves both the absence-of-bump and the absence-of-counter-increment contracts"
  - "SP-04 lint reads ladder.py docstring text — replaced literal 'create_subprocess_exec' phrase with 'kernel-touching primitives' to avoid false positive on the lint regex (the lint script greps src/ for the literal token)"

patterns-established:
  - "Per-kind backoff timestamp dict pattern — extends to any future per-action timing (e.g. per-kind cooldown overrides) without changing wire shape; populates atomically alongside counter bump"
  - "Settings-migrated module constants — dropping Final constants in favor of RELOAD_DATA Settings fields keeps SIGHUP retunability without breaking call surface (signature changes from (snap) to (snap, config))"
  - "Ladder rebind pattern in engine — select_rung() returns ActionKind | 'skip:exhausted' so its result rebinds on top of action_or_skip without adding new control-flow branches"

requirements-completed: [FR-23]

# Metrics
duration: 15min
completed: 2026-05-10
---

# Phase 04 Plan 04-04: policy/ladder.py + per-action timestamps + signal-gate Settings migration Summary

**RECOVERY_SPEC §4.1 escalation ladder lands as a pure-function module; per-action timestamp dict supersedes the legacy single timestamp on both backoff gates; signal-gate thresholds migrate from module Final constants to 3 RELOAD_DATA Settings fields; 3 ladder ceilings join Settings; engine bumps legacy + new timestamp fields atomically in ONE model_copy per cycle (back-compat contract locked by I-03 test).**

## Performance

- **Duration:** 15 min
- **Started:** 2026-05-10T12:13:50Z
- **Completed:** 2026-05-10T12:28:44Z
- **Tasks:** 3
- **Files created:** 2 (`policy/ladder.py`, `test_ladder.py`)
- **Files modified:** 11 (5 src + 6 tests; one decision_table.py format-only reflow)

## Accomplishments

- New `policy/ladder.py` (76 LOC, pure-function): `select_rung(base, counters, config) -> ActionKind | "skip:exhausted"` walks `_LADDER_RUNGS` from the base index forward, promoting when `counters[rung] >= ceiling[rung]`; non-ladder ActionKinds (SET_APN, DRIVER_RESET, etc.) pass through unchanged
- `ModemState.last_action_monotonic_by_kind: dict[ActionKind, float] = Field(default_factory=dict)` — additive; Phase 2 state files load cleanly with empty default; legacy `last_action_monotonic` field PRESERVED on the wire shape
- Both backoff gates re-keyed: `gate_same_action_backoff` consults `state.last_action_monotonic_by_kind.get(action)`; `gate_ladder_backoff` takes `MAX(timestamps over destructive kinds)`. Phase 2 placeholder `del action  # reserved` removed
- `is_signal_below_gate(snap, config: Settings)` reads thresholds from Settings; 3 module-level Final constants (`_RSRP_FLOOR_DBM`, `_RSRQ_FLOOR_DB`, `_SNR_FLOOR_DB`) deleted; `transition()` threads `ctx.config` (the `del ctx` placeholder is gone)
- 6 new RELOAD_DATA Settings fields: 3 signal floors (defaults match RECOVERY_SPEC §6.1 verbatim: -110 / -15.0 / 0.0) + 3 ladder ceilings (max_soft=3, max_modem=2, max_usb=1 per RECOVERY_SPEC §4.1; all `ge=1`)
- Engine integrates `select_rung()` at Step 5.5 (between `lookup_action` and gate evaluation) and bumps both `last_action_monotonic` AND `last_action_monotonic_by_kind[counter_bump]` in ONE atomic `model_copy` (per RECOVERY_SPEC §8 / CLAUDE.md invariant 8)
- Plan 04-03's 3 `getattr(ctx.config, "signal_*_floor_*", default)` defensive reads in `_global_driver_reset_eligible` deleted; direct attribute reads now (Settings has the fields)
- 30+ new/migrated unit tests; full unit + integration suite 905 passed / 90 skipped (M7 30s budget preserved at ~14s)

## Task Commits

Each task TDD'd as RED → GREEN:

1. **Task 1 RED — Settings field tests** — `944f748` (test)
2. **Task 1 GREEN — 6 Settings fields + remove getattr** — `66eb77c` (feat)
3. **Task 2 RED — last_action_monotonic_by_kind / per-kind gates / ladder tests** — `b75f194` (test)
4. **Task 2 GREEN — ladder.py + ModemState field + re-keyed gates** — `4c9f469` (feat)
5. **Task 3 RED — ladder integration / atomic bump / signal-gate Settings tests** — `f9e8ff0` (test)
6. **Task 3 GREEN — engine wires ladder + atomic bump; transitions migrates to Settings** — `c02ca8b` (feat)

## Files Created/Modified

- `src/spark_modem/policy/ladder.py` (NEW, 76 LOC) — pure-function `select_rung()`; only typing + Settings + ActionKind imports
- `tests/unit/policy/test_ladder.py` (NEW) — 9 tests: 4 RECOVERY_SPEC §10.2 scenarios (A-D) + DATAPATH base-rung-2 path (2) + Settings overrides (1) + non-ladder passthrough (2)
- `src/spark_modem/wire/state.py` — `last_action_monotonic_by_kind` field with `default_factory=dict`; legacy field preserved with explicit "back-compat contract — do not delete the bump" comment
- `src/spark_modem/policy/gates.py` — `gate_same_action_backoff` keys per-kind; `gate_ladder_backoff` MAX over destructive kinds; ruff format reflowed `gate_ladder_backoff` return to one line
- `src/spark_modem/policy/transitions.py` — 3 Final constants + `Final` import dropped; `is_signal_below_gate(snap, config)` signature; `transition()` threads ctx.config; the `del ctx` placeholder is gone
- `src/spark_modem/policy/engine.py` — `from spark_modem.policy.ladder import select_rung`; Step 5.5 ladder dispatch (collapsed to single `action_or_skip = select_rung(...)` rebind to keep PLR0912 happy); Step 7 atomic bump of `last_action_monotonic` + `last_action_monotonic_by_kind`; `_fresh_initial_state` populates the new field; getattr defensive reads dropped
- `src/spark_modem/config/settings.py` — 6 new RELOAD_DATA fields with `json_schema_extra=RELOAD_DATA`; 3 floors as `int` / `float` with no `ge` constraint (RSRP can legitimately be a stricter -100, -90, etc.); 3 ladder ceilings with `ge=1`
- `src/spark_modem/policy/decision_table.py` — ruff format reflow only (lookup_action signature single-line)
- `tests/unit/wire/test_state.py` — 3 new tests: default empty dict, Phase 2 JSON load (asserts both new field defaults to {} AND legacy last_action_monotonic preserved AND counter survives), populated round-trip
- `tests/unit/policy/test_gates.py` — _state helper extended with `last_action_monotonic_by_kind` kwarg; 8 existing tests migrated to populate the per-kind dict; 4 new tests covering per-kind discrimination + MAX-over-destructive
- `tests/unit/policy/test_transitions.py` — 2 existing `is_signal_below_gate(snap)` calls migrated to (snap, settings); 4 new tests for B-03 (rsrp/rsrq/snr Settings reads + transition() threading)
- `tests/unit/policy/test_engine.py` — _state helper extended; existing backoff-suppression test populated with per-kind dict; 5 new tests: ladder integration (registration + skip:exhausted), atomic bump back-compat contract (I-03 fix), no-bump on signal-gate skip, Phase 2 state replay
- `tests/unit/config/test_settings.py` — 11 new tests covering defaults, RELOAD_DATA tagging, ge=1 validation, YAML round-trip on 6 fields
- `tests/unit/policy/test_engine_driver_reset.py` — 1 new integration test (`test_engine_reads_signal_floors_from_settings_directly`) pinning the 04-03 → 04-04 refactor: same Diag flips eligibility based on `signal_rsrp_floor_dbm` Settings override

## Decisions Made

- **select_rung uses `base` parameter, not `category`.** Engine already does `lookup_action(category, detail)` and gets a base ActionKind in hand. Passing the base lets the ladder respect DATAPATH base-rung-2 semantics: `(DATAPATH, SESSION_DISCONNECTED) -> base MODEM_RESET` — ladder starts at MODEM index, never walks backwards to SOFT. The plan body explicitly refines this signature.
- **Legacy `last_action_monotonic` preserved AND bumped.** Even though no gate consults it after this plan, the field stays on the wire shape (Phase 2 readers see it) and is bumped atomically alongside the new dict. The back-compat contract is locked by `test_engine_atomically_bumps_legacy_and_per_kind_timestamps` — a future engineer must NOT delete the legacy bump as dead code.
- **Non-ladder ActionKinds pass through `select_rung` unchanged.** SET_APN, FIX_RAW_IP, SIM_POWER_ON, FIX_AUTOSUSPEND, SET_OPERATING_MODE, DRIVER_RESET — only the destructive triplet (SOFT/MODEM/USB_RESET) escalates. The early-return `if base not in _LADDER_RUNGS: return base` keeps the contract obvious.
- **Engine collapses ladder dispatch to one rebind.** `action_or_skip = select_rung(...)` rebinds the variable in-place on top of the lookup_action result; the existing isinstance(ActionKind | str) Step-6 dispatch handles both shapes. PLR0912 (too many branches) satisfied without extracting a helper — keeps the cycle algorithm linear-readable per RECOVERY_SPEC §8.
- **skip:exhausted assertion in test_engine asserts counters carry forward unchanged.** Plan body said "counter NOT bumped" — the natural assertion is that prior counters survive (ladder didn't add a fresh increment on top) AND `last_action_monotonic_by_kind` stays empty. Both contracts pinned in one test.
- **SP-04 lint regex literally matches docstrings.** `scripts/lint_no_subprocess.sh` greps `src/` for `create_subprocess_exec|...|os.system` as a regex against ALL .py text including docstrings. Initial ladder.py docstring referenced the lint by mentioning "create_subprocess_exec etc." — the lint flagged it. Reworded to "kernel-touching primitives" to avoid the false positive.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Engine PLR0912 too-many-branches after ladder integration**
- **Found during:** Task 3 GREEN (engine ladder wiring)
- **Issue:** Adding the Step-5.5 ladder dispatch as `if isinstance ladder_result == "skip:exhausted": ... else: ...` pushed `run_cycle` over ruff PLR0912's 12-branch ceiling
- **Fix:** Collapsed the ladder dispatch to one rebind `action_or_skip = select_rung(...)`; the existing Step-6 isinstance(ActionKind | str) dispatch handles the two return shapes uniformly
- **Files modified:** src/spark_modem/policy/engine.py
- **Verification:** ruff check src/spark_modem/policy/ exits 0; full unit suite 877 pass
- **Committed in:** c02ca8b (Task 3 commit)

**2. [Rule 1 - Bug] SP-04 lint false-positive on ladder.py docstring**
- **Found during:** Task 2 GREEN (after creating ladder.py)
- **Issue:** ladder.py docstring referenced `scripts/lint_no_subprocess.sh enforces no \`create_subprocess_exec\` etc.` — the lint regex greps src/ as plain text and matched the literal string in the docstring
- **Fix:** Reworded the docstring to "the package-level SP-04 lint script enforces no kernel-touching primitives" — avoids the literal regex term
- **Files modified:** src/spark_modem/policy/ladder.py
- **Verification:** `bash scripts/lint_no_subprocess.sh` exits 0
- **Committed in:** 4c9f469 (Task 2 commit)

**3. [Rule 1 - Bug] gates.py + decision_table.py auto-formatted by ruff**
- **Found during:** Task 2 + Task 3 GREEN (post-edit format checks)
- **Issue:** ruff format --check flagged gates.py (multi-line return collapsed to one line in gate_ladder_backoff) and decision_table.py (lookup_action signature reflowed)
- **Fix:** Ran `ruff format` on both files; the changes are formatter-cosmetic only (no semantic changes)
- **Files modified:** src/spark_modem/policy/gates.py, src/spark_modem/policy/decision_table.py
- **Verification:** `ruff format --check src/spark_modem/policy/` exits 0
- **Committed in:** 4c9f469 + c02ca8b respectively

**4. [Rule 1 - Bug] test_run_cycle_counter_does_not_bump_when_skipped_by_gate fixture migration**
- **Found during:** Task 2 GREEN (full unit suite regression check)
- **Issue:** The existing test populated only `last_action_monotonic=0.0` (legacy field) to trigger same-action backoff. Once gates re-keyed off `last_action_monotonic_by_kind`, the legacy field no longer gates and the test failed
- **Fix:** Updated the test to populate `last_action_monotonic_by_kind={ActionKind.SET_APN: 0.0}` so the gate fires off the new dict; preserved the legacy-field assignment as documentation
- **Files modified:** tests/unit/policy/test_engine.py
- **Verification:** Full unit suite 868 pass after the migration
- **Committed in:** 4c9f469 (Task 2 commit)

---

**Total deviations:** 4 auto-fixed (1 lint-config bug, 1 lint-content bug, 2 formatter cleanups, 1 test fixture migration that is itself part of the plan's contract)
**Impact on plan:** All auto-fixes essential for shipping a green build under existing lint gates. No scope creep — every change traces to a Plan 04-04 contract or a CLAUDE.md invariant.

## Issues Encountered

- **Lint regex matches docstring text.** SP-04 lint pattern is `create_subprocess_exec|create_subprocess_shell|subprocess\.(...)|os\.system` applied as plain regex over `src/` .py files including docstrings. Documenting the lint in code is hazardous — note for future executors: avoid spelling out the forbidden tokens in docstrings.
- **PLR0912 ceiling on run_cycle.** The cycle algorithm is naturally branching (decision-table/skip/ladder/gate), and adding the ladder dispatch pushed it over the limit. The rebind pattern (single variable consumed by downstream isinstance dispatch) keeps it inside the budget without losing clarity.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

Phase 4 ladder + signal-gate machinery is operational:

- **Plan 04-05** (`ActionSkipped` event variant) can now consume `select_rung() == "skip:exhausted"` results and the per-kind suppressed_* flags to emit consumer-friendly events alongside PlannedAction
- **Plan 04-07** (HIL scenarios) can construct fault scenarios that walk the ladder rungs (SOFT_RESET fires 3x → MODEM_RESET → 2x → USB_RESET → exhausted) using the new counter ceilings; signal-gate scenarios can use Settings overrides to inject stricter floors per cohort
- **Phase 5** (bench shadow) inherits the SIGHUP-tunable signal floors via Settings RELOAD_DATA; per-cohort tuning is YAML-only

**Plan 04-04 status:** ✅ COMPLETE — 877 unit + 28 integration tests green; mypy --strict clean on 126 source files; ruff check + format clean; SP-04 lint clean; M7 30s budget preserved (~14s)

## Self-Check: PASSED

All claimed files exist and all task commits are visible in `git log`.

- src/spark_modem/policy/ladder.py: FOUND
- tests/unit/policy/test_ladder.py: FOUND
- 944f748 (Task 1 RED): FOUND
- 66eb77c (Task 1 GREEN): FOUND
- b75f194 (Task 2 RED): FOUND
- 4c9f469 (Task 2 GREEN): FOUND
- f9e8ff0 (Task 3 RED): FOUND
- c02ca8b (Task 3 GREEN): FOUND

## Threat Flags

None. All new surfaces match the plan's `<threat_model>` register (T-04-04-01..T-04-04-06).

---
*Phase: 04-destructive-actions-hil*
*Completed: 2026-05-10*
