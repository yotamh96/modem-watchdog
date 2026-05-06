# Recovery decision specification — spark-modem-watchdog v2

| Field         | Value                  |
| ------------- | ---------------------- |
| Status        | Draft                  |
| Owner         | TBD (modem platform)   |
| Last updated  | 2026-05-05             |

This is the single source of truth for what the daemon does in
response to a `Diag` snapshot. It is written as a state machine plus
decision tables so it can be implemented, tested, and audited line
by line.

The policy engine is a **pure function**:
`Diag × {ModemState[], Globals, Config, MonotonicClock} → PlannedAction[]`.
It calls no subprocess, opens no file, reads no environment.

---

## 1. Vocabulary

- **Issue**: a `(category, detail)` enum pair attached to a modem (or
  the host). Source: observer.
- **State**: the current per-modem situation, persisted across cycles.
- **Action**: a recovery operation (`soft_reset`, `modem_reset`,
  `set_apn`, ...). Has a defined cost (outage duration), idempotency,
  and side-effects.
- **Gate**: a check that may suppress an action even if the state
  machine wants it. Examples: signal-quality, same-action backoff,
  global driver-reset cooldown.
- **Counter**: a per-modem, per-action integer. Bumped on action
  execution. **Decays** to zero after `decay_after_healthy_cycles`
  consecutive `Healthy` cycles for that modem.

## 2. Action catalogue

| Action          | Cost (line outage) | Idempotent | Affects     | When useful                                     |
| --------------- | ------------------ | ---------- | ----------- | ----------------------------------------------- |
| `set_apn`       | ~5 s (SIM cycle)   | yes        | one modem   | profile #1 APN missing or wrong.                |
| `fix_raw_ip`    | < 1 s              | yes        | one modem   | `raw_ip` flag is `N` on the wwan iface.         |
| `sim_power_on`  | ~3 s               | yes        | one modem   | SIM is in `power-down`.                         |
| `soft_reset`    | ~5 s               | yes        | one modem   | SIM-app stuck, registration searching (rung 1). |
| `modem_reset`   | ~30–60 s           | yes        | one modem   | Registration searching (rung 2); session disconnected; operating-mode wrong. |
| `usb_reset`     | ~10–20 s           | yes        | one modem   | QMI channel hung; registration (rung 3).        |
| `driver_reset`  | ~60 s              | yes        | **all modems** | ≥75 % of modems QMI-hung at once with at least one having actionable signal. |

`driver_reset` is the only multi-modem action. All other actions are
strictly single-line.

## 3. Per-modem state machine

States:

```
   ┌─────────────┐
   │   unknown   │   ← bootstrap / fresh state file
   └──────┬──────┘
          │ first observation
          ▼
   ┌─────────────┐                       ┌──────────────┐
   │   healthy   │ ─── issue observed ──▶│   degraded   │
   └─────▲───────┘                       └──────┬───────┘
         │                                       │
         │  K consecutive healthy cycles         │ action chosen
         │  (counters decay; level drops)        ▼
         │                                ┌──────────────┐
         ├────────────────────────────────│  recovering  │
         │       fixed                    │  level=soft  │
         │                                │       │modem │
         │                                │       │usb   │
         │                                └──┬────┬──────┘
         │                                   │    │
         │                                   │    │ ladder exhausted
         │                                   ▼    ▼
         │                                ┌──────────────┐
         └────── return to good ──────────│  exhausted   │
                                          └──────────────┘

  Orthogonal substates that override action selection:
   ┌──────────────┐   ┌──────────────────┐
   │  rf_blocked  │   │   disconnected   │   ← USB removed (FR-1)
   └──────────────┘   └──────────────────┘
```

### 3.1 State definitions

| State          | Meaning                                                                                              |
| -------------- | ---------------------------------------------------------------------------------------------------- |
| `unknown`      | No observation yet. Treated like `healthy` for action gating (no actions taken).                     |
| `healthy`      | Latest snapshot has zero issues for this modem.                                                      |
| `degraded`     | Issues observed, but we have not yet committed to a recovery (e.g. backoff still active).            |
| `recovering`   | Actively running a recovery ladder. Carries a `level` ∈ {`soft`, `modem`, `usb`} indicating rung.    |
| `rf_blocked`   | Signal below thresholds. Destructive actions are gated; the FSM still runs cheap actions (e.g. `fix_raw_ip`, `set_apn`). |
| `exhausted`    | All ladder rungs spent without a fix. No further actions until counter decay.                        |
| `disconnected` | USB device gone (e.g. modem unplugged). All probes skipped.                                          |

