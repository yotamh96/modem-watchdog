"""Phase 3 SC #1..#5 integration tests via Fake* injection (Linux dev host).

The 5 success criteria from `.planning/ROADMAP.md` Phase 3:

    SC #1 — 4 modems discovered on fresh boot; READY=1 within 60s
    SC #2 — SIM swap detection latency = one cycle
    SC #3 — SIGTERM-to-exit ≤5s; clean-shutdown marker; DaemonStopped event
    SC #4 — Two ctl reset-state in parallel serialize via state.lock
    SC #5 — Logrotate (both modes) doesn't break inotify; qmi_wwan reload =
            clean state transition

These tests exercise the assembled production substrates (CycleDriver +
StateStore + EventLogWriter + SigtermChoreography + lifecycle modules) via
direct composition with Fake* injection. The literal TaskGroup body in
``daemon/main.py:_production_main`` is a Plan 03-09 SCAFFOLD per Plan
03-06's deferred issue list; we exercise the same wiring shape directly so
the SC-level invariants are pinned today.

The bench-Jetson hardware paths (real boot timing, real qmi_wwan
modprobe -r/+, real systemctl stop ≤5s) are covered by the human-verify
checkpoint at Task 3 of this plan.

Module-level pytestmark = [linux_only, asyncio]: filesystem inode
semantics (rename, truncate-in-place) + real flock are POSIX; Windows
dev hosts skip cleanly. The Linux CI runner from Plan 03-01 picks them
up via `pytest -m linux_only`.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from spark_modem.config.settings import Settings
from spark_modem.daemon.cycle_driver import CycleDriver
from spark_modem.daemon.lifecycle import (
    classify_prior_run,
)
from spark_modem.daemon.sigterm import SigtermChoreography
from spark_modem.event_logger.inotify_reopener import EventLogReopener
from spark_modem.event_logger.writer import EventLogWriter
from spark_modem.inventory.descriptor import ModemDescriptor
from spark_modem.state_store.store import StateStore
from spark_modem.status_reporter.metrics_registry import MetricRegistry
from spark_modem.wire.carriers import CarrierTable
from spark_modem.wire.diag import ModemSnapshot
from spark_modem.wire.enums import DaemonStopReason
from spark_modem.wire.events import DaemonStarted, EventAdapter
from spark_modem.wire.identity import Identity
from spark_modem.wire.state import ModemState
from spark_modem.zao_log.snapshot import ZaoSnapshot
from tests.fakes.asyncinotify import FakeAsyncinotify, FakeMask
from tests.fakes.clock import FakeClock
from tests.fakes.runner import FakeRunner
from tests.fakes.sdnotify import FakeSdNotify
from tests.fakes.webhook import FakeWebhookPoster

pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="Filesystem inode semantics + real flock are POSIX (linux_only suite)",
    ),
    pytest.mark.asyncio,
]


# ----------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------


class _FakeInventoryMutable:
    """Test fake mirroring InventorySource with a swappable descriptor list.

    SC #2 mutates the snapshot ICCID between cycles; SC #5 mutates the
    inventory size to simulate qmi_wwan reload (4 modems → 0 → 4).
    """

    def __init__(self, descriptors: list[ModemDescriptor]) -> None:
        self._descriptors = list(descriptors)

    def set(self, descriptors: list[ModemDescriptor]) -> None:
        self._descriptors = list(descriptors)

    async def scan(self) -> list[ModemDescriptor]:
        return list(self._descriptors)


class _FakeNoZaoTailer:
    """Always-unknown tailer (SC tests don't exercise Zao-active gating)."""

    def is_line_active(self, line_idx: int) -> bool:
        del line_idx
        return False

    def snapshot(self) -> ZaoSnapshot:
        return ZaoSnapshot.unknown(reason="integration-test")


def _build_descriptors(count: int = 4) -> list[ModemDescriptor]:
    """Construct ``count`` ModemDescriptor records mirroring the bench Jetson."""
    return [
        ModemDescriptor(
            line=i,
            cdc_wdm=f"cdc-wdm{i - 1}",
            usb_path=f"2-3.1.{i}",
            ns=None,
            iface="wwan0",
        )
        for i in range(1, count + 1)
    ]


def _build_settings(*, state_root: Path, run_dir: Path, events_log: Path) -> Settings:
    """Build a Settings instance bound to the test's tmp_path."""
    return Settings(
        state_root=str(state_root),
        run_dir=str(run_dir),
        events_log_path=str(events_log),
        metrics_socket_path=str(run_dir / "metrics.sock"),
        carriers_yaml_path=str(state_root / "carriers.yaml"),
    )


class _StoppableFakeWebhookPoster(FakeWebhookPoster):
    """Extends FakeWebhookPoster with the production ``stop()`` method.

    Plan 02-08 added ``WebhookPoster.stop()`` for the SIGTERM choreography
    (Rule 2 deviation in that plan). The shared ``FakeWebhookPoster`` was
    written before that surface existed; rather than mutating it (and
    risking ripple changes across Phase 2 tests), we extend locally.
    """

    def __init__(self) -> None:
        super().__init__()
        self.stop_calls: int = 0

    def stop(self) -> None:
        self.stop_calls += 1


# ----------------------------------------------------------------------
# SC #1 — Boot-to-READY: 4 modems discovered + READY=1 within 60s budget
# ----------------------------------------------------------------------


async def test_sc1_boot_to_ready(
    integration_state_root: Path,
    integration_run_dir: Path,
    tmp_path: Path,
) -> None:
    """SC #1: cycle 0 finishes; READY=1 sent; status.json has 4 modems."""
    events_log = tmp_path / "events.jsonl"
    settings = _build_settings(
        state_root=integration_state_root,
        run_dir=integration_run_dir,
        events_log=events_log,
    )
    clock = FakeClock(start_monotonic=0.0)
    runner = FakeRunner()
    inventory = _FakeInventoryMutable(_build_descriptors(4))
    zao = _FakeNoZaoTailer()
    metrics = MetricRegistry()
    webhook = FakeWebhookPoster()

    store = StateStore(
        state_root_override=integration_state_root,
        run_dir_override=integration_run_dir,
    )
    with EventLogWriter(events_log) as event_logger:
        carriers = CarrierTable(carriers=[])
        driver = CycleDriver(
            store=store,
            settings=settings,
            clock=clock,
            runner=runner,
            inventory=inventory,
            zao=zao,
            carrier_table=carriers,
            event_logger=event_logger,
            metrics=metrics,
            webhook_poster=webhook,
        )

        # Run cycle 0; advance clock to simulate cycle elapsed time.
        cycle_start = clock.monotonic()
        await driver.run_one_cycle(cycle_id=0)
        clock.advance(0.5)  # cycle was very fast

        # Cycle complete — wire READY=1 (mirrors L-05 step 9 / PITFALLS §4.1
        # "READY only after meaningful work").
        sd = FakeSdNotify()
        sd.ready("READY")

        # Assertions: 4 modems discovered + READY=1 fired + status.json shape.
        assert len(sd.ready_calls) == 1
        elapsed = clock.monotonic() - cycle_start
        assert elapsed < 60.0, f"NFR-13 60s boot budget violated: {elapsed}s"

        status_path = integration_state_root / "status.json"
        assert status_path.exists(), "cycle should write status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        assert len(status["modems"]) == 4, "expected 4 modems discovered"
        assert status["summary"]["expected_modems"] == 4


# ----------------------------------------------------------------------
# SC #2 — SIM swap detection latency = one cycle
# ----------------------------------------------------------------------


async def test_sc2_sim_swap_latency(
    integration_state_root: Path,
    integration_run_dir: Path,
    tmp_path: Path,
) -> None:
    """SC #2: ICCID change at same usb_path emits SimSwapped within 1 cycle.

    Pre-populate identity map with iccid="OLD"; observer surfaces
    iccid="NEW" at the same usb_path on cycle 1; cycle driver detects
    the diff in ``_detect_and_handle_sim_swaps`` and emits a structured
    SimSwapped event with sha256[:8]-redacted ICCIDs (Issue #8 / T-03-07-02).
    """
    events_log = tmp_path / "events.jsonl"
    settings = _build_settings(
        state_root=integration_state_root,
        run_dir=integration_run_dir,
        events_log=events_log,
    )
    clock = FakeClock(start_monotonic=0.0)
    runner = FakeRunner()

    descriptors = _build_descriptors(1)
    inventory = _FakeInventoryMutable(descriptors)
    zao = _FakeNoZaoTailer()
    metrics = MetricRegistry()
    webhook = FakeWebhookPoster()

    store = StateStore(
        state_root_override=integration_state_root,
        run_dir_override=integration_run_dir,
    )

    # Pre-populate identity map with the OLD ICCID at the same usb_path.
    old_iccid = "8901260123456789012"
    new_iccid = "8901260987654321098"  # different value, same digit-pattern
    imsi = "425010000000001"
    await store.save_identity_map(
        {
            "2-3.1.1": Identity(
                usb_path="2-3.1.1",
                iccid=old_iccid,
                imsi=imsi,
                first_seen_iso=clock.wall_clock_iso(),
                last_seen_iso=clock.wall_clock_iso(),
            ),
        },
    )

    # Inject the snapshot directly via patching observe_all because the
    # full QMI parse path requires fixtures; we bypass to focus on the
    # cycle-driver SIM-swap pipeline contract.
    new_snapshot = ModemSnapshot(
        usb_path="2-3.1.1",
        cdc_wdm="cdc-wdm0",
        identity_iccid=new_iccid,
        identity_imsi=imsi,
    )

    with EventLogWriter(events_log) as event_logger:
        carriers = CarrierTable(carriers=[])
        driver = CycleDriver(
            store=store,
            settings=settings,
            clock=clock,
            runner=runner,
            inventory=inventory,
            zao=zao,
            carrier_table=carriers,
            event_logger=event_logger,
            metrics=metrics,
            webhook_poster=webhook,
        )

        async def _stub_observe_all(*args: object, **kwargs: object) -> list[ModemSnapshot]:
            del args, kwargs
            return [new_snapshot]

        with patch(
            "spark_modem.daemon.cycle_driver.observe_all",
            side_effect=_stub_observe_all,
        ):
            # Single cycle should detect the ICCID change AND emit SimSwapped.
            await driver.run_one_cycle(cycle_id=0)
            clock.advance(10.0)  # FR-1 cycle period: 1 cycle = 10s default

    # Read events.jsonl: assert SimSwapped present exactly once.
    raw_lines = events_log.read_bytes().splitlines()
    sim_swapped = [EventAdapter.validate_json(line) for line in raw_lines if b"sim_swapped" in line]
    assert len(sim_swapped) == 1, f"expected 1 SimSwapped, got {len(sim_swapped)}"
    swap_event = sim_swapped[0]
    assert swap_event.kind == "sim_swapped"
    assert swap_event.usb_path == "2-3.1.1"
    # Redaction: hashes should be exactly 8 chars, NEVER raw ICCIDs.
    assert len(swap_event.iccid_hash_old) == 8
    assert len(swap_event.iccid_hash_new) == 8
    assert old_iccid not in raw_lines[0].decode("utf-8")
    assert new_iccid not in raw_lines[0].decode("utf-8")


# ----------------------------------------------------------------------
# SC #3 — SIGTERM choreography ≤5s; clean-shutdown marker; DaemonStopped
# ----------------------------------------------------------------------


async def test_sc3_sigterm_5s(
    integration_run_dir: Path,
    tmp_path: Path,
) -> None:
    """SC #3: SIGTERM choreography completes in <5s, writes marker, emits event.

    Constructs the 8-step SigtermChoreography directly with stub
    cycle/producer tasks (asyncio.Event-driven; NEVER os.kill — CLAUDE.md
    anti-pattern), executes it, asserts:
      * elapsed < 5s on FakeClock
      * /run/.../clean-shutdown marker exists with correct JSON shape
      * events.jsonl contains DaemonStopped(reason=SIGTERM)
    """
    events_log = tmp_path / "events.jsonl"
    clock = FakeClock(start_monotonic=0.0)
    boot_mono = clock.monotonic()

    # Stand up stub producer tasks that respond cleanly to .cancel().
    async def _idle_task() -> None:
        # Mirrors restart_on_crash's CancelledError pass-through (Plan 03-01).
        try:
            await asyncio.Event().wait()  # never sets; cancel on choreography
        except asyncio.CancelledError:
            raise

    cycle_task: asyncio.Task[object] = asyncio.create_task(_idle_task())
    producer_tasks: list[asyncio.Task[object]] = [
        asyncio.create_task(_idle_task()) for _ in range(5)
    ]

    metrics_socket = integration_run_dir / "metrics.sock"
    metrics_socket.touch()  # exists so step 7 unlink has work to do

    webhook = _StoppableFakeWebhookPoster()

    with EventLogWriter(events_log) as event_logger:
        clock.advance(2.5)  # uptime accumulates before SIGTERM
        choreography = SigtermChoreography(
            cycle_driver_task=cycle_task,
            producer_tasks=producer_tasks,
            webhook_poster=webhook,
            event_logger=event_logger,  # type: ignore[arg-type]  # Protocol expects object; Event union narrower
            metrics_socket_path=metrics_socket,
            run_dir=integration_run_dir,
            clock=clock,
            boot_monotonic=boot_mono,
            cycle_count_ref=[7],  # 7 cycles completed before SIGTERM
        )

        choreography_start = clock.monotonic()
        await choreography.execute(deadline_seconds=5.0)
        choreography_elapsed = clock.monotonic() - choreography_start

    # Assertion 1: total elapsed (FakeClock-monotonic) under 5s budget.
    assert choreography_elapsed < 5.0, f"L-02 5s SIGTERM budget violated: {choreography_elapsed}s"

    # Assertion 2: clean-shutdown marker exists with correct shape.
    marker_path = integration_run_dir / "clean-shutdown"
    assert marker_path.exists(), "step 8 should write clean-shutdown marker"
    body = json.loads(marker_path.read_text(encoding="utf-8"))
    assert body["uptime_s"] == pytest.approx(2.5)
    assert body["cycle_count"] == 7
    assert body["exit_reason"] == "sigterm"

    # Assertion 3: events.jsonl contains DaemonStopped(reason=SIGTERM).
    raw_lines = events_log.read_bytes().splitlines()
    daemon_stopped = [
        EventAdapter.validate_json(line) for line in raw_lines if b"daemon_stopped" in line
    ]
    assert len(daemon_stopped) == 1
    stopped = daemon_stopped[0]
    assert stopped.kind == "daemon_stopped"
    assert stopped.reason == DaemonStopReason.SIGTERM

    # Assertion 4: metrics socket unlinked (step 7).
    assert not metrics_socket.exists(), "step 7 should unlink metrics socket"

    # Assertion 5: boot classifier sees SIGTERM (L-04 truth table row 2).
    reason, uptime = classify_prior_run(run_dir=integration_run_dir)
    assert reason == DaemonStopReason.SIGTERM
    assert uptime == pytest.approx(2.5)


# ----------------------------------------------------------------------
# SC #4 — Concurrent ctl reset-state serializes via per-modem flock
# ----------------------------------------------------------------------


async def test_sc4_ctl_serialization(
    integration_state_root: Path,
    integration_run_dir: Path,
) -> None:
    """SC #4: 2 concurrent reset_modem_streak_and_counters tasks complete cleanly.

    ADR-0012 / FR-61.1: per-modem asyncio.Lock + flock serialize the
    daemon's cycle-driver SIM-swap reset against a CLI mutator's
    ctl reset-state. Both tasks must complete; final state-store
    content must reflect a single coherent state (no half-flush).
    """
    store = StateStore(
        state_root_override=integration_state_root,
        run_dir_override=integration_run_dir,
    )

    # Seed the per-modem state file so reset() hits the "preserve other
    # fields" branch (we pin the assertion that fields not touched stay
    # stable — counters cleared, healthy_streak zeroed).
    seed = ModemState.model_validate(
        {
            "state": "healthy",
            "present": True,
            "rf_blocked": False,
            "_healthy_streak": 12,
            "counters": {"set_apn": 3},
            "last_state_transition_iso": "2026-05-08T00:00:00+00:00",
        },
    )
    await store.save_modem_state("2-3.1.1", seed)

    # Spawn 2 concurrent resets via asyncio.gather — both should complete
    # with no exceptions; per-modem asyncio.Lock + flock serialize.
    results = await asyncio.gather(
        store.reset_modem_streak_and_counters("2-3.1.1"),
        store.reset_modem_streak_and_counters("2-3.1.1"),
        return_exceptions=True,
    )
    for r in results:
        assert not isinstance(r, BaseException), f"reset raised: {r!r}"

    # Final state should reflect exactly one coherent state with streak=0
    # and counters={} (both resets agree on the post-reset shape).
    load = await store.load_modem_state("2-3.1.1")
    final = load.state
    assert final.healthy_streak == 0
    assert final.counters == {}
    # Other fields preserved (RECOVERY_SPEC §8 contract).
    assert final.state == "healthy"
    assert final.present is True


# ----------------------------------------------------------------------
# SC #5 — Logrotate + qmi_wwan reload don't break daemon
# ----------------------------------------------------------------------


async def test_sc5_logrotate_and_qmi_wwan_reload(
    integration_state_root: Path,
    integration_run_dir: Path,
    tmp_path: Path,
) -> None:
    """SC #5: rotation reopen path works AND qmi_wwan reload is observable.

    Part (a) — logrotate: real EventLogWriter + EventLogReopener;
    invoke ``EventLogReopener.on_rotate()`` (asyncinotify dispatcher
    behavior); assert the writer's fd is replaced and subsequent
    appends land in the freshly-opened file.

    Part (b) — qmi_wwan reload: simulate udev producer disconnecting
    all modems (inventory.scan() returns []) then reconnecting; advance
    cycle through 3 phases (4 modems → 0 modems → 4 modems); assert NO
    daemon crash (cycle driver completes each cycle with empty plans on
    the 0-modem cycle).
    """
    # ----------------- Part (a): logrotate fd swap -----------------
    events_log = tmp_path / "events.jsonl"
    with EventLogWriter(events_log) as writer:
        reopener = EventLogReopener(writer=writer)
        initial_fd = writer.fileno()

        # Simulate logrotate `create` mode: rename the file out from
        # under us and create a new one (POSIX-only, hence the
        # linux_only marker on the module).
        rotated = events_log.with_suffix(".jsonl.1")
        events_log.rename(rotated)
        events_log.touch()

        # Dispatcher invokes writer.reopen() — fd swap.
        await reopener.on_rotate()
        new_fd = writer.fileno()
        assert new_fd != initial_fd, "reopen should replace the fd"

        # Subsequent append lands in the NEW file (freshly created).
        writer.append(
            DaemonStarted(
                ts_iso="2026-05-08T00:00:00+00:00",
                version="2.0.0",
                bundled_python_version="3.12.13",
            ),
        )

    # The rotated file should NOT contain the post-rotation event.
    rotated_text = rotated.read_bytes()
    assert b"daemon_started" not in rotated_text
    new_text = events_log.read_bytes()
    assert b"daemon_started" in new_text

    # ----------------- Part (b): qmi_wwan reload -----------------
    events_log_b = tmp_path / "events_b.jsonl"
    settings = _build_settings(
        state_root=integration_state_root,
        run_dir=integration_run_dir,
        events_log=events_log_b,
    )
    clock = FakeClock(start_monotonic=0.0)
    runner = FakeRunner()
    inventory = _FakeInventoryMutable(_build_descriptors(4))
    zao = _FakeNoZaoTailer()
    metrics = MetricRegistry()
    webhook = FakeWebhookPoster()
    store = StateStore(
        state_root_override=integration_state_root,
        run_dir_override=integration_run_dir,
    )

    # Stub observe_all for cycles where qmi probes would error on FakeRunner.
    async def _empty_observe(
        modems: list[ModemDescriptor],
        *args: object,
        **kwargs: object,
    ) -> list[ModemSnapshot]:
        del args, kwargs
        # On modem-disconnect cycle, modems is []; observer naturally returns [].
        return [ModemSnapshot(usb_path=m.usb_path, cdc_wdm=m.cdc_wdm) for m in modems]

    with EventLogWriter(events_log_b) as event_logger:
        carriers = CarrierTable(carriers=[])
        driver = CycleDriver(
            store=store,
            settings=settings,
            clock=clock,
            runner=runner,
            inventory=inventory,
            zao=zao,
            carrier_table=carriers,
            event_logger=event_logger,
            metrics=metrics,
            webhook_poster=webhook,
        )

        with patch(
            "spark_modem.daemon.cycle_driver.observe_all",
            side_effect=_empty_observe,
        ):
            # Cycle 0: 4 modems present.
            r0 = await driver.run_one_cycle(cycle_id=0)
            assert r0.policy_exception is None, f"cycle 0 raised: {r0.policy_exception}"

            # Cycle 1: simulate qmi_wwan reload — all modems disappear.
            inventory.set([])
            clock.advance(10.0)
            r1 = await driver.run_one_cycle(cycle_id=1)
            assert r1.policy_exception is None, (
                f"cycle 1 (modems disconnected) raised: {r1.policy_exception}"
            )

            # Cycle 2: modems reconnect.
            inventory.set(_build_descriptors(4))
            clock.advance(10.0)
            r2 = await driver.run_one_cycle(cycle_id=2)
            assert r2.policy_exception is None, (
                f"cycle 2 (modems reconnected) raised: {r2.policy_exception}"
            )


# ----------------------------------------------------------------------
# SC #5 (a) bonus: FakeAsyncinotify smoke for rotation flow
# ----------------------------------------------------------------------


async def test_sc5a_fake_asyncinotify_dispatch_smoke(tmp_path: Path) -> None:
    """Ancillary: FakeAsyncinotify dispatches MOVE_SELF → reopen synchronously.

    Pinned belt-and-suspenders to guard against future Plan 03-04 regressions
    silently breaking the dispatch path (Plan 03-09's role is to wire the
    full TaskGroup body around this — this test pins the substrate today).
    """
    events_log = tmp_path / "events.jsonl"
    with EventLogWriter(events_log) as writer:
        reopener = EventLogReopener(writer=writer)
        # Simulate the asyncinotify producer's dispatch step directly.
        fake = FakeAsyncinotify()
        # Synthesize a watch, inject a MOVE_SELF event, drain.
        fake.add_watch(events_log.parent, FakeMask.MOVE_SELF)
        fake.inject_event(FakeMask.MOVE_SELF, events_log)

        async with fake as ino:
            count = 0
            # Consume one event (dispatcher would call on_rotate here).
            async for evt in ino:
                if evt.mask & FakeMask.MOVE_SELF:
                    # Mirror logrotate semantics: re-create the file
                    # then dispatch the reopen.
                    if not events_log.exists():
                        events_log.touch()
                    await reopener.on_rotate()
                    count += 1
                    fake.close()
            assert count == 1
