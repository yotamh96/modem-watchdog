"""Tests for src.spark_modem.wire.versioning."""

import pathlib

import pytest

from spark_modem.wire.versioning import (
    CURRENT_SCHEMA_VERSION,
    SchemaVersionTooNew,
    shadow_filename,
    validate_schema_version,
)


def test_current_schema_version_is_int() -> None:
    """CURRENT_SCHEMA_VERSION must be an int."""
    assert isinstance(CURRENT_SCHEMA_VERSION, int)


def test_current_schema_version_is_one() -> None:
    """v2.0 baseline is schema version 1."""
    assert CURRENT_SCHEMA_VERSION == 1


def test_schema_version_too_new_is_exception() -> None:
    """SchemaVersionTooNew must be an Exception subclass."""
    assert issubclass(SchemaVersionTooNew, Exception)


def test_validate_schema_version_future_raises() -> None:
    """validate_schema_version raises SchemaVersionTooNew on future version."""
    with pytest.raises(SchemaVersionTooNew) as exc_info:
        validate_schema_version(file_version=99)
    err = exc_info.value
    assert err.seen == 99
    assert err.current == CURRENT_SCHEMA_VERSION
    assert "99" in str(err)
    assert str(CURRENT_SCHEMA_VERSION) in str(err)


def test_validate_schema_version_current_returns_current() -> None:
    """validate_schema_version returns 'current' for current version."""
    result = validate_schema_version(file_version=CURRENT_SCHEMA_VERSION)
    assert result == "current"


def test_validate_schema_version_past_returns_downgrade() -> None:
    """validate_schema_version returns 'downgrade' for older version."""
    result = validate_schema_version(file_version=0)
    assert result == "downgrade"


def test_shadow_filename_absolute() -> None:
    """shadow_filename converts an absolute path correctly."""
    result = shadow_filename("/some/dir/2-3.1.1.json", from_version=0)
    assert result == pathlib.Path("/some/dir/2-3.1.1.from-v0.json")


def test_shadow_filename_relative() -> None:
    """shadow_filename handles a relative path correctly."""
    result = shadow_filename("state/2-3.1.2.json", from_version=2)
    assert result == pathlib.Path("state/2-3.1.2.from-v2.json")


def test_shadow_filename_pathlib_input() -> None:
    """shadow_filename accepts a pathlib.Path as input."""
    result = shadow_filename(pathlib.Path("/var/lib/foo/bar.json"), from_version=1)
    assert result == pathlib.Path("/var/lib/foo/bar.from-v1.json")
