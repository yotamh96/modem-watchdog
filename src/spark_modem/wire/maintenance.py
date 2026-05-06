"""MaintenanceWindow — C-02 dual-clock maintenance window in globals.json.

Both monotonic and wall-clock fields are persisted; expiry check uses
``min(now_mono >= expires_monotonic, now_wall_iso >= expires_iso)`` so an
NTP step can neither prematurely expire nor extend the window.

The 8-hour cap (``max_duration_seconds = 28800``) is enforced at
construction time; CLI must reject ``--duration > 8h`` before any state
mutation, but a hand-edited globals.json with a larger value is also
caught here at load time (Pydantic raises ValidationError).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from spark_modem.wire._base import BaseWire


class MaintenanceWindow(BaseWire):
    """Dual-clock maintenance window persisted at globals.json (C-02).

    scope is hard-coded to ``"destructive"`` for v2.0 — only modem_reset /
    usb_reset / driver_reset are gated when active. Cheap actions still
    run because they are idempotent and ≤5 s outage.
    """

    active: bool
    scope: Literal["destructive"] = "destructive"
    started_iso: str
    started_monotonic: float = Field(ge=0.0)
    expires_iso: str
    expires_monotonic: float = Field(ge=0.0)
    max_duration_seconds: int = Field(default=28800, ge=1, le=28800)
