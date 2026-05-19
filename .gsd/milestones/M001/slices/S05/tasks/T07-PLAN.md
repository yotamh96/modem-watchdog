# T07: Plan 07

**Slice:** S05 — **Milestone:** M001

## Description

Author the two operator-facing markdown artifacts the on-site engineer uses during
Phase 5 execution and at Phase 5 exit: SOAK_RUNBOOK.md (daily checks + soak-exit
procedure) and SIGNOFF.md (Phase 6 entry checklist). Add a single cross-reference
line to docs/RUNBOOK.md. Per RESEARCH Q8/Q9 + CONTEXT.md S-04/F-04.

Purpose: SIGNOFF.md is the Phase 6 entry gate (S-04: the engineer authors + commits
this file with the replay-harness JSON attached). SOAK_RUNBOOK.md is the operator's
source of truth during the 1+2 week soak windows (S-02). Without these, the engineer
has no canonical procedure for the daily checks, the soak-exit audit, or the F-04
violation disposition workflow.

Output: Two new markdown files in the phase directory; one-line addition to
docs/RUNBOOK.md. No code, no tests. Doc-only plan.
