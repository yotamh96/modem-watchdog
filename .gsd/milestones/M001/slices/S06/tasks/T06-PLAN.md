# T06: Plan 06

**Slice:** S06 — **Milestone:** M001

## Description

Land the two documentation/metadata changes that finalize the phase plan:

1. Rewrite ROADMAP.md Phase 05.1's placeholder Goal line (currently
   `Goal: [Urgent work - to be planned]`) and populate the Plans list to
   reflect the 6 plans `/gsd-plan-phase 05.1` produced. CONTEXT.md
   "Roadmap housekeeping" deferred-ideas section explicitly defers this to
   plan-phase, not discuss-phase.

2. Add a `2.0.1-1` entry to `debian/changelog` per CONTEXT.md "Claude's
   Discretion" (PEP-440 patch bump chosen over `2.0.0+hotfix.1` for
   simplicity and broad tooling compatibility — both are valid Debian
   version strings; 2.0.1 is the cleaner shape).

Purpose: future readers of ROADMAP.md (Phase 6 planner, future operators)
need to see what Phase 05.1 actually delivered. Future `apt-cache policy`
consumers need to see the version reflects the hotfix. Without this plan,
the Phase 05.1 entry stays as `[Urgent work - to be planned]` and the .deb
ships as `2.0.0-1` indistinguishable from the pre-hotfix package.

Output:
- `.planning/ROADMAP.md` Phase 05.1 entry rewritten.
- `debian/changelog` with a new top entry.
