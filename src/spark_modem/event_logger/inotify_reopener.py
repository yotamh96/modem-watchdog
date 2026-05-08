"""EventLogReopener — async dispatcher hook for the asyncinotify producer.

R-01: when the asyncinotify producer detects an events.jsonl rotation
(IN_CREATE / IN_MOVED_TO on the basename in the parent dir), it calls
``EventLogReopener.on_rotate()`` which in turn calls the writer's
``reopen()`` method.

The producer (Plan 03-04 ``event_sources/asyncinotify_producer.py``) is a
single supervised task watching BOTH the events.jsonl parent dir AND the
Zao log dir; this module is one of the two consumers (the other is
``zao_log/inotify_tailer.py:ZaoLogInotifyTailer``).

The buffer + ``_reopening`` flag live on the writer (R-03), not on this
dispatcher. This module is intentionally thin: it exists so the producer
can dispatch uniformly across two consumers (the Zao tailer's
``on_inotify_event`` is naturally async because it may stat the file; this
async wrapper around ``writer.reopen()`` matches the shape).
"""

from __future__ import annotations

from typing import Protocol


class _WriterProto(Protocol):
    """Minimal writer surface ``EventLogReopener`` needs.

    Production wires ``EventLogWriter``; tests inject any object with a
    ``reopen()`` method.
    """

    def reopen(self) -> None: ...


class EventLogReopener:
    """Calls ``writer.reopen()`` on each rotation event.

    Stateless beyond the writer reference; the buffer + ``_reopening`` flag
    live on the writer (R-03). Concurrency is single-coroutine (the
    asyncinotify producer is one supervised task), so no lock is needed
    here — ``writer.reopen()`` is sync and the producer awaits it.
    """

    def __init__(self, *, writer: _WriterProto) -> None:
        self._writer = writer

    async def on_rotate(self) -> None:
        """Dispatch a rotation signal to the writer.

        We wrap the sync ``writer.reopen()`` in an async signature so the
        asyncinotify producer can ``await`` uniformly across the two
        consumers. The actual reopen work is sync and microseconds-fast in
        the happy path; the await is essentially a noop yield.
        """
        self._writer.reopen()
