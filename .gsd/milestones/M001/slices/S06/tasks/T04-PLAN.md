# T04: 05.1-deb-packaging-hotfix 04

**Slice:** S06 — **Milestone:** M001

## Description

Author the operator-facing EXIT-CHECKLIST.md template that the on-site
engineer fills + commits as the Phase 05.1 EXIT gate. Mirror the shape of
Phase 5's SIGNOFF.md (CONTEXT.md decision V-03 explicitly invokes the same
pattern).

Implements locked decision **V-03** from
`.planning/phases/05.1-deb-packaging-hotfix/05.1-CONTEXT.md`.

Purpose: phase 05.1 has no ROADMAP-shaped Success Criteria block (D-03:
EXIT bar pattern, not a full SC block). The forcing function is a
structured operator-filled checklist with 9 rows — one per V-03 step from
CONTEXT.md L-162..173. The committed checklist is the phase-exit artifact.

This plan creates the TEMPLATE; the actual fill-in happens out-of-band on
the bench Jetson by the on-site engineer (single-operator workflow per
CONTEXT.md specifics).

Output: `.planning/phases/05.1-deb-packaging-hotfix/EXIT-CHECKLIST.md` with
header table, 9-row gate table, approval footer, footer reference.

## Must-Haves

- [ ] "EXIT-CHECKLIST.md exists at .planning/phases/05.1-deb-packaging-hotfix/EXIT-CHECKLIST.md"
- [ ] "EXIT-CHECKLIST.md has a header table for box-id / .deb commit SHA / install + EXIT ISO timestamps (operator-fillable)"
- [ ] "EXIT-CHECKLIST.md has a 9-row gate table covering the 9 V-03 steps from CONTEXT.md L-162..173"
- [ ] "Each gate row has columns: # / Step / Status (☐ PASS ☐ FAIL) / Command / Expected / Observed / Notes"
- [ ] "EXIT-CHECKLIST.md has an approval footer with engineer signature + ISO date (mirror SIGNOFF.md lines 109-119)"
- [ ] "EXIT-CHECKLIST.md is template-only (placeholder values italicized with underscores, e.g. _bench-jetson-01_)"

## Files

- `.planning/phases/05.1-deb-packaging-hotfix/EXIT-CHECKLIST.md`
