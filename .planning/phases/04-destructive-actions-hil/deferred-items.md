# Phase 04 — Deferred Items

Items discovered during Phase 04 plan execution that are out of scope
for the discovering plan but should be addressed.

## Pre-existing ruff format drift (discovered during Plan 04-01)

The following files have `ruff format --check` violations that pre-date
Plan 04-01 (they are NOT touched by this plan, so per the
SCOPE BOUNDARY rule they are not auto-fixed):

- src/spark_modem/cli/ctl/support_bundle.py
- src/spark_modem/cli/explain.py
- src/spark_modem/policy/decision_table.py
- src/spark_modem/policy/engine.py
- tests/test_recovery_spec.py
- tests/unit/cli/test_ctl_history.py
- tests/unit/daemon/test_cycle_perf.py
- tests/unit/policy/test_decision_table.py
- tests/unit/policy/test_engine.py
- tests/unit/policy/test_gates.py

Recommendation: a one-shot `ruff format` housekeeping commit at the next
plan that naturally touches these files (e.g. Plan 04-04 wires the
ladder into engine.py + decision_table.py + gates.py, which would clean
up most of the policy/ drift).

## Pre-existing test_recovery_spec failure (discovered during Plan 04-07)

`tests/test_recovery_spec.py::test_recovery_spec_row[qmi-qmi_channel_hung]`
fails with:

```
AssertionError: (qmi, qmi_channel_hung): expected usb_reset, got driver_reset
```

Root cause: the recovery-spec test constructs a single-modem scenario
(``expected_modem_count=1``) with one modem QMI-hung. After Plan 04-03
wired the real ``_global_driver_reset_eligible`` predicate (75%
denominator + actionable signal), 1/1 hung == 100% which exceeds the
75% gate, so the engine fires ``driver_reset`` instead of the per-modem
``usb_reset`` the spec test expected.

This is OUT OF SCOPE for Plan 04-07 (which only adds test files; it
does NOT modify the engine, decision table, or recovery spec). Per the
SCOPE BOUNDARY rule, the failure pre-dates this plan and was not
auto-fixed.

Recommendation: A follow-up plan should either:
  (a) update the recovery-spec test fixture to set
      ``expected_modem_count=4`` so single-modem hangs don't trip the
      75% gate (test bugfix); or
  (b) update the recovery-spec contract docstring to acknowledge that
      ``qmi_channel_hung`` routes to ``driver_reset`` when the entire
      observed fleet is hung, with ``usb_reset`` reserved for the
      partial-fleet case (spec clarification).

Option (a) is the lighter touch and matches the bench-Jetson reality
(``expected_modem_count=4`` always). Option (b) requires
RECOVERY_SPEC.md edits and an ADR.

Verified pre-existing by ``git stash`` + re-running the same test
without Plan 04-07 changes -- same failure surfaces, confirming this is
not Plan 04-07's regression.
