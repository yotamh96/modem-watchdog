---
status: partial
phase: 05-bench-field-shadow
source: [05-VERIFICATION.md]
started: 2026-05-11T09:47:34Z
updated: 2026-05-11T09:47:34Z
---

## Current Test

[awaiting human testing — 3-4 week multi-stage operator campaign]

## Tests

### 1. R-01 day-1 v1-trace pull → LFS PR
expected: tests/fixtures/replay/v1-30d/ refreshed via LFS PR; merge-commit SHA recorded for SIGNOFF.md 'Bundle source' field. No raw 18-22 digit runs survive outside `<redacted:[0-9a-f]{8}>` form; ≥30d coverage documented; PR merged BEFORE bench soak begins.
result: [pending]

### 2. Bench Jetson 1-week clean soak
expected: 0 daemon crashes (M6), 0 act-on-Zao-active (ADR-0003), 0 unexplained Exhausted (M4); F-04 budget ≤1 minor/week observed and dispositioned. Evidence saved under phase5-evidence/bench/day-{1..7}/. Daily checks per SOAK_RUNBOOK § 2 for 7 consecutive days.
result: [pending]

### 3. S-03 handoff gate (bench-week-end)
expected: phase5-evidence/bench/audit-zao.json + audit-exhausted.json both show violations==0 OR within budget. `tools/audit_soak_zao.py` + `tools/audit_soak_exhausted.py` both exit 0; daemon-crash count over bench window is 0; S-03 PASSED logged.
result: [pending]

### 4. Field box 2-week clean soak
expected: Same gates as bench week, measured over 14 days. F-01 honored — no synthetic injection on the field box (DO NOT run `tests/hil/fault_inject.py`). Natural-fault events recorded for informational purposes (F-03 no minimum). Evidence saved under phase5-evidence/field/day-{1..14}/.
result: [pending]

### 5. X-04 fleet-fixture capture sweep
expected: Operator runs `sudo spark-modem ctl capture-fleet-fixture --out=/tmp/fleet-fixture-<box-id>` on every Phase 6 cutover box (including bench + field) during physical-access window. `tests/fixtures/fleet/<box-id>/` contains triple.json + `qmi/<usb_path>/` tree for every box. PII redaction verified (no raw 18-22 digit runs); ADR-0009 usb_path-keyed subdirs (NOT cdc-wdmN).
result: [pending]

### 6. X-04 batched Phase-6-prereq PR merge
expected: All per-box fixtures committed in a single PR, reviewed, and merged BEFORE the Phase 6 entry PR opens. git log shows the X-04 batched PR merge SHA; tests/fixtures/fleet/ contains one subdir per cutover box; `.deb` rebuild ships them at `/etc/spark-modem-watchdog/known-fleet/<box-id>/`.
result: [pending]

### 7. R-02 replay-harness one-shot at Phase 5 exit
expected: `pytest tests/replay/test_v1_agreement.py -v --tb=short` against freshly-pulled v1-30d bundle (from item 1) achieves ≥0.95 fault-cycle agreement. `.planning/phases/05-bench-field-shadow/replay-summary-phase5-exit.json` committed with `fault_cycle_agreement ≥ 0.95`; pytest exits 0 (R-03 hard-fail threshold satisfied).
result: [pending]

### 8. SIGNOFF.md filled in by on-site engineer
expected: All template slots filled (header front-matter, S-01 Exit Gates table 3 rows × bench+field columns, R-02 row, S-01.1 informational metrics, F-04 violations log, X-04 fleet fixtures checklist, free-text rationale, Phase 6 entry approval). No `_engineer fills here_` placeholders remain except deliberate free-text section. All 4 Phase 6 entry approval boxes ticked (☒ or ✅).
result: [pending]

### 9. SIGNOFF.md + audit JSONs + replay-summary committed in one PR
expected: Phase 6 entry PR merged; merge-commit SHA recorded; Phase 5 is COMPLETE and `/gsd-plan-phase 6` can begin. Reviewer enforces that all four approval boxes are ticked AND X-04 batched PR has already merged.
result: [pending]

### 10. CR-01 fix BEFORE X-04 sweep
expected: `_RAW_QMICLI_PII_PATTERNS` in `src/spark_modem/cli/redact.py` extended to cover `IPv4 subnet mask: '...'` and `IPv4 gateway address: '...'`. Tests in `tests/unit/cli/test_redact_raw_qmicli.py` extended with assertions for both; `wds_get_current_settings.txt` capture path is exercised in `tests/unit/cli/ctl/test_capture_fleet_fixture.py`. Must merge BEFORE X-04 sweep (item 5) otherwise routable carrier-NAT gateway IPs leak into committed per-box fixtures.
result: [pending]

## Summary

total: 10
passed: 0
issues: 0
pending: 10
skipped: 0
blocked: 0

## Gaps
