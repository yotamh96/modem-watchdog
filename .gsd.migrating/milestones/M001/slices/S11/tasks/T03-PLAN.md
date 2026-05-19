# T03: Health-gate PromQL definitions

**Slice:** S11 — **Milestone:** M001

## Description

Create `docs/FLEET_GATES.md` with concrete PromQL queries for the 4 ROADMAP SC#2 canary gates used during fleet rollout.

Gates:
1. **Exhausted-time ≤ baseline** — query modem_state_value == 4 duration over 24h window
2. **Destructive-reset rate ≤ baseline + 10%** — sum rate of actions_total{kind=~"modem_reset|usb_reset|driver_reset"}
3. **Session-disconnect rate ≤ baseline + 10%** — use actions_total as proxy (each action implies disruption); document the approximation
4. **Zero daemon crashes in 24h** — changes(process_start_time_seconds[24h]) == 0

All metric names must reference only metrics defined in `src/spark_modem/status_reporter/metrics_registry.py`. Include brief explanation of each gate, the PromQL query, and the pass/fail threshold.

## Files

- `docs/FLEET_GATES.md`

## Verify

- All referenced metrics exist in metrics_registry.py
- PromQL syntax is valid
- 4 gates defined with thresholds

## Inputs

- `src/spark_modem/status_reporter/metrics_registry.py` (authoritative metric names)
- `.gsd/milestones/M001/slices/S11/S11-RESEARCH.md` §4 (gate definitions)
- `docs/adr/0013-metric-surface.md` (integer encoding rationale)

## Expected Output

New docs/FLEET_GATES.md (~60 lines) with 4 PromQL gate definitions.
