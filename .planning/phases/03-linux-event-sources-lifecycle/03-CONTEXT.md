# Phase 3: Linux Event Sources & Lifecycle - Context

**Gathered:** 2026-05-07
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 swaps the laptop's polling-only fixture mode for real Linux
event-driven observation on a bench Jetson and ships a production-grade
systemd `Type=notify` lifecycle. By exit:

1. On a fresh Jetson boot, the daemon discovers all four Sierra-VID
   (`1199:9091`) modems via `pyudev.Monitor` (single-threaded reader,
   `loop.add_reader(monitor.fileno())`, NOT `MonitorObserver`), resolves
   each to `(line, cdc_wdm, usb_path, namespace, iface)` from sysfs,
   persists the `usb_path → identity` map (ICCID/IMSI), and emits
   `READY=1` via `sd_notify` after the first full cycle within 60 s of
   process start (FR-1, FR-3, FR-75, NFR-13).
2. SIM swap (ICCID change at the same `usb_path`) is detected within one
   cycle: observer captures fresh ICCID/IMSI; cycle driver compares
   against `StateStore.load_identity_map()`; on diff it persists the new
   identity, **resets the modem's `_healthy_streak` and escalation
   counters** (new SIM = clean slate, ADR-0006 spirit), and emits a
   `sim_swapped` event. Re-provisioning happens naturally on the next
   cycle when the carrier-table lookup against the new (MCC, MNC)
   yields a different APN; no special-case re-provisioning trigger
   (FR-4).
3. USB hot-plug `usb_remove`/`usb_add` updates inventory without
   restarting the daemon; USB overcurrent / "device not accepting
   address" / thermal events from `/dev/kmsg` surface as `WhoHost`
   Issues with closed-enum `IssueDetail` taxonomy (`usb_overcurrent`,
   `usb_enum_failure`, `thermal_throttle`, `qmi_wwan_probe_fail`,
   `tegra_hub_psu_droop`) routed through events.jsonl and
   `status.aggregate_health`; per-detail 30 s dedup window prevents
   storms from flooding the log (FR-14, PITFALLS §13.2).
4. `systemctl stop spark-modem-watchdog.service` triggers SIGTERM and
   the daemon shuts down within 5 s with: cycle cancel → event-source
   producers stopped → `webhook_poster.drain(3.0)` → final state-store
   flush → `DaemonStopped(reason=SIGTERM)` event → UDS metrics socket
   close (unlink) → write `/run/spark-modem-watchdog/clean-shutdown`
   marker with `{uptime_s, cycle_count, exit_reason}` → release PID
   lock → exit 0. `systemctl reload` issues SIGHUP and applies a
   transactional Settings swap: data-only fields (carrier table path,
   thresholds, webhook URL) update with DNS re-resolve + carrier-table
   re-read on sha256 change; topology-affecting fields
   (`state_root`, `run_dir`, `events_log_path`, `metrics_socket_path`,
   `carriers_yaml_path`) emit a structured `restart_required` event
   listing the changed fields and are NOT applied (FR-53, FR-54).
5. Two concurrent state-mutating CLI invocations (`spark-modem ctl
   reset-state` × 2) serialize cleanly via the state-store flock at
   `/run/spark-modem-watchdog/state.lock`; per-modem flocks at
   `/run/spark-modem-watchdog/modem-{usb_path}.lock` separate from the
   daemon's PID lock at `/run/spark-modem-watchdog/lock` (flock-based,
   kernel-released on death) — daemon and a `ctl reset-state` from a
   second shell never produce a lost-update on the same modem (FR-61,
   FR-61.1). PID lock is acquired AFTER preflight checks (FR-60) and
   BEFORE `sd_notify READY=1`.
