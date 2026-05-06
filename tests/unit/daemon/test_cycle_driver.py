"""Tests for CycleDriver — the integration point of every Phase 2 subsystem.

Covers:
  - run_one_cycle writes status.json (FR-41 / O-01)
  - run_one_cycle persists per-modem ModemState atomically (Phase 1 store)
  - MetricRegistry.set_modem_state called with state_to_int per modem
  - MetricRegistry.observe_cycle_duration called once per cycle
  - StateTransition events appended on state change (NFR-20)
  - Webhook envelopes (HealthyToDegraded, RecoveringToExhausted,
    ActionFailedWebhook) constructed and enqueued (SC #5)
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from prometheus_client.registry import CollectorRegistry

from spark_modem.actions.result import ActionResult
from spark_modem.config.settings import Settings
from spark_modem.daemon.cycle_driver import CycleDriver
from spark_modem.event_logger.writer import EventLogWriter
from spark_modem.inventory.descriptor import ModemDescriptor
from spark_modem.policy.result import CycleResult, StateTransition
from spark_modem.state_store.store import StateStore
from spark_modem.status_reporter.metrics_registry import MetricRegistry
from spark_modem.subproc.result import CompletedProcess
from spark_modem.wire.carriers import CarrierTable
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind
from spark_modem.wire.events import StateTransition as StateTransitionEvent
from spark_modem.wire.globals import GlobalsState
from spark_modem.wire.state import ModemState
from spark_modem.wire.status import StatusReport
from spark_modem.wire.webhook import (
    ActionFailedWebhook,
    HealthyToDegraded,
    RecoveringToExhausted,
)
from tests.fakes.clock import FakeClock
from tests.fakes.inventory import FixtureInventory
from tests.fakes.runner import FakeRunner
from tests.fakes.webhook import FakeWebhookPoster
from tests.fakes.zao_log import FixtureZaoTailer

_FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures"
_QMI_FIXTURES = _FIXTURES_ROOT / "qmicli"
_INVENTORY_FIXTURE = _FIXTURES_ROOT / "inventory" / "four_modems.json"


def _read_qmi(intent: str, scenario: str, version: str = "1.30") -> bytes:
    """Read a qmicli fixture as bytes."""
    return (_QMI_FIXTURES / intent / version / f"{scenario}.txt").read_bytes()


def _read_text(path: Path) -> str:
    """Synchronous helper -- pulled out to keep async test bodies free of
    direct ``Path.read_text`` calls (ASYNC240)."""
    return path.read_text(encoding="utf-8")


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
    """Register canned healthy qmicli responses for the seven probe queries."""
    device = f"/dev/{cdc_wdm}"
    base = ["qmicli", "--device-open-proxy", f"--device={device}"]
    fixtures: list[tuple[list[str], str, str]] = [
        ([*base, "--nas-get-signal-info"], "get_signal", "lte_strong"),
        ([*base, "--nas-get-serving-system"], "get_serving_system", "registered_home"),
        ([*base, "--uim-get-card-status"], "get_sim_state", "ready"),
        ([*base, "--wds-get-packet-service-status"], "get_data_session", "connected"),
        (
            [*base, "--wds-get-profile-settings=3gpp,1"],
            "get_profile_settings",
            "profile1_internet",
        ),
        ([*base, "--wds-get-current-settings"], "get_current_settings", "raw_ip_y"),
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
    """Per-test-isolated MetricRegistry — never touches the global REGISTRY."""
    coll = CollectorRegistry(auto_describe=False)
    return MetricRegistry(registry=coll), coll


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[StateStore]:
    """tmp_path-rooted StateStore for hermetic per-test state."""
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
    inventory_path: Path = _INVENTORY_FIXTURE,
    webhook_poster: FakeWebhookPoster | None = None,
    zao: FixtureZaoTailer | None = None,
) -> tuple[CycleDriver, FakeClock, EventLogWriter, Settings]:
    settings = _settings_for(tmp_path)
    clock = FakeClock(start_monotonic=1000.0)
    event_logger = EventLogWriter(settings.events_log_path)
    inventory = FixtureInventory(inventory_path)
    zao_tailer = zao if zao is not None else FixtureZaoTailer()
    carriers = CarrierTable(carriers=[])
    driver = CycleDriver(
        store=store,
        settings=settings,
        clock=clock,
        runner=runner,
        inventory=inventory,
        zao=zao_tailer,
        carrier_table=carriers,
        event_logger=event_logger,
        metrics=metrics,
        webhook_poster=webhook_poster,
    )
    return driver, clock, event_logger, settings


# ---------------------------------------------------------------------------
# 1. status.json written every cycle (FR-41 / O-01)
# ---------------------------------------------------------------------------


async def test_run_one_cycle_writes_status_json(
    tmp_path: Path,
    metrics: tuple[MetricRegistry, CollectorRegistry],
    store: StateStore,
) -> None:
    runner = FakeRunner()
    for cdc in ("cdc-wdm0", "cdc-wdm1", "cdc-wdm2", "cdc-wdm3"):
        _register_healthy(runner, cdc)

    driver, _clock, event_logger, settings = _make_driver(
        tmp_path=tmp_path,
        runner=runner,
        metrics=metrics[0],
        store=store,
    )
    try:
        await driver.run_one_cycle(cycle_id=0)
    finally:
        event_logger.close()

    status_path = Path(settings.state_root) / "status.json"
    assert status_path.exists(), "status.json must be written every cycle"
    raw = status_path.read_text(encoding="utf-8")
    report = StatusReport.model_validate_json(raw)
    assert report.cycle_index == 0
    assert report.summary.expected_modems == 4
    # Healthy fixtures → 4 modems classified healthy.
    assert report.summary.healthy == 4


# ---------------------------------------------------------------------------
# 2. Per-modem ModemState persisted atomically (Phase 1 StateStore)
# ---------------------------------------------------------------------------


async def test_run_one_cycle_persists_modem_states(
    tmp_path: Path,
    metrics: tuple[MetricRegistry, CollectorRegistry],
    store: StateStore,
) -> None:
    runner = FakeRunner()
    for cdc in ("cdc-wdm0", "cdc-wdm1", "cdc-wdm2", "cdc-wdm3"):
        _register_healthy(runner, cdc)

    driver, _clock, event_logger, settings = _make_driver(
        tmp_path=tmp_path,
        runner=runner,
        metrics=metrics[0],
        store=store,
    )
    try:
        await driver.run_one_cycle(cycle_id=7)
    finally:
        event_logger.close()

    # state_store/paths.state_by_usb_dir places modem state under
    # ``<state_root>/state/by-usb/`` per ADR-0009.
    state_dir = Path(settings.state_root) / "state" / "by-usb"
    expected = {
        state_dir / "2-3.1.1.json",
        state_dir / "2-3.1.2.json",
        state_dir / "2-3.1.3.json",
        state_dir / "2-3.1.4.json",
    }
    for p in expected:
        assert p.exists(), f"{p} must be persisted after one cycle"
    # All four modems should now be in 'healthy' state.
    state = ModemState.model_validate_json(
        (state_dir / "2-3.1.1.json").read_text(encoding="utf-8"),
    )
    assert state.state == "healthy"


# ---------------------------------------------------------------------------
# 3. MetricRegistry.set_modem_state called per modem with integer encoding
# ---------------------------------------------------------------------------


async def test_metrics_recorded_per_modem(
    tmp_path: Path,
    metrics: tuple[MetricRegistry, CollectorRegistry],
    store: StateStore,
) -> None:
    runner = FakeRunner()
    for cdc in ("cdc-wdm0", "cdc-wdm1", "cdc-wdm2", "cdc-wdm3"):
        _register_healthy(runner, cdc)

    driver, _clock, event_logger, _settings = _make_driver(
        tmp_path=tmp_path,
        runner=runner,
        metrics=metrics[0],
        store=store,
    )
    try:
        await driver.run_one_cycle(cycle_id=0)
    finally:
        event_logger.close()

    coll = metrics[1]
    # Collect modem_state_value gauge samples — should have one per modem.
    samples: list[tuple[dict[str, str], float]] = []
    for family in coll.collect():
        for sample in family.samples:
            if sample.name == "modem_state_value":
                samples.append((dict(sample.labels), sample.value))
    assert len(samples) == 4
    # All four are healthy → state_to_int == 1.
    for _labels, value in samples:
        assert value == 1.0


# ---------------------------------------------------------------------------
# 4. MetricRegistry.observe_cycle_duration called once per cycle
# ---------------------------------------------------------------------------


async def test_metrics_records_cycle_duration(
    tmp_path: Path,
    metrics: tuple[MetricRegistry, CollectorRegistry],
    store: StateStore,
) -> None:
    runner = FakeRunner()
    for cdc in ("cdc-wdm0", "cdc-wdm1", "cdc-wdm2", "cdc-wdm3"):
        _register_healthy(runner, cdc)

    driver, _clock, event_logger, _settings = _make_driver(
        tmp_path=tmp_path,
        runner=runner,
        metrics=metrics[0],
        store=store,
    )
    try:
        await driver.run_one_cycle(cycle_id=0)
    finally:
        event_logger.close()

    coll = metrics[1]
    # cycle_duration_seconds is a Histogram; the _count sample is incremented
    # once per ``observe()`` call.
    count = 0.0
    for family in coll.collect():
        for sample in family.samples:
            if sample.name == "cycle_duration_seconds_count":
                count = sample.value
    assert count == 1.0


# ---------------------------------------------------------------------------
# 5. StateTransition events appended on state change (NFR-20)
# ---------------------------------------------------------------------------


async def test_state_transition_events_appended_on_state_change(
    tmp_path: Path,
    metrics: tuple[MetricRegistry, CollectorRegistry],
    store: StateStore,
) -> None:
    """unknown → healthy for all 4 modems → 4 StateTransition lines in events.jsonl."""
    runner = FakeRunner()
    for cdc in ("cdc-wdm0", "cdc-wdm1", "cdc-wdm2", "cdc-wdm3"):
        _register_healthy(runner, cdc)

    driver, _clock, event_logger, settings = _make_driver(
        tmp_path=tmp_path,
        runner=runner,
        metrics=metrics[0],
        store=store,
    )
    try:
        await driver.run_one_cycle(cycle_id=0)
    finally:
        event_logger.close()

    raw = _read_text(Path(settings.events_log_path))
    transitions = [
        json.loads(line)
        for line in raw.splitlines()
        if line and json.loads(line).get("kind") == "state_transition"
    ]
    assert len(transitions) == 4
    for tr in transitions:
        assert tr["from_state"] == "unknown"
        assert tr["to_state"] == "healthy"


# ---------------------------------------------------------------------------
# 6-8. Webhook envelopes (SC #5)
# ---------------------------------------------------------------------------


def _make_one_modem_inventory(tmp_path: Path) -> Path:
    """Write a single-modem inventory fixture for webhook tests."""
    target = tmp_path / "one_modem.json"
    target.write_text(
        json.dumps(
            {
                "modems": [
                    {
                        "line": 1,
                        "cdc_wdm": "cdc-wdm0",
                        "usb_path": "2-3.1.1",
                        "ns": "line1",
                        "iface": "wwan0",
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    return target


def _patched_run_cycle_returning(
    transitions: list[StateTransition],
    new_states: dict[str, ModemState],
) -> Callable[..., CycleResult]:
    """Return a stub run_cycle that always returns the given transitions/states."""

    def _stub(
        diag: object,
        prior_states: dict[str, ModemState],
        globals_state: GlobalsState,
        ctx: object,
    ) -> CycleResult:
        del diag, prior_states, ctx
        return CycleResult(
            plans=[],
            transitions=list(transitions),
            new_states=dict(new_states),
            new_globals=globals_state,
        )

    return _stub


async def test_webhook_enqueue_on_healthy_to_degraded_transition(
    tmp_path: Path,
    metrics: tuple[MetricRegistry, CollectorRegistry],
    store: StateStore,
) -> None:
    """SC #5 gate: HealthyToDegraded webhook constructed + enqueued."""
    inventory_path = _make_one_modem_inventory(tmp_path)
    runner = FakeRunner()
    _register_healthy(runner, "cdc-wdm0")

    fake_poster = FakeWebhookPoster()
    driver, _clock, event_logger, _settings = _make_driver(
        tmp_path=tmp_path,
        runner=runner,
        metrics=metrics[0],
        store=store,
        inventory_path=inventory_path,
        webhook_poster=fake_poster,
    )

    new_state = ModemState.model_validate(
        {
            "state": "degraded",
            "present": True,
            "rf_blocked": False,
            "recovering_level": None,
            "_healthy_streak": 0,
            "counters": {},
            "last_action_monotonic": None,
            "last_state_transition_iso": None,
        },
    )
    transitions = [
        StateTransition(
            usb_path="2-3.1.1",
            from_state="healthy",
            to_state="degraded",
            cause="registration/not_registered_searching",
            new_modem_state=new_state,
        ),
    ]
    new_states = {"2-3.1.1": new_state}

    try:
        with patch(
            "spark_modem.daemon.cycle_driver.policy_engine.run_cycle",
            new=_patched_run_cycle_returning(transitions, new_states),
        ):
            await driver.run_one_cycle(cycle_id=0)
    finally:
        event_logger.close()

    assert len(fake_poster.sent) >= 1, "HealthyToDegraded must be enqueued"
    payload = fake_poster.sent[0].payload
    assert isinstance(payload, HealthyToDegraded)
    assert payload.modem_usb_path == "2-3.1.1"
    assert payload.prior_state == "healthy"
    assert payload.new_state == "degraded"


