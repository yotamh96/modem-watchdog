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
