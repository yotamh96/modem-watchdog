# S02: Core Daemon Laptop Testable

**Goal:** Plan 02-01 lands the test scaffolding every other Phase 2 plan depends on:
the five test fakes (`FakeRunner`, `FakeClock`, `FakeWebhookPoster`,
`FixtureInventory`, `FakeDNSResolver`) plus a small `FixtureZaoTailer`,
and the empty fixture directories that will hold qmicli text fixtures, Zao
log snippets, inventory JSON snapshots, and replay cycle JSON.
**Demo:** Plan 02-01 lands the test scaffolding every other Phase 2 plan depends on:
the five test fakes (`FakeRunner`, `FakeClock`, `FakeWebhookPoster`,
`FixtureInventory`, `FakeDNSResolver`) plus a small `FixtureZaoTailer`,
and the empty fixture directories that will hold qmicli text fixtures, Zao
log snippets, inventory JSON snapshots, and replay cycle JSON.

## Must-Haves


## Tasks

- [x] **T01: 02-core-daemon-laptop-testable 01** `est:5min`
  - Plan 02-01 lands the test scaffolding every other Phase 2 plan depends on:
the five test fakes (`FakeRunner`, `FakeClock`, `FakeWebhookPoster`,
`FixtureInventory`, `FakeDNSResolver`) plus a small `FixtureZaoTailer`,
and the empty fixture directories that will hold qmicli text fixtures, Zao
log snippets, inventory JSON snapshots, and replay cycle JSON.

Purpose: every downstream plan in waves 2–6 imports from `tests/fakes/*`.
If we wait until each plan needs a fake to land it, those plans cannot run
parallel within their wave. By staging all fakes here in wave 1, plans 02-02
through 02-08 can develop and self-test in parallel.

Output: six fake modules under `tests/fakes/` (each with mypy --strict +
self-tests under `tests/unit/fakes/`) and five empty `.gitkeep`-tracked
fixture directories under `tests/fixtures/`. No production code changes.
- [x] **T02: 02-core-daemon-laptop-testable 02** `est:9min`
  - Plan 02-02 lands the qmicli boundary: a single `QmiWrapper` class that owns
every qmicli invocation in the daemon (via the existing `subproc.run`
plumbing), seven per-intent parser modules that turn qmicli text output into
typed records, and the per-libqmi-version fixture set.

Purpose: every other Phase 2 module that wants to talk to a modem (observer,
actions, CLI) goes through `QmiWrapper`. By centralising the qmicli surface
here we (a) keep `--device-open-proxy` always-on (FR-74), (b) keep the
boundary `extra='ignore'` so a libqmi point-release doesn't break the daemon,
and (c) give downstream plans a stable typed return value rather than raw
text.

Output: `qmi/wrapper.py`, `qmi/parsers/*.py`, `qmi/errors.py`, the per-version
qmicli fixture tree, and unit tests parametrized over every fixture.
- [x] **T03: 02-core-daemon-laptop-testable 03** `est:~4min`
  - Plan 02-03 lands the Zao log boundary needed for FR-10 (the `RASCOW_STAT`
gate that prevents the daemon from QMI-probing a Zao-active line).

Phase 2 ships the file-read fallback (`ZaoLogParser.snapshot()` walks the
log backward to find the most recent `RASCOW_STAT` block); Phase 3 swaps
in an inotify-backed implementation behind the same `ZaoLogTailer` Protocol
surface — Phase 2 callers (observer/) never need to change.

Purpose: the observer (plan 02-04) calls `tailer.is_line_active(line_idx)`
before invoking qmicli on any modem. If the line is bonding-active under
Zao, we must not probe — Zao requires exclusive access (`ModemManager` is
masked for the same reason).

Output: `zao_log/protocol.py` + `parser.py` + `snapshot.py` plus five log
fixture scenarios + parametrized parser tests.
- [x] **T04: 02-core-daemon-laptop-testable 04** `est:25min`
  - Plan 02-04 lands the observer subsystem and its supporting inventory:
the `InventorySource` Protocol + `SysfsInventory` impl, and the
`asyncio.TaskGroup`-based probe orchestrator that produces one `Diag` per cycle.

This is the "fan-out" half of the cycle (the policy engine is the "decide"
half — plan 02-05). The orchestrator obeys two CLAUDE.md invariants:
- Every per-modem probe runs under `asyncio.timeout(8s)` inside a TaskGroup
  (FR-70, NFR-4).
