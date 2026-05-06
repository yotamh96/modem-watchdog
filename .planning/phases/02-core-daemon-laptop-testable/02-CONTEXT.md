# Phase 2: Core Daemon (laptop-testable) - Context

**Gathered:** 2026-05-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 2 ships a complete asyncio daemon that runs end-to-end on a developer
laptop using fixtures only. By exit:

1. Replaying ≥1000 synthesized v1 cycles via `spark-modem recovery
   --diag-fixture=<dir>` produces planned actions that **agree** with v1's
   historical actions on healthy cycles and produce **equal-or-safer** choices
   on fault cycles (partial order on action cost + skip-as-safest;
   pytest-gated at ≥95 % fault-cycle agreement).
2. The `spark-modem` CLI runs hardware-free on a developer laptop:
   `diag --qmi-fixture-dir=` returns a typed `Diag` snapshot in <1 s;
   `recovery --diag-fixture=` returns a ranked `PlannedAction[]`;
   `--explain` surfaces the decision rationale; `ctl history`,
   `ctl maintenance`, `ctl support-bundle` are wired.
3. P99 cycle ≤10 s on fixture replay (NFR-1 / M5); RSS ≤80 MiB with the
   psutil tripwire wired at 200 MiB (NFR-3); per-modem QMI probes execute
   concurrently via `asyncio.TaskGroup` with per-task `asyncio.timeout(8s)`;
   a deliberately-thrown policy exception is logged and the cycle continues.
4. The Prometheus UDS endpoint at `/run/spark-modem-watchdog/metrics.sock`
   responds to `curl --unix-socket` with valid Prom text containing
   `actions_total{kind,modem,result}`, `signal_dbm{modem,kind}`,
   `cycle_duration_seconds`, integer-encoded `modem_state_value{modem}`
   (NOT one-hot), `state_duration_seconds{modem,state}` histogram with
   buckets `[1, 5, 15, 60, 300, 1800, 7200, 86400]`, `cycle_drift_seconds`
   gauge, `webhook_delivery_total{result}`.
5. Webhook delivery on `Healthy → Degraded` and `Recovering → Exhausted`
   transitions emits a typed payload with `X-Spark-Signature: sha256=<hex>`
   over raw body bytes, `X-Spark-Timestamp` header, in-memory retry queue
   (3 attempts + exp backoff 1s/4s/16s), per-`(modem, transition)` 60 s
   coalescing, daemon-restart events with reason enum, `action_failed`
   variant, pre-exit best-effort send (3 s drain budget) — all running in
   a separate task with explicit httpx timeouts and pre-resolved cached DNS.
6. `_healthy_streak` persisted every cycle and reloaded on daemon start;
   streak update + decay check + counter reset + state-write happen as
   one atomic write per cycle (RECOVERY_SPEC §8 ordering); replay harness
   includes a daemon-restart-mid-streak case.

**Carried forward from Phase 1 (locked, do not re-discuss):**

- Pure-function policy engine: `Diag × State × Globals × Config × Clock →
  PlannedAction[]`. No subprocess, no I/O, no env reads (CLAUDE.md §1).
- TaskGroup + per-task `asyncio.timeout` (no `gather + wait_for`).
- 5+2 ModemState shape (ADR-0008); `usb_path` keying (ADR-0009);
  integer-encoded `modem_state_value{modem}` (ADR-0013).
- HMAC-SHA256 v2.0 + `X-Spark-Timestamp` (ADR-0011); webhook payload
  variants frozen in `wire/webhook.py` (HealthyToDegraded,
  RecoveringToExhausted, DaemonRestart, ActionFailedWebhook).
- Per-modem `asyncio.Lock` + globals lock + flocks (ADR-0012; already wired
  into `state_store/`).
- "All errors are data" subprocess model (Phase 1 SP-02);
  `extra='forbid'` on wire models, `extra='ignore'` on qmicli parsers.
- 60 s default `(modem, transition)` dedup window (research SUMMARY M-2).

</domain>

<decisions>
## Implementation Decisions

### R. Replay harness & v1 agreement gate (SC #1)

- **R-01: Synthesized cycle source.** The ≥1000 cycles are generated from
  RECOVERY_SPEC §4 decision-table rows + the top-15 PITFALLS scenarios + a
  randomized fault generator. Hardware-free, deterministic, ships as
  fixtures in `tests/fixtures/replay/`. Pairs with TEST_STRATEGY.md §4
  spec-as-tests philosophy. Live-fleet capture is deferred to Phase 5
  (bench/field shadow).
- **R-02: "equal-or-safer" partial order.** Action cost order:
  `no_action ≺ set_apn ≺ fix_raw_ip ≺ sim_power_on ≺ soft_reset ≺
  modem_reset ≺ usb_reset ≺ driver_reset`. v2 is OK if its action ≤ v1's;
  v2 is NOT OK if v1 chose cheaper-but-sufficient and v2 chose more
  destructive. Per-cycle classification:
  `agree | safer | less-safe | different-issue | both-skip`. Each fixture
  carries `{prior_state, diag, expected_v1_actions, fault_cycle: bool,
  v1_succeeded: bool|null}`; `v1_succeeded` enables the SC #1 clause "no
  cheap action where v1 succeeded with destructive."
