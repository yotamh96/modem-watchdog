# Architecture — spark-modem-watchdog v2

| Field         | Value                  |
| ------------- | ---------------------- |
| Status        | Draft                  |
| Owner         | TBD (modem platform)   |
| Last updated  | 2026-05-05             |

This document is the architectural ground truth. When v2 code does
something surprising, the answer SHOULD be visible here or in a linked
ADR. If it is not, the architecture has drifted and either the code
or this doc is wrong.

---

## 1. System context

```
                 ┌───────────────────────────────────────────────────┐
                 │                  NVIDIA Jetson Orin NX             │
                 │                                                    │
   +-- USB 3 --→ │  ┌──────────┐    ┌────────────┐   ┌─────────────┐  │
   │             │  │ Sierra   │    │  qmi_wwan  │   │  Zao stack  │  │
   │ 4× Sierra   │  │ EM7421×4 │←──→│  driver    │←─→│ Infra+Cloud │←──── bonded
   │ EM7421     →│  │          │    │  cdc-wdm0..3│  │             │     uplink
   │ on USB hub  │  └──────────┘    └────────────┘   └─────────────┘     to PoP
   │             │         ▲                ▲                ▲           ─────
   │             │         │ qmicli         │ ip netns,      │ inotify
   │             │         │                │ sysfs          │ logfile
   │             │         │                │                │
   │             │  ┌──────┴──────────────────┴────────────────┴────┐  │
   │             │  │              spark-modem-watchdog              │  │
   │             │  │                  (this project)                 │  │
   │             │  │                                                 │  │
   │             │  │  Observer  →  Policy Engine  →  Action Workers  │  │
   │             │  │                                                 │  │
   │             │  │  State Store    Status Reporter   Alerting      │  │
   │             │  └──────────────────────────────────────────────────┘  │
   │             │                ▲              │             ▲       │
   │             │                │ udev,        │ status.json │ events.jsonl │
   └─────────────┴────────────────┘ rtnetlink    ▼ /var/lib    ▼ /var/log    │
                                                  ▲              │       │
                                                  │ Prom scrape  │ webhook POST │
                                                  │              ▼       │
                                                  │   ┌─────────┐  ┌──────────┐
                                                  │   │   NOC    │  │   Alert  │
                                                  │   │ dashboard│  │  manager │
                                                  │   └──────────┘  └──────────┘
```

External actors:

- **Site technician** — runs `spark-modem ctl status` and `... diag` on
  the box.
- **NOC** — scrapes Prometheus metrics, reads `status.json` over fleet-
  management agent, receives webhook alerts.
- **Field engineer** — SSH for forensics; replays `events.jsonl`.

External dependencies (we call these; we do not own them):

- `qmicli` from `libqmi-utils` — control-plane to modems.
- `ip` (`iproute2`) for namespace operations.
- `qmi-proxy` (started by Zao) — multiplexes QMI access; we route
  through it when available.
- `InfraCtrl.script` (Zao) — owns profile programming. We invoke it
  rather than writing profiles ourselves, because Zao must observe
  the change.
- `udev`, `rtnetlink`, `inotify` — event sources.

## 2. What we are taking from v1

These v1 design decisions are correct and we keep them. If you find
yourself wanting to revisit them, raise an ADR first.

| v1 decision                                  | Why we keep it                                                                                                |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Three seams: observe → decide → act          | Enables dry-run, replay, single-component testing.                                                            |
| Zao is authoritative for active lines        | Avoids QMI control-channel race; Zao's view is correct by definition (it's the entity using the line).        |
| Signal-quality gate                          | Without it, a watchdog actively damages uptime in marginal RF.                                                |
| Bounded escalation ladder                    | Distinguishes us from a stuck-reset-loop watchdog.                                                            |
| One-action-per-modem-per-cycle               | Prevents stacked operations.                                                                                  |
| Priority order across categories             | Cheapest, most-deterministic things first.                                                                    |
| Sysfs runtime discovery                      | Survives port shifts and re-enumeration.                                                                      |
| Idempotent action implementations            | Safe to retry; safe to dry-run.                                                                               |
| Atomic file writes (temp + rename)           | State is always consistent on disk.                                                                           |

