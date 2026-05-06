"""Tests for spark_modem.cli.explain — text formatters."""

from __future__ import annotations

from spark_modem.cli.explain import format_diag_explain, format_plans_explain
from spark_modem.wire.diag import (
    Diag,
    Issue,
    ModemSnapshot,
    PlannedAction,
    SignalSnapshot,
    WhoHost,
    WhoModem,
)
from spark_modem.wire.enums import (
    ActionKind,
    IssueCategory,
    IssueDetail,
    RegistrationState,
)


def _diag_two_modems() -> Diag:
    return Diag(
        ts_iso="2026-05-06T00:00:00+00:00",
        cycle_id=7,
        per_modem={
            "2-3.1.1": ModemSnapshot(
                usb_path="2-3.1.1",
                cdc_wdm="cdc-wdm0",
                operating_mode="online",
                sim_state="ready",
                registration=RegistrationState.REGISTERED_HOME,
                signal=SignalSnapshot(rsrp_dbm=-94, rsrq_db=-9.0, snr_db=8.4),
                issues=[],
            ),
            "2-3.1.2": ModemSnapshot(
                usb_path="2-3.1.2",
                cdc_wdm="cdc-wdm1",
                operating_mode="low_power",
                sim_state="ready",
                registration=RegistrationState.NOT_REGISTERED_SEARCHING,
                signal=SignalSnapshot(rsrp_dbm=-110, rsrq_db=-15.0, snr_db=0.0),
                issues=[
                    Issue(
                        category=IssueCategory.QMI,
                        detail=IssueDetail.OPERATING_MODE_LOW_POWER,
                        who=WhoModem(usb_path="2-3.1.2", cdc_wdm="cdc-wdm1"),
                    )
                ],
            ),
        },
    )


def test_format_diag_explain_lists_per_modem_lines() -> None:
    out = format_diag_explain(_diag_two_modems())
    lines = out.split("\n")
    assert lines[0].startswith("Diag cycle=7")
    assert "modem 2-3.1.1" in out
    assert "modem 2-3.1.2" in out
    assert "issues=[]" in out  # healthy modem
    assert "operating_mode_low_power" in out  # the one issue


def test_format_diag_explain_signal_block() -> None:
    out = format_diag_explain(_diag_two_modems())
    assert "rsrp=-94dBm" in out
    assert "snr=8.4dB" in out


def test_format_plans_explain_lists_per_plan_lines() -> None:
    plans = [
        PlannedAction(
            kind=ActionKind.SET_APN,
            who=WhoModem(usb_path="2-3.1.1", cdc_wdm="cdc-wdm0"),
            reason="action_planned:set_apn",
        ),
        PlannedAction(
            kind=ActionKind.SOFT_RESET,
            who=WhoModem(usb_path="2-3.1.2", cdc_wdm="cdc-wdm1"),
            reason="skip:dry_run",
            suppressed_by_dry_run=True,
        ),
    ]
    out = format_plans_explain(plans)
    assert "Plans:" in out
    assert "RUN kind=set_apn who=2-3.1.1" in out
    assert "GATED kind=soft_reset who=2-3.1.2" in out
    assert "dry_run=True" in out


def test_format_plans_explain_host_who() -> None:
    """A WhoHost plan (e.g. driver_reset) renders 'who=host'."""
    plans = [
        PlannedAction(
            kind=ActionKind.DRIVER_RESET,
            who=WhoHost(),
            reason="action_planned:driver_reset",
        )
    ]
    out = format_plans_explain(plans)
    assert "who=host" in out


def test_format_plans_explain_empty_list() -> None:
    out = format_plans_explain([])
    assert out == "Plans:"
