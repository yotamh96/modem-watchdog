"""Tests for src.spark_modem.wire.carriers — CarrierEntry + CarrierTable.

Covers the YAML "Norway problem" (PITFALLS §11.2), leading-zero MNCs,
MNC-as-int rejection, and a Hypothesis property test on MNC validation.
"""

from __future__ import annotations

import pathlib
import re

import pytest
import yaml
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from spark_modem.wire.carriers import CarrierEntry, CarrierTable

_FIXTURE_DIR = pathlib.Path(__file__).parent.parent.parent / "fixtures" / "wire" / "carriers"


def _load_yaml(name: str) -> object:
    return yaml.safe_load((_FIXTURE_DIR / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_carrier_entry_constructs() -> None:
    """CarrierEntry with valid fields constructs cleanly."""
    e = CarrierEntry(country="IL", mcc="425", mnc="01", apn="internetg", carrier_name="Partner")
    assert e.country == "IL"
    assert e.mcc == "425"
    assert e.mnc == "01"
    assert e.unverified is False


def test_happy_minimal_yaml_loads() -> None:
    """happy_minimal.yaml with 12 carrier entries loads and round-trips."""
    data = _load_yaml("happy_minimal.yaml")
    table = CarrierTable.model_validate(data)
    assert len(table.carriers) == 12


def test_happy_minimal_round_trip() -> None:
    """CarrierTable round-trips via JSON."""
    data = _load_yaml("happy_minimal.yaml")
    table = CarrierTable.model_validate(data)
    j = table.model_dump_json()
    table2 = CarrierTable.model_validate_json(j)
    assert table == table2


# ---------------------------------------------------------------------------
# Hostile inputs
# ---------------------------------------------------------------------------


def test_hostile_norway_problem() -> None:
    """country: NO parsed by YAML 1.1 as boolean False must be rejected."""
    data = _load_yaml("hostile_norway_problem.yaml")
    # PyYAML parses bare NO as False (boolean). Pydantic StrictStr rejects False.
    with pytest.raises(ValidationError):
        CarrierTable.model_validate(data)


def test_hostile_leading_zero_mnc_accepted() -> None:
    """mnc: '01' (leading-zero string) must be accepted — it is a valid 2-digit MNC."""
    data = _load_yaml("hostile_leading_zero_mnc.yaml")
    table = CarrierTable.model_validate(data)
    assert table.carriers[0].mnc == "01"


def test_hostile_mnc_as_int_rejected() -> None:
    """mnc: 1 (integer, not string) must be rejected with a type error."""
    data = _load_yaml("hostile_mnc_as_int.yaml")
    with pytest.raises(ValidationError):
        CarrierTable.model_validate(data)


def test_hostile_mnc_too_long_rejected() -> None:
    """mnc: '1234' (4 digits) must be rejected by the regex."""
    data = _load_yaml("hostile_mnc_too_long.yaml")
    with pytest.raises(ValidationError):
        CarrierTable.model_validate(data)


def test_hostile_missing_apn_rejected() -> None:
    """Missing apn field must raise 'Field required'."""
    data = _load_yaml("hostile_missing_apn.yaml")
    with pytest.raises(ValidationError, match="apn"):
        CarrierTable.model_validate(data)


def test_hostile_extra_field_rejected() -> None:
    """Extra 'bogus' field must be rejected by extra='forbid'."""
    data = _load_yaml("hostile_extra_field.yaml")
    with pytest.raises(ValidationError):
        CarrierTable.model_validate(data)


def test_hostile_mixed_case_country_rejected() -> None:
    """country: 'il' (lowercase) must be rejected — must be uppercase ISO 3166-1 alpha-2."""
    data = _load_yaml("hostile_mixed_case_country.yaml")
    with pytest.raises(ValidationError):
        CarrierTable.model_validate(data)


# ---------------------------------------------------------------------------
# Hypothesis property test: MNC string validation
# ---------------------------------------------------------------------------


@given(st.from_regex(r"^\d{2,3}$", fullmatch=True))
def test_mnc_valid_strings_accepted(mnc: str) -> None:
    """Any 2-3 digit string must be accepted as a valid MNC."""
    e = CarrierEntry(country="IL", mcc="425", mnc=mnc, apn="internet", carrier_name="Test")
    assert e.mnc == mnc


@given(
    st.one_of(
        st.text(max_size=1),  # empty or 1 char
        st.from_regex(r"^\d{4,}$", fullmatch=True),  # too long
        st.from_regex(r".*[^\d].*", fullmatch=True),  # non-digit chars
    )
)
def test_mnc_invalid_strings_rejected(mnc: str) -> None:
    """Strings that aren't 2-3 decimal digits must always be rejected."""
    if re.fullmatch(r"^\d{2,3}$", mnc):
        return  # hypothesis may generate a valid string from some branches; skip
    with pytest.raises(ValidationError):
        CarrierEntry(country="IL", mcc="425", mnc=mnc, apn="internet", carrier_name="Test")
