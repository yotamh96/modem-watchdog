---
id: T03
parent: S11
milestone: M001
key_files:
  - docs/FLEET_GATES.md
  - tests/unit/test_fleet_gates_doc.py
key_decisions:
  - Gate 3 uses actions_total as proxy for session-disconnect rate (no dedicated counter in v2; actions_total is a conservative superset)
  - Gate 4 uses process_start_time_seconds (prometheus_client builtin) rather than a custom metric — documented as not in metrics_registry.py
  - Test handles Prometheus histogram suffixes (_sum, _count, _bucket) by stripping to base metric name for registry validation
duration: 
verification_result: passed
completed_at: 2026-05-19T09:14:29.671Z
blocker_discovered: false
---

# T03: Created docs/FLEET_GATES.md with 4 PromQL canary gate definitions referencing only metrics from metrics_registry.py

**Created docs/FLEET_GATES.md with 4 PromQL canary gate definitions referencing only metrics from metrics_registry.py**

## What Happened

Created `docs/FLEET_GATES.md` with concrete PromQL queries for the 4 ROADMAP SC#2 canary gates used during fleet rollout:

1. **Exhausted-time ≤ baseline** — `rate(state_duration_seconds_sum{state="exhausted"}[24h])` aggregated by modem. Uses the ADR-0013 §Exception histogram with `{modem, state}` labels.
2. **Destructive-reset rate ≤ baseline + 10%** — `rate(actions_total{kind=~"modem_reset|usb_reset|driver_reset"}[24h])`. Filters to the three destructive action kinds.
3. **Session-disruption rate ≤ baseline + 10%** — `rate(actions_total[24h])` unfiltered. Documents that this is a conservative proxy since v2 has no dedicated session-disconnect counter; every action implies at least one disruption.
4. **Zero daemon crashes in 24h** — `changes(process_start_time_seconds[24h]) == 0`. Uses the built-in prometheus_client gauge; includes supplementary journalctl cross-check.

Each gate includes the PromQL query, pass/fail threshold, and the authoritative metric name with its label set.

Added `tests/unit/test_fleet_gates_doc.py` with 4 tests:
- `test_all_metric_refs_exist_in_registry` — extracts metric names from PromQL blocks and validates they exist in `metric_names()` or are known Prometheus builtins. Handles histogram suffixes (`_sum`, `_count`, etc.).
- `test_four_gates_defined` — verifies exactly 4 gate headings.
- `test_each_gate_has_promql_block` — each gate section contains a PromQL code block.
- `test_each_gate_has_threshold` — each gate section contains a threshold definition.

The previous verification failure (`pytest not recognized`) was due to bare `pytest` not being on PATH on this Windows machine. Tests run successfully via `uv run --extra dev python -m pytest`.

## Verification

Ran `uv run --extra dev python -m pytest tests/unit/test_fleet_gates_doc.py -v` — all 4 tests passed. Tests validate: (1) all metric references in PromQL blocks exist in metrics_registry.py or are Prometheus builtins, (2) exactly 4 gates defined, (3) each gate has a PromQL block, (4) each gate has a threshold.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `uv run --extra dev python -m pytest tests/unit/test_fleet_gates_doc.py -v` | 0 | pass | 380ms |

## Deviations

none

## Known Issues

Bare `pytest` command fails on this Windows dev machine — must use `uv run --extra dev python -m pytest`. This is a dev environment issue, not a code issue.

## Files Created/Modified

- `docs/FLEET_GATES.md`
- `tests/unit/test_fleet_gates_doc.py`
