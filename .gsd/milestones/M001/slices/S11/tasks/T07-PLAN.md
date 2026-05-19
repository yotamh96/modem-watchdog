# T07: Per-box cutover runbook

**Slice:** S11 — **Milestone:** M001

## Description

Write `docs/CUTOVER_RUNBOOK.md` — operator-facing step-by-step for the simplified v1-retired cutover flow on a single box.

Steps:
1. Pre-flight: verify box connectivity, check current daemon state (if any)
2. Install: `apt install spark-modem-watchdog` (v2 .deb from fleet apt repo)
3. Enable: `systemctl enable --now spark-modem-watchdog.service`
4. Verify: wait ≤60s, confirm all 4 modems reach Healthy via `spark-modem status`
5. Validate: run `tools/validate_cutover.py` — all checks green
6. Monitor: verify Prometheus scrape is flowing, check Grafana dashboard
7. Rollback (if needed): `apt install spark-modem-watchdog=<previous-version>` (v2→v2-prev only; no v1 rollback)

Include: prerequisites, expected durations, troubleshooting section for common failures, escalation contacts placeholder.

## Files

- `docs/CUTOVER_RUNBOOK.md`

## Verify

- File exists with all 7 steps covered
- No stale v1 references
- Rollback section references v2→v2-prev only (consistent with ADR-0014)
- References validate_cutover.py from T04

## Inputs

- T02 output (rewritten MIGRATION.md for consistency)
- T04 output (validate_cutover.py for reference in step 5)
- `docs/RUNBOOK.md` (existing steady-state runbook style reference)

## Expected Output

New docs/CUTOVER_RUNBOOK.md (~80 lines) with operator-facing step-by-step procedure.
