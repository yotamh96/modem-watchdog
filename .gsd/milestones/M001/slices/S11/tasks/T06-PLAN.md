# T06: Communication templates

**Slice:** S11 — **Milestone:** M001

## Description

Write the Phase 3/4/5 operator communication templates referenced by MIGRATION.md §11. These don't exist yet despite being referenced.

Templates:
1. **Phase 3 site email** — notification to site operators that v2 cutover is beginning on their box(es)
2. **Phase 4 canary-expansion notice** — notification that canary batch is expanding to additional boxes
3. **Phase 5 full-fleet notice** — notification that fleet-wide rollout is complete, v2 is the production daemon

Place as `docs/templates/cutover-phase3-notice.md`, `docs/templates/cutover-phase4-notice.md`, `docs/templates/cutover-phase5-notice.md`.

## Files

- `docs/templates/cutover-phase3-notice.md`
- `docs/templates/cutover-phase4-notice.md`
- `docs/templates/cutover-phase5-notice.md`

## Verify

- All 3 template files exist
- Templates reference correct procedures from rewritten MIGRATION.md

## Inputs

- T02 output (rewritten MIGRATION.md for procedure references)

## Expected Output

3 new markdown template files (~30 lines each) in docs/templates/.