## 3. What we are dropping from v1

| v1 thing                                             | Why we drop it                                                                                                |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Bash-as-implementation language                      | Forks of `python3` for JSON; hand-rolled JSON encoder; fragile `awk -F"'"` parsing. See ADR-0001.             |
| Free-form `detail` strings in issues                 | Pattern-matched on substrings; one typo silently changes behaviour. Replaced by typed enums. See ADR-0004.    |
| Heterogeneous `who` field                            | `"ALL"` / `/dev/...` / `cdc-wdmN` / `lineN/wwanN`. Replaced by tagged union.                                  |
| Counters that never decay                            | Modems become permanently `Exhausted` after a single bad incident. See ADR-0006.                              |
| Wall-clock backoff                                   | NTP step can wedge backoff. See ADR-0007.                                                                     |
| Polling-only loop                                    | Misses events that a kernel-side subscription would have caught immediately. See ADR-0002.                    |
| Python heredoc with shell var interpolation          | Command injection via SIM ICCID. Replaced by typed `subprocess.run(list-form)`.                               |
| `.bak` files instead of git                          | Required: project lives in git from commit 0.                                                                 |
| Single rolling text log                              | Replaced by JSON Lines events log + structured status snapshot + Prom metrics.                                |

## 4. Component architecture

The daemon is a single Python process composed of well-defined modules
that can be unit-tested in isolation. Each module owns a small surface
and communicates through typed dataclasses.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ spark-modem-watchdog daemon (single Python process)                      │
│                                                                           │
│  ┌──────────────┐       ┌──────────────┐       ┌──────────────────────┐  │
│  │  Inventory   │──────▶│   Observer   │──────▶│   Policy Engine      │  │
│  │              │       │              │       │  (state machine)     │  │
│  │  udev,       │       │  qmicli,     │       │  decides actions,    │  │
│  │  sysfs       │       │  Zao log,    │       │  enforces gates,     │  │
│  │  enumeration │       │  netns reads │       │  picks priority      │  │
│  └──────────────┘       └──────────────┘       └──────────┬───────────┘  │
│                                                            │              │
│                                                            ▼              │
│                                                  ┌──────────────────┐    │
│                                                  │  Action Workers  │    │
│                                                  │                  │    │
│                                                  │  set_apn,        │    │
│                                                  │  fix_raw_ip,     │    │
│                                                  │  sim_power_on,   │    │
│                                                  │  soft_reset,     │    │
│                                                  │  modem_reset,    │    │
│                                                  │  usb_reset,      │    │
│                                                  │  driver_reset    │    │
│                                                  └──────────────────┘    │
│                                                                           │
│  ┌──────────────┐       ┌──────────────┐       ┌──────────────────────┐  │
│  │  State Store │◀─────▶│ Event Logger │       │ Status Reporter      │  │
│  │              │       │              │       │                      │  │
│  │  per-modem   │       │  events.jsonl│       │  status.json,        │  │
│  │  states,     │       │  rotated     │       │  Prom exporter,      │  │
│  │  counters,   │       │  by logrotate│       │  webhook hooks       │  │
│  │  identity    │       │              │       │                      │  │
│  └──────────────┘       └──────────────┘       └──────────────────────┘  │
│                                                                           │
│  ┌──────────────┐       ┌──────────────┐       ┌──────────────────────┐  │
│  │   Config     │       │   Clock      │       │   Subprocess Wrap    │  │
│  │              │       │              │       │                      │  │
│  │  YAML +      │       │  monotonic + │       │  qmicli, ip netns,   │  │
│  │  env + flags │       │  wall (only  │       │  systemctl, modprobe │  │
│  │              │       │  for stamps) │       │  (list-form argv)    │  │
│  └──────────────┘       └──────────────┘       └──────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Module responsibilities

