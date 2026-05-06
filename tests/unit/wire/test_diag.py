"""Tests for src.spark_modem.wire.diag — Diag snapshot, Issue, PlannedAction."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

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
from spark_modem.wire.enums import ActionKind, IssueCategory, IssueDetail

_WHO_ADAPTER: TypeAdapter[Who] = TypeAdapter(Who)


# ---------------------------------------------------------------------------
# WhoModem / WhoHost discriminator
# ---------------------------------------------------------------------------


def test_who_modem_constructs() -> None:
    """WhoModem(kind='modem', usb_path='2-3.1.1') constructs."""
    w = WhoModem(kind="modem", usb_path="2-3.1.1")
    assert w.kind == "modem"
    assert w.usb_path == "2-3.1.1"


def test_who_host_constructs() -> None:
    """WhoHost(kind='host') constructs."""
    w = WhoHost(kind="host")
    assert w.kind == "host"


def test_who_discriminator_modem() -> None:
    """Validating {'kind': 'modem', 'usb_path': '2-3.1.1'} produces a WhoModem."""
    w = _WHO_ADAPTER.validate_python({"kind": "modem", "usb_path": "2-3.1.1"})
    assert isinstance(w, WhoModem)
    assert w.usb_path == "2-3.1.1"


def test_who_discriminator_host() -> None:
    """Validating {'kind': 'host'} produces a WhoHost."""
    w = _WHO_ADAPTER.validate_python({"kind": "host"})
    assert isinstance(w, WhoHost)


# ---------------------------------------------------------------------------
# Issue
# ---------------------------------------------------------------------------


def test_issue_with_who_modem_constructs() -> None:
    """Issue with a WhoModem who constructs cleanly."""
    issue = Issue(
        category=IssueCategory.SIM,
        detail=IssueDetail.NO_SIM,
        who=WhoModem(kind="modem", usb_path="2-3.1.1"),
        description="SIM absent",
    )
    assert issue.category == IssueCategory.SIM
    assert isinstance(issue.who, WhoModem)


def test_issue_with_who_host_constructs() -> None:
    """Issue with a WhoHost who (e.g. dmesg overcurrent) constructs."""
    issue = Issue(
        category=IssueCategory.QMI,
        detail=IssueDetail.ENUMERATION_OVERCURRENT,
        who=WhoHost(kind="host"),
    )
    assert isinstance(issue.who, WhoHost)


def test_issue_discriminator_from_dict() -> None:
    """Issue.who discriminates WhoModem vs WhoHost from a plain dict."""
    issue = Issue.model_validate(
        {
            "category": "sim",
            "detail": "no_sim",
            "who": {"kind": "modem", "usb_path": "2-3.1.1"},
        }
    )
    assert isinstance(issue.who, WhoModem)

    issue2 = Issue.model_validate(
        {
            "category": "qmi",
            "detail": "enumeration_overcurrent",
            "who": {"kind": "host"},
        }
    )
    assert isinstance(issue2.who, WhoHost)


# ---------------------------------------------------------------------------
# SignalSnapshot
# ---------------------------------------------------------------------------


def test_signal_snapshot_all_none_constructs() -> None:
    """SignalSnapshot with all None fields constructs (nullable per SCHEMA §2)."""
    s = SignalSnapshot()
    assert s.rsrp_dbm is None


def test_signal_snapshot_with_values() -> None:
    """SignalSnapshot with real values constructs."""
    s = SignalSnapshot(rssi_dbm=-51, rsrp_dbm=-92, rsrq_db=-18.0, snr_db=-8.2)
    assert s.rsrp_dbm == -92


# ---------------------------------------------------------------------------
# ModemSnapshot
# ---------------------------------------------------------------------------


def test_modem_snapshot_constructs() -> None:
    """ModemSnapshot with minimal required fields constructs."""
    ms = ModemSnapshot(
        usb_path="2-3.1.1",
        cdc_wdm="cdc-wdm0",
    )
    assert ms.usb_path == "2-3.1.1"
    assert ms.registration is None


# ---------------------------------------------------------------------------
# Diag
# ---------------------------------------------------------------------------


def test_diag_constructs() -> None:
    """Diag with required fields constructs cleanly."""
    d = Diag(schema_version=1, ts_iso="2026-05-06T00:00:00+00:00", cycle_id=0)
    assert d.schema_version == 1
    assert d.per_modem == {}
    assert d.host_issues == []


def test_diag_round_trip_json() -> None:
    """Diag round-trips via model_dump_json / model_validate_json."""
    d = Diag(
        schema_version=1,
        ts_iso="2026-05-06T00:00:00+00:00",
        cycle_id=42,
        per_modem={
            "2-3.1.1": ModemSnapshot(usb_path="2-3.1.1", cdc_wdm="cdc-wdm0"),
        },
        host_issues=[
            Issue(
                category=IssueCategory.QMI,
                detail=IssueDetail.ENUMERATION_OVERCURRENT,
                who=WhoHost(kind="host"),
            )
        ],
    )
    j = d.model_dump_json()
    d2 = Diag.model_validate_json(j)
    assert d == d2


# ---------------------------------------------------------------------------
# PlannedAction
# ---------------------------------------------------------------------------


def test_planned_action_constructs() -> None:
    """PlannedAction with kind, who, reason constructs cleanly."""
    pa = PlannedAction(
        kind=ActionKind.SOFT_RESET,
        who=WhoModem(kind="modem", usb_path="2-3.1.1"),
        reason="registration_failure",
        dry_run=False,
    )
    assert pa.kind == ActionKind.SOFT_RESET
    assert pa.dry_run is False
    assert pa.suppressed_by_signal_gate is False


def test_planned_action_cdc_wdm_validation() -> None:
    """WhoModem.cdc_wdm must match ^cdc-wdm\\d+$ or be None."""
    w = WhoModem(kind="modem", usb_path="2-3.1.1", cdc_wdm="cdc-wdm3")
    assert w.cdc_wdm == "cdc-wdm3"

    with pytest.raises(ValidationError):
        WhoModem(kind="modem", usb_path="2-3.1.1", cdc_wdm="wwan0")
