---
phase: 5
slug: bench-field-shadow
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-11
finalized: 2026-05-11
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

> Populated after planning. Phase 5 is a delivery/shadow-validation phase. Code tasks (Plans 01-06) have automated pytest verification. Operator-doc tasks (Plan 07) verify via static grep on the produced markdown. Manual-operator tasks (Plan 08) verify via committed-artifact state (markdown fills + JSON evidence + git log markers).

| Task ID  | Plan | Wave | Source decision  | Test Type   | Automated Command                                                                                  | File Exists | Status   |
|----------|------|------|------------------|-------------|----------------------------------------------------------------------------------------------------|-------------|----------|
| 5-01-01  | 01   | 1    | X-02             | unit        | `pytest tests/unit/qmi/parsers/test_get_revision.py tests/unit/qmi/test_wrapper_dms_get_revision.py -x -q` | ❌ W0       | ⬜ pending |
| 5-01-02  | 01   | 1    | X-02             | unit        | `pytest tests/unit/qmi/parsers/test_get_revision.py::test_parser_accepts_libqmi_1_32_fixture tests/unit/qmi/parsers/test_get_revision.py::test_fixture_tree_has_locked_set_of_libqmi_versions -x -q` | ❌ W0       | ⬜ pending |
| 5-02-01  | 02   | 1    | X-03 / Q3        | unit        | `pytest tests/unit/qmi/test_version.py -x -q`                                                       | ❌ W0       | ⬜ pending |
| 5-02-02  | 02   | 1    | X-03 / Q3        | unit        | `pytest tests/unit/zao_log/test_version.py -x -q`                                                   | ❌ W0       | ⬜ pending |
| 5-02-03  | 02   | 1    | X-02 + X-03      | unit        | `pytest tests/unit/qmi/test_version.py -x -q`                                                       | ❌ W0       | ⬜ pending |
| 5-03-01  | 03   | 2    | X-02 (PII)       | unit        | `pytest tests/unit/cli/test_redact_raw_qmicli.py -x -q`                                             | ❌ W0       | ⬜ pending |
| 5-03-02  | 03   | 2    | X-01 + X-02      | unit        | `pytest tests/unit/cli/ctl/test_capture_fleet_fixture.py -x -q`                                     | ❌ W0       | ⬜ pending |
| 5-03-03  | 03   | 2    | X-02             | integration | `pytest tests/integration/test_fleet_fixture_roundtrip.py -x -q`                                    | ❌ W0       | ⬜ pending |
| 5-04-01  | 04   | 2    | X-03             | unit        | `pytest tests/unit/daemon/test_preflight_triple.py -x -q`                                           | ❌ W0       | ⬜ pending |
| 5-04-02  | 04   | 2    | X-03             | integration | `pytest tests/integration/test_daemon_preflight_triple.py -x -q`                                    | ❌ W0       | ⬜ pending |
| 5-05-01  | 05   | 2    | S-01 #2          | unit        | `pytest tests/unit/tools/test_audit_soak_zao.py -x -q`                                              | ❌ W0       | ⬜ pending |
| 5-05-02  | 05   | 2    | S-01 #3 / M4     | unit        | `pytest tests/unit/tools/test_audit_soak_exhausted.py -x -q`                                        | ❌ W0       | ⬜ pending |
| 5-06-01  | 06   | 3    | X-03             | integration | `pytest tests/integration/test_deb_ships_known_fleet.py -x -q`                                      | ❌ W0       | ⬜ pending |
| 5-07-01  | 07   | 4    | S-04             | static-doc  | `test -f .planning/phases/05-bench-field-shadow/SIGNOFF.md && grep -c "S-01 Exit Gates\|R-02 Replay-harness gate\|F-04 Violations log" .planning/phases/05-bench-field-shadow/SIGNOFF.md` | n/a (doc)   | ⬜ pending |
| 5-07-02  | 07   | 4    | S-02 / F-04      | static-doc  | `test -f .planning/phases/05-bench-field-shadow/SOAK_RUNBOOK.md && grep -c "modem_state_value" .planning/phases/05-bench-field-shadow/SOAK_RUNBOOK.md && ! grep -q 'modem_state\{state=' .planning/phases/05-bench-field-shadow/SOAK_RUNBOOK.md` | n/a (doc)   | ⬜ pending |
| 5-07-03  | 07   | 4    | Q9               | static-doc  | `grep -c "SOAK_RUNBOOK.md" docs/RUNBOOK.md` (expect 1)                                              | n/a (doc)   | ⬜ pending |
| 5-08-01  | 08   | 5    | R-01             | manual      | `git log --oneline tests/fixtures/replay/v1-30d/ \| head -1 \| grep -i "phase.5.*R-01"`             | n/a (op)    | ⬜ pending |
| 5-08-02  | 08   | 5    | S-02 + S-03      | manual      | operator-attested in SIGNOFF.md S-01 Exit Gates table — bench column                                 | n/a (op)    | ⬜ pending |
| 5-08-03  | 08   | 5    | S-02             | manual      | operator-attested in SIGNOFF.md S-01 Exit Gates table — field column                                 | n/a (op)    | ⬜ pending |
| 5-08-04  | 08   | 5    | X-04             | manual      | `find tests/fixtures/fleet/ -name 'triple.json' \| wc -l` >= number of fleet boxes                  | n/a (op)    | ⬜ pending |
| 5-08-05  | 08   | 5    | R-02             | manual      | `python -c "import json; d=json.load(open('.planning/phases/05-bench-field-shadow/replay-summary-phase5-exit.json')); assert d.get('fault_cycle_agreement', 0) >= 0.95"` | n/a (op)    | ⬜ pending |
| 5-08-06  | 08   | 5    | S-04             | manual      | `git log --oneline .planning/phases/05-bench-field-shadow/SIGNOFF.md \| head -1 \| grep "phase 5: SIGNOFF\|Phase 6 entry"` | n/a (op)    | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