async def test_webhook_enqueue_on_recovering_to_exhausted_transition(
    tmp_path: Path,
    metrics: tuple[MetricRegistry, CollectorRegistry],
    store: StateStore,
) -> None:
    """SC #5 gate: RecoveringToExhausted webhook constructed + enqueued."""
    inventory_path = _make_one_modem_inventory(tmp_path)
    runner = FakeRunner()
    _register_healthy(runner, "cdc-wdm0")

    fake_poster = FakeWebhookPoster()
    driver, _clock, event_logger, _settings = _make_driver(
        tmp_path=tmp_path,
        runner=runner,
        metrics=metrics[0],
        store=store,
        inventory_path=inventory_path,
        webhook_poster=fake_poster,
    )

    new_state = ModemState.model_validate(
        {
            "state": "exhausted",
            "present": True,
            "rf_blocked": False,
            "recovering_level": None,
            "_healthy_streak": 0,
            "counters": {},
            "last_action_monotonic": None,
            "last_state_transition_iso": None,
        },
    )
    transitions = [
        StateTransition(
            usb_path="2-3.1.1",
            from_state="recovering",
            to_state="exhausted",
            cause="registration/not_registered_searching",
            new_modem_state=new_state,
        ),
    ]
    new_states = {"2-3.1.1": new_state}

    try:
        with patch(
            "spark_modem.daemon.cycle_driver.policy_engine.run_cycle",
            new=_patched_run_cycle_returning(transitions, new_states),
        ):
            await driver.run_one_cycle(cycle_id=0)
    finally:
        event_logger.close()

    assert len(fake_poster.sent) >= 1
    payload = fake_poster.sent[0].payload
    assert isinstance(payload, RecoveringToExhausted)
    assert payload.modem_usb_path == "2-3.1.1"
    assert payload.exhaustion_reason == "registration/not_registered_searching"


