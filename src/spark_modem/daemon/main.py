"""Daemon entry point — wires every Phase 2 subsystem and runs ONE cycle.

Phase 2 production: not the actual deployed daemon yet — Phase 3 wires
``sd_notify``, signal handlers, PID lock, and event-driven sources via
the no-op event_queue arm in ``CycleScheduler``.  This ``main()`` is
callable from the test suite for end-to-end integration tests AND
serves as the canonical example wiring of every Phase 2 subsystem
(observer + policy + actions + state-store + status_reporter +
metrics + webhook + carrier_table) into a single ``CycleDriver``.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from spark_modem.cli.clients import (
    _CliClock,
    _InventoryFromFile,
    _NoZaoTailer,
    build_default_settings,
)
from spark_modem.daemon.cycle_driver import CycleDriver
from spark_modem.daemon.cycle_scheduler import CycleScheduler
from spark_modem.event_logger.writer import EventLogWriter
from spark_modem.state_store.store import StateStore
from spark_modem.status_reporter.metrics_registry import MetricRegistry
from spark_modem.subproc import runner as subproc_runner
from spark_modem.webhook.poster import WebhookPoster
from spark_modem.wire.carriers import CarrierTable
from spark_modem.wire.enums import DaemonStopReason
from spark_modem.wire.webhook import DaemonRestart, WebhookEnvelope

logger = logging.getLogger(__name__)


def _ensure_dirs(*paths: Path) -> None:
    """Synchronously create the listed directories (idempotent).

    Pulled out of ``main`` so the async function does not call ``Path.mkdir``
    in its own body (ASYNC240).  These are one-shot startup operations; no
    benefit from running them through a thread executor.
    """
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


async def main(argv: list[str] | None = None) -> int:
    """Entry point: wire subsystems + run a single cycle.

    Phase 3 will replace the single-cycle invocation with a long-lived
    loop driven by ``CycleScheduler``; the wiring above the loop is
    Phase 2's deliverable and matches what Phase 3 will use unchanged.
    """
    del argv  # Phase 3 will parse argparse here.

    settings = build_default_settings()
    clock = _CliClock()
    state_root_path = Path(settings.state_root)
    # Synchronous filesystem prep before entering the cycle loop -- pulled
    # into a helper so the async top-level only contains await-able work
    # (ASYNC240: pathlib in async context).
    _ensure_dirs(state_root_path, Path(settings.run_dir), Path(settings.events_log_path).parent)

    store = StateStore(
        state_root_override=state_root_path,
        run_dir_override=Path(settings.run_dir),
    )
    event_logger = EventLogWriter(settings.events_log_path)
    metrics = MetricRegistry()
    inventory = _InventoryFromFile(
        Path("tests/fixtures/inventory/four_modems.json"),
    )
    zao = _NoZaoTailer()
    # Empty carrier table is acceptable for the laptop integration path
    # (Phase 2 production loads YAML; the daemon tolerates an empty table
    # because actions/set_apn surfaces ``no_carrier:<mcc>/<mnc>`` rather
    # than failing the cycle).
    carriers = CarrierTable(carriers=[])
    scheduler = CycleScheduler(interval_seconds=30.0, clock=clock)

    # WebhookPoster wiring (SC #5).  For Phase 2 laptop integration the
    # poster is constructed but the network leg is disabled (no
    # webhook_url configured); enqueue() short-circuits to
    # ``skipped_no_url`` and the cycle never blocks on network I/O.
    # Phase 3 wires the production webhook URL + HMAC secret via
    # systemd ``LoadCredential=`` (ADR-0011).
    webhook_poster = WebhookPoster(
        url=settings.webhook_url,
        secret=b"",
        clock=clock,
        config=settings,
        event_logger=event_logger,
        metrics=metrics,
    )

    # M-6 / SC #5c — DaemonRestart envelope emitted ONCE at boot, BEFORE
    # the first cycle.  The reason is ``CRASH`` for laptop integration
    # (the previous run was never confirmed clean); Phase 3 swaps in the
    # ``SIGTERM`` reason via a clean-shutdown marker file.
    boot_envelope = WebhookEnvelope(
        payload=DaemonRestart(
            ts_iso=clock.wall_clock_iso(),
            reason=DaemonStopReason.CRASH,
            prior_run_uptime_seconds=0.0,
        ),
    )
    await webhook_poster.enqueue(boot_envelope)

    driver = CycleDriver(
        store=store,
        settings=settings,
        clock=clock,
        runner=subproc_runner,
        inventory=inventory,
        zao=zao,
        carrier_table=carriers,
        event_logger=event_logger,
        metrics=metrics,
        webhook_poster=webhook_poster,
    )

    # Run a single cycle for laptop integration; production loop is Phase 3.
    # ``scheduler`` is constructed so the wiring shape mirrors the Phase 3
    # cycle loop, but it is not yet invoked here.
    del scheduler

    result = await driver.run_one_cycle(cycle_id=0)
    if result.policy_exception is not None:
        logger.warning("policy raised: %s", result.policy_exception)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
