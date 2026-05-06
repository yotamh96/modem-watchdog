"""Webhook payload and envelope.

ADR-0011 (drafted in Plan 07): HMAC-SHA256 signing in v2.0 + X-Spark-Timestamp
replay-protection header. Phase 1 defines the payload shape; Phase 2 implements
the WebhookPoster (signing, retry queue, dedup, pre-resolved DNS).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from spark_modem.wire._base import BaseWire
from spark_modem.wire.enums import ActionKind, DaemonStopReason
from spark_modem.wire.versioning import CURRENT_SCHEMA_VERSION


class _WebhookBase(BaseWire):
    """Common fields for all webhook payloads."""

    schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, ge=1)
    ts_iso: str
    # M-2: dedup window. dedup_count > 0 means this payload coalesces multiple
    # transitions; dedup_window_ends_iso is the wall-clock end of the window.
    dedup_count: int = Field(default=0, ge=0)
    dedup_window_ends_iso: str | None = None


class HealthyToDegraded(_WebhookBase):
    """A modem transitioned from healthy to degraded."""

    kind: Literal["healthy_to_degraded"] = "healthy_to_degraded"
    modem_usb_path: str
    prior_state: str
    new_state: str
    reason: str


class RecoveringToExhausted(_WebhookBase):
    """A modem has exhausted the full recovery ladder (M-4)."""

    kind: Literal["recovering_to_exhausted"] = "recovering_to_exhausted"
    modem_usb_path: str
    action_chain: list[ActionKind]
    exhaustion_reason: str


class DaemonRestart(_WebhookBase):
    """Daemon restarted unexpectedly (M-6)."""

    kind: Literal["daemon_restart"] = "daemon_restart"
    reason: DaemonStopReason
    prior_run_uptime_seconds: float = Field(ge=0.0)


class ActionFailedWebhook(_WebhookBase):
    """A recovery action failed. Named ActionFailedWebhook to avoid import collision
    with events.ActionFailed (same kind string, different union namespace).
    """

    kind: Literal["action_failed"] = "action_failed"
    modem_usb_path: str
    action: ActionKind
    failure_reason: str


WebhookPayload = Annotated[
    HealthyToDegraded | RecoveringToExhausted | DaemonRestart | ActionFailedWebhook,
    Field(discriminator="kind"),
]

WebhookPayloadAdapter: TypeAdapter[WebhookPayload] = TypeAdapter(WebhookPayload)


class WebhookEnvelope(BaseWire):
    """The thing that's actually POSTed (signing handled by Phase 2 WebhookPoster).

    signature_header_value: HMAC-SHA256 hex of raw body bytes (Phase 2 fills).
    timestamp_header_value: Unix timestamp string (Phase 2 fills).

    Phase 1 defines the shape; Phase 2 writes a `sign(payload, secret) -> envelope`
    helper that consumes this type.
    """

    payload: WebhookPayload
    signature_header_value: str = ""
    timestamp_header_value: str = ""
