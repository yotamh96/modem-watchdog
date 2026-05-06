# PRD — spark-modem-watchdog v2

| Field         | Value                                          |
| ------------- | ---------------------------------------------- |
| Status        | Draft                                          |
| Owner         | TBD (modem platform)                           |
| Last updated  | 2026-05-05                                     |
| Supersedes    | The v1 toolchain (bash scripts in repo root).  |

---

## 1. Executive summary

`spark-modem-watchdog` is the on-device software that keeps a fleet
of Jetson Orin NX bonded-uplink boxes online. It watches four Sierra
EM7421 cellular modems, detects when one is unhealthy, and applies
the smallest recovery action that has a chance of fixing it — without
making things worse. v2 is a from-scratch rewrite that preserves the
operational principles proven out in v1 while replacing the
implementation, the contracts, and the observability story.

## 2. Background

### 2.1 What v1 is

A pipeline of bash scripts (`diag.sh` → `recovery.sh` → `auto_profile.sh`,
`zao_reset_line.sh`) driven by a systemd watchdog. It runs in a 120-second
loop: produce JSON diagnostics, decide actions, apply them with backoff
and escalation ceilings. Documented in `../README.md`.

### 2.2 What v1 got right (we keep these)

- **Read-only diag → typed wire format → policy → action tools** as
  separate seams.
- **Zao log is authoritative** for "is this line bonding?" — never
  probe an active line.
- **Signal-quality gate**: a reset cannot fix RF, so don't run one
  on a modem with insufficient signal.
- **Bounded recovery**: escalation ceilings, backoff, one-action-per-
  modem-per-cycle, priority order across categories.
- **Sysfs-based runtime discovery** of line→cdc-wdm→USB mapping.
- **Idempotent operations** at every level.

### 2.3 What v1 got wrong (we fix these)

- Two-language hybrid (bash + python heredocs) with hand-rolled JSON
  encoder; no type checking; fragile parsing of `qmicli` text output.
- The contract between diag and recovery is informal: free-form
  `detail` strings, heterogeneous `who` fields, no `schema_version`
  enforcement.
- Recovery counters never decay — modems become permanently
  "exhausted" after a single bad incident.
- Backoff only blocks the *exact same* action; ping-pong escalation
  is possible.
- Wall-clock time used for backoff (NTP step can wedge it).
- Polling-only architecture; events on the system are ignored.
- No tests, no fixtures, no replay harness.
- No log rotation, no metrics, no status endpoint, no alerting hook.
- Command injection in `auto_profile.sh` (python heredoc with
  variable interpolation).
- `.bak` files instead of git.

The full review is preserved in the project history at
`../docs-review-v1.md` (TODO: lift from chat transcript).

## 3. Goals (G) and non-goals (NG)

### Goals

| ID  | Goal                                                           |
| --- | -------------------------------------------------------------- |
| G1  | Maximize end-user uplink availability across the 4 bonded modems. |
| G2  | Detect modem health regressions within 30 s of onset.          |
| G3  | Apply the minimum-impact recovery action with a >50 % chance of fixing the issue. |
| G4  | Never run a destructive recovery that has zero chance of fixing the observed issue (e.g. reset on bad RF). |
| G5  | Provision SIM-correct APNs automatically on first boot.        |
| G6  | Expose a typed status snapshot and Prometheus-scrape metrics for NOC dashboards. |
| G7  | Run the same code under a fake hardware shim for CI tests.     |
| G8  | Cleanly survive reboots, SIM swaps, modem flaps, USB hub
       resets, and Zao restarts.                                       |
| G9  | Be operable by a site technician with shell access and the runbook. |

### Non-goals

