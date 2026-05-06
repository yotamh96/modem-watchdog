"""Tests for status.json writer + StatusReport / MaintenanceWindow wire round-trip.

Covers FR-41 / FR-41.1 / ADR-0013 / C-02:
  - ``write_status_json`` writes via the Phase 1 atomic helper.
  - ``StatusReport`` carries every FR-41.1 field (cycle_index, cycle,
    summary, modems, cycle_actions_executed, cycle_transitions,
    carrier_table_sha256, last_modified).
  - ``StatusPerModem.state_int`` round-trips (ADR-0013 integer encoding).
  - ``GlobalsState`` round-trips with AND without ``maintenance``.
  - ``MaintenanceWindow.max_duration_seconds`` 8h cap is enforced.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from spark_modem.status_reporter.status import write_status_json
from spark_modem.wire.globals import GlobalsState
from spark_modem.wire.maintenance import MaintenanceWindow
from spark_modem.wire.status import (
    StatusCycleSummary,
    StatusModemSummary,
    StatusPerModem,
    StatusReport,
)


def _make_report() -> StatusReport:
    return StatusReport(
        last_modified="2026-05-06T17:00:00+00:00",
        cycle_index=42,
        cycle=StatusCycleSummary(
            n=42,
            duration_seconds=3.5,
            next_at_iso="2026-05-06T17:00:30+00:00",
        ),
        summary=StatusModemSummary(
            expected_modems=4,
            healthy=3,
            degraded=1,
        ),
        modems=[
            StatusPerModem(
                usb_path="2-3.1.1",
                cdc_wdm="cdc-wdm0",
                line=1,
                state="healthy",
                state_int=1,
                rf_blocked=False,
                ipv4="100.64.1.10",
                cause=None,
                last_action_iso=None,
            ),
            StatusPerModem(
                usb_path="2-3.1.2",
                cdc_wdm="cdc-wdm1",
                line=2,
                state="recovering",
                state_int=3,
                rf_blocked=False,
                ipv4=None,
                cause="not_registered_searching",
                last_action_iso="2026-05-06T16:59:30+00:00",
            ),
        ],
        cycle_actions_executed=1,
        cycle_transitions=1,
        carrier_table_sha256="a" * 64,
        maintenance_active_until_iso=None,
    )


def test_write_status_json_atomic(tmp_path: Path) -> None:
    """write_status_json round-trips via model_validate_json."""
    target = tmp_path / "status.json"
    report = _make_report()

    write_status_json(target, report)

    assert target.exists()
    parsed = StatusReport.model_validate_json(target.read_bytes())
    assert parsed == report


def test_status_report_includes_required_fr_41_1_fields() -> None:
    """All FR-41.1 fields are present on StatusReport."""
    report = _make_report()
    # FR-41 baseline
    assert report.last_modified == "2026-05-06T17:00:00+00:00"
    assert report.cycle_index == 42
    assert report.cycle.n == 42
    assert report.cycle.duration_seconds == 3.5
    # FR-41.1
    assert report.cycle_actions_executed == 1
    assert report.cycle_transitions == 1
    assert report.carrier_table_sha256 == "a" * 64
    # Aggregate summary + per-modem list
    assert report.summary.expected_modems == 4
    assert len(report.modems) == 2


def test_status_report_per_modem_state_int_encodes_per_adr_0013(tmp_path: Path) -> None:
    """state_int is preserved across JSON round-trip (ADR-0013).

    The integer encoding stays stable: 0=unknown, 1=healthy, 2=degraded,
    3=recovering, 4=exhausted. The on-disk shape carries both the
    string state AND the integer so consumers don't need to re-encode.
    """
    per_modem = StatusPerModem(
        usb_path="2-3.1.1",
        cdc_wdm="cdc-wdm0",
        line=1,
        state="recovering",
        state_int=3,
    )
    report = StatusReport(
        last_modified="2026-05-06T17:00:00+00:00",
        cycle_index=1,
        cycle=StatusCycleSummary(n=1, duration_seconds=1.0),
        summary=StatusModemSummary(expected_modems=1, recovering=1),
        modems=[per_modem],
    )
    target = tmp_path / "status.json"
    write_status_json(target, report)
    parsed = StatusReport.model_validate_json(target.read_bytes())
    assert parsed.modems[0].state == "recovering"
    assert parsed.modems[0].state_int == 3


def test_status_per_modem_rejects_state_int_out_of_range() -> None:
    """state_int is bounded to 0..4 (ADR-0013 stable mapping)."""
    with pytest.raises(ValidationError):
        StatusPerModem(usb_path="2-3.1.1", state="rogue", state_int=5)


def test_globals_with_maintenance_round_trips() -> None:
    """GlobalsState carries MaintenanceWindow through JSON round-trip."""
    window = MaintenanceWindow(
        active=True,
        scope="destructive",
        started_iso="2026-05-06T16:00:00+00:00",
        started_monotonic=10_000.0,
        expires_iso="2026-05-06T17:00:00+00:00",
        expires_monotonic=13_600.0,
        max_duration_seconds=3600,
    )
    globals_state = GlobalsState(
        driver_reset_count=2,
        last_driver_reset_monotonic=9_900.0,
        last_driver_reset_iso="2026-05-06T15:58:00+00:00",
        qmi_proxy_uptime_seconds=3600.0,
        maintenance=window,
    )

    payload = globals_state.model_dump_json(by_alias=True)
    parsed = GlobalsState.model_validate_json(payload)

    assert parsed == globals_state
    assert parsed.maintenance is not None
    assert parsed.maintenance.active is True
    assert parsed.maintenance.scope == "destructive"
    assert parsed.maintenance.started_iso == "2026-05-06T16:00:00+00:00"
    assert parsed.maintenance.started_monotonic == 10_000.0
    assert parsed.maintenance.expires_iso == "2026-05-06T17:00:00+00:00"
    assert parsed.maintenance.expires_monotonic == 13_600.0
    assert parsed.maintenance.max_duration_seconds == 3600


def test_globals_without_maintenance_round_trips() -> None:
    """maintenance defaults to None and round-trips cleanly.

    Backward-compatibility check: a Phase 1-shape globals.json (no
    maintenance field) parses successfully.
    """
    globals_state = GlobalsState()
    payload = globals_state.model_dump_json(by_alias=True)
    parsed = GlobalsState.model_validate_json(payload)
    assert parsed.maintenance is None
    assert parsed == globals_state

    # Phase 1-shape JSON literal (no `maintenance` key) parses cleanly.
    legacy = (
        '{"schema_version":1,"driver_reset_count":0,'
        '"last_driver_reset_monotonic":null,"last_driver_reset_iso":null,'
        '"qmi_proxy_uptime_seconds":0.0}'
    )
    legacy_parsed = GlobalsState.model_validate_json(legacy)
    assert legacy_parsed.maintenance is None


def test_maintenance_max_duration_8h_cap() -> None:
    """C-02 8-hour hard cap rejected at construction (defensive)."""
    with pytest.raises(ValidationError):
        MaintenanceWindow(
            active=True,
            started_iso="2026-05-06T16:00:00+00:00",
            started_monotonic=10_000.0,
            expires_iso="2026-05-07T01:00:00+00:00",
            expires_monotonic=42_400.0,
            max_duration_seconds=28801,
        )


def test_maintenance_negative_monotonic_rejected() -> None:
    """started_monotonic / expires_monotonic must be >= 0."""
    with pytest.raises(ValidationError):
        MaintenanceWindow(
            active=False,
            started_iso="2026-05-06T16:00:00+00:00",
            started_monotonic=-1.0,
            expires_iso="2026-05-06T17:00:00+00:00",
            expires_monotonic=10.0,
        )
