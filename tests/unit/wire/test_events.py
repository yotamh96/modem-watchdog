"""Tests for src.spark_modem.wire.events — events.jsonl union variants."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from spark_modem.wire.enums import ActionKind, ActionResult, DaemonStopReason, DowngradeReason
from spark_modem.wire.events import (
    ActionExecuted,
    ActionFailed,
    ActionPlanned,
    DaemonStarted,
    DaemonStopped,
    EventAdapter,
    MaintenanceWindowEnded,
    MaintenanceWindowStarted,
    SchemaDowngradePending,
    StateTransition,
    UsbPathMismatch,
)

# ---------------------------------------------------------------------------
# Individual event models
# ---------------------------------------------------------------------------


def test_action_planned_constructs() -> None:
    """ActionPlanned constructs with required fields."""
    e = ActionPlanned(
        kind="action_planned",
        ts_iso="2026-05-06T00:00:00+00:00",
        usb_path="2-3.1.1",
        action=ActionKind.SOFT_RESET,
        reason="registration_failure",
    )
    assert e.kind == "action_planned"
    assert e.schema_version == 1


def test_action_executed_constructs() -> None:
    """ActionExecuted constructs."""
    e = ActionExecuted(
        kind="action_executed",
        ts_iso="2026-05-06T00:00:00+00:00",
        usb_path="2-3.1.1",
        action=ActionKind.SOFT_RESET,
        result=ActionResult.SUCCESS,
        duration_seconds=5.2,
    )
    assert e.result == ActionResult.SUCCESS


def test_action_failed_has_failure_reason() -> None:
    """ActionFailed has a failure_reason field (M-15)."""
    e = ActionFailed(
        kind="action_failed",
        ts_iso="2026-05-06T00:00:00+00:00",
        usb_path="2-3.1.1",
        action=ActionKind.MODEM_RESET,
        failure_reason="qmicli timed out",
    )
    assert e.failure_reason == "qmicli timed out"


def test_state_transition_constructs() -> None:
    """StateTransition constructs."""
    e = StateTransition(
        kind="state_transition",
        ts_iso="2026-05-06T00:00:00+00:00",
        usb_path="2-3.1.1",
        from_state="healthy",
        to_state="degraded",
        cause="registration/not_registered_searching",
    )
    assert e.from_state == "healthy"


def test_daemon_started_constructs() -> None:
    """DaemonStarted constructs."""
    e = DaemonStarted(
        kind="daemon_started",
        ts_iso="2026-05-06T00:00:00+00:00",
        version="2.0.0",
        bundled_python_version="3.12.13",
    )
    assert e.version == "2.0.0"


def test_daemon_stopped_has_reason_enum() -> None:
    """DaemonStopped has reason: DaemonStopReason (M-6)."""
    e = DaemonStopped(
        kind="daemon_stopped",
        ts_iso="2026-05-06T00:00:00+00:00",
        reason=DaemonStopReason.SIGTERM,
        uptime_seconds=3600.0,
    )
    assert e.reason == DaemonStopReason.SIGTERM


def test_schema_downgrade_pending_fields() -> None:
    """SchemaDowngradePending carries all required fields."""
    e = SchemaDowngradePending(
        kind="schema_downgrade_pending",
        ts_iso="2026-05-06T00:00:00+00:00",
        file_path="/var/lib/spark-modem-watchdog/state/by-usb/2-3.1.1.json",
        from_version=0,
        to_version=1,
        shadow_path="/var/lib/spark-modem-watchdog/state/by-usb/2-3.1.1.from-v0.json",
        reason=DowngradeReason.FILE_TOO_OLD,
    )
    assert e.from_version == 0
    assert e.reason == DowngradeReason.FILE_TOO_OLD


def test_usb_path_mismatch_fields() -> None:
    """UsbPathMismatch carries file_usb_path, sysfs_usb_path, cdc_wdm (S-02)."""
    e = UsbPathMismatch(
        kind="usb_path_mismatch",
        ts_iso="2026-05-06T00:00:00+00:00",
        file_usb_path="2-3.1.1",
        sysfs_usb_path="2-3.1.2",
        cdc_wdm="cdc-wdm0",
    )
    assert e.cdc_wdm == "cdc-wdm0"


def test_maintenance_window_started_constructs() -> None:
    """MaintenanceWindowStarted constructs."""
    e = MaintenanceWindowStarted(
        kind="maintenance_window_started",
        ts_iso="2026-05-06T00:00:00+00:00",
        duration_seconds=1800.0,
    )
    assert e.duration_seconds == 1800.0


def test_maintenance_window_started_rejects_zero_duration() -> None:
    """duration_seconds must be > 0."""
    with pytest.raises(ValidationError):
        MaintenanceWindowStarted(
            kind="maintenance_window_started",
            ts_iso="2026-05-06T00:00:00+00:00",
            duration_seconds=0.0,
        )


def test_maintenance_window_ended_constructs() -> None:
    """MaintenanceWindowEnded constructs."""
    e = MaintenanceWindowEnded(
        kind="maintenance_window_ended",
        ts_iso="2026-05-06T00:00:00+00:00",
    )
    assert e.reason == "expired"


# ---------------------------------------------------------------------------
# Event union — discriminator dispatch via EventAdapter
# ---------------------------------------------------------------------------


def test_event_adapter_dispatches_action_planned() -> None:
    """EventAdapter dispatches kind='action_planned' to ActionPlanned."""
    raw = {
        "kind": "action_planned",
        "ts_iso": "2026-05-06T00:00:00+00:00",
        "usb_path": "2-3.1.1",
        "action": "soft_reset",
        "reason": "registration failure",
        "schema_version": 1,
    }
    event = EventAdapter.validate_python(raw)
    assert isinstance(event, ActionPlanned)


def test_event_adapter_dispatches_schema_downgrade_pending() -> None:
    """EventAdapter dispatches kind='schema_downgrade_pending'."""
    raw = {
        "kind": "schema_downgrade_pending",
        "ts_iso": "2026-05-06T00:00:00+00:00",
        "file_path": "/some/path.json",
        "from_version": 0,
        "to_version": 1,
        "shadow_path": "/some/path.from-v0.json",
        "reason": "file_too_old",
        "schema_version": 1,
    }
    event = EventAdapter.validate_python(raw)
    assert isinstance(event, SchemaDowngradePending)


def test_event_adapter_validate_json() -> None:
    """EventAdapter.validate_json parses a raw JSON line string."""
    raw = {
        "kind": "daemon_stopped",
        "ts_iso": "2026-05-06T00:00:00+00:00",
        "reason": "sigterm",
        "uptime_seconds": 86400.0,
        "schema_version": 1,
    }
    event = EventAdapter.validate_json(json.dumps(raw))
    assert isinstance(event, DaemonStopped)
    assert event.reason == DaemonStopReason.SIGTERM