| Module             | Owns                                                                          | Inputs                                          | Outputs                              |
| ------------------ | ----------------------------------------------------------------------------- | ----------------------------------------------- | ------------------------------------ |
| `inventory`        | Knowing what modems exist and their topology (line, cdc-wdm, usb_path, ns).   | sysfs, udev events.                             | `Modem` records, change events.      |
| `observer`         | Producing `Diag` snapshots.                                                   | Inventory + qmicli + Zao log + netlink.         | `Diag`.                              |
| `policy`           | Deciding what to do given a `Diag` and current per-modem `ModemState`.        | `Diag`, `ModemState`, config.                   | `Action[]` (zero or one per modem).  |
| `actions`          | Executing recovery actions.                                                   | `Action`, qmicli, sysfs, InfraCtrl.script.      | `ActionResult`, side-effects.        |
| `state_store`      | Persisting per-modem state, counters, SIM identity, global markers.           | Updates from policy + actions.                  | Read-back for next cycle.            |
| `event_logger`     | Writing `events.jsonl`.                                                       | Events from any module.                         | Lines on disk.                       |
| `status_reporter`  | Writing `status.json`, serving Prom scrape, posting webhooks.                 | Aggregated state + transitions.                 | Files, HTTP, webhooks.               |
| `config`           | Loading + merging defaults / YAML / env / flags. Hot-reload via SIGHUP.       | Files, env, flags.                              | `Config` dataclass.                  |
| `clock`            | Returning monotonic seconds for backoff math + wall ISO-8601 stamps for logs. | `time.monotonic`, `time.time`.                  | seconds, ISO strings.                |
| `subproc`          | Wrapping every external command. Always argv-list; always with timeout.       | argv, timeout, stdin.                           | `(rc, stdout, stderr)`.              |
| `qmi`              | Wrapping `qmicli` calls; parsing the human output into typed records.         | `subproc`, dev path, intent (`get_signal`...).  | typed result or `QmiError`.          |
| `zao_log`          | Tailing Zao log; exposing latest `RASCOW_STAT` view as a fresh struct.        | inotify on logfile.                             | `ZaoLineState[]`, last-seen ts.      |
| `cli`              | The `spark-modem` entry point and subcommands.                                | argv, fixtures, daemon socket.                  | exit codes, stdout JSON / text.      |

### 4.2 Cycle (the hot loop)

The daemon runs an outer cycle that wakes on either an event or a
timer. One cycle does:

1. **Refresh inventory** — apply any pending udev `add`/`remove` events.
2. **Read Zao log state** — pull latest `RASCOW_STAT` snapshot from
   the inotify-fed parser.
3. **Run observer in parallel per modem** — `asyncio.gather` across
   inactive lines (Zao-active lines are skipped per FR-10). Each per-
   modem observation has its own timeout budget.
4. **Build `Diag`** — combine per-modem records, host-level facts
   (dmesg, thermal), and the issue list.
5. **Persist `Diag`** to `last_diag.json` (atomic write).
6. **Run policy engine** — for each modem, look up current `ModemState`
   from store, intersect with `Diag.issues`, decide `Action | None`.
   Apply gates (signal, backoff, escalation, global driver-reset).
7. **Execute actions** — one per modem at most; record start/end in
   events log; capture `ActionResult`.
8. **Update state store** — transition per-modem state; bump counters;
   record action timestamps; decay counters where applicable.
9. **Write `status.json`** — single atomic write.
10. **Emit webhooks** — for state transitions that match alerting rules.
11. **Sleep** until the next event arrives or the polling deadline expires.

### 4.3 Concurrency model

- The daemon is `asyncio` based. The hot loop is single-threaded.
- Per-modem observer probes run concurrently with `asyncio.gather`,
  with a per-task timeout (default 8 s).
