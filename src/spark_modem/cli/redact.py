"""PII redaction (C-04 / NFR-22 / NFR-22.1).

One-way and consistent: same input → same ``<redacted:<sha256[:8]>>``
across the support bundle so identity-correlation is preserved without
exporting PII. The 8-character truncation gives ~32 bits of distinct
hash space — sufficient to cross-reference within a single bundle but
not enough to enable a brute-force lookup table for the full ICCID space.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any
from urllib.parse import urlsplit

_PII_FIELDS: frozenset[str] = frozenset({"iccid", "imsi"})


def redact_pii(value: str) -> str:
    """Returns ``<redacted:<sha256[:8]>>``. Same input → same redacted form.

    Used by ``redact_iccid_imsi_in_dict`` for ICCID/IMSI fields. Suitable
    for support-bundle export where the operator can correlate the same
    identity across files (events, state, status) but cannot recover the
    underlying value.
    """
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"<redacted:{digest}>"


def redact_iccid_imsi_in_dict(obj: Any) -> Any:
    """Recursively redact ICCID/IMSI fields in a parsed JSON-like structure.

    Walks dicts and lists; replaces any string value at a key whose
    lowercase form is ``iccid`` or ``imsi`` with the redacted form.
    Other fields (numbers, bools, non-PII strings) are returned unchanged.

    Note: matching is by key-name only — values that happen to look like
    an ICCID but live under a non-PII key are NOT redacted. The support
    bundle's normalized JSON shape uses ``iccid`` / ``imsi`` consistently.
    """
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k.lower() in _PII_FIELDS and isinstance(v, str):
                out[k] = redact_pii(v)
            else:
                out[k] = redact_iccid_imsi_in_dict(v)
        return out
    if isinstance(obj, list):
        return [redact_iccid_imsi_in_dict(item) for item in obj]
    return obj


def redact_webhook_url_to_host_only(url: str) -> str:
    """Strip path/query from URL; keep ``<scheme>://<host>/`` only.

    Webhook URLs may include secret-like path/query material (route IDs,
    auth tokens accidentally embedded). The support bundle records only
    ``scheme://host/`` so support engineers can identify the receiver
    without exporting the full URL.
    """
    parts = urlsplit(url)
    if not parts.netloc:
        return url
    return f"{parts.scheme}://{parts.netloc}/"


# ---- raw qmicli stdout redaction (Phase 5 X-02) ----------------------

# Match ``ICCID: '<digits>'``, ``UIM ID: '<digits>'``, ``IMSI: '<digits>'``,
# ``IPv4 address: '<dotted>'``. Captured groups: (label-prefix-with-colon-and-quote,
# value, closing-quote). Replacement preserves the prefix and closing quote so
# consumers of the captured fixture can still read the line shape; only the
# value is replaced with the ``<redacted:<sha256[:8]>>`` sentinel.
#
# ``UIM ID`` is included alongside ``ICCID`` because real qmicli uim_get_card_status
# stdout carries the ICCID value under both labels (Rule 2 — missing critical PII
# coverage; same identity in two places of the same stdout would otherwise leak).
_RAW_QMICLI_PII_PATTERNS: tuple[re.Pattern[bytes], ...] = (
    re.compile(rb"(ICCID:\s*')([^']+)(')"),
    re.compile(rb"(UIM ID:\s*')([^']+)(')"),
    re.compile(rb"(IMSI:\s*')([^']+)(')"),
    re.compile(rb"(IPv4 address:\s*')([^']+)(')"),
)


def redact_pii_from_raw_qmicli(stdout: bytes) -> bytes:
    """Redact ICCID / IMSI / IPv4 values from raw qmicli stdout.

    Returns bytes with every matched value replaced by
    ``<redacted:<sha256[:8]>>`` (the same sentinel shape ``redact_pii``
    produces). Determinism is preserved: same input → same output;
    the same ICCID value appearing twice in one stdout becomes the
    same redacted form so cross-file identity correlation survives.

    Phase 5 X-02 / CONTEXT.md: applied at capture time to every raw
    qmicli output written under
    ``tests/fixtures/fleet/<box-id>/qmi/<usb_path>/<verb>.txt``.

    Lines without a matching pattern are returned byte-identical (the
    captured fixture text remains useful to operators reading it).
    """

    def _sub(m: re.Match[bytes]) -> bytes:
        value = m.group(2).decode("utf-8", errors="replace")
        redacted = redact_pii(value).encode("utf-8")
        return m.group(1) + redacted + m.group(3)

    out = stdout
    for pat in _RAW_QMICLI_PII_PATTERNS:
        out = pat.sub(_sub, out)
    return out
