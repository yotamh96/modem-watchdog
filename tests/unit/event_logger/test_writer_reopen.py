"""Tests for EventLogWriter.reopen + _reopen_buffer + EventLogReopener (Plan 03-04).

R-01/R-03: when the asyncinotify producer detects an events.jsonl rotation,
it calls EventLogWriter.reopen(). During the reopen window writes go to a
deque(maxlen=1000) buffer; reopen() then flushes the buffer to the new fd
in FIFO order. Buffer overflow is observable via reopen_overflow_count for
the Plan 03-06 metrics integration.

These tests are POSIX-only because they exercise real fd-replacement
semantics (logrotate's `create` mode renames the inode out from under the
existing fd; only POSIX has that semantic).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from spark_modem.event_logger import EventLogClosedError, EventLogWriter
from spark_modem.event_logger.inotify_reopener import EventLogReopener
from spark_modem.wire.events import DaemonStarted

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="O_APPEND fd-replacement semantics are POSIX",
)


def _make_event() -> DaemonStarted:
    return DaemonStarted(
        ts_iso="2026-01-01T00:00:00+00:00",
        version="2.0.0",
        bundled_python_version="3.12.7",
    )


def test_reopen_replaces_fd_on_same_path(tmp_path: Path) -> None:
    """reopen() closes the old fd and opens a new one at the same path."""
    path = tmp_path / "events.jsonl"
    with EventLogWriter(path) as w:
        initial_fd = w.fileno()
        w.reopen()
        new_fd = w.fileno()
        assert new_fd != initial_fd, "fd should be different after reopen"
        # The path is unchanged; subsequent appends still target it.
        assert path.exists()


def test_append_during_reopening_buffers_to_deque(tmp_path: Path) -> None:
    """When _reopening=True, append() routes the line to the buffer (no os.write)."""
    path = tmp_path / "events.jsonl"
    event = _make_event()
    with EventLogWriter(path) as w:
        # Manually flip the flag to simulate the reopen-window state.
        w._reopening = True  # type: ignore[reportPrivateUsage]
        # File should still be empty after this append (it goes to buffer).
        w.append(event)
        assert len(w._reopen_buffer) == 1, "1 line should be buffered"  # type: ignore[reportPrivateUsage]
        # Reset _reopening so the writer cleans up on close.
        w._reopening = False  # type: ignore[reportPrivateUsage]
    # After close, file content should be empty (buffered line was never flushed).
    assert path.read_bytes() == b""


def test_reopen_flushes_buffer_in_fifo_order(tmp_path: Path) -> None:
    """reopen() drains the buffer to the new fd in insertion order."""
    path = tmp_path / "events.jsonl"
    with EventLogWriter(path) as w:
        # Push three pre-formed lines into the buffer.
        w._reopen_buffer.append(b'{"kind":"first"}\n')  # type: ignore[reportPrivateUsage]
        w._reopen_buffer.append(b'{"kind":"second"}\n')  # type: ignore[reportPrivateUsage]
        w._reopen_buffer.append(b'{"kind":"third"}\n')  # type: ignore[reportPrivateUsage]
        w.reopen()
        # After reopen, buffer is empty.
        assert len(w._reopen_buffer) == 0  # type: ignore[reportPrivateUsage]
    # File content shows FIFO order.
    lines = path.read_bytes().splitlines()
    assert len(lines) == 3
    assert json.loads(lines[0])["kind"] == "first"
    assert json.loads(lines[1])["kind"] == "second"
    assert json.loads(lines[2])["kind"] == "third"


def test_buffer_overflow_increments_counter(tmp_path: Path) -> None:
    """deque(maxlen=1000) silently drops oldest; reopen_overflow_count tracks it."""
    path = tmp_path / "events.jsonl"
    event = _make_event()
    with EventLogWriter(path) as w:
        w._reopening = True  # type: ignore[reportPrivateUsage]
        # Fill buffer to maxlen.
        for _ in range(1000):
            w.append(event)
        assert len(w._reopen_buffer) == 1000  # type: ignore[reportPrivateUsage]
        assert w.reopen_overflow_count == 0
        # Push 5 more — these overflow.
        for _ in range(5):
            w.append(event)
        assert len(w._reopen_buffer) == 1000  # type: ignore[reportPrivateUsage]
        assert w.reopen_overflow_count == 5
        w._reopening = False  # type: ignore[reportPrivateUsage]


def test_reopen_creates_file_if_logrotate_renamed_inode(tmp_path: Path) -> None:
    """Simulate logrotate's `create` mode: rename the file, then reopen.

    Phase 3 R-02: the .deb's logrotate snippet uses `create 0640 root adm`
    which already creates the file. To exercise the worst case (asyncinotify
    fires before logrotate's create), we rename the file first and let
    reopen() create a fresh one via O_CREAT.
    """
    path = tmp_path / "events.jsonl"
    event = _make_event()
    with EventLogWriter(path) as w:
        w.append(event)
        # logrotate's create-mode rotation: rename the active file.
        rotated = tmp_path / "events.jsonl.1"
        path.rename(rotated)
        # Now reopen — should re-create the file at the original path.
        w.reopen()
        assert path.exists(), "reopen should re-create the original path"
        # Subsequent appends go to the new file.
        w.append(event)
    # The new file has exactly one line; the rotated file has the prior line.
    assert len(path.read_bytes().splitlines()) == 1
    assert len(rotated.read_bytes().splitlines()) == 1


@pytest.mark.asyncio
async def test_eventlog_reopener_calls_writer_reopen() -> None:
    """EventLogReopener.on_rotate() delegates to the writer's reopen()."""
    call_count = {"n": 0}

    class _RecordingWriter:
        def reopen(self) -> None:
            call_count["n"] += 1

    reopener = EventLogReopener(writer=_RecordingWriter())
    await reopener.on_rotate()
    assert call_count["n"] == 1
    await reopener.on_rotate()
    assert call_count["n"] == 2


def test_close_after_reopen_closes_new_fd(tmp_path: Path) -> None:
    """close() after a reopen closes the new fd; subsequent append raises."""
    path = tmp_path / "events.jsonl"
    event = _make_event()
    w = EventLogWriter(path)
    try:
        w.reopen()
        w.close()
    finally:
        # Idempotent close — calling again is safe.
        w.close()
    with pytest.raises(EventLogClosedError):
        w.append(event)


def test_reopen_with_empty_buffer_is_a_noop_for_content(tmp_path: Path) -> None:
    """reopen() with no buffered writes leaves the file content unchanged."""
    path = tmp_path / "events.jsonl"
    event = _make_event()
    with EventLogWriter(path) as w:
        w.append(event)
        before_content = path.read_bytes()
        w.reopen()
        after_content = path.read_bytes()
        # No new bytes written by reopen itself; the buffer was empty.
        assert after_content == before_content


def test_reopen_overflow_count_initial_zero(tmp_path: Path) -> None:
    """A freshly-constructed writer reports zero overflow."""
    path = tmp_path / "events.jsonl"
    with EventLogWriter(path) as w:
        assert w.reopen_overflow_count == 0


def test_reopen_window_sequence_buffers_then_flushes(tmp_path: Path) -> None:
    """End-to-end: enter reopen window, queue writes, exit window via reopen()."""
    path = tmp_path / "events.jsonl"
    event = _make_event()
    with EventLogWriter(path) as w:
        # Pre-window write — goes directly to fd.
        w.append(event)
        # Enter the reopen window.
        w._reopening = True  # type: ignore[reportPrivateUsage]
        w.append(event)
        w.append(event)
        assert len(w._reopen_buffer) == 2  # type: ignore[reportPrivateUsage]
        # Exit the window via reopen() which flushes the buffer.
        w.reopen()
        assert len(w._reopen_buffer) == 0  # type: ignore[reportPrivateUsage]
        # Post-window write — goes directly to fd again.
        w.append(event)
    # Total: 1 pre-window + 2 buffered + 1 post-window = 4 lines.
    assert len(path.read_bytes().splitlines()) == 4
