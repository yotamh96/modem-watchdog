# Phase 3: Linux Event Sources & Lifecycle - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or
> execution agents. Decisions are captured in CONTEXT.md — this log
> preserves the alternatives considered.

**Date:** 2026-05-07
**Phase:** 03-linux-event-sources-lifecycle
**Areas discussed:** Event source orchestration & Linux behaviors,
Lifecycle & shutdown discipline, events.jsonl rotation (writer side),
systemd unit file hardening

---

## Area 1: Event source orchestration & Linux behaviors

### Q1.1 — Producer task supervision

| Option | Description | Selected |
|--------|-------------|----------|
| TaskGroup with per-task restart supervisor | asyncio.TaskGroup + per-child `restart_on_crash` wrapper with bounded backoff; ENOBUFS / observer-crash / watch-breaks become self-healing restart loops | ✓ |
| Single supervisor coroutine spawning bare tasks | Manual `set[Task]` + `asyncio.wait(FIRST_COMPLETED)` | |
| TaskGroup with crash-fast escalation | TaskGroup unwinds whole daemon on any producer crash; systemd brings it back | |

**User's choice:** TaskGroup with per-task restart supervisor (recommended)
**Notes:** Self-healing model preserves daemon uptime through transient OS-level event source flakiness.

### Q1.2 — `event_queue` payload shape

| Option | Description | Selected |
|--------|-------------|----------|
| Opaque WakeSignal sentinel | `WakeSignal.<source>` enum; cycle re-observes; producers never push state | ✓ |
| Typed event payloads with source metadata | `UdevAddEvent(usb_path=...)` etc.; cycle inspects to optimize | |
| Hybrid: enum + small payload for kmsg only | Optional dataclass for kmsg | |

**User's choice:** Opaque WakeSignal sentinel (recommended)
**Notes:** State derives from re-observation, not event payloads — single source of truth, honors PITFALLS §6.1 tight-read-loop prescription.

### Q1.3 — kmsg → IssueDetail mapping

| Option | Description | Selected |
|--------|-------------|----------|
| Closed-enum classifier with 30s dedup | regex → IssueDetail enum (usb_overcurrent, usb_enum_failure, thermal_throttle, qmi_wwan_probe_fail, tegra_hub_psu_droop) + per-detail dedup | ✓ |
| Pass-through with regex-only filtering | Single `kmsg_event` Issue type, raw line in detail | |
| Defer dmesg classification to Phase 4 | Phase 3 ships reader only | |

**User's choice:** Closed-enum classifier with 30s dedup (recommended)
**Notes:** Closed-enum discipline (W-04 anti-pattern: free-form details caused v1 regressions); Phase 4 destructive actions can gate on enum values cleanly.

### Q1.4 — SIM swap detection behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Detect, persist new identity, reset SIM-related state, emit event | Observer captures ICCID/IMSI; cycle compares; on diff: persist + reset streak + reset counters in one atomic write; re-provisioning happens naturally on next cycle | ✓ |
| Detect + force immediate second cycle | Same as above + explicit follow-up cycle scheduling | |
| Detect, persist, but DON'T reset state counters | Preserve healthy_streak/counters across SIM change | |

**User's choice:** Detect + persist + reset (recommended)
**Notes:** Atomic write per RECOVERY_SPEC §8 ordering; SIM swap is a meaningful boundary justifying clean-slate counters.

### Q1.5 — More questions or move on?

| Option | Description | Selected |
|--------|-------------|----------|
| More questions about Area 1 | Cover netns derivation specifics and qmi_wwan reload special-casing | |
| Move to Area 2 | Take netns + qmi_wwan reload as Claude's discretion | ✓ |

**User's choice:** Move to Area 2
**Notes:** Accepted Claude's discretion: netns derived in inventory.scan; qmi/wrapper auto-prepends `ip netns exec` when descriptor.ns is non-None; qmi_wwan reload gets no special-case suppression.

---

## Area 2: Lifecycle & shutdown discipline

### Q2.1 — sd_notify cadence

