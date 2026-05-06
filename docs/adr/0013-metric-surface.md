# ADR-0013 — Integer-encoded modem_state_value{modem} metric

| Field        | Value          |
| ------------ | -------------- |
| Status       | Accepted       |
| Date         | 2026-05-06     |
| Deciders     | Eng team       |

## Context

PRD NFR-21 originally specified:

```
modem_state{modem, state}  # one-hot gauge: 1 = current state, 0 = others
```

For example, a modem in `recovering` state would have:

```
modem_state{modem="2-3.1.1", state="unknown"}     0
modem_state{modem="2-3.1.1", state="healthy"}     0
modem_state{modem="2-3.1.1", state="degraded"}    0
modem_state{modem="2-3.1.1", state="recovering"}  1
modem_state{modem="2-3.1.1", state="exhausted"}   0
```

**The problem** (`.planning/research/PITFALLS.md` §13.1 / §9.4):

The `state` label is a **cardinality dimension** in Prometheus. With 4
modems × 5 states, the one-hot scheme produces 20 time series per
box. At fleet scale (N boxes), this is 20N series in the global
federation. Each series has its own WAL segment; Prometheus WAL
compaction scales O(cardinality). At moderate fleet sizes this is
manageable; at large scale it becomes a real operational cost.

More importantly: if state names ever change (e.g. `recovering` is
renamed, or a new state is added), the old series persist in
Prometheus's WAL until the WAL compaction horizon (typically 2 hours).
During that window, dashboards show stale data from the old label
names alongside fresh data from the new names — a source of NOC
confusion.

The `state` label is also a label on a *gauge*, not a histogram. The
cardinality cost of a gauge label is `|label_values| × |modem_values|`
= 5 × 4 = 20 series per box, bounded. But with a one-hot gauge, every
state transition creates a step function on 2 series (the old state
goes from 1→0; the new state goes from 0→1), producing twice the WAL
write traffic per transition. Under sustained state flapping, this is
a non-trivial write amplification.

## Decision

Replace the one-hot `state` label with a **single integer-encoded
gauge per modem**:

```
modem_state_value{modem="2-3.1.1"}  3  # 3 = recovering
```

### Stable canonical integer mapping

| Integer | State        |
| ------- | ------------ |
| 0       | `unknown`    |
| 1       | `healthy`    |
| 2       | `degraded`   |
| 3       | `recovering` |
| 4       | `exhausted`  |

**This mapping is stable across releases.** Never reuse a number for
a different state. New states extend the table at the end (5, 6, …).

Implementation: `spark_modem.wire.state.state_to_int(ModemState) -> int`
(Plan 03). The function has an inline comment referencing this ADR
as the canonical mapping source.

### Orthogonal dimensions as separate gauges

The `recovering_level` orthogonal axis (1, 2, 3, …) is exposed as a
separate gauge:

```
modem_recovering_level{modem="2-3.1.1"}  2  # level 2; 0 when state != recovering
```

**`0` means "not in recovering"**; levels start at 1. Dashboard queries
should filter `modem_state_value == 3` before reading
`modem_recovering_level` to avoid misreading 0 as "level 0."

The two orthogonal flags (ADR-0008) are separate gauges:

```
modem_present{modem="2-3.1.1"}     1  # 1 = on USB bus; 0 = absent/unplugged
modem_rf_blocked{modem="2-3.1.1"}  0  # 1 = RF below signal gate; 0 = ok
```

### Cardinality result

With the integer encoding:

```
4 modems × 1 (modem_state_value) = 4 series
4 modems × 1 (modem_recovering_level) = 4 series
4 modems × 1 (modem_present) = 4 series
4 modems × 1 (modem_rf_blocked) = 4 series
Total: 16 series per box
```

vs the one-hot scheme: `4 modems × 5 states = 20 series per box`.
The integer encoding has fewer series AND avoids the step-function
write amplification on transitions.

### Exception: state_duration_seconds histogram

The `state_duration_seconds{modem, state}` histogram (M-5) still uses
a `state` label — it measures time-in-state and is a histogram (not a
gauge). Histograms have bounded buckets per label combination:
`4 modems × 5 states × N buckets`. This is acceptable cardinality for
a histogram (histograms are inherently multi-series). The `state` label
on a histogram is a measurement dimension, not a current-state
indicator.

### Other metrics (for completeness)

