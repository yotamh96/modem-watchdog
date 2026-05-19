# Fleet Rollout Health Gates

PromQL definitions for the four canary gates used during phased fleet rollout
(ROADMAP SC#2). Each gate must pass on the canary cohort before the next
rollout phase proceeds.

All metric names reference `src/spark_modem/status_reporter/metrics_registry.py`.

---

## Gate 1 — Exhausted-time ≤ baseline

A modem reaching `exhausted` (state value 4, per ADR-0013) means every
recovery level has been tried and failed. Time spent exhausted on the canary
cohort must not exceed the pre-rollout baseline.

```promql
sum by (modem) (
  rate(state_duration_seconds_sum{state="exhausted"}[24h])
)
```

**Threshold:** ≤ baseline value measured on the same box during the 7-day
pre-rollout observation window. Any modem exceeding its baseline fails the
gate.

**Metric:** `state_duration_seconds` — Histogram with `{modem, state}` labels
(ADR-0013 §Exception).

---

## Gate 2 — Destructive-reset rate ≤ baseline + 10 %

Destructive resets (`modem_reset`, `usb_reset`, `driver_reset`) drop the
modem's radio link. An elevated rate signals the new version is triggering
unnecessary heavy recovery.

```promql
sum(rate(actions_total{kind=~"modem_reset|usb_reset|driver_reset"}[24h]))
```

**Threshold:** ≤ 1.1 × baseline destructive-reset rate from the 7-day
pre-rollout window.

**Metric:** `actions_total` — Counter with `{kind, modem, result}` labels.

---

## Gate 3 — Session-disruption rate ≤ baseline + 10 %

The daemon does not export a dedicated session-disconnect counter.
`actions_total` serves as a proxy: every recovery action implies at least one
session disruption, making the total action rate a strict superset of actual
disconnects. This is a conservative approximation — if the proxy passes, real
disconnects are necessarily within budget.

```promql
sum(rate(actions_total[24h]))
```

**Threshold:** ≤ 1.1 × baseline total-action rate from the 7-day pre-rollout
window.

**Metric:** `actions_total` — Counter with `{kind, modem, result}` labels
(same metric as Gate 2, unfiltered).

**Approximation note:** If a future version adds a dedicated
`session_disconnect_total` counter, this gate should switch to it for higher
fidelity.

---

## Gate 4 — Zero daemon crashes in 24 h

A daemon restart resets the `process_start_time_seconds` gauge (a default
metric from `prometheus_client`). The `changes()` function detects resets.

```promql
changes(process_start_time_seconds[24h]) == 0
```

**Threshold:** Exactly 0 restarts. Any restart fails the gate.

**Metric:** `process_start_time_seconds` — built-in gauge from
`prometheus_client`, not registered in `metrics_registry.py`. Always present
when the Prometheus client library is active.

**Supplementary check:** `journalctl -u spark-modem-watchdog --since '24 hours ago' | grep -c 'Main process exited'` provides a systemd-level cross-check
independent of Prometheus scrape availability.