- **R-03: pytest gate + JSON summary.** `tests/replay/test_v1_agreement.py`
  is the CI gate. Per-cycle results are xfail-tolerant; the aggregate hard
  fails at <95 % fault-cycle agreement. Emits `artifacts/replay-summary.json`
  with per-fixture verdicts + counts. Lives inside the existing pytest
  pipeline; counts toward the M7 ≤30 s budget if cycles are kept
  fixture-light (target: 1000 fixture cycles → ≤5 s total via parametrize +
  asyncio fast loop).
- **R-04: Trace layout.** `tests/fixtures/replay/<scenario>/<NNN>.json`,
  one cycle per file, mirroring `tests/fixtures/diag/`. Easy to diff, easy
  to add a single cycle by hand. Hypothesis can additionally generate
  cycles in-memory for property tests, but the literal ≥1000 must be on
  disk and audited.

### C. CLI surface & operability (SC #2)

- **C-01: `ctl maintenance` scope = destructive only.** Cycles, observation,
  status writes, metrics, webhooks all continue. Only `modem_reset` /
  `usb_reset` / `driver_reset` (Phase 4) are gated when maintenance is
  active. Cheap actions (`set_apn`, `fix_raw_ip`, `sim_power_on`,
  `soft_reset`, `set_operating_mode`, `fix_autosuspend`) still run because
  they're idempotent and ≤5 s outage. A `maintenance_active` gate emits
  `gate_failed` for any destructive action attempted during the window.
- **C-02: Maintenance window in `globals.json`, dual-clock expiry.**
  Field shape:
  `{maintenance: {active, scope: "destructive", started_iso,
  started_monotonic, expires_iso, expires_monotonic, max_duration_seconds:
  28800}}`. Cycle driver checks **both** clocks each cycle and uses
  `min(now_monotonic >= expires_monotonic, now_wall >= expires_iso)` so
  NTP step on the Jetson can neither prematurely expire nor extend the
  window (ADR-0007 spirit). Daemon restart preserves the window via
  `globals.json` reload; if expired during downtime, log
  `maintenance_expired_during_downtime` event on next cycle. `ctl
  maintenance on --duration` is mandatory; `--duration > 8h` hard rejects
  at the CLI before any state mutation.
- **C-03: `ctl history` reads events.jsonl + rotated siblings.** Parses
  pydantic events; filters by modem `usb_path` (canonical) or `device`
  (alias). No separate transitions log — events.jsonl is the single source
  of truth (FR-40, atomic appends). Works against laptop fixtures: just
  point at a fixture events.jsonl. Matches RUNBOOK.md §"replay events.jsonl".
- **C-04: `ctl support-bundle` is a redacted tarball.**
  Output: `/var/lib/spark-modem-watchdog/support-bundles/sparkmd-<host>-<iso>.tar.gz`
  (override via `--out=PATH`). Mode `0640 root:adm`. Contents:
  - last 200 events from `events.jsonl` (replay-able)
  - all `state/by-usb/*.json`
  - current `globals.json` (with maintenance window if active)
  - current `status.json`
  - last 24 h of webhook delivery rows (result, status code, URL with
    path stripped to host-only)
  - `journalctl -u spark-modem-watchdog --since=24h --no-pager`
  - `dmesg --time-format=iso`
  - `/etc/spark-modem-watchdog/conf.d/` excluding the `hmac-secret`
    credential file
  - `qmicli --version`, daemon version, python version,
    `carrier_table_sha256`

  Redactions:
  - **ICCID / IMSI** → `<redacted:<sha256[:8]>>` so identity correlation is
    preserved across the bundle without exporting PII
  - **HMAC secret** never copied (not even path)
  - **Webhook URL** → host-only

  Print absolute path of the bundle on success.

### M. Phase 2 module decomposition & build-order

- **M-01: Inventory via `InventorySource` Protocol.** Production impl is
  `SysfsInventory` walking `/sys/bus/usb/devices/` for VID:PID `1199:9091`,
  deriving `(line, cdc_wdm, usb_path, ns, iface)`. Test impl is
  `FixtureInventory` reading `tests/fixtures/inventory/<scenario>.json`.
  Phase 2 calls `scan()` at startup + once per cycle (cheap; sysfs is
  local). Phase 3 swaps in `UdevInventory` (event-driven via
  `pyudev.Monitor` + `add_reader(monitor.fileno())`) behind the same
  Protocol — **no caller changes**. Hardware-free Phase 2 unit tests use
  FixtureInventory; integration tests on Linux use SysfsInventory against a
  temp sysfs tree.
