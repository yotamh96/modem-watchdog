# spark-modem-watchdog v2

## What This Is

`spark-modem-watchdog` is the on-device daemon that keeps a fleet of NVIDIA
Jetson Orin NX bonded-uplink boxes online by watching four Sierra Wireless
EM7421 cellular modems, detecting when one is unhealthy, and applying the
smallest recovery action that has a chance of fixing it without making things
worse. v2 is a from-scratch Python rewrite that preserves the operational
principles proven out in the v1 bash toolchain while replacing the
implementation, the wire contracts, and the observability story.

## Core Value

Maximize end-user uplink availability across the four bonded modems by
applying minimum-impact recovery actions — and never running a destructive
recovery (modem/USB reset) that has zero chance of fixing the observed
issue (e.g. reset on bad RF).

## Requirements

### Validated

<!-- v1 design decisions inherited and frozen by ADRs. These are the
operational invariants v2 must preserve, not capabilities to re-prove. -->

- ✓ Three-seam architecture: observe → decide → act — v1 carry-over (testability)
- ✓ Zao log is authoritative for active lines — ADR-0003
- ✓ Signal-quality gate on destructive actions — v1 carry-over (uptime safety)
- ✓ Bounded escalation ladder per modem — v1 carry-over (no stuck-reset loops)
- ✓ One-action-per-modem-per-cycle — v1 carry-over (no stacked operations)
- ✓ Priority order across categories: config > sim > datapath > registration > qmi — v1 carry-over
- ✓ Sysfs-based runtime discovery of `(line, cdc_wdm, usb_path, ns, iface)` — v1 carry-over
- ✓ Idempotent action implementations — v1 carry-over
- ✓ Atomic file writes (temp + rename) — v1 carry-over

**Phase 1 (Foundations & ADRs) — validated 2026-05-06:**

- ✓ ADR set closes Q1–Q8: 0001/0003/0004/0005/0006 amended + 0008–0013 authored
- ✓ Wire-type contracts locked: `wire/` package (Pydantic v2, BaseWire, schema_version, 5+2 ModemState, integer-encoded Prometheus state)
- ✓ State store atomic-write + 3-layer locking + non-destructive schema downgrade + inventory cross-check (`state/by-usb/<usb_path>.json`)
- ✓ Single async subprocess wrapper with list-form argv + locale baseline + process-group kill + cpython#127049/#139373 mitigations (SP-04 lint enforces no `subprocess.run` outside `subproc/`)
- ✓ Plumbing skeletons: `clock/` (monotonic), `config/` (Pydantic Settings + reload markers), `event_logger/` (O_APPEND JSONL)
- ✓ `.deb` build pipeline: PBS-bundled CPython 3.12 + 10 runtime libs (locked + hash-verified) + systemd Type=notify unit + B-03 belt-and-suspenders smoke import; CI builds on aarch64 self-hosted runner; smoke-install in clean Ubuntu 20.04 arm64 container is green; size ≤40 MiB (NFR-51)
- ✓ Day-one carrier table: 12 entries (IL/US/GB/DE) with hostile-input fixtures (Norway problem + leading-zero MNCs)
- ✓ CI gates green on aarch64: `mypy --strict`, `ruff check`, `ruff format --check`, `pytest -m "unit or integration"` (302 tests)

