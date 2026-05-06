---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Completed 02-05-PLAN.md
last_updated: "2026-05-06T16:45:35.547Z"
last_activity: 2026-05-06
progress:
  total_phases: 7
  completed_phases: 1
  total_plans: 17
  completed_plans: 11
  percent: 65
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-05)

**Core value:** Maximize end-user uplink availability across the four bonded modems by applying minimum-impact recovery actions — and never running a destructive recovery that has zero chance of fixing the observed issue.
**Current focus:** Phase 02 — core-daemon-laptop-testable

## Current Position

Phase: 02 (core-daemon-laptop-testable) — EXECUTING
Plan: 5 of 10
Status: Ready to execute
Last activity: 2026-05-06

Progress: [███████░░░] 65%

## Performance Metrics

**Velocity:**

- Total plans completed: 7
- Average duration: -
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 7 | - | - |

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

### Pending Todos

None yet.

### Blockers/Concerns

None yet — all eight PROJECT.md open questions (Q1-Q8) have a research-recommended answer to be ratified as ADRs in Phase 1.

## Deferred Items

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| *(none)* | | | |

## Session Continuity

Last session: 2026-05-06T16:45:35.532Z
Stopped at: Completed 02-05-PLAN.md
Resume file: None

**Planned Phase:** 2 (Core Daemon (laptop-testable)) — 10 plans — 2026-05-06T15:16:01.546Z