- **M-02: Cycle scheduling = 30 s monotonic timer + event-queue stub.**
  Cycle scheduler:
  `await asyncio.wait({sleep_until(next_deadline_monotonic),
  event_queue.get()}, return_when=FIRST_COMPLETED)`. Phase 2 ships only
  the sleep arm; Phase 3 wires udev/rtnetlink/inotify producers into
  `event_queue`. The queue plumbing exists in Phase 2 as a no-op stub —
  not dead code: test fixtures push synthetic events through it for cycle
  driver tests. `cycle_drift_seconds = now_monotonic -
  expected_next_cycle_monotonic`, computed at wake-up boundary BEFORE
  the cycle runs. Cycle overrun (>30 s wallclock): log `cycle_overran`
  event and start the next cycle immediately (no queueing, no skip).
- **M-03: Plan slicing = 8–10 plans aligned to module boundaries.**
  Each plan ends with the module green under `mypy --strict` + its layer
  of tests passing. Provisional slicing (planner may rebalance):

  | Plan | Module |
  |------|--------|
  | 02-01 | cycle driver scaffold + main entry (`spark_modem.daemon.main`) |
  | 02-02 | `qmi/parsers/` (per-libqmi-version fixtures) + `qmi/wrapper.py` (`--device-open-proxy` always) |
  | 02-03 | `zao_log/parser.py` (RASCOW_STAT-only; inotify lands Phase 3) |
  | 02-04 | `observer/` (TaskGroup probe orchestrator) + `inventory/sysfs.py` + `InventorySource` Protocol |
  | 02-05 | `policy/` (state transitions + decision table + gates; pure function) |
  | 02-06 | `actions/` cheap actions (one file per action + dispatcher) |
  | 02-07 | `status_reporter/status.py` (status.json) + `status_reporter/prom.py` (Prom UDS) |
  | 02-08 | `webhook/` poster (HMAC + retry + dedup + DNS resolver) |
  | 02-09 | `cli/` (`spark-modem` subcommands: `diag`, `recovery`, `provision`, `reset`, `status`, `ctl`) |
  | 02-10 | replay harness: synth fault-scenario generator + `tests/replay/test_v1_agreement.py` + `artifacts/replay-summary.json` |

  Final plan count is the planner's call (`/gsd-plan-phase 2`); 8–10 is
  the target band.
- **M-04: `actions/` = one file per action + shared dispatcher.**
  `actions/{set_apn.py, fix_raw_ip.py, sim_power_on.py, soft_reset.py,
  set_operating_mode.py, fix_autosuspend.py}`, each exposing
  `async def execute(modem, ctx) -> ActionResult` plus a small `verify()`
  for post-action read-back. `actions/__init__.py` has a dispatcher
  mapping `ActionKind → callable`. CLI's `spark-modem recovery
  --action=set_apn` and the cycle driver both go through the dispatcher
  (FR-25 "runnable individually via CLI"). Phase 4 adds destructive actions
  as new files behind the same shape — no dispatcher churn.

### W. Webhook poster + DNS strategy

- **W-01: In-memory ring buffer + pre-exit best-effort flush.**
  Bounded `asyncio.Queue` (default 100 items). Each item carries
  `(envelope, attempts_left, next_retry_monotonic)`. 3 attempts, exp
  backoff `[1s, 4s, 16s]`. On retry-budget exhaustion: increment
  `webhook_delivery_total{result="dropped"}` and write a `webhook_dropped`
  event. On SIGTERM (Phase 3 wires this), `webhook_drain_seconds` (default
  3 s, bounded by the 5 s graceful-shutdown budget) gives the daemon a
  one-shot "we tried" send for queued items — not retries. Crash means the
  in-memory queue is lost; the events.jsonl `webhook_pending` markers
  enable post-mortem reconstruction.
- **W-02: DNS pre-resolved at config-load + 60 s refresh + go-stale on
  failure.** On daemon start and on SIGHUP config reload, run
  `loop.getaddrinfo(host)` and cache resolved IP(s) with a monotonic
  expires_at. A background task refreshes every 60 s. httpx is constructed
  with `transport=AsyncHTTPTransport(retries=0)`. Cached IP is injected via
  the `Host` header trick (URL becomes `https://<cached_ip>/...` with
  `Host: <original_host>`); TLS SNI uses the original host. On resolve
  failure, log `webhook_dns_resolve_failed`, increment counter, keep using
  the previous "stale" result up to `webhook_dns_stale_max_seconds`
  (default 600 s); after that, mark webhooks as `no_dns` and skip until
  next successful resolve. Pure asyncio; resolver never blocks the loop.

### O. status.json + Prometheus surface

- **O-01: status.json written every cycle, atomic.** Written at the end
  of every cycle (after policy + actions, before sleep). Atomic
  temp+rename+dir-fsync via `state_store` helpers (already wired Phase 1).
  Carries `last_modified` (ISO-8601 wall) + `cycle_index` (monotonic int)
  so consumers detect a stuck daemon. fsync cost dominated by per-modem
  state writes that already happen every cycle — marginal cost negligible
  vs M5's 10 s P99 budget.