**Phase 3 (Linux Event Sources & Lifecycle) — validated 2026-05-08 (bench-Jetson SC #1/#3/#4/#5 hardware exec deferred to Phase 4 HIL):**

- ✓ Event-source supervisor: WakeSignal closed StrEnum (5 members) + restart_on_crash with bounded backoff [1,2,4,8,60]s + 300s uptime reset + CancelledError passthrough; EventSourceCrashed structurally emitted on producer crash
- ✓ pyudev producer + UdevInventory: `Monitor.from_netlink + loop.add_reader(monitor.fileno())` — never MonitorObserver; netns derivation (`derive_ns`) + QmiWrapper netns prepend (all 11 qmicli methods routed); deferred pyudev import for Windows dev-host parsing
- ✓ pyroute2 rtnetlink producer: `AsyncIPRoute` with 4 MiB SO_RCVBUF; tight read-loop body is exactly `event_queue.put_nowait(WakeSignal.RTNETLINK)`; ENOBUFS escapes to supervisor for socket close+reopen
- ✓ asyncinotify dual-mode logrotate: `EventLogWriter.reopen()` for own-log rotation + `ZaoLogInotifyTailer` handling both create-mode (MOVE_SELF/DELETE_SELF) and copytruncate (st_size shrink + inode unchanged)
- ✓ /dev/kmsg producer: `O_RDONLY|O_NONBLOCK + lseek(SEEK_END) + loop.add_reader`; 5 closed-enum KMSG_PATTERNS classifier with case-insensitive regex (real Linux writes lowercase 'usb'); per-detail 30s monotonic dedup; 6 host-level IssueDetail values (E-03)
- ✓ Daemon lifecycle: preflight (kernel module + topology probe), sd_notify Type=notify with WatchdogSec=90s + cycle-end watchdog kick (Issue #5 regression gate pinned), 8-step SIGTERM choreography ≤5s, SIGHUP atomic config swap (pre-validate → flip), single PID lock + per-modem flocks + state-store flock all separate from PID lock
- ✓ cycle_driver SIM-swap detection: `_detect_and_handle_sim_swaps` between observation and policy.engine; sha256[:8] ICCID redaction; `StateStore.reset_modem_streak_and_counters` single-atomic-write per RECOVERY_SPEC §8; structured `SimSwapped` emit
- ✓ systemd unit hardened (U-01..U-05): WatchdogSec=90s, RuntimeDirectoryPreserve=yes, LoadCredential= for HMAC secret, ExecStartPre=config-check, R-02 logrotate snippet (`create 0640 root adm` + empty postrotate); 20-test cross-platform unit-file audit gate
- ✓ Integration test tier: 6 SC tests (`test_lifecycle.py` covers boot-to-READY, SIM-swap, SIGTERM 5s, ctl serialisation, qmi_wwan reload) + real `/usr/sbin/logrotate -f` exercise (`test_logrotate_create.py`); Linux-only via per-module `pytestmark = pytest.mark.linux_only` (Issue #6 resolved — conftest does NOT auto-mark)
- ✓ Test suite at exit: 1835 pass / 88 skip / 0 fail in 17.80s (M7 30s budget preserved); mypy --strict + ruff check + ruff format + SP-04 subprocess lint all green; FR-1, FR-3, FR-4, FR-14, FR-43, FR-43.1, FR-53, FR-61, FR-61.1, FR-75, NFR-12, NFR-13, NFR-30 marked done

### Active

<!-- v2.0 scope. All hypotheses until shipped against the live fleet
(see Migration phases 1-5). -->

**Discovery & inventory (FR-1..FR-4)**
- [ ] Discover all Sierra-VID modems on USB at startup and on udev add/remove
- [ ] Resolve each modem to `(line, cdc_wdm, usb_path, namespace, iface)` via sysfs
- [ ] Detect SIM identity (ICCID, IMSI) per modem and persist `(usb_path → identity)` map
- [ ] Detect SIM swap and trigger re-provisioning

**Diagnosis (FR-10..FR-14)**
- [ ] Consult Zao `RASCOW_STAT` before probing; never QMI-probe an active line
- [ ] Per-inactive-modem probe: USB speed, QMI responsiveness, op mode, SIM card/app, registration, carrier MCC/MNC, signal RSSI/RSRP/RSRQ/SNR, profile-1 APN, data session, IPv4
- [ ] Classify each modem: Healthy / Degraded / RfBlocked / Recovering(level) / Exhausted
- [ ] Emit typed `Diag` snapshot every cycle (SCHEMA § Diag)
- [ ] Detect host-level issues from dmesg (USB overcurrent, enum failures, thermal)

**Recovery (FR-20..FR-28)**
- [ ] At most one action per modem per cycle
- [ ] Action selection follows priority `config > sim > datapath > registration > qmi`
- [ ] Per-modem escalation ladder: set_apn / fix_raw_ip / sim_power_on / soft_reset → modem_reset → usb_reset → Exhausted
- [ ] Signal-quality gate on `modem_reset`/`usb_reset` (RSRP ≥ -110, RSRQ ≥ -15, SNR ≥ 0)
- [ ] Global `driver_reset` only when ≥75% of modems are simultaneously QMI-hung AND at least one has actionable signal
- [ ] Same-action backoff (default 300 s) and cross-action ladder backoff (default 90 s)
- [ ] Per-action escalation counters decay to zero after K consecutive Healthy cycles (ADR-0006)
- [ ] All recovery actions implemented as separate idempotent functions, runnable individually via CLI
- [ ] `--dry-run` everywhere a real action would mutate state

**Provisioning (FR-30..FR-33)**
- [ ] APN selection by `(MCC, MNC)` lookup in config-file carrier table
- [ ] Profile #1 written only when desired APN differs from currently programmed
- [ ] Post-write APN verification (read-back); fail loudly on mismatch
- [ ] New MCC/MNC entries addable without code release (config reload)

**Observability (FR-40..FR-44)**
- [ ] Structured `events.jsonl` (JSON Lines) at `/var/log/spark-modem-watchdog/events.jsonl`
- [ ] `status.json` at `/var/lib/spark-modem-watchdog/status.json` with per-modem state and aggregate health
- [ ] Prometheus scrape endpoint on Unix socket (default `/run/spark-modem-watchdog/metrics.sock`)
- [ ] Logrotate rotation: 7 days, 100 MiB
- [ ] Webhook POST on `Healthy → Degraded` and `Recovering → Exhausted` transitions

**Operability (FR-50..FR-54)**
- [ ] Single `spark-modem` CLI: `diag`, `recovery`, `provision`, `reset`, `status`, `ctl` subcommands
- [ ] `--qmi-fixture-dir=PATH` for replay; `--diag-fixture=PATH` for recovery replay
- [ ] systemd `Type=notify` unit; graceful SIGTERM within 5 s
- [ ] Layered config: flags > env > `/etc/spark-modem-watchdog/conf.d/*.yaml` > defaults

**Safety (FR-60..FR-64)**
- [ ] Refuse to start if `qmicli`/`ip`/`python3 ≥3.11` not on PATH
- [ ] Single PID lock on `/run/spark-modem-watchdog/lock`
- [ ] All persistent file writes atomic
- [ ] Validate every external input (qmicli output, JSON, Zao log) before acting
- [ ] Never `exec` a string built from external data — list-form argv only

**Non-functional**
- [ ] NFR-1: Diag cycle ≤ 10 s steady-state
- [ ] NFR-3: RSS ≤ 80 MiB
- [ ] NFR-4: Per-modem QMI probes run in parallel (`asyncio.gather`)
- [ ] NFR-13: Steady state within 60 s of process start
- [ ] NFR-21: Prometheus metrics exposed: `actions_total`, `signal_dbm`, `cycle_duration_seconds`, `modem_state{state}`
- [ ] NFR-40: `mypy --strict`, `ruff`, formatter all pass in CI
- [ ] NFR-41: Unit tests run hardware-free using fixtures only
- [ ] NFR-43: Schema-version refusal of future versions; explicit migration

**Migration (delivery, not a feature)**
- [ ] Phase 0: `.deb` builds, HIL passes, dry-run replay agrees with v1 on ≥1000 historical cycles
- [ ] Phase 1: bench Jetson, v2 dry-run alongside v1 for one week
- [ ] Phase 2: one field box, dry-run alongside v1, two weeks
- [ ] Phase 3: one field box, v2 active, v1 disabled, two weeks
- [ ] Phase 4: 10 % canary, two weeks
- [ ] Phase 5: rolling 10 %/day to 100 %
- [ ] Phase 6: archive v1 scripts, decommission

### Out of Scope

- Replacing or modifying Zao — we integrate; we do not own it (NG1)
- Multi-region carrier support beyond Israel in v2.0 — non-IL MCCs land via config, not release (NG2)
- Cloud control plane / remote management — v2 is a daemon on the box (NG3)
- Generic "any modem" support — v2 targets Sierra EM7421 + qmi_wwan (NG4)
- GUI or web UI on the device — CLI + structured status only (NG5)
- Replacing `qmicli` as the QMI client — we wrap it (NG6)
- Multi-SIM / eSIM management — EM7421 is single-SIM
- 5G NR-aware policy — NR is informational in v2.0; full NR policy is v2.1
- Cross-vendor modems (Quectel, Telit) — single hardware target
- HTTP API on Unix socket vs CLI-only ctl tool — open question Q1; CLI-only for v2.0
- HMAC-SHA256 webhook payload signing — open question Q5; deferred to v2.1 unless reclassified
- Migration of v1 state files — v2 starts fresh per box (acceptable; nothing structural is lost)

## Context

**Production reality.** v1 is a pipeline of bash scripts (`diag.sh` →
`recovery.sh` → `auto_profile.sh`, `zao_reset_line.sh`) driven by a systemd
watchdog on a 120 s loop. It currently keeps a real fleet online; v2 must
prove itself in shadow mode before replacing v1 on any box (see Migration
phases 1-2).

**What v1 got wrong (motivates the rewrite).**
- Two-language hybrid (bash + python heredocs); hand-rolled JSON; fragile
  `awk -F"'"` parsing of `qmicli`.
- Free-form `detail` strings and heterogeneous `who` field — no type checking
  on the wire (replaced by typed enums + tagged union, ADR-0004).
- Recovery counters never decay → modems become permanently Exhausted after
  one bad incident (fixed by counter-decay-on-healthy, ADR-0006).
- Wall-clock backoff (NTP step can wedge it) → all backoff math is on
  `time.monotonic()` in v2 (ADR-0007).
- Polling-only architecture; events ignored → v2 subscribes to udev,
  rtnetlink, inotify, dmesg with polling fallback (ADR-0002).
- Command injection in `auto_profile.sh` via shell-string interpolation;
  `.bak` files instead of git; no tests, no fixtures, no replay harness;
  no log rotation; no metrics; no status endpoint.

**Domain glue.** Zao (Soliton's bonding stack) owns the modems at runtime;
the watchdog observes around it. Zao's `RASCOW_STAT` log line tells us which
of lines 1..4 are currently bonding — never QMI-probe a Zao-active line
(ADR-0003). Zao's `InfraCtrl.script` owns profile programming; we invoke it
rather than writing profiles directly so Zao observes the change.

**Carrier table.** Israeli MCC 425 with MNC entries for Partner (01),
Cellcom (02), Pelephone (03). New MCC/MNC entries are pure config (YAML
edit + reload) — never a code release.

**Observability targets.** NOC consumes Prometheus metrics + webhook alerts.
Field engineers consume `events.jsonl` (replay-able) and the support bundle
(`spark-modem ctl support-bundle` produces a tarball with the last 200
events, current `status.json`, all per-modem state, journal slice, dmesg
slice).

## Constraints

- **Hardware**: NVIDIA Jetson Orin NX (16 GB) on P3768 reference carrier — C1
- **Hardware**: 4× Sierra Wireless EM7421 (VID:PID `1199:9091`) on USB 3 hub, typically `2-3.1.{1..4}` — C2
- **Software**: JetPack 5.1.5 / L4T R35.6.4 / Ubuntu 20.04 / aarch64 / kernel 5.10-tegra — C10/C11
- **Software**: Soliton Zao SDK 2.1.0+; `ModemManager` MUST remain disabled (Zao requires exclusive modem access) — C12/C13
- **Language (target runtime)**: **Python 3.8.10** is the actual Jetson system Python and the runtime we must support on-box. ADR-0001 / docs/ assumed 3.11+; that conflict is open and must be resolved during the research/planning phases (options: bundle 3.11 in a venv as ADR-0001 originally proposed, drop to 3.8-compatible code, or upgrade the Jetson runtime). The pydantic v2, `match` statements, asyncio TaskGroup, `tomllib`, and various typing features the docs use are 3.10/3.11 — careful inventory needed.
- **Schema/types**: pydantic v2 for all wire formats; closed enums for `IssueCategory` / `IssueDetail` / `RegistrationState` etc. — ADR-0004
- **Network**: Install-time the box MAY be offline; installer MUST not require internet — C20
- **Network**: Zero outbound runtime dependencies except optional alert webhook — C21
- **Performance**: P99 cycle ≤ 10 s; RSS ≤ 80 MiB; 1 % CPU steady-state — NFR-1/3/2
- **Process**: Single-process `asyncio` daemon; per-modem probes via `asyncio.gather` with per-task timeout (default 8 s); single `asyncio.Lock` guards state-store commits — ARCH § 4.3
- **Time**: All durations and backoffs use `time.monotonic()`; `time.time()` only for ISO-8601 stamps — ADR-0007
- **Subprocess**: Every external command via one wrapper, list-form argv, with timeout — FR-64 / NFR-31

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python 3.11+, single-process asyncio daemon, `.deb` with bundled venv | ADR-0001: typed wire formats need real types; `qmicli` text parsing is awkward in any language; team velocity is best in Python | ⚠️ Revisit — Jetson system Python is 3.8.10; resolve via venv-bundled 3.11 (ADR-0001's original plan), 3.8-compatible code, or runtime upgrade |
| Event-driven core (udev / rtnetlink / inotify / dmesg) with 30 s polling fallback (down from v1's 120 s) | ADR-0002: cycle is much cheaper now; events shorten median MTTR | — Pending |
| Zao `RASCOW_STAT` is authoritative for "is line N bonding"; never QMI-probe a Zao-active line | ADR-0003: avoids QMI control-channel race; Zao's view is correct by definition | — Pending |
| Strict typed JSON contract (pydantic v2, closed enums, `schema_version` int, tagged-union `who`) | ADR-0004: v1's free-form `detail` strings + heterogeneous `who` caused silent regressions | — Pending |
| Explicit per-modem state machine: `unknown` / `healthy` / `degraded` / `recovering(level)` / `rf_blocked` / `exhausted` / `disconnected` | ADR-0005: makes recovery decisions auditable; spec-as-tests against the markdown table | — Pending |
| Per-action escalation counters decay to zero after K consecutive Healthy cycles (default K=10) | ADR-0006: fixes v1's permanent-`Exhausted` failure mode after a single bad incident | — Pending |
| All backoff arithmetic uses `time.monotonic()`; wall clock only for ISO-8601 stamps | ADR-0007: NTP step on the Jetson can wedge wall-clock backoff | — Pending |
| Policy engine is a pure function `Diag × {ModemState, Globals, Config, Clock} → PlannedAction[]` — no subprocess, no I/O | Testability: every decision-table row in RECOVERY_SPEC § 4 is a fixture | — Pending |
| Six-phase migration (bench → field box dry-run → field box live → 10 % canary → 100 %) before v1 decommission | v1 keeps a real fleet online; conservative cutover; rollback button at every phase | — Pending |
| CLI-only ctl tool (no HTTP API on Unix socket) for v2.0 | Open question Q1 deferred to v2.1; minimize surface area | — Pending |

## Open questions (carried from PRD § 10)

All eight original open questions are CLOSED in writing as of Phase 1
(2026-05-06). Each is now backed by an ADR; the ADR is authoritative —
the bullet here is a one-line summary of the resolution, not the spec.

- **Q1** ✓ HTTP API on Unix socket vs CLI-only ctl? — **CLI-only for v2.0**, no inbound IPC; ADR-0011 + amendments to 0001/0004
- **Q2** ✓ Daemon owns `qmi-proxy` or assumes Zao does? — **Zao owns it**; ADR-0003 amendment, ADR-0011
- **Q3** ✓ Minimum-supported Zao SDK version? — **2.1.0+ confirmed**; ADR-0003 amendment binds parser to `RASCOW_STAT`
- **Q4** ✓ Feature parity with v1 `--watch` mode? — **Replace with `journalctl -fu` + Prometheus UDS scrape**; ADR-0011, ADR-0013
- **Q5** ✓ HMAC-SHA256 webhook signing in v2.0 or v2.1? — **v2.0**; ADR-0011 (`X-Spark-Signature: sha256=<hex>` over raw body, `X-Spark-Timestamp` for replay protection)
- **Q6** ✓ Config-change communication? — **SIGHUP reload via `json_schema_extra={'reload': '...'}` markers**; ADR-0006 amendment, `config/reload_marker.py`
- **Q7** ✓ Carrier-table ownership post-launch? — **Config file at `/etc/spark-modem-watchdog/conf.d/00-carriers.yaml`**, day-one IL/US/GB/DE table shipped with .deb; addable without code release
- **Q8** ✓ Jetson system Python is 3.8.10. — **Bundle CPython 3.12 via `python-build-standalone` in the `.deb` venv**; ADR-0010 ratified the recipe, ADR-0001 amended

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-11 after Phase 5 (Bench & Field Shadow) code-completion — Plans 05-01..05-07 shipped (X-* fleet-triple chain, audit tools, .deb known-fleet shipment, operator docs). Plan 05-08 (3-4 week operator soak campaign + SIGNOFF) tracked in 05-HUMAN-UAT.md.*
