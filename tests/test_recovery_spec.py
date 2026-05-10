"""RECOVERY_SPEC §4 spec-as-tests: every decision-table row gets a test.

Each test seeds a minimal Diag containing one issue, runs the policy
engine, and asserts the resulting PlannedAction.kind matches the
expected mapping (or that the plan is a skip with the expected reason).

`tools/check_spec.py` is the CI gate that asserts every row in
`_DECISION_TABLE` is referenced by enum value somewhere in this file
(matched via parametrize ids and the value-listing block below).

NOTE: This file lives at `tests/test_recovery_spec.py` (NOT under
`tests/unit/`) so it doesn't pick up the auto-applied "unit" marker
from the conftest hook -- it's a higher-level cross-module test that
exercises the full policy engine against minimal Diag fixtures.

Coverage manifest (read by tools/check_spec.py via substring match):

  config / apn_empty
  config / apn_mismatch
  sim / sim_power_down
  sim / sim_app_unreadable
  sim / sim_app_pin_required
  sim / sim_app_puk_required
  sim / sim_app_detected
  sim / sim_card_absent
  sim / sim_card_error
  sim / sim_card_unreadable
  datapath / raw_ip_off
  datapath / session_disconnected
  registration / not_registered_searching
  registration / not_registered_idle
  registration / denied
  qmi / qmi_channel_hung
  qmi / operating_mode_offline
  qmi / operating_mode_low_power
  qmi / qmi_proxy_died
  qmi / qmi_timeout
  qmi / sierra_bootloader  (Plan 04-02 / A-06 -- usb_reset parent-hub variant
    per PITFALLS §1.6 selected via CLI --target=parent-hub; PATTERNS correction
    #4: IssueCategory.ENUMERATION does not exist, so SIERRA_BOOTLOADER lives
    under QMI category)
"""

from __future__ import annotations

import pytest

from spark_modem.config.settings import Settings
from spark_modem.policy.context import PolicyContext
from spark_modem.policy.decision_table import all_table_rows, lookup_action
from spark_modem.policy.engine import run_cycle
from spark_modem.wire.diag import Diag, Issue, ModemSnapshot, SignalSnapshot, WhoModem
from spark_modem.wire.enums import ActionKind, IssueCategory, IssueDetail
from spark_modem.wire.globals import GlobalsState
from spark_modem.wire.state import ModemState
from tests.fakes.clock import FakeClock


def _make_state() -> ModemState:
    return ModemState.model_validate(
        {
            "state": "unknown",
            "present": True,
            "rf_blocked": False,
            "recovering_level": None,
            "_healthy_streak": 0,
            "counters": {},
            "last_action_monotonic": None,
            "last_state_transition_iso": None,
        }
    )


def _make_diag_with_one_issue(
    category: IssueCategory,
    detail: IssueDetail,
) -> Diag:
    who = WhoModem(usb_path="2-3.1.1", cdc_wdm="cdc-wdm0")
    snap = ModemSnapshot(
        usb_path="2-3.1.1",
        cdc_wdm="cdc-wdm0",
        signal=SignalSnapshot(rsrp_dbm=-90, rsrq_db=-10.0, snr_db=5.0),
        issues=[Issue(category=category, detail=detail, who=who)],
    )
    return Diag(
        ts_iso="2026-01-01T00:00:00+00:00",
        cycle_id=1,
        per_modem={"2-3.1.1": snap},
    )


def _row_id(row: tuple[IssueCategory, IssueDetail]) -> str:
    cat, detail = row
    return f"{cat.value}-{detail.value}"


@pytest.mark.parametrize(
    ("cat", "detail"),
    all_table_rows(),
    ids=[_row_id(row) for row in all_table_rows()],
)
def test_recovery_spec_row(
    cat: IssueCategory,
    detail: IssueDetail,
    settings: Settings,
) -> None:
    """For every RECOVERY_SPEC §4 row, the engine produces the expected
    ActionKind (or the expected skip:<reason>).
    """
    diag = _make_diag_with_one_issue(cat, detail)
    ctx = PolicyContext(
        clock=FakeClock(),
        config=settings,
        maintenance_active=False,
        expected_modem_count=4,
    )
    result = run_cycle(diag, {"2-3.1.1": _make_state()}, GlobalsState(), ctx)
    assert len(result.plans) == 1, f"expected one plan for ({cat}, {detail})"

    plan = result.plans[0]
    expected = lookup_action(cat, detail)
    if isinstance(expected, ActionKind):
        # The engine may have suppressed via a soft gate (signal/backoff/
        # dry_run), but with our defaults nothing trips: assert the
        # ActionKind matches and the plan is action_planned (not skip).
        assert plan.kind == expected, (
            f"({cat}, {detail}): expected {expected}, got {plan.kind}"
        )
        assert plan.reason == f"action_planned:{expected.value}", (
            f"({cat}, {detail}): expected action_planned reason, got {plan.reason!r}"
        )
    else:
        # Skip-reason rows: PlannedAction.kind is nominal (SOFT_RESET)
        # because pydantic requires a kind; the truth is plan.reason.
        assert isinstance(expected, str) and expected.startswith("skip:")
        assert plan.reason == expected, (
            f"({cat}, {detail}): expected reason {expected!r}, got {plan.reason!r}"
        )