- Every per-modem probe catches its own exceptions; the TaskGroup never sees
  an exception escape, so one slow modem never cancels its three siblings
  (NFR-11).

Output: `inventory/` package + `observer/` package + parametrized tests
(parallel-probe correctness, single-probe timeout, single-probe exception,
Zao-active-skip behavior) + sysfs fixture tree for SysfsInventory.
- [x] **T05: 02-core-daemon-laptop-testable 05** `est:~25min`
  - Plan 02-05 lands the pure-function policy engine — the core of the daemon
and the only file that decides "what action runs on which modem this cycle."

Per CLAUDE.md §1: the entire `policy/` package is a pure function. No
subprocess, no httpx, no os, no env reads. mypy + the lint gate
(`scripts/lint_no_subprocess.sh`) enforce this; the test suite proves it.

The engine is structured as four files mirroring RECOVERY_SPEC §3..§7:
- `transitions.py` — `Diag × ModemState → new ModemState` (FR-12 5+2 shape)
- `decision_table.py` — `(IssueCategory, IssueDetail) → ActionKind` (FR-21 priority)
- `gates.py` — pure gates: signal / same-action backoff / ladder backoff /
  exhausted / maintenance / disconnected (FR-25, FR-25.1, FR-23 stub, C-01)
- `engine.py` — `run_cycle(Diag, state[], globals, config, clock) → CycleResult`

Counter decay ordering (RECOVERY_SPEC §8 / ADR-0006) is encoded in
`engine.run_cycle`: transition → streak update → decay check → counter reset
→ planned action selection → gates → CycleResult. The atomic state-write
itself is performed by the cycle driver in plan 02-10 — but the planned
order is fixed here (the engine returns the new ModemState[] alongside the
PlannedAction[]; the driver writes both in one atomic per-modem write).

Output: `policy/` package + `tests/unit/policy/*` exhaustive coverage +
`tests/test_recovery_spec.py` spec-as-tests gate + `tools/check_spec.py`
coverage-checker tool.
- [x] **T06: 02-core-daemon-laptop-testable 06**
  - Plan 02-06 lands the cheap action set the policy engine in plan 02-05
selects from. Six action modules (one file per action) plus a shared
dispatcher and result types.

The dispatcher is the SINGLE entry point used by:
- The cycle driver (plan 02-10) for `execute_and_verify(plan.kind, plan.who, ctx)`.
- The CLI (plan 02-09) for `spark-modem reset --action=<name> --modem=...`.

Phase 2 cheap actions (per CLAUDE.md "Critical invariants" + RECOVERY_SPEC §2):
1. `set_apn` — reads carrier table by (MCC, MNC), writes profile-1 if APN
   differs (FR-31), then reads back to verify (FR-32). Idempotent.
2. `fix_raw_ip` — sets `--wds-set-ip-family=4` when raw_ip is "N".
3. `sim_power_on` — `--uim-sim-power-on=1`.
4. `soft_reset` — single qmicli reset; verify is deferred (effect observed
   next cycle, not inline).
5. `set_operating_mode` — DMS set/get operating mode (used to push out of
   `low_power` / `offline`; idempotent — FR-31-style read-then-write).
6. `fix_autosuspend` — writes "on" to the USB device's `power/control`
   sysfs file (this is the only action that doesn't go through qmicli;
   it goes through `subproc.run` for `tee` so SP-04 lint stays clean —
   alternative: use `Path.write_text` since it's a regular file write,
   not a subprocess).

Destructive actions (modem_reset / usb_reset / driver_reset) are NOT
registered here — they land in Phase 4. The dispatcher registry shape
guarantees Phase 4 is a pure data-add.

Output: `actions/` package + per-action tests using FakeRunner +
dry-run gate tests + carrier-table lookup tests.
- [x] **T07: 02-core-daemon-laptop-testable 07**
  - Plan 02-07 lands the observability surface: status.json writer + Prometheus
UDS exporter + the metric registry that's wired into the cycle driver.

The work splits cleanly along three subsystems:
1. Wire model additions: `StatusReport` (the on-disk shape of status.json),
   `MaintenanceWindow` (C-02 dual-clock window stored in globals.json),
   plus extending `GlobalsState` with `maintenance`.
