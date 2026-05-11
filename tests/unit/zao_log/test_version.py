"""Unit tests for zao_log.version — Zao SDK banner detection.

Tests cover the six branches called out in Plan 05-02 Task 2:
banner-present (returns version) / banner-absent (returns None) /
missing file (returns None, never raises) / huge file with banner
outside the head-read window (returns None — T-05-02-01 DoS mitigation
pin) / legacy banner shape / first-match-wins ordering.

Module under test is pure I/O (no subprocess); SP-04 lint scope applies
but is trivially satisfied.
"""

from __future__ import annotations

from pathlib import Path

from spark_modem.zao_log.version import _HEAD_BYTES, detect_zao_sdk_version

_FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "zao_log" / "version"


def test_banner_present_returns_version() -> None:
    path = _FIXTURE_ROOT / "banner_present.txt"
    assert detect_zao_sdk_version(path) == "2.1.0"


def test_no_banner_returns_none() -> None:
    path = _FIXTURE_ROOT / "no_banner.txt"
    assert detect_zao_sdk_version(path) is None


def test_missing_file_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "does_not_exist.log"
    assert detect_zao_sdk_version(path) is None


def test_banner_outside_head_window_returns_none(tmp_path: Path) -> None:
    """T-05-02-01: 64 KiB head-read cap prevents OOM on huge logs.

    Synthesise a file with the banner past the head-read window; the
    detector must return None rather than scan the entire file.
    """
    path = tmp_path / "huge.log"
    padding = b"x" * (_HEAD_BYTES + 100)
    path.write_bytes(padding + b"zao_remote_endpoint/2.1.0 starting\n")
    assert detect_zao_sdk_version(path) is None


def test_legacy_banner_shape_also_matches(tmp_path: Path) -> None:
    """Pre-2.0 builds wrote ``zao-remote-endpoint X.Y.Z`` (dash + space)."""
    path = tmp_path / "legacy.log"
    path.write_text(
        "2026-05-11T14:32:00Z INFO zao-remote-endpoint 1.9.5 starting\n",
        encoding="utf-8",
    )
    assert detect_zao_sdk_version(path) == "1.9.5"


def test_first_match_wins(tmp_path: Path) -> None:
    """Multiple banners in the head window: first occurrence wins (idempotent)."""
    path = tmp_path / "multi.log"
    path.write_text(
        "INFO zao_remote_endpoint/2.1.0 starting\n"
        "WARN zao_remote_endpoint/9.9.9 reload\n",
        encoding="utf-8",
    )
    assert detect_zao_sdk_version(path) == "2.1.0"
