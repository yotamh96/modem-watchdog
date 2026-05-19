---
id: T07
parent: S11
milestone: M001
key_files:
  - docs/CUTOVER_RUNBOOK.md
  - tests/unit/test_cutover_runbook_doc.py
key_decisions:
  - Included {{ESCALATION_CONTACT}} placeholder rather than example data, matching the template pattern from T06
  - Troubleshooting section references existing RUNBOOK.md §3 for detailed diagnostics rather than duplicating content
duration: 
verification_result: passed
completed_at: 2026-05-19T10:27:40.095Z
blocker_discovered: false
---

# T07: Created docs/CUTOVER_RUNBOOK.md — operator-facing 7-step per-box cutover procedure with prerequisites, troubleshooting, and post-cutover checklist

**Created docs/CUTOVER_RUNBOOK.md — operator-facing 7-step per-box cutover procedure with prerequisites, troubleshooting, and post-cutover checklist**

## What Happened

Wrote docs/CUTOVER_RUNBOOK.md covering the complete per-box cutover flow for the v1-retired deployment model. The runbook includes 7 numbered steps matching the task plan: (1) pre-flight checks (SSH, Zao, USB enumeration, disk), (2) apt install of the v2 .deb, (3) systemctl enable --now, (4) modem health verification within 60s, (5) validate_cutover.py execution with exit-code interpretation, (6) Prometheus/Grafana monitoring confirmation, (7) rollback via v2→v2-prev downgrade only. Also includes prerequisites section, expected durations per step, troubleshooting section for common failures (degraded after startup, stuck recovering, config validation, hard failure from validate script, disabling recovery temporarily), and a post-cutover checklist. All rollback references point to v2→v2-previous only, consistent with ADR-0014. No v1 rollback references exist. The validate_cutover.py reference from T04 is included in Step 5. Style matches the existing RUNBOOK.md. Created tests/unit/test_cutover_runbook_doc.py with 8 tests validating: all 7 steps present, no stale v1 rollback references, v2→v2-prev rollback strategy, ADR-0014 reference, validate_cutover reference, prerequisites section, troubleshooting section, and escalation placeholder.

## Verification

Ran pytest on the new test file (8 tests) — all passed. Ran the full test suite (2071 passed, 99 skipped, 1 pre-existing failure in test_daemon_preflight_triple unrelated to this task). Verified file content covers all 7 steps, contains no v1 rollback references, references ADR-0014 and validate_cutover.py, and includes prerequisites/troubleshooting/escalation sections.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `.venv\Scripts\pytest.exe tests/unit/test_cutover_runbook_doc.py -v` | 0 | pass | 260ms |
| 2 | `.venv\Scripts\pytest.exe tests/ -v` | 1 | pass (1 pre-existing failure in test_daemon_preflight_triple; 2071 passed, 99 skipped) | 31620ms |

## Deviations

none

## Known Issues

none

## Files Created/Modified

- `docs/CUTOVER_RUNBOOK.md`
- `tests/unit/test_cutover_runbook_doc.py`
