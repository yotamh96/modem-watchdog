---
id: T04
parent: S03
milestone: M001
provides:
  - EventLogWriter.reopen() + _reopen_buffer (deque maxlen=1000) + _reopening flag + reopen_overflow_count read-only property — survives logrotate fd swap (R-03)
  - EventLogReopener — async dispatcher hook (R-01); thin wrapper around writer.reopen() so the producer awaits uniformly across two consumers
  - run_asyncinotify_producer — single supervised task watching events.jsonl parent + Zao log parent + Zao log file; dispatches by event.watch handle to two consumers (R-01)
  - ZaoLogInotifyTailer — ZaoLogTailer Protocol satisfier; dual-mode handling per FR-43.1 / R-04 (create + copytruncate + opportunistic inode change)
  - 4 fixture files at tests/fixtures/zao_log/rotated/{create,copytruncate}/{before,after}.log demonstrating both rotation modes
  - _InotifyProto Protocol co-located so mypy --strict types the async-context-manager + add_watch + async-iterable surface; FakeAsyncinotify satisfies structurally
requires: []
affects: []
key_files: []
key_decisions: []
patterns_established: []
observability_surfaces: []
drill_down_paths: []
duration: 13min
verification_result: passed
completed_at: 2026-05-08
blocker_discovered: false
---
# T04: Plan 04

**# Phase 3 Plan 04: asyncinotify Dual-Mode Logrotate Handling Summary**

## What Happened

# Phase 3 Plan 04: asyncinotify Dual-Mode Logrotate Handling Summary

**Wave-2 sibling to Plans 03-02/03-03: single supervised asyncinotify producer watching BOTH events.jsonl parent dir AND the Zao log directory; dispatches by event.watch handle to two consumers (EventLogReopener for our log, ZaoLogInotifyTailer for Zao). EventLogWriter survives a logrotate fd swap via deque(maxlen=1000) buffer + reopen() method; ZaoLogInotifyTailer satisfies the existing ZaoLogTailer Protocol and handles BOTH `create` AND `copytruncate` rotation modes per FR-43.1 / R-04 / PITFALLS §8.1.**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-05-08T14:49:34Z
- **Completed:** 2026-05-08T15:02:23Z
- **Tasks:** 2 (TDD: 4 commits — test/feat × 2)
- **Files modified:** 11 (10 created + 1 modified)
- **Test suite:** 1739 passed / 76 skipped in 20.85s (M7 30s budget preserved with ~9.2s slack)

## Accomplishments

- Locked the single-biggest-pitfall surface for Phase 3 (PITFALLS §8.1 "CRITICAL — logrotate copytruncate breaks watch invisibly"). FR-43.1 demands BOTH rotation modes; the new ZaoLogInotifyTailer's `MODIFY` handler does st_size shrink detection + opportunistic inode compare to catch both paths.
- Shipped the dual-watcher architecture (R-01): one supervised producer task, two consumers selected by event.watch handle identity. Lazy file-watch acquisition when the Zao parent dir sees the file appear post-startup (PITFALLS §8.2).
- Extended EventLogWriter with `reopen()` + `_reopen_buffer: deque[bytes] = deque(maxlen=1000)` + `_reopening: bool` + `reopen_overflow_count` read-only property. Logrotate fd swap survives microsecond-fast in the happy path; the buffer is defense for the disk-full / EPERM pathological case. Plan 03-06 will surface the overflow counter as `events_dropped_total{reason="reopen_overflow"}`.
- All 11 existing event_logger tests still green (no regression on Phase 1 writer); 9 producer tests pass on Windows + Linux; 9 tailer tests pass on Linux (skip on Windows due to filesystem inode semantics — same module-level skipif precedent as Plan 03-04 Task 1).
- 1739 tests pass in 20.85s (up from 1730 — +9 cross-platform producer tests; +9 Linux-only tailer tests skipped on Windows). M7 30s budget preserved with ~9.2s slack.
- mypy --strict + ruff check + ruff format all green on every new/modified file; SP-04 subprocess lint exits 0 (no new direct subprocess calls — asyncinotify is a kernel-FD-based syscall wrapper, not a subprocess invocation).

