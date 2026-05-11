---
phase: 5
slug: bench-field-shadow
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-11
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + pytest-asyncio (mode=auto) + hypothesis |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `pytest tests/unit/ -x --ff` |
| **Full suite command** | `pytest tests/ -v --ignore=tests/replay --ignore=tests/hil` |
| **Estimated runtime** | ~30 seconds (dev-laptop target, M7) |

---

## Sampling Rate

- **After every task commit:** Run quick command on touched modules
- **After every plan wave:** Run full suite
- **Before `/gsd-verify-work`:** Full suite must be green + ruff check + mypy --strict
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

> Populated by planner — one row per task with `type: execute`. Plans not yet drafted; planner fills this from PLAN.md tasks. Phase 5 is a delivery/shadow-validation phase, so most "tests" are integration checks against fakes (`FixtureRunner`, `_InventoryFromFile`, `_NoZaoTailer`) rather than new unit tests.

| Task ID | Plan | Wave | Source decision | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-----------------|-----------|-------------------|-------------|--------|
| 5-01-01 | 01 | 1 | X-02 (dms_get_revision verb) | unit | `pytest tests/unit/qmi/test_wrapper_dms_get_revision.py -x` | ❌ W0 | ⬜ pending |
| 5-01-02 | 01 | 1 | X-02 (per-libqmi fixture tree) | unit | `pytest tests/unit/qmi/test_wrapper_dms_get_revision.py -x` | ❌ W0 | ⬜ pending |
| 5-02-01 | 02 | 1 | Q3 (libqmi + Zao SDK version helpers) | unit | `pytest tests/unit/qmi/test_version.py -x` | ❌ W0 | ⬜ pending |
| 5-03-01 | 03 | 2 | X-01 (capture-fleet-fixture CLI) | unit | `pytest tests/unit/cli/test_capture_fleet_fixture.py -x` | ❌ W0 | ⬜ pending |
| 5-03-02 | 03 | 2 | X-02 (fleet fixture round-trip) | integration | `pytest tests/integration/test_fleet_fixture_roundtrip.py -x` | ❌ W0 | ⬜ pending |
| 5-04-01 | 04 | 2 | X-03 (preflight_check_known_fleet_triple) | unit | `pytest tests/unit/daemon/test_preflight_triple.py -x` | ❌ W0 | ⬜ pending |
| 5-04-02 | 04 | 2 | X-03 (preflight integration in daemon startup) | integration | `pytest tests/integration/test_daemon_preflight_triple.py -x` | ❌ W0 | ⬜ pending |
| 5-05-01 | 05 | 2 | S-01 #2 (audit_soak_zao tool) | unit | `pytest tests/unit/tools/test_audit_soak_zao.py -x` | ❌ W0 | ⬜ pending |
| 5-05-02 | 05 | 2 | S-01 #3 (audit_soak_exhausted tool) | unit | `pytest tests/unit/tools/test_audit_soak_exhausted.py -x` | ❌ W0 | ⬜ pending |
| 5-06-01 | 06 | 1 | X-03 (.deb known-fleet install) | integration | `dpkg-deb --contents dist/*.deb \| grep known-fleet` | ❌ W0 | ⬜ pending |
| 5-07-01 | 07 | 3 | SIGNOFF template + SOAK_RUNBOOK author | manual | n/a — operator doc | n/a | ⬜ pending |
| 5-08-01 | 08 | 4 | R-01 day-1 trace pull (operator) | manual | LFS PR merged | n/a | ⬜ pending |
| 5-09-01 | 09 | 5 | R-02 replay-harness one-shot at exit | manual | `pytest tests/replay/test_v1_agreement.py -v` | ✅ existing | ⬜ pending |

