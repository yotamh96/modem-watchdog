# Requirements: spark-modem-watchdog v2

**Defined:** 2026-05-05
**Core Value:** Maximize end-user uplink availability across the four bonded modems by applying minimum-impact recovery actions — and never running a destructive recovery (modem/USB reset) that has zero chance of fixing the observed issue.

These requirements derive from `docs/PRD.md` (FR-1..FR-64, NFR-1..NFR-43) with deltas from `.planning/research/SUMMARY.md` (state-machine refactor, HMAC v2.0 promotion, per-modem dry-run, Promoted M-* features, usb_path keying, cardinality-safe metrics).

REQ-IDs use the docs/PRD.md convention: `FR-NN` for functional, `NFR-NN` for non-functional. Numbering is stable across revisions; new requirements append at the end. Where research surfaced a new requirement, the ID has a letter suffix (e.g. `FR-44.1`, `FR-44.2`) so PRD numbering stays intact.

---

## v1 Requirements

### Discovery & Inventory

- [ ] **FR-1**: System discovers all Sierra-VID modems on USB at startup and on udev `add`/`remove` events
- [ ] **FR-2**: System resolves each modem to `(line, cdc_wdm, usb_path, namespace, iface)` via sysfs (no hardcoded paths)
- [ ] **FR-3**: System detects SIM identity (ICCID, IMSI) per modem and persists `(usb_path → identity)` map across reboots
- [ ] **FR-4**: System detects SIM swap (ICCID change at the same `usb_path`) and triggers re-provisioning

### Diagnosis

