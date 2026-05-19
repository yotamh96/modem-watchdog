---
estimated_steps: 7
estimated_files: 2
skills_used: []
---

# T03: ADR README and docs README updates

**Why:** docs/adr/README.md status table stops at ADR-0013 — ADR-0014 (v1-retired-pivot) is missing. docs/README.md line 6 says 'The v1 system (the scripts in the parent directory)' which is stale (v1 is retired, scripts were never in parent directory of this repo). The ADR list in docs/README.md stops at ADR-0007, missing 0008-0014. The 'What v1 looked like' section (lines 44-53) needs past-tense update and pointer to archive/v1/README.md.

**Do:**
1. Add ADR-0014 row to docs/adr/README.md status table (line 26, after ADR-0013): '| [ADR-0014](0014-v1-retired-pivot.md) | v1 retired — scope pivot | Accepted | — |'
2. Update docs/README.md line 6: change 'The v1 system (the scripts in the parent directory) works in production but has limits' to 'The v1 system was a set of bash scripts deployed directly to /usr/local/bin/ on each Jetson. It was retired across the fleet on 2026-05-11 (ADR-0014). These documents now describe v2 exclusively.'
3. Add ADRs 0008-0014 to the ADR list in docs/README.md (after line 42, the ADR-0007 entry).
4. Update 'What v1 looked like' section (lines 44-53) to past tense and add pointer to archive/v1/README.md.

**Done-when:** docs/adr/README.md contains ADR-0014 row. docs/README.md no longer contains 'scripts in the parent directory'. docs/README.md ADR list includes entries for 0008 through 0014. 'What v1 looked like' section references archive/v1/README.md.

## Inputs

- `docs/adr/README.md`
- `docs/README.md`
- `docs/adr/0014-v1-retired-pivot.md`

## Expected Output

- `docs/adr/README.md`
- `docs/README.md`

## Verification

grep -q '0014' docs/adr/README.md && ! grep -q 'scripts in the parent directory' docs/README.md && grep -q 'ADR-0008' docs/README.md && grep -q 'ADR-0014' docs/README.md && grep -q 'archive/v1' docs/README.md