*Plan/task IDs above are the planner's anticipated decomposition; the planner re-numbers as needed and updates this table during PLAN.md creation.*

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/qmi/test_wrapper_dms_get_revision.py` — stubs for `QmiWrapper.dms_get_revision` (X-02)
- [ ] `tests/unit/qmi/test_version.py` — stubs for libqmi + Zao SDK version helpers (Q3)
- [ ] `tests/unit/cli/test_capture_fleet_fixture.py` — stubs for `ctl capture-fleet-fixture` (X-01)
- [ ] `tests/integration/test_fleet_fixture_roundtrip.py` — stub for capture→parse round-trip (X-02)
- [ ] `tests/unit/daemon/test_preflight_triple.py` — stubs for `preflight_check_known_fleet_triple` (X-03)
- [ ] `tests/integration/test_daemon_preflight_triple.py` — stub for daemon-startup integration (X-03)
- [ ] `tests/unit/tools/test_audit_soak_zao.py` — stub for "no action on Zao-active line" detection (S-01 #2)
- [ ] `tests/unit/tools/test_audit_soak_exhausted.py` — stub for "unexplained Exhausted" detection (S-01 #3)
- [ ] `tests/fixtures/qmicli/dms_get_revision/<libqmi-version>/` — per-libqmi-version fixture tree for the new verb (mirrors Plan 02-02's pattern)
- [ ] `tests/fixtures/fleet/<box-id>/` — root for captured fleet fixtures; per-box subdirs added during X-04 capture sweep

*Framework already installed (pyproject.toml, conftest.py). No framework install needed.*

---

## Manual-Only Verifications

| Behavior | Source decision | Why Manual | Test Instructions |
|----------|-----------------|------------|-------------------|
| Bench Jetson 1-week clean soak | S-01, S-02 | Real-hardware time-bound observation; cannot be synthesized | Operator follows SOAK_RUNBOOK.md daily checks for 7 consecutive days; gates: 0 daemon crashes, 0 "act on Zao-active", 0 unexplained Exhausted (F-04 budget: 1 minor/week). |
| Field-box 2-week clean soak | S-01, S-02 | Real-hardware time-bound observation on customer infrastructure | Operator follows SOAK_RUNBOOK.md daily checks for 14 consecutive days; same gates as bench week. |
| R-01 day-1 trace pull | R-01 | Requires physical access to (now-decommissioned) v1 boxes for log archive | On-site engineer runs `tools/pull_replay_traces.py` against archived `/var/log/spark-modem-watchdog/`; opens single LFS PR updating `tests/fixtures/replay/v1-30d/`. |
| R-02 replay-harness one-shot at exit | R-02 | Manually triggered, not on commit-CI or scheduled cron | Engineer runs `pytest tests/replay/test_v1_agreement.py -v` against freshly-pulled bundle on dev laptop; commits resulting JSON summary to phase dir; gate ≥0.95 fault-cycle agreement. |
| X-04 fleet fixture capture sweep | X-04 | Requires physical access window to each fleet box | On-site engineer runs `spark-modem ctl capture-fleet-fixture --out=tests/fixtures/fleet/<box-id>/` on each box during Phase 6 prep; commits one PR per box, batched into Phase 6 prerequisite PR. |
| F-02 bench HIL nightly observation | F-02 | The HIL nightly already exists (Plan 04-06); Phase 5 only observes results | Engineer reviews `.github/workflows/hil.yml` nightly run results during bench week; failures count toward F-04 budget. |
| SIGNOFF.md authoring + commit | S-04 | Free-text rationale section + checklist by the on-site engineer | Engineer fills `.planning/phases/05-bench-field-shadow/SIGNOFF.md` checklist using the template Plan 07 ships; attaches `replay-summary-phase5-exit.json` from R-02; commits before Phase 6 PR. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies (planner fills per-task verify blocks)
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (test files above)
- [ ] No watch-mode flags (CI parity: `pytest -x`, not `pytest-watch`)
- [ ] Feedback latency < 30s (M7 dev-laptop target)
- [ ] Manual-only verifications are explicit (real-hardware time-bound observations cannot be automated; SOAK_RUNBOOK.md is the authoritative substrate)
- [ ] `nyquist_compliant: true` set in frontmatter after planner finalizes per-task verify

**Approval:** pending
