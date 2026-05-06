"""Unit tests for policy.gates -- pure gate predicates.

Covers RECOVERY_SPEC §6 gate variants:
  - Disconnected (§6.5)
  - Maintenance (C-01)
  - Signal-quality (§6.1)
  - Same-action backoff (§6.2 / FR-25)
  - Cross-action ladder backoff (§6.3 / FR-25.1)
  - Exhausted (§6.6)
"""

from __future__ import annotations

from spark_modem.config.settings import Settings
from spark_modem.policy.gates import (
    gate_disconnected,
    gate_exhausted,
    gate_ladder_backoff,
    gate_maintenance,
    gate_same_action_backoff,
    gate_signal,
)
from spark_modem.wire.enums import ActionKind
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


def _state(
    *,
    state: str = "healthy",
    present: bool = True,
    rf_blocked: bool = False,
    last_action_monotonic: float | None = None,
    recovering_level: int | None = None,
) -> ModemState:
    return ModemState.model_validate(
        {
            "state": state,
            "present": present,
            "rf_blocked": rf_blocked,
            "recovering_level": recovering_level,
            "_healthy_streak": 0,
            "counters": {},
            "last_action_monotonic": last_action_monotonic,
            "last_state_transition_iso": None,
        }
    )


# --- gate_disconnected ---


def test_gate_disconnected_skips_when_present_false() -> None:
    """present=False -> True (skip)."""
    assert gate_disconnected(_state(present=False)) is True


def test_gate_disconnected_passes_when_present_true() -> None:
    """present=True -> False (no skip)."""
    assert gate_disconnected(_state(present=True)) is False


# --- gate_maintenance (C-01) ---


def test_gate_maintenance_skips_destructive() -> None:
    """maintenance_active=True + destructive action -> True (skip)."""
    assert gate_maintenance(True, ActionKind.MODEM_RESET) is True
    assert gate_maintenance(True, ActionKind.USB_RESET) is True
    assert gate_maintenance(True, ActionKind.DRIVER_RESET) is True


def test_gate_maintenance_allows_cheap_during_window() -> None:
    """C-01: cheap actions still run during maintenance."""
    assert gate_maintenance(True, ActionKind.SET_APN) is False
    assert gate_maintenance(True, ActionKind.FIX_RAW_IP) is False
    assert gate_maintenance(True, ActionKind.SOFT_RESET) is False
    assert gate_maintenance(True, ActionKind.SIM_POWER_ON) is False


def test_gate_maintenance_disabled_passes_destructive() -> None:
    """maintenance_active=False -> False even for destructive."""
    assert gate_maintenance(False, ActionKind.MODEM_RESET) is False


# --- gate_signal (RECOVERY_SPEC §6.1) ---


def test_gate_signal_skips_destructive_when_rf_blocked() -> None:
    """rf_blocked=True + destructive -> True (skip)."""
    state = _state(rf_blocked=True)
    assert gate_signal(state, ActionKind.MODEM_RESET) is True
    assert gate_signal(state, ActionKind.USB_RESET) is True


def test_gate_signal_passes_cheap_actions_even_when_rf_blocked() -> None:
    """RECOVERY_SPEC §6.1: cheap actions run even during rf_blocked."""
    state = _state(rf_blocked=True)
    assert gate_signal(state, ActionKind.SET_APN) is False
    assert gate_signal(state, ActionKind.FIX_RAW_IP) is False
    assert gate_signal(state, ActionKind.SOFT_RESET) is False
    assert gate_signal(state, ActionKind.SIM_POWER_ON) is False


def test_gate_signal_passes_destructive_when_rf_ok() -> None:
    """rf_blocked=False -> destructive action passes the signal gate."""
    assert gate_signal(_state(rf_blocked=False), ActionKind.MODEM_RESET) is False


# --- gate_same_action_backoff (FR-25, default 300s) ---


def test_gate_same_action_backoff_blocks_within_300s() -> None:
    """last_action at t0; clock at t0+200 -> backoff active."""
    clock = FakeClock(start_monotonic=200.0)
    state = _state(last_action_monotonic=0.0)
    assert (
        gate_same_action_backoff(state, ActionKind.SOFT_RESET, clock, _settings())
        is True
    )


