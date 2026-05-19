---
estimated_steps: 9
estimated_files: 1
skills_used: []
---

# T03: Post-cutover validation script

**Why:** No automated way exists to verify a box is healthy after .deb install + service start. Operators need a single command that checks daemon health, modem state, metrics scrape, and HMAC configuration.

**Do:**
1. Write `tools/validate_cutover.py` as a standalone script following the `tools/audit_soak_*.py` pattern (argparse, structured JSON output, sys.exit 0/1/2).
2. Checks: (a) `systemctl is-active spark-modem-watchdog.service` == active; (b) `spark-modem status --json` — all 4 modems present, none exhausted; (c) status.json exists and mtime < 2x cycle interval; (d) events.jsonl exists and is growing; (e) HMAC secret is not placeholder sentinel.
3. Exit codes: 0 = all green, 1 = soft failure (non-critical check failed), 2 = hard failure (daemon not running or modem unhealthy).
4. Must NOT import from `spark_modem` — uses subprocess calls to the installed CLI and direct file reads. This script runs on the target box at `/opt/spark-modem-watchdog/`, not from the dev tree.
5. Include `--json` flag for machine-readable output and `--help` with clear usage.
6. Pass mypy --strict and ruff check.

**Done-when:** `python tools/validate_cutover.py --help` exits 0. mypy --strict and ruff clean.

## Inputs

- `tools/audit_soak_exhausted.py`
- `tools/audit_soak_zao.py`
- `src/spark_modem/status_reporter/metrics_registry.py`

## Expected Output

- `tools/validate_cutover.py`

## Verification

uv run python tools/validate_cutover.py --help; uv run mypy --strict tools/validate_cutover.py; uv run ruff check tools/validate_cutover.py
