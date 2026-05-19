---
id: T06
parent: S11
milestone: M001
key_files:
  - docs/templates/cutover-phase3-notice.md
  - docs/templates/cutover-phase4-notice.md
  - docs/templates/cutover-phase5-notice.md
key_decisions:
  - Used {{PLACEHOLDER}} syntax for all site-specific values rather than example data, keeping templates reusable
  - Phase 5 template includes before/after metrics table matching MIGRATION.md §10 requirement for MTTR, false-positive rate, CPU/RSS, and support-ticket counts
duration: 
verification_result: passed
completed_at: 2026-05-19T10:21:27.773Z
blocker_discovered: false
---

# T06: Created Phase 3/4/5 operator communication templates referenced by MIGRATION.md §10

**Created Phase 3/4/5 operator communication templates referenced by MIGRATION.md §10**

## What Happened

MIGRATION.md §10 (Communication) references phase-specific operator notices but no templates existed. Created three markdown templates in docs/templates/:

1. **cutover-phase3-notice.md** — Canary deployment notice for fleet ops/NOC. Covers: what is changing (v1→v2 with ADR-0014 context), canary scope table (box list, version, duration, health gates), what to expect (no manual intervention), rollback procedure (v2→previous-v2 only), and escalation contacts.

2. **cutover-phase4-notice.md** — Fleet rollout expansion notice, sent daily with each 10% batch. Covers: current batch details, health gate pass status from canary (all 4 gates), daily progress tracker, per-box and cohort rollback procedures.

3. **cutover-phase5-notice.md** — Post-rollout summary notice. Covers: rollout timeline summary, before/after metrics table (MTTR, false-positive rate, CPU/RSS, support tickets per MIGRATION.md §10 requirements), v1 decommission status, ongoing operations (rollback path, health monitoring, runbook pointers).

All templates use `{{PLACEHOLDER}}` syntax for site-specific values. Each template cross-references MIGRATION.md, FLEET_GATES.md, and ADR-0014 with correct relative paths. Rollback procedures in all templates consistently describe the v2→previous-v2 path with no v1 fallback, matching ADR-0014.

## Verification

Verified: (1) all 3 template files exist in docs/templates/; (2) referenced documents (MIGRATION.md, FLEET_GATES.md, adr/0014-v1-retired-pivot.md) all exist at the relative paths used in templates; (3) phase names in templates match MIGRATION.md phase naming (Phase 3 = Canary 10%, Phase 4 = Fleet rollout, Phase 5 = v1 decommission); (4) rollback procedure in all templates matches the canonical procedure from MIGRATION.md.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `ls -la docs/templates/cutover-phase{3,4,5}-notice.md` | 0 | pass | 120ms |
| 2 | `ls docs/adr/0014-v1-retired-pivot.md docs/FLEET_GATES.md docs/MIGRATION.md` | 0 | pass | 95ms |
| 3 | `wc -l docs/templates/*.md` | 0 | pass — 57+63+60=180 lines total | 80ms |

## Deviations

None

## Known Issues

None

## Files Created/Modified

- `docs/templates/cutover-phase3-notice.md`
- `docs/templates/cutover-phase4-notice.md`
- `docs/templates/cutover-phase5-notice.md`
