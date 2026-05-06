"""HMAC signing — pure / stateless.

Critical invariant (PITFALLS §10.5): sign the raw body bytes that flow on
the wire, NOT the parsed dict. Receivers verify the signature against the
same bytes; if we re-serialize after signing, the signature stops matching.

The caller MUST use the returned `payload_bytes` verbatim as the request
body. ``sign_envelope`` returns those bytes alongside the headers so the
poster can hand them straight to httpx without round-tripping through
pydantic again.
"""

from __future__ import annotations

import hashlib
import hmac

from spark_modem.wire.webhook import WebhookEnvelope, WebhookPayloadAdapter


def sign_envelope(
    envelope: WebhookEnvelope,
    secret: bytes,
    *,
    ts_unix: int,
) -> tuple[bytes, str, str]:
    """Sign the envelope's payload and return (body_bytes, sig_header, ts_header).

    body_bytes:
        Raw JSON bytes for ``envelope.payload`` produced by the discriminated-
        union TypeAdapter. The caller MUST use these bytes verbatim as the
        HTTP request body — re-serializing breaks the signature.
    sig_header:
        ``sha256=<hex>`` where ``<hex>`` is HMAC-SHA256(secret, body_bytes).
        Goes into the ``X-Spark-Signature`` header.
    ts_header:
        ``str(ts_unix)``. Goes into the ``X-Spark-Timestamp`` header for
        replay protection (ADR-0011, FR-44.2).
    """
    payload_bytes = WebhookPayloadAdapter.dump_json(envelope.payload)
    sig_hex = hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()
    return payload_bytes, f"sha256={sig_hex}", str(ts_unix)


def verify_signature(
    body_bytes: bytes,
    signature_header: str,
    secret: bytes,
) -> bool:
    """Verify a signature header against body bytes.

    Receiver-side helper, included so the same code path is exercised by
    the test suite. Uses ``hmac.compare_digest`` to avoid timing-attack
    leakage of the expected hex.

    Returns True iff ``signature_header`` is exactly ``sha256=<hex>``
    where ``<hex>`` matches HMAC-SHA256(secret, body_bytes).
    """
    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False
    expected_hex = signature_header[len(prefix) :]
    actual_hex = hmac.new(secret, body_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_hex, actual_hex)
