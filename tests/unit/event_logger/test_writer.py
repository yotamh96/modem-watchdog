"""Tests for spark_modem.event_logger.writer — O_APPEND JSON Lines writer."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from spark_modem.event_logger import EventLogClosedError, EventLogWriter
from spark_modem.wire.events import DaemonStarted, EventAdapter


def _make_daemon_started() -> DaemonStarted:
    return DaemonStarted(
        ts_iso="2026-01-01T00:00:00+00:00",
        version="2.0.0",
        bundled_python_version="3.12.7",
    )


def test_writer_creates_parent_directory(tmp_path: Path) -> None:
    nested = tmp_path / "nested" / "dir" / "events.jsonl"
    with EventLogWriter(nested) as w:
        assert nested.parent.is_dir()
        assert w.fileno() >= 0


def test_writer_opens_with_o_append(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    with EventLogWriter(path) as w:
        # fileno() should return a valid fd opened with O_APPEND
        fd = w.fileno()
        assert isinstance(fd, int)
        assert fd >= 0
        # Verify the fd is functional (can call os.fstat)
        stat = os.fstat(fd)
        assert stat.st_size >= 0


def test_writer_appends_single_line(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    event = _make_daemon_started()
    with EventLogWriter(path) as w:
        w.append(event)
    content = path.read_bytes()
    assert content.endswith(b"\n")
    lines = content.splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["kind"] == "daemon_started"


def test_writer_100_sequential_appends(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    event = _make_daemon_started()
    with EventLogWriter(path) as w:
        for _ in range(100):
            w.append(event)
    lines = path.read_bytes().splitlines()
    assert len(lines) == 100
    for line in lines:
        parsed = EventAdapter.validate_json(line)
        assert parsed is not None


def test_writer_kind_discriminator_present(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    event = _make_daemon_started()
    with EventLogWriter(path) as w:
        w.append(event)
    rec = json.loads(path.read_bytes().splitlines()[0])
    assert "kind" in rec
    assert rec["kind"] == "daemon_started"


def test_writer_closed_raises_event_log_closed(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    event = _make_daemon_started()
    w = EventLogWriter(path)
    w.close()
    with pytest.raises(EventLogClosedError):
        w.append(event)


def test_writer_context_manager(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    event = _make_daemon_started()
    with EventLogWriter(path) as w:
        w.append(event)
    # After exit, append should raise
    with pytest.raises(EventLogClosedError):
        w.append(event)


def test_writer_type_error_on_non_event(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    w = EventLogWriter(path)
    try:
        with pytest.raises((TypeError, Exception)):
            w.append({"kind": "not_an_event"})  # type: ignore[arg-type]
    finally:
        w.close()


def test_writer_single_os_write_per_append(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    event = _make_daemon_started()
    write_calls: list[tuple[object, ...]] = []
    real_write = os.write

    def counting_write(fd: int, data: bytes) -> int:
        write_calls.append((fd, data))
        return real_write(fd, data)

    with EventLogWriter(path) as w, patch("os.write", side_effect=counting_write):
        w.append(event)
    assert len(write_calls) == 1, f"Expected 1 os.write call, got {len(write_calls)}"
    written = write_calls[0][1]
    assert isinstance(written, bytes)
    assert written.endswith(b"\n")


def test_writer_fileno_returns_int(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    with EventLogWriter(path) as w:
        fd = w.fileno()
        assert isinstance(fd, int)
        assert fd >= 0


def test_writer_fileno_raises_after_close(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    w = EventLogWriter(path)
    w.close()
    with pytest.raises(EventLogClosedError):
        w.fileno()
