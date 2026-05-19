---
estimated_steps: 9
estimated_files: 5
skills_used: []
---

# T05: Cross-document consistency verification

**Why:** S11 touches 8+ documentation files. A final consistency pass catches cross-references that point at dead sections, metric names that don't match the registry, and stale ADR references.

**Do:**
1. Verify MIGRATION.md references ADR-0014 and FLEET_GATES.md correctly.
2. Verify CUTOVER_RUNBOOK.md references validate_cutover.py correctly.
3. Verify FLEET_GATES.md metric names are a subset of metrics_registry.py `_METRIC_NAMES` (plus `process_start_time_seconds`).
4. Verify no file in docs/ or .planning/ contains stale shadow/v1-active references: `99-shadow`, `compare_v1_v2`, `watchdog-v2.service`, `-v2/`, `v1 currently keeps`.
5. Verify existing unit tests still pass (`uv run pytest tests/unit/ -q`).
6. Verify validate_cutover.py passes mypy and ruff.

**Done-when:** All grep checks return 0 matches for stale patterns. Unit tests pass. mypy + ruff clean on validation script.

## Inputs

- `docs/MIGRATION.md`
- `docs/FLEET_GATES.md`
- `docs/CUTOVER_RUNBOOK.md`
- `docs/adr/0014-v1-retired-pivot.md`
- `tools/validate_cutover.py`
- `src/spark_modem/status_reporter/metrics_registry.py`

## Expected Output

- `docs/MIGRATION.md`
- `docs/FLEET_GATES.md`
- `docs/CUTOVER_RUNBOOK.md`
- `docs/adr/0014-v1-retired-pivot.md`
- `tools/validate_cutover.py`

## Verification

uv run pytest tests/unit/ -q --tb=short; uv run mypy --strict tools/validate_cutover.py; uv run ruff check tools/validate_cutover.py; Select-String -Pattern '99-shadow|compare_v1_v2|watchdog-v2\.service|v1 currently keeps' docs/*.md,.planning/PROJECT.md -Quiet; if ($?) { Write-Error 'Stale refs remain'; exit 1 } else { Write-Output 'All consistency checks passed' }
