"""Pure-function policy engine (CLAUDE.md §1).

The policy/ package decides what action runs on which modem this cycle.
It is a pure function: Diag x {ModemState[], Globals, Config, Clock} ->
PlannedAction[]. No subprocess, no I/O, no env reads, no httpx, no asyncio.

Module layout:
- transitions.py   -- state-machine transitions (RECOVERY_SPEC §3, ADR-0008)
- decision_table.py -- (IssueCategory, IssueDetail) -> ActionKind (FR-21)
- gates.py         -- pure gate predicates (RECOVERY_SPEC §6)
- engine.py        -- run_cycle orchestrator (RECOVERY_SPEC §8 ordering)
- context.py       -- PolicyContext dataclass (clock + config + maintenance)
- result.py        -- CycleResult + StateTransition records
"""
