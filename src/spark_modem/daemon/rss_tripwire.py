"""psutil RSS tripwire — events at 200 MiB; no graceful-exit in Phase 2.

Phase 3's ``sd_notify`` watchdog owns the restart decision based on the
``daemon_self_health{kind="rss"}`` counter; Phase 2 owns ONLY the
detection + metric.

Per NFR-3: target steady-state RSS ≤ 80 MiB; the 200 MiB tripwire is the
"something is leaking" alarm threshold (2.5x headroom over normal).
"""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)

# NFR-3 alarm threshold; PRD § Performance.
_TRIPWIRE_BYTES: int = 200 * 1024 * 1024


class MetricRecorderProto(Protocol):
    """The ``record_rss_tripwire`` accessor on ``MetricRegistry``."""

    def record_rss_tripwire(self) -> None: ...


def check_rss_tripwire(metrics: MetricRecorderProto, *, rss_bytes: int) -> bool:
    """Increment ``daemon_self_health{kind="rss"}`` if ``rss_bytes`` > tripwire.

    Phase 2: event-only.  Returns True iff the tripwire fired this cycle
    (so the cycle driver can emit a paired ``rss_tripwire_breached`` log
    line for human-readable journaling).  Never raises, never exits, never
    re-raises.
    """
    if rss_bytes > _TRIPWIRE_BYTES:
        metrics.record_rss_tripwire()
        logger.warning(
            "rss_tripwire_breached rss_bytes=%d threshold=%d",
            rss_bytes,
            _TRIPWIRE_BYTES,
        )
        return True
    return False


def get_self_rss_bytes() -> int:
    """Best-effort RSS read — returns 0 if ``psutil`` is unavailable.

    On developer hosts without ``psutil`` (Windows CI / minimal venvs)
    the tripwire silently does nothing.  Production ``.deb`` ships
    ``psutil`` in the bundled venv (Plan 01) so the tripwire is always
    armed on the Jetson.
    """
    try:
        import psutil  # type: ignore[import-untyped]  # noqa: PLC0415
    except ImportError:
        return 0
    return int(psutil.Process().memory_info().rss)