| ID    | Non-goal                                                     |
| ----- | ------------------------------------------------------------ |
| NG1   | Replacing or modifying Zao. We integrate; we do not own it.  |
| NG2   | Multi-region carrier support beyond Israel in v2.0. (Carrier table is data; new MCCs land in a config file, not a release.) |
| NG3   | Cloud control plane. v2 is a daemon on the box; remote management is out of scope. |
| NG4   | Generic "any modem" support. v2 targets Sierra EM7421 + qmi_wwan. Other modems may work but are not tested. |
| NG5   | A GUI or web UI on the device. CLI + structured status only. |
| NG6   | Replacing `qmicli` as the QMI client. We wrap it.            |

## 4. Personas and primary use cases

### P1 — Field site technician

Installs a fresh-flashed Jetson at a customer site. Has SSH and sudo;
no permanent network at install time.

- UC1: Run `spark-modem ctl install` and walk away.
- UC2: After installation, run `spark-modem ctl status` and see all four lines green.
- UC3: When something is red, run `spark-modem ctl diag --explain` and follow the suggested action.

### P2 — NOC operator

Watches a fleet from a dashboard. Cares about aggregates, alerts.

- UC4: See a Prometheus time-series of "modems healthy / total" per box.
- UC5: Get a webhook alert when a modem reaches the `Exhausted` state.
- UC6: Pull the last 24 h of recovery actions from one box for forensics.

### P3 — Field engineer (escalation)

Onboards remotely when the site tech and NOC are stuck.

- UC7: Tail a structured event log and follow what the watchdog has tried.
- UC8: Force a reset state, replay a captured diag JSON in dry-run, run a single action manually.
- UC9: Dump the per-modem state machine state and inspect counters.

### P4 — Developer (us)

Adds a new check, a new recovery action, a new carrier APN.

- UC10: Add a new diag check; write a fixture; assert recovery picks the right action.
- UC11: Add a new MCC/MNC to the carrier table without a code change.
- UC12: Bump the schema version and ensure old/new components fail loudly.

## 5. Functional requirements

Numbering is stable across revisions. New requirements append at the
end; obsolete ones are marked `[withdrawn]`.

### 5.1 Discovery and inventory

- **FR-1.** The system MUST discover all Sierra-VID modems on the USB
  bus at startup and on udev `add`/`remove` events.
- **FR-2.** The system MUST resolve each modem to a `(line, cdc_wdm,
  usb_path, namespace, iface)` tuple via sysfs, never via hardcoded
  paths.
- **FR-3.** The system MUST detect SIM identity (ICCID, IMSI) per
  modem and persist a `(usb_path → identity)` map across reboots.
- **FR-4.** The system MUST detect a SIM swap (ICCID change at the
  same `usb_path`) and trigger re-provisioning.

### 5.2 Diagnosis

- **FR-10.** The system MUST consult Zao's authoritative source
  (`zao-remote-endpoint.log` `RASCOW_STAT` lines) before probing a
  modem via QMI; if Zao reports the line as `active`, no QMI probe
  is run for that line.
- **FR-11.** The system MUST gather, per inactive modem: USB speed,
  QMI responsiveness, operating mode, SIM card state, SIM application
  state, registration state, serving carrier (MCC/MNC/description),
  signal (RSSI/RSRP/RSRQ/SNR), profile-1 APN, data session state,
  current IPv4.
- **FR-12.** The system MUST classify each modem as `Healthy`,
  `Degraded(reason)`, `RfBlocked`, `Recovering(level)`, or
  `Exhausted` (see [RECOVERY_SPEC.md](RECOVERY_SPEC.md)).
