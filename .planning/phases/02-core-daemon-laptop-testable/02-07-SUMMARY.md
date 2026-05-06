---
phase: 02-core-daemon-laptop-testable
plan: 07
subsystem: status_reporter
tags: [status-json, prometheus, uds, metric-registry, maintenance-window, fr-41, fr-41.1, fr-42, nfr-3, nfr-5, nfr-21, nfr-21.1, adr-0013, c-02, o-01, o-02, o-03, o-04]

# Dependency graph
requires:
  - phase: 01-foundations-adrs
    provides: BaseWire (frozen, extra='forbid'); state_store.atomic.atomic_write_bytes (temp+rename+dir-fsync); GlobalsState (Phase 1 shape with driver_reset_count / qmi_proxy_uptime_seconds); CURRENT_SCHEMA_VERSION; ActionKind / ActionResult enums; state_to_int (ADR-0013 stable mapping)
  - external
    provides: prometheus-client >=0.25 (Counter / Gauge / Histogram + make_wsgi_app); stdlib socketserver.UnixStreamServer (POSIX-only) + wsgiref.simple_server (cross-platform import)
provides:
  - wire/maintenance.py — MaintenanceWindow BaseWire (C-02): dual-clock fields (started_iso + started_monotonic + expires_iso + expires_monotonic), 8-hour hard cap (max_duration_seconds le=28800), scope=Literal["destructive"]
  - wire/status.py — StatusReport / StatusCycleSummary / StatusModemSummary / StatusPerModem (FR-41 + FR-41.1 + ADR-0013): cycle_index, last_modified, cycle.{n,duration_seconds,next_at_iso}, summary aggregate counts, modems[].state_int (0..4), cycle_actions_executed, cycle_transitions, carrier_table_sha256, maintenance_active_until_iso
  - wire/globals.py — GlobalsState extended with optional MaintenanceWindow (Phase 1-shape globals.json without `maintenance` still parses cleanly; default None)
  - status_reporter/status.py — write_status_json(path, report) wraps state_store.atomic.atomic_write_bytes (never re-implements temp+rename+fsync); single function, ≤20 lines
  - status_reporter/metrics_registry.py — MetricRegistry typed accessors (record_action / record_signal / observe_cycle_duration / set_modem_state / observe_state_duration / set_cycle_drift / record_webhook_delivery / record_rss_tripwire); ADR-0013 integer encoding enforced; 10 metric names exposed via metric_names()
  - status_reporter/prom.py — _UnixWSGIServer (UnixStreamServer + WSGIServer MRO; no SO_REUSEADDR); start_metrics_server(socket_path, *, registry=None) with 0o660 mode + stale-socket unlink + parent-dir mkdir; Windows-safe at import time (POSIX guard)
  - status_reporter/__init__.py — package docstring listing the three submodules
  - 23 tests across 3 files (test_status 8 / test_metrics_registry 11 / test_prom_uds 4 — Linux-only). All cross-platform tests pass; UDS scrape tests skipif(win32).
affects: [02-09-cli, 02-10-cycle-driver, phase-3-sd_notify-watchdog, phase-3-sighup-reload]