- **O-02: state_duration_seconds buckets = `[1, 5, 15, 60, 300, 1800,
  7200, 86400]`.** Targets MTTR semantics: 1 s (cheap action), 5 s (SIM
  cycle), 15 s (modem reset early), 60 s (M2 SIM target), 300 s (5 min —
  SIM-app stuck), 1800 s (30 min), 7200 s (2 h), 86400 s (24 h — stuck
  unhealthy detection). +Inf is implicit. Cardinality stays bounded at
  16 series per box (4 modems × 5 states).
- **O-03: cycle_drift_seconds = signed gauge.**
  `now_monotonic - expected_next_cycle_monotonic`, recorded at wake-up
  boundary BEFORE cycle work begins. Negative would only happen if
  monotonic moved backward — clamp to 0 (defensive). Drift is mostly noise
  in Phase 2 (pure 30 s timer; bounded by asyncio scheduler jitter); it
  becomes the load-bearing signal in Phase 3 once event-driven wakeups
  land.
- **O-04: webhook_delivery_total{result} enum.** Result values:
  `sent | failed | dropped | coalesced | skipped_no_url | skipped_no_dns`.
  Each enumerates a distinct outcome; cardinality bounded.

### Claude's Discretion

The user accepted the recommended option in every question across all four
areas — total alignment with research SUMMARY's prescriptions. The
following surfaces are explicitly delegated to Claude during planning:

- **`--explain` output format.** Default: human-readable text summary
  printed to stdout (per-modem decision rationale, gates passed/failed,
  selected action, cause issue). `--json` flag emits structured form
  alongside (single object per cycle to stdout, `PlannedAction` list with
  full decision metadata). Both formats stable across releases.
- **Plan ordering / dependency graph.** Within the 8–10 plans, the
  planner decides wave parallelization (PROJECT.md `parallelization=true`).
  Suggested topology: 02-02 (qmi/parsers) ‖ 02-03 (zao_log) → 02-04
  (observer) ‖ 02-05 (policy) → 02-06 (actions) → 02-07 (status+Prom)
  ‖ 02-08 (webhook) → 02-09 (CLI) → 02-10 (replay).
- **Test seam Protocol locations.** Co-located with implementations
  (`subproc/runner.py` defines the `Runner` Protocol used by callers;
  `webhook/poster.py` defines `WebhookPoster`). Fakes live in
  `tests/fakes/` (`FakeRunner`, `FakeClock`, `FakeWebhookPoster`,
  `FakeInventorySource`, `FixtureInventory`) — single import surface.
- **qmicli per-libqmi fixture layout.**
  `tests/fixtures/qmicli/<intent>/<libqmi-version>/<scenario>.txt` (e.g.
  `tests/fixtures/qmicli/get_signal/1.30/lte_strong.txt`). Parser is
  version-aware via a header line in each fixture; CI runs parsers
  against all versions. New libqmi point release = new directory + new
  fixtures, no parser code change unless the format genuinely drifted.
- **Histogram bucket selection for `cycle_duration_seconds`.** Buckets
  `[0.5, 1, 2, 4, 8, 16, 32]` targeting M5's 10 s budget with two-sided
  visibility (early-side: catch sub-second outliers; late-side: catch
  budget breaches before P99 alerts fire).
- **psutil RSS tripwire policy.** When RSS > 200 MiB, emit
  `rss_tripwire_breached` event + increment `daemon_self_health{kind="rss"}`
  counter. Do NOT graceful-exit in Phase 2 — Phase 3's sd_notify watchdog
  owns restart. Phase 2 wires the metric and the event so downstream
  alerting can be tested against fixtures.
- **maintenance.lock acquisition.** No new lock surface. The mutating
  CLI command (`ctl maintenance on/off`) acquires the existing
  state-store flock (`/run/spark-modem-watchdog/state.lock`) before
  reading + updating `globals.json`. Keeps the lock hierarchy at three
  levels (asyncio.Lock + per-modem flock + state-store flock + PID lock,
  per ADR-0012).

### Folded Todos

None — the cross_reference_todos step found no pending todos relevant to
Phase 2.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor) MUST read these before
planning or implementing Phase 2.** Every entry is a full relative path so
the file can be read directly.

### Phase boundary, requirements, prior decisions

- `.planning/ROADMAP.md` §"Phase 2: Core Daemon (laptop-testable)" — goal,
  requirements list, six success criteria.
- `.planning/REQUIREMENTS.md` §Traceability — the FR + NFR Phase-2-mapped
  entries (FR-2, FR-10..FR-13, FR-20..FR-22, FR-25, FR-25.1, FR-26..FR-28,
  FR-30..FR-33, FR-40..FR-42, FR-44, FR-44.3..FR-44.8, FR-50..FR-52,
  FR-70, FR-71, FR-74; NFR-1..NFR-5, NFR-10, NFR-11, NFR-20..NFR-22.1,
  NFR-42).
- `.planning/PROJECT.md` §"Active" requirements + §"Key Decisions" — the
  v2.0 commitments this phase delivers.