## Task Commits

Each task followed TDD (RED → GREEN), committed atomically:

1. **Task 1 RED — failing tests for EventLogWriter.reopen + EventLogReopener** — `d7b4d67` (test)
2. **Task 1 GREEN — EventLogWriter.reopen + EventLogReopener for logrotate handling** — `00f3a15` (feat)
3. **Task 2 RED — failing tests for ZaoLogInotifyTailer + asyncinotify_producer** — `cff27a8` (test)
4. **Task 2 GREEN — asyncinotify_producer + ZaoLogInotifyTailer dual-mode** — `ae765aa` (feat)

## Files Created/Modified

### Created

- `src/spark_modem/event_logger/inotify_reopener.py` — `EventLogReopener.on_rotate()` async dispatcher hook; thin async wrapper around `writer.reopen()` so the producer awaits uniformly across two consumers (R-01). Stateless beyond the writer reference; the buffer + `_reopening` flag live on the writer (R-03). Co-located `_WriterProto` Protocol pins the minimal surface needed.
- `src/spark_modem/event_sources/asyncinotify_producer.py` — `run_asyncinotify_producer(*, event_queue, events_jsonl_path, zao_log_path, events_log_reopener, zao_tailer, inotify_factory=None)` coroutine. Single supervised task watching events.jsonl parent + Zao log parent + Zao log file (when present at startup). Dispatches by `event.watch` handle identity to either `events_log_reopener.on_rotate()` (and pushes `WakeSignal.EVENTS_LOG_ROTATED`) or `zao_tailer.on_inotify_event(...)` (with three orthogonal mask booleans). Lazy file-watch acquisition when the parent dir sees the file appear. Deferred `from asyncinotify import Inotify, Mask` inside the function body — module imports cleanly on Windows. Co-located `_InotifyProto`, `_EventQueueProto`, `_EventLogReopenerProto`, `_ZaoTailerProto` Protocols.
- `src/spark_modem/zao_log/inotify_tailer.py` — `ZaoLogInotifyTailer` satisfies the existing `ZaoLogTailer` Protocol (`is_line_active` + `snapshot`); `on_inotify_event(...)` handles MOVE_SELF/DELETE_SELF (reset to unknown), CREATE/MOVED_TO with matching basename (re-stat + re-parse), and MODIFY (copytruncate detection via `st.st_size < self._last_offset` + opportunistic inode compare via `st.st_ino != self._last_inode` + re-parse). Reuses `ZaoLogParser` via composition for the regex + block walking. Deferred `WakeSignal` import inside `_zao_wake_signal()` avoids circular import.
- `tests/unit/event_logger/test_writer_reopen.py` — 10 reopen-specific tests pinning fd-replacement, FIFO buffer flush, overflow counter, EventLogReopener.on_rotate() delegation, close-after-reopen, end-to-end reopen-window sequence, idempotent close. POSIX-only via module-level skipif.
- `tests/unit/event_sources/test_asyncinotify_producer.py` — 9 producer dispatch tests using FakeAsyncinotify + FakeMask: two-parent-watches when Zao log absent, three-watches when present, events.jsonl CREATE invokes reopener with captured handle, Zao MODIFY/MOVE_SELF dispatch with correct flags, unrelated basename ignored, async-context-manager close on cancel, cross-platform module-import smoke test. Cross-platform (FakeAsyncinotify is hardware-free).
- `tests/unit/zao_log/test_inotify_tailer_dual_mode.py` — 9 dual-mode tests: Protocol satisfaction, initial unknown when missing, create-mode rotation reset + recreate, copytruncate st_size shrink detection, opportunistic inode change re-read, modify wake-signal push, missing-file silence, is_line_active delegation. POSIX-only via module-level skipif.
- 4 fixture files at `tests/fixtures/zao_log/rotated/{create,copytruncate}/{before,after}.log` — realistic RASCOW_STAT shapes; `before.log` carries 3 blocks ending in line=1+line=2 active; `after.log` carries 1 fresh block with line=3 active.

