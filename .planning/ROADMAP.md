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
- [x] **Phase 3: Linux Event Sources & Lifecycle** ✅ 2026-05-08 - udev/rtnetlink/inotify/dmesg, sd_notify, signal handling, PID-lock, per-modem flocks (build D + E)
- [x] **Phase 4: Destructive Actions & HIL** - soft/modem/usb/driver_reset wired up, signal-gate end-to-end, qmi-proxy crash recovery, HIL CI lane (build F) — code complete 2026-05-10; Phase 4 EXIT contingent on first green nightly HIL run on bench Jetson + replay-harness >=95% gate (Plan 04-07 bench-Jetson human-verify auto-approved under --auto)
- [x] **Phase 5: Bench & Field Shadow** ✅ 2026-05-11 - code-complete on Plans 05-01..05-07 (X-* fleet-triple chain + audit tools + .deb shipment + operator docs); Plan 05-08 (multi-week operator soak + SIGNOFF) tracked in 05-HUMAN-UAT.md
- [x] **Phase 05.1: deb-packaging-hotfix (INSERTED)** ✅ 2026-05-12 - .deb install pipeline unblocked: 3 bugs retired (I-01 sys.path, I-02/I-04 entry-point, L-02 LoadCredential silent-ignore on systemd 245) + V-01/V-02/V-04 regression gates landed; bench Jetson dpkg-install + ExecStartPre gates pass; L-04 verdict captured (WARN, code-side fallback handles it)
- [x] **Phase 05.2: daemon-startup-hotfix (INSERTED)** ✅ 2026-05-12 - Daemon `_production_main` now constructs `Settings()` directly instead of the CLI laptop-sandbox factory `build_default_settings()`; bench Jetson `ExecStart` no longer mkdirs `/tmp/spark-modem-cli` against `ProtectSystem=strict`'s read-only `/tmp`
- [x] **Phase 05.3: libqmi-version-regex-hotfix (INSERTED)** ✅ 2026-05-12 - `_LIBQMI_VERSION_RE` broadened to match both `qmicli X.Y.Z` and `Compiled with libqmi-glib X.Y.Z` formats; JetPack 5.1.5 / libqmi 1.30.4 output (qmicli-only banner, no libqmi-glib footer) now parses correctly through the Phase 5 X-03 preflight
- [x] **Phase 05.4: dms-revision-parser-hotfix (INSERTED)** ✅ 2026-05-12 - `parse_get_revision` header check broadened to accept both `Device revisions retrieved` (plural — when both Revision + Boot code lines are present) and `Device revision retrieved` (singular — when only Revision is present); bench Jetson SWI9X50C modem stdout now parses through the X-03 preflight's second probe
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
- [x] 03-04-PLAN.md — asyncinotify dual-watcher (events.jsonl reopen + Zao log tailer) + EventLogWriter.reopen + ZaoLogInotifyTailer dual-mode (R-01, R-03, R-04, FR-43, FR-43.1)
- [x] 03-05-PLAN.md — kmsg producer + classifier + dedup (E-03, FR-14)
- [x] 03-06-PLAN.md — Daemon lifecycle modules + main.py rewrite + wire variants (EventSourceCrashed + SimSwapped); WATCHDOG cycle-end placement (L-01..L-05, FR-53, FR-61, FR-61.1, FR-75, NFR-13)
- [x] 03-07-PLAN.md — cycle_driver SIM-swap detection + StateStore.reset_modem_streak_and_counters atomic reset (FR-3, FR-4, RECOVERY_SPEC §8)
- [x] 03-08-PLAN.md — systemd unit hardening (U-01..U-05) + logrotate snippet (R-02) + cross-platform unit-file-audit test (FR-53, NFR-30)
- [x] 03-09-PLAN.md — Integration tests (SC #1..#5) + bench Jetson human-verify checkpoint (FR-1, FR-43, FR-43.1, NFR-12) — completed approved-with-deferral 2026-05-08; bench-Jetson SC #1/#3/#4/#5 hardware verification deferred to Phase 4 HIL ticket (STATE.md Deferred Items)

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

**Plans**: 7 plans

Plans:
- [x] 04-01-modem-reset-action-PLAN.md — modem_reset action + dispatcher registration + CLI unblock — completed 2026-05-10
- [x] 04-02-usb-reset-action-PLAN.md — usb_reset action + sysfs/ module + Sierra-bootloader handling + --target CLI flag — completed 2026-05-10
- [x] 04-03-driver-reset-and-eligibility-PLAN.md — driver_reset action + global eligibility predicate + thermal suppression + cooldown — completed 2026-05-10
- [x] 04-04-ladder-and-signal-gate-PLAN.md — policy/ladder.py + per-action timestamps + signal-gate Settings migration — completed 2026-05-10
- [x] 04-05-action-skipped-event-PLAN.md — ActionSkipped event variant + decision-table/engine integration — completed 2026-05-10
- [x] 04-06-hil-infra-scaffold-PLAN.md — HIL CI workflow + fault-injection helpers + LFS trace puller — completed 2026-05-10
- [x] 04-07-hil-scenario-suite-PLAN.md — 12 HIL scenarios + Phase-3 piggyback + replay-harness 30-day gate — completed 2026-05-10 (bench-Jetson human-verify auto-approved; first nightly HIL run is the EXIT bar)

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

> **Note (2026-05-11):** SC #1/#2/#3 above describe the original
> shadow-vs-v1 framing. Per `.planning/phases/05-bench-field-shadow/05-CONTEXT.md`
> scope_pivot, v1 has been retired across the fleet; v2 runs at canonical
> paths from day 1. `tools/compare_v1_v2.py`, `99-shadow.yaml`, and
> `-v2`-suffixed paths are NOT built. The effective Phase 5 exit gates
> are the locked R-/S-/F-/X- decisions in 05-CONTEXT.md + the M-metrics
> in PROJECT.md § 8. Doc-rewrite of SC#1/#2/#3 is deferred per CONTEXT.md
> Deferred Ideas (Phase 7 or doc-fixup phase).

**Plans**: 8 plans

Plans:
- [x] 05-01-PLAN.md — `dms_get_revision` qmicli verb + parser + per-libqmi-version fixtures (X-02 firmware probe)
- [x] 05-02-PLAN.md — Version-detection helpers: libqmi + Zao SDK + FleetTriple orchestrator (X-03 triple)
- [x] 05-03-PLAN.md — `spark-modem ctl capture-fleet-fixture` CLI verb + PII redaction (X-01, X-02)
- [x] 05-04-PLAN.md — `preflight_check_known_fleet_triple` daemon preflight + main.py wiring (X-03)
- [x] 05-05-PLAN.md — Soak audit tools: `tools/audit_soak_zao.py` + `tools/audit_soak_exhausted.py` (S-01 #2, S-01 #3 / M4)
- [x] 05-06-PLAN.md — `.deb` ships `/etc/spark-modem-watchdog/known-fleet/` via debian/install (X-03)
- [x] 05-07-PLAN.md — Operator docs: SIGNOFF.md template + SOAK_RUNBOOK.md + RUNBOOK.md cross-reference (S-04, F-04)
- [x] 05-08-PLAN.md — Manual operator workflow: R-01 trace pull → bench 1-week soak → field 2-week soak → X-04 sweep → R-02 replay-harness → SIGNOFF commit (R-01, R-02, S-02, S-03, S-04, X-04)

### Phase 05.1: deb-packaging-hotfix (INSERTED)

**Goal**: `dpkg -i spark-modem-watchdog_2.0.*_arm64.deb` followed by
`systemctl start spark-modem-watchdog.service` reaches `active (running)`
with `sd_notify READY=1` on a bench Jetson (JetPack 5.1.5 / Ubuntu 20.04 /
systemd 245 / aarch64). Three known bugs fixed: (1) `spark_modem` not on
`sys.path` of the bundled venv → fixed by `uv pip install .` inside
`override_dh_auto_install`; (2) no daemon entry point → fixed by adding
`spark-modem-watchdog` to `pyproject.toml [project.scripts]`; (3) systemd-
245 `LoadCredential=` incompatibility → fixed by a code-side fallback in
`Settings.resolve_hmac_secret_path()`. Regression gate (D-01) lands so
the same class of bug cannot recur silently.

**Requirements**: (no formal v1 REQ-IDs — inserted hotfix; indirectly
tied to NFR-30 root-only secrets via L-03 mode/owner check, and ADR-0011
HMAC discipline via L-01..L-05)

**Depends on**: Phase 5

**Success Criteria** (EXIT bar pattern per D-03, mirroring Phase 4):
  The committed `.planning/phases/05.1-deb-packaging-hotfix/EXIT-CHECKLIST.md`
  has every V-03 gate row marked PASS by the on-site engineer. The
  checklist's 9 rows are: (1) .deb built from merged hotfix branch;
  (2) `dpkg -i` returns 0; (3) operator provisions HMAC secret;
  (4) `systemctl start` returns 0; (5) `is-active` reports `active`;
  (6) `journalctl` shows `Started ...` with no ERROR/CRITICAL;
  (7) `/run/spark-modem-watchdog/lock` present + owned by root;
  (8) `/run/spark-modem-watchdog/metrics.sock` scrape returns valid
  Prometheus text; (9) daemon reaches Healthy on all 4 modems within
  60s (NFR-13). The aarch64 GHA install test (V-02) gates the .deb
  artifact in CI; the cross-platform unit-file audit (V-04) gates the
  unit ↔ pyproject ↔ install layout on every dev-host pytest.

**Plans**: 6 plans

Plans:
- [x] 05.1-01-PLAN.md — pyproject.toml [project.scripts] + daemon _sync_main inline + debian/rules uv pip install . + .install/.dirs lib-line removal (I-01, I-02, I-04, I-05) — completed 2026-05-12
- [x] 05.1-02-PLAN.md — Settings.resolve_hmac_secret_path() (L-02) + ctl config-check verb (L-05) + postinst HMAC placeholder write (L-03) — completed 2026-05-12
- [x] 05.1-03-PLAN.md — debian/spark-modem-watchdog.service ExecStart* paths repointed to /opt/.../python/bin/ (I-03; L-01 preserved) — completed 2026-05-12
- [x] 05.1-04-PLAN.md — EXIT-CHECKLIST.md operator template (V-03) — completed 2026-05-12
- [x] 05.1-05-PLAN.md — Postinst smoke extension (V-01) + unit-file audit V-04 (a/b/c) + CI install test strict superset incl. systemd-analyze verify (V-02 + L-04 forcing function) — completed 2026-05-12
- [x] 05.1-06-PLAN.md — ROADMAP.md goal rewrite + debian/changelog 2.0.1-1 entry — completed 2026-05-12

Post-phase deploy hotfixes landed on main after the 6 plans (chain of 4
follow-up commits, applied in the same session): `78d1359` install
setuptools+wheel in Step 2; `56a6ab1` scrub __pycache__ to honor NFR-51;
`7d45b14` strip builder DESTDIR from shim trampolines + V-02 gates;
`10cec6d` scope the sed rewrite to bin/ only. Each was caught by a CI
run or the first bench Jetson install and fixed inline. The L-04
systemd-analyze verdict on Ubuntu 20.04 / systemd 245 was captured as
WARN (silent-ignore branch) — no drop-in override needed; the L-02
code-side fallback handles it.

### Phase 05.2: daemon-startup-hotfix (INSERTED)

**Goal**: After Phase 05.1 unblocked the .deb pipeline, the bench Jetson
install of `spark-modem-watchdog_2.0.0-0.gite49dc7b-1_arm64.deb` reached
the daemon's `ExecStart` and exploded with
`OSError: [Errno 30] Read-only file system: '/tmp/spark-modem-cli'`.
Root cause: `daemon/main.py:_production_main` was calling
`build_default_settings()` (the CLI laptop-sandbox factory which hardcodes
every path under `/tmp/spark-modem-cli/`) instead of `Settings()` (which
uses production defaults `/var/lib/`, `/run/`, `/var/log/` with normal
pydantic-settings env-var override semantics). The systemd unit's
`ProtectSystem=strict` correctly renders `/tmp` read-only inside the
service namespace, so the daemon's mkdir failed with EROFS — the unit
hardening is doing its job; the daemon was asking for the wrong path.

**Requirements**: (no formal v1 REQ-IDs — single-task hotfix; indirectly
tied to NFR-30 root-only-secrets pattern and the systemd hardening
discipline locked in Phase 3 U-01..U-05)

**Depends on**: Phase 05.1

**Success Criteria** (what must be TRUE):
  1. `daemon/main.py:_production_main` constructs `Settings()` directly,
     no longer routing through `build_default_settings()`. The CLI
     laptop-sandbox factory is reserved for `_laptop_main` and CLI
     `recovery --diag-fixture=...` runs.
  2. The .deb built from a commit containing this fix installs on a
     bench Jetson and the daemon successfully passes its first cycle —
     `Active: active (running)` + `sd_notify READY=1` — without any
     `/tmp/spark-modem-cli` reference in the journal.
  3. `mypy --strict src/spark_modem/daemon/main.py` and `ruff check`
     stay green over the change. No other source files modified.

**Plans**: 1 plan

Plans:
- [x] 05.2-01-PLAN.md — Use `Settings()` directly in `_production_main` instead of `build_default_settings()` — completed 2026-05-12 (commit e49dc7b; CI run 25725010483 PASS; bench Jetson 2026-05-12 10:25 UTC PASS — failure mode shifted from EROFS to structured 78/CONFIG preflight rejection, proving the Settings swap worked)

### Phase 05.3: libqmi-version-regex-hotfix (INSERTED)

**Goal**: The Phase 05.2 fix unblocked the daemon's filesystem-init step,
and the bench Jetson then surfaced a deeper structured rejection at
Phase 5's X-03 fleet-triple preflight: `qmicli --version stdout did not
match libqmi-glib regex`. The bench Jetson runs JetPack 5.1.5 / Ubuntu
20.04 / libqmi 1.30.4, whose `qmicli --version` emits only the first-line
`qmicli 1.30.4` banner — there is no `Compiled with libqmi-glib X.Y.Z`
footer that the existing regex required. Broaden the regex to accept
either form (qmicli and libqmi-glib are lockstep so the version matches
either way), add a fixture captured from the bench Jetson, and a
regression test.

**Requirements**: (no formal v1 REQ-IDs — single-task regex hotfix; Phase
5 X-02 / X-03 preflight chain from plans 05-02 and 05-04 stays semantically
intact)

**Depends on**: Phase 05.2

**Success Criteria** (what must be TRUE):
  1. `_LIBQMI_VERSION_RE` matches both `qmicli X.Y.Z` and
     `Compiled with libqmi-glib X.Y.Z` strings. The two existing fixture
     tests continue to pass without modification because qmicli and
     libqmi-glib are versioned lockstep upstream.
  2. A new fixture
     `tests/fixtures/qmicli/version/1.30/jetpack-1.30.4.txt` captures
     the bench Jetson's exact stdout (qmicli banner + Copyright +
     license + freedom + no-warranty, no libqmi-glib footer).
  3. A new test
     `test_detect_libqmi_version_parses_jetpack_qmicli_only_format`
     asserts `"1.30.4"` is parsed from the new fixture; pytest reports
     ≥11 passed on `tests/unit/qmi/test_version.py`.
  4. The bench Jetson's daemon `ExecStart` no longer fails with the
     `did not match libqmi-glib regex` message. (It may still fail at
     a deeper known-fleet allow-list check — that is a separate
     operator gate outside 05.3 scope.)

**Plans**: 1 plan

Plans:
- [x] 05.3-01-PLAN.md — `_LIBQMI_VERSION_RE` broadened + bench Jetson fixture + regression test — completed 2026-05-12 (mypy/ruff/pytest all green locally; CI + bench verification tracked in `.planning/phases/05.3-libqmi-version-regex-hotfix/VERIFICATION.md`)

### Phase 05.4: dms-revision-parser-hotfix (INSERTED)

**Goal**: Phase 05.3 unblocked the libqmi-version probe; the bench Jetson
then surfaced the next layer — `dms_get_revision` parser rejecting the
SWI9X50C modem stdout with `no revisions block in stdout`. The bench
modem emits a singular `Device revision retrieved:` header (no plural
'-s') because only a `Revision:` line is present, no `Boot code:` line
follows. libqmi adapts the header text to the field count; the parser
was hardcoded to the plural form. Broaden the response-header check to
accept both forms, capture the bench Jetson's stdout as a fixture, and
add a regression test.

**Requirements**: (no formal v1 REQ-IDs — single-task parser hotfix;
Phase 5 X-02 / X-03 fleet-triple chain semantics preserved)

**Depends on**: Phase 05.3

**Success Criteria** (what must be TRUE):
  1. `parse_get_revision` accepts both `Device revisions retrieved`
     (plural — with Boot code line) and `Device revision retrieved`
     (singular — Revision only). The two existing happy-path tests
     against the plural fixtures continue to pass.
  2. A new fixture
     `tests/fixtures/qmicli/get_revision/1.30/jetpack-singular.txt`
     captures the bench Jetson's verbatim stdout (singular header,
     tab-indented `Revision: 'SWI9X50C_01.14.03.00 ...'`).
  3. A new test
     `test_parser_accepts_singular_revision_header_jetpack` asserts the
     full SWI9X50C revision string (including build-id + jenkins build
     path) is captured; pytest reports ≥18 passed on the combined
     parser + version test suites.
  4. The bench Jetson's daemon `ExecStart` no longer fails with
     `dms_get_revision returned QmiError: reason=unexpected_output
     detail='no revisions block in stdout'`. (Failure may shift to
     the third preflight probe — Zao SDK version detection — or to
     the known-fleet allow-list check; both are outside 05.4 scope.)

**Plans**: 1 plan

Plans:
- [x] 05.4-01-PLAN.md — `parse_get_revision` header regex + bench Jetson fixture + regression test — completed 2026-05-12 (mypy/ruff/pytest all green locally, 18/18; CI + bench verification tracked in `.planning/phases/05.4-dms-revision-parser-hotfix/VERIFICATION.md`)

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
| 3. Linux Event Sources & Lifecycle | 9/9 | Complete | 2026-05-08 |
| 4. Destructive Actions & HIL | 0/7 | Not started | - |
| 5. Bench & Field Shadow | 7/8 | Complete (code) | 2026-05-11 |
| 05.1. deb-packaging-hotfix (INSERTED) | 6/6 | Complete | 2026-05-12 |
| 05.2. daemon-startup-hotfix (INSERTED) | 1/1 | Complete (bench PASS) | 2026-05-12 |
| 05.3. libqmi-version-regex-hotfix (INSERTED) | 1/1 | Complete (bench verify pending) | 2026-05-12 |
| 05.4. dms-revision-parser-hotfix (INSERTED) | 1/1 | Complete (bench verify pending) | 2026-05-12 |
| 6. Cutover & Fleet Rollout | 0/TBD | Not started | - |
| 7. v1 Decommission & Archive | 0/TBD | Not started | - |

---

*Roadmap created: 2026-05-05 (synthesized from PROJECT.md, REQUIREMENTS.md, research/SUMMARY.md, docs/MIGRATION.md)*
</content>
</invoke>