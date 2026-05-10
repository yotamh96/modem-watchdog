---
phase: 04-destructive-actions-hil
plan: 01
subsystem: actions
tags: [modem_reset, qmicli, dispatcher, action-registry, dms_set_operating_mode]

# Dependency graph
requires:
  - phase: 02-core-daemon-laptop-testable
    provides: actions/dispatcher._REGISTRY, actions/soft_reset.py analog, QmiWrapper.dms_set_operating_mode("reset"), VerifyResult.deferred(), CLI cli/reset.py with is_registered() guard
  - phase: 01-foundations-adrs
    provides: ActionKind.MODEM_RESET enum value, WhoModem, ActionContext, QmiErrorReason.PROXY_DIED/TIMEOUT
provides:
  - actions/modem_reset.py (new) — execute() + verify() for ladder rung 2
  - dispatcher._REGISTRY append — ActionKind.MODEM_RESET routed to modem_reset.{execute,verify}
  - cli/reset.py wording change — destructive-guard message rewritten as generic "is not registered"
  - Phase 4 dispatcher contract: 7 ActionKinds registered (was 6); kind-count test renamed to _seven_kinds
affects:
  - 04-02 (usb_reset action) — will rename _seven_kinds -> _eight_kinds + flip USB_RESET in test_modem_reset_registered_phase4
  - 04-03 (driver_reset action) — will rename _eight_kinds -> _nine_kinds + flip DRIVER_RESET; rotate test_dispatch_unknown_kind probe to a synthetic kind
  - 04-04 (ladder + signal gate + per-action timestamps) — wires the engine-side gating that distinguishes MODEM_RESET from SOFT_RESET (same QMI verb; different rung + signal gate per A-01)
  - 04-05 (ActionSkipped event) — replay harness back-compat shim around the new event variant; not affected by Plan 04-01

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Verbatim-mirror pattern: new destructive actions copy soft_reset.py shape with kind enum + failure_reason prefix substitutions; same QMI verb (A-01)."
    - "Dispatcher-count assertion rename per plan: 04-01 -> _seven_kinds, 04-02 -> _eight_kinds, 04-03 -> _nine_kinds. Wave ordering guarantees correctness at each plan's commit time."
    - "CLI guard message becomes kind-agnostic: 'reset: action {k} is not registered; valid: ...' — same shape for Phase 4 and any future kinds without phase-specific wording drift."

key-files:
  created:
    - src/spark_modem/actions/modem_reset.py
    - tests/unit/actions/test_modem_reset.py
    - .planning/phases/04-destructive-actions-hil/deferred-items.md
  modified:
    - src/spark_modem/actions/dispatcher.py (import + _REGISTRY row)
    - src/spark_modem/cli/reset.py (rejection message + module docstring)
    - tests/unit/actions/test_dispatcher.py (rename count test + invert destructive-guard test + pivot unknown-kind probe)
    - tests/unit/cli/test_reset.py (replace destructive-rejection tests with new "is not registered" assertions; add modem_reset smoke test; add quantum_tunnel regression)

key-decisions:
  - "Followed plan A-01 verbatim: modem_reset.py is a verbatim mirror of soft_reset.py with three substitutions (ActionKind enum, failure_reason prefix, module docstring). Same dms_set_operating_mode('reset') verb. The ladder/signal-gate distinction is engine-side (Plan 04-04)."
  - "Pivoted test_dispatch_unknown_kind_returns_failure to probe USB_RESET (still unregistered) instead of MODEM_RESET (newly registered). Documented the rotation expectation for Plans 04-02 / 04-03 in the docstring."
  - "Acceptance criterion 'ActionKind.MODEM_RESET — 3 occurrences' was a planner miscount: actual analog (soft_reset) has 2 occurrences (success + failure branches). Verified via grep -c on soft_reset.py for shape parity."
  - "10 pre-existing ruff format drifts in unrelated files (policy/, daemon/, cli/explain.py, etc.) discovered during full-suite verification. Logged to deferred-items.md per SCOPE BOUNDARY rule; not auto-fixed (not touched by this plan)."

