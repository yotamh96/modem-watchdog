---
phase: 04-destructive-actions-hil
plan: 05
subsystem: wire+policy+daemon
tags: [pydantic-v2, discriminated-union, FR-23, ADR-0006, RECOVERY_SPEC-section-8, back-compat-horizon]

# Dependency graph
requires:
  - phase: 02-core-daemon-laptop-testable
    provides: Event tagged-union (13 variants pre-04-05), PlannedAction.suppressed_* flags, replay harness consumer of suppressed_* fields, EventLogWriter.append discipline
  - phase: 04-destructive-actions-hil
    provides: 04-04 ladder.select_rung -> "skip:exhausted" path; per-kind backoff timestamps; Settings-driven signal floors
provides:
  - "wire/enums.py: SkipReason closed StrEnum (7 values: signal_below_gate / ladder_backoff / same_action_backoff / exhausted / disconnected / maintenance / dry_run)"
  - "wire/enums.py: EventKind.ACTION_SKIPPED registered alongside the existing 10 EventKind values"
  - "wire/events.py: ActionSkipped variant + Event tagged-union extended 13 -> 14 variants with kind='action_skipped' discriminator"
  - "policy/result.py: CycleResult.skipped: list[ActionSkipped] field with default empty list"
  - "policy/engine.py: ActionSkipped emission on every gate-failure / hard-skip / dry-run / ladder-skip-exhausted path -- 7-of-7 SkipReason coverage"
  - "policy/engine.py: PlannedAction.suppressed_by_signal_gate / suppressed_by_backoff / suppressed_by_dry_run flags PRESERVED -- replay harness back-compat lock per CONTEXT B-04"
  - "daemon/cycle_driver.py: CycleResult.skipped flushed to event_logger.append AFTER the atomic state write per RECOVERY_SPEC §8"
  - "event_logger/writer.py: _EVENT_TYPES tuple covers the full 14-variant Event union (ActionSkipped + previously-uncovered SimSwapped/EventSourceCrashed)"
affects: [04-06-hil-infra-scaffold, 04-07-hil-scenario-suite, phase-05-bench-shadow]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Closed-enum SkipReason (W-04 discipline) -- adding a new gate failure mode is a deliberate enum extension, never a runtime string"
    - "Dual-emit at gate-failure path: engine emits ActionSkipped event AND PlannedAction.suppressed_* flags; replay harness keeps reading flags unmodified (CONTEXT B-04 'back-compat horizon')"
    - "_apply_gates_to_action returns 3-tuple (PlannedAction, would_execute, list[ActionSkipped]) -- threading the new emission through the existing gate evaluator without splitting hard-skip and soft-skip paths"
    - "Soft-skip distinguishes same_action vs ladder backoff at SkipReason emission time even though PlannedAction.suppressed_by_backoff conflates the two -- consumers of the new event get the precise reason"
    - "Engine helper extraction (_emit_skip_string_outputs + _finalize_per_modem_state) keeps run_cycle under PLR0912/PLR0915 ceilings without losing RECOVERY_SPEC §8 line-by-line readability"
    - "EventLogWriter._EVENT_TYPES gap-closure as a Rule 2 deviation -- the writer's isinstance gate now covers the full Event union, eliminating a latent TypeError on SimSwapped/EventSourceCrashed in production"

