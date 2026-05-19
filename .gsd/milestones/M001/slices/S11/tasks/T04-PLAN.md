---
estimated_steps: 7
estimated_files: 4
skills_used: []
---

# T04: Cutover runbook, communication templates, and stale-doc cleanup

**Why:** Operators need a simplified per-box cutover procedure (current MIGRATION.md §5 was stale). MIGRATION.md §11 references communication templates that don't exist. Several docs still say "v1 currently keeps a real fleet online" which is false post-pivot.

**Do:**
1. Write `docs/CUTOVER_RUNBOOK.md` — operator-facing step-by-step for the simplified cutover: pre-checks (SSH access, .deb on apt repo, maintenance window), install (`apt install spark-modem-watchdog`), enable (`systemctl enable --now`), verify (run `tools/validate_cutover.py`), rollback procedure (install previous v2 version). Include estimated timing per step.
2. Add communication templates section to the rewritten MIGRATION.md (or create `docs/templates/` directory with 3 files): Phase 3 site-cutover email template, Phase 4 canary-rollout ops notice, Phase 5 fleet-wide completion notice. Keep templates concise — operator names, box counts, health-gate status, rollback procedure summary.
3. Stale-doc cleanup: (a) Update `docs/PRD.md` intro — remove/replace "v1 currently keeps a real fleet online" with v2 context. (b) Update `.planning/PROJECT.md` if it contains stale v1-active references. (c) Verify `.planning/ROADMAP.md` Phase 5 SC#1-3 are accurate (read-only check — ROADMAP.md is GSD-managed, note any needed updates but don't break the managed format).
4. `grep -rc 'v1 currently keeps' docs/ .planning/` must return 0.

**Done-when:** CUTOVER_RUNBOOK.md exists with step-by-step procedure. Communication templates exist. Zero matches for 'v1 currently keeps' in docs/ and .planning/.

## Inputs

- `docs/MIGRATION.md`
- `docs/PRD.md`
- `.planning/PROJECT.md`
- `docs/adr/0014-v1-retired-pivot.md`
- `tools/validate_cutover.py`

## Expected Output

- `docs/CUTOVER_RUNBOOK.md`
- `docs/PRD.md`
- `.planning/PROJECT.md`

## Verification

Test-Path docs/CUTOVER_RUNBOOK.md; Select-String -Pattern 'v1 currently keeps' docs/PRD.md,.planning/PROJECT.md -Quiet; if ($?) { Write-Error 'Stale v1 refs found'; exit 1 } else { Write-Output 'Clean' }