### 3.2 Transitions

Transitions are evaluated **after** the cycle's observation, **before**
action selection. The relevant inputs are:

- `issues`: list of issues for this modem this cycle.
- `signal_sufficient`: tri-state (`true`, `false`, `null`).
- `present`: bool (USB device present).
- `prior_state`: the persisted state from the previous cycle.
- `counters`: per-modem per-action counters.
- `ladder_exhausted`: derived from counters and config ceilings.

Pseudo-code:

```python
def transition(prior: State, snap: ModemSnap, ctx: Context) -> State:
    if not snap.present:
        return Disconnected()

    if not snap.issues and snap.signal_sufficient is not False:
        return Healthy()

    if snap.signal_sufficient is False:
        # rf_blocked overrides recovering for destructive levels;
        # but we still run cheap actions. The state name reflects
        # the dominant fact: radio is the bottleneck.
        return RfBlocked(issues=snap.issues)

    if ctx.ladder_exhausted_for(snap):
        return Exhausted(since=ctx.now)

    if isinstance(prior, Recovering):
        # Stay in recovering with the right level
        return Recovering(level=ctx.next_level(prior, snap, ctx))

    return Degraded(issues=snap.issues)
```

The `Degraded → Recovering` transition happens at action-selection
time when an action is actually chosen.

### 3.3 Counter decay (FR-26, ADR-0006)

Each `ModemState` carries a `_healthy_streak` counter:
- Incremented on every cycle that ends in `Healthy`.
- Reset to 0 on any non-`Healthy` cycle.
- When `_healthy_streak >= decay_after_healthy_cycles` (default 10),
  all action counters reset to 0 and `_healthy_streak` is reset to 0.

This is what prevents v1's permanent-`Exhausted` failure mode.

## 4. Issue → action decision table

The policy engine processes one issue per modem per cycle (the
highest-priority one; see § 5). The choice of action for that issue
follows this table.

| Category         | Detail                              | Default action       | Notes                                                            |
| ---------------- | ----------------------------------- | -------------------- | ---------------------------------------------------------------- |
| `config`         | `apn_empty`                         | `set_apn`            | Auto-detect from SIM; fall back to config `fallback_apn`.        |
| `config`         | `apn_mismatch`                      | `set_apn`            | Same.                                                            |
| `sim`            | `sim_power_down`                    | `sim_power_on`       | Single qmicli call.                                              |
| `sim`            | `sim_app_unreadable`                | `soft_reset`         | Could be transient mid-handover.                                 |
| `sim`            | `sim_app_pin_required`              | `skip:requires_human`| No safe automatic recovery.                                      |
| `sim`            | `sim_app_puk_required`              | `skip:requires_human`| Locked. Alert.                                                   |
| `sim`            | `sim_app_detected`                  | `soft_reset`         | App present but not yet `ready`.                                 |
| `sim`            | `sim_card_absent`                   | `skip:no_card`       | No recovery; alert.                                              |
| `sim`            | `sim_card_error`                    | `skip:hardware`      | No recovery; alert.                                              |
| `sim`            | `sim_card_unreadable`               | `soft_reset`         | Try once.                                                        |
| `datapath`       | `raw_ip_off`                        | `fix_raw_ip`         | Cheap, deterministic.                                            |
| `datapath`       | `session_disconnected`              | escalation: `modem_reset` → `skip:exhausted` | Session won't come back without a kick.                  |
| `registration`   | `not_registered_searching`          | escalation: `soft_reset` → `modem_reset` → `usb_reset` → `skip:exhausted` | Standard ladder. |
| `registration`   | `not_registered_idle`               | escalation: same as above | A modem stuck idle wants the same kicks as searching.  |
| `registration`   | `denied`                            | `skip:carrier_denied`| Carrier rejected the SIM. Alert; needs human.                    |
| `qmi`            | `qmi_channel_hung`                  | `usb_reset` once; if fleet-wide ≥75 %, `driver_reset` | See § 6.                  |
| `qmi`            | `operating_mode_offline`            | `modem_reset`        | DMS set-mode online would also work; reset is more reliable.     |
| `qmi`            | `operating_mode_low_power`          | `modem_reset`        |                                                                  |
| `enumeration`    | `enumeration_missing`               | wait + `usb_reset` (parent hub) on N consecutive cycles | Slow because it might be cabling. |
| `enumeration`    | `enumeration_overcurrent`           | `skip:hardware`      | Alert; nothing software can do.                                  |
| `power`          | `autosuspend_on`                    | `fix_autosuspend`    | Apply runtime + log a TODO if udev rule absent.                  |
| `thermal`        | `thermal_warn`                      | none                 | Informational; recorded in metrics, not actioned.                |
| `thermal`        | `thermal_critical`                  | `skip:hardware`      | Alert.                                                           |
| `zao`            | `zao_unit_inactive`                 | `restart_zao` (gated)| Only if Zao has been down ≥60 s; never on every cycle.           |
| `zao`            | `zao_log_stale`                     | none                 | Alert; daemon falls back to direct probing per FR-12.            |

