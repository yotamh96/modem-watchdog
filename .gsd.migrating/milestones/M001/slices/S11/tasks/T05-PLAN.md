# T05: Stale-doc cleanup

**Slice:** S11 — **Milestone:** M001

## Description

Update docs that still reference v1 as active to reflect the v1-retired pivot:

1. `docs/PRD.md` — remove "v1 currently keeps a real fleet online" and similar framing
2. `.planning/PROJECT.md` — update any v1-active references
3. `.planning/ROADMAP.md` — update Phase 5 SC#1-3 descriptions to reflect v1-retired reality

Scope: targeted edits only — fix stale v1 references, don't restructure documents.

## Files

- `docs/PRD.md`
- `.planning/PROJECT.md`
- `.planning/ROADMAP.md`

## Verify

- `grep -rc 'v1 currently keeps' docs/ .planning/` == 0
- No claims that v1 is running or active anywhere in updated files

## Inputs

- T01 output (ADR-0014 for cross-reference)
- T02 output (rewritten MIGRATION.md for consistency)

## Expected Output

3 files updated with targeted edits removing stale v1 references.
