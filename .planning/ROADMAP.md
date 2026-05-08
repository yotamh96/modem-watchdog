# Roadmap: spark-modem-watchdog v2

## Overview

`spark-modem-watchdog` v2 is a from-scratch Python rewrite of an in-production
bash toolchain that keeps a fleet of NVIDIA Jetson Orin NX bonded-uplink boxes
online by recovering misbehaving Sierra EM7421 modems with the smallest action
that has a chance of fixing the issue. v1 currently keeps a real fleet online,
so v2 must prove itself in shadow mode before replacing v1 on any box.

The roadmap is organized as **four build phases** (1-4) that produce the
software, followed by **three delivery phases** (5-7) that map onto the
pre-authored `docs/MIGRATION.md` rollout contract (bench shadow → field shadow
→ field live → 10% canary → 100% rolling → v1 decommission).

Phase 1 resolves the eight open questions (PROJECT.md Q1-Q8), lands the six
new ADRs (0008-0013) that the research surfaced, amends the five existing
ADRs that the state-machine refactor / packaging / metric-cardinality findings
ripple into, and ships a working `.deb` packaging pipeline as a hard exit
gate. Phase 2 builds the laptop-testable core (asyncio cycle, policy engine,
status/Prom/webhook surface). Phase 3 adds Linux event sources and lifecycle
plumbing (udev / rtnetlink / inotify / dmesg / sd_notify / SIGHUP / SIGTERM /
PID-lock / per-modem flocks). Phase 4 wires up destructive actions and the
HIL fault-injection lane. Phases 5-7 are the rollout.

Granularity is `standard`. Phase 1 corresponds to MIGRATION.md Phase 0 (build
+ HIL); Phase 5 to MIGRATION 1+2 (bench + field shadow); Phase 6 to MIGRATION
3+4+5 (one box live + canary + 100%); Phase 7 to MIGRATION 6 (decommission).

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundations & ADRs** ✅ 2026-05-06 - Resolve open questions, land 6 new + 5 amended ADRs, ship `.deb` pipeline, lock wire types (build A "plumbing")
- [x] **Phase 2: Core Daemon** ✅ 2026-05-06 - Laptop-testable asyncio cycle, policy engine, status/Prom/webhook surface (build B "minimal cycle" + C "status+metrics")
- [ ] **Phase 3: Linux Event Sources & Lifecycle** - udev/rtnetlink/inotify/dmesg, sd_notify, signal handling, PID-lock, per-modem flocks (build D + E)
- [ ] **Phase 4: Destructive Actions & HIL** - soft/modem/usb/driver_reset wired up, signal-gate end-to-end, qmi-proxy crash recovery, HIL CI lane (build F)
- [ ] **Phase 5: Bench & Field Shadow** - MIGRATION Phases 1+2: dry-run alongside v1 on bench Jetson, then on one field box; fault-cycle agreement ≥95%
- [ ] **Phase 6: Cutover & Fleet Rollout** - MIGRATION Phases 3-5: one box live → 10% canary → 100% rolling; meet M1-M7 success metrics
- [ ] **Phase 7: v1 Decommission & Archive** - MIGRATION Phase 6: purge v1 packages, archive scripts, update agent docs

## Phase Details

### Phase 1: Foundations & ADRs

**Goal**: Lock the wire formats, packaging story, ADR set, and
plumbing skeleton so that no Phase 2 module is ever built against a wire
type that needs to change. By exit, a `.deb` containing CPython 3.12 and
all 10 runtime libs installs cleanly on a real Jetson, every open question
from PROJECT.md is closed by an ADR or explicit deferral, and the `wire/`,
`config/`, `clock/`, `subproc/`, `state_store/`, `event_logger/` modules
exist with mypy --strict and ruff green in CI.

**Depends on**: Nothing (first phase)

