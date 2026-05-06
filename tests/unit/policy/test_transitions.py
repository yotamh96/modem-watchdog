"""Unit tests for policy.transitions -- pure state-machine transitions.

Covers RECOVERY_SPEC §3.2 (state transitions) and §6.1 (rf_blocked
threshold derivation from snap.signal).  Also asserts the source file
uses `match prior.state:` (CLAUDE.md anti-pattern catalogue forbids
if/elif on ModemState).
"""

from __future__ import annotations

from pathlib import Path

from spark_modem.config.settings import Settings
from spark_modem.policy.context import PolicyContext
from spark_modem.policy.transitions import is_signal_below_gate, transition
from spark_modem.wire.diag import Issue, ModemSnapshot, SignalSnapshot, WhoModem
from spark_modem.wire.enums import IssueCategory, IssueDetail
from spark_modem.wire.state import ModemState
from tests.fakes.clock import FakeClock


def _settings() -> Settings:
    return Settings(
        state_root="/tmp/test-state",
        run_dir="/tmp/test-run",
        events_log_path="/tmp/events.jsonl",
        metrics_socket_path="/tmp/metrics.sock",
        carriers_yaml_path="/tmp/carriers.yaml",
    )


def _ctx() -> PolicyContext:
    return PolicyContext(
        clock=FakeClock(),
        config=_settings(),
        maintenance_active=False,
        expected_modem_count=1,
    )


def _state(
    *,
    state: str = "unknown",
    healthy_streak: int = 0,
    recovering_level: int | None = None,
    last_action_monotonic: float | None = None,
) -> ModemState:
    return ModemState.model_validate(
        {
            "state": state,
            "present": True,
            "rf_blocked": False,
            "recovering_level": recovering_level,
            "_healthy_streak": healthy_streak,
            "counters": {},
            "last_action_monotonic": last_action_monotonic,
            "last_state_transition_iso": None,
        }
    )


def _snap(
    *,
    issues: list[Issue] | None = None,
    rsrp_dbm: int | None = -90,
    rsrq_db: float | None = -10.0,
    snr_db: float | None = 5.0,
) -> ModemSnapshot:
    return ModemSnapshot(
        usb_path="2-3.1.1",
        cdc_wdm="cdc-wdm0",
        signal=SignalSnapshot(rsrp_dbm=rsrp_dbm, rsrq_db=rsrq_db, snr_db=snr_db),
        issues=issues or [],
    )


def _issue(
    category: IssueCategory = IssueCategory.SIM,
    detail: IssueDetail = IssueDetail.SIM_APP_DETECTED,
) -> Issue:
    return Issue(
        category=category,
        detail=detail,
        who=WhoModem(usb_path="2-3.1.1", cdc_wdm="cdc-wdm0"),
    )


# --- 1: bootstrap path ---------------------------------------------------


def test_no_issues_no_signal_block_returns_healthy() -> None:
    """prior=unknown + no issues + good signal -> healthy."""
    new = transition(_state(state="unknown"), _snap(), _ctx())
    assert new.state == "healthy"
    assert new.rf_blocked is False
    assert new.present is True


def test_unknown_with_issues_returns_degraded() -> None:
    """prior=unknown + 1 issue + good signal -> degraded."""
    new = transition(
        _state(state="unknown"),
        _snap(issues=[_issue()]),
        _ctx(),
    )
    assert new.state == "degraded"
    assert new.rf_blocked is False


def test_healthy_with_issues_returns_degraded() -> None:
    """prior=healthy + 1 issue -> degraded."""
    new = transition(
        _state(state="healthy"),
        _snap(issues=[_issue()]),
        _ctx(),
    )
    assert new.state == "degraded"


def test_recovering_with_no_issues_returns_healthy() -> None:
    """Recovering snapshot turning clean -> healthy (level cleared)."""
    new = transition(
        _state(state="recovering", recovering_level=2),
        _snap(),
        _ctx(),
    )
    assert new.state == "healthy"
    assert new.recovering_level is None


def test_recovering_with_issues_stays_recovering() -> None:
    """Still has issues -> stays recovering with level preserved."""
    new = transition(
        _state(state="recovering", recovering_level=2),
        _snap(issues=[_issue()]),
        _ctx(),
    )
    assert new.state == "recovering"
    assert new.recovering_level == 2


def test_exhausted_holds_until_decay() -> None:
    """prior=exhausted + 0 issues -> stays exhausted (decay tested in test_streak)."""
    # NOTE: An exhausted modem with NO issues would normally go to healthy
    # via the early-return path; but the spec says exhausted holds until
    # counter decay. Pass an issue so the early-return doesn't trigger;
    # the match arm should keep us in exhausted.
    new = transition(
        _state(state="exhausted"),
        _snap(issues=[_issue()]),
        _ctx(),
    )
    assert new.state == "exhausted"