key-files:
  created:
    - "tests/unit/wire/test_action_skipped_event.py -- 16 tests covering closed-enum discipline + round-trip + tagged-union routing"
  modified:
    - "src/spark_modem/wire/enums.py -- new SkipReason StrEnum (7 values) + EventKind.ACTION_SKIPPED"
    - "src/spark_modem/wire/events.py -- new ActionSkipped variant + Event union 13 -> 14 variants + IssueCategory/IssueDetail/SkipReason imports"
    - "src/spark_modem/policy/result.py -- CycleResult.skipped: list[ActionSkipped] field"
    - "src/spark_modem/policy/engine.py -- emit ActionSkipped on every gate-failure path; capture base_for_ladder before select_rung rebinds; helper extraction for ruff PLR0912/PLR0915"
    - "src/spark_modem/daemon/cycle_driver.py -- post-state-write flush of CycleResult.skipped to event_logger.append (RECOVERY_SPEC §8 ordering)"
    - "src/spark_modem/event_logger/writer.py -- _EVENT_TYPES gap-closure (ActionSkipped + SimSwapped + EventSourceCrashed)"
    - "tests/unit/wire/test_events.py -- union-coverage test for ActionSkipped + import surface extended"
    - "tests/unit/policy/test_engine.py -- 12 new tests covering all 7 SkipReason paths + back-compat lock for suppressed_* flags + decision-table-skip exclusion"
    - "tests/unit/daemon/test_cycle_driver.py -- 2 new tests for the event_logger flush arm + empty-skipped-list no-op"

key-decisions:
  - "Decision-table-level skip strings (skip:requires_human / skip:no_card / skip:hardware / skip:carrier_denied) are NOT mapped to SkipReason values -- they are upstream of gate machinery; the existing PlannedAction with reason='skip:requires_human' remains the audit trail (CONTEXT B-04 threat register T-04-05-05 disposition: accept). Documented in code comment in _emit_skip_string_outputs."
  - "ActionSkipped emitted ALONGSIDE PlannedAction.suppressed_* flags, not replacing them. Plan 02-10 replay harness reads suppressed_by_signal_gate / suppressed_by_backoff / suppressed_by_dry_run from Phase 2 fixtures -- no shim needed, no harness change. Phase 5/6 may decide to drop the flags after consumers migrate (CONTEXT 'Discretion' deferred)."
  - "Soft-skip same-action vs ladder backoff distinguished at SkipReason emission time even though PlannedAction.suppressed_by_backoff is a single bool -- the engine calls gate_same_action_backoff and gate_ladder_backoff SEPARATELY (via short-circuit `(not suppressed_same_action) and gate_ladder_backoff(...)`) so consumers of ActionSkipped get the precise reason without losing PlannedAction back-compat."
  - "dry_run only emits ActionSkipped(reason=DRY_RUN) when no harder gate fired (signal/backoff already suppressing makes dry_run downstream-noise). Mirrors the existing PlannedAction.reason discipline ('skip:dry_run' only when nothing else suppressed)."
  - "Ladder skip:exhausted (Plan 04-04 select_rung output) emits ActionSkipped(reason=EXHAUSTED) using the BASE action (pre-ladder) as suppressed_action -- captured via base_for_ladder local variable BEFORE select_rung rebinds action_or_skip. This preserves the consumer-facing semantics: 'we tried to fire SOFT_RESET but the entire ladder is exhausted'."
  - "EventLogWriter._EVENT_TYPES gap-closure (Rule 2 auto-fix): the tuple was missing SimSwapped + EventSourceCrashed since Phase 3 -- the production daemon would have raised TypeError on first emission of either variant. Plan 04-05 closes the gap at the same time as adding ActionSkipped because the same isinstance gate is touched."
  - "transition() forces present=True in Phase 4 (observer-driven; udev-driven absence lands Phase 5+). The disconnected-gate test patches transition() with unittest.mock.patch to surface a present=False ModemState -- avoids dragging udev infrastructure into a unit test for a gate-emission contract."
  - "Engine helper extraction (_emit_skip_string_outputs + _finalize_per_modem_state) reduces run_cycle's branch and statement counts under ruff PLR0912 (>12) and PLR0915 (>50) ceilings. Mirrors Plan 04-04's rebind-pattern discipline (collapse paths into helpers, never lose RECOVERY_SPEC §8 line-by-line readability)."

patterns-established:
  - "First-class events alongside legacy flags (back-compat horizon pattern): introduce a richer event variant; emit it from the same code path that sets the legacy flags; preserve flags until consumer migration is complete; deprecate flags in a future phase via ADR. Replay harness keeps reading the legacy surface; new consumers (operators, dashboards) read the rich event."
  - "Closed-enum SkipReason with parametrized round-trip test -- @pytest.mark.parametrize over all 7 values acts as a coverage gate for the closed enum; adding an 8th value breaks the test and forces a deliberate plan."
  - "Discriminated-union extension with isinstance-tuple sync: when adding a new Event variant, the EventLogWriter._EVENT_TYPES tuple must be extended in lock-step. Future variant additions should grep for _EVENT_TYPES and audit the tuple."

