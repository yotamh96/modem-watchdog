"""Unit tests for policy.ladder -- pure-function rung selector (Phase 4 B-01).

Covers the four RECOVERY_SPEC §10.2 progression scenarios PLUS:
  - DATAPATH base-rung-2 path (SESSION_DISCONNECTED -> base MODEM_RESET; ladder
    starts at MODEM rung when MODEM counter unfilled)
  - Settings overrides: max_soft = 10 (from default 3) flips a counter=5 case
    from MODEM_RESET back to SOFT_RESET
  - Non-ladder ActionKind passthrough (DRIVER_RESET / SET_APN ignore the ladder)

CLAUDE.md invariant 1: ladder.py is a pure function -- no I/O, no subprocess.
This test module imports only typing + Settings + ladder + ActionKind.
"""

from __future__ import annotations

from spark_modem.config.settings import Settings
from spark_modem.policy.ladder import select_rung
from spark_modem.wire.enums import ActionKind


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


# --- RECOVERY_SPEC §10.2 progression scenarios (registration ladder) ------


def test_ladder_picks_soft_reset_when_counter_zero() -> None:
    """Scenario A: counters={} -> SOFT_RESET (rung 1)."""
    rung = select_rung(
        base=ActionKind.SOFT_RESET, counters={}, config=_settings()
    )
    assert rung == ActionKind.SOFT_RESET


def test_ladder_promotes_to_modem_reset_at_max_soft() -> None:
    """Scenario B: counters={SOFT_RESET: 3} (== max_soft default 3) -> MODEM_RESET."""
    rung = select_rung(
        base=ActionKind.SOFT_RESET,
        counters={ActionKind.SOFT_RESET: 3},
        config=_settings(),
    )
    assert rung == ActionKind.MODEM_RESET


def test_ladder_promotes_to_usb_reset_at_max_modem() -> None:
    """Scenario C: counters={SOFT:3, MODEM:2} -> USB_RESET (rung 3)."""
    rung = select_rung(
        base=ActionKind.SOFT_RESET,
        counters={ActionKind.SOFT_RESET: 3, ActionKind.MODEM_RESET: 2},
        config=_settings(),
    )
    assert rung == ActionKind.USB_RESET


def test_ladder_returns_skip_exhausted_when_all_rungs_at_ceiling() -> None:
    """Scenario D: counters={SOFT:3, MODEM:2, USB:1} -> 'skip:exhausted'."""
    rung = select_rung(
        base=ActionKind.SOFT_RESET,
        counters={
            ActionKind.SOFT_RESET: 3,
            ActionKind.MODEM_RESET: 2,
            ActionKind.USB_RESET: 1,
        },
        config=_settings(),
    )
    assert rung == "skip:exhausted"


# --- DATAPATH path: ladder STARTS at MODEM_RESET (base from decision_table) --


def test_ladder_session_disconnected_starts_at_modem_reset() -> None:
    """(DATAPATH, SESSION_DISCONNECTED) base is MODEM_RESET; ladder starts there.

    The decision table maps SESSION_DISCONNECTED -> MODEM_RESET (not SOFT_RESET);
    the ladder respects that by starting from rung-2 when called with
    base=MODEM_RESET. Empty counters -> stays at MODEM_RESET.
    """
    rung = select_rung(
        base=ActionKind.MODEM_RESET, counters={}, config=_settings()
    )
    assert rung == ActionKind.MODEM_RESET


def test_ladder_picks_usb_reset_when_modem_reset_ceiling_for_datapath() -> None:
    """DATAPATH base=MODEM_RESET, counter at ceiling -> promotes to USB_RESET.

    The SOFT_RESET rung is BELOW the base; the ladder doesn't walk backwards.
    """
    rung = select_rung(
        base=ActionKind.MODEM_RESET,
        counters={ActionKind.MODEM_RESET: 2},
        config=_settings(),
    )
    assert rung == ActionKind.USB_RESET


# --- Settings overrides: ladder is config-driven ---------------------------


def test_ladder_uses_settings_overrides() -> None:
    """max_soft=10 (overrides default 3) -> counter=5 still sits at SOFT_RESET."""
    rung = select_rung(
        base=ActionKind.SOFT_RESET,
        counters={ActionKind.SOFT_RESET: 5},
        config=_settings(max_soft=10),
    )
    assert rung == ActionKind.SOFT_RESET


# --- Non-ladder ActionKind passthrough -------------------------------------


def test_ladder_passes_through_non_destructive_action_kinds() -> None:
    """Non-ladder ActionKinds (SET_APN, FIX_RAW_IP, SIM_POWER_ON) -> base unchanged.

    The ladder only owns the destructive triplet (SOFT/MODEM/USB_RESET); cheap
    actions don't escalate, so select_rung returns them as-is.
    """
    for non_ladder in (
        ActionKind.SET_APN,
        ActionKind.FIX_RAW_IP,
        ActionKind.SIM_POWER_ON,
        ActionKind.FIX_AUTOSUSPEND,
        ActionKind.SET_OPERATING_MODE,
    ):
        rung = select_rung(
            base=non_ladder,
            counters={ActionKind.SOFT_RESET: 99},  # huge counter, irrelevant
            config=_settings(),
        )
        assert rung == non_ladder


def test_ladder_passes_through_driver_reset() -> None:
    """DRIVER_RESET is a global action, not a per-modem ladder rung.

    DRIVER_RESET fires from the engine's short-circuit path
    (_global_driver_reset_eligible), not from a per-modem decision-table
    lookup that hits the ladder. select_rung returns it unchanged.
    """
    rung = select_rung(
        base=ActionKind.DRIVER_RESET,
        counters={
            ActionKind.SOFT_RESET: 3,
            ActionKind.MODEM_RESET: 2,
            ActionKind.USB_RESET: 1,
        },
        config=_settings(),
    )
    assert rung == ActionKind.DRIVER_RESET
