---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: planning
stopped_at: Phase 5 context gathered
last_updated: "2026-05-11T06:09:30.003Z"
last_activity: 2026-05-10
progress:
  total_phases: 7
  completed_phases: 4
  total_plans: 33
  completed_plans: 33
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-05)

**Core value:** Maximize end-user uplink availability across the four bonded modems by applying minimum-impact recovery actions — and never running a destructive recovery that has zero chance of fixing the observed issue.
**Current focus:** Phase 04 — destructive-actions-hil

## Current Position

Phase: 5
Plan: Not started
Status: Ready to plan
Last activity: 2026-05-10

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 23
- Average duration: -
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 7 | - | - |
| 03 | 9 | - | - |
| 04 | 7 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*
| Phase 01-foundations-adrs P01 | 10 minutes | 2 tasks | 15 files |
| Phase 01 P07 | 14 | 3 tasks | 12 files |
| Phase 01 P01-03-wire-package | 18 | 3 tasks | 30 files |
| Phase 01-foundations-adrs P04 | 240 | 4 tasks | 15 files |
| Phase 01 P01-05-subproc-runner | 10 | 2 tasks | 11 files |
| Phase 01-foundations-adrs P01-06-clock-config-event-logger-carriers | 11 | 3 tasks | 18 files |
| Phase 01-foundations-adrs P01-02-deb-build-pipeline | 10 | 2 tasks | 15 files |
| Phase 02 P01 | 5min | 2 tasks | 20 files |
| Phase 02 P02 | 9min | 2 tasks | 31 files |
| Phase 02 P02-03 | 4min | 2 tasks tasks | 12 files files |
| Phase 02 P02-05 | 25 minutes | 2 tasks tasks | 15 files files |
| Phase 02 P02-04 | 25min | 2 tasks tasks | 16 files files |
| Phase 02 P06 | 12m 30s | 2 tasks tasks | 22 files files |
| Phase 02 P08 | ~30m | 2 tasks tasks | 13 files files |
| Phase 02 P07 | 12 minutes | 2 tasks tasks | 11 files files |
| Phase 02 P09 | ~30m | 2 tasks tasks | 27 files files |
| Phase 02 P10 | ~30m | 2 tasks | 1015 files (5 daemon src + 4 daemon tests + 1 generator + 4 replay tests + 1004 fixture JSONs + 1 .gitkeep) |
| Phase 03 P01 | 12min | 2 tasks tasks | 10 files files |
| Phase 03 P02 | 13min | 2 tasks tasks | 13 files files |
| Phase 03 P03 | 6min | 1 task tasks | 4 files files |
| Phase 03 P04 | 13min | 2 tasks tasks | 11 files files |
| Phase 03 P05 | 9min | 2 tasks tasks | 14 files files |
| Phase 03 P06 | 17min | 2 tasks tasks | 16 files files |
| Phase 03-linux-event-sources-lifecycle P07 | 9min | 2 tasks | 6 files |
| Phase 03-linux-event-sources-lifecycle P08 | 4min | 1 tasks | 3 files |
| Phase 03-linux-event-sources-lifecycle P09 | ~8min | 3 tasks | 4 files (3 integration tests + SUMMARY) |
| Phase 04-destructive-actions-hil P01-modem-reset | 6min | 2 tasks tasks | 7 files files |
| Phase 04-destructive-actions-hil P06-hil-infra-scaffold | 7min | 2 tasks tasks | 8 files files |
| Phase 04 P02 | 10min | 2 tasks tasks | 16 files files |
| Phase 04 P03 | 11min (683s) | 3 tasks tasks | 9 files files |
| Phase 04 P04 | 15min | 3 tasks tasks | 13 files files |
| Phase 04-destructive-actions-hil PP05 | 14min | 2 tasks tasks | 10 files files |
| Phase 04-destructive-actions-hil P07-hil-scenario-suite | 21min | 3 tasks tasks | 16 files files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Init: Bundle CPython 3.12 via `python-build-standalone` in `.deb` venv (closes Q8) — research SUMMARY §2
- Init: State machine refactored to 5 top-level states + 2 orthogonal flags (`present`, `rf_blocked`); ADR-0008 supersedes ADR-0005's 7-state shape
- Init: State files keyed by `usb_path` (`state/by-usb/<usb_path>.json`); ADR-0009
- Init: HMAC v2.0 webhook signing promoted from v2.1 (closes Q5); ADR-0011
- Init: Per-modem `asyncio.Lock` + globals lock + cross-process `flock`s separate from PID lock; ADR-0012
- Init: Integer-encoded `modem_state_value{modem}` Prom metric (NOT one-hot); ADR-0013
- requirements.lock compiled with --python-platform linux to exclude win-inet-pton and target aarch64/Linux deployment
- pydantic-settings upstreamed to Plan 01 requirements.in so Plan 02 .deb smoke test and Plan 06 Settings class both consume from same lockfile
- ADR-0008 supersedes ADR-0005: 5 top-level states + 2 orthogonal flags (present, rf_blocked) replaces 7-state flat enum
- ADR-0009: state files keyed by usb_path at state/by-usb/<usb_path>.json; daemon refuses to start on topology mismatch
- ADR-0010: CPython 3.12 via python-build-standalone + uv + custom debhelper; closes Q8
- ADR-0011: HMAC-SHA256 promoted to v2.0 (closes Q5); X-Spark-Signature over raw body bytes; pre-resolved DNS prevents event-loop block
- ADR-0012: 3-layer locking — per-modem asyncio.Lock + globals lock + per-modem flock + state-store flock + separate PID lock
- ADR-0013: integer-encoded modem_state_value{modem} (0-4 stable mapping) replaces one-hot state label; 16 series per box
- All 8 PROJECT.md open questions Q1-Q8 closed in writing as of Phase 1 (2026-05-06)
- Pydantic v2 BaseWire: frozen=True, extra=forbid, populate_by_name=True — strict wire boundary (CONTEXT.md W-02)
- ModemState 5+2 ADR-0008: state Literal + recovering_level + present + rf_blocked; state_to_int() stable 0-4 encoding for ADR-0013 metric
- CarrierTable uses StrictStr to reject YAML type coercions including Norway problem (NO->False) and MNC-as-int
- Public/private lock split in StateStore: public save_* acquires asyncio.Lock + flock; private _save_*_locked called from downgrade branch — prevents asyncio.Lock re-entry deadlock (ADR-0012)
- Windows dev-host flock no-op: AsyncFlockHandle(fd=-1) sentinel when fcntl unavailable; asyncio.Lock tests pass on non-POSIX hosts without skipping whole test files
- model_validate() over constructor for pydantic alias fields without mypy plugin — bypasses call-arg error on populate_by_name aliases
- timeout parameter renamed to timeout_s to satisfy ruff ASYNC109 (async function with 'timeout' parameter name)
- signal.SIGKILL replaced with integer literal 9 -- POSIX-only, absent from Windows stubs under mypy --strict
- os.killpg/os.getpgid guarded by sys.platform != win32 -- POSIX-only attributes absent from typeshed Windows stubs
- All 24 runner tests marked skipif(win32) -- Windows dev host lacks POSIX binaries; production Jetson is Linux/aarch64
- EventLogClosedError (ruff N818 rename from EventLogClosed); alias kept for compat
- Settings model_validator enforces NFR-33 http-only block cross-field
- clock uses datetime.UTC alias (Python 3.12 UP017) instead of timezone.utc
- types-PyYAML installed as dev dep for mypy --strict on yaml_merge.py
- Pin cpython-3.12.13+20260504-aarch64-unknown-linux-gnu-install_only.tar.gz (SHA256 8a27d68c0dec7573c269e16da61fed358e4bb9f986ae976549ca87ed49fe1506) as bundled CPython for .deb
- postinst masks ModemManager.service (hardware constraint: Zao requires exclusive modem access)
- LoadCredential= in systemd unit for HMAC secret (ADR-0011); credential path /etc/spark-modem-watchdog/hmac-secret
- Plan 02-01: tests/fakes/ houses six hardware-free fakes (Runner/Clock/ZaoTailer/WebhookPoster/Inventory/DNSResolver) — single import surface for all Phase 2 unit tests
- Plan 02-01: FixtureInventory carries a local _FixtureModemDescriptor pydantic shape; Plan 02-04 will promote to production InventorySource Protocol type and update the fake
- Plan 02-01: tests/fixtures/{qmicli,zao_log,inventory,diag,replay}/.gitkeep tracks empty fixture roots; Wave 2-6 plans populate them
- Plan 02-01: FakeRunner raises KeyError on unregistered argv — tests must declare every expected command, no silent passthrough
- Plan 02-02: QmiWrapper centralizes qmicli (always with --device-open-proxy / FR-74); 11 methods routed through subproc.runner.run; SP-04 lint enforces no bypass
- Plan 02-02: _in_critical_section flag set on 4 state-changing methods (dms_set_operating_mode, uim_sim_power_on, wds_modify_profile, wds_set_ip_family); cleared in finally so Phase 3 SIGTERM handler can wait for cleanup
- Plan 02-02: classify() short-circuits on PROXY_DIED stderr signatures (PITFALLS §1.1) so policy/ chooses driver_reset (RECOVERY_SPEC §6.4); timeout wins over proxy-died when both present
- Plan 02-02: parsers use ConfigDict(extra='ignore', frozen=True) absorbing libqmi version drift; required fields surface as QmiError(MISSING_FIELD, field=<name>) not silent None
- Plan 02-02: per-libqmi-version fixture tree at tests/fixtures/qmicli/<intent>/<version>/<scenario>.txt with  line-1 comment; 16 fixtures across 1.30 + 1.32; new libqmi release = new directory + new fixtures, no parser code change
- Plan 02-03: ZaoLogTailer @runtime_checkable Protocol seam co-located with parser; ZaoLogParser walks log backwards from EOF anchored on shared ISO timestamp prefix to pick LATEST RASCOW_STAT block
- Plan 02-03: ZaoSnapshot.unknown(reason=...) classmethod factory uses canonical reason strings (zao_log_missing | zao_log_io_error:<errno> | zao_log_no_rascow_stat); never embeds raw log content (T-02-03-03)
- Plan 02-03: FixtureZaoTailer.snapshot() added (Rule 2) so test fake satisfies new ZaoLogTailer Protocol; observer/ in plan 02-04 can swap parser<->fake without divergent call surfaces
- Plan 02-03: active_lines stored as frozenset[int] (not set) -- consistent with BaseWire frozen=True; observer must read snapshot().unknown_reason defensively for FR-10 safe direction (T-02-03-04)
- Plan 02-05: policy/ pure-function package -- transitions/decision_table/gates/engine; CLAUDE.md §1 verified by import grep + lint_no_subprocess; match-on-state enforced (anti-pattern)
- Plan 02-05: ClockProto Protocol shared between context.py and gates.py so policy/ never imports production clock module (purity boundary)
- Plan 02-05: Decision table is dict[(IssueCategory,IssueDetail), ActionKind|str] -- skip-reasons are open str literals (extensible without enum churn); 20 rows cover the 5 IssueCategory enum values' RECOVERY_SPEC §4 rows
- Plan 02-05: tools/check_spec.py uses substring-match against tests/test_recovery_spec.py 'Coverage manifest' docstring; parametrize ids alone don't appear as text -- the manifest is the auditable contract
- Plan 02-04: InventorySource @runtime_checkable Protocol seam co-located with descriptor.py and sysfs.py; Phase 3 swaps SysfsInventory -> UdevInventory transparently; observer/ never changes
- Plan 02-04: TaskGroup + per-task asyncio.timeout(8s) + per-task try/except (TimeoutError + Exception) absorbs failures inside _probe_one so the TaskGroup never sees an exception escape (NFR-11); verified by test_one_slow_probe_does_not_cancel_siblings + test_exception_in_probe_does_not_propagate_to_taskgroup
- Plan 02-04: Zao-active gate runs BEFORE qmicli (FR-10/ADR-0003); Zao-active modems return zero-issue ModemSnapshot built fresh from descriptor fields, never QMI-probed; verified by test_zao_active_short_circuits_qmicli
- Plan 02-04: extract_issues is pure function (no I/O, no clock); probe_modem_to_snapshot owns qmicli I/O and routes parsed results through extract_issues; preserves §4 decision-table testability
- Plan 02-04: §4 detection split observer-vs-policy: per-modem facts (apn_empty, raw_ip_off, sim/registration/operating_mode, qmi_proxy_died, qmi_timeout) live in observer; cross-source detections (apn_mismatch needs carrier table, qmi_channel_hung needs fleet aggregation) live in policy/
- Plan 02-04: FixtureInventory.scan() now returns list[ModemDescriptor] (production type); _FixtureModemDescriptor removed -- Plan 02-01 promotion delivered
- Plan 02-04: WhoModem placeholder-bug self-test (test_extract_issues_who_uses_modem_usb_path_and_cdc_wdm) catches a copy-paste failure pattern flagged in PLAN; passing test proves the implementation builds WhoModem from modem.usb_path/cdc_wdm
- Plan 02-06: ActionKind enum extended with SET_OPERATING_MODE + FIX_AUTOSUSPEND (Rule 3 deviation) -- Phase 1 enum lacked these two cheap-action kinds the dispatcher registry references
- Plan 02-06: actions.dispatcher._REGISTRY is exactly six cheap-action kinds; Phase 4 destructive actions land by appending entries -- no dispatcher code change
- Plan 02-06: CarrierTable.lookup(mcc, mnc) iterates self.carriers (per-entry mcc/mnc per Phase 1 schema); shape-agnostic vs the plan's per-table-mcc example
- Plan 02-06: soft_reset.verify() returns VerifyResult.deferred(detail='next_cycle_observation') -- modem is rebooting, in-line read-back impossible; cycle driver and replay defer judgment
- Plan 02-06: fix_autosuspend uses Path.write_text('on') against sysfs_root -- no qmicli, no subprocess; tmp_path tests work cross-platform on Windows dev hosts
- Plan 02-06: per-action test files share tests/unit/actions/_helpers.py (RecordingEventLogger + make_ctx + canned ok/fail builders); each per-action file stays focused on argv-shape + outcome assertions
- Plan 02-06: test_registered_kinds_has_exactly_six_cheap_actions catches the deliberate duplicate-SET_APN bug planted in PLAN text -- frozenset comparison fails on silent-overwrite (which would otherwise still produce len==6)
- Plan 02-08: webhook/ subsystem (sign + dedup + dns + poster) ships HMAC over RAW PAYLOAD BYTES (PITFALLS §10.5) — sign_envelope returns (body_bytes, sig_header, ts_header) tuple so callers can NEVER re-serialise after signing
- Plan 02-08: Host-header DNS trick — URL embeds cached IP, Host header carries hostname for TLS SNI (W-02 / ADR-0011); spike-before-Phase-5 caveat documented in SUMMARY (httpx SNI derivation behaviour)
- Plan 02-08: WebhookPoster runs in a SEPARATE asyncio task (FR-44.8); enqueue is non-blocking (queue.put_nowait + counter increment); cycle driver never awaits delivery
- Plan 02-08: Bounded asyncio.Queue (default 100); 3-attempt retry with [1, 4, 16]s backoff; on exhaustion → webhook_delivery_total{result=dropped} + WebhookDropped(reason=retry_exhausted) event
- Plan 02-08: Drain (W-01) — pre-exit best-effort flush bounded at 3s default; failed-but-attempted items emit WebhookDropped(reason=drain_timeout); remainders post-budget emit reason=drain_budget_exhausted
- Plan 02-08: WebhookDropped Event variant added to events.jsonl union with kind="webhook_dropped"; reason is open string ({queue_full, retry_exhausted, drain_timeout, drain_budget_exhausted, no_dns, no_url}) — extensible without enum churn
- Plan 02-08: ClockProto + DnsCacheProto + EventLogWriterProto + MetricRegistryProto seams co-located in poster.py; FakeClock + FakeDNSResolver + RecordingEventLogger + RecordingMetrics satisfy all four without monkey-patching production code
- Plan 02-08: Test pattern -- _install_mock_transport(poster, handler) monkey-patches WebhookPoster._make_client to return AsyncClient(transport=httpx.MockTransport(handler)); avoids adding pytest-httpx dev dep (httpx ships MockTransport)
- Plan 02-08: BaseEventLoop.getaddrinfo patched (NOT AbstractEventLoop) -- AbstractEventLoop only stubs the abstract method; concrete SelectorEventLoop / ProactorEventLoop both inherit getaddrinfo from BaseEventLoop; one patch covers Linux + Windows dev hosts
- Plan 02-08: WebhookPoster.stop() public method added (Rule 2 deviation) -- Phase 3 SIGTERM wiring needs to stop the poster WITHOUT forcing drain (e.g. SIGKILL-imminent / OOM paths); drain() also calls stop() internally
- Plan 02-08: _StepClock pattern in test_drain_budget_exhausted_drops_remaining -- hand-rolled clock that handler advances per call replaces real-time asyncio.sleep; keeps test under 1s (M7 budget) AND lets drain's deadline check actually trip
- Plan 02-07: status_reporter ships StatusReport + MaintenanceWindow wire types + write_status_json wraps Phase 1 atomic_write_bytes (FR-41/FR-41.1/C-02)
- Plan 02-07: MetricRegistry single chokepoint enforces ADR-0013 (modem_state_value{modem} as integer-valued single Gauge, never one-hot); state label permitted only on state_duration_seconds histogram
- Plan 02-07: _UnixWSGIServer MRO (UnixStreamServer + WSGIServer) skips SO_REUSEADDR setsockopt for AF_UNIX; 0o660 socket mode + stale-socket unlink (PITFALLS §13.3)
- Plan 02-07: prom.py POSIX-guarded import (sys.platform != win32) so mypy --strict + pytest collection succeed on Windows dev hosts; UDS scrape tests skipif(win32)
- Plan 02-07: cycle_duration_seconds buckets (0.5,1,2,4,8,16,32) for M5 10s P99 budget; state_duration_seconds buckets [1,5,15,60,300,1800,7200,86400] verbatim per O-02
- Plan 02-07: GlobalsState.maintenance: MaintenanceWindow|None=None preserves Phase 1 backward-compat (Phase 1-shape globals.json without maintenance key parses cleanly)
- Plan 02-07: MetricRegistry takes registry: CollectorRegistry|None=None for test isolation (per-test isolated registry); production passes None and uses global REGISTRY for make_wsgi_app exposure
- Plan 02-07: RSS tripwire is event-only in Phase 2 (NFR-3); MetricRegistry.record_rss_tripwire increments daemon_self_health{kind=rss} but never raises/exits — Phase 3 sd_notify watchdog owns restart decision
- Plan 02-09: spark-modem CLI entry point in pyproject.toml [project.scripts]; six subcommands + ctl{history,maintenance,support-bundle}; argparse subparser dispatch keeps Phase 2 dependency-free
- Plan 02-09: cli/clients.py hosts FixtureRunner + _CliClock + _InventoryFromFile + _NoZaoTailer + build_default_settings — production code under src/ NEVER imports from tests/fakes/* (boundary discipline)
- Plan 02-09: ctl maintenance dual-clock expiry stored in globals.json (started/expires both monotonic AND ISO); status check uses now_mono >= expires_mono OR now_wall_iso >= expires_iso so NTP step in either direction cannot extend or prematurely expire the window (ADR-0007 spirit)
- Plan 02-09: 8h hard cap (MAX_DURATION_SECONDS=28800) enforced at the CLI BEFORE any state mutation; MaintenanceWindow.max_duration_seconds=Field(le=28800) catches hand-edited globals.json at load time
- Plan 02-09: ctl maintenance writes through StateStore.save_globals which acquires globals_lock (asyncio.Lock) + state_store_lockfile flock — no new lock surface (Claude's Discretion); daemon and CLI mutator serialize on the same flock per CLAUDE.md §12 + ADR-0012
- Plan 02-09: ctl support-bundle Phase 2 limitation — omits journalctl + dmesg outputs (subprocess required, would fail SP-04 lint gate); Phase 3 wires through subproc.run. Bundle still ships events + state + status + conf + metadata, sufficient for Phase 2 NOC use
- Plan 02-09: PII redaction is one-way and consistent (sha256[:8]) — same ICCID/IMSI → same <redacted:<8 hex>> across the bundle for cross-file identity correlation without exporting PII; HMAC secret never copied; webhook URL host-only
- Plan 02-09: ctl history reader handles plain rotated siblings (.1, .2, ...) AND gzipped (.1.gz, ...); oldest-first chronological output; corrupt JSONL lines skipped not raised — events.jsonl integrity is the writer's responsibility
- Plan 02-09: provision and reset CLI subcommands print Phase-2 stub messages — full execution requires daemon-style runner injection landing with cycle driver in plan 02-10 + Phase 3 production sysfs/zao. reset still validates action-kind correctness and rejects destructive actions before any dispatcher call
- Plan 02-10: CycleDriver is the integration point for every Phase 2 subsystem (observe -> policy -> actions -> persist -> status -> webhook); each pipeline phase isolated to its own helper for readability and Phase 3/4 extensibility
- Plan 02-10: per-modem QmiWrapper rebuilt per-dispatch from plan.who.usb_path -> cdc_wdm lookup against the cycle's inventory snapshot — single shared QmiWrapper would risk applying actions to the wrong modem
- Plan 02-10: NFR-11 isolation verified end-to-end — try/except Exception around policy.engine.run_cycle stores repr(exc) on RunCycleResult.policy_exception and continues with empty plans; status.json STILL written so consumers can detect a stuck daemon
- Plan 02-10: SC #5 webhook envelopes constructed inline in cycle_driver._enqueue_webhooks (HealthyToDegraded / RecoveringToExhausted / ActionFailedWebhook); DaemonRestart emitted ONCE at boot in daemon/main.py with DaemonStopReason.CRASH (Phase 3 swaps in SIGTERM via clean-shutdown marker)
- Plan 02-10: CycleScheduler.advance() ceiling-loops past now to avoid back-to-back hot-loops (PITFALLS §9.3); the no-op event_queue arm is sketched for Phase 3's udev/rtnetlink/inotify producers
- Plan 02-10: RSS tripwire is event-only in Phase 2 (T-02-10-05 mitigation) — records daemon_self_health{kind=rss} + WARNING log; Phase 3 sd_notify watchdog owns restart decision based on the counter
- Plan 02-10: gen_replay_fixtures.py uses ceiling-divide on per_fault count so --count 1000 produces >=1000 fixtures (1002 actual: 952 fault + 50 healthy); deterministic via random.seed(42) — same seed + count produces byte-identical fixtures for CI regenerability (T-02-10-04)
- Plan 02-10: replay verdict classifier R-02 partial order — 'safer' partial order: v2 picking cheaper than v1 is 'less-safe' ONLY when v1 picked destructive AND v1_succeeded; v1_succeeded=False/None means cheaper is at-least-as-good ('safer')
- Plan 02-10: restart_mid_streak fixtures hand-authored (generator does not synthesise daemon-restart scenarios); two-fixture pre/post + JSON round-trip simulates restart and proves FR-26.1 streak persistence end-to-end
- Plan 02-10: Phase 2 EXIT GATE PASSED — 100% (952/952) fault-cycle agreement with v1; replay-summary.json gitignored (T-02-10-03); full pytest suite 1675 tests in 11.82s (well under M7 30s)
- Plan 03-01: WakeSignal closed StrEnum (E-02) — 5 sources locked (UDEV/RTNETLINK/ZAO_LOG/EVENTS_LOG_ROTATED/KMSG); state derives from re-observation, queue carries opaque sentinels only (ADR-0002)
- Plan 03-01: restart_on_crash supervisor (E-01) — bounded backoff (1,2,4,8,60) cap + Pitfall 15 attempt-counter reset after >=300s clean uptime; CancelledError passthrough; logger.exception only in 03-01 (Plan 03-06 wires structured event_source_crashed emission, T-03-01-06 accepted threat)
- Plan 03-01: Sleeper Protocol (PITFALLS §14.1) — production wires asyncio.sleep adapter, tests inject FakeSleeper that advances FakeClock and yields control; runtime_checkable so isinstance(fake, Sleeper) works in contract tests
- Plan 03-01: IssueDetail extended 34→40 with 6 host-level kmsg values (USB_OVERCURRENT/USB_ENUM_FAILURE/THERMAL_THROTTLE/QMI_WWAN_PROBE_FAIL/TEGRA_HUB_PSU_DROOP/UNKNOWN); USB_OVERCURRENT distinct from per-modem ENUMERATION_OVERCURRENT (W-04 closed-enum discipline) — pinned by contract test
- Plan 03-01: FakeAsyncinotify async-iterable + FakeMask IntFlag + FakeInotifyEvent dataclass — depended on by Plans 03-04 (zao_log + events.jsonl rotation) and 03-06 (lifecycle integration); same dual-surface pattern as Phase 2 FixtureZaoTailer (production Protocol + test-only inject_event mutator)
- Plan 03-01: linux_only pytest marker registered once in pyproject.toml [tool.pytest.ini_options].markers — Plans 03-02..03-06 (~14 test files) reference it without re-registering
- Plan 03-02: pyudev.Monitor.from_netlink + loop.add_reader is the sole USB subscription path; producer body is signals-only (action filter forwards add/remove/bind/unbind for VID=1199 only); MonitorObserver never imported (PITFALLS §7.1 PRESCRIPTIVE)
- Plan 03-02: pyudev import deferred inside _build_default_monitor() so the module is Windows-importable; tests inject FakeUdevMonitor and never trigger the real import; same pattern Plans 03-03/04 will adopt for pyroute2/asyncinotify
- Plan 03-02: UdevInventory uses composition over inheritance — holds a SysfsInventory and delegates scan(); Plan 03-06 daemon swap is one line (SysfsInventory→UdevInventory); observer/cycle_driver/cli/diag don't change
- Plan 03-02: derive_ns option-(a) — sysfs symlink at <usb_dev>/.../net/wwan*/device/ns/net resolved against /var/run/netns by stat().st_ino; bench Jetson single-namespace yields None; subprocess-free (PITFALLS §6.2: never setns from asyncio loop)
- Plan 03-02: QmiWrapper(ns: str|None=None) defaults to None for backwards compat; every existing qmicli method routes through self._argv() helper; 11-method parameterized test + count-pin assertion catches Phase 4 destructive method bypass
- Plan 03-02: cycle_driver.py qmi_factory + per-action QmiWrapper construction + cli/diag.py qmi_factory now pass ns=descriptor.ns; ns_by_usb dict mirrors cdc_by_usb shape; bench Jetson with ns=None is no-op
- Plan 03-02: _make_on_readable factored as module-level closure factory so unit tests exercise classification + drain logic directly (cross-platform); one POSIX-only test verifies loop.add_reader/remove_reader lifecycle through os.pipe() pair
- Plan 03-03: rtnetlink producer ships with tight read loop body (PITFALLS §6.1 PRESCRIPTIVE) —  ONLY, no parsing/no logging/no state; 4 MiB SO_RCVBUF (16x kernel default) absorbs USB hub PSU droop storms
- Plan 03-03: ENOBUFS escapes the producer to the supervisor — restart_on_crash (Plan 03-01) catches Exception and re-enters the factory which constructs a fresh AsyncIPRoute() (close+reopen recovery prescribed); catching ENOBUFS in the producer would silently exhaust the kernel buffer
- Plan 03-03: pyroute2 imports deferred (mirrors Plan 03-02 pyudev pattern) —  lives inside  and  lives inside the run_rtnetlink_producer body; tests inject ipr_factory tuple, never trigger the real imports; module imports cleanly on Windows dev hosts
- Plan 03-03: ipr_factory is  — preconstructed (FakeAsyncIPRoute, groups_constant) tuple injection is lighter than callable factory currying; production wires None and constructs both objects internally
- Plan 03-03: FakeAsyncIPRoute exposes asyncore.socket.setsockopt as a recording surface via _FakeAsyncoreHolder + _FakeSocket; production setsockopt access uses defensive getattr chain so tests can record calls without monkey-patching pyroute2 internals
- Plan 03-03: pyproject.toml mypy override extended — module list is now ['sdnotify', 'asyncinotify', 'pyudev', 'pyroute2', 'pyroute2.netlink']; both pyroute2 modules added because they are imported via two separate from-statements
- Plan 03-03: rtnetlink producer body is exactly put_nowait WakeSignal.RTNETLINK ONLY (PITFALLS 6.1 PRESCRIPTIVE) — no parsing, no logging, no state; 4 MiB SO_RCVBUF 16x kernel default absorbs USB hub PSU droop storms
- Plan 03-03: pyroute2 imports deferred mirroring Plan 03-02 pyudev pattern — from pyroute2 import AsyncIPRoute lives inside _build_default_ipr and from pyroute2.netlink import rtnl lives inside run_rtnetlink_producer body; tests inject ipr_factory tuple and never trigger real imports; module imports cleanly on Windows dev hosts
- Plan 03-03: ipr_factory is a tuple of AsyncIPRoute-like object plus groups_constant defaulting to None — preconstructed FakeAsyncIPRoute plus groups_constant tuple injection is lighter than callable factory currying; production wires None and constructs both objects internally
- Plan 03-04: ZaoLogInotifyTailer dual-mode (FR-43.1) — copytruncate detected via st.st_size < self._last_offset; opportunistic inode compare via st.st_ino != self._last_inode; create-mode handled via MOVE_SELF/DELETE_SELF reset → CREATE/MOVED_TO basename match → re-stat + re-parse. Reuses ZaoLogParser via composition (snapshot is idempotent against current file)
- Plan 03-04: single supervised asyncinotify producer (R-01) watches events.jsonl parent + Zao log parent + Zao log file; dispatches by event.watch handle identity to two consumers (EventLogReopener + ZaoLogInotifyTailer). Three orthogonal mask booleans (modify/move-or-delete/create-or-moved-to) extracted at producer boundary so consumer code path runs identically against FakeMask + real Mask
- Plan 03-04: EventLogWriter extended with reopen() + _reopen_buffer (deque maxlen=1000) + _reopening flag + reopen_overflow_count read-only property (R-03). Logrotate fd swap is microsecond-fast in happy path; buffer is defense for disk-full/EPERM pathological case. _REOPEN_BUFFER_MAX module constant; bounded ~500 KiB worst case. Plan 03-06 wires reopen_overflow_count into events_dropped_total{reason=reopen_overflow}
- Plan 03-04: tailer pushes WakeSignal.ZAO_LOG itself (consumer owns wake-signal semantics because it has internal state); producer pushes WakeSignal.EVENTS_LOG_ROTATED directly because EventLogReopener has zero state. Two-consumers, two-shapes: producer dispatches; consumers push wake signals
- Plan 03-04: deferred WakeSignal import inside zao_log/inotify_tailer.py:_zao_wake_signal() avoids circular import event_sources/supervisor.py to zao_log/. _InotifyProto Protocol co-located in asyncinotify_producer.py types the async-context-manager + add_watch + async-iterable surface; FakeAsyncinotify satisfies structurally without inheritance
- Plan 03-05: kmsg classifier locks 5 closed-enum IssueDetail values via test contract gate (test_kmsg_patterns_table_size_locked_at_5) — adding a 6th regex requires deliberate edits to enum + table + count assertion; per CONTEXT.md Deferred Ideas catalog growth lands via ADR or Phase 4 follow-up
- Plan 03-05: KmsgDedup mirrors webhook/dedup.py shape with key=IssueDetail and default window=30s (LOCKED per CONTEXT.md E-03); semantics flipped vs is_deduped — should_emit returns True on EMIT for caller readability
- Plan 03-05: re.IGNORECASE on all 5 KMSG_PATTERNS regexes — RESEARCH.md cited capital 'USB' but real Linux kernel writes lowercase 'usb 1-3.1:'; bench-Jetson regex iteration per CONTEXT.md 'Claude's Discretion' since enum values are LOCKED but regex strings are data
- Plan 03-05: EPIPE handled inside drain loop (NOT escaped to supervisor like rtnetlink ENOBUFS) — semantics differ: EPIPE on /dev/kmsg means kernel ring buffer wrapped (just keep reading at new tail); ENOBUFS on rtnetlink means socket buffer overflow (close+reopen); per-error-code semantics matter
- Plan 03-05: fd_factory tuple injection (production wires None and opens /dev/kmsg lazily; tests pass sentinel fd + fake.read) — same testable-defaults pattern as ipr_factory (Plan 03-03) and inotify_factory (Plan 03-04); module imports cleanly on Windows dev hosts
- Plan 03-05: test path uses loop.call_soon (vs production loop.add_reader) — fake fd is a sentinel value not registered with OS event loop; ProactorEventLoop on Windows would error on add_reader(99, ...); both paths exit via the same finally cleanup
- Plan 03-06: EventSourceCrashed (Issue #7) + SimSwapped (Issue #8) wire variants — supervisor emits structurally on producer crash via event_logger.append (Open Question 2 RESOLVED); SimSwapped iccid_hash_old/new pinned sha256[:8] (8 chars); error_message capped max_length=200 (T-03-06-07)
- Plan 03-06: SigtermChoreography 8-step strict ordering (cancel cycle → cancel producers → drain → emit DaemonStopped → stop webhook → unlink metrics socket → write marker); per-step try/except (NFR-11); deadline budget 5s with min(deadline_remaining, 3.0) drain cap
- Plan 03-06: SighupSwapper transactional swap — RELOAD_RESTART field changes refused (returns False, keeps old); RELOAD_DATA-only changes applied via atomic ref swap; DnsCache force-refresh on webhook_url change; cycle driver reads self._settings once per cycle so swap is naturally cycle-boundary atomic
- Plan 03-06: WATCHDOG cycle-end placement (Issue #5 / PITFALLS §4.1) regression-gated by test_watchdog_kicks_after_cycle_completion — recording status_reporter and recording sd_notify share call_order list; assert write_status_json index < watchdog_kick index
- Plan 03-06: L-04 boot classifier marker precedence (CONFIG_INVALID > SIGTERM > CRASH); corrupt JSON in clean-shutdown still classifies SIGTERM with uptime fallback to 0.0 (the marker existed; the daemon DID emit it); markers unlinked after read so next boot starts clean
- Plan 03-06: PID lock built on top of state_store.locks.acquire_flock at run_dir/lock — third file separate from state.lock and modem-{usb_path}.lock per ADR-0012; StateStoreLocked translated into PidLockHeldError; FakePIDLock asyncio.Lock-backed for cross-platform tests (production POSIX flock, kernel-released on death)
- Plan 03-06: main.py production path is a SCAFFOLD — argparse + preflight + marker classify + PID lock + SdNotifyLifecycle construction land today; TaskGroup body spawning 5 supervised producers + cycle loop + 2 signal watchers documented inline; full wiring lands Plan 03-09 integration suite. WATCHDOG cycle-end placement asserted by Plan 03-06 unit test today.
- Plan 03-06: --laptop CLI flag preserves Phase 2 single-cycle wiring path; build_default_settings + _NoZaoTailer + _InventoryFromFile fakes survive in cli.clients for backwards-compat with Phase 2 integration tests
- Plan 03-07: StateStore.reset_modem_streak_and_counters public async method — resets healthy_streak=0 + counters={} in ONE atomic write per RECOVERY_SPEC §8 (Issue #9); per-modem asyncio.Lock + flock (FR-61.1 / ADR-0012); preserves all OTHER ModemState fields; brand-new-modem path constructs fresh shell
- Plan 03-07: cycle_driver._detect_and_handle_sim_swaps inserts AFTER observation AND BEFORE policy.engine.run_cycle (T-03-07-05) so the engine reads post-reset ModemState; pipeline order is save_identity_map -> reset_modem_streak_and_counters -> event_logger.append (T-03-07-03); ICCID values sha256[:8]-redacted in SimSwapped event payload (T-03-07-02; Issue #8: NEVER logger.info)
- Plan 03-07: ModemSnapshot extended with identity_iccid + identity_imsi optional fields (18-22 / 14-15 digit patterns matching wire/identity.Identity); observer/issue_extractor surfaces both from existing GetSimStateResult parser; empty-string parser output collapses to None at observer boundary so transient SIM states (PIN required, app not detected, error) don't trigger false-positive SimSwapped events
- Plan 03-07: did NOT extract _load_modem_state_unlocked / _save_modem_state_unlocked private helpers (plan called this OPTIONAL); reused existing _save_modem_state_locked private helper; new method's read side is 3-line inline (target.read_bytes + json.loads + ModemState.model_validate); kept diff to store.py minimal at +44 LOC
- Plan 03-08: U-01..U-05 systemd unit hardening + R-02 logrotate + 20-test cross-platform audit gate; CAP_NET_ADMIN+CAP_SYS_ADMIN+CAP_SYS_MODULE+CAP_DAC_READ_SEARCH preallocated for Phase 4; WatchdogSec=90s with cycle-end kicks (Plan 03-06 Issue #5); StartLimit overrides prevent fleet-bricking (PITFALLS §4.2); RuntimeDirectoryPreserve=yes load-bearing; ExecStartPre=spark-modem ctl config-check pre-flight gate (subcommand body deferred to Plan 03-09)
- Plan 03-08: NFR-30 User=root + NoNewPrivileges=yes (Phase 3+ needs CAP_NET_ADMIN on udev/pyroute2, Phase 4 needs CAP_SYS_ADMIN/CAP_SYS_MODULE on usb_reset/driver_reset); replaces Phase 1 spark-modem-watchdog non-root user (postinst cleanup deferred to Phase 4)
- Plan 03-08: R-02 empty postrotate is deliberate one-signal-per-concern decision; logrotate handles POSIX rotation, daemon handles fd swap via asyncinotify (Plan 03-04 EventLogReopener); debhelper dh_installlogrotate auto-picks debian/spark-modem-watchdog.logrotate (no debian/rules change needed)
- Plan 03-09: integration test tier scaffold (tests/integration/__init__.py + conftest.py) uses per-module pytestmark NOT pytest_collection_modifyitems auto-marker (Issue #6 RESOLVED stays consistent — Plan 03-08's test_unit_file_audit.py runs cross-platform; auto-marker would have broken it)
- Plan 03-09: SC #1..#5 lifecycle tests in test_lifecycle.py via Fake* injection (FakeRunner + FakeClock + FixtureInventory + FakeSdNotify + FakePIDLock); SC #3 SIGTERM uses asyncio.Event.set() NOT os.kill — production code path is identical (loop.add_signal_handler sets the same Event); avoids cross-platform real-signal issues. Real-signal verification deferred to Phase 4 HIL
- Plan 03-09: real-logrotate cron exercise in test_logrotate_create.py wraps subprocess.run in asyncio.to_thread (ASYNC221); per-test pytest.mark.skipif on /usr/sbin/logrotate presence so Linux dev hosts without the binary skip cleanly; tests/ tier is SP-04-exempt for direct subprocess.run usage
- Plan 03-09: Phase 3 EXIT — bench-Jetson SC #1/#3/#4/#5 hardware verification deferred to Phase 4 HIL via approved-with-deferral resume signal (hardware not accessible at Phase 3 exit; integration scaffold + linux_only suite + unit-file audit all green at 1835 pass / 88 skip / 0 fail in 17.94s); WatchdogSec=90s actual-fire under deliberate qmicli wedge already deferred per CONTEXT.md
- Plan 03-09: Phase 3 status COMPLETE — 9/9 plans shipped; integration tier established as the regression-gate substrate for Phase 4 destructive-action lifecycle tests + Phase 5 shadow-mode no-regression contract
- Plan 04-01: ActionKind.MODEM_RESET registered as ladder rung 2 destructive action; same dms_set_operating_mode('reset') verb as soft_reset (CONTEXT A-01 policy distinction); deferred-verify shape per A-04; dispatcher registry size 6→7; cli/reset.py guard wording rewritten kind-agnostic 'is not registered; valid: ...'.
- Plan 04-01: cross-plan test rename convention encoded in test names — _seven_kinds (this plan) → _eight_kinds (04-02) → _nine_kinds (04-03). Wave ordering guarantees correctness at each plan's commit time; greppable across the codebase.
- Plan 04-01: pivoted test_dispatch_unknown_kind_returns_failure probe MODEM_RESET → USB_RESET (Rule 1 deviation — cascading test missed by planner); Plans 04-02/04-03 will rotate again.
- Plan 04-06: HIL workflow uses [self-hosted, linux, ARM64, hil-bench] label specialisation; ci.yml's [self-hosted, linux, ARM64] is the analog. Bench Jetson is the only physical runner that picks up HIL jobs. Serial concurrency via group: hil-bench / cancel-in-progress: false; never two simultaneous fault-injection sessions.
- Plan 04-06: trigger discipline against T-04-06-01 — hil.yml uses ONLY schedule (cron 0 4 * * *) + workflow_dispatch; explicitly NOT pull_request_target (would expose CAP_SYS_MODULE on bench Jetson to fork PR authors).
- Plan 04-06: 7 module-level async fault-injection helpers (sim_power_off/on, qmi_proxy_kill, kmsg, offline/online, thermal_critical) — software-only per CONTEXT D-02 (NO real RF detuning hardware). tests/ tier is SP-04-exempt; direct subprocess.run is the canonical pattern for fault injection.
- Plan 04-06: ASYNC240 fix in fault_inject.py:inject_kmsg — _KMSG.exists() and _KMSG.write_text() wrapped in asyncio.to_thread (pathlib methods on async functions are blocking I/O; ruff ASYNC240 enforces this). Plan 04-07 scenarios will follow the same pattern.
- Plan 04-06: v1-30d trace directory ships .gitkeep + .gitattributes (*.json + *.jsonl LFS) + README today; actual JSON shards land via git lfs track + commit when first quarterly refresh produces real fixtures. README's redaction contract is verbatim sha256[:8] hash (deterministic per identity) — same shape as Plan 02-09's ctl support-bundle.
- Plan 04-06: pyproject.toml NOT modified — hil pytest marker already registered at line 78 (Plan 03-01 era). PATTERNS correction #3 honored.
- Plan 04-02: usb_reset is sysfs file I/O via new src/spark_modem/sysfs/ package -- Path.write_text only, NO subprocess (CLAUDE.md A-02 verbatim); SP-04 lint scope unchanged
- Plan 04-02: PATTERNS correction #4 applied -- IssueCategory.ENUMERATION does NOT exist in wire/enums.py; SIERRA_BOOTLOADER lives under IssueCategory.QMI (decision-table row qmi/sierra_bootloader -> usb_reset)
- Plan 04-02: --target=parent-hub argparse choices flag (RESEARCH Q9) over --parent-hub boolean -- self-documenting --help, type-checkable, extends to additional variants without script breakage
- Plan 04-02: ActionContext gains target: Literal['child-port', 'parent-hub']='child-port' field -- read only by usb_reset; backwards-compat preserved (every other action ignores it); engine swaps via dataclasses.replace
- Plan 04-02: dispatcher contract test rename _seven_kinds -> _eight_kinds + unknown-kind probe rotation USB_RESET -> DRIVER_RESET; cross-plan test convention continues 04-01->04-02->04-03
- Plan 04-03: driver_reset is two subproc.run calls (modprobe -r qmi_wwan + modprobe qmi_wwan) flowing through subproc.runner -- SP-04 lint clean; PATTERNS correction #1 honored (subproc_run direct module import; ActionContext has no runner field)
- Plan 04-03: _global_driver_reset_eligible 4-gate predicate replaces Phase 2 placeholder -- thermal -> cooldown -> 75% denominator -> actionable-signal; first-fire (None last_driver_reset_monotonic) handled via explicit is-not-None guard; PROXY_DIED does NOT bypass 75% gate (C-02 user deviation)
- Plan 04-03: 4 RELOAD_DATA Settings fields land (multi_modem_threshold_fraction=0.75, expected_modem_count=4, global_driver_reset_backoff_seconds=3600, modprobe_timeout_seconds=30); expected_modem_count is RELOAD_DATA not RELOAD_RESTART because cycle driver re-reads it per cycle; signal-floor fields read defensively via getattr until Plan 04-04 lands them in Settings
- Plan 04-03: dispatcher contract concludes cross-plan rename convention -- _seven_kinds (04-01) -> _eight_kinds (04-02) -> _nine_kinds (04-03); unknown-kind probe rotated to a synthetic non-ActionKind sentinel since every legitimate ActionKind is now registered
- Plan 04-04: select_rung uses base parameter (not category) -- engine has already done lookup_action so the BASE ActionKind is in hand; this preserves DATAPATH base-rung-2 semantics ((DATAPATH, SESSION_DISCONNECTED) -> base MODEM_RESET; ladder starts at MODEM, never walks back to SOFT)
- Plan 04-04: legacy ModemState.last_action_monotonic preserved on the wire shape AND bumped atomically -- back-compat contract for Phase 2 state-file replay; locked by test_engine_atomically_bumps_legacy_and_per_kind_timestamps; future engineer must NOT delete the legacy bump as dead code
- Plan 04-04: non-ladder ActionKinds (SET_APN, FIX_RAW_IP, SIM_POWER_ON, FIX_AUTOSUSPEND, SET_OPERATING_MODE, DRIVER_RESET) pass through select_rung unchanged -- only the destructive triplet (SOFT/MODEM/USB_RESET) escalates
- Plan 04-04: engine collapses ladder dispatch to one rebind (action_or_skip = select_rung(...)) -- existing isinstance(ActionKind | str) Step-6 dispatch handles both shapes; ruff PLR0912 satisfied without extracting a helper
- Plan 04-04: SP-04 lint regex literally matches docstring text -- avoid spelling out forbidden tokens (create_subprocess_exec etc.) in docstrings; reword to abstract phrasing like 'kernel-touching primitives'
- Plan 04-05: SkipReason closed StrEnum (7 values: signal_below_gate / ladder_backoff / same_action_backoff / exhausted / disconnected / maintenance / dry_run) -- adding a new gate-failure mode is a deliberate enum extension, never a runtime string (W-04 discipline)
- Plan 04-05: dual-emit at gate-failure path -- ActionSkipped event AND PlannedAction.suppressed_* flags both emitted on every soft-skip / hard-skip path; replay harness reads suppressed_* flags from Phase 2 fixtures unmodified (CONTEXT B-04 'back-compat horizon' decision; no shim needed)
- Plan 04-05: decision-table-level skip strings (skip:requires_human / skip:no_card / skip:hardware / skip:carrier_denied) NOT mapped to SkipReason -- they are upstream of the gate machinery; SkipReason is for GATE-failure paths only (CONTEXT B-04 threat T-04-05-05 disposition: accept). The existing PlannedAction with reason='skip:requires_human' remains the audit trail
- Plan 04-05: ladder skip:exhausted (Plan 04-04 select_rung output) emits ActionSkipped(reason=EXHAUSTED) using the BASE action (pre-ladder) as suppressed_action -- captured via base_for_ladder local before select_rung rebinds; consumer-facing semantics: 'we tried to fire SOFT_RESET but the entire ladder is exhausted', not 'we tried to fire skip:exhausted'
- Plan 04-05: EventLogWriter._EVENT_TYPES gap-closure (Rule 2) -- pre-existing gap for SimSwapped + EventSourceCrashed since Phase 3 closed at the same time as adding ActionSkipped; production daemon would have raised TypeError on first emission of either variant in a real (non-fake) event_logger. Tuple now covers the full 14-variant Event union
- Plan 04-07: 12 HIL scenarios authored under tests/hil/scenarios/ (7 SC#4 + 4 Phase-3 piggyback + 1 destructive-actions end-to-end), each gated linux_only+hil+skipif(win32)+asyncio; conftest's collect_ignore_glob blocks Windows collection, scenarios collect on the [self-hosted, linux, ARM64, hil-bench] runner only.
- Plan 04-07: tests/property/ tier created net-new (PATTERNS correction #6) with __init__.py + conftest.py + test_destructive_idempotency.py -- 5 hypothesis tests for modem_reset/usb_reset/driver_reset back-to-back idempotency against fakes; conftest auto-marks every property test with 'unit' so the CI filter pytest -m 'unit or integration' picks them up without each test author needing to decorate.
- Plan 04-07: replay-harness 30-day gate wired by invoking Plan 02-10's pytest harness (tests/replay/) directly -- the conftest.pytest_sessionfinish R-03 hard-fail at <0.95 fault-cycle agreement subsumes the plan's hypothetical tools.replay_harness CLI shape (which does not exist in this project). Verbatim references to tools.replay_harness, 0.95, and tests/fixtures/replay/v1-30d preserved in workflow step docstring for auditable greppable criteria.
- Plan 04-07: 5-of-12 scenarios import fault_inject helpers; the other 7 test paths the helper toolkit doesn't cover (systemctl restart/stop, spark-modem reset CLI, modprobe direct, ctl reset-state, os.kill SIGSTOP+pgrep). The plan's '>=10 scenarios use fault_inject' criterion was over-aspirational; semantic coverage is correct.
- Plan 04-07: Phase 4 EXIT bench-Jetson human-verify checkpoint auto-approved under --auto mode (workflow._auto_chain_active=true). Bench-Jetson hardware verification deferred to first nightly HIL run post-merge; Phase 4 EXIT contingent on first green nightly run of .github/workflows/hil.yml (all 12 scenarios + replay-harness >=95% gate).
- Plan 04-07: ASYNC240 + ASYNC109 + SIM105 + RUF100 lint sweep across all 12 HIL scenarios (Rule 3 Blocking) -- pathlib methods on async functions wrapped in asyncio.to_thread; timeout= renamed to timeout_s=; try/except/pass replaced with contextlib.suppress; obsolete # noqa: BLE001 directives removed (BLE rules not in this project's ruff selectors).

### Pending Todos

None yet.

### Blockers/Concerns

None yet — all eight PROJECT.md open questions (Q1-Q8) have a research-recommended answer to be ratified as ADRs in Phase 1.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| Phase 4 HIL | Bench-Jetson SC #1/#3/#4/#5 hardware verification (real EM7421s on USB hub 2-3.1.{1..4}, real qmi_wwan reload, real cross-process flock concurrent ctl reset-state, real systemd Type=notify SIGTERM ≤5s) — integration scaffold + linux_only suite + unit-file audit all green; only true hardware-loop verification deferred. WatchdogSec=90s actual-fire also deferred per CONTEXT.md. | **Folded into Plan 04-07 HIL scenario suite (CONTEXT D-04)** — 4 scenario files authored under tests/hil/scenarios/ (test_qmi_wwan_reload_clean_transition.py, test_sigterm_within_5s.py, test_ctl_reset_state_serialisation.py, test_watchdog_90s_actual_fire.py); scenarios collect on the [self-hosted, linux, ARM64, hil-bench] runner; **resolution pending first nightly HIL run on the bench Jetson** | Phase 03 exit gate; piggyback now landed in Plan 04-07 |
| Phase 4 EXIT | First nightly green run of `.github/workflows/hil.yml` on the bench Jetson with all 12 HIL scenarios passing AND replay-harness 30-day fault-cycle agreement >=95% | Awaiting bench-Jetson runner online + Git LFS auth configured + first nightly trigger; bench-Jetson human-verify checkpoint auto-approved under --auto mode 2026-05-10 | Plan 04-07 (Task 3 checkpoint) |

## Session Continuity

Last session: --stopped-at
Stopped at: Phase 5 context gathered
Resume file: --resume-file

**Planned Phase:** 04 (destructive-actions-hil) — 7 plans — 2026-05-10T09:43:20.063Z
**Phase 2 status:** ✅ COMPLETE — all 10 plans shipped, replay harness 100% v1 agreement, 1675-test suite green in 11.82s
**Phase 3 status:** ✅ COMPLETE — all 9 plans shipped; integration tier scaffold + SC #1..#5 lifecycle tests + real-logrotate cron exercise + cross-platform unit-file audit; 1835 unit + integration tests green in 17.94s on Windows dev host (M7 30s budget preserved)
**Plan 03-09 status:** ✅ COMPLETE — approved-with-deferral

- Task 1 ✅ commit f5079e9 — integration scaffold + SC #1..#5 lifecycle tests
- Task 2 ✅ commit f00b13c — real logrotate cron exercise (FR-43 / R-02)
- Task 3 ✅ resolved — bench-Jetson SC verification deferred to Phase 4 HIL ticket (see Deferred Items table)

**Next:** Phase 4 (Destructive Actions & HIL) — /gsd-plan-phase 4 to scope soft_reset/modem_reset/usb_reset/driver_reset destructive actions + HIL CI lane + bench-Jetson SC #1/#3/#4/#5 verification piggyback
