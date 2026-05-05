# spark-modem-watchdog v2 — Claude Code project guide

On-device daemon for a fleet of NVIDIA Jetson Orin NX boxes. Watches 4× Sierra
Wireless EM7421 LTE modems behind the Soliton Zao bonding stack; detects
unhealthy modems and applies the smallest recovery action that has a chance
of fixing it without making things worse. Python rewrite of an existing v1
bash toolchain.

## Workflow

This project uses **GSD** (`get-shit-done`) for planning and execution. Read
the `.planning/` directory before starting any non-trivial task.

| Artifact                 | What's in it                                                       |
|--------------------------|--------------------------------------------------------------------|
| `.planning/PROJECT.md`   | Core value, constraints, key decisions, open questions Q1..Q8     |
| `.planning/REQUIREMENTS.md` | 90 v1 REQ-IDs (FR-* + NFR-*); v2.1 deferred; out-of-scope     |
| `.planning/ROADMAP.md`   | 7 phases (4 build + 3 delivery); REQ traceability                  |
| `.planning/STATE.md`     | Current phase, last commit, next action                            |
| `.planning/research/`    | STACK / FEATURES / ARCHITECTURE / PITFALLS / SUMMARY              |
| `.planning/config.json`  | mode=yolo, granularity=standard, parallelization=true              |
| `docs/`                  | User-authored: PRD, ARCHITECTURE, RECOVERY_SPEC, SCHEMA, RUNBOOK,  |
|                          | TEST_STRATEGY, MIGRATION, GLOSSARY, ADRs 0001..0007                 |

**Always read `.planning/research/SUMMARY.md` before planning a phase** — it
captures the deltas between docs/ and current best practice (state-machine
refactor, HMAC v2.0, usb_path keying, cardinality-safe metrics, …).

## Commands

- **Status**: `/gsd-progress` — current phase, what's next
- **Plan a phase**: `/gsd-plan-phase N` — produces `.planning/phase-N/PLAN.md`
- **Execute**: `/gsd-execute-phase N` — wave-based parallel plans
- **Resume**: `/gsd-resume-work` — restore session context
- **Help**: `/gsd-help`

## Stack snapshot (from `.planning/research/STACK.md`)

- **Runtime**: CPython 3.12.x bundled in the `.deb` venv via `astral-sh/python-build-standalone` (closes PROJECT.md Q8). Target deployment is Ubuntu 20.04 / L4T R35.6.4 / aarch64. The Jetson's system Python (3.8.10) is **not** used.
- **Async**: stdlib `asyncio` — `TaskGroup` + `asyncio.timeout` (not `gather`+`wait_for`).
- **Wire types**: `pydantic >=2.13,<3` for every JSON shape (Diag, ModemState, status, events, webhook, identity, globals, carrier table).
- **Subprocess**: `asyncio.subprocess` only; **list-form argv always**; never shell strings; one wrapper module (`subproc/`) — `grep -r 'create_subprocess_exec' src/` outside `subproc/` must be empty.
- **Event sources**: `pyudev >=0.24.4` (USB add/remove via `add_reader(monitor.fileno())`, **not** `MonitorObserver`); `pyroute2 >=0.9.6` `AsyncIPRoute` (rtnetlink link-state); `asyncinotify >=4.0.10` (Zao log + `/dev/kmsg` rotation).
- **Webhooks**: `httpx >=0.27,<1` async client; HMAC-SHA256 signing in v2.0 (header `X-Spark-Signature: sha256=<hex>` over raw body bytes; `X-Spark-Timestamp` for replay protection).
- **systemd**: `Type=notify` via `sdnotify >=0.3.2` (pure-Python; not `systemd-python`); `LoadCredential=` for HMAC secret.
- **Metrics**: `prometheus-client >=0.25` over Unix socket. **Integer-encoded `modem_state_value{modem}`** — never one-hot `state` label (cardinality-safe; ADR-0013).
- **Packaging**: custom debhelper rule + `uv pip install -r requirements.lock` against the bundled venv (drop `dh-virtualenv`).
- **Dev**: `mypy --strict`, `ruff check`, `ruff format --check` (drop `black`); `pytest`, `pytest-asyncio` (`mode=auto`), `hypothesis`.

