# T02: MIGRATION.md rewrite

**Slice:** S11 — **Milestone:** M001

## Description

Rewrite `docs/MIGRATION.md` to reflect v1-retired reality. The current document references dead artifacts (99-shadow.yaml, compare_v1_v2.py, -v2 paths, v1 .deb for rollback) and procedures that were never implemented (shadow-alongside-v1 Phases 1-2).

Scope:
1. Remove dead Phases 1-2 framing (shadow-alongside-v1, -v2 service/paths, compare tool)
2. Rewrite Phase 3 to simplified flow: apt install → systemctl enable --now → verify
3. Fix rollback section: v2→v2-previous only (no v1 .deb; reference ADR-0014)
4. Update metric names to match ADR-0013 integer encoding (modem_state_value, not spark_modem_state)
5. Remove references to 99-shadow.yaml, compare_v1_v2.py, watchdog-v2.service
6. Keep surviving sections: canary gates concept (Phase 4), fleet-management gating (Phase 5), data migration (§9), risks (§10), communication plan (§11)

Constraint: scope to content updates only — don't restructure the document's section numbering unnecessarily.

## Files

- `docs/MIGRATION.md`

## Verify

- `grep -cE '99-shadow|compare_v1_v2|watchdog-v2\.service|-v2/' docs/MIGRATION.md` == 0
- All Phase procedures updated for v1-retired reality
- ADR-0014 referenced

## Inputs

- `.gsd/milestones/M001/slices/S11/S11-RESEARCH.md` §3 (pivot impact analysis)
- `docs/MIGRATION.md` (current version)
- `src/spark_modem/status_reporter/metrics_registry.py` (real metric names)

## Expected Output

Rewritten MIGRATION.md (~200 lines) with no stale v1 references.
