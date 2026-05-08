"""ZaoLogInotifyTailer dual-mode (create + copytruncate) tests (Plan 03-04 / R-04).

PITFALLS §8.1 prescription: BOTH `create` mode (MOVE_SELF/DELETE_SELF +
parent-dir CREATE/MOVED_TO) AND `copytruncate` mode (st_size shrink +
opportunistic inode compare) must be handled. FR-43.1 demands both code
paths exist and are exercised.

These tests are POSIX-only at module level — they exercise filesystem
inode semantics (rename, truncate-in-place, inode reuse) that Windows
doesn't model the same way.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from spark_modem.event_sources.supervisor import WakeSignal
from spark_modem.zao_log.inotify_tailer import ZaoLogInotifyTailer
from spark_modem.zao_log.protocol import ZaoLogTailer

if TYPE_CHECKING:
    pass

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="filesystem inode semantics POSIX",
)

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "zao_log" / "rotated"


class _RecordingQueue:
    """Tiny stand-in for asyncio.Queue exposing only put_nowait."""

    def __init__(self) -> None:
        self.items: list[object] = []

    def put_nowait(self, item: object) -> None:
        self.items.append(item)


def test_satisfies_zao_log_tailer_protocol() -> None:
    """ZaoLogInotifyTailer is a structural ZaoLogTailer."""
    tailer = ZaoLogInotifyTailer(log_path=Path("/nonexistent"))
    assert isinstance(tailer, ZaoLogTailer)


def test_initial_state_unknown_when_file_missing(tmp_path: Path) -> None:
    """Constructor on a missing file yields snapshot.unknown_reason='zao_log_missing'."""
    tailer = ZaoLogInotifyTailer(log_path=tmp_path / "missing.log")
    snap = tailer.snapshot()
    assert snap.unknown_reason == "zao_log_missing"
    assert snap.active_lines == frozenset()


@pytest.mark.asyncio
async def test_create_mode_rotation_resets_state(tmp_path: Path) -> None:
    """MOVE_SELF / DELETE_SELF makes the tailer go back to unknown."""
    log = tmp_path / "zao.log"
    shutil.copy(_FIXTURES / "create" / "before.log", log)
    tailer = ZaoLogInotifyTailer(log_path=log)
    # Pre-rotation state reflects before.log content.
    assert 1 in tailer.snapshot().active_lines
    assert 2 in tailer.snapshot().active_lines

    queue = _RecordingQueue()
    await tailer.on_inotify_event(
        mask_modify=False,
        mask_move_or_delete_self=True,
        mask_create_or_moved_to=False,
        event_path_basename=None,
        event_queue=queue,
    )
    assert tailer.snapshot().unknown_reason == "zao_log_missing"
    assert queue.items == [WakeSignal.ZAO_LOG]


@pytest.mark.asyncio
async def test_create_mode_recreate_picks_up_new_content(tmp_path: Path) -> None:
    """After the file reappears, IN_CREATE/MOVED_TO triggers a re-read."""
    log = tmp_path / "zao.log"
    shutil.copy(_FIXTURES / "create" / "before.log", log)
    tailer = ZaoLogInotifyTailer(log_path=log)
    queue = _RecordingQueue()

    # Simulate rotation: file goes away.
    await tailer.on_inotify_event(
        mask_modify=False,
        mask_move_or_delete_self=True,
        mask_create_or_moved_to=False,
        event_path_basename=None,
        event_queue=queue,
    )
    assert tailer.snapshot().unknown_reason == "zao_log_missing"
    queue.items.clear()

    # logrotate's `create` then writes new content; we replace the file.
    log.unlink()
    shutil.copy(_FIXTURES / "create" / "after.log", log)

    # Producer fires CREATE/MOVED_TO with the basename matching.
    await tailer.on_inotify_event(
        mask_modify=False,
        mask_move_or_delete_self=False,
        mask_create_or_moved_to=True,
        event_path_basename=log.name,
        event_queue=queue,
    )
    snap = tailer.snapshot()
    assert snap.unknown_reason is None
    # after.log shows line=3 active only.
    assert snap.active_lines == frozenset({3})
    assert queue.items == [WakeSignal.ZAO_LOG]


@pytest.mark.asyncio
async def test_copytruncate_detected_via_st_size_shrink(tmp_path: Path) -> None:
    """copytruncate keeps the inode but truncates content; st_size shrinks."""
    log = tmp_path / "zao.log"
    shutil.copy(_FIXTURES / "copytruncate" / "before.log", log)
    tailer = ZaoLogInotifyTailer(log_path=log)
    # Pre-truncate snapshot reflects before.log: line=1 + line=2 active.
    snap_before = tailer.snapshot()
    assert snap_before.active_lines == frozenset({1, 2})

    # logrotate's copytruncate: copy content elsewhere, then truncate IN PLACE
    # (same inode). We simulate by overwriting the file content while the
    # tailer's _last_offset still points beyond the new size.
    after_content = (_FIXTURES / "copytruncate" / "after.log").read_bytes()
    log.write_bytes(after_content)

    queue = _RecordingQueue()
    await tailer.on_inotify_event(
        mask_modify=True,
        mask_move_or_delete_self=False,
        mask_create_or_moved_to=False,
        event_path_basename=log.name,
        event_queue=queue,
    )
    snap_after = tailer.snapshot()
    # after.log shows line=3 active only.
    assert snap_after.active_lines == frozenset({3})
    assert queue.items == [WakeSignal.ZAO_LOG]


@pytest.mark.asyncio
async def test_inode_change_triggers_full_reread(tmp_path: Path) -> None:
    """Opportunistic inode compare detects an unmissed rotation."""
    log = tmp_path / "zao.log"
    shutil.copy(_FIXTURES / "create" / "before.log", log)
    tailer = ZaoLogInotifyTailer(log_path=log)
    # Establish pre-rotation snapshot.
    assert tailer.snapshot().active_lines == frozenset({1, 2})

    # Replace the file with a different inode (delete + recreate).
    log.unlink()
    shutil.copy(_FIXTURES / "create" / "after.log", log)

    queue = _RecordingQueue()
    await tailer.on_inotify_event(
        mask_modify=True,
        mask_move_or_delete_self=False,
        mask_create_or_moved_to=False,
        event_path_basename=log.name,
        event_queue=queue,
    )
    snap = tailer.snapshot()
    # after.log shows line=3 active.
    assert snap.active_lines == frozenset({3})
    assert queue.items == [WakeSignal.ZAO_LOG]


@pytest.mark.asyncio
async def test_modify_pushes_wake_signal(tmp_path: Path) -> None:
    """A normal MODIFY event pushes exactly one WakeSignal.ZAO_LOG."""
    log = tmp_path / "zao.log"
    shutil.copy(_FIXTURES / "create" / "before.log", log)
    tailer = ZaoLogInotifyTailer(log_path=log)
    queue = _RecordingQueue()

    await tailer.on_inotify_event(
        mask_modify=True,
        mask_move_or_delete_self=False,
        mask_create_or_moved_to=False,
        event_path_basename=log.name,
        event_queue=queue,
    )
    assert queue.items == [WakeSignal.ZAO_LOG]


@pytest.mark.asyncio
async def test_modify_on_missing_file_is_silent(tmp_path: Path) -> None:
    """MODIFY on a vanished file is a no-op (waits for parent-dir CREATE)."""
    tailer = ZaoLogInotifyTailer(log_path=tmp_path / "missing.log")
    queue = _RecordingQueue()
    await tailer.on_inotify_event(
        mask_modify=True,
        mask_move_or_delete_self=False,
        mask_create_or_moved_to=False,
        event_path_basename="missing.log",
        event_queue=queue,
    )
    # No wake signal, no crash, snapshot still unknown.
    assert queue.items == []
    assert tailer.snapshot().unknown_reason == "zao_log_missing"


def test_is_line_active_delegates_to_snapshot(tmp_path: Path) -> None:
    """is_line_active(N) returns True iff snapshot.active_lines contains N."""
    log = tmp_path / "zao.log"
    shutil.copy(_FIXTURES / "create" / "before.log", log)
    tailer = ZaoLogInotifyTailer(log_path=log)
    # before.log: line=1 + line=2 active.
    assert tailer.is_line_active(1) is True
    assert tailer.is_line_active(2) is True
    assert tailer.is_line_active(3) is False
    assert tailer.is_line_active(4) is False
