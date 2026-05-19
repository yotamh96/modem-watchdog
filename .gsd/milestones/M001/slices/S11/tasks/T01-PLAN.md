---
estimated_steps: 5
estimated_files: 2
skills_used: []
---

# T01: ADR-0014 and health-gate PromQL definitions

**Why:** The v1-retired pivot is a locked decision (05-CONTEXT.md, 2026-05-11) but has no formal ADR. ROADMAP SC#2 references 4 fleet-aggregate health gates with no concrete PromQL. Both are prerequisites for the MIGRATION.md rewrite.

**Do:**
1. Write `docs/adr/0014-v1-retired-pivot.md` following the ADR-0001 through ADR-0013 template: Status/Date/Deciders table, Context (v1 was retired across the fleet before v2 deployment began; shadow-alongside framing is invalid), Decision (v2 deploys directly to canonical paths; rollback is v2-previous not v1), Consequences (MIGRATION.md Phases 1-2 dead, rollback story simplified, no v1 .deb needed).
2. Write `docs/FLEET_GATES.md` with 4 health-gate PromQL definitions using only metrics from `metrics_registry.py`: (a) Gate 1: exhausted-time — `modem_state_value == 4` threshold via `state_duration_seconds`; (b) Gate 2: destructive-reset rate — `rate(actions_total{kind=~"modem_reset|usb_reset|driver_reset"}[24h])`; (c) Gate 3: session-disconnect proxy — `rate(actions_total[24h])` with documented approximation rationale; (d) Gate 4: zero daemon crashes — `changes(process_start_time_seconds[24h]) == 0`. Document the integer-encoding from ADR-0013 and the session-disconnect proxy decision.

**Done-when:** ADR-0014 exists with correct template format. FLEET_GATES.md references only metric names from the `_METRIC_NAMES` tuple in metrics_registry.py (plus `process_start_time_seconds` from prometheus_client default).

## Inputs

- `docs/adr/0001-language-python.md`
- `docs/adr/0013-metric-surface.md`
- `src/spark_modem/status_reporter/metrics_registry.py`

## Expected Output

- `docs/adr/0014-v1-retired-pivot.md`
- `docs/FLEET_GATES.md`

## Verification

Test-Path docs/adr/0014-v1-retired-pivot.md; Select-String -Pattern '99-shadow|compare_v1_v2|watchdog-v2' docs/adr/0014-v1-retired-pivot.md -Quiet; Select-String -Pattern 'modem_state_value|actions_total|state_duration_seconds|process_start_time_seconds' docs/FLEET_GATES.md | Measure-Object -Line
