---
id: T04
parent: S11
milestone: M001
key_files:
  - tools/validate_cutover.py
key_decisions:
  - Early-exit after service_active hard failure — skip remaining checks if daemon is not running
  - HMAC path resolution mirrors Settings.resolve_hmac_secret_path() logic (CREDENTIALS_DIRECTORY → /etc fallback) without importing from spark_modem
  - Carrier-table SHA check is skip-on-None rather than fail-on-None — fleet SHA may not be known at initial cutover
  - events_growing uses 5-second sample delay (blocking) — acceptable for a one-shot validation tool
duration: 
verification_result: passed
completed_at: 2026-05-19T09:18:30.709Z
blocker_discovered: false
---

# T04: Created tools/validate_cutover.py — standalone post-cutover validation script with 7 checks, structured JSON output, and exit-code-based pass/fail

**Created tools/validate_cutover.py — standalone post-cutover validation script with 7 checks, structured JSON output, and exit-code-based pass/fail**

## What Happened

Created `tools/validate_cutover.py` following the `audit_soak_zao.py` pattern (argparse, structured JSON output, exit-code semantics). The script runs on target boxes after .deb install + service start, using only subprocess calls to `spark-modem` CLI and direct file/socket reads — no imports from `spark_modem`.

Seven checks implemented, ordered by criticality:
1. **service_active** (hard): `systemctl is-active spark-modem-watchdog.service` == "active"
2. **modem_status** (hard): `spark-modem status --json` — all 4 modems present, none exhausted
3. **prometheus_metrics** (soft): Unix socket scrape of `/run/spark-modem-watchdog/metrics.sock` — expects `modem_state_value` lines for all 4 modems
4. **status_freshness** (hard): `status.json` mtime < 2× cycle interval (default 60s)
5. **hmac_secret** (soft): HMAC secret file exists at the correct path (respects `CREDENTIALS_DIRECTORY` for systemd 247+, falls back to `/etc/spark-modem-watchdog/hmac-secret`), is non-empty, and does not match the placeholder sentinel
6. **carrier_table_sha** (soft): `carrier_table_sha256` in `status.json` matches `--expected-carrier-sha` if provided; skipped if not
7. **events_growing** (soft): `events.jsonl` size increases over a 5-second sample window

Exit codes: 0 = all green, 1 = soft failure only, 2 = hard failure (daemon not running or modem unhealthy). Early-exit after check 1 fails (no point checking modem status if service is down).

Constants extracted from source: HMAC placeholder sentinel matches `config_check.py`, HMAC path resolution mirrors `Settings.resolve_hmac_secret_path()`, metric name `modem_state_value` from `metrics_registry.py`, default paths from `Settings` defaults.

## Verification

Ran all three verification gates from the task plan:
1. `python tools/validate_cutover.py --help` — exits 0, prints usage
2. `uv run mypy --strict tools/validate_cutover.py` — "Success: no issues found in 1 source file"
3. `uv run ruff check tools/validate_cutover.py` — "All checks passed!"

Also verified `ruff format --check` passes after auto-formatting.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `python tools/validate_cutover.py --help` | 0 | pass | 500ms |
| 2 | `uv run mypy --strict tools/validate_cutover.py` | 0 | pass | 5000ms |
| 3 | `uv run ruff check tools/validate_cutover.py` | 0 | pass | 1000ms |
| 4 | `uv run ruff format --check tools/validate_cutover.py` | 0 | pass | 500ms |

## Deviations

None. Script implements all 7 checks from the task plan spec. Check numbering in the plan listed 7 items; the S11-RESEARCH §5 listed 8 (adding a known-fleet triple check), but the authoritative task plan specified 7 checks, which is what was implemented.

## Known Issues

None.

## Files Created/Modified

- `tools/validate_cutover.py`
