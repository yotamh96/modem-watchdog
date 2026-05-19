# T04: Plan 04

**Slice:** S03 — **Milestone:** M001

## Description

Wave 2 — asyncinotify-backed log rotation handling for BOTH our own
events.jsonl (R-01/R-03) AND the Zao log we don't own (R-04 / FR-43.1
dual-mode).

Specifically:

  1. Extend `event_logger/writer.py` with `reopen()` + `_reopen_buffer:
     deque[bytes] = deque(maxlen=1000)` + `_reopening: bool` flag
     (R-03). When `_reopening=True`, `append()` writes to the deque
     instead of fd; `reopen()` closes old fd, opens new, flushes
     deque in order.
  2. Create `event_logger/inotify_reopener.py` —
     `EventLogReopener.on_rotate()` async method that calls
     `writer.reopen()`. Consumed by the asyncinotify producer.
  3. Create `event_sources/asyncinotify_producer.py` — ONE supervised
     producer task that watches BOTH `/var/log/spark-modem-watchdog/`
     parent dir AND the Zao log directory; dispatches on
     `event.watch` to either `EventLogReopener.on_rotate()` or
     `ZaoLogInotifyTailer.on_inotify_event(event)`. Pushes
     `WakeSignal.EVENTS_LOG_ROTATED` and `WakeSignal.ZAO_LOG`
     respectively to the cycle's event_queue.
  4. Create `zao_log/inotify_tailer.py` —
     `ZaoLogInotifyTailer` satisfying the existing `ZaoLogTailer`
     Protocol (`is_line_active`, `snapshot`). Replaces
     `parser.py` as the runtime tailer; `parser.py` stays as the
     test/replay helper (the regex + RASCOW_STAT block logic is
     reused directly). Implements both rotation modes per
     PITFALLS §8.1 / R-04: copytruncate (st_size truncation) +
     create-mode (parent-dir CREATE/MOVED_TO).
  5. Test fixtures: `tests/fixtures/zao_log/rotated/{create,
     copytruncate}/{before,after}.log` — two RASCOW_STAT scenarios
     so the dual-mode test exercises both code paths against real
     log content shapes.
  6. Three new test files: writer.reopen behavior; producer
     dispatch shape; tailer dual-mode behavior.

Purpose: The single biggest pitfall surface in Phase 3 (PITFALLS §8.1
"CRITICAL — logrotate copytruncate breaks watch invisibly"). FR-43.1
demands BOTH modes. Single plan owns the entire inotify subsystem so
the dual-watcher architecture (R-01 — one producer, two consumers)
ships as a coherent unit.

Output: 3 new production files + 1 modified production file + 3 new
test files + 4 new fixture files.
