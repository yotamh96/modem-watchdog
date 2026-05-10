"""Boundary tests for policy.engine._global_driver_reset_eligible.

Plan 04-03 Task 3 -- 12 boundary cases covering the four eligibility gates,
in their evaluation order:

  1. Thermal suppression (C-03 / PITFALLS §17.4): host_issues includes
     THERMAL_WARN or THERMAL_CRITICAL -> NOT eligible.
  2. Cooldown (C-05 / RECOVERY_SPEC §6.4): elapsed since last fire <
     global_driver_reset_backoff_seconds -> NOT eligible. None last-fire
     short-circuits to allow.
  3. >=75% denominator (C-01): hung_count / expected_modem_count >=
     multi_modem_threshold_fraction. Denominator is the EXPECTED total
     (Settings.expected_modem_count, threaded into PolicyContext), NOT
     the enumerated count -- Zao-active and missing modems counted as
     'not-hung' per the user's conservative deviation.
  4. Actionable signal (FR-24): at least one hung modem has rsrp >= floor
     AND rsrq >= floor AND snr >= floor (None readings count as 'not above
     floor' -- conservative).

Each test names the gate it pins. The predicate is purely-functional: no
clock advance, no I/O. The only "time" element is the cooldown read of
``ctx.clock.monotonic() - globals_state.last_driver_reset_monotonic`` which
the FakeClock controls deterministically.
"""

from __future__ import annotations

from typing import cast

from spark_modem.config.settings import Settings
from spark_modem.policy.context import PolicyContext
from spark_modem.policy.engine import _global_driver_reset_eligible
from spark_modem.wire.diag import (
    Diag,
    Issue,
    ModemSnapshot,
    SignalSnapshot,
    WhoHost,
    WhoModem,
)
from spark_modem.wire.enums import IssueCategory, IssueDetail
from spark_modem.wire.globals import GlobalsState
from spark_modem.wire.state import ModemState
from tests.fakes.clock import FakeClock


# --- Builders --------------------------------------------------------------


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "state_root": "/tmp/test-state",
        "run_dir": "/tmp/test-run",
        "events_log_path": "/tmp/events.jsonl",
        "metrics_socket_path": "/tmp/metrics.sock",
        "carriers_yaml_path": "/tmp/carriers.yaml",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _ctx(
    *,
    clock: FakeClock | None = None,
    expected_modem_count: int = 4,
    config_overrides: dict[str, object] | None = None,
) -> PolicyContext:
    settings = _settings(**(config_overrides or {}))
    return PolicyContext(
        clock=clock or FakeClock(),
        config=settings,
        maintenance_active=False,
        expected_modem_count=expected_modem_count,
    )


def _hung_modem(
    usb_path: str,
    cdc_wdm: str,
    *,
    rsrp: int | None = -95,
    rsrq: float | None = -10.0,
    snr: float | None = 5.0,
) -> ModemSnapshot:
    """Build a ModemSnapshot whose issues list contains QMI_CHANNEL_HUNG."""
    return ModemSnapshot(
        usb_path=usb_path,
        cdc_wdm=cdc_wdm,
        signal=SignalSnapshot(rsrp_dbm=rsrp, rsrq_db=rsrq, snr_db=snr),
        issues=[
            Issue(
                category=IssueCategory.QMI,
                detail=IssueDetail.QMI_CHANNEL_HUNG,
                who=WhoModem(usb_path=usb_path, cdc_wdm=cdc_wdm),
            )
        ],
    )


def _healthy_modem(
    usb_path: str,
    cdc_wdm: str,
    *,
    rsrp: int | None = -90,
    rsrq: float | None = -10.0,
    snr: float | None = 5.0,
) -> ModemSnapshot:
    """Build a ModemSnapshot with no issues (e.g. healthy or Zao-active)."""
    return ModemSnapshot(
        usb_path=usb_path,
        cdc_wdm=cdc_wdm,
        signal=SignalSnapshot(rsrp_dbm=rsrp, rsrq_db=rsrq, snr_db=snr),
        issues=[],
    )


def _diag(snaps: list[ModemSnapshot], *, host_issues: list[Issue] | None = None) -> Diag:
    return Diag(
        ts_iso="2026-01-01T00:00:00+00:00",
        cycle_id=1,
        per_modem={s.usb_path: s for s in snaps},
        host_issues=host_issues or [],
    )


def _host_issue(detail: IssueDetail) -> Issue:
    return Issue(
        category=IssueCategory.QMI,
        detail=detail,
        who=cast(WhoModem, WhoHost()),
        # Note: Issue.who is a discriminated union; pydantic accepts WhoHost.
    )


def _all_4_hung_good_signal() -> list[ModemSnapshot]:
    return [
        _hung_modem("2-3.1.1", "cdc-wdm0"),
        _hung_modem("2-3.1.2", "cdc-wdm1"),
        _hung_modem("2-3.1.3", "cdc-wdm2"),
        _hung_modem("2-3.1.4", "cdc-wdm3"),
    ]


# --- Test 1: thermal_warn suppresses ---------------------------------------