- A single `asyncio.Lock` guards the state store during cycle commits.
- `subproc` calls use `asyncio.subprocess` and never block the loop.
- Inotify, udev, rtnetlink consumers are background tasks that push
  events onto an `asyncio.Queue` consumed by the main loop.
- A PID-file lock on `/run/spark-modem-watchdog/lock` ensures only
  one daemon ever runs.

## 5. Tech stack

| Concern              | Choice                                              | Rationale (link)                              |
| -------------------- | --------------------------------------------------- | --------------------------------------------- |
| Language             | Python 3.11+                                        | [ADR-0001](adr/0001-language-python.md)       |
| Async runtime        | `asyncio` (stdlib)                                  | One-process, IO-bound, no thread complexity.  |
| Schema/types         | `pydantic` v2 for all wire formats                  | [ADR-0004](adr/0004-typed-contract.md)        |
| Config               | YAML via `PyYAML`, layered with env + flags         | FR-54.                                         |
| Subprocess           | stdlib `asyncio.subprocess`                         | List-form argv, no shell.                     |
| QMI parsing          | In-house thin wrapper over `qmicli` text output     | qmicli output is stable enough; no `libqmi` Python bindings on this Jetson. |
| Logging              | stdlib `logging` + JSON formatter                   | One handler for events.jsonl, one for journal.|
| Metrics              | `prometheus_client` over Unix socket                | Pull-based; NOC scrapes via fleet agent.      |
| Tests                | `pytest`, `pytest-asyncio`, fixture-driven          | [TEST_STRATEGY.md](TEST_STRATEGY.md)          |
| Lint/format          | `ruff`, `black` (configured-as-ruff-format)         | Single tool.                                  |
| Type-check           | `mypy --strict` on all modules                      | NFR-40.                                        |
| Packaging            | One Debian `.deb` containing a venv under `/opt/spark-modem-watchdog/`  | Avoids fighting Ubuntu's system Python. |
| Init                 | systemd unit (`Type=notify`)                        | FR-53.                                         |

## 6. Deployment model

```
/opt/spark-modem-watchdog/                  ← venv, code, default config
├─ bin/
│  └─ spark-modem                            ← single-file CLI shim
├─ lib/python3.11/site-packages/...          ← venv contents
├─ share/
│  ├─ default-config.yaml
│  └─ carriers/il.yaml                       ← MCC/MNC table
└─ libexec/
   └─ spark-modem-watchdog                    ← daemon entry point

/etc/spark-modem-watchdog/
├─ config.yaml                                ← site-specific overrides
└─ conf.d/
   ├─ 10-thresholds.yaml
   └─ 20-alerts.yaml

/etc/systemd/system/
├─ spark-modem-watchdog.service
└─ spark-modem-watchdog.service.d/           ← drop-ins (created by `ctl edit`)

/var/lib/spark-modem-watchdog/                ← state (mode 0750, owner root)
├─ status.json                                ← latest aggregate snapshot
├─ last_diag.json                             ← latest diag output
├─ state/
│  ├─ cdc-wdm0.json                          ← per-modem ModemState
│  ├─ cdc-wdm1.json
│  ├─ cdc-wdm2.json
│  └─ cdc-wdm3.json
├─ identity.json                              ← (usb_path → ICCID/IMSI/last_seen)
└─ globals.json                               ← driver_reset marker, etc.

/var/log/spark-modem-watchdog/
├─ events.jsonl                               ← rotated by logrotate
├─ events.jsonl.1.gz
└─ ...

/run/spark-modem-watchdog/
├─ lock                                       ← PID lock
└─ metrics.sock                               ← Prom scrape Unix socket
```

State directories are created by the post-install hook with explicit
ownership and modes; the daemon does not `mkdir` at runtime.

## 7. Storage and persistence

### 7.1 Per-modem state file