requirements-completed: [FR-23]

# Metrics
duration: 14min
completed: 2026-05-10
---

# Phase 04 Plan 04-05: ActionSkipped Event Variant + SkipReason StrEnum + Engine/CycleDriver Wiring Summary

**Phase 4 B-04 / FR-23 SC#2 lands as a first-class `ActionSkipped` event variant (kind='action_skipped' discriminator) plus a closed `SkipReason` StrEnum with 7 canonical values; engine emits the event ALONGSIDE the legacy `PlannedAction.suppressed_*` flags on every gate-failure / hard-skip / dry-run / ladder-skip-exhausted path; cycle_driver flushes via event_logger.append AFTER the atomic state write per RECOVERY_SPEC §8; replay harness back-compat preserved (1003 replay tests still pass without modification).**

## Performance

- **Duration:** 14 min
- **Started:** 2026-05-10T12:35:30Z
- **Completed:** 2026-05-10T12:49:56Z
- **Tasks:** 2
- **Files created:** 1 (`tests/unit/wire/test_action_skipped_event.py`)
- **Files modified:** 9 (5 src + 4 tests)

## Accomplishments

- New `SkipReason(StrEnum)` in `wire/enums.py` with EXACTLY 7 closed values matching the canonical wire strings: `signal_below_gate / ladder_backoff / same_action_backoff / exhausted / disconnected / maintenance / dry_run`
- New `EventKind.ACTION_SKIPPED = "action_skipped"` registered alongside the existing 10 EventKind values
- New `ActionSkipped(_EventBase)` variant in `wire/events.py` with fields `kind: Literal["action_skipped"]`, `usb_path`, `suppressed_action: ActionKind`, `reason: SkipReason`, `cause_category: IssueCategory`, `cause_detail: IssueDetail`. Routed via the discriminator in the `Event` tagged union (now 14 variants)
- `policy/result.py` CycleResult gains `skipped: list[ActionSkipped] = field(default_factory=list)` -- additive; existing call sites that construct CycleResult without the new kwarg keep working
- `policy/engine.py` `_apply_gates_to_action` returns a 3-tuple `(PlannedAction, would_execute, list[ActionSkipped])` instead of 2-tuple. Hard-skip gates produce exactly one ActionSkipped event each (DISCONNECTED / MAINTENANCE / EXHAUSTED). Soft-skip path emits up to 3 (SIGNAL_BELOW_GATE + SAME_ACTION_BACKOFF or LADDER_BACKOFF + DRY_RUN, the last only when no harder gate already fired)
- `policy/engine.py` ladder skip:exhausted (Plan 04-04 `select_rung` output) emits an additional ActionSkipped(reason=EXHAUSTED) -- distinguishes from the hard-skip exhausted-state path (which uses the post-ladder action as suppressed_action; the ladder path uses the BASE action via the `base_for_ladder` local capture)
- `policy/engine.py` PRESERVES `PlannedAction.suppressed_by_signal_gate / suppressed_by_backoff / suppressed_by_dry_run` flags on every soft-skip path -- replay harness back-compat locked by `test_engine_preserves_planned_action_suppressed_flags_alongside_action_skipped`
- `daemon/cycle_driver.py` post-state-write loop flushes `CycleResult.skipped` to `event_logger.append(skipped)` -- order is state-write FIRST, event-log SECOND per RECOVERY_SPEC §8 (state authoritative; events.jsonl advisory)
- `event_logger/writer.py` `_EVENT_TYPES` tuple gap-closure: now covers the full 14-variant Event union (ActionSkipped + previously-uncovered SimSwapped + EventSourceCrashed)
- 16 new tests in `tests/unit/wire/test_action_skipped_event.py` covering closed-enum size + canonical strings + discriminator routing + parametrized round-trip across all 7 SkipReason values + extra-fields rejection
- 12 new tests in `tests/unit/policy/test_engine.py` covering all 7 SkipReason emission paths (signal / same_action / ladder / exhausted-hard-skip / exhausted-ladder / disconnected / maintenance / dry_run) + PlannedAction back-compat lock + decision-table-skip-strings exclusion + empty-list no-issues path
- 2 new tests in `tests/unit/daemon/test_cycle_driver.py` for the cycle_driver flush arm: ActionSkipped events appear in events.jsonl post-cycle; empty skipped list does not block other event flow
- 1 new test in `tests/unit/wire/test_events.py` for the union-coverage of ActionSkipped via `EventAdapter`
- Full unit suite: **908 passed** (894 prior + 14 net new), 82 skipped, 1 deselected; full integration suite: **28 passed**; replay regression suite: **1003 passed** (back-compat preserved)
- mypy --strict clean on 126 source files; ruff check clean on touched files; ruff format --check clean on touched files; SP-04 lint (`scripts/lint_no_subprocess.sh`) clean