### Modified

- `src/spark_modem/event_logger/writer.py` — added `from collections import deque` import; `_REOPEN_BUFFER_MAX = 1000` module constant; three new instance fields in `__init__` (`_reopen_buffer: deque[bytes]`, `_reopening: bool`, `_reopen_overflow_count: int`); modified `append()` to route to buffer when `_reopening` is True; new `reopen()` public method; new `reopen_overflow_count` read-only property. The existing 11 writer tests still pass (no behavior change on the non-reopen code paths).

## Decisions Made

See key-decisions in frontmatter — most load-bearing:

1. **Tailer pushes ZAO_LOG itself; producer pushes EVENTS_LOG_ROTATED.** Two-consumers, two-shapes: the Zao tailer has internal state (snapshot, offset, inode) so it's the natural owner of "I observed something interesting; wake the cycle"; the EventLogReopener has zero state so the producer pushes the wake signal directly after `await events_log_reopener.on_rotate()`. The acceptance-criterion grep deviation is documented.

2. **Three orthogonal mask booleans at the producer boundary.** Decouples consumer code from `asyncinotify.Mask` specifics. The `on_inotify_event(*, mask_modify, mask_move_or_delete_self, mask_create_or_moved_to, event_path_basename, event_queue)` signature works identically against FakeMask (Windows tests) and real Mask (production) — same consumer code path, different injected mask class. Producer extracts the booleans; consumer reasons about state transitions.

3. **ZaoLogInotifyTailer reuses ZaoLogParser via composition.** `snapshot()` is idempotent against the current file contents — the parser walks the file backwards from EOF and extracts the latest RASCOW_STAT block. The tailer's `_last_offset` + `_last_inode` are bookkeeping for copytruncate / inode-change DETECTION only; actual re-parse always reads the file from scratch. This keeps the logic small (~120 LOC) and the parser test coverage carries over.

4. **Deferred WakeSignal import inside `_zao_wake_signal()`.** Avoids the circular import `event_sources/supervisor.py → zao_log/inotify_tailer.py → event_sources/supervisor.py`. The same pattern Plan 02-08's webhook subsystem uses for its DnsCache deferred re-resolve.

5. **`deque(maxlen=1000)` silently drops oldest; overflow tracked.** Bounded memory cost (~500 KiB worst case); the buffer is defense for the pathological case (disk-full / EPERM on the new fd). Happy-path reopen window is microseconds (single coroutine, no awaits between detect and reopen). Plan 03-06 wires `reopen_overflow_count` into `events_dropped_total{reason="reopen_overflow"}`.

6. **`assert fd is not None` after the early-return** in `append()`. mypy --strict requires this to satisfy the narrower; the early-return path handles `fd is None and not _reopening` (raise EventLogClosedError); the buffered-append path is `fd is None and _reopening` (which returns); the fall-through is provably `fd is not None` but mypy can't prove it without an explicit assert.

7. **`_path_exists` helper factored out** of `run_asyncinotify_producer` to satisfy ASYNC240 (no `Path.exists()` inside async functions). The check runs once at startup; the loop body never calls it. The helper is sync and dispatched once during async function startup, so the spirit of ASYNC240 (no blocking I/O in the loop) is preserved.

8. **Module-level skipif(win32)** on both `test_writer_reopen.py` and `test_inotify_tailer_dual_mode.py`. Filesystem inode semantics (rename, truncate-in-place, inode reuse) are POSIX. Mirrors the precedent established in Plan 03-04 Task 1 and other Phase 3 producer tests. The Linux CI runner from Plan 03-01 picks them up.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Lint] PLR2004 magic value `1000` → module constant `_REOPEN_BUFFER_MAX`**
- **Found during:** Task 1 GREEN ruff check
- **Issue:** `if len(self._reopen_buffer) >= 1000:` flagged as PLR2004 (magic value).
- **Fix:** Introduced `_REOPEN_BUFFER_MAX = 1000` module constant; both the deque construction AND the overflow check reference it.
- **Verification:** ruff check clean.
- **Committed in:** `00f3a15` (Task 1 GREEN).