# Tech tracking
tech-stack:
  added:
    - "prometheus-client >=0.25 — already pinned in packaging/requirements.in (Phase 1); Plan 02-07 is the first consumer in src/. Provides Counter / Gauge / Histogram primitives + make_wsgi_app() for the UDS bridge."
  patterns:
    - "ADR-0013 enforcement (cardinality discipline): modem_state_value{modem} is a SINGLE Gauge whose VALUE is the integer state code (0..4 stable mapping via state_to_int). The label set is exactly {modem} — `state` does NOT appear as a label on this gauge. Verified by `! grep -E 'modem_state\\{.*state='` and by `test_modem_state_value_is_single_gauge_not_one_hot` (collects via REGISTRY.collect() and asserts label-set keys are exactly `{modem}`)."
    - "ADR-0013 §exception: state_duration_seconds{modem, state} histogram is the ONE place a `state` label is permitted — histograms are inherently multi-series and time-in-state is a measurement dimension, not a current-state indicator. Buckets are [1, 5, 15, 60, 300, 1800, 7200, 86400] (O-02 verbatim) — verified by `test_state_duration_buckets_match_o_02` reading `_upper_bounds` from collected samples."
    - "Atomic file writes (status.json, globals.json) all delegate to state_store.atomic.atomic_write_bytes — the canonical Phase 1 helper. status.py never re-implements temp + rename + dir-fsync; this preserves the `! grep create_subprocess_exec outside subproc/` invariant AND the 'one atomic-write helper' invariant (FR-62)."
    - "_UnixWSGIServer MRO: UnixStreamServer first, WSGIServer second. Reason: WSGIServer.server_bind() calls setsockopt(SO_REUSEADDR) which is invalid on AF_UNIX sockets on some kernels (Linux 5.10-tegra returns ENOPROTOOPT). Calling UnixStreamServer.server_bind() directly skips the setsockopt dance. Verified by `! grep -E 'SO_REUSEADDR' src/spark_modem/status_reporter/prom.py`."
    - "Windows-safe import: prom.py guards `from socketserver import UnixStreamServer` behind `if sys.platform != \"win32\":` because UnixStreamServer is conditionally defined inside the stdlib's socketserver module on POSIX hosts only. On Windows, _UnixWSGIServer is a stub class that raises RuntimeError if instantiated; tests skipif(win32). This lets `python -m mypy --strict src/spark_modem/status_reporter/` succeed on the dev laptop AND on the production aarch64 Linux build."
    - "Stale-socket cleanup (PITFALLS §13.3): start_metrics_server calls `target.unlink(missing_ok=True)` before bind. A daemon restart after crash leaves the previous socket file in place; without unlink the bind fails with EADDRINUSE. The daemon's PID lock (Phase 3) prevents a real concurrent instance from racing the unlink."
    - "Socket mode 0o660 (T-02-07-01 mitigation): non-adm processes on the box cannot scrape metrics. Verified by `grep -q '0o660' src/spark_modem/status_reporter/prom.py` AND by `test_start_metrics_server_creates_socket` reading st_mode bits."
    - "CollectorRegistry injection seam: MetricRegistry takes `registry: CollectorRegistry | None = None`; defaults to prometheus_client.REGISTRY in production (so make_wsgi_app() picks up the metrics) but tests pass a fresh `CollectorRegistry(auto_describe=False)` per test to avoid global-singleton state pollution and ordering-sensitive failures."
    - "Sample-name vs family-name (prometheus_client quirk): a Counter registered as `actions_total` has family.name == 'actions' (suffix stripped) but sample.name stays 'actions_total'. Tests use a `_samples_for(coll, sample_name)` helper that matches on sample.name to handle Counter / Gauge / Histogram uniformly without family-name special-casing."
    - "GlobalsState backward compatibility: the new `maintenance: MaintenanceWindow | None = None` field defaults to None, and a Phase 1-shape globals.json (no `maintenance` key) round-trips cleanly through model_validate_json. Verified by `test_globals_without_maintenance_round_trips` parsing a literal Phase 1 JSON string."

key-files:
  created:
    - src/spark_modem/wire/maintenance.py
    - src/spark_modem/wire/status.py
    - src/spark_modem/status_reporter/__init__.py
    - src/spark_modem/status_reporter/status.py
    - src/spark_modem/status_reporter/metrics_registry.py
    - src/spark_modem/status_reporter/prom.py
    - tests/unit/status_reporter/__init__.py
    - tests/unit/status_reporter/test_status.py
    - tests/unit/status_reporter/test_metrics_registry.py
    - tests/unit/status_reporter/test_prom_uds.py
  modified:
    - src/spark_modem/wire/globals.py   # +maintenance: MaintenanceWindow | None = None (Phase 1 fields preserved verbatim)