`skip:` actions log a structured `action_skipped` event but do not
mutate state.

### 4.1 Escalation ladder for `registration` and `session_disconnected`

```
soft_reset (counter < MAX_SOFT)
   ↓ count >= MAX_SOFT
modem_reset (counter < MAX_MODEM)
   ↓ count >= MAX_MODEM
usb_reset (counter < MAX_USB)
   ↓ count >= MAX_USB
exhausted
```

Defaults: `MAX_SOFT=3`, `MAX_MODEM=2`, `MAX_USB=1`. Counters decay
per § 3.3.

## 5. Priority ordering across categories

When a modem reports multiple issues in a single snapshot, only the
top-priority one is actioned this cycle. The rest are deferred to
the next cycle (where they may have been resolved as a side-effect of
the action taken, or they remain and are picked up).

| Priority | Category         |
| -------- | ---------------- |
| 1        | `config`         |
| 2        | `sim`            |
| 3        | `datapath`       |
| 4        | `registration`   |
| 5        | `qmi`            |
| 6        | `power`          |
| 7        | `enumeration`    |
| 8        | `zao`            |
| 9        | `thermal`        |

`enumeration` is low because its only action (waiting + parent hub
reset) is rare and slow. `thermal` is informational — no automatic
action.

## 6. Gates

Gates run **after** action selection and may demote the action to
`skip:`. They run in this order; any gate that rejects the action
records the reason and short-circuits.

### 6.1 Signal-quality gate

For destructive actions (`modem_reset`, `usb_reset`):
- If `signal.sufficient` is `false` → **skip with reason `signal_below_threshold`**.
- If `signal.sufficient` is `null` → proceed (we don't know; the
  absence of a reading is itself diagnostic).
- If `signal.sufficient` is `true` → proceed.

Cheap actions (`set_apn`, `fix_raw_ip`, `sim_power_on`, `soft_reset`)
are **never** gated on signal — they don't damage uptime when run
during bad RF.

### 6.2 Same-action backoff gate

If the same action was executed on the same modem within
`backoff_seconds` (default 300 s, monotonic clock) → **skip with
reason `same_action_backoff`**.

### 6.3 Cross-action ladder backoff (new in v2)

Even across different rungs, no destructive action runs more than
once every `ladder_min_interval` seconds (default 90 s). Prevents v1's
soft → modem → soft → modem ping-pong.

### 6.4 Global driver-reset gate

`driver_reset` runs only when **all** of:
- ≥ `multi_modem_threshold_fraction` (default 0.75) of expected
  modems are reporting `qmi_channel_hung` in the same cycle.
- At least one of the hung modems has `signal.sufficient ∈ {true, null}`
  (i.e. not pure RF interference). If every hung modem is RF-blocked,
  the cause is more likely radio than driver state, and a driver
  reset will not help.
- Time since last `driver_reset` ≥ `global_driver_reset_backoff_seconds`
  (default 3600 s).

After `driver_reset` runs, the cycle exits early. Per-line actions
this cycle are skipped; the next cycle re-evaluates against fresh
observations.

### 6.5 Disconnected gate

If the modem's USB device is absent, **all** actions are skipped.
The state is `disconnected` until the device reappears.

### 6.6 Exhausted gate

