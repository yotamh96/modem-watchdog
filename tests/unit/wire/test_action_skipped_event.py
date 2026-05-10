"""Tests for the ActionSkipped event variant + SkipReason StrEnum (Phase 4 B-04).

Plan 04-05 Task 1 contract:
  - SkipReason is a closed StrEnum with exactly 7 canonical values.
  - EventKind.ACTION_SKIPPED == "action_skipped".
  - ActionSkipped is a BaseWire-derived event with discriminator
    kind="action_skipped"; round-trips through pydantic v2; the tagged-union
    Event routes the discriminator correctly via EventAdapter.
  - Closed-enum discipline (W-04): unknown reason strings are rejected with
    pydantic ValidationError.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from spark_modem.wire.enums import (
    ActionKind,
    EventKind,
    IssueCategory,
    IssueDetail,
    SkipReason,
)
from spark_modem.wire.events import ActionSkipped, EventAdapter


# ---------------------------------------------------------------------------
# SkipReason closed StrEnum (W-04)
# ---------------------------------------------------------------------------


def test_skip_reason_has_seven_values() -> None:
    """SkipReason has EXACTLY 7 entries -- closed-enum discipline."""
    assert set(SkipReason) == {
        SkipReason.SIGNAL_BELOW_GATE,
        SkipReason.LADDER_BACKOFF,
        SkipReason.SAME_ACTION_BACKOFF,
        SkipReason.EXHAUSTED,
        SkipReason.DISCONNECTED,
        SkipReason.MAINTENANCE,
        SkipReason.DRY_RUN,
    }
    assert len(set(SkipReason)) == 7


def test_skip_reason_string_values_canonical() -> None:
    """The wire-canonical string forms are pinned -- changing one is a
    schema break and must be a deliberate edit."""
    assert SkipReason.SIGNAL_BELOW_GATE.value == "signal_below_gate"
    assert SkipReason.LADDER_BACKOFF.value == "ladder_backoff"
    assert SkipReason.SAME_ACTION_BACKOFF.value == "same_action_backoff"
    assert SkipReason.EXHAUSTED.value == "exhausted"
    assert SkipReason.DISCONNECTED.value == "disconnected"
    assert SkipReason.MAINTENANCE.value == "maintenance"
    assert SkipReason.DRY_RUN.value == "dry_run"


def test_event_kind_action_skipped_value() -> None:
    """EventKind.ACTION_SKIPPED maps to 'action_skipped' (the discriminator)."""
    assert EventKind.ACTION_SKIPPED.value == "action_skipped"


# ---------------------------------------------------------------------------
# ActionSkipped variant -- construction + field surface
# ---------------------------------------------------------------------------


def test_action_skipped_constructs_with_required_fields() -> None:
    """ActionSkipped builds with all required fields and the kind discriminator."""
    e = ActionSkipped(
        ts_iso="2026-05-10T12:00:00Z",
        usb_path="2-3.1.1",
        suppressed_action=ActionKind.MODEM_RESET,
        reason=SkipReason.SIGNAL_BELOW_GATE,
        cause_category=IssueCategory.REGISTRATION,
        cause_detail=IssueDetail.NOT_REGISTERED_SEARCHING,
    )
    assert e.kind == "action_skipped"
    assert e.usb_path == "2-3.1.1"
    assert e.suppressed_action == ActionKind.MODEM_RESET
    assert e.reason == SkipReason.SIGNAL_BELOW_GATE
    assert e.cause_category == IssueCategory.REGISTRATION
    assert e.cause_detail == IssueDetail.NOT_REGISTERED_SEARCHING
    assert e.schema_version == 1


def test_action_skipped_round_trip() -> None:
    """model_dump_json + model_validate_json round-trip preserves all fields."""
    original = ActionSkipped(
        ts_iso="2026-05-10T12:00:00Z",
        usb_path="2-3.1.1",
        suppressed_action=ActionKind.MODEM_RESET,
        reason=SkipReason.SIGNAL_BELOW_GATE,
        cause_category=IssueCategory.REGISTRATION,
        cause_detail=IssueDetail.NOT_REGISTERED_SEARCHING,
    )
    raw = original.model_dump_json()
    back = ActionSkipped.model_validate_json(raw)
    assert back == original
    assert back.kind == "action_skipped"
    assert back.suppressed_action == ActionKind.MODEM_RESET
    assert back.reason == SkipReason.SIGNAL_BELOW_GATE


def test_action_skipped_kind_discriminator_routes_correctly() -> None:
    """EventAdapter (the discriminated tagged union) routes kind='action_skipped'
    to ActionSkipped, NOT to any other variant."""
    e = ActionSkipped(
        ts_iso="2026-05-10T12:00:00Z",
        usb_path="2-3.1.1",
        suppressed_action=ActionKind.USB_RESET,
        reason=SkipReason.LADDER_BACKOFF,
        cause_category=IssueCategory.QMI,
        cause_detail=IssueDetail.QMI_CHANNEL_HUNG,
    )
    raw = EventAdapter.dump_json(e)
    routed = EventAdapter.validate_json(raw)
    assert isinstance(routed, ActionSkipped)
    assert routed.kind == "action_skipped"
    assert routed.reason == SkipReason.LADDER_BACKOFF


def test_action_skipped_rejects_unknown_reason() -> None:
    """Closed-enum discipline (W-04): a SkipReason value not in the 7-member
    enum raises pydantic ValidationError at construction time."""
    with pytest.raises(ValidationError):
        ActionSkipped(
            ts_iso="2026-05-10T12:00:00Z",
            usb_path="2-3.1.1",
            suppressed_action=ActionKind.MODEM_RESET,
            reason="quantum_tunnel",  # type: ignore[arg-type]
            cause_category=IssueCategory.REGISTRATION,
            cause_detail=IssueDetail.NOT_REGISTERED_SEARCHING,
        )


@pytest.mark.parametrize(
    "skip_reason",
    [
        SkipReason.SIGNAL_BELOW_GATE,
        SkipReason.LADDER_BACKOFF,
        SkipReason.SAME_ACTION_BACKOFF,
        SkipReason.EXHAUSTED,
        SkipReason.DISCONNECTED,
        SkipReason.MAINTENANCE,
        SkipReason.DRY_RUN,
    ],
)
def test_action_skipped_per_skip_reason_round_trip(skip_reason: SkipReason) -> None:
    """Every SkipReason value round-trips cleanly through ActionSkipped JSON.

    Parametrised over all 7 SkipReason values -- closed-enum coverage gate.
    """
    e = ActionSkipped(
        ts_iso="2026-05-10T12:00:00Z",
        usb_path="2-3.1.1",
        suppressed_action=ActionKind.MODEM_RESET,
        reason=skip_reason,
        cause_category=IssueCategory.QMI,
        cause_detail=IssueDetail.QMI_CHANNEL_HUNG,
    )
    raw = e.model_dump_json()
    back = ActionSkipped.model_validate_json(raw)
    assert back.reason == skip_reason


def test_action_skipped_round_trip_through_event_adapter() -> None:
    """EventAdapter.dump_json + validate_json round-trips an ActionSkipped via
    the tagged union (proves the discriminator survives JSON serialization)."""
    original = ActionSkipped(
        ts_iso="2026-05-10T12:00:00Z",
        usb_path="2-3.1.4",
        suppressed_action=ActionKind.SOFT_RESET,
        reason=SkipReason.SAME_ACTION_BACKOFF,
        cause_category=IssueCategory.DATAPATH,
        cause_detail=IssueDetail.SESSION_DISCONNECTED,
    )
    raw = EventAdapter.dump_json(original)
    back = EventAdapter.validate_json(raw)
    assert isinstance(back, ActionSkipped)
    assert back == original


def test_action_skipped_rejects_extra_fields() -> None:
    """BaseWire (frozen, extra=forbid) rejects unknown fields -- prevents
    schema drift at the wire boundary (W-02)."""
    with pytest.raises(ValidationError):
        ActionSkipped(
            ts_iso="2026-05-10T12:00:00Z",
            usb_path="2-3.1.1",
            suppressed_action=ActionKind.MODEM_RESET,
            reason=SkipReason.SIGNAL_BELOW_GATE,
            cause_category=IssueCategory.REGISTRATION,
            cause_detail=IssueDetail.NOT_REGISTERED_SEARCHING,
            extra_field="should_be_rejected",  # type: ignore[call-arg]
        )