## Critical invariants (skim before any non-trivial change)

1. **Policy engine is a pure function** — `Diag × {ModemState, Globals, Config, Clock} → PlannedAction[]`. No subprocess, no I/O, no env reads. If you're about to import anything that touches the kernel from `policy/`, stop and put it behind a `Protocol`.
2. **Per-modem state files are keyed by `usb_path`**, not `cdc-wdmN`. ADR-0009. `state/by-usb/<usb_path>.json`. cdc-wdmN renumbering must not corrupt state.
3. **State machine: 5 top-level + 2 orthogonal flags.** `unknown` / `healthy` / `degraded` / `recovering(level)` / `exhausted` plus `present: bool` and `rf_blocked: bool`. ADR-0008. Status output composes them.
4. **All durations and backoffs use `time.monotonic()`.** `time.time()` only for ISO-8601 stamps. ADR-0007.
5. **Atomic file writes** — temp + rename + directory fsync. Never partial-write a state file.
6. **Zao `RASCOW_STAT` is authoritative for "is this line bonding"** — never QMI-probe a Zao-active line. ADR-0003.
7. **Counter decay**: `_healthy_streak` is persisted every cycle and reloaded on daemon start; mid-streak restart does **not** reset progress. ADR-0006 amendment.
8. **Cycle write order is atomic**: streak update → decay check → counter reset → state-write is one atomic write per cycle. RECOVERY_SPEC § 8.
9. **One action per modem per cycle**, priority `config > sim > datapath > registration > qmi`.
10. **Signal-quality gate** on `modem_reset` and `usb_reset` only; cheap actions still run during `rf_blocked`.
11. **No inbound IPC in v2.0** — no HTTP, no DBus, no domain socket. Prometheus UDS is one-way scrape only.
12. **CLI mutating commands take the same `flock`s the daemon does** (state-store + per-modem). Daemon and CLI never produce a lost update.

## Anti-patterns (Phase 0 temptations to avoid)

`subprocess.run` sync; `gather(return_exceptions=True)` for probes; `MonitorObserver`; cdc-wdmN-keyed state; single state-store lock; `signal.signal` from asyncio; subprocess/httpx in `policy/`; UDS RPC for `ctl status`; `urllib.request` for webhooks; missing directory `fsync`; blocking read on `/dev/kmsg`; best-effort event-log swallowing exceptions; hot-reload of event-source paths; `run_in_executor` to "speed up" qmicli; `if/elif` instead of `match` on `ModemState`; `state` as one-hot Prometheus label.

## Out of scope (don't add without explicit go-ahead)

Cloud control plane, GUI/web UI, multi-vendor modem support, replacing
`qmicli`, multi-SIM/eSIM, owning Zao, migration of v1 state files,
hot-plug-of-modems-mid-flight as a v2.0 priority, retroactive re-decision on
past cycles, predictive ML on signal trends, auto-firmware-update of EM7421,
cross-box coordination, HTTP API on UDS in v2.0.

## Hardware target

- NVIDIA Jetson Orin NX (16 GB) on P3768 reference carrier
- 4× Sierra EM7421 (VID:PID `1199:9091`) on USB 3 hub at `2-3.1.{1..4}`
- JetPack 5.1.5 / L4T R35.6.4 / Ubuntu 20.04 / aarch64 / kernel 5.10-tegra
- Soliton Zao SDK 2.1.0+ (`ZaoInfraCtrl` + `ZaoRemoteEndpointCloud`)
- `ModemManager` MUST remain disabled (Zao requires exclusive access)

## Success metrics (PRD § 8)

| ID  | Target                                                       |
|-----|--------------------------------------------------------------|
| M1  | ≥99.5 % per-modem availability over rolling 7 days           |
| M2  | Median MTTR ≤60 s (SIM) / ≤90 s (registration) / ≤180 s (QMI-hung) |
| M3  | False-positive destructive resets ≤5 %                       |
| M4  | Zero `Exhausted` states caused by counter accumulation       |
| M5  | P99 cycle duration ≤10 s                                     |
| M6  | Zero OOM/unhandled-exception daemon restarts in 30 days      |
| M7  | Dev-laptop test suite ≤30 s                                  |