## Task Commits

Each task TDD'd as RED → GREEN:

1. **Task 1 RED — wire-level tests for SkipReason / ActionSkipped / Event union** — `b3bb933` (test)
2. **Task 1 GREEN — SkipReason StrEnum + EventKind.ACTION_SKIPPED + ActionSkipped variant + Event union extension** — `b559737` (feat)
3. **Task 2 RED — engine + cycle_driver tests for ActionSkipped emission and flush** — `de615c9` (test)
4. **Task 2 GREEN — CycleResult.skipped + engine emission on every gate-failure path + cycle_driver flush + EventLogWriter gap-closure + helper extraction for ruff PLR0912/PLR0915** — `f62b8a4` (feat)

## Files Created/Modified

- `tests/unit/wire/test_action_skipped_event.py` (NEW, 16 tests) -- closed-enum size, canonical strings, EventKind value, construction with required fields, model_dump_json round-trip, kind discriminator routing through `EventAdapter`, rejection of unknown reason strings (W-04), parametrized round-trip across all 7 SkipReason values, EventAdapter round-trip for the variant, BaseWire frozen+extra=forbid rejection
- `src/spark_modem/wire/enums.py` -- new `SkipReason(StrEnum)` (7 values) + `EventKind.ACTION_SKIPPED = "action_skipped"`; closed-enum docstring captures the 1:1 mapping to engine gate-failure paths
- `src/spark_modem/wire/events.py` -- imports extended (`IssueCategory`, `IssueDetail`, `SkipReason`); new `ActionSkipped(_EventBase)` variant with full docstring tying SkipReason values back to the gate machinery + decision-table-skip exclusion note; `Event` Annotated tagged union grows from 13 to 14 variants
- `src/spark_modem/policy/result.py` -- new `from spark_modem.wire.events import ActionSkipped` import; `CycleResult.skipped: list[ActionSkipped] = field(default_factory=list)` field with docstring tying back to RECOVERY_SPEC §8 ordering
- `src/spark_modem/policy/engine.py` -- imports extended (`SkipReason`, `ActionSkipped`); `run_cycle` accumulates `skipped_out: list[ActionSkipped] = []`; captures `base_for_ladder` BEFORE `select_rung` rebinds; passes `cause_category` + `cause_detail` to `_apply_gates_to_action` via kwargs; CycleResult constructor now also takes `skipped=skipped_out`; `_apply_gates_to_action` signature extended with required-kwarg `cause_category` + `cause_detail` and returns 3-tuple; soft-skip path now distinguishes `gate_same_action_backoff` vs `gate_ladder_backoff` separately; new `_emit_skip_string_outputs` helper handles decision-table-skip + ladder-skip-exhausted routing; new `_finalize_per_modem_state` helper consolidates Step 7 (counter bump + atomic model_copy) -- both extractions keep `run_cycle` under PLR0912/PLR0915 ruff ceilings
- `src/spark_modem/daemon/cycle_driver.py` -- new for-loop in `_persist_states_and_globals` after the StateTransition emission loop: `for skipped in cycle_result.skipped: self._events.append(skipped)`; comment ties ordering to RECOVERY_SPEC §8 (state authoritative, events advisory)
- `src/spark_modem/event_logger/writer.py` -- `_EVENT_TYPES` tuple now imports + lists `ActionSkipped`, `SimSwapped`, `EventSourceCrashed` (gap-closure for the full 14-variant Event union; comment captures the Rule 2 disposition)
- `tests/unit/wire/test_events.py` -- import surface extended; new `test_event_tagged_union_includes_action_skipped` test that round-trips an ActionSkipped JSON shape through `EventAdapter` and asserts isinstance + reason routing
- `tests/unit/policy/test_engine.py` -- imports extended (`SkipReason`, `ActionSkipped`, `unittest.mock.patch as _patch`); 12 new tests at the bottom of the file covering: `test_engine_emits_action_skipped_on_signal_gate`, `test_engine_preserves_planned_action_suppressed_flags_alongside_action_skipped`, `test_engine_emits_action_skipped_on_same_action_backoff`, `test_engine_emits_action_skipped_on_ladder_backoff`, `test_engine_emits_action_skipped_on_exhausted_state`, `test_engine_emits_action_skipped_on_disconnected`, `test_engine_emits_action_skipped_on_maintenance`, `test_engine_emits_action_skipped_on_dry_run`, `test_engine_emits_action_skipped_on_ladder_skip_exhausted`, `test_engine_skipped_list_empty_when_no_gate_fires`, `test_engine_skipped_list_empty_on_no_issues`, `test_engine_skipped_list_empty_on_decision_table_skip`
- `tests/unit/daemon/test_cycle_driver.py` -- imports extended; new `_patched_run_cycle_with_skipped` helper; 2 new tests: `test_cycle_driver_appends_action_skipped_to_event_logger` (asserts events.jsonl line shape with canonical wire strings); `test_cycle_driver_does_not_emit_action_skipped_when_skipped_list_empty` (asserts state-transition flow continues unchanged)

