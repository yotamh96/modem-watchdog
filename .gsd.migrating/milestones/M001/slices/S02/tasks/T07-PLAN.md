# T07: 02-core-daemon-laptop-testable 07

**Slice:** S02 — **Milestone:** M001

## Description

Plan 02-07 lands the observability surface: status.json writer + Prometheus
UDS exporter + the metric registry that's wired into the cycle driver.

The work splits cleanly along three subsystems:
1. Wire model additions: `StatusReport` (the on-disk shape of status.json),
   `MaintenanceWindow` (C-02 dual-clock window stored in globals.json),
   plus extending `GlobalsState` with `maintenance`.
2. `status.json` writer — a thin wrapper around Phase 1's
   `state_store.atomic.atomic_write_bytes` that serialises a `StatusReport`
   pydantic model and writes it atomically every cycle (O-01).
3. Prometheus UDS exporter — `_UnixWSGIServer` subclass that binds AF_UNIX,
   served by `prometheus_client.make_wsgi_app()` in a `to_thread` worker;
   plus a typed `MetricRegistry` that the cycle driver and webhook poster
   use to record metrics. Integer-encoded `modem_state_value{modem}` per
   ADR-0013 — never one-hot.

Output: `wire/status.py` + `wire/maintenance.py` + extended `wire/globals.py`
+ `status_reporter/{status,prom,metrics_registry}.py` + parametrized tests
including a Linux-only UDS scrape integration test (skipif win32) and a
Windows-friendly metric-registry test.

## Must-Haves

- [ ] "status.json is written every cycle via state_store.atomic.atomic_write_bytes (FR-41 + atomic guarantees from Phase 1)."
- [ ] "StatusReport (BaseWire frozen) carries ts_iso (last_modified), cycle_index, cycle.actions_executed, cycle.transitions, carrier_table_sha256, per-modem state-as-integer (ADR-0013), maintenance_active_until_iso when active."
- [ ] "GlobalsState is extended with a `maintenance` field per CONTEXT.md C-02 (active, scope, started_iso, started_monotonic, expires_iso, expires_monotonic, max_duration_seconds=28800)."
- [ ] "MetricRegistry exposes typed accessors for every NFR-21/NFR-21.1 metric: actions_total, signal_rsrp_dbm/rsrq_db/snr_db, cycle_duration_seconds, modem_state_value (integer), state_duration_seconds, cycle_drift_seconds, webhook_delivery_total, daemon_self_health (RSS tripwire)."
- [ ] "Prom UDS exporter binds AF_UNIX socket at config.metrics_socket_path, mode 0o660; cleans stale socket on restart; serves via wsgiref.simple_server.WSGIRequestHandler under asyncio.to_thread."
- [ ] "Cardinality stays bounded: modem_state_value{modem} is a single Gauge (integer), NOT one-hot label (ADR-0013); state_duration_seconds buckets are exactly [1, 5, 15, 60, 300, 1800, 7200, 86400] (O-02)."
- [ ] "psutil RSS tripwire emits an event + increments daemon_self_health counter when RSS > 200 MiB; does NOT graceful-exit in Phase 2 (Phase 3 sd_notify watchdog owns restart)."
- [ ] "Windows dev-host: the AF_UNIX exporter is replaced by FakeMetricsServer that records set/inc calls (Win10 1803+ supports AF_UNIX but the wsgiref+asyncio.to_thread bridge is fragile; tests mark skipif(win32))."

## Files

- `src/spark_modem/wire/status.py`
- `src/spark_modem/wire/maintenance.py`
- `src/spark_modem/wire/globals.py`
- `src/spark_modem/status_reporter/__init__.py`
- `src/spark_modem/status_reporter/status.py`
- `src/spark_modem/status_reporter/prom.py`
- `src/spark_modem/status_reporter/metrics_registry.py`
- `tests/unit/status_reporter/__init__.py`
- `tests/unit/status_reporter/test_status.py`
- `tests/unit/status_reporter/test_metrics_registry.py`
- `tests/unit/status_reporter/test_prom_uds.py`