- **FR-13.** The system MUST emit a typed `Diag` snapshot every cycle
  conforming to [SCHEMA.md § Diag](SCHEMA.md#diag).
- **FR-14.** The system MUST detect host-level issues (USB
  over-current, "device not accepting address" enumeration failures,
  thermal events) from `dmesg` and treat them as global issues.

### 5.3 Recovery

- **FR-20.** Given a `Diag` snapshot, the system MUST select at most
  one recovery action per modem per cycle.
- **FR-21.** Action selection MUST follow the priority order
  `config > sim > datapath > registration > qmi`. The highest-priority
  issue wins; lower-priority issues are deferred to the next cycle.
- **FR-22.** Action selection MUST honour the per-modem escalation
  ladder defined in [RECOVERY_SPEC.md](RECOVERY_SPEC.md): set_apn,
  fix_raw_ip, sim_power_on, soft_reset → modem_reset → usb_reset →
  give-up (Exhausted).
- **FR-23.** The system MUST gate `modem_reset` and `usb_reset`
  actions when the modem's signal is *measurably* below thresholds
  (see [RECOVERY_SPEC.md § Gates](RECOVERY_SPEC.md#gates)).
- **FR-24.** The system MUST gate the global `driver_reset` to fire
  only when ≥75 % of modems are simultaneously QMI-hung AND at least
  one of them has actionable signal.
- **FR-25.** Same-action backoff MUST suppress repeating any action
  on the same modem within `BACKOFF_SECONDS` (default 300 s).
- **FR-26.** Per-action escalation counters MUST decay to zero after
  `K` consecutive `Healthy` cycles for that modem (see ADR-0006).
- **FR-27.** All recovery actions MUST be implemented as separate,
  idempotent functions and MUST be runnable individually via the CLI.
- **FR-28.** The system MUST provide `--dry-run` everywhere a real
  action would mutate state.

### 5.4 Provisioning

- **FR-30.** The system MUST select the correct APN for a SIM by
  looking up `(MCC, MNC)` in a config-file carrier table.
- **FR-31.** The system MUST write profile #1 only when the desired
  APN differs from the currently programmed value.
- **FR-32.** The system MUST verify the post-write APN by reading
  the profile back and MUST fail loudly if it does not match.
- **FR-33.** New MCC/MNC entries MUST be addable without a code
  release (config-file reload).

### 5.5 Observability

- **FR-40.** The system MUST write a structured event line (JSON
  Lines) for every issue observed and every action taken/skipped, to
  `/var/log/spark-modem-watchdog/events.jsonl`.
- **FR-41.** The system MUST maintain a `status.json` file at
  `/var/lib/spark-modem-watchdog/status.json` containing the current
  per-modem state, last cycle timestamp, and aggregate health.
- **FR-42.** The system MUST expose a Prometheus scrape endpoint on
  a configurable Unix socket (default `/run/spark-modem-watchdog/metrics.sock`).
- **FR-43.** The system MUST rotate the event log via `logrotate`
  with a 7-day, 100 MiB retention default.
- **FR-44.** The system MUST emit a webhook POST (configurable URL)
  on `Healthy → Degraded` and `Recovering → Exhausted` transitions,
  with a typed payload.

### 5.6 Operability

- **FR-50.** The system MUST ship a single CLI entry point
  (`spark-modem`) with subcommands `diag`, `recovery`, `provision`,
  `reset`, `status`, `ctl`.
- **FR-51.** The CLI MUST accept `--qmi-fixture-dir=PATH` to read
  recorded `qmicli` output from disk instead of executing `qmicli`.
- **FR-52.** The CLI MUST accept `--diag-fixture=PATH` for the
  recovery subcommand to replay a captured snapshot.
- **FR-53.** The system MUST run as a systemd unit with `Type=notify`
  (so `systemctl status` shows real readiness) and graceful SIGTERM
  handling within 5 s.
- **FR-54.** Configuration MUST come from, in order of precedence:
  command-line flags, environment variables, drop-in YAML files in
  `/etc/spark-modem-watchdog/conf.d/`, baked-in defaults.

### 5.7 Safety

- **FR-60.** The system MUST refuse to start if `qmicli`, `ip`, and
  `python3` (≥3.11) are not present on `PATH`.
- **FR-61.** The system MUST hold a single PID lock on `/run/spark-modem-watchdog/lock`
  for the duration of any state mutation.
- **FR-62.** All persistent file writes MUST be atomic (temp file +
  rename).
- **FR-63.** The system MUST validate every external input
  (`qmicli` output, JSON snapshot, Zao log) before acting on it; an
  invalid input is a logged error, not a crash.
- **FR-64.** The system MUST never `exec` a string built from
  external data; all subprocess calls MUST use list-form `argv`.

## 6. Non-functional requirements

### 6.1 Performance

| ID       | Requirement                                                  |
| -------- | ------------------------------------------------------------ |
| NFR-1    | A full diag cycle MUST complete in ≤ 10 s on the target Jetson when no modems are unresponsive. |
| NFR-2    | The daemon MUST consume ≤ 1 % CPU averaged over a 10-min window in steady state. |
| NFR-3    | RSS MUST stay ≤ 80 MiB.                                       |
| NFR-4    | Per-modem QMI probes MUST run in parallel (asyncio or threads), not sequentially. |
| NFR-5    | Disk write rate MUST stay ≤ 1 MiB/min in steady state (events log + status file). |

### 6.2 Reliability

| ID       | Requirement                                                  |
| -------- | ------------------------------------------------------------ |
| NFR-10   | The daemon MUST recover from any single transient error (parse failure, qmicli timeout, partial fixture) within one cycle. |
| NFR-11   | An uncaught exception in the policy engine MUST NOT terminate the daemon; it MUST be logged and the cycle skipped. |
| NFR-12   | The daemon MUST tolerate `qmi_wwan` driver reload during operation: a recovery `driver_reset` MUST be observable as a clean state transition, not a daemon crash. |
| NFR-13   | The daemon MUST reach steady-state operation within 60 s of process start, given Zao is already running. |

### 6.3 Observability

| ID       | Requirement                                                  |
| -------- | ------------------------------------------------------------ |
| NFR-20   | Every state transition MUST be logged as a single JSON line with fields `ts, modem, from, to, cause, action, dry_run`. |
| NFR-21   | The Prometheus exporter MUST expose `actions_total{kind,modem,result}`, `signal_dbm{modem,kind}`, `cycle_duration_seconds`, `modem_state{modem,state}` (gauge with state as label). |
| NFR-22   | A snapshot of `status.json` plus the last 200 events MUST be retrievable via a single `spark-modem ctl support-bundle` command for offline analysis. |

### 6.4 Security

| ID       | Requirement                                                  |
| -------- | ------------------------------------------------------------ |
| NFR-30   | Daemon runs as root (it MUST manipulate netns, sysfs, modules), but no other process is granted suid bits. |
| NFR-31   | All subprocess calls MUST pass arguments as a list, never a shell string. |
| NFR-32   | External text inputs (qmicli output, Zao log, JSON files) MUST be parsed by a validator that rejects unexpected types/shapes. |
| NFR-33   | Webhook URLs MUST be validated to be `https://` only by default; `http://` allowed only with an explicit `webhook_allow_http=true` config. |
| NFR-34   | No secrets are stored on disk. The webhook signing secret (if used) is read from systemd `LoadCredential=`. |

### 6.5 Maintainability

| ID       | Requirement                                                  |
| -------- | ------------------------------------------------------------ |
| NFR-40   | The codebase MUST pass `mypy --strict`, `ruff`, and a project-wide formatter. |
| NFR-41   | Unit tests MUST run without hardware on a developer laptop, using fixtures only. |
| NFR-42   | A new MCC/MNC entry MUST be addable in a single YAML edit + reload, without a release. |
| NFR-43   | Schema versions are integers (`v1`, `v2`); a daemon MUST refuse to load a snapshot/state file from a future schema and MUST migrate or refuse a snapshot from a known-old schema with an explicit message. |

## 7. Constraints

### 7.1 Hardware

- **C1.** NVIDIA Jetson Orin NX (16 GB) on P3768 reference carrier.
- **C2.** 4× Sierra Wireless EM7421 (VID:PID `1199:9091`) on a USB 3
  hub plugged into one carrier USB-A port, typically enumerating on
  `3610000.xhci/usb2/2-3/2-3.1/2-3.1.{1..4}`.

### 7.2 Software

- **C10.** JetPack 5.1.5 / L4T R35.6.4 / Ubuntu 20.04 / aarch64.
- **C11.** Kernel 5.10-tegra with `qmi_wwan` and `cdc_wdm` modules.
- **C12.** Soliton Zao SDK 2.1.0+ (`ZaoInfraCtrl` + `ZaoRemoteEndpointCloud`).
- **C13.** ModemManager MUST remain disabled (Zao requires exclusive
  modem access).
- **C14.** Python ≥ 3.11 available system-wide (it ships with Ubuntu
  20.04 via `python3.11` PPA, or we bundle it in a venv).

### 7.3 Network

- **C20.** Install-time the box MAY be offline; the installer MUST
  not require internet.
- **C21.** No outbound dependencies at runtime except the optional
  alert webhook.

### 7.4 Regulatory

- **C30.** No code change is required for new MCC/MNC entries; they
  are configuration data.

## 8. Success metrics

These are measured on the production fleet 90 days after v2.0 ships
across the fleet. v2 is considered successful if it meets all of:

- **M1.** ≥ 99.5 % per-modem availability over a rolling 7 days, where
  availability = `(seconds_in_Healthy + seconds_in_Recovering) / total_seconds`.
- **M2.** Median MTTR (from `Healthy → Degraded` to `Degraded → Healthy`)
  ≤ 60 s for SIM-app issues, ≤ 90 s for registration issues, ≤ 180 s
  for QMI-hung issues.
- **M3.** False-positive destructive resets (a `modem_reset` or
  `usb_reset` that did not change signal/registration outcome within
  one cycle) ≤ 5 % of all destructive resets fleet-wide.
- **M4.** Zero `Exhausted` states caused by counter accumulation
  rather than a real recurring fault. Verified by running the
  decay-on-healthy logic against 30 days of replay traces.
- **M5.** P99 cycle duration ≤ 10 s.
- **M6.** Zero out-of-memory or unhandled-exception daemon restarts
  in any 30-day window across the fleet.
- **M7.** Dev-laptop test suite runs in ≤ 30 s on a typical laptop.

## 9. Out of scope (v2.0)

- Carrier table for non-Israeli MCCs (data, not code; can be added
  post-launch via config).
- Multi-SIM (eSIM) management. EM7421 is single-SIM.
- 5G NR-only operation (the modem is LTE+NR; we currently treat NR
  as "informational" — full NR-aware policy is v2.1).
- Cellular-only fleet management (assumes Zao bonding is the uplink).
- Hot-plug of modems mid-flight (we support it via udev events but
  do not prioritise it; SLA on FR-1 covers boot-time discovery).
- Cross-vendor modems (Quectel, Telit, etc.).

## 10. Open questions

| #   | Question                                                       | Owner    |
| --- | -------------------------------------------------------------- | -------- |
| Q1  | Do we want a HTTP API on a Unix socket (vs. a CLI-only ctl tool)? Pros: easier remote agents, test harness. Cons: more code, more surface area. | Eng lead |
| Q2  | Should the daemon take ownership of `qmi-proxy` (start it if not running) or assume Zao does? | Eng lead |
| Q3  | What is the minimum-supported Zao SDK version? 2.1.0 confirmed; older may fail Zao-log parsing. | Field eng |
| Q4  | Do we want feature parity with the v1 `--watch` mode, or replace it with `journalctl -fu` + Prometheus? | Product |
| Q5  | Is the alert webhook payload signing requirement (HMAC-SHA256 with shared secret) a v2.0 must, or v2.1? | Security |
| Q6  | How do we communicate config changes to the running daemon: SIGHUP reload, file-watcher, restart-only? | Eng lead |
| Q7  | Who owns the carrier table after launch? Updates to Israeli MNCs change every couple of years. | Product |

## 11. Glossary

See [GLOSSARY.md](GLOSSARY.md).