patterns-established:
  - "Phase 4 destructive-action skeleton: docstring references RECOVERY_SPEC §4.1 ladder rung + the engine-side gates that distinguish it from cheap analogs; execute() body == soft_reset shape with kind-name substitutions; verify() returns deferred unconditionally."
  - "Cross-plan test rename convention: when an assertion's expected value changes monotonically across sequential plans (6 -> 7 -> 8 -> 9 here), rename the test name to encode the value at that plan's commit time. Future planners and reviewers can grep the rename across plans to audit wave ordering correctness."

requirements-completed: [FR-23, FR-27]

# Metrics
duration: 6min
completed: 2026-05-10
---

# Phase 04 Plan 01: modem_reset action + dispatcher registration Summary

**MODEM_RESET registered as ladder rung 2 destructive action — same `dms_set_operating_mode("reset")` QMI verb as soft_reset (A-01 policy distinction); deferred-verify shape mirrors Phase 2's soft_reset; CLI guard wording rewritten generic for the Phase 4 mixed-registration era.**

## Performance

- **Duration:** ~6 min (377 s)
- **Started:** 2026-05-10T11:11:02Z
- **Completed:** 2026-05-10T11:17:18Z
- **Tasks:** 2 (each TDD: RED + GREEN)
- **Files modified:** 7 (1 new src module, 1 modified src module, 1 modified CLI module, 1 new test file, 2 modified test files, 1 new deferred-items doc)

## Accomplishments

- New `src/spark_modem/actions/modem_reset.py` (63 LOC) — verbatim mirror of `soft_reset.py` with `ActionKind.MODEM_RESET` + `failure_reason="modem_reset:..."` substitutions; same `dms_set_operating_mode("reset")` QMI verb per CONTEXT A-01; `verify()` returns `VerifyResult.deferred(detail="next_cycle_observation")` per A-04.
- `actions/dispatcher.py:_REGISTRY` size **6 → 7**: appended `ActionKind.MODEM_RESET: (modem_reset.execute, modem_reset.verify)` row + corresponding import. USB_RESET / DRIVER_RESET remain unregistered (Plans 04-02 / 04-03).
- `cli/reset.py` destructive-guard wording rewritten: was `"is destructive (Phase 4); Phase 2 supports: ..."`, now `"is not registered; valid: ..."` — kind-agnostic, no future Phase-N drift.
- Dispatcher contract test `test_registered_kinds_has_exactly_six_cheap_actions` renamed to `test_registered_kinds_has_exactly_seven_kinds` (intentional rename per Plan 04-01 Task 2 `<note>`; Plans 04-02/04-03 will rename again).
- 5 new modem_reset unit tests covering: argv shape, proxy_died classification, timeout classification, deferred verify, dispatcher registration.
- Replaced obsolete `test_destructive_actions_not_registered` with `test_modem_reset_registered_phase4` (asserts MODEM_RESET True; USB_RESET / DRIVER_RESET still False).
- `test_dispatch_unknown_kind_returns_failure` probe pivoted from MODEM_RESET (now registered) to USB_RESET (still unregistered).
- 4 CLI tests added/rewritten: `test_reset_modem_reset_cli_smoke` (registered → exit 0 + dispatch stub line), `test_reset_unknown_action_still_rejected` (regression on argparse-level rejection), `test_reset_usb_reset_still_rejected` + `test_reset_driver_reset_still_rejected` (asserting the new "is not registered" wording on still-unregistered kinds).
- Full unit suite stays green: **790 passed, 80 skipped** (M7 budget preserved at 14.41 s on Windows dev host).
- All gates green: mypy --strict (121 source files), ruff check (src/ + tests/), ruff format --check on all 6 plan-touched files, SP-04 lint (no new subprocess calls).

## Task Commits

Each task was committed atomically (TDD RED + GREEN per task):

1. **Task 1 RED — failing modem_reset tests** — `8b19b58` (test)
2. **Task 1 GREEN — implement modem_reset + register** — `4e823bc` (feat)
3. **Task 2 RED — rename + invert dispatcher/CLI tests** — `d881af7` (test)
4. **Task 2 GREEN — rewrite cli/reset destructive-guard wording** — `fca29e6` (feat)

No REFACTOR commits — both GREEN implementations are minimal/idiomatic mirrors of their analogs (soft_reset shape; existing reset.py guard branch).

## Files Created/Modified

