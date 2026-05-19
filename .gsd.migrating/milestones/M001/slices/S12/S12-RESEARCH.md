# S12 Research: V1 Decommission & Archive

**Depth:** Light research — this is a documentation and repo-hygiene slice with no daemon code changes. The scope is well-defined by MIGRATION.md Phase 5 (formerly Phase 6/7) success criteria.

---

## Summary

S12 is the final slice in M001. It performs the v1 decommission tasks defined in MIGRATION.md § 7 ("Phase 5 — v1 decommission") and ROADMAP.md Phase 7 success criteria. The work is entirely documentation, repo organization, and cleanup — no daemon code changes.

**Key finding:** v1 is already retired across the fleet (ADR-0014, 2026-05-11). The v1 bash scripts (`diag.sh`, `recovery.sh`, `auto_profile.sh`, `zao_reset_line.sh`) are **not in this repository** — they were never committed here. ADR-0014 line 47 says they are "archived in the `v1-legacy` branch for reference only", but **no such branch exists** (verified via `git branch -a`). This means either:
- (a) The v1 scripts were in a separate repo and the `v1-legacy` branch was never created, or
- (b) The branch needs to be created as part of S12.

Since v1 was loose scripts deployed directly (never .deb-packaged, per ADR-0014), and this repo is the v2 Python rewrite, the most honest approach is: **create `archive/v1/README.md`** pointing at where the v1 scripts lived (on-device paths, not in this repo), and documenting that they are retired. There are no v1 source files to move into `archive/v1/` because they were never in this repo.

---

## Scope from ROADMAP.md Phase 7 Success Criteria

Three success criteria define the exit gate:

### SC#1 — Fleet purge of v1 paths
> `apt purge spark-modem-watchdog-v1` runs cleanly on every box; a fleet-wide grep confirms zero references remain to v1 paths (`/usr/local/bin/diag.sh`, `/usr/local/bin/recovery.sh`, `/usr/local/bin/auto_profile.sh`, `/usr/local/bin/zao_reset_line.sh`) in any unit file, cron entry, or systemd dependency.

**Status:** This is a fleet-ops task, not a code task. v1 was never .deb-packaged (ADR-0014), so there is no `apt purge` to run. The v1 scripts were loose files manually deployed. Fleet purge is an operator runbook step, not an S12 code deliverable. However, S12 should produce a **v1 purge checklist** document that operators can follow to confirm v1 remnants are gone from each box.

### SC#2 — Archive v1 scripts in repo
> The v1 source scripts are moved to `archive/v1/` in the repository with a README pointing at v2; the v1 issue-tracker label is closed; `CLAUDE.md` and `AGENTS.md` no longer reference v1 paths or workflows.

**Status:**
- v1 scripts are NOT in this repo — `archive/v1/README.md` should document their origin and retirement, not move files.
- `AGENTS.md` does not exist — no action needed.
- `CLAUDE.md` line 6-7 says "Python rewrite of an existing v1 bash toolchain" — this is historical context, not an active v1 reference. It's accurate and should stay. Line 72 mentions "migration of v1 state files" as out-of-scope — also accurate.
- `docs/README.md` line 6 says "The v1 system (the scripts in the parent directory)" — this is stale; v1 scripts are no longer in the parent directory. Needs update.
- `docs/adr/README.md` — ADR-0014 is missing from the status table. Needs adding.

### SC#3 — Post-mortem summary
> A post-mortem-style summary documents the migration outcome regardless of whether anything went wrong, including before/after metrics: MTTR, false-positive reset rate, daemon CPU/RSS, support-ticket count.

**Status:** This requires real fleet metrics data that only exists after production operation. S12 should produce a **migration post-mortem template** with the structure and metric placeholders, matching the Phase 5 notice template (`docs/templates/cutover-phase5-notice.md`) which already covers most of this content.

---

## Existing Artifacts Inventory