2. `status.json` writer — a thin wrapper around Phase 1's
   `state_store.atomic.atomic_write_bytes` that serialises a `StatusReport`
   pydantic model and writes it atomically every cycle (O-01).
3. Prometheus UDS exporter — `_UnixWSGIServer` subclass that binds AF_UNIX,
   served by `prometheus_client.make_wsgi_app()` in a `to_thread` worker;
   plus a typed `MetricRegistry` that the cycle driver and webhook poster
   use to record metrics. Integer-encoded `modem_state_value{modem}` per
   ADR-0013 — never one-hot.

Output: `wire/status.py` + `wire/maintenance.py` + extended `wire/globals.py`
+ `status_reporter/{status,prom,metrics_registry}.py` + parametrized tests
including a Linux-only UDS scrape integration test (skipif win32) and a
Windows-friendly metric-registry test.
- [x] **T08: 02-core-daemon-laptop-testable 08**
  - Plan 02-08 lands the webhook subsystem: HMAC-signed POSTs to a configured
URL on Healthy→Degraded and Recovering→Exhausted transitions, plus
DaemonRestart and ActionFailed variants.

The poster runs in a SEPARATE asyncio task so the cycle never blocks on
webhook I/O (FR-44.8). DNS is pre-resolved at config-load + refreshed every
60s with a 600s "go-stale" fallback before marking webhooks `skipped_no_dns`.
TLS uses the Host-header trick: URL string contains the cached IP, but the
`Host:` header carries the original hostname so TLS SNI verifies correctly.

Output: `webhook/` package + parametrized tests using `pytest-httpx` (or a
small custom transport mock if pytest-httpx is not in the dev deps) +
property tests for the dedup table + a Linux/Windows-portable DNS test
that exercises `loop.getaddrinfo` against a known-static name (`localhost`).
- [x] **T09: 02-core-daemon-laptop-testable 09** `est:~30min`
  - Plan 02-09 ships the `spark-modem` CLI: six subcommands plus the three
`ctl` sub-subcommands (history, maintenance, support-bundle).

The CLI hits ALL of Phase 2's underlying subsystems:
- `diag` ← inventory + observer + zao_log + qmi (Plan 02-04 / 02-02 / 02-03)
- `recovery` ← policy.engine.run_cycle (Plan 02-05)
- `provision`, `reset` ← actions.dispatcher.execute_and_verify (Plan 02-06)
- `status` ← reads `/var/lib/spark-modem-watchdog/status.json` (Plan 02-07)
- `ctl history` ← reads `/var/log/spark-modem-watchdog/events.jsonl` (Phase 1 + new logrotate-rotated-siblings reader)
- `ctl maintenance` ← writes `globals.json` via state_store (Phase 1)
- `ctl support-bundle` ← assembles + redacts a tarball (NFR-22 + C-04)

`diag --qmi-fixture-dir=PATH` and `recovery --diag-fixture=PATH` are the
hardware-free fast paths: they swap a `FixtureRunner` (a small variant of
FakeRunner that loads canned qmicli output from per-version fixture files
on disk) into the QmiWrapper plumbing.

Output: `cli/` package + entry point in pyproject.toml + parametrized tests
covering happy paths and error paths (mandatory --duration on maintenance,
8h cap rejection, no carrier match, etc.).
- [x] **T10: 02-core-daemon-laptop-testable 10** `est:~30 min`
  - Plan 02-10 is the Phase 2 EXIT GATE. It ships:

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

## Files Likely Touched

