# T01: ADR-0014 v1-retired pivot

**Slice:** S11 — **Milestone:** M001

## Description

Write `docs/adr/0014-v1-retired-pivot.md` formally recording the v1-retired scope pivot from 2026-05-11. Follow the ADR template established by 0001-0013 (Status, Context, Decision, Consequences).

Context: v1 is already retired fleet-wide as of 2026-05-11. This invalidates the shadow-alongside-v1 migration strategy (MIGRATION.md Phases 1-2), the v1 .deb rollback story, and all `-v2`-suffixed paths. The decision was locked in `05-CONTEXT.md` but never formally recorded as an ADR.

Decision: v2 is the only daemon; rollback = v2→v2-previous-version only. No v1 .deb will be built.

## Files

- `docs/adr/0014-v1-retired-pivot.md`

## Verify

- `test -f docs/adr/0014-v1-retired-pivot.md`
- File follows ADR template (Status/Context/Decision/Consequences sections present)

## Inputs

- `docs/adr/0001-language-python.md` (template reference)
- `.gsd/milestones/M001/slices/S11/S11-RESEARCH.md` §6 (rollback strategy)

## Expected Output

One new ADR file (~40 lines) following established template.
