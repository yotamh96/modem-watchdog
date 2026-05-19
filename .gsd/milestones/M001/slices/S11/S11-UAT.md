# S11: Cutover & Fleet Rollout — UAT

**Milestone:** M001
**Written:** 2026-05-19T11:13:30.179Z

# S11 UAT: Cutover & Fleet Rollout

## UAT Type
Operational — documentation correctness verified by grep-based consistency checks; validation script verified by type-check + lint + --help invocation; no new daemon behavior to integration-test.

## Preconditions
- All daemon code slices (S01–S10) are complete.
- Working tree is on `milestone/M001` branch with S11 task commits applied.
- Python venv with dev extras is available (`.venv/`).

## Steps

1. **ADR-0014 exists and follows template**
   - Verify `docs/adr/0014-v1-retired-pivot.md` exists.
   - Confirm it contains: Status (Accepted), Context, Decision, Consequences, Revisit-when sections.
   - Expected: File present, all 4 required sections present, status = Accepted.

2. **MIGRATION.md has no stale references**
   - Run: `grep -cE '99-shadow|compare_v1_v2|watchdog-v2\.service|-v2/' docs/MIGRATION.md`
   - Expected: 0 matches.
   - Run: `grep 'ADR-0014' docs/MIGRATION.md`
   - Expected: ≥1 match (actual: 3).

3. **FLEET_GATES.md metric consistency**
   - Run: `pytest tests/unit/test_fleet_gates_doc.py -v`
   - Expected: 4 tests pass, validating all PromQL metric references exist in `metrics_registry.py` or are Prometheus builtins.

4. **validate_cutover.py quality gates**
   - Run: `python tools/validate_cutover.py --help` → exits 0.
   - Run: `mypy --strict tools/validate_cutover.py` → "Success: no issues found".
   - Run: `ruff check tools/validate_cutover.py` → "All checks passed!".

5. **No stale v1-as-active phrasing in project docs**
   - Run: `grep -r 'v1 currently keeps' docs/ .planning/PROJECT.md`
   - Expected: 0 matches.

6. **Communication templates exist**
   - Verify `docs/templates/cutover-phase3-notice.md`, `cutover-phase4-notice.md`, `cutover-phase5-notice.md` all exist.
   - Expected: 3 files present.

7. **Cutover runbook structure**
   - Run: `pytest tests/unit/test_cutover_runbook_doc.py -v`
   - Expected: 8 tests pass (7 steps present, no stale v1 refs, ADR-0014 ref, validate_cutover ref, prerequisites, troubleshooting, escalation placeholder).

8. **No regressions**
   - Run: `pytest tests/unit/ -q --tb=short`
   - Expected: All tests pass (1001 passed, 90 skipped on Windows dev machine).

## Edge Cases
- ADR-0014's Context section mentions `99-shadow`, `compare_v1_v2`, and `-v2` paths in historical narrative — these are expected and correct (describing what was replaced).
- `process_start_time_seconds` in Gate 4 is a Prometheus builtin, not in `metrics_registry.py` — documented in FLEET_GATES.md and handled by test.
- Windows dev machine skips ~90 POSIX-only tests (subproc signals, inotify) — these pass on the Jetson target.

## Not Proven By This UAT
- Actual fleet deployment execution (requires production Jetson boxes).
- PromQL queries returning correct data against a live Prometheus instance.
- validate_cutover.py running on a live Jetson with daemon active (it checks systemd, modem state, etc.).
- Operator comprehension of runbook and templates (requires human review).
- Communication template delivery via actual notification channels.
