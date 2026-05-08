"""Phase 3 event sources — supervisor + 5 producer modules.

Producers push opaque WakeSignal sentinels onto the cycle scheduler's
event_queue (E-02). Each producer task is wrapped in restart_on_crash
(E-01) so producer crashes self-heal with bounded backoff without
taking down the daemon's TaskGroup.

ADR-0002: events shorten cycle latency; the cycle is the source of truth.
State derives from re-observation, NOT from WakeSignal payloads — the
queue is a wake-up-now mechanism only.
"""

from __future__ import annotations

from spark_modem.event_sources.supervisor import (
    ClockProto,
    EventLogWriterProto,
    Sleeper,
    WakeSignal,
    restart_on_crash,
)

__all__ = [
    "ClockProto",
    "EventLogWriterProto",
    "Sleeper",
    "WakeSignal",
    "restart_on_crash",
]