One JSON file per cdc-wdm device, under `state/`. Schema in
[SCHEMA.md § ModemState](SCHEMA.md#modemstate). Written atomically.
Read on every cycle; written only when something changes.

### 7.2 Identity map

`identity.json` is a single object keyed by USB sysfs path
(e.g. `2-3.1.1`). Survives cdc-wdm renumbering. Written by the
provisioner when ICCID/IMSI is read.

### 7.3 Globals

`globals.json` holds singletons that don't fit a single modem:
- `last_driver_reset_monotonic` (set by `driver_reset` action)
- `last_zao_log_seen_at` (set by zao_log tailer; used for staleness
  detection)
- `schema_version` (matches the daemon's; refusing future versions
  is a startup check)

### 7.4 What we **do not** persist

- The full `Diag` snapshot history. Use `events.jsonl` for that.
- Prometheus counters across daemon restarts (Prom client handles
  initialization to last-seen on its own where required, and a fresh
  start is fine for our metrics).

## 8. Event sources and the polling fallback

Polling alone is wasteful (v1) and slow. v2 subscribes to events
where the kernel or another component already emits them, and falls
back to polling for things with no event source.

| Event                              | Source                              | Use                                                    |
| ---------------------------------- | ----------------------------------- | ------------------------------------------------------ |
| USB device added / removed         | `udev` via `pyudev`                 | Inventory refresh; mark missing modems as `Disconnected`. |
| Link state change (wwan up/down)   | `rtnetlink` via `pyroute2`          | Trigger early diag for the affected modem.            |
| Zao log line appended              | `inotify` on `/var/log/zao-remote-endpoint.log` | Update `ZaoLineState`; if a line transitions active→inactive, schedule a cycle. |
| systemd unit state change          | `dbus` if available, else polled    | React to `zao-infra-ctrl.service` restarts (we re-bootstrap). |
| Signal quality drift               | None (polled)                       | Scheduled in the cycle timer.                          |
| Profile #1 APN drift               | None (polled, infrequent)           | Once per N cycles; not every cycle.                    |
| dmesg overcurrent / enum failures  | `kmsg` via `/dev/kmsg` reader       | Surface as host-level issue.                           |

The polling deadline is `cycle_interval` (default 30 s in v2, down
from v1's 120 s, because the cycle is much cheaper now). If an event
arrives, the cycle runs immediately, then the timer resets.

## 9. Failure domains and what we do about them

| Failure                                      | Detection                                        | Daemon response                                                      |
| -------------------------------------------- | ------------------------------------------------ | -------------------------------------------------------------------- |
| `qmicli` not present                         | startup check                                    | Exit 1 with structured error.                                        |
| `qmicli` command times out                   | per-call timeout                                 | Marked as transient; one retry; on second failure, classify as `qmi/channel_hung`. |
| Zao log file missing or stale > 5 min        | inotify + age check                              | Log warning; fall back to QMI-direct probing for all lines; emit alert. |
| Zao log format change (RASCOW_STAT not found)| zero-match for ≥10 minutes                       | Log error; alert; fall back as above.                                |
| Daemon crashes                               | systemd                                          | `Restart=on-failure`; cycle resumes.                                 |
| State file corrupted                         | JSON load fails                                  | Backup to `<file>.corrupt-<ts>`; reset to defaults; log error; alert.|
| Disk full                                    | write fails                                      | Stop logging; daemon continues; status.json marks degraded.          |
| Webhook endpoint unreachable                 | request fails                                    | Drop, log, increment a counter; never block the cycle.               |
| qmi-proxy crashes                            | qmicli starts failing en-masse                   | Issue `driver_reset` (per the global gate).                          |

## 10. Configuration model

Layered from lowest precedence to highest:

1. Baked-in defaults (in code).
2. `/opt/spark-modem-watchdog/share/default-config.yaml` (shipped).
3. `/etc/spark-modem-watchdog/config.yaml` (site, single file).
4. `/etc/spark-modem-watchdog/conf.d/*.yaml` (drop-ins, sorted lex).
5. Environment variables (`SPARK_MODEM_*`).
6. Command-line flags.

A SIGHUP reloads (1)–(5); CLI flags are not reload-time. Reload is
hot for thresholds and webhook URLs; cycle interval and event source
choices require a restart.

Example `config.yaml`:

```yaml
schema_version: 1

cycle:
  interval_seconds: 30          # polling deadline; events shorten this
  startup_delay_seconds: 30      # let Zao boot

thresholds:
  signal:
    min_rsrp_dbm: -110
    min_rsrq_db: -15
    min_snr_db: 0
  backoff_seconds: 300
  global_driver_reset_backoff_seconds: 3600
  multi_modem_threshold_fraction: 0.75

ladders:
  registration:
    max_soft_resets: 3
    max_modem_resets: 2
    max_usb_resets: 1
  decay_after_healthy_cycles: 10

carriers:
  paths:
    - /opt/spark-modem-watchdog/share/carriers/il.yaml
  fallback_apn: internetg

zao:
  log_path: /var/log/zao-remote-endpoint.log
  infractrl_script: /usr/share/zao/InfraCtrl.script
  units:
    - zao-infra-ctrl.service
    - zao-remote-endpoint.service

alerts:
  webhook:
    url: https://noc.example.invalid/spark/alerts
    require_https: true
    transitions:
      - "healthy -> degraded"
      - "recovering -> exhausted"
      - "any -> rf_blocked"

logging:
  events_path: /var/log/spark-modem-watchdog/events.jsonl
  level: info
```

## 11. Cross-cutting concerns

### 11.1 Logging

- **Two outputs**: events JSONL (machine), systemd journal (human via
  `journalctl`).
- Every line is a `LogEvent` typed record (see SCHEMA).
- No `print`; everything via the `logging` framework.
- Levels: `debug`, `info`, `warn`, `error`. `info` is default.

### 11.2 Metrics

Exposed via `prometheus_client` over a Unix socket. The agent on the
box (Telegraf / node exporter / fleet agent) scrapes it and forwards
to NOC.

| Metric                                         | Type      | Labels                                  |
| ---------------------------------------------- | --------- | --------------------------------------- |
| `spark_modem_actions_total`                    | counter   | `kind`, `modem`, `result`               |
| `spark_modem_state`                            | gauge     | `modem`, `state` (one-hot per state)    |
| `spark_modem_signal_dbm`                       | gauge     | `modem`, `kind` (`rsrp`/`rsrq`/`rssi`)  |
| `spark_modem_signal_db`                        | gauge     | `modem`, `kind` (`snr`)                 |
| `spark_modem_cycle_duration_seconds`           | histogram | —                                       |
| `spark_modem_qmi_probe_duration_seconds`       | histogram | `modem`, `intent`                       |
| `spark_modem_zao_log_age_seconds`              | gauge     | —                                       |
| `spark_modem_daemon_uptime_seconds`            | counter   | —                                       |
| `spark_modem_active_lines`                     | gauge     | —                                       |
| `spark_modem_apn_writes_total`                 | counter   | `modem`, `result`                       |
| `spark_modem_webhook_total`                    | counter   | `result` (`sent`/`failed`)              |

### 11.3 Configuration validation

`config.yaml` is parsed via `pydantic`; loading is fail-closed. The
daemon refuses to start with an invalid config and prints the
validation errors as a single structured block.

### 11.4 Time

- All durations and backoffs use `time.monotonic()`. ADR-0007.
- `time.time()` is used **only** for ISO-8601 timestamps on log lines
  and event records, never for arithmetic.

## 12. Module seams (the testability story)

Every external IO is behind one of the following protocols (Python
`Protocol` types). Tests inject fakes; production wires the real
implementation.

```python
class QmiClient(Protocol):
    async def get_ids(self, dev: str) -> ModemIds: ...
    async def get_signal(self, dev: str) -> SignalReading | None: ...
    async def get_card_status(self, dev: str) -> CardStatus: ...
    # ... etc.

class SubprocessRunner(Protocol):
    async def run(self, argv: list[str], *, timeout: float, stdin: bytes | None = None) -> Completed: ...

class Clock(Protocol):
    def now_monotonic(self) -> float: ...
    def now_iso(self) -> str: ...

class ZaoLogTailer(Protocol):
    def latest(self) -> ZaoSnapshot | None: ...

class StateStore(Protocol):
    def load_modem(self, key: str) -> ModemState | None: ...
    def save_modem(self, key: str, state: ModemState) -> None: ...
    def load_globals(self) -> Globals: ...
    def save_globals(self, g: Globals) -> None: ...

class FileWriter(Protocol):
    def atomic_write(self, path: Path, payload: bytes) -> None: ...
```

The policy engine consumes a `Diag` and a `StateStore` and produces
`PlannedAction[]`. It calls **no** subprocesses, opens **no** files,
reads **no** environment. Pure function of inputs.

This is the single most important rule for testability. If you're
about to put `subprocess.run` in `policy/`, stop and put it behind
a protocol.

## 13. Public CLI surface

Single binary, subcommands. Output defaults to human; `--json` for
machine. Exit codes: 0 success, 1 generic failure, 2 usage error,
3 preflight failure (e.g. not root), 4 partial success (some modems
recovered, some didn't).

```
spark-modem diag [--json] [--quick] [--qmi-fixture-dir=PATH] [--device=cdc-wdmN]
spark-modem recovery [--diag-fixture=PATH | --from-stdin] [--dry-run] [--device=cdc-wdmN]
spark-modem provision [--dry-run] [--apn=NAME] [--device=cdc-wdmN] [--restart-zao]
spark-modem reset <line> {--soft|--modem|--usb}
spark-modem reset --all --driver
spark-modem status [--json]
spark-modem ctl install
spark-modem ctl uninstall [--purge]
spark-modem ctl edit-config
spark-modem ctl reset-state [--device=cdc-wdmN | --all]
spark-modem ctl support-bundle [--out=PATH]
spark-modem ctl version
```

The daemon itself is `spark-modem-watchdog` (no subcommand) and is
not normally run by hand.

## 14. Build, package, and release

- Source layout (`src/spark_modem_watchdog/`) is `policy/`,
  `observer/`, `actions/`, `state/`, `config/`, `cli/`, `daemon/`,
  `qmi/`, `zao/`, `metrics/`, `events/`, `wire/`.
- Tests live in `tests/` mirroring source layout, plus `tests/fixtures/`
  with recorded `qmicli` output and sample diag JSONs.
- Build outputs a `.deb` for `arm64` containing a self-contained venv
  under `/opt/spark-modem-watchdog/`, plus the systemd unit, default
  config, and `logrotate` snippet.
- CI publishes the `.deb` on tag push.
- Release version is semver. Breaking changes to the wire format
  require a `schema_version` bump and a major version bump.

## 15. Risks and open architectural questions

- **Q1**: `qmicli` text output stability. We rely on it; it has been
  stable across libqmi 1.x but is not a guaranteed contract. *Mitigation:*
  fixture-based parser tests; the `qmi` module is the only place that
  parses `qmicli` output.
- **Q2**: `inotify` on the Zao log can miss events if the file rotates.
  *Mitigation:* re-open on `IN_MOVE_SELF`/`IN_DELETE_SELF`; full re-read
  on rotation.
- **Q3**: `pyudev` requires a libudev that matches the system. We pin
  versions in the venv.
- **Q4**: Running asyncio under root with `subprocess` calls can leak
  FDs if not careful. *Mitigation:* explicit `close_fds=True` (default
  in Python 3) plus a periodic `lsof` self-check counter as a tripwire.
- **Q5**: The fleet has heterogeneous BSPs (R35.x). *Mitigation:* the
  daemon does not depend on Tegra-specific kernel features; only `qmi_wwan`
  generic interfaces.

See [PRD § 10](PRD.md#10-open-questions) for product-level questions.
