# ADR-0008 — Per-modem state machine: 5 top-level states + 2 orthogonal flags

| Field        | Value                    |
| ------------ | ------------------------ |
| Status       | Accepted                 |
| Date         | 2026-05-06               |
| Deciders     | Eng team                 |
| Supersedes   | ADR-0005                 |

<!-- Supersedes: ADR-0005 -->

## Context

ADR-0005 defined the per-modem state machine as a 7-state discriminated
union: `Healthy`, `Degraded`, `Recovering(level)`, `RfBlocked`,
`Exhausted`, `Disconnected`, plus an implied unknown/initial state.

Research (`.planning/research/FEATURES.md` §4.1) found two problems
with the 7-state shape:

1. **`disconnected` is a guard, not a state.** "Modem is not on the USB
   bus" is a precondition for the state machine, not a state within it.
   When a modem disappears from USB, the state machine is irrelevant —
   there is nothing to transition. The `present` flag captures this
   orthogonally.

2. **`rf_blocked` is partly orthogonal.** The original design treated
   `RfBlocked` as a top-level state that could replace `Recovering`.
   But cheap actions (set_apn, fix_raw_ip, sim_power_on, soft_reset)
   still run while RF is below the gate; only the destructive actions
   (`modem_reset`, `usb_reset`) honor the signal-quality gate. A worked
   example from RECOVERY_SPEC.md §10.2 shows
   `recovering(modem) → rf_blocked → recovering(usb)`: the modem
   remained in `recovering` throughout; `rf_blocked` was a transient
   flag on the orthogonal axis, not a state transition. Treating it as a
   top-level state forced incorrect policy (skipping cheap actions that
   should still run) and produced ambiguous transition diagrams.

The 7-state shape also conflated two different kinds of orthogonality
into a flat enum, making the `match` branches combinatorially larger
than necessary.

## Decision

Replace the 7-state shape with **5 top-level states + 2 orthogonal
flags**. The new `ModemState` wire type (`.planning/phases/
01-foundations-adrs/01-CONTEXT.md` W-04; `src/spark_modem/wire/state.py`,
Plan 03) carries:

```python
state: Literal['unknown', 'healthy', 'degraded', 'recovering', 'exhausted']
recovering_level: int | None   # None unless state == 'recovering'; levels start at 1
present: bool                  # orthogonal flag #1: modem is on the USB bus
rf_blocked: bool               # orthogonal flag #2: RF below signal-quality gate
```

### State semantics

| State        | Meaning                                                       |
| ------------ | ------------------------------------------------------------- |
| `unknown`    | Initial state; no diagnostic data yet collected.              |
| `healthy`    | Zao reports line active, or QMI probes show no issues.        |
| `degraded`   | Issues detected; escalation ladder not yet engaged.           |
| `recovering` | Escalation ladder active at `recovering_level` (1, 2, 3, …). |
| `exhausted`  | Ladder exhausted; no further automatic action; alert sent.    |

### Flag semantics

- **`present: bool`** — True when the modem's USB device node appears
  in sysfs (`/sys/bus/usb/devices/<usb_path>`). False during a
  hot-unplug window or after a `usb_reset` before re-enumeration.
  When `present=False`, the policy engine skips all probe and action
  logic for that modem.

- **`rf_blocked: bool`** — True when the modem's last measured RF
  signal is below the signal-quality gate (RSRP < -110 dBm, or
  RSRQ < -15 dB, or SNR < 0 dB; thresholds from RECOVERY_SPEC §6.1).
  When `rf_blocked=True`, the policy engine still executes cheap
  actions; it blocks only `modem_reset` and `usb_reset`.

### Policy engine match pattern (CLAUDE.md invariant: `match`, not `if/elif`)

```python
match modem_state.state:
    case 'unknown':
        ...
    case 'healthy':
        ...
    case 'degraded':
        ...
    case 'recovering':
        level = modem_state.recovering_level  # never None here
        ...
    case 'exhausted':
        ...
```

The `present` and `rf_blocked` flags are checked as guards within
each branch, not as outer match axes, to preserve exhaustiveness
checking on the primary `state` dimension.

### Why not 7 states

