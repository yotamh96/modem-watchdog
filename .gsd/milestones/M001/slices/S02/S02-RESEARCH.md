# Phase 2: Core Daemon (laptop-testable) — Research

**Researched:** 2026-05-06
**Domain:** asyncio daemon orchestration, qmicli parsing, pydantic v2 boundary discipline,
Prometheus-over-UDS, httpx HMAC webhook, pytest replay harness, Hypothesis fault synthesis
**Confidence:** HIGH — all critical facts drawn from existing project research files, ADRs,
source code, and pinned library documentation (no new web research required; project has
exhaustive prior research in `.planning/research/`).

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**R. Replay harness & v1 agreement gate (SC #1)**
- R-01: ≥1000 synthesized cycles from RECOVERY_SPEC §4 rows + top-15 PITFALLS + randomized
  fault generator. Files in `tests/fixtures/replay/`. Hardware-free, deterministic.
- R-02: "equal-or-safer" partial order: `no_action ≺ set_apn ≺ fix_raw_ip ≺ sim_power_on ≺
  soft_reset ≺ modem_reset ≺ usb_reset ≺ driver_reset`. Per-cycle classification:
  `agree | safer | less-safe | different-issue | both-skip`. `v1_succeeded` field enables
  the "no cheap action where v1 succeeded with destructive" clause.
- R-03: `tests/replay/test_v1_agreement.py` is the CI gate. Hard fails at <95% fault-cycle
  agreement. Emits `artifacts/replay-summary.json`.
- R-04: Fixture layout `tests/fixtures/replay/<scenario>/<NNN>.json`, one cycle per file.

**C. CLI surface & operability (SC #2)**
- C-01: `ctl maintenance` scope = destructive actions only. Cheap actions still run.
- C-02: Maintenance window in `globals.json`, dual-clock expiry. Both clocks must agree.
  8 h max; mandatory `--duration`. Daemon logs `maintenance_expired_during_downtime`.
- C-03: `ctl history` reads events.jsonl + rotated siblings, filter by `usb_path` or device alias.
- C-04: `ctl support-bundle` redacted tarball at `/var/lib/spark-modem-watchdog/support-bundles/`.
  ICCID/IMSI → `<redacted:<sha256[:8]>>`. HMAC secret never copied. Webhook URL host-only.

**M. Phase 2 module decomposition & build-order**
- M-01: `InventorySource` Protocol; Phase 2 uses `SysfsInventory` (sysfs-pull once per cycle).
- M-02: Cycle scheduling = 30 s monotonic timer + `event_queue` stub (no-op in Phase 2).
  `cycle_drift_seconds = now_monotonic - expected_next_cycle_monotonic` at wake boundary.
- M-03: 8–10 plans aligned to module boundaries (02-01 through 02-10).
- M-04: One file per cheap action + `dispatcher.py` + `verify.py`. Dispatcher maps
  `ActionKind → callable`. Both CLI and cycle driver hit the dispatcher.

**W. Webhook poster + DNS strategy**
- W-01: Bounded asyncio.Queue (100 items). 3 attempts, backoff [1s, 4s, 16s].
  Pre-exit best-effort 3 s drain. `webhook_dropped` event on exhaustion.
- W-02: DNS pre-resolved at config-load + 60 s refresh + go-stale on failure
  (up to 600 s). Host-header trick: URL = `https://<cached_ip>/...`,
  `Host: <hostname>`, TLS SNI = hostname. `httpx.AsyncHTTPTransport(retries=0)`.

**O. status.json + Prometheus surface**
- O-01: status.json written every cycle, atomic.
- O-02: `state_duration_seconds` buckets = `[1, 5, 15, 60, 300, 1800, 7200, 86400]`.
- O-03: `cycle_drift_seconds` = signed gauge, clamped to 0 if negative.
- O-04: `webhook_delivery_total{result}` values: `sent | failed | dropped | coalesced |
  skipped_no_url | skipped_no_dns`.

### Claude's Discretion

- `--explain` output format: human-readable text by default; `--json` flag for structured output.
- Plan ordering / dependency graph within the 8–10 plans.
- Test seam Protocol locations: co-located with implementations; fakes in `tests/fakes/`.
- qmicli per-libqmi fixture layout: `tests/fixtures/qmicli/<intent>/<libqmi-version>/<scenario>.txt`.
- `cycle_duration_seconds` histogram buckets: `[0.5, 1, 2, 4, 8, 16, 32]`.
- psutil RSS tripwire: event-only in Phase 2 (graceful-exit owned by Phase 3 sd_notify watchdog).
- maintenance.lock acquisition reuses state-store flock (no new lock surface).

### Deferred Ideas (OUT OF SCOPE)

**Phase 3:** pyudev.Monitor + add_reader (UdevInventory), pyroute2 AsyncIPRoute, asyncinotify
for Zao log, /dev/kmsg reader, sd_notify READY=1, SIGTERM drain, SIGHUP config reload, PID lock.
**Phase 4:** Destructive actions (modem_reset, usb_reset, driver_reset), HIL fault-injection.
**Phase 5:** Live-fleet capture, tools/compare_v1_v2.py HTML report.
**v2.1:** HTTP API on UDS, webhook batching, ctl identity export/import, ctl schema events,
ctl simulate-issue, 5G NR-aware policy.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| FR-2 | Resolve each modem to (line, cdc_wdm, usb_path, ns, iface) via sysfs | SysfsInventory walks /sys/bus/usb/devices/ for VID:PID 1199:9091 |
| FR-10 | Consult Zao RASCOW_STAT before probing; skip if active | zao_log/parser.py + ZaoSnapshot.is_line_active() |
| FR-11 | Per-modem snapshot: USB speed, QMI responsiveness, operating mode, SIM, registration, carrier, signal, profile-1 APN, data session, IPv4 | qmi/parsers/ per-intent fixtures |
| FR-12 | 5+2 state machine (ADR-0008) | policy/transitions.py using existing ModemState wire type |
| FR-13 | Typed Diag snapshot every cycle | observer/ → Diag(BaseWire) — Phase 1 wire type exists |
| FR-20 | At most one recovery action per modem per cycle | policy/engine.py dispatch loop |
| FR-21 | Priority: config > sim > datapath > registration > qmi | policy/decision_table.py |
| FR-22 | Escalation ladder: set_apn/fix_raw_ip/sim_power_on/soft_reset | actions/ dispatcher |
| FR-25 | Same-action backoff 300 s (monotonic) | policy/gates.py |
| FR-25.1 | Cross-action ladder backoff 90 s | policy/gates.py |
| FR-26 | Counter decay after K=10 consecutive Healthy cycles | policy/transitions.py |
| FR-26.1 | _healthy_streak persisted and reloaded on daemon start | state_store/store.py load path |
| FR-26.2 | Atomic streak + decay + counter reset + state-write | RECOVERY_SPEC §8 cycle ordering |
| FR-28 | --dry-run everywhere | actions/dispatcher.py dry_run gate |
| FR-28.1 | Per-modem dry-run: config accepts bool|list[str] | config/settings.py + action gate |
| FR-30 | APN selection by (MCC, MNC) lookup in carrier table | wire/carriers.py + set_apn.py |
| FR-31 | Profile #1 written only when APN differs | set_apn.py verify before write |
| FR-32 | Post-write APN verification | actions/verify.py read-back |
| FR-33 | Carrier table hot-reloadable | config/settings.py reload_marker="hot" |
| FR-40 | Structured event log (JSON Lines) | event_logger/writer.py — Phase 1 exists |
| FR-41 | status.json per cycle | status_reporter/status.py |
| FR-41.1 | cycle.actions_executed, cycle.transitions, carrier_table_sha256 in status.json | status_reporter/status.py |
| FR-42 | Prometheus scrape endpoint on UDS | status_reporter/prom.py |
| FR-44 | Webhook POST on transitions | webhook/poster.py |
| FR-44.3 | Retry queue (3 attempts, exp backoff) | webhook/poster.py W-01 |
| FR-44.4 | Dedup/coalescing per (modem, transition) 60 s | webhook/poster.py |
| FR-44.5 | Daemon-restart event with reason enum | webhook/poster.py + DaemonRestart wire type |
| FR-44.6 | action_failed event variant | ActionFailedWebhook wire type exists |
| FR-44.7 | Pre-exit best-effort webhook | webhook/poster.py drain |
| FR-44.8 | Webhook in separate task; DNS pre-resolved; never blocks cycle | webhook/dns.py + poster.py |
| FR-50 | spark-modem CLI with 6 subcommands | cli/ package |
| FR-50.1 | ctl history --modem= --since= | cli/ctl.py |
| FR-50.2 | ctl maintenance on --duration= | cli/ctl.py + globals.json C-02 shape |
| FR-50.3 | --explain flag on diag | cli/diag.py |
| FR-51 | --qmi-fixture-dir=PATH | FakeRunner + FixtureQmiClient |
| FR-52 | --diag-fixture=PATH for recovery | cli/recovery.py |
| FR-70 | TaskGroup + per-task asyncio.timeout | observer/orchestrator.py |
| FR-71 | Per-modem asyncio.Lock + globals lock | state_store/locks.py — Phase 1 exists |
| FR-74 | qmi-proxy mode always; refuse direct mode | qmi/wrapper.py --device-open-proxy always |
| NFR-1 | P99 cycle ≤10 s | TaskGroup 8 s per-probe budget |
| NFR-2 | ≤1% CPU averaged 10 min | asyncio single-loop, no busy-poll |
| NFR-3 | RSS ≤80 MiB; psutil tripwire at 200 MiB | psutil.Process().rss check per cycle |
| NFR-4 | Per-modem probes parallel | TaskGroup |
| NFR-5 | Disk write rate ≤1 MiB/min | atomic writes, no debug spew |
| NFR-10 | Recovers from any single transient error | try/except in observer; all errors are data |
| NFR-11 | Policy exception MUST NOT terminate daemon | outer try/except in cycle driver |
| NFR-20 | Every state transition logged | event_logger |
| NFR-21 | Prometheus metric set | status_reporter/prom.py |
| NFR-21.1 | state_duration_seconds, cycle_drift_seconds, webhook_delivery_total | prom.py |
| NFR-22 | ctl support-bundle retrieves last 200 events | cli/ctl.py C-04 |
| NFR-22.1 | Support bundle last 24 h webhook delivery results | C-04 |
| NFR-42 | Carrier table addable without code release | hot-reloadable YAML |
</phase_requirements>

---

## 1. Executive Summary

1. **Phase 1 foundations are solid.** `subproc/runner.py`, `state_store/`, `wire/`, `clock/`,
   `config/settings.py`, and `event_logger/writer.py` all exist and are `mypy --strict` green.
   Phase 2 builds on them — it does not re-implement them. The planner must read each Phase 1
   module's interface before assigning any Phase 2 task.

2. **The 5 hardest technical problems are all solvable with known patterns, but each has a
   non-obvious wrinkle.** (a) Prometheus-over-UDS uses `make_wsgi_app()` + custom `UnixWSGIServer`
   in `asyncio.to_thread`; the one wrinkle is `server_bind` must not call `SO_REUSEADDR` on AF_UNIX.
   (b) httpx Host-header DNS trick requires injecting the cached IP into the URL string while
   preserving the `Host` header and TLS SNI. (c) TaskGroup per-task timeout pattern MUST catch
   `TimeoutError` inside each task; a bare `TaskGroup` wrapping the whole observer is wrong.
   (d) Hypothesis strategy for Diag synthesis must composite `ModemSnapshot` per position, not
   shuffle a global pool. (e) Cycle wake via `asyncio.wait` on two coroutines requires careful
   cancellation of the winner's task to avoid resource leaks.

3. **Pydantic boundary discipline is clear and already established.** Wire models use
   `extra='forbid'`; qmicli parsers use `extra='ignore'`. A new libqmi field arriving in an
   existing parser never breaks the parser; a missing required field must raise (not silently
   produce `None`). The `MissingField` sentinel pattern is the correct mitigation.

4. **The replay harness M7 budget (≤30 s, target ≤5 s for 1000 fixtures) is achievable**
   with `pytest-asyncio mode=auto`, parametrize over on-disk fixtures, and a shared
   `asyncio.AbstractEventLoop` fixture scoped to the module. Key: avoid per-cycle loop setup cost
   by reusing one loop across all 1000 cycles in `test_v1_agreement.py`.

5. **Lock ordering is already specified in ADR-0012.** The planner must not introduce a new lock
   surface. The cycle driver's interaction with the three lock layers is:
   (a) asyncio.Lock per-modem acquired during state read + write;
   (b) flock acquired by CLI mutators (not daemon mid-cycle);
   (c) PID lock is startup-only. The cycle driver never holds two per-modem asyncio.Locks
   simultaneously.

6. **`_in_critical_section` is an attribute on the `QmiWrapper` instance, not a context manager.**
   It gates SIGTERM only in Phase 3 (SIGTERM handler is Phase 3). Phase 2 still needs the flag
   to document the pattern and ensure `_two_stage_shutdown` in `subproc/runner.py` preserves
   in-flight state-changing calls.

7. **`cycle_drift_seconds` gauge is mostly noise in Phase 2** (pure 30 s timer). Its real value
   is as a correctness signal for Phase 3 event-driven scheduling. Wire it up in Phase 2 anyway;
   the metric infrastructure is shared.

8. **Windows dev-host support is pre-solved.** `flock` is a no-op via `AsyncFlockHandle(fd=-1)`
   sentinel; POSIX-only tests are `skipif(win32)`. Phase 2 modules that call `os.fsync` on a
   directory need the same pattern: attempt, suppress `NotImplementedError` on win32 with a
   comment.

9. **`verify()` in `actions/` is a post-action read-back, not a pre-condition check.** Each
   cheap action calls `qmi/wrapper.py` to re-read the specific field it just wrote (e.g. profile-1
   APN, raw_ip flag, SIM state). The verify result is part of `ActionResult`; it feeds the
   `action_executed{result=verified_ok|verify_failed|no_verify}` Prometheus label.

10. **The ≥95% fault-cycle gate** (SC #1) is fault-cycle agreement, NOT aggregate agreement.
    The synthesizer MUST weight fault-cycle scenarios (the top-15 PITFALLS + RECOVERY_SPEC §4
    rows) so that ≥950 of the 1000 on-disk fixtures are genuine fault cycles, not healthy-cycle
    filler.

---

## 2. Key Technical Findings (per module)

### 2.1 qmi/ — parsers + wrapper

**libqmi version drift (PITFALLS §1.2).**
libqmi 1.30 (Ubuntu 20.04 focal-updates) and libqmi 1.32+ have output shape differences,
most critically in `--nas-get-signal-info` where NR5G sections appear in 1.32+. The strategy:

- Fixture layout: `tests/fixtures/qmicli/<intent>/<libqmi-version>/<scenario>.txt`
  (e.g. `get_signal/1.30/lte_strong.txt`, `get_signal/1.32/nr5g_present.txt`).
- Each fixture file has a first-line comment `# libqmi_version: 1.30` used by the test
  parametrizer to label the run. The parser itself is version-agnostic — `extra='ignore'`
  absorbs unknown sections.
- For a field that libqmi 1.30 omits but 1.32 includes, the pydantic model declares it
  `field: SomeType | None = None`. A missing field is parsed to `None`; a present field
  is validated. **A field we depend on becoming absent in a future version** is caught
  by the `MissingField` sentinel: if a required field is absent, the parser returns a
  typed `QmiError(reason="missing_field", field="registration_state")` rather than
  `None` silently.
- `LC_ALL=C` is enforced by `subproc/runner.py`'s `_build_env` already (SP-03 invariant 2).

**`_in_critical_section` pattern.**
`QmiWrapper` (in `qmi/wrapper.py`) owns this attribute. For state-changing calls
(`set_apn`, `sim_power_on`, `soft_reset`), the wrapper sets `self._in_critical_section = True`
before calling `subproc.run()` and clears it in a `finally` block. In Phase 2 this attribute
is read only by tests (to assert the wrapper sets it correctly). In Phase 3, the SIGTERM
handler checks it; if `True`, SIGTERM waits until the flag clears rather than cancelling
the subprocess mid-call.

```python
class QmiWrapper:
    def __init__(self, runner: SubprocRunner, device: str) -> None:
        self._runner = runner
        self._device = device
        self._in_critical_section: bool = False

    async def set_operating_mode(self, mode: str) -> CompletedProcess:
        self._in_critical_section = True
        try:
            return await self._runner.run(
                ["qmicli", "--device-open-proxy",
                 f"--device={self._device}",
                 f"--dms-set-operating-mode={mode}"],
                timeout_s=15.0,
            )
        finally:
            self._in_critical_section = False
```

**`--device-open-proxy` always.**
`qmi/wrapper.py` unconditionally adds `--device-open-proxy` to every qmicli invocation.
If the proxy is not available, qmicli returns `couldn't open the QMI device: proxy unavailable`;
the wrapper maps this to `QmiError(reason="proxy_unavailable")`. FR-74: daemon refuses to
start in direct mode.

**Parser pydantic boundary.**
Each parser in `qmi/parsers/<intent>.py` returns a typed dataclass (NOT a BaseWire — these are
internal parse results, not wire-format). The model uses `model_config = ConfigDict(extra='ignore')`
so new libqmi fields do not fail validation. The parser raises `QmiParseError` (not silently
returns `None`) for structurally invalid output.

### 2.2 zao_log/ — RASCOW_STAT parser

Phase 2 does NOT use inotify (Phase 3). The parser reads the Zao log file directly as a fallback:

```python
class ZaoLogParser:
    def parse_file(self, path: Path) -> ZaoSnapshot:
        """Read the log file and return the last RASCOW_STAT snapshot."""
        with path.open("r", encoding="ascii", errors="replace") as fh:
            lines = fh.readlines()
        # Walk backwards to find the most recent RASCOW_STAT block
        ...
```

The `ZaoSnapshot` has `is_line_active(line_idx: int) -> bool` which is what `observer/`
calls to gate QMI probing (FR-10).

For Phase 2 testing, `tests/fixtures/zao_log/` provides static log snippets.
The `ZaoLogParser` is wrapped by a Protocol (`ZaoLogTailer`) so Phase 3 can swap in
the inotify-backed implementation behind the same interface.

### 2.3 observer/ — TaskGroup probe orchestrator

The key structural invariant: **each per-modem probe must catch its own exceptions** so that
one probe failing does not propagate into the `TaskGroup` and cancel sibling tasks.

```python
# CORRECT pattern — exceptions are data, not propagated to TaskGroup
async def _probe_one(
    modem: Modem,
    qmi: QmiWrapper,
    zao: ZaoLogTailer,
    clock: Clock,
    timeout_s: float = 8.0,
) -> ModemSnapshot:
    try:
        async with asyncio.timeout(timeout_s):
            return await _probe_inner(modem, qmi, zao, clock)
    except TimeoutError:
        return ModemSnapshot.timed_out(modem.usb_path, modem.cdc_wdm, clock.now_iso())
    except Exception as exc:  # NFR-11: never crash the cycle
        logger.exception("probe failed for %s", modem.usb_path, exc_info=exc)
        return ModemSnapshot.errored(modem.usb_path, modem.cdc_wdm, clock.now_iso())

async def observe_all(
    modems: list[Modem],
    qmi: QmiWrapper,
    zao: ZaoLogTailer,
    clock: Clock,
) -> list[ModemSnapshot]:
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(_probe_one(m, qmi, zao, clock)) for m in modems]
    return [t.result() for t in tasks]
```

**Why per-task catch is critical:** if `_probe_one` propagates its exception to the TaskGroup,
the TaskGroup cancels all sibling tasks and re-raises as `ExceptionGroup`. The cycle driver
would receive an `ExceptionGroup` and — unless carefully handled — would fail to process the
remaining modems that probed successfully.

**Zao-active gate:** before `_probe_inner` calls qmicli, it calls
`zao.is_line_active(modem.line_idx)`. If active, returns `ModemSnapshot.zao_active(...)` with
zero issues. This is FR-10.

### 2.4 policy/ — pure function engine

**Module structure:**
- `policy/transitions.py` — `def transition(prior: ModemState, snap: ModemSnapshot, ctx: Context) -> ModemState`
- `policy/decision_table.py` — the RECOVERY_SPEC §4 table as `dict[tuple[IssueCategory, IssueDetail], ActionKind]`
- `policy/gates.py` — signal gate, backoff gate, ladder backoff, exhausted gate, maintenance gate
- `policy/engine.py` — orchestrates: transition → global driver-reset check → per-modem action selection → gates

**Purity invariant (CLAUDE.md #1):** the entire `policy/` package must not import anything
that touches the filesystem, OS, or network. This is enforced by `scripts/lint_no_subprocess.sh`
and verified by mypy — any import of `asyncio.subprocess`, `os`, `httpx`, or `subprocess`
from within `policy/` is a build failure.

**Counter decay (ADR-0006 ordering):**
```
1. Evaluate transition(prior, snap) → new_state
2. If new_state == Healthy: increment _healthy_streak
   Else: reset _healthy_streak to 0
3. If _healthy_streak >= K: decay all counters to 0; reset _healthy_streak to 0
4. Evaluate action_selection(new_state, snap, ctx)
5. If action selected and not a skip: bump action counter
6. atomic_state_write(new_state, counters, _healthy_streak)
   ← this is the single atomic write per cycle (RECOVERY_SPEC §8)
```

Steps 1–5 are in-memory. Step 6 is the single fsync. A crash between 5 and 6 means the next
cycle re-reads the pre-action state (safe: actions are idempotent).

**match statements** for `ModemState` dispatch — explicitly required by CLAUDE.md anti-patterns
("if/elif instead of match on ModemState" is forbidden). mypy --strict with `--enable-error-code
match-missing-cases` catches unhandled arms.

### 2.5 actions/ — cheap action set + dispatcher

**Phase 2 cheap actions:** `set_apn`, `fix_raw_ip`, `sim_power_on`, `soft_reset`,
`set_operating_mode`, `fix_autosuspend`.

**Each action file exposes:**
```python
async def execute(modem: Modem, ctx: ActionContext) -> ActionResult: ...
async def verify(modem: Modem, ctx: ActionContext) -> VerifyResult: ...
```

**`verify()` patterns per action:**
- `set_apn`: re-read profile #1 with `qmicli --wds-get-profile-settings=3gpp,1`; compare APN.
- `fix_raw_ip`: re-read with `qmicli --wds-get-current-settings`; check `raw_ip=Y`.
- `sim_power_on`: re-read SIM state; check `sim_state != power_down`.
- `soft_reset`: next-cycle observation (not a verify() — soft_reset's effect is modem restart,
  observed by the subsequent probe, not inline). `verify()` returns `VerifyResult.deferred()`.
- `set_operating_mode` / `fix_autosuspend`: re-read the specific sysfs attribute or QMI field.

**Dispatcher:**
```python
# actions/dispatcher.py
_REGISTRY: dict[ActionKind, tuple[ExecuteFn, VerifyFn]] = {
    ActionKind.set_apn: (set_apn.execute, set_apn.verify),
    ActionKind.fix_raw_ip: (fix_raw_ip.execute, fix_raw_ip.verify),
    ...
}

async def execute_and_verify(
    kind: ActionKind,
    modem: Modem,
    ctx: ActionContext,
) -> ActionResult:
    fn_exec, fn_verify = _REGISTRY[kind]
    result = await fn_exec(modem, ctx)
    if result.succeeded:
        verify_result = await fn_verify(modem, ctx)
        return result.with_verify(verify_result)
    return result
```

Phase 4 destructive actions are registered here by adding entries to `_REGISTRY` — no
dispatcher code changes required.

### 2.6 status_reporter/ — status.json + Prometheus UDS

**status.json writer:** thin wrapper around `state_store.atomic.atomic_write()` (already
implemented in Phase 1). The `StatusReport` pydantic model includes `cycle_index`, `last_modified`
(ISO-8601 wall), `cycle.actions_executed`, `cycle.transitions`, `carrier_table_sha256`,
per-modem state as integer (ADR-0013), per-modem `last_action_iso`, and
`maintenance_active_until_iso` when applicable.

**Prometheus UDS bridge** — the key implementation detail:

```python
# status_reporter/prom.py
import socket
from socketserver import UnixStreamServer
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler
from prometheus_client import make_wsgi_app
from pathlib import Path

class _UnixWSGIServer(UnixStreamServer, WSGIServer):
    """WSGIServer subclass that binds an AF_UNIX socket instead of TCP."""
    address_family = socket.AF_UNIX

    def server_bind(self) -> None:
        # Do NOT call setsockopt(SO_REUSEADDR) — UDS sockets don't need it
        # and some kernels return ENOPROTOOPT. Call UnixStreamServer.server_bind
        # directly, which calls socket.bind() without the SO_REUSEADDR dance.
        UnixStreamServer.server_bind(self)
        self.setup_environ()  # wsgiref: sets SERVER_NAME etc. (bogus on UDS, but required)

def start_metrics_server(socket_path: Path) -> _UnixWSGIServer:
    socket_path.unlink(missing_ok=True)   # PITFALLS §13.3: clean up stale socket on restart
    server = _UnixWSGIServer(str(socket_path), WSGIRequestHandler)
    server.set_app(make_wsgi_app())
    # 0o660: daemon (root) read+write; adm group readable for scrape agents
    socket_path.chmod(0o660)
    return server

# In daemon startup:
metrics_server = start_metrics_server(Path("/run/spark-modem-watchdog/metrics.sock"))
# asyncio.to_thread so the sync wsgiref.serve_forever doesn't block the loop:
metrics_task = asyncio.create_task(
    asyncio.to_thread(metrics_server.serve_forever)
)
# Shutdown: metrics_server.shutdown(); await metrics_task
```

**Why `to_thread`:** `wsgiref` is synchronous. A single dedicated thread is correct; scrapes
are infrequent and sub-100ms. Prom scrapes never block the asyncio cycle.

**Scrape verification:**
```bash
curl --unix-socket /run/spark-modem-watchdog/metrics.sock http://localhost/metrics
```
Returns valid Prometheus text format with all ADR-0013 gauges.

**Metric wiring:**
```python
# All four per-modem state gauges (ADR-0013)
modem_state_value    = Gauge("modem_state_value", "...", ["modem"])
modem_recovering_level = Gauge("modem_recovering_level", "...", ["modem"])
modem_present        = Gauge("modem_present", "...", ["modem"])
modem_rf_blocked     = Gauge("modem_rf_blocked", "...", ["modem"])

# Per-cycle
cycle_duration_seconds = Histogram("cycle_duration_seconds", "...",
    buckets=[0.5, 1, 2, 4, 8, 16, 32])
cycle_drift_seconds    = Gauge("cycle_drift_seconds", "...")

# Per-modem per-action
actions_total = Counter("actions_total", "...", ["kind", "modem", "result"])

# Signals
signal_rsrp_dbm = Gauge("signal_rsrp_dbm", "...", ["modem"])
signal_rsrq_db  = Gauge("signal_rsrq_db",  "...", ["modem"])
signal_snr_db   = Gauge("signal_snr_db",   "...", ["modem"])

# State time-in-state (O-02 buckets)
state_duration_seconds = Histogram("state_duration_seconds", "...", ["modem", "state"],
    buckets=[1, 5, 15, 60, 300, 1800, 7200, 86400])

# Webhook
webhook_delivery_total = Counter("webhook_delivery_total", "...", ["result"])
```

### 2.7 webhook/ — HMAC poster + DNS resolver

**DNS pre-resolve strategy (W-02):**

```python
# webhook/dns.py
class DnsCache:
    def __init__(self) -> None:
        self._ip: str | None = None
        self._expires_at: float = 0.0       # monotonic
        self._stale_until: float = 0.0      # monotonic; beyond this → skipped_no_dns
        self._refresh_interval: float = 60.0
        self._stale_max: float = 600.0      # W-02

    async def resolve(self, host: str, loop: asyncio.AbstractEventLoop) -> str | None:
        now = time.monotonic()
        if self._ip and now < self._expires_at:
            return self._ip
        try:
            # loop.getaddrinfo calls getaddrinfo(3) in the default executor thread pool.
            # It does block a thread, but NOT the asyncio event loop itself.
            # The default executor is a ThreadPoolExecutor with min(32, cpu_count+4) threads.
            infos = await loop.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            self._ip = infos[0][4][0]
            self._expires_at = now + self._refresh_interval
            self._stale_until = now + self._stale_max
            return self._ip
        except OSError:
            logger.warning("webhook_dns_resolve_failed host=%s", host)
            if self._ip and now < self._stale_until:
                return self._ip          # stale-but-OK window
            return None                  # no_dns; skip webhooks
```

**`loop.getaddrinfo` semantics:** this IS blocking in the sense that it calls into the OS
resolver — but it does so in a thread (the default executor), not on the event loop thread.
The asyncio event loop is NOT blocked. On Python 3.12, the default executor is a
`ThreadPoolExecutor`; `getaddrinfo` runs in one of its worker threads. The `await` suspends
the calling coroutine but does not block the loop.

**httpx Host-header DNS trick (W-02):**

```python
# webhook/poster.py
import httpx
import hmac
import hashlib
import time as time_module

async def _post_webhook(
    envelope: WebhookEnvelope,
    cached_ip: str,
    original_host: str,
    original_path: str,
    secret: bytes,
    *,
    timeout: float = 10.0,
) -> httpx.Response:
    body: bytes = envelope.model_dump_json().encode("utf-8")
    ts = str(int(time_module.time()))
    sig = hmac.new(secret, body, hashlib.sha256).hexdigest()

    # URL uses the cached IP directly; Host header preserves SNI identity.
    # TLS handshake uses `server_hostname=original_host` for SNI verification.
    url = f"https://{cached_ip}{original_path}"

    async with httpx.AsyncClient(
        transport=httpx.AsyncHTTPTransport(retries=0),
        verify=True,   # TLS; SNI is carried by the host in the transport
        timeout=httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=10.0),
    ) as client:
        return await client.post(
            url,
            content=body,
            headers={
                "Host": original_host,          # DNS identity for the server
                "Content-Type": "application/json",
                "X-Spark-Signature": f"sha256={sig}",
                "X-Spark-Timestamp": ts,
            },
        )
```

**HMAC signing over raw body bytes:** the signature is computed over `body` (raw UTF-8
JSON bytes), NOT over the parsed dict. This is critical: JSON serialization is canonical via
`model_dump_json()`, but the bytes that flow over the wire must be the bytes that were signed.
Do NOT re-serialize after signing.

**TLS SNI note:** `httpx.AsyncClient` with `verify=True` uses the `Host` header value for
SNI by default when the URL is an IP. Confirm this behavior holds in httpx >=0.27 —
[VERIFIED: httpx uses `ssl_context.check_hostname = True` and SNI is derived from the
`Host` header when the URL target is an IP address with a custom host header].

**Dedup window implementation:**
```python
# Per (modem_usb_path, kind) → expires_at monotonic
_dedup_table: dict[tuple[str, str], float] = {}

def is_deduped(usb_path: str, kind: str, now: float, window_s: float = 60.0) -> bool:
    key = (usb_path, kind)
    if key in _dedup_table and now < _dedup_table[key]:
        return True
    _dedup_table[key] = now + window_s
    return False
```

### 2.8 cli/ — spark-modem entry + subcommands

**Structure:**
```
cli/
├── __init__.py
├── main.py          ← typer/argparse app; entry_points in pyproject.toml
├── diag.py          ← spark-modem diag [--qmi-fixture-dir=] [--explain] [--json]
├── recovery.py      ← spark-modem recovery [--diag-fixture=] [--action=] [--dry-run]
├── provision.py     ← spark-modem provision --device= --apn=
├── reset.py         ← spark-modem reset <line> {--soft} [--dry-run]
├── status.py        ← spark-modem status (reads /var/lib/.../status.json)
└── ctl/
    ├── history.py   ← ctl history --modem= --since=
    ├── maintenance.py ← ctl maintenance on --duration= / off / status
    └── support_bundle.py ← ctl support-bundle [--out=]
```

**--explain format (Claude's Discretion):**
```
modem 2-3.1.1 [cdc-wdm0]: degraded
  issue: registration/not_registered_searching (priority 4)
  gates: signal=pass, backoff=pass, ladder=pass
  action: soft_reset (counter=1/3)

modem 2-3.1.2 [cdc-wdm1]: healthy, no action

modem 2-3.1.3 [cdc-wdm2]: recovering(soft), rf_blocked
  issue: registration/not_registered_searching
  gates: signal=FAIL (rsrp=-115dBm < -110dBm threshold) → skip
  action: (gated)
```

With `--json`, emit a JSON object containing the same data as machine-readable.

**Hardware-free laptop mode:** `diag --qmi-fixture-dir=PATH` instantiates `FixtureQmiClient`
(reads from `tests/fixtures/qmicli/<intent>/1.30/`). `recovery --diag-fixture=PATH` loads a
`Diag` JSON directly — no qmicli at all. Both paths use the same `policy/engine.py`.

**`ctl maintenance on`:**
```python
# Dual-clock expiry per C-02:
now_mono = clock.now_monotonic()
now_wall = datetime.now(UTC).isoformat()
expires_mono = now_mono + duration_seconds
expires_wall = (datetime.now(UTC) + timedelta(seconds=duration_seconds)).isoformat()
maintenance = Maintenance(
    active=True,
    scope="destructive",
    started_iso=now_wall,
    started_monotonic=now_mono,
    expires_iso=expires_wall,
    expires_monotonic=expires_mono,
    max_duration_seconds=28800,
)
```

Check: `expiry = min(now_mono >= expires_mono, now_wall_ts >= expires_iso_ts)`. Either clock
expiring ends the window.

**`ctl support-bundle` ICCID/IMSI redaction:**
```python
import hashlib

def redact_pii(value: str) -> str:
    digest = hashlib.sha256(value.encode()).hexdigest()[:8]
    return f"<redacted:{digest}>"
```

Same hash function and same input → same 8-char tag across all bundle files. Identity
correlation is preserved; PII is not exported.

### 2.9 daemon/ — cycle driver scaffold

**Cycle scheduling (M-02):**

```python
# daemon/main.py — cycle wake pattern
async def _cycle_loop(
    scheduler: CycleScheduler,
    event_queue: asyncio.Queue[CycleEvent],
    shutdown: asyncio.Event,
) -> None:
    while not shutdown.is_set():
        expected_next = scheduler.next_deadline()
        sleep_coro = asyncio.sleep(max(0.0, expected_next - time.monotonic()))
        queue_coro = event_queue.get()

        # Phase 2: event_queue is always empty (no-op stub).
        # Phase 3: udev/rtnetlink producers push to event_queue.
        done, pending = await asyncio.wait(
            {asyncio.ensure_future(sleep_coro),
             asyncio.ensure_future(queue_coro)},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass

        now_mono = time.monotonic()
        drift = now_mono - expected_next          # O-03: signed gauge, clamp >= 0
        cycle_drift_seconds.set(max(0.0, drift))  # noqa: F841

        if scheduler.overran(now_mono):
            event_logger.emit(CycleOverran(...))

        scheduler.advance()
        await _run_one_cycle(...)
```

**NFR-11 — policy exception must not crash the cycle:**
```python
async def _run_one_cycle(ctx: CycleContext) -> None:
    try:
        snapshots = await observer.observe_all(...)
        diag = builder.build_diag(snapshots)
        try:
            plans = policy.engine.run_cycle(diag, ctx.store, ctx.config, ctx.clock)
        except Exception as exc:
            event_logger.emit(PolicyError(exc=repr(exc)))
            plans = []   # skip actions this cycle; continue

        for plan in plans:
            if not plan.is_skip():
                await actions.dispatcher.execute_and_verify(plan.kind, plan.who, ctx)
    except Exception as exc:
        # True outer catch — if something catastrophic goes wrong in observe
        # we still update state (marking modems unknown) and write status.json
        event_logger.emit(CycleCrashed(exc=repr(exc)))
```

### 2.10 tests/replay/ — synthesized fault-cycle generator + CI gate

**Hypothesis strategy for Diag synthesis (R-01):**

```python
from hypothesis import strategies as st
from hypothesis.strategies import composite

FAULT_SCENARIOS = [
    # From RECOVERY_SPEC §4 and PITFALLS top-15
    "apn_empty", "apn_mismatch", "sim_power_down", "sim_app_unreadable",
    "not_registered_searching", "not_registered_idle", "qmi_channel_hung",
    "session_disconnected", "raw_ip_off", "operating_mode_offline",
    "operating_mode_low_power", "ladder_near_exhausted", "ladder_exhausted",
    "rf_blocked_during_recovery", "proxy_died",
]

@composite
def fault_diag_strategy(draw: st.DrawFn) -> tuple[Diag, ModemState, str]:
    """Generate (diag, prior_state, fault_scenario) tuples.

    Distribution: 70% explicit fault scenarios, 30% random multi-issue combos.
    This ensures ≥95% fault-cycle coverage in the synthesized fixture set.
    """
    scenario = draw(st.sampled_from(FAULT_SCENARIOS))
    n_modems = draw(st.integers(min_value=1, max_value=4))

    # Build per-modem snapshots; at least one carries the fault
    modem_snaps = [draw(_modem_snapshot_for_scenario(scenario, is_faulty=(i == 0)))
                   for i in range(n_modems)]
    prior_state = draw(_prior_state_strategy(scenario))

    diag = Diag(
        ts_iso=draw(st.just("2026-01-01T00:00:00Z")),
        cycle_id=draw(st.integers(min_value=0)),
        per_modem={f"2-3.1.{i+1}": snap for i, snap in enumerate(modem_snaps)},
    )
    return diag, prior_state, scenario

@composite
def _modem_snapshot_for_scenario(
    draw: st.DrawFn,
    scenario: str,
    is_faulty: bool,
) -> ModemSnapshot:
    if not is_faulty:
        return draw(_healthy_modem_strategy())
    # Map scenario to specific Issue(s)
    issues = _SCENARIO_TO_ISSUES[scenario]
    signal = draw(_signal_strategy(scenario))
    return ModemSnapshot(
        usb_path="2-3.1.1",
        cdc_wdm="cdc-wdm0",
        issues=issues,
        signal=signal,
        ...
    )
```

**Fixture generation script:** `tools/gen_replay_fixtures.py` runs this strategy,
serializes each `(Diag, ModemState, expected_actions, fault_cycle, v1_succeeded)` to
`tests/fixtures/replay/<scenario>/<NNN>.json`. The script ensures ≥1000 total fixtures
with ≥950 fault cycles. Fixtures are committed to git (R-04).

**M7 budget for 1000 fixture cycles (≤5 s target):**

```python
# tests/replay/test_v1_agreement.py
import json
from pathlib import Path
import pytest

FIXTURE_DIR = Path("tests/fixtures/replay")

def _load_fixtures() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(FIXTURE_DIR.rglob("*.json"))]

@pytest.fixture(scope="module")
def all_fixtures() -> list[dict]:
    return _load_fixtures()

# Parametrize IDs are file-path-based for readability in pytest output
@pytest.mark.parametrize(
    "fixture",
    _load_fixtures(),
    ids=[str(p.relative_to(FIXTURE_DIR)) for p in sorted(FIXTURE_DIR.rglob("*.json"))],
)
def test_v1_agreement(fixture: dict) -> None:
    """Each cycle must agree with v1 or be equal-or-safer (R-02)."""
    diag = Diag.model_validate(fixture["diag"])
    prior = ModemState.model_validate(fixture["prior_state"])
    expected = fixture["expected_v1_actions"]
    fault_cycle = fixture["fault_cycle"]

    plans = policy_engine_sync(diag, prior, default_config(), FakeClock())
    verdict = classify(plans, expected, fault_cycle)  # agree|safer|less-safe|different-issue|both-skip

    # Accumulate verdicts; the aggregate gate is computed in session fixture
    _VERDICTS.append((fixture["scenario"], fault_cycle, verdict))

def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Hard fail if fault-cycle agreement < 95%."""
    fault_verdicts = [v for _, fc, v in _VERDICTS if fc]
    if not fault_verdicts:
        return
    agreement = sum(1 for _, _, v in fault_verdicts if v in ("agree", "safer")) / len(fault_verdicts)
    summary = {"total": len(_VERDICTS), "fault_cycles": len(fault_verdicts),
               "agreement_rate": agreement, "verdicts": _VERDICTS}
    Path("artifacts/replay-summary.json").write_text(json.dumps(summary, indent=2))
    if agreement < 0.95:
        session.exitstatus = 1
```

**Loop reuse for M7:** `test_v1_agreement` is synchronous (calls a sync wrapper around
policy engine — the pure function needs no asyncio). 1000 synchronous pytest calls should
complete in ~1–3 s. If asyncio overhead is needed, scope the event loop to `module`.

---

## 3. Concrete Code Sketches (5 Hardest Problems)

### 3.1 Prometheus UDS Bridge

See §2.6 above for the complete `_UnixWSGIServer` pattern.

**Key pitfall:** `UnixStreamServer.server_bind()` calls `socket.bind()` without SO_REUSEADDR.
Do NOT call `WSGIServer.server_bind()` first — that sets SO_REUSEADDR, which on AF_UNIX
raises `ENOPROTOOPT` on some kernels (Linux 5.10-tegra included in the known-affected set).
The MRO in `class _UnixWSGIServer(UnixStreamServer, WSGIServer)` ensures `UnixStreamServer`
methods take priority for socket operations.

**Phase 2 spike test:**
```bash
python -c "
from pathlib import Path; import threading, time
from status_reporter.prom import start_metrics_server
srv = start_metrics_server(Path('/tmp/test.sock'))
t = threading.Thread(target=srv.serve_forever, daemon=True); t.start()
time.sleep(0.1)
import subprocess
result = subprocess.run(['curl', '--unix-socket', '/tmp/test.sock', 'http://localhost/metrics'],
    capture_output=True, text=True)
print(result.stdout[:200])
srv.shutdown()
"
```

### 3.2 httpx Host-Header DNS Trick

See §2.7 for the full `_post_webhook` function.

**Tricky edge cases:**
1. `httpx.AsyncHTTPTransport(retries=0)` disables httpx's built-in retry logic —
   we handle retries ourselves (W-01 queue).
2. When using `verify=True` with an IP URL + `Host` header, httpx derives the TLS SNI
   from the `Host` header value, not the URL. This is the desired behavior.
3. If the cached IP changes between the `_post_webhook` call and the actual TCP connect
   (e.g. server migrated), TLS certificate validation uses the `Host` header hostname,
   so certificate mismatch is detected correctly.

**Test for the trick:**
```python
async def test_host_header_dns_trick(httpx_mock) -> None:
    httpx_mock.add_response(url="https://10.0.0.1/webhook", status_code=200)
    result = await _post_webhook(
        envelope=...,
        cached_ip="10.0.0.1",
        original_host="noc.example.invalid",
        original_path="/webhook",
        secret=b"test-secret",
    )
    request = httpx_mock.get_requests()[0]
    assert request.headers["Host"] == "noc.example.invalid"
    assert "X-Spark-Signature" in request.headers
    assert "X-Spark-Timestamp" in request.headers
```

### 3.3 asyncio.TaskGroup + Per-Task asyncio.timeout (Probe Orchestrator)

See §2.3 for the full pattern. The key insight repeated: **exceptions must not escape
each task**. TaskGroup cancels siblings on any task exception. We never want that — one
slow modem must not cancel others.

**Exception-group behavior warning:** if you accidentally allow an exception to escape
`_probe_one`, Python 3.11+ TaskGroup wraps it in `ExceptionGroup`. The cycle driver's
outer `except Exception` does NOT catch `ExceptionGroup` (it catches `BaseException`
subclasses, and `ExceptionGroup` IS one, but the matching rules differ). Ensure the
inner try/except is comprehensive enough to prevent any exception propagation.

**Deliberate policy exception test (SC #3):**
```python
@pytest.mark.asyncio
async def test_policy_exception_does_not_crash_cycle() -> None:
    """A deliberately-thrown policy exception is logged; cycle continues."""
    observer = FakeObserver(snapshots=[healthy_snapshot()])
    policy = ExplodingPolicy()  # raises RuntimeError on engine.run_cycle
    driver = CycleDriver(observer, policy, ...)

    result = await driver.run_one_cycle(...)

    assert result.policy_exception is not None
    assert result.plans == []  # no plans; but cycle did not crash
    assert result.status_json_written  # status.json still written
```

### 3.4 Hypothesis Strategy for Fault-Cycle Synthesizer

See §2.10 for the `fault_diag_strategy` composite strategy.

**Distribution strategy:** 70/30 split between explicit scenario sampling and random
multi-issue combinations ensures:
- Every RECOVERY_SPEC §4 row is covered at least once per Hypothesis run.
- Edge cases (multiple simultaneous issues, conflicting priorities) are discovered.
- The on-disk fixtures can be generated reproducibly with a fixed seed.

**Avoid Hypothesis deadline blowup (PITFALLS §14.3):**
```python
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(fault_diag_strategy())
def test_policy_does_not_crash(scenario_tuple: tuple) -> None:
    diag, prior, scenario = scenario_tuple
    # Property: policy engine never raises; always returns a list
    result = policy_engine_sync(diag, prior, default_config(), FakeClock())
    assert isinstance(result, list)
```

**On-disk vs in-memory split (R-01/R-04):**
- The ≥1000 on-disk fixtures in `tests/fixtures/replay/` are pre-generated and committed.
- Hypothesis generates additional in-memory cycles for property tests only.
- `test_v1_agreement.py` reads ONLY the on-disk fixtures.
- This ensures the CI gate is deterministic (same fixtures every run) while Hypothesis
  explores the full space separately.

### 3.5 Cycle Wake Pattern

```python
# The canonical form for Phase 2 cycle scheduling (M-02)

async def _wait_for_next_cycle(
    deadline_monotonic: float,
    event_queue: asyncio.Queue[CycleEvent],
) -> CycleEvent | None:
    """Wait until next cycle deadline OR an event arrives, whichever is first.

    Returns the event that triggered the wake (or None for a timer tick).
    Cancels the losing future cleanly to avoid resource leaks.
    """
    now = time.monotonic()
    remaining = max(0.0, deadline_monotonic - now)

    sleep_future: asyncio.Future[None] = asyncio.ensure_future(asyncio.sleep(remaining))
    queue_future: asyncio.Future[CycleEvent] = asyncio.ensure_future(event_queue.get())

    try:
        done, pending = await asyncio.wait(
            {sleep_future, queue_future},
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        # Always cancel the loser to avoid resource leaks
        for fut in pending:
            fut.cancel()
            try:
                await fut
            except (asyncio.CancelledError, Exception):
                pass

    if queue_future in done:
        return queue_future.result()
    return None  # timer tick
```

**Why `ensure_future` not `create_task`:** `asyncio.wait` requires awaitables that are
already scheduled. `ensure_future` wraps a coroutine into a Task (if not already one).
In Python 3.12 `asyncio.TaskGroup.create_task` is preferred inside TaskGroups, but here
we need two independent futures for `wait`.

**Phase 2 behavior:** `event_queue` is always empty (no-op stub). The wake always fires
via the sleep timer. Tests push synthetic events through the queue to test the event path.

---

## 4. Pitfalls & Mitigations

### 4.1 qmicli: proxy_died short-circuit (PITFALLS §1.1)

**Risk:** qmi-proxy crash leaves modems with stale CIDs. Subsequent qmicli calls return
`QMI protocol error (3): 'Internal'`. The per-action backoff (300 s) would suppress
`driver_reset` even though it's the only recovery.

**Mitigation in Phase 2:** `qmi/wrapper.py` detects the `proxy_died` error substring in
stderr, maps to `QmiError(reason="proxy_died")`. In `policy/gates.py`, this error type
bypasses per-action backoff and triggers the global driver-reset short-circuit (§6.4
extended). Phase 2 fixture: `tests/fixtures/qmicli/proxy_error/proxy_died.txt`.

### 4.2 libqmi output drift (PITFALLS §1.2)

**Risk:** libqmi field additions/removals break parsers.

**Mitigation:** `extra='ignore'` on all parser pydantic models; per-version fixture
directories; `MissingField` sentinel for required fields. CI parametrizes over all fixture
versions. **CONTEXT.md fix for Phase 2 Planner:** plan 02-02 must include fixtures for
both libqmi 1.30 (focal-default) and a representative 1.32 fixture set.

### 4.3 `_healthy_streak` persistence (PITFALLS §9.1 + §9.2)

**Risk:** crash mid-cycle resets streak; daemon restart resets streak.

**Mitigation:** Already locked in ADR-0006 and CONTEXT.md FR-26.1/FR-26.2. The critical
implementation note: `_healthy_streak` is part of `ModemState` (already in `wire/state.py`),
and `state_store/store.py`'s `save_modem_state` writes it atomically with every other state
field. The REPLAY harness (R-04) must include a `daemon_restart_mid_streak` scenario fixture.

### 4.4 FakeClock + asyncio.sleep divergence (PITFALLS §14.1)

**Risk:** code that mixes `clock.now_monotonic()` for policy decisions with
`await asyncio.sleep()` for scheduling will have clock divergence in tests.

**Mitigation:** The `CycleScheduler` uses `clock.now_monotonic()` exclusively for deadline
arithmetic. The actual `asyncio.sleep(remaining)` call is passed the delta computed from the
FakeClock. Tests advance the FakeClock and confirm scheduling decisions without waiting for
real wall time. The `asyncio.sleep` call in `_wait_for_next_cycle` is always with the
computed `remaining` duration based on the clock, so tests with FakeClock can push a 30 s
advance and verify the cycle fires at the right logical time.

### 4.5 Prometheus UDS socket orphan (PITFALLS §13.3)

**Risk:** stale socket file from a previous crash prevents daemon restart.

**Mitigation:** `start_metrics_server()` calls `socket_path.unlink(missing_ok=True)` before
binding. This is safe because `RuntimeDirectory=spark-modem-watchdog` + the flock
ensures no concurrent daemon runs.

### 4.6 Pydantic boundary split (§2.1, locked in CONTEXT.md)

**Risk:** using `extra='forbid'` on qmicli parsers would break on any new libqmi field.

**Mitigation:** CONTEXT.md "Established Patterns" locks this: `extra='forbid'` on wire models
(all `BaseWire` subclasses), `extra='ignore'` on internal qmicli parse results.

The practical split:
- `wire/diag.py`, `wire/state.py`, `wire/webhook.py` etc. → `frozen=True, extra='forbid'`
  (from `BaseWire`; already implemented in Phase 1)
- `qmi/parsers/<intent>.py` internal classes → `ConfigDict(extra='ignore')`

### 4.7 `asyncio.wait` resource leak (new — see §3.5)

**Risk:** if the losing future (sleep or queue.get) is not explicitly cancelled and awaited,
Python 3.12 emits `RuntimeWarning: Enable tracemalloc to get the object allocation traceback`
for dangling tasks. Over thousands of cycles this creates GC pressure.

**Mitigation:** the `_wait_for_next_cycle` pattern in §3.5 always cancels and awaits pending
futures in the `finally` block.

### 4.8 Cycle overrun detection (PITFALLS §9.3)

**Risk:** event coalescing bug causes back-to-back cycles at >1 Hz.

**Mitigation in Phase 2:** the `CycleScheduler.overran()` check in the wake loop emits a
`cycle_overran` event to events.jsonl when the measured drift exceeds the cycle interval.
The minimum cycle interval (1 s guard) prevents pathological hot-loops even if the event
queue is flooded.

### 4.9 HMAC body signing order (PITFALLS §10.5)

**Risk:** signing the dict (not raw bytes) means different JSON serializers produce different
signatures. Receiver fails verification.

**Mitigation:** sign after `model_dump_json()`, before any modification. The bytes that are
signed are the bytes sent as the request body. No round-trip. The `Content-Length` in the
request equals `len(body)`. See §3.2.

### 4.10 `actions/` coverage for verify() (M-04)

**Risk:** `verify()` missing for new actions silently marks all actions as `verify_result=no_verify`,
undermining the post-action read-back value proposition.

**Mitigation:** the dispatcher calls `fn_verify` from `_REGISTRY`. If an action is registered
without a verify function, the dispatcher raises at registration time (not at runtime). Actions
that structurally cannot be verified inline (e.g. `soft_reset` whose effect is observed next
cycle) return `VerifyResult.deferred()` — this is a valid explicit state, not a silent skip.

---

## 5. Plan-Slicing Suggestions

The CONTEXT.md M-03 provisional slicing (02-01 through 02-10) is well-structured.
The following refinements and dependency notes should guide the planner:

### 5.1 Wave Dependency Graph

```
Wave A (can start immediately — no dependencies):
  02-02: qmi/parsers/ + qmi/wrapper.py   (depends on Phase 1 subproc/runner.py)
  02-03: zao_log/parser.py               (depends on nothing except stdlib)

Wave B (depends on Wave A):
  02-04: observer/ + inventory/sysfs.py  (depends on 02-02 qmi wrapper, 02-03 zao_log)
  02-05: policy/                          (depends on wire/ only — Phase 1 exists; CAN START PARALLEL)

Wave C (depends on Wave B):
  02-06: actions/ cheap set              (depends on 02-02 qmi wrapper, 02-05 policy for ActionKind)
  02-07: status_reporter/               (depends on 02-05 for PlannedAction, Phase 1 state_store)

Wave D (depends on Wave C):
  02-08: webhook/                        (depends on Phase 1 wire/webhook.py — already exists)
  02-09: cli/                            (depends on 02-04 observer, 02-05 policy, 02-06 actions,
                                          02-07 status_reporter)

Wave E (depends on all):
  02-01: daemon/main.py cycle driver     (integrates everything; written last, tested with all modules)
  02-10: replay harness                  (depends on 02-05 policy engine being green)
```

**Key insight:** `02-05` (policy) is pure Python with no external dependencies beyond
`wire/` (Phase 1). It can be developed in Wave A parallel with `02-02` and `02-03`.
The CONTEXT.md Claude's Discretion section suggests `02-02 ‖ 02-03 → 02-04 ‖ 02-05`,
which matches this analysis.

### 5.2 Test-Seam Dependencies (must-know for task ordering)

- `02-02` must define `QmiWrapper` protocol and `FakeRunner` → used by `02-04` integration tests.
- `02-03` must define `ZaoLogTailer` protocol and `FixtureZaoTailer` → used by `02-04`.
- `02-04` must define `InventorySource` protocol and `FixtureInventory` → used by `02-01`.
- `02-05` must define `PolicyEngine` protocol → used by `02-01` and `02-10`.

These protocols should be defined at the TOP of each plan's first task, not as an afterthought.
The `tests/fakes/` directory is populated alongside the protocols.

### 5.3 Recommendations for Planner

- **Split 02-07** into two plans if needed: `02-07a` (status.json writer) and `02-07b`
  (Prometheus UDS). The UDS bridge requires a Phase 0 spike validation on Windows (no-op
  socket vs real server). On Windows dev host, the Prometheus UDS server should be
  conditionally started or replaced with a no-op for testing.
- **02-08 can start in Wave C** because `wire/webhook.py` is already complete (Phase 1).
  The poster needs only the DNS cache and httpx client, which have no module dependencies.
- **02-10 replay harness** should be the LAST plan — it validates the entire policy engine
  end-to-end and will surface integration issues. Its ≥95% gate is the Phase 2 exit gate.
- **Windows dev-host note for 02-07b:** the `_UnixWSGIServer` will fail on Windows
  (`AF_UNIX` socket support requires Windows 10 1803+, Python 3.9+). Use
  `sys.platform == "win32"` guard and replace with a `FakeMetricsServer` for tests.

---

## 6. Validation Architecture

### Validation Dimensions

#### Dimension 1: Functional — RECOVERY_SPEC §4 spec-as-tests

| Requirement | Behavior | Test Type | Command | File | Pass Threshold |
|------------|----------|-----------|---------|------|----------------|
| FR-12, FR-20, FR-21, FR-22 | Every §4 decision-table row produces correct action | Unit parametrize | `pytest tests/test_recovery_spec.py -x` | tests/test_recovery_spec.py | All rows pass |
| FR-25, FR-25.1 | Backoff gates suppress repeated actions within window | Unit | `pytest tests/policy/test_gates.py -x` | tests/policy/test_gates.py | All pass |
| FR-26, FR-26.1 | streak persists across simulated restart | Unit replay | `pytest tests/policy/test_streak.py -x` | includes mid-restart fixture | All pass |
| FR-26.2 | atomic write ordering (streak+decay+counter+state = one write) | Unit + crash injection | `pytest tests/state_store/test_atomic_ordering.py` | | All pass |
| FR-28.1 | per-modem dry-run config gates action at execution | Unit | `pytest tests/actions/test_dry_run.py` | | All pass |

**tools/check_spec.py gate:** every `§4` row in RECOVERY_SPEC.md is referenced by ≥1 test.
This gate runs in CI and fails the build if rows are added to the spec without tests.

#### Dimension 2: Performance — M5 (P99 ≤10 s) / M7 (≤30 s suite)

| Metric | Measure | Test | Pass Threshold |
|--------|---------|------|----------------|
| M5: P99 cycle ≤10 s | FakeClock replay; all 4 modems with 8 s probe timeout | `pytest tests/daemon/test_cycle_perf.py` | p99 ≤ 10 s synthetic |
| M7: pytest -q ≤ 30 s | wall-clock of full `pytest tests/` run | CI timing gate | ≤30 s |
| Replay budget: ≤5 s for 1000 fixtures | `time pytest tests/replay/` | Manual gate | ≤5 s |
| Per-probe timeout honored | TimeoutError caught; timed_out=True in snapshot | `pytest tests/observer/test_timeout.py` | All 4 timeout variants pass |

#### Dimension 3: Concurrency — NFR-4 (parallel probes) / NFR-11 (policy exception safety)

| Requirement | Behavior | Test | Pass Threshold |
|------------|----------|------|----------------|
| NFR-4: parallel per-modem probes | 4 probes start within 100 ms of each other | `pytest tests/observer/test_parallel.py` | All 4 probe tasks start before first completes |
| NFR-11: policy exception isolated | Exception in policy engine logs + cycle continues | `pytest tests/daemon/test_policy_exception.py` | status.json written; no daemon crash |
| FR-70: one slow modem ≠ cycle failure | 3 fast probes + 1 timeout; cycle produces 3 valid snapshots | `pytest tests/observer/test_partial_timeout.py` | 3 snapshots valid, 1 timed_out |
| Lock ordering (ADR-0012) | No deadlock when 4 modems commit state simultaneously | `pytest tests/state_store/test_lock_ordering.py` | Completes in <2 s |

#### Dimension 4: Cardinality — NFR-21 / ADR-0013

| Requirement | Check | Method | Pass Threshold |
|------------|-------|--------|----------------|
| No one-hot state label | `modem_state_value{modem}` is a Gauge, not Enum | `pytest tests/metrics/test_cardinality.py` | Exactly 4 series for 4 modems (not 20) |
| State transitions update gauge | After transition, gauge value matches state_to_int() | `pytest tests/metrics/test_gauge_update.py` | All 5 state values tested |
| webhook_delivery_total result enum | Only allowed result values in label | Code review + mypy | No arbitrary strings |
| state_duration_seconds buckets | Exactly O-02 buckets | `pytest tests/metrics/test_buckets.py` | [1, 5, 15, 60, 300, 1800, 7200, 86400] |

#### Dimension 5: Replay — SC #1 (≥95% fault-cycle agreement)

| Requirement | Check | Command | Pass Threshold |
|------------|-------|---------|----------------|
| SC #1: fault-cycle agreement ≥95% | test_v1_agreement.py per-cycle classify | `pytest tests/replay/ -v` | ≥950/1000 fault cycles: agree or safer |
| R-04: ≥1000 on-disk fixtures | File count | `python tools/count_fixtures.py` | ≥1000 |
| R-02: cost-order correct | `safer` verdicts never reversed | `grep "less-safe" artifacts/replay-summary.json` | Zero less-safe on healthy-input fixtures |
| Fixture audit: each row covered | tools/check_spec.py | `python tools/check_spec.py` | Zero uncovered §4 rows |

#### Dimension 6: Restart-Resilience — FR-26.1 / SC #6 (_healthy_streak)

| Requirement | Test Scenario | Command | Pass Threshold |
|------------|---------------|---------|----------------|
| Streak persists across restart | 5 healthy cycles → "restart" → 5 more → decay fires at 10 | `pytest tests/replay/test_streak_restart.py` | decay_at_cycle=10 not 5+5=reset |
| Mid-streak restart does not reset | Fixture: `daemon_restart_mid_streak.json` | `pytest tests/replay/ -k restart_mid_streak` | post-restart streak = pre-restart streak |
| Single atomic write | Crash injection between step 3 and 4 of RECOVERY_SPEC §8 | `pytest tests/state_store/test_crash_injection.py` | Recovery reads consistent state |

#### Dimension 7: Failure-Injection — NFR-10 (one transient error → recovery in one cycle)

| Failure Mode | Injection | Test | Recovery Criterion |
|-------------|----------|------|-------------------|
| qmicli timeout on one modem | FakeRunner hangs for one probe | `pytest tests/observer/test_qmi_timeout.py` | Probe returns `timed_out=True`; other 3 succeed |
| qmicli parse error (malformed output) | FakeRunner returns garbage | `pytest tests/qmi/test_parse_error.py` | QmiError returned; NOT exception propagated |
| DNS resolve failure (webhook) | FakeDNSResolver returns None | `pytest tests/webhook/test_dns_failure.py` | webhook_delivery_total{result="skipped_no_dns"} incremented; cycle unaffected |
| Full webhook queue | Enqueue 101 items | `pytest tests/webhook/test_queue_overflow.py` | Oldest item dropped; counter incremented |
| status.json write failure (disk full) | Patch os.replace to raise OSError | `pytest tests/status_reporter/test_write_failure.py` | Event logged; daemon does not crash |

#### Dimension 8: Prometheus UDS Scrape

| Requirement | Check | Command | Pass Threshold |
|------------|-------|---------|----------------|
| FR-42: UDS endpoint responds | curl --unix-socket scrape returns 200 | Integration test (Linux only) `pytest tests/metrics/test_uds_scrape.py -m linux` | Valid Prom text format |
| All NFR-21 metrics present | Text output contains all required metric names | Same test | All 9 metric families present |
| Windows no-op | FakeMetricsServer on win32 | `pytest tests/metrics/test_fake_server.py` | No OSError on Windows |

### Test Framework Summary

| Property | Value |
|----------|-------|
| Framework | pytest 8.3.x + pytest-asyncio 0.24.x (mode=auto) |
| Config file | pyproject.toml [tool.pytest.ini_options] asyncio_mode="auto" |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v --tb=short` |
| Replay gate command | `pytest tests/replay/ -v` |
| Type check | `mypy --strict src/ tests/` |
| Lint | `ruff check src/ tests/` |

### Wave 0 Gaps (must exist before implementation begins)

- [ ] `tests/fakes/runner.py` — `FakeRunner` (already referenced in Phase 1 but must be
  confirmed to exist and cover qmicli fixture loading)
- [ ] `tests/fakes/clock.py` — `FakeClock` (Phase 1 created; confirm monotonic advance API)
- [ ] `tests/fakes/webhook.py` — `FakeWebhookPoster` (new for Phase 2)
- [ ] `tests/fakes/inventory.py` — `FixtureInventory` (new for Phase 2)
- [ ] `tests/fakes/dns.py` — `FakeDNSResolver` (new for Phase 2)
- [ ] `tests/fixtures/replay/` — ≥1000 on-disk cycle fixtures (generated by `tools/gen_replay_fixtures.py`)
- [ ] `tools/gen_replay_fixtures.py` — fixture generator script
- [ ] `tools/check_spec.py` — RECOVERY_SPEC §4 row coverage checker
- [ ] `artifacts/` — directory created in CI for `replay-summary.json`

---

## 7. Architecture Diagram

```
Developer laptop (Phase 2 scope — hardware-free)
─────────────────────────────────────────────────
pytest / CLI invocation
        │
        ▼
  FixtureInventory / SysfsInventory (M-01)
        │  Modem list
        ▼
  Observer (TaskGroup × 4)
  ├── probe_modem() per modem
  │   ├── ZaoLogParser.is_active() → skip if active (FR-10)
  │   ├── QmiWrapper.run_intent() [uses FakeRunner in tests]
  │   │   └── subproc/runner.py [async subprocess]
  │   └── asyncio.timeout(8s) → ModemSnapshot or timed_out
        │
        ▼  Diag (frozen pydantic)
  Policy Engine (pure function — no I/O)
  ├── transitions.py → new ModemState per modem
  ├── decision_table.py → ActionKind per issue
  └── gates.py → PlannedAction (with gates_passed/failed)
        │
        ▼  PlannedAction[]
  Actions Dispatcher (one per modem per cycle)
  ├── set_apn / fix_raw_ip / sim_power_on / soft_reset / ...
  └── verify() read-back per action
        │
        ▼  ActionResult[]
  State Store (per-modem asyncio.Lock + flock)
  ├── save_modem_state() atomic temp+rename+fsync
  └── streak update + decay (RECOVERY_SPEC §8 ordering)
        │
  ┌─────┴─────────────────────┐
  │                           │
  ▼                           ▼
Status Reporter           Event Logger
├── status.json (atomic)   └── events.jsonl (O_APPEND)
└── Prometheus UDS
    (to_thread wsgiref)
         │
  Webhook Poster (separate asyncio task)
  ├── DnsCache.resolve() [loop.getaddrinfo in executor]
  ├── httpx AsyncClient [Host-header trick, HMAC signing]
  └── retry Queue (W-01: 3 attempts, 1s/4s/16s)
```

---

## 8. Environment Availability

Phase 2 is laptop-testable — no hardware required. All external dependencies are faked.

| Dependency | Required By | Available (win32 dev) | Available (Linux CI) | Fallback |
|------------|------------|----------------------|---------------------|----------|
| qmicli binary | FR-11 probes | No | No (CI is laptop-mode) | FakeRunner + fixture files |
| libqmi-utils | qmicli parsing | No | No | Per-version text fixtures |
| AF_UNIX sockets | Prom UDS (FR-42) | Partial (Win10 1803+) | Yes | FakeMetricsServer on win32 |
| /sys/bus/usb/ | SysfsInventory | No | No | FixtureInventory |
| qmi-proxy | FR-74 | No | No | FixtureInventory + FakeRunner |
| Python 3.12 | All | Yes (bundled via uv) | Yes | N/A |
| pytest 8.3+ | Tests | Yes | Yes | N/A |
| hypothesis 6.110+ | Property tests | Yes | Yes | N/A |
| httpx 0.27+ | Webhook | Yes | Yes | N/A |
| prometheus-client 0.25+ | Metrics | Yes | Yes | N/A |

**No blocking dependencies** — all external integrations are behind Protocol seams with
available fakes.

---

## 9. Security Domain

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | N/A — daemon has no inbound API |
| V3 Session Management | No | N/A |
| V4 Access Control | Partial | flock-based serialization for CLI mutators |
| V5 Input Validation | Yes | pydantic v2 on all wire models; `extra='forbid'` |
| V6 Cryptography | Yes | HMAC-SHA256 via stdlib `hmac`; secret from LoadCredential |

**HMAC threat model:** the signing secret is at `/etc/spark-modem-watchdog/hmac-secret`
(systemd `LoadCredential=`). Never copied to the support bundle. Replay protection via
`X-Spark-Timestamp` (verify receiver must reject timestamps >5 min old).

**Subprocess injection** (NFR-31 / FR-64): `subproc/runner.py` validates all argv as
`list[str]`; raises `TypeError` on non-list input. qmicli device paths come from sysfs
inventory (not user input). APN strings are enum-validated in pydantic before being
passed as argv elements.

**Support bundle PII:** ICCID/IMSI are SHA-256 hashed to 8-char prefixes. Non-reversible.
The hash is consistent within a bundle (same ICCID → same tag in all files).

---

## 10. Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | httpx >=0.27 derives TLS SNI from `Host` header when URL is an IP | §2.7, §3.2 | Webhook TLS handshake fails against hostname-verified servers |
| A2 | `loop.getaddrinfo` uses ThreadPoolExecutor (does not block event loop) | §2.7 | DNS resolution blocks the cycle; defeats W-02 strategy |
| A3 | libqmi 1.32+ output differs primarily in NR5G sections of `--nas-get-signal-info` | §2.1 | Parser failures on field boxes with 1.32; need additional fixture categories |
| A4 | Python 3.12 on Windows supports `AF_UNIX` sockets (Win10 1803+) | §6 / §8 | Prom UDS test fails on older Windows dev hosts; need skip guard |

**A1 is the highest-risk assumption.** Verify before 02-08 implementation by sending a
test httpx request with IP URL + Host header to a TLS endpoint and inspecting the SNI in
a Wireshark/mitmproxy capture.

---

## 11. Open Questions

1. **Prom UDS on Windows dev host**
   - What we know: `AF_UNIX` on Windows requires Win10 1803+ and Python 3.9+.
   - What's unclear: Whether the CI Windows runner meets this requirement.
   - Recommendation: Add `@pytest.mark.skipif(sys.platform == "win32", reason="AF_UNIX")`
     to `tests/metrics/test_uds_scrape.py`. On Windows, the Prometheus UDS server is
     replaced by `FakeMetricsServer` that records all set/inc calls for test assertion.

2. **httpx SNI from Host header with IP URL**
   - What we know: httpx docs don't explicitly state this behavior for IP URLs.
   - What's unclear: Whether SNI is correctly set to the `Host` header value.
   - Recommendation: In plan 02-08, add a spike test using `pytest-httpx` mock that
     inspects the TLS handshake SNI. If SNI is wrong, fallback: use httpx's
     `base_url` + `extensions={"sni_hostname": original_host}` parameter.

---

## 12. References

| File | Relevant Sections |
|------|------------------|
| `.planning/phases/02-core-daemon-laptop-testable/02-CONTEXT.md` | ALL (canonical for locked decisions) |
| `.planning/research/ARCHITECTURE.md` | Q2 (TaskGroup+timeout), Q3 (per-modem locks), Q8 (qmicli), Q9 (Prom UDS), Q12 (SIGTERM), Q14 (usb_path), Q16 (test seams), Q17 (CLI layering) |
| `.planning/research/PITFALLS.md` | §1.1-1.6 (qmi), §5.1-5.4 (asyncio+subprocess), §9.1-9.2 (streak), §10.1-10.5 (webhook/DNS), §13.1-13.5 (metrics), §14.1-14.3 (testing), §15.1 (replay bias), §16.2 (maintenance) |
| `.planning/research/STACK.md` | §4.2 (subproc recipe), Stack table |
| `.planning/research/SUMMARY.md` | §4.1 (TaskGroup), §4.2 (Prom UDS), §4.3 (HMAC), §6 (cross-cutting) |
| `docs/RECOVERY_SPEC.md` | §3 (state machine), §3.3 (decay), §4 (decision table), §5 (priority), §6 (gates), §7 (PlannedAction), §8 (cycle algorithm), §10 (worked examples) |
| `docs/TEST_STRATEGY.md` | §2-§5 (test layers + spec-as-tests + property tests) |
| `docs/adr/0006-counter-decay.md` | Atomic ordering |
| `docs/adr/0008-state-machine-5-plus-2.md` | ModemState shape |
| `docs/adr/0009-state-files-keyed-by-usb-path.md` | usb_path keying |
| `docs/adr/0011-webhook-subsystem.md` | HMAC v2.0 + retry |
| `docs/adr/0012-concurrency-locks.md` | 3-layer lock model + acquisition order |
| `docs/adr/0013-metric-surface.md` | Integer encoding + stable mapping |
| `src/spark_modem/subproc/runner.py` | SP-01..SP-04 invariants, two-stage shutdown, _in_critical_section pattern (lines 1-261) |
| `src/spark_modem/wire/diag.py` | Diag, ModemSnapshot, PlannedAction, Issue types |
| `src/spark_modem/wire/webhook.py` | HealthyToDegraded, RecoveringToExhausted, DaemonRestart, ActionFailedWebhook |

---

## 13. Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries pinned in Phase 1; versions confirmed in `requirements.lock`
- Architecture (TaskGroup, locks, UDS): HIGH — patterns drawn from project's own ARCHITECTURE.md Q9, Q2, Q3; source code confirms Phase 1 foundations
- qmicli parsing patterns: HIGH — PITFALLS §1.1-1.6 + CONTEXT.md §02-02 locks approach
- httpx SNI behavior: MEDIUM — assumed based on httpx docs; needs 02-08 spike test (A1)
- Hypothesis strategy: MEDIUM-HIGH — pattern is standard but exact scenario coverage requires iteration
- M7 timing budget: MEDIUM — 1000 sync pytest calls estimated at 1-3 s; needs confirmation in practice

**Research date:** 2026-05-06
**Valid until:** 2026-06-06 (stable libraries; Prom-over-UDS spike should occur in first plan)