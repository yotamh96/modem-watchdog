"""FakeWebhookPoster -- records sent envelopes for test assertions.

The real `webhook/poster.py` (Plan 02-08) implements the WebhookPoster
Protocol with HMAC signing, retry queue, dedup, and pre-resolved DNS. This
fake satisfies the same call surface (`enqueue` + `drain`) but simply records
each envelope on `sent` for tests to assert on.

`dropped` is exposed so tests that simulate retry-budget exhaustion can move
items from `sent` to `dropped` manually; the fake itself never drops on its
own.
"""

from __future__ import annotations

from spark_modem.wire.webhook import WebhookEnvelope


class FakeWebhookPoster:
    """Test double for WebhookPoster: enqueue records the envelope; drain is a no-op."""

    def __init__(self) -> None:
        self.sent: list[WebhookEnvelope] = []
        self.dropped: list[WebhookEnvelope] = []

    async def enqueue(self, envelope: WebhookEnvelope) -> None:
        """Record the envelope as 'sent' (no real network I/O)."""
        self.sent.append(envelope)

    async def drain(self, *, budget_seconds: float = 3.0) -> None:
        """No-op drain: every enqueued envelope is already in `sent`."""
        del budget_seconds  # call-surface parity with the real poster