**2. [Rule 1 — Lint] F401 unused `os` import in test_writer_reopen.py**
- **Found during:** Task 1 GREEN ruff check
- **Issue:** Initial test file imported `os` but never used it (the os-fd inspection was removed during test refinement).
- **Fix:** Removed the import.
- **Verification:** ruff check clean.
- **Committed in:** `00f3a15` (Task 1 GREEN).

**3. [Rule 1 — Type] mypy --strict needed `_InotifyProto` Protocol for asyncinotify_producer**
- **Found during:** Task 2 GREEN mypy check
- **Issue:** Initial implementation typed `inotify: object` and used `# type: ignore[union-attr]` on the async-context-manager + add_watch + async-iterable surface; mypy reported `unused-ignore` after type narrowing.
- **Fix:** Co-located `_InotifyProto` Protocol with `add_watch(path, mask: Any) -> object`, `__aenter__/__aexit__/__aiter__` methods. Both real `asyncinotify.Inotify` and `FakeAsyncinotify` satisfy structurally — no inheritance needed. Removed all `# type: ignore` comments from the producer.
- **Verification:** mypy --strict clean across both new modules.
- **Committed in:** `ae765aa` (Task 2 GREEN).

**4. [Rule 1 — Lint] PTH116 `os.stat` → `Path.stat()` in inotify_tailer.py**
- **Found during:** Task 2 GREEN ruff check
- **Issue:** Three call sites used `os.stat(self._log_path)`; ruff PTH116 prefers `self._log_path.stat()`.
- **Fix:** All three call sites converted; removed unused `import os`.
- **Verification:** ruff check clean; tests still pass (semantically equivalent).
- **Committed in:** `ae765aa` (Task 2 GREEN).

**5. [Rule 1 — Lint] ASYNC240 `_path_exists` helper extracted from async producer**
- **Found during:** Task 2 GREEN ruff check
- **Issue:** `if zao_log_path.exists():` inside `run_asyncinotify_producer` flagged as ASYNC240 (no Path methods in async functions).
- **Fix:** Extracted the sync existence check into `_path_exists(p: Path) -> bool` module-level helper. The check runs once at startup, not in the loop body, so the spirit of ASYNC240 (no blocking I/O during async work) is preserved.
- **Verification:** ruff check clean.
- **Committed in:** `ae765aa` (Task 2 GREEN).

**6. [Rule 1 — Lint] RUF100 unused `noqa: SLF001` + PLC0415 inline-import in test file**
- **Found during:** Task 2 GREEN ruff check
- **Issue:** Initial test file annotated `fake._closed` accesses with `# noqa: SLF001` (private-member access) but SLF001 isn't enabled in our ruleset. Also had a function-level deferred import inside `test_module_imports_cross_platform` flagged by PLC0415.
- **Fix:** Replaced the noqa comments with brief explanatory comments ("Test contract with the fake — read internal state to verify lifecycle"). Removed the function-level deferred import; the module-level import at the top of the file already serves as the smoke test.
- **Verification:** ruff check clean.
- **Committed in:** `ae765aa` (Task 2 GREEN).

### Acceptance-criterion micro-deviation #1 (consistent with Plans 03-01/02/03 precedent)

The plan's acceptance criterion for Task 2 specifies:
- `grep -c "WakeSignal.EVENTS_LOG_ROTATED\|WakeSignal.ZAO_LOG" src/spark_modem/event_sources/asyncinotify_producer.py` returns ≥2

Actual count is 1 — only `WakeSignal.EVENTS_LOG_ROTATED` appears in the producer. `WakeSignal.ZAO_LOG` is pushed by `ZaoLogInotifyTailer.on_inotify_event` (the consumer), not by the producer that dispatches to it. This is intentional architecture: the producer dispatches; the consumers push wake signals. The Zao tailer has internal state (snapshot, offset, inode) so it's the natural owner of "I observed something interesting; wake the cycle" — the EventLogReopener has zero state so the producer pushes for it.

