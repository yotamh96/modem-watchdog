"""Tests for src.spark_modem.wire.globals — GlobalsState."""

import pytest
from pydantic import ValidationError

from spark_modem.wire.globals import GlobalsState


def test_globals_state_constructs() -> None:
    """GlobalsState with all explicit fields constructs cleanly."""
    g = GlobalsState(
        driver_reset_count=0,
        last_driver_reset_monotonic=None,
        last_driver_reset_iso=None,
        qmi_proxy_uptime_seconds=0.0,
    )
    assert g.schema_version == 1
    assert g.driver_reset_count == 0
    assert g.last_driver_reset_monotonic is None
    assert g.last_driver_reset_iso is None
    assert g.qmi_proxy_uptime_seconds == 0.0


def test_globals_state_defaults() -> None:
    """GlobalsState constructs with all defaults."""
    g = GlobalsState()
    assert g.driver_reset_count == 0
    assert g.qmi_proxy_uptime_seconds == 0.0


def test_driver_reset_count_non_negative() -> None:
    """driver_reset_count must be >= 0."""
    with pytest.raises(ValidationError):
        GlobalsState(driver_reset_count=-1)


def test_globals_state_round_trip_json() -> None:
    """GlobalsState round-trips via model_dump_json / model_validate_json."""
    g = GlobalsState(
        driver_reset_count=3,
        last_driver_reset_monotonic=11100.5,
        last_driver_reset_iso="2026-05-05T11:00:00+00:00",
        qmi_proxy_uptime_seconds=86400.0,
    )
    j = g.model_dump_json()
    g2 = GlobalsState.model_validate_json(j)
    assert g == g2
