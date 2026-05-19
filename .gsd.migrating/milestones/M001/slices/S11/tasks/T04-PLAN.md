# T04: Post-cutover validation script

**Slice:** S11 — **Milestone:** M001

## Description

Create `tools/validate_cutover.py` — standalone script run on each target box after .deb install + service start.

Checks (ordered by criticality):
1. `systemctl is-active spark-modem-watchdog.service` → active
2. `spark-modem status --json` → all 4 modems present, none exhausted
3. Prometheus UDS scrape (curl --unix-socket /run/spark-modem-watchdog/metrics.sock) → non-empty response with modem_state_value for all 4 modems
4. status.json exists and mtime < 2× cycle interval
5. HMAC secret is not the placeholder sentinel
6. Carrier-table SHA matches expected fleet value
7. events.jsonl is being written (size increasing over 2 samples)

Exit codes: 0 = all green, 1 = soft failure (non-critical check failed), 2 = hard failure (daemon not running or modem unhealthy).

Constraint: must NOT import from spark_modem — it runs on the target box where the daemon is installed, not from the dev tree. Use subprocess calls to spark-modem CLI and direct file/socket reads. Follow audit_soak_*.py pattern (argparse, structured JSON output).

## Files

- `tools/validate_cutover.py`

## Verify

- `python tools/validate_cutover.py --help` exits 0
- `uv run mypy --strict tools/validate_cutover.py` passes
- `uv run ruff check tools/validate_cutover.py` passes

## Inputs

- `tools/audit_soak_zao.py` (pattern reference)
- `src/spark_modem/status_reporter/metrics_registry.py` (metric names to verify)
- `.gsd/milestones/M001/slices/S11/S11-RESEARCH.md` §5 (design spec)

## Expected Output

New standalone Python script (~150 LOC) with argparse, structured JSON output, exit-code-based pass/fail.