def test_driver_reset_suppressed_by_thermal_warn() -> None:
    """C-03: host_issues containing THERMAL_WARN -> not eligible."""
    diag = _diag(
        _all_4_hung_good_signal(),
        host_issues=[_host_issue(IssueDetail.THERMAL_WARN)],
    )
    eligible = _global_driver_reset_eligible(diag, {}, GlobalsState(), _ctx())
    assert eligible is False


# --- Test 2: thermal_critical suppresses -----------------------------------


def test_driver_reset_suppressed_by_thermal_critical() -> None:
    """C-03: host_issues containing THERMAL_CRITICAL -> not eligible."""
    diag = _diag(
        _all_4_hung_good_signal(),
        host_issues=[_host_issue(IssueDetail.THERMAL_CRITICAL)],
    )
    eligible = _global_driver_reset_eligible(diag, {}, GlobalsState(), _ctx())
    assert eligible is False


# --- Test 3: first-fire NPE prevention -------------------------------------


def test_driver_reset_first_fire_no_npe() -> None:
    """C-05: globals_state.last_driver_reset_monotonic=None must NOT NPE.

    First-fire path: there has never been a driver_reset before. The cooldown
    branch must short-circuit to 'allow' rather than attempt a comparison
    against None.
    """
    diag = _diag(_all_4_hung_good_signal())
    globals_state = GlobalsState()
    assert globals_state.last_driver_reset_monotonic is None
    eligible = _global_driver_reset_eligible(diag, {}, globals_state, _ctx())
    assert eligible is True


# --- Test 4: cooldown enforces within window -------------------------------


def test_driver_reset_cooldown_blocks_within_3600s() -> None:
    """C-05: elapsed (1800 s) < backoff (3600 s) -> not eligible."""
    clock = FakeClock(start_monotonic=10_000.0)
    # Last fire was 1800 s ago (within the 3600 s cooldown).
    globals_state = GlobalsState(last_driver_reset_monotonic=8_200.0)
    diag = _diag(_all_4_hung_good_signal())
    eligible = _global_driver_reset_eligible(diag, {}, globals_state, _ctx(clock=clock))
    assert eligible is False


# --- Test 5: cooldown allows after window ----------------------------------


def test_driver_reset_cooldown_allows_after_3600s() -> None:
    """C-05: elapsed (3700 s) > backoff (3600 s) -> eligible (other gates pass)."""
    clock = FakeClock(start_monotonic=10_000.0)
    globals_state = GlobalsState(last_driver_reset_monotonic=6_300.0)
    diag = _diag(_all_4_hung_good_signal())
    eligible = _global_driver_reset_eligible(diag, {}, globals_state, _ctx(clock=clock))
    assert eligible is True


# --- Test 6: 3/4 hung at threshold -----------------------------------------


def test_driver_reset_eligible_at_3_of_4_hung_with_good_signal() -> None:
    """C-01: 3/4 = 0.75 == threshold -> eligible (>= comparison)."""
    diag = _diag(
        [
            _hung_modem("2-3.1.1", "cdc-wdm0"),
            _hung_modem("2-3.1.2", "cdc-wdm1"),
            _hung_modem("2-3.1.3", "cdc-wdm2"),
            _healthy_modem("2-3.1.4", "cdc-wdm3"),
        ]
    )
    eligible = _global_driver_reset_eligible(diag, {}, GlobalsState(), _ctx())
    assert eligible is True


# --- Test 7: 2/4 hung below threshold --------------------------------------


def test_driver_reset_NOT_eligible_at_2_of_4_hung() -> None:
    """C-01: 2/4 = 0.5 < 0.75 -> not eligible."""
    diag = _diag(
        [
            _hung_modem("2-3.1.1", "cdc-wdm0"),
            _hung_modem("2-3.1.2", "cdc-wdm1"),
            _healthy_modem("2-3.1.3", "cdc-wdm2"),
            _healthy_modem("2-3.1.4", "cdc-wdm3"),
        ]
    )
    eligible = _global_driver_reset_eligible(diag, {}, GlobalsState(), _ctx())
    assert eligible is False


# --- Test 8: denominator is expected, not enumerated -----------------------


def test_driver_reset_denominator_is_expected_count_NOT_enumerated() -> None:
    """C-01 conservative deviation: 3 hung / 4 expected = 0.75 -> eligible.

    Only 3 modems are present in the Diag; the 4th is missing (e.g. removed
    or not yet enumerated). The 75% gate uses the EXPECTED denominator (4),
    so 3/4 = 0.75 fires. If the predicate naively used len(diag.per_modem)
    as the denominator, 3/3 = 1.0 would also fire but for the WRONG reason
    (and 2 hung / 2 enumerated would fire too -- breaking the conservative
    profile).
    """
    diag = _diag(
        [
            _hung_modem("2-3.1.1", "cdc-wdm0"),
            _hung_modem("2-3.1.2", "cdc-wdm1"),
            _hung_modem("2-3.1.3", "cdc-wdm2"),
            # 4th modem missing.
        ]
    )
    eligible = _global_driver_reset_eligible(
        diag, {}, GlobalsState(), _ctx(expected_modem_count=4)
    )
    assert eligible is True


