"""Tests for spark_modem.cli.redact.redact_pii_from_raw_qmicli (Phase 5 X-02).

Companion to ``test_redact.py``; this file focuses on the raw-qmicli-stdout
helper added for the capture-fleet-fixture CLI verb (Plan 05-03 Task 1).

Redaction must be deterministic (sha256[:8]) so the same ICCID/IMSI value
yields the same ``<redacted:<hash>>`` token across files. Non-PII lines pass
through byte-identical so the captured fixture text remains useful to
operators reading it (e.g. card state, registration state).
"""

from __future__ import annotations

import re
from pathlib import Path

from spark_modem.cli.redact import redact_pii_from_raw_qmicli

_REDACTED_RE = re.compile(rb"<redacted:[0-9a-f]{8}>")


def test_iccid_redacted() -> None:
    out = redact_pii_from_raw_qmicli(b"ICCID: '8997201700123456789'\n")
    assert _REDACTED_RE.search(out) is not None
    assert b"8997201700123456789" not in out


def test_imsi_redacted() -> None:
    out = redact_pii_from_raw_qmicli(b"IMSI: '425010012345678'\n")
    assert _REDACTED_RE.search(out) is not None
    assert b"425010012345678" not in out


def test_ipv4_redacted() -> None:
    out = redact_pii_from_raw_qmicli(b"IPv4 address: '10.0.1.42'\n")
    assert _REDACTED_RE.search(out) is not None
    assert b"10.0.1.42" not in out


def test_idempotent_redaction_is_deterministic() -> None:
    body = b"ICCID: '8997201700123456789'\nIMSI: '425010012345678'\n"
    a = redact_pii_from_raw_qmicli(body)
    b = redact_pii_from_raw_qmicli(body)
    assert a == b


def test_repeated_iccid_yields_same_hash() -> None:
    body = b"ICCID: '8997201700123456789'\nICCID: '8997201700123456789'\n"
    out = redact_pii_from_raw_qmicli(body)
    matches = _REDACTED_RE.findall(out)
    assert len(matches) == 2
    assert matches[0] == matches[1]


def test_non_pii_line_byte_identical() -> None:
    body = b"Mode: 'online'\nHW restricted: 'no'\n"
    assert redact_pii_from_raw_qmicli(body) == body


def test_uim_fixture_roundtrip() -> None:
    fixture = Path(
        "tests/fixtures/qmicli/uim_get_card_status/1.30/with_iccid.txt"
    ).read_bytes()
    out = redact_pii_from_raw_qmicli(fixture)
    # The fixture has 18-digit ICCID and 15-digit IMSI; assert no raw long-digit
    # run survives (defensive — catches a pattern miss).
    assert b"8997201700123456789" not in out
    assert b"425010012345678" not in out
    # And confirm at least one redaction token appears
    assert _REDACTED_RE.search(out) is not None
