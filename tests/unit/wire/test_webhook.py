"""Tests for src.spark_modem.wire.webhook — WebhookPayload variants."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from spark_modem.wire.enums import ActionKind, DaemonStopReason
from spark_modem.wire.webhook import (
    ActionFailedWebhook,
    DaemonRestart,
    HealthyToDegraded,
    RecoveringToExhausted,
    WebhookEnvelope,
    WebhookPayloadAdapter,
)

# ---------------------------------------------------------------------------
# WebhookPayload base fields (dedup, ts_iso, schema_version)
# ---------------------------------------------------------------------------


def test_healthy_to_degraded_has_dedup_fields() -> None:
    """WebhookPayload has dedup_count and dedup_window_ends_iso (M-2 coalescing)."""
    p = HealthyToDegraded(
        kind="healthy_to_degraded",
        ts_iso="2026-05-06T00:00:00+00:00",
        modem_usb_path="2-3.1.1",
        prior_state="healthy",
        new_state="degraded",
        reason="registration/not_registered_searching",
    )
    assert p.dedup_count == 0
    assert p.dedup_window_ends_iso is None
    assert p.schema_version == 1


# ---------------------------------------------------------------------------
# HealthyToDegraded
# ---------------------------------------------------------------------------


def test_healthy_to_degraded_constructs() -> None:
    """HealthyToDegraded constructs with required fields."""
    p = HealthyToDegraded(
        kind="healthy_to_degraded",
        ts_iso="2026-05-06T00:00:00+00:00",
        modem_usb_path="2-3.1.1",
        prior_state="healthy",
        new_state="degraded",
        reason="registration failure",
        dedup_count=2,
        dedup_window_ends_iso="2026-05-06T00:01:00+00:00",
    )
    assert p.modem_usb_path == "2-3.1.1"
    assert p.dedup_count == 2


# ---------------------------------------------------------------------------
# RecoveringToExhausted
# ---------------------------------------------------------------------------


def test_recovering_to_exhausted_constructs() -> None:
    """RecoveringToExhausted constructs with action_chain list."""
    p = RecoveringToExhausted(
        kind="recovering_to_exhausted",
        ts_iso="2026-05-06T00:00:00+00:00",
        modem_usb_path="2-3.1.1",
        action_chain=[ActionKind.SOFT_RESET, ActionKind.MODEM_RESET, ActionKind.USB_RESET],
        exhaustion_reason="all ladder actions exhausted",
    )
    assert len(p.action_chain) == 3
    assert p.action_chain[0] == ActionKind.SOFT_RESET


# ---------------------------------------------------------------------------
# DaemonRestart
# ---------------------------------------------------------------------------


def test_daemon_restart_constructs() -> None:
    """DaemonRestart has reason: DaemonStopReason and prior_run_uptime_seconds."""
    p = DaemonRestart(
        kind="daemon_restart",
        ts_iso="2026-05-06T00:00:00+00:00",
        reason=DaemonStopReason.CRASH,
        prior_run_uptime_seconds=3600.0,
    )
    assert p.reason == DaemonStopReason.CRASH
    assert p.prior_run_uptime_seconds == 3600.0


def test_daemon_restart_rejects_negative_uptime() -> None:
    """prior_run_uptime_seconds must be >= 0."""
    with pytest.raises(ValidationError):
        DaemonRestart(
            kind="daemon_restart",
            ts_iso="2026-05-06T00:00:00+00:00",
            reason=DaemonStopReason.CRASH,
            prior_run_uptime_seconds=-1.0,
        )


# ---------------------------------------------------------------------------
# ActionFailedWebhook
# ---------------------------------------------------------------------------


def test_action_failed_webhook_constructs() -> None:
    """ActionFailedWebhook (distinct from events.ActionFailed) constructs."""
    p = ActionFailedWebhook(
        kind="action_failed",
        ts_iso="2026-05-06T00:00:00+00:00",
        modem_usb_path="2-3.1.1",
        action=ActionKind.USB_RESET,
        failure_reason="usb_reset command timed out",
    )
    assert p.failure_reason == "usb_reset command timed out"


# ---------------------------------------------------------------------------
# WebhookPayload union — discriminator dispatch
# ---------------------------------------------------------------------------


def test_webhook_payload_adapter_dispatches_healthy_to_degraded() -> None:
    """WebhookPayloadAdapter dispatches kind='healthy_to_degraded'."""
    raw = {
        "kind": "healthy_to_degraded",
        "ts_iso": "2026-05-06T00:00:00+00:00",
        "modem_usb_path": "2-3.1.1",
        "prior_state": "healthy",
        "new_state": "degraded",
        "reason": "registration failure",
        "schema_version": 1,
    }
    p = WebhookPayloadAdapter.validate_python(raw)
    assert isinstance(p, HealthyToDegraded)


def test_webhook_payload_adapter_dispatches_recovering_to_exhausted() -> None:
    """WebhookPayloadAdapter dispatches kind='recovering_to_exhausted'."""
    raw = {
        "kind": "recovering_to_exhausted",
        "ts_iso": "2026-05-06T00:00:00+00:00",
        "modem_usb_path": "2-3.1.1",
        "action_chain": ["soft_reset", "modem_reset"],
        "exhaustion_reason": "exhausted",
        "schema_version": 1,
    }
    p = WebhookPayloadAdapter.validate_python(raw)
    assert isinstance(p, RecoveringToExhausted)


def test_webhook_payload_adapter_dispatches_daemon_restart() -> None:
    """WebhookPayloadAdapter dispatches kind='daemon_restart'."""
    raw = {
        "kind": "daemon_restart",
        "ts_iso": "2026-05-06T00:00:00+00:00",
        "reason": "crash",
        "prior_run_uptime_seconds": 1800.0,
        "schema_version": 1,
    }
    p = WebhookPayloadAdapter.validate_python(raw)
    assert isinstance(p, DaemonRestart)


def test_webhook_payload_adapter_dispatches_action_failed() -> None:
    """WebhookPayloadAdapter dispatches kind='action_failed' to ActionFailedWebhook."""
    raw = {
        "kind": "action_failed",
        "ts_iso": "2026-05-06T00:00:00+00:00",
        "modem_usb_path": "2-3.1.1",
        "action": "usb_reset",
        "failure_reason": "timeout",
        "schema_version": 1,
    }
    p = WebhookPayloadAdapter.validate_python(raw)
    assert isinstance(p, ActionFailedWebhook)


# ---------------------------------------------------------------------------
# WebhookEnvelope
# ---------------------------------------------------------------------------


def test_webhook_envelope_constructs() -> None:
    """WebhookEnvelope wraps a payload; signature/timestamp are empty (Phase 2 fills)."""
    payload = HealthyToDegraded(
        kind="healthy_to_degraded",
        ts_iso="2026-05-06T00:00:00+00:00",
        modem_usb_path="2-3.1.1",
        prior_state="healthy",
        new_state="degraded",
        reason="test",
    )
    env = WebhookEnvelope(
        payload=payload,
        signature_header_value="",
        timestamp_header_value="",
    )
    assert env.signature_header_value == ""
    assert isinstance(env.payload, HealthyToDegraded)