def test_gate_same_action_backoff_passes_after_300s() -> None:
    """clock at t0+301 -> backoff cleared."""
    clock = FakeClock(start_monotonic=301.0)
    state = _state(last_action_monotonic=0.0)
    assert (
        gate_same_action_backoff(state, ActionKind.SOFT_RESET, clock, _settings())
        is False
    )


def test_gate_same_action_backoff_passes_when_first_action() -> None:
    """last_action_monotonic=None -> never backoff (first action)."""
    clock = FakeClock(start_monotonic=10000.0)
    state = _state(last_action_monotonic=None)
    assert (
        gate_same_action_backoff(state, ActionKind.SOFT_RESET, clock, _settings())
        is False
    )


def test_gate_same_action_backoff_at_exact_threshold_blocks() -> None:
    """Strict-less-than: exactly at backoff_seconds is still blocked."""
    # Settings.backoff_seconds default is 300; t0+299 < 300 -> blocked.
    clock = FakeClock(start_monotonic=299.0)
    state = _state(last_action_monotonic=0.0)
    assert (
        gate_same_action_backoff(state, ActionKind.SOFT_RESET, clock, _settings())
        is True
    )


# --- gate_ladder_backoff (FR-25.1, default 90s, destructive only) ---


def test_gate_ladder_backoff_only_fires_for_destructive() -> None:
    """Cheap actions bypass the cross-action ladder backoff."""
    clock = FakeClock(start_monotonic=10.0)
    state = _state(last_action_monotonic=0.0)
    assert (
        gate_ladder_backoff(state, ActionKind.SOFT_RESET, clock, _settings()) is False
    )
    assert gate_ladder_backoff(state, ActionKind.SET_APN, clock, _settings()) is False
    assert (
        gate_ladder_backoff(state, ActionKind.FIX_RAW_IP, clock, _settings()) is False
    )
    assert (
        gate_ladder_backoff(state, ActionKind.SIM_POWER_ON, clock, _settings()) is False
    )


def test_gate_ladder_backoff_blocks_destructive_within_90s() -> None:
    """last_action at t0; clock at t0+45 -> ladder backoff active."""
    clock = FakeClock(start_monotonic=45.0)
    state = _state(last_action_monotonic=0.0)
    assert (
        gate_ladder_backoff(state, ActionKind.MODEM_RESET, clock, _settings()) is True
    )
    assert gate_ladder_backoff(state, ActionKind.USB_RESET, clock, _settings()) is True


def test_gate_ladder_backoff_passes_destructive_after_90s() -> None:
    """t0+91 -> ladder backoff cleared."""
    clock = FakeClock(start_monotonic=91.0)
    state = _state(last_action_monotonic=0.0)
    assert (
        gate_ladder_backoff(state, ActionKind.MODEM_RESET, clock, _settings()) is False
    )


def test_gate_ladder_backoff_passes_when_first_action() -> None:
    """last_action_monotonic=None -> not blocked."""
    clock = FakeClock(start_monotonic=1000.0)
    state = _state(last_action_monotonic=None)
    assert (
        gate_ladder_backoff(state, ActionKind.MODEM_RESET, clock, _settings()) is False
    )


# --- gate_exhausted (RECOVERY_SPEC §6.6) ---


def test_gate_exhausted_blocks_modem_reset() -> None:
    """state=exhausted + ladder action -> True (skip)."""
    state = _state(state="exhausted")
    assert gate_exhausted(state, ActionKind.MODEM_RESET) is True
    assert gate_exhausted(state, ActionKind.USB_RESET) is True
    assert gate_exhausted(state, ActionKind.SOFT_RESET) is True
    assert gate_exhausted(state, ActionKind.SIM_POWER_ON) is True


def test_gate_exhausted_allows_set_apn_and_fix_raw_ip() -> None:
    """RECOVERY_SPEC §6.6: only set_apn / fix_raw_ip allowed in exhausted."""
    state = _state(state="exhausted")
    assert gate_exhausted(state, ActionKind.SET_APN) is False
    assert gate_exhausted(state, ActionKind.FIX_RAW_IP) is False


def test_gate_exhausted_irrelevant_when_state_not_exhausted() -> None:
    """state=degraded -> exhausted gate never trips."""
    state = _state(state="degraded")
    assert gate_exhausted(state, ActionKind.MODEM_RESET) is False
    assert gate_exhausted(state, ActionKind.SOFT_RESET) is False
    assert gate_exhausted(state, ActionKind.SET_APN) is False
