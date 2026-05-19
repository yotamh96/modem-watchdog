---
estimated_steps: 6
estimated_files: 1
skills_used: []
---

# T02: Migration postmortem template

**Why:** MIGRATION.md Phase 5 SC#3 requires a post-mortem-style summary documenting migration outcome with before/after metrics. Real fleet metrics are not yet available, so S12 delivers a template with placeholders. Structure mirrors docs/templates/cutover-phase5-notice.md (the Phase 5 completion notice from S11) but adds timeline, incident log, lessons learned, and formal sign-off sections.

**Do:**
1. Create docs/MIGRATION_POSTMORTEM_TEMPLATE.md with these sections: Executive Summary (with {{PLACEHOLDER}} values), Timeline (rollout phases with date placeholders), Incident Log (table, even if empty), Before/After Metrics (reuse the same metric table from cutover-phase5-notice.md: MTTR-SIM, MTTR-registration, MTTR-QMI-hung, false-positive rate, daemon CPU, daemon RSS, support tickets), Lessons Learned (numbered list with prompts), Formal Sign-Off (table with role/name/date columns for eng lead, ops lead, product owner).
2. Use {{PLACEHOLDER}} syntax consistent with S11 templates.
3. Reference ADR-0014, FLEET_GATES.md, and MIGRATION.md where appropriate.

**Done-when:** File exists with all required sections and metric placeholders matching PRD success metrics M1-M7 coverage.

## Inputs

- `docs/templates/cutover-phase5-notice.md`
- `docs/FLEET_GATES.md`
- `docs/MIGRATION.md`

## Expected Output

- `docs/MIGRATION_POSTMORTEM_TEMPLATE.md`

## Verification

test -f docs/MIGRATION_POSTMORTEM_TEMPLATE.md && grep -q 'MTTR' docs/MIGRATION_POSTMORTEM_TEMPLATE.md && grep -q 'Lessons Learned' docs/MIGRATION_POSTMORTEM_TEMPLATE.md && grep -q 'Sign-Off' docs/MIGRATION_POSTMORTEM_TEMPLATE.md && grep -q 'ADR-0014' docs/MIGRATION_POSTMORTEM_TEMPLATE.md