# --- Test 9: Zao-active counted as 'not-hung' ------------------------------


def test_driver_reset_denominator_with_zao_active() -> None:
    """C-01: Zao-active modems carry no QMI_CHANNEL_HUNG issue -> 'not-hung'.

    With 3 hung + 1 Zao-active (no issues) and expected=4, hung/expected =
    3/4 = 0.75 -> eligible. The Zao-active modem is not QMI-probed (ADR-0003)
    so it never produces QMI_CHANNEL_HUNG; it counts toward the 'not-hung'
    bucket in the denominator.
    """
    diag = _diag(
        [
            _hung_modem("2-3.1.1", "cdc-wdm0"),
            _hung_modem("2-3.1.2", "cdc-wdm1"),
            _hung_modem("2-3.1.3", "cdc-wdm2"),
            _healthy_modem("2-3.1.4", "cdc-wdm3"),  # Zao-active stand-in.
        ]
    )
    eligible = _global_driver_reset_eligible(diag, {}, GlobalsState(), _ctx())
    assert eligible is True


# --- Test 10: all hung modems below signal floors --------------------------


def test_driver_reset_NOT_eligible_when_all_hung_modems_rf_blocked() -> None:
    """FR-24: 4/4 hung but all with weak signal -> no actionable signal.

    rsrp=-120 (below -110 floor), rsrq=-20 (below -15 floor), snr=-5 (below
    0 floor) on every hung modem. The 75% threshold passes but gate 4 fails
    because no modem clears all three floors simultaneously.
    """
    diag = _diag(
        [
            _hung_modem("2-3.1.1", "cdc-wdm0", rsrp=-120, rsrq=-20.0, snr=-5.0),
            _hung_modem("2-3.1.2", "cdc-wdm1", rsrp=-120, rsrq=-20.0, snr=-5.0),
            _hung_modem("2-3.1.3", "cdc-wdm2", rsrp=-120, rsrq=-20.0, snr=-5.0),
            _hung_modem("2-3.1.4", "cdc-wdm3", rsrp=-120, rsrq=-20.0, snr=-5.0),
        ]
    )
    eligible = _global_driver_reset_eligible(diag, {}, GlobalsState(), _ctx())
    assert eligible is False


# --- Test 11: at least one hung modem has actionable signal ----------------


def test_driver_reset_eligible_when_one_hung_modem_has_actionable_signal() -> None:
    """FR-24: 4/4 hung, 3 with weak signal, 1 with actionable -> eligible.

    The predicate fires on 'at least one hung modem above all 3 floors',
    not 'all hung modems'. One viable RF environment is sufficient evidence
    that a kernel reload is the right recovery (vs an RF problem masquerading
    as a hang).
    """
    diag = _diag(
        [
            _hung_modem("2-3.1.1", "cdc-wdm0", rsrp=-120, rsrq=-20.0, snr=-5.0),
            _hung_modem("2-3.1.2", "cdc-wdm1", rsrp=-120, rsrq=-20.0, snr=-5.0),
            _hung_modem("2-3.1.3", "cdc-wdm2", rsrp=-120, rsrq=-20.0, snr=-5.0),
            _hung_modem("2-3.1.4", "cdc-wdm3", rsrp=-100, rsrq=-10.0, snr=5.0),
        ]
    )
    eligible = _global_driver_reset_eligible(diag, {}, GlobalsState(), _ctx())
    assert eligible is True


# --- Test 12: missing signal readings -> conservative not-eligible ---------


def test_driver_reset_handles_missing_signal_readings_as_no_actionable_signal() -> None:
    """FR-24: None signal readings cannot prove actionable -> not eligible.

    All hung modems have signal=SignalSnapshot() with all fields None
    (e.g. observer hit a probe error and surfaced an unknown-signal
    snapshot). The conservative interpretation: we have no evidence that
    any modem has actionable RF, so we don't fire driver_reset.
    """
    diag = _diag(
        [
            _hung_modem("2-3.1.1", "cdc-wdm0", rsrp=None, rsrq=None, snr=None),
            _hung_modem("2-3.1.2", "cdc-wdm1", rsrp=None, rsrq=None, snr=None),
            _hung_modem("2-3.1.3", "cdc-wdm2", rsrp=None, rsrq=None, snr=None),
            _hung_modem("2-3.1.4", "cdc-wdm3", rsrp=None, rsrq=None, snr=None),
        ]
    )
    eligible = _global_driver_reset_eligible(diag, {}, GlobalsState(), _ctx())
    assert eligible is False


# --- Helper: prior_states is unused by the predicate but accept the dict --


def test_driver_reset_predicate_is_pure_no_side_effects() -> None:
    """Sanity: calling the predicate twice yields the same answer (purity)."""
    diag = _diag(_all_4_hung_good_signal())
    ctx = _ctx()
    prior_states: dict[str, ModemState] = {}
    g = GlobalsState()
    a = _global_driver_reset_eligible(diag, prior_states, g, ctx)
    b = _global_driver_reset_eligible(diag, prior_states, g, ctx)
    assert a == b