Additional metrics shipped in Phase 2/3 (not this ADR's subject but
documented here for the NOC):

```
actions_total{modem, action, result}   # counter; bounded label set
signal_rsrp_dbm{modem}                 # gauge
signal_rsrq_db{modem}                  # gauge
signal_snr_db{modem}                   # gauge
cycle_duration_seconds                 # histogram (no modem label; whole-cycle)
webhook_delivery_total{result}         # counter; result in {ok, retry, drop}
zao_log_unparsed_lines_total           # counter (ADR-0003 amendment)
```

## Consequences

- **Cardinality is bounded**: 16 series per box regardless of state
  churn. A flapping modem (rapid state transitions) produces no new
  series; only the value of the existing gauge changes.

- **NOC dashboards** translate the integer back to a human-readable
  label via Prometheus's `label_replace` or Grafana's value-mapping
  feature. The mapping table in this ADR is the canonical source for
  those dashboard configs.

- **Adding a new state** requires: (1) adding it to the canonical
  mapping table in this ADR, (2) adding it to `state_to_int` in
  `state.py`, (3) updating dashboard value mappings. Steps 1 and 2
  are coupled by code review; mypy catches any `state_to_int` miss.

- **Dashboard queries for current state**: use
  `modem_state_value{modem="2-3.1.1"}` and apply the mapping table
  in the dashboard layer. This is a one-time dashboard configuration
  cost.

- **Prometheus alerting**: `modem_state_value == 4` fires "modem
  exhausted"; `modem_state_value >= 2` fires "modem degraded or
  worse." Integer comparisons are simpler and more robust than
  one-hot equality checks.

- The cycle driver (Phase 2) wires:
  ```python
  modem_state_gauge.labels(modem=usb_path).set(
      state_to_int(modem_state)
  )
  ```
  after every transition.

## Risks and mitigations

| Risk | Mitigation |
| ---- | ---------- |
| Adding a new state without bumping the ADR mapping table | This ADR is the canonical source; `state_to_int` has an inline comment citing it. Code review enforces the pair update. mypy `--strict` catches a missing `match` arm in `state_to_int`. |
| NOC dashboard breaks when the integer mapping changes | The mapping is **stable**: never reuse numbers. New states extend at the end. Dashboard configs are updated in the same PR as `state_to_int`. |
| `modem_recovering_level` reads 0 when state != recovering — misread as "level 0" | Dashboard queries filter `modem_state_value == 3` before reading `modem_recovering_level`. The metric docstring and this ADR both document that 0 = "not in recovering." |
| Old one-hot series persist in Prometheus WAL after migration | The one-hot metric is never implemented in v2.0. No migration from one-hot to integer is needed; v2.0 starts fresh with the integer encoding. |
| Integer encoding makes alerting rules less readable | Integer comparisons (`== 4`) are actually more concise and less error-prone than one-hot checks (`{state="exhausted"} == 1`). Grafana value-mapping provides the human-readable label at the display layer. |

## Implementation reference

- `src/spark_modem/wire/state.py state_to_int` — canonical integer
  mapping function (Plan 03, Wave 4). The mapping table in this
  function is the single source of truth for the integer encoding.
- Phase 2 cycle driver — wires `modem_state_gauge.labels(modem=...).set(
  state_to_int(modem_state))` after every transition.
- Phase 2 `MetricRegistry` — registers all four per-modem gauges
  (`modem_state_value`, `modem_recovering_level`, `modem_present`,
  `modem_rf_blocked`) and exposes them over the Prometheus UDS
  (ADR-0002; NFR-21 amended).

## Revisit when

- Real fleet data shows that cardinality is not a problem even with
  one-hot (e.g. boxes don't actually flap state often in production).
  Then we can revisit whether the NOC dashboard complexity of
  integer-to-label mapping is worth it. If cardinality is fine, we
  can stay with the integer encoding (simpler alerts) OR revert to
  one-hot (simpler dashboards) — a conscious tradeoff.
- A new state is added that changes the meaning of an existing
  integer (should never happen — the rule is "stable mapping"). If
  someone proposes this, the rule requires a major version bump and
  fleet-wide Prometheus WAL reset. The cost of this is the enforcement
  of the "never reuse" rule.
- The fleet grows to a scale where even 16 series per box × N boxes
  becomes a Prometheus cardinality concern. At that scale, the metric
  architecture deserves a dedicated re-evaluation regardless of encoding.
