"""Hardware-free fakes for unit tests.

Single import surface for every fake the unit suite uses. Production code
under ``src/spark_modem/`` MUST NOT import from this package — boundary
discipline (Phase 2 convention).
"""

from __future__ import annotations

from tests.fakes.sleeper import FakeSleeper

__all__ = ["FakeSleeper"]