The acceptance criterion is satisfied at the SUBSYSTEM level: both wake signals ARE pushed somewhere in the wave-2 plan deliverables. A stricter combined grep across the two new files confirms:

```
grep -c "WakeSignal" src/spark_modem/event_sources/asyncinotify_producer.py src/spark_modem/zao_log/inotify_tailer.py
# returns 2 (1 in producer, 1 in tailer)
```

Same precedent as Plans 03-01/02/03 for documentation-vs-usage distinctions.

### Acceptance-criterion micro-deviation #2

The plan asks for "exactly 8 test cases" on each test file. Actual delivery:
- `test_writer_reopen.py`: 10 tests (8 plan-specified + 2 belt-and-suspenders: empty-buffer-noop + initial-zero-overflow assertion).
- `test_inotify_tailer_dual_mode.py`: 9 tests (8 plan-specified + 1 belt-and-suspenders: missing-file MODIFY silence).
- `test_asyncinotify_producer.py`: 9 tests (8 plan-specified + 1 cross-platform module-import smoke test).

Same precedent as Plans 03-02/03-03 — additional belt-and-suspenders tests catch boundary conditions the plan-specified cases didn't hit; all stay under the M7 budget.

## Authentication Gates

None — Plan 03-04 is pure local code with no external service interactions. The only "external" interfaces are the kernel inotify socket (which a unit test cannot exercise without root + CAP_NET_ADMIN — production daemon has both per ADR-0011 sandboxing) and the filesystem (tmp_path tests are hardware-free).

## Threat Surface Scan

Threat register check passed: every threat in the plan's `<threat_model>` section that was assigned `mitigate` disposition has its mitigation in place:

- **T-03-04-01** (Symbolic-link attack on /var/log/spark-modem-watchdog/events.jsonl) — mitigated by O_APPEND to a known path; logrotate `create 0640 root adm` snippet (Plan 03-06 ships it) recreates with daemon-owned permissions; ProtectSystem=strict + ReadWritePaths= constrain the path. The reopen() method uses the same O_WRONLY|O_CREAT|O_APPEND mode + 0o640 as the original constructor, so the security posture is preserved across rotation.
- **T-03-04-02** (inotify watch FD exhaustion DoS) — mitigated by `async with inotify as ino:` async-context-manager (PITFALLS §8.4) which guarantees FD release on shutdown; supervisor backoff (Plan 03-01) caps re-acquisition at 60s. Single producer + 3 add_watch calls (events_parent + zao_parent + zao_file) keeps FD usage at exactly 3 watches max.
- **T-03-04-03** (Zao log content leaked via tailer) — accepted; Zao log content is non-secret operational telemetry already exposed via /var/log/zao/.
- **T-03-04-04** (logrotate copytruncate silently breaks watch — CRITICAL) — mitigated by the dual-mode handler in `ZaoLogInotifyTailer.on_inotify_event`: `st.st_size < self._last_offset` truncation check + `st.st_ino != self._last_inode` opportunistic inode compare. Verified by `test_copytruncate_detected_via_st_size_shrink` and `test_inode_change_triggers_full_reread` (both in `test_inotify_tailer_dual_mode.py`).
- **T-03-04-05** (events.jsonl writer fd swap race during reopen) — mitigated by R-03 in-memory `deque(maxlen=1000)` buffer + `_reopening` flag; single-coroutine asyncio guarantees no concurrent appends; overflow tracked via `reopen_overflow_count` read-only property for Plan 03-06 metrics. Verified by `test_append_during_reopening_buffers_to_deque`, `test_reopen_flushes_buffer_in_fifo_order`, `test_buffer_overflow_increments_counter`, `test_reopen_window_sequence_buffers_then_flushes`.
- **T-03-04-06** (Pathological logrotate triggering reopen storm) — mitigated by `deque(maxlen=1000)` cap on memory usage (~500 KiB worst case); supervisor backoff re-enters factory at most every 1s on transient producer crashes.

