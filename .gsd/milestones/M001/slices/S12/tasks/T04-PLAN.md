---
estimated_steps: 15
estimated_files: 1
skills_used: []
---

# T04: Stale-reference sweep and validation test

**Why:** Final verification gate. Must confirm no stale v1-as-active references remain in docs, and that all S12 deliverables meet the completion contract. Follows the same grep-based doc validation pattern established by S11's test_cutover_runbook_doc.py.

**Do:**
1. Run a grep sweep for v1-as-active patterns across docs/*.md, CLAUDE.md, .planning/PROJECT.md. Distinguish historical/architectural references (keep) from active-state claims (fix any found). Patterns to check: 'v1 currently', 'scripts in the parent directory', 'v1 works in production', 'v1 is deployed'.
2. Create tests/unit/test_v1_decommission.py with these test cases:
   - test_archive_readme_exists: archive/v1/README.md exists and contains 'ADR-0014', all 5 v1 script names, '2026-05-11' retirement date
   - test_purge_checklist_exists: docs/V1_PURGE_CHECKLIST.md exists and contains '/usr/local/bin/' and operator verification steps
   - test_postmortem_template_exists: docs/MIGRATION_POSTMORTEM_TEMPLATE.md exists and contains 'MTTR', 'Lessons Learned', 'Sign-Off'
   - test_adr_readme_has_0014: docs/adr/README.md contains 'ADR-0014' and '0014-v1-retired-pivot'
   - test_docs_readme_no_stale_v1: docs/README.md does not contain 'scripts in the parent directory'; does contain 'archive/v1'
   - test_docs_readme_has_all_adrs: docs/README.md contains entries for ADR-0008 through ADR-0014
   - test_no_v1_as_active_in_docs: grep-based sweep across docs/*.md confirming zero matches for v1-as-active patterns (allow ADR context/background sections)
3. Follow the pattern from tests/unit/test_cutover_runbook_doc.py: use Path(__file__).resolve().parents[2] for repo root, pytest fixtures, clear assertion messages.
4. Run pytest tests/unit/test_v1_decommission.py -v to confirm all pass.
5. Run pytest tests/unit/ -q --tb=short to confirm no regressions.

**Done-when:** All tests in test_v1_decommission.py pass. Full test suite shows zero new failures.

## Inputs

- `archive/v1/README.md`
- `docs/V1_PURGE_CHECKLIST.md`
- `docs/MIGRATION_POSTMORTEM_TEMPLATE.md`
- `docs/adr/README.md`
- `docs/README.md`
- `tests/unit/test_cutover_runbook_doc.py`

## Expected Output

- `tests/unit/test_v1_decommission.py`

## Verification

python -m pytest tests/unit/test_v1_decommission.py -v && python -m pytest tests/unit/ -q --tb=short
