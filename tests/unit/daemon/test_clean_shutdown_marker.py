"""Unit tests for clean-shutdown marker IO + boot classifier (L-04)."""

from __future__ import annotations

import json
from pathlib import Path

from spark_modem.daemon.lifecycle import (
    classify_prior_run,
    write_clean_shutdown_marker,
)
from spark_modem.wire.enums import DaemonStopReason


def test_write_marker_atomic_with_uptime_and_cycle_count(tmp_path: Path) -> None:
    """Marker file is JSON containing uptime_s + cycle_count + exit_reason."""
    write_clean_shutdown_marker(
        run_dir=tmp_path,
        uptime_seconds=86400.5,
        cycle_count=2880,
        exit_reason="sigterm",
    )
    marker = tmp_path / "clean-shutdown"
    assert marker.exists()
    body = json.loads(marker.read_text(encoding="utf-8"))
    assert body["uptime_s"] == 86400.5
    assert body["cycle_count"] == 2880
    assert body["exit_reason"] == "sigterm"


def test_classify_returns_config_invalid_when_last_config_error_exists(
    tmp_path: Path,
) -> None:
    """Precedence #1: last-config-error → CONFIG_INVALID, uptime 0.0; unlinks."""
    config_error = tmp_path / "last-config-error"
    config_error.write_text("settings invalid", encoding="utf-8")
    reason, uptime = classify_prior_run(run_dir=tmp_path)
    assert reason is DaemonStopReason.CONFIG_INVALID
    assert uptime == 0.0
    assert not config_error.exists(), "classify_prior_run must unlink the marker"


def test_classify_returns_sigterm_when_marker_exists(tmp_path: Path) -> None:
    """Precedence #2: clean-shutdown → SIGTERM, uptime from JSON; unlinks."""
    write_clean_shutdown_marker(
        run_dir=tmp_path,
        uptime_seconds=120.0,
        cycle_count=10,
        exit_reason="sigterm",
    )
    reason, uptime = classify_prior_run(run_dir=tmp_path)
    assert reason is DaemonStopReason.SIGTERM
    assert uptime == 120.0
    assert not (tmp_path / "clean-shutdown").exists()


def test_classify_returns_crash_when_neither_exists(tmp_path: Path) -> None:
    """Precedence #3: neither marker → CRASH, uptime 0.0."""
    reason, uptime = classify_prior_run(run_dir=tmp_path)
    assert reason is DaemonStopReason.CRASH
    assert uptime == 0.0


def test_classify_handles_corrupt_marker_json(tmp_path: Path) -> None:
    """Corrupt JSON in clean-shutdown still classifies SIGTERM, uptime 0.0."""
    marker = tmp_path / "clean-shutdown"
    marker.write_text("{not-valid-json", encoding="utf-8")
    reason, uptime = classify_prior_run(run_dir=tmp_path)
    assert reason is DaemonStopReason.SIGTERM
    assert uptime == 0.0
    assert not marker.exists(), "corrupt marker must still be unlinked"