- `.planning/phases/01-foundations-adrs/01-CONTEXT.md` — Phase 1 decisions
  this phase builds on (W-01..W-04, B-01..B-04, S-01..S-04, SP-01..SP-04).
- `CLAUDE.md` §"Critical invariants" + §"Anti-patterns" — non-negotiable
  rules.

### Recovery semantics (R-01..R-04, M-04)

- `docs/RECOVERY_SPEC.md` §3 (per-modem state machine), §3.3 (counter
  decay; load via ADR-0006 amendment), §4 (issue → action decision table —
  every row is a fixture per spec-as-tests), §5 (priority ordering), §6
  (gates: signal / backoff / cross-action / driver-reset / disconnected /
  exhausted), §7 (`PlannedAction` record), §8 (cycle algorithm — atomic
  ordering), §9 (idempotency), §10 (worked examples — 10.1, 10.2 are
  fixture seeds).
- `docs/adr/0008-state-machine-5-plus-2.md` — 5+2 shape (supersedes 0005).
- `docs/adr/0006-counter-decay.md` — atomic streak update + decay + reset
  + state-write per cycle.
- `.planning/research/PITFALLS.md` §15.1 — fault-cycle weighting (NOT
  aggregate ≥99%); top-15 fault scenarios feed the synthesizer.

### Test strategy + replay harness (R-01..R-04)

- `docs/TEST_STRATEGY.md` §2 (test layers), §3 (fixture library), §4
  (spec-as-tests pattern — `tests/test_recovery_spec.py`), §5 (property
  tests), §8 (conventions: FakeClock, FakeSubprocessRunner).
- `.planning/research/PITFALLS.md` §9.1, §9.2 (`_healthy_streak`
  persistence + decay race — replay must include daemon-restart-mid-streak
  case).

### CLI surface, support-bundle, maintenance (C-01..C-04)

- `docs/PRD.md` FR-50..FR-52, FR-50.1 (`--qmi-fixture-dir=PATH`), FR-50.2
  (`--diag-fixture=PATH`), FR-25 ("runnable individually via CLI").
- `docs/RUNBOOK.md` — operator-facing context: `ctl support-bundle` use
  case, PII handling, post-mortem workflow.
- `docs/SCHEMA.md` §4 (status.json shape — needs `cycle_index`, `last_modified`
  fields added), §5 (events.jsonl shape — `ctl history` reads this),
  §7 (globals.json shape — needs `maintenance` field added per C-02),
  §10 (versioning policy).
- `.planning/research/FEATURES.md` M-9 (`ctl history`), M-10 (maintenance
  mode — 8 h max + auto-expiry + mandatory `--duration`), M-22
  (support-bundle 24 h webhook deliveries).
- `.planning/research/PITFALLS.md` §16.2 (maintenance-mode-without-auto-expiry
  is a critical operational pitfall).

### Cycle, observer, policy, inventory (M-01..M-04)

- `docs/ARCHITECTURE.md` §1 (system context), §4 (component architecture
  — module decomposition is normative; do not split or merge), §4.1
  (module responsibilities), §4.2 (cycle hot loop), §4.3 (concurrency:
  TaskGroup + per-task timeout per ARCH Q2; per-modem `asyncio.Lock` per
  ARCH Q3), §6 (inventory keying — `usb_path`-canonical), §7 (state
  store), §12 (test seams — protocols).
- `.planning/research/ARCHITECTURE.md` Q2 (TaskGroup + asyncio.timeout),
  Q3 (per-modem locks), Q9 (Prom-over-UDS), Q14 (usb_path keying).
- `docs/adr/0012-concurrency-locks.md` — 3-layer locking model (already
  wired in `state_store/`).
- `docs/adr/0009-state-files-keyed-by-usb-path.md` — file naming + cross-
  check on startup.

### qmicli wrapper + parsers (M-03 plan 02-02)

- `docs/ARCHITECTURE.md` §5 — qmicli is the contract; never replaced.
- `.planning/research/STACK.md` §4.2 — `create_subprocess_exec`,
  `start_new_session=True`, two-stage shutdown, `proc.communicate(timeout=)`.
- `.planning/research/PITFALLS.md` §1.1 (qmi-proxy crash → driver_reset
  short-circuit per RECOVERY §6.4), §1.2 (output drift across libqmi
  1.30→1.32+ → per-version fixtures + `extra='ignore'`), §1.3
  (`LC_ALL=C` already enforced by SP-03), §1.4 (SIGPIPE / mid-call
  cancellation — `_in_critical_section=True` flag), §1.5
  (`--device-open-proxy` always; never direct mode).

### Webhook + DNS (W-01..W-02)

- `docs/adr/0011-webhook-subsystem.md` — HMAC v2.0, retry/dedup queue,
  pre-resolved DNS.
- `src/spark_modem/wire/webhook.py` — `HealthyToDegraded`,
  `RecoveringToExhausted`, `DaemonRestart`, `ActionFailedWebhook`, plus
  `WebhookEnvelope` (already shipped Phase 1).
