---
id: T01
parent: S11
milestone: M001
key_files:
  - docs/adr/0014-v1-retired-pivot.md
key_decisions:
  - Rollback strategy is v2→v2-previous-version only (Option C from S11-RESEARCH §6); no v1 .deb will be built
  - ADR date set to 2026-05-11 (when decision was locked in 05-CONTEXT.md), not today
duration: 
verification_result: passed
completed_at: 2026-05-19T09:06:11.688Z
blocker_discovered: false
---

# T01: Wrote ADR-0014 formally recording the v1-retired scope pivot from 2026-05-11

**Wrote ADR-0014 formally recording the v1-retired scope pivot from 2026-05-11**

## What Happened

Created `docs/adr/0014-v1-retired-pivot.md` following the established ADR template (0001–0013 pattern). The ADR records the decision locked in `05-CONTEXT.md` on 2026-05-11: v1 is already retired fleet-wide, so the shadow-alongside-v1 migration strategy (MIGRATION.md Phases 1-2) is dead. The decision formalizes that v2 is the only daemon, rollback = v2→v2-previous-version only, no v1 `.deb` will be built, and all `-v2`-suffixed paths / shadow artifacts are removed from scope.

Inputs used: ADR-0001 for template structure, S11-RESEARCH.md §6 for rollback strategy analysis (Option C selected: rollback = v2 previous version only). The ADR covers Context (original shadow migration plan + why it's invalid), Decision (4 specific points), Consequences (MIGRATION.md rewrite, honest rollback story, no shadow tooling, simplified cutover, risk acceptance with canary mitigation), and Revisit-when clause.

## Verification

Verified file existence and ADR template compliance:
1. `test -f docs/adr/0014-v1-retired-pivot.md` — file exists.
2. Grep for required sections: Context (line 10), Decision (line 30), Consequences (line 52), Revisit when (line 73) — all 4 present.
3. Status header table present at line 5 with value "Accepted".
4. File is ~78 lines, within the expected ~40-80 line range for an ADR.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `test -f docs/adr/0014-v1-retired-pivot.md` | 0 | pass | 150ms |
| 2 | `grep -cE '^## (Context|Decision|Consequences|Revisit when)' docs/adr/0014-v1-retired-pivot.md` | 0 | pass — 4 sections found | 200ms |
| 3 | `grep -c '^| Status' docs/adr/0014-v1-retired-pivot.md` | 0 | pass — Status field present | 180ms |

## Deviations

None

## Known Issues

None

## Files Created/Modified

- `docs/adr/0014-v1-retired-pivot.md`
