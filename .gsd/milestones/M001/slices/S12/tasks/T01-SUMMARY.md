---
id: T01
parent: S12
milestone: M001
key_files:
  - archive/v1/README.md
  - docs/V1_PURGE_CHECKLIST.md
key_decisions:
  - archive/v1/ directory is a pointer only — no v1 scripts are copied into the repo since they were never version-controlled here; the v1-legacy branch is referenced instead
  - Purge checklist includes sign-off block for operator audit trail
  - Checklist covers five verification areas: scripts, cron, systemd, state files, and v2 health confirmation
duration: 
verification_result: passed
completed_at: 2026-05-19T12:16:38.483Z
blocker_discovered: false
---

# T01: Created archive/v1/README.md documenting the retired v1 bash toolchain and docs/V1_PURGE_CHECKLIST.md with per-box operator verification steps.

**Created archive/v1/README.md documenting the retired v1 bash toolchain and docs/V1_PURGE_CHECKLIST.md with per-box operator verification steps.**

## What Happened

Read docs/MIGRATION.md and docs/adr/0014-v1-retired-pivot.md for context on the v1 retirement (2026-05-11) and the decision that v2 replaces v1 entirely with no rollback to bash scripts.

Created archive/v1/README.md (38 lines) documenting:
- What v1 was: five bash scripts (diag.sh, recovery.sh, auto_profile.sh, zao_reset_line.sh, spark-modem-watchdog.sh)
- Where they lived on-device: /usr/local/bin/ as loose files, never packaged as a .deb
- When retired: 2026-05-11 per ADR-0014
- That v2 replaces them entirely; no v1 rollback path exists
- That this directory is a pointer, not a container — the v1 scripts were never in this repo; the v1-legacy branch holds a reference copy

Created docs/V1_PURGE_CHECKLIST.md (47 lines of operator steps) covering:
1. Verify no v1 scripts remain at /usr/local/bin/ (with removal command)
2. Verify no v1 cron entries (root crontab + /etc/cron.d/ etc.)
3. Verify no v1 systemd units (only v2 unit should appear)
4. Verify no stale v1 state files (.state/.txt files vs v2's JSON)
5. Verify v2 is running and healthy
6. Sign-off block for operator record-keeping

## Verification

Ran four PowerShell verification checks: Test-Path for both files, Select-String for ADR-0014 in README, Select-String for diag.sh in README. All four returned True.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `Test-Path archive/v1/README.md` | 0 | True | 50ms |
| 2 | `Test-Path docs/V1_PURGE_CHECKLIST.md` | 0 | True | 50ms |
| 3 | `Select-String -Pattern 'ADR-0014' archive/v1/README.md -Quiet` | 0 | True | 50ms |
| 4 | `Select-String -Pattern 'diag.sh' archive/v1/README.md -Quiet` | 0 | True | 50ms |

## Deviations

None.

## Known Issues

None.

## Files Created/Modified

- `archive/v1/README.md`
- `docs/V1_PURGE_CHECKLIST.md`
