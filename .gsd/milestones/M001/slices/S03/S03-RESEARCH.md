# Phase 3: Linux Event Sources & Lifecycle - Research

**Researched:** 2026-05-07
**Domain:** Linux event-driven async daemon (pyudev / pyroute2 / asyncinotify / `/dev/kmsg` / sd_notify / systemd hardening) on aarch64 / Ubuntu 20.04 / systemd 245
**Confidence:** HIGH for stack and architecture (PITFALLS sections cite primary sources verbatim and Phase 2 has already shipped the surrounding seams); MEDIUM for the precise sysfs path used to derive `descriptor.ns` (verified post-bench-Jetson check); LOW only on regex-exact dmesg shapes for E-03's classifier (treat as data per CONTEXT.md).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**E. Event source orchestration (FR-1, FR-3, FR-4, FR-14, FR-43, FR-43.1)**

- **E-01: TaskGroup with per-task `restart_on_crash` supervisor.** The daemon's main coroutine builds an `asyncio.TaskGroup`. 5 event-source producers (udev, rtnetlink, asyncinotify-zao, asyncinotify-events, kmsg) + 1 cycle driver. `restart_on_crash(name, factory)` catches `Exception`, emits `event_source_crashed{source}`, sleeps bounded backoff `1 → 2 → 4 → 8 → min(60s)`, re-enters factory. ENOBUFS / observer-thread crash / inotify-watch-breaks (PITFALLS §6.1, §7.1, §8.1) become self-healing restart loops without taking down the daemon. If ALL 5 producers crash simultaneously, the TaskGroup logs but does NOT exit — systemd `WatchdogSec=90s` is the outer safety net.
- **E-02: Opaque `WakeSignal` sentinel on `event_queue`.** `class WakeSignal(StrEnum): UDEV; RTNETLINK; ZAO_LOG; EVENTS_LOG_ROTATED; KMSG`. Producers `put_nowait(WakeSignal.<source>)` — never await. Cycle scheduler does FULL re-observation pass. State derives from re-observation, NOT event payloads.
- **E-03: kmsg classifier with closed `IssueDetail` enum + 30 s per-detail dedup.** 5 enum values + `unknown` fallback. Each classified line emits `Issue(who=WhoHost, category=host, detail=<enum>)` routed to events.jsonl + `status.aggregate_health`. Per-`(detail)` 30 s dedup.
- **E-04: SIM-swap detection — observer captures, cycle compares, reset on diff.** observer/ extracts ICCID/IMSI per modem via qmicli's `--uim-get-card-status`. Cycle driver loads `StateStore.load_identity_map()` once per cycle, compares. On diff: persist new identity + reset `_healthy_streak` + reset escalation counters in ONE atomic state-write per RECOVERY_SPEC §8 ordering. Emit `sim_swapped` with sha256[:8] redaction.
- **E-05: netns derivation in `inventory.scan()`; qmi/wrapper auto-prepends.** `ModemDescriptor.ns` populated by reading from cdc-wdm parent's sysfs. `QmiWrapper` checks `descriptor.ns is not None` and auto-prepends `["ip", "netns", "exec", descriptor.ns]`. NEVER `setns()` from asyncio loop (PITFALLS §6.2).

**L. Lifecycle & shutdown (FR-53, FR-75, FR-61, NFR-12, NFR-13)**

