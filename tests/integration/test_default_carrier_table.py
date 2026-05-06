"""Default carrier table validates and ships day-one IL/US/GB/DE coverage.

Closes Phase 1 SC #3 — carrier table covers Israel + US/UK/DE marked
unverified, parses against pydantic, hostile-input fixtures still reject.

Source: .planning/research/FEATURES.md §4.6, ROADMAP §"Phase 1: Foundations & ADRs".
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from spark_modem.wire.carriers import CarrierTable

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_YAML = REPO_ROOT / "debian" / "conf.d" / "00-carriers.yaml"


def test_default_yaml_exists() -> None:
    assert DEFAULT_YAML.is_file(), DEFAULT_YAML


def test_default_yaml_validates() -> None:
    data = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    assert data is not None
    table = CarrierTable.model_validate(data)
    assert len(table.carriers) == 12


def test_default_yaml_country_distribution() -> None:
    data = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    table = CarrierTable.model_validate(data)
    countries = Counter(c.country for c in table.carriers)
    assert countries == {"IL": 3, "US": 3, "GB": 3, "DE": 3}, countries


def test_default_yaml_il_verified_others_unverified() -> None:
    data = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    table = CarrierTable.model_validate(data)
    for entry in table.carriers:
        if entry.country == "IL":
            assert entry.unverified is False, entry
        else:
            assert entry.unverified is True, entry


def test_default_yaml_uses_quoted_mnc_strings_no_norway_problem() -> None:
    # Confirm we did not regress to bare unquoted mnc values
    # (PITFALLS §11.2). The whole-file text inspection is belt; the wire
    # validator (Plan 03) is suspenders.
    text = DEFAULT_YAML.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("mnc:"):
            # mnc: "<digits>"
            value = stripped[len("mnc:") :].strip()
            assert value.startswith('"') and value.endswith('"'), (
                f"mnc line not quoted (Norway-problem hazard): {stripped!r}"
            )


def test_default_yaml_apns_non_empty_and_reasonable_length() -> None:
    data = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    table = CarrierTable.model_validate(data)
    for entry in table.carriers:
        assert len(entry.apn) >= 1, f"Empty APN for {entry.carrier_name}"
        assert len(entry.apn) < 64, f"APN too long for {entry.carrier_name}"


def test_hostile_fixtures_still_reject_after_default_table_change() -> None:
    # Regression cover: re-validate against Plan 03's hostile fixtures so
    # we don't accidentally widen the validator while shipping the default.
    fixtures = REPO_ROOT / "tests" / "fixtures" / "wire" / "carriers"
    for hostile in (
        "hostile_norway_problem.yaml",
        "hostile_mnc_as_int.yaml",
        "hostile_mnc_too_long.yaml",
        "hostile_missing_apn.yaml",
        "hostile_extra_field.yaml",
        "hostile_mixed_case_country.yaml",
    ):
        p = fixtures / hostile
        if not p.exists():
            pytest.skip(f"fixture missing: {p} (Plan 03 not yet executed)")
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        with pytest.raises(ValidationError):
            CarrierTable.model_validate(data)


def test_hostile_leading_zero_mnc_is_happy_path() -> None:
    # leading_zero_mnc fixture uses mnc: "01" (quoted string) — VALID.
    p = REPO_ROOT / "tests" / "fixtures" / "wire" / "carriers" / "hostile_leading_zero_mnc.yaml"
    if not p.exists():
        pytest.skip(f"fixture missing: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    # Should NOT raise — quoted leading-zero MNC is valid per CarrierEntry.
    table = CarrierTable.model_validate(data)
    assert len(table.carriers) >= 1
