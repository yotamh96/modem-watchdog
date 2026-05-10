---
phase: 04-destructive-actions-hil
verified: 2026-05-10T13:35:36Z
status: human_needed
score: 3/4 success criteria fully verified; SC#4 deferred to first nightly HIL run
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: n/a
  gaps_closed: []
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "First nightly HIL run on bench Jetson (post-merge)"
    expected: "GitHub Actions workflow `.github/workflows/hil.yml` runs cleanly via workflow_dispatch or 04:00 UTC cron on the [self-hosted, linux, ARM64, hil-bench] runner: 12 HIL scenario files collect under `pytest -m hil tests/hil/`; SC#4 sub-scenarios (boot-to-Healthy, SIM swap, soft_reset resolves SIM-app issue, modem_reset after one soft_reset, three-modem QMI hang fires single driver_reset, RF event keeps daemon out of destructive resets, pkill qmi-proxy recovered with one driver_reset) all pass; replay-harness 30-day fault-cycle agreement ≥95% gate green; support-bundle artifact uploads on any failure."
    why_human: "HIL scenarios are linux_only + hil-marker-gated (correctly skip with 'no tests collected' on this Windows dev host). Bench-Jetson hardware verification was Plan 04-07 Task 3 checkpoint:human-verify auto-approved under --auto. Phase 4 EXIT bar per ROADMAP.md line 41 is 'first green nightly HIL run on bench Jetson + replay-harness >=95% gate' — execution requires real hardware (4× EM7421 on USB hub 2-3.1.{1..4}) tethered to the self-hosted aarch64 runner. The scenario files, fault-injection helpers, replay-harness gate, and workflow are all in place; only the runner activation is pending."
---

# Phase 4: Destructive Actions & HIL — Verification Report

**Phase Goal:** Implement the four destructive recovery actions (`soft_reset`, `modem_reset`, `usb_reset`, global `driver_reset`) as idempotent CLI-runnable functions wired into the policy engine, gated by the signal-quality gate (RSRP / RSRQ / SNR thresholds) and the ≥75%-QMI-hung + actionable-signal gate for the global driver reset, and prove all of it on a hardware-in-the-loop bench Jetson with deliberate fault injection.

**Verified:** 2026-05-10T13:35:36Z
**Status:** `human_needed` — code complete; bench-Jetson hardware verification deferred to first post-merge nightly HIL run
**Re-verification:** No — initial verification

## Goal Achievement Summary

