# S12: V1 Decommission & Archive

**Goal:** Complete v1 decommission by creating the archive pointer README, operator purge checklist, migration postmortem template, updating docs/adr/README.md and docs/README.md to reflect v1 retirement and ADRs 0008-0014, and validating no stale v1-as-active references remain. Documentation-only slice with no daemon code changes.
**Demo:** unit tests prove v1 Decommission & Archive works

## Must-Haves

- 1. archive/v1/README.md exists documenting v1 retirement, on-device paths, and pointer to v2.\n2. docs/V1_PURGE_CHECKLIST.md exists with operator steps for confirming v1 remnants removed per box.\n3. docs/MIGRATION_POSTMORTEM_TEMPLATE.md exists with metric placeholders matching phase-5 notice structure.\n4. docs/adr/README.md contains ADR-0014 row in status table.\n5. docs/README.md updated: line 6 no longer says \"scripts in the parent directory\"; ADR list includes 0008-0014; What v1 looked like section references archive/v1/README.md.\n6. No v1-as-active references remain in docs/*.md (architectural/historical references are OK).\n7. pytest tests/unit/test_v1_decommission.py passes with all assertions green.\n8. pytest tests/unit/ full suite shows zero regressions.

## Proof Level

- This slice proves: doc-existence + grep-sweep + unit-test. No daemon code changes so no mypy/ruff/integration needed.

## Integration Closure

Final slice in M001. No downstream slices depend on S12. Closes MIGRATION.md Phase 5 success criteria SC#1 (purge checklist), SC#2 (archive + README updates), SC#3 (postmortem template). All S11 deliverables (ADR-0014, FLEET_GATES, MIGRATION, CUTOVER_RUNBOOK, templates) are inputs.

## Verification

- None. Documentation-only slice with no runtime changes.

## Tasks

- [ ] **T01: Archive pointer and purge checklist** `est:small`
  **Why:** MIGRATION.md Phase 5 SC#2 requires v1 scripts archived in repo with a pointer README. SC#1 requires a fleet purge verification path. v1 scripts were never in this repo (they were loose files on-device at /usr/local/bin/), so the archive is a pointer document, not a file move. The purge checklist gives operators a per-box verification procedure.
  - Files: `archive/v1/README.md`, `docs/V1_PURGE_CHECKLIST.md`
  - Verify: test -f archive/v1/README.md && grep -q 'ADR-0014' archive/v1/README.md && grep -q 'diag.sh' archive/v1/README.md && grep -q 'recovery.sh' archive/v1/README.md && grep -q 'auto_profile.sh' archive/v1/README.md && grep -q 'zao_reset_line.sh' archive/v1/README.md && test -f docs/V1_PURGE_CHECKLIST.md && grep -q '/usr/local/bin/' docs/V1_PURGE_CHECKLIST.md

- [ ] **T02: Migration postmortem template** `est:small`
  **Why:** MIGRATION.md Phase 5 SC#3 requires a post-mortem-style summary documenting migration outcome with before/after metrics. Real fleet metrics are not yet available, so S12 delivers a template with placeholders. Structure mirrors docs/templates/cutover-phase5-notice.md (the Phase 5 completion notice from S11) but adds timeline, incident log, lessons learned, and formal sign-off sections.
  - Files: `docs/MIGRATION_POSTMORTEM_TEMPLATE.md`
  - Verify: test -f docs/MIGRATION_POSTMORTEM_TEMPLATE.md && grep -q 'MTTR' docs/MIGRATION_POSTMORTEM_TEMPLATE.md && grep -q 'Lessons Learned' docs/MIGRATION_POSTMORTEM_TEMPLATE.md && grep -q 'Sign-Off' docs/MIGRATION_POSTMORTEM_TEMPLATE.md && grep -q 'ADR-0014' docs/MIGRATION_POSTMORTEM_TEMPLATE.md

- [ ] **T03: ADR README and docs README updates** `est:small`
  **Why:** docs/adr/README.md status table stops at ADR-0013 — ADR-0014 (v1-retired-pivot) is missing. docs/README.md line 6 says 'The v1 system (the scripts in the parent directory)' which is stale (v1 is retired, scripts were never in parent directory of this repo). The ADR list in docs/README.md stops at ADR-0007, missing 0008-0014. The 'What v1 looked like' section (lines 44-53) needs past-tense update and pointer to archive/v1/README.md.
  - Files: `docs/adr/README.md`, `docs/README.md`
  - Verify: grep -q '0014' docs/adr/README.md && ! grep -q 'scripts in the parent directory' docs/README.md && grep -q 'ADR-0008' docs/README.md && grep -q 'ADR-0014' docs/README.md && grep -q 'archive/v1' docs/README.md

- [ ] **T04: Stale-reference sweep and validation test** `est:small`
  **Why:** Final verification gate. Must confirm no stale v1-as-active references remain in docs, and that all S12 deliverables meet the completion contract. Follows the same grep-based doc validation pattern established by S11's test_cutover_runbook_doc.py.
  - Files: `tests/unit/test_v1_decommission.py`
  - Verify: python -m pytest tests/unit/test_v1_decommission.py -v && python -m pytest tests/unit/ -q --tb=short

## Files Likely Touched

- archive/v1/README.md
- docs/V1_PURGE_CHECKLIST.md
- docs/MIGRATION_POSTMORTEM_TEMPLATE.md
- docs/adr/README.md
- docs/README.md
- tests/unit/test_v1_decommission.py
