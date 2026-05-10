---
phase: 4
slug: destructive-actions-hil
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-10
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> See `04-RESEARCH.md` § "Validation Architecture" for the source-of-truth
> requirements → test map and per-plan sampling rates. This file is the
> tracking artifact updated by the planner and executor as work progresses.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (mode=auto) + hypothesis |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` |
| **Quick run command** | `pytest -m "unit and not linux_only and not hil" -x` |
| **Per-plan suite** | `pytest tests/unit/policy/ tests/unit/actions/ -ra` |
| **Full suite (regular CI)** | `pytest -m "unit or integration" -ra` |
| **HIL suite** | `pytest -m hil tests/hil/ -ra --tb=short` |
| **Estimated runtime** | ~1-2s quick · ~17-25s full · ≤90 min HIL |

---

## Sampling Rate

- **After every task commit:** Run `pytest -m "unit and not linux_only and not hil" -x`
- **After every plan wave:** Run `pytest -m "unit or integration" -ra`
- **Before `/gsd-verify-work`:** Full suite green + HIL nightly green + replay-harness ≥95%
- **Max feedback latency:** ~30 seconds (M7 budget)

---

## Per-Task Verification Map

> Populated by gsd-planner during plan creation. Each task in each PLAN.md
> contributes one or more rows here. See 04-RESEARCH.md § "Phase Requirements
> → Test Map" for the canonical FR-23 / FR-24 / FR-27 coverage matrix.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _pending planner population_ | | | | | | | | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

> Test files that must exist before any plan can claim its REQ-IDs as tested.
> See 04-RESEARCH.md § "Wave 0 Gaps" for the full list with REQ-ID mapping.

- [ ] `tests/unit/policy/test_ladder.py` — FR-22 / FR-23 / FR-24 ladder progression
- [ ] `tests/unit/policy/test_engine_driver_reset.py` — FR-24 eligibility predicate boundary
- [ ] `tests/unit/actions/test_modem_reset.py` — FR-23 / FR-27 modem_reset
- [ ] `tests/unit/actions/test_usb_reset.py` — FR-23 / FR-27 / A-06 Sierra-bootloader
- [ ] `tests/unit/actions/test_driver_reset.py` — FR-24 / FR-27 / A-03 modprobe stderr
- [ ] `tests/unit/sysfs/test_usb_unbind_rebind.py` — A-02 sysfs file-write semantics
- [ ] `tests/unit/cli/test_reset.py` — FR-27 CLI surface (`--target=parent-hub`) [extended; not created]
- [ ] `tests/unit/wire/test_action_skipped_event.py` — B-04 ActionSkipped + SkipReason
- [ ] `tests/property/test_destructive_idempotency.py` — SC#1 idempotency property
- [ ] `tests/hil/conftest.py` — bench-Jetson fixtures (linux_only + hil markers)
- [ ] `tests/hil/fault_inject.py` — fault-injection helpers (Plan 04-06)
- [ ] `tests/hil/scenarios/*.py` — 7 Phase-4 SC#4 scenarios + 4 Phase-3 piggyback scenarios + 1 destructive-actions end-to-end (Plan 04-07; total 12 HIL scenario files)
- [ ] `tools/pull_replay_traces.py` — LFS trace materialization (Plan 04-06)
- [ ] `tests/fixtures/replay/v1-30d/README.md` + `.gitattributes` — quarterly refresh runbook
- [ ] `.github/workflows/hil.yml` — nightly + workflow_dispatch (Plan 04-06)

*Wave 0 is complete when all the above exist with at least empty stub functions; checker validates.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Bench Jetson SIM-swap detection | FR-23 / FR-27 | Requires physical SIM removal/insertion on bench hardware | Power down bench Jetson, swap SIM in slot 0, power up, confirm `inventory_state` reflects new ICCID and SIM-swap event recorded in event log |
| WatchdogSec=90s actual-fire | FR-31 (Phase 3 piggyback) | Requires deliberately-wedged qmicli on bench Jetson + systemd kill observation | Run scripted fault: SIGSTOP qmicli child of daemon; wait 90s; observe `systemctl status` showing `Result: watchdog`; daemon restart logged |
| Real qmi_wwan reload as clean state transition | FR-24 (Phase 3 piggyback) | Driver reload behavior depends on real kernel + Zao + qmi-proxy interaction | HIL scenario `test_qmi_wwan_reload_clean_transition.py` automates the observation; manual review of state transitions in event log confirms no spurious destructive resets |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s (M7 budget)
- [ ] HIL suite ≤90 min (D-01 budget)
- [ ] Replay-harness 30-day agreement ≥95% gate green
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