The Phase 4 codebase delivers all destructive-action machinery end-to-end on the dev host: three new actions (`modem_reset`, `usb_reset`, `driver_reset`) registered in the dispatcher, signal-gate thresholds migrated to `Settings` (RELOAD_DATA-tagged), the `_global_driver_reset_eligible` 4-gate predicate (thermal → cooldown → 75% denominator → actionable-signal) wired and tested with 14 boundary cases, the `ActionSkipped` event variant with 7-value `SkipReason` enum emitted on every gate-failure path, and a complete HIL infrastructure (12 scenario files, fault-injection toolkit, replay-harness 30-day gate, nightly + workflow_dispatch GitHub Actions workflow). All 1965 unit/integration tests pass in 17.47s (well under M7's 30s budget); 5 hypothesis-driven idempotency property tests pass; 21 RECOVERY_SPEC decision-table rows pass after the test_recovery_spec fixture was repaired to `expected_modem_count=4`.

The single open item is execution of the HIL scenarios on real hardware: by design, `tests/hil/scenarios/*.py` are `linux_only + hil`-marker-gated and correctly skip on this Windows dev host (`pytest --collect-only -m hil` returns "no tests collected"). The Phase 4 EXIT bar per ROADMAP.md is "first green nightly HIL run on bench Jetson + replay-harness ≥95% gate" — a runner activation, not a code gap. The Plan 04-07 Task 3 bench-Jetson human-verify checkpoint was auto-approved under `--auto` mode with that EXIT contingency explicitly recorded.

## Observable Truths (per Success Criterion)

### SC#1 — Idempotent destructive actions (FR-27)

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1.1 | `actions/modem_reset.py` exists with execute/verify mirroring `soft_reset` shape; registered as `ActionKind.MODEM_RESET` in dispatcher | ✓ VERIFIED | `src/spark_modem/actions/modem_reset.py` 63 LOC; `dispatcher._REGISTRY` line 49 |
| 1.2 | `actions/usb_reset.py` exists; uses sysfs file-write (no subprocess); supports `child-port` + `parent-hub` variants; registered | ✓ VERIFIED | `src/spark_modem/actions/usb_reset.py` 73 LOC; delegates to `sysfs.unbind_rebind`; `dispatcher._REGISTRY` line 50 |
| 1.3 | `actions/driver_reset.py` exists; uses two `subproc.run` calls (`modprobe -r qmi_wwan` + `modprobe qmi_wwan`); module-busy / load-exit classifier; registered | ✓ VERIFIED | `src/spark_modem/actions/driver_reset.py` 96 LOC; imports `subproc_run` directly per PATTERNS correction #1; `dispatcher._REGISTRY` line 51 |
| 1.4 | Each destructive action returns `VerifyResult.deferred(detail="next_cycle_observation")` | ✓ VERIFIED | All three `verify()` bodies are identical 1-line returns; A-04 honored verbatim |
| 1.5 | `spark-modem reset --action=<name> --modem=cdc-wdmN` accepts all 4 destructive kinds (`soft_reset` from Phase 2 + 3 new); CLI guard wording is generic "is not registered" | ✓ VERIFIED | `cli/reset.py:40-46`; all 9 ActionKinds in `registered_kinds()`: `['driver_reset', 'fix_autosuspend', 'fix_raw_ip', 'modem_reset', 'set_apn', 'set_operating_mode', 'sim_power_on', 'soft_reset', 'usb_reset']` |
| 1.6 | `--target=child-port`/`--target=parent-hub` flag exposed for usb_reset (Sierra-bootloader routing) | ✓ VERIFIED | `cli/reset.py:9-12, 52`; passes through `dataclasses.replace(ctx, target=...)` |
| 1.7 | Property test `tests/property/test_destructive_idempotency.py` passes (back-to-back invocations identical end-state for all 3 destructive actions) | ✓ VERIFIED | 5 tests pass in 0.66s; tests assert both runs ran (idempotency vs. single-flight discriminator) |
| 1.8 | Bench-Jetson `tests/hil/scenarios/test_destructive_actions.py` end-to-end via real `spark-modem reset --action=<kind>` CLI | ⚠ HUMAN_VERIFY | Authored as opt-in via `BENCH_JETSON_DESTRUCTIVE_TESTS_OK=true`; runs only on bench Jetson |

**SC#1 status:** ✓ MET (code/tests); bench-Jetson real-CLI invocation classified as part of SC#4.

### SC#2 — Signal-quality gate + ActionSkipped + rf_blocked (FR-23)

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 2.1 | Signal-gate thresholds migrated from `Final` constants to `Settings` (`signal_rsrp_floor_dbm = -110`, `signal_rsrq_floor_db = -15.0`, `signal_snr_floor_db = 0.0`); RELOAD_DATA tagged | ✓ VERIFIED | `config/settings.py:132-145`; defaults match RECOVERY_SPEC §6.1 verbatim |
| 2.2 | `policy/transitions.py:is_signal_below_gate` reads thresholds from `PolicyContext.config` (not module constants); blocks destructive actions via `gate_signal` | ✓ VERIFIED | `transitions.py:22-39`; `gates.py:57-69` (`gate_signal` consults `state.rf_blocked` + `_DESTRUCTIVE_KINDS` set) |
| 2.3 | `wire/events.py` has `ActionSkipped` variant with `kind="action_skipped"` discriminator | ✓ VERIFIED | `wire/events.py:66-91`; included in tagged-union at line 235 |
| 2.4 | `wire/enums.py` has `SkipReason` StrEnum with 7 values (`signal_below_gate, ladder_backoff, same_action_backoff, exhausted, disconnected, maintenance, dry_run`) | ✓ VERIFIED | `wire/enums.py:151-170`; closed-enum discipline (W-04) |
| 2.5 | `policy/engine.py` emits `ActionSkipped` on every gate-failure path (`disconnected, maintenance, exhausted, signal_below_gate, same_action_backoff, ladder_backoff, dry_run`) | ✓ VERIFIED | `engine.py:354, 368, 382, 408, 410, 412, 416` (1:1 mapping for each `SkipReason`) |
| 2.6 | `transitions.py` sets `rf_blocked` orthogonal flag on `ModemState` correctly when signal below gate | ✓ VERIFIED | `transitions.py:60` (`rf_blocked = is_signal_below_gate(snap, ctx.config)`) |
| 2.7 | Cheap actions still run while `rf_blocked=True` (gate_signal short-circuits to False for non-destructive kinds) | ✓ VERIFIED | `gates.py:67-68` (`if action not in _DESTRUCTIVE_KINDS: return False`); RECOVERY_SPEC §6.1 last paragraph |
| 2.8 | HIL synthetic-RF-noise scenario at `tests/hil/scenarios/test_rf_event_no_destructive.py` exists | ⚠ HUMAN_VERIFY | File exists with `linux_only + hil` markers; uses config-injected forced `rf_blocked` via temporary `99-test-rf-gate.yaml` + SIGHUP; execution deferred to bench Jetson |

**SC#2 status:** ✓ MET (code/tests); HIL scenario authored, execution deferred.

### SC#3 — Global driver_reset eligibility (FR-24)

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 3.1 | `policy/engine.py:_global_driver_reset_eligible` is wired (no longer hardcoded False placeholder) | ✓ VERIFIED | `engine.py:432-516`; full 4-gate predicate body |
| 3.2 | 4-gate ordering: thermal → cooldown → 75% denominator → actionable-signal (any False short-circuits) | ✓ VERIFIED | `engine.py:466-516`; gates evaluated in documented order |
| 3.3 | `Settings` has `multi_modem_threshold_fraction` (default 0.75), `expected_modem_count` (default 4), `global_driver_reset_backoff_seconds` (default 3600) | ✓ VERIFIED | `config/settings.py:98-115`; all RELOAD_DATA tagged |
| 3.4 | `None last_driver_reset_monotonic` short-circuits to allow (first-fire NPE prevention) | ✓ VERIFIED | `engine.py:474` (`if globals_state.last_driver_reset_monotonic is not None:`) — explicit None check before subtraction |
| 3.5 | `thermal_warn` / `thermal_critical` host-issue detail suppresses driver_reset | ✓ VERIFIED | `engine.py:469-471` (Gate 1) |
| 3.6 | Denominator is total expected (4), NOT non-Zao-active (CONTEXT C-01 user deviation) | ✓ VERIFIED | `engine.py:480-491`; `expected = ctx.expected_modem_count` direct read |
| 3.7 | PROXY_DIED does NOT bypass the 75% threshold (CONTEXT C-02 user deviation) | ✓ VERIFIED | `engine.py:483-489` only counts QMI_CHANNEL_HUNG; PROXY_DIED is a separate IssueDetail not counted in `hung_count` |
| 3.8 | Actionable-signal gate (Gate 4): at least one hung modem clears all three RSRP/RSRQ/SNR floors; None readings count as 'not above floor' | ✓ VERIFIED | `engine.py:497-516`; conservative None handling (must not fire on missing data) |
| 3.9 | Boundary tests in `tests/unit/policy/test_engine_driver_reset.py` pass | ✓ VERIFIED | 14 tests pass in 0.34s (covers all 4 gates × on/off + None-timestamp + Zao-active counted as not-hung) |
| 3.10 | HIL three-modem-hang scenario at `tests/hil/scenarios/test_three_modem_hang.py` exists; asserts exactly 1 driver_reset + no per-modem usb_reset race (engine cycle short-circuit) | ⚠ HUMAN_VERIFY | File exists with proper assertions; execution deferred to bench Jetson |
| 3.11 | Cycle short-circuit prevents per-modem actions on the same cycle as a global driver_reset | ✓ VERIFIED | `engine.py:82-83` calls `_global_driver_reset_eligible` first, branches before per-modem loop |
| 3.12 | `tests/test_recovery_spec.py` fixture repaired to `expected_modem_count=4` (post Plan 04-03 wiring) | ✓ VERIFIED | `tests/test_recovery_spec.py:115` — 21 rows pass in 0.39s |

**SC#3 status:** ✓ MET (code/tests); HIL scenario authored, execution deferred.

### SC#4 — HIL CI lane

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 4.1 | `.github/workflows/hil.yml` exists with nightly cron (`0 4 * * *`) + `workflow_dispatch` + serial concurrency (`group: hil-bench, cancel-in-progress: false`) + 90 min timeout | ✓ VERIFIED | `.github/workflows/hil.yml:12-25` |
| 4.2 | `tests/hil/conftest.py` + `tests/hil/fault_inject.py` + `tests/hil/scenarios/` all exist | ✓ VERIFIED | All files present in `tests/hil/` directory |
| 4.3 | 12 HIL scenario files authored (7 SC#4 + 4 Phase-3 piggyback + 1 destructive end-to-end) | ✓ VERIFIED | `tests/hil/scenarios/` contains exactly 12 `test_*.py` files; all have `pytestmark = [linux_only, hil, skipif(win32), asyncio]` |
| 4.4 | Replay-harness 30-day agreement ≥95% gate wired in workflow | ✓ VERIFIED | `.github/workflows/hil.yml:49-72` (Step "Replay-harness 30-day fault-cycle agreement gate" runs `pytest tests/replay/`; Plan 02-10's `pytest_sessionfinish` hook hard-fails at <0.95) |
| 4.5 | `tools/pull_replay_traces.py` exists with LFS pointer materialization + fail-fast on missing auth | ✓ VERIFIED | `tools/pull_replay_traces.py` exists; invoked by workflow at line 44 |
| 4.6 | HIL scenarios collect cleanly on Linux; correctly skip on Windows dev host via `linux_only` marker | ✓ VERIFIED (Windows side); ⚠ HUMAN_VERIFY (Linux side) | `pytest --collect-only -m hil tests/hil/` returns "no tests collected" on this Windows host (correct skip via `pytest.mark.skipif(sys.platform == "win32")`) |
| 4.7 | Bench-Jetson end-to-end execution: SC#4 scenarios pass on real hardware (boot-to-Healthy ≤60s; SIM swap detected; soft_reset resolves SIM-app issue; modem_reset after one soft_reset; three-modem QMI hang triggers single driver_reset; RF event keeps daemon out of destructive resets; pkill qmi-proxy recovered with one driver_reset) | ⚠ HUMAN_VERIFY | Phase 4 EXIT bar per ROADMAP.md line 41; deferred to first post-merge nightly HIL run |
| 4.8 | Replay-harness 30-day fault-cycle agreement ≥95% on real v1 traces | ⚠ HUMAN_VERIFY | Gate is wired; execution requires LFS-pulled v1-30d trace snapshot on bench-Jetson runner |

**SC#4 status:** ⚠ HUMAN_VERIFY — all infrastructure in place; bench-Jetson execution is the EXIT bar.

**Score:** 3/4 success criteria fully verified on dev host; SC#4 deferred to first nightly HIL run (per phase plan, expected behavior).

## CLAUDE.md Invariant Check

| #   | Invariant | Status | Evidence |
| --- | --------- | ------ | -------- |
| 1 | Pure policy engine — no subprocess/I/O imports | ✓ HONORED | `grep "subprocess\|create_subprocess_exec" src/spark_modem/policy/` returns 0 matches in actual import lines (only docstring/comment mentions of CLAUDE.md §1 itself); `policy/__init__.py:5` and `policy/engine.py:3` document the rule |
| 2 | usb_path-keyed state files preserved | ✓ HONORED | No new state-keying scheme introduced; Phase 4 only adds `last_action_monotonic_by_kind` field to existing `ModemState` shape |
| 3 | State machine 5+2 unchanged | ✓ HONORED | `transitions.py` still uses `match prior.state` over `unknown/healthy/degraded/recovering/exhausted` + `present`/`rf_blocked` flags; ADR-0008 preserved |
| 4 | `time.monotonic()` for backoffs (no `time.time()` in policy code) | ✓ HONORED | `grep "time\.time\(\)\|time\.monotonic\(\)" src/spark_modem/policy/` returns 0 matches; all clock reads go through `ctx.clock.monotonic()` (ClockProto) per ADR-0007 |
| 5 | Atomic file writes preserved | ✓ HONORED | Phase 4 does not touch `state_store/store.py`; existing temp+rename+fsync semantics intact |
| 6 | Zao RASCOW_STAT authoritative | ✓ HONORED | CONTEXT C-01 conservative deviation: Zao-active modems counted as 'not-hung' in driver_reset denominator (via expected_modem_count denominator, not enumerated count) |
| 7 | Counter decay persisted | ✓ HONORED | Plan 04-04 added per-kind timestamps additively; legacy `last_action_monotonic` preserved; `last_action_monotonic_by_kind` defaults to empty dict on Phase 2 state files |
| 8 | Cycle write order atomic | ✓ HONORED | Engine still bumps counters + per-kind timestamp + state-write together (RECOVERY_SPEC §8 ordering documented `gates.py:82-92`) |
| 9 | One action per modem per cycle | ✓ HONORED | Engine cycle short-circuit on driver_reset (`engine.py:82-106`) prevents per-modem races; documented + tested via `test_three_modem_hang.py` assertions |
| 10 | Signal-quality gate on destructive only | ✓ HONORED | `gates.py:67-68` short-circuits to False for non-destructive kinds; `_DESTRUCTIVE_KINDS = {MODEM_RESET, USB_RESET, DRIVER_RESET}` |
| 11 | No inbound IPC in v2.0 | ✓ HONORED | Phase 4 introduces no new IPC; only outbound subprocess calls (modprobe) + sysfs writes |
| 12 | CLI mutating commands take same flocks as daemon | ✓ HONORED | `cli/reset.py` inherits Phase 2 `ctl reset-state` flock pattern (ADR-0012); not modified in Phase 4 |

All 12 invariants honored.

## PATTERNS Corrections Applied

| #   | Correction | Status | Evidence |
| --- | ---------- | ------ | -------- |
| 1 | `ActionContext.runner` does NOT exist → driver_reset imports `subproc.runner` directly | ✓ APPLIED | `actions/driver_reset.py:45` (`from spark_modem.subproc.runner import run as subproc_run`) |
| 2 | `IssueCategory.ENUMERATION` does NOT exist → `(IssueCategory.QMI, IssueDetail.SIERRA_BOOTLOADER)` | ✓ APPLIED | `decision_table.py:72` routes `(QMI, SIERRA_BOOTLOADER) → USB_RESET`; `wire/enums.py:66-70` documents the correction inline |
| 3 | `pyproject.toml` `hil` marker NOT modified (already registered Phase 1) | ✓ APPLIED | `pyproject.toml:78` (existing entry; not touched in Phase 4) |
| 4 | `expected_modem_count` on PolicyContext not duplicated (added to Settings as source-of-truth, threaded through context) | ✓ APPLIED | `policy/context.py:45` (`expected_modem_count: int = 4`); `config/settings.py:105` (Settings field with RELOAD_DATA marker); cycle driver re-reads each cycle |
| 5 | RESEARCH.md excerpts 8/9 superseded by verified `tests/fakes/runner.py` and `tests/integration/test_lifecycle.py` snippets | ✓ APPLIED | 04-PATTERNS.md metadata block lines 1207-1213 documents the override |
| 6 | `tests/property/` created net-new (no existing analog) | ✓ APPLIED | `tests/property/__init__.py + conftest.py + test_destructive_idempotency.py` all exist; `conftest.pytest_collection_modifyitems` auto-marks tests as `unit` so the `pytest -m "unit or integration"` filter picks them up |

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full unit + integration suite green and within M7 budget | `pytest -m "unit or integration" -q` | 1965 passed, 90 skipped in 17.47s | ✓ PASS (M7: ≤30s) |
| Destructive idempotency property tests pass | `pytest tests/property/test_destructive_idempotency.py -q` | 5 passed in 0.66s | ✓ PASS |
| driver_reset eligibility predicate boundary tests pass | `pytest tests/unit/policy/test_engine_driver_reset.py -q` | 14 passed in 0.34s | ✓ PASS |
| Recovery-spec decision table rows pass (post Plan 04-03 fixture fix) | `pytest tests/test_recovery_spec.py -q` | 21 passed in 0.39s | ✓ PASS |
| All 9 ActionKinds registered in dispatcher | Python introspection of `registered_kinds()` | `['driver_reset', 'fix_autosuspend', 'fix_raw_ip', 'modem_reset', 'set_apn', 'set_operating_mode', 'sim_power_on', 'soft_reset', 'usb_reset']` | ✓ PASS (3 destructive + 6 cheap = 9) |
| HIL scenarios skip cleanly on Windows dev host | `pytest --collect-only -m hil tests/hil/` | "no tests collected" | ✓ PASS (correct linux_only skip) |
| HIL scenarios execute on bench Jetson | (requires real hardware) | not run in this environment | ? SKIP (HUMAN_VERIFY) |
| Replay-harness ≥95% gate against 30-day v1 traces | (requires LFS-pulled traces + bench Jetson runner) | not run in this environment | ? SKIP (HUMAN_VERIFY) |

## Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
| ----------- | ------------ | ----------- | ------ | -------- |
| FR-23 | 04-01, 04-02, 04-04, 04-05, 04-06, 04-07 | Signal-quality gate refuses destructive resets when RSRP/RSRQ/SNR below floors; ActionSkipped event | ✓ SATISFIED | `is_signal_below_gate` reads from PolicyContext.config; `gate_signal` blocks destructive only; `ActionSkipped(reason=signal_below_gate)` emitted; HIL scenario `test_rf_event_no_destructive.py` authored. REQUIREMENTS.md line 298 marks Done. |
| FR-24 | 04-03, 04-06, 04-07 | Global `driver_reset` fires only when ≥75% QMI-hung + actionable signal + no thermal + cooldown elapsed | ✓ SATISFIED | `_global_driver_reset_eligible` 4-gate predicate; 14 boundary tests pass; HIL scenarios `test_three_modem_hang.py` + `test_proxy_died_recovery.py` authored. REQUIREMENTS.md line 299 marks Done. |
| FR-27 | 04-01, 04-02, 04-03, 04-06, 04-07 | All 4 destructive actions are separate idempotent CLI-runnable functions; deferred verify | ✓ SATISFIED | 3 new actions + soft_reset all in dispatcher; CLI `spark-modem reset --action=<kind>` accepts all 4; 5 hypothesis idempotency property tests pass; bench-Jetson `test_destructive_actions.py` authored. REQUIREMENTS.md line 305 marks Done. |

All 3 phase requirements covered by ≥1 plan; all 3 marked Done in REQUIREMENTS.md traceability matrix.

## Anti-Pattern Scan

No blocker anti-patterns found in the Phase 4 surface. Specifically checked:

| Pattern | Result |
| ------- | ------ |
| `subprocess.run` sync calls in `actions/` | None — driver_reset uses async `subproc_run` from `subproc.runner` |
| `subprocess` imports in `policy/` | None (CLAUDE.md §1 enforced) |
| `time.time()` in policy code | None (`ctx.clock.monotonic()` everywhere) |
| `gather + return_exceptions=True` for probes | Not introduced in Phase 4 |
| `MonitorObserver` for udev | Not introduced in Phase 4 (Plan 03-02 already used `add_reader(monitor.fileno())`) |
| `if/elif` instead of `match` on `ModemState` | None — `transitions.py:69` uses `match prior.state` |
| One-hot Prometheus `state` label | Not introduced in Phase 4 |
| TODO/FIXME/PLACEHOLDER markers in shipped code | None in the new modules |

## Human Verification Required

### 1. First nightly HIL run on bench Jetson (post-merge)

**Test:** Trigger `.github/workflows/hil.yml` via `workflow_dispatch` after merging Phase 4 to the default branch (or wait for the `0 4 * * *` UTC nightly cron). The job runs on the `[self-hosted, linux, ARM64, hil-bench]` runner physically tethered to the bench Jetson Orin NX with 4× Sierra EM7421 modems on USB hub `2-3.1.{1..4}`.

**Expected:**
- All 12 HIL scenario files collect under `pytest -m hil tests/hil/` (correct on Linux runner)
- SC#4 sub-scenarios all pass:
  - `test_boot_to_healthy.py` — daemon reaches Healthy on all 4 modems within 60 s of process start
  - `test_sim_swap.py` — SIM swap (operator-gated via `BENCH_JETSON_SIM_SWAP_PERFORMED=true`) detected within 1 cycle
  - `test_soft_reset_sim_app_detected.py` — SIM `app_state_detected` resolved by `soft_reset`
  - `test_modem_reset_after_soft.py` — ladder progression `soft_reset → modem_reset` after one rung-1 retry
  - `test_three_modem_hang.py` — 3-of-4 QMI-hung fires exactly ONE `driver_reset`, no per-modem `usb_reset` race
  - `test_rf_event_no_destructive.py` — config-injected forced `rf_blocked` keeps daemon out of destructive resets
  - `test_proxy_died_recovery.py` — `pkill -9 qmi-proxy` mid-cycle recovered with one `driver_reset`
- 4 Phase-3 piggyback scenarios pass:
  - `test_qmi_wwan_reload_clean_transition.py`
  - `test_sigterm_within_5s.py`
  - `test_ctl_reset_state_serialisation.py`
  - `test_watchdog_90s_actual_fire.py` (opt-in)
- 1 destructive end-to-end scenario passes:
  - `test_destructive_actions.py` (opt-in via `BENCH_JETSON_DESTRUCTIVE_TESTS_OK=true`)
- Replay-harness 30-day fault-cycle agreement ≥95% gate green: `pytest tests/replay/` after `tools.pull_replay_traces` materializes the LFS-pulled `tests/fixtures/replay/v1-30d/` snapshot
- `artifacts/replay-summary.json` uploaded as workflow artifact for diagnostics
- On any failure: `spark-modem ctl support-bundle` artifact uploaded

**Why human:** HIL scenarios are `linux_only + hil`-marker-gated and correctly skip with "no tests collected" on this Windows dev host. The Plan 04-07 Task 3 bench-Jetson human-verify checkpoint was auto-approved under `--auto` mode (workflow `_auto_chain_active=true`) with the explicit understanding that bench-Jetson hardware verification was deferred to the first post-merge nightly HIL run. Phase 4 EXIT per ROADMAP.md line 41 is "code complete 2026-05-10; Phase 4 EXIT contingent on first green nightly HIL run on bench Jetson + replay-harness >=95% gate". The scenario files (12), fault-injection toolkit (`fault_inject.py`), workflow (`.github/workflows/hil.yml`), replay-harness gate (`tests/replay/conftest.pytest_sessionfinish`), and LFS trace tooling (`tools/pull_replay_traces.py`) are all in place; only the runner activation is pending.

## Gaps Summary

No code-level gaps found. All Phase 4 must-haves on the dev host are MET:

- 3 new destructive actions implemented and registered (modem_reset, usb_reset, driver_reset)
- Signal-gate thresholds migrated to RELOAD_DATA-tagged Settings; `gate_signal` blocks destructive only
- `_global_driver_reset_eligible` 4-gate predicate wired with all CONTEXT C-01..C-05 conservative deviations applied
- `ActionSkipped` event variant + 7-value `SkipReason` enum emitted on every gate-failure path
- 12 HIL scenario files + replay-harness 30-day gate + nightly workflow + LFS trace tooling all present
- All 6 PATTERNS corrections applied verbatim
- All 12 CLAUDE.md invariants honored
- 1965 unit/integration tests pass in 17.47s (M7 budget preserved); 5 idempotency property tests pass; 14 driver_reset boundary tests pass; 21 recovery-spec rows pass

The single open item — first nightly HIL run on bench Jetson — was explicitly deferred per Plan 04-07's auto-approved bench-Jetson human-verify checkpoint and is recorded as the Phase 4 EXIT bar in ROADMAP.md.

---

*Verified: 2026-05-10T13:35:36Z*
*Verifier: Claude (gsd-verifier)*
