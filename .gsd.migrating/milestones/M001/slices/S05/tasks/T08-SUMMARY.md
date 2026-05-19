---
id: T08
parent: S05
milestone: M001
provides:
  - Stub completion marker so GSD tracking can advance past Plan 05-08.
  - Explicit pointer to .planning/phases/05-bench-field-shadow/05-HUMAN-UAT.md as the live tracking surface for the 10 operator-bound items.
requires: []
affects: []
key_files: []
key_decisions: []
patterns_established: []
observability_surfaces: []
drill_down_paths: []
duration: 0min
verification_result: passed
completed_at: 2026-05-11
blocker_discovered: false
---
# T08: Plan 08

**# Phase 05 Plan 08: Operator Soak — Deferred to Human Operator**

## What Happened

# Phase 05 Plan 08: Operator Soak — Deferred to Human Operator

**Plan 05-08 is operator-bound by design; this SUMMARY exists only to unblock GSD tracking. Real Phase 5 exit is gated on the on-site engineer's SIGNOFF.md merge, not on this file.**

## Why a stub

Plan 05-08's own objective states:

> "Schedule: this plan spans ~3-4 weeks calendar time. The executor (Claude) does NOT run automated commands — every task is a checklist for the human operator."

All six tasks are `<task type="checkpoint:human-action" gate="blocking">`:

1. R-01 day-1 v1-trace pull + LFS PR merge
2. Bench Jetson 1-week clean soak + S-03 handoff
3. Field box 2-week clean soak (F-01 natural-faults-only)
4. X-04 fleet-fixture capture sweep + batched PR merge
5. R-02 replay-harness one-shot at Phase 5 exit
6. SIGNOFF.md fill + commit + Phase 6 entry PR merge

There is nothing for an executor agent to do that would not fabricate evidence (fake `phase5-evidence/bench/day-N/` files, fake merge SHAs, fake `replay-summary-phase5-exit.json` values, etc.).

## Where the live state lives

| Artifact                                                            | Role                                                                        |
|---------------------------------------------------------------------|-----------------------------------------------------------------------------|
| `.planning/phases/05-bench-field-shadow/05-HUMAN-UAT.md`            | 10 pending operator items; surfaces in `/gsd-progress` + `/gsd-audit-uat`. |
| `.planning/phases/05-bench-field-shadow/SIGNOFF.md`                 | Template awaiting engineer fill-in; merge is the real Phase 5 exit gate.   |
| `.planning/phases/05-bench-field-shadow/SOAK_RUNBOOK.md`            | Authoritative procedure for the operator (delivered by Plan 05-07).        |
| `.planning/phases/05-bench-field-shadow/05-VERIFICATION.md`         | `status: human_needed`; 30/40 must-haves verified (10 operator-bound).     |

When the operator returns with evidence, the correct entry point is `/gsd-verify-work 5` against `05-HUMAN-UAT.md`, then a follow-up commit of SIGNOFF.md + audit JSONs + replay-summary.

## Performance

- **Duration:** 0 min (no Claude execution)
- **Started:** 2026-05-11
- **Completed:** 2026-05-11 (deferral marker only)
- **Tasks:** 0 of 6 Claude-actionable (all 6 are human-action checkpoints)
- **Files modified:** 1 (this stub)

## Accomplishments

- Tracking advanced past Plan 05-08 without fabricating soak evidence.
- HUMAN-UAT.md explicitly named as the live tracking surface.
- Phase 5 exit gate (SIGNOFF.md merge) preserved intact for the on-site engineer.

## Task Commits

None. No executor work was performed. This SUMMARY is the only artifact this plan produces; the rest are produced by the operator outside the GSD execution loop.

## Files Created/Modified

- `.planning/phases/05-bench-field-shadow/05-08-SUMMARY.md` — this deferral marker.

## What Phase 6 should assume

- Plan 05-08's 6 operator tasks may still be running calendar-time when Phase 6 planning begins.
- The X-04 batched PR merge (Task 4) and the SIGNOFF.md merge (Task 6) MUST land before any Phase 6 cutover .deb ships, regardless of what STATE.md / ROADMAP.md say about Phase 5 completion. The .deb build needs `tests/fixtures/fleet/<box-id>/triple.json` for every Phase-6 box.
- The CR-01 redact.py extension (HUMAN-UAT item 10) blocks the X-04 sweep. Schedule it before Task 4 in real-world execution order.

## Self-Check: PASSED

Stub written transparently. No fabricated evidence. No requirements claimed completed. Live tracking pointer (HUMAN-UAT.md) named explicitly.
