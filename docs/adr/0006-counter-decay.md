# ADR-0006 — Recovery counters decay on healthy cycles

| Field        | Value          |
| ------------ | -------------- |
| Status       | Accepted       |
| Date         | 2026-05-05     |
| Deciders     | Eng team       |
| Amended      | 2026-05-06     |

## Context

In v1, per-modem recovery counters increment monotonically and are
never decremented. The intent of escalation ceilings (`MAX_SOFT=3`,
`MAX_MODEM=2`, `MAX_USB=1`) is to bound recovery during a single
incident. But because counters never reset on healthy operation, a
Jetson that runs for a month accumulates hundreds of cumulative
actions per modem. After one bad-RF event in week 3, a modem can
hit the ceilings and become permanently `skip:exhausted` — the only
escape hatch is `recovery.sh --reset-state`, which a NOC operator
would have to know to run.

This is the single biggest correctness issue carried forward from v1.

## Decision

**Per-modem action counters decay to zero after K consecutive
`Healthy` cycles.** Default K is 10 cycles; configurable via
`ladders.decay_after_healthy_cycles`.

Mechanism:

- Each `ModemState` carries a `_healthy_streak` integer counter.
- On every cycle that ends in `Healthy` for that modem, the streak
  increments by 1.
- On any cycle that ends in non-`Healthy`, the streak resets to 0.
- When the streak reaches K, all action counters reset to 0 and the
  streak resets to 0. This is logged as a `counters_decayed` event
  for observability.

## Consequences

- A modem that's flapping (degraded → healthy → degraded) accumulates
  counters across the events because its streak never reaches K.
  This is correct: a flapping modem may need the full ladder.
- A modem with a single isolated incident, followed by 10 stable
  cycles (5 minutes at 30 s cycle interval), starts fresh.
- The default K=10 corresponds to 5 minutes at the 30 s polling
  cadence, or as little as 10 events under heavy event-driven
  cycling. We accept that the wall-clock effective duration varies
  with event traffic; "10 stable observations" is what we mean
  semantically.
- Counter decay is logged so that a debugger can replay an
  Exhausted-then-recovered transition and see how the budget came
  back.
- Counter decay is **not** the same as backoff. Backoff is
  same-action time-based; decay is per-action streak-based. Both
  exist.

## Why not time-based decay?

- Time-based decay (e.g. "halve counters every hour") couples the
  decay to wall clock, which is fragile (NTP, suspend-resume).
- Streak-based decay says "we've observed N healthy cycles," which
  is exactly what we mean: the machine tells us it's been working.

## Risks and mitigations

| Risk                                                  | Mitigation                                                           |
| ----------------------------------------------------- | -------------------------------------------------------------------- |
| Decay too aggressive: a modem with chronic intermittent issues never escalates because it heals briefly between failures | The streak is exactly K consecutive cycles; a single non-healthy cycle resets to 0. Chronic flap → counters accumulate → escalation engages. |
| Decay too conservative: a modem with a transient issue gets stuck Exhausted longer than necessary | K=10 (5 min at default polling) is short enough that a transient SIM hiccup doesn't pin a modem out. |
| Off-by-one: streak reaches K but counters don't decay | Tested explicitly in `tests/replay/test_counter_decay.py` with a 12-cycle fixture. |

## Amendment 2026-05-06

**Pinned cycle ordering + streak persistence (closes PITFALLS §9.1, §9.2).**

Research surfaced two failure modes the original ADR did not address:

1. **Daemon-restart silently resets `_healthy_streak`** (PITFALLS §9.2).
   The original "Decision" describes the mechanism but does not say the
   streak is durable. v1's regression risk: a streak that's lost on
   every daemon restart re-introduces the v1 permanent-Exhausted
   failure mode this ADR was written to fix.

2. **`_healthy_streak` persistence vs decay race** (PITFALLS §9.1):
   a crash mid-cycle between "streak += 1" and "counters reset" leaves
   the on-disk file inconsistent.

**Refined rule (atomic single-write per cycle):**

Per cycle, the per-modem state-write pipeline is:

```
streak update → decay check → counter reset (if streak == K) →
state-write (one atomic temp+rename+dir-fsync)
```

All four happen as ONE atomic write per cycle. `_healthy_streak` is
persisted in the per-modem state file every cycle and reloaded on
daemon start; mid-streak restart does NOT reset progress.

Replay test contract (Phase 2): the policy-engine replay harness
includes a daemon-restart-mid-streak case that proves K consecutive
Healthy cycles correctly resume after restart and decay counters to
zero on cycle K post-restart, not on cycle K post-most-recent-boot.

Implementation reference: `src/spark_modem/wire/state.py`
(`_healthy_streak` field with alias on ModemState, Plan 03);
`src/spark_modem/state_store/store.py` (atomic save, Plan 04);
Phase 2 cycle driver wires the actual streak increment/decay logic.

See ADR-0009 (state files keyed by usb_path) and ADR-0012 (atomic
write + locking) for the persistence and concurrency context.

## Revisit when

- Field data shows real chronic flap that still gets stuck Exhausted.
  Tune K, or add a secondary "max time in Exhausted" rule.
- We add new actions and the per-action ceilings need different
  decay rates. Today all counters share K; per-action K is a
  forward extension.
- The atomic-write semantics in ADR-0012 change (e.g. a write-ahead
  log replaces temp+rename); the cycle ordering guarantee here must
  be re-verified against the new write model.
