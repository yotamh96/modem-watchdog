"""Tests for spark_modem.cli.redact — PII redaction helpers."""

from __future__ import annotations

import re

from spark_modem.cli.redact import (
    redact_iccid_imsi_in_dict,
    redact_pii,
    redact_webhook_url_to_host_only,
)

_REDACTED_RE = re.compile(r"^<redacted:[0-9a-f]{8}>$")


def test_redact_pii_returns_redacted_format() -> None:
    assert _REDACTED_RE.match(redact_pii("8997201700123456789"))


def test_redact_pii_consistent_for_same_input() -> None:
    """Same input → same redacted form (one-way correlation across bundle)."""
    a = redact_pii("8997201700123456789")
    b = redact_pii("8997201700123456789")
    assert a == b


def test_redact_pii_different_inputs_yield_different_outputs() -> None:
    a = redact_pii("8997201700123456789")
    b = redact_pii("8997201700987654321")
    assert a != b


def test_redact_iccid_imsi_in_dict_redacts_iccid() -> None:
    out = redact_iccid_imsi_in_dict({"iccid": "8997201700123456789", "other": "x"})
    assert isinstance(out, dict)
    assert _REDACTED_RE.match(out["iccid"])
    assert out["other"] == "x"


def test_redact_iccid_imsi_in_dict_redacts_imsi() -> None:
    out = redact_iccid_imsi_in_dict({"imsi": "425010123456789"})
    assert _REDACTED_RE.match(out["imsi"])


def test_redact_iccid_imsi_in_dict_recursive_nested() -> None:
    raw = {
        "modems": [
            {"iccid": "8997201700123456789", "usb_path": "2-3.1.1"},
            {"iccid": "8997201700987654321", "usb_path": "2-3.1.2"},
        ],
        "id_block": {"imsi": "425010123456789"},
    }
    out = redact_iccid_imsi_in_dict(raw)
    assert _REDACTED_RE.match(out["modems"][0]["iccid"])
    assert _REDACTED_RE.match(out["modems"][1]["iccid"])
    assert _REDACTED_RE.match(out["id_block"]["imsi"])
    assert out["modems"][0]["usb_path"] == "2-3.1.1"


def test_redact_iccid_imsi_in_dict_does_not_touch_other_fields() -> None:
    raw = {
        "iccid": "abc",
        "state": "healthy",
        "counters": {"set_apn": 1, "fix_raw_ip": 0},
    }
    out = redact_iccid_imsi_in_dict(raw)
    assert _REDACTED_RE.match(out["iccid"])
    assert out["state"] == "healthy"
    assert out["counters"] == {"set_apn": 1, "fix_raw_ip": 0}


def test_redact_iccid_imsi_in_dict_handles_lists_of_primitives() -> None:
    out = redact_iccid_imsi_in_dict([1, "x", {"iccid": "y"}])
    assert isinstance(out, list)
    assert out[0] == 1
    assert out[1] == "x"
    assert _REDACTED_RE.match(out[2]["iccid"])


def test_redact_iccid_imsi_handles_non_string_iccid_gracefully() -> None:
    """Non-string ICCID values are passed through (defensive)."""
    out = redact_iccid_imsi_in_dict({"iccid": None})
    assert out["iccid"] is None


def test_redact_webhook_url_to_host_only_strips_path_and_query() -> None:
    assert (
        redact_webhook_url_to_host_only("https://noc.example.com/secret/path?q=1")
        == "https://noc.example.com/"
    )


def test_redact_webhook_url_to_host_only_handles_http() -> None:
    assert (
        redact_webhook_url_to_host_only("http://noc.example.com:8080/x")
        == "http://noc.example.com:8080/"
    )


def test_redact_webhook_url_to_host_only_passes_through_invalid() -> None:
    """No netloc → input is returned unchanged."""
    assert redact_webhook_url_to_host_only("not-a-url") == "not-a-url"