6. Logrotate running in either `create` mode (MOVE_SELF/DELETE_SELF) or
   `copytruncate` mode (file inode unchanged, st_size truncates to 0)
   does not silently break: the `asyncinotify` Zao-log reader handles
   both per FR-43.1 (st_size truncation check + opportunistic inode
   compare); the events.jsonl writer reopens via the same asyncinotify
   producer watching the parent directory for IN_CREATE/IN_MOVED_FROM
   on the file basename, with an in-memory bounded buffer
   (`deque(maxlen=1000)`) catching writes during the reopen window.
   The .deb's logrotate snippet ships in `create` mode with empty
   postrotate (we own our snippet; reader-side robustness is the
   defense for the Zao log we don't own). A `qmi_wwan` driver reload
   (`modprobe -r qmi_wwan; modprobe qmi_wwan`) is observable as a clean
   state transition through `disconnected → recovering → healthy`, not
   as a daemon crash, with NO special-case suppression — the state
   machine's `present → False → present → True` transitions are exactly
   what NFR-12 demands (FR-43, FR-43.1, NFR-12). Daemon runs as root
   with `NoNewPrivileges=yes`; no other process granted suid bits
   (NFR-30).

**Carried forward from prior phases (locked, do not re-discuss):**

- `pyudev.Monitor.from_netlink()` + `loop.add_reader(monitor.fileno())`
  — never `MonitorObserver` (PITFALLS §7.1; SUMMARY §4.2).
- `pyroute2.AsyncIPRoute` async context manager (NOT `IPRoute` sync,
  NOT NDB) — SUMMARY §4.2.
- `asyncinotify` (NOT `inotify_simple`) for log watchers — STACK §95.
- `/dev/kmsg`: `O_RDONLY|O_NONBLOCK` + `lseek(SEEK_END)` +
  `add_reader` — SUMMARY §4.2.
- `loop.add_signal_handler(SIGTERM/SIGHUP, …)` — NEVER `signal.signal()`
  from asyncio (anti-pattern catalogue).
- `sdnotify >=0.3.2` (NOT `systemd-python`) — STACK §93.
- READY=1 sent from main daemon PID, after first full cycle, within
  the 60 s NFR-13 budget (PITFALLS §4.1).
- 3-layer locks: per-modem `asyncio.Lock` + globals lock + per-modem
  flock + state-store flock + separate PID lock (ADR-0012).
- `InventorySource` and `ZaoLogTailer` Protocols already exist
  (Phase 2); Phase 3 swaps in event-driven implementations behind the
  same surfaces — `observer/` doesn't change.
- `CycleScheduler.event_queue` plumbed as no-op stub in Phase 2;
  Phase 3 wires real producers.
- `WebhookPoster.stop()` and `.drain(budget_seconds=3.0)` already
  exist (Phase 2 W-01); Phase 3 wires from SIGTERM.
- `Settings` has `RELOAD_DATA` / `RELOAD_RESTART` field markers and
  `restart_required_fields()` / `data_reloadable_fields()` helpers
  ready for SIGHUP transactional reload.
- Counter decay state already persisted per cycle (FR-26.1/.2);
  restart-mid-streak preserved.
- `DaemonRestart` event ships with `reason: DaemonStopReason` enum
  (`sigterm` / `crash` / `config_invalid` / `oom` / `kill`); Phase 2
  always emits `CRASH` — Phase 3 wires the clean-shutdown classifier.
- 5 s graceful SIGTERM SLA with 3 s webhook drain budget inside it
  (Phase 2 C-04 / W-01).

</domain>

<decisions>
## Implementation Decisions

### E. Event source orchestration (FR-1, FR-3, FR-4, FR-14, FR-43, FR-43.1)

- **E-01: TaskGroup with per-task `restart_on_crash` supervisor.** The
  daemon's main coroutine builds an `asyncio.TaskGroup`. Inside it,
  each of the 5 event-source producers (udev, rtnetlink,
  asyncinotify-zao, asyncinotify-events, kmsg) is a child task wrapped
  in a small `restart_on_crash(name, factory)` coroutine that catches
  `Exception`, emits an `event_source_crashed{source}` event, sleeps a
  bounded backoff (`1 → 2 → 4 → 8 → min(60s)`), and re-enters the
  factory. ENOBUFS / observer-thread crash / inotify-watch-breaks
  (PITFALLS §6.1, §7.1, §8.1) become self-healing restart loops without
  taking down the daemon. The cycle driver is a 6th child task. If
  ALL producers crash simultaneously (catastrophic OS-level event), the
  TaskGroup logs but does NOT exit — systemd's `WatchdogSec=90s` is the
  outer safety net.
- **E-02: Opaque `WakeSignal` sentinel on `event_queue`.** The
  `CycleScheduler.event_queue` payload is a closed enum:
  `class WakeSignal(StrEnum): UDEV; RTNETLINK; ZAO_LOG;
  EVENTS_LOG_ROTATED; KMSG`. Producers `put_nowait(WakeSignal.<source>)`
  and never await on the queue (drop-on-full is acceptable: a missed
  signal just means we wait until the 30 s polling deadline). Cycle
  scheduler's `wait({sleep_until_deadline, event_queue.get},
  return_when=FIRST_COMPLETED)` wakes early; cycle then does a FULL
  re-observation pass. Producers never push state into the queue —
  state derives from re-observation, not from event payloads (single
  source of truth; PITFALLS §6.1 "tight read loop" honored).
- **E-03: kmsg classifier with closed `IssueDetail` enum + 30 s
  per-detail dedup (FR-14).** A new `kmsg/classifier.py` table maps
  regex → canonical `IssueDetail` value:
    - `r"USB \S+: device not accepting address"` → `usb_enum_failure`
    - `r"over-current.*on port"` → `usb_overcurrent`
    - `r"thermal.*throttl(ing|ed)"` → `thermal_throttle`
    - `r"qmi_wwan.*probe.*fail(ed)?"` → `qmi_wwan_probe_fail`
    - `r"tegra-xusb.*power.*loss"` → `tegra_hub_psu_droop`
    - fallback → `unknown` (raw line stored separately for forensic;
      not the `detail` field).

  Each classified line emits an `Issue(who=WhoHost, category=host,
  detail=<enum>)` routed to events.jsonl AND `status.aggregate_health`
  flags. Per-`(detail)` 30 s dedup window: the `kmsg/dedup.py`
  collapses repeats within the window and bumps a `repeat_count` field
  on the original event (PITFALLS §13.2). The `IssueDetail` enum gains
  these 5 host-level values + `unknown`; existing 5+2 ModemState shape
  is unchanged. Phase 4 destructive actions can gate on these enum
  values cleanly (e.g. `usb_reset` may be suppressed when
  `usb_overcurrent` is the active host issue).
- **E-04: SIM-swap detection — observer captures, cycle compares,
  reset on diff.** observer/ extracts ICCID/IMSI per modem via
  qmicli's `--uim-get-card-status` (already ships in Phase 2's QMI
  parsers); cycle driver loads `StateStore.load_identity_map()` once
  per cycle and compares. On `(usb_path, ICCID)` diff: (1) persist
  new identity via `save_identity_map()` (atomic, takes globals lock
  + state-store flock); (2) **reset that modem's `_healthy_streak`
  AND escalation counters to zero** in the SAME atomic state-write
  (RECOVERY_SPEC §8 ordering preserved); (3) emit `sim_swapped` event
  with redacted-hash old/new ICCID (`<sha256[:8]>` per Phase 2 C-04
  bundle redaction). Re-provisioning happens NATURALLY on the next
  cycle: policy engine sees stale APN vs new (MCC, MNC) and schedules
  `set_apn`. No special-case "schedule immediate cycle" — the udev
  notification that surfaced the swap already triggered the cycle via
  E-02.
- **E-05: netns derivation in `inventory.scan()`; qmi/wrapper
  auto-prepend.** `ModemDescriptor.ns` is populated by reading the
  netns name from the cdc-wdm parent's sysfs link (Linux exposes the
  netns id via `/sys/class/net/wwanN/device/netns` or via `ip netns
  identify`); inventory is the only place that does sysfs walks, so
  it's the natural site. `qmi/wrapper.QmiWrapper` checks
  `descriptor.ns is not None` and, when set, auto-prepends `["ip",
  "netns", "exec", descriptor.ns]` to the argv before
  `runner.run(...)`. Per PITFALLS §6.2: NEVER call `setns()` from the
  asyncio loop — `ip netns exec` forks a child that does its own
  setns, so the daemon's loop stays in the host namespace. On
  Phase 3's bench Jetson without netns (single-namespace setup),
  `descriptor.ns is None` and behavior is identical to Phase 2.

### L. Lifecycle & shutdown (FR-53, FR-75, FR-61, NFR-12, NFR-13)

- **L-01: sd_notify cadence.** `READY=1` fires at the END of the FIRST
  successful cycle (all subsystems wired, status.json written) — budget
  45 s inside NFR-13's 60 s. `STATUS=` updated each cycle with
  `"cycle=N healthy=K/4 actions=M drift=Xs"`. `WATCHDOG=1` sent at
  cycle-END (PITFALLS §4.1: kicks AFTER successful work, so a stuck
  mid-cycle triggers systemd-restart at the 90 s mark). RSS-tripwire
  from Phase 2's `daemon/rss_tripwire.py` is observation-only — it
  emits `daemon_self_health{kind=rss}` and a WARN log but does NOT
  skip the watchdog kick (separate concerns: metrics observe, watchdog
  is liveness only).
- **L-02: SIGTERM choreography (5 s budget).** Strict ordering:
    1. Cancel `CycleDriver.run_one_cycle` task. `subproc/runner`'s
       two-stage shutdown drains in-flight qmicli per PITFALLS §5.3
       (graceful → SIGKILL → re-communicate with 1 s grace). Track
       outstanding subprocesses in a `set[Process]` so the SIGTERM
       handler iterates and `await proc.wait()` each with a small
       per-proc budget.
    2. Cancel the 5 event-source producer tasks (their
       `restart_on_crash` wrappers exit cleanly on `CancelledError`).
    3. `await webhook_poster.drain(budget_seconds=3.0)` — emits
       `WebhookDropped(reason="drain_budget_exhausted")` for items
       beyond the budget.
    4. Final `state_store.save_modem_state(...)` for any in-flight
       state changes captured pre-cancel (the cycle's atomic
       state-write per RECOVERY_SPEC §8 may have started before the
       cancel — flush it).
    5. Emit `DaemonStopped` event with `reason=SIGTERM`,
       `uptime_seconds`, `cycle_count`. (Distinct from
       `DaemonRestart` which is emitted at boot of the NEXT run.)
    6. `webhook_poster.stop()` (closes httpx client cleanly).
    7. Close UDS metrics socket via the `prom.py` `_UnixWSGIServer`
       shutdown path; `unlink(metrics_socket_path)` to free the path
       (PITFALLS §13.3).
    8. Touch `/run/spark-modem-watchdog/clean-shutdown` marker with a
       small JSON body: `{uptime_s, cycle_count, exit_reason:
       "sigterm"}`.
    9. Close PID lock fd (auto-released by kernel on close).
   10. Return 0 from `main()`; `asyncio.run` cleanup.
- **L-03: SIGHUP transactional Settings swap.** Handler builds a new
  `Settings` instance by re-reading env + YAML (the `from_yaml_layer`
  path); diffs against the current instance. If any field tagged
  `RELOAD_RESTART` changed (`state_root`, `run_dir`, `events_log_path`,
  `metrics_socket_path`, `carriers_yaml_path`,
  `startup_delay_seconds`), refuse the reload: emit a structured
  `restart_required` event listing the offending fields, keep the old
  Settings, return. On success (only `RELOAD_DATA` fields changed):
  atomic-swap the cycle driver's `self._settings` reference (cycle
  driver reads `self._settings` once per cycle, so the swap is
  naturally atomic at cycle boundary). Side effects on success:
    - `webhook/dns.DnsCache.resolve()` invoked immediately (W-02
      honored — fresh URL takes effect without 60 s timer wait);
    - Carrier-table file re-read if `carriers_yaml_path` content's
      sha256 changed (the path itself is RELOAD_RESTART, but the
      file's contents are RELOAD_DATA — re-reading on every SIGHUP is
      cheap and matches FR-33);
    - Emit `config_reloaded` event with a short diff summary.

  Settings model is `frozen=True` (Phase 2 settings.py L36) so every
  swap is a fresh immutable instance. No mid-flight field mutation.
- **L-04: Clean-shutdown marker — `/run/.../clean-shutdown` (tmpfs).**
  Marker path is in tmpfs by design: a planned reboot is materially
  equivalent to a crash from the daemon's perspective (no in-flight
  state to preserve, prior session is gone). At boot, `daemon/main.py`
  checks for the marker BEFORE acquiring the PID lock:
    - present → read JSON, set `DaemonRestart.reason =
      DaemonStopReason.SIGTERM`, set
      `prior_run_uptime_seconds = JSON.uptime_s`, `unlink(marker)`.
    - absent → `reason = DaemonStopReason.CRASH`, `prior_run_uptime =
      0.0` (or compute from /proc/<pid>/stat if available, but
      Phase 2 already defaults to 0.0 — keep the simple default).

  `config_invalid` reason: pre-flight Settings validation that fails
  writes `/run/.../last-config-error` and exits non-zero; next boot
  classifies as CONFIG_INVALID and unlinks. `oom` and `kill` reasons
  are best-effort in Phase 3 (flagged for Phase 4): the daemon cannot
  reliably classify these from its own process, so the boot
  classifier defaults to CRASH unless a more-specific marker is found.
- **L-05: PID lock placement in startup.** Order:
    1. `daemon/main.py` argparse (Phase 3 wires CLI flags here for the
       first time — Phase 2 had `del argv`).
    2. Build `Settings`; on validation failure write
       `last-config-error` and exit non-zero.
    3. FR-60 preflight: `qmicli --version`, `ip --version` available
       on PATH. Phase 1's B-03 import smoke test runs in
       `ExecStartPre=` not in-process.
    4. Read `/run/.../clean-shutdown` marker; classify prior run.
    5. Acquire PID lock at `/run/.../lock` via flock (kernel-released
       on death — stale PID file is safe per ADR-0012).
    6. Wire subsystems (state_store, event_logger, webhook_poster,
       metrics, carrier_table, etc. — same shape as Phase 2's
       `daemon/main.py`).
    7. Emit `DaemonRestart` envelope at boot (already wired in
       Phase 2, just feed it the classified `reason` from step 4).
    8. Build the TaskGroup; spawn 5 event-source producer tasks +
       1 cycle-driver task.
    9. Run cycle 0; on its successful completion, send `READY=1` via
       sd_notify.
   10. Continue cycling; STATUS / WATCHDOG kicks per L-01.

### R. Logrotate handling (FR-43, FR-43.1)

- **R-01: events.jsonl writer reopen via asyncinotify on parent
  directory.** A new `event_logger/inotify_reopener.py` is wired as
  one of the 5 producer tasks (E-01 supervised). It watches
  `/var/log/spark-modem-watchdog/` for `IN_CREATE` on the file
  basename + `IN_MOVED_FROM` on the file basename. On either event,
  it calls `EventLogWriter.reopen()` (a new method on Phase 1's
  writer that closes the old fd, opens the new path with `O_APPEND`,
  flushes the in-memory buffer). Same producer ALSO watches the Zao
  log directory (FR-43.1 reader-side robustness — single asyncinotify
  pattern, two consumers).
- **R-02: `create` mode for the .deb logrotate snippet.** Ship
  `/etc/logrotate.d/spark-modem-watchdog` with: `daily / rotate 7 /
  size 100M / compress / delaycompress / missingok / notifempty /
  sharedscripts / create 0640 root adm`. The `postrotate` block is
  EMPTY — we own the snippet AND the writer; the inotify producer
  detects the rename without needing logrotate to send a signal. This
  decouples log-reopen from SIGHUP's config-reload responsibility (one
  signal verb per concern).
- **R-03: Reopen-window in-memory buffer.** `EventLogWriter` adds a
  `_reopen_buffer: deque[bytes] = deque(maxlen=1000)`. State machine:
    - normal: `append(event)` → `os.write(fd, …)`.
    - rotate-detected (set by reopener via a `_reopening: bool` flag):
      `append(event)` → `_reopen_buffer.append(line)`.
    - reopen complete: flush buffer to new fd in order; clear flag.
    - buffer overflow: bump `events_dropped_total{reason="reopen_overflow"}`
      counter + emit a one-shot `events_dropped_during_reopen` warning.

  The window is microseconds in the happy path (single coroutine, no
  awaits between detect and reopen); the buffer is defense for the
  pathological case of disk-full / EPERM on the new fd.
- **R-04: Zao log reader handles BOTH rotation modes per FR-43.1.**
  We don't own Zao's logrotate config. The Phase 3 inotify-backed
  `ZaoLogInotifyTailer` (replacing Phase 2's file-read
  `ZaoLogParser` behind the same `ZaoLogTailer` Protocol)
  implements the dual-mode handler from PITFALLS §8.1:
    - On `IN_MODIFY`: `os.fstat(fd).st_size` vs `last_known_offset`;
      if `st_size < offset`, file was truncated (copytruncate mode);
      reset offset to 0 and re-read.
    - On `IN_MOVE_SELF` / `IN_DELETE_SELF`: reopen via the parent-dir
      watch (PITFALLS §8.2 pattern).
    - Opportunistic inode check: every N reads compare `os.fstat`'s
      `st_dev/st_ino` against last-known watched inode; on diff,
      reopen.
- **R-05: qmi_wwan driver reload — no special-case suppression.** On
  `modprobe -r qmi_wwan; modprobe qmi_wwan` the kernel emits 4 USB
  unbind events (cdc-wdm devices vanish) followed by 4 rebind events.
  pyudev producer signals UDEV → cycle re-observes → inventory.scan
  finds zero modems mid-reload → state machine transitions all four
  to `present=False` → `state=disconnected` (orthogonal flag from
  ADR-0008). When devices return, scan finds them → `present=True` →
  cycle proceeds → `state=recovering(level=0)` → next healthy cycle
  → `state=healthy`. NFR-12 success criteria #5 demands EXACTLY this
  shape ("clean state transition through `disconnected → recovering
  → healthy`, not as a daemon crash"); the state machine already
  does it without a special-case "qmi_wwan reload in progress"
  predicate. Phase 2's NFR-11 isolation (try/except around
  `policy_engine.run_cycle`) is the safety net for any unexpected
  exception during the transient.

### U. systemd unit file hardening (NFR-30, FR-53)

- **U-01: CapabilityBoundingSet — Phase 4-forward.**
  `CapabilityBoundingSet=CAP_NET_ADMIN CAP_SYS_ADMIN CAP_SYS_MODULE
  CAP_DAC_READ_SEARCH`. Phase 3 doesn't USE `CAP_SYS_MODULE` (driver
  reset lands in Phase 4) but ships it preallocated so the unit-file
  is stable across the Phase 3 → Phase 4 boundary. Single unit-file
  edit at the start of Phase 3, no mid-rollout edits in Phase 4.
- **U-02: Restart policy — operationally safe.**
  `Restart=on-failure` (NOT always — clean SIGTERM exits do not
  trigger restart). `RestartSec=10`. `StartLimitIntervalSec=300`.
  `StartLimitBurst=20`. (PITFALLS §4.2: 5-restart-per-50-second
  default banishes the unit during a config rollout.)
  `TimeoutStopSec=10s` (5 s graceful + 5 s buffer; PITFALLS §5.3).
  `KillMode=mixed` (SIGTERM to main, SIGKILL to children if they
  linger past `TimeoutStopSec`).
- **U-03: Sandboxing — defense-in-depth without breaking
  LoadCredential.**
    - `ProtectSystem=strict`
    - `ReadWritePaths=/var/lib/spark-modem-watchdog
      /var/log/spark-modem-watchdog`
    - `ProtectHome=true`
    - `NoNewPrivileges=yes`
    - `RestrictNamespaces=net mnt` (ALLOW netns + mnt; needed for
      `ip netns exec` and the prom UDS bind)
    - `RuntimeDirectory=spark-modem-watchdog`
    - `RuntimeDirectoryPreserve=yes` (PITFALLS §4.4 — preserves
      `/run/.../{lock, clean-shutdown, state.lock, modem-*.lock,
      metrics.sock}` across systemd-supervised stop/restart so PID
      lock + clean-shutdown marker semantics work)
    - **No** `PrivateMounts=yes` (PITFALLS §4.3: incompatible with
      `LoadCredential=` on systemd 245 / Ubuntu 20.04).
    - `LoadCredential=webhook_hmac_secret:/etc/spark-modem-watchdog/hmac-secret`
      (Phase 1 placeholder; Phase 3 wires Settings to read
      `$CREDENTIALS_DIRECTORY/webhook_hmac_secret`).
- **U-04: `WatchdogSec=90s` + cycle-end kicks.** PITFALLS §4.1
  recommended cadence (3× cycle interval). Daemon kicks WATCHDOG=1 at
  the END of each successful cycle, not at start. A cycle that hangs
  mid-pipeline triggers systemd-managed restart at the 90 s mark.
  Phase 4's HIL stress tests must verify the watchdog kicks even
  during cycles approaching the 10 s P99 budget (NFR-1).
- **U-05: ExecStartPre extension.** Phase 1's B-03 import smoke test
  runs as `ExecStartPre=/opt/spark-modem-watchdog/python/bin/python3.12
  -c '<imports>'`. Phase 3 adds a second `ExecStartPre=` that runs
  `spark-modem ctl config-check` (Phase 2 CLI) which builds a Settings
  from the current env+YAML and exits non-zero on validation failure.
  This pushes config-validation BEFORE the main daemon process runs;
  PITFALLS §4.2 says this catches bad rollouts before crash-loops can
  trip the StartLimit.

### Claude's Discretion

- **kmsg classifier regex specifics.** The 5 enum values are locked
  (E-03); the exact regexes may evolve based on bench-Jetson dmesg
  observations — treat as data, not contract. Add new regex/enum
  pairs with an ADR or as a Phase 4 follow-up; never bury them as
  one-line edits without trace.
- **Producer task naming + supervisor-emitted events.** The
  `restart_on_crash(name, factory)` wrapper's `name` parameter (e.g.
  `"udev_producer"`, `"rtnetlink_producer"`) flows into
  `event_source_crashed{source=name}` events and any Prom metric
  labels. Use snake_case names matching the source.
- **inventory.scan() netns derivation specifics.** Whether the netns
  is read from `/proc/<pid>/ns/net` of the kernel cdc-wdm worker, from
  `ip netns identify`, or by walking `/var/run/netns/` is an
  implementation detail — researcher / planner picks the most-stable
  sysfs read.
- **observer's identity-extraction qmicli call shape.** Existing
  Phase 2 qmi parsers cover SIM card status. The observer extension
  to populate identity may live in `observer/probe.py` (existing) or
  a new `observer/identity.py`; planner decides based on size.
- **Detailed kmsg dedup state.** Whether the 30 s dedup window is a
  per-(detail) sliding window or a per-(detail) timestamp-of-last-emit,
  whether the `repeat_count` field is the count since last emit or
  since first emit in the window — implementation detail.
- **`cycle_drift_seconds` interpretation under event-driven wakeups.**
  Phase 2 O-03 noted drift becomes the load-bearing scheduling-health
  signal once Phase 3 wires events. Drift goes negative when an event
  wakes us before the deadline (expected behavior); the metric is a
  signed gauge already. Phase 3 implementation may adjust the gauge's
  semantics (e.g. clamp to 0 for early-wake, or report as-is) based
  on what's most legible to NOC.
- **Test seam Protocol locations.** New `EventSourceProducer`
  Protocol (or just shared `restart_on_crash` interface), new
  `KmsgClassifier` Protocol, new `PIDLock` Protocol — co-located with
  implementations per Phase 1/2 convention. Fakes in `tests/fakes/`.
- **Plan slicing.** Phase 3 deliverables fall naturally into ~6–8
  plans (udev producer + UdevInventory swap, rtnetlink producer,
  asyncinotify zao + events reopener, kmsg reader + classifier,
  sd_notify + signal handlers + clean-shutdown marker, PID lock + .deb
  unit file + logrotate snippet, integration tests on a Linux CI
  runner). Final count is the planner's call.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor) MUST read these
before planning or implementing Phase 3.** Every entry is a full
relative path so the file can be read directly.

### Phase boundary, requirements, prior decisions

- `.planning/ROADMAP.md` §"Phase 3: Linux Event Sources & Lifecycle" —
  goal, 13-requirement list (FR-1, FR-3, FR-4, FR-14, FR-43, FR-43.1,
  FR-53, FR-61, FR-61.1, FR-75, NFR-12, NFR-13, NFR-30), five success
  criteria.
- `.planning/REQUIREMENTS.md` §Traceability — the FR + NFR
  Phase-3-mapped entries verbatim.
- `.planning/PROJECT.md` §"Active" requirements + §"Key Decisions" —
  v2.0 commitments this phase delivers.
- `.planning/phases/01-foundations-adrs/01-CONTEXT.md` — Phase 1
  decisions this phase builds on (W-02 wire boundary, S-01 state-store
  Protocols, B-03 ExecStartPre import test).
- `.planning/phases/02-core-daemon-laptop-testable/02-CONTEXT.md` —
  Phase 2 decisions Phase 3 wires into production
  (M-01 InventorySource, M-02 cycle scheduler event_queue stub, W-01
  webhook drain, O-04 metric labels including
  `webhook_delivery_total{result}`).
- `CLAUDE.md` §"Critical invariants" + §"Anti-patterns" —
  non-negotiable rules (signal.signal anti-pattern, MonitorObserver
  anti-pattern, blocking /dev/kmsg anti-pattern).

### Event sources (E-01..E-05)

- `docs/ARCHITECTURE.md` §8 (event sources and polling fallback —
  table mapping event → source → use).
- `docs/adr/0002-event-driven-core.md` — coalesce semantics: at most
  one cycle queued regardless of event count.
- `docs/adr/0009-state-files-keyed-by-usb-path.md` — usb_path is
  canonical identity; cdc-wdm renumbers.
- `.planning/research/SUMMARY.md` §4.2 — pyudev / pyroute2 /
  asyncinotify / `/dev/kmsg` recipes verbatim.
- `.planning/research/STACK.md` §95 — pyudev `>=0.24.4,<1`, pyroute2
  `>=0.9.6,<1`, asyncinotify `>=4.0.10,<5`.
- `.planning/research/PITFALLS.md` §6.1 (rtnetlink ENOBUFS — tight
  read loop + SO_RCVBUF=4MiB + close+reopen + force inventory
  refresh), §6.2 (setns NEVER from asyncio loop — use `ip netns
  exec` subprocess), §6.3 (pyroute2 socket leaks — async context
  manager), §7.1 (MonitorObserver crashes silently — use Monitor +
  add_reader; PRESCRIPTIVE), §7.2 (sysfs not fully populated on add
  — wait for `bind` event or retry 3× / 100ms backoff), §7.3
  (USB hub power cycle storm — coalescing already in scheduler),
  §7.4 (devices vanish before fully appearing — usb_path-keyed
  inventory + 5 s GC), §13.2 (event-log rate spike — per-detail
  dedup window, the basis for E-03's 30 s dedup).
- `src/spark_modem/inventory/protocol.py` — `InventorySource` Protocol
  surface (Phase 2; Phase 3 swaps in `UdevInventory` impl).
- `src/spark_modem/inventory/sysfs.py` — `SysfsInventory` reference
  impl Phase 3 extends (line/cdc-wdm/usb_path/iface derivation;
  Phase 3 adds `ns` derivation).
- `src/spark_modem/inventory/descriptor.py` — `ModemDescriptor.ns`
  field already exists; Phase 2 sets to None.
- `src/spark_modem/zao_log/protocol.py` — `ZaoLogTailer` Protocol
  surface (Phase 3 swaps in `ZaoLogInotifyTailer` impl).
- `src/spark_modem/zao_log/parser.py` — Phase 2 file-read fallback
  Phase 3 replaces.
- `src/spark_modem/daemon/cycle_scheduler.py` — `event_queue`
  consumer pattern + `cycle_drift_seconds` calculation.

### SIM identity + swap (E-04)

- `src/spark_modem/state_store/store.py` §354–390 — `save_identity_map`
  / `load_identity_map` (already wired, atomic, takes globals lock +
  state-store flock).
- `src/spark_modem/wire/identity.py` — `Identity` model.
- `docs/RECOVERY_SPEC.md` §8 — atomic-write ordering for streak +
  decay + counter reset (E-04 reset MUST follow this ordering).
- `docs/adr/0006-counter-decay.md` — clean-slate semantics on
  meaningful boundary changes.

### Lifecycle, signals, sd_notify (L-01..L-05)

- `docs/PRD.md` FR-53 (graceful SIGTERM ≤5 s), FR-54 (SIGHUP
  transactional reload), FR-75 (sd_notify READY/STATUS/WatchdogSec),
  FR-61 (PID lock), FR-61.1 (per-modem + state-store flocks separate
  from PID lock).
- `.planning/research/SUMMARY.md` §4.2 — sd_notify cadence
  (READY after first cycle; STATUS keepalive; WatchdogSec=90s
  optional; send from main daemon PID only).
- `.planning/research/PITFALLS.md` §4.1 (sd_notify race — send from
  main daemon PID, READY after meaningful work, WatchdogSec=90s),
  §4.2 (StartLimit defaults brick fleet rollouts — override to
  300/20/10), §4.3 (LoadCredential incompat with PrivateMounts on
  systemd 245), §4.4 (RuntimeDirectory cleanup vs PID lock —
  RuntimeDirectoryPreserve=yes), §5.1 (cpython#139373 cancel-loses-stdout —
  asyncio.timeout NOT wait_for around communicate; subproc/runner
  already does this), §5.2 (cpython#127049 PID lifetime race —
  process-group kill via start_new_session=True; subproc/runner
  already does this), §5.3 (asyncio.run shutdown hangs — track
  subprocesses in set, await proc.wait per-proc with budget).
- `docs/adr/0011-webhook-subsystem.md` — pre-exit best-effort drain
  semantics (3 s budget); `WebhookDropped(reason="drain_*")` events.
- `docs/adr/0012-concurrency-locks.md` — 3-layer lock model:
  PID lock SEPARATE from per-modem + state-store flocks; flock
  kernel-released on death.
- `src/spark_modem/state_store/locks.py` — flock primitives + acquire
  ordering (asyncio.Lock first, flock second; per ADR-0012).
- `src/spark_modem/config/settings.py` + `config/reload_marker.py` —
  RELOAD_DATA / RELOAD_RESTART markers + `restart_required_fields()` /
  `data_reloadable_fields()` helpers ready for L-03 SIGHUP swap.
- `src/spark_modem/webhook/poster.py` §187–304 — `WebhookPoster.stop()`
  and `.drain(budget_seconds=3.0)` already implemented; Phase 3 wires
  from SIGTERM handler.
- `src/spark_modem/webhook/dns.py` — `DnsCache` for L-03 SIGHUP
  re-resolve.
- `src/spark_modem/wire/webhook.py` — `DaemonRestart` envelope with
  `reason: DaemonStopReason` enum (sigterm/crash/config_invalid/oom/
  kill); Phase 2 always emits CRASH (laptop integration).
- `src/spark_modem/daemon/main.py` — Phase 2 wiring shape Phase 3
  replaces with the long-lived event-driven loop.

### Logrotate (R-01..R-05)

- `docs/PRD.md` FR-43 (logrotate 7-day, 100 MiB), FR-43.1 (inotify
  tail tolerates `create` AND `copytruncate` modes).
- `.planning/research/PITFALLS.md` §8.1 (CRITICAL — logrotate
  copytruncate breaks watch invisibly; `os.stat().st_size`
  truncation check + opportunistic inode check; coordinate field eng
  to switch Zao to `create` mode), §8.2 (watch path absent at
  startup — watch the directory for IN_CREATE), §8.3 (multiple writes
  batched into single IN_MODIFY — read everything new since last
  offset in a loop until EOF), §8.4 (inotify watch FD exhaustion —
  asyncinotify async context manager + cleanup on shutdown).
- `src/spark_modem/event_logger/writer.py` — Phase 1 O_APPEND JSONL
  writer Phase 3 extends with `reopen()` + in-memory buffer (R-03).

### systemd unit file (U-01..U-05)

- `docs/PRD.md` NFR-30 (root + no other suid), FR-53 (Type=notify).
- `.planning/research/SUMMARY.md` §4.2 — sd_notify recipe; SUMMARY
  §4.5 — Phase 0 spike list mentions Type=notify on Ubuntu 20.04
  systemd 245 (NOT notify-reload which needs 253+).
- `.planning/research/PITFALLS.md` §4.1, §4.2, §4.3, §4.4, §4.5
  (already cited under Lifecycle section), §12.1 (CRITICAL — systemd
  hardening + setns + sysfs unbind; CAP_NET_ADMIN + CAP_SYS_ADMIN +
  CAP_SYS_MODULE + CAP_DAC_READ_SEARCH minimum), §12.2 (logrotate
  user lacks read on events.jsonl — `create 0640 root adm`), §12.3
  (NoNewPrivileges=yes safe).
- `docs/adr/0011-webhook-subsystem.md` — `LoadCredential=` for HMAC
  secret per NFR-34.

### Test strategy + integration

- `docs/TEST_STRATEGY.md` §2 (test layers — Phase 3 introduces a
  Linux-only integration tier), §3 (fixture library), §8
  (FakeClock / FakeSubprocessRunner conventions).
- `.planning/research/PITFALLS.md` §14.1 (FakeClock not advancing under
  asyncio.sleep — `Sleeper` Protocol injected with clock; production
  uses real `asyncio.sleep`, tests use a fake that advances FakeClock
  and yields control), §14.2 (pytest-asyncio flakiness on busy CI
  runners — generous bounds).
- `tests/fakes/` — Phase 2 conventions (single import surface,
  hardware-free fakes); Phase 3 adds `FakeUdevMonitor`,
  `FakeRtnetlinkSocket`, `FakeKmsgReader`, `FakeAsyncinotify`,
  `FakeSdNotify`, `FakePIDLock` behind their respective Protocols.

### Migration / rollout context

- `docs/MIGRATION.md` — Phase 5 (bench/field shadow) is the first
  consumer of the production-grade systemd unit; Phase 3 deliverables
  are the substrate.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (from Phase 1 + Phase 2)

- `src/spark_modem/daemon/cycle_scheduler.py` — `CycleScheduler` already
  exposes `next_deadline()` / `expected_for_drift()` / `overran(now)` /
  `advance()`. Phase 3 keeps this unchanged; the only addition is the
  `event_queue` arm (already plumbed as no-op in Phase 2 per M-02).
- `src/spark_modem/daemon/cycle_driver.py` — `CycleDriver.run_one_cycle`
  is the per-cycle pipeline; Phase 3 wraps it in a long-lived loop
  driven by `CycleScheduler.wait({sleep, event_queue.get})`.
- `src/spark_modem/daemon/main.py` — current Phase 2 shape (single
  cycle, then exit) is the wiring template; Phase 3 swaps in:
  `argparse → Settings → preflight → marker check → PID lock →
  subsystem wiring → DaemonRestart emit → TaskGroup → first cycle →
  sd_notify READY → cycle loop`.
- `src/spark_modem/daemon/rss_tripwire.py` — `check_rss_tripwire()` is
  observation-only (Phase 2 design); Phase 3 keeps semantics. The
  WATCHDOG=1 kick is independent.
- `src/spark_modem/state_store/locks.py` — `acquire_flock_async()`
  ready for Phase 3 PID lock at `/run/.../lock` (separate file from
  state.lock + modem-*.lock per ADR-0012).
- `src/spark_modem/state_store/store.py` — `save_identity_map` /
  `load_identity_map` (atomic; globals lock + state-store flock)
  ready for E-04 SIM-swap detection.
- `src/spark_modem/inventory/protocol.py` + `sysfs.py` +
  `descriptor.py` — `InventorySource` Protocol with `ns` field on
  descriptor (currently None) ready for E-05 netns derivation.
- `src/spark_modem/zao_log/protocol.py` + `parser.py` — `ZaoLogTailer`
  Protocol with file-read parser; Phase 3 swaps in
  `ZaoLogInotifyTailer` behind the same surface.
- `src/spark_modem/event_logger/writer.py` — Phase 1 O_APPEND JSONL
  writer; Phase 3 adds a `reopen()` method + in-memory buffer (R-03).
- `src/spark_modem/webhook/poster.py` — `stop()` + `drain(3.0)` ready
  for L-02 SIGTERM choreography.
- `src/spark_modem/webhook/dns.py` — `DnsCache.resolve()` ready for
  L-03 SIGHUP re-resolve.
- `src/spark_modem/config/settings.py` + `reload_marker.py` —
  `Settings(frozen=True)` + RELOAD_DATA/RELOAD_RESTART markers +
  helpers ready for L-03 transactional swap.
- `src/spark_modem/wire/webhook.py` — `DaemonRestart` envelope with
  `DaemonStopReason` enum + `prior_run_uptime_seconds` field ready
  for L-04 marker-driven classification.
- `src/spark_modem/wire/diag.py` — `Issue` with `Who = WhoModem |
  WhoHost` discriminated union ready for E-03 kmsg-classified host
  issues.
- `src/spark_modem/wire/enums.py` — `IssueDetail` enum gains 5+1 new
  values for E-03 kmsg classification.
- `src/spark_modem/qmi/wrapper.py` — `QmiWrapper` consumes the
  injected runner; E-05 modifies the argv-build path to prepend
  `["ip", "netns", "exec", ns]` when `descriptor.ns is not None`.
- `src/spark_modem/cli/clients.py` — `_NoZaoTailer`, `_CliClock`,
  `_InventoryFromFile`, `build_default_settings` are the laptop-only
  helpers; Phase 3 production code path uses real implementations
  but the fakes survive for `spark-modem ctl <cmd>` flows that don't
  spawn a daemon.

### Established Patterns

- All wire JSON via pydantic v2 `model_dump_json` /
  `model_validate_json`. No `json.loads` of untyped dicts in
  production code (boundary discipline; W-02).
- `asyncio` everywhere. No `subprocess.run` sync. No
  `gather + wait_for`. No `MonitorObserver`. No `signal.signal()` from
  asyncio (anti-pattern).
- `mypy --strict` + `ruff check` + `ruff format --check` green per
  module.
- `scripts/lint_no_subprocess.sh` (SP-04) fails CI on
  `create_subprocess_exec` / `subprocess.*` / `os.system` outside
  `subproc/`. Phase 3's new modules call into `subproc.run` for any
  subprocess work (`ip netns exec` invocations are constructed argvs
  passed to QmiWrapper, which already routes through subproc.runner).
- Per-libqmi parser fixtures at
  `tests/fixtures/qmicli/<intent>/<version>/<scenario>.txt` are
  hardware-free; Phase 3 SIM-swap detection extends parsers
  (`uim-get-card-status` shape) using the same per-version pattern.
- Tests: `pytest` + `pytest-asyncio` (`mode=auto`) + `hypothesis`.
  `tmp_path` for filesystem; `FakeClock` for time. No global state.
- Windows dev-host friendliness: `flock` is no-op via
  `AsyncFlockHandle(fd=-1)` sentinel; POSIX-only test files marked
  `skipif(win32)`. Phase 3 introduces multiple Linux-only paths
  (pyudev, pyroute2, asyncinotify, /dev/kmsg, sd_notify); these tests
  are `skipif(win32)`. Production target is Linux/aarch64 (Jetson).

### Integration Points

Phase 3 introduces these new package paths under `src/spark_modem/`:

| Path | Owns |
|------|------|
| `inventory/udev.py` | `UdevInventory` impl of `InventorySource` (pyudev.Monitor + add_reader) |
| `inventory/netns.py` | netns derivation from sysfs (E-05) |
| `event_sources/` | new package — wraps the 5 producer tasks |
| `event_sources/supervisor.py` | `restart_on_crash` wrapper + WakeSignal enum |
| `event_sources/udev_producer.py` | pyudev producer (push WakeSignal.UDEV) |
| `event_sources/rtnetlink_producer.py` | pyroute2.AsyncIPRoute producer |
| `event_sources/kmsg_producer.py` | /dev/kmsg reader + classifier dispatch |
| `event_sources/asyncinotify_producer.py` | shared inotify watch (Zao log + events.jsonl rotate) |
| `kmsg/classifier.py` | regex → IssueDetail mapping (E-03) |
| `kmsg/dedup.py` | per-detail 30 s sliding-window dedup |
| `zao_log/inotify_tailer.py` | `ZaoLogInotifyTailer` impl (replaces parser.py runtime; parser stays as test/replay helper) |
| `daemon/lifecycle.py` | sd_notify wrapper, signal handlers, clean-shutdown marker IO, PID lock acquisition |
| `daemon/sighup.py` | transactional Settings swap + SIGHUP-side effects (DNS resolve, carrier reload) |
| `daemon/sigterm.py` | choreographed shutdown sequence (L-02) |
| `daemon/preflight.py` | FR-60 PATH check + Settings validate gate |
| `event_logger/writer.py` | Phase 1 file extended with `reopen()` + buffer |
| `event_logger/inotify_reopener.py` | reopen-on-rotate dispatcher |

Test seams:

| Path | Owns |
|------|------|
| `tests/fakes/udev.py` | `FakeUdevMonitor` recording subscribed actions + injecting events |
| `tests/fakes/rtnetlink.py` | `FakeAsyncIPRoute` |
| `tests/fakes/asyncinotify.py` | `FakeAsyncinotify` (yields canned event sequences) |
| `tests/fakes/kmsg.py` | `FakeKmsgReader` |
| `tests/fakes/sdnotify.py` | `FakeSdNotify` recording READY/STATUS/WATCHDOG calls |
| `tests/fakes/pidlock.py` | `FakePIDLock` (asyncio.Lock fallback for non-POSIX) |
| `tests/fixtures/kmsg/<scenario>.log` | dmesg lines for classifier tests |
| `tests/fixtures/zao_log/rotated/{create,copytruncate}/*` | rotation scenarios |
| `tests/integration/test_lifecycle.py` | SIGTERM/SIGHUP end-to-end on Linux runners |

### Lint / quality gates extended in Phase 3

- `mypy --strict` extends to all new modules above.
- `ruff check` + `ruff format --check` extend.
- Existing `scripts/lint_no_subprocess.sh` continues to enforce
  `create_subprocess_exec` only inside `subproc/`.
- New gate: integration tests on a Linux CI runner (separate from the
  laptop-friendly unit suite). The aarch64 self-hosted runner from
  Phase 1's CI extension is the natural target; `pytest -m
  "linux_only"` selects them. Windows dev hosts skip these tests
  cleanly.

</code_context>

<specifics>
## Specific Ideas

The user accepted the recommended option in every question across all
four selected areas — total alignment with research SUMMARY's
prescriptions and PITFALLS' top-15 mitigations. Concrete specifics
worth pinning:

- **Producer supervision is self-healing, not crash-fast.** A producer
  hitting ENOBUFS, observer-thread death, or watch-FD exhaustion
  emits a structured event and restarts itself with bounded backoff.
  The daemon survives all 5 producers misbehaving simultaneously;
  systemd's `WatchdogSec=90s` is the outer safety net.
- **`event_queue` carries opaque wake signals, not state.** State
  derives from re-observation; the queue is a wake-up-now mechanism
  only. This honors PITFALLS §6.1's "tight read loop" prescription
  for rtnetlink and matches ADR-0002's "events shorten cycle latency,
  cycle is the source of truth" philosophy.
- **kmsg classification uses closed `IssueDetail` enums.** Phase 4's
  destructive actions can gate on these values cleanly (e.g. suppress
  `usb_reset` when `usb_overcurrent` is the active host issue). The
  raw line is preserved for forensic but never enters the `detail`
  field — closed-enum discipline (W-04 anti-pattern: free-form detail
  caused v1's silent regressions).
- **SIM-swap reset is one atomic write.** On `sim_swapped` detection,
  identity update + `_healthy_streak` reset + counter reset +
  state-write are one atomic operation per RECOVERY_SPEC §8 ordering.
  Honors FR-26.2's invariant: streak/decay/counter/write atomicity is
  not negotiable.
- **netns derivation lives in inventory.** sysfs walks happen in
  `inventory/sysfs.py` already; netns is a sysfs-readable attribute.
  qmi/wrapper.py auto-prepends `ip netns exec` when descriptor.ns is
  set — never `setns()` from the asyncio loop (PITFALLS §6.2).
- **READY=1 means "we did real work."** PITFALLS §4.1's "meaningful
  readiness" — fired AFTER the first cycle observes all 4 modems and
  writes status.json. Budget 45 s of NFR-13's 60 s; 15 s of slack for
  sysfs latency, qmicli first-call cost, etc.
- **WATCHDOG=1 kicks at cycle-end, not cycle-start.** A stuck mid-cycle
  triggers systemd-restart at the 90 s mark. Cycle-start kicking
  would mask hung cycles (the prior cycle's kick is still valid for
  90 s — too forgiving).
- **SIGTERM choreography is strictly sequenced.** Cycle cancel → event
  sources stop → webhook drain (3 s) → final state flush →
  DaemonStopped event → metrics socket close → clean-shutdown marker
  → PID lock release → exit. Sequencing matters: webhook drain MUST
  come AFTER cycle cancel so the drain sees any final-cycle
  transitions, but BEFORE the metrics socket close (the drain emits
  `webhook_delivery_total{result}` increments).
- **Clean-shutdown marker is in tmpfs by design.** Reboots reset the
  marker; that's correct because a reboot is functionally equivalent
  to a crash for a daemon that has no cross-reboot state to preserve.
  The `DaemonStopReason` enum has no `reboot` value, and we don't
  need one.
- **SIGHUP refuses topology changes loudly.** Settings fields tagged
  RELOAD_RESTART (state_root, run_dir, events_log_path,
  metrics_socket_path, carriers_yaml_path, startup_delay_seconds)
  trigger a `restart_required` event listing the offending fields and
  keep the old Settings. The daemon does NOT silently apply some and
  reject others — it's atomic: either the whole new Settings swap
  succeeds or none of it does.
- **Logrotate writer-side reopen is inotify-driven, not signal-driven.**
  The .deb's logrotate snippet has empty postrotate; the daemon's
  asyncinotify producer detects the rename and reopens. Decoupled
  responsibilities (SIGHUP = config reload, asyncinotify = log
  reopen). One signal verb per concern.
- **Logrotate reader-side handles BOTH modes per FR-43.1.** We don't
  own Zao's logrotate config; the reader handles `create` mode
  (MOVE_SELF/DELETE_SELF + reopen via parent-dir watch) and
  `copytruncate` mode (st_size truncation check on each read). Both
  paths are exercised by Phase 3's fixture suite.
- **qmi_wwan reload is invisible to the policy engine.** No
  special-case predicate. The state machine's `present → False →
  present → True` transitions ARE the NFR-12 success criteria #5
  shape. Phase 2's NFR-11 isolation (try/except around
  `policy_engine.run_cycle`) is the safety net.
- **CapabilityBoundingSet ships Phase 4-forward.** `CAP_SYS_MODULE`
  is preallocated even though Phase 3 doesn't exercise it. One
  unit-file edit at the start of Phase 3, no mid-rollout edits in
  Phase 4. Single source of truth across the phase boundary.
- **`Restart=on-failure`, NOT `Restart=always`.** Clean SIGTERM exit
  (clean-shutdown marker write succeeds, exit 0) does NOT trigger a
  systemd restart. Operator-initiated `systemctl stop` stays stopped.
- **`StartLimitBurst=20` over default 5.** Default rate-limit was the
  fleet-bricker (PITFALLS §4.2). 20 restarts within 300 s gives ops
  time to push a config fix before any one box gets banished.
- **`PrivateMounts=` is INTENTIONALLY off.** Incompat with
  `LoadCredential=` on systemd 245 (Ubuntu 20.04; PITFALLS §4.3).
  ProtectSystem=strict + ProtectHome=true + NoNewPrivileges=yes
  are the defense-in-depth substitutes.
- **`RuntimeDirectoryPreserve=yes` is load-bearing.** Without it,
  systemd cleans `/run/spark-modem-watchdog/` on stop, taking out the
  PID lock + clean-shutdown marker + state.lock + modem-*.lock +
  metrics.sock. PITFALLS §4.4 — the directives form a cluster:
  `RuntimeDirectory=spark-modem-watchdog` +
  `RuntimeDirectoryPreserve=yes`.

</specifics>

<deferred>
## Deferred Ideas

Items mentioned during analysis or surfaced during scope policing that
belong outside Phase 3. None lost.

### Phase 4 (Destructive Actions & HIL)

- Destructive actions (`modem_reset`, `usb_reset`, `driver_reset`)
  with the signal-quality gate end-to-end. Phase 3 ships the
  `CAP_SYS_MODULE` cap preallocated (U-01) so Phase 4 doesn't edit the
  unit file.
- `kmsg/classifier` regex catalog may grow as Phase 4 HIL surfaces
  new dmesg shapes (e.g. driver_reset's own kernel messages). Add via
  ADR or as a Phase 4 follow-up; NEVER bury new enum values without
  trace.
- `oom` and `kill` reasons in `DaemonStopReason` classification
  (L-04). Phase 3 ships `sigterm` / `crash` / `config_invalid`; oom +
  kill require external observation (systemd's `MemoryMax=` triggers
  oom; SIGKILL is undetectable from the dying process). Phase 4 may
  wire a `journalctl -k` post-mortem at boot or accept these as
  best-effort.
- HIL fault-injection lane (`tests/hil/`) for verifying:
  - sd_notify watchdog actually kicks at 90 s when a cycle hangs
    (bench Jetson + deliberately wedged qmicli).
  - StartLimitBurst=20 actually allows 20 restarts within 300 s.
  - LoadCredential= delivers the HMAC secret correctly under our
    sandboxing (PITFALLS §4.3 verification).
  - `qmi_wwan` reload via `modprobe -r qmi_wwan; modprobe qmi_wwan`
    produces the expected `disconnected → recovering → healthy`
    transition shape.

### Phase 5 (Bench & Field Shadow)

- Cross-fleet observation of dmesg variance — the kmsg classifier's
  regex catalog likely needs widening based on the variety of dmesg
  lines real Jetsons produce under load.
- WATCHDOG cadence calibration based on real-fleet cycle-duration
  histograms (`cycle_duration_seconds` + `cycle_drift_seconds` in
  Prometheus). 90 s may prove too conservative or too aggressive.
- LoadCredential rotation procedure (per-box HMAC secret rotation
  without daemon downtime — SIGHUP suffices because the secret is
  RELOAD_DATA-equivalent, but the rotation runbook lives in Phase 5).

### v2.1 (already deferred in REQUIREMENTS.md)

- HTTP API on Unix socket (CTL-01, CTL-02) — the inbound IPC
  prohibition is a Phase 3 invariant (CLAUDE.md §11: "No inbound IPC
  in v2.0").
- Webhook batching (WHK-01, M-3).
- `ctl identity export/import` for RMA box swap (CARR-01) — uses the
  identity-map APIs Phase 3 finishes wiring (E-04).
- `ctl simulate-issue` (SIM-01, M-24) — would be a great way to test
  the kmsg classifier without touching real dmesg.
- 5G NR-aware policy (NR-01).

### Tactical / Claude-discretion (handled during planning)

- kmsg classifier exact regex strings (E-03 enum is locked; regexes
  are data).
- Producer task naming convention (snake_case, suffix `_producer`).
- inventory.scan() netns derivation specifics (sysfs vs `ip netns
  identify`).
- observer's identity-extraction qmicli call placement
  (`observer/probe.py` extension vs new `observer/identity.py`).
- kmsg dedup state shape (sliding window vs timestamp-of-last-emit).
- `cycle_drift_seconds` semantics for negative drift (early-wake);
  clamp to 0 vs report as-is.
- Test seam Protocol locations (co-located per Phase 1/2 convention).
- Plan slicing within the 6–8 plan target (planner's call).

### Unrelated future work

- ADR-0014 candidate: "Event source supervision pattern" formalizing
  the `restart_on_crash` shape if it grows beyond Phase 3 (e.g. a
  Phase 4 D-Bus watcher for Zao restart announcements would adopt
  the same pattern; PITFALLS §2.3/§2.4).
- Investigation of D-Bus `zao-infra-ctrl.service` state subscription
  (PITFALLS §2.3 / §2.4 — qmi-proxy ownership transition on Zao
  restart). Not in Phase 3 scope; may land as a Phase 4 enhancement.

</deferred>

---

*Phase: 03-linux-event-sources-lifecycle*
*Context gathered: 2026-05-07*
