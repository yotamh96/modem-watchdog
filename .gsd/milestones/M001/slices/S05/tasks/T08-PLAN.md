# T08: Plan 08

**Slice:** S05 — **Milestone:** M001

## Description

This is the **operator-facing manual plan** that executes Phase 5 in the real world.
The plan covers the time-bound, hardware-dependent, judgment-bearing steps the on-site
engineer performs over ~3+ weeks: the R-01 day-1 trace pull, the 1-week bench soak,
the S-03 handoff gate, the 2-week field soak, the X-04 fleet-fixture capture sweep,
the R-02 replay-harness one-shot, and the final SIGNOFF.md authoring + commit.

Purpose: Phase 5's exit gate is human-attested. No automated script can declare
"bench Jetson ran clean for 1 week with no daemon crashes" — only the engineer
watching it can. This plan structures their work as a sequenced operator checklist
with explicit success criteria per stage.

Output: Six committed artifacts (LFS PR for v1-30d, X-04 batched fleet-fixture PR,
filled SIGNOFF.md, replay-summary-phase5-exit.json, two audit JSONs). NO code, NO
tests. All steps reference Plan 07's SOAK_RUNBOOK.md as the authoritative procedure;
this plan is the SEQUENCING + ACCEPTANCE OVERLAY.

Schedule: this plan spans ~3-4 weeks calendar time. The executor (Claude) does NOT
run automated commands — every task is a checklist for the human operator.
