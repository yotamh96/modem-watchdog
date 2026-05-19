---
estimated_steps: 5
estimated_files: 2
skills_used: []
---

# T01: Archive pointer and purge checklist

**Why:** MIGRATION.md Phase 5 SC#2 requires v1 scripts archived in repo with a pointer README. SC#1 requires a fleet purge verification path. v1 scripts were never in this repo (they were loose files on-device at /usr/local/bin/), so the archive is a pointer document, not a file move. The purge checklist gives operators a per-box verification procedure.

**Do:**
1. Create archive/v1/README.md documenting: what v1 was (bash scripts: diag.sh, recovery.sh, auto_profile.sh, zao_reset_line.sh, spark-modem-watchdog.sh); where they lived on-device (/usr/local/bin/); when retired (2026-05-11, ADR-0014); that v2 (spark-modem-watchdog) replaces them entirely; that the v1-legacy branch referenced in ADR-0014 was never created because v1 scripts were not version-controlled in this repo.
2. Create docs/V1_PURGE_CHECKLIST.md with operator steps: verify no v1 scripts at /usr/local/bin/{diag,recovery,auto_profile,zao_reset_line,spark-modem-watchdog}.sh; verify no v1 cron entries or systemd units referencing v1 paths; verify no stale v1 state files; confirm v2 service is active and healthy. Use {{PLACEHOLDER}} syntax for site-specific values matching S11 template conventions.

**Done-when:** Both files exist with all required sections. archive/v1/README.md mentions ADR-0014 and all 5 v1 script names. docs/V1_PURGE_CHECKLIST.md has actionable operator steps with verification commands.

## Inputs

- `docs/adr/0014-v1-retired-pivot.md`
- `docs/MIGRATION.md`
- `docs/templates/cutover-phase5-notice.md`

## Expected Output

- `archive/v1/README.md`
- `docs/V1_PURGE_CHECKLIST.md`

## Verification

test -f archive/v1/README.md && grep -q 'ADR-0014' archive/v1/README.md && grep -q 'diag.sh' archive/v1/README.md && grep -q 'recovery.sh' archive/v1/README.md && grep -q 'auto_profile.sh' archive/v1/README.md && grep -q 'zao_reset_line.sh' archive/v1/README.md && test -f docs/V1_PURGE_CHECKLIST.md && grep -q '/usr/local/bin/' docs/V1_PURGE_CHECKLIST.md