**Requirements**:
FR-30.1, FR-33.1, FR-44.1, FR-44.2, FR-54, FR-60, FR-62, FR-62.1, FR-63,
FR-64, FR-72, FR-73,
NFR-31, NFR-32, NFR-33, NFR-34, NFR-40, NFR-41, NFR-43, NFR-50, NFR-51,
NFR-52

**Success Criteria** (what must be TRUE):
  1. The arm64 `.deb` builds in CI from a checked-in `requirements.lock`
     (uv pip compile output) and, when installed on a fresh Jetson Orin NX
     running JetPack 5.1.5 / Ubuntu 20.04, all 10 pinned runtime libraries
     (`pydantic`, `pydantic-settings`, `PyYAML`, `prometheus-client`,
     `pyudev`, `pyroute2`, `asyncinotify`, `httpx`, `sdnotify`, `psutil`)
     import successfully under the bundled
     `/opt/spark-modem-watchdog/python/bin/python3.12`.
  2. All eight PROJECT.md open questions (Q1-Q8) are closed in writing:
     six new ADRs (0008 state-machine, 0009 usb_path keying, 0010 packaging,
     0011 webhook subsystem, 0012 concurrency, 0013 metric surface) are
     merged, and ADRs 0001/0003/0004/0005/0006 carry the research-derived
     amendments (CPython bundle, Zao parser surface bound, schema downgrade
     non-destructive, 5+2 state shape supersedes 7-state, atomic streak
     ordering pinned).
  3. The default carrier table at `/etc/spark-modem-watchdog/conf.d/00-carriers.yaml`
     covers Israel (MCC 425 / Partner / Cellcom / Pelephone) plus US (310/410,
     311/480, 312/530), UK (234/10, 234/15, 234/30), DE (262/01, 262/02,
     262/03) marked `unverified: true`; YAML parses against pydantic
     validators with hostile-input fixtures (Norway problem, leading-zero
     MNCs, `mnc: str` regex `^\d{2,3}$`).
  4. `mypy --strict`, `ruff check`, `ruff format --check` are green on the
     `clock/`, `subproc/`, `wire/`, `config/`, `state_store/`, `event_logger/`
     modules; the `wire/` package defines all closed enums, tagged-union
     `who` types, and `Diag`/`PlannedAction`/`StateTransition` pydantic
     models with `schema_version: int` enforcement and non-destructive
     downgrade behavior (`*.from-v<N>.json` shadow, `schema_downgrade_pending`
     log line); `grep -r 'subprocess.run\|os.system' src/` outside `subproc/`
     returns zero matches.
  5. State files round-trip on disk under `state/by-usb/<usb_path>.json`
     with atomic temp+rename+directory-fsync semantics; `tests/unit/`
     spike harness simulates random USB renumbering and the inventory
     cross-check (file usb_path ↔ sysfs ↔ current cdc-wdm) raises a
     structured error on mismatch rather than silently overwriting.

**Plans**: 7 plans

