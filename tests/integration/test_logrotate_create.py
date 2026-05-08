"""FR-43 / R-02 — real logrotate cron exercise on Linux runners.

Linux-only because ``/usr/sbin/logrotate`` is a POSIX binary that the
.deb depends on. Uses real ``EventLogWriter`` + ``EventLogReopener``;
only the cycle scheduler / clock are faked.

PITFALLS §8.1 dual-mode coverage: this test exercises ``create`` mode
end-to-end. ``copytruncate`` mode is covered by the unit test
``tests/unit/zao_log/test_inotify_tailer_dual_mode.py`` +
``tests/unit/event_logger/test_writer_reopen.py`` (Plan 03-04). This
integration test additionally pins the wired-up version: real
logrotate writes a real log file, real EventLogReopener re-opens
the writer.

The .deb's logrotate snippet at
``debian/spark-modem-watchdog.logrotate`` (Plan 03-08 R-02) is the
production contract; this test mirrors that snippet's directives in
a tmp-bound config.

Module-level pytestmark = [linux_only, asyncio]: the linux_only suite
gate plus the per-test ``skipif(/usr/sbin/logrotate missing)`` cover
Linux dev hosts that don't have logrotate installed.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

from spark_modem.event_logger.inotify_reopener import EventLogReopener
from spark_modem.event_logger.writer import EventLogWriter
from spark_modem.wire.events import DaemonStarted

pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="logrotate is a POSIX binary; production target is Linux/aarch64",
    ),
    pytest.mark.asyncio,
]

_LOGROTATE_BIN = "/usr/sbin/logrotate"


@pytest.mark.skipif(
    not Path(_LOGROTATE_BIN).exists(),
    reason=f"{_LOGROTATE_BIN} not available on this Linux runner",
)
async def test_logrotate_force_rotation_triggers_writer_reopen(tmp_path: Path) -> None:
    """logrotate -f rotates events.jsonl in `create` mode; writer.reopen runs.

    1. Set up real events.jsonl + a tmp logrotate config matching
       ``debian/spark-modem-watchdog.logrotate`` (Plan 03-08 R-02).
    2. Force logrotate to run NOW with ``-f`` (skips daily/size gates).
    3. Invoke ``EventLogReopener.on_rotate()`` — production path.
    4. Append a new event; assert it lands in the freshly-created
       ``events.jsonl`` (NOT the rotated archive).
    """
    log_dir = tmp_path / "log"
    log_dir.mkdir()
    events_path = log_dir / "events.jsonl"

    # Build the writer FIRST so the inode it holds is the one logrotate
    # rotates. Seed an entry so notifempty doesn't suppress rotation.
    writer = EventLogWriter(events_path)
    try:
        writer.append(
            DaemonStarted(
                ts_iso="2026-05-08T00:00:00+00:00",
                version="2.0.0",
                bundled_python_version="3.12.13",
            ),
        )
        initial_fd = writer.fileno()

        # `create 0640 USER USER` directive: use real runner identity so
        # `chown` inside logrotate works on dev hosts without root.
        # `getlogin` may raise on CI runners with no controlling tty —
        # fall back to whoami via os.environ.
        owner = os.environ.get("USER", "root")

        conf_path = tmp_path / "logrotate.conf"
        conf_path.write_text(
            f"""\
{events_path} {{
    daily
    rotate 7
    missingok
    notifempty
    sharedscripts
    create 0640 {owner} {owner}
    postrotate
        # Empty per R-02 — daemon's asyncinotify producer detects via
        # parent-dir watch and calls EventLogWriter.reopen() autonomously.
    endscript
}}
""",
            encoding="utf-8",
        )
        state_path = tmp_path / "logrotate.state"

        # Force rotation regardless of size/age. logrotate creates the new
        # file via the `create` directive AND moves the old one out of the
        # way; the writer's fd still points at the rotated inode until
        # reopen() runs.
        #
        # subprocess.run is wrapped in asyncio.to_thread to satisfy
        # ASYNC221 (no blocking subprocess calls inside async coroutines).
        # tests/ is exempt from the SP-04 lint that bans subprocess.run
        # outside src/spark_modem/subproc/, so this direct call is OK at
        # the integration tier.
        result = await asyncio.to_thread(
            subprocess.run,
            [
                _LOGROTATE_BIN,
                "-f",
                "-s",
                str(state_path),
                str(conf_path),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=10.0,
        )
        assert result.returncode == 0, (
            f"logrotate failed: stdout={result.stdout!r} stderr={result.stderr!r}"
        )

        # Assertion 1: rotated archive exists (logrotate moved the old file).
        rotated_candidates = list(log_dir.glob("events.jsonl.*"))
        assert rotated_candidates, "logrotate did not produce a rotated file"

        # Assertion 2: events_path exists (logrotate `create` recreated it).
        assert events_path.exists(), "logrotate `create` should re-create events.jsonl"

        # Production dispatch: asyncinotify producer would have called this
        # on observing the rotation. We invoke directly so this test stays
        # focused on logrotate-vs-writer interaction (Plan 03-04 already
        # exercises the inotify dispatch path with FakeAsyncinotify).
        reopener = EventLogReopener(writer=writer)
        await reopener.on_rotate()

        new_fd = writer.fileno()
        assert new_fd != initial_fd, "writer.reopen should swap the fd after logrotate rename"

        # Assertion 3: subsequent append lands in the NEW file, not the
        # rotated archive (R-03 buffer flush correctness).
        writer.append(
            DaemonStarted(
                ts_iso="2026-05-08T00:01:00+00:00",
                version="2.0.0",
                bundled_python_version="3.12.13",
            ),
        )

        # The post-rotation event should appear in events_path but NOT in
        # any rotated archive (logrotate moved the OLD content).
        new_text = events_path.read_bytes()
        assert new_text.count(b"daemon_started") >= 1, (
            "post-rotation append should be in the new events.jsonl"
        )
        for archive in rotated_candidates:
            archive_text = archive.read_bytes()
            assert archive_text.count(b"2026-05-08T00:01:00") == 0, (
                f"post-rotation event should NOT appear in archive {archive}"
            )
    finally:
        writer.close()
