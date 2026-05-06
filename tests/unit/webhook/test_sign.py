"""Tests for webhook.sign — HMAC over raw payload bytes (PITFALLS §10.5)."""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

import pytest

from spark_modem.webhook.sign import sign_envelope, verify_signature
from spark_modem.wire.enums import ActionKind
from spark_modem.wire.webhook import (
    HealthyToDegraded,
    RecoveringToExhausted,
    WebhookEnvelope,
    WebhookPayloadAdapter,
)

_SECRET = b"super-secret-hmac-key"
_TS = 1700000000


def _make_envelope(*, reason: str = "qmi_timeout") -> WebhookEnvelope:
    payload = HealthyToDegraded(
        ts_iso="2026-05-06T12:00:00+00:00",
        modem_usb_path="2-3.1.1",
        prior_state="healthy",
        new_state="degraded",
        reason=reason,
    )
    return WebhookEnvelope(payload=payload)


def test_sign_envelope_signs_raw_payload_bytes() -> None:
    """The signature must verify against the payload bytes returned by sign_envelope."""
    env = _make_envelope()
    body, sig_header, ts_header = sign_envelope(env, _SECRET, ts_unix=_TS)

    # Verifies — same secret, same body bytes.
    assert verify_signature(body, sig_header, _SECRET) is True

    # body MUST equal what the WebhookPayloadAdapter would emit (raw bytes
    # over the wire).
    assert body == WebhookPayloadAdapter.dump_json(env.payload)
    assert ts_header == str(_TS)


def test_signature_changes_when_payload_changes() -> None:
    """Different payloads must produce different signatures."""
    env_a = _make_envelope(reason="qmi_timeout")
    env_b = _make_envelope(reason="not_registered_searching")
    _, sig_a, _ = sign_envelope(env_a, _SECRET, ts_unix=_TS)
    _, sig_b, _ = sign_envelope(env_b, _SECRET, ts_unix=_TS)
    assert sig_a != sig_b


def test_signature_format_is_sha256_hex() -> None:
    """Header value is exactly ``sha256=<64 lowercase hex chars>``."""
    env = _make_envelope()
    _, sig_header, _ = sign_envelope(env, _SECRET, ts_unix=_TS)

    assert sig_header.startswith("sha256=")
    hex_part = sig_header[len("sha256=") :]
    assert len(hex_part) == 64
    int(hex_part, 16)  # raises ValueError if not hex


def test_verify_returns_false_on_wrong_secret() -> None:
    """Verifying with a different secret must NOT pass."""
    env = _make_envelope()
    body, sig_header, _ = sign_envelope(env, _SECRET, ts_unix=_TS)
    assert verify_signature(body, sig_header, b"different-secret") is False


def test_verify_returns_false_on_tampered_body() -> None:
    """Even one byte changed in the body must invalidate the signature."""
    env = _make_envelope()
    body, sig_header, _ = sign_envelope(env, _SECRET, ts_unix=_TS)
    tampered = body.replace(b"qmi_timeout", b"injected!!!")
    assert tampered != body
    assert verify_signature(tampered, sig_header, _SECRET) is False


def test_verify_rejects_signature_without_sha256_prefix() -> None:
    """Header values without the algorithm prefix must be rejected."""
    env = _make_envelope()
    body, sig_header, _ = sign_envelope(env, _SECRET, ts_unix=_TS)
    bare_hex = sig_header[len("sha256=") :]
    assert verify_signature(body, bare_hex, _SECRET) is False
    assert verify_signature(body, "md5=" + bare_hex, _SECRET) is False


def test_compare_digest_used_for_verification() -> None:
    """Source must use ``hmac.compare_digest`` for timing-safe comparison."""
    sign_path = Path(__file__).resolve().parents[3] / "src" / "spark_modem" / "webhook" / "sign.py"
    source = sign_path.read_text(encoding="utf-8")
    assert "hmac.compare_digest" in source


def test_sign_does_not_mutate_envelope() -> None:
    """sign_envelope must not mutate the envelope's signature/timestamp fields.

    BaseWire is frozen, but verify the contract end-to-end.
    """
    env = _make_envelope()
    sign_envelope(env, _SECRET, ts_unix=_TS)
    assert env.signature_header_value == ""
    assert env.timestamp_header_value == ""


def test_sign_envelope_works_for_recovering_to_exhausted_variant() -> None:
    """All discriminated-union variants must produce verifiable signatures."""
    payload = RecoveringToExhausted(
        ts_iso="2026-05-06T12:30:00+00:00",
        modem_usb_path="2-3.1.2",
        action_chain=[ActionKind.SOFT_RESET, ActionKind.MODEM_RESET],
        exhaustion_reason="ladder_exhausted",
    )
    env = WebhookEnvelope(payload=payload)
    body, sig_header, _ = sign_envelope(env, _SECRET, ts_unix=_TS)

    assert verify_signature(body, sig_header, _SECRET) is True


def test_payload_bytes_match_adapter_dump_json_exactly() -> None:
    """Regression guard: body bytes are produced by WebhookPayloadAdapter,
    not by re-serialising via json.dumps or model_dump_json on the envelope.
    """
    env = _make_envelope()
    body, sig_header, _ = sign_envelope(env, _SECRET, ts_unix=_TS)

    expected = WebhookPayloadAdapter.dump_json(env.payload)
    assert body == expected

    # Recompute the digest manually to anchor the contract: HMAC over the
    # exact bytes returned by sign_envelope.
    expected_hex = hmac.new(_SECRET, expected, hashlib.sha256).hexdigest()
    assert sig_header == f"sha256={expected_hex}"


@pytest.mark.parametrize("ts_unix", [0, 1, 1700000000, 9999999999])
def test_ts_header_is_string_of_int(ts_unix: int) -> None:
    """The timestamp header is the integer Unix timestamp as a string."""
    env = _make_envelope()
    _, _, ts_header = sign_envelope(env, _SECRET, ts_unix=ts_unix)
    assert ts_header == str(ts_unix)
