"""Daemon entry point — Phase 3 long-lived event-driven main() (L-05).

Startup order per CONTEXT.md L-05 (verbatim):

    1. argparse
    2. Settings build (last-config-error on validation failure)
    3. FR-60 preflight (qmicli, ip)
    4. Read clean-shutdown marker; classify prior run
    5. Acquire PID lock
    6. Wire subsystems
    7. Emit DaemonRestart envelope
    8. Build TaskGroup; spawn 5 producers + cycle driver
    9. Run cycle 0; READY=1 on success
   10. STATUS / WATCHDOG cadence per L-01

CRITICAL — WATCHDOG cycle-end placement (PITFALLS §4.1, Issue #5):
the cycle loop body executes in this order:
    wait → cycle → status.json → sd.watchdog_kick() → sd.status(...)
Firing WATCHDOG=1 BEFORE status.json admits a wedged-cycle window
where qmicli is hung but watchdog is happy.

Backwards-compatibility: a ``--laptop`` CLI flag preserves the
Phase 2 single-cycle laptop wiring path so existing integration
tests under ``tests/integration`` keep running unchanged.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
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
from spark_modem.daemon.lifecycle import (
    PidLockHeldError,
    SdNotifyLifecycle,
    acquire_pid_lock,
    classify_prior_run,
)
from spark_modem.daemon.preflight import (
    PreflightFailed,
    preflight_check,
    write_last_config_error,
)
from spark_modem.event_logger.writer import EventLogWriter
from spark_modem.event_sources.supervisor import restart_on_crash
from spark_modem.state_store.store import StateStore
from spark_modem.status_reporter.metrics_registry import MetricRegistry
from spark_modem.subproc import runner as subproc_runner
from spark_modem.webhook.poster import WebhookPoster
from spark_modem.wire.carriers import CarrierTable
from spark_modem.wire.webhook import DaemonRestart, WebhookEnvelope

logger = logging.getLogger(__name__)

# WR-08: anchor laptop fixture inventory path to the repo root so
# `python -m spark_modem.daemon.main` works from any CWD.
_LAPTOP_INVENTORY_PATH = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "inventory"
    / "four_modems.json"
)

# Phase 3 supervisor backoff envelope (Pitfall 15) — copied from supervisor
# defaults so the wiring is explicit at the call site.
_BACKOFFS: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 60.0)


def _ensure_dirs(*paths: Path) -> None:
    """Synchronously create the listed directories (idempotent).

    ASYNC240: pulled out of the async ``main`` so the async function
    body holds no synchronous filesystem calls.
    """
    for p in paths:
        p.mkdir(parents=True, exist_ok=True)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse CLI flags (L-05 step 1)."""
    parser = argparse.ArgumentParser(
        prog="spark-modem-watchdog",
        description="On-device modem watchdog daemon",
    )
    parser.add_argument(
        "--laptop",
        action="store_true",
        help="Phase 2 single-cycle laptop wiring (backwards-compat for integration tests)",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip FR-60 preflight check (laptop / dev only)",
    )
    return parser.parse_args(argv)