All Wave 1 test files (Plans 01, 02) and Wave 2 test files (Plans 03, 04, 05) are NEW; each plan creates its own test scaffolding inside the same task that writes the production code. The pattern (TDD per `tdd="true"` on every code task) means Wave 0 is satisfied incrementally as plans execute, not as a separate pre-wave step.

Explicitly needed Wave 0 fixture roots that do NOT come from plan tasks (already exist via earlier phases):

- [x] `tests/fixtures/qmicli/get_operating_mode/1.30/` — Phase 2 baseline
- [x] `tests/fixtures/qmicli/get_signal/` etc. — Phase 2 baseline
- [x] `tests/fixtures/zao_log/` — Phase 2 baseline
- [x] `tests/fixtures/replay/v1-30d/` — Phase 4 placeholder (LFS); Phase 5 Plan 08 refreshes it via R-01

New fixture roots created by plan tasks:

- [ ] `tests/fixtures/qmicli/get_revision/<libqmi>/standard.txt` — Plan 01
- [ ] `tests/fixtures/qmicli/version/<libqmi>/standard.txt` — Plan 02
- [ ] `tests/fixtures/zao_log/version/banner_{present,no}.txt` — Plan 02
- [ ] `tests/fixtures/qmicli/uim_get_card_status/1.30/with_iccid.txt` — Plan 03
- [ ] `tests/fixtures/fleet/_test/triple.json` — Plan 03 example fixture
- [ ] `tests/unit/tools/__init__.py` — new test root, Plan 05

*Framework already installed (pyproject.toml, conftest.py). No framework install needed.*

---

## Manual-Only Verifications

| Behavior | Source decision | Why Manual | Test Instructions |
|----------|-----------------|------------|-------------------|
| Bench Jetson 1-week clean soak | S-01, S-02 | Real-hardware time-bound observation; cannot be synthesized | Operator follows SOAK_RUNBOOK.md daily checks for 7 consecutive days; gates: 0 daemon crashes (M6), 0 act-on-Zao-active (ADR-0003), 0 unexplained Exhausted (M4); F-04 budget: 1 minor/week. Plan 08 Task 2. |
| Field-box 2-week clean soak | S-01, S-02 | Real-hardware time-bound observation on customer infrastructure | Operator follows SOAK_RUNBOOK.md daily checks for 14 consecutive days; same gates as bench week. NO synthetic injection (F-01). Plan 08 Task 3. |
| R-01 day-1 trace pull | R-01 | Requires physical access to (now-decommissioned) v1 boxes for log archive | On-site engineer runs `tools/pull_replay_traces.py` against archived `/var/log/spark-modem-watchdog/`; opens single LFS PR updating `tests/fixtures/replay/v1-30d/`. Plan 08 Task 1. |
| R-02 replay-harness one-shot at exit | R-02 | Manually triggered at Phase 5 exit (not in commit-CI / nightly per CONTEXT) | Engineer runs `pytest tests/replay/test_v1_agreement.py -v` against the R-01 freshly-pulled bundle on dev laptop; commits `replay-summary-phase5-exit.json`; gate ≥0.95. Plan 08 Task 5. |
| X-04 fleet fixture capture sweep | X-04 | Requires physical access window to each fleet box | On-site engineer runs `spark-modem ctl capture-fleet-fixture --out=tests/fixtures/fleet/<box-id>/` on each box; one PR per box → batched into a Phase 6 prerequisite PR. Plan 08 Task 4. |
| F-02 bench HIL nightly observation | F-02 | The HIL nightly already exists (Plan 04-06); Phase 5 only observes | Engineer reviews `.github/workflows/hil.yml` nightly run results during bench week; failures count toward F-04 budget. Embedded in Plan 08 Task 2. |
| SIGNOFF.md authoring + commit | S-04 | Free-text rationale + checklist by the on-site engineer | Engineer fills `.planning/phases/05-bench-field-shadow/SIGNOFF.md`; attaches replay-summary JSON + audit JSONs; commits in the Phase 6 entry PR. Plan 08 Task 6. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (planner filled per-task verify blocks; code plans 01-06 use pytest; doc plan 07 uses static grep; manual plan 08 uses committed-artifact state checks)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (code/doc plans all carry automated verify; the only non-automated tasks are the 6 manual operator tasks in Plan 08, which are unavoidably time-bound)
- [x] Wave 0 covers all MISSING references (the test files are created inside the same tasks that write production code, per `tdd="true"` discipline)
- [x] No watch-mode flags (CI parity: `pytest -x -q`, not `pytest-watch`)
- [x] Feedback latency < 30s (M7 dev-laptop target preserved; Plan 06 dpkg-deb check is the only longer integration step but it's optional/skipped on dev hosts)
- [x] Manual-only verifications are explicit (Plan 08 tasks are checkpoint:human-action with operator checklists; SOAK_RUNBOOK.md is the authoritative substrate; SIGNOFF.md is the audit artifact)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validation complete; ready for execution.