### Already Done (by S11)
- `docs/adr/0014-v1-retired-pivot.md` — ADR recording v1-retired decision ✓
- `docs/MIGRATION.md` — Rewritten for v1-retired reality, Phase 5 = decommission ✓
- `docs/FLEET_GATES.md` — Health-gate PromQL definitions ✓
- `docs/CUTOVER_RUNBOOK.md` — Per-box cutover procedure ✓
- `docs/templates/cutover-phase{3,4,5}-notice.md` — Communication templates ✓
- Stale v1-as-active references removed from `.planning/PROJECT.md` and `.planning/ROADMAP.md` ✓

### Needs Doing (S12 scope)
1. **`archive/v1/README.md`** — Pointer file documenting v1's origin, retirement, and where scripts lived.
2. **`docs/V1_PURGE_CHECKLIST.md`** — Operator checklist for confirming v1 remnants removed from a box.
3. **`docs/MIGRATION_POSTMORTEM_TEMPLATE.md`** — Template for the migration outcome summary with metric placeholders.
4. **`docs/adr/README.md`** — Add ADR-0014 to the status table.
5. **`docs/README.md`** — Update line 6 ("scripts in the parent directory") to reflect v1 is retired; update ADR list (stops at 0007, missing 0008-0014).
6. **`CLAUDE.md`** — Evaluate whether any v1 references need updating (finding: line 6 historical context is fine; line 72 out-of-scope is fine; line 17 REQUIREMENTS reference is fine).
7. **Test(s)** — Validation test(s) confirming no stale v1-as-active references remain in docs and that archive/v1/README.md exists.

---

## Recommendation

### Implementation Approach

This is a **light, documentation-only slice** with 4-5 tasks:

**T01 — `archive/v1/README.md` + `docs/V1_PURGE_CHECKLIST.md`**
Create the archive pointer and purge checklist. The README documents:
- What v1 was (bash scripts: `diag.sh`, `recovery.sh`, `auto_profile.sh`, `zao_reset_line.sh`, `spark-modem-watchdog.sh`)
- Where they lived on-device (`/usr/local/bin/`)
- When retired (2026-05-11, ADR-0014)
- That v2 (`spark-modem-watchdog`) replaces them entirely

The purge checklist documents per-box operator steps:
- Verify no v1 scripts at `/usr/local/bin/{diag,recovery,auto_profile,zao_reset_line}.sh`
- Verify no v1 cron entries or systemd units referencing v1 paths
- Verify no stale v1 state files (v2 starts fresh per ADR-0014)

**T02 — `docs/MIGRATION_POSTMORTEM_TEMPLATE.md`**
Template for the SC#3 migration outcome summary. Structure mirrors `docs/templates/cutover-phase5-notice.md` but adds:
- Timeline section (rollout phases with dates)
- Incident log (even if empty)
- Lessons learned section
- Before/after metrics table (same as phase-5 notice)
- Formal sign-off block

**T03 — ADR README + docs README updates**
- Add ADR-0014 to `docs/adr/README.md` status table (row 14)
- Update `docs/README.md`:
  - Line 6: change "The v1 system (the scripts in the parent directory)" to past-tense retired reference
  - Lines 36-43: Add ADRs 0008-0014 to the ADR list
  - Lines 44-52: Update "What v1 looked like" section to past tense with pointer to `archive/v1/README.md`

