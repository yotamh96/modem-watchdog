"""status.json writer — atomic, every cycle (FR-41, O-01).

Wraps :func:`spark_modem.state_store.atomic.atomic_write_bytes` — the
canonical Phase 1 atomic helper. Never re-implements temp + rename +
directory fsync. Caller invokes once per cycle, after policy + actions,
before sleep.

Per O-01 the marginal fsync cost is dominated by the per-modem state
writes that already happen every cycle, so this stays inside the M5
≤10 s P99 budget.
"""

from __future__ import annotations

from pathlib import Path

from spark_modem.state_store.atomic import atomic_write_bytes
from spark_modem.wire.status import StatusReport


def write_status_json(path: Path | str, report: StatusReport) -> None:
    """Atomically serialise ``report`` to ``path`` as JSON bytes.

    Uses the by-alias serialisation form so ``StatusReport`` and any
    future aliased fields round-trip cleanly through ``model_validate_json``.
    """
    target = Path(path)
    payload = report.model_dump_json(by_alias=True).encode("utf-8")
    atomic_write_bytes(target, payload)