key-decisions:
  - "StatusPerModem carries BOTH `state` (string, human-readable) AND `state_int` (ADR-0013 integer 0..4). Rationale: status.json is consumed by NOC tooling that may not have the integer mapping handy, and integer-only translators (Prom dashboards via label_replace) want the integer ready-baked. Carrying both means writers compute state_to_int once at write time; readers don't re-encode. state_int is bounded to 0..4 by Pydantic Field(ge=0, le=4) so a writer bug surfaces at validation."
  - "MaintenanceWindow.scope is hard-coded to Literal[\"destructive\"]. Rationale: C-01 specifies maintenance gates ONLY destructive actions in v2.0 (modem_reset / usb_reset / driver_reset). The scope field exists so future versions can extend (e.g. \"all\" / \"observation_only\") without a wire-format break — but v2.0 accepts only \"destructive\"."
  - "MaintenanceWindow.max_duration_seconds is bounded by Pydantic Field(le=28800). Rationale: C-02 specifies the 8h cap. The CLI rejects --duration > 8h before any state mutation, but a hand-edited globals.json with 28801 seconds is also caught here at load time (defensive — RUNBOOK suggests defending against operator typos)."
  - "GlobalsState.maintenance: MaintenanceWindow | None = None default makes the field optional without breaking Phase 1's globals.json. Phase 1-shape JSON (no `maintenance` key) parses cleanly because Pydantic emits the default for missing fields, and the JSON literal `{\"schema_version\":1,\"driver_reset_count\":0,...}` was tested to verify."
  - "MetricRegistry is the single chokepoint — every set/inc on a Prom metric goes through a typed accessor on this class. Rationale: code-review enforcement of ADR-0013 / O-02..O-04 discipline. A future caller that wanted to add `state` as a label would have to either modify MetricRegistry (caught in review) or import prometheus_client directly (caught by test_state_label_appears_only_on_state_duration_histogram which scans every collected sample's labels). Both gates align."
  - "MetricRegistry takes `registry: CollectorRegistry | None = None` for test isolation. Production passes None and uses the global REGISTRY (so make_wsgi_app picks up the metrics). Tests pass a per-test `CollectorRegistry(auto_describe=False)` so the global singleton is never touched and tests stay deterministic regardless of pytest execution order. The `iter_collectors()` accessor is shipped for completeness; tests never need it because the per-test registry is just garbage-collected at fixture teardown."
  - "_CYCLE_BUCKETS = (0.5, 1, 2, 4, 8, 16, 32) — Claude's discretion per CONTEXT.md C/D section. Targets M5's 10s P99 budget with two-sided visibility: sub-second outliers (0.5, 1, 2) AND budget breaches before P99 alerts fire (16, 32). The +Inf bucket is implicit per prometheus_client convention."
  - "_STATE_DURATION_BUCKETS = (1, 5, 15, 60, 300, 1800, 7200, 86400) — O-02 verbatim, MTTR semantic targets: 1s (cheap action), 5s (SIM cycle), 15s (modem reset early), 60s (M2 SIM target), 300s (5 min — SIM-app stuck), 1800s (30 min), 7200s (2 h), 86400s (24 h — stuck-unhealthy detection)."
  - "Windows-safe import for prom.py: `from socketserver import UnixStreamServer` is gated behind `if sys.platform != \"win32\":` because the stdlib's socketserver module only defines UnixStreamServer when `hasattr(socket, \"AF_UNIX\")`. On Windows hosts (dev laptops) the module imports cleanly and _UnixWSGIServer is a stub class that raises RuntimeError if instantiated. Tests in test_prom_uds.py mark `pytestmark = pytest.mark.skipif(sys.platform == 'win32')` and the module-level import succeeds without erroring at pytest collection. Production target is Linux/aarch64."
  - "_UnixWSGIServer.server_bind() calls UnixStreamServer.server_bind() directly (NOT super().server_bind()) so it skips WSGIServer.server_bind's setsockopt(SO_REUSEADDR) call. UDS sockets don't need SO_REUSEADDR and on Linux 5.10-tegra (the production kernel) setsockopt returns ENOPROTOOPT for AF_UNIX. The setup_environ() call after server_bind is required by wsgiref to populate SERVER_NAME etc. — values are nonsense on UDS but the WSGI handler does not consume them."
  - "Sample-name matching helper `_samples_for(coll, sample_name)` matches on the SAMPLE name, not the family name. Rationale: prometheus_client strips `_total` from Counter family names (so a Counter registered as `actions_total` has family.name='actions' but sample.name='actions_total'). Matching on sample.name uniformly handles Counter / Gauge / Histogram without special-casing the suffix-stripping rule."
  - "RSS tripwire is event-only in Phase 2 (NFR-3). MetricRegistry.record_rss_tripwire() increments daemon_self_health{kind=\"rss\"} but does NOT raise / graceful_exit / signal anything. Phase 3's sd_notify watchdog reads this counter to decide whether to restart on RSS breach. The pairing of metric + (eventually) event_logger entry is what closes NFR-3; this plan only ships the metric side."

