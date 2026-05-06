"""status.json wire model — FR-41 + FR-41.1 + ADR-0013.

Written every cycle via ``state_store.atomic.atomic_write_bytes`` (O-01).
Consumers (NOC, ``ctl status``, fleet agent) parse this back via Pydantic
with ``extra='forbid'`` — a future drift in the daemon's writer is
detected at the consumer boundary.

Per-modem state appears in BOTH a string form (``state``) for
human-readability and an integer form (``state_int``) per ADR-0013, so
the on-disk payload is consumable by integer-only Prom translators
without re-encoding.
"""

from __future__ import annotations

from pydantic import Field

from spark_modem.wire._base import BaseWire
from spark_modem.wire.versioning import CURRENT_SCHEMA_VERSION


class StatusCycleSummary(BaseWire):
    """Per-cycle metadata block in ``status.json``."""

    n: int = Field(ge=0)
    """Cycle count (== ``StatusReport.cycle_index``)."""

    duration_seconds: float = Field(ge=0.0)
    """Wall-clock duration of the cycle that just finished."""

    next_at_iso: str | None = None
    """Wall-clock ISO-8601 of the next scheduled cycle (None if shutting down)."""


class StatusModemSummary(BaseWire):
    """Aggregate counts of modems by state for at-a-glance NOC views."""

    expected_modems: int = Field(ge=0)
    healthy: int = Field(default=0, ge=0)
    degraded: int = Field(default=0, ge=0)
    recovering: int = Field(default=0, ge=0)
    rf_blocked: int = Field(default=0, ge=0)
    exhausted: int = Field(default=0, ge=0)
    disconnected: int = Field(default=0, ge=0)
    unknown: int = Field(default=0, ge=0)


class StatusPerModem(BaseWire):
    """Per-modem entry in ``status.json``.

    ``state`` is the human-readable 5-state name. ``state_int`` is the
    canonical ADR-0013 integer encoding (0..4); writers MUST set both
    consistently using ``spark_modem.wire.state.state_to_int``.
    """

    usb_path: str
    cdc_wdm: str | None = None
    line: int | None = None
    state: str
    state_int: int = Field(ge=0, le=4)
    rf_blocked: bool = False
    ipv4: str | None = None
    cause: str | None = None
    last_action_iso: str | None = None


class StatusReport(BaseWire):
    """Top-level shape of ``status.json``. Written every cycle (FR-41 / O-01)."""

    schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, ge=1)
    last_modified: str
    """Wall-clock ISO-8601 of the write that produced this file."""

    cycle_index: int = Field(ge=0)
    """Monotonic cycle counter; lets consumers detect a stuck daemon (FR-41.1)."""

    cycle: StatusCycleSummary
    summary: StatusModemSummary
    modems: list[StatusPerModem] = Field(default_factory=list)

    cycle_actions_executed: int = Field(default=0, ge=0)
    """Count of actions that executed during the last cycle (FR-41.1)."""

    cycle_transitions: int = Field(default=0, ge=0)
    """Count of state transitions observed during the last cycle (FR-41.1)."""

    carrier_table_sha256: str = Field(
        default="",
        description="hex digest of /etc/spark-modem-watchdog/conf.d/00-carriers.yaml",
    )
    """Lets NOC verify carrier-table propagation across the fleet (FR-41.1 / M-17)."""

    maintenance_active_until_iso: str | None = None
    """When non-None, the wall-clock ISO-8601 expiry of the active maintenance window."""
