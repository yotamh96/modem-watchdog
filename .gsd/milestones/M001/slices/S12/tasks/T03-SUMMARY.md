---
id: T03
parent: S12
milestone: M001
key_files:
  - docs/adr/README.md
  - docs/README.md
key_decisions:
  - ADR list in docs/README.md extended to include all 14 ADRs rather than just the original 7, matching the adr/README.md status table
duration: 
verification_result: passed
completed_at: 2026-05-19T12:19:31.983Z
blocker_discovered: false
---

# T03: Added ADR-0014 to adr/README.md status table and updated docs/README.md with ADRs 0008-0014, past-tense v1 language, and archive pointer

**Added ADR-0014 to adr/README.md status table and updated docs/README.md with ADRs 0008-0014, past-tense v1 language, and archive pointer**

## What Happened

Updated two documentation index files to reflect the current state of the project:\n\n1. **docs/adr/README.md**: Added ADR-0014 (v1-Retired Scope Pivot) row to the status overview table, keeping it consistent with the 14 ADR files on disk.\n\n2. **docs/README.md**: Three changes:\n   - **ADR list**: Extended from ADRs 0001-0007 to 0001-0014, adding the seven ADRs created during later phases (state machine 5+2, usb_path keying, packaging, webhooks, locking, metrics, v1-retired pivot).\n   - **v1 references updated to past tense**: The intro paragraph changed "works in production / has limits we want to break out of" to "worked in production / had limits we needed to break out of", with a pointer to archive/v1/README.md. The "What v1 looked like" section changed "is a set of bash scripts" to "was", added the retirement note with ADR-0014 link, changed "keep/replace" to "kept/replaces", and added the archive pointer.\n   - **Archive pointer**: Both the intro and the v1 section now link to archive/v1/README.md for the full v1 decommission record.

## Verification

Ran grep checks confirming: (1) '0014' appears in docs/adr/README.md status table, (2) '0008' appears in docs/README.md ADR list, (3) 'retired', 'archive/v1', and 'worked in production' appear in docs/README.md at the expected locations.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `Select-String -Pattern '0014' docs/adr/README.md -Quiet` | 0 | pass | 50ms |
| 2 | `Select-String -Pattern '0008' docs/README.md -Quiet` | 0 | pass | 50ms |
| 3 | `grep 'retired|archive/v1|worked in production' docs/README.md` | 0 | pass — 5 matches across intro and v1 section | 40ms |

## Deviations

none

## Known Issues

none

## Files Created/Modified

- `docs/adr/README.md`
- `docs/README.md`