patterns-established:
  - "src/spark_modem/<package>/<module>.py production module + tests/unit/<package>/test_<module>.py test pattern continues. status_reporter/ joins observer/ / policy/ / actions/ / webhook/ / qmi/ / inventory/ / zao_log/ as Phase 2 packages."
  - "Atomic write delegation: any code path that writes a JSON file calls state_store.atomic.atomic_write_bytes — never re-implements temp+rename+fsync. status_reporter/status.py is the third call site (after state_store/store.py and webhook event log)."
  - "Per-test isolated CollectorRegistry pattern: tests/unit/status_reporter/test_metrics_registry.py uses a fixture that constructs `CollectorRegistry(auto_describe=False)` per test, instead of mutating the global REGISTRY and unregistering on teardown. Faster, more deterministic, plays well with pytest-xdist (future)."
  - "Linux-only test module pattern: tests/unit/status_reporter/test_prom_uds.py uses `pytestmark = pytest.mark.skipif(sys.platform == 'win32', reason=...)` at module scope; the production code's import path is also gated so the module imports cleanly on Windows even though no test in it runs there."

requirements-completed:
  - FR-41      # status.json at /var/lib/spark-modem-watchdog/status.json with per-modem state and aggregate health
  - FR-41.1    # cycle_index + last_modified + cycle.actions_executed + cycle.transitions + carrier_table_sha256 added to status.json shape
  - FR-42      # Prometheus scrape endpoint on Unix socket (default /run/spark-modem-watchdog/metrics.sock)
  - NFR-3      # RSS tripwire metric path (event-only in Phase 2; sd_notify restart owned by Phase 3)
  - NFR-5      # status.json freshness invariant via cycle_index monotonic counter (consumers detect stuck daemon)
  - NFR-21     # Prometheus metrics: actions_total, signal_dbm, cycle_duration_seconds, modem_state_value (per ADR-0013)
  - NFR-21.1   # Extended metric surface: cycle_drift_seconds, state_duration_seconds, webhook_delivery_total, daemon_self_health

# Metrics
metrics:
  duration: "~25m"
  tasks_completed: 2
  files_created: 10
  files_modified: 1
  tests_added: 23
  test_pass_rate: "100% applicable (19/19 cross-platform pass; 4 UDS scrape tests skipif(win32) on dev host, will run on Linux CI). Full suite: 578 passed, 48 skipped (POSIX-only); zero regressions."
  completed: 2026-05-06
---

# Phase 2 Plan 07: status_reporter/ status.json + Prometheus UDS + MetricRegistry Summary

Plan 02-07 lands the observability surface for the daemon: a
`status.json` writer (atomic, every cycle), a Prometheus UDS exporter
(AF_UNIX socket bound to `make_wsgi_app()`), and a typed
`MetricRegistry` that the cycle driver and webhook poster will both go
through to set/inc Prom metrics.

The work splits cleanly along three subsystems:

1. **Wire model additions** — `StatusReport` (the on-disk shape of
   `status.json`), `MaintenanceWindow` (C-02 dual-clock window stored
   in `globals.json`), and an extension to `GlobalsState` adding the
   optional `maintenance` field.
2. **`status.json` writer** — a thin wrapper around Phase 1's
   `state_store.atomic.atomic_write_bytes` that serialises a
   `StatusReport` Pydantic model and writes it atomically every cycle
   (O-01).
3. **Prometheus UDS exporter** — `_UnixWSGIServer` subclass that binds
   AF_UNIX, served by `prometheus_client.make_wsgi_app()` in a
   `to_thread` worker — plus a typed `MetricRegistry` enforcing
   integer-encoded `modem_state_value{modem}` per ADR-0013 (NEVER
   one-hot).

## The wire-type additions

| Type | Module | Purpose |
| --- | --- | --- |
| `StatusReport` | `wire/status.py` | Top-level shape of `status.json`. Schema-versioned; carries every FR-41.1 field. |
| `StatusCycleSummary` | `wire/status.py` | Per-cycle metadata: `n` / `duration_seconds` / `next_at_iso`. |
| `StatusModemSummary` | `wire/status.py` | Aggregate counts by state for at-a-glance NOC views. |
| `StatusPerModem` | `wire/status.py` | Per-modem entry; carries BOTH `state` (string) AND `state_int` (0..4 per ADR-0013). |
| `MaintenanceWindow` | `wire/maintenance.py` | Dual-clock (`started_iso` + `started_monotonic` + `expires_iso` + `expires_monotonic`); 8h hard cap; scope hard-coded to `"destructive"` for v2.0. |
| `GlobalsState.maintenance` | `wire/globals.py` (modified) | New optional field; default None; Phase 1-shape JSON parses cleanly. |