Plans:
- [x] 01-01-PLAN.md — Repo + lint/CI scaffolding (pyproject.toml, requirements.lock with 10 pinned runtime libs including pydantic-settings, lint_no_subprocess.sh, pre-commit, GitHub Actions self-hosted aarch64 CI)
- [x] 01-02-PLAN.md — `.deb` build pipeline (debian/rules with PBS+uv+compileall, postinst smoke test importing all 10 libs, systemd Type=notify with ExecStartPre=, NFR-51 ≤40 MiB, SOURCE_DATE_EPOCH reproducibility, ships Plan 06's day-one carrier YAML to /etc/spark-modem-watchdog/conf.d/)
- [x] 01-03-PLAN.md — `wire/` package (BaseWire + closed StrEnum types + ModemState 5+2 flat + Diag with Who tagged union + Events/Webhook discriminated unions + schema_version helpers)
- [x] 01-04-PLAN.md — `state_store/` (atomic temp+rename+dir-fsync writes + 3-layer locks WIRED INTO StateStore methods + inventory cross-check via StateStore.cross_check_inventory_for + hypothesis property test for SC #5 + non-destructive schema downgrade shadow with deadlock-safe public/private helper split)
- [x] 01-05-PLAN.md — `subproc/` runner (single async run() entrypoint with all 4 SP-03 invariants: list-form argv, LC_ALL=C, start_new_session, two-stage SIGTERM→2s→SIGKILL→drain via asyncio.timeout)
- [x] 01-06-PLAN.md — `clock/` + `config/` (Settings imports pydantic_settings — pin upstreamed to Plan 01) + `event_logger/` + day-one carrier YAML (12 entries IL/US/GB/DE; install line lives in Plan 02)
- [x] 01-07-PLAN.md — ADR set (amend 0001/0003/0004/0005/0006 + author 0008..0013; closes PROJECT.md Q1..Q8)

### Phase 2: Core Daemon (laptop-testable)

**Goal**: Ship a complete asyncio daemon that runs end-to-end on a
developer laptop using fixtures only — the cycle driver, the per-modem
TaskGroup probe orchestrator, the pure-function policy engine (every
RECOVERY_SPEC §4 decision-table row covered by spec-as-tests), the
non-destructive (cheap) actions, the `status.json` writer, the Prometheus
UDS exporter, the webhook poster (HMAC + retry/dedup + DNS pre-resolve),
and the `spark-modem` CLI. Exit when the policy engine agrees with v1 on
≥1000 historical cycle replays, hardware-free `pytest -q` runs in ≤30 s
(M7), and mypy --strict is green.

**Depends on**: Phase 1

**Requirements**:
FR-2, FR-10, FR-11, FR-12, FR-13, FR-20, FR-21, FR-22, FR-25, FR-25.1,
FR-26, FR-26.1, FR-26.2, FR-28, FR-28.1, FR-30, FR-31, FR-32, FR-33,
FR-40, FR-41, FR-41.1, FR-42, FR-44, FR-44.3, FR-44.4, FR-44.5, FR-44.6,
FR-44.7, FR-44.8, FR-50, FR-50.1, FR-50.2, FR-50.3, FR-51, FR-52, FR-70,
FR-71, FR-74,
NFR-1, NFR-2, NFR-3, NFR-4, NFR-5, NFR-10, NFR-11, NFR-20, NFR-21,
NFR-21.1, NFR-22, NFR-22.1, NFR-42

**Success Criteria** (what must be TRUE):
  1. Replaying ≥1000 captured v1 cycles via `spark-modem recovery
     --diag-fixture=<dir>` produces planned actions that agree with v1's
     historical actions on healthy cycles, and on fault cycles produce
     equal-or-safer choices (no destructive reset where v1 chose a cheap
     action; no cheap action where v1 succeeded with destructive).
  2. The `spark-modem` CLI runs hardware-free on a developer laptop:
     `diag --qmi-fixture-dir=tests/fixtures/qmi/healthy/` returns a typed
     `Diag` snapshot in <1 s; `recovery --diag-fixture=...` returns a
     ranked `PlannedAction[]` list; `--explain` surfaces the decision
     rationale; `ctl history --modem=cdc-wdm0 --since=1h` prints a per-
     modem timeline; `ctl maintenance on --duration=2h` succeeds with
     mandatory `--duration` (rejects without it, rejects >8h, auto-
     expires); `ctl support-bundle` produces a tarball with last 200
     events + status.json + last 24h of webhook delivery results.
  3. Cycle wallclock on a laptop fixture run is ≤10 s P99 (NFR-1 / M5);
     RSS stays ≤80 MiB with the psutil tripwire wired at 200 MiB
     (NFR-3); per-modem QMI probes execute concurrently via
     `asyncio.TaskGroup` with per-task `asyncio.timeout(8s)` (FR-70 /
     NFR-4); state-store writes serialize via per-modem `asyncio.Lock`
     plus a separate globals lock (FR-71); a deliberately-thrown policy
     exception is logged and the cycle continues (NFR-11).
  4. The Prometheus UDS endpoint at `/run/spark-modem-watchdog/metrics.sock`
     responds to `curl --unix-socket` with valid Prom text containing
     `actions_total{kind,modem,result}`, `signal_dbm{modem,kind}`,
     `cycle_duration_seconds`, integer-encoded `modem_state_value{modem}`
     (NOT one-hot — ADR-0013), `state_duration_seconds{modem,state}`
     histogram, `cycle_drift_seconds` gauge, `webhook_delivery_total{result}`
     counter; cardinality stays bounded under fixture-driven 7-day replay
     (every label combination accounted for).
  5. Webhook delivery on `Healthy → Degraded` and `Recovering → Exhausted`
     transitions emits a typed payload with `X-Spark-Signature: sha256=<hex>`
     over raw body bytes, `X-Spark-Timestamp: <unix>` header, retry queue
     with 3 attempts + exponential backoff before drop, per-`(modem,
     transition)` 60s coalescing with `dedup_count` field, daemon-restart
     events with reason enum, `action_failed` variant, and a pre-exit
     best-effort send on schema-version refusal — all running in a separate
     task with explicit httpx timeouts and pre-resolved cached DNS so the
     cycle never blocks on webhook I/O.
  6. `_healthy_streak` is persisted in the per-modem state file every
     cycle, reloaded on daemon start, and the streak update + decay check
     + counter reset + state-write happens as one atomic write per cycle
     (RECOVERY_SPEC §8 ordering); the replay harness includes a
     daemon-restart-mid-streak case that proves K consecutive Healthy
     cycles correctly resume after restart and decay counters to zero.

**Plans**: 10 plans

Plans:
- [x] 02-01-PLAN.md — Test fakes + Wave 0 fixture directories (FakeRunner, FakeClock, FakeWebhookPoster, FixtureInventory, FakeDNSResolver, FixtureZaoTailer)
- [x] 02-02-PLAN.md — qmi/ wrapper + parsers + per-libqmi-version fixtures (FR-11, FR-74; --device-open-proxy always; extra='ignore' boundary)
- [x] 02-03-PLAN.md — zao_log/ parser + ZaoLogTailer Protocol + RASCOW_STAT fixtures (FR-10)
- [x] 02-04-PLAN.md — inventory/ + observer/ TaskGroup orchestrator with per-task asyncio.timeout(8s) + Diag builder + Issue extractor (FR-2, FR-13, FR-70, FR-71, NFR-4, NFR-10)
- [x] 02-05-PLAN.md — policy/ pure engine: transitions + decision_table + gates + engine + spec-as-tests (FR-12, FR-20, FR-21, FR-22, FR-25, FR-25.1, FR-26, FR-26.1, FR-26.2, NFR-11, NFR-20)
- [x] 02-06-PLAN.md — actions/ cheap set + dispatcher + verify (set_apn / fix_raw_ip / sim_power_on / soft_reset / set_operating_mode / fix_autosuspend) (FR-22, FR-28, FR-28.1, FR-30..FR-33, FR-40, NFR-42)
- [x] 02-07-PLAN.md — status_reporter/ status.json + Prom UDS + MetricRegistry + maintenance window in globals.json (FR-41, FR-41.1, FR-42, NFR-3, NFR-5, NFR-21, NFR-21.1)
- [x] 02-08-PLAN.md — webhook/ poster + DNS pre-resolve + HMAC sign + dedup + retry queue + drain (FR-44, FR-44.3..FR-44.8)
- [x] 02-09-PLAN.md — cli/ all subcommands (diag/recovery/provision/reset/status/explain/ctl) with PII redaction in support-bundle (FR-50, FR-50.1, FR-50.2, FR-50.3, FR-51, FR-52, NFR-22, NFR-22.1)
- [x] 02-10-PLAN.md — daemon/main.py cycle driver + replay harness + 1002 fixtures + 100% fault-cycle agreement gate (NFR-1, NFR-2, FR-26.1)
**UI hint**: no

### Phase 3: Linux Event Sources & Lifecycle

**Goal**: Replace the laptop's polling-only fixture mode with real
event-driven observation on a bench Jetson — `pyudev.Monitor` for USB
add/remove, `pyroute2.AsyncIPRoute` for link state, `asyncinotify` for
Zao log + logrotate (both `create` and `copytruncate` modes), `/dev/kmsg`
non-blocking reader for dmesg host-level events, `sd_notify` lifecycle
(READY / STATUS / WatchdogSec), `loop.add_signal_handler` for SIGTERM
graceful shutdown ≤5 s and SIGHUP transactional config reload, single
PID-lock at `/run/spark-modem-watchdog/lock`, and per-modem + state-store
`flock`s separate from the PID lock (so the daemon and a CLI mutator
serialize). Exit when a bench Jetson with 4 real modems boots clean,
reaches Healthy within 60 s, and survives a `qmi_wwan` driver reload as
a clean state transition (not a crash).

**Depends on**: Phase 2

**Requirements**:
FR-1, FR-3, FR-4, FR-14, FR-43, FR-43.1, FR-53, FR-61, FR-61.1, FR-75,
NFR-12, NFR-13, NFR-30

**Success Criteria** (what must be TRUE):
  1. On a fresh Jetson boot, the daemon discovers all four Sierra-VID
     (`1199:9091`) modems via `pyudev.Monitor` (single-threaded reader,
     not `MonitorObserver`), resolves each to `(line, cdc_wdm, usb_path,
     namespace, iface)` from sysfs, persists the ICCID/IMSI identity map
     keyed by `usb_path`, and emits `READY=1` via `sd_notify` after the
     first full cycle within 60 s of process start (FR-1, FR-3, FR-75,
     NFR-13).
  2. A SIM swap (ICCID change at the same `usb_path`) is detected within
     one cycle and triggers automatic re-provisioning; a hot-plug
     `usb_remove` followed by `usb_add` updates inventory without
     restarting the daemon (FR-4); USB overcurrent / "device not
     accepting address" / thermal events from `dmesg` surface as global
     issues in `events.jsonl` and `status.json` (FR-14).
  3. `systemctl stop spark-modem-watchdog.service` triggers SIGTERM and
     the daemon shuts down within 5 s with a final state-store flush, a
     pre-exit best-effort webhook on outstanding transitions, and a
     `daemon_stopped` event with reason `sigterm`; `systemctl reload`
     issues SIGHUP and data-only fields (carrier table, thresholds,
     webhook URL) update transactionally without restarting; topology-
     affecting fields trigger a structured "restart required" log line
     and are not applied (FR-53, FR-54-runtime).
  4. Two concurrent state-mutating CLI invocations (`spark-modem ctl
     reset-state` × 2) serialize cleanly via the state-store `flock` at
     `/run/spark-modem-watchdog/state.lock`; per-modem `flock`s at
     `/run/spark-modem-watchdog/modem-{usb_path}.lock` separate from the
     daemon's PID lock at `/run/spark-modem-watchdog/lock`; the daemon
     and a `ctl reset-state` from a second shell never produce a
     lost-update on the same modem (FR-61, FR-61.1).
  5. `logrotate` running in either `create` mode (MOVE_SELF /
     DELETE_SELF) or `copytruncate` mode (file inode unchanged, st_size
     truncates to 0) does not silently break the inotify watch on
     `events.jsonl` or the Zao log tailer — the watcher reopens
     correctly and the next event arrives within one cycle; a
     `qmi_wwan` driver reload (`modprobe -r qmi_wwan; modprobe
     qmi_wwan`) is observable as a clean state transition through
     `disconnected → recovering → healthy`, not as a daemon crash (FR-43,
     FR-43.1, NFR-12); daemon runs as root with no other process granted
     suid bits (NFR-30).

**Plans**: 9 plans

Plans:
- [x] 03-01-PLAN.md — Event source supervisor + WakeSignal scaffold + IssueDetail extension (E-01, E-02, E-03 enum + FakeAsyncinotify + FakeSleeper + linux_only marker)
- [x] 03-02-PLAN.md — pyudev producer + UdevInventory + netns derivation + qmicli netns prepend (E-05, FR-1, FR-3, FR-4)
- [x] 03-03-PLAN.md — pyroute2 rtnetlink producer (PITFALLS §6.1 ENOBUFS handling)
- [ ] 03-04-PLAN.md — asyncinotify dual-watcher (events.jsonl reopen + Zao log tailer) + EventLogWriter.reopen + ZaoLogInotifyTailer dual-mode (R-01, R-03, R-04, FR-43, FR-43.1)
- [ ] 03-05-PLAN.md — kmsg producer + classifier + dedup (E-03, FR-14)
- [ ] 03-06-PLAN.md — Daemon lifecycle modules + main.py rewrite + wire variants (EventSourceCrashed + SimSwapped); WATCHDOG cycle-end placement (L-01..L-05, FR-53, FR-61, FR-61.1, FR-75, NFR-13)
- [ ] 03-07-PLAN.md — cycle_driver SIM-swap detection + StateStore.reset_modem_streak_and_counters atomic reset (FR-3, FR-4, RECOVERY_SPEC §8)
- [ ] 03-08-PLAN.md — systemd unit hardening (U-01..U-05) + logrotate snippet (R-02) + cross-platform unit-file-audit test (FR-53, NFR-30)
- [ ] 03-09-PLAN.md — Integration tests (SC #1..#5) + bench Jetson human-verify checkpoint (FR-1, FR-43, FR-43.1, NFR-12)

### Phase 4: Destructive Actions & HIL

**Goal**: Implement the four destructive recovery actions
(`soft_reset`, `modem_reset`, `usb_reset`, global `driver_reset`) as
idempotent CLI-runnable functions wired into the policy engine, gated by
the signal-quality gate (RSRP / RSRQ / SNR thresholds) and the
≥75%-QMI-hung + actionable-signal gate for the global driver reset, and
prove all of it on a hardware-in-the-loop bench Jetson with deliberate
fault injection. Exit when the HIL CI job is green: SIM-app issue
resolved by `soft_reset`, `not_registered_searching` resolved by
`modem_reset` after one `soft_reset`, three-modem QMI-hang triggers
`driver_reset`, an RF-blocked modem refuses destructive actions, and
`pkill -9 qmi-proxy` mid-cycle is recovered with one `driver_reset`
without thrash.

**Depends on**: Phase 3

**Requirements**:
FR-23, FR-24, FR-27

**Success Criteria** (what must be TRUE):
  1. Each of `soft_reset`, `modem_reset`, `usb_reset`, `driver_reset`
     is a separate idempotent function callable individually via
     `spark-modem reset --action=<name> --modem=cdc-wdm0` (or
     `--global` for `driver_reset`), survives being invoked twice in a
     row without producing a different outcome the second time, and
     returns a structured success/failure with verification (post-reset
     read-back of `operating_mode == "online"` and `raw_ip == "Y"`)
     (FR-27).
  2. The signal-quality gate refuses `modem_reset` and `usb_reset` when
     measured RSRP < -110 dBm OR RSRQ < -15 dB OR SNR < 0 dB; the
     refusal emits an `action_skipped` event with reason
     `signal_below_gate` and the modem state transitions to `rf_blocked`
     (orthogonal flag, ADR-0008); cheap actions still run while
     `rf_blocked` is set; HIL synthetic-RF-noise scenario confirms the
     gate fires (FR-23).
  3. Global `driver_reset` fires only when ≥3 of 4 modems are
     simultaneously QMI-hung AND at least one of them has actionable
     signal (RSRP ≥ -110 AND RSRQ ≥ -15 AND SNR ≥ 0); the HIL three-
     modem-QMI-hang scenario triggers exactly one `driver_reset` (no
     thrash, no per-modem `usb_reset` race), the `qmi_wwan` reload
     surfaces as a clean state transition, and metrics record
     `actions_total{kind="driver_reset",result="success"}` once
     (FR-24).
  4. The HIL CI lane (`tests/hil/`) runs the full MIGRATION.md §2
     scenario list against a real bench Jetson with 4 modems and passes
     end-to-end: boot and reach Healthy; SIM swap detected; SIM
     `app_state_detected` resolved by `soft_reset`;
     `not_registered_searching` resolved by `modem_reset` after one
     `soft_reset`; three-modem QMI hang triggers `driver_reset`; an RF
     event keeps the daemon out of destructive resets;
     `pkill -9 qmi-proxy` mid-cycle is detected via stderr `proxy_died`
     and recovered with one `driver_reset`. Replay-harness fault-cycle
     agreement against ≥30 days of v1 historical traces ≥95%.

**Plans**: TBD

### Phase 5: Bench & Field Shadow

**Goal**: Run v2 in shadow mode (dry-run, separate state/log/metrics
paths) alongside v1 on a bench Jetson for one week (MIGRATION Phase 1),
then on one carefully-chosen field box for two weeks (MIGRATION Phase
2). The compare tool from Phase 1 design produces hourly reports that
weight fault cycles separately from healthy cycles. Exit when fault-
cycle agreement ≥95% (NOT aggregate), v2 plans never mark a Zao-active
line for action, the entire field cohort's firmware/SDK is captured as
known-set fixtures, and the on-site engineer is comfortable with v2's
behavior.

**Depends on**: Phase 4

**Requirements**:
(no v1 REQ-IDs — this is a delivery / shadow-validation phase from
PROJECT.md "Migration (delivery, not a feature)" mapping to MIGRATION.md
Phases 1-2)

**Success Criteria** (what must be TRUE):
  1. v2 has been running in dry-run on the bench Jetson for ≥7
     consecutive days under `spark-modem-watchdog-v2.service` writing
     to `/var/lib/spark-modem-watchdog-v2/`, `/var/log/spark-modem-
     watchdog-v2/events.jsonl`, and `/run/spark-modem-watchdog-v2/
     metrics.sock`, with `dry_run: true` in `99-shadow.yaml` and v1
     retaining exclusive ownership of canonical paths (MIGRATION §3).
  2. The hourly compare tool (`tools/compare_v1_v2.py`) report shows
     ≥95% fault-cycle agreement (PITFALLS §15.1 — NOT the legacy
     aggregate ≥99% gate) over the bench week and the field two-week
     window; every disagreement is either bug-fixed in v2 or filed
     with explicit rationale; v2 has zero "act on Zao-active line"
     planned actions (would indicate a Zao-log parsing regression).
  3. Daily synthetic fault injection (one per scenario per day:
     SIM-app issue, registration loss, QMI-hang, RF degradation)
     produces v2 plans equal-or-safer than v1's actions; v2 never
     plans `driver_reset` more often than v1, never plans destructive
     resets on RF-blocked modems, and never misses an issue v1
     catches.
  4. By field-shadow exit: every box's `(EM7421 firmware version,
     Zao SDK version, libqmi version)` triple is captured in
     `tests/fixtures/fleet/<box-id>/` and parses cleanly through the
     v2 qmicli parser; any box with a triple outside the known set is
     flagged for either fixture capture or fleet upgrade before Phase
     6 begins.

**Plans**: TBD

### Phase 6: Cutover & Fleet Rollout

**Goal**: Cut v2 live on one field box for two weeks (MIGRATION Phase 3)
with v1 disabled and masked but available for ≤10-minute rollback,
expand to 10% of the fleet for two weeks (MIGRATION Phase 4), then roll
forward at 10% per day with the fleet-management tool gating each batch
on the previous batch's health metrics (MIGRATION Phase 5). Exit when
100% of the fleet is on v2 and the success metrics M1-M7 are met over
a rolling 30-day window.

**Depends on**: Phase 5

**Requirements**:
(no v1 REQ-IDs — delivery phase mapping to MIGRATION.md Phases 3-5)

**Success Criteria** (what must be TRUE):
  1. The single-box live cutover (MIGRATION §5) completes cleanly: v1
     stopped/disabled/masked, v2 moved to canonical paths, v2 reaches
     Healthy on all four modems within 60 s, the rollback procedure
     (unmask v1, reinstall `spark-modem-watchdog-v1_1.0.0_all.deb`,
     restart) is exercised end-to-end and completes in <10 minutes;
     two clean weeks follow with per-modem availability within ±0.2%
     of the historical baseline.
  2. The 10% canary cohort (two weeks) hits all four fleet-aggregate
     gates: `modem_state_value` time-in-`exhausted` ≤ baseline,
     destructive-reset rate ≤ baseline + 10%, session-disconnect rate
     ≤ baseline + 10%, zero daemon crashes in any 24h window across
     the cohort; Prometheus WAL compaction stays within budget at the
     fleet's ingest rate (cardinality stays bounded under real load).
  3. Rolling 10%/day cutover proceeds to 100% with no batch failing
     its previous-batch health gate; carrier-table SHA convergence
     across the fleet is observable via the `carrier_table_sha256`
     field in `status.json` and converges to a single value within
     1 hour of any rollout.
  4. Over a rolling 30-day window post-100%, the success metrics are
     met: M1 per-modem availability ≥99.5%; M2 median MTTR ≤60 s
     (SIM), ≤90 s (registration), ≤180 s (QMI-hung); M3 false-
     positive destructive resets ≤5%; M4 zero `Exhausted` from
     counter accumulation (verified by replaying decay logic against
     30 days of traces); M5 P99 cycle ≤10 s; M6 zero OOM /
     unhandled-exception daemon restarts.

**Plans**: TBD

### Phase 7: v1 Decommission & Archive

**Goal**: After 30 days of clean v2 operation post-100%-rollout, remove
v1 packages from all boxes, archive the v1 source scripts in the repo
with a forwarding README, and update the agent-facing documentation
(`CLAUDE.md`, `AGENTS.md`) to point at v2.

**Depends on**: Phase 6

**Requirements**:
(no v1 REQ-IDs — delivery phase mapping to MIGRATION.md Phase 6)

**Success Criteria** (what must be TRUE):
  1. `apt purge spark-modem-watchdog-v1` runs cleanly on every box;
     a fleet-wide grep confirms zero references remain to the v1 paths
     (`/usr/local/bin/diag.sh`, `/usr/local/bin/recovery.sh`,
     `/usr/local/bin/auto_profile.sh`, `/usr/local/bin/zao_reset_line.sh`)
     in any unit file, cron entry, or systemd dependency.
  2. The v1 source scripts are moved to `archive/v1/` in the repository
     with a README pointing at v2; the v1 issue-tracker label is closed;
     `CLAUDE.md` and `AGENTS.md` no longer reference v1 paths or
     workflows.
  3. A post-mortem-style summary documents the migration outcome
     regardless of whether anything went wrong, including before/after
     metrics: MTTR, false-positive reset rate, daemon CPU/RSS, support-
     ticket count over the migration window.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundations & ADRs | 7/7 | Complete | 2026-05-06 |
| 2. Core Daemon | 9/10 | In Progress | - |
| 3. Linux Event Sources & Lifecycle | 3/9 | In Progress | - |
| 4. Destructive Actions & HIL | 0/TBD | Not started | - |
| 5. Bench & Field Shadow | 0/TBD | Not started | - |
| 6. Cutover & Fleet Rollout | 0/TBD | Not started | - |
| 7. v1 Decommission & Archive | 0/TBD | Not started | - |

---

*Roadmap created: 2026-05-05 (synthesized from PROJECT.md, REQUIREMENTS.md, research/SUMMARY.md, docs/MIGRATION.md)*
</content>
</invoke>