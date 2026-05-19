# T05: Plan 05

**Slice:** S05 — **Milestone:** M001

## Description

Build the two post-hoc soak-audit tools the on-site engineer runs at bench-week-end
and field-2-weeks-end to validate the S-01 #2 and S-01 #3 exit gates:

1. `tools/audit_soak_zao.py` (S-01 #2): "no action planned on Zao-active line."
   Joins `events.jsonl` `ActionPlanned` events with the `ZaoSnapshot` history (from
   the Zao log); for each ActionPlanned, checks whether the modem's line was active
   at the cycle's wallclock. Per RESEARCH Q5 §352-396.

2. `tools/audit_soak_exhausted.py` (S-01 #3): "no unexplained Exhausted transitions."
   Replays policy decay logic against events.jsonl; for each
   StateTransition(new_state='exhausted'), checks whether the modem had ≥K consecutive
   healthy cycles in the lookback window AND counters were not reset (= bug; ADR-0006
   amendment regression). Per RESEARCH Q6 §399-451.

Purpose: These tools quantify S-01 #2 and #3 violations at SIGNOFF time. Plan 07
(SIGNOFF.md template) and Plan 07 (SOAK_RUNBOOK.md) wire them into the operator
soak-exit procedure. Without these tools, the engineer cannot prove the two
non-trivial S-01 gates were green.

Output: Two new Python scripts under `tools/` (SP-04-exempt). One new test directory
`tests/unit/tools/` with `__init__.py` + two test files. ~150 LOC per script + ~150 LOC
per test.
