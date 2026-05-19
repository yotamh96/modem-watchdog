---
id: T07
parent: S02
milestone: M001
provides:
  - wire/maintenance.py — MaintenanceWindow BaseWire (C-02): dual-clock fields (started_iso + started_monotonic + expires_iso + expires_monotonic), 8-hour hard cap (max_duration_seconds le=28800), scope=Literal["destructive"]
  - wire/status.py — StatusReport / StatusCycleSummary / StatusModemSummary / StatusPerModem (FR-41 + FR-41.1 + ADR-0013): cycle_index, last_modified, cycle.{n,duration_seconds,next_at_iso}, summary aggregate counts, modems[].state_int (0..4), cycle_actions_executed, cycle_transitions, carrier_table_sha256, maintenance_active_until_iso
  - wire/globals.py — GlobalsState extended with optional MaintenanceWindow (Phase 1-shape globals.json without `maintenance` still parses cleanly; default None)
  - status_reporter/status.py — write_status_json(path, report) wraps state_store.atomic.atomic_write_bytes (never re-implements temp+rename+fsync); single function, ≤20 lines
  - status_reporter/metrics_registry.py — MetricRegistry typed accessors (record_action / record_signal / observe_cycle_duration / set_modem_state / observe_state_duration / set_cycle_drift / record_webhook_delivery / record_rss_tripwire); ADR-0013 integer encoding enforced; 10 metric names exposed via metric_names()
  - status_reporter/prom.py — _UnixWSGIServer (UnixStreamServer + WSGIServer MRO; no SO_REUSEADDR); start_metrics_server(socket_path, *, registry=None) with 0o660 mode + stale-socket unlink + parent-dir mkdir; Windows-safe at import time (POSIX guard)
  - status_reporter/__init__.py — package docstring listing the three submodules
  - 23 tests across 3 files (test_status 8 / test_metrics_registry 11 / test_prom_uds 4 — Linux-only). All cross-platform tests pass; UDS scrape tests skipif(win32).
requires: []
affects: []
key_files: []
key_decisions: []
patterns_established: []
observability_surfaces: []
drill_down_paths: []
duration: 
verification_result: passed
completed_at: 
blocker_discovered: false
---
# T07: 02-core-daemon-laptop-testable 07

**# Phase 2 Plan 07: status_reporter/ status.json + Prometheus UDS + MetricRegistry Summary**

## What Happened

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
