"""Diag builder - combines per-modem snapshots + ZaoSnapshot into a Diag."""

from __future__ import annotations

from typing import Protocol

from spark_modem.wire.diag import Diag, ModemSnapshot
from spark_modem.zao_log.snapshot import ZaoSnapshot


class ClockProto(Protocol):
    """Subset of the Clock surface used by build_diag (test-shimmable)."""

    def wall_clock_iso(self) -> str: ...


def build_diag(
    snapshots: list[ModemSnapshot],
    zao_snapshot: ZaoSnapshot,
    cycle_id: int,
    clock: ClockProto,
) -> Diag:
    """FR-13: produce one typed Diag per cycle.

    Phase 2 packs only per-modem and the cycle metadata. The ZaoSnapshot
    is currently consumed inside the observer (via the FR-10 gate) and
    not re-encoded into Diag - the policy engine accepts ZaoSnapshot
    separately so the Diag wire stays small.
    """
    del zao_snapshot  # carried separately into policy.engine.run_cycle
    per_modem = {snap.usb_path: snap for snap in snapshots}
    return Diag(
        ts_iso=clock.wall_clock_iso(),
        cycle_id=cycle_id,
        per_modem=per_modem,
        host_issues=[],  # Phase 3 surfaces dmesg-driven host issues
    )
