# T05: 02-core-daemon-laptop-testable 05

**Slice:** S02 — **Milestone:** M001

## Description

Plan 02-05 lands the pure-function policy engine — the core of the daemon
and the only file that decides "what action runs on which modem this cycle."

Per CLAUDE.md §1: the entire `policy/` package is a pure function. No
subprocess, no httpx, no os, no env reads. mypy + the lint gate
(`scripts/lint_no_subprocess.sh`) enforce this; the test suite proves it.

The engine is structured as four files mirroring RECOVERY_SPEC §3..§7:
- `transitions.py` — `Diag × ModemState → new ModemState` (FR-12 5+2 shape)
- `decision_table.py` — `(IssueCategory, IssueDetail) → ActionKind` (FR-21 priority)
- `gates.py` — pure gates: signal / same-action backoff / ladder backoff /
  exhausted / maintenance / disconnected (FR-25, FR-25.1, FR-23 stub, C-01)
- `engine.py` — `run_cycle(Diag, state[], globals, config, clock) → CycleResult`

Counter decay ordering (RECOVERY_SPEC §8 / ADR-0006) is encoded in
`engine.run_cycle`: transition → streak update → decay check → counter reset
→ planned action selection → gates → CycleResult. The atomic state-write
itself is performed by the cycle driver in plan 02-10 — but the planned
order is fixed here (the engine returns the new ModemState[] alongside the
PlannedAction[]; the driver writes both in one atomic per-modem write).

Output: `policy/` package + `tests/unit/policy/*` exhaustive coverage +
`tests/test_recovery_spec.py` spec-as-tests gate + `tools/check_spec.py`
coverage-checker tool.

## Must-Haves

- [ ] "policy/ package contains zero subprocess / httpx / asyncio / os imports — purity invariant (CLAUDE.md §1)."
- [ ] "engine.run_cycle is a pure function: (Diag, ModemState[], Globals, Config, Clock) -> CycleResult; no I/O, no env reads."
- [ ] "decision_table maps every RECOVERY_SPEC §4 (IssueCategory, IssueDetail) row to an ActionKind or skip:reason."
- [ ] "transitions.transition uses `match` on ModemState (not if/elif) — CLAUDE.md anti-pattern enforced."
- [ ] "Counter decay ordering matches RECOVERY_SPEC §8: transition → streak update → decay-check → counter reset → state-write planned. The state-write itself happens in plan 02-10 (cycle driver)."
- [ ] "Same-action backoff gate (FR-25, 300s) and cross-action ladder backoff (FR-25.1, 90s) use clock.monotonic()."
- [ ] "Signal-quality gate stub returns 'pass' for all destructive actions in Phase 2 (Phase 4 wires the rsrp/rsrq/snr thresholds end-to-end); the plumbing is here."
- [ ] "Maintenance-window gate predicate (C-01) refuses destructive actions when active; cheap actions still run."
- [ ] "tests/test_recovery_spec.py covers every §4 row as a parametrized fixture; tools/check_spec.py asserts coverage."
- [ ] "_healthy_streak persists across simulated daemon restart (FR-26.1) — fixture in tests/unit/policy/test_streak.py."

## Files

- `src/spark_modem/policy/__init__.py`
- `src/spark_modem/policy/context.py`
- `src/spark_modem/policy/transitions.py`
- `src/spark_modem/policy/decision_table.py`
- `src/spark_modem/policy/gates.py`
- `src/spark_modem/policy/engine.py`
- `src/spark_modem/policy/result.py`
- `tests/unit/policy/__init__.py`
- `tests/unit/policy/test_transitions.py`
- `tests/unit/policy/test_decision_table.py`
- `tests/unit/policy/test_gates.py`
- `tests/unit/policy/test_engine.py`
- `tests/unit/policy/test_streak.py`
- `tests/test_recovery_spec.py`
- `tools/check_spec.py`
