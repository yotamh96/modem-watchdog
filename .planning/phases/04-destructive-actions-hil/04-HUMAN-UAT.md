---
status: partial
phase: 04-destructive-actions-hil
source: [04-VERIFICATION.md]
started: 2026-05-10T00:00:00Z
updated: 2026-05-10T00:00:00Z
---

## Current Test

[awaiting bench-Jetson HIL nightly run]

## Tests

### 1. First nightly HIL run on bench Jetson (post-merge)
expected: `.github/workflows/hil.yml` runs end-to-end on the `[self-hosted, linux, ARM64, hil-bench]` runner with 4× Sierra EM7421 modems on USB hub `2-3.1.{1..4}`. All 12 scenario files in `tests/hil/scenarios/` pass:

  Phase-4 SC#4 (7):
    - test_boot_to_healthy.py — boot and reach Healthy in 60s
    - test_sim_swap.py — SIM swap detected
    - test_soft_reset_sim_app_detected.py — SIM app_state_detected resolved by soft_reset
    - test_modem_reset_after_soft.py — not_registered_searching resolved by modem_reset after one soft_reset (ladder rung 1 → 2)
    - test_three_modem_hang.py — 3-modem QMI hang triggers exactly one driver_reset
    - test_rf_event_no_destructive.py — RF event keeps daemon out of destructive resets
    - test_proxy_died_recovery.py — pkill -9 qmi-proxy recovered with one driver_reset (no thrash)

  Phase-3 piggyback (4):
    - test_qmi_wwan_reload_clean_transition.py — real qmi_wwan reload as clean state transition
    - test_sigterm_within_5s.py — SIGTERM ≤ 5s with real flock release
    - test_ctl_reset_state_serialisation.py — concurrent ctl reset-state flock serialisation
    - test_watchdog_90s_actual_fire.py — WatchdogSec=90s actual-fire under deliberately-wedged qmicli

  Destructive-actions end-to-end (1):
    - test_destructive_actions.py — each of 4 destructive actions runs end-to-end

  Plus replay-harness 30-day agreement gate ≥ 95% against LFS-pulled v1-30d traces.

result: [pending — requires bench-Jetson hardware access not available in dev environment]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps

(none — gap closure not needed; this is hardware verification deferred to first post-merge nightly HIL run per Plan 04-07 Task 3 auto-approved checkpoint disposition under `--auto` mode)
