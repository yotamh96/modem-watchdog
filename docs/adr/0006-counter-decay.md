# ADR-0006 — Recovery counters decay on healthy cycles

| Field        | Value          |
| ------------ | -------------- |
| Status       | Accepted       |
| Date         | 2026-05-05     |
| Deciders     | Eng team       |

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

## Revisit when

- Field data shows real chronic flap that still gets stuck Exhausted.
  Tune K, or add a secondary "max time in Exhausted" rule.
- We add new actions and the per-action ceilings need different
  decay rates. Today all counters share K; per-action K is a
  forward extension.
