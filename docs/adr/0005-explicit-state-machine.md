# ADR-0005 — Explicit per-modem state machine

| Field        | Value          |
| ------------ | -------------- |
| Status       | Accepted       |
| Date         | 2026-05-05     |
| Deciders     | Eng team       |

## Context

In v1 the per-modem behaviour is the implicit composition of:

- `decide_action()`'s switch over (category, detail, counters)
- per-action counters loaded from disk (`count_soft_reset`, …)
- `MAX_*` constants
- the signal-quality gate
- the `recently_did` backoff
- "one action per modem per cycle" loop guard
- the global driver-reset gate

There is no single function or document that says "the modem state
machine is X." It's implied across 250 lines of bash. A bug in any
layer is hard to spot — and there are bugs (counters never decay;
backoff blocks only the same action; no formal `Exhausted` state).

## Decision

**Make the per-modem state machine explicit.** One source file
(`src/spark_modem_watchdog/state/machine.py`) defines:

- The `ModemState` discriminated union (`Healthy`, `Degraded`,
  `Recovering(level)`, `RfBlocked`, `Exhausted`, `Disconnected`).
- The `transition(prior, snap, ctx) -> new_state` pure function.
- The `decide_action(state, snap, ctx) -> ActionKind | Skip` pure
  function.
- The counter and decay logic.

Each piece is unit-tested in isolation; the whole is tested with
fixtures that mirror [RECOVERY_SPEC.md](../RECOVERY_SPEC.md) row
by row.

## Consequences

- **Persisted state is the state object, not raw counters.** The
  state file (per [SCHEMA.md § 3](../SCHEMA.md#3-modemstate-state-store))
  contains the discriminated state plus counters; loading and saving
  is round-trip via pydantic.
- **One state diagram lives in [RECOVERY_SPEC.md § 3](../RECOVERY_SPEC.md#3-per-modem-state-machine);** code matches it.
- **Adding a new state** is a deliberate schema change; mypy and
  tests catch missing transitions.
- **Counter decay** (ADR-0006) is a property of the machine, not a
  cross-cutting hack.
- **The signal-quality gate** is part of the gates layer (still a
  separate concern from the state machine itself), so the machine
  doesn't have a `signal_sufficient` parameter; it has
  `RfBlocked` as a state input from observation.

## Risks and mitigations

| Risk                                                  | Mitigation                                              |
| ----------------------------------------------------- | ------------------------------------------------------- |
| A new state added without updating all transitions    | Exhaustive `match` statements (Python 3.10+) on `ModemState`; mypy errors on a missing arm. |
| State drift between the machine and the spec doc      | `tools/check_spec.py` parses the doc's state-transition table and asserts the machine implements every row. |
| A bug in counter decay leaves modems Exhausted forever| Replay tests over 30 days of v1 production logs in `tests/replay/` with v2's machine; assert no modem ends in Exhausted at the end. |

## Revisit when

- We need a multi-modem state (e.g. "site is RF-blocked"). Today
  that's modelled as N independent RfBlocked states; if it grows
  enough, we may add a global state above the per-modem machines.
