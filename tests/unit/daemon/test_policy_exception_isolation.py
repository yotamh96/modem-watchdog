"""NFR-11: a policy exception MUST NOT crash the cycle.

The cycle driver wraps ``policy.engine.run_cycle`` in a try/except
that logs the exception, sets ``RunCycleResult.policy_exception``,
and continues — status.json is still written, the daemon is still
ready for the next cycle.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

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


async def test_policy_exception_does_not_crash_cycle_status_still_written(
    tmp_path: Path,
    metrics: tuple[MetricRegistry, CollectorRegistry],
    store: StateStore,
) -> None:
    """NFR-11: monkeypatched policy raises → driver returns; status.json exists."""
    runner = FakeRunner()
    for cdc in ("cdc-wdm0", "cdc-wdm1", "cdc-wdm2", "cdc-wdm3"):
        _register_healthy(runner, cdc)

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
        metrics=metrics[0],
    )

    def _raise(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise RuntimeError("boom")

    try:
        with patch(
            "spark_modem.daemon.cycle_driver.policy_engine.run_cycle",
            new=_raise,
        ):
            result = await driver.run_one_cycle(cycle_id=0)
    finally:
        event_logger.close()

    # Driver returned without raising.
    assert result.policy_exception is not None
    assert "boom" in result.policy_exception

    # status.json STILL written.
    status_path = Path(settings.state_root) / "status.json"
    assert status_path.exists(), "status.json must be written even on policy crash"