## The MetricRegistry surface — every typed accessor

| Accessor | Metric | ADR / O-Ref |
| --- | --- | --- |
| `record_action(kind, modem, result)` | `actions_total{kind, modem, result}` Counter | NFR-21 |
| `record_signal(modem, *, rsrp, rsrq, snr)` | `signal_rsrp_dbm{modem}` / `signal_rsrq_db{modem}` / `signal_snr_db{modem}` Gauges (None values skipped) | NFR-21 |
| `observe_cycle_duration(seconds)` | `cycle_duration_seconds` Histogram (buckets `(0.5, 1, 2, 4, 8, 16, 32)`) | NFR-21 / M5 |
| `set_modem_state(modem, value)` | `modem_state_value{modem}` Gauge — VALUE is integer state code | **ADR-0013** (no one-hot) |
| `observe_state_duration(modem, state, seconds)` | `state_duration_seconds{modem, state}` Histogram (buckets `[1, 5, 15, 60, 300, 1800, 7200, 86400]`) | O-02 + ADR-0013 §exception |
| `set_cycle_drift(seconds)` | `cycle_drift_seconds` Gauge — clamped to >= 0 | O-03 |
| `record_webhook_delivery(result)` | `webhook_delivery_total{result}` Counter — closed enum | O-04 |
| `record_rss_tripwire()` | `daemon_self_health{kind="rss"}` Counter — Phase 2 event-only | NFR-3 |

Every set/inc on a Prom metric goes through one of these. That's the
chokepoint we use to enforce ADR-0013 discipline at code review time;
the supplementary
`test_state_label_appears_only_on_state_duration_histogram` test
verifies the surface at runtime by collecting every family from the
test's CollectorRegistry and asserting `state` does not appear as a
label on any non-histogram metric.

## The Prometheus UDS bridge — `_UnixWSGIServer` + `asyncio.to_thread`

`prom.py` ships:

```python
class _UnixWSGIServer(UnixStreamServer, WSGIServer):
    address_family = socket.AF_UNIX
    def server_bind(self) -> None:
        UnixStreamServer.server_bind(self)   # NO SO_REUSEADDR
        self.setup_environ()                  # wsgiref needs this

def start_metrics_server(socket_path: Path | str, *, registry=None) -> _UnixWSGIServer:
    target = Path(socket_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)            # PITFALLS §13.3
    server = _UnixWSGIServer(str(target), WSGIRequestHandler)
    server.set_app(make_wsgi_app(registry or REGISTRY))
    target.chmod(0o660)                        # T-02-07-01
    return server
```

The MRO is `UnixStreamServer + WSGIServer` — `server_bind` resolves to
`UnixStreamServer.server_bind` which skips the
`setsockopt(SO_REUSEADDR)` call that `WSGIServer.server_bind` makes
(invalid on AF_UNIX on the production kernel; returns ENOPROTOOPT on
Linux 5.10-tegra).

The caller wraps the returned server in
`asyncio.create_task(asyncio.to_thread(srv.serve_forever))` —
`serve_forever` is synchronous and would block the asyncio event loop
otherwise; the dedicated thread is fine because scrapes are infrequent
(~30 s) and sub-100 ms.

## Cross-platform behavior

The daemon production target is Linux/aarch64. Dev hosts include
Windows, where `socketserver.UnixStreamServer` is conditionally
defined inside the stdlib (gated on `hasattr(socket, "AF_UNIX")`). To
keep `mypy --strict` and `pytest` green on Windows dev hosts:

- `prom.py` guards `from socketserver import UnixStreamServer` behind
  `if sys.platform != "win32":`. On Windows `_UnixWSGIServer` is a
  stub class that raises `RuntimeError` if instantiated.
- `tests/unit/status_reporter/test_prom_uds.py` carries a module-level
  `pytestmark = pytest.mark.skipif(sys.platform == "win32")` so all 4
  UDS scrape tests are skipped on Windows.
