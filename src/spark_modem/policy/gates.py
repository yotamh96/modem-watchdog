"""Gates (RECOVERY_SPEC §6).  Pure functions; no I/O.

Gate order (FR-20):
  1. Disconnected
  2. Maintenance (C-01: destructive only; cheap actions still run)
  3. Signal-quality (Phase 2 reads ModemState.rf_blocked which is set by
     transitions.py from snap.signal thresholds)
  4. Same-action backoff (FR-25, default 300s)
  5. Cross-action ladder backoff (FR-25.1, default 90s)
  6. Exhausted (RECOVERY_SPEC §6.6: only set_apn / fix_raw_ip allowed)

All durations use clock.monotonic() arithmetic (ADR-0007).
"""

from __future__ import annotations

from spark_modem.config.settings import Settings
from spark_modem.policy.context import ClockProto
from spark_modem.wire.enums import ActionKind
from spark_modem.wire.state import ModemState

_DESTRUCTIVE_KINDS: frozenset[ActionKind] = frozenset(
    {
        ActionKind.MODEM_RESET,
        ActionKind.USB_RESET,
        ActionKind.DRIVER_RESET,
    }
)

_CHEAP_KINDS_DURING_EXHAUSTED: frozenset[ActionKind] = frozenset(
    {
        ActionKind.SET_APN,
        ActionKind.FIX_RAW_IP,
    }
)


def gate_disconnected(state: ModemState) -> bool:
    """Return True if action MUST be skipped because modem is absent.

    Derived from the orthogonal `present` flag (ADR-0008 5+2 shape).
    """
    return not state.present


def gate_maintenance(maintenance_active: bool, action: ActionKind) -> bool:
    """C-01: destructive actions skipped during maintenance; cheap run.

    Returns True if this action should be skipped due to active
    maintenance window.
    """
    if not maintenance_active:
        return False
    return action in _DESTRUCTIVE_KINDS


def gate_signal(state: ModemState, action: ActionKind) -> bool:
    """RECOVERY_SPEC §6.1: rf_blocked -> skip destructive actions.

    Phase 2 reads ModemState.rf_blocked which the transitions module sets
    based on signal-quality threshold checks against ModemSnapshot.

    Cheap actions (set_apn / fix_raw_ip / sim_power_on / soft_reset) are
    NEVER gated on signal -- they don't damage uptime when run during
    bad RF (RECOVERY_SPEC §6.1 last paragraph).
    """
    if action not in _DESTRUCTIVE_KINDS:
        return False
    return state.rf_blocked


def gate_same_action_backoff(
    state: ModemState,
    action: ActionKind,
    clock: ClockProto,
    config: Settings,
) -> bool:
    """FR-25: skip if same action attempted within backoff_seconds (300s).

    Uses monotonic clock arithmetic (ADR-0007).

    Per-action timestamps are NOT persisted in ModemState today (only
    last_action_monotonic globally per modem); the engine treats
    same-action and cross-action backoffs uniformly off this single
    timestamp in Phase 2.  Phase 4 may split per-action timestamps.

    The `action` parameter is reserved for the Phase 4 split; see also
    `gate_ladder_backoff` which DOES discriminate by action kind.
    """
    del action  # reserved for Phase 4 per-action timestamp split
    if state.last_action_monotonic is None:
        return False
    elapsed = clock.monotonic() - state.last_action_monotonic
    return elapsed < float(config.backoff_seconds)


def gate_ladder_backoff(
    state: ModemState,
    action: ActionKind,
    clock: ClockProto,
    config: Settings,
) -> bool:
    """FR-25.1: cross-action ladder backoff for destructive actions.

    No destructive action runs more than once every
    config.ladder_min_interval_seconds (default 90s).  Cheap actions
    (soft_reset, set_apn, etc.) bypass this gate.

    See RECOVERY_SPEC §6.3 -- prevents v1's soft -> modem -> soft -> modem
    ping-pong.
    """
    if action not in _DESTRUCTIVE_KINDS:
        return False
    if state.last_action_monotonic is None:
        return False
    elapsed = clock.monotonic() - state.last_action_monotonic
    return elapsed < float(config.ladder_min_interval_seconds)


def gate_exhausted(state: ModemState, action: ActionKind) -> bool:
    """RECOVERY_SPEC §6.6: in exhausted state, only cheap kinds allowed.

    Returns True (skip) for ladder-rung actions when state is exhausted.
    set_apn / fix_raw_ip remain allowed because they're cheap and may
    break the deadlock.
    """
    if state.state != "exhausted":
        return False
    return action not in _CHEAP_KINDS_DURING_EXHAUSTED