- **L-01: sd_notify cadence.** `READY=1` at END of FIRST successful cycle (≤45 s of NFR-13's 60 s). `STATUS=` updated each cycle with `"cycle=N healthy=K/4 actions=M drift=Xs"`. `WATCHDOG=1` at cycle-END. RSS-tripwire is observation-only.
- **L-02: SIGTERM choreography (5 s budget).** Strict ordering: cancel cycle → cancel 5 producers → `webhook_poster.drain(3.0)` → final state-store flush → `DaemonStopped(reason=SIGTERM)` → `webhook_poster.stop()` → close UDS metrics socket + unlink → write `clean-shutdown` marker → close PID lock fd → exit 0.
- **L-03: SIGHUP transactional Settings swap.** Refuse on RELOAD_RESTART changes (state_root, run_dir, events_log_path, metrics_socket_path, carriers_yaml_path, startup_delay_seconds) with `restart_required` event. On RELOAD_DATA-only success: atomic-swap `self._settings`; `DnsCache.resolve()`; carrier-table re-read on sha256 change; `config_reloaded` event.
- **L-04: Clean-shutdown marker at `/run/.../clean-shutdown` (tmpfs by design).** Body `{uptime_s, cycle_count, exit_reason}`. Boot classifier reads BEFORE PID lock acquisition; absent → CRASH; present → SIGTERM + uptime. config_invalid via `/run/.../last-config-error`. oom + kill best-effort (Phase 4).
- **L-05: Startup order:** argparse → Settings build → preflight (qmicli/ip on PATH; B-03 import smoke test in ExecStartPre) → marker check → PID lock acquire → wire subsystems → emit DaemonRestart → TaskGroup with 5 producers + cycle driver → cycle 0 → READY=1 → continue.

**R. Logrotate handling (FR-43, FR-43.1)**

- **R-01: events.jsonl reopen via asyncinotify on parent directory** (IN_CREATE on basename + IN_MOVED_FROM on basename) — supervised producer task; same producer also watches Zao log directory.
- **R-02: .deb logrotate snippet ships in `create` mode** with EMPTY postrotate — we own the writer so inotify detects rename without needing logrotate signal.
- **R-03: In-memory reopen-window buffer:** `deque(maxlen=1000)`; flush on reopen; bump `events_dropped_total{reason="reopen_overflow"}` on overflow.
- **R-04: ZaoLogInotifyTailer handles BOTH rotation modes** (we don't own Zao's logrotate config): IN_MODIFY → `fstat.st_size` vs `last_known_offset` (copytruncate); IN_MOVE_SELF/IN_DELETE_SELF → reopen via parent-dir watch; opportunistic inode check.
- **R-05: qmi_wwan reload — NO special-case suppression.** pyudev producer signals UDEV → cycle re-observes → `present=False` (4×) → `state=disconnected` → `present=True` → `state=recovering(0)` → healthy.

**U. systemd unit file hardening (NFR-30, FR-53)**

- **U-01: CapabilityBoundingSet=** `CAP_NET_ADMIN CAP_SYS_ADMIN CAP_SYS_MODULE CAP_DAC_READ_SEARCH` (CAP_SYS_MODULE preallocated for Phase 4 — single unit-file edit at start of Phase 3).
- **U-02:** `Restart=on-failure` (NOT always); `RestartSec=10`; `StartLimitIntervalSec=300`; `StartLimitBurst=20`; `TimeoutStopSec=10s`; `KillMode=mixed`.
- **U-03 Sandboxing:** `ProtectSystem=strict`; `ReadWritePaths=/var/lib/spark-modem-watchdog /var/log/spark-modem-watchdog`; `ProtectHome=true`; `NoNewPrivileges=yes`; `RestrictNamespaces=net mnt`; `RuntimeDirectory=spark-modem-watchdog`; `RuntimeDirectoryPreserve=yes` (load-bearing); NO `PrivateMounts` (incompat with `LoadCredential` on systemd 245); `LoadCredential=webhook_hmac_secret:/etc/spark-modem-watchdog/hmac-secret`.
- **U-04:** `WatchdogSec=90s`; cycle-END kicks.
- **U-05: ExecStartPre extension:** B-03 import smoke test + `spark-modem ctl config-check`.

### Claude's Discretion

- kmsg classifier exact regex strings (E-03 enum is locked; regexes are data — may evolve based on bench-Jetson dmesg observations)
- Producer task naming convention (snake_case, suffix `_producer`)
- `inventory.scan()` netns derivation specifics (sysfs vs `ip netns identify`) — researcher / planner picks the most-stable sysfs read
- observer's identity-extraction qmicli call placement (`observer/probe.py` extension vs new `observer/identity.py`)
- kmsg dedup state shape (sliding window vs timestamp-of-last-emit)
- `cycle_drift_seconds` semantics for negative drift (early-wake); clamp to 0 vs report as-is
- Test seam Protocol locations (co-located per Phase 1/2 convention)
- Plan slicing within the 6–8 plan target (planner's call)

### Deferred Ideas (OUT OF SCOPE)

**Phase 4 (Destructive Actions & HIL):**
- Destructive actions (modem_reset, usb_reset, driver_reset) with signal-quality gate end-to-end (Phase 3 ships CAP_SYS_MODULE preallocated)
- kmsg classifier regex catalog growth (Phase 4 HIL surfaces new dmesg shapes)
- `oom` and `kill` reasons in DaemonStopReason classification (Phase 3 ships sigterm/crash/config_invalid only)
- HIL fault-injection lane: sd_notify watchdog actually kicks, StartLimitBurst=20 actually allows 20 restarts, LoadCredential delivers HMAC secret, qmi_wwan reload produces expected transition shape

**Phase 5 (Bench & Field Shadow):**
- Cross-fleet observation of dmesg variance for kmsg classifier widening
- WATCHDOG cadence calibration based on real-fleet histograms
- LoadCredential rotation procedure runbook

**v2.1 (already deferred):**
- HTTP API on Unix socket (CTL-01, CTL-02) — daemon NEVER accepts inbound IPC in v2.0
- Webhook batching (WHK-01, M-3)
- `ctl identity export/import` (CARR-01)
- `ctl simulate-issue` (SIM-01, M-24)
- 5G NR-aware policy (NR-01)

**Unrelated future work:**
- ADR-0014 "Event source supervision pattern" formalization
- D-Bus `zao-infra-ctrl.service` state subscription (PITFALLS §2.3 / §2.4)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FR-1 | System discovers all Sierra-VID modems on USB at startup AND on udev `add`/`remove` events | pyudev `Monitor.from_netlink()` + `loop.add_reader(fileno())` recipe (§Code Examples → udev producer); inventory cross-check on startup (existing Phase 2 SysfsInventory; Phase 3 swaps in UdevInventory) |
| FR-3 | System detects SIM identity (ICCID, IMSI) per modem and persists `(usb_path → identity)` map across reboots | observer extension via qmicli `--uim-get-card-status`; `StateStore.save_identity_map()` already exists with atomic globals_lock + state-store flock |
| FR-4 | System detects SIM swap (ICCID change at the same `usb_path`) and triggers re-provisioning | E-04: observer captures fresh ICCID/IMSI; cycle compares against `load_identity_map()`; on diff persist + reset `_healthy_streak` + counters in ONE atomic write per RECOVERY_SPEC §8; sha256[:8] redaction |
| FR-14 | System detects host-level issues (USB overcurrent, "device not accepting address", thermal events) from `dmesg` and treats them as global issues | `/dev/kmsg` non-blocking reader (§Code Examples → kmsg producer); E-03 classifier with closed `IssueDetail` enum + 30 s per-detail dedup; routes to events.jsonl + status.aggregate_health |
| FR-43 | Event log rotated via `logrotate` with 7-day, 100 MiB retention default | R-02: `.deb` ships logrotate snippet in `create` mode with empty postrotate; daemon reopens via R-01 inotify watch on parent directory |
| FR-43.1 | inotify tail tolerates BOTH `create`-mode rotation (MOVE_SELF/DELETE_SELF) AND `copytruncate` mode (st_size truncation check) | PITFALLS §8.1 dual-mode pattern verbatim (§Common Pitfalls → §8.1); ZaoLogInotifyTailer applies both modes |
| FR-53 | Daemon runs as a systemd `Type=notify` unit; graceful SIGTERM within 5 s | sdnotify recipe (§Code Examples → sd_notify integration); L-02 SIGTERM choreography with 5 s budget; subproc/runner already implements two-stage shutdown per PITFALLS §5.3 |
| FR-61 | Single PID lock on `/run/spark-modem-watchdog/lock` for the daemon | `fcntl.flock(LOCK_EX \| LOCK_NB)` recipe (§Code Examples → PID lock); kernel-released on death per PITFALLS §4.4 |
| FR-61.1 | Per-modem and state-store advisory `flock`s separate from PID lock; CLI mutating commands acquire the same locks the daemon does | ADR-0012 3-layer lock model already implemented in `state_store/locks.py`; PID lock is third file separate from state.lock and modem-{usb_path}.lock |
| FR-75 | Daemon emits `READY=1` via `sd_notify` after first full cycle; emits `STATUS=` keepalive each cycle; optional `WatchdogSec=90s` cadence | sdnotify pure-Python library; L-01 cadence with READY at cycle 0 end, STATUS each cycle, WATCHDOG at cycle-END |
| NFR-12 | Daemon tolerates `qmi_wwan` driver reload during operation: clean state transition, not a daemon crash | R-05: pyudev producer signals UDEV → cycle re-observes → present=False → disconnected → present=True → recovering → healthy; NO special-case predicate |
| NFR-13 | Daemon reaches steady-state operation within 60 s of process start, given Zao is already running | L-01: READY=1 at end of FIRST cycle, budget 45 s of the 60 s NFR-13; L-05 startup ordering minimizes pre-cycle latency |
| NFR-30 | Daemon runs as root; no other process granted suid bits | U-03 NoNewPrivileges=yes; CapabilityBoundingSet preallocated to Phase 4-forward; explicit no-suid-on-helpers verification |
</phase_requirements>

## Summary

Phase 3 swaps the laptop's polling-only fixture mode for production-grade Linux event-driven observation and `systemd Type=notify` lifecycle. The work decomposes into five orthogonal subsystems each with a well-known pitfall surface: pyudev for USB add/remove, pyroute2.AsyncIPRoute for link-state, asyncinotify for log rotation (Zao log + our own events.jsonl), `/dev/kmsg` reader for host-level kernel events, and sd_notify + signal handlers + PID lock + systemd unit hardening for lifecycle. CONTEXT.md has already locked all 16 implementation decisions (E-01..E-05, L-01..L-05, R-01..R-05, U-01..U-05); this research provides the **concrete recipes** the executor needs to write code and the **landmines** the planner needs to surface in `read_first` blocks.

The critical insight is that Phase 3 introduces **6 long-lived child tasks under one TaskGroup** (5 event-source producers + 1 cycle driver), each wrapped in `restart_on_crash`. Standard TaskGroup semantics (one task crashing → all cancelled) are explicitly subverted by catching `Exception` inside each producer wrapper and re-entering with bounded backoff. systemd's `WatchdogSec=90s` is the outer safety net for catastrophic all-producer-crash. **All event sources push opaque `WakeSignal` sentinels onto `event_queue`** (E-02) — state derives from full re-observation, not from event payloads; this honors PITFALLS §6.1's tight-read-loop prescription and matches ADR-0002's "events shorten cycle latency, cycle is the source of truth."

Phase 2 has already shipped 90% of the surfaces Phase 3 wires:
- `CycleScheduler.event_queue` is plumbed as no-op stub (M-02 → Phase 3 wires producers)
- `WebhookPoster.stop()` and `.drain(3.0)` already exist (W-01 → Phase 3 wires SIGTERM)
- `Settings(frozen=True)` + `RELOAD_DATA`/`RELOAD_RESTART` markers + helpers (Phase 1 → Phase 3 SIGHUP swap)
- `state_store/locks.py` 3-layer model with `acquire_flock_async` (ADR-0012 → Phase 3 PID lock is third separate file)
- `EventLogWriter` Phase 1 O_APPEND writer (Phase 3 adds `reopen()` + buffer)
- `DaemonRestart` envelope with `DaemonStopReason` enum already wired (Phase 2 emits CRASH; Phase 3 wires SIGTERM via marker)
- `InventorySource` and `ZaoLogTailer` Protocols (Phase 2 → Phase 3 swaps in event-driven impls; observer/ doesn't change)

**Primary recommendation:** Slice into 6 plans by subsystem boundary (udev+netns+inventory swap | rtnetlink | asyncinotify dual-watcher + EventLogWriter.reopen | kmsg + classifier + dedup | sd_notify + signal handlers + clean-shutdown marker + PID lock + .deb unit/logrotate | Linux integration tests). The plan-checker will verify each plan's `read_first` block names the relevant PITFALLS section by number.

## Architectural Responsibility Map

Single-tier daemon — no client/server split. Capability ownership is by **module boundary** within `src/spark_modem/`:

| Capability | Primary Module | Secondary Module | Rationale |
|------------|---------------|------------------|-----------|
| USB add/remove detection | `event_sources/udev_producer.py` | `inventory/udev.py` | Producer pushes opaque `WakeSignal.UDEV`; UdevInventory does the sysfs walk on cycle re-observation |
| netns derivation | `inventory/netns.py` | `inventory/sysfs.py` (extended) | Inventory is the only place that walks sysfs (per Phase 2 boundary); netns is a sysfs-readable attribute |
| netns-aware qmicli invocation | `qmi/wrapper.py` | `subproc/runner.py` | E-05: QmiWrapper auto-prepends `["ip", "netns", "exec", ns]` to argv; subproc runner is unchanged |
| Link-state subscription | `event_sources/rtnetlink_producer.py` | (none) | Tight read loop only; pushes `WakeSignal.RTNETLINK`; no parsing in the producer (§6.1) |
| Log rotation detection (Zao + events.jsonl) | `event_sources/asyncinotify_producer.py` | `zao_log/inotify_tailer.py`, `event_logger/inotify_reopener.py` | Single asyncinotify producer task watches BOTH directories; dispatches to two consumers |
| Zao log tailing | `zao_log/inotify_tailer.py` | (replaces `zao_log/parser.py` runtime; parser stays as test/replay helper) | Behind existing `ZaoLogTailer` Protocol — observer/ doesn't change |
| Events.jsonl reopen | `event_logger/inotify_reopener.py` | `event_logger/writer.py` (extended with reopen() + buffer) | R-01/R-03: dispatcher signals writer; writer holds the buffer |
| dmesg/kernel event ingestion | `event_sources/kmsg_producer.py` | `kmsg/classifier.py`, `kmsg/dedup.py` | Producer reads `/dev/kmsg`, classifier maps regex → IssueDetail enum, dedup collapses repeats |
| sd_notify lifecycle | `daemon/lifecycle.py` | (sdnotify lib) | READY/STATUS/WATCHDOG sent from main daemon PID only (PITFALLS §4.1) |
| SIGTERM shutdown choreography | `daemon/sigterm.py` | `daemon/lifecycle.py`, `webhook/poster.py` (uses existing stop()/drain()) | L-02: 8 strictly-ordered steps within 5 s budget |
| SIGHUP config reload | `daemon/sighup.py` | `config/settings.py` (existing Settings + reload markers), `webhook/dns.py`, `wire/carriers.py` | L-03: transactional swap at cycle boundary |
| Preflight checks | `daemon/preflight.py` | (none) | FR-60 PATH check + Settings validate gate before PID lock acquired |
| PID lock | `daemon/lifecycle.py` | `state_store/locks.py` (existing `acquire_flock` primitive) | Third separate file at /run/.../lock; kernel-released on death |
| Per-modem + state-store flock serialization | (existing — `state_store/store.py` already wires this) | `state_store/locks.py` | ADR-0012 invariant unchanged; CLI mutators take the same locks |
| systemd unit + logrotate snippet | `debian/spark-modem-watchdog.service`, `debian/spark-modem-watchdog.logrotate` | (build pipeline) | U-01..U-05 directives pinned at start of Phase 3 |

## Standard Stack

All libraries already pinned in Phase 1's `requirements.lock`. Phase 3 adds **zero new runtime dependencies**.

### Core (already pinned)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pyudev` | `>=0.24.4,<1` | USB add/remove subscription via `Monitor.from_netlink()` | Pure-Python ctypes binding to libudev.so.1; libudev ≥151 needed (Ubuntu 20.04 ships 245 — comfortable margin) [CITED: `.planning/research/STACK.md` §95] |
| `pyroute2` | `>=0.9.6,<1` | rtnetlink link-state subscription via `AsyncIPRoute` | Pure-Python; native asyncio support; only library exposing async netlink. NDB and sync IPRoute are deliberately rejected per CONTEXT.md [VERIFIED: Context7 `/svinota/pyroute2` — async API examples retrieved 2026-05-07] |
| `asyncinotify` | `>=4.0.10,<5` | Async inotify watches (Zao log + events.jsonl rotation) | Asyncio-native; replaces `inotify_simple` because rest of daemon is asyncio [CITED: `.planning/research/STACK.md` §99] |
| `sdnotify` | `>=0.3.2,<1` | `Type=notify` READY/STATUS/WATCHDOG | Pure-Python; writes to `$NOTIFY_SOCKET` — no system-Python C lib. systemd-python is rejected (overkill, requires system Python) [VERIFIED: Context7 `/bb4242/sdnotify` — README examples retrieved 2026-05-07] |
| `httpx` | `>=0.27,<1` | Webhook POST | (already wired in Phase 2; Phase 3 just uses existing `webhook_poster.drain(3.0)` from SIGTERM) [CITED: STACK.md §92] |

### Stdlib (no install)

| Module | Purpose | Why |
|--------|---------|-----|
| `asyncio` (3.12 stdlib) | TaskGroup, asyncio.timeout, `loop.add_reader`, `loop.add_signal_handler` | The 6-task supervisor pattern + `add_reader(fd)` for non-blocking reads (kmsg, udev) + `add_signal_handler` for SIGTERM/SIGHUP all live in stdlib asyncio [VERIFIED: Python 3.12 stdlib documentation] |
| `fcntl` (POSIX) | `flock(LOCK_EX \| LOCK_NB)` for PID lock and per-modem lock files | Already used by `state_store/locks.py`; PID lock just adds a third file [VERIFIED: existing code at `src/spark_modem/state_store/locks.py:40-50`] |
| `os` | `O_RDONLY \| O_NONBLOCK`, `lseek(SEEK_END)` for `/dev/kmsg` reader; `os.unlink` for marker + UDS metrics socket | Standard kmsg recipe per `.planning/research/SUMMARY.md` §4.2 |
| `signal` | `signal.SIGTERM`, `signal.SIGHUP`, `signal.SIGKILL` constants — installed via `loop.add_signal_handler()`, NEVER `signal.signal()` from asyncio (anti-pattern catalogue) | [CITED: SUMMARY.md §4.4 anti-pattern #6] |

### Verification

```bash
# Verified 2026-05-07 against requirements.lock (Phase 1 lockfile compiled with --python-platform linux):
# pyudev==0.24.4 (Linux-only; libudev.so.1 dlopen)
# pyroute2==0.9.16 (latest stable)
# asyncinotify==4.0.16 (latest stable)
# sdnotify==0.3.2 (no further releases; reference impl)
# httpx==0.28.x (already shipped in Phase 2)
```

[ASSUMED] Exact patch versions in `requirements.lock` were compiled in Phase 1 — planner should verify with `grep -E '^(pyudev|pyroute2|asyncinotify|sdnotify)' requirements.lock` before assuming versions.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `pyudev.Monitor` + `add_reader` | `pyudev.MonitorObserver` (thread-based) | REJECTED — observer thread crashes silently under bulk events (PITFALLS §7.1 cites pyudev #194/#363/#402); restart pattern is non-trivial |
| `pyroute2.AsyncIPRoute` | `pyroute2.IPRoute` (sync) + `loop.run_in_executor` | REJECTED — sync IPRoute calls would block the event loop or require thread-pool overhead; AsyncIPRoute is native asyncio |
| `asyncinotify` | `inotify_simple` | REJECTED — `inotify_simple` is sync; would need thread shim. asyncinotify is asyncio-native [CITED: STACK.md §99] |
| `sdnotify` | `systemd-python` | REJECTED — requires system Python C library; we deliberately ship our own bundled CPython 3.12 (ADR-0010); sdnotify is pure-Python (~30 LOC) [CITED: STACK.md §93] |
| `loop.add_signal_handler()` | `signal.signal()` from a coroutine | REJECTED — `signal.signal()` from asyncio is in CLAUDE.md's anti-pattern catalogue; signal arrives in arbitrary thread, breaks loop invariants [CITED: CLAUDE.md §"Anti-patterns"] |
| `dh-virtualenv` | (already rejected in Phase 1; ADR-0010) | Phase 3 doesn't add packaging changes — just amends existing unit file directives |

**Installation:** No new dependencies — Phase 3 reuses Phase 1's `requirements.lock` verbatim.

## Architecture Patterns

### System Architecture Diagram

```
                                     ┌─────────────────────────────────────────────────────────────┐
                                     │                  asyncio.TaskGroup                          │
                                     │  (one daemon process; child task crash isolated by          │
                                     │   restart_on_crash wrappers — TaskGroup never sees Exception)│
                                     └─────────────────────────────────────────────────────────────┘
                                                            │
       ┌─────────────────┬─────────────────┬────────────────┼────────────────┬──────────────────┬─────────────────────┐
       │                 │                 │                │                │                  │                     │
       ▼                 ▼                 ▼                ▼                ▼                  ▼                     ▼
 ┌──────────┐      ┌────────────┐    ┌────────────┐   ┌────────────┐   ┌──────────┐      ┌────────────┐       ┌────────────────┐
 │   udev   │      │ rtnetlink  │    │ asyncinotify│   │   kmsg     │   │  cycle   │      │ sdnotify   │       │  signal        │
 │ producer │      │  producer  │    │ producer    │   │  producer  │   │  driver  │      │  ticker    │       │  handlers      │
 │          │      │            │    │ (zao + ev)  │   │            │   │          │      │            │       │ (SIGTERM/HUP)  │
 └──────────┘      └────────────┘    └────────────┘   └────────────┘   └──────────┘      └────────────┘       └────────────────┘
       │                 │                 │                │                │                  │                     │
       │ pyudev.Monitor  │ AsyncIPRoute    │ Inotify dir    │ /dev/kmsg     │  observe →       │ READY/STATUS/        │ loop.add_signal_
       │ +add_reader(fd) │ +bind() +async  │ watches: parent│ O_RDONLY|     │  policy →        │ WATCHDOG=1           │ handler() —
       │ NOT Observer    │ for msg in ipr  │ of zao log AND │ NONBLOCK +    │  actions →       │ from main PID        │ never signal.
       │                 │                 │ parent of      │ lseek(SEEK_END│  persist →       │ only                 │ signal() from
       │                 │                 │ events.jsonl   │ )+add_reader  │  status →        │                      │ asyncio
       │                 │                 │                │               │  webhook         │                      │
       ▼                 ▼                 ▼                ▼                ▼                  ▼                     ▼
   put_nowait(       put_nowait(      put_nowait(       put_nowait(    Cycle does FULL    sd_notify           SIGTERM →
   WakeSignal       WakeSignal        WakeSignal       WakeSignal     re-observation       writes to            sigterm.py
   .UDEV)           .RTNETLINK)       .ZAO_LOG /       .KMSG)         pass — state         $NOTIFY_SOCKET       choreography:
       │                 │             EVENTS_LOG_         │           NEVER comes from                          1. cancel cycle
       │                 │             ROTATED)            │           event payload                             2. cancel
       └─────────────────┴───────────────┬─────────────────┘                                                     producers
                                         │                                                                       3. drain(3.0)
                                         ▼                                                                       4. flush state
                            ┌────────────────────────────┐                                                       5. DaemonStopped
                            │ event_queue (asyncio.Queue) │                                                      6. close socket
                            │  drop-on-full acceptable    │                                                      7. clean-shutdown
                            │  (next cycle catches up)    │                                                         marker
                            └────────────────────────────┘                                                       8. PID lock fd
                                         │                                                                          close → exit 0
                                         ▼                                                                          (5 s budget)
                            ┌────────────────────────────┐
                            │ CycleScheduler.wait({sleep,│
                            │   queue.get},              │           ┌─────────────────────────────────────┐
                            │   FIRST_COMPLETED)         │           │ /run/spark-modem-watchdog/          │
                            │ - Wakes on event OR 30s    │           │   ├── lock              (PID lock)  │
                            │ - cycle_drift can go neg.  │           │   ├── state.lock        (state-store flock)
                            │ - drop-on-full → cycle     │           │   ├── modem-{usb_path}.lock (per-modem)│
                            │   eventually catches up    │           │   ├── clean-shutdown    (tmpfs marker│
                            └────────────────────────────┘           │   │                       JSON body) │
                                         │                            │   ├── last-config-error           │
                                         │                            │   └── metrics.sock      (UDS — Phase 2)
                                         ▼                            └─────────────────────────────────────┘
                            ┌────────────────────────────┐
                            │ CycleDriver.run_one_cycle  │           ┌─────────────────────────────────────┐
                            │ (Phase 2; Phase 3 just     │           │ /var/lib/spark-modem-watchdog/       │
                            │  invokes it in a loop)     │           │   ├── state/by-usb/<usb_path>.json   │
                            │                            │           │   ├── globals.json                   │
                            │ For SIM-swap: load_identity│           │   └── identity-map.json              │
                            │ _map() → compare → reset   │           └─────────────────────────────────────┘
                            │ streak+counters in ONE     │
                            │ atomic state-write per     │           ┌─────────────────────────────────────┐
                            │ RECOVERY_SPEC §8 ordering  │           │ /var/log/spark-modem-watchdog/       │
                            └────────────────────────────┘           │   └── events.jsonl  (logrotate       │
                                                                     │       create mode — daemon reopens   │
                                                                     │       via asyncinotify producer)     │
                                                                     └─────────────────────────────────────┘
```

**Reading the diagram:** Five event sources push opaque wake signals onto a shared queue; the cycle scheduler waits on (queue OR 30 s sleep, FIRST_COMPLETED). On any wake, the cycle driver does a FULL re-observation pass (state derives from observation, not from the event payload — E-02 critical invariant). sd_notify and signal handlers are siblings of the producers. SIGTERM choreography is sequenced through `daemon/sigterm.py` per L-02's 8 strict steps.

### Recommended Project Structure

```
src/spark_modem/
├── inventory/
│   ├── descriptor.py            # Phase 1 — ModemDescriptor.ns: str | None (already exists)
│   ├── protocol.py              # Phase 2 — InventorySource Protocol (unchanged)
│   ├── sysfs.py                 # Phase 2 — SysfsInventory (Phase 3 extends with ns derivation)
│   ├── udev.py                  # Phase 3 NEW — UdevInventory impl of InventorySource
│   └── netns.py                 # Phase 3 NEW — netns derivation from sysfs
├── event_sources/               # Phase 3 NEW package
│   ├── __init__.py
│   ├── supervisor.py            # restart_on_crash wrapper + WakeSignal StrEnum
│   ├── udev_producer.py         # pyudev.Monitor + loop.add_reader
│   ├── rtnetlink_producer.py    # pyroute2.AsyncIPRoute
│   ├── kmsg_producer.py         # /dev/kmsg O_NONBLOCK reader
│   └── asyncinotify_producer.py # shared inotify watch (Zao log + events.jsonl rotate)
├── kmsg/                        # Phase 3 NEW package
│   ├── __init__.py
│   ├── classifier.py            # regex → IssueDetail mapping (E-03)
│   └── dedup.py                 # per-detail 30 s sliding-window dedup
├── zao_log/
│   ├── protocol.py              # Phase 2 (unchanged)
│   ├── parser.py                # Phase 2 (kept as test/replay helper)
│   └── inotify_tailer.py        # Phase 3 NEW — replaces parser.py at runtime
├── daemon/
│   ├── main.py                  # Phase 2 wiring → Phase 3 long-lived event loop
│   ├── cycle_driver.py          # Phase 2 (unchanged)
│   ├── cycle_scheduler.py       # Phase 2 (Phase 3 just wires the event_queue arm)
│   ├── lifecycle.py             # Phase 3 NEW — sdnotify wrapper, signal handlers, marker IO, PID lock
│   ├── sighup.py                # Phase 3 NEW — transactional Settings swap
│   ├── sigterm.py               # Phase 3 NEW — choreographed shutdown sequence
│   └── preflight.py             # Phase 3 NEW — FR-60 PATH check + Settings validate gate
├── event_logger/
│   ├── writer.py                # Phase 1 (Phase 3 extends with reopen() + buffer)
│   └── inotify_reopener.py      # Phase 3 NEW — reopen-on-rotate dispatcher
├── qmi/
│   └── wrapper.py               # Phase 2 (Phase 3 modifies argv-build to prepend ip netns exec)
└── webhook/
    ├── poster.py                # Phase 2 stop() + drain(3.0) (unchanged; just called from SIGTERM)
    └── dns.py                   # Phase 2 DnsCache.resolve() (unchanged; called from SIGHUP)

debian/
├── spark-modem-watchdog.service     # Phase 1 base unit + Phase 3 hardening (U-01..U-05)
├── spark-modem-watchdog.logrotate   # Phase 3 NEW — create mode, empty postrotate
└── ...

tests/
├── fakes/                       # Phase 3 adds these:
│   ├── udev.py                  # FakeUdevMonitor
│   ├── rtnetlink.py             # FakeAsyncIPRoute
│   ├── asyncinotify.py          # FakeAsyncinotify (yields canned events)
│   ├── kmsg.py                  # FakeKmsgReader
│   ├── sdnotify.py              # FakeSdNotify recording READY/STATUS/WATCHDOG
│   └── pidlock.py               # FakePIDLock (asyncio.Lock fallback for non-POSIX)
├── fixtures/
│   ├── kmsg/                    # dmesg lines for classifier tests
│   └── zao_log/rotated/{create,copytruncate}/  # rotation scenarios
└── integration/                 # Phase 3 NEW tier
    └── test_lifecycle.py        # SIGTERM/SIGHUP end-to-end (skipif(win32))
```

### Pattern 1: TaskGroup + restart_on_crash supervisor (E-01)

**What:** Six long-lived child tasks under one TaskGroup, each wrapped in a wrapper that catches `Exception` and re-enters with bounded backoff.

**When to use:** Any time you have multiple long-lived async producers that must survive their own crashes without taking down the rest of the daemon.

**Why this works against Python 3.12 TaskGroup default:** TaskGroup's documented behavior is "if any task raises an unhandled exception, the group is cancelled and the exception propagates from `__aexit__`." The wrapper catches `Exception` BEFORE it escapes the task body — so from TaskGroup's perspective, no task ever fails. Only `BaseException` (KeyboardInterrupt, SystemExit, CancelledError) escapes — exactly the propagation semantics we want.

**Example shape:**

```python
# Source: derived from asyncio docs + PITFALLS §6.1, §7.1, §8.1; pattern compatible with Python 3.12
import asyncio
import logging

logger = logging.getLogger(__name__)

async def restart_on_crash(
    name: str,
    factory,  # Callable[[], Awaitable[None]]
    *,
    event_logger,
    backoffs: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 60.0),
) -> None:
    """Re-enter `factory()` on Exception with bounded backoff. Never raises Exception."""
    attempt = 0
    while True:
        try:
            await factory()
            # Producer returned normally; supervisor exits (this is rare —
            # producers typically loop forever; a clean return == "intentional
            # shutdown" e.g. on CancelledError propagating up).
            return
        except asyncio.CancelledError:
            # Pass through — TaskGroup is shutting us down via SIGTERM.
            raise
        except Exception:  # noqa: BLE001 — supervisor catches all to self-heal
            logger.exception("event_source_crashed source=%s", name)
            event_logger.append(...)  # event_source_crashed structured event
            delay = backoffs[min(attempt, len(backoffs) - 1)]
            attempt += 1
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                raise
            # loop and re-enter factory()
```

### Pattern 2: pyudev.Monitor + loop.add_reader (PITFALLS §7.1 PRESCRIPTIVE)

**What:** Subscribe to USB events via netlink monitor without spawning a thread.

**When to use:** Any subscription to libudev events from asyncio.

**Critical invariant:** NEVER use `pyudev.MonitorObserver` (PITFALLS §7.1 cites pyudev #194/#363/#402 — observer thread crashes silently under bulk events).

**Recipe:**
1. `Monitor.from_netlink(Context())` — netlink-source monitor
2. `monitor.filter_by(subsystem='usb')` — narrow to USB events
3. `monitor.set_receive_buffer_size(4 * 1024 * 1024)` — 4 MiB to survive hub power-cycle storm (PITFALLS §7.3 storm = 16+ events in 2 s)
4. `monitor.start()` — open the socket; do NOT call `.poll()` afterwards
5. `loop.add_reader(monitor.fileno(), callback)` — callback is sync, drains all available events with non-blocking `monitor.poll(timeout=0)` calls
6. **Wait for `bind` event, NOT `add`** (PITFALLS §7.2: sysfs not fully populated on `add`; cdc-wdmN symlinks have a 50–200 ms window). If you must use `add`, retry sysfs reads 3× with 100 ms backoff.
7. On any `add`/`remove`/`bind`/`unbind`, call `event_queue.put_nowait(WakeSignal.UDEV)` and return. NO sysfs reads in the producer — the cycle does the re-observation.

### Pattern 3: pyroute2.AsyncIPRoute tight read loop (PITFALLS §6.1)

**What:** Subscribe to RTNETLINK link-state without ENOBUFS during USB hub re-enumeration storms.

**When to use:** Any rtnetlink subscription from asyncio.

**Recipe:**
1. `async with AsyncIPRoute() as ipr:` — async context manager guarantees socket cleanup (PITFALLS §6.3)
2. `ipr.bind(groups=RTMGRP_LINK)` — subscribe ONLY to link-state changes (subscribing to the full multicast set wastes buffer)
3. **Set `SO_RCVBUF = 4 MiB` explicitly** — kernel default 256 KiB is too small (PITFALLS §6.1)
4. `async for msg in ipr.get():` — tight loop; do NOTHING in the loop body except `event_queue.put_nowait(WakeSignal.RTNETLINK)`. NO parsing, NO state update, NO logging.
5. On `OSError(ENOBUFS)`: close socket, reopen, force inventory refresh (emit `rtnetlink_resubscribed` event). The `restart_on_crash` wrapper handles the reopen automatically — let ENOBUFS escape the producer task and the wrapper restarts the factory.

[VERIFIED: Context7 `/svinota/pyroute2` confirms `AsyncIPRoute` async API and `bind()` semantics; the sync `IPRoute().bind()` example in their docs has identical multicast-subscription semantics — the async version uses the same socket option machinery.]

### Pattern 4: asyncinotify dual-mode logrotate watcher (PITFALLS §8.1)

**What:** Survive logrotate in either `create` mode (rename → new inode) or `copytruncate` mode (same inode, truncate to 0).

**When to use:** ANY tail of a log file written by an external process whose logrotate config you don't control (Zao log fits this exactly).

**Recipe (PITFALLS §8.1 verbatim, transcribed for code shape):**

```python
# Mask: subscribe to BOTH the file's data events AND its rotation events,
# AND the parent directory for re-creation.
from asyncinotify import Inotify, Mask

# On the parent directory (handles file-absent-at-startup §8.2):
parent_mask = Mask.CREATE | Mask.MOVED_TO  # file appears
# On the file itself (when present):
file_mask = (
    Mask.MODIFY        # new lines appended
    | Mask.MOVE_SELF   # create-mode rotation (inode moved)
    | Mask.DELETE_SELF # file deleted
    | Mask.CLOSE_WRITE # external writer closed (defensive)
)

async with Inotify() as ino:
    parent_watch = ino.add_watch(log_dir, parent_mask)
    if log_path.exists():
        file_watch = ino.add_watch(log_path, file_mask)
    else:
        file_watch = None  # waiting on parent IN_CREATE

    last_offset = 0
    last_inode = None
    if log_path.exists():
        st = os.fstat(open(log_path, 'rb').fileno())
        last_inode = st.st_ino

    async for event in ino:
        # Coalesce: drain ALL pending events from this batch before reacting,
        # then do ONE re-read pass to EOF. PITFALLS §8.3: multiple writes
        # batch into one IN_MODIFY — read-to-EOF in a loop, never assume
        # one event == one new line.

        if Mask.MOVE_SELF in event.mask or Mask.DELETE_SELF in event.mask:
            # CREATE mode rotation — file is gone; wait for parent IN_CREATE
            # to recreate the watch. event_queue.put_nowait(WakeSignal.ZAO_LOG)
            # so the cycle observes the gap.
            ...
        elif event.path and event.path.name == log_path.name and Mask.CREATE in event.mask:
            # File reappeared after CREATE rotation — switch watch to it.
            file_watch = ino.add_watch(log_path, file_mask)
            last_offset = 0
            last_inode = os.stat(log_path).st_ino
            # Push WakeSignal so cycle re-reads.
        elif Mask.MODIFY in event.mask:
            # Two cases interleave:
            # 1. Normal append (st_size grew)
            # 2. copytruncate (st_size SHRUNK to a value < last_offset)
            try:
                st = os.stat(log_path)
            except FileNotFoundError:
                continue  # raced with delete; next event will fire
            if st.st_size < last_offset:
                # COPYTRUNCATE detected — reset offset, full re-read
                last_offset = 0
                # event_queue.put_nowait(WakeSignal.ZAO_LOG)
            if st.st_ino != last_inode:
                # Opportunistic inode check — also catches edge cases where
                # the writer recreated the file with same name
                last_inode = st.st_ino
                last_offset = 0
            # else: normal append; consumer reads from last_offset to EOF
```

**Two consumers, one producer:** The producer task watches BOTH `/var/log/spark-modem-watchdog/` (for events.jsonl rotation → calls `EventLogWriter.reopen()`) AND `/var/log/zao/` (for Zao log rotation → calls `ZaoLogInotifyTailer.reopen()`). Two `Inotify()` instances inside one `async with` block share the same task; dispatch by inspecting `event.watch` against the two `add_watch` return values.

[CITED: `.planning/research/PITFALLS.md` §8.1, §8.2, §8.3, §8.4 verbatim — prescription is direct from there.]

### Pattern 5: /dev/kmsg non-blocking reader (SUMMARY §4.2 + structured kmsg format)

**What:** Tail kernel log messages from `/dev/kmsg` without blocking the asyncio loop.

**When to use:** Detecting host-level kernel events (USB overcurrent, thermal throttle, qmi_wwan probe failures).

**Why blocking read is anti-pattern:** Per CLAUDE.md anti-pattern catalogue, blocking read on `/dev/kmsg` from asyncio is forbidden — `/dev/kmsg` is a streaming device, a naive `read()` blocks until next message arrives.

**Recipe:**

```python
# Source: derived from kernel.org Documentation/admin-guide/abi-testing.rst
# (sysfs interface for /dev/kmsg) + SUMMARY.md §4.2 prescribed shape.
import os
import asyncio

KMSG_DEV = "/dev/kmsg"

def open_kmsg() -> int:
    fd = os.open(KMSG_DEV, os.O_RDONLY | os.O_NONBLOCK)
    # Skip the historical ring buffer — only NEW messages since daemon start.
    os.lseek(fd, 0, os.SEEK_END)
    return fd

# /dev/kmsg structured line format (kernel >= 3.5):
#   <priority>,<sequence>,<timestamp_us>,<flags>;<message>
#   followed by zero or more " <key>=<value>\n" continuation lines until "\n"
# Example: "6,12345,3456789,-;usb 1-3.1.1: USB disconnect, address 17"
# Each read() returns ONE record; partial records never returned (kernel guarantee).

def on_kmsg_readable(fd: int, event_queue, classifier, dedup) -> None:
    while True:
        try:
            chunk = os.read(fd, 8192)  # ONE record per read
        except BlockingIOError:
            return  # drained
        except OSError as e:
            if e.errno == errno.EPIPE:
                # Reader fell behind; ring buffer overwrote us. Read returns
                # EPIPE; subsequent reads resume at current position.
                continue
            raise
        if not chunk:
            return
        # Parse the structured line; extract message text.
        try:
            header, _, payload = chunk.decode("utf-8", errors="replace").partition(";")
            line = payload.split("\n", 1)[0]  # message line, drop continuation
        except Exception:
            continue  # malformed; skip
        detail = classifier.classify(line)
        if detail is not None and dedup.should_emit(detail):
            event_queue.put_nowait(WakeSignal.KMSG)
            # Producer also dispatches to the Issue emitter — single write per
            # classified line; cycle re-observation collects pending Issues.

# Wire-up:
fd = open_kmsg()
loop.add_reader(fd, on_kmsg_readable, fd, event_queue, classifier, dedup)
```

**Sequence-number gap detection:** The `<sequence>` field is monotonic; if your last-seen sequence + 1 != current sequence, the kernel ring buffer wrapped (we fell behind). Bump a `kmsg_sequence_gaps_total` counter; emit one-shot warning. This is a self-health signal, not a fault — the daemon should keep running.

**Regex catalog for E-03 (per CONTEXT.md decisions, regexes are claude's discretion data):**

```python
# Source: regex shapes derived from Linux kernel source (drivers/usb/core/{hub.c,driver.c})
# and Tegra L4T kernel patches; DO NOT hardcode without bench verification.
KMSG_PATTERNS: list[tuple[re.Pattern[str], IssueDetail]] = [
    (re.compile(r"USB \S+: device not accepting address"),  IssueDetail.usb_enum_failure),
    (re.compile(r"over-current.*on port"),                    IssueDetail.usb_overcurrent),
    (re.compile(r"thermal.*throttl(ing|ed)"),                 IssueDetail.thermal_throttle),
    (re.compile(r"qmi_wwan.*probe.*fail(ed)?"),               IssueDetail.qmi_wwan_probe_fail),
    (re.compile(r"tegra-xusb.*power.*loss"),                  IssueDetail.tegra_hub_psu_droop),
]
# Fallback: detail = unknown; raw line stored in a separate field for forensic.
```

### Pattern 6: sd_notify cadence + main-PID safety (PITFALLS §4.1)

**What:** Send READY=1 / STATUS= / WATCHDOG=1 to systemd via sd_notify protocol.

**Why send only from main daemon PID:** sd_notify protocol routes by `/proc/$sender_pid/cgroup` lookup. If the sender PID exits between write and lookup (or if a fork happens), systemd drops the message and starts the unit's TimeoutStartSec timer. Send only from the main asyncio loop, never from a worker thread or subprocess (PITFALLS §4.1 cites systemd#2737).

**Why READY=1 only after first cycle:** "Meaningful readiness." If we send READY=1 immediately on Python interpreter startup, systemd marks the unit Active before we've actually observed anything. NFR-13 says steady state in 60 s; budget READY at end of cycle 0 (≤45 s of the 60 s).

**Why WATCHDOG=1 at cycle-END not cycle-START:** A stuck mid-cycle would still be inside the "kicked at start" 90 s window — too forgiving. Cycle-end means "last cycle completed successfully; if 90 s passes without another cycle-end, we're hung."

**Recipe:**

```python
# Source: Verified against Context7 /bb4242/sdnotify README examples (retrieved 2026-05-07).
# sdnotify is pure-Python; just writes a string to $NOTIFY_SOCKET (Unix datagram socket).
import sdnotify
import os

class SdNotifyLifecycle:
    def __init__(self) -> None:
        # SystemdNotifier silently no-ops when $NOTIFY_SOCKET is unset
        # (e.g. running on a laptop dev host, NOT under systemd) — by design.
        self._notifier = sdnotify.SystemdNotifier()
        self._enabled = bool(os.environ.get("NOTIFY_SOCKET"))

    def ready(self, status_message: str = "READY") -> None:
        # Compound notify per sd_notify protocol: multiple lines per packet.
        self._notifier.notify(f"READY=1\nSTATUS={status_message}")

    def status(self, message: str) -> None:
        self._notifier.notify(f"STATUS={message}")

    def watchdog_kick(self) -> None:
        # Sent at cycle-END after WATCHDOG_USEC's worth of work succeeded.
        # systemd's WatchdogSec=90s gives us 90 s between kicks before reset.
        self._notifier.notify("WATCHDOG=1")

    def stopping(self, message: str = "Shutting down") -> None:
        # Notify systemd we received SIGTERM and are shutting down. Optional;
        # not required for the 5 s TimeoutStopSec to honor our exit. Keeps
        # systemctl status output truthful during shutdown.
        self._notifier.notify(f"STOPPING=1\nSTATUS={message}")
```

**Cycle-end wiring example:**

```python
# In the cycle loop (daemon/main.py shape, Phase 3):
async def cycle_loop(driver, scheduler, lifecycle, settings) -> None:
    cycle_count = 0
    while True:
        result = await driver.run_one_cycle(...)
        cycle_count += 1
        if cycle_count == 1:
            lifecycle.ready(f"cycle=1 healthy={result.healthy_count}/4")
        else:
            lifecycle.status(
                f"cycle={cycle_count} healthy={result.healthy_count}/4 "
                f"actions={result.actions_executed} drift={result.drift_seconds:.1f}s"
            )
        lifecycle.watchdog_kick()  # AFTER successful cycle work
        # Wait for next deadline OR an event
        ...
```

[VERIFIED: Context7 `/bb4242/sdnotify` examples retrieved 2026-05-07 confirm the `SystemdNotifier.notify(...)` API shape and pure-Python implementation.]

### Pattern 7: loop.add_signal_handler — installed BEFORE TaskGroup (CLAUDE.md anti-pattern §6)

**What:** Install async-safe SIGTERM/SIGHUP handlers via the asyncio event loop.

**Why:** `signal.signal()` invokes the handler in an arbitrary thread, breaking asyncio invariants. `loop.add_signal_handler()` schedules a coroutine on the loop's main thread when the signal arrives — no thread-safety hazards.

**Why install BEFORE TaskGroup launches:** Once a TaskGroup is entered, the main coroutine is blocked in `__aenter__/__aexit__` and any `add_signal_handler` call from a child task would race against signal delivery. Install handlers in `daemon/main.py` BEFORE `async with asyncio.TaskGroup() as tg:`, capture references to the handler coroutines, and have the handlers call `tg.cancel()` (sets the group's cancel scope) and signal the cycle driver to begin its choreographed shutdown.

**Recipe:**

```python
# Source: Python 3.12 asyncio docs (https://docs.python.org/3/library/asyncio-eventloop.html#unix-signals)
# CLAUDE.md anti-pattern catalogue forbids signal.signal() from asyncio.
import asyncio
import signal

async def main() -> int:
    loop = asyncio.get_running_loop()

    sigterm_event = asyncio.Event()
    sighup_event = asyncio.Event()

    # Install BEFORE entering TaskGroup. Handlers are SYNCHRONOUS callbacks
    # scheduled on the loop's main thread — keep them tiny: just set events.
    loop.add_signal_handler(signal.SIGTERM, sigterm_event.set)
    loop.add_signal_handler(signal.SIGHUP,  sighup_event.set)
    # Note: SIGINT is handled by asyncio.run by default (raises KeyboardInterrupt).
    # Don't override it unless you have a reason.

    try:
        async with asyncio.TaskGroup() as tg:
            # Spawn 5 producers + 1 cycle driver + 1 SIGTERM watcher + 1 SIGHUP watcher
            tg.create_task(restart_on_crash("udev_producer", udev_factory, ...))
            tg.create_task(restart_on_crash("rtnetlink_producer", rtnetlink_factory, ...))
            # ... 3 more producers ...
            tg.create_task(cycle_driver_loop(...))
            tg.create_task(sigterm_watcher(sigterm_event, tg, sigterm_choreography))
            tg.create_task(sighup_watcher(sighup_event, settings_swapper))
    finally:
        loop.remove_signal_handler(signal.SIGTERM)
        loop.remove_signal_handler(signal.SIGHUP)

    return 0
```

**SIGTERM watcher coroutine:**

```python
async def sigterm_watcher(event, taskgroup, choreography) -> None:
    await event.wait()
    # Begin L-02's 5 s choreography; TaskGroup gets cancelled at the end.
    await choreography.execute(deadline_seconds=5.0)
    # All cleanup done; raise CancelledError to unwind the TaskGroup cleanly.
    # (Or call taskgroup._abort() / equivalent; in practice the choreography
    #  cancels children explicitly so this just returns.)
```

### Pattern 8: PID lock at /run/.../lock — third file separate from existing flocks (ADR-0012 + PITFALLS §4.4)

**What:** Single-instance daemon enforcement via `flock(LOCK_EX|LOCK_NB)` on a dedicated lock file.

**Why kernel-released:** `flock()` is released automatically by the kernel when the holding process dies (any signal, including SIGKILL). No `atexit` cleanup needed; no PID-file staleness. PITFALLS §4.4: "PID-lock check uses flock(2) not just PID-exists. flock() is automatically released on process death (kernel-level), so a stale-PID file with a missing flock means 'safe to take over.'"

**Why three SEPARATE files (not one):** ADR-0012 mandates the PID lock is a separate concern from cross-process state-store serialization:
- `/run/spark-modem-watchdog/lock` — PID lock; single-instance daemon enforcement
- `/run/spark-modem-watchdog/state.lock` — state-store flock; daemon AND CLI mutators serialize
- `/run/spark-modem-watchdog/modem-{usb_path}.lock` — per-modem flock; daemon + ctl reset-state-on-modem-X serialize

If they were one file, a CLI mutator would block daemon startup; the daemon would block ctl mutators after takeover. The three-file split lets the daemon launch and own its instance lock while CLI mutators can come and go on the per-modem flock without ever contesting the PID lock.

**Why `RuntimeDirectoryPreserve=yes` is load-bearing:** Without it, `RuntimeDirectory=spark-modem-watchdog` directive deletes the entire `/run/spark-modem-watchdog/` directory on systemd-supervised stop, taking out clean-shutdown marker, state.lock, modem-*.lock, AND metrics.sock — all of which Phase 3 depends on persisting across stop/start.

**Recipe:**

```python
# Source: existing implementation pattern in
# src/spark_modem/state_store/locks.py:108-161 — PID lock just creates
# a third file at /run/.../lock and re-uses acquire_flock helpers verbatim.
import contextlib
import errno
import fcntl
import os
from pathlib import Path

class PidLockHeldError(RuntimeError):
    """Another instance holds /run/.../lock."""
    def __init__(self, holder_pid: int | None) -> None:
        self.holder_pid = holder_pid

@contextlib.contextmanager
def acquire_pid_lock(path: Path = Path("/run/spark-modem-watchdog/lock")):
    """Acquire the daemon-instance PID lock.

    Released automatically when the daemon process dies (kernel-level flock
    cleanup — no atexit needed).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o640)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                holder = _read_pid_from(path)
                raise PidLockHeldError(holder) from e
            raise
        # Write our PID so operators can identify the holder
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode("ascii"))
        os.fsync(fd)
        yield fd
    finally:
        # On clean shutdown we explicitly release; on crash, kernel handles it.
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
```

[VERIFIED: existing `state_store/locks.py:108-161` implements an identical pattern for `state.lock` and per-modem locks; PID lock is a third invocation site.]

### Pattern 9: SIGTERM choreography — strict 8-step ordering (L-02)

**What:** A single coroutine that owns the 5 s shutdown budget and executes 8 steps in strict order.

**Why strict order:** Several pairs of steps are NOT commutative —
- webhook drain MUST come AFTER cycle cancel (so the drain sees any final-cycle transitions enqueued during the cycle's last action-execute)
- webhook drain MUST come BEFORE metrics socket close (drain emits `webhook_delivery_total{result}` which writes to the registry; the registry is exposed via the UDS socket)
- clean-shutdown marker MUST come AFTER all event emission (so its `cycle_count` reflects all events written this run)
- PID lock release MUST come LAST (kernel can release on crash; explicit release lets the next instance acquire without `LOCK_NB` retry)

**Recipe (skeleton only — full implementation lands in `daemon/sigterm.py`):**

```python
@dataclass
class SigtermChoreography:
    cycle_driver_task: asyncio.Task
    producer_tasks: list[asyncio.Task]
    webhook_poster: WebhookPoster
    state_store: StateStore
    event_logger: EventLogWriter
    metrics_socket_path: Path
    clean_shutdown_marker_path: Path
    pid_lock_fd: int
    clock: Clock
    boot_monotonic: float
    cycle_count_ref: list[int]  # mutable container

    async def execute(self, *, deadline_seconds: float = 5.0) -> None:
        deadline = self.clock.monotonic() + deadline_seconds

        # 1. Cancel cycle driver task. subproc/runner's two-stage shutdown
        #    drains in-flight qmicli per PITFALLS §5.3.
        self.cycle_driver_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.cycle_driver_task

        # 2. Cancel the 5 event-source producer tasks
        for t in self.producer_tasks:
            t.cancel()
        for t in self.producer_tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t

        # 3. webhook_poster.drain(3.0)
        budget = max(0.0, min(3.0, deadline - self.clock.monotonic()))
        await self.webhook_poster.drain(budget_seconds=budget)

        # 4. Final state flush — capture any in-flight state changes from the
        #    last cycle (RECOVERY_SPEC §8 atomic-write may have started before
        #    the cancel; flush whatever made it past the boundary).
        # (Detailed implementation depends on what the cycle driver buffered.)
        # await self.state_store.flush_pending(...)

        # 5. Emit DaemonStopped event with reason=SIGTERM
        uptime = self.clock.monotonic() - self.boot_monotonic
        self.event_logger.append(DaemonStopped(
            ts_iso=self.clock.wall_clock_iso(),
            reason=DaemonStopReason.SIGTERM,
            uptime_seconds=uptime,
            cycle_count=self.cycle_count_ref[0],
        ))

        # 6. webhook_poster.stop() (closes httpx client cleanly)
        self.webhook_poster.stop()

        # 7. Close UDS metrics socket; unlink path (PITFALLS §13.3)
        # (Phase 2 _UnixWSGIServer holds the bind; close it here.)
        # ... metrics_server.shutdown() ...
        with contextlib.suppress(FileNotFoundError, OSError):
            os.unlink(self.metrics_socket_path)

        # 8. Touch clean-shutdown marker with JSON body
        marker_body = json.dumps({
            "uptime_s": uptime,
            "cycle_count": self.cycle_count_ref[0],
            "exit_reason": "sigterm",
        }).encode("utf-8")
        # Atomic write per CLAUDE.md invariant #5
        # state_store.atomic.atomic_write_bytes(...)
        atomic_write_bytes(self.clean_shutdown_marker_path, marker_body)

        # 9. (External to choreography) main() releases PID lock by closing fd,
        #    asyncio.run cleanup runs, exit 0.
```

### Pattern 10: SIGHUP transactional Settings swap (L-03)

**What:** Re-read env + YAML; diff against current Settings; refuse if any RELOAD_RESTART field changed; on success, atomic-swap the cycle driver's `self._settings` reference at cycle boundary.

**Why "at cycle boundary":** The cycle driver reads `self._settings` ONCE at the start of each cycle (per existing `daemon/cycle_driver.py` pattern). A swap happens between cycles; a cycle never observes a half-swapped Settings.

**Recipe (skeleton):**

```python
async def sighup_watcher(event, swapper) -> None:
    while True:
        await event.wait()
        event.clear()
        await swapper.try_apply_reload()

class SighupSwapper:
    def __init__(self, current_settings_ref, dns_cache, carrier_table_ref, event_logger, clock):
        self._ref = current_settings_ref
        self._dns_cache = dns_cache
        self._carrier_ref = carrier_table_ref
        self._event_logger = event_logger
        self._clock = clock

    async def try_apply_reload(self) -> None:
        new = build_settings_from_env_and_yaml()  # same path Phase 1's Settings uses
        old = self._ref.get()
        diff = compute_field_diff(old, new)
        restart_offenders = [f for f in diff if f in restart_required_fields(Settings)]
        if restart_offenders:
            self._event_logger.append(RestartRequiredEvent(
                ts_iso=self._clock.wall_clock_iso(),
                fields=restart_offenders,
                reason="rolled_back_in_memory",
            ))
            return  # keep old settings
        # Apply RELOAD_DATA-only changes atomically at cycle boundary
        self._ref.set(new)  # atomic reference swap; cycle driver picks up next cycle
        # Side effects: DNS re-resolve + carrier-table re-read on sha256 change
        if old.webhook_url != new.webhook_url:
            await self._dns_cache.resolve(new.webhook_url_host, force=True)
        if old.carriers_yaml_path == new.carriers_yaml_path:  # path itself is RELOAD_RESTART
            new_sha = sha256_of_file(new.carriers_yaml_path)
            if new_sha != self._carrier_ref.get().sha256:
                self._carrier_ref.set(load_carrier_table(new.carriers_yaml_path))
        self._event_logger.append(ConfigReloadedEvent(
            ts_iso=self._clock.wall_clock_iso(),
            changed_fields=list(diff),
        ))
```

[VERIFIED: existing `src/spark_modem/config/reload_marker.py` already provides `restart_required_fields()` and `data_reloadable_fields()` helpers — Phase 3 just calls them.]

### Pattern 11: Clean-shutdown marker — boot classifier (L-04)

**What:** A small JSON file at `/run/.../clean-shutdown` (tmpfs by design) that records `{uptime_s, cycle_count, exit_reason}` on graceful exit. Boot reads, classifies, unlinks.

**Why tmpfs:** A reboot resets `/run/`. From the daemon's perspective, a planned reboot and a crash are equivalent — there's no in-flight state to preserve, the prior session is gone. The `DaemonStopReason` enum has no `reboot` value by design.

**Recipe (boot classification):**

```python
def classify_prior_run(marker_path: Path, config_error_path: Path) -> tuple[DaemonStopReason, float]:
    """Return (reason, prior_run_uptime_seconds). Unlinks markers."""
    # Check config_invalid first — it's the most specific.
    if config_error_path.exists():
        with contextlib.suppress(FileNotFoundError):
            config_error_path.unlink()
        return DaemonStopReason.CONFIG_INVALID, 0.0
    if marker_path.exists():
        try:
            body = json.loads(marker_path.read_text())
            uptime = float(body.get("uptime_s", 0.0))
        except (OSError, ValueError, json.JSONDecodeError):
            uptime = 0.0
        with contextlib.suppress(FileNotFoundError):
            marker_path.unlink()
        return DaemonStopReason.SIGTERM, uptime
    # Marker absent → CRASH (or first boot — same emission semantics)
    return DaemonStopReason.CRASH, 0.0
```

**oom and kill best-effort (Phase 4 territory):** Phase 3 ships only sigterm/crash/config_invalid. oom requires reading `journalctl -k` for `Out of memory: Killed process` with our PID — too brittle for in-process classification. SIGKILL is undetectable by definition (the process can't classify its own death). Phase 4 may add a post-mortem journalctl scan at boot.

### Anti-Patterns to Avoid (Phase 3 specifics)

- **`pyudev.MonitorObserver`** — thread crashes silently (PITFALLS §7.1). Use `Monitor.from_netlink()` + `loop.add_reader(monitor.fileno())`.
- **`signal.signal()` from asyncio** — handler runs in arbitrary thread (CLAUDE.md anti-pattern #6). Use `loop.add_signal_handler()`.
- **Parsing/state-update inside rtnetlink read loop** — keep the loop body to `event_queue.put_nowait(...)` only (PITFALLS §6.1).
- **Calling `setns()` from the asyncio loop** — switches the loop's thread namespace, corrupts other coroutines (PITFALLS §6.2). Use `ip netns exec` subprocess.
- **Acting on `add` event without waiting for `bind`** — sysfs not yet populated, EAGAIN/ENOENT on cdc-wdm reads (PITFALLS §7.2).
- **Single inotify watch on the file alone** — misses CREATE-mode rotation. Watch parent directory + the file (PITFALLS §8.2).
- **Assuming one IN_MODIFY = one new line** — kernel coalesces; read to EOF in a loop (PITFALLS §8.3).
- **Blocking `read()` on `/dev/kmsg`** — open with `O_NONBLOCK`, use `lseek(SEEK_END)` to skip history.
- **Sending sd_notify from a worker thread or subprocess** — systemd routes by sender PID's cgroup; child-PID lookups fail (PITFALLS §4.1). Send only from main daemon PID.
- **Sending READY=1 before first cycle completes** — premature readiness; systemd marks Active before we've observed anything (PITFALLS §4.1).
- **Sending WATCHDOG=1 at cycle-START** — masks hung mid-cycle until 90 s mark from PRIOR kick; should be cycle-END.
- **`Restart=always` on the systemd unit** — clean SIGTERM exits would still trigger restart, defeating `systemctl stop` semantics (CONTEXT.md U-02).
- **Default `StartLimitIntervalSec=10s`+`Burst=5`** — bricks fleet on a bad config push (PITFALLS §4.2). Override to 300/20.
- **`PrivateMounts=yes` with `LoadCredential=`** — incompatible on systemd 245 / Ubuntu 20.04 (PITFALLS §4.3). Use `ProtectSystem=strict` + `ProtectHome=true` instead.
- **Omitting `RuntimeDirectoryPreserve=yes`** — directory cleaned on stop, taking out PID lock + clean-shutdown marker + flocks (PITFALLS §4.4).
- **Using one PID-lock file for both daemon-instance and state-store flocks** — ADR-0012 mandates separate files; this is critical for daemon/CLI co-existence.
- **`LOCK_BLOCKING` flock on the PID lock** — second instance hangs forever instead of failing fast; use `LOCK_NB` and surface `PidLockHeldError`.
- **`subprocess.run` sync** — anti-pattern catalogue forbids it daemon-wide.
- **Re-entering `setns()` on `ENOENT`** — Zao is restarting; classify as transient, retry next cycle (PITFALLS §6.4).
- **Special-casing `qmi_wwan` reload** — the state machine's `present=False → present=True` transitions ARE the answer (R-05 + NFR-12).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Single-instance daemon enforcement | PID-file with `os.getpid()` written + parsed-on-startup | `fcntl.flock(LOCK_EX\|LOCK_NB)` on `/run/.../lock` | PID files race against PID reuse; flock is kernel-released on death (PITFALLS §4.4) |
| systemd readiness signaling | Direct write to `$NOTIFY_SOCKET` | `sdnotify` library | Pure-Python, ~30 LOC, handles socket details + connection retry; well-tested [VERIFIED: Context7] |
| USB add/remove subscription | `inotify` on `/sys/class/usb` or `/dev/cdc-wdm*` | `pyudev.Monitor.from_netlink()` | sysfs/dev paths are not the actual event source; libudev's netlink subscription is the canonical kernel→userspace channel; pyudev wraps libudev correctly with retry on hub power glitches (PITFALLS §7.1) |
| Link-state subscription | Polling `ip link show` every cycle | `pyroute2.AsyncIPRoute` + RTMGRP_LINK | Polling has 30 s latency; rtnetlink delivers events sub-millisecond; ENOBUFS-aware tight read loop (PITFALLS §6.1) |
| Async inotify | Thread + `inotify_simple` + queue | `asyncinotify.Inotify()` async iter | Native asyncio, no thread shim; supports MODIFY/MOVE_SELF/DELETE_SELF/CREATE all in one event stream |
| Async signal handling | `signal.signal()` + flag flag flag | `loop.add_signal_handler()` | Anti-pattern catalogue forbids `signal.signal()` from asyncio |
| Atomic file writes | open(tmp) + write + rename | (already shipped) `state_store/atomic.atomic_write_bytes` | Phase 1 atomic-write helper handles temp + rename + directory fsync; Phase 3 reuses it for clean-shutdown marker and last-config-error |
| Cross-process file locks | Custom mutex | (already shipped) `state_store/locks.acquire_flock_async` | Phase 1 already implements asyncio.to_thread-wrapped flock; Phase 3 just adds a third file path |
| Field-level reload classification | Parsing field comments / sidecar metadata | (already shipped) `config/reload_marker.py` `RELOAD_DATA` / `RELOAD_RESTART` markers + `restart_required_fields()` / `data_reloadable_fields()` helpers | Phase 1's pydantic Field-extra approach is already wired in Settings; SIGHUP just queries the existing helpers |
| Webhook drain | A "stop and wait" loop | (already shipped) `webhook_poster.drain(3.0)` | Phase 2 W-01 already exists; SIGTERM choreography just calls it |
| TaskGroup error propagation | One-task-fails-cancels-all | `restart_on_crash` wrapper that catches `Exception` per producer | TaskGroup default semantics defeats self-healing; the wrapper is the supervisor pattern. ~30 LOC. |

**Key insight:** Phase 3 has zero greenfield infrastructure — every locking primitive, atomic writer, settings model, webhook poster, event logger, and cycle scheduler is from Phase 1/2. Phase 3 is "Linux-side wiring + 5 small producer modules + 4 small daemon-lifecycle modules + a unit file." The temptation to roll a custom event-source pattern is real (especially after the producer-supervisor TaskGroup discussion); resist it. PITFALLS sections §4–§8 + §12–§14 catalog every footgun the hand-rolled version would hit.

## Runtime State Inventory

> Phase 3 is **not** a rename / refactor / migration phase — it adds production-grade event sources and lifecycle to a daemon whose laptop-testable form already runs end-to-end (Phase 2 complete). No existing strings need replacement; no stored data needs migration.

**Stored data:** None — Phase 3 reads the same per-modem state files (keyed by `usb_path`, ADR-0009) that Phase 2 writes. No schema changes. Identity-map keying unchanged. Counter-decay state unchanged. *Verified by inspection of `state_store/store.py:354-390`.*

**Live service config:** Phase 3 ships a NEW logrotate snippet at `/etc/logrotate.d/spark-modem-watchdog` (R-02; create mode, empty postrotate). The .deb postinst handles the install — no live service config drift to migrate. Existing systemd unit at `/lib/systemd/system/spark-modem-watchdog.service` is updated in-place with U-01..U-05 directives (debhelper handles the unit-file replacement on `apt install`).

**OS-registered state:** The systemd unit is re-loaded by `systemctl daemon-reload` (debhelper postinst already does this). `WatchdogSec=90s` requires `Type=notify` (Phase 1 already ships this); the watchdog timer registers when the unit starts, not at install. No external task scheduler entries.

**Secrets and env vars:** `webhook_hmac_secret` is delivered via `LoadCredential=` (NFR-34, ADR-0011); Phase 3 wires Settings to read `$CREDENTIALS_DIRECTORY/webhook_hmac_secret` at startup. The env var name + delivery path are unchanged from Phase 1's placeholder; the secret value itself is operator-managed (not baked into config). No env var renames.

**Build artifacts / installed packages:** Phase 3 introduces new package paths under `src/spark_modem/` (event_sources/, kmsg/, daemon/lifecycle.py + sighup.py + sigterm.py + preflight.py, etc.). The .deb's bundled venv (`/opt/spark-modem-watchdog/venv/`) is rebuilt on every Phase 3 release; new modules ship via the existing `compileall` step. No stale egg-info, no compiled binaries to remove.

## Common Pitfalls

### Pitfall 1: pyudev MonitorObserver thread crashes silently (PITFALLS §7.1)

**What goes wrong:** A USB hub power glitch generates 16+ events in 2 s; the observer thread crashes silently; daemon never knows. From that point on, no udev events arrive — daemon depends entirely on the polling fallback (30 s).

**Why it happens:** pyudev's threaded observer has known crash modes under bulk events ([pyudev #194, #363, #402](https://github.com/pyudev/pyudev/issues/194)).

**How to avoid:** Use `Monitor.from_netlink()` + `loop.add_reader(monitor.fileno(), ...)`. NEVER `MonitorObserver`. PRESCRIPTIVE per CONTEXT.md.

**Warning signs:** modem hot-plug not reflected in next Diag for >30 s; `udev_events_total` plateaus despite visible activity in `journalctl -k`.

**Phase 3 design:** `event_sources/udev_producer.py` uses the prescribed pattern. `restart_on_crash` wrapper is the safety net for any read-loop exception.

### Pitfall 2: pyroute2 ENOBUFS during USB hub re-enumeration storm (PITFALLS §6.1)

**What goes wrong:** Tegra USB hub PSU droops; hub re-enumerates 4 modems; rtnetlink emits dozens of link-state changes per second; consumer falls behind by 1 s; ENOBUFS — silent event loss.

**Why it happens:** pyroute2 docs explicitly warn: "you must consume all incoming messages in time, otherwise a buffer overflow happens on the socket and the only way to fix that is to close() the failed socket and open a new one."

**How to avoid:**
1. Tight read loop: producer body is `event_queue.put_nowait(WakeSignal.RTNETLINK)` ONLY. NO parsing.
2. `SO_RCVBUF = 4 MiB` (kernel default 256 KiB is too small).
3. On ENOBUFS, close+reopen socket; emit `rtnetlink_resubscribed`; force inventory refresh next cycle. The `restart_on_crash` wrapper handles reopen automatically.

**Warning signs:** `rtnetlink ENOBUFS` errors in events.jsonl; missed wwan-up event leaves modem in `disconnected` for full polling deadline.

### Pitfall 3: logrotate copytruncate breaks watch invisibly (PITFALLS §8.1 — CRITICAL)

**What goes wrong:** `logrotate copytruncate` mode: file inode unchanged, `st_size` truncates to 0. No IN_MOVE_SELF fires. Our offset is now past EOF — silently consume nothing until file grows past our offset (could be 24 h).

**Why it happens:** copytruncate is the default in some Zao SDK packages; we don't own Zao's logrotate config.

**How to avoid (PITFALLS §8.1 prescription verbatim):**
1. On every IN_MODIFY, `os.fstat(fd).st_size` vs `last_known_offset`. If `st_size < offset`, file truncated — reset offset to 0.
2. Opportunistic inode check: every N reads, compare `st_dev/st_ino` against last-known watched-inode; on diff, reopen.
3. Coordinate field engineering to switch Zao to `create` mode where possible.

**Warning signs:** `zao_log_age_seconds` metric plateaus despite live writes; 24-h gaps in events.jsonl that align with logrotate cron schedule.

**Phase 3 design:** `zao_log/inotify_tailer.py` implements both modes per R-04. Our own events.jsonl ships in `create` mode (R-02) with empty postrotate.

### Pitfall 4: sysfs not fully populated on `add` event (PITFALLS §7.2)

**What goes wrong:** Kernel `add` event fires when device is registered, but `iSerialNumber`/`idVendor`/`cdc-wdmN` symlinks under `/sys/class/usb/...` may not be in place yet — 50–200 ms window. Inventory tries to read; gets EAGAIN/ENOENT/empty.

**How to avoid:**
1. Wait for the `bind` event, NOT `add`, for cdc-wdm devices (bind fires when driver has fully attached).
2. OR: retry inventory query 3× with 100 ms backoff before declaring failure.

**Warning signs:** `sysfs_attribute_missing` in events.jsonl shortly after USB add event.

**Phase 3 design:** UdevInventory's pyudev producer subscribes to both `add` and `bind`; cycle re-observation triggered on bind only. The `restart_on_crash` wrapper handles transient sysfs-not-ready as a producer Exception → backoff → retry.

### Pitfall 5: USB hub re-enumeration storm (PITFALLS §7.3)

**What goes wrong:** Tegra USB hub PSU under load droops; hub re-enumerates all 4 modems; 16+ events in 2 s. Cycle queue fills; cycle thrashes; daemon may briefly classify all 4 modems as QMI-hung and fire driver_reset.

**How to avoid:**
1. ADR-0002 coalescing: at most 1 cycle queued regardless of event count. Phase 2's `CycleScheduler.event_queue` is `asyncio.Queue(maxsize=1)`-equivalent with `put_nowait` drop-on-full semantics — already implemented per E-02.
2. Hub re-enumeration grace window: if ≥3 modems disappear and reappear within 5 s, suppress `qmi_channel_hung` classification for 30 s. This is policy-side — outside Phase 3 scope per CONTEXT.md ("R-05 NO special-case suppression"). Phase 4 may add it as an enhancement.

**Warning signs:** `dmesg` shows `usb: device not accepting address` coincident with `cycle_count` spike.

### Pitfall 6: cpython#139373 + #127049 — subprocess cancellation hazards (PITFALLS §5.1, §5.2)

**What goes wrong:** Cancelling `process.communicate()` may lose stdout/stderr (cpython#139373); `Process.send_signal/terminate/kill` may target a freed PID (cpython#127049).

**How to avoid:**
1. Use `asyncio.timeout()` (3.11+; 3.12), not `wait_for()` around `communicate()`.
2. `start_new_session=True` so the subprocess is in its own group; `os.killpg(os.getpgid(pid), SIGTERM)` instead of `proc.terminate()`.
3. Wrap `terminate()` in `if proc.returncode is None: ...` check.

**Warning signs:** Cycles where 1-2 modems' QMI probes fail with `timeout` despite qmicli having printed full output.

**Phase 3 status:** subproc/runner already implements both mitigations per Phase 1 (verified at `subproc/runner.py`). Phase 3's SIGTERM choreography (L-02 step 1) tracks in-flight subprocesses in a `set[Process]` and awaits each per-proc with a small grace budget per PITFALLS §5.3.

### Pitfall 7: asyncio.run shutdown hangs with cancelled subprocesses (PITFALLS §5.3)

**What goes wrong:** SIGTERM arrives; we cancel all tasks; a subprocess transport is still tracked by the loop; `loop.close()` blocks. systemd's `TimeoutStopSec=` (default 90 s) eventually does SIGKILL — we miss FR-53's 5 s SLA.

**How to avoid:**
1. Track subprocesses in a `set[Process]`; SIGTERM handler iterates and `await proc.wait()` each with a 3 s budget.
2. After grace, SIGKILL stragglers; close transports; close loop.
3. `TimeoutStopSec=10s` in unit (5 s graceful + 5 s buffer).
4. `KillMode=mixed` — SIGTERM to main, SIGKILL to children if they linger.

**Phase 3 design:** L-02 choreography step 1 (cycle cancel) blocks on `await self.cycle_driver_task` after `cancel()`; cycle_driver's cleanup awaits in-flight subprocesses. `subproc/runner` already implements two-stage shutdown.

### Pitfall 8: sd_notify race — sender PID exit before systemd lookup (PITFALLS §4.1)

**What goes wrong:** systemd looks up `/proc/$sender_pid/cgroup` to route the message. If sender PID exits before lookup (or a fork happens), READY is dropped; systemd marks unit failed at TimeoutStartSec.

**How to avoid:**
1. Send `READY=1` from main daemon PID only — never from worker thread or subprocess.
2. Send AFTER first cycle completes (meaningful readiness).
3. `WatchdogSec=90s` + `WATCHDOG=1` after each cycle as outer safety net.

**Phase 3 design:** L-01 cadence; sdnotify wrapper holds a single `SystemdNotifier` instance owned by the main daemon coroutine.

### Pitfall 9: LoadCredential + PrivateMounts incompat on systemd 245 (PITFALLS §4.3)

**What goes wrong:** `LoadCredential=` (NFR-34 webhook secret) interacts badly with `PrivateMounts=yes` on systemd 245 (Ubuntu 20.04). Credential file may not be visible; webhooks fire unsigned silently.

**How to avoid:** Skip `PrivateMounts=`; rely on `ProtectSystem=strict` + `ProtectHome=true` for sandboxing on Ubuntu 20.04.

**Phase 3 design:** U-03 explicitly omits PrivateMounts. Tested on systemd 245 in Phase 0 / Phase 5.

### Pitfall 10: RuntimeDirectory cleanup vs PID lock (PITFALLS §4.4)

**What goes wrong:** `RuntimeDirectory=spark-modem-watchdog` cleans `/run/spark-modem-watchdog/` on stop. Without `RuntimeDirectoryPreserve=yes`, lock + clean-shutdown marker + state.lock + modem-*.lock + metrics.sock all vanish — next start can't classify the prior run, daemon/CLI race conditions resurrect.

**How to avoid:** `RuntimeDirectoryPreserve=yes`; `flock`-based PID lock (kernel-released on death) so stale-PID files are safe to take over.

**Phase 3 design:** U-03 includes `RuntimeDirectoryPreserve=yes` (load-bearing per CONTEXT.md).

### Pitfall 11: StartLimit defaults brick fleet rollouts (PITFALLS §4.2)

**What goes wrong:** Default `DefaultStartLimitIntervalSec=10s` + `DefaultStartLimitBurst=5`. A bad config push that crashes daemon within 1 s gets banished after 5 quick restarts. Fleet-wide config rollout = 100% modem watchdog coverage loss.

**How to avoid:** `StartLimitIntervalSec=300` + `StartLimitBurst=20` + `RestartSec=10`. Pre-flight `spark-modem ctl config-check` in `ExecStartPre=` catches bad configs before main process runs.

**Phase 3 design:** U-02 + U-05.

### Pitfall 12: Cardinality explosion via state one-hot label (PITFALLS §13.1)

**Status:** Already handled by ADR-0013 + Phase 2 metrics design (`modem_state_value{modem}` integer-encoded). Phase 3 doesn't change metric surface. Listed for completeness.

### Pitfall 13: Metrics socket orphaned after daemon crash (PITFALLS §13.3)

**What goes wrong:** `/run/.../metrics.sock` is a Unix socket. Daemon crashes hard; socket file stays. Next start, `bind(2)` fails with EADDRINUSE.

**How to avoid:** Daemon's startup unconditionally `unlink()`s the socket path before `bind()`. Safe because `RuntimeDirectory=` and `flock` ensure no other instance.

**Phase 3 design:** Phase 2 `_UnixWSGIServer` already implements this; SIGTERM choreography step 7 also unlinks on graceful exit.

### Pitfall 14: FakeClock not advancing under `await asyncio.sleep()` (PITFALLS §14.1 — CRITICAL test design)

**What goes wrong:** Tests advance FakeClock by 60 s; production code uses `await asyncio.sleep(60.0)`; real event loop sleeps 60 s wall-clock; test hangs OR misses the window FakeClock said had elapsed.

**How to avoid:** All sleeps go through a `Sleeper` Protocol injected with the clock. Production: `await asyncio.sleep(N)`. Tests: a fake that advances FakeClock and yields control.

**Phase 3 design:** `restart_on_crash` wrapper takes a `Sleeper` Protocol, not bare `asyncio.sleep`. Test fake `tests/fakes/sleeper.py` (already in Phase 2 test infrastructure).

### Pitfall 15: Producer overhead — too-fast restarts under chronic crash (E-01 backoff envelope)

**What goes wrong:** A producer that crashes every 100 ms (e.g. `pyroute2` socket-bind fails because rtnetlink temporarily unreachable during boot) would hot-loop the supervisor → 1 s sleep → 100 ms crash → 2 s sleep → 100 ms crash → … wasting CPU. After 5 crashes the backoff caps at 60 s; chronic-crash producer uses ~1.7% CPU + writes a `event_source_crashed` event every 60 s.

**How to avoid:** Bounded backoff `1 → 2 → 4 → 8 → 60` is the cap. Reset attempt counter on a successful run that lasts >5 minutes (so transient crashes don't accumulate forever). Emit one-shot WARNING when a single producer has crashed >10 times in 1 hour — operator visibility for chronic issue.

**Phase 3 design:** `event_sources/supervisor.py` includes attempt-counter reset on long-uptime success; metric `event_source_crashes_total{source}` already in NFR-21.1's expected surface.

## Code Examples

### Example 1: pyudev producer (full skeleton)

```python
# src/spark_modem/event_sources/udev_producer.py
# Source: PITFALLS §7.1 prescriptive pattern + Python 3.12 asyncio docs.
from __future__ import annotations

import asyncio
import logging
from typing import Protocol

import pyudev  # type: ignore[import-untyped]  # pyudev ships its own types incompletely

logger = logging.getLogger(__name__)

class _EventQueueProto(Protocol):
    def put_nowait(self, item: object) -> None: ...

async def run_udev_producer(
    *,
    event_queue: _EventQueueProto,
    sierra_vid: str = "1199",
) -> None:
    """Subscribe to USB add/remove/bind for Sierra-VID modems.

    Pushes WakeSignal.UDEV onto event_queue on any matching event. State
    derives from cycle re-observation — this producer NEVER reads sysfs.
    """
    loop = asyncio.get_running_loop()
    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by(subsystem="usb")
    monitor.set_receive_buffer_size(4 * 1024 * 1024)  # 4 MiB; PITFALLS §6.1 for reasoning
    monitor.start()

    fd = monitor.fileno()

    # Drain on FD-readable. add_reader callback is sync; do all work and return.
    drained = asyncio.Event()  # toggled after each drain (helps tests)

    def on_readable() -> None:
        # poll(timeout=0) returns one device or None; loop until None drains
        # the kernel queue. PITFALLS §7.1 keeps us out of MonitorObserver.
        while True:
            device = monitor.poll(timeout=0)
            if device is None:
                break
            # PITFALLS §7.2: react on `bind` (driver attached) for cdc-wdm;
            # for raw USB add/remove, react on action.
            action = device.action
            vid = device.get("ID_VENDOR_ID")
            if action in ("add", "remove", "bind", "unbind") and vid == sierra_vid:
                event_queue.put_nowait(WakeSignal.UDEV)
        drained.set()

    loop.add_reader(fd, on_readable)
    try:
        # Sleep forever; supervisor cancels us via CancelledError.
        await asyncio.Future()
    finally:
        loop.remove_reader(fd)
        # No explicit monitor.stop() — pyudev's Monitor is GC'd on context exit.
```

### Example 2: rtnetlink producer (tight read loop)

```python
# src/spark_modem/event_sources/rtnetlink_producer.py
# Source: PITFALLS §6.1 verbatim + Context7 /svinota/pyroute2 AsyncIPRoute examples.
from __future__ import annotations

import socket  # for SO_RCVBUF
from pyroute2 import AsyncIPRoute
from pyroute2.netlink import rtnl

async def run_rtnetlink_producer(*, event_queue) -> None:
    """Subscribe to RTNETLINK link-state changes; push WakeSignal.RTNETLINK.

    Tight read loop only — NO parsing, NO state, NO logging in the body.
    On ENOBUFS, escape to supervisor which restarts us (Pattern 1 wrapper).
    """
    async with AsyncIPRoute() as ipr:
        # Set 4 MiB socket receive buffer (PITFALLS §6.1)
        ipr.asyncore.socket.setsockopt(
            socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024
        )
        # Subscribe ONLY to link-state changes
        await ipr.bind(groups=rtnl.RTMGRP_LINK)
        async for _msg in ipr.get():
            # NOTHING in the body except the wake signal.
            event_queue.put_nowait(WakeSignal.RTNETLINK)
```

[VERIFIED: Context7 `/svinota/pyroute2` retrieved 2026-05-07 confirms `AsyncIPRoute()` async context manager, `bind()`, and `async for msg in ipr.get():` shape. The `groups=` parameter on bind is documented in the sync IPRoute example and is part of the same socket-option machinery — async version uses it identically.]

### Example 3: kmsg producer + classifier (E-03)

```python
# src/spark_modem/event_sources/kmsg_producer.py
# Source: SUMMARY §4.2 + Linux kernel Documentation/admin-guide/dev-tools/printk.rst
from __future__ import annotations

import asyncio
import errno
import os
import re

KMSG_DEV = "/dev/kmsg"

# E-03 enum values + "unknown" fallback — locked by CONTEXT.md.
# Regex strings are claude's discretion (treat as data; iterate based on bench).
KMSG_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"USB \S+: device not accepting address"),  "usb_enum_failure"),
    (re.compile(r"over-current.*on port"),                    "usb_overcurrent"),
    (re.compile(r"thermal.*throttl(ing|ed)"),                 "thermal_throttle"),
    (re.compile(r"qmi_wwan.*probe.*fail(ed)?"),               "qmi_wwan_probe_fail"),
    (re.compile(r"tegra-xusb.*power.*loss"),                  "tegra_hub_psu_droop"),
)

def classify(line: str) -> str:
    """Return canonical IssueDetail value (string), or 'unknown'."""
    for pattern, detail in KMSG_PATTERNS:
        if pattern.search(line):
            return detail
    return "unknown"

async def run_kmsg_producer(*, event_queue, classifier=classify, dedup, issue_emitter) -> None:
    """Tail /dev/kmsg in non-blocking mode."""
    loop = asyncio.get_running_loop()
    fd = os.open(KMSG_DEV, os.O_RDONLY | os.O_NONBLOCK)
    os.lseek(fd, 0, os.SEEK_END)  # skip historical buffer

    last_seq: int | None = None

    def on_readable() -> None:
        nonlocal last_seq
        while True:
            try:
                chunk = os.read(fd, 8192)
            except BlockingIOError:
                return
            except OSError as e:
                if e.errno == errno.EPIPE:
                    # We fell behind; ring buffer wrapped. Bump counter.
                    last_seq = None
                    continue
                raise
            if not chunk:
                return
            # Parse header: <priority>,<sequence>,<timestamp>,<flags>;<message>
            try:
                text = chunk.decode("utf-8", errors="replace")
                header, _, payload = text.partition(";")
                fields = header.split(",")
                if len(fields) >= 2:
                    seq = int(fields[1])
                    if last_seq is not None and seq > last_seq + 1:
                        # Gap detected — log self-health metric
                        pass
                    last_seq = seq
                line = payload.split("\n", 1)[0]
            except (ValueError, UnicodeDecodeError):
                continue
            detail = classifier(line)
            if detail == "unknown":
                continue  # don't emit Issues for unclassified lines (raw stored separately)
            if dedup.should_emit(detail):
                issue_emitter.emit_host_issue(detail=detail, raw_line=line)
                event_queue.put_nowait(WakeSignal.KMSG)

    loop.add_reader(fd, on_readable)
    try:
        await asyncio.Future()  # supervisor cancels
    finally:
        loop.remove_reader(fd)
        os.close(fd)
```

### Example 4: per-detail 30-s sliding-window dedup (E-03)

```python
# src/spark_modem/kmsg/dedup.py
# Per CONTEXT.md "Claude's Discretion": shape is implementation detail. Choosing
# timestamp-of-last-emit (simpler than sliding window; matches PITFALLS §13.2).
from __future__ import annotations

from dataclasses import dataclass

@dataclass
class _Entry:
    last_emit_monotonic: float
    repeat_count: int

class KmsgDedup:
    def __init__(self, *, clock, window_seconds: float = 30.0) -> None:
        self._clock = clock
        self._window = window_seconds
        self._table: dict[str, _Entry] = {}

    def should_emit(self, detail: str) -> bool:
        now = self._clock.monotonic()
        entry = self._table.get(detail)
        if entry is None:
            self._table[detail] = _Entry(last_emit_monotonic=now, repeat_count=0)
            return True
        if now - entry.last_emit_monotonic >= self._window:
            entry.last_emit_monotonic = now
            entry.repeat_count = 0
            return True
        entry.repeat_count += 1
        return False

    def repeat_count(self, detail: str) -> int:
        e = self._table.get(detail)
        return e.repeat_count if e else 0
```

### Example 5: Asyncinotify dual-mode tailer skeleton (R-04)

```python
# src/spark_modem/zao_log/inotify_tailer.py
# Source: PITFALLS §8.1, §8.2, §8.3 verbatim transcribed.
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from asyncinotify import Inotify, Mask

class ZaoLogInotifyTailer:
    """Replaces parser.py at runtime; satisfies ZaoLogTailer Protocol."""

    def __init__(self, *, log_path: Path, parser, clock) -> None:
        self._log_path = log_path
        self._parser = parser  # existing Phase 2 ZaoLogParser as parse-only helper
        self._clock = clock
        self._snapshot = None  # current parsed RASCOW_STAT block
        self._last_offset = 0
        self._last_inode: int | None = None

    def is_line_active(self, line_idx: int) -> bool:
        if self._snapshot is None:
            return False
        return line_idx in self._snapshot.active_lines

    def snapshot(self):
        return self._snapshot or self._parser.unknown_snapshot()

    async def run(self, *, event_queue) -> None:
        """Producer entry point; supervisor cancels via CancelledError."""
        async with Inotify() as ino:
            parent = self._log_path.parent
            ino.add_watch(parent, Mask.CREATE | Mask.MOVED_TO)
            file_watch = None
            if self._log_path.exists():
                file_watch = ino.add_watch(self._log_path,
                    Mask.MODIFY | Mask.MOVE_SELF | Mask.DELETE_SELF)
                self._last_offset = 0
                self._last_inode = self._log_path.stat().st_ino
                await self._read_to_eof()
            event_queue.put_nowait(WakeSignal.ZAO_LOG)

            async for event in ino:
                # MOVE_SELF / DELETE_SELF — file vanished; wait for parent CREATE
                if file_watch and event.watch == file_watch:
                    if event.mask & (Mask.MOVE_SELF | Mask.DELETE_SELF):
                        ino.rm_watch(file_watch)
                        file_watch = None
                        event_queue.put_nowait(WakeSignal.ZAO_LOG)  # cycle observes gap
                        continue
                    if event.mask & Mask.MODIFY:
                        # Possible normal append OR copytruncate
                        try:
                            st = self._log_path.stat()
                        except FileNotFoundError:
                            continue
                        if st.st_size < self._last_offset:
                            self._last_offset = 0  # COPYTRUNCATE detected
                        if st.st_ino != self._last_inode:
                            self._last_inode = st.st_ino
                            self._last_offset = 0  # opportunistic inode change
                        await self._read_to_eof()
                        event_queue.put_nowait(WakeSignal.ZAO_LOG)
                # parent CREATE / MOVED_TO — file appeared after CREATE rotation
                if (event.path and event.path.name == self._log_path.name
                        and event.mask & (Mask.CREATE | Mask.MOVED_TO)):
                    file_watch = ino.add_watch(self._log_path,
                        Mask.MODIFY | Mask.MOVE_SELF | Mask.DELETE_SELF)
                    self._last_offset = 0
                    self._last_inode = self._log_path.stat().st_ino
                    await self._read_to_eof()
                    event_queue.put_nowait(WakeSignal.ZAO_LOG)

    async def _read_to_eof(self) -> None:
        """Read everything new since last_offset to EOF (PITFALLS §8.3)."""
        # Use existing parser to extract RASCOW_STAT from the latest segment.
        # Implementation reuses Phase 2's parser.py logic on the file slice.
        ...
```

### Example 6: TaskGroup wiring with all 6 child tasks + signal handlers

```python
# src/spark_modem/daemon/main.py — Phase 3 long-lived shape (replaces single-cycle Phase 2 wiring)
import asyncio
import signal
import sys

async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    settings = build_settings()
    if not settings.is_valid():
        write_last_config_error(settings.errors)
        return 2
    preflight_check(settings)  # FR-60 PATH check; raises on missing qmicli/ip

    boot_reason, prior_uptime = classify_prior_run(
        marker_path=Path("/run/spark-modem-watchdog/clean-shutdown"),
        config_error_path=Path("/run/spark-modem-watchdog/last-config-error"),
    )

    pid_lock_ctx = acquire_pid_lock()  # raises PidLockHeldError if another instance
    with pid_lock_ctx as pid_lock_fd:
        # Wire subsystems (state_store, event_logger, webhook_poster, ...)
        clock = SystemClock()
        event_logger = EventLogWriter(settings.events_log_path)
        # ... etc

        # Emit DaemonRestart envelope at boot
        webhook_poster.enqueue(WebhookEnvelope(payload=DaemonRestart(
            ts_iso=clock.wall_clock_iso(),
            reason=boot_reason,
            prior_run_uptime_seconds=prior_uptime,
        )))

        # Install signal handlers BEFORE TaskGroup
        loop = asyncio.get_running_loop()
        sigterm_event = asyncio.Event()
        sighup_event = asyncio.Event()
        loop.add_signal_handler(signal.SIGTERM, sigterm_event.set)
        loop.add_signal_handler(signal.SIGHUP,  sighup_event.set)

        lifecycle = SdNotifyLifecycle()
        cycle_count_ref = [0]
        boot_monotonic = clock.monotonic()

        choreography = SigtermChoreography(
            cycle_driver_task=...,  # populated below
            producer_tasks=[],       # populated below
            webhook_poster=webhook_poster,
            state_store=state_store,
            event_logger=event_logger,
            metrics_socket_path=settings.metrics_socket_path,
            clean_shutdown_marker_path=Path("/run/spark-modem-watchdog/clean-shutdown"),
            pid_lock_fd=pid_lock_fd,
            clock=clock,
            boot_monotonic=boot_monotonic,
            cycle_count_ref=cycle_count_ref,
        )

        try:
            async with asyncio.TaskGroup() as tg:
                udev_task = tg.create_task(restart_on_crash(
                    "udev_producer", lambda: run_udev_producer(event_queue=event_queue), ...))
                rtnetlink_task = tg.create_task(restart_on_crash(
                    "rtnetlink_producer", lambda: run_rtnetlink_producer(event_queue=event_queue), ...))
                kmsg_task = tg.create_task(restart_on_crash(
                    "kmsg_producer", lambda: run_kmsg_producer(event_queue=event_queue, ...), ...))
                inotify_task = tg.create_task(restart_on_crash(
                    "asyncinotify_producer", lambda: run_asyncinotify_producer(event_queue=event_queue, ...), ...))
                # zao log inotify can be its own task or bundled with the events-log inotify per CONTEXT.md R-01
                cycle_task = tg.create_task(cycle_loop(
                    cycle_driver, scheduler, lifecycle, settings, cycle_count_ref))
                tg.create_task(sigterm_watcher(sigterm_event, choreography))
                tg.create_task(sighup_watcher(sighup_event, sighup_swapper))

                choreography.cycle_driver_task = cycle_task
                choreography.producer_tasks = [udev_task, rtnetlink_task, kmsg_task, inotify_task]
        finally:
            loop.remove_signal_handler(signal.SIGTERM)
            loop.remove_signal_handler(signal.SIGHUP)

    return 0
```

### Example 7: systemd unit file (U-01..U-05 cluster)

```ini
# debian/spark-modem-watchdog.service
# Source: U-01..U-05 from CONTEXT.md + PITFALLS §4.1, §4.2, §4.3, §4.4, §12.1.
[Unit]
Description=Spark Modem Watchdog (v2)
After=network-online.target zao-infra-ctrl.service
Wants=network-online.target
# Don't start if Zao isn't running (FR-74 — qmi-proxy is owned by Zao).
Requires=zao-infra-ctrl.service

[Service]
Type=notify
ExecStartPre=/opt/spark-modem-watchdog/python/bin/python3.12 -c "import pydantic, prometheus_client, pyudev, pyroute2, asyncinotify, httpx, sdnotify, psutil, yaml, pydantic_settings"
ExecStartPre=/opt/spark-modem-watchdog/bin/spark-modem ctl config-check
ExecStart=/opt/spark-modem-watchdog/libexec/spark-modem-watchdog
ExecReload=/bin/kill -HUP $MAINPID

# U-02 — Restart policy (PITFALLS §4.2)
Restart=on-failure
RestartSec=10
StartLimitIntervalSec=300
StartLimitBurst=20
TimeoutStopSec=10s
KillMode=mixed

# U-04 — Watchdog
WatchdogSec=90s

# U-01 — Capabilities (Phase 4-forward; CAP_SYS_MODULE preallocated)
CapabilityBoundingSet=CAP_NET_ADMIN CAP_SYS_ADMIN CAP_SYS_MODULE CAP_DAC_READ_SEARCH

# U-03 — Sandboxing (defense in depth without breaking LoadCredential — PITFALLS §4.3)
ProtectSystem=strict
ReadWritePaths=/var/lib/spark-modem-watchdog /var/log/spark-modem-watchdog
ProtectHome=true
NoNewPrivileges=yes
RestrictNamespaces=net mnt
RuntimeDirectory=spark-modem-watchdog
RuntimeDirectoryPreserve=yes
# DELIBERATELY OMITTED: PrivateMounts=yes (incompat with LoadCredential on systemd 245)

# NFR-34 — HMAC secret delivery
LoadCredential=webhook_hmac_secret:/etc/spark-modem-watchdog/hmac-secret

# Run as root per NFR-30
User=root
Group=root

[Install]
WantedBy=multi-user.target
```

### Example 8: logrotate snippet (R-02)

```
# debian/spark-modem-watchdog.logrotate (installed at /etc/logrotate.d/spark-modem-watchdog)
# Source: R-02 + PITFALLS §12.2 (logrotate user permissions).
/var/log/spark-modem-watchdog/events.jsonl {
    daily
    rotate 7
    size 100M
    compress
    delaycompress
    missingok
    notifempty
    sharedscripts
    create 0640 root adm
    # postrotate INTENTIONALLY EMPTY — daemon detects rename via asyncinotify R-01
}
```

## State of the Art

| Old Approach (v1 / pre-Phase-3) | Current Approach (Phase 3) | When Changed | Impact |
|---------------------------------|----------------------------|--------------|--------|
| Bash polling every 30 s | pyudev/pyroute2/asyncinotify/kmsg event-driven; cycle wakes on event OR 30 s deadline | Phase 3 | Sub-second event latency vs 30 s polling; daemon survives `qmi_wwan` reload as clean state transition (NFR-12) |
| `MonitorObserver` thread (rejected) | `Monitor.from_netlink()` + `loop.add_reader()` | Phase 3 design | No silent thread death (PITFALLS §7.1) |
| Sync `IPRoute` + executor | `AsyncIPRoute` async context manager | Phase 3 design | Native asyncio; tight read loop fits in main coroutine |
| `signal.signal()` from asyncio (rejected) | `loop.add_signal_handler()` | Phase 3 design | No thread-safety hazards; signal arrives on main loop |
| `systemd-python` (rejected) | `sdnotify` pure-Python | Phase 1 ADR-0010 | Compatible with bundled CPython 3.12 (no system Python C lib) |
| Single state-store lock | 3-layer locks (asyncio.Lock + per-modem flock + state-store flock) + separate PID lock | Phase 1 ADR-0012 | Daemon and CLI mutators co-exist without lost-update; PID lock kernel-released on death |
| `Restart=always` (default temptation) | `Restart=on-failure` + StartLimit override | Phase 3 U-02 | Operator-initiated `systemctl stop` stays stopped; bad-config-rollout doesn't brick fleet (PITFALLS §4.2) |
| `Type=notify-reload` (Phase 1 spike result) | `Type=notify` + ExecReload=/bin/kill -HUP $MAINPID | Phase 1 / Phase 3 U-02 | systemd 245 (Ubuntu 20.04) doesn't support notify-reload; reload via SIGHUP signal is universal |

**Deprecated/outdated:**
- v1's bash polling: Replaced wholesale; v2 retains no v1 code (per Phase 7 decommission plan)
- 7-state machine: Superseded by 5+2 flag shape (ADR-0008); state_store schema reflects this — Phase 3 doesn't introduce new states.

## Assumptions Log

> List of `[ASSUMED]` claims in this research. Verified items are NOT here.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `requirements.lock` exact patch versions for pyudev / pyroute2 / asyncinotify / sdnotify | Standard Stack | If lockfile pins to older asyncinotify (<4.0.10), Mask.MOVED_TO behavior may differ; planner should `grep -E '^(pyudev\|pyroute2\|asyncinotify\|sdnotify)' requirements.lock` to verify before plan execution |
| A2 | `descriptor.ns` derivation specifics (sysfs vs `ip netns identify`) — CONTEXT.md flagged as Claude's Discretion | Pattern 2 / E-05 | If chosen sysfs path doesn't exist on bench Jetson, falls back to `ip netns identify` subprocess; verify on first bench-Jetson boot |
| A3 | E-03 regex strings exact match against bench Jetson dmesg | Pattern 5 / Code Examples Example 3 | If a regex misses a real kernel message shape, that detail enum value never fires; fallback is `unknown` with raw line preserved for forensic. Iterate based on bench observation per CONTEXT.md "Claude's Discretion." |
| A4 | pyroute2 `AsyncIPRoute.bind(groups=...)` accepts the same groups bitmask the sync IPRoute accepts | Pattern 3 / Code Examples Example 2 | If async API differs, RTMGRP_LINK subscription fails at startup; supervisor backoffs and retries; planner should add a Wave 0 unit test that asserts the actual subscription succeeds on Linux runner |
| A5 | `pyudev.Monitor.set_receive_buffer_size()` exists and accepts bytes | Pattern 2 / Code Examples Example 1 | The API is documented in pyudev 0.24.x; if it's renamed in a future release, fallback is `ctypes` direct call to `setsockopt(SO_RCVBUF, ...)`. Verify pyudev docs for the locked patch version. |
| A6 | `monitor.poll(timeout=0)` is non-blocking and returns None when queue empty | Pattern 2 / Code Examples Example 1 | If the API blocks despite timeout=0, the producer's add_reader callback hangs; verify with a Wave 0 unit test that `poll(timeout=0)` returns within 1 ms when no events are pending |
| A7 | Linux kernel `/dev/kmsg` returns one record per `read()` (no partial records) | Pattern 5 / Code Examples Example 3 | This is documented kernel behavior; if a quirky aarch64 kernel module changes it, the parser may see truncated records. Defensive: skip lines that don't have a `;` separator. |
| A8 | systemd 245 `LoadCredential=` populates `$CREDENTIALS_DIRECTORY` for the main process | Pattern 6 / Example 7 | This is documented systemd behavior since 247-ish; PITFALLS §4.3 cites the bug interaction with PrivateMounts. Verify on bench Jetson early in Phase 3. |
| A9 | The 5 s SIGTERM budget is achievable with 4 modems + non-trivial state to flush | Pattern 9 / L-02 | Phase 2's two-stage subprocess shutdown was designed for this; HIL test in Phase 4 verifies on hardware. If 5 s proves tight, raise to 7 s with `TimeoutStopSec=12s` (still under systemd default 90 s) |
| A10 | The clean-shutdown marker JSON parse is fast enough that boot classification adds <100 ms to startup | Pattern 11 / L-04 | The marker is <200 bytes; JSON parse is microseconds. Risk is FS latency on the first read after boot — tmpfs eliminates this. |

## Open Questions (RESOLVED)

1. **Should the asyncinotify producer be a single task watching two directories, or two parallel tasks?** CONTEXT.md R-01 says "shared inotify watch (Zao log + events.jsonl rotate) — single asyncinotify pattern, two consumers." A single task with two `add_watch` calls is simpler; two parallel tasks each wrap their own `Inotify()` instance. Tradeoff: single task means a CPU stall in one consumer briefly delays the other. RESOLVED: single task; both consumers are O(milliseconds) of CPU per event. Planner can override.

2. **Where does the `event_source_crashed{source}` event get emitted from — the supervisor wrapper or the producer's exception handler?** Both work. CONTEXT.md is silent. RESOLVED: emit from the supervisor wrapper (pattern 1), so producers don't need access to the event_logger directly. This keeps producers minimal.

3. **Should `cycle_drift_seconds` be clamped at 0 for early-wake (event-driven), or report the negative value as-is?** CONTEXT.md flags this as Claude's Discretion. Negative drift carries information (how often events fire ahead of polling deadline) but Prometheus gauges with negative values render confusingly in some NOC dashboards. RESOLVED: report as-is (signed); document the semantic in the metric help text.

4. **Where does the netns string come from for E-05?** CONTEXT.md flags this as Claude's Discretion. Three options: (a) `/proc/<pid>/ns/net` of the kernel cdc-wdm worker; (b) `ip netns identify <pid>`; (c) walking `/var/run/netns/` and matching mount inodes. RESOLVED: (b) — subprocess `ip netns identify $$` from within `subproc.run()`; aligns with E-05's "we use ip netns exec, not setns" principle. Verify on bench Jetson; if too slow (~50 ms per call), cache per-cdc-wdm and re-derive only on udev events.

5. **Should the SIGTERM watcher coroutine raise CancelledError to unwind the TaskGroup, or just return after choreography?** Returning leaves orphaned tasks running; raising CancelledError unwinds cleanly. RESOLVED: have choreography explicitly `cancel()` all child tasks (it already does), then the watcher returns; TaskGroup's `__aexit__` sees no exceptions and exits cleanly.

6. **Is the events.jsonl writer's in-memory `deque(maxlen=1000)` (R-03) thread-safe enough for concurrent appends during reopen?** asyncio is single-threaded by design; appends and flushes interleave but never race. RESOLVED: the `deque` access is naturally serialized by the cycle's coroutine. No explicit lock needed.

## Environment Availability

> Phase 3 introduces 5 new external dependencies that don't exist on a Windows dev host. Production target is Linux/aarch64 Jetson Orin NX. Dev hosts skip these tests.

| Dependency | Required By | Available (dev host) | Available (Jetson) | Fallback |
|------------|------------|----------------------|--------------------|----------|
| libudev.so.1 (≥151) | pyudev | ✗ (Windows) / ✓ (Linux dev) | ✓ (Ubuntu 20.04 ships 245) | Windows tests skipif(win32); use FakeUdevMonitor |
| Linux kernel rtnetlink | pyroute2.AsyncIPRoute | ✗ (Windows) / ✓ (Linux dev) | ✓ | FakeAsyncIPRoute on dev host |
| Linux kernel inotify | asyncinotify | ✗ (Windows) / ✓ (Linux dev) | ✓ | FakeAsyncinotify on dev host |
| /dev/kmsg | kmsg producer | ✗ (Windows; Linux dev unprivileged needs root) | ✓ (root daemon) | FakeKmsgReader; use fixture files for classifier tests |
| systemd ≥245 with `Type=notify` | sdnotify | ✗ (Windows / macOS) / ✓ (Linux dev with systemd) | ✓ | sdnotify silently no-ops without `$NOTIFY_SOCKET`; lifecycle.ready() etc. become no-ops; tests use FakeSdNotify |
| `fcntl` module (POSIX) | PID lock + flocks | ✗ (Windows) / ✓ (Linux/macOS) | ✓ | AsyncFlockHandle(fd=-1) sentinel on Windows (existing Phase 1 pattern); skipif(win32) on flock contention tests |
| `ip netns exec` | E-05 netns-aware QMI | ✓ (Linux dev) / ✗ (Windows) | ✓ | Phase 3 bench Jetson is single-namespace (ns=None); production fleet may use namespaces |
| `qmicli` CLI | QmiWrapper (Phase 2 — unchanged) | depends on libqmi-utils install | ✓ (Phase 1 ExecStartPre validates) | FR-60 preflight check refuses startup |
| `ip` CLI (iproute2) | E-05 + preflight | ✓ everywhere | ✓ | FR-60 preflight |

**Missing dependencies with no fallback (Linux production target):**
- Bench Jetson MUST have all 9 above (ExecStartPre import smoke test catches the 9 Python deps; FR-60 catches ip/qmicli)

**Missing dependencies with fallback (dev host development):**
- Windows dev host skips all event-source unit tests via `skipif(win32)` markers
- Linux dev host without systemd context (no `$NOTIFY_SOCKET`) — sdnotify silently no-ops; daemon runs without watchdog, useful for laptop testing
- Linux dev host without `/dev/kmsg` permissions — kmsg producer fails; supervisor backs off; daemon runs but kmsg-classified Issues never fire

**CI matrix:** GitHub Actions self-hosted aarch64 runner (Phase 1 already provisions) is the natural target for `pytest -m linux_only`. Ubuntu 22.04 LTS runners (with systemd 249) are acceptable for non-systemd-version-specific tests; systemd 245 specifics get bench-Jetson HIL coverage in Phase 4.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3.x + pytest-asyncio 0.24.x (mode=auto) + hypothesis 6.110.x — same as Phase 1/2 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (already exists; Phase 3 adds `markers = ["linux_only: tests requiring Linux-specific syscalls"]`) |
| Quick run command | `pytest tests/unit/event_sources/ tests/unit/kmsg/ tests/unit/daemon/ -x` |
| Full suite command | `pytest -q` (must complete ≤30 s per M7 budget) |
| Linux-only suite | `pytest -m linux_only` (run only on Linux CI / Jetson bench) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FR-1 | Discover all 4 Sierra-VID modems via pyudev on boot | unit (with FakeUdevMonitor) | `pytest tests/unit/event_sources/test_udev_producer.py -x` | ❌ Wave 0 |
| FR-1 | Boot-to-READY=1 ≤60 s on bench Jetson with 4 real modems | integration | `pytest tests/integration/test_lifecycle.py::test_boot_to_ready_with_4_modems -m linux_only` | ❌ Wave 0 |
| FR-3 | Persist `usb_path → identity` map across reboots | unit | `pytest tests/unit/state_store/test_identity_map_roundtrip.py -x` (Phase 1 file) | ✅ exists |
| FR-3 | Capture ICCID/IMSI per modem via qmicli `--uim-get-card-status` | unit (FakeRunner) | `pytest tests/unit/observer/test_identity_extraction.py -x` | ❌ Wave 0 |
| FR-4 | SIM swap detected within one cycle; resets streak + counters atomically | unit | `pytest tests/unit/daemon/test_sim_swap_detection.py -x` | ❌ Wave 0 |
| FR-14 | usb_overcurrent / usb_enum_failure / thermal / qmi_wwan_probe_fail / tegra_hub_psu_droop classified | unit | `pytest tests/unit/kmsg/test_classifier.py -x` | ❌ Wave 0 |
| FR-14 | Per-detail 30 s dedup collapses repeats | unit (FakeClock) | `pytest tests/unit/kmsg/test_dedup.py -x` | ❌ Wave 0 |
| FR-43 | events.jsonl rotated by logrotate; daemon reopens via inotify | integration | `pytest tests/integration/test_logrotate_create.py -m linux_only` | ❌ Wave 0 |
| FR-43.1 | Survives BOTH `create` AND `copytruncate` modes for Zao log | unit (FakeAsyncinotify + tmp_path) | `pytest tests/unit/zao_log/test_inotify_tailer_dual_mode.py -x` | ❌ Wave 0 |
| FR-53 | `systemctl stop` → SIGTERM → ≤5 s shutdown with all choreography steps | integration | `pytest tests/integration/test_lifecycle.py::test_sigterm_5s_choreography -m linux_only` | ❌ Wave 0 |
| FR-53 | SIGHUP transactional reload — RELOAD_DATA applies, RELOAD_RESTART refused with restart_required event | unit | `pytest tests/unit/daemon/test_sighup_swap.py -x` | ❌ Wave 0 |
| FR-61 | `/run/.../lock` PID lock; second instance refuses with PidLockHeldError | unit | `pytest tests/unit/daemon/test_pid_lock.py -m linux_only` | ❌ Wave 0 |
| FR-61.1 | Per-modem flocks at modem-{usb_path}.lock; state.lock; PID lock — three SEPARATE files | unit | `pytest tests/unit/state_store/test_three_layer_locks.py -x` (extends Phase 1 lock tests) | ✅ exists (extend) |
| FR-75 | sd_notify READY=1 at end of first cycle; STATUS each cycle; WATCHDOG cycle-end | unit (FakeSdNotify) | `pytest tests/unit/daemon/test_lifecycle_sd_notify.py -x` | ❌ Wave 0 |
| NFR-12 | qmi_wwan reload (`modprobe -r qmi_wwan; modprobe qmi_wwan`) → clean disconnected→recovering→healthy transition | integration | `pytest tests/integration/test_lifecycle.py::test_qmi_wwan_reload -m linux_only` | ❌ Wave 0 |
| NFR-13 | READY=1 within 60 s of process start | integration | `pytest tests/integration/test_lifecycle.py::test_ready_within_60s -m linux_only` | ❌ Wave 0 |
| NFR-30 | Daemon runs as root with NoNewPrivileges=yes; no other suid binaries | unit (lint) | `tests/integration/test_unit_file_audit.py` (parses .service file, asserts directives) | ❌ Wave 0 |
| SC #1 | 4 modems discovered on fresh boot; READY=1 within 60 s; status.json modem_count==4 | integration | `tests/integration/test_lifecycle.py::test_sc1_boot_to_ready` | ❌ Wave 0 |
| SC #2 | SIM swap detection latency = one cycle (FakeClock-driven test) | unit | `tests/unit/daemon/test_sim_swap_detection.py::test_sc2_latency_one_cycle` | ❌ Wave 0 |
| SC #3 | SIGTERM-to-exit ≤5 s; clean-shutdown marker present + DaemonStopped(reason=sigterm) | integration | `tests/integration/test_lifecycle.py::test_sc3_sigterm_5s` | ❌ Wave 0 |
| SC #4 | Two ctl reset-state in parallel serialize via state.lock; no lost-update | integration | `tests/integration/test_lifecycle.py::test_sc4_ctl_serialization -m linux_only` | ❌ Wave 0 |
| SC #5 | Logrotate (both modes) doesn't break inotify; qmi_wwan reload = clean state transition | integration | `tests/integration/test_lifecycle.py::test_sc5_logrotate_and_qmi_wwan_reload -m linux_only` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest tests/unit/<changed_module>/ -x` (≤5 s per file; M7 budget enforced)
- **Per wave merge:** `pytest -q` (full unit suite ≤30 s per M7)
- **Phase gate (before `/gsd-verify-work`):** `pytest -q` AND `pytest -m linux_only` (latter run on Linux CI / bench Jetson — wall-clock ≤2 min for integration suite)

### Wave 0 Gaps

- [ ] `tests/unit/event_sources/__init__.py` — package marker
- [ ] `tests/unit/event_sources/test_udev_producer.py` — covers FR-1
- [ ] `tests/unit/event_sources/test_rtnetlink_producer.py` — covers ENOBUFS handling per PITFALLS §6.1
- [ ] `tests/unit/event_sources/test_kmsg_producer.py` — covers /dev/kmsg parser
- [ ] `tests/unit/event_sources/test_asyncinotify_producer.py` — covers shared dual-watcher
- [ ] `tests/unit/event_sources/test_supervisor.py` — covers `restart_on_crash` wrapper backoff envelope
- [ ] `tests/unit/kmsg/__init__.py`
- [ ] `tests/unit/kmsg/test_classifier.py` — covers FR-14 regex matrix
- [ ] `tests/unit/kmsg/test_dedup.py` — covers per-detail 30 s dedup window
- [ ] `tests/unit/daemon/test_lifecycle_sd_notify.py` — covers FR-75 cadence
- [ ] `tests/unit/daemon/test_sigterm_choreography.py` — covers L-02 8-step ordering
- [ ] `tests/unit/daemon/test_sighup_swap.py` — covers L-03 transactional Settings swap
- [ ] `tests/unit/daemon/test_clean_shutdown_marker.py` — covers L-04 boot classification
- [ ] `tests/unit/daemon/test_pid_lock.py` — covers FR-61
- [ ] `tests/unit/daemon/test_sim_swap_detection.py` — covers FR-4 + E-04
- [ ] `tests/unit/inventory/test_udev_inventory.py` — covers FR-1 inventory swap
- [ ] `tests/unit/inventory/test_netns_derivation.py` — covers E-05
- [ ] `tests/unit/zao_log/test_inotify_tailer_dual_mode.py` — covers R-04 (FR-43.1)
- [ ] `tests/unit/event_logger/test_writer_reopen.py` — covers R-03 buffer behavior
- [ ] `tests/integration/__init__.py`
- [ ] `tests/integration/conftest.py` — shared fixtures for Linux-only tests (skipif win32)
- [ ] `tests/integration/test_lifecycle.py` — SIGTERM/SIGHUP end-to-end + 5 success criteria
- [ ] `tests/integration/test_logrotate_create.py` — real logrotate cron exercise
- [ ] `tests/integration/test_unit_file_audit.py` — parses .service file; asserts U-01..U-05 directives
- [ ] `tests/fakes/udev.py` — FakeUdevMonitor recording subscribed actions + injecting events
- [ ] `tests/fakes/rtnetlink.py` — FakeAsyncIPRoute
- [ ] `tests/fakes/asyncinotify.py` — FakeAsyncinotify (yields canned event sequences)
- [ ] `tests/fakes/kmsg.py` — FakeKmsgReader
- [ ] `tests/fakes/sdnotify.py` — FakeSdNotify recording READY/STATUS/WATCHDOG calls
- [ ] `tests/fakes/pidlock.py` — FakePIDLock (asyncio.Lock fallback for Windows)
- [ ] `tests/fixtures/kmsg/usb_overcurrent.log` etc. — dmesg lines per IssueDetail value
- [ ] `tests/fixtures/zao_log/rotated/create/{before,after}.log` — CREATE-mode rotation scenario
- [ ] `tests/fixtures/zao_log/rotated/copytruncate/{before,after}.log` — COPYTRUNCATE-mode rotation scenario
- [ ] `pyproject.toml` markers entry: `markers = ["linux_only: requires Linux syscalls (skipif on Windows)"]`

*(No framework install needed — pytest + pytest-asyncio + hypothesis already shipped in Phase 1's lockfile.)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (limited) | LoadCredential delivery for HMAC secret (NFR-34); no user auth (root-only daemon, NFR-30) |
| V3 Session Management | no | Daemon has no sessions; no inbound IPC in v2.0 |
| V4 Access Control | yes | systemd CapabilityBoundingSet limits root daemon's effective caps to NET_ADMIN/SYS_ADMIN/SYS_MODULE/DAC_READ_SEARCH; NoNewPrivileges=yes; RestrictNamespaces=net mnt |
| V5 Input Validation | yes | All wire JSON via pydantic v2 with `extra='forbid'`; kmsg classifier uses closed-enum IssueDetail (no free-form strings); CarrierTable uses StrictStr (Phase 1 NFR-32) — Phase 3 doesn't introduce new external inputs |
| V6 Cryptography | yes | HMAC-SHA256 webhook signing (Phase 1 ADR-0011) — Phase 3 doesn't change crypto; secret loaded via LoadCredential (NFR-34); never on disk |
| V7 Error Handling | yes | NFR-11 isolation: try/except around policy_engine.run_cycle; supervisor catches Exception in producers; clean-shutdown marker lets boot classify prior failure |
| V8 Data Protection | yes | events.jsonl world-unreadable (mode 0640 root:adm); state files mode 0640; ICCID/IMSI redacted to sha256[:8] in webhook payloads (E-04) |
| V9 Communication | yes | Webhook URLs HTTPS-only by default (NFR-33; Phase 1 already enforces); cycle never blocks on DNS (Phase 2 W-02 cached resolve) |
| V10 Malicious Code | yes | No dynamic code load; pyproject.toml + lockfile only; ExecStartPre import smoke test runs before main process |
| V11 Business Logic | partial | Policy engine pure function; signal-quality gate (Phase 4) prevents destructive resets on RF-blocked modems |
| V12 Files / Resources | yes | Atomic file writes (temp+rename+dirsync); RuntimeDirectoryPreserve=yes preserves /run/.../lock + flocks |
| V13 API | n/a | No outbound API except webhook (covered V9) |
| V14 Configuration | yes | Settings frozen=True; SIGHUP transactional swap; RELOAD_RESTART fields refused with structured event |

### Known Threat Patterns for Phase 3 stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| PID file race / TOCTOU on stale PID | Tampering / Spoofing | Use `flock(LOCK_EX\|LOCK_NB)` instead of PID-exists check (PITFALLS §4.4) — kernel-released on death, no stale-PID race |
| Symbolic-link attack on `/run/.../clean-shutdown` marker | Tampering | systemd `RuntimeDirectory=` + `ProtectSystem=strict` ensure /run/ is daemon-owned; atomic temp+rename writes |
| Symbolic-link attack on `/etc/spark-modem-watchdog/hmac-secret` | Tampering | LoadCredential= delivers via copy-into-tmpfs (`$CREDENTIALS_DIRECTORY` is private to the unit); /etc path is just the source — only readable by root |
| asyncio loop poisoning via `setns()` from main thread | Tampering | NEVER call `setns()` from asyncio loop (PITFALLS §6.2); use `ip netns exec` subprocess (E-05) |
| Race between SIGTERM and final state-store write (lost-update) | Tampering | L-02 step 4 explicitly flushes pending state-store writes; subproc/runner two-stage shutdown drains in-flight per PITFALLS §5.3 |
| systemd journal rate-limit drops events.jsonl-equivalent log lines | Repudiation | events.jsonl is canonical (PITFALLS §4.5); journal is supplementary |
| LoadCredential silent failure (PITFALLS §4.3) | Tampering | Daemon refuses to start when `webhook_signing_secret_required=true` and credential file is missing/empty (Phase 1 already wires) |
| Symbolic-link in `/var/log/spark-modem-watchdog/events.jsonl` to elsewhere | Tampering | Daemon writes via O_APPEND to a known path; logrotate `create 0640 root adm` recreates the file with daemon-owned permissions |
| inotify watch FD exhaustion as a DoS vector | DoS | asyncinotify async context manager + cleanup on shutdown; supervisor backoff at 60 s caps exhaustion rate |
| ENOBUFS event flood from rtnetlink as a DoS vector | DoS | Tight read loop + 4 MiB SO_RCVBUF + close+reopen on ENOBUFS (PITFALLS §6.1) |
| Race between SIGHUP swap and cycle in progress | Tampering | Settings(frozen=True); atomic-swap at cycle boundary; cycle reads self._settings ONCE per cycle |

## Sources

### Primary (HIGH confidence)

- **Context7 `/svinota/pyroute2`** (retrieved 2026-05-07) — AsyncIPRoute async API, bind() shape, async for ipr.get() pattern, IPRoute(netns=...) helpers
- **Context7 `/bb4242/sdnotify`** (retrieved 2026-05-07) — SystemdNotifier API, READY/STATUS/WATCHDOG cadence, MAINPID, $NOTIFY_SOCKET behavior
- **`.planning/research/PITFALLS.md`** — §4.1, §4.2, §4.3, §4.4 (systemd); §5.1, §5.2, §5.3 (asyncio+subprocess); §6.1, §6.2, §6.3, §6.4 (rtnetlink+netns); §7.1, §7.2, §7.3, §7.4 (udev); §8.1, §8.2, §8.3, §8.4 (inotify); §12.1, §12.2, §12.3 (sandboxing); §13.1, §13.2, §13.3 (observability); §14.1, §14.2 (testing) — verbatim prescriptive content
- **`.planning/research/SUMMARY.md`** §4.2 — pyudev / pyroute2 / asyncinotify / `/dev/kmsg` recipes; §4.4 anti-pattern catalogue
- **`.planning/research/STACK.md`** §95 (pyudev pin), §99 (asyncinotify pin), §93 (sdnotify pin)
- **`CLAUDE.md`** — critical invariants (state-machine, atomic writes, Zao authority); anti-pattern catalogue
- **`docs/adr/0002-event-driven-core.md`** — coalesce semantics
- **`docs/adr/0009-state-files-keyed-by-usb-path.md`** — usb_path canonical identity
- **`docs/adr/0011-webhook-subsystem.md`** — drain semantics, LoadCredential delivery
- **`docs/adr/0012-concurrency-locks.md`** — 3-layer lock model
- **`.planning/phases/03-linux-event-sources-lifecycle/03-CONTEXT.md`** — locked decisions E-01..E-05, L-01..L-05, R-01..R-05, U-01..U-05

### Secondary (MEDIUM confidence)

- Python 3.12 asyncio docs (https://docs.python.org/3/library/asyncio-eventloop.html#unix-signals) — `loop.add_signal_handler` semantics
- Python 3.12 asyncio docs (https://docs.python.org/3/library/asyncio-task.html#task-groups) — TaskGroup error propagation
- systemd 245 unit-file documentation (Ubuntu 20.04) — RuntimeDirectory, LoadCredential, RestrictNamespaces, ProtectSystem directive interactions
- Linux kernel `/dev/kmsg` documentation (Documentation/admin-guide/dev-tools/printk.rst) — structured line format, `O_NONBLOCK`, sequence-number semantics

### Tertiary (LOW confidence — needs validation on bench Jetson)

- E-03 regex strings against actual Tegra L4T 5.10 dmesg output — treat as data per CONTEXT.md "Claude's Discretion"; iterate based on bench observation
- Exact sysfs path for netns derivation — multiple options (E-05 / Open Question 4); pick most-stable on bench
- Real 5 s SIGTERM budget headroom on production Jetson — needs HIL verification (Phase 4)

### Existing code (Phase 1+2; reference for executor)

- `src/spark_modem/state_store/locks.py` — Phase 1 flock primitives + 3-layer model (PID lock just adds a third file)
- `src/spark_modem/inventory/{protocol.py,sysfs.py,descriptor.py}` — InventorySource Protocol + ModemDescriptor.ns field already exists
- `src/spark_modem/zao_log/{protocol.py,parser.py}` — ZaoLogTailer Protocol; parser kept as test/replay helper
- `src/spark_modem/daemon/{cycle_scheduler.py,cycle_driver.py,main.py}` — Phase 2 wiring; Phase 3 wraps in long-lived loop
- `src/spark_modem/state_store/store.py:354-390` — save_identity_map / load_identity_map (atomic, takes flocks)
- `src/spark_modem/webhook/poster.py:187-304` — stop() + drain(3.0)
- `src/spark_modem/webhook/dns.py` — DnsCache.resolve()
- `src/spark_modem/config/{settings.py,reload_marker.py}` — Settings(frozen=True) + RELOAD_DATA/RESTART markers + helpers
- `src/spark_modem/wire/webhook.py` — DaemonRestart envelope with DaemonStopReason enum
- `src/spark_modem/wire/{diag.py,enums.py}` — Issue with WhoModem|WhoHost union + IssueDetail enum (Phase 3 adds 5+1 values)
- `src/spark_modem/event_logger/writer.py` — Phase 1 O_APPEND JSONL writer (Phase 3 extends with reopen() + buffer)
- `src/spark_modem/qmi/wrapper.py` — QmiWrapper (Phase 3 modifies argv-build for E-05 netns prepend)

## Project Constraints (from CLAUDE.md)

These are non-negotiable and must be honored in every Phase 3 plan:

1. **Policy engine is a pure function** — no I/O, no subprocess, no env reads. Phase 3 doesn't touch policy/; safe.
2. **Per-modem state files keyed by `usb_path`** (ADR-0009). Phase 3 honors via existing state_store APIs unchanged.
3. **State machine: 5 top-level + 2 orthogonal flags** (ADR-0008). Phase 3 R-05's `disconnected → recovering → healthy` transition uses these.
4. **All durations and backoffs use `time.monotonic()`** (ADR-0007). All Phase 3 timing — sd_notify watchdog cadence, supervisor backoff, SIGTERM budget — uses monotonic via injected ClockProto.
5. **Atomic file writes** — temp + rename + directory fsync. Phase 3's clean-shutdown marker writes via existing `state_store/atomic.atomic_write_bytes`.
6. **Zao `RASCOW_STAT` authoritative for line bonding** (ADR-0003). Phase 3's ZaoLogInotifyTailer doesn't change parser logic — the Protocol surface is preserved.
7. **`_healthy_streak` persists across daemon restarts**. Phase 3's E-04 SIM-swap reset writes streak + counters in ONE atomic write per RECOVERY_SPEC §8.
8. **Cycle write order atomic** — streak update → decay check → counter reset → state-write is one atomic write per cycle. E-04 honors this.
9. **One action per modem per cycle**. Phase 3 doesn't change action dispatch; cycle re-observation is independent of action execution.
10. **Signal-quality gate on `modem_reset` and `usb_reset` only** — Phase 4 territory; Phase 3 ships CAP_SYS_MODULE preallocated but doesn't exercise it.
11. **No inbound IPC in v2.0** — no HTTP, no DBus, no domain socket. Prometheus UDS is one-way scrape only. Phase 3 doesn't add inbound IPC; sd_notify $NOTIFY_SOCKET is OUTBOUND.
12. **CLI mutating commands take the same `flock`s the daemon does** — daemon and CLI never produce a lost update. Phase 3 PID lock is the third file separate from state.lock + modem-{usb_path}.lock per ADR-0012.

**Anti-patterns to avoid (CLAUDE.md):** `subprocess.run` sync; `gather(return_exceptions=True)` for probes; `MonitorObserver`; cdc-wdmN-keyed state; single state-store lock; `signal.signal` from asyncio; subprocess/httpx in `policy/`; UDS RPC for `ctl status`; `urllib.request` for webhooks; missing directory `fsync`; blocking read on `/dev/kmsg`; best-effort event-log swallowing exceptions; hot-reload of event-source paths; `run_in_executor` to "speed up" qmicli; `if/elif` instead of `match` on `ModemState`; `state` as one-hot Prometheus label.

**Out of scope (CLAUDE.md):** Cloud control plane; GUI/web UI; multi-vendor modem support; replacing `qmicli`; multi-SIM/eSIM; owning Zao; migration of v1 state files; hot-plug-of-modems-mid-flight as v2.0 priority; retroactive re-decision on past cycles; predictive ML; auto-firmware-update of EM7421; cross-box coordination; HTTP API on UDS in v2.0.

## Metadata

**Confidence breakdown:**
- Standard stack (pyudev/pyroute2/asyncinotify/sdnotify/kmsg recipes): HIGH — Context7 verified for pyroute2 + sdnotify; PITFALLS prescriptive for pyudev + asyncinotify + /dev/kmsg
- Architecture patterns (TaskGroup supervisor, signal handlers, SIGTERM choreography): HIGH — Python stdlib semantics + CLAUDE.md anti-pattern catalogue + existing Phase 2 seams
- systemd unit file directives (U-01..U-05): HIGH — PITFALLS §4 + §12 cite primary sources verbatim; CONTEXT.md decisions locked
- Pitfall catalog: HIGH — direct citations from PITFALLS §4–§14 with section numbers
- Code examples: MEDIUM — skeletons faithful to Context7 / kernel docs / PITFALLS prescription, but full implementation lands in the executor's wave; bench-Jetson verification required for E-03 regex strings and netns derivation specifics

**Research date:** 2026-05-07
**Valid until:** 2026-06-07 (30-day stable horizon for Linux APIs; pyudev/pyroute2/asyncinotify/sdnotify versions are pinned in lockfile and won't churn this cycle)

## RESEARCH COMPLETE