"""Tests for parsers/get_revision.py — parse qmicli --dms-get-revision stdout.

Tests mirror the parser-test shape established for get_operating_mode in
tests/unit/qmi/test_parsers.py: happy path against the libqmi 1.30 fixture,
UNEXPECTED_OUTPUT when the response header is absent, MISSING_FIELD when the
Revision line is absent, and pydantic frozen-model behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from spark_modem.qmi.errors import QmiError, QmiErrorReason
from spark_modem.qmi.parsers.get_revision import (
    GetRevisionResult,
    parse_get_revision,
)

_FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "fixtures" / "qmicli"


def test_parser_happy_path_libqmi_1_30() -> None:
    """Fixture-driven happy path: Revision line is parsed verbatim
    (firmware strings preserve case — NOT lower-cased).
    """
    body = (_FIXTURES_ROOT / "get_revision" / "1.30" / "standard.txt").read_bytes()
    result = parse_get_revision(body)
    assert isinstance(result, GetRevisionResult)
    assert result.revision == "SWI9X30C_02.38.00.00"


def test_parser_no_header_returns_unexpected_output() -> None:
    """If the response header ('Device revisions retrieved') is absent,
    parser returns QmiError(UNEXPECTED_OUTPUT).
    """
    result = parse_get_revision(b"completely unrelated stdout")
    assert isinstance(result, QmiError)
    assert result.reason is QmiErrorReason.UNEXPECTED_OUTPUT
    assert result.argv == ("qmicli", "--dms-get-revision")


def test_parser_header_present_but_revision_missing_returns_missing_field() -> None:
    """If the response header is present but the Revision line is absent,
    parser returns QmiError(MISSING_FIELD, field='revision').
    """
    result = parse_get_revision(b"[/dev/cdc-wdm0] Device revisions retrieved:\n")
    assert isinstance(result, QmiError)
    assert result.reason is QmiErrorReason.MISSING_FIELD
    assert result.field == "revision"
    assert result.argv == ("qmicli", "--dms-get-revision")


def test_result_is_frozen_and_ignores_extra_fields() -> None:
    """GetRevisionResult uses ConfigDict(extra='ignore', frozen=True):
    attribute assignment after construction must raise ValidationError;
    construction with extra fields must silently ignore them.
    """
    result = GetRevisionResult(revision="SWI9X30C_02.38.00.00")
    with pytest.raises(ValidationError):
        result.revision = "MUTATED"  # type: ignore[misc]

    # extra='ignore': construction with unknown fields succeeds and the
    # extras are dropped.
    silent = GetRevisionResult.model_validate(
        {"revision": "SWI9X30C_02.38.00.00", "unknown_field": "should be ignored"},
    )
    assert silent.revision == "SWI9X30C_02.38.00.00"
    assert not hasattr(silent, "unknown_field")


def test_parser_accepts_singular_revision_header_jetpack() -> None:
    """Phase 05.4 regression: libqmi 1.30 emits SINGULAR 'Device revision
    retrieved' (no plural 's') when only the Revision line is present and
    no Boot code line follows. Bench Jetson 2026-05-12 (SWI9X50C modem)
    surfaced this — the parser previously hardcoded the plural form and
    rejected the entire stdout with QmiError(UNEXPECTED_OUTPUT).
    """
    body = (
        _FIXTURES_ROOT / "get_revision" / "1.30" / "jetpack-singular.txt"
    ).read_bytes()
    result = parse_get_revision(body)
    assert isinstance(result, GetRevisionResult)
    assert result.revision == (
        "SWI9X50C_01.14.03.00 b06bd3 jenkins 2020/09/23 10:53:35"
    )


def test_parser_accepts_libqmi_1_32_fixture() -> None:
    """The parser handles the libqmi 1.32 fixture identically — Revision
    line shape has not changed across 1.30→1.32 per RESEARCH Q3 A4/A5.
    """
    body = (_FIXTURES_ROOT / "get_revision" / "1.32" / "standard.txt").read_bytes()
    result = parse_get_revision(body)
    assert isinstance(result, GetRevisionResult)
    assert result.revision == "SWI9X30C_02.38.00.00"


def test_fixture_tree_has_locked_set_of_libqmi_versions() -> None:
    """Phase 5: 1.30 + 1.32. Adding a new libqmi version is a deliberate
    extension (new fixture file); deleting one is a regression caught here.
    """
    root = _FIXTURES_ROOT / "get_revision"
    version_dirs = sorted(d.name for d in root.iterdir() if d.is_dir())
    assert version_dirs == ["1.30", "1.32"], version_dirs
