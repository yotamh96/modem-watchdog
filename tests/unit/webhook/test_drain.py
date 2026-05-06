"""Tests for WebhookPoster.drain() — pre-exit best-effort flush (W-01)."""

from __future__ import annotations

from typing import Any

import httpx

from spark_modem.config.settings import Settings
from spark_modem.webhook.poster import WebhookPoster
from spark_modem.wire.events import Event, WebhookDropped
from spark_modem.wire.webhook import HealthyToDegraded, WebhookEnvelope
from tests.fakes.clock import FakeClock
from tests.fakes.dns import FakeDNSResolver

_SECRET = b"super-secret-hmac-key"
_URL = "https://noc.example.test:443/v2/webhooks/spark"
_CANNED_IP = "192.0.2.7"


class _RecordingEventLogger:
    def __init__(self) -> None:
        self.appended: list[Event] = []

    def append(self, event: Event) -> None:
        self.appended.append(event)


class _RecordingMetrics:
    def __init__(self) -> None:
        self.results: list[str] = []

    def record_webhook_delivery(self, result: str) -> None:
        self.results.append(result)


def _make_envelope() -> WebhookEnvelope:
    payload = HealthyToDegraded(
        ts_iso="2026-05-06T12:00:00+00:00",
        modem_usb_path="2-3.1.1",
        prior_state="healthy",
        new_state="degraded",
        reason="qmi_timeout",
    )
    return WebhookEnvelope(payload=payload)


def _make_settings() -> Settings:
    return Settings(
        state_root="/tmp/test-state",
        run_dir="/tmp/test-run",
        events_log_path="/tmp/events.jsonl",
        metrics_socket_path="/tmp/metrics.sock",
        carriers_yaml_path="/tmp/carriers.yaml",
        webhook_url=_URL,
        webhook_max_retries=3,
    )


def _install_mock_transport(poster: WebhookPoster, handler: Any) -> None:
    def _factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            timeout=httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=10.0),
        )

    poster._make_client = _factory  # type: ignore[method-assign]


def _build_poster() -> tuple[
    WebhookPoster, _RecordingEventLogger, _RecordingMetrics, FakeClock, FakeDNSResolver
]:
    clock = FakeClock()
    logger = _RecordingEventLogger()
    metrics = _RecordingMetrics()
    dns = FakeDNSResolver(canned_ip=_CANNED_IP)
    poster = WebhookPoster(
        url=_URL,
        secret=_SECRET,
        clock=clock,
        config=_make_settings(),
        event_logger=logger,
        metrics=metrics,
        dns_cache=dns,
    )
    return poster, logger, metrics, clock, dns


async def test_drain_attempts_each_queued_item_once() -> None:
    """Three queued items + 200 handler → 3 attempts, 3 'sent' results."""
    poster, _, metrics, _, _ = _build_poster()
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        call_count["n"] += 1
        return httpx.Response(status_code=200)

    _install_mock_transport(poster, handler)

    for _ in range(3):
        await poster.enqueue(_make_envelope())
    await poster.drain(budget_seconds=10.0)

    assert call_count["n"] == 3
    assert metrics.results.count("sent") == 3
    assert metrics.results.count("dropped") == 0


async def test_drain_failure_emits_drain_timeout_dropped() -> None:
    """500 response within drain → WebhookDropped(reason='drain_timeout')."""
    poster, logger, metrics, _, _ = _build_poster()

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(status_code=500)

    _install_mock_transport(poster, handler)
    await poster.enqueue(_make_envelope())
    await poster.drain(budget_seconds=10.0)

    dropped = [e for e in logger.appended if isinstance(e, WebhookDropped)]
    assert len(dropped) == 1
    assert dropped[0].reason == "drain_timeout"
    assert metrics.results.count("dropped") == 1


async def test_drain_budget_exhausted_drops_remaining() -> None:
    """Slow attempts exhaust the budget; remaining items get drain_budget_exhausted.

    Drives time via a step-clock that the handler advances by 1.5 s per call.
    Budget = 2.0 s. With three items queued, only the FIRST attempt fits
    inside the budget (after it, t=1.5 < 2.0; the second attempt starts at
    t=1.5 and bumps t to 3.0; the post-budget cleanup loop then sweeps the
    third item with reason='drain_budget_exhausted').

    Real-time ``asyncio.sleep`` is avoided — both for hermeticity and so
    the test runs in <1 s (M7).
    """

    class _StepClock:
        def __init__(self) -> None:
            self._t = 0.0

        def monotonic(self) -> float:
            return self._t

        def wall_clock_iso(self) -> str:
            return "2026-05-06T12:00:00+00:00"

        def advance(self, seconds: float) -> None:
            self._t += seconds

    clock = _StepClock()
    logger = _RecordingEventLogger()
    metrics = _RecordingMetrics()
    dns = FakeDNSResolver(canned_ip=_CANNED_IP)
    poster = WebhookPoster(
        url=_URL,
        secret=_SECRET,
        clock=clock,
        config=_make_settings(),
        event_logger=logger,
        metrics=metrics,
        dns_cache=dns,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        # Advance the (mocked) wall-clock budget by 1.5 s per "slow" attempt.
        clock.advance(1.5)
        return httpx.Response(status_code=200)

    _install_mock_transport(poster, handler)
    for _ in range(3):
        await poster.enqueue(_make_envelope())

    await poster.drain(budget_seconds=2.0)

    dropped = [e for e in logger.appended if isinstance(e, WebhookDropped)]
    budget_exhausted = [e for e in dropped if e.reason == "drain_budget_exhausted"]
    # At least one remaining item must be flagged drain_budget_exhausted.
    assert len(budget_exhausted) >= 1
    # Sanity: at least one item DID complete before the budget expired.
    assert metrics.results.count("sent") >= 1


async def test_drain_no_op_on_empty_queue() -> None:
    """No queued items: drain returns immediately, no metrics, no events."""
    poster, logger, metrics, _, _ = _build_poster()

    await poster.drain(budget_seconds=3.0)

    assert metrics.results == []
    assert logger.appended == []


async def test_drain_marks_poster_stopped() -> None:
    """drain() must set the stopped flag so any background run loop exits."""
    poster, _, _, _, _ = _build_poster()

    assert not poster._stopped.is_set()
    await poster.drain(budget_seconds=1.0)
    assert poster._stopped.is_set()
