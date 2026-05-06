"""Tests for src.spark_modem.wire.identity — Identity (ADR-0009 usb_path keying)."""

import pytest
from pydantic import ValidationError

from spark_modem.wire.identity import Identity


def test_identity_constructs_cleanly() -> None:
    """Identity with valid fields constructs without error."""
    m = Identity(
        usb_path="2-3.1.1",
        iccid="899720100000000001",
        imsi="42503000000001",
        first_seen_iso="2026-05-06T00:00:00+00:00",
        last_seen_iso="2026-05-06T01:00:00+00:00",
    )
    assert m.usb_path == "2-3.1.1"
    assert m.schema_version == 1


def test_usb_path_accepts_valid_patterns() -> None:
    """usb_path accepts valid sysfs USB path patterns."""
    for valid in ("2-3.1.1", "2-3", "1-1.4.2", "1-1", "10-2.3.4"):
        Identity(
            usb_path=valid,
            iccid="899720100000000001",
            imsi="42503000000001",
            first_seen_iso="2026-05-06T00:00:00+00:00",
            last_seen_iso="2026-05-06T01:00:00+00:00",
        )


def test_usb_path_rejects_cdc_wdm() -> None:
    """usb_path must reject cdc-wdmN device names (ADR-0009)."""
    with pytest.raises(ValidationError):
        Identity(
            usb_path="cdc-wdm0",
            iccid="899720100000000001",
            imsi="42503000000001",
            first_seen_iso="2026-05-06T00:00:00+00:00",
            last_seen_iso="2026-05-06T01:00:00+00:00",
        )


def test_usb_path_rejects_empty_string() -> None:
    """usb_path must reject empty string."""
    with pytest.raises(ValidationError):
        Identity(
            usb_path="",
            iccid="899720100000000001",
            imsi="42503000000001",
            first_seen_iso="2026-05-06T00:00:00+00:00",
            last_seen_iso="2026-05-06T01:00:00+00:00",
        )


def test_usb_path_rejects_path_traversal() -> None:
    """usb_path must reject path-traversal strings."""
    with pytest.raises(ValidationError):
        Identity(
            usb_path="../../etc/passwd",
            iccid="899720100000000001",
            imsi="42503000000001",
            first_seen_iso="2026-05-06T00:00:00+00:00",
            last_seen_iso="2026-05-06T01:00:00+00:00",
        )


def test_iccid_validator_accepts_valid() -> None:
    """iccid validator accepts 18-22 digit strings (ITU-T E.118)."""
    for length in (18, 19, 20, 21, 22):
        iccid = "8" * length
        Identity(
            usb_path="2-3.1.1",
            iccid=iccid,
            imsi="42503000000001",
            first_seen_iso="2026-05-06T00:00:00+00:00",
            last_seen_iso="2026-05-06T01:00:00+00:00",
        )


def test_iccid_validator_rejects_too_short() -> None:
    """iccid validator rejects strings shorter than 18 digits."""
    with pytest.raises(ValidationError):
        Identity(
            usb_path="2-3.1.1",
            iccid="89972010000000001",  # 17 digits
            imsi="42503000000001",
            first_seen_iso="2026-05-06T00:00:00+00:00",
            last_seen_iso="2026-05-06T01:00:00+00:00",
        )


def test_iccid_validator_rejects_too_long() -> None:
    """iccid validator rejects strings longer than 22 digits."""
    with pytest.raises(ValidationError):
        Identity(
            usb_path="2-3.1.1",
            iccid="89972010000000001234567",  # 23 digits
            imsi="42503000000001",
            first_seen_iso="2026-05-06T00:00:00+00:00",
            last_seen_iso="2026-05-06T01:00:00+00:00",
        )


def test_imsi_validator_accepts_valid() -> None:
    """imsi validator accepts 14-15 digit strings."""
    for length in (14, 15):
        imsi = "4" * length
        Identity(
            usb_path="2-3.1.1",
            iccid="899720100000000001",
            imsi=imsi,
            first_seen_iso="2026-05-06T00:00:00+00:00",
            last_seen_iso="2026-05-06T01:00:00+00:00",
        )


def test_imsi_validator_rejects_too_short() -> None:
    """imsi validator rejects strings shorter than 14 digits."""
    with pytest.raises(ValidationError):
        Identity(
            usb_path="2-3.1.1",
            iccid="899720100000000001",
            imsi="4250300000001",  # 13 digits
            first_seen_iso="2026-05-06T00:00:00+00:00",
            last_seen_iso="2026-05-06T01:00:00+00:00",
        )


def test_sim_swap_detectable() -> None:
    """Two Identity objects at same usb_path with different ICCIDs are not equal."""
    base_kwargs = {
        "usb_path": "2-3.1.1",
        "imsi": "42503000000001",
        "first_seen_iso": "2026-05-06T00:00:00+00:00",
        "last_seen_iso": "2026-05-06T01:00:00+00:00",
    }
    m1 = Identity(iccid="899720100000000001", **base_kwargs)
    m2 = Identity(iccid="899720100000000002", **base_kwargs)
    assert m1 != m2