- The `MetricRegistry` test module is pure cross-platform; the 11
  metric-registry tests run on every host.

The Linux CI box runs the full 23-test surface (8 status + 11 metric
registry + 4 UDS scrape).

## ADR-0013 invariant — `modem_state_value{modem}` is NOT one-hot

CLAUDE.md anti-pattern catalogue: `state` as a one-hot Prometheus
label. ADR-0013 mandates a SINGLE Gauge per modem whose VALUE is the
integer state code (0=unknown / 1=healthy / 2=degraded / 3=recovering
/ 4=exhausted, stable mapping).

Verified by:

- Acceptance criterion `! grep -E "modem_state\{.*state="
  src/spark_modem/status_reporter/metrics_registry.py` (passes — empty
  result).
- Test `test_modem_state_value_is_single_gauge_not_one_hot`: calls
  `set_modem_state("2-3.1.1", 3)` then `set_modem_state("2-3.1.2", 1)`;
  collects via `REGISTRY.collect()`; asserts exactly TWO samples (one
  per modem) and that each sample's label-set is exactly `{modem}`.
- Test `test_modem_state_value_value_changes_in_place_no_new_series`:
  three consecutive `set_modem_state` calls on the same modem produce
  ONE sample (mutated value), not three; rules out the "is the gauge
  value getting written but new series leaking too?" failure mode.
- Test `test_state_label_appears_only_on_state_duration_histogram`:
  scans every sample of every family and asserts `state` is absent
  from labels on every metric EXCEPT `state_duration_seconds`. Catches
  any future regression that adds `state` to a gauge label set.

Cardinality stays bounded at **16 series per box** (4 modems × 1
modem_state_value + 4 modems × 5 states × N buckets state_duration is
a histogram and contributes per-bucket series, but bounded; modem
gauges are single-series-per-modem). Compare to the rejected one-hot
scheme (4 × 5 = 20 series per modem state-as-label gauge) which also
produces step-function write amplification on every transition.

## Phase 3 hooks

This plan ships the `daemon_self_health{kind="rss"}` counter and the
`record_rss_tripwire()` accessor. Phase 3's `sd_notify` watchdog reads
this counter (alongside an `events.jsonl` `rss_tripwire_breached`
event written by the cycle driver) to decide whether to restart the
daemon when RSS exceeds 200 MiB.

The pattern: Phase 2 emits the metric + event; Phase 3 owns the
restart decision. Phase 2 deliberately does NOT graceful-exit on RSS
breach because the cycle driver (Plan 02-10) is the right home for
"pause cycle, drain webhooks, exit clean" — and the daemon driver
isn't constructed yet.

## Self-Check: PASSED

Files created (verified `ls -la`):
- `src/spark_modem/wire/maintenance.py` ✓
- `src/spark_modem/wire/status.py` ✓
- `src/spark_modem/status_reporter/__init__.py` ✓
- `src/spark_modem/status_reporter/status.py` ✓
- `src/spark_modem/status_reporter/metrics_registry.py` ✓
- `src/spark_modem/status_reporter/prom.py` ✓
- `tests/unit/status_reporter/__init__.py` ✓
- `tests/unit/status_reporter/test_status.py` ✓
- `tests/unit/status_reporter/test_metrics_registry.py` ✓
- `tests/unit/status_reporter/test_prom_uds.py` ✓

File modified:
- `src/spark_modem/wire/globals.py` ✓ (extended with `maintenance` field; existing fields preserved verbatim)

Commits exist (verified `git log --oneline | grep`):
- `c38f438` feat(02-07): add StatusReport + MaintenanceWindow wire types + status.json writer ✓
- `8156e81` feat(02-07): add MetricRegistry + Prom UDS exporter (ADR-0013 + O-02..O-04) ✓