def test_exhausted_to_healthy_on_clear_snapshot() -> None:
    """WR-01: exhausted -> healthy when issues clear AND signal good.

    RECOVERY_SPEC §3.2: an exhausted modem must be able to return to
    healthy when the snapshot becomes clean (no issues, signal above
    gate).  This is currently served by the early-return at the top of
    ``transition``, but the explicit ``case "exhausted":`` arm now also
    handles it defensively so a future refactor of the early-return
    cannot regress M4 (zero exhausted-stuck).
    """
    new = transition(
        _state(state="exhausted"),
        _snap(),  # default signal: rsrp=-90, rsrq=-10, snr=5 (all above gate)
        _ctx(),
    )
    assert new.state == "healthy"
    assert new.recovering_level is None
    assert new.rf_blocked is False


def test_exhausted_with_rf_blocked_only_stays_exhausted() -> None:
    """WR-01 boundary: exhausted + no issues + rf_blocked -> stays exhausted.

    The recovery condition requires BOTH ``not snap.issues`` AND
    ``not rf_blocked``; if signal is below gate, the modem must stay
    exhausted even with an empty issues list (the radio environment is
    not yet good enough to declare recovery).
    """
    new = transition(
        _state(state="exhausted"),
        _snap(rsrp_dbm=-115),  # rf_blocked = True; no issues
        _ctx(),
    )
    assert new.state == "exhausted"
    assert new.rf_blocked is True


# --- 2: rf_blocked derivation -------------------------------------------


def test_rf_blocked_set_when_rsrp_below_minus_110() -> None:
    """rsrp_dbm=-115 -> rf_blocked=True (RECOVERY_SPEC §6.1)."""
    new = transition(
        _state(),
        _snap(issues=[_issue()], rsrp_dbm=-115),
        _ctx(),
    )
    assert new.rf_blocked is True


def test_rf_blocked_set_when_rsrq_below_minus_15() -> None:
    """rsrq_db=-19 -> rf_blocked=True."""
    new = transition(
        _state(),
        _snap(issues=[_issue()], rsrq_db=-19.0),
        _ctx(),
    )
    assert new.rf_blocked is True


def test_rf_blocked_set_when_snr_below_0() -> None:
    """snr_db=-3 -> rf_blocked=True."""
    new = transition(
        _state(),
        _snap(issues=[_issue()], snr_db=-3.0),
        _ctx(),
    )
    assert new.rf_blocked is True


def test_rf_blocked_false_when_signal_missing() -> None:
    """All signal fields None -> rf_blocked=False (absence is not a block)."""
    new = transition(
        _state(),
        _snap(issues=[_issue()], rsrp_dbm=None, rsrq_db=None, snr_db=None),
        _ctx(),
    )
    assert new.rf_blocked is False


def test_is_signal_below_gate_at_threshold_boundary() -> None:
    """Strict-less-than: rsrp=-110 itself is NOT below gate (boundary)."""
    snap = _snap(rsrp_dbm=-110, rsrq_db=-15.0, snr_db=0.0)
    assert is_signal_below_gate(snap) is False


def test_is_signal_below_gate_just_below_threshold() -> None:
    """One field a hair below threshold trips the gate."""
    snap = _snap(rsrp_dbm=-111, rsrq_db=-10.0, snr_db=5.0)
    assert is_signal_below_gate(snap) is True


# --- 3: rf_blocked + no issues stays healthy (RECOVERY_SPEC §3.2) ------


def test_rf_only_with_no_issues_returns_healthy() -> None:
    """rf_blocked is reflected in flag but state is healthy if no issues.

    Per RECOVERY_SPEC §3.2 first conditional: "no issues AND signal not
    measurably below threshold -> healthy". Here signal IS below
    threshold but no issues, so we have an RF-only condition. The
    transition spec keeps this in healthy with rf_blocked flag set.
    """
    new = transition(
        _state(state="healthy"),
        _snap(rsrp_dbm=-115),  # rf_blocked condition, but no issues
        _ctx(),
    )
    # Spec is ambiguous here -- pick the conservative behavior:
    # rf_blocked alone (no issues) is a degraded radio. We mark it as
    # such; cheap actions can still run (RECOVERY_SPEC §6.1).
    # But the transition function's first conditional only short-circuits
    # to healthy when rf_blocked is False. With rf_blocked=True we fall
    # into the match arms.
    # For prior=healthy + rf_blocked + no issues: we land in
    # `case "healthy"` with no issues, returning healthy.  The rf flag
    # is set; the engine's gates handle the rest.
    assert new.state == "healthy"
    assert new.rf_blocked is True


# --- 4: structural -- match enforcement ---------------------------------


def test_transitions_uses_match_statement_not_if_elif() -> None:
    """CLAUDE.md anti-pattern catalogue: forbid `if/elif` on ModemState."""
    src = (
        Path(__file__).resolve().parents[3] / "src" / "spark_modem" / "policy" / "transitions.py"
    ).read_text(encoding="utf-8")
    assert "match prior.state:" in src, (
        "transitions.py must dispatch via `match prior.state:` -- "
        "CLAUDE.md anti-patterns forbid if/elif on ModemState"
    )
