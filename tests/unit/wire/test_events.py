"""Tests for src.spark_modem.wire.events — events.jsonl union variants."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from spark_modem.wire.enums import (
    ActionKind,
    ActionResult,
    DaemonStopReason,
    DowngradeReason,
    IssueCategory,
    IssueDetail,
    SkipReason,
)
from spark_modem.wire.events import (
    ActionExecuted,
    ActionFailed,
    ActionPlanned,
    ActionSkipped,
    DaemonStarted,
    DaemonStopped,
    EventAdapter,
    EventSourceCrashed,
    MaintenanceWindowEnded,
    MaintenanceWindowStarted,
    SchemaDowngradePending,
    SimSwapped,
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


# ---------------------------------------------------------------------------
# Phase 3 Plan 03-06: EventSourceCrashed (Issue #7) + SimSwapped (Issue #8)
# ---------------------------------------------------------------------------


def test_event_source_crashed_constructs() -> None:
    """EventSourceCrashed constructs with required fields (Issue #7)."""
    e = EventSourceCrashed(
        ts_iso="2026-05-07T00:00:00Z",
        source="udev_producer",
        error_class="OSError",
        error_message="ENOBUFS",
        restart_attempt=1,
        backoff_seconds=1.0,
    )
    assert e.kind == "event_source_crashed"
    assert e.source == "udev_producer"
    assert e.error_class == "OSError"
    assert e.error_message == "ENOBUFS"
    assert e.restart_attempt == 1
    assert e.backoff_seconds == 1.0
    assert e.schema_version == 1


def test_event_source_crashed_error_message_capped_at_200() -> None:
    """T-03-06-07: pathological exception messages capped at 200 chars."""
    long_msg = "x" * 250
    with pytest.raises(ValidationError):
        EventSourceCrashed(
            ts_iso="2026-05-07T00:00:00Z",
            source="udev_producer",
            error_class="OSError",
            error_message=long_msg,
            restart_attempt=1,
            backoff_seconds=1.0,
        )


def test_event_source_crashed_restart_attempt_must_be_positive() -> None:
    """restart_attempt must be >= 1 (1-indexed restart count)."""
    with pytest.raises(ValidationError):
        EventSourceCrashed(
            ts_iso="2026-05-07T00:00:00Z",
            source="udev_producer",
            error_class="OSError",
            error_message="boom",
            restart_attempt=0,
            backoff_seconds=1.0,
        )


def test_event_source_crashed_backoff_seconds_non_negative() -> None:
    """backoff_seconds must be >= 0."""
    with pytest.raises(ValidationError):
        EventSourceCrashed(
            ts_iso="2026-05-07T00:00:00Z",
            source="udev_producer",
            error_class="OSError",
            error_message="boom",
            restart_attempt=1,
            backoff_seconds=-1.0,
        )


def test_event_source_crashed_round_trips_through_event_adapter() -> None:
    """EventAdapter.dump_json + validate_json round-trip preserves all fields."""
    e = EventSourceCrashed(
        ts_iso="2026-05-07T00:00:00Z",
        source="udev_producer",
        error_class="OSError",
        error_message="ENOBUFS",
        restart_attempt=1,
        backoff_seconds=1.0,
    )
    raw = EventAdapter.dump_json(e)
    back = EventAdapter.validate_json(raw)
    assert isinstance(back, EventSourceCrashed)
    assert back.kind == "event_source_crashed"
    assert back.source == "udev_producer"
    assert back.error_class == "OSError"
    assert back.restart_attempt == 1
    assert back.backoff_seconds == 1.0


def test_sim_swapped_constructs() -> None:
    """SimSwapped constructs with required fields (Issue #8 / E-04)."""
    e = SimSwapped(
        ts_iso="2026-05-07T00:00:00Z",
        usb_path="2-3.1.1",
        iccid_hash_old="deadbeef",
        iccid_hash_new="cafebabe",
    )
    assert e.kind == "sim_swapped"
    assert e.usb_path == "2-3.1.1"
    assert e.iccid_hash_old == "deadbeef"
    assert e.iccid_hash_new == "cafebabe"


def test_sim_swapped_iccid_hash_must_be_8_chars() -> None:
    """ICCID hashes are sha256[:8] redacted — pinned to exactly 8 chars."""
    with pytest.raises(ValidationError):
        SimSwapped(
            ts_iso="2026-05-07T00:00:00Z",
            usb_path="2-3.1.1",
            iccid_hash_old="short",  # less than 8 chars
            iccid_hash_new="cafebabe",
        )
    with pytest.raises(ValidationError):
        SimSwapped(
            ts_iso="2026-05-07T00:00:00Z",
            usb_path="2-3.1.1",
            iccid_hash_old="deadbeef",
            iccid_hash_new="toolongstring",  # more than 8 chars
        )


def test_sim_swapped_round_trips_through_event_adapter() -> None:
    """EventAdapter round-trip preserves SimSwapped fields."""
    e = SimSwapped(
        ts_iso="2026-05-07T00:00:00Z",
        usb_path="2-3.1.1",
        iccid_hash_old="deadbeef",
        iccid_hash_new="cafebabe",
    )
    raw = EventAdapter.dump_json(e)
    back = EventAdapter.validate_json(raw)
    assert isinstance(back, SimSwapped)
    assert back.kind == "sim_swapped"
    assert back.usb_path == "2-3.1.1"


def test_event_adapter_dispatches_event_source_crashed() -> None:
    """EventAdapter discriminator dispatches kind='event_source_crashed'."""
    raw = {
        "kind": "event_source_crashed",
        "ts_iso": "2026-05-07T00:00:00Z",
        "source": "rtnetlink_producer",
        "error_class": "OSError",
        "error_message": "ENOBUFS",
        "restart_attempt": 2,
        "backoff_seconds": 2.0,
        "schema_version": 1,
    }
    event = EventAdapter.validate_python(raw)
    assert isinstance(event, EventSourceCrashed)


def test_event_adapter_dispatches_sim_swapped() -> None:
    """EventAdapter discriminator dispatches kind='sim_swapped'."""
    raw = {
        "kind": "sim_swapped",
        "ts_iso": "2026-05-07T00:00:00Z",
        "usb_path": "2-3.1.1",
        "iccid_hash_old": "deadbeef",
        "iccid_hash_new": "cafebabe",
        "schema_version": 1,
    }
    event = EventAdapter.validate_python(raw)
    assert isinstance(event, SimSwapped)


# ---------------------------------------------------------------------------
# Phase 4 Plan 04-05: ActionSkipped variant in the discriminated Event union
# ---------------------------------------------------------------------------


def test_event_tagged_union_includes_action_skipped() -> None:
    """The Event tagged union routes kind='action_skipped' to ActionSkipped.

    Phase 4 B-04: ActionSkipped is a first-class event variant alongside
    PlannedAction.suppressed_* flags (back-compat preserved per CONTEXT B-04).
    The Event union grew from 13 to 14 variants when this test was added.
    """
    raw = {
        "kind": "action_skipped",
        "ts_iso": "2026-05-10T12:00:00Z",
        "usb_path": "2-3.1.1",
        "suppressed_action": "modem_reset",
        "reason": "signal_below_gate",
        "cause_category": "registration",
        "cause_detail": "not_registered_searching",
        "schema_version": 1,
    }
    event = EventAdapter.validate_python(raw)
    assert isinstance(event, ActionSkipped)
    assert event.reason == SkipReason.SIGNAL_BELOW_GATE
    assert event.suppressed_action == ActionKind.MODEM_RESET
    assert event.cause_category == IssueCategory.REGISTRATION
    assert event.cause_detail == IssueDetail.NOT_REGISTERED_SEARCHING
