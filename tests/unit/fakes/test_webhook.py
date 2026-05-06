"""Tests for tests.fakes.webhook.FakeWebhookPoster."""

from __future__ import annotations

from spark_modem.wire.webhook import HealthyToDegraded, WebhookEnvelope
from tests.fakes.webhook import FakeWebhookPoster


def _make_envelope(usb_path: str = "2-3.1.1") -> WebhookEnvelope:
    payload = HealthyToDegraded(
        ts_iso="2026-01-01T00:00:00+00:00",
        modem_usb_path=usb_path,
        prior_state="healthy",
        new_state="degraded",
        reason="test",
    )
    return WebhookEnvelope(payload=payload)


async def test_enqueue_records_envelope_in_sent() -> None:
    poster = FakeWebhookPoster()
    env = _make_envelope()
    await poster.enqueue(env)
    assert poster.sent == [env]
    assert poster.dropped == []


async def test_enqueue_preserves_order_across_calls() -> None:
    poster = FakeWebhookPoster()
    e1 = _make_envelope("2-3.1.1")
    e2 = _make_envelope("2-3.1.2")
    e3 = _make_envelope("2-3.1.3")
    await poster.enqueue(e1)
    await poster.enqueue(e2)
    await poster.enqueue(e3)
    assert [e.payload.modem_usb_path for e in poster.sent] == [  # type: ignore[union-attr]
        "2-3.1.1",
        "2-3.1.2",
        "2-3.1.3",
    ]


async def test_drain_is_noop() -> None:
    poster = FakeWebhookPoster()
    env = _make_envelope()
    await poster.enqueue(env)
    await poster.drain(budget_seconds=3.0)
    # Drain in the fake never moves items to dropped or removes from sent.
    assert poster.sent == [env]
    assert poster.dropped == []
