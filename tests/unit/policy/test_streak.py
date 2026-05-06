"""Unit tests for FR-26.1 healthy_streak persistence + counter decay.

The transitions module produces the new state shape; the engine in
`engine.py` (Task 2) is responsible for actually updating
`healthy_streak` and applying the decay-on-K-consecutive-healthy rule.

These tests verify:
1. The transitions function preserves prior counters and streak
   across cycles -- it does NOT mutate them itself.
2. ModemState round-trips healthy_streak across model_dump_json /
   model_validate (FR-26.1: persisted every cycle, reloaded on
   daemon start; mid-streak restart does NOT reset progress).
3. healthy_streak == 0 after non-healthy transition (engine-level
   contract; we assert that the wire model accepts a zero-streak
   state and round-trips it cleanly so the engine can reset on
   non-healthy transitions in Task 2).
"""

from __future__ import annotations

from spark_modem.config.settings import Settings
from spark_modem.policy.context import PolicyContext
from spark_modem.policy.transitions import transition
from spark_modem.wire.diag import Issue, ModemSnapshot, SignalSnapshot, WhoModem
from spark_modem.wire.enums import ActionKind, IssueCategory, IssueDetail
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


def _state_with_streak(
    *,
    state: str = "healthy",
    healthy_streak: int = 0,
) -> ModemState:
    return ModemState.model_validate(
        {
            "state": state,
            "present": True,
            "rf_blocked": False,
            "recovering_level": None,
            "_healthy_streak": healthy_streak,
            "counters": {},
            "last_action_monotonic": None,
            "last_state_transition_iso": None,
        }
    )


def _clean_snap() -> ModemSnapshot:
    return ModemSnapshot(
        usb_path="2-3.1.1",
        cdc_wdm="cdc-wdm0",
        signal=SignalSnapshot(rsrp_dbm=-90, rsrq_db=-10.0, snr_db=5.0),
        issues=[],
    )


def _snap_with_issue() -> ModemSnapshot:
    return ModemSnapshot(
        usb_path="2-3.1.1",
        cdc_wdm="cdc-wdm0",
        signal=SignalSnapshot(rsrp_dbm=-90, rsrq_db=-10.0, snr_db=5.0),
        issues=[
            Issue(
                category=IssueCategory.SIM,
                detail=IssueDetail.SIM_APP_DETECTED,
                who=WhoModem(usb_path="2-3.1.1", cdc_wdm="cdc-wdm0"),
            )
        ],
    )


def test_transitions_preserve_streak_when_state_unchanged() -> None:
    """transitions() does NOT bump streak -- engine.run_cycle does.

    This pins the contract that transitions is purely state-shape: the
    streak update is engine-level (RECOVERY_SPEC §8 step 2).
    """
    prior = _state_with_streak(state="healthy", healthy_streak=5)
    new = transition(prior, _clean_snap(), _ctx())
    # transitions returns the new state shape; streak is preserved
    # for the engine to update in Task 2.
    assert new.healthy_streak == 5


def test_state_round_trips_healthy_streak_across_serialize() -> None:
    """FR-26.1: healthy_streak persists across model_dump_json round-trip.

    Simulates daemon restart: serialize a state with streak=7, parse it
    back, and assert the next-cycle transition starts from 7 (not 0).
    """
    state_before_restart = _state_with_streak(state="healthy", healthy_streak=7)
    payload = state_before_restart.model_dump_json(by_alias=True)
    state_after_restart = ModemState.model_validate_json(payload)
    assert state_after_restart.healthy_streak == 7

    # And the transitions function preserves it for the next cycle:
    new = transition(state_after_restart, _clean_snap(), _ctx())
    assert new.healthy_streak == 7  # unchanged by transitions; engine increments


def test_state_serialization_uses_underscore_alias() -> None:
    """The wire alias is `_healthy_streak` (FR-26.1)."""
    state = _state_with_streak(healthy_streak=3)
    payload = state.model_dump_json(by_alias=True)
    assert '"_healthy_streak":3' in payload


def test_state_round_trips_counters_across_serialize() -> None:
    """ADR-0006: per-action counters persist with state.

    The engine bumps counters; the wire model must round-trip them
    across daemon restart so the ladder rung selection is stable.
    """
    state = ModemState.model_validate(
        {
            "state": "recovering",
            "present": True,
            "rf_blocked": False,
            "recovering_level": 2,
            "_healthy_streak": 0,
            "counters": {ActionKind.SOFT_RESET.value: 3, ActionKind.MODEM_RESET.value: 1},
            "last_action_monotonic": None,
            "last_state_transition_iso": None,
        }
    )
    payload = state.model_dump_json(by_alias=True)
    state2 = ModemState.model_validate_json(payload)
    assert state2.counters[ActionKind.SOFT_RESET] == 3
    assert state2.counters[ActionKind.MODEM_RESET] == 1


def test_streak_zeroes_through_non_healthy_state_round_trip() -> None:
    """A degraded state with streak=0 round-trips cleanly.

    The engine resets streak to 0 on non-healthy transitions in Task 2;
    this test pins the wire-model contract that streak=0 is valid.
    """
    state = _state_with_streak(state="degraded", healthy_streak=0)
    new = transition(state, _snap_with_issue(), _ctx())
    assert new.state == "degraded"
    # streak preserved by transitions; engine zeroes it.
    payload = new.model_dump_json(by_alias=True)
    parsed = ModemState.model_validate_json(payload)
    assert parsed.healthy_streak == 0


def test_streak_increments_each_healthy_cycle_in_simulation() -> None:
    """Simulate 12 cycles where the state remains healthy and streak grows.

    transitions does not bump streak; we simulate the engine's bump
    inline (the engine-level decay test lives in test_engine.py / Task 2).
    """
    state = _state_with_streak(state="healthy", healthy_streak=0)
    streak_history: list[int] = []
    for _ in range(12):
        new = transition(state, _clean_snap(), _ctx())
        # Simulate engine step 2 inline: bump streak when state is healthy.
        new = new.model_copy(update={"healthy_streak": new.healthy_streak + 1})
        streak_history.append(new.healthy_streak)
        state = new
    assert streak_history == list(range(1, 13))
