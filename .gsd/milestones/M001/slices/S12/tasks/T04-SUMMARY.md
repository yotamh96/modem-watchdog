---
id: T04
parent: S12
milestone: M001
key_files:
  - tests/unit/test_v1_decommission.py
key_decisions:
  - Followed test_cutover_runbook_doc.py pattern: module-scoped fixtures, Path-based repo root, clear assertion messages
  - Grep sweep for v1-as-active patterns found zero matches — no doc fixes needed
duration: 
verification_result: passed
completed_at: 2026-05-19T12:25:44.389Z
blocker_discovered: false
---

# T04: Created test_v1_decommission.py with 7 validation tests confirming all S12 decommission artifacts exist with required content and no stale v1-as-active references remain

**Created test_v1_decommission.py with 7 validation tests confirming all S12 decommission artifacts exist with required content and no stale v1-as-active references remain**

## What Happened

Ran a grep sweep for v1-as-active patterns (`v1 currently`, `scripts in the parent directory`, `v1 works in production`, `v1 is deployed`) across docs/*.md — zero matches found, confirming T03's past-tense updates are complete.

Created `tests/unit/test_v1_decommission.py` following the pattern established by `test_cutover_runbook_doc.py`: module-scoped fixtures reading files relative to `Path(__file__).resolve().parents[2]`, clear assertion messages. Seven test functions validate:

1. **test_archive_readme_exists** — `archive/v1/README.md` contains ADR-0014 reference, all 5 v1 script names, and 2026-05-11 retirement date
2. **test_purge_checklist_exists** — `docs/V1_PURGE_CHECKLIST.md` contains `/usr/local/bin/` paths and sign-off section
3. **test_postmortem_template_exists** — `docs/MIGRATION_POSTMORTEM_TEMPLATE.md` contains MTTR, Lessons, and Sign-off sections
4. **test_adr_readme_has_0014** — `docs/adr/README.md` contains ADR-0014 entry with `0014-v1-retired-pivot` filename
5. **test_docs_readme_no_stale_v1** — `docs/README.md` has no "scripts in the parent directory" and does reference `archive/v1`
6. **test_docs_readme_has_all_adrs** — `docs/README.md` lists ADR-0008 through ADR-0014
7. **test_no_v1_as_active_in_docs** — regex sweep across all `docs/*.md` for v1-as-active patterns returns zero violations

The initial verification failure was caused by bare `pytest` not being on PATH — the worktree's `.venv` needed `uv sync --extra dev` plus runtime deps (pydantic, pyyaml, prometheus-client, httpx) that are in `packaging/requirements.lock` but not in `pyproject.toml`'s `dependencies` array. After installing, all tests pass.

## Verification

Ran pytest on the new test file (7/7 passed), full unit suite (1008 passed, 90 skipped, 0 failures), mypy --strict (no issues), and ruff check (clean after fixing one f-string lint).

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `uv run pytest tests/unit/test_v1_decommission.py -v` | 0 | pass — 7/7 tests passed | 290ms |
| 2 | `uv run pytest tests/unit/ -q --tb=short` | 0 | pass — 1008 passed, 90 skipped, 0 failures | 17500ms |
| 3 | `uv run mypy --strict tests/unit/test_v1_decommission.py` | 0 | pass — no issues found | 3000ms |
| 4 | `uv run ruff check tests/unit/test_v1_decommission.py` | 0 | pass — all checks passed | 200ms |

## Deviations

none

## Known Issues

pyproject.toml dependencies array is empty — runtime deps (pydantic, httpx, etc.) are only in packaging/requirements.lock, requiring manual uv pip install for the worktree .venv. This is a pre-existing project structure issue, not introduced by this task.

## Files Created/Modified

- `tests/unit/test_v1_decommission.py`