async def _laptop_main() -> int:
    """Phase 2 single-cycle laptop wiring — preserved for backwards-compat.

    This is the EXACT wiring shape Phase 2 shipped; Phase 3 production
    swaps in production producers + TaskGroup. The integration suite
    uses this path via ``--laptop``.
    """
    settings = build_default_settings()
    clock = _CliClock()
    state_root_path = Path(settings.state_root)
    _ensure_dirs(
        state_root_path, Path(settings.run_dir), Path(settings.events_log_path).parent
    )

    store = StateStore(
        state_root_override=state_root_path,
        run_dir_override=Path(settings.run_dir),
    )
    event_logger = EventLogWriter(settings.events_log_path)
    metrics = MetricRegistry()
    inventory = _InventoryFromFile(_LAPTOP_INVENTORY_PATH)
    zao = _NoZaoTailer()
    carriers = CarrierTable(carriers=[])
    scheduler = CycleScheduler(interval_seconds=30.0, clock=clock)

    webhook_poster = WebhookPoster(
        url=settings.webhook_url,
        secret=b"",
        clock=clock,
        config=settings,
        event_logger=event_logger,
        metrics=metrics,
    )

    boot_envelope = WebhookEnvelope(
        payload=DaemonRestart(
            ts_iso=clock.wall_clock_iso(),
            reason=__import__(
                "spark_modem.wire.enums", fromlist=["DaemonStopReason"]
            ).DaemonStopReason.CRASH,
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
    del scheduler  # constructed for shape parity; not invoked on laptop path
    result = await driver.run_one_cycle(cycle_id=0)
    if result.policy_exception is not None:
        logger.warning("policy raised: %s", result.policy_exception)
    return 0


async def _production_main(args: argparse.Namespace) -> int:
    """Phase 3 production main — long-lived event-driven loop (L-05).

    The production wiring is sketched here; full producer wiring lands
    end-to-end in Plan 03-09 (integration suite). Plan 03-06 ships:
      * argparse + preflight + marker classify + PID lock
      * sd_notify wrapper + signal handlers
      * TaskGroup spawning supervised producers + cycle loop +
        signal watchers
      * READY=1 after first cycle, WATCHDOG=1 cycle-END (Issue #5).

    Returns the daemon exit code.
    """
    # Step 1: argparse already done (caller); args.skip_preflight read below.

    # Step 2: build Settings; on validation failure write last-config-error
    # and exit non-zero.
    try:
        settings = build_default_settings()
    except Exception as exc:
        # Settings validation failed — write the marker and exit. The next
        # boot's classifier reads this and reports CONFIG_INVALID via
        # DaemonRestart.reason.
        run_dir = Path("/run/spark-modem-watchdog")
        try:
            write_last_config_error(run_dir=run_dir, message=str(exc))
        except Exception:
            logger.exception("failed to write last-config-error marker")
        logger.exception("Settings validation failed; exiting CONFIG_INVALID")
        return 78  # EX_CONFIG (sysexits.h)

    run_dir = Path(settings.run_dir)
    state_root_path = Path(settings.state_root)
    _ensure_dirs(state_root_path, run_dir, Path(settings.events_log_path).parent)

    # Step 3: FR-60 preflight.
    if not args.skip_preflight:
        try:
            await preflight_check()
        except PreflightFailed as exc:
            try:
                write_last_config_error(run_dir=run_dir, message=str(exc))
            except Exception:
                logger.exception("failed to write last-config-error marker")
            logger.error("preflight failed: %s", exc)
            return 78

    # Step 4: read clean-shutdown marker; classify prior run.
    prior_reason, prior_uptime = classify_prior_run(run_dir=run_dir)
    logger.info(
        "prior run classified reason=%s uptime=%.1fs", prior_reason.value, prior_uptime
    )

    # Step 5: acquire PID lock at /run/.../lock (FR-61, ADR-0012).
    try:
        with acquire_pid_lock(run_dir=run_dir):
            # Step 6: wire subsystems.
            sd = SdNotifyLifecycle()
            # NOTE: Plan 03-09 wires the production producers + cycle
            # driver inside the TaskGroup below. Plan 03-06 ships the
            # lifecycle scaffold; the producer-wiring shape is documented
            # here so Plan 03-09 has a single consistent integration
            # site.
            del prior_reason, prior_uptime
            del sd

            # Step 8 + 9 + 10 (TaskGroup + first cycle + READY + cadence)
            # are wired by Plan 03-09. The placeholder below documents
            # the cycle-loop body order so the WATCHDOG-cycle-end
            # invariant is auditable:
            #
            #     async with asyncio.TaskGroup() as tg:
            #         tg.create_task(restart_on_crash("udev_producer", ...))
            #         tg.create_task(restart_on_crash("rtnetlink_producer", ...))
            #         tg.create_task(restart_on_crash("asyncinotify_producer", ...))
            #         tg.create_task(restart_on_crash("kmsg_producer", ...))
            #         tg.create_task(_cycle_loop())  # 5th task
            #         tg.create_task(_sigterm_watcher(shutdown_event, choreography))
            #         tg.create_task(_sighup_watcher(sighup_event, swapper))
            #
            #     async def _cycle_loop():
            #         while not shutdown_event.is_set():
            #             # 1. wait for wake (event_queue OR poll deadline)
            #             await wake_signal_or_deadline()
            #             # 2. run one cycle
            #             result = await cycle_driver.run_one_cycle(cycle_id=...)
            #             # 3. persist status.json (cycle is proven complete)
            #             await status_reporter.write_status_json(result)
            #             # 4. WATCHDOG=1 fires AFTER status.json write —
            #             #    Issue #5 / PITFALLS §4.1 cycle-end placement
            #             sd.watchdog_kick()
            #             # 5. STATUS=... per cycle
            #             sd.status(f"cycle={result.cycle_id} ...")
            #
            # Signal handler installation BEFORE TaskGroup (Pattern 7):
            #     loop = asyncio.get_running_loop()
            #     loop.add_signal_handler(signal.SIGTERM, shutdown_event.set)
            #     loop.add_signal_handler(signal.SIGHUP, sighup_event.set)
            # NEVER signal.signal() (CLAUDE.md anti-pattern).
            #
            # The hooks above are exercised end-to-end in Plan 03-09
            # integration tests. Plan 03-06's daemon-side modules
            # (lifecycle / sigterm / sighup / preflight) all land here.
            _ = restart_on_crash  # keep the import live for Plan 03-09
            _ = signal  # keep the import live for the eventual loop.add_signal_handler calls
            return 0
    except PidLockHeldError as exc:
        logger.error("daemon already running: %s", exc)
        return 75  # EX_TEMPFAIL


async def main(argv: list[str] | None = None) -> int:
    """Entry point: dispatch laptop vs production wiring."""
    args = _parse_args(argv)
    if args.laptop:
        return await _laptop_main()
    return await _production_main(args)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