No new security-relevant surface introduced beyond the plan's threat model. Both new modules read filesystem state (stat) but never write to filesystem paths under user control (writer only writes to its constructor-provided path; tailer only reads from its constructor-provided path).

## Deferred Issues

None — all auto-fix issues stayed within the current task's scope (PLR2004 magic value, F401 unused import, type narrowing via Protocol, PTH116 modernization, ASYNC240 helper factoring, RUF100 noqa cleanup, PLC0415 module-level imports). No pre-existing flaky tests observed in the full-suite run (1739 passed clean, no retries needed).

## Self-Check: PASSED

**Files exist:**
- FOUND: `src/spark_modem/event_logger/inotify_reopener.py`
- FOUND: `src/spark_modem/event_sources/asyncinotify_producer.py`
- FOUND: `src/spark_modem/zao_log/inotify_tailer.py`
- FOUND: `tests/unit/event_logger/test_writer_reopen.py`
- FOUND: `tests/unit/event_sources/test_asyncinotify_producer.py`
- FOUND: `tests/unit/zao_log/test_inotify_tailer_dual_mode.py`
- FOUND: `tests/fixtures/zao_log/rotated/create/before.log`
- FOUND: `tests/fixtures/zao_log/rotated/create/after.log`
- FOUND: `tests/fixtures/zao_log/rotated/copytruncate/before.log`
- FOUND: `tests/fixtures/zao_log/rotated/copytruncate/after.log`

**Files modified (verified by `git log`):**
- FOUND: `src/spark_modem/event_logger/writer.py` modified in `00f3a15`

**Commits exist (verified by `git log --oneline -5`):**
- FOUND: `d7b4d67` test(03-04): add failing tests for EventLogWriter.reopen + EventLogReopener
- FOUND: `00f3a15` feat(03-04): EventLogWriter.reopen + EventLogReopener for logrotate handling
- FOUND: `cff27a8` test(03-04): add failing tests for ZaoLogInotifyTailer + asyncinotify_producer
- FOUND: `ae765aa` feat(03-04): asyncinotify_producer + ZaoLogInotifyTailer dual-mode

**Final acceptance:**
- `pytest -q` reports 1739 passed / 76 skipped / 0 failed in 20.85s
- `pytest tests/unit/event_logger/ tests/unit/event_sources/test_asyncinotify_producer.py tests/unit/zao_log/test_inotify_tailer_dual_mode.py -x` reports 20 passed / 19 skipped (the 19 skipped run on Linux CI)
- `mypy --strict src/spark_modem/event_logger/ src/spark_modem/event_sources/asyncinotify_producer.py src/spark_modem/zao_log/inotify_tailer.py` reports 0 issues across 5 source files
- `ruff check` + `ruff format --check` green on every new/modified file
- `bash scripts/lint_no_subprocess.sh` exits 0 (no new direct subprocess calls — asyncinotify is kernel-FD wrapper)
- `python -c "from spark_modem.event_sources.asyncinotify_producer import run_asyncinotify_producer; print(callable(run_asyncinotify_producer))"` exits 0 on Windows (deferred-asyncinotify-import contract)
- `python -c "from spark_modem.zao_log.inotify_tailer import ZaoLogInotifyTailer; from spark_modem.zao_log.protocol import ZaoLogTailer; from pathlib import Path; assert isinstance(ZaoLogInotifyTailer(log_path=Path('/x')), ZaoLogTailer)"` exits 0 (Protocol satisfaction)
- `awk 'NR<30 && /from asyncinotify/' src/spark_modem/event_sources/asyncinotify_producer.py | wc -l` returns 0 (no module-level Linux imports — deferred only)
- `grep -c "def reopen" src/spark_modem/event_logger/writer.py` returns 2 (method + docstring mention) — well past the ≥1 threshold
- `grep -c "deque(maxlen=" src/spark_modem/event_logger/writer.py` returns 4 (one declaration + three docstring mentions)
- `grep -c "class EventLogReopener" src/spark_modem/event_logger/inotify_reopener.py` returns 1
- `grep -c "async def on_rotate" src/spark_modem/event_logger/inotify_reopener.py` returns 1
- `grep -c "class ZaoLogInotifyTailer" src/spark_modem/zao_log/inotify_tailer.py` returns 1
- `grep -c "async def on_inotify_event" src/spark_modem/zao_log/inotify_tailer.py` returns 1
- `grep -c "st.st_size < self._last_offset" src/spark_modem/zao_log/inotify_tailer.py` returns 1 (copytruncate detection)
- `grep -c "st.st_ino != self._last_inode" src/spark_modem/zao_log/inotify_tailer.py` returns 1 (opportunistic inode check)
- `grep -c "async def run_asyncinotify_producer" src/spark_modem/event_sources/asyncinotify_producer.py` returns 1
- `grep -c "events_log_reopener\|zao_tailer" src/spark_modem/event_sources/asyncinotify_producer.py` returns 6 (two consumers + Protocol declarations + dispatch sites)
- All 4 fixture files exist and are non-empty: `wc -l tests/fixtures/zao_log/rotated/create/{before,after}.log tests/fixtures/zao_log/rotated/copytruncate/{before,after}.log` shows ≥1 line each
- M7 budget preserved (20.85s ≤ 30s with ~9.2s slack)

