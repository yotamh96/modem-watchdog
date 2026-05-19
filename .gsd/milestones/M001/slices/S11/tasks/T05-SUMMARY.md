---
id: T05
parent: S11
milestone: M001
key_files:
  - docs/PRD.md
  - .planning/PROJECT.md
  - .planning/ROADMAP.md
key_decisions:
  - docs/PRD.md needed no edits — its v1 references are architectural/historical, not active-state claims
  - Phase 5 SC#1-3 in ROADMAP.md left unchanged — the existing note block (lines 387-394) already documents the scope pivot correctly
  - .planning/phases/ historical context docs not edited — they record decisions about staleness, not active claims
duration: 
verification_result: passed
completed_at: 2026-05-19T09:30:32.274Z
blocker_discovered: false
---

# T05: Removed stale v1-as-active references from PROJECT.md and ROADMAP.md to reflect the v1-retired pivot (ADR-0014)

**Removed stale v1-as-active references from PROJECT.md and ROADMAP.md to reflect the v1-retired pivot (ADR-0014)**

## What Happened

Scanned all three target files (docs/PRD.md, .planning/PROJECT.md, .planning/ROADMAP.md) for references treating v1 as currently running or active.

**docs/PRD.md** — no stale references found. The PRD correctly describes v1 in architectural/historical terms ("What v1 is", "What v1 got right/wrong") without claiming it is currently running. No edits needed.

**.planning/PROJECT.md** — 3 edits:
1. Context paragraph (line 152-155): Changed "v1 is a pipeline... It currently keeps a real fleet online; v2 must prove itself in shadow mode before replacing v1" → past tense "v1 was a pipeline... v1 has been retired across the fleet (ADR-0014)" with honest rollback statement.
2. Migration phase checkboxes (lines 128-133): Collapsed 6 shadow-era phases into 5 reflecting v1-retired reality — removed "alongside v1" and "v1 disabled" framing.
3. Key Decisions table (line 216): Updated "Six-phase migration... v1 keeps a real fleet online" → "Five-phase migration... v1 retired across the fleet (ADR-0014); rollback is v2-previous-version only."

**.planning/ROADMAP.md** — 3 edits:
1. Overview paragraph (lines 8-9): Changed "v1 currently keeps a real fleet online, so v2 must prove itself in shadow mode" → "v1 has been retired across the fleet (ADR-0014); v2 deploys directly to canonical paths."
2. Phase 6 Goal (lines 720-726): Removed "v1 disabled and masked but available for ≤10-minute rollback" → "Rollback is v2-previous-version only (ADR-0014)."
3. Phase 6 SC#1 (lines 734-740): Replaced "v1 stopped/disabled/masked... reinstall spark-modem-watchdog-v1_1.0.0_all.deb" with apt-install v2 procedure and ADR-0014 rollback path.

Phase 5's SC#1-3 already carry an inline note block (lines 387-394) documenting the scope pivot — no further edit needed there.

## Verification

Ran grep for "v1 currently keeps" across docs/ and .planning/ — zero matches in all target files. Ran broader pattern grep for "v1 keeps|v1 is running|v1 retaining|alongside v1|shadow.*before replacing v1|v1 disabled and masked" across all three target files — zero matches. The only remaining "v1 currently keeps" hits are in .planning/phases/05-bench-field-shadow/05-CONTEXT.md which is a historical decision log (it documents "this reference is stale") — not a user-facing claim.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `grep 'v1 currently keeps' docs/ .planning/PROJECT.md .planning/ROADMAP.md` | 1 | pass — zero matches | 50ms |
| 2 | `grep -E 'v1 keeps|v1 is running|v1 retaining|alongside v1|v1 disabled and masked' docs/PRD.md .planning/PROJECT.md .planning/ROADMAP.md` | 1 | pass — zero matches in target files | 50ms |

## Deviations

docs/PRD.md required no edits (plan expected edits); this is correct — the PRD uses past-tense architectural description, not active-state claims.

## Known Issues

none

## Files Created/Modified

- `docs/PRD.md`
- `.planning/PROJECT.md`
- `.planning/ROADMAP.md`
