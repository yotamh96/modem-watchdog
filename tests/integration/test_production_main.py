"""Phase 05.6 in-process main() regression test for production TaskGroup wiring.

T-01..T-04 per CONTEXT.md: pin the WIRING in `_production_main` (vs the
producer contracts which are covered by their own Plan 03-02..05 tests).

A return-0 placeholder slips through ``test_lifecycle.py`` (which bypasses
`_production_main` via direct composition). This test catches that
regression by going through the real ``main()`` entrypoint.

T-05: SC #3 SIGTERM 5s + SC #4 SIGHUP coverage stays in test_lifecycle.py.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import signal
import sys
import threading
from pathlib import Path

import pytest
from prometheus_client.registry import CollectorRegistry

from spark_modem.config.settings import Settings
from spark_modem.daemon import main as main_module
from spark_modem.daemon.main import main
from spark_modem.inventory.descriptor import ModemDescriptor
from spark_modem.status_reporter.metrics_registry import MetricRegistry
from spark_modem.zao_log.snapshot import ZaoSnapshot
from tests.fakes.sdnotify import FakeSdNotify

pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="Filesystem inode semantics + real flock are POSIX (linux_only suite)",
    ),
    pytest.mark.asyncio,
]


# ---------------------------------------------------------------------------
# Producer + subsystem stubs.
#
# The test does NOT exercise real pyudev / pyroute2 / asyncinotify / kmsg
# bindings — those have their own Plan 03-02..05 tests. This test pins the
# WIRING in _production_main.
#
# Strategy: monkeypatch the producer entry points (run_udev_producer,
# run_rtnetlink_producer, run_asyncinotify_producer, run_kmsg_producer)
# to coroutines that sleep forever; the cycle loop still wakes via the
# scheduler deadline (sub-second cadence via env-var override) so cycle 0
# completes on the deadline arm. ALL 4 producers are cancelled when
# shutdown_event is set (TaskGroup propagation; SigtermChoreography step 2).
# ---------------------------------------------------------------------------


async def _idle_producer(*args: object, **kwargs: object) -> None:
    """Drop-in for any of the 4 run_*_producer functions.

    Sleeps forever; CancelledError passes through (TaskGroup unwinds it
    cleanly per restart_on_crash's supervisor wrapper).
    """
    del args, kwargs
    await asyncio.Future()


class _FakeNoZaoTailer:
    """Always-unknown Zao tailer — copied from test_lifecycle.py:95-103.

    Production wires ZaoLogInotifyTailer(log_path=...); the test path needs
    only is_line_active + snapshot.
    """

    def is_line_active(self, line_idx: int) -> bool:
        del line_idx
        return False

    def snapshot(self) -> object:
        return ZaoSnapshot.unknown(reason="integration-test-production-main")

    async def on_inotify_event(self, **kwargs: object) -> None:
        # asyncinotify producer is monkeypatched away; this is just here
        # in case the ZaoLogTailer Protocol is widened in future.
        del kwargs


class _FakeFourModemInventory:
    """Returns 4 ModemDescriptors matching the bench Jetson layout."""

    async def scan(self) -> list[object]:
        return [
            ModemDescriptor(
                line=i,
                cdc_wdm=f"cdc-wdm{i - 1}",
                usb_path=f"2-3.1.{i}",
                ns=None,
                iface=f"wwan{i - 1}",
            )
            for i in range(1, 5)
        ]


async def test_production_main_wires_taskgroup_and_fires_ready(  # noqa: PLR0915
    integration_state_root: Path,
    integration_run_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T-01..T-04: in-process main() runs cycle 0 + fires READY=1 + writes status.json.

    Catches the return-0 placeholder regression:
      1. fake_sd.ready_calls has exactly 1 entry (TaskGroup ran cycle 0).
      2. status.json exists with 4 modems + summary.expected_modems == 4.
      3. At least one cycle metric recorded (cycle_duration_seconds via
         an isolated CollectorRegistry injected via monkeypatched MetricRegistry).
    """
    # ---- Set up env-var Settings overrides so production paths point at tmp ----
    events_log = tmp_path / "events.jsonl"
    carriers_yaml = tmp_path / "carriers.yaml"
    # Write a minimal valid carriers.yaml so the production loader does not
    # bail to the empty-fallback path.
    carriers_yaml.write_text("carriers: []\n", encoding="utf-8")
    # Provide an empty HMAC secret file so resolve_hmac_secret_path returns
    # a readable path (production code path); webhook_url is None so the
    # poster effectively no-ops.
    hmac_secret = tmp_path / "hmac-secret"
    hmac_secret.write_bytes(b"")

    monkeypatch.setenv("SPARK_MODEM_STATE_ROOT", str(integration_state_root))
    monkeypatch.setenv("SPARK_MODEM_RUN_DIR", str(integration_run_dir))
    monkeypatch.setenv("SPARK_MODEM_EVENTS_LOG_PATH", str(events_log))
    monkeypatch.setenv(
        "SPARK_MODEM_METRICS_SOCKET_PATH",
        str(integration_run_dir / "metrics.sock"),
    )
    monkeypatch.setenv("SPARK_MODEM_CARRIERS_YAML_PATH", str(carriers_yaml))
    # Force cycle interval to the Settings floor (ge=1.0 enforced by pydantic;
    # 05.6-01 explicitly preserved that floor against this plan's earlier
    # 0.1 example). Cycle 0 drops straight into observe without waiting on
    # the scheduler deadline (per plan 05.6-03 wiring), so the 1.0s value
    # only affects cycles 1+, which the asyncio.wait_for(timeout=15.0)
    # budget accommodates.
    monkeypatch.setenv("SPARK_MODEM_CYCLE_INTERVAL_SECONDS", "1.0")
    # Disable sd_notify in production: NOTIFY_SOCKET unset means the
    # SdNotifyLifecycle constructor silently no-ops. The monkeypatch below
    # swaps in FakeSdNotify so calls are observable.
    monkeypatch.delenv("NOTIFY_SOCKET", raising=False)
    # webhook_url defaults to None — poster's enqueue() will record
    # webhook_delivery_total{result="skipped_no_url"} and return.

    # ---- Monkeypatch SdNotifyLifecycle to FakeSdNotify ----
    fake_sd = FakeSdNotify()
    monkeypatch.setattr(main_module, "SdNotifyLifecycle", lambda: fake_sd)

    # ---- Monkeypatch the 4 producer entry points to idle coroutines ----
    monkeypatch.setattr(main_module, "run_udev_producer", _idle_producer)
    monkeypatch.setattr(main_module, "run_rtnetlink_producer", _idle_producer)
    monkeypatch.setattr(main_module, "run_asyncinotify_producer", _idle_producer)
    monkeypatch.setattr(main_module, "run_kmsg_producer", _idle_producer)

    # ---- Monkeypatch UdevInventory + ZaoLogInotifyTailer to test doubles ----
    # The cycle driver's CycleDriver constructor takes the InventorySource +
    # ZaoLogTailer. Production wires UdevInventory + ZaoLogInotifyTailer;
    # we monkeypatch the classes' constructors to return our fakes.
    monkeypatch.setattr(main_module, "UdevInventory", lambda **kw: _FakeFourModemInventory())
    monkeypatch.setattr(
        main_module,
        "ZaoLogInotifyTailer",
        lambda **kw: _FakeNoZaoTailer(),
    )

    # ---- Monkeypatch resolve_hmac_secret_path to point at the empty file ----
    # Settings.resolve_hmac_secret_path is an instance METHOD, so we
    # monkeypatch it at the class level on Settings.
    monkeypatch.setattr(
        Settings,
        "resolve_hmac_secret_path",
        lambda self: hmac_secret,
    )

    # ---- Monkeypatch MetricRegistry to use an isolated CollectorRegistry ----
    # The global prometheus_client.REGISTRY is shared across the test session;
    # constructing a second MetricRegistry() with the global registry raises
    # ValueError("Duplicated timeseries") if any prior test already registered
    # the same metric names. We inject an isolated CollectorRegistry so this
    # test is hermetic. The assertion below reads from this isolated registry.
    isolated_registry = CollectorRegistry(auto_describe=False)
    isolated_metrics = MetricRegistry(registry=isolated_registry)

    # Replace the MetricRegistry CLASS in the main_module namespace so that
    # `_production_main`'s `metrics = MetricRegistry()` returns our pre-built
    # isolated instance (via a no-arg lambda).
    monkeypatch.setattr(main_module, "MetricRegistry", lambda: isolated_metrics)

    # ---- Monkeypatch start_metrics_server to a no-op stub ----
    # The real start_metrics_server binds an AF_UNIX socket + calls
    # asyncio.to_thread(serve_forever). For the in-process test we
    # don't want a worker thread leaking past the test; replace with
    # a server whose serve_forever blocks on a threading.Event so the
    # asyncio.to_thread task stays parked until CancelledError unwinds it.
    class _FakePromServer:
        def serve_forever(self) -> None:
            threading.Event().wait()

        def shutdown(self) -> None:
            pass

    monkeypatch.setattr(main_module, "start_metrics_server", lambda *a, **kw: _FakePromServer())

    # ---- Drive shutdown after cycle 0 completes ----
    # The daemon's `_production_main` body creates `shutdown_event` locally.
    # We can't directly access it from outside without exposing it. The
    # cleanest seam: poll `fake_sd.ready_calls` and, once cycle 0 fired,
    # signal shutdown. The daemon's `_sigterm_watcher` reads shutdown_event;
    # we trigger it via signal.raise_signal(signal.SIGTERM) which delivers
    # via the signal API the loop has registered.
    #
    # Asyncio's loop.add_signal_handler does receive signal.raise_signal()
    # in the same process — the kernel signal is delivered to the running
    # process and the handler fires. This is the canonical "trigger
    # SIGTERM from a test" pattern (NOT os.kill, which is the documented
    # CLAUDE.md anti-pattern). signal.raise_signal is the
    # current-process equivalent (Python 3.8+).
    #
    # NOTE: the handler installed inside the daemon dispatches the event
    # correctly so the full SigtermChoreography runs end-to-end.
    async def _drive_shutdown_after_ready() -> None:
        deadline = asyncio.get_running_loop().time() + 10.0
        while asyncio.get_running_loop().time() < deadline:
            if fake_sd.ready_calls:
                # Cycle 0 finished; give the rest of the loop one more
                # tick to wire WATCHDOG + STATUS before signalling.
                await asyncio.sleep(0.1)
                # FR-61: assert the PID lock file exists at run_dir/lock
                # WHILE the daemon is still running (before SIGTERM
                # unwinds the choreography, which deletes the lock via
                # the kernel on process exit per ADR-0012). This proves
                # the PID-lock-held-during-cycle invariant — without
                # this assertion T-04 would silently miss FR-61
                # coverage.
                assert (integration_run_dir / "lock").exists(), (
                    "FR-61: PID lock file must exist at run_dir/lock while daemon is running"
                )
                signal.raise_signal(signal.SIGTERM)
                return
            await asyncio.sleep(0.05)
        # Timeout: cycle 0 never fired READY. Test will fail on the
        # assert below; raise the signal anyway so the daemon exits.
        signal.raise_signal(signal.SIGTERM)

    # Spawn the shutdown-driver concurrently with main().
    shutdown_driver_task = asyncio.create_task(_drive_shutdown_after_ready())

    # ---- Run main() via the real entrypoint ----
    # asyncio.wait_for with a 15 s total budget (T-05.6-05-02 mitigation).
    # The `await main([...])` call below is the ONLY entry path the test
    # exercises; _production_main wires the real TaskGroup via this argv.
    async def _run_main() -> int:
        """Thin wrapper so asyncio.wait_for can time-bound the entire run."""
        return await main(["--skip-preflight"])

    rc = await asyncio.wait_for(_run_main(), timeout=15.0)

    # Cleanup the driver task.
    shutdown_driver_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await shutdown_driver_task

    # ---- T-04 assertions ----
    assert rc == 0, f"main() returned {rc}; expected 0 on clean shutdown"
    assert len(fake_sd.ready_calls) == 1, (
        f"READY=1 must fire exactly once after cycle 0; "
        f"got {len(fake_sd.ready_calls)} calls (calls={fake_sd.ready_calls!r})"
    )
    assert fake_sd.watchdog_calls >= 1, (
        f"watchdog_kick must fire at least once at cycle-end; got {fake_sd.watchdog_calls}"
    )
    assert fake_sd.status_calls, "STATUS= must fire at least once per cycle (C-05)"

    # status.json shape
    status_path = integration_state_root / "status.json"
    assert status_path.exists(), "cycle 0 must write status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert len(status["modems"]) == 4, (
        f"expected 4 modems in status.json; got {len(status['modems'])}"
    )
    assert status["summary"]["expected_modems"] == 4

    # cycle metric recorded — read from the isolated CollectorRegistry.
    # The cycle driver calls metrics.observe_cycle_duration(seconds) in
    # cycle_driver.py. The histogram has a _count sample we can read.
    cycle_duration_total = 0.0
    for metric in isolated_registry.collect():
        if metric.name == "cycle_duration_seconds":
            for sample in metric.samples:
                if sample.name == "cycle_duration_seconds_count":
                    cycle_duration_total += sample.value
    assert cycle_duration_total >= 1.0, (
        f"cycle_duration_seconds_count must be ≥1 after cycle 0; got {cycle_duration_total}"
    )