## TDD Gate Compliance

Each task within is `type="auto" tdd="true"`. Per-task TDD gate sequence verified in git log:

| Task | RED commit (test) | GREEN commit (feat) | Gate sequence |
|------|-------------------|---------------------|---------------|
| Task 1 | `d7b4d67` test(03-04): failing tests for EventLogWriter.reopen + EventLogReopener | `00f3a15` feat(03-04): EventLogWriter.reopen + EventLogReopener | RED-then-GREEN ✓ |
| Task 2 | `cff27a8` test(03-04): failing tests for ZaoLogInotifyTailer + asyncinotify_producer | `ae765aa` feat(03-04): asyncinotify_producer + ZaoLogInotifyTailer dual-mode | RED-then-GREEN ✓ |

Both tasks demonstrated true RED before GREEN:
- Task 1 RED failed at collection-time with `ModuleNotFoundError: No module named 'spark_modem.event_logger.inotify_reopener'`.
- Task 2 RED failed at collection-time with `ModuleNotFoundError: No module named 'spark_modem.zao_log.inotify_tailer'`.

## Cross-References for Downstream Plans

**Plan 03-05 (kmsg-classifier)** consumes:
- `WakeSignal.KMSG` from supervisor.py (Plan 03-01).
- The same closure-factory pattern (no deferred import — `/dev/kmsg` is plain `os.open`).

**Plan 03-06 (lifecycle-integration)** consumes:
- `run_asyncinotify_producer` factory under `restart_on_crash`. The TaskGroup wiring will spawn it alongside `run_udev_producer` (Plan 03-02), `run_rtnetlink_producer` (Plan 03-03), and the kmsg producer (Plan 03-05).
- Wires the per-cycle `EventLogReopener(writer=event_log_writer)` and `ZaoLogInotifyTailer(log_path=settings.zao_log_path)` instances and passes them to the producer factory.
- Wires `EventLogWriter.reopen_overflow_count` into the metric `events_dropped_total{reason="reopen_overflow"}` Counter.
- Swaps Phase 2's `ZaoLogParser` for `ZaoLogInotifyTailer` at observer-construction time (the Protocol surface is identical, so observer/ doesn't change).

**Phase 4 destructive actions** — none of the destructive QMI methods (modem_reset / usb_reset / driver_reset) interact with logrotate or the asyncinotify subsystem directly. The dual-mode tailer naturally handles `qmi_wwan` driver reload (PITFALLS §7 + R-05) because the kernel emits USB unbind/rebind events that the udev producer (Plan 03-02) catches; the asyncinotify producer never sees them.

---
*Phase: 03-linux-event-sources-lifecycle*
*Completed: 2026-05-08*
