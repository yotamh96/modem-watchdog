"""Performance + concurrency tests for the cycle driver.

NFR-1: P99 cycle ≤ 10s on the production hardware.  Phase 2 measures
on a developer laptop with FakeRunner-canned qmicli output; the budget
is much tighter (< 1s per cycle) because no real subprocess spawn,
no real I/O.

NFR-11 + observer concurrency: a single hung probe must not stall the
whole cycle — the observer's per-task asyncio.timeout cancels it; the
cycle continues with the remaining snapshots.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from prometheus_client.registry import CollectorRegistry

from spark_modem.config.settings import Settings
from spark_modem.daemon.cycle_driver import CycleDriver
from spark_modem.event_logger.writer import EventLogWriter
from spark_modem.state_store.store import StateStore
from spark_modem.status_reporter.metrics_registry import MetricRegistry
from spark_modem.subproc.result import CompletedProcess
from spark_modem.wire.carriers import CarrierTable
from tests.fakes.clock import FakeClock
from tests.fakes.inventory import FixtureInventory
from tests.fakes.runner import FakeRunner
from tests.fakes.zao_log import FixtureZaoTailer

_FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures"
_QMI_FIXTURES = _FIXTURES_ROOT / "qmicli"
_INVENTORY_FIXTURE = _FIXTURES_ROOT / "inventory" / "four_modems.json"


def _read_qmi(intent: str, scenario: str, version: str = "1.30") -> bytes:
    return (_QMI_FIXTURES / intent / version / f"{scenario}.txt").read_bytes()


def _ok(argv: list[str], stdout: bytes) -> CompletedProcess:
    return CompletedProcess.make(
        argv=argv,
        exit_code=0,
        stdout=stdout,
        stderr=b"",
        duration_monotonic=0.01,
        timed_out=False,
    )


def _register_healthy(runner: FakeRunner, cdc_wdm: str) -> None:
    device = f"/dev/{cdc_wdm}"
    base = ["qmicli", "--device-open-proxy", f"--device={device}"]
    fixtures: list[tuple[list[str], str, str]] = [
        ([*base, "--nas-get-signal-info"], "get_signal", "lte_strong"),
        (
            [*base, "--nas-get-serving-system"],
            "get_serving_system",
            "registered_home",
        ),
        ([*base, "--uim-get-card-status"], "get_sim_state", "ready"),
        (
            [*base, "--wds-get-packet-service-status"],
            "get_data_session",
            "connected",
        ),
        (
            [*base, "--wds-get-profile-settings=3gpp,1"],
            "get_profile_settings",
            "profile1_internet",
        ),
        (
            [*base, "--wds-get-current-settings"],
            "get_current_settings",
            "raw_ip_y",
        ),
        ([*base, "--dms-get-operating-mode"], "get_operating_mode", "online"),
    ]
    for argv, intent, scenario in fixtures:
        runner.register(argv, _ok(argv, _read_qmi(intent, scenario)))


def _settings_for(tmp_path: Path) -> Settings:
    return Settings(
        state_root=str(tmp_path / "state"),
        run_dir=str(tmp_path / "run"),
        events_log_path=str(tmp_path / "events.jsonl"),
        metrics_socket_path=str(tmp_path / "metrics.sock"),
        carriers_yaml_path=str(tmp_path / "carriers.yaml"),
    )


@pytest.fixture
def metrics() -> tuple[MetricRegistry, CollectorRegistry]:
    coll = CollectorRegistry(auto_describe=False)
    return MetricRegistry(registry=coll), coll


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[StateStore]:
    s = StateStore(
        state_root_override=tmp_path / "state",
        run_dir_override=tmp_path / "run",
    )
    yield s


def _make_driver(
    *,
    tmp_path: Path,
    runner: FakeRunner,
    metrics: MetricRegistry,
    store: StateStore,
) -> tuple[CycleDriver, EventLogWriter, Settings]:
    settings = _settings_for(tmp_path)
    clock = FakeClock(start_monotonic=1000.0)
    event_logger = EventLogWriter(settings.events_log_path)
    inventory = FixtureInventory(_INVENTORY_FIXTURE)
    zao = FixtureZaoTailer()
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
    )
    return driver, event_logger, settings


async def test_one_cycle_completes_under_one_second_with_fixtures(
    tmp_path: Path,
    metrics: tuple[MetricRegistry, CollectorRegistry],
    store: StateStore,
) -> None:
    """NFR-1: a single fixture cycle completes in well under 1s on a laptop.

    Production hardware budget is 10s P99; a developer laptop with
    fakes-only I/O comes in 100x under that.  This is the M5 measurable
    proxy.
    """
    runner = FakeRunner()
    for cdc in ("cdc-wdm0", "cdc-wdm1", "cdc-wdm2", "cdc-wdm3"):
        _register_healthy(runner, cdc)

    driver, event_logger, _settings = _make_driver(
        tmp_path=tmp_path,
        runner=runner,
        metrics=metrics[0],
        store=store,
    )
    try:
        t0 = time.monotonic()
        await driver.run_one_cycle(cycle_id=0)
        elapsed = time.monotonic() - t0
    finally:
        event_logger.close()

    # Generous laptop budget — assert well under 1s.
    assert elapsed < 1.0, f"cycle took {elapsed:.3f}s; M5 laptop budget < 1s"


class _SlowOnFirstRunner(FakeRunner):
    """Runner that hangs forever on the first modem's qmicli calls."""

    def __init__(self, hang_device: str) -> None:
        super().__init__()
        self._hang_device = hang_device

    async def run(
        self,
        argv: list[str],
        *,
        timeout_s: float,
        stdin: bytes | None = None,
        env: dict[str, str] | None = None,
    ) -> CompletedProcess:
        if any(p.startswith(f"--device={self._hang_device}") for p in argv):
            await asyncio.sleep(3600)
        return await super().run(
            argv,
            timeout_s=timeout_s,
            stdin=stdin,
            env=env,
        )


