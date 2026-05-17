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
    wait -> cycle -> status.json -> watchdog kick -> STATUS line
Firing WATCHDOG=1 BEFORE status.json admits a wedged-cycle window
where qmicli is hung but watchdog is happy.

Backwards-compatibility: a ``--laptop`` CLI flag preserves the
Phase 2 single-cycle laptop wiring path so existing integration
tests under ``tests/integration`` keep running unchanged.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import signal
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol, cast

import yaml
from pydantic import ValidationError

from spark_modem.cli.clients import (
    _CliClock,
    _InventoryFromFile,
    _NoZaoTailer,
    build_default_settings,
)
from spark_modem.config.settings import Settings
from spark_modem.daemon.cycle_driver import (
    CycleDriver,
    InventorySourceProto,
)
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
from spark_modem.daemon.sighup import SighupSwapper
from spark_modem.daemon.sigterm import SigtermChoreography
from spark_modem.event_logger.inotify_reopener import EventLogReopener
from spark_modem.event_logger.writer import EventLogWriter
from spark_modem.event_sources.asyncinotify_producer import (
    run_asyncinotify_producer,
)
from spark_modem.event_sources.kmsg_producer import run_kmsg_producer
from spark_modem.event_sources.rtnetlink_producer import (
    run_rtnetlink_producer,
)
from spark_modem.event_sources.supervisor import (
    WakeSignal,
    restart_on_crash,
)
from spark_modem.event_sources.udev_producer import run_udev_producer
from spark_modem.inventory.udev import UdevInventory
from spark_modem.kmsg.dedup import KmsgDedup
from spark_modem.state_store.store import StateStore
from spark_modem.status_reporter.metrics_registry import MetricRegistry
from spark_modem.status_reporter.prom import start_metrics_server
from spark_modem.subproc import runner as subproc_runner
from spark_modem.webhook.poster import WebhookPoster
from spark_modem.wire.carriers import CarrierTable
from spark_modem.wire.enums import IssueDetail
from spark_modem.wire.webhook import DaemonRestart, WebhookEnvelope
from spark_modem.zao_log.inotify_tailer import ZaoLogInotifyTailer
from spark_modem.zao_log.protocol import ZaoLogTailer as ZaoLogTailerProto


class _MainIssueEmitterProto(Protocol):
    """Local re-derivation of kmsg_producer's module-private ``_IssueEmitterProto``.

    Plan 05.6-02 wires a ``_LoggingHostIssueEmitter`` placeholder; plan 05.6-03
    replaces it with a CycleDriver-fed accumulator. We re-derive here to avoid
    importing an underscore-prefixed Protocol from another module.
    """

    def emit_host_issue(self, *, detail: IssueDetail, raw_line: str) -> None: ...


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


def _load_carrier_table_yaml(yaml_path: Path) -> CarrierTable:
    """Synchronously load + validate the carrier-table YAML (idempotent).

    ASYNC240 helper: pulled out of ``_production_main`` so the async body
    holds no synchronous filesystem reads (mirrors ``_ensure_dirs``).

    FR-63: malformed input is a logged error + empty-table degradation,
    not a daemon-blocking crash (T-05.6-03-03). Plan 05.6-04 may decide
    to refuse to start; for plan 05.6-03 we degrade.
    """
    try:
        carrier_data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        return CarrierTable.model_validate(carrier_data or {"carriers": []})
    except FileNotFoundError:
        logger.warning(
            "carriers_yaml_path=%s missing; using empty CarrierTable",
            yaml_path,
        )
        return CarrierTable(carriers=[])
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        logger.error(
            "carrier table parse failed: %s; using empty table",
            exc,
        )
        return CarrierTable(carriers=[])


def _read_hmac_secret(secret_path: Path) -> bytes:
    """Synchronously read the HMAC secret bytes (idempotent).

    ASYNC240 helper. T-05.6-03-01: secret_bytes never reaches a log line;
    only the path is logged on missing-file fallback. If the file is
    missing the webhook poster runs with empty secret — signing still
    works but receivers will reject the X-Spark-Signature header. That's
    the correct degradation: webhook delivery is observability, not a
    daemon-blocking concern.
    """
    try:
        return secret_path.read_bytes().strip()
    except FileNotFoundError:
        logger.warning(
            "HMAC secret %s missing; webhook delivery will be skipped"
            " by NFR-33-conformant receivers",
            secret_path,
        )
        return b""


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


