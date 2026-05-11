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


def test_ipv4_subnet_mask_redacted() -> None:
    """Phase 5 CR-01: every IPv4 label shape emitted by qmicli must redact.

    The real ``wds_get_current_settings`` stdout emits ``IPv4 subnet mask``
    alongside ``IPv4 address`` and ``IPv4 gateway address``. The original
    pattern list only covered ``IPv4 address:`` (CR-01 in REVIEW.md).
    """
    out = redact_pii_from_raw_qmicli(b"\tIPv4 subnet mask: '255.255.255.248'\n")
    assert _REDACTED_RE.search(out) is not None
    assert b"255.255.255.248" not in out


def test_ipv4_gateway_address_redacted() -> None:
    """Phase 5 CR-01: gateway IP is routable carrier-NAT data; must redact."""
    out = redact_pii_from_raw_qmicli(b"\tIPv4 gateway address: '10.69.92.150'\n")
    assert _REDACTED_RE.search(out) is not None
    assert b"10.69.92.150" not in out


def test_ipv4_primary_dns_redacted() -> None:
    """Phase 5 CR-01: DNS server addresses also fall under the IPv4 prefix
    redaction; covered by the generalised label-prefix pattern."""
    out = redact_pii_from_raw_qmicli(b"\tIPv4 primary DNS: '8.8.8.8'\n")
    assert _REDACTED_RE.search(out) is not None
    assert b"8.8.8.8" not in out


def test_wds_current_settings_fixture_redacts_all_ipv4_fields() -> None:
    """Phase 5 CR-01 regression: real wds_get_current_settings fixture must
    have every dotted-quad IPv4 value redacted (address + subnet + gateway)."""
    fixture = Path("tests/fixtures/qmicli/get_current_settings/1.30/raw_ip_y.txt").read_bytes()
    out = redact_pii_from_raw_qmicli(fixture)
    # The fixture contains three IPv4 values; assert none survive.
    for raw_ip in (b"10.69.92.156", b"255.255.255.248", b"10.69.92.150"):
        assert raw_ip not in out, f"raw IPv4 value {raw_ip!r} survived redaction"
    # At least the three IPv4 lines should produce redaction tokens.
    assert len(_REDACTED_RE.findall(out)) >= 3


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
    fixture = Path("tests/fixtures/qmicli/uim_get_card_status/1.30/with_iccid.txt").read_bytes()
    out = redact_pii_from_raw_qmicli(fixture)
    # The fixture has 18-digit ICCID and 15-digit IMSI; assert no raw long-digit
    # run survives (defensive — catches a pattern miss).
    assert b"8997201700123456789" not in out
    assert b"425010012345678" not in out
    # And confirm at least one redaction token appears
    assert _REDACTED_RE.search(out) is not None
