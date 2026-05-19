# T10: 02-core-daemon-laptop-testable 10

**Slice:** S02 — **Milestone:** M001

## Description

Plan 02-10 is the Phase 2 EXIT GATE. It ships:

1. The cycle driver (`daemon/main.py` + `daemon/cycle_driver.py` +
   `daemon/cycle_scheduler.py` + `daemon/rss_tripwire.py`) — the integration
   point that wires every Phase 2 subsystem together. The cycle loop is
   the canonical pattern from RESEARCH §2.9: `asyncio.wait` on a sleep arm
   + an event-queue arm (no-op in Phase 2; Phase 3 wires udev producers);
   `cycle_drift_seconds` recorded BEFORE cycle work; per-cycle pipeline:
   observe → policy → action dispatch → atomic state persist → status.json →
   webhook enqueue.

2. The replay harness (`tools/gen_replay_fixtures.py` +
   `tests/replay/test_v1_agreement.py`). The generator produces ≥1000
   fault-cycle fixtures on disk; the test runs every fixture through
   `policy.engine.run_cycle` and classifies the verdict against the
   fixture's `expected_v1_actions`. The pytest gate hard-fails the build
   at <95% fault-cycle agreement (R-03). A separate restart-mid-streak
   replay fixture proves FR-26.1 streak persistence.

3. The performance + concurrency tests (NFR-1 P99 ≤10s; NFR-11 policy
   exception isolated) that prove the integration works.

This plan has the largest fan-in: it depends on every prior Phase 2 plan.
It is the smallest in code volume per task (most code already exists) but
the highest in integration risk.

Output: ~150 LOC of cycle-driver glue + ~150 LOC of fixture generator + the
exit-gate pytest module + ≥1000 committed fixture files (~50 KB total) +
artifacts/ directory for replay-summary.json.

## Must-Haves

- [ ] "daemon/main.py wires up: StateStore + ConfigLoader + EventLogWriter + MetricRegistry + WebhookPoster + CarrierTable + Inventory + ZaoLogTailer + QmiWrapper-factory + ActionDispatcher + StatusReporter into a single CycleDriver."
- [ ] "CycleScheduler ticks every 30s monotonic; cycle_drift_seconds gauge is set BEFORE cycle work; overrun emits cycle_overran event."
- [ ] "CycleDriver.run_one_cycle: observe_all → policy.run_cycle → action dispatch → atomic state-store + globals write → status.json write → webhook enqueue."
- [ ] "NFR-11: a deliberately-thrown policy exception is caught, logged, and the cycle continues; status.json is still written."
- [ ] "_healthy_streak persists across simulated daemon restart: pre-restart fixture (cycle 5/10) → re-load → post-restart fixture (cycle 6/10) reaches decay at cycle 10 not 5+5 = reset."
- [ ] "tools/gen_replay_fixtures.py generates ≥1000 fault-cycle fixtures from RECOVERY_SPEC §4 + top-15 PITFALLS scenarios + Hypothesis property strategies."
- [ ] "tests/replay/test_v1_agreement.py runs every on-disk fixture, classifies each verdict (agree | safer | less-safe | different-issue | both-skip), emits artifacts/replay-summary.json, and HARD FAILS at <95% fault-cycle agreement (R-03)."
- [ ] "Wallclock for the full pytest suite stays under M7 30s budget with the replay harness contributing ~5s for 1000 fixtures (R-03 / NFR-1 measurable on a developer laptop)."
- [ ] "RSS tripwire emits rss_tripwire_breached event + records daemon_self_health{kind='rss'} when RSS > 200 MiB; does NOT graceful-exit (Phase 2 owns the metric only)."

## Files

- `src/spark_modem/daemon/__init__.py`
- `src/spark_modem/daemon/main.py`
- `src/spark_modem/daemon/cycle_scheduler.py`
- `src/spark_modem/daemon/cycle_driver.py`
- `src/spark_modem/daemon/rss_tripwire.py`
- `tests/unit/daemon/__init__.py`
- `tests/unit/daemon/test_cycle_scheduler.py`
- `tests/unit/daemon/test_cycle_driver.py`
- `tests/unit/daemon/test_policy_exception_isolation.py`
- `tests/unit/daemon/test_cycle_perf.py`
- `tools/gen_replay_fixtures.py`
- `tests/replay/__init__.py`
- `tests/replay/conftest.py`
- `tests/replay/test_v1_agreement.py`
- `tests/replay/test_streak_restart.py`
- `tests/fixtures/replay/healthy/000_clean_cycle.json`
- `tests/fixtures/replay/healthy/001_clean_cycle.json`
- `tests/fixtures/replay/registration_searching/000_first_cycle.json`
- `tests/fixtures/replay/sim_app_detected/000_resolves_on_soft_reset.json`
- `tests/fixtures/replay/raw_ip_off/000.json`
- `tests/fixtures/replay/apn_empty/000.json`
- `tests/fixtures/replay/operating_mode_low_power/000.json`
- `tests/fixtures/replay/proxy_died/000.json`
- `tests/fixtures/replay/exhausted_holds/000.json`
- `tests/fixtures/replay/rf_blocked_during_recovery/000.json`
- `tests/fixtures/replay/restart_mid_streak/000_pre.json`
- `tests/fixtures/replay/restart_mid_streak/001_post.json`
- `artifacts/.gitkeep`