async def _production_main(  # noqa: PLR0915
    args: argparse.Namespace,
    *,
    inventory_factory: Callable[[], InventorySourceProto] | None = None,
    zao_factory: Callable[[Path], ZaoLogTailerProto] | None = None,
    udev_factory: Callable[[asyncio.Queue[WakeSignal]], Awaitable[None]] | None = None,
    rtnetlink_factory: Callable[[asyncio.Queue[WakeSignal]], Awaitable[None]] | None = None,
    asyncinotify_factory: Callable[[asyncio.Queue[WakeSignal]], Awaitable[None]] | None = None,
    kmsg_factory: Callable[[asyncio.Queue[WakeSignal]], Awaitable[None]] | None = None,
) -> int:
    """Phase 3 production main — long-lived event-driven loop (L-05).

    The production wiring is sketched here; full producer wiring lands
    end-to-end in Plan 03-09 (integration suite). Plan 03-06 ships:
      * argparse + preflight + marker classify + PID lock
      * sd_notify wrapper + signal handlers
      * TaskGroup spawning supervised producers + cycle loop +
        signal watchers
      * READY=1 after first cycle, WATCHDOG=1 cycle-END (Issue #5).

    Plan 05.6-02 adds 6 keyword-only factory parameters (all default
    None → real producers / inventory / zao tailer). Plan 05.6-05's
    integration test passes Fake* factories so the wiring is exercised
    without monkey-patching pyudev / pyroute2 / asyncinotify / kmsg
    modules. Production callers (the ``_sync_main`` / ``main`` chain
    via ``main(argv)``) never set these — defaults stay None.

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
    # Names carry through to step 7's boot-envelope construction (renamed
    # from prior_reason / prior_uptime in plan 05.6-03; the boot envelope
    # consumes them so we can no longer ``del`` them after acquire_pid_lock).
    prior_reason_for_boot, prior_uptime_for_boot = classify_prior_run(run_dir=run_dir)
    logger.info(
        "prior run classified reason=%s uptime=%.1fs",
        prior_reason_for_boot.value,
        prior_uptime_for_boot,
    )

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
            # boot_mono: captured BEFORE the TaskGroup. The SigtermChoreography
            # uses this as the reference for uptime computation in step 5
            # (DaemonStopped.uptime_seconds) and step 8 (clean-shutdown marker
            # uptime_s). ADR-0007: monotonic only — never wall-clock arithmetic.
            boot_mono = clock.monotonic()

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

            # ---- 05.6-02: producer wiring scaffolding ---------------------
            # The producers push opaque WakeSignal enums onto event_queue;
            # plan 05.6-03's real _cycle_loop drains it via asyncio.wait
            # between cycle iterations. The maxsize=1024 cap bounds memory
            # under a producer-side storm (a USB hub PSU droop emits 16+
            # rtnetlink + udev events; the cycle waking absorbs them all
            # via re-observation, so the queue rarely backs up).
            event_queue: asyncio.Queue[WakeSignal] = asyncio.Queue(maxsize=1024)

            # EventLogWriter wire path: production = settings.events_log_path
            # (RELOAD_RESTART; default /var/log/spark-modem-watchdog/events.jsonl).
            # The writer itself is opened as a context manager INSIDE the
            # TaskGroup block (plan 05.6-02 task 2 wraps it) so the fd is
            # released cleanly on TaskGroup unwind. We resolve + parent-mkdir
            # the path here so the writer's __init__ finds the directory.
            event_log_path = Path(settings.events_log_path)
            event_log_path.parent.mkdir(parents=True, exist_ok=True)

            # Asyncio adapter for the Sleeper Protocol (supervisor.py:62-75).
            # Production Sleeper wraps asyncio.sleep for restart_on_crash
            # backoff; tests inject FakeSleeper via Sleeper Protocol.
            class _AsyncioSleeper:
                """Production Sleeper — wraps asyncio.sleep for restart_on_crash backoff."""

                async def sleep(self, delay: float) -> None:
                    await asyncio.sleep(delay)

            sleeper = _AsyncioSleeper()

            # ---- subsystem construction for producers ----
            # InventorySource: production = UdevInventory (sysfs walk);
            # plan 05.6-05's integration test passes a FixtureInventory
            # via inventory_factory.
            inventory: InventorySourceProto = (
                inventory_factory() if inventory_factory is not None else UdevInventory()
            )
            # ZaoLogTailer: production = ZaoLogInotifyTailer(log_path=...);
            # canonical zao log path matches preflight_triple._DEFAULT_ZAO_LOG_PATH
            # and capture_fleet_fixture.py:55.
            zao_log_path = Path("/var/log/zao-remote-endpoint.log")
            zao_tailer: ZaoLogTailerProto = (
                zao_factory(zao_log_path)
                if zao_factory is not None
                else ZaoLogInotifyTailer(log_path=zao_log_path)
            )
            # Spine: 4 producers + cycle + webhook + prom + 2 signal watchers
            # (9 tasks). Plan 05.6-04 wires the SigtermChoreography +
            # SighupSwapper into the two signal watchers (replacing the
            # plan-05.6-01 stubs). The ``producer_tasks`` list is declared
            # OUTSIDE the TaskGroup body so the choreography can read the
            # 4 task handles at SIGTERM (sigterm.py:94-117 takes
            # ``producer_tasks: list[Task]``).
            #
            # ``cycle_count_ref`` is a 1-element list (read-write cell) that
            # the cycle loop bumps after every cycle. Plan 05.6-04's
            # SigtermChoreography reads cycle_count_ref[0] to report the
            # final cycle count in the DaemonStopped event (sigterm.py:105).
            cycle_count_ref: list[int] = [0]
            producer_tasks: list[asyncio.Task[object]] = []
            # ---- 05.6-04: SIGTERM choreography wiring ----
            # cycle_task_ref holds the cycle task handle; populated inside
            # the TaskGroup block after tg.create_task(_cycle_loop()). The
            # _sigterm_watcher coroutine reads cycle_task_ref[0] when
            # shutdown_event fires; by then the cycle task is fully
            # created (asyncio guarantees tg.create_task is synchronous).
            cycle_task_ref: list[asyncio.Task[object] | None] = [None]

            # ---- 05.6-04: SIGHUP transactional swap wiring ----
            # _SettingsRef is a single-cell mutable container. The cycle
            # driver reads its Settings ONCE per cycle via self._settings
            # (the swap is naturally atomic at cycle boundary; sighup.py
            # module docstring). For Phase 05.6, the cycle driver was
            # constructed with `settings=settings` at the start of
            # _production_main, so it holds a reference to the INITIAL
            # Settings. The SighupSwapper updates settings_ref's cell;
            # since the cycle driver doesn't read settings_ref directly,
            # it keeps using the initial Settings. THAT IS EXPECTED for
            # plan 05.6-04 — the swap is observable for fields that
            # OTHER subsystems read live (e.g. webhook_poster's
            # webhook_url which it pulls per request). Fields that
            # the cycle driver caches at construction (e.g.
            # cycle_interval_seconds in the scheduler) will not retune
            # without a restart for THIS phase. A future phase can wire
            # the cycle driver to read settings_ref.get() per cycle.
            # SPEC out-of-scope "Refactoring CycleDriver internals"
            # confirms this is intentional for plan 05.6.

            class _SettingsRef:
                """Single-cell mutable container around the current frozen Settings."""

                def __init__(self, initial: Settings) -> None:
                    self._cur = initial

                def get(self) -> Settings:
                    return self._cur

                def set(self, new: Settings) -> None:
                    self._cur = new

            settings_ref = _SettingsRef(settings)
            with EventLogWriter(event_log_path) as event_logger:
                # KmsgDedup per-detail 30s window (CONTEXT.md E-03).
                kmsg_dedup = KmsgDedup(window_seconds=30.0)

                # Production HostIssueEmitter placeholder — plan 05.6-03 swaps
                # in the CycleDriver-fed accumulator. For now: log at INFO so
                # the journal records every detected host issue and the bench
                # Jetson checkpoint can observe FR-14 detection working.
                # T-05.6-02-01: raw_line is truncated to 200 chars to bound
                # log volume + accidental PII.
                class _LoggingHostIssueEmitter:
                    """Plan 05.6-02 placeholder; 05.6-03 swaps for cycle-driver-fed list."""

                    def emit_host_issue(self, *, detail: IssueDetail, raw_line: str) -> None:
                        logger.info(
                            "host_issue detail=%s raw=%r",
                            detail.value,
                            raw_line[:200],
                        )

                host_issue_emitter: _MainIssueEmitterProto = _LoggingHostIssueEmitter()

                # events.jsonl reopener — consumed by the asyncinotify producer
                # on logrotate rotation (R-01 dispatcher path).
                events_log_reopener = EventLogReopener(writer=event_logger)

                # ---- 05.6-03: production subsystem composition --------------
                # StateStore + per-modem flocks under settings.run_dir/state.lock.
                store = StateStore(
                    state_root_override=state_root_path,
                    run_dir_override=run_dir,
                )

                # MetricRegistry: process-singleton; the Prom UDS scrapes the
                # same registry the cycle driver writes to (ADR-0013 chokepoint).
                metrics = MetricRegistry()

                # CarrierTable: production loads from settings.carriers_yaml_path.
                # The .deb ships /etc/spark-modem-watchdog/conf.d/00-carriers.yaml
                # (12 entries IL/US/GB/DE); operators SIGHUP-reload by editing
                # the file (FR-33). yaml.safe_load + model_validate is the
                # canonical pattern from test_default_carrier_table.py:28-32.
                carriers = _load_carrier_table_yaml(Path(settings.carriers_yaml_path))

                # CycleScheduler: production cadence = settings.cycle_interval_seconds
                # (C-01 default 60.0; C-02 RELOAD_DATA so SIGHUP can retune).
                scheduler = CycleScheduler(
                    interval_seconds=settings.cycle_interval_seconds,
                    clock=clock,
                )

                # HMAC secret read (settings.resolve_hmac_secret_path is the
                # Phase 05.2 L-02 fallback). FileNotFoundError -> empty secret
                # is documented in _read_hmac_secret.
                secret_bytes = _read_hmac_secret(settings.resolve_hmac_secret_path())

                # WebhookPoster: separate task in the TaskGroup (FR-44.8 —
                # cycle never blocks on webhook I/O). DNS pre-resolve
                # happens inside the poster's run_forever loop via DnsCache.
                webhook_poster = WebhookPoster(
                    url=settings.webhook_url,
                    secret=secret_bytes,
                    clock=clock,
                    config=settings,
                    event_logger=event_logger,
                    metrics=metrics,
                )

                # ---- 05.6-04 SIGHUP swapper ---------------------------
                # SighupSwapper rebuilds Settings from env+YAML via the
                # zero-arg `Settings` constructor (pydantic-settings reads
                # env vars at construction time). dns_cache is the same
                # cache the webhook poster uses, so a SIGHUP-driven
                # webhook_url change force-refreshes DNS via W-02
                # (sighup.py:118-126).
                sighup_swapper = SighupSwapper(
                    settings_ref=settings_ref,
                    settings_factory=Settings,
                    dns_cache=webhook_poster.dns_cache,
                )

                # Boot envelope (FR-44.5 — DaemonRestart with reason enum).
                # Enqueue BEFORE TaskGroup entry so the very first webhook
                # the receiver sees identifies the prior-run reason.
                # _laptop_main:145-154 has the same shape.
                boot_envelope = WebhookEnvelope(
                    payload=DaemonRestart(
                        ts_iso=clock.wall_clock_iso(),
                        reason=prior_reason_for_boot,
                        prior_run_uptime_seconds=prior_uptime_for_boot,
                    ),
                )
                await webhook_poster.enqueue(boot_envelope)

                # CycleDriver: the cycle's complete pipeline (observe →
                # policy → actions → persist → status → webhook). The
                # driver itself writes status.json INTERNALLY at step 6 of
                # run_one_cycle (cycle_driver.py:270); DO NOT also call
                # write_status_json from _cycle_loop — that would race.
                driver = CycleDriver(
                    store=store,
                    settings=settings,
                    clock=clock,
                    runner=subproc_runner,
                    inventory=inventory,
                    zao=zao_tailer,
                    carrier_table=carriers,
                    event_logger=event_logger,
                    metrics=metrics,
                    webhook_poster=webhook_poster,
                )

                # Prometheus UDS server — starts BEFORE cycle 0 (CONTEXT.md
                # Claude's Discretion: scrape protocol tolerates empty
                # registries). The server runs in a worker thread via
                # asyncio.to_thread so wsgiref's blocking serve_forever
                # doesn't stall the event loop. registry=None makes the
                # WSGI app expose the global REGISTRY — the same one
                # MetricRegistry registered into above.
                prom_server = start_metrics_server(
                    settings.metrics_socket_path,
                    registry=None,
                )

                # --- Production-default 0-arg coroutine factories ----------
                # Each wrapper re-constructs the inner coroutine on every
                # call so restart_on_crash's bounded re-entry envelope works
                # cleanly (an already-awaited coroutine raises RuntimeError).
                #
                # ``cast(Any, ...)`` at producer boundaries: each producer
                # module declares its own narrow ``_EventQueueProto`` /
                # ``_ZaoTailerProto`` Protocol (with ``put_nowait(item:
                # object)`` / structural ``on_inotify_event`` surface) which
                # is invariant-incompatible at type-check time with the
                # concrete ``asyncio.Queue[WakeSignal]`` and the production
                # ``ZaoLogInotifyTailer`` (whose ``ZaoLogTailer`` Protocol is
                # a different nominal type than asyncinotify's local Protocol
                # — both Protocols are co-located in their producer modules
                # to keep cross-package imports out of event_sources/).
                # ``cast`` makes the type-erasure explicit at the producer
                # boundary; the runtime call is correct (the producers only
                # call ``put_nowait(WakeSignal.UDEV)`` etc., which is a
                # narrower argument to the queue's ``put_nowait(WakeSignal)``).
                async def _udev_factory_default() -> None:
                    await run_udev_producer(event_queue=cast(Any, event_queue))

                async def _rtnetlink_factory_default() -> None:
                    await run_rtnetlink_producer(event_queue=cast(Any, event_queue))

                async def _asyncinotify_factory_default() -> None:
                    await run_asyncinotify_producer(
                        event_queue=cast(Any, event_queue),
                        events_jsonl_path=event_log_path,
                        zao_log_path=zao_log_path,
                        events_log_reopener=events_log_reopener,
                        zao_tailer=cast(Any, zao_tailer),
                    )

                async def _kmsg_factory_default() -> None:
                    await run_kmsg_producer(
                        event_queue=cast(Any, event_queue),
                        dedup=kmsg_dedup,
                        clock=clock,
                        issue_emitter=host_issue_emitter,
                    )

                # --- restart_on_crash-compatible supervised wrappers -------
                # 0-arg coroutine factories. Each call constructs a fresh
                # inner coroutine; restart_on_crash re-enters on Exception
                # with bounded (1,2,4,8,60)s backoff (supervisor.py:107).
                async def _udev_supervised() -> None:
                    if udev_factory is not None:
                        await udev_factory(event_queue)
                    else:
                        await _udev_factory_default()

                async def _rtnetlink_supervised() -> None:
                    if rtnetlink_factory is not None:
                        await rtnetlink_factory(event_queue)
                    else:
                        await _rtnetlink_factory_default()

                async def _asyncinotify_supervised() -> None:
                    if asyncinotify_factory is not None:
                        await asyncinotify_factory(event_queue)
                    else:
                        await _asyncinotify_factory_default()

                async def _kmsg_supervised() -> None:
                    if kmsg_factory is not None:
                        await kmsg_factory(event_queue)
                    else:
                        await _kmsg_factory_default()

                # supervisor's ``EventLogWriterProto.append(event: object)`` is
                # invariant-wider than the concrete
                # ``EventLogWriter.append(event: Event-union)``; cast once
                # here so the 4 restart_on_crash call sites stay clean.
                supervisor_event_logger: Any = event_logger

                # ---- 05.6-03 production cycle body ------------------------
                # Closure over: clock, scheduler, shutdown_event, event_queue,
                # driver, metrics, sd, cycle_count_ref, logger.
                #
                # Pipeline per cycle (PITFALLS §4.1 / L-01 ORDER):
                #   1. Wait: event_queue.get() OR scheduler.next_deadline() OR
                #      shutdown.
                #   2. CycleDriver.run_one_cycle(cycle_id) — observe / policy /
                #      actions / persist / status.json / metrics / webhook
                #      enqueues (driver writes status.json INTERNALLY at
                #      cycle_driver.py line 270; never call the status
                #      writer twice — that would race).
                #   3. kick the systemd watchdog AFTER the cycle.
                #   4. emit a terse STATUS line per C-05.
                #   5. fire sd READY on the FIRST SUCCESSFUL cycle (PITFALLS
                #      §4.1 "real work done"). Tracked via the
                #      ``ready_fired_ref`` single-cell list rather than the
                #      ``cycle_id == 0`` predicate so a cycle-0 crash that
                #      falls into the except arm below does not orphan READY
                #      — cycle 1's success branch will fire it. Same
                #      single-cell-list pattern as ``cycle_count_ref``.
                #   6. advance the cycle scheduler.
                ready_fired_ref: list[bool] = [False]

                async def _cycle_loop() -> None:
                    cycle_id = 0
                    while not shutdown_event.is_set():
                        # Step 1: wait for wake. The wake conditions are
                        # event_queue arrival, scheduler deadline, or shutdown.
                        # On the FIRST cycle there is no previous deadline so
                        # we drop straight into observe — cycle 0 runs ASAP
                        # to honour NFR-13 60 s READY budget.
                        if cycle_id > 0:
                            now_mono = clock.monotonic()
                            wait_seconds = max(
                                0.0,
                                scheduler.next_deadline() - now_mono,
                            )
                            try:
                                async with asyncio.timeout(wait_seconds):
                                    # event_queue.get() OR shutdown_event.wait()
                                    queue_task = asyncio.create_task(event_queue.get())
                                    shutdown_task = asyncio.create_task(shutdown_event.wait())
                                    _done, pending = await asyncio.wait(
                                        {queue_task, shutdown_task},
                                        return_when=asyncio.FIRST_COMPLETED,
                                    )
                                    for task in pending:
                                        task.cancel()
                                        with contextlib.suppress(
                                            asyncio.CancelledError,
                                            Exception,
                                        ):
                                            await task
                            except TimeoutError:
                                pass  # normal: scheduler deadline elapsed
                            # Drain coalesced wake signals UNCONDITIONALLY
                            # (after EITHER the queue/shutdown arm OR the
                            # timeout arm). A USB hub storm can deposit
                            # dozens of WakeSignals in <100 ms — and
                            # producers may also have enqueued items between
                            # cycle-end and the next get(); both paths must
                            # drain so no wake-signal is silently dropped on
                            # the next timeout boundary. The drain MUST live
                            # OUTSIDE the asyncio.timeout(...) block
                            # (placing it inside would skip drain on the
                            # normal-cadence timeout arm).
                            while True:
                                try:
                                    event_queue.get_nowait()
                                except asyncio.QueueEmpty:
                                    break

                        if shutdown_event.is_set():
                            return

                        # Step 2: drift accounting BEFORE cycle work begins (O-03).
                        cycle_start_mono = clock.monotonic()
                        if cycle_id > 0:
                            drift = max(
                                0.0,
                                cycle_start_mono - scheduler.expected_for_drift(),
                            )
                            metrics.set_cycle_drift(drift)
                        else:
                            drift = 0.0

                        # Step 3: the production cycle (NFR-11: errors are data,
                        # never crash; cycle_driver.run_one_cycle catches policy
                        # exceptions internally).
                        try:
                            result = await driver.run_one_cycle(cycle_id=cycle_id)
                        except Exception:
                            # Belt-and-suspenders: a bug in the driver itself
                            # MUST NOT kill the daemon. NFR-11.
                            logger.exception(
                                "cycle %d crashed in driver; continuing",
                                cycle_id,
                            )
                            cycle_id += 1
                            cycle_count_ref[0] = cycle_id
                            scheduler.advance()
                            continue

                        cycle_count_ref[0] = cycle_id + 1

                        # Step 4: WATCHDOG=1 fires AFTER the cycle completes
                        # (cycle driver writes status.json inside run_one_cycle
                        # step 6). PITFALLS §4.1 cycle-end placement.
                        sd.watchdog_kick()

                        # Step 5: STATUS= per cycle (C-05 verbatim format).
                        new_states = (
                            result.cycle_result.new_states
                            if result.cycle_result is not None
                            else {}
                        )
                        healthy_count = sum(
                            1 for s in new_states.values() if str(s.state).lower() == "healthy"
                        )
                        actions_count = len(result.action_results)
                        sd.status(
                            f"cycle={cycle_id} healthy={healthy_count}/4 "
                            f"actions={actions_count} drift={drift:.1f}s"
                        )

                        # Step 6: READY=1 on the first SUCCESSFUL cycle
                        # (PITFALLS §4.1). Decoupled from ``cycle_id`` so a
                        # cycle-0 crash followed by cycle-1 success still
                        # fires READY — see ready_fired_ref docstring above.
                        if not ready_fired_ref[0]:
                            sd.ready(f"first cycle ok healthy={healthy_count}/4")
                            ready_fired_ref[0] = True

                        cycle_id += 1
                        scheduler.advance()

                # ---- 05.6-04 SIGTERM choreography watcher ----------------
                # Replaces _stub_sigterm_watcher (plan 05.6-01). Waits for
                # shutdown_event, then constructs and runs the 8-step
                # SigtermChoreography. The choreography never raises
                # (NFR-11); each step is bounded by the 5s deadline.
                #
                # After the choreography returns, this coroutine RETURNS —
                # which signals the cycle_loop and the producer tasks to
                # cancel via the choreography's step 1 + step 2.
                #
                # Step ordering invariants (sigterm.py docstring):
                #   1. cancel cycle driver task FIRST
                #   2. cancel the 4 producer tasks
                #   3. webhook drain (<=3 s budget)
                #   4. final state flush (no-op: cycle driver atomic per cycle)
                #   5. emit DaemonStopped(reason=SIGTERM)
                #   6. stop the webhook poster (closes httpx client)
                #   7. unlink metrics socket
                #   8. write clean-shutdown marker
                async def _sigterm_watcher() -> None:
                    """L-02 SIGTERM choreography watcher."""
                    await shutdown_event.wait()
                    cycle_task_local = cycle_task_ref[0]
                    if cycle_task_local is None:
                        # Defensive: shutdown_event fired before the cycle
                        # task was created. Should never happen because
                        # tg.create_task(...) is synchronous and the
                        # cycle task is created BEFORE _sigterm_watcher
                        # itself is created in the TaskGroup spawn block.
                        logger.warning(
                            "shutdown_event fired before cycle task created; "
                            "skipping choreography step 1"
                        )
                        return

                    choreography = SigtermChoreography(
                        cycle_driver_task=cycle_task_local,
                        producer_tasks=producer_tasks,
                        webhook_poster=webhook_poster,
                        event_logger=cast(Any, event_logger),
                        metrics_socket_path=Path(settings.metrics_socket_path),
                        run_dir=run_dir,
                        clock=clock,
                        boot_monotonic=boot_mono,
                        cycle_count_ref=cycle_count_ref,
                        state_flush=None,  # cycle driver's atomic per-cycle write
                    )
                    await choreography.execute(deadline_seconds=5.0)
                    # After execute(): cycle_task already cancelled (step 1),
                    # producer tasks already cancelled (step 2). Returning
                    # from this watcher lets the TaskGroup unwind.

                # ---- 05.6-04 SIGHUP transactional Settings swap watcher --
                # Replaces _stub_sighup_watcher (plan 05.6-01). Loops until
                # shutdown_event is set. On each SIGHUP:
                #   * SighupSwapper.try_apply_reload() rebuilds Settings
                #     from env+YAML, diffs against current.
                #   * RELOAD_DATA-only diff: applies; webhook DNS
                #     force-refresh on webhook_url change.
                #   * RELOAD_RESTART field change: refuses with a
                #     structured `restart_required` log line; keeps old
                #     Settings (FR-54-runtime semantics).
                #   * No-op SIGHUP (no diff): also returns True; common
                #     pattern for operator "is daemon responsive?" probes.
                async def _sighup_watcher() -> None:
                    """L-03 SIGHUP transactional Settings swap watcher."""
                    while not shutdown_event.is_set():
                        # Race the SIGHUP event vs the shutdown event so
                        # this watcher exits promptly under either trigger.
                        # Same shape plan 05.6-01 established for
                        # _stub_sighup_watcher (caught by smoke test as
                        # deadlock-on-SIGTERM-without-SIGHUP).
                        sighup_task = asyncio.create_task(sighup_event.wait())
                        shutdown_task = asyncio.create_task(shutdown_event.wait())
                        _done, pending = await asyncio.wait(
                            {sighup_task, shutdown_task},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        for task in pending:
                            task.cancel()
                            with contextlib.suppress(asyncio.CancelledError, Exception):
                                await task

                        if shutdown_event.is_set():
                            return

                        # SIGHUP fired; consume the event and apply.
                        sighup_event.clear()
                        try:
                            await sighup_swapper.try_apply_reload()
                        except Exception:
                            # NFR-11: a swap failure NEVER crashes the daemon.
                            # SighupSwapper.try_apply_reload already catches
                            # internally; this is belt-and-suspenders.
                            logger.exception("sighup swap raised unexpectedly")

                # --- TaskGroup: 4 producers + webhook + prom + cycle +
                # 2 signal watchers (9 tasks total).
                # The TaskGroup exits when shutdown_event is set: _cycle_loop
                # observes via its asyncio.wait race, _sigterm_watcher runs
                # the 8-step SigtermChoreography (which cancels the cycle
                # driver task FIRST, then producer_tasks, then drains the
                # webhook, then closes the prom UDS socket), then the
                # producers + webhook + prom + sighup watcher get cancelled
                # via CancelledError when this watcher returns.
                async with asyncio.TaskGroup() as tg:
                    producer_tasks.append(
                        tg.create_task(
                            restart_on_crash(
                                "udev_producer",
                                _udev_supervised,
                                sleeper=sleeper,
                                event_logger=supervisor_event_logger,
                                clock=clock,
                            )
                        )
                    )
                    producer_tasks.append(
                        tg.create_task(
                            restart_on_crash(
                                "rtnetlink_producer",
                                _rtnetlink_supervised,
                                sleeper=sleeper,
                                event_logger=supervisor_event_logger,
                                clock=clock,
                            )
                        )
                    )
                    producer_tasks.append(
                        tg.create_task(
                            restart_on_crash(
                                "asyncinotify_producer",
                                _asyncinotify_supervised,
                                sleeper=sleeper,
                                event_logger=supervisor_event_logger,
                                clock=clock,
                            )
                        )
                    )
                    producer_tasks.append(
                        tg.create_task(
                            restart_on_crash(
                                "kmsg_producer",
                                _kmsg_supervised,
                                sleeper=sleeper,
                                event_logger=supervisor_event_logger,
                                clock=clock,
                            )
                        )
                    )

                    # ---- webhook background task (FR-44.8: cycle never
                    # blocks on webhook I/O) ------------------------------
                    tg.create_task(webhook_poster.run_forever())

                    # ---- Prometheus UDS scrape server ------------------
                    # serve_forever is blocking sync; run in a worker thread
                    # so wsgiref's accept loop doesn't stall the event loop.
                    tg.create_task(asyncio.to_thread(prom_server.serve_forever))

                    # ---- cycle + signal watchers -----------------------
                    # Capture cycle task handle for SigtermChoreography
                    # (plan 05.6-04). The choreography's step 1 cancels
                    # this task FIRST so any in-flight cycle aborts before
                    # the producers + webhook drain start.
                    cycle_task_ref[0] = tg.create_task(_cycle_loop())
                    tg.create_task(_sigterm_watcher())
                    tg.create_task(_sighup_watcher())

                # Belt-and-suspenders: ensure webhook_poster is stopped even
                # if the TaskGroup unwound via something other than SIGTERM
                # (e.g. an uncaught exception bubble; the choreography's
                # step 6 already calls stop() on the SIGTERM path, and
                # WebhookPoster.stop() is idempotent).
                webhook_poster.stop()
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