- `.planning/research/PITFALLS.md` §10.1 (DNS blocking the loop — Host-
  header trick), §10.2 (retry without dedup → alert fatigue), §10.4
  (header injection — payload is pydantic-validated, not free-form),
  §10.5 (HMAC misuse — sign over raw body bytes, not parsed JSON).
- `.planning/research/FEATURES.md` §4.3 (HMAC v2.0 cost/benefit), M-1..M-4
  (retry, dedup, restart event, X-Spark-Timestamp).

### Status.json + Prometheus surface (O-01..O-04)

- `docs/adr/0013-metric-surface.md` — integer-encoded
  `modem_state_value{modem}`; cardinality-bounded label set.
- `docs/SCHEMA.md` §4 — status.json normative shape.
- `.planning/research/PITFALLS.md` §13.1 (cardinality explosion), §9.4
  (state one-hot anti-pattern).
- `.planning/research/ARCHITECTURE.md` Q9 — Prom-over-UDS via
  `make_wsgi_app` + custom UDS server in `asyncio.to_thread`.
- `docs/PRD.md` NFR-21 — Prom metric list (amended for ADR-0013).

### Migration / rollout context

- `docs/MIGRATION.md` — Phase 5 (bench/field shadow) consumes the replay
  artifacts produced this phase.
- `.planning/research/PITFALLS.md` §15.1 — fault-cycle weighting is the
  Phase 5 exit gate; the synthesized harness here is the Phase 2 gate.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (from Phase 1)

- `src/spark_modem/wire/` — every wire model is in place:
  `BaseWire` (frozen, extra='forbid'), `ModemState` (5+2 + healthy_streak +
  counters + last_action_monotonic), `Diag`, `PlannedAction`, `Identity`,
  `Globals`, `CarrierTable`, `webhook.{HealthyToDegraded,
  RecoveringToExhausted, DaemonRestart, ActionFailedWebhook,
  WebhookEnvelope}`, `events.*`. Phase 2 consumes these as-is.
- `src/spark_modem/state_store/` — `StateStore` exposes
  `save_modem_state`, `load_modem_state`, `save_globals`, `load_globals`,
  `cross_check_inventory_for(usb_paths)`, atomic temp+rename+fsync,
  3-layer locks (asyncio.Lock + per-modem flock + state-store flock).
  Public/private split (`save_*` vs `_save_*_locked`) avoids re-entry.
  Maintenance window addition (C-02) extends the existing `Globals` model.