async def test_webhook_enqueue_on_action_failed(
    tmp_path: Path,
    metrics: tuple[MetricRegistry, CollectorRegistry],
    store: StateStore,
) -> None:
    """SC #5 gate: ActionFailedWebhook enqueued for any failed action.

    We can't easily produce a real failure through the fixture qmicli
    pipeline without registering a non-zero CompletedProcess; instead we
    inject the action_results list directly through a wrapped
    ``_dispatch_actions`` so the per-cycle logic exercises the webhook
    arm honestly.
    """
    inventory_path = _make_one_modem_inventory(tmp_path)
    runner = FakeRunner()
    _register_healthy(runner, "cdc-wdm0")

    fake_poster = FakeWebhookPoster()
    driver, _clock, event_logger, _settings = _make_driver(
        tmp_path=tmp_path,
        runner=runner,
        metrics=metrics[0],
        store=store,
        inventory_path=inventory_path,
        webhook_poster=fake_poster,
    )

    failed_result = ActionResult(
        kind=ActionKind.SOFT_RESET,
        who=WhoModem(usb_path="2-3.1.1", cdc_wdm="cdc-wdm0"),
        succeeded=False,
        duration_seconds=0.05,
        failure_reason="proxy_died",
    )

    async def _stub_dispatch(
        cycle_result: CycleResult,
        modems: list[ModemDescriptor],
    ) -> list[ActionResult]:
        del cycle_result, modems
        return [failed_result]

    # Force policy.run_cycle to return non-empty so cycle_result is not None.
    pretend_state = ModemState.model_validate(
        {
            "state": "healthy",
            "present": True,
            "rf_blocked": False,
            "recovering_level": None,
            "_healthy_streak": 0,
            "counters": {},
            "last_action_monotonic": None,
            "last_state_transition_iso": None,
        },
    )

    try:
        with (
            patch(
                "spark_modem.daemon.cycle_driver.policy_engine.run_cycle",
                new=_patched_run_cycle_returning([], {"2-3.1.1": pretend_state}),
            ),
            patch.object(driver, "_dispatch_actions", new=_stub_dispatch),
        ):
            await driver.run_one_cycle(cycle_id=0)
    finally:
        event_logger.close()

    assert len(fake_poster.sent) == 1
    payload = fake_poster.sent[0].payload
    assert isinstance(payload, ActionFailedWebhook)
    assert payload.modem_usb_path == "2-3.1.1"
    assert payload.action == ActionKind.SOFT_RESET
    assert payload.failure_reason == "proxy_died"


# ---------------------------------------------------------------------------
# Misc: the cycle returns even when policy short-circuits
# ---------------------------------------------------------------------------


async def test_run_one_cycle_returns_run_cycle_result(
    tmp_path: Path,
    metrics: tuple[MetricRegistry, CollectorRegistry],
    store: StateStore,
) -> None:
    runner = FakeRunner()
    for cdc in ("cdc-wdm0", "cdc-wdm1", "cdc-wdm2", "cdc-wdm3"):
        _register_healthy(runner, cdc)
    driver, _clock, event_logger, _settings = _make_driver(
        tmp_path=tmp_path,
        runner=runner,
        metrics=metrics[0],
        store=store,
    )
    try:
        result = await driver.run_one_cycle(cycle_id=3)
    finally:
        event_logger.close()
    assert result.diag.cycle_id == 3
    assert result.cycle_result is not None
    assert result.policy_exception is None


# Silence unused import warnings.
_: Any = StateTransitionEvent