async def test_observer_concurrency_one_slow_probe_does_not_stall_cycle(
    tmp_path: Path,
    metrics: tuple[MetricRegistry, CollectorRegistry],
    store: StateStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NFR-1 + observer per-task timeout: one slow modem must not stall the cycle.

    The observer's default per-task timeout is 8s.  We replace
    ``observe_all`` in the cycle driver's namespace with a wrapper that
    forces a 50ms timeout so the test runs fast; the production code
    path (DEFAULT_PROBE_TIMEOUT_S=8.0) is exercised by the matching
    observer-suite test.  This test asserts the cycle-driver invariant:
    a single hung probe must not stall the whole cycle and the cycle
    still produces a Diag for every modem.
    """
    from spark_modem.observer import orchestrator as orch  # noqa: PLC0415

    real_observe_all = orch.observe_all

    async def _short_timeout_observe_all(
        modems: object,
        qmi_factory: object,
        zao: object,
        clock: object,
        *,
        timeout_s: float = 0.05,
    ) -> object:
        del timeout_s
        return await real_observe_all(
            modems,  # type: ignore[arg-type]
            qmi_factory,  # type: ignore[arg-type]
            zao,  # type: ignore[arg-type]
            clock,  # type: ignore[arg-type]
            timeout_s=0.05,
        )

    monkeypatch.setattr(
        "spark_modem.daemon.cycle_driver.observe_all",
        _short_timeout_observe_all,
    )

    runner = _SlowOnFirstRunner(hang_device="/dev/cdc-wdm0")
    for cdc in ("cdc-wdm1", "cdc-wdm2", "cdc-wdm3"):
        _register_healthy(runner, cdc)

    driver, event_logger, _settings = _make_driver(
        tmp_path=tmp_path,
        runner=runner,
        metrics=metrics[0],
        store=store,
    )

    try:
        t0 = time.monotonic()
        result = await driver.run_one_cycle(cycle_id=0)
        elapsed = time.monotonic() - t0
    finally:
        event_logger.close()

    # Whole cycle should complete in well under 1s -- slow probe is
    # cancelled by per-task asyncio.timeout(50ms), three siblings still
    # finish.
    assert elapsed < 2.0, (
        f"cycle took {elapsed:.3f}s; one slow probe should not stall it"
    )
    # Diag still has all 4 modems represented.
    assert len(result.diag.per_modem) == 4
