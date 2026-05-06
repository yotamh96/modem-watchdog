"""Public surface of the spark_modem wire types.

Every Phase 2/3/4 module imports from here. Adding a type here is a
deliberate API surface change.
"""

from spark_modem.wire._base import BaseWire
from spark_modem.wire.carriers import CarrierEntry, CarrierTable
from spark_modem.wire.diag import (
    Diag,
    Issue,
    ModemSnapshot,
    PlannedAction,
    SignalSnapshot,
    Who,
    WhoHost,
    WhoModem,
)
from spark_modem.wire.enums import (
    ActionKind,
    ActionResult,
    DaemonStopReason,
    DowngradeReason,
    EventKind,
    IssueCategory,
    IssueDetail,
    RegistrationState,
    WebhookEventKind,
)
from spark_modem.wire.events import (
    ActionExecuted,
    ActionFailed,
    ActionPlanned,
    DaemonStarted,
    DaemonStopped,
    Event,
    EventAdapter,
    MaintenanceWindowEnded,
    MaintenanceWindowStarted,
    SchemaDowngradePending,
    StateTransition,
    UsbPathMismatch,
)
from spark_modem.wire.globals import GlobalsState
from spark_modem.wire.identity import Identity
from spark_modem.wire.state import ModemState, state_to_int
from spark_modem.wire.versioning import (
    CURRENT_SCHEMA_VERSION,
    SchemaVersionTooNew,
    shadow_filename,
    validate_schema_version,
)
from spark_modem.wire.webhook import (
    ActionFailedWebhook,
    DaemonRestart,
    HealthyToDegraded,
    RecoveringToExhausted,
    WebhookEnvelope,
    WebhookPayload,
    WebhookPayloadAdapter,
)

__all__ = [  # noqa: RUF022 — grouped by domain for readability
    # Base
    "BaseWire",
    # Versioning
    "CURRENT_SCHEMA_VERSION",
    "SchemaVersionTooNew",
    "shadow_filename",
    "validate_schema_version",
    # Enums
    "ActionKind",
    "ActionResult",
    "DaemonStopReason",
    "DowngradeReason",
    "EventKind",
    "IssueCategory",
    "IssueDetail",
    "RegistrationState",
    "WebhookEventKind",
    # Diag
    "Diag",
    "Issue",
    "ModemSnapshot",
    "PlannedAction",
    "SignalSnapshot",
    "Who",
    "WhoHost",
    "WhoModem",
    # State
    "ModemState",
    "state_to_int",
    # Identity / Globals / Carriers
    "Identity",
    "GlobalsState",
    "CarrierEntry",
    "CarrierTable",
    # Events
    "Event",
    "EventAdapter",
    "ActionExecuted",
    "ActionFailed",
    "ActionPlanned",
    "DaemonStarted",
    "DaemonStopped",
    "MaintenanceWindowEnded",
    "MaintenanceWindowStarted",
    "SchemaDowngradePending",
    "StateTransition",
    "UsbPathMismatch",
    # Webhook
    "ActionFailedWebhook",
    "DaemonRestart",
    "HealthyToDegraded",
    "RecoveringToExhausted",
    "WebhookEnvelope",
    "WebhookPayload",
    "WebhookPayloadAdapter",
]