The 7-state shape from ADR-0005 is superseded for the reasons above.
The `disconnected` concept is now the `present=False` flag; the
`rf_blocked` concept is the `rf_blocked=True` flag. Neither belongs
in the primary state axis. The new shape has 5 top-level states
instead of 7, making the match statement 5 arms instead of 7, and
making the policy logic for each arm simpler (no "am I in RfBlocked
while also conceptually Recovering?" ambiguity).

## Consequences

- **`SCHEMA.md` §3** is reshaped to reflect `state`, `recovering_level`,
  `present`, and `rf_blocked` as flat top-level fields on `ModemState`.
  Downstream consumers (status.json composition, webhook payloads) adapt.

- **`status.json`** composes the 5+2 shape into a human-readable
  `v1`-compatible form for the NOC dashboards. The cycle driver
  (Phase 2) is responsible for this composition.

- **Webhook payloads** carry `prior_state` / `new_state` as 5+2-shaped
  strings (e.g. `"recovering"` with a separate `recovering_level` field).

- **`transition()`** and **`decide_action()`** from ADR-0005 survive in
  spirit. Their signatures shift to accept and return the new
  `ModemState` shape. See `src/spark_modem/wire/state.py` (Plan 03).

- **Cheap actions still run while `rf_blocked=True`**: set_apn,
  fix_raw_ip, sim_power_on, soft_reset. Only `modem_reset` and
  `usb_reset` honor the gate. This is explicit in the policy engine,
  not implicit in the state shape.

- **`state_to_int(ModemState) -> int`** provides a stable
  integer encoding for the `modem_state_value{modem}` Prometheus
  metric (see ADR-0013). The mapping is:
  `unknown=0, healthy=1, degraded=2, recovering=3, exhausted=4`.

- **mypy exhaustiveness**: adding a 6th top-level state will be caught
  by `match` with a `case _: assert_never(state)` arm (Plan 03).

## Risks and mitigations

| Risk | Mitigation |
| ---- | ---------- |
| A 6th state is added without updating all `match` arms | `assert_never` catch-all in every `match`; mypy `--strict` enforces it. |
| `status.json` composes the wrong human-readable shape | Phase 2 has spec-as-tests for status.json composition against every (state, flags) combination. |
| `rf_blocked=True` + `state=recovering` produces ambiguous policy | Explicit precedence rule: `rf_blocked` is informational; policy reads `state` first, then gates on `rf_blocked` only for destructive actions. Documented in RECOVERY_SPEC §6.1. |
| `present=False` flag left stale after USB re-enumeration | `pyudev` add event (Phase 3) sets `present=True` and triggers a fresh probe cycle; the flag is never stale by more than one event cycle. |
| `recovering_level` is `None` when `state != 'recovering'` — misread as "level 0" | `state_to_int` and status.json composition both guard on `state == 'recovering'` before reading `recovering_level`. A `None` level outside `recovering` is a logic error caught by mypy (Plan 03 type annotations). |

## Implementation reference

- `src/spark_modem/wire/state.py` — `ModemState` pydantic model +
  `state_to_int()` function (Plan 03, Wave 4).
- `src/spark_modem/wire/state.py state_to_int` — integer encoding
  consumed by ADR-0013 metric surface.
- `docs/SCHEMA.md` §3 — authoritative human-readable schema (amended
  in Phase 1 to reflect 5+2).
- `docs/RECOVERY_SPEC.md` §3, §6.1, §10.2 — state diagram + signal
  gate + worked example (amended in Phase 1).
- Phase 2 cycle driver — wires `transition()`, `decide_action()`, and
  status.json composition against this shape.

## Revisit when

- Real fleet data shows a state we should split (e.g. `recovering` at
  level 3 deserves its own top-level state for NOC alerting). The
  `recovering_level` field already carries the sub-level; promotion to
  a top-level state is a schema-version bump.
- `rf_blocked` needs to be promoted to a top-level state (e.g. fleet
  data shows that the cheap-actions-still-run rule is wrong in practice
  and `rf_blocked` should suppress all actions). Then it replaces the
  flag with a state.
- A global site-level state is needed above per-modem (e.g. "all 4
  modems RF-blocked"). Today modelled as 4 independent `rf_blocked`
  flags; a site-level state is a separate ADR.