| Option | Description | Selected |
|--------|-------------|----------|
| READY after first cycle, STATUS each cycle, WatchdogSec=90s, kicks=cycle-end | Meaningful readiness; 3× cycle interval watchdog; RSS observation-only | ✓ |
| READY after first cycle + WatchdogSec=60s + kicks per cycle-start | Tighter watchdog | |
| READY immediately at process start, WatchdogSec=120s | Boot-fast | |

**User's choice:** READY-after-first-cycle + WatchdogSec=90s + cycle-end kicks (recommended)
**Notes:** PITFALLS §4.1 cadence; cycle-end kicks ensure stuck mid-cycle triggers systemd-restart.

### Q2.2 — SIGTERM choreography

| Option | Description | Selected |
|--------|-------------|----------|
| Cancel cycle → stop sources → drain webhook (3s) → final state flush → DaemonStopped event → metrics socket close → clean-shutdown marker → exit | Strict 9-step sequence within 5s budget | ✓ |
| Let inflight cycle finish (1s budget) then drain | Cleaner state at cost of wall-time | |
| Parallel drain (cycle cancel + webhook drain simultaneously) | Saves wall-time but loses final-cycle webhooks | |

**User's choice:** Strict sequenced choreography (recommended)
**Notes:** Sequencing matters — webhook drain MUST come after cycle cancel so it sees final transitions, but BEFORE metrics socket close (drain emits `webhook_delivery_total` increments).

### Q2.3 — SIGHUP transactional reload

| Option | Description | Selected |
|--------|-------------|----------|
| Atomic Settings swap + DNS re-resolve + carrier table re-read | RELOAD_DATA fields swap atomically; RELOAD_RESTART fields refused with structured event; DNS resolved immediately; carrier table re-read on sha256 change | ✓ |
| Settings swap only — callers re-read on next cycle | Simpler but stale DNS up to 60s | |
| Full subsystem rebuild on SIGHUP | Equivalent to restart, less surprise | |

**User's choice:** Atomic Settings swap with active side-effects (recommended)
**Notes:** Settings is `frozen=True` already; cycle driver reads `self._settings` once per cycle so swap is atomic at boundary.

### Q2.4 — Clean-shutdown marker location

| Option | Description | Selected |
|--------|-------------|----------|
| /run/spark-modem-watchdog/clean-shutdown (tmpfs) | Created at end of SIGTERM; classified at boot; reboot resets correctly | ✓ |
| /var/lib/spark-modem-watchdog/clean-shutdown (persistent) | Survives reboots | |
| Discussion of config_invalid / oom / kill reasons | How to derive each | (informational) |

**User's choice:** tmpfs `/run/.../clean-shutdown` marker (recommended)
**Notes:** Reboot is functionally equivalent to crash for our purposes — DaemonStopReason has no `reboot` value and we don't need one. config_invalid via `last-config-error` file written by pre-flight; oom/kill best-effort in Phase 3, may reclassify in Phase 4.

### Q2.5 — More questions or move on?

| Option | Description | Selected |
|--------|-------------|----------|
| Move to Area 3 | Take PID lock placement + ExecStartPre + refuse-to-start as Claude's discretion | ✓ |
| More questions about Area 2 | Cover PID lock ordering, config-validate gate, refuse-to-start webhook | |

**User's choice:** Move to Area 3
**Notes:** Accepted Claude's discretion: PID lock acquired AFTER preflight checks AND BEFORE sd_notify READY; flock-based per ADR-0012; ExecStartPre runs Phase 1 import smoke test + `ctl config-check`; stale PID file with no live flock is safe takeover.

---

## Area 3: events.jsonl rotation (writer side)

### Q3.1 — Writer reopen mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| asyncinotify on parent dir + IN_CREATE/IN_MOVED_FROM | Same producer also serves Zao log; single inotify pattern, two consumers | ✓ |
| SIGHUP from logrotate postrotate | Couples log-reopen to config-reload (one signal, two responsibilities) | |
| Periodic stat() comparison | Daemon-driven; up to N events written to wrong file | |