If the modem is in `exhausted`, only `set_apn` and `fix_raw_ip` are
allowed (because they're cheap and may break the deadlock). All
ladder-rung actions are skipped until counter decay (§ 3.3) restores
budget.

## 7. PlannedAction record

```python
class PlannedAction(BaseModel):
    schema_version: int = 1
    modem: str                       # cdc-wdmN, or "global" for driver_reset
    kind: ActionKind                 # enum
    cause: Issue | None              # the issue that motivated it; null for driver_reset
    gates_passed: list[str]          # ordered: ["signal", "backoff", "ladder", ...]
    gates_failed: list[GateFail]     # empty when action will execute
    dry_run: bool
```

`gates_failed` is non-empty only when the planned action was demoted
to skip. Both forms are recorded in `events.jsonl`.

## 8. Cycle algorithm (pseudo-code)

```python
def run_cycle(diag: Diag, store: StateStore, cfg: Config, clock: Clock) -> CycleResult:
    plans: list[PlannedAction] = []

    # 1. Per-modem state transitions (no actions yet)
    for modem in diag.modems:
        prior = store.load_modem(modem.device) or initial_state(modem.device)
        new_state = transition(prior, modem, ctx)
        store.save_modem(modem.device, new_state)

    # 2. Global driver-reset evaluation
    if global_driver_reset_eligible(diag, store, cfg, clock):
        plans.append(plan_driver_reset(...))
        return CycleResult(plans=plans)   # short-circuit; per-line skipped

    # 3. Per-modem action selection (one per modem)
    for modem in diag.modems:
        issue = highest_priority_issue(modem)
        if issue is None:
            continue
        action_kind = decide_action(modem.device, issue, store, cfg)
        if action_kind.is_skip():
            plans.append(plan_skip(modem, issue, action_kind))
            continue
        plan = run_gates(modem, issue, action_kind, store, cfg, clock)
        plans.append(plan)

    return CycleResult(plans=plans)
```

`run_gates` returns a `PlannedAction` whose `gates_failed` is non-
empty when the action was demoted.

## 9. Idempotency, atomicity, and ordering

- A planned action is recorded (`action_planned` event) **before**
  execution. If the daemon crashes mid-action, the next cycle's
  observation reflects the partial state.
- Counters are bumped after `action_executed` returns, not before.
  A crash mid-action does not double-count.
- State file writes are atomic (temp + rename). Either the previous
  cycle's state or this cycle's state is on disk; never half-written.

## 10. Worked examples

### 10.1 SIM stuck `app_state_detected` → resolves on first soft reset

| Cycle | Observed                         | Prior state    | Counter (soft) | Action          | Resulting state |
| ----- | -------------------------------- | -------------- | -------------- | --------------- | --------------- |
| t0    | `sim/sim_app_detected`           | healthy        | 0              | `soft_reset`    | recovering(soft)|
| t1    | none                             | recovering(soft)| 1              | (none)          | healthy         |
| t2-11 | none                             | healthy        | 1              | (none)          | healthy         |
| t11   | (10 healthy cycles)              | healthy        | 0 (decayed)    | (none)          | healthy         |

### 10.2 Registration searching, signal goes bad

| Cycle | Observed                                                         | State            | Action               |
| ----- | ---------------------------------------------------------------- | ---------------- | -------------------- |
| t0    | `registration/not_registered_searching`, signal.sufficient=true  | recovering(soft) | `soft_reset`         |
| t1    | same, signal sufficient still true                               | recovering(modem)| `modem_reset`        |
| t2    | same, signal.sufficient=false                                    | rf_blocked       | (no destructive; cheap actions allowed but no cheap issue) |
| t3    | signal.sufficient=true again, still searching                    | recovering(usb)  | `usb_reset`          |
| t4    | registered                                                       | healthy          | (none); counters start to decay |

### 10.3 Three modems QMI-hung simultaneously

| Cycle | Observed                                              | Action                   |
| ----- | ----------------------------------------------------- | ------------------------ |
| t0    | 3/4 modems `qmi/qmi_channel_hung`, all with sufficient signal | `driver_reset` (global); per-line skipped this cycle |
| t1    | 4/4 modems `qmi/responsive=true`                      | (none); states settle to healthy |

### 10.4 RF event causes thrashing in v1; v2 absorbs it

| Cycle | Observed                                                                 | v1 action       | v2 action          |
| ----- | ------------------------------------------------------------------------ | --------------- | ------------------ |
| t0    | `registration/searching`, signal.sufficient=false                        | soft_reset      | (signal-gated for any reset >= soft? cheap actions only) → no action |

(v2 still allows `soft_reset` per § 6.1; only destructive actions are
RF-gated. The v1 behaviour was ping-ponging through soft → modem →
soft after the wall-clock backoff expired; v2's cross-action ladder
backoff in § 6.3 prevents that.)

## 11. Test plan for this spec

Every row of § 4 has at least one fixture in `tests/fixtures/`:
a Diag JSON + an expected `PlannedAction[]`. Plus:

- Each gate (§ 6) has a fixture pair: one where the gate passes, one
  where it rejects.
- Each state transition (§ 3.2) has a fixture pair: one before, one
  after.
- Counter decay (§ 3.3) is tested with a 12-cycle replay fixture.

See [TEST_STRATEGY.md](TEST_STRATEGY.md) for how these are run.
