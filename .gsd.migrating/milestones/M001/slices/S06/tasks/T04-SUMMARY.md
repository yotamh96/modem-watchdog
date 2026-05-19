---
id: T04
parent: S06
milestone: M001
provides:
  - EXIT-CHECKLIST.md operator-fillable template for Phase 05.1 EXIT bar (V-03)
  - 9-row V-03 gate table covering all CONTEXT.md L-162..173 steps
  - Approval footer anchoring phase-exit provenance
requires: []
affects: []
key_files: []
key_decisions: []
patterns_established: []
observability_surfaces: []
drill_down_paths: []
duration: 2min
verification_result: passed
completed_at: 2026-05-12
blocker_discovered: false
---
# T04: 05.1-deb-packaging-hotfix 04

**# Phase 05.1 Plan 04: EXIT-CHECKLIST.md Summary**

## What Happened

# Phase 05.1 Plan 04: EXIT-CHECKLIST.md Summary

**Operator-facing 9-step bench Jetson EXIT checklist (V-03) with header table, gate table, free-text rationale, and approval footer — template only, operator fills + commits at phase exit.**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-05-12T06:35:15Z
- **Completed:** 2026-05-12T06:37:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created complete operator-fillable EXIT-CHECKLIST.md template at `.planning/phases/05.1-deb-packaging-hotfix/EXIT-CHECKLIST.md`
- Implemented all 9 V-03 gate rows matching CONTEXT.md L-162..173 verbatim
- Template mirrors Phase 5 SIGNOFF.md shape (header table, gate table, approval footer, footer reference)

## Gate Row Titles (V-03 steps, for orchestrator coverage check)

1. `.deb` built from merged hotfix branch
2. scp + `dpkg -i` returns 0
3. Operator provisions `/etc/spark-modem-watchdog/hmac-secret`
4. `systemctl start spark-modem-watchdog.service` returns 0
5. `systemctl is-active` reports `active`
6. `journalctl` shows `Started ...` + no ERROR/CRITICAL
7. `/run/spark-modem-watchdog/lock` present + owned by root
8. `/run/spark-modem-watchdog/metrics.sock` scrape
9. Daemon reaches Healthy on all 4 modems within 60s (NFR-13)

## Task Commits

Each task was committed atomically:

1. **Task 1: Author EXIT-CHECKLIST.md template** - `20dc8f3` (docs)

**Plan metadata:** (see final commit below)

## Files Created/Modified

- `.planning/phases/05.1-deb-packaging-hotfix/EXIT-CHECKLIST.md` - Operator-facing V-03 exit checklist template; 9-row gate table; approval footer; no pre-filled operator fields

## Decisions Made

- Template is intentionally blank — per plan spec, committing a partially-filled template before all gates pass would falsely signal phase exit
- Step 3 row Expected column specifies `stat -c '%a %u:%g'` output only (never file contents) to prevent HMAC secret disclosure (mitigates T-05.1-15)
- Free-text rationale section explicitly requests L-04 verdict capture (silent-ignore vs hard-fail vs warning-with-degraded) so future plans have the systemd 245 finding documented

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

The actual operator-fill-in cycle is OUT OF SCOPE for this plan.

Phase 05.1 EXIT bar: the on-site engineer scp's the built `.deb` to the bench Jetson, runs `dpkg -i`, provisions the HMAC secret, starts the service, walks each of the 9 V-03 gate rows, fills the EXIT-CHECKLIST.md, and commits it. The committed filled checklist IS the Phase 05.1 EXIT signal.

This plan ships the empty template only. The operator-fill-in is handled out-of-band at Phase 05.1 exit.

## Threat Surface

No new network endpoints or auth paths introduced. The template explicitly instructs operators not to paste HMAC secret bytes (mitigates T-05.1-15). Footer reference `*Template authored by Plan 05.1-04*` anchors provenance against future tampering (T-05.1-16).

## Next Phase Readiness

- EXIT-CHECKLIST.md template is ready for on-site engineer use
- Plan 05-08 Task 2 (bench soak window) is blocked until operator completes and commits the filled EXIT-CHECKLIST.md
- All Phase 05.1 plans (01-04) now complete; remaining plans 05-06 cover CI and unit-file audit

---
*Phase: 05.1-deb-packaging-hotfix*
*Completed: 2026-05-12*
