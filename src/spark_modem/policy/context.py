"""PolicyContext -- pure-data context object for the engine.

NO IMPORTS of subprocess / asyncio / os / httpx -- CLAUDE.md §1 purity.

The cycle driver constructs a PolicyContext per cycle and passes it by
value to engine.run_cycle. The ClockProto is satisfied by both
spark_modem.clock.clock module-functions wrapped in an instance and by
tests.fakes.clock.FakeClock.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from spark_modem.config.settings import Settings


class ClockProto(Protocol):
    """Subset of clock surface the policy engine needs.

    Both `tests.fakes.clock.FakeClock` and a thin instance wrapper around
    `spark_modem.clock.clock` module functions satisfy this surface. The
    engine does NOT import the production clock module directly -- doing
    so would couple `policy/` to a non-pure import surface.
    """

    def monotonic(self) -> float: ...
    def wall_clock_iso(self) -> str: ...


@dataclass(frozen=True, slots=True)
class PolicyContext:
    """Pure context: clock, config, derived counts.

    Constructed by the cycle driver and passed by value to engine.run_cycle.
    `maintenance_active` is computed by the cycle driver from
    GlobalsState.maintenance (added in C-02); the engine only reads the
    boolean.
    """

    clock: ClockProto
    config: Settings
    maintenance_active: bool = False
    expected_modem_count: int = 4