**User's choice:** asyncinotify on parent dir (recommended)
**Notes:** Decouples log-reopen from SIGHUP's config-reload responsibility; one signal verb per concern; doesn't depend on operator's logrotate config.

### Q3.2 — logrotate snippet mode

| Option | Description | Selected |
|--------|-------------|----------|
| `create 0640 root adm` mode | Standard rename + new file; daemon reopens via inotify | ✓ |
| `copytruncate` mode | Daemon detects via st_size truncation check | |
| Support both — bias toward `create` for our snippet | Reader-side tolerates both per FR-43.1 | |

**User's choice:** `create` mode for our snippet (recommended)
**Notes:** We own the events.jsonl logrotate snippet; bias toward `create` mode. Reader-side asyncinotify still tolerates both modes for the Zao log we don't own (FR-43.1).

### Q3.3 — Reopen-window write semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Buffer in-memory; flush on reopen success | `deque(maxlen=1000)`; bumps `events_dropped_total` on overflow | ✓ |
| Direct write to new fd, no buffer | Window is microseconds in happy path | |
| Best-effort: drop writes during reopen | Breaks events.jsonl as single source of truth | |

**User's choice:** In-memory buffer (recommended)
**Notes:** Window is microseconds in happy path; buffer is defense for pathological case (disk-full / EPERM on new fd). Lock-free because EventLogWriter is single-task.

### Q3.4 — Postrotate hook coordination

| Option | Description | Selected |
|--------|-------------|----------|
| Strictly inotify-driven — empty postrotate | One signal verb per concern; same code path catches all renames | ✓ |
| Belt-and-suspenders — inotify + SIGUSR1 from postrotate | Redundancy at cost of new signal verb | |
| Postrotate primary, inotify fallback | Inverts the above | |

**User's choice:** Strictly inotify-driven (recommended)
**Notes:** Producer is supervised with restart-on-crash (E-01) so inotify-failure is self-healing.

---

## Area 4: systemd unit file hardening

### Q4.1 — CapabilityBoundingSet

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 4-forward caps: CAP_NET_ADMIN + CAP_SYS_ADMIN + CAP_SYS_MODULE + CAP_DAC_READ_SEARCH | Preallocate Phase 4 caps; one unit-file edit | ✓ |
| Phase 3 strict — only CAP_NET_ADMIN + CAP_DAC_READ_SEARCH | Add caps in Phase 4 | |
| No CapabilityBoundingSet — full root caps | Reject — bad precedent + NFR-30 | |

**User's choice:** Phase 4-forward caps (recommended)
**Notes:** No mid-rollout unit-file edits during Phase 4 destructive-action HIL; daemon doesn't EXERCISE unallocated caps in Phase 3 anyway (they're inert).

### Q4.2 — Restart policy

| Option | Description | Selected |
|--------|-------------|----------|
| RestartSec=10 + StartLimitIntervalSec=300 + StartLimitBurst=20 + Restart=on-failure | PITFALLS §4.2 verbatim | ✓ |
| Defaults + Restart=always | Default rate-limit bricks fleet on bad config rollouts | |
| Aggressive: RestartSec=2 + StartLimit disabled | Crash-loop scenarios eat CPU + mask underlying bug | |

**User's choice:** Operationally safe restart policy (recommended)
**Notes:** Default rate-limit was the well-known fleet-bricker (PITFALLS §4.2); 20 restarts within 300s gives ops time to push fix. Restart=on-failure (NOT always) so clean SIGTERM exits don't trigger restart.

### Q4.3 — Sandboxing

| Option | Description | Selected |
|--------|-------------|----------|
| ProtectSystem=strict + ReadWritePaths + RuntimeDirectoryPreserve=yes | Defense-in-depth without breaking LoadCredential | ✓ |
| ProtectSystem=full + minimal hardening | Misses defense-in-depth | |
| Maximum hardening: PrivateMounts=yes + RestrictNamespaces=user pid | Breaks LoadCredential AND netns ops; reject | |

