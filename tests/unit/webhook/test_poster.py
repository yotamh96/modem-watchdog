"""Tests for webhook.poster.WebhookPoster — queue + retry + Host-header trick."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from spark_modem.config.settings import Settings
from spark_modem.webhook.poster import WebhookPoster
from spark_modem.webhook.sign import verify_signature
from spark_modem.wire.events import Event, WebhookDropped
from spark_modem.wire.webhook import (
    HealthyToDegraded,
    WebhookEnvelope,
    WebhookPayloadAdapter,
)
from tests.fakes.clock import FakeClock
from tests.fakes.dns import FakeDNSResolver

_SECRET = b"super-secret-hmac-key"
_URL = "https://noc.example.test:443/v2/webhooks/spark"
_HOST = "noc.example.test"
_CANNED_IP = "192.0.2.7"


# ----------------------------- helpers ---------------------------------------


class _RecordingEventLogger:
    """Append-only events.jsonl stub for assertions."""

    def __init__(self) -> None:
        self.appended: list[Event] = []

    def append(self, event: Event) -> None:
        self.appended.append(event)


class _RecordingMetrics:
    """webhook_delivery_total{result} stub: list of recorded labels."""

    def __init__(self) -> None:
        self.results: list[str] = []

    def record_webhook_delivery(self, result: str) -> None:
        self.results.append(result)


class _RequestCapture:
    """Capture the last httpx.Request seen by MockTransport handlers."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []


def _make_envelope() -> WebhookEnvelope:
    payload = HealthyToDegraded(
        ts_iso="2026-05-06T12:00:00+00:00",
        modem_usb_path="2-3.1.1",
        prior_state="healthy",
        new_state="degraded",
        reason="qmi_timeout",
    )
    return WebhookEnvelope(payload=payload)


def _make_settings(*, url: str | None = _URL, max_retries: int = 3) -> Settings:
    """Settings with an explicit webhook config."""
    return Settings(
        state_root="/tmp/test-state",
        run_dir="/tmp/test-run",
        events_log_path="/tmp/events.jsonl",
        metrics_socket_path="/tmp/metrics.sock",
        carriers_yaml_path="/tmp/carriers.yaml",
        webhook_url=url,
        webhook_max_retries=max_retries,
    )


def _install_mock_transport(
    poster: WebhookPoster,
    handler: Any,
) -> None:
    """Replace ``poster._make_client`` with one that uses MockTransport.

    handler is invoked with each httpx.Request and must return an
    httpx.Response (sync or async — we wrap MockTransport accordingly).
    """

    def _factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            timeout=httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=10.0),
        )

    poster._make_client = _factory  # type: ignore[method-assign]


def _build_poster(
    *,
    url: str | None = _URL,
    max_retries: int = 3,
    canned_ip: str | None = _CANNED_IP,
    max_queue: int = 100,
    backoff_seconds: tuple[float, ...] = (1.0, 4.0, 16.0),
) -> tuple[WebhookPoster, _RecordingEventLogger, _RecordingMetrics, FakeClock, FakeDNSResolver]:
    clock = FakeClock()
    logger = _RecordingEventLogger()
    metrics = _RecordingMetrics()
    dns = FakeDNSResolver(canned_ip=canned_ip if canned_ip is not None else "0.0.0.0")
    if canned_ip is None:
        dns.set_canned_ip(None)
    poster = WebhookPoster(
        url=url,
        secret=_SECRET,
        clock=clock,
        config=_make_settings(url=url, max_retries=max_retries),
        event_logger=logger,
        metrics=metrics,
        dns_cache=dns,
        max_queue=max_queue,
        backoff_seconds=backoff_seconds,
    )
    return poster, logger, metrics, clock, dns


# ----------------------------- tests -----------------------------------------


async def test_enqueue_returns_skipped_no_url_when_url_is_none() -> None:
    """webhook_url=None: enqueue records skipped_no_url and queue stays empty."""
    poster, logger, metrics, _, _ = _build_poster(url=None)

    await poster.enqueue(_make_envelope())

    assert metrics.results == ["skipped_no_url"]
    assert poster._queue.empty()
    assert logger.appended == []