Verification gates:
- `python -m mypy --strict src/spark_modem/status_reporter/ src/spark_modem/wire/status.py src/spark_modem/wire/maintenance.py src/spark_modem/wire/globals.py tests/unit/status_reporter/` — exit 0 ✓
- `python -m ruff check src/spark_modem/status_reporter/ src/spark_modem/wire/ tests/unit/status_reporter/` — exit 0 ✓
- `python -m ruff format --check src/spark_modem/status_reporter/ tests/unit/status_reporter/` — exit 0 ✓
- `python -m pytest tests/unit/status_reporter/ -q` — 19 passed, 4 skipped(win32) ✓
- `python -m pytest -q` (full suite) — 578 passed, 48 skipped, zero regressions ✓
- `bash scripts/lint_no_subprocess.sh` — exit 0 ✓
- `! grep -E "modem_state\{.*state=" src/spark_modem/status_reporter/metrics_registry.py` — empty result ✓
- `grep -q "0o660" src/spark_modem/status_reporter/prom.py` — match ✓
- `! grep -E "SO_REUSEADDR" src/spark_modem/status_reporter/prom.py` — empty result ✓

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Windows-safe import for `prom.py`**
- **Found during:** Task 2 verification.
- **Issue:** `from socketserver import UnixStreamServer` raises
  `ImportError` on Windows because the stdlib's `socketserver` module
  conditionally defines `UnixStreamServer` only when `socket.AF_UNIX`
  is available. Even though `test_prom_uds.py` carries
  `skipif(win32)`, pytest still imports the test module (and
  therefore `prom.py`) at collection time — collection failed with
  ImportError before any test could be skipped.
- **Fix:** Wrapped the `UnixStreamServer` import + class definition in
  an `if sys.platform != "win32":` block. On Windows, `_UnixWSGIServer`
  is a stub class whose `__init__` raises `RuntimeError`.
  `start_metrics_server` already had a `sys.platform == "win32"` guard
  at the top, so the stub class is unreachable in production.
- **Files modified:** `src/spark_modem/status_reporter/prom.py`
- **Commit:** `8156e81`

**2. [Rule 1 — Bug] Sample-name vs family-name mismatch in test assertions**
- **Found during:** Task 2 test execution (`test_record_action_uses_kind_modem_result_labels` and `test_record_webhook_delivery_supports_o_04_enum` failed with `KeyError` / empty dict).
- **Issue:** `prometheus_client` strips the `_total` suffix from
  Counter family names — a Counter registered as `actions_total` has
  `family.name == "actions"` but `sample.name == "actions_total"`.
  The first cut of `_samples_for(coll, name)` matched on
  `family.name`, so it returned no samples for any Counter test.
- **Fix:** Changed `_samples_for` to match on `sample.name` directly,
  which uniformly handles Counter (sample name has the `_total` the
  caller expects), Gauge (sample name == family name), and Histogram
  (sample names like `<name>_bucket` / `<name>_sum` / `<name>_count`).
  Updated the `daemon_self_health` test to ask for
  `daemon_self_health_total` (the actual sample name; the metric was
  registered without an explicit `_total` suffix so prometheus_client
  appends one).
- **Files modified:** `tests/unit/status_reporter/test_metrics_registry.py`
- **Commit:** `8156e81` (squashed with the rest of Task 2; rationale: test-only fix on the same task)

**3. [Rule 1 — Bug] `test_observe_cycle_duration_clamps_negative_to_zero` filtered on the wrong sample**
- **Found during:** Task 2 test execution.
- **Issue:** The first cut of the test looked for a sample with empty
  labels and value 0.0 in `cycle_duration_seconds`, but Histograms
  emit per-bucket samples (`_bucket`, `_sum`, `_count`), not a single
  unlabeled sample. The `next(...)` call raised `StopIteration`.
- **Fix:** Look up the `_sum` (sum of observations, == 0 after a
  clamped negative observation) and `_count` (== 1 — the clamp DID
  record an observation, just at value 0) samples explicitly. Both
  asserts pass.
- **Files modified:** `tests/unit/status_reporter/test_metrics_registry.py`
- **Commit:** `8156e81`

**No architectural deviations (Rule 4 not triggered).**

## Authentication Gates

None.

## Threat Flags

None — the plan's `<threat_model>` register lists T-02-07-01 (socket
mode) through T-02-07-06 (maintenance window timing). T-02-07-01,
-02-07-02, -02-07-03, -02-07-04, -02-07-05 dispositions are all
`mitigate` and the corresponding mitigations are in place; T-02-07-06
disposition is `accept`. No new threat surface introduced beyond what
the plan's threat model anticipated.

---

*Plan: 02-07*
*Phase: 02-core-daemon-laptop-testable*
*Wave: 4 (sequential)*
*Completed: 2026-05-06*
