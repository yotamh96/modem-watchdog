"""WebhookPoster — bounded asyncio.Queue + retry loop + drain (Plan 02-08).

The poster runs in a SEPARATE asyncio task so the cycle never blocks on
webhook I/O (FR-44.8). It uses ``httpx`` with the Host-header DNS trick
(W-02 / ADR-0011): the request URL embeds the cached IP so the connection
never blocks on resolver state, while the ``Host`` header carries the
original hostname so TLS SNI verifies correctly.

Pre-exit drain (W-01): on shutdown, the daemon calls
``await poster.drain(budget_seconds=3.0)``; the poster does ONE attempt
per queued item within the budget, no retries. Items not delivered when
the budget expires emit ``WebhookDropped`` events for post-mortem
reconstruction.

Metrics labels (ADR-0013, O-04):
  - ``sent``                — successful 2xx response.
  - ``failed``              — non-2xx response or transport error.
  - ``dropped``             — retry-exhausted / queue-full / drain-budget.
  - ``skipped_no_url``      — config has no webhook_url.
  - ``skipped_no_dns``      — DnsCache returned None.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from spark_modem.config.settings import Settings
from spark_modem.webhook.dns import DnsCache
from spark_modem.webhook.sign import sign_envelope
from spark_modem.wire.events import Event, WebhookDropped
from spark_modem.wire.webhook import WebhookEnvelope

logger = logging.getLogger(__name__)

_DEFAULT_BACKOFF_SECONDS: tuple[float, ...] = (1.0, 4.0, 16.0)
_DEFAULT_QUEUE_SIZE = 100

# 2xx range for HTTP success; lifted out of the inline check so ruff PLR2004
# doesn't flag literal magic numbers and so the boundary is named at one site.
_HTTP_OK_LOW = 200
_HTTP_OK_HIGH = 300


class ClockProto(Protocol):
    """Monotonic + wall-clock surface (matches FakeClock and clock module).

    ``unix_seconds()`` returns Unix wall-clock seconds (``int(time.time())``)
    for the ``X-Spark-Timestamp`` replay-protection header (ADR-0011 /
    FR-44.2).  ``monotonic()`` is reserved for durations and backoffs per
    CLAUDE.md invariant #4 — never used for a wire-format timestamp.
    """

    def monotonic(self) -> float: ...
    def wall_clock_iso(self) -> str: ...
    def unix_seconds(self) -> int: ...


class EventLogWriterProto(Protocol):
    """Append-only events.jsonl surface used for WebhookDropped lines."""

    def append(self, event: Event) -> None: ...


class MetricRegistryProto(Protocol):
    """Prom counter increment surface for webhook_delivery_total{result}."""

    def record_webhook_delivery(self, result: str) -> None: ...


class DnsCacheProto(Protocol):
    """Async resolver surface — implemented by DnsCache and FakeDNSResolver."""

    async def resolve(self, host: str) -> str | None: ...


@dataclass(slots=True)
class _QueuedItem:
    envelope: WebhookEnvelope
    modem_usb_path: str | None
    attempts_left: int
    next_retry_monotonic: float


class WebhookPoster:
    """Bounded queue + retry loop + drain for HMAC-signed webhook POSTs."""

    def __init__(
        self,
        *,
        url: str | None,
        secret: bytes,
        clock: ClockProto,
        config: Settings,
        event_logger: EventLogWriterProto,
        metrics: MetricRegistryProto,
        dns_cache: DnsCacheProto | None = None,
        max_queue: int = _DEFAULT_QUEUE_SIZE,
        backoff_seconds: tuple[float, ...] = _DEFAULT_BACKOFF_SECONDS,
    ) -> None:
        self._url = url
        self._secret = secret
        self._clock = clock
        self._config = config
        self._event_logger = event_logger
        self._metrics = metrics
        # Default DnsCache wires in the real getaddrinfo path; tests inject
        # FakeDNSResolver via dns_cache=. ClockProto satisfies DnsCache's
        # ClockProto subset (only .monotonic() is required).
        self._dns_cache: DnsCacheProto = (
            dns_cache if dns_cache is not None else DnsCache(clock=clock)
        )
        self._queue: asyncio.Queue[_QueuedItem] = asyncio.Queue(maxsize=max_queue)
        self._backoff = backoff_seconds
        self._stopped = asyncio.Event()
        # Pre-parse URL once so the run loop does not re-split per attempt.
        if url is not None:
            parts = urlsplit(url)
            self._host = parts.hostname or ""
            self._port = parts.port or (443 if parts.scheme == "https" else 80)
            self._path = parts.path or "/"
            self._scheme = parts.scheme
        else:
            self._host = ""
            self._port = 0
            self._path = ""
            self._scheme = ""

    # -------- producer side (called from the cycle driver) --------

    async def enqueue(
        self,
        envelope: WebhookEnvelope,
        *,
        modem_usb_path: str | None = None,
    ) -> None:
        """Enqueue an envelope for background delivery.

        Non-blocking: if the queue is full, increments
        ``webhook_delivery_total{result="dropped"}`` and emits a
        ``WebhookDropped`` event with ``reason="queue_full"``. Never raises;
        the cycle driver must not be derailed by webhook backpressure.
        """
        if self._url is None:
            self._metrics.record_webhook_delivery("skipped_no_url")
            return
        item = _QueuedItem(
            envelope=envelope,
            modem_usb_path=modem_usb_path,
            attempts_left=self._config.webhook_max_retries,
            next_retry_monotonic=self._clock.monotonic(),
        )
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            self._metrics.record_webhook_delivery("dropped")
            self._event_logger.append(
                WebhookDropped(
                    ts_iso=self._clock.wall_clock_iso(),
                    modem_usb_path=modem_usb_path,
                    payload_kind=envelope.payload.kind,
                    attempts=0,
                    reason="queue_full",
                )
            )

    # -------- consumer side (run as a separate asyncio task) --------

    async def run_forever(self) -> None:
        """Background delivery loop — never blocks the cycle.

        Polls the queue with a 0.5s timeout so ``stop()`` (Phase 3 SIGTERM)
        can preempt the loop without leaking a hung get().
        """
        while not self._stopped.is_set():
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except TimeoutError:
                continue
            await self._attempt_or_requeue(item)

    def stop(self) -> None:
        """Mark the poster as stopped (Phase 3 SIGTERM hook)."""
        self._stopped.set()

    async def _attempt_or_requeue(self, item: _QueuedItem) -> None:
        now = self._clock.monotonic()
        if now < item.next_retry_monotonic:
            await asyncio.sleep(max(0.0, item.next_retry_monotonic - now))
        success = await self._post_one(item.envelope, item.modem_usb_path)
        if success:
            self._metrics.record_webhook_delivery("sent")
            return
        item.attempts_left -= 1
        if item.attempts_left <= 0:
            self._metrics.record_webhook_delivery("dropped")
            self._event_logger.append(
                WebhookDropped(
                    ts_iso=self._clock.wall_clock_iso(),
                    modem_usb_path=item.modem_usb_path,
                    payload_kind=item.envelope.payload.kind,
                    attempts=self._config.webhook_max_retries,
                    reason="retry_exhausted",
                )
            )
            return
        attempt_index = self._config.webhook_max_retries - item.attempts_left - 1
        delay = self._backoff[min(attempt_index, len(self._backoff) - 1)]
        item.next_retry_monotonic = self._clock.monotonic() + delay
        await self._queue.put(item)

    def _make_client(self) -> httpx.AsyncClient:
        """Build the AsyncClient used for one attempt.

        Extracted as a method so tests can monkeypatch the transport with
        ``httpx.MockTransport`` without intercepting global httpx state.
        """
        return httpx.AsyncClient(
            transport=httpx.AsyncHTTPTransport(retries=0),
            timeout=httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=10.0),
            verify=True,
        )

    async def _post_one(
        self,
        envelope: WebhookEnvelope,
        modem_usb_path: str | None,
    ) -> bool:
        """Send one POST attempt; returns True on 2xx, False otherwise.

        Implements the Host-header DNS trick: URL has the cached IP, the
        ``Host`` header carries the original hostname so TLS SNI matches the
        certificate. Resolves DNS via the injected DnsCache (W-02).
        """
        del modem_usb_path  # only used by callers for WebhookDropped logging
        if self._url is None:
            self._metrics.record_webhook_delivery("skipped_no_url")
            return False
        ip = await self._dns_cache.resolve(self._host)
        if ip is None:
            self._metrics.record_webhook_delivery("skipped_no_dns")
            return False
        # FR-44.2 / ADR-0011: X-Spark-Timestamp is Unix wall-clock seconds
        # (the receiver compares it against time.time() to enforce a replay
        # window).  CLAUDE.md invariant #4: monotonic() is for durations,
        # NOT wire-format timestamps — use unix_seconds() here.
        ts_unix = self._clock.unix_seconds()
        body, sig_header, ts_header = sign_envelope(
            envelope,
            self._secret,
            ts_unix=ts_unix,
        )
        url_for_request = f"{self._scheme}://{ip}:{self._port}{self._path}"
        headers = {
            "Host": self._host,
            "Content-Type": "application/json",
            "X-Spark-Signature": sig_header,
            "X-Spark-Timestamp": ts_header,
        }
        try:
            async with self._make_client() as client:
                response = await client.post(
                    url_for_request,
                    content=body,
                    headers=headers,
                )
            if _HTTP_OK_LOW <= response.status_code < _HTTP_OK_HIGH:
                return True
            logger.warning("webhook non-2xx: %s", response.status_code)
            self._metrics.record_webhook_delivery("failed")
            return False
        except httpx.HTTPError:
            logger.warning("webhook http error", exc_info=True)
            self._metrics.record_webhook_delivery("failed")
            return False

    # -------- shutdown --------

    async def drain(self, *, budget_seconds: float = 3.0) -> None:
        """Pre-exit best-effort drain (W-01) — ONE attempt per queued item.

        Stops the run loop and tries to flush the queue within
        ``budget_seconds``. Items that fail their single attempt or that
        remain when the budget expires emit ``WebhookDropped`` events with
        ``reason="drain_timeout"`` / ``"drain_budget_exhausted"``.

        WR-03 (Phase 2 review) — drain INTENTIONALLY ignores
        ``next_retry_monotonic`` on each item.  W-01 promises ONE attempt
        per queued item within budget; honouring per-item backoff would
        either (a) waste the budget on ``asyncio.sleep`` when the daemon
        is already shutting down, or (b) requeue items that would then
        fail the budget check on their second pop.  The drain is a
        best-effort flush, not a retry loop — the receiver is expected to
        be idempotent across post-shutdown deliveries (NFR-22 §"webhook
        receiver idempotency contract").  If the receiver rejects an
        in-backoff retry inside its anti-spam window, the item still
        emits a ``WebhookDropped`` event so post-mortem replay sees it.
        """
        self._stopped.set()
        deadline = self._clock.monotonic() + budget_seconds
        while not self._queue.empty() and self._clock.monotonic() < deadline:
            item = self._queue.get_nowait()
            success = await self._post_one(item.envelope, item.modem_usb_path)
            if success:
                self._metrics.record_webhook_delivery("sent")
            else:
                self._metrics.record_webhook_delivery("dropped")
                self._event_logger.append(
                    WebhookDropped(
                        ts_iso=self._clock.wall_clock_iso(),
                        modem_usb_path=item.modem_usb_path,
                        payload_kind=item.envelope.payload.kind,
                        attempts=self._config.webhook_max_retries - item.attempts_left,
                        reason="drain_timeout",
                    )
                )
        # Anything remaining when the budget expired:
        while not self._queue.empty():
            item = self._queue.get_nowait()
            self._metrics.record_webhook_delivery("dropped")
            self._event_logger.append(
                WebhookDropped(
                    ts_iso=self._clock.wall_clock_iso(),
                    modem_usb_path=item.modem_usb_path,
                    payload_kind=item.envelope.payload.kind,
                    attempts=self._config.webhook_max_retries - item.attempts_left,
                    reason="drain_budget_exhausted",
                )
            )