async def test_post_one_signs_request_with_hmac_header() -> None:
    """Request has X-Spark-Signature: sha256=<hex> over the raw payload bytes."""
    poster, _, metrics, _, _ = _build_poster()
    capture = _RequestCapture()

    def handler(request: httpx.Request) -> httpx.Response:
        capture.requests.append(request)
        return httpx.Response(status_code=200, json={"ok": True})

    _install_mock_transport(poster, handler)
    await poster.enqueue(_make_envelope())
    await poster.drain(budget_seconds=10.0)

    assert len(capture.requests) == 1
    req = capture.requests[0]
    sig = req.headers["X-Spark-Signature"]
    ts = req.headers["X-Spark-Timestamp"]
    assert sig.startswith("sha256=")
    assert ts.isdigit()

    # The body the poster sent must match WebhookPayloadAdapter.dump_json
    # of the envelope.payload — and the signature must verify against THAT
    # exact byte sequence (PITFALLS §10.5 / FR-44.1).
    expected_body = WebhookPayloadAdapter.dump_json(_make_envelope().payload)
    assert req.content == expected_body
    assert verify_signature(req.content, sig, _SECRET) is True

    assert "sent" in metrics.results


async def test_post_one_uses_host_header_with_cached_ip_url() -> None:
    """URL embeds the cached IP; ``Host`` header carries the original hostname."""
    poster, _, _, _, _ = _build_poster()
    capture = _RequestCapture()

    def handler(request: httpx.Request) -> httpx.Response:
        capture.requests.append(request)
        return httpx.Response(status_code=204)

    _install_mock_transport(poster, handler)
    await poster.enqueue(_make_envelope())
    await poster.drain(budget_seconds=10.0)

    assert len(capture.requests) == 1
    req = capture.requests[0]
    # URL host is the cached IP, not the original hostname.
    assert _CANNED_IP in str(req.url)
    assert _HOST not in str(req.url.host)
    # Host header carries the original hostname so TLS SNI verifies.
    assert req.headers["Host"] == _HOST


async def test_retry_with_backoff_on_5xx() -> None:
    """503 → 503 → 200 succeeds on the third attempt; metrics record both states."""
    poster, _, metrics, _, _ = _build_poster(
        max_retries=3,
        backoff_seconds=(0.0, 0.0, 0.0),  # zero-delay backoff so test runs fast
    )
    sequence: list[int] = [503, 503, 200]
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        idx = call_count["n"]
        call_count["n"] += 1
        return httpx.Response(status_code=sequence[idx])

    _install_mock_transport(poster, handler)

    # Run the poster loop in the background; advance clock as backoff elapses.
    task = asyncio.create_task(poster.run_forever())
    await poster.enqueue(_make_envelope())

    # Wait for all three attempts to flush through. With zero backoff the
    # loop should terminate well before this timeout.
    for _ in range(50):
        await asyncio.sleep(0)
        if metrics.results.count("sent") >= 1:
            break

    poster.stop()
    await asyncio.wait_for(task, timeout=2.0)

    assert call_count["n"] == 3
    assert metrics.results.count("failed") == 2
    assert metrics.results.count("sent") == 1


