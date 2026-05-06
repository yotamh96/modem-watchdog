"""Tests for spark_modem.config.reload_marker — RELOAD_DATA / RELOAD_RESTART."""

from __future__ import annotations

from pydantic import BaseModel, Field

from spark_modem.config.reload_marker import (
    RELOAD_DATA,
    RELOAD_RESTART,
    data_reloadable_fields,
    restart_required_fields,
)


def test_reload_data_value() -> None:
    assert RELOAD_DATA == {"reload": "data"}


def test_reload_restart_value() -> None:
    assert RELOAD_RESTART == {"reload": "restart"}


def test_restart_required_fields_returns_tagged_fields() -> None:
    class MyModel(BaseModel):
        topology_field: str = Field(default="x", json_schema_extra=RELOAD_RESTART)
        data_field: str = Field(default="y", json_schema_extra=RELOAD_DATA)
        no_marker_field: str = Field(default="z")

    result = restart_required_fields(MyModel)
    assert "topology_field" in result
    assert "data_field" not in result
    assert "no_marker_field" not in result


def test_restart_required_fields_ignores_no_marker() -> None:
    class NoMarkerModel(BaseModel):
        plain_field: str = Field(default="x")

    result = restart_required_fields(NoMarkerModel)
    assert result == frozenset()


def test_data_reloadable_fields_returns_data_tagged() -> None:
    class MyModel(BaseModel):
        topo: str = Field(default="a", json_schema_extra=RELOAD_RESTART)
        data: str = Field(default="b", json_schema_extra=RELOAD_DATA)

    result = data_reloadable_fields(MyModel)
    assert "data" in result
    assert "topo" not in result


def test_mixed_marker_partition() -> None:
    class MixedModel(BaseModel):
        r1: str = Field(default="a", json_schema_extra=RELOAD_RESTART)
        r2: str = Field(default="b", json_schema_extra=RELOAD_RESTART)
        d1: str = Field(default="c", json_schema_extra=RELOAD_DATA)
        none: str = Field(default="d")

    restart = restart_required_fields(MixedModel)
    data = data_reloadable_fields(MixedModel)
    assert restart == frozenset({"r1", "r2"})
    assert data == frozenset({"d1"})
    assert "none" not in restart
    assert "none" not in data