**T04 — Stale-reference sweep + validation test**
- `grep` sweep for any remaining v1-as-active references in `docs/*.md`, `CLAUDE.md`, `.planning/PROJECT.md`
- Distinguish historical/architectural references (keep) from active-state claims (fix)
- Write `tests/unit/test_v1_decommission.py` validating:
  - `archive/v1/README.md` exists and contains required sections
  - `docs/adr/README.md` contains ADR-0014 entry
  - No v1-as-active references in key docs (same pattern as S11's `test_cutover_runbook_doc.py`)
  - `docs/V1_PURGE_CHECKLIST.md` exists

### Risk Assessment

**Low risk.** This is documentation cleanup with no daemon code changes. The primary risk is accidentally breaking a docs cross-reference or removing a v1 reference that is legitimately historical/architectural.

### Natural Seams (Independent Work Units)

- T01 (archive + purge checklist) — standalone, no dependencies
- T02 (postmortem template) — standalone, no dependencies
- T03 (README updates) — standalone, no dependencies
- T04 (sweep + test) — depends on T01-T03 being complete

T01, T02, T03 can be done in parallel. T04 is the verification gate.

### First Proof

T01 (`archive/v1/README.md`) is the highest-value deliverable — it's the primary artifact that SC#2 demands. Start there.

### Verification

```bash
# File existence
test -f archive/v1/README.md
test -f docs/V1_PURGE_CHECKLIST.md
test -f docs/MIGRATION_POSTMORTEM_TEMPLATE.md

# ADR-0014 in README table
grep "0014" docs/adr/README.md

# No stale v1-as-active references
# (v1 references in ADR context/background/PRD background are OK)
grep -rn "v1 currently" docs/*.md  # should be zero
grep -rn "scripts in the parent directory" docs/README.md  # should be zero

# Unit tests
pytest tests/unit/test_v1_decommission.py -v

# Full suite regression
pytest tests/unit/ -q --tb=short
```

---

## Implementation Landscape

### Files to Create
| File | Purpose |
|------|---------|
| `archive/v1/README.md` | Pointer documenting v1 retirement, replaces SC#2's "move v1 scripts" |
| `docs/V1_PURGE_CHECKLIST.md` | Operator checklist for confirming v1 remnants gone from box |
| `docs/MIGRATION_POSTMORTEM_TEMPLATE.md` | Template for SC#3 migration outcome summary |
| `tests/unit/test_v1_decommission.py` | Validation test for decommission artifacts |

### Files to Modify
| File | Change |
|------|--------|
| `docs/adr/README.md` | Add ADR-0014 row to status table |
| `docs/README.md` | Update v1 references to past tense; add ADRs 0008-0014 to list; update "What v1 looked like" section |

### Files NOT to Modify
| File | Why |
|------|-----|
| `CLAUDE.md` | v1 references are historical context ("Python rewrite of v1") and out-of-scope exclusions — both accurate |
| `docs/PRD.md` | v1 references are in Background section — architectural history, not active claims (confirmed by S11) |
| `docs/ARCHITECTURE.md` | "What we are taking/dropping from v1" sections are architectural rationale — permanent record |
| `docs/RECOVERY_SPEC.md` | v1 comparisons are design rationale |
| `docs/SCHEMA.md` | v1 comparisons are design rationale |
| `docs/MIGRATION.md` | Already rewritten by S11 |
| `docs/adr/0014-v1-retired-pivot.md` | Already correct |

### Patterns from S11 to Follow
- `tests/unit/test_cutover_runbook_doc.py` — same grep-based doc validation pattern for the new test
- `docs/templates/cutover-phase5-notice.md` — reference for postmortem template structure
- `{{PLACEHOLDER}}` syntax for operator-populated values

---

## Skill Recommendations

No external skills needed. This is standard documentation and test writing — established patterns from S11 apply directly. The `write-docs` skill could help with the postmortem template, but the scope is small enough that it's not necessary.

---

## Constraints and Watch-outs

1. **v1 scripts are NOT in this repo.** Don't try to `git mv` anything. The `archive/v1/README.md` is a pointer, not a container.
2. **The `v1-legacy` branch referenced in ADR-0014 does not exist.** The archive README should note this honestly — the v1 scripts lived on-device only, not in version control.
3. **Don't touch architectural v1 references.** PRD, ARCHITECTURE, RECOVERY_SPEC, SCHEMA all have legitimate v1 comparisons that are permanent design rationale. Only fix references that claim v1 is currently active or present.
4. **`docs-review-v1.md` referenced in PRD.md:64 never existed.** This is a pre-existing TODO, not an S12 concern.
5. **No `AGENTS.md` exists** — the ROADMAP SC#2 mentions it but it was never created. No action needed.
