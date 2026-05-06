"""State-machine transitions (RECOVERY_SPEC §3, ADR-0008 5+2 shape).

Pure function: (prior, snap, ctx) -> new ModemState.  No I/O.

`match` on ModemState.state -- CLAUDE.md anti-pattern catalogue forbids
if/elif on ModemState.

This module ONLY computes the new (state, present, rf_blocked,
recovering_level) tuple.  The engine in `engine.py` is responsible for
streak update + decay check + counter management + the final ModemState
copy that goes into CycleResult.new_states (RECOVERY_SPEC §8).
"""

from __future__ import annotations

from typing import Final

from spark_modem.policy.context import PolicyContext
from spark_modem.wire.diag import ModemSnapshot
from spark_modem.wire.state import ModemState

# RECOVERY_SPEC §6.1 signal-quality thresholds (Phase 4 may move these
# into Settings; Phase 2 ships them as policy-package constants).
_RSRP_FLOOR_DBM: Final[int] = -110
_RSRQ_FLOOR_DB: Final[float] = -15.0
_SNR_FLOOR_DB: Final[float] = 0.0


def is_signal_below_gate(snap: ModemSnapshot) -> bool:
    """RECOVERY_SPEC §6.1: rsrp < -110 OR rsrq < -15 OR snr < 0.

    rf_blocked is True when the signal is measurably below threshold.
    Missing readings (None) -> return False (not blocked; absence of data
    is not the same as "below threshold" -- the absence-of-data case is
    handled by the observer / Zao gate upstream, not here).
    """
    sig = snap.signal
    if sig.rsrp_dbm is not None and sig.rsrp_dbm < _RSRP_FLOOR_DBM:
        return True
    if sig.rsrq_db is not None and sig.rsrq_db < _RSRQ_FLOOR_DB:
        return True
    return sig.snr_db is not None and sig.snr_db < _SNR_FLOOR_DB


def transition(  # noqa: PLR0911 -- one return per state-machine arm; intentional
    prior: ModemState,
    snap: ModemSnapshot,
    ctx: PolicyContext,
) -> ModemState:
    """RECOVERY_SPEC §3.2 transition logic with `match` on prior.state.

    Per RECOVERY_SPEC §3.2 the inputs are:
      - issues: list[Issue] from snap
      - signal_sufficient: tri-state derived from snap.signal
      - present: True (Phase 2 -- observer always sees the modem; Phase 3
        adds udev-driven false-present transitions)
      - prior_state: prior.state

    The Degraded -> Recovering transition (RECOVERY_SPEC §3.2 last
    paragraph) happens at action-selection time inside engine.run_cycle,
    not here.
    """
    del ctx  # reserved for future ladder_exhausted_for(snap) lookup

    rf_blocked = is_signal_below_gate(snap)
    present = True  # Phase 2: assume present (Phase 3: udev-driven)

    # If no issues AND signal not measurably below threshold -> healthy.
    # An RF-only condition with NO issues stays healthy (rare but possible).
    if not snap.issues and not rf_blocked:
        return _to_healthy(prior, present, rf_blocked)

    # match on the closed StateLiteral -- mypy --strict catches missing arms.
    match prior.state:
        case "unknown":
            # First observation: degrade or recover-soft based on issues
            if snap.issues:
                return _to_degraded(prior, present, rf_blocked)
            return _to_healthy(prior, present, rf_blocked)
        case "healthy":
            if snap.issues:
                return _to_degraded(prior, present, rf_blocked)
            return _to_healthy(prior, present, rf_blocked)
        case "degraded":
            # Stay degraded until an action runs (engine bumps to recovering
            # at action-selection time per RECOVERY_SPEC §3.2 last paragraph)
            return _stay_or_update(prior, "degraded", present, rf_blocked)
        case "recovering":
            # If still has issues, stay recovering (level may bump in engine).
            if snap.issues:
                level = prior.recovering_level if prior.recovering_level is not None else 1
                return prior.model_copy(
                    update={
                        "state": "recovering",
                        "recovering_level": level,
                        "present": present,
                        "rf_blocked": rf_blocked,
                    }
                )
            return _to_healthy(prior, present, rf_blocked)
        case "exhausted":
            # Exhausted -> healthy is reached via the early-return at line 70
            # ("no issues AND not rf_blocked").  When that early-return does
            # NOT trigger (issues present OR rf_blocked), the modem stays
            # exhausted; counter decay in engine.run_cycle eventually clears
            # the counters and the next cycle that observes a clean snapshot
            # falls through the early-return back to healthy.
            #
            # WR-01 (Phase 2 review): explicit no-issues + clear-signal arm
            # added defensively so the recovery path does not depend on the
            # ordering of the early-return at line 70.  Equivalent to the
            # early-return today; a future refactor that moves or removes
            # that early-return MUST NOT regress M4 (zero exhausted-stuck).
            if not snap.issues and not rf_blocked:
                return _to_healthy(prior, present, rf_blocked)
            return _stay_or_update(prior, "exhausted", present, rf_blocked)


def _to_healthy(prior: ModemState, present: bool, rf_blocked: bool) -> ModemState:
    return prior.model_copy(
        update={
            "state": "healthy",
            "recovering_level": None,
            "present": present,
            "rf_blocked": rf_blocked,
        }
    )


def _to_degraded(prior: ModemState, present: bool, rf_blocked: bool) -> ModemState:
    return prior.model_copy(
        update={
            "state": "degraded",
            "recovering_level": None,
            "present": present,
            "rf_blocked": rf_blocked,
        }
    )


def _stay_or_update(
    prior: ModemState,
    target_state: str,
    present: bool,
    rf_blocked: bool,
) -> ModemState:
    return prior.model_copy(
        update={
            "state": target_state,
            "present": present,
            "rf_blocked": rf_blocked,
        }
    )