## Decisions Made

- **Decision-table-level skip strings stay unmapped.** `skip:requires_human` / `skip:no_card` / `skip:hardware` / `skip:carrier_denied` are upstream of the gate machinery (no action was selected). SkipReason is for GATE-failure paths only (CONTEXT B-04 threat register T-04-05-05 disposition: accept). Documented in code comment in `_emit_skip_string_outputs`. Pinned by `test_engine_skipped_list_empty_on_decision_table_skip`.
- **Dual-emit at gate-failure path.** ActionSkipped event emitted ALONGSIDE PlannedAction.suppressed_* flags, not replacing them. Plan 02-10 replay harness reads suppressed_by_signal_gate / suppressed_by_backoff / suppressed_by_dry_run from Phase 2 fixtures -- no shim needed, no harness change. Lock-test: `test_engine_preserves_planned_action_suppressed_flags_alongside_action_skipped`. Phase 5/6 may decide to drop the flags after consumers migrate (CONTEXT 'Discretion' deferred).
- **Soft-skip same_action vs ladder distinguished at emission time.** PlannedAction.suppressed_by_backoff is a single bool (back-compat). The engine calls `gate_same_action_backoff` and `gate_ladder_backoff` SEPARATELY (via `suppressed_ladder = (not suppressed_same_action) and gate_ladder_backoff(...)`) so consumers of ActionSkipped get the precise SkipReason without losing PlannedAction back-compat.
- **dry_run only emits when no harder gate fired.** Mirrors PlannedAction.reason discipline ('skip:dry_run' only when nothing else suppressed). Code: `if suppressed_dry_run and not (suppressed_signal or suppressed_backoff): skipped_events.append(...)`.
- **Ladder skip:exhausted uses BASE action (pre-ladder) as suppressed_action.** Captured via `base_for_ladder` local before `select_rung` rebinds action_or_skip. Consumer-facing semantics: 'we tried to fire SOFT_RESET but the entire ladder is exhausted', not 'we tried to fire skip:exhausted'. Pinned by `test_engine_emits_action_skipped_on_ladder_skip_exhausted`.
- **EventLogWriter._EVENT_TYPES gap-closure (Rule 2).** Pre-existing tuple was missing SimSwapped + EventSourceCrashed since Phase 3 -- production daemon would have raised TypeError on first emission of either variant in a real (non-fake) event_logger. Plan 04-05 closes the gap at the same time as adding ActionSkipped. Comment captures the rationale and ties future variant additions to the audit responsibility.
- **transition() patched in disconnected test.** transition() forces present=True in Phase 4 (observer-driven; udev-driven absence lands Phase 5+). The disconnected-gate test uses `unittest.mock.patch` to surface a present=False ModemState -- avoids dragging udev infrastructure into a unit test for a gate-emission contract.
- **Engine helper extraction (PLR0912 + PLR0915 fix).** `run_cycle` was over the ruff branch (12) and statement (50) limits after the new ActionSkipped wiring. Extracted `_emit_skip_string_outputs` (handles decision-table-skip + ladder-skip-exhausted) and `_finalize_per_modem_state` (Step 7 counter bump + atomic model_copy). Mirrors Plan 04-04's rebind-pattern discipline: collapse paths into helpers, never lose RECOVERY_SPEC §8 line-by-line readability.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test fixture for ladder backoff used SOFT_RESET timestamp, but SOFT_RESET is NOT in `_DESTRUCTIVE_KINDS`**
- **Found during:** Task 2 GREEN (running new engine tests)
- **Issue:** Initial test populated `last_action_monotonic_by_kind={ActionKind.SOFT_RESET: 0.0}`; gate_ladder_backoff iterates over `_DESTRUCTIVE_KINDS = {MODEM_RESET, USB_RESET, DRIVER_RESET}` and ignores SOFT_RESET -- gate didn't fire, test failed
- **Fix:** Repopulated fixture with `last_action_monotonic_by_kind={ActionKind.USB_RESET: 0.0}` (a destructive kind, recent timestamp); test action MODEM_RESET (different destructive kind) is suppressed by the MAX-over-destructive-kinds gate
- **Files modified:** tests/unit/policy/test_engine.py
- **Verification:** test_engine_emits_action_skipped_on_ladder_backoff passes
- **Committed in:** f62b8a4 (Task 2 GREEN)