- `tests/fakes/__init__.py`
- `tests/fakes/runner.py`
- `tests/fakes/clock.py`
- `tests/fakes/webhook.py`
- `tests/fakes/inventory.py`
- `tests/fakes/dns.py`
- `tests/fakes/zao_log.py`
- `tests/fixtures/qmicli/.gitkeep`
- `tests/fixtures/zao_log/.gitkeep`
- `tests/fixtures/inventory/.gitkeep`
- `tests/fixtures/diag/.gitkeep`
- `tests/fixtures/replay/.gitkeep`
- `tests/unit/fakes/__init__.py`
- `tests/unit/fakes/test_runner.py`
- `tests/unit/fakes/test_clock.py`
- `tests/unit/fakes/test_webhook.py`
- `tests/unit/fakes/test_inventory.py`
- `tests/unit/fakes/test_dns.py`
- `tests/unit/fakes/test_zao_log.py`
- `tests/conftest.py`
- `src/spark_modem/qmi/__init__.py`
- `src/spark_modem/qmi/errors.py`
- `src/spark_modem/qmi/wrapper.py`
- `src/spark_modem/qmi/parsers/__init__.py`
- `src/spark_modem/qmi/parsers/get_signal.py`
- `src/spark_modem/qmi/parsers/get_serving_system.py`
- `src/spark_modem/qmi/parsers/get_sim_state.py`
- `src/spark_modem/qmi/parsers/get_data_session.py`
- `src/spark_modem/qmi/parsers/get_profile_settings.py`
- `src/spark_modem/qmi/parsers/get_operating_mode.py`
- `src/spark_modem/qmi/parsers/get_current_settings.py`
- `src/spark_modem/qmi/parsers/_header.py`
- `tests/unit/qmi/__init__.py`
- `tests/unit/qmi/test_wrapper.py`
- `tests/unit/qmi/test_parsers.py`
- `tests/fixtures/qmicli/get_signal/1.30/lte_strong.txt`
- `tests/fixtures/qmicli/get_signal/1.30/lte_weak.txt`
- `tests/fixtures/qmicli/get_signal/1.32/nr5g_present.txt`
- `tests/fixtures/qmicli/get_serving_system/1.30/registered_home.txt`
- `tests/fixtures/qmicli/get_serving_system/1.30/not_registered_searching.txt`
- `tests/fixtures/qmicli/get_sim_state/1.30/ready.txt`
- `tests/fixtures/qmicli/get_sim_state/1.30/sim_app_detected.txt`
- `tests/fixtures/qmicli/get_sim_state/1.30/sim_power_down.txt`
- `tests/fixtures/qmicli/get_data_session/1.30/connected.txt`
- `tests/fixtures/qmicli/get_data_session/1.30/disconnected.txt`
- `tests/fixtures/qmicli/get_profile_settings/1.30/profile1_internet.txt`
- `tests/fixtures/qmicli/get_operating_mode/1.30/online.txt`
- `tests/fixtures/qmicli/get_operating_mode/1.30/low_power.txt`
- `tests/fixtures/qmicli/get_current_settings/1.30/raw_ip_y.txt`
- `tests/fixtures/qmicli/get_current_settings/1.30/raw_ip_n.txt`
- `tests/fixtures/qmicli/proxy_error/proxy_died.txt`
- `src/spark_modem/zao_log/__init__.py`
- `src/spark_modem/zao_log/protocol.py`
- `src/spark_modem/zao_log/parser.py`
- `src/spark_modem/zao_log/snapshot.py`
- `tests/unit/zao_log/__init__.py`
- `tests/unit/zao_log/test_parser.py`
- `tests/fixtures/zao_log/all_lines_active.log`
- `tests/fixtures/zao_log/two_lines_active.log`
- `tests/fixtures/zao_log/no_lines_active.log`
- `tests/fixtures/zao_log/stale.log`
- `tests/fixtures/zao_log/multiple_blocks_use_last.log`
- `src/spark_modem/inventory/__init__.py`
- `src/spark_modem/inventory/protocol.py`
- `src/spark_modem/inventory/descriptor.py`
- `src/spark_modem/inventory/sysfs.py`
- `src/spark_modem/observer/__init__.py`
- `src/spark_modem/observer/orchestrator.py`
- `src/spark_modem/observer/diag_builder.py`
- `src/spark_modem/observer/issue_extractor.py`
- `tests/unit/inventory/__init__.py`
- `tests/unit/inventory/test_sysfs.py`
- `tests/unit/observer/__init__.py`
- `tests/unit/observer/test_orchestrator.py`
- `tests/unit/observer/test_diag_builder.py`
- `tests/fakes/inventory.py`
- `tests/fixtures/inventory/four_modems_one_zao_active.json`
- `tests/fixtures/inventory/two_modems.json`
- `tests/fixtures/sysfs/four_modems/sys/bus/usb/devices/.gitkeep`
- `src/spark_modem/policy/__init__.py`
- `src/spark_modem/policy/context.py`
- `src/spark_modem/policy/transitions.py`
- `src/spark_modem/policy/decision_table.py`
- `src/spark_modem/policy/gates.py`
- `src/spark_modem/policy/engine.py`
- `src/spark_modem/policy/result.py`
- `tests/unit/policy/__init__.py`
- `tests/unit/policy/test_transitions.py`
- `tests/unit/policy/test_decision_table.py`
- `tests/unit/policy/test_gates.py`
- `tests/unit/policy/test_engine.py`
- `tests/unit/policy/test_streak.py`
- `tests/test_recovery_spec.py`
- `tools/check_spec.py`
- `src/spark_modem/actions/__init__.py`
- `src/spark_modem/actions/result.py`
- `src/spark_modem/actions/context.py`
- `src/spark_modem/actions/dispatcher.py`
- `src/spark_modem/actions/verify.py`
- `src/spark_modem/actions/set_apn.py`
- `src/spark_modem/actions/fix_raw_ip.py`
- `src/spark_modem/actions/sim_power_on.py`
- `src/spark_modem/actions/soft_reset.py`
- `src/spark_modem/actions/set_operating_mode.py`
- `src/spark_modem/actions/fix_autosuspend.py`
- `src/spark_modem/wire/carriers.py`
- `tests/unit/actions/__init__.py`
- `tests/unit/actions/test_dispatcher.py`
- `tests/unit/actions/test_set_apn.py`
- `tests/unit/actions/test_fix_raw_ip.py`
- `tests/unit/actions/test_sim_power_on.py`
- `tests/unit/actions/test_soft_reset.py`
- `tests/unit/actions/test_set_operating_mode.py`
- `tests/unit/actions/test_fix_autosuspend.py`
- `tests/unit/actions/test_dry_run.py`
- `tests/unit/actions/test_verify.py`
- `src/spark_modem/wire/status.py`
- `src/spark_modem/wire/maintenance.py`
- `src/spark_modem/wire/globals.py`
- `src/spark_modem/status_reporter/__init__.py`
- `src/spark_modem/status_reporter/status.py`
- `src/spark_modem/status_reporter/prom.py`
- `src/spark_modem/status_reporter/metrics_registry.py`
- `tests/unit/status_reporter/__init__.py`
- `tests/unit/status_reporter/test_status.py`
- `tests/unit/status_reporter/test_metrics_registry.py`
- `tests/unit/status_reporter/test_prom_uds.py`
- `src/spark_modem/webhook/__init__.py`
- `src/spark_modem/webhook/dns.py`
- `src/spark_modem/webhook/sign.py`
- `src/spark_modem/webhook/dedup.py`
- `src/spark_modem/webhook/poster.py`
- `src/spark_modem/wire/events.py`
- `tests/unit/webhook/__init__.py`
- `tests/unit/webhook/test_dns.py`
- `tests/unit/webhook/test_sign.py`
- `tests/unit/webhook/test_dedup.py`
- `tests/unit/webhook/test_poster.py`
- `tests/unit/webhook/test_drain.py`
- `src/spark_modem/cli/__init__.py`
- `src/spark_modem/cli/main.py`
- `src/spark_modem/cli/diag.py`
- `src/spark_modem/cli/recovery.py`
- `src/spark_modem/cli/provision.py`
- `src/spark_modem/cli/reset.py`
- `src/spark_modem/cli/status.py`
- `src/spark_modem/cli/explain.py`
- `src/spark_modem/cli/ctl/__init__.py`
- `src/spark_modem/cli/ctl/history.py`
- `src/spark_modem/cli/ctl/maintenance.py`
- `src/spark_modem/cli/ctl/support_bundle.py`
- `src/spark_modem/cli/redact.py`
- `src/spark_modem/cli/clients.py`
- `pyproject.toml`
- `tests/unit/cli/__init__.py`
- `tests/unit/cli/test_main.py`
- `tests/unit/cli/test_diag.py`
- `tests/unit/cli/test_recovery.py`
- `tests/unit/cli/test_provision.py`
- `tests/unit/cli/test_reset.py`
- `tests/unit/cli/test_status.py`
- `tests/unit/cli/test_explain.py`
- `tests/unit/cli/test_ctl_history.py`
- `tests/unit/cli/test_ctl_maintenance.py`
- `tests/unit/cli/test_ctl_support_bundle.py`
- `tests/unit/cli/test_redact.py`
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