- `src/spark_modem/subproc/runner.py` — `async def run(argv, *, timeout_s,
  stdin, env)`. SP-03 invariants: list-form argv, `LC_ALL=C/LANG=C`,
  `start_new_session=True`, two-stage SIGTERM→2s→SIGKILL→drain via
  `asyncio.timeout()`. Returns `CompletedProcess(timed_out: bool, ...)` —
  "all errors are data" (SP-02). qmi/wrapper.py and actions/* call this.
- `src/spark_modem/clock/clock.py` — `Clock.now_monotonic()`,
  `Clock.now_iso()`. ADR-0007 separation. Tests use `FakeClock`.
- `src/spark_modem/config/settings.py` — pydantic v2 BaseSettings with
  reload_marker (`Field(json_schema_extra={"reload": "restart"|"hot"})`)
  + YAML merger. Phase 2 adds webhook URL, hmac secret credential path
  reference, maintenance defaults.
- `src/spark_modem/event_logger/writer.py` — `O_APPEND` JSONL writer,
  newline-terminated atomic `os.write()`. `ctl history` reads this; the
  webhook poster writes `webhook_pending`/`webhook_sent`/`webhook_dropped`
  events through it.

### Established Patterns

- All wire JSON via pydantic v2 `model_dump_json` / `model_validate_json`.
  No `json.loads` of untyped dicts in production code (boundary discipline).
- `asyncio` everywhere. No `subprocess.run` sync. No `gather + wait_for`.
  No `MonitorObserver`. No `signal.signal` from asyncio.
- `mypy --strict` + `ruff check` + `ruff format --check` green per module.
- `scripts/lint_no_subprocess.sh` (SP-04) fails CI on
  `create_subprocess_exec`/`subprocess.*`/`os.system` outside `subproc/`.
- Tests: `pytest` + `pytest-asyncio` (`mode=auto`) + `hypothesis`.
  `tmp_path` for filesystem; `FakeClock` for time. No global state.
- Windows dev-host friendliness: `flock` is no-op via
  `AsyncFlockHandle(fd=-1)` sentinel; POSIX-only test files marked
  `skipif(win32)`. Production target is Linux/aarch64; dev hosts include
  Windows.

### Integration Points

Phase 2 introduces these new package paths under `src/spark_modem/`:

| Path | Owns |
|------|------|
| `qmi/wrapper.py` | qmicli invocation (`--device-open-proxy` always); `_in_critical_section` flag |
| `qmi/parsers/<intent>.py` | per-intent text→typed-record parsers (`extra='ignore'` boundary) |
| `zao_log/parser.py` | `RASCOW_STAT` → `ZaoSnapshot` (no inotify in Phase 2 — file-read fallback) |
| `inventory/sysfs.py` | `SysfsInventory` impl of `InventorySource` Protocol |
| `inventory/protocol.py` | `InventorySource` Protocol definition |
| `observer/` | TaskGroup probe orchestrator; per-modem `asyncio.timeout(8s)` |
| `policy/` | Pure-function engine: `transitions.py` + `decision_table.py` + `gates.py` + `engine.py` |
| `actions/` | One file per cheap action + `dispatcher.py` + shared `verify.py` |
| `status_reporter/status.py` | status.json writer (every cycle, atomic) |
| `status_reporter/prom.py` | Prom UDS exporter via `make_wsgi_app` + custom UDS server |
| `webhook/poster.py` | HMAC + retry queue + dedup + DNS resolver |
| `webhook/dns.py` | Async pre-resolve cache (60 s refresh + go-stale) |
| `cli/` | `spark-modem` entry + subcommands (`diag`, `recovery`, `provision`, `reset`, `status`, `ctl`) |
| `daemon/main.py` | Cycle driver scaffold + main entry |

Test seams:

| Path | Owns |
|------|------|
| `tests/fakes/runner.py` | `FakeRunner` mapping argv → canned `CompletedProcess` |
| `tests/fakes/clock.py` | `FakeClock` (asyncio-compatible, deterministic) |
| `tests/fakes/webhook.py` | `FakeWebhookPoster` recording sent envelopes |
| `tests/fakes/inventory.py` | `FixtureInventory` reading JSON fixtures |
| `tests/fakes/dns.py` | `FakeDNSResolver` returning canned IPs |
| `tests/fixtures/qmicli/<intent>/<libqmi-version>/*.txt` | per-version qmicli outputs |
| `tests/fixtures/zao_log/*.log` | RASCOW_STAT scenarios |
| `tests/fixtures/inventory/<scenario>.json` | sysfs inventory snapshots |
| `tests/fixtures/diag/*.json` | full Diag snapshots (consumed by replay harness) |
| `tests/fixtures/replay/<scenario>/<NNN>.json` | ≥1000 synthesized cycles |
| `tests/replay/test_v1_agreement.py` | The pytest gate (≥95 % fault-cycle agreement) |

### Lint / quality gates extended in Phase 2

- `mypy --strict` extends to all new modules above.
- `ruff check` + `ruff format --check` extend.
- New gate: `tools/check_spec.py` walks `RECOVERY_SPEC.md` §4 rows and
  asserts each is referenced by ≥1 test (TEST_STRATEGY §6).
- New gate: `tests/replay/test_v1_agreement.py` ≥95 % fault-cycle.
- Existing gate: `scripts/lint_no_subprocess.sh` continues to enforce no
  `create_subprocess_exec` outside `subproc/`. New code (qmi/wrapper.py,
  webhook/poster.py) calls into `subproc.run` — does not bypass.

</code_context>

<specifics>
## Specific Ideas

The user accepted the recommended option in every question across all four
selected areas — total alignment with research SUMMARY's prescriptions and
the spirit of Phase 1's locked decisions. Concrete specifics worth pinning:

- **Replay agreement is partial-order, not strict.** The CI gate is "≥95 %
  fault-cycle agreement" where each fixture cycle is classified as one of
  `agree | safer | less-safe | different-issue | both-skip`. `safer`
  counts as agreement. `less-safe` is the only failure mode. The
  classification IS the audit trail — every divergence is named, not
  silently masked.
- **Maintenance mode is dual-clock.** `min(now_monotonic >=
  expires_monotonic, now_wall >= expires_iso)` — neither NTP step nor a
  monotonic-only path can extend or prematurely expire the window. The
  8 h maximum is enforced at the CLI before any state mutation; the daemon
  trusts what it reads from `globals.json` but logs out-of-spec values it
  finds (defensive: a hand-edited globals.json with a 24 h window must
  not silently work).
- **support-bundle redaction is one-way and consistent.** ICCID/IMSI are
  hashed to `<redacted:<sha256[:8]>>` so a single bundle preserves
  identity-correlation across files (state, events, status all hash the
  same value to the same redacted form). This is non-reversible — support
  cannot un-hash, but they don't need to. HMAC secret is never copied.
  Webhook URL is host-only.
- **Phase 2 inventory is sysfs-pull, not udev-push.** The
  `InventorySource` Protocol is the seam. Phase 2 production code uses
  `SysfsInventory.scan()` once per cycle. Phase 3 swaps in `UdevInventory`
  driving the same Protocol — but additionally pushes events to the cycle
  driver's `event_queue` to wake out-of-band. The Phase 2 cycle driver
  already plumbs `event_queue` (no-op Phase 2; tests push synthetic
  events through it).
- **Cycle scheduling is poll-only in Phase 2 by design.** Drift is
  measured but mostly noise. The `cycle_drift_seconds` gauge becomes the
  load-bearing scheduling-health signal once Phase 3 wires real event
  sources.
- **status.json is written every cycle.** Predictable freshness for NOC
  consumers; `cycle_index` + `last_modified` let consumers detect a stuck
  daemon. `fsync` cost is dominated by per-modem state writes (already
  every cycle); marginal.
- **Webhook retry is in-memory only.** Pre-exit best-effort flush of 3 s
  is bounded by the 5 s graceful-shutdown budget Phase 3 will wire. Crash
  loses queued items; `webhook_pending` events.jsonl markers enable
  post-mortem reconstruction. NOC is informed: webhooks are best-effort.
- **DNS uses Host-header trick.** Cached IP injected via URL
  (`https://<ip>/...`) with `Host: <hostname>` header; TLS SNI uses the
  hostname. httpx supports this cleanly. No blocking resolver path.
- **Plans expose dispatchers, not stringly-typed switches.** Both the
  CLI and the cycle driver hit `actions.dispatcher.execute(action_kind,
  modem, ctx)`. Adding Phase 4's destructive actions is purely
  data-driven: register the new file → no switch statement to update.
- **Replay harness lives in pytest.** No new tooling, no new entrypoint.
  `pytest tests/replay/` is the gate; `artifacts/replay-summary.json` is
  the audit artifact. Stays inside the M7 ≤30 s budget by parametrize +
  fast asyncio loop.

</specifics>

<deferred>
## Deferred Ideas

Items mentioned during discussion or surfaced during analysis that belong
outside Phase 2 scope. None lost.

### Phase 3 (Linux Event Sources & Lifecycle)

- `pyudev.Monitor.from_netlink()` + `loop.add_reader(monitor.fileno())`
  for USB add/remove (FR-1, NFR-13). The `InventorySource` Protocol M-01
  gets a `UdevInventory` impl behind the same surface; cycle driver's
  `event_queue` from M-02 is wired here.
- `pyroute2.AsyncIPRoute` for rtnetlink link-state.
- `asyncinotify` for Zao log + `events.jsonl` rotation watcher (FR-43.1).
- `/dev/kmsg` non-blocking reader for dmesg (FR-14).
- `sd_notify` `READY=1` + `STATUS=` + optional `WatchdogSec=90s` (FR-75).
- `loop.add_signal_handler` SIGTERM (graceful shutdown ≤5 s; W-01's
  3 s drain budget lives here) + SIGHUP (transactional config reload;
  W-02's DNS re-resolve fires here).
- PID-lock at `/run/spark-modem-watchdog/lock`.
- Real callers of the per-modem flocks + state-store flock that Phase 1
  set up.

### Phase 4 (Destructive Actions & HIL)

- `soft_reset` is cheap and ships in Phase 2 (cheap action set), but
  **destructive** actions (`modem_reset`, `usb_reset`, `driver_reset`)
  land in Phase 4 with the signal-quality gate end-to-end.
- The `maintenance_active` gate added in C-01 must reject destructive
  actions when active; Phase 2 ships the gate predicate, Phase 4 wires
  it into destructive paths.
- HIL fault-injection lane (`tests/hil/`).

### Phase 5 (Bench & Field Shadow)

- **Capture-from-production v1 logger.** Optional Phase 5 tool that
  augments the Phase 2 synthesized fixtures with ≥1000 real-fleet cycles
  during the bench/field shadow weeks. The Phase 2 gate stays
  synthesized-only; Phase 5 widens the gate to real captures.
- `tools/compare_v1_v2.py` hourly HTML report (the heavier-weight version
  of Phase 2's pytest gate). Same partial-order classification, but
  emits per-scenario tables and tracks fleet-wide trends.

### Tactical / Claude-discretion (handled during planning)

- `--explain` output format details — text by default, `--json` for
  structured output.
- Plan ordering / dependency graph within the 8–10 plans.
- Test seam Protocol locations (co-located with implementations; fakes
  in `tests/fakes/`).
- qmicli per-libqmi fixture layout
  (`tests/fixtures/qmicli/<intent>/<libqmi-version>/<scenario>.txt`).
- `cycle_duration_seconds` histogram bucket selection (`[0.5, 1, 2, 4,
  8, 16, 32]`).
- psutil RSS tripwire as event-only in Phase 2 (graceful-exit owned by
  Phase 3 sd_notify watchdog).
- maintenance.lock acquisition reuses state-store flock (no new lock
  surface).

### v2.1 (already deferred in REQUIREMENTS.md)

- HTTP API on Unix socket (CTL-01, CTL-02).
- Webhook batching (WHK-01, M-3).
- `ctl identity export/import` for RMA box swap (CARR-01).
- `ctl schema events` JSON-Schema export (SCH-01, M-14).
- `ctl simulate-issue` (SIM-01, M-24).
- 5G NR-aware policy (NR-01).

</deferred>

---

*Phase: 02-core-daemon-laptop-testable*
*Context gathered: 2026-05-06*
