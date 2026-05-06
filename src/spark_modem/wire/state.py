"""ModemState (per-modem state file).

ADR-0008 5+2 shape: 5 top-level states + 2 orthogonal flags.
ADR-0009 keying: this model is persisted at state/by-usb/<usb_path>.json.
ADR-0006 amendment: _healthy_streak persisted every cycle, reloaded on start.
ADR-0007: last_action_monotonic uses time.monotonic(); ISO timestamps wall-clock.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from spark_modem.wire._base import BaseWire
from spark_modem.wire.enums import ActionKind
from spark_modem.wire.versioning import CURRENT_SCHEMA_VERSION

StateLiteral = Literal["unknown", "healthy", "degraded", "recovering", "exhausted"]


# Canonical integer encoding for the modem_state_value{modem} Prom metric (ADR-0013).
# NO ONE-HOT LABEL — see CLAUDE.md anti-pattern catalogue and PITFALLS §13.1.
_STATE_TO_INT: dict[str, int] = {
    "unknown": 0,
    "healthy": 1,
    "degraded": 2,
    "recovering": 3,
    "exhausted": 4,
}


class ModemState(BaseWire):
    """Per-modem state. Persisted at state/by-usb/<usb_path>.json (ADR-0009)."""

    schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, ge=1)

    # 5 top-level states (ADR-0008).
    state: StateLiteral

    # Orthogonal flag #1 (ADR-0008): is the modem currently visible on USB?
    present: bool

    # Orthogonal flag #2 (ADR-0008): is RF below the signal-quality gate?
    rf_blocked: bool

    # Recovering depth (only meaningful when state == "recovering").
    recovering_level: int | None = Field(default=None, ge=1)

    # FR-26.1: persisted every cycle, reloaded on daemon start.
    healthy_streak: int = Field(default=0, ge=0, alias="_healthy_streak")

    # Per-action escalation counters (ADR-0006). Decay to zero after K consecutive
    # Healthy cycles; persisted every cycle.
    counters: dict[ActionKind, int] = Field(default_factory=dict)

    # Monotonic timestamp of the last action attempted on this modem (ADR-0007).
    # None on first observation.
    last_action_monotonic: float | None = None

    # Wall-clock ISO-8601 stamp of the last state transition (ADR-0007 — wall
    # clock is fine for ISO timestamps; only durations / backoffs use monotonic).
    last_state_transition_iso: str | None = None

    @model_validator(mode="after")
    def _check_recovering_level(self) -> ModemState:
        """recovering_level must be set iff state == 'recovering'."""
        if self.state == "recovering":
            if self.recovering_level is None:
                raise ValueError("recovering_level is required when state == 'recovering'")
        elif self.recovering_level is not None:
            raise ValueError(
                f"recovering_level must be None when state == {self.state!r} "
                f"(only used for state == 'recovering')"
            )
        return self

    @model_validator(mode="after")
    def _check_counters_nonneg(self) -> ModemState:
        """All counter values must be non-negative."""
        for k, v in self.counters.items():
            if v < 0:
                raise ValueError(f"counters[{k!s}] must be >= 0; got {v}")
        return self


def state_to_int(s: ModemState) -> int:
    """Canonical encoding for the modem_state_value{modem} metric (ADR-0013).

    The integer mapping is *stable* across releases: never reuse a number for
    a different state. Add new states by extending the table at the end.
    """
    return _STATE_TO_INT[s.state]