**User's choice:** ProtectSystem=strict bundle (recommended)
**Notes:** No PrivateMounts= per PITFALLS §4.3 (LoadCredential incompat on systemd 245); RestrictNamespaces=net mnt allows netns + UDS ops; RuntimeDirectoryPreserve=yes is load-bearing for PID lock + clean-shutdown marker semantics.

### Q4.4 — WatchdogSec value

| Option | Description | Selected |
|--------|-------------|----------|
| WatchdogSec=90s + WATCHDOG=1 each cycle-end | PITFALLS §4.1 standard guidance (3× cycle interval) | ✓ |
| WatchdogSec=60s + kicks per cycle-end | 2× cycle interval; tighter detection | |
| WatchdogSec=120s + kicks per cycle-start | More forgiving; less responsive | |

**User's choice:** 90s + cycle-end kicks (recommended)
**Notes:** Aligns with Q2.1 sd_notify decision — same "meaningful liveness" philosophy. RSS-tripwire fires events but does NOT skip the watchdog kick.

---

## Final confirmation

### Q5 — Ready to write CONTEXT.md?

| Option | Description | Selected |
|--------|-------------|----------|
| Create context | Write 03-CONTEXT.md, commit, update STATE.md | ✓ |
| Explore more gray areas | Surface additional questions | |
| Revisit an area | Refine answers | |

**User's choice:** Create context (recommended)

---

## Claude's Discretion

The user explicitly delegated the following to Claude during planning (deferred from Q1.5 and Q2.5):

- netns derivation lives in `inventory.scan()`; sysfs walk site is the natural home
- `qmi/wrapper.py` auto-prepends `["ip", "netns", "exec", descriptor.ns]` when `descriptor.ns is not None`
- `qmi_wwan` driver reload gets NO special-case suppression — state machine's `present → False → present → True` transitions ARE the NFR-12 success criteria #5 shape
- PID lock acquired AFTER preflight checks AND BEFORE `sd_notify READY=1`; flock-based per ADR-0012
- ExecStartPre runs Phase 1 B-03 import smoke test + `spark-modem ctl config-check` (Phase 2 CLI)
- Stale PID file with no live flock is safe takeover (kernel-released on death)
- kmsg classifier exact regex strings (the 5+1 enum values are locked; regexes are data)
- Producer task naming convention (snake_case, suffix `_producer`)
- inventory.scan() netns derivation specifics (sysfs vs `ip netns identify`)
- observer's identity-extraction qmicli call placement (`observer/probe.py` extension vs new `observer/identity.py`)
- kmsg dedup state shape (sliding window vs timestamp-of-last-emit)
- `cycle_drift_seconds` semantics for negative drift (early-wake) — clamp vs report as-is
- Test seam Protocol locations (co-located per Phase 1/2 convention; fakes in `tests/fakes/`)
- Plan slicing within the 6–8 plan target (planner's call)

---

## Deferred Ideas

(Mirrored from CONTEXT.md `<deferred>` section for audit completeness.)

### Phase 4 (Destructive Actions & HIL)
- Destructive actions with signal-quality gate
- kmsg classifier regex catalog widening based on Phase 4 HIL observations
- `oom` and `kill` reasons in DaemonStopReason classification
- HIL fault-injection lane verifying watchdog kick, StartLimit, LoadCredential, qmi_wwan reload

### Phase 5 (Bench & Field Shadow)
- Cross-fleet dmesg variance widening the kmsg regex catalog
- WATCHDOG cadence calibration based on real fleet histograms
- LoadCredential rotation runbook

### v2.1 (already deferred in REQUIREMENTS.md)
- HTTP API on UDS (CTL-01, CTL-02)
- Webhook batching (WHK-01, M-3)
- `ctl identity export/import` for RMA box swap (CARR-01)
- `ctl simulate-issue` for kmsg classifier testing (SIM-01, M-24)
- 5G NR-aware policy (NR-01)

### Unrelated future work
- ADR-0014 candidate: "Event source supervision pattern" if `restart_on_crash` shape grows beyond Phase 3
- D-Bus `zao-infra-ctrl.service` state subscription (PITFALLS §2.3/§2.4 — qmi-proxy ownership transition on Zao restart)
