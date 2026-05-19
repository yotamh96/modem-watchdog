# S12: V1 Decommission & Archive

**Goal:** Complete v1 decommission documentation: archive pointer, purge checklist, postmortem template, README updates, and validation test. No daemon code changes — documentation and repo hygiene only.
**Demo:** unit tests prove v1 Decommission & Archive works

## Must-Haves

- 1. archive/v1/README.md exists documenting v1 retirement.\n2. docs/V1_PURGE_CHECKLIST.md exists with operator steps.\n3. docs/MIGRATION_POSTMORTEM_TEMPLATE.md exists with metric placeholders.\n4. docs/adr/README.md contains ADR-0014 entry.\n5. docs/README.md has no stale v1-as-active references.\n6. No stale v1-as-active references remain in docs/ or .planning/.\n7. Existing unit tests still pass (no regressions).

## Proof Level

- This slice proves: operational — documentation correctness verified by grep-based consistency checks and file-existence tests; no new daemon behavior to integration-test.

## Integration Closure

Upstream: S11 (Cutover and Fleet Rollout) delivered rewritten MIGRATION.md and stale-doc cleanup. S12 consumes those artifacts and adds the final decommission layer. Downstream: none — S12 is the last slice in M001.

## Verification

- No runtime observability changes. Documentation-only slice.

## Tasks

- [ ] **T01: V1 archive pointer and purge checklist** `est:20min`
  Create archive/v1/README.md documenting what v1 was (bash scripts: diag.sh, recovery.sh, auto_profile.sh, zao_reset_line.sh, spark-modem-watchdog.sh), where they lived on-device (/usr/local/bin/), when retired (2026-05-11, ADR-0014), and that v2 replaces them entirely. The v1 scripts were never in this repo — the README is a pointer, not a container.
  - Files: `archive/v1/README.md`, `docs/V1_PURGE_CHECKLIST.md`
  - Verify: Test-Path archive/v1/README.md; Test-Path docs/V1_PURGE_CHECKLIST.md; Select-String -Pattern 'ADR-0014' archive/v1/README.md -Quiet; Select-String -Pattern 'diag.sh' archive/v1/README.md -Quiet

- [ ] **T02: Migration postmortem template** `est:15min`
  Create docs/MIGRATION_POSTMORTEM_TEMPLATE.md as the template for SC#3 migration outcome summary. Adds: timeline section (rollout phases with dates), incident log (even if empty), lessons learned section, before/after metrics table (MTTR, false-positive reset rate, daemon CPU/RSS, support-ticket count), and formal sign-off block. Uses {{PLACEHOLDER}} syntax for operator-populated values.
  - Files: `docs/MIGRATION_POSTMORTEM_TEMPLATE.md`
  - Verify: Test-Path docs/MIGRATION_POSTMORTEM_TEMPLATE.md; Select-String -Pattern 'MTTR' docs/MIGRATION_POSTMORTEM_TEMPLATE.md -Quiet; Select-String -Pattern 'PLACEHOLDER' docs/MIGRATION_POSTMORTEM_TEMPLATE.md -Quiet

- [ ] **T03: ADR README and docs README updates** `est:20min`
  Update docs/adr/README.md to add ADR-0014 to the status table. Update docs/README.md: fix any stale v1-as-active references to past-tense retired language; add ADRs 0008-0014 to the ADR list (currently stops at 0007); update any 'What v1 looked like' section to past tense with pointer to archive/v1/README.md.
  - Files: `docs/adr/README.md`, `docs/README.md`
  - Verify: Select-String -Pattern '0014' docs/adr/README.md -Quiet; Select-String -Pattern '0008' docs/README.md -Quiet

- [ ] **T04: Stale-reference sweep and validation test** `est:25min`
  Grep sweep for any remaining v1-as-active references in docs/*.md, CLAUDE.md, .planning/PROJECT.md. Distinguish historical/architectural references (keep) from active-state claims (fix). Write tests/unit/test_v1_decommission.py validating: archive/v1/README.md exists and contains required sections; docs/adr/README.md contains ADR-0014 entry; no v1-as-active references in key docs; docs/V1_PURGE_CHECKLIST.md exists.
  - Files: `tests/unit/test_v1_decommission.py`
  - Verify: uv run pytest tests/unit/test_v1_decommission.py -v; uv run mypy --strict tests/unit/test_v1_decommission.py; uv run ruff check tests/unit/test_v1_decommission.py

## Files Likely Touched

- archive/v1/README.md
- docs/V1_PURGE_CHECKLIST.md
- docs/MIGRATION_POSTMORTEM_TEMPLATE.md
- docs/adr/README.md
- docs/README.md
- tests/unit/test_v1_decommission.py
