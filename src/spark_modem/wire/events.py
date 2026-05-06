"""events.jsonl variants. discriminator='kind' on the union.

Each variant corresponds to one EventKind. Events are append-only to
events.jsonl and are never mutated after writing.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from spark_modem.wire._base import BaseWire
from spark_modem.wire.enums import (
    ActionKind,
    ActionResult,
    DaemonStopReason,
    DowngradeReason,
)
from spark_modem.wire.versioning import CURRENT_SCHEMA_VERSION


class _EventBase(BaseWire):
    """Common fields for all events.jsonl entries."""

    schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, ge=1)
    ts_iso: str


class ActionPlanned(_EventBase):
    """Policy engine decided to attempt an action on a modem."""

    kind: Literal["action_planned"] = "action_planned"
    usb_path: str
    action: ActionKind
    reason: str
    dry_run: bool = False


class ActionExecuted(_EventBase):
    """An action was executed (regardless of outcome)."""

    kind: Literal["action_executed"] = "action_executed"
    usb_path: str
    action: ActionKind
    result: ActionResult
    duration_seconds: float = Field(ge=0.0)


class ActionFailed(_EventBase):
    """An action raised an exception / returned a non-recoverable error.

    M-15: failure_reason is surfaced so the operator and policy engine can
    optionally accelerate the recovery ladder.
    """

    kind: Literal["action_failed"] = "action_failed"
    usb_path: str
    action: ActionKind
    failure_reason: str


class StateTransition(_EventBase):
    """A modem's state machine transitioned to a new top-level state."""

    kind: Literal["state_transition"] = "state_transition"
    usb_path: str
    # Literal not used here so old/legacy state names don't break replay.
    from_state: str
    to_state: str
    cause: str
    action: ActionKind | None = None
    dry_run: bool = False


class DaemonStarted(_EventBase):
    """Daemon process started successfully."""

    kind: Literal["daemon_started"] = "daemon_started"
    version: str
    bundled_python_version: str


class DaemonStopped(_EventBase):
    """Daemon process is stopping (M-6: reason enum for restart tracking)."""

    kind: Literal["daemon_stopped"] = "daemon_stopped"
    reason: DaemonStopReason
    uptime_seconds: float = Field(ge=0.0)


class SchemaDowngradePending(_EventBase):
    """A state file with an older schema_version was found.

    ADR-0004: non-destructive downgrade — the original file is preserved as a
    .from-v<N>.json shadow; the daemon writes a fresh default at CURRENT_SCHEMA_VERSION.
    """

    kind: Literal["schema_downgrade_pending"] = "schema_downgrade_pending"
    file_path: str
    from_version: int
    to_version: int
    shadow_path: str
    reason: DowngradeReason


class UsbPathMismatch(_EventBase):
    """The usb_path recorded in a state file does not match sysfs.

    S-02: inventory cross-check. The daemon refuses to start on mismatch to
    prevent a renumbered cdc-wdmN from silently inheriting another modem's
    state.
    """

    kind: Literal["usb_path_mismatch"] = "usb_path_mismatch"
    file_usb_path: str
    sysfs_usb_path: str
    cdc_wdm: str


class MaintenanceWindowStarted(_EventBase):
    """A maintenance window was opened (suppresses destructive actions)."""

    kind: Literal["maintenance_window_started"] = "maintenance_window_started"
    operator: str = ""
    duration_seconds: float = Field(gt=0.0, le=8 * 3600.0)
    reason: str = ""


class MaintenanceWindowEnded(_EventBase):
    """A maintenance window closed (by expiry or operator command)."""

    kind: Literal["maintenance_window_ended"] = "maintenance_window_ended"
    reason: Literal["expired", "operator_off"] = "expired"


Event = Annotated[
    ActionPlanned
    | ActionExecuted
    | ActionFailed
    | StateTransition
    | DaemonStarted
    | DaemonStopped
    | SchemaDowngradePending
    | UsbPathMismatch
    | MaintenanceWindowStarted
    | MaintenanceWindowEnded,
    Field(discriminator="kind"),
]
"""One discriminated-union type for parsing events.jsonl back."""

EventAdapter: TypeAdapter[Event] = TypeAdapter(Event)
"""Use EventAdapter.validate_python(line_dict) or .validate_json(raw_line)."""
