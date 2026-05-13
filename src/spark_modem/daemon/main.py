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
from datetime import UTC, datetime
from pathlib import Path

from spark_modem.cli.clients import (
    _CliClock,
    _InventoryFromFile,
    _NoZaoTailer,
    build_default_settings,
)
from spark_modem.config.settings import Settings
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
from spark_modem.daemon.preflight_triple import (
    UnknownFleetTriple,
    preflight_check_known_fleet_triple,
)
from spark_modem.event_logger.writer import EventLogWriter

# Imports kept alive for plans 05.6-02 / 03 / 04 (consumed by future task
# additions; not referenced in the 05.6-01 spine body — noqa silences
# the unused-import warning until plan 05.6-02 / 03 wires them).
from spark_modem.event_sources.supervisor import restart_on_crash  # noqa: F401
from spark_modem.inventory.udev import UdevInventory  # noqa: F401
from spark_modem.state_store.store import StateStore
from spark_modem.status_reporter.metrics_registry import MetricRegistry
from spark_modem.status_reporter.status import write_status_json
from spark_modem.subproc import runner as subproc_runner
from spark_modem.webhook.poster import WebhookPoster
from spark_modem.wire.carriers import CarrierTable
from spark_modem.wire.status import (
    StatusCycleSummary,
    StatusModemSummary,
    StatusReport,
)
from spark_modem.wire.webhook import DaemonRestart, WebhookEnvelope
from spark_modem.zao_log.inotify_tailer import ZaoLogInotifyTailer  # noqa: F401

logger = logging.getLogger(__name__)

# WR-08: anchor laptop fixture inventory path to the repo root so
# `python -m spark_modem.daemon.main` works from any CWD.
_LAPTOP_INVENTORY_PATH = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "inventory" / "four_modems.json"
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
    _ensure_dirs(state_root_path, Path(settings.run_dir), Path(settings.events_log_path).parent)

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


async def _stub_cycle_loop(
    *,
    settings: Settings,
    sd: SdNotifyLifecycle,
    state_root_path: Path,
    cycle_interval: float,
    shutdown_event: asyncio.Event,
) -> None:
    """Phase 05.6-01 stub cycle body.

    Writes a placeholder status.json each cycle, fires sd.ready() once
    after cycle 0, kicks the watchdog at cycle-end, and sleeps for
    ``cycle_interval`` seconds (or until ``shutdown_event`` is set).
    Plan 05.6-03 replaces this with the real CycleDriver invocation.
    """
    cycle_id = 0
    while not shutdown_event.is_set():
        # 1. Stub status.json so plan 05.6-05's integration test can
        #    assert the file exists with the canonical 4-modem shape.
        report = StatusReport(
            last_modified=datetime.now(UTC).isoformat(),
            cycle_index=cycle_id,
            cycle=StatusCycleSummary(n=cycle_id, duration_seconds=0.0),
            summary=StatusModemSummary(expected_modems=settings.expected_modem_count),
            modems=[],
        )
        write_status_json(state_root_path / "status.json", report)

        # 2. WATCHDOG=1 fires AFTER status.json is written
        #    (PITFALLS §4.1 / Issue #5 cycle-end placement).
        sd.watchdog_kick()

        # 3. STATUS= per cycle (C-05 terse format; plan 05.6-03 fills
        #    healthy/actions/drift after real cycle work).
        sd.status(f"cycle={cycle_id} stub healthy=?/4 actions=0 drift=0.0s")

        # 4. READY=1 only after cycle 0 completes (PITFALLS §4.1
        #    "READY = real work done"; L-01 / C-04).
        if cycle_id == 0:
            sd.ready("stub-skeleton cycle 0 ok")

        cycle_id += 1
        try:
            async with asyncio.timeout(cycle_interval):
                await shutdown_event.wait()
        except TimeoutError:
            pass  # normal: cadence elapsed, run the next cycle


async def _stub_sigterm_watcher(shutdown_event: asyncio.Event) -> None:
    """Wait for SIGTERM. Plan 05.6-04 replaces this with SigtermChoreography."""
    await shutdown_event.wait()
    # Spine: just let the TaskGroup observe shutdown_event by returning.
    # Plan 05.6-04 wires the 8-step choreography here.


