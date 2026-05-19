# S11: Cutover & Fleet Rollout

**Goal:** Deliver all cutover documentation, health-gate definitions, and post-cutover validation tooling needed for fleet rollout. No daemon code changes — this is a delivery-phase slice that produces ADR-0014 (v1-retired pivot), a rewritten MIGRATION.md reflecting v1-retired reality, health-gate PromQL definitions, a post-cutover validation script, per-box cutover runbook, communication templates, and stale-doc cleanup.
**Demo:** unit tests prove Cutover & Fleet Rollout works

## Must-Haves

- 1. ADR-0014 exists following the 0001-0013 template pattern.\n2. MIGRATION.md contains zero references to dead artifacts (99-shadow, compare_v1_v2, watchdog-v2.service, -v2/ paths).\n3. Health-gate PromQL definitions reference only metrics present in metrics_registry.py.\n4. validate_cutover.py passes --help, mypy --strict, and ruff check.\n5. No stale "v1 currently keeps" phrasing in docs/ or .planning/.\n6. Existing unit tests still pass (no regressions).

## Proof Level

- This slice proves: operational — documentation correctness verified by grep-based consistency checks; validation script verified by type-check + lint + --help invocation; no new daemon behavior to integration-test.

## Integration Closure

Upstream: all daemon code (S01-S10) is complete. This slice consumes the metrics surface (ADR-0013, metrics_registry.py), the .deb packaging pipeline, and the CLI interface. Downstream: S12 (v1 Decommission & Archive) depends on the rewritten MIGRATION.md and ADR-0014. No new wiring into daemon code.

## Verification

- No runtime observability changes. The health-gate PromQL definitions document how to query existing metrics for fleet-level gating decisions — they don't add new metrics.

## Tasks

- [ ] **T01: ADR-0014 and health-gate PromQL definitions** `est:30min`
  **Why:** The v1-retired pivot is a locked decision (05-CONTEXT.md, 2026-05-11) but has no formal ADR. ROADMAP SC#2 references 4 fleet-aggregate health gates with no concrete PromQL. Both are prerequisites for the MIGRATION.md rewrite.
  - Files: `docs/adr/0014-v1-retired-pivot.md`, `docs/FLEET_GATES.md`
  - Verify: Test-Path docs/adr/0014-v1-retired-pivot.md; Select-String -Pattern '99-shadow|compare_v1_v2|watchdog-v2' docs/adr/0014-v1-retired-pivot.md -Quiet; Select-String -Pattern 'modem_state_value|actions_total|state_duration_seconds|process_start_time_seconds' docs/FLEET_GATES.md | Measure-Object -Line

- [ ] **T02: MIGRATION.md rewrite for v1-retired reality** `est:45min`
  **Why:** The current MIGRATION.md references dead artifacts (99-shadow.yaml, compare_v1_v2.py, -v2 paths, v1 .deb rollback) and dead phases (Phase 1 shadow-alongside, Phase 2 field-shadow). Operators will follow stale procedures if this isn't fixed. This is the P0 deliverable.
  - Files: `docs/MIGRATION.md`
  - Verify: Select-String -Pattern '99-shadow|compare_v1_v2|watchdog-v2\.service|-v2/' docs/MIGRATION.md -Quiet; if ($?) { Write-Error 'Stale refs found'; exit 1 } else { Write-Output 'No stale refs' }; Select-String -Pattern 'ADR-0014' docs/MIGRATION.md -Quiet

- [ ] **T03: Post-cutover validation script** `est:45min`
  **Why:** No automated way exists to verify a box is healthy after .deb install + service start. Operators need a single command that checks daemon health, modem state, metrics scrape, and HMAC configuration.
  - Files: `tools/validate_cutover.py`
  - Verify: uv run python tools/validate_cutover.py --help; uv run mypy --strict tools/validate_cutover.py; uv run ruff check tools/validate_cutover.py

- [ ] **T04: Cutover runbook, communication templates, and stale-doc cleanup** `est:40min`
  **Why:** Operators need a simplified per-box cutover procedure (current MIGRATION.md §5 was stale). MIGRATION.md §11 references communication templates that don't exist. Several docs still say "v1 currently keeps a real fleet online" which is false post-pivot.
  - Files: `docs/CUTOVER_RUNBOOK.md`, `docs/MIGRATION.md`, `docs/PRD.md`, `.planning/PROJECT.md`
  - Verify: Test-Path docs/CUTOVER_RUNBOOK.md; Select-String -Pattern 'v1 currently keeps' docs/PRD.md,.planning/PROJECT.md -Quiet; if ($?) { Write-Error 'Stale v1 refs found'; exit 1 } else { Write-Output 'Clean' }

- [ ] **T05: Cross-document consistency verification** `est:15min`
  **Why:** S11 touches 8+ documentation files. A final consistency pass catches cross-references that point at dead sections, metric names that don't match the registry, and stale ADR references.
  - Files: `docs/MIGRATION.md`, `docs/FLEET_GATES.md`, `docs/CUTOVER_RUNBOOK.md`, `docs/adr/0014-v1-retired-pivot.md`, `tools/validate_cutover.py`
  - Verify: uv run pytest tests/unit/ -q --tb=short; uv run mypy --strict tools/validate_cutover.py; uv run ruff check tools/validate_cutover.py; Select-String -Pattern '99-shadow|compare_v1_v2|watchdog-v2\.service|v1 currently keeps' docs/*.md,.planning/PROJECT.md -Quiet; if ($?) { Write-Error 'Stale refs remain'; exit 1 } else { Write-Output 'All consistency checks passed' }

## Files Likely Touched

- docs/adr/0014-v1-retired-pivot.md
- docs/FLEET_GATES.md
- docs/MIGRATION.md
- tools/validate_cutover.py
- docs/CUTOVER_RUNBOOK.md
- docs/PRD.md
- .planning/PROJECT.md