**2. [Rule 1 - Bug] Test fixture for exhausted state used QMI_CHANNEL_HUNG, which triggers global driver_reset**
- **Found during:** Task 2 GREEN (running new engine tests)
- **Issue:** Initial test used QMI_CHANNEL_HUNG. With expected_modem_count=1 in `_ctx`, the global driver_reset short-circuit fired (1/1 hung modems = 100% threshold met); engine bypassed the per-modem path entirely, so no per-modem ActionSkipped emission
- **Fix:** Changed fixture to `NOT_REGISTERED_SEARCHING` -> base SOFT_RESET (no driver_reset eligibility); ladder.select_rung returns SOFT_RESET on empty counters; SOFT_RESET is NOT in `_CHEAP_KINDS_DURING_EXHAUSTED = {SET_APN, FIX_RAW_IP}`; gate_exhausted fires; ActionSkipped(reason=EXHAUSTED) emitted
- **Files modified:** tests/unit/policy/test_engine.py
- **Verification:** test_engine_emits_action_skipped_on_exhausted_state passes
- **Committed in:** f62b8a4 (Task 2 GREEN)

**3. [Rule 2 - Missing critical functionality] EventLogWriter._EVENT_TYPES tuple was missing SimSwapped + EventSourceCrashed**
- **Found during:** Task 2 GREEN (running cycle_driver test that flushed an ActionSkipped through a real EventLogWriter)
- **Issue:** First failure was for ActionSkipped (Plan 04-05 forgot to extend `_EVENT_TYPES`). Investigating, also discovered the tuple was missing SimSwapped + EventSourceCrashed since Phase 3 -- the production daemon would have raised TypeError on first emission of either variant if a real (non-fake) EventLogWriter were used. Tests that use the production EventLogWriter (cycle_driver tests) had not exercised these paths previously
- **Fix:** Added all three (ActionSkipped + SimSwapped + EventSourceCrashed) to `_EVENT_TYPES`; comment captures Rule 2 rationale + future audit responsibility
- **Files modified:** src/spark_modem/event_logger/writer.py
- **Verification:** test_cycle_driver_appends_action_skipped_to_event_logger passes; full sim_swap regression suite (8 tests) still green
- **Committed in:** f62b8a4 (Task 2 GREEN)