async def _stub_sighup_watcher(
    shutdown_event: asyncio.Event,
    sighup_event: asyncio.Event,
) -> None:
    """Drain SIGHUP events. Plan 05.6-04 replaces this with SighupSwapper.

    Races the sighup event against the shutdown event so this watcher
    exits promptly when the daemon is shutting down (otherwise the
    inner ``await sighup_event.wait()`` would block forever if SIGHUP
    never fires before SIGTERM does).
    """
    shutdown_task = asyncio.create_task(shutdown_event.wait())
    sighup_task = asyncio.create_task(sighup_event.wait())
    try:
        while not shutdown_event.is_set():
            done, _pending = await asyncio.wait(
                {shutdown_task, sighup_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if sighup_task in done:
                sighup_event.clear()
                logger.info("sighup received (no-op in spine; wired in 05.6-04)")
                sighup_task = asyncio.create_task(sighup_event.wait())
            if shutdown_task in done:
                break
    finally:
        for t in (shutdown_task, sighup_task):
            if not t.done():
                t.cancel()


async def _production_main(args: argparse.Namespace) -> int:  # noqa: PLR0915
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
    # and exit non-zero. Use Settings() directly (production defaults from
    # config/settings.py: /var/lib/, /run/, /var/log/) overridable via env
    # vars per pydantic-settings. Do NOT use build_default_settings() — that
    # is the CLI laptop-sandbox factory which hardcodes every path under
    # /tmp/spark-modem-cli/ and explodes against the systemd unit's
    # ProtectSystem=strict + read-only /tmp namespace (EROFS at mkdir).
    # Bench Jetson deploy 2026-05-12 caught this.
    try:
        settings = Settings()
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

    # Step 3.5: X-03 known-fleet triple preflight (Phase 5 addition).
    # Runs AFTER FR-60 (binary check) and BEFORE acquire_pid_lock (so
    # failure does not leave a stale PID lock). Same exit-code-78 +
    # last-config-error marker contract as FR-60; boot classifier reads
    # the marker on next boot and emits DaemonRestart(reason=CONFIG_INVALID).
    if not args.skip_preflight:
        try:
            await preflight_check_known_fleet_triple()
        except UnknownFleetTriple as exc:
            try:
                write_last_config_error(run_dir=run_dir, message=str(exc))
            except Exception:
                logger.exception("failed to write last-config-error marker")
            logger.error("unknown fleet triple: %s", exc)
            return 78

    # Step 4: read clean-shutdown marker; classify prior run.
    prior_reason, prior_uptime = classify_prior_run(run_dir=run_dir)
    logger.info("prior run classified reason=%s uptime=%.1fs", prior_reason.value, prior_uptime)

    # Step 5: acquire PID lock at /run/.../lock (FR-61, ADR-0012).
    try:
        with acquire_pid_lock(run_dir=run_dir):
            # Step 6: wire the production sd_notify lifecycle + clock + shutdown events.
            #
            # The clock is _CliClock (production: real wall-clock + monotonic + unix_seconds);
            # plans 05.6-02 / 03 / 04 add producers, the real cycle body, and choreography
            # on top of this spine. This plan ships a STUB cycle loop only — proves the
            # TaskGroup wiring is sound before the heavier subsystems land.
            clock = _CliClock()
            del clock  # plan 05.6-03 wires this into CycleDriver + SigtermChoreography
            del prior_reason, prior_uptime  # consumed by plan 05.6-03's webhook boot envelope

            sd = SdNotifyLifecycle()

            # Signal handler installation BEFORE the TaskGroup is entered (Pattern 7).
            # CLAUDE.md anti-pattern: NEVER use the stdlib signal handler-installer
            # from asyncio — call loop.add_signal_handler so the event-set fires on
            # the running loop.
            shutdown_event = asyncio.Event()
            sighup_event = asyncio.Event()
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGTERM, shutdown_event.set)
            loop.add_signal_handler(signal.SIGHUP, sighup_event.set)

            # Spine: 1 cycle task + 2 signal watchers. Plans 05.6-02 / 04 add
            # producers + choreography on top. The TaskGroup exits when
            # shutdown_event is set: ``_stub_cycle_loop`` notices,
            # ``_stub_sigterm_watcher`` returns, ``_stub_sighup_watcher``'s outer
            # while-condition flips false at the next iteration (or the inner
            # wait gets cancelled).
            cycle_interval = settings.cycle_interval_seconds
            async with asyncio.TaskGroup() as tg:
                tg.create_task(
                    _stub_cycle_loop(
                        settings=settings,
                        sd=sd,
                        state_root_path=state_root_path,
                        cycle_interval=cycle_interval,
                        shutdown_event=shutdown_event,
                    )
                )
                tg.create_task(_stub_sigterm_watcher(shutdown_event))
                tg.create_task(_stub_sighup_watcher(shutdown_event, sighup_event))

            # Phase 05.6 SC #3 budget for graceful shutdown (≤5 s) is honored
            # by plan 05.6-04's SigtermChoreography.execute(deadline_seconds=5.0).
            # In the spine we just exit cleanly when the TaskGroup unwinds.
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


def _sync_main(argv: list[str] | None = None) -> int:
    """Sync wrapper for [project.scripts] console-script entry point (I-04).

    systemd Type=notify spawns this via the spark-modem-watchdog console
    script materialized by `uv pip install .` (Phase 05.1 I-01 + I-02).
    """
    return asyncio.run(main(argv))


if __name__ == "__main__":
    sys.exit(_sync_main())