- `src/spark_modem/actions/modem_reset.py` (NEW, 63 LOC) — MODEM_RESET execute() + verify(); same QMI verb as soft_reset; deferred-verify shape per A-04.
- `src/spark_modem/actions/dispatcher.py` (MODIFIED, +2 lines) — import row + _REGISTRY row for MODEM_RESET. Module docstring unchanged.
- `src/spark_modem/cli/reset.py` (MODIFIED) — destructive-guard message reworded; module docstring updated to reflect the Phase-4 mixed-registration state.
- `tests/unit/actions/test_modem_reset.py` (NEW, 124 LOC) — 5 tests: argv shape, proxy_died, timeout, deferred verify, registry membership.
- `tests/unit/actions/test_dispatcher.py` (MODIFIED) — count test rename + body update (frozenset adds MODEM_RESET, len 6→7); destructive-guard test inverted to assert MODEM_RESET registered + USB_RESET / DRIVER_RESET unregistered; unknown-kind probe pivoted to USB_RESET.
- `tests/unit/cli/test_reset.py` (MODIFIED) — destructive-rejection tests replaced with `is_not_registered` assertions; new modem_reset_cli_smoke test; new quantum_tunnel regression for the argparse-level rejection branch.
- `.planning/phases/04-destructive-actions-hil/deferred-items.md` (NEW) — logs 10 pre-existing ruff format drifts in unrelated files (policy/decision_table.py, policy/engine.py, policy/gates.py, daemon/cycle_perf, cli/explain, cli/ctl/support_bundle, etc.). Recommendation: housekeeping commit at Plan 04-04 (which naturally touches policy/ engine.py + decision_table.py + gates.py).

## Decisions Made

- **Same QMI verb as soft_reset:** Strict adherence to CONTEXT A-01 — modem_reset is a policy distinction (signal gate, ladder rung 2, outage envelope), not a protocol distinction. The `dms_set_operating_mode("reset")` call is unchanged from soft_reset; the engine-side differentiation lands in Plan 04-04.
- **Generic CLI guard wording:** Replaced phase-specific `"is destructive (Phase 4); Phase 2 supports: ..."` with kind-agnostic `"is not registered; valid: ..."`. The new message will continue to fire correctly through Plans 04-02 / 04-03 / Phase 5+ without further wording edits.
- **Test rename convention encoded in test names:** `_seven_kinds` (this plan) → `_eight_kinds` (04-02) → `_nine_kinds` (04-03). Visible in name; greppable across the codebase; reviewers can audit wave ordering by inspecting which name is in tree at a given commit.
- **Pivoted unknown-kind probe to USB_RESET:** Test `test_dispatch_unknown_kind_returns_failure` previously used MODEM_RESET as its "non-registered" probe — that probe is now stale post-Plan-04-01. Pivoted to USB_RESET (still unregistered until 04-02). Documented the rotation expectation inline.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] `test_dispatch_unknown_kind_returns_failure` probe pivoted MODEM_RESET → USB_RESET**
- **Found during:** Task 2 (verifying dispatcher tests after the registration in Task 1)
- **Issue:** Plan 04-01 only specified renaming the count test and inverting `test_destructive_actions_not_registered`. It did NOT mention `test_dispatch_unknown_kind_returns_failure`, which used MODEM_RESET as its "non-registered" probe. Without pivoting it, the test would either fail (MODEM_RESET now registered, dispatch returns success not failure) or assert against the wrong kind.
- **Fix:** Pivoted probe to `ActionKind.USB_RESET` and updated the assertion to look for `"usb_reset"` in the failure reason. Added a docstring paragraph documenting the rotation expectation across Plans 04-02 / 04-03 / 04-04.
- **Files modified:** `tests/unit/actions/test_dispatcher.py`
- **Verification:** Test passes; the assertion is on a still-unregistered kind so the "action_kind_not_registered:..." failure path is exercised correctly.
- **Committed in:** `d881af7` (Task 2 RED commit)

