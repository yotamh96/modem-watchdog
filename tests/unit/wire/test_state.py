"""Tests for src.spark_modem.wire.state — ModemState 5+2 shape (ADR-0008)."""

import pytest
from pydantic import ValidationError

from spark_modem.wire.enums import ActionKind
from spark_modem.wire.state import ModemState, state_to_int


def test_modem_state_healthy_constructs() -> None:
    """ModemState with state='healthy' and no recovering_level constructs cleanly."""
    m = ModemState(state="healthy", recovering_level=None, present=True, rf_blocked=False)
    assert m.state == "healthy"
    assert m.recovering_level is None
    assert m.present is True
    assert m.rf_blocked is False


def test_modem_state_recovering_with_level_constructs() -> None:
    """ModemState with state='recovering' and recovering_level >= 1 constructs."""
    m = ModemState(state="recovering", recovering_level=2, present=True, rf_blocked=False)
    assert m.state == "recovering"
    assert m.recovering_level == 2


def test_modem_state_recovering_without_level_raises() -> None:
    """state='recovering' with recovering_level=None must raise ValidationError."""
    with pytest.raises(ValidationError, match="recovering_level is required"):
        ModemState(state="recovering", recovering_level=None, present=True, rf_blocked=False)


def test_modem_state_non_recovering_with_level_raises() -> None:
    """recovering_level must be None when state != 'recovering'."""
    with pytest.raises(ValidationError, match="recovering_level must be None"):
        ModemState(state="healthy", recovering_level=2, present=True, rf_blocked=False)


def test_modem_state_only_five_states_accepted() -> None:
    """Only 'unknown','healthy','degraded','recovering','exhausted' are valid states."""
    for valid in ("unknown", "healthy", "degraded", "exhausted"):
        m = ModemState(state=valid, recovering_level=None, present=True, rf_blocked=False)
        assert m.state == valid

    with pytest.raises(ValidationError):
        ModemState(state="rf_blocked", recovering_level=None, present=True, rf_blocked=False)  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        ModemState(state="connected", recovering_level=None, present=True, rf_blocked=False)  # type: ignore[arg-type]


def test_modem_state_schema_version_default() -> None:
    """ModemState has a schema_version defaulting to 1."""
    m = ModemState(state="healthy", recovering_level=None, present=True, rf_blocked=False)
    assert m.schema_version == 1


def test_modem_state_healthy_streak_default() -> None:
    """_healthy_streak defaults to 0 (FR-26.1)."""
    m = ModemState(state="healthy", recovering_level=None, present=True, rf_blocked=False)
    assert m.healthy_streak == 0


def test_modem_state_healthy_streak_via_alias() -> None:
    """_healthy_streak can be set via the alias '_healthy_streak' (ADR-0006)."""
    m = ModemState.model_validate(
        {
            "state": "healthy",
            "recovering_level": None,
            "present": True,
            "rf_blocked": False,
            "_healthy_streak": 5,
        }
    )
    assert m.healthy_streak == 5


def test_modem_state_counters_default_empty() -> None:
    """Counters default to an empty dict."""
    m = ModemState(state="healthy", recovering_level=None, present=True, rf_blocked=False)
    assert m.counters == {}


def test_modem_state_counters_with_action_kinds() -> None:
    """Counters accept ActionKind keys with non-negative int values."""
    m = ModemState(
        state="degraded",
        recovering_level=None,
        present=True,
        rf_blocked=False,
        counters={ActionKind.SOFT_RESET: 3, ActionKind.MODEM_RESET: 1},
    )
    assert m.counters[ActionKind.SOFT_RESET] == 3


def test_modem_state_counters_negative_raises() -> None:
    """Negative counter values must raise ValidationError."""
    with pytest.raises(ValidationError, match="must be >= 0"):
        ModemState(
            state="degraded",
            recovering_level=None,
            present=True,
            rf_blocked=False,
            counters={ActionKind.SOFT_RESET: -1},
        )


def test_modem_state_last_action_monotonic_default_none() -> None:
    """last_action_monotonic defaults to None (ADR-0007)."""
    m = ModemState(state="healthy", recovering_level=None, present=True, rf_blocked=False)
    assert m.last_action_monotonic is None


def test_modem_state_last_state_transition_iso_default_none() -> None:
    """last_state_transition_iso defaults to None."""
    m = ModemState(state="healthy", recovering_level=None, present=True, rf_blocked=False)
    assert m.last_state_transition_iso is None


def test_modem_state_round_trip_json() -> None:
    """ModemState round-trips via model_dump_json / model_validate_json."""
    m = ModemState(
        state="recovering",
        recovering_level=2,
        present=True,
        rf_blocked=False,
        counters={ActionKind.SOFT_RESET: 2},
        last_action_monotonic=12300.0,
        last_state_transition_iso="2026-05-06T00:00:00+00:00",
    )
    j = m.model_dump_json(by_alias=True)
    m2 = ModemState.model_validate_json(j)
    assert m == m2


def _ms(state: str, level: int | None = None) -> ModemState:
    """Helper: construct a ModemState with minimal required fields."""
    return ModemState(state=state, recovering_level=level, present=True, rf_blocked=False)  # type: ignore[arg-type]


def test_state_to_int_stable_mapping() -> None:
    """state_to_int returns the canonical ADR-0013 integer encoding."""
    assert state_to_int(_ms("unknown")) == 0
    assert state_to_int(_ms("healthy")) == 1
    assert state_to_int(_ms("degraded")) == 2
    assert state_to_int(_ms("recovering", level=1)) == 3
    assert state_to_int(_ms("exhausted")) == 4