**4. [Rule 1 - Bug] disconnected gate test could not construct present=False fixture without monkey-patch**
- **Found during:** Task 2 GREEN (running new engine tests)
- **Issue:** transition() always forces present=True in Phase 4 (observer-driven; the modem is in the snapshot map, so it's present). The disconnected gate fires only when udev-driven absence lands Plan 03-02+, which the engine doesn't reach in a unit test
- **Fix:** Used `unittest.mock.patch("spark_modem.policy.engine.transition", return_value=absent_state)` to inject a present=False ModemState; gate fires; ActionSkipped(reason=DISCONNECTED) emitted. Imported `patch as _patch` at module top after ruff PLC0415 flagged inline imports
- **Files modified:** tests/unit/policy/test_engine.py
- **Verification:** test_engine_emits_action_skipped_on_disconnected passes
- **Committed in:** f62b8a4 (Task 2 GREEN)

**5. [Rule 1 - Bug] run_cycle blew through ruff PLR0912 (>12 branches) + PLR0915 (>50 statements) ceilings after ActionSkipped wiring**
- **Found during:** Task 2 GREEN (post-edit ruff check)
- **Issue:** Adding the ActionSkipped emission paths (cause_category/cause_detail threading + ladder skip:exhausted emission + skipped_out accumulator) pushed `run_cycle` over both ruff thresholds
- **Fix:** Extracted two helpers without losing RECOVERY_SPEC §8 line-by-line readability:
  - `_emit_skip_string_outputs` -- handles decision-table-skip + ladder-skip-exhausted (the `elif isinstance(action_or_skip, str)` branch body)
  - `_finalize_per_modem_state` -- Step 7 counter bump + atomic model_copy
- **Files modified:** src/spark_modem/policy/engine.py
- **Verification:** ruff check clean; full unit suite 908 pass; tests for atomic-bump back-compat (test_engine_atomically_bumps_legacy_and_per_kind_timestamps) still green
- **Committed in:** f62b8a4 (Task 2 GREEN)

**6. [Rule 1 - Bug] ruff auto-organised imports + ruff format reflow**
- **Found during:** Task 1 + Task 2 GREEN (post-edit ruff checks)
- **Issue:** New imports in test_action_skipped_event.py and test_cycle_driver.py needed re-sort; engine.py + test_engine.py needed ruff format reflow after the helper extraction
- **Fix:** Ran `ruff check --fix` for imports and `ruff format` on the touched files
- **Files modified:** tests/unit/wire/test_action_skipped_event.py, tests/unit/daemon/test_cycle_driver.py, src/spark_modem/policy/engine.py, tests/unit/policy/test_engine.py
- **Verification:** ruff check + ruff format --check both clean on touched files
- **Committed in:** b559737 (test_action_skipped_event.py); f62b8a4 (the rest)

---

**Total deviations:** 6 auto-fixed (3 test fixture corrections, 1 Rule 2 wire-boundary gap-closure, 1 helper-extraction PLR0912/PLR0915 fix, 1 ruff hygiene cleanup)
**Impact on plan:** All auto-fixes essential for shipping a green build under existing lint gates and test contract. No scope creep -- every change traces to a Plan 04-05 contract or a CLAUDE.md invariant. Rule 2 EventLogWriter gap-closure was discovered while implementing Plan 04-05 but the underlying gap is pre-existing (Phase 3 era); fixing it now is correctness-required because the production daemon would otherwise raise TypeError when CycleDriver flushes a SimSwapped/EventSourceCrashed/ActionSkipped event through a non-fake event_logger.

## Issues Encountered

- **`_EVENT_TYPES` tuple drift (pre-existing).** EventLogWriter has an isinstance gate that must be kept in sync with the Event union. Phase 3 added SimSwapped + EventSourceCrashed without updating the tuple -- only fake event_loggers in tests caught the gap, so production was latent. Plan 04-05 closes this by adding all three new-since-Phase-2 variants. Recommendation for future executors: when adding a new Event variant, grep for `_EVENT_TYPES` and audit the tuple.
- **transition() forces present=True in Phase 4.** The disconnected gate exists at the engine level but cannot fire in a Phase 4 unit test without monkey-patching (no Phase 5 udev-driven absence yet). Test uses `unittest.mock.patch` to inject a present=False state. Future Phase 5 work that lands real udev absence detection should re-evaluate whether the patch is still needed.
- **Pre-existing ruff format drift on unrelated files.** 6 files (cli/ctl/support_bundle.py, cli/explain.py, tests/unit/policy/test_decision_table.py, tests/unit/policy/test_engine_driver_reset.py, tests/unit/policy/test_gates.py, tests/unit/policy/test_ladder.py) have `ruff format --check` violations that pre-date Plan 04-05. Per SCOPE BOUNDARY rule they are NOT auto-fixed; they remain in `.planning/phases/04-destructive-actions-hil/deferred-items.md` (which already lists this drift from Plan 04-01 onwards).

## User Setup Required

None -- no external service configuration required.

## Next Phase Readiness

Phase 4 ActionSkipped wiring is operational:

- **Plan 04-06** (HIL infra scaffold) and **Plan 04-07** (HIL scenario suite) can now construct fault scenarios that assert ActionSkipped emissions in events.jsonl with the canonical SkipReason wire strings (e.g. RF-blocked HIL scenario asserts `kind="action_skipped" and reason="signal_below_gate"` lines)
- **Phase 5** (bench shadow) inherits both surfaces (events.jsonl ActionSkipped AND PlannedAction.suppressed_*); the back-compat horizon decision can be revisited when Phase 5/6 has real-fleet consumer migration data
- **Replay harness** (Plan 02-10) is unchanged -- the new ActionSkipped events are purely additive; replay's per-cycle classifier reads only PlannedAction.suppressed_* from Phase 2 fixtures (1003 replay tests still green post-04-05)

**Plan 04-05 status:** COMPLETE -- 908 unit + 28 integration + 1003 replay tests green; mypy --strict clean on 126 source files; ruff check + format clean on touched files; SP-04 lint clean

## Self-Check: PASSED

All claimed files exist and all task commits are visible in `git log`.

- src/spark_modem/wire/enums.py (modified): FOUND
- src/spark_modem/wire/events.py (modified): FOUND
- src/spark_modem/policy/result.py (modified): FOUND
- src/spark_modem/policy/engine.py (modified): FOUND
- src/spark_modem/daemon/cycle_driver.py (modified): FOUND
- src/spark_modem/event_logger/writer.py (modified): FOUND
- tests/unit/wire/test_action_skipped_event.py (NEW): FOUND
- tests/unit/wire/test_events.py (modified): FOUND
- tests/unit/policy/test_engine.py (modified): FOUND
- tests/unit/daemon/test_cycle_driver.py (modified): FOUND
- b3bb933 (Task 1 RED): FOUND
- b559737 (Task 1 GREEN): FOUND
- de615c9 (Task 2 RED): FOUND
- f62b8a4 (Task 2 GREEN): FOUND

## Threat Flags

None. All new surfaces match the plan's `<threat_model>` register (T-04-05-01..T-04-05-05). The Rule 2 EventLogWriter gap-closure for SimSwapped + EventSourceCrashed does not introduce new surface -- it ENABLES emission paths that already existed in cycle_driver but would have raised TypeError in production; the events.jsonl write surface is unchanged (T-04-05-01 disposition: accept stays valid; the file is owned by the daemon at 0o640).

---
*Phase: 04-destructive-actions-hil*
*Completed: 2026-05-10*