**2. [Out-of-scope, logged not fixed] 10 pre-existing ruff format drifts in unrelated files**
- **Found during:** Task 2 verification (`ruff format --check src/ tests/`)
- **Issue:** 10 files have format drift: `src/spark_modem/cli/ctl/support_bundle.py`, `src/spark_modem/cli/explain.py`, `src/spark_modem/policy/decision_table.py`, `src/spark_modem/policy/engine.py`, `tests/test_recovery_spec.py`, `tests/unit/cli/test_ctl_history.py`, `tests/unit/daemon/test_cycle_perf.py`, `tests/unit/policy/test_decision_table.py`, `tests/unit/policy/test_engine.py`, `tests/unit/policy/test_gates.py`. None are touched by Plan 04-01.
- **Fix:** NOT auto-fixed per SCOPE BOUNDARY rule (pre-existing, not caused by this plan's changes). Logged to `.planning/phases/04-destructive-actions-hil/deferred-items.md` for future cleanup.
- **Verification:** Confirmed all 6 Plan-04-01-touched files pass `ruff format --check` cleanly.
- **Committed in:** `fca29e6` (Task 2 GREEN commit, alongside the cli/reset.py update)

---

**Total deviations:** 2 (1 auto-fixed bug, 1 out-of-scope deferred)
**Impact on plan:** Both deviations are minor. The probe pivot was a Rule-1 cascading-test-update missed by the planner; the fix is a 2-line edit + docstring. The format-drift discovery is purely informational and intentionally not addressed in this plan.

## Issues Encountered

- **Acceptance criterion miscount:** Plan stated `actions/modem_reset.py` should contain "ActionKind.MODEM_RESET (3 occurrences)" but the analog `soft_reset.py` has 2 (one per branch). Verified parity with soft_reset (2 occurrences each, in success and failure branches of execute()). The intent (mirror soft_reset shape) is met. Not a code defect — a minor planning text artefact.

## TDD Gate Compliance

Both tasks followed RED → GREEN cycle with separate commits per gate:
- Task 1: `8b19b58` (test) → `4e823bc` (feat) ✅
- Task 2: `d881af7` (test) → `fca29e6` (feat) ✅

No REFACTOR commits — implementations are minimal/idiomatic on first pass (verbatim mirror of soft_reset; one-line wording change in cli/reset.py).

## Self-Check: PASSED

All files-claimed-created exist on disk:
- src/spark_modem/actions/modem_reset.py ✓
- tests/unit/actions/test_modem_reset.py ✓
- .planning/phases/04-destructive-actions-hil/deferred-items.md ✓
- .planning/phases/04-destructive-actions-hil/04-01-modem-reset-action-SUMMARY.md ✓

All files-claimed-modified exist on disk:
- src/spark_modem/actions/dispatcher.py ✓
- src/spark_modem/cli/reset.py ✓
- tests/unit/actions/test_dispatcher.py ✓
- tests/unit/cli/test_reset.py ✓

All claimed commit hashes resolve in `git log --oneline --all`:
- 8b19b58 (Task 1 RED) ✓
- 4e823bc (Task 1 GREEN) ✓
- d881af7 (Task 2 RED) ✓
- fca29e6 (Task 2 GREEN) ✓

## Threat Flags

None. The plan's `<threat_model>` (T-04-01-01..05) covers the surfaces this plan touches; no new trust boundaries or auth paths introduced.

## Next Phase Readiness

- **Plan 04-02 (usb_reset)** ready: needs to (a) rename the dispatcher count test `_seven_kinds` → `_eight_kinds` and update the frozenset, (b) flip USB_RESET to True in `test_modem_reset_registered_phase4`, (c) potentially pivot the unknown-kind probe in `test_dispatch_unknown_kind_returns_failure` if 04-02 also registers USB_RESET in the same plan (DRIVER_RESET remains unregistered for the probe).
- **Plan 04-03 (driver_reset)** ready: same kind of cascading test updates as 04-02; once all 3 destructive kinds are registered, the unknown-kind probe will need a synthetic / iteration approach.
- **Plan 04-04 (ladder + signal gate)** ready: this is where modem_reset gains its operational distinction from soft_reset (signal gate via `gate_signal`, ladder rung 2 via `policy/ladder.py`, per-kind backoff via `last_action_monotonic_by_kind`). modem_reset.execute()/verify() shapes do not change in 04-04; the engine routes to it differently.
- **No blockers.** Manual `python -m spark_modem.cli ...` smoke confirmed: `--action=modem_reset --modem=cdc-wdm0 --dry-run` returns exit 0 + stub line; `--action=usb_reset` returns 2 with the new "is not registered" message.

---
*Phase: 04-destructive-actions-hil*
*Completed: 2026-05-10*