async def test_retry_exhausted_emits_webhook_dropped_event() -> None:
    """Persistent 500 → after 3 attempts the envelope is dropped + event emitted."""
    poster, logger, metrics, _, _ = _build_poster(
        max_retries=3,
        backoff_seconds=(0.0, 0.0, 0.0),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(status_code=500)

    _install_mock_transport(poster, handler)

    task = asyncio.create_task(poster.run_forever())
    await poster.enqueue(_make_envelope())

    for _ in range(100):
        await asyncio.sleep(0)
        if metrics.results.count("dropped") >= 1:
            break

    poster.stop()
    await asyncio.wait_for(task, timeout=2.0)

    dropped_events = [e for e in logger.appended if isinstance(e, WebhookDropped)]
    assert len(dropped_events) == 1
    ev = dropped_events[0]
    assert ev.attempts == 3
    assert ev.reason == "retry_exhausted"
    assert ev.payload_kind == "healthy_to_degraded"
    assert metrics.results.count("dropped") == 1
    assert metrics.results.count("failed") == 3


async def test_dedup_is_responsibility_of_caller_not_poster() -> None:
    """The poster accepts envelopes regardless of dedup state.

    Dedup is the cycle driver's responsibility (Plan 02-10) — the poster
    treats every enqueued envelope as a new send.
    """
    poster, _, metrics, _, _ = _build_poster()
    capture = _RequestCapture()

    def handler(request: httpx.Request) -> httpx.Response:
        capture.requests.append(request)
        return httpx.Response(status_code=200)

    _install_mock_transport(poster, handler)

    # Enqueue the same envelope shape three times; all should attempt.
    for _ in range(3):
        await poster.enqueue(_make_envelope())
    await poster.drain(budget_seconds=10.0)

    assert len(capture.requests) == 3
    assert metrics.results.count("sent") == 3


async def test_dns_failure_increments_skipped_no_dns() -> None:
    """When the resolver returns None, no HTTP attempt is made."""
    poster, logger, metrics, _, dns = _build_poster()
    dns.set_canned_ip(None)
    capture = _RequestCapture()

    def handler(request: httpx.Request) -> httpx.Response:
        capture.requests.append(request)
        return httpx.Response(status_code=200)

    _install_mock_transport(poster, handler)

    await poster.enqueue(_make_envelope())
    await poster.drain(budget_seconds=10.0)

    assert capture.requests == []
    assert "skipped_no_dns" in metrics.results
    # Drain still emits a WebhookDropped because the post failed.
    dropped = [e for e in logger.appended if isinstance(e, WebhookDropped)]
    assert any(e.reason == "drain_timeout" for e in dropped)


async def test_queue_full_emits_dropped_with_queue_full_reason() -> None:
    """maxsize=2: third enqueue records dropped + emits WebhookDropped(queue_full)."""
    poster, logger, metrics, _, _ = _build_poster(max_queue=2)

    # Don't run the consumer — fill the queue.
    await poster.enqueue(_make_envelope())
    await poster.enqueue(_make_envelope())
    assert poster._queue.qsize() == 2

    # Third enqueue must drop without blocking.
    await poster.enqueue(_make_envelope())

    dropped_events = [e for e in logger.appended if isinstance(e, WebhookDropped)]
    assert len(dropped_events) == 1
    assert dropped_events[0].reason == "queue_full"
    assert dropped_events[0].attempts == 0
    assert metrics.results.count("dropped") == 1


async def test_modem_usb_path_propagated_to_dropped_events() -> None:
    """A WebhookDropped event must carry the modem_usb_path for post-mortem."""
    poster, logger, _, _, _ = _build_poster(max_queue=1)

    await poster.enqueue(_make_envelope(), modem_usb_path="2-3.1.1")
    # Force queue-full path for a second enqueue with a different usb_path.
    await poster.enqueue(_make_envelope(), modem_usb_path="2-3.1.2")

    dropped = [e for e in logger.appended if isinstance(e, WebhookDropped)]
    assert len(dropped) == 1
    assert dropped[0].modem_usb_path == "2-3.1.2"


async def test_post_one_signs_with_correct_secret() -> None:
    """Sanity check: the request signature verifies but a wrong secret does not."""
    poster, _, _, _, _ = _build_poster()
    capture = _RequestCapture()

    def handler(request: httpx.Request) -> httpx.Response:
        capture.requests.append(request)
        return httpx.Response(status_code=200)

    _install_mock_transport(poster, handler)
    await poster.enqueue(_make_envelope())
    await poster.drain(budget_seconds=10.0)

    req = capture.requests[0]
    sig = req.headers["X-Spark-Signature"]
    assert verify_signature(req.content, sig, _SECRET) is True
    assert verify_signature(req.content, sig, b"wrong-secret") is False


async def test_url_https_default_port_round_trip() -> None:
    """An https:// URL without explicit port resolves to 443 internally."""
    url = "https://noc.example.test/v2/webhook"
    poster, _, _, _, _ = _build_poster(url=url)
    # The poster pre-parses scheme, host, port, path at construction time
    # so the run loop doesn't re-split per attempt.
    assert poster._scheme == "https"
    assert poster._host == "noc.example.test"
    assert poster._port == 443
    assert poster._path == "/v2/webhook"
