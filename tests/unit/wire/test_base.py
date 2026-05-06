"""Tests for src.spark_modem.wire._base.BaseWire."""

import pytest
from pydantic import Field, ValidationError

from spark_modem.wire._base import BaseWire


class _SampleModel(BaseWire):
    x: int


class _AliasModel(BaseWire):
    external: int = Field(alias="external_name")


def test_basewire_is_frozen() -> None:
    """A BaseWire subclass must raise ValidationError when mutated after construction."""
    m = _SampleModel(x=1)
    with pytest.raises(ValidationError):
        m.x = 2  # type: ignore[misc]


def test_basewire_extra_forbid() -> None:
    """A BaseWire subclass must raise ValidationError on extra keys."""
    with pytest.raises(ValidationError, match="extra_forbidden"):
        _SampleModel.model_validate({"x": 1, "unknown_key": "bad"})


def test_basewire_populate_by_name_alias() -> None:
    """populate_by_name=True allows construction with alias key."""
    m1 = _AliasModel.model_validate({"external_name": 42})
    assert m1.external == 42


def test_basewire_populate_by_name_attr() -> None:
    """populate_by_name=True allows construction with python attribute name too."""
    m2 = _AliasModel.model_validate({"external": 42})
    assert m2.external == 42


def test_basewire_round_trip() -> None:
    """model_dump_json / model_validate_json round-trip produces an equal model."""
    m = _SampleModel(x=99)
    json_bytes = m.model_dump_json()
    m2 = _SampleModel.model_validate_json(json_bytes)
    assert m == m2


def test_basewire_empty_instantiation() -> None:
    """BaseWire itself has zero declared fields; instantiating succeeds."""
    b = BaseWire()
    assert b is not None