- [ ] **FR-10**: System consults Zao `RASCOW_STAT` before probing; if Zao reports the line as `active`, no QMI probe is run
- [x] **FR-11
**: Per-inactive-modem snapshot includes USB speed, QMI responsiveness, operating mode, SIM card/app state, registration, serving carrier (MCC/MNC/desc), signal (RSSI/RSRP/RSRQ/SNR), profile-1 APN, data session, current IPv4
- [ ] **FR-12**: System classifies each modem with state-machine v2 (post-research refactor): top-level `unknown` / `healthy` / `degraded` / `recovering(level)` / `exhausted` plus orthogonal flags `present` and `rf_blocked` (supersedes PRD FR-12's 7-state shape; ADR-0008)
- [ ] **FR-13**: System emits a typed `Diag` snapshot every cycle conforming to SCHEMA § Diag
- [ ] **FR-14**: System detects host-level issues (USB overcurrent, "device not accepting address", thermal events) from `dmesg` and treats them as global issues

### Recovery

- [ ] **FR-20**: At most one recovery action per modem per cycle
- [ ] **FR-21**: Action selection follows category priority `config > sim > datapath > registration > qmi`
- [ ] **FR-22**: Per-modem escalation ladder: `set_apn` / `fix_raw_ip` / `sim_power_on` / `soft_reset → modem_reset → usb_reset → exhausted`
- [ ] **FR-23**: System gates `modem_reset` and `usb_reset` when signal is measurably below thresholds (RECOVERY_SPEC § 6.1)
- [ ] **FR-24**: Global `driver_reset` fires only when ≥75 % of modems are simultaneously QMI-hung **and** at least one has actionable signal
- [ ] **FR-25**: Same-action backoff suppresses repeating an action on the same modem within `BACKOFF_SECONDS` (default 300 s)
- [ ] **FR-25.1**: Cross-action ladder backoff: no destructive action runs more than once every `ladder_min_interval` seconds (default 90 s) — RECOVERY_SPEC § 6.3 (new in v2 spec)
- [ ] **FR-26**: Per-action escalation counters decay to zero after K consecutive `Healthy` cycles for that modem (default K=10) — ADR-0006
- [ ] **FR-26.1**: `_healthy_streak` is persisted in the per-modem state file every cycle and reloaded on daemon start; mid-streak restart does not reset progress (closes PITFALLS §9.2 regression risk)
- [ ] **FR-26.2**: Streak update + decay check + counter reset + state-write are one atomic write per cycle; ordering pinned in RECOVERY_SPEC § 8 (closes PITFALLS §9.1)
- [ ] **FR-27**: All recovery actions are separate idempotent functions, runnable individually via the CLI
- [ ] **FR-28**: `--dry-run` everywhere a real action would mutate state
- [ ] **FR-28.1**: Per-modem dry-run: config accepts `dry_run: bool | list[str]`; gate at action-execution time; surfaced in `status.json` and on each `action_planned` event (research §4.5)

### Provisioning

- [ ] **FR-30**: APN selection by `(MCC, MNC)` lookup in config-file carrier table
- [x] **FR-30.1
**: Day-one carrier coverage includes Israel (authoritative) plus minimal US (310/410, 311/480, 312/530), UK (234/10, 234/15, 234/30), DE (262/01, 262/02, 262/03) marked `unverified: true` (research §4.6)
- [ ] **FR-31**: Profile #1 written only when desired APN differs from currently programmed value
- [ ] **FR-32**: Post-write APN verification (read profile back); fail loudly on mismatch
- [ ] **FR-33**: New MCC/MNC entries addable without code release (config reload)
- [x] **FR-33.1
**: Carrier-table entries fixture-validated against hostile inputs (YAML "Norway problem", leading-zero MCC/MNC); `mnc: str` regex `r"^\d{2,3}$"` (PITFALLS §11.2)

### Observability

- [ ] **FR-40**: Structured event log (JSON Lines) at `/var/log/spark-modem-watchdog/events.jsonl`
- [ ] **FR-41**: `status.json` at `/var/lib/spark-modem-watchdog/status.json` with current per-modem state, last cycle ts, aggregate health
- [ ] **FR-41.1**: `status.json` includes `cycle.actions_executed` and `cycle.transitions` counters and `carrier_table_sha256` (M-11/M-17)
- [ ] **FR-42**: Prometheus scrape endpoint on Unix socket (default `/run/spark-modem-watchdog/metrics.sock`)
- [ ] **FR-43**: Event log rotated via `logrotate` with 7-day, 100 MiB retention default
- [ ] **FR-43.1**: inotify tail tolerates both `create`-mode rotation (MOVE_SELF/DELETE_SELF) **and** `copytruncate` mode (st_size truncation check) (PITFALLS §8.1)
- [ ] **FR-44**: Webhook POST on `Healthy → Degraded` and `Recovering → Exhausted` transitions, with typed payload
- [x] **FR-44.1
**: HMAC-SHA256 webhook signing in v2.0 (header `X-Spark-Signature: sha256=<hex>` over raw body bytes), promoted from v2.1 (closes PRD Q5 — research §4.3)
- [x] **FR-44.2
**: Replay-protection header `X-Spark-Timestamp: <unix>` on every webhook (M-4)
- [ ] **FR-44.3**: Webhook delivery retry with bounded queue (3 attempts, exponential backoff) before drop (M-1)
- [ ] **FR-44.4**: Webhook payload deduplication / coalescing per `(modem, transition)` with default 60 s cooldown; `dedup_count` field on next emission (M-2)
- [ ] **FR-44.5**: Daemon-restart event with reason enum (`sigterm` / `crash` / `config_invalid` / `oom` / `kill`) (M-6)
- [ ] **FR-44.6**: `action_failed` event variant with structured failure reason (M-15)
- [ ] **FR-44.7**: Pre-exit best-effort webhook on schema-version refusal (M-25)
- [ ] **FR-44.8**: Webhook delivery runs in a separate task with explicit httpx timeouts; URL DNS pre-resolved at config-load and cached 60 s; never blocks the cycle (PITFALLS §10.1)

### Operability

- [ ] **FR-50**: Single `spark-modem` CLI with subcommands `diag`, `recovery`, `provision`, `reset`, `status`, `ctl`
- [ ] **FR-50.1**: `spark-modem ctl history --modem=cdc-wdmN --since=DURATION` first-class subcommand for per-modem timeline (M-9)
- [ ] **FR-50.2**: `spark-modem ctl maintenance on --duration=DURATION` (max 8 h, mandatory `--duration`, auto-expiry); suppresses webhooks while observing continues (M-10; PITFALLS §16.2)
- [ ] **FR-50.3**: `--explain` flag on `diag` surfaces decision rationale (PRD UC3, RUNBOOK reference)
- [ ] **FR-51**: CLI accepts `--qmi-fixture-dir=PATH` to read recorded `qmicli` output instead of executing
- [ ] **FR-52**: CLI accepts `--diag-fixture=PATH` for `recovery` to replay a captured snapshot
- [ ] **FR-53**: Daemon runs as a systemd `Type=notify` unit; graceful SIGTERM within 5 s
- [x] **FR-54
**: Configuration precedence: CLI flags > env vars > `/etc/spark-modem-watchdog/conf.d/*.yaml` > baked-in defaults; SIGHUP transactional reload for data-only fields (closes PRD Q6 — research §8 #7)

### Safety

- [x] **FR-60
**: Refuse to start if `qmicli`, `ip`, and bundled `python3` (>=3.12 from `python-build-standalone`) are not present (closes PROJECT.md Q8 — research §2)
- [ ] **FR-61**: Single PID lock on `/run/spark-modem-watchdog/lock` for the daemon
- [ ] **FR-61.1**: Per-modem and state-store advisory `flock`s separate from PID lock; CLI mutating commands acquire the same locks the daemon does (M-21; PITFALLS §3.2/§16.1)
- [x] **FR-62
**: All persistent file writes are atomic (temp + rename + directory fsync)
- [x] **FR-62
.1**: Per-modem state files keyed by `usb_path` (`state/by-usb/<usb_path>.json`), not `cdc-wdmN`; startup cross-checks file usb_path vs sysfs vs current cdc-wdm — mismatch is an error (closes ARCHITECTURE Q14 / PITFALLS §3.1; ADR-0009)
- [x] **FR-63
**: Validate every external input (qmicli output, JSON, Zao log) before acting; invalid input is logged error, not a crash
- [x] **FR-64
**: Never `exec` a string built from external data; all subprocess calls use list-form `argv`

### Daemon design (research-derived)

- [ ] **FR-70**: Single-process asyncio daemon; per-modem probes via `asyncio.TaskGroup` + per-task `asyncio.timeout` (default 8 s) — not `gather` + `wait_for` (research §4.1 #1)
- [ ] **FR-71**: State-store concurrency uses per-modem `asyncio.Lock` plus a globals lock; in-process locks separate from the cross-process flocks of FR-61.1 (research §4.1 #2; ADR-0012)
- [x] **FR-72
**: External-IO seams behind `Protocol` types: `QmiClient`, `SubprocessRunner`, `Clock`, `ZaoLogTailer`, `StateStore`, `FileWriter`, plus research-added `WebhookPoster`, `MetricRegistry`, `PIDLock`, `SignalHandler`
- [x] **FR-73
**: Policy engine is a pure function `Diag × {ModemState, Globals, Config, Clock} → PlannedAction[]` — no subprocess, no I/O, no env reads (RECOVERY_SPEC §1)
- [x] **FR-74
**: qmi-proxy is owned by Zao; daemon refuses to start in qmicli-direct mode if proxy is unavailable (closes PRD Q2 — research §8 #3)
- [ ] **FR-75**: Daemon emits `READY=1` via `sd_notify` after first full cycle; emits `STATUS=` keepalive each cycle; optional `WatchdogSec=90s` cadence (research §4.2)

---

## v1 Requirements — Non-functional

### Performance

- [ ] **NFR-1**: A full diag cycle completes in ≤10 s on the target Jetson when no modems are unresponsive (cold-start first cycle exempt, see startup_delay_seconds)
- [ ] **NFR-2**: Daemon consumes ≤1 % CPU averaged over a 10-min window in steady state
- [ ] **NFR-3**: RSS ≤80 MiB; psutil-based tripwire fires at >200 MiB
- [ ] **NFR-4**: Per-modem QMI probes run in parallel via `asyncio.TaskGroup`
- [ ] **NFR-5**: Disk write rate ≤1 MiB/min in steady state

### Reliability

- [ ] **NFR-10**: Daemon recovers from any single transient error (parse failure, qmicli timeout, partial fixture) within one cycle
- [x] **NFR-11
**: Uncaught exception in policy engine MUST NOT terminate the daemon; logged and cycle skipped
- [ ] **NFR-12**: Daemon tolerates `qmi_wwan` driver reload during operation: `driver_reset` is observable as a clean state transition, not a daemon crash
- [ ] **NFR-13**: Daemon reaches steady-state operation within 60 s of process start, given Zao is already running

### Observability

- [ ] **NFR-20**: Every state transition logged as a single JSON line with `ts, modem, from, to, cause, action, dry_run`
- [ ] **NFR-21**: Prometheus exporter exposes: `actions_total{kind,modem,result}`, `signal_dbm{modem,kind}`, `cycle_duration_seconds`, **`modem_state_value{modem}` integer-encoded** (replaces PRD's one-hot `modem_state{modem,state}` to avoid cardinality explosion — research §5.1; ADR-0013)
- [ ] **NFR-21.1**: Additional metrics: `state_duration_seconds{modem,state}` histogram (M-5), `cycle_drift_seconds` self-health gauge (M-8), `webhook_delivery_total{result}` counter
- [ ] **NFR-22**: Snapshot of `status.json` plus last 200 events retrievable via `spark-modem ctl support-bundle` for offline analysis
- [ ] **NFR-22.1**: Support bundle includes last 24 h of webhook delivery results (success/fail + http_status) so NOC can verify "did the alert fire?" (research §3 §4.2)

### Security

- [ ] **NFR-30**: Daemon runs as root; no other process granted suid bits
- [x] **NFR-31
**: All subprocess calls pass arguments as a list, never a shell string
- [x] **NFR-32
**: External text inputs parsed by validators that reject unexpected types/shapes
- [x] **NFR-33
**: Webhook URLs validated as `https://` only by default; `http://` allowed only with explicit `webhook_allow_http=true`
- [x] **NFR-34
**: HMAC signing secret loaded from systemd `LoadCredential=`; never on disk

### Maintainability

- [x] **NFR-40
**: Codebase passes `mypy --strict`, `ruff check`, `ruff format --check` in CI (drop `black`)
- [x] **NFR-41
**: Unit tests run hardware-free on a developer laptop using fixtures only
- [ ] **NFR-42**: New MCC/MNC entries addable in a single YAML edit + reload, without a release
- [x] **NFR-43
**: Schema versions are integers (v1, v2); daemon refuses to load forward-version files; downgrade is non-destructive (shadow as `.from-v<N>.json`, log `schema_downgrade_pending`); `ctl migrate-state` and `ctl reset-state --all` available (closes ARCHITECTURE Q15 / PITFALLS §3.4 — research §8 #14)

### Packaging & deployment (research-derived)

- [x] **NFR-50
**: Distributed as a Debian `.deb` for `arm64` containing a self-contained venv at `/opt/spark-modem-watchdog/python/`, built from `astral-sh/python-build-standalone` CPython 3.12.x (closes PROJECT.md Q8; ADR-0010)
- [x] **NFR-51
**: `.deb` size ≤40 MiB; security-update story: rebuild on each CPython security release
- [x] **NFR-52
**: Build pipeline produces a `requirements.lock` from `uv pip compile` and commits it for reproducibility

---

## v2.1 Requirements (deferred)

### HTTP control plane

- **CTL-01**: HTTP API on Unix socket for read endpoints (status, last_diag, events tail) — closes PRD Q1 in v2.1
- **CTL-02**: `--watch` mode replacement via long-poll/SSE on the same socket — closes PRD Q4

### Webhook batching

- **WHK-01**: Cycle-end coalescing of multi-modem transitions into a single batched webhook (M-3)

### Carrier-table portability

- **CARR-01**: `spark-modem ctl identity export / import` for RMA box swap (M-23)

### Schema export & introspection

- **SCH-01**: `spark-modem ctl schema events` exposes pydantic-derived JSON Schema for `events.jsonl` variants (M-14)

### Operational simulation

- **SIM-01**: `spark-modem ctl simulate-issue --device=X --issue=Y` injects a synthetic issue end-to-end for alert-pipeline testing (M-24)

### NR-aware policy

- **NR-01**: 5G NR-aware recovery policy (NR information moves from "informational" to actionable) — PRD §9 deferred from v2.0

---

## Out of Scope

| Feature | Reason |
|---------|--------|
| Cloud control plane / remote management | NG3 — daemon-on-box; adding kills C20 (offline install) and C21 (no outbound deps) |
| GUI / web UI on the device | NG5 — customer is NOC + shell; UI is dead weight + attack surface |
| Multi-vendor modem support (Quectel, Telit, etc.) | NG4 — single hardware target; premature abstraction doubles test matrix |
| Replacing `qmicli` with Python libqmi bindings | NG6 + ARCH §5 — qmicli is the contract; this would be a separate project |
| Multi-SIM / eSIM management | EM7421 is single-SIM hardware |
| Owning or modifying Zao | NG1 — we integrate, we do not own; ownership invites scope creep |
| Migration of v1 state files | v2 starts fresh per box; v1 state files have no value v2 needs |
| Hot-plug of modems mid-flight as a v2.0 priority | Supported via udev events; not SLA'd in v2.0 |
| Retroactive "re-decision" on past cycles (replay-second-guessing) | AF-10 — would grow into a parallel policy engine |
| Predictive recovery / ML on signal trends | AF-11 — testability collapses; an ML model running as root |
| Auto-firmware-update of the EM7421 | AF-12 — Sierra owns firmware; folding it in invites bricked modems |
| Cross-box / fleet-wide coordination | AF-13 — coordination belongs in NOC, not the daemon (alert-storm risk) |
| HTTP API on Unix socket in v2.0 | Defer to v2.1 — surface-area discipline; daemon never accepts inbound IPC in v2.0 |

---

## Traceability

Mapped during ROADMAP creation 2026-05-06. Every v1 REQ-ID maps to exactly one phase. Phases 5-7 are delivery / rollout phases (mapping to `docs/MIGRATION.md` Phases 1-6) that contain no code-introducing REQ-IDs — they verify success metrics M1-M7.

### Functional requirements

| Requirement | Phase | Status |
|-------------|-------|--------|
| FR-1 | Phase 3 | Pending |
| FR-2 | Phase 2 | Pending |
| FR-3 | Phase 3 | Pending |
| FR-4 | Phase 3 | Pending |
| FR-10 | Phase 2 | Pending |
| FR-11 | Phase 2 | Pending |
| FR-12 | Phase 2 | Pending |
| FR-13 | Phase 2 | Pending |
| FR-14 | Phase 3 | Pending |
| FR-20 | Phase 2 | Pending |
| FR-21 | Phase 2 | Pending |
| FR-22 | Phase 2 | Pending |
| FR-23 | Phase 4 | Pending |
| FR-24 | Phase 4 | Pending |
| FR-25 | Phase 2 | Pending |
| FR-25.1 | Phase 2 | Pending |
| FR-26 | Phase 2 | Pending |
| FR-26.1 | Phase 2 | Pending |
| FR-26.2 | Phase 2 | Pending |
| FR-27 | Phase 4 | Pending |
| FR-28 | Phase 2 | Pending |
| FR-28.1 | Phase 2 | Pending |
| FR-30 | Phase 2 | Pending |
| FR-30.1 | Phase 1 | Pending |
| FR-31 | Phase 2 | Pending |
| FR-32 | Phase 2 | Pending |
| FR-33 | Phase 2 | Pending |
| FR-33.1 | Phase 1 | Pending |
| FR-40 | Phase 2 | Pending |
| FR-41 | Phase 2 | Pending |
| FR-41.1 | Phase 2 | Pending |
| FR-42 | Phase 2 | Pending |
| FR-43 | Phase 3 | Pending |
| FR-43.1 | Phase 3 | Pending |
| FR-44 | Phase 2 | Pending |
| FR-44.1 | Phase 1 | Pending |
| FR-44.2 | Phase 1 | Pending |
| FR-44.3 | Phase 2 | Pending |
| FR-44.4 | Phase 2 | Pending |
| FR-44.5 | Phase 2 | Pending |
| FR-44.6 | Phase 2 | Pending |
| FR-44.7 | Phase 2 | Pending |
| FR-44.8 | Phase 2 | Pending |
| FR-50 | Phase 2 | Pending |
| FR-50.1 | Phase 2 | Pending |
| FR-50.2 | Phase 2 | Pending |
| FR-50.3 | Phase 2 | Pending |
| FR-51 | Phase 2 | Pending |
| FR-52 | Phase 2 | Pending |
| FR-53 | Phase 3 | Pending |
| FR-54 | Phase 1 | Pending |
| FR-60 | Phase 1 | Pending |
| FR-61 | Phase 3 | Pending |
| FR-61.1 | Phase 3 | Pending |
| FR-62 | Phase 1 | Pending |
| FR-62.1 | Phase 1 | Pending |
| FR-63 | Phase 1 | Pending |
| FR-64 | Phase 1 | Pending |
| FR-70 | Phase 2 | Pending |
| FR-71 | Phase 2 | Pending |
| FR-72 | Phase 1 | Pending |
| FR-73 | Phase 1 | Pending |
| FR-74 | Phase 2 | Pending |
| FR-75 | Phase 3 | Pending |

### Non-functional requirements

| Requirement | Phase | Status |
|-------------|-------|--------|
| NFR-1 | Phase 2 | Pending |
| NFR-2 | Phase 2 | Pending |
| NFR-3 | Phase 2 | Pending |
| NFR-4 | Phase 2 | Pending |
| NFR-5 | Phase 2 | Pending |
| NFR-10 | Phase 2 | Pending |
| NFR-11 | Phase 2 | Pending |
| NFR-12 | Phase 3 | Pending |
| NFR-13 | Phase 3 | Pending |
| NFR-20 | Phase 2 | Pending |
| NFR-21 | Phase 2 | Pending |
| NFR-21.1 | Phase 2 | Pending |
| NFR-22 | Phase 2 | Pending |
| NFR-22.1 | Phase 2 | Pending |
| NFR-30 | Phase 3 | Pending |
| NFR-31 | Phase 1 | Pending |
| NFR-32 | Phase 1 | Pending |
| NFR-33 | Phase 1 | Pending |
| NFR-34 | Phase 1 | Pending |
| NFR-40 | Phase 1 | Pending |
| NFR-41 | Phase 1 | Pending |
| NFR-42 | Phase 2 | Pending |
| NFR-43 | Phase 1 | Pending |
| NFR-50 | Phase 1 | Pending |
| NFR-51 | Phase 1 | Pending |
| NFR-52 | Phase 1 | Pending |

### Per-phase rollups

| Phase | FR count | NFR count | Total |
|-------|----------|-----------|-------|
| Phase 1: Foundations & ADRs | 12 | 10 | 22 |
| Phase 2: Core Daemon | 39 | 13 | 52 |
| Phase 3: Linux Event Sources & Lifecycle | 10 | 3 | 13 |
| Phase 4: Destructive Actions & HIL | 3 | 0 | 3 |
| Phase 5: Bench & Field Shadow | 0 | 0 | 0 (delivery) |
| Phase 6: Cutover & Fleet Rollout | 0 | 0 | 0 (delivery) |
| Phase 7: v1 Decommission & Archive | 0 | 0 | 0 (delivery) |
| **Totals** | **64** | **26** | **90** |

**Coverage:**
- v1 functional requirements: 64 total (FR-1..FR-75 with sub-requirements)
- v1 non-functional requirements: 26 total (NFR-1..NFR-52 with sub-requirements)
- Total v1: 90 requirements
- Mapped to phases: 90 ✓
- Unmapped: 0 ✓

(Earlier coverage header counted 67/24/91; recount during traceability mapping arrived at 64/26/90 — every REQ-ID listed above is mapped exactly once and accounted for in the rollup.)

---

*Requirements defined: 2026-05-05*
*Last updated: 2026-05-06 — traceability section populated; every v1 REQ-ID mapped to exactly one phase (synthesized from `docs/PRD.md`, `.planning/research/SUMMARY.md`, and `.planning/ROADMAP.md`).*
