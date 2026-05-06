"""Tests for src.spark_modem.wire.enums — closed StrEnum types."""

import json
from enum import StrEnum

import pytest

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

# ---------------------------------------------------------------------------
# IssueCategory
# ---------------------------------------------------------------------------


def test_issue_category_members() -> None:
    """IssueCategory has the 5 members from FR-21 priority order."""
    assert IssueCategory.CONFIG == "config"
    assert IssueCategory.SIM == "sim"
    assert IssueCategory.DATAPATH == "datapath"
    assert IssueCategory.REGISTRATION == "registration"
    assert IssueCategory.QMI == "qmi"


# ---------------------------------------------------------------------------
# IssueDetail
# ---------------------------------------------------------------------------


def test_issue_detail_members() -> None:
    """IssueDetail covers canonical issue strings."""
    expected = {
        "NO_SIM",
        "SIM_LOCKED",
        "SIM_APP_DETECTED",
        "NOT_REGISTERED_SEARCHING",
        "NOT_REGISTERED_DENIED",
        "QMI_TIMEOUT",
        "QMI_HUNG",
        "APN_MISMATCH",
        "RAW_IP_OFF",
        "NO_DATA_SESSION",
        "NO_IPV4",
    }
    names = {m.name for m in IssueDetail}
    assert expected.issubset(names)


# ---------------------------------------------------------------------------
# RegistrationState
# ---------------------------------------------------------------------------


def test_registration_state_members() -> None:
    """RegistrationState has the expected 5 members."""
    assert RegistrationState.REGISTERED_HOME == "registered_home"
    assert RegistrationState.REGISTERED_ROAMING == "registered_roaming"
    assert RegistrationState.NOT_REGISTERED_SEARCHING == "not_registered_searching"
    assert RegistrationState.NOT_REGISTERED_DENIED == "not_registered_denied"
    assert RegistrationState.UNKNOWN == "unknown"


# ---------------------------------------------------------------------------
# ActionKind
# ---------------------------------------------------------------------------


def test_action_kind_members() -> None:
    """ActionKind covers the recovery ladder (RECOVERY_SPEC § ladder)."""
    assert ActionKind.SET_APN == "set_apn"
    assert ActionKind.FIX_RAW_IP == "fix_raw_ip"
    assert ActionKind.SIM_POWER_ON == "sim_power_on"
    assert ActionKind.SOFT_RESET == "soft_reset"
    assert ActionKind.MODEM_RESET == "modem_reset"
    assert ActionKind.USB_RESET == "usb_reset"
    assert ActionKind.DRIVER_RESET == "driver_reset"


# ---------------------------------------------------------------------------
# ActionResult
# ---------------------------------------------------------------------------


def test_action_result_members() -> None:
    """ActionResult covers all outcome codes."""
    assert ActionResult.SUCCESS == "success"
    assert ActionResult.FAILURE == "failure"
    assert ActionResult.SKIPPED_SIGNAL_GATE == "skipped_signal_gate"
    assert ActionResult.SKIPPED_BACKOFF == "skipped_backoff"
    assert ActionResult.SKIPPED_DRY_RUN == "skipped_dry_run"


# ---------------------------------------------------------------------------
# EventKind
# ---------------------------------------------------------------------------


def test_event_kind_members() -> None:
    """EventKind covers all events.jsonl variant discriminators."""
    expected_values = {
        "action_planned",
        "action_executed",
        "action_failed",
        "state_transition",
        "daemon_started",
        "daemon_stopped",
        "schema_downgrade_pending",
        "usb_path_mismatch",
        "maintenance_window_started",
        "maintenance_window_ended",
    }
    actual_values = {m.value for m in EventKind}
    assert expected_values.issubset(actual_values)


# ---------------------------------------------------------------------------
# WebhookEventKind
# ---------------------------------------------------------------------------


def test_webhook_event_kind_members() -> None:
    """WebhookEventKind covers all 4 webhook payload variants."""
    assert WebhookEventKind.HEALTHY_TO_DEGRADED == "healthy_to_degraded"
    assert WebhookEventKind.RECOVERING_TO_EXHAUSTED == "recovering_to_exhausted"
    assert WebhookEventKind.DAEMON_RESTART == "daemon_restart"
    assert WebhookEventKind.ACTION_FAILED == "action_failed"


# ---------------------------------------------------------------------------
# DowngradeReason
# ---------------------------------------------------------------------------


def test_downgrade_reason_members() -> None:
    """DowngradeReason covers the two downgrade triggers."""
    assert DowngradeReason.FILE_TOO_OLD == "file_too_old"
    assert DowngradeReason.SCHEMA_MISMATCH == "schema_mismatch"


# ---------------------------------------------------------------------------
# DaemonStopReason
# ---------------------------------------------------------------------------


def test_daemon_stop_reason_members() -> None:
    """DaemonStopReason covers the daemon-stop trigger codes."""
    expected = {"sigterm", "crash", "config_invalid", "oom", "kill"}
    assert expected.issubset({m.value for m in DaemonStopReason})


# ---------------------------------------------------------------------------
# StrEnum properties (parametrized over all enums)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "enum_cls",
    [
        IssueCategory,
        IssueDetail,
        RegistrationState,
        ActionKind,
        ActionResult,
        EventKind,
        WebhookEventKind,
        DowngradeReason,
        DaemonStopReason,
    ],
)
def test_enum_is_strenum_subclass(enum_cls: type) -> None:
    """All closed enums must be StrEnum subclasses for auto JSON serialization."""
    assert issubclass(enum_cls, StrEnum)


def test_issue_category_equality_with_string() -> None:
    """IssueCategory.SIM == 'sim' (StrEnum equality with plain string)."""
    assert IssueCategory.SIM == "sim"


def test_issue_category_json_serialization() -> None:
    """json.dumps(IssueCategory.SIM) produces a JSON string value, not an object."""
    assert json.dumps(IssueCategory.SIM) == '"sim"'


def test_issue_category_construction_from_string() -> None:
    """IssueCategory('sim') returns IssueCategory.SIM."""
    assert IssueCategory("sim") is IssueCategory.SIM
