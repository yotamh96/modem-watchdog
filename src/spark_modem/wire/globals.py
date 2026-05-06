"""Globals state (driver_reset cooldown, qmi_proxy uptime tracking, maintenance window)."""

from __future__ import annotations

from pydantic import Field

from spark_modem.wire._base import BaseWire
from spark_modem.wire.maintenance import MaintenanceWindow
from spark_modem.wire.versioning import CURRENT_SCHEMA_VERSION


class GlobalsState(BaseWire):
    """Daemon-global counters and cooldown state. Persisted at globals.json."""

    schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, ge=1)
    driver_reset_count: int = Field(default=0, ge=0)
    last_driver_reset_monotonic: float | None = None
    last_driver_reset_iso: str | None = None
    qmi_proxy_uptime_seconds: float = Field(default=0.0, ge=0.0)

    # Phase 2 / C-02: dual-clock maintenance window. None when no window
    # is active. Defaults to None so existing v1-shaped Phase 1 globals
    # files (without maintenance) parse cleanly.
    maintenance: MaintenanceWindow | None = None
