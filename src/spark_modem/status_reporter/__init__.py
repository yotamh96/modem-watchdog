"""status_reporter/ — observability surface (Phase 2 Plan 02-07).

Submodules:
  - status: ``status.json`` writer (atomic, every cycle / FR-41 / O-01).
  - prom: Prometheus UDS exporter (``_UnixWSGIServer`` + AF_UNIX socket).
  - metrics_registry: typed ``MetricRegistry`` — single chokepoint for
    every set/inc, ADR-0013 integer-encoded ``modem_state_value``.
"""
