---
id: T05
parent: S03
milestone: M001
provides:
  - KMSG_PATTERNS — closed regex catalog (5 entries; LOCKED at table-size via test contract gate); maps to IssueDetail enum via re.IGNORECASE
  - classify(line) -> IssueDetail — first-match-wins; returns IssueDetail.UNKNOWN fallback for unrecognized lines (W-04 closed-enum discipline)
  - KmsgDedup.should_emit(detail, *, now_monotonic) -> bool — per-IssueDetail 30s sliding-window dedup (PITFALLS §13.2); semantics: True == EMIT, False == suppressed; consume_dedup_count(detail) returns + clears suppressed counter
  - run_kmsg_producer coroutine — O_RDONLY|O_NONBLOCK + lseek(SEEK_END) + add_reader pattern; on_readable drain loop classifies + dedups + emits Issue + WakeSignal.KMSG; UNKNOWN suppressed; EPIPE on ring-buffer wrap resets last_seq and continues
  - FakeKmsgReader — dual-surface test fake (production read/fileno + test-only inject_record/inject_raw/inject_oserror mutators); same convention as Phase 3's FakeAsyncinotify / FakeAsyncIPRoute / FakeUdevMonitor
  - fd_factory injection point on run_kmsg_producer — tests pass (fd_sentinel, read_fn) tuple so the producer never opens /dev/kmsg in unit-test paths; production wires None and the module opens /dev/kmsg inside the coroutine
requires: []
affects: []
key_files: []
key_decisions: []
patterns_established: []
observability_surfaces: []
drill_down_paths: []
duration: 9min
verification_result: passed
completed_at: 2026-05-08
blocker_discovered: false
---
# T05: Plan 05

**# Phase 3 Plan 05: kmsg Producer + Closed-Enum Classifier + Per-Detail Dedup Summary**

## What Happened

# Phase 3 Plan 05: kmsg Producer + Closed-Enum Classifier + Per-Detail Dedup Summary

**Wave-2 sibling to Plans 03-03 (rtnetlink) and 03-04 (asyncinotify): non-blocking ``/dev/kmsg`` reader (``O_RDONLY|O_NONBLOCK`` + ``lseek(SEEK_END)`` + ``loop.add_reader``) + closed-enum regex classifier (E-03 LOCKED at 5 host-level IssueDetail values + UNKNOWN) + per-IssueDetail 30s sliding-window dedup (PITFALLS §13.2). Pipeline: drain kernel queue -> parse ``<priority>,<seq>,<ts>,<flags>;<msg>`` header -> ``classify(line) -> IssueDetail`` -> ``dedup.should_emit(detail, now_monotonic) -> bool`` -> if emit: ``issue_emitter.emit_host_issue(detail=, raw_line=)`` + ``event_queue.put_nowait(WakeSignal.KMSG)``. UNKNOWN-classified lines suppressed (W-04 closed-enum discipline). EPIPE on ring-buffer wrap resets ``last_seq`` and continues draining.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-05-08T15:10:26Z
- **Completed:** 2026-05-08T15:19:08Z
- **Tasks:** 2 (TDD: 4 commits — test/feat × 2)
- **Files modified:** 14 (14 created + 0 modified)
- **Test suite:** 1767 passed / 77 skipped in 17.84s (M7 30s budget preserved with ~12.2s slack; up from 1739 — exactly +28 new tests including the linux_only stub)

## Accomplishments

- Locked the FR-14 host-level Issue surface as a closed-enum classifier-driven channel: 5 regexes -> 5 ``IssueDetail`` values (LOCKED via test catalog-size assertion); UNKNOWN fallback never enters the wire detail field. Phase 4 destructive-action gating (e.g. suppress ``usb_reset`` when ``USB_OVERCURRENT`` is the active host issue) reads from this surface without further work.
- Mirrored Plan 03-03/03-04's testable-defaults pattern verbatim for ``/dev/kmsg``: ``fd_factory: tuple[int, Callable[[int, int], bytes]] | None = None`` lets tests inject ``(sentinel_fd, fake.read)`` without opening real ``/dev/kmsg`` or touching ``os.open``. Production wires None and ``/dev/kmsg`` is opened lazily inside the coroutine. Module imports cleanly on Windows dev hosts.
- Shipped FakeKmsgReader as the fourth Phase 3 dual-surface fake (after FakeUdevMonitor + FakeAsyncIPRoute + FakeAsyncinotify): production-shape methods (``read``, ``fileno``), test-only mutators (``inject_record``, ``inject_raw``, ``inject_oserror``), and an internal ``_ErrorSentinel`` slots class for OSError injection that's typed cleanly under mypy --strict.
- KmsgDedup mirrors webhook/dedup.py's ``DedupTable`` shape (same ``_expires_at`` + ``_suppressed`` dicts, same ``consume_dedup_count`` helper) with key shape ``IssueDetail`` instead of ``(modem, kind)`` and default window 30s instead of 60s. Semantics flipped (returns True on EMIT, not on suppression) for caller readability — the producer reads it as ``if dedup.should_emit(...): emit_issue(...)``.
- 1767 tests pass in 17.84s on Windows dev host (up from 1739 — exactly +28 new tests: 9 classifier + 9 dedup + 10 producer; one linux_only test skipped on Windows). mypy --strict + ruff check + ruff format all green on every new file; SP-04 subprocess lint exits 0 (no new direct subprocess calls — kmsg is a syscall, not a subprocess).

## Task Commits

Each task followed TDD (RED -> GREEN), committed atomically:

1. **Task 1 RED — failing tests for classifier + dedup + 5 fixtures** — `1a01e2f` (test)
2. **Task 1 GREEN — kmsg/__init__.py + classifier.py + dedup.py** — `e3865a7` (feat)
3. **Task 2 RED — failing tests for kmsg_producer + FakeKmsgReader** — `3ec00b1` (test)
4. **Task 2 GREEN — event_sources/kmsg_producer.py + ruff cleanups in test file** — `a1876c8` (feat)

## Files Created/Modified

### Created

- `src/spark_modem/kmsg/__init__.py` — package marker; documents the classifier + dedup contract surface and the W-04 closed-enum discipline. Phase 4 destructive-action gating reads ``IssueDetail`` values produced by this subsystem.
- `src/spark_modem/kmsg/classifier.py` — ``KMSG_PATTERNS: tuple[tuple[re.Pattern[str], IssueDetail], ...]`` with 5 entries (LOCKED via test contract gate); ``classify(line) -> IssueDetail`` scans patterns in order, returns first match or ``IssueDetail.UNKNOWN``. ``re.IGNORECASE`` on every pattern (real Linux kernel writes lowercase 'usb' but the docs cite capital 'USB'; the flag tolerates both).
- `src/spark_modem/kmsg/dedup.py` — ``KmsgDedup.should_emit(detail, *, now_monotonic) -> bool`` (True == EMIT) + ``consume_dedup_count(detail) -> int``; default ``window_seconds=30.0`` LOCKED; mirrors ``webhook/dedup.py::DedupTable`` shape with key shape and default window varied. Module never imports ``time`` (CLAUDE.md invariant #4 — caller passes the monotonic value).
- `src/spark_modem/event_sources/kmsg_producer.py` — ``run_kmsg_producer(*, event_queue, dedup, clock, issue_emitter, fd_factory=None) -> None`` coroutine. Body: ``O_RDONLY|O_NONBLOCK`` + ``lseek(SEEK_END)`` + ``loop.add_reader(fd, on_readable)`` (production) / ``loop.call_soon(on_readable)`` (test path). on_readable drain loop: ``read_fn(fd, 8192)`` until ``BlockingIOError``; parse header; classify; UNKNOWN-skip; dedup; emit. Co-located ``_EventQueueProto``, ``_ClockProto``, ``_IssueEmitterProto`` Protocols + module-level ``_KMSG_DEV``, ``_READ_CHUNK_BYTES``, ``_KMSG_HEADER_MIN_FIELDS`` constants. Cleanup in finally suppresses OSError on ``loop.remove_reader`` + ``os.close``.
- `tests/fakes/kmsg.py` — ``FakeKmsgReader`` with production-shape ``read(fd, nbytes) -> bytes`` + ``fileno() -> int`` and test-only ``inject_record(*, priority=6, seq, ts_us=0, message)``, ``inject_raw(raw)``, ``inject_oserror(errno_value)``. Internal ``_ErrorSentinel`` slots class for OSError injection (typed cleanly under mypy --strict). Records every ``read`` call's ``nbytes`` for assertion.
- `tests/unit/kmsg/__init__.py` — empty package marker.
- `tests/unit/kmsg/test_classifier.py` — 9 tests pinning every contract point: UNKNOWN-fallback, 5 parametrized fixture-classification, table-size-locked-at-5 contract gate, first-match-wins on overlapping pattern, UNKNOWN-not-in-pattern-targets.
- `tests/unit/kmsg/test_dedup.py` — 9 tests pinning: first-call-emits, repeat-suppressed, repeat-count-accumulates, consume-clears-to-zero, window-reopens-after-30s, distinct-details-independent, default-window-30s-LOCKED, consume-for-unknown-key-returns-zero, custom-window-seconds-honored.
- `tests/unit/event_sources/test_kmsg_producer.py` — 11 tests (10 active + 1 linux_only stub) pinning: classified-emits-issue-and-wake, UNKNOWN-suppressed, dedup-window-suppress, dedup-window-reopen, distinct-details-emit-independently, BlockingIOError-terminates-drain, EPIPE-resets-last_seq-and-continues, malformed-record-skipped, cross-platform-module-import, signature-matches-protocols, default-fd-path linux_only stub (covered by Plan 03-06 integration suite).
- 5 fixture files at `tests/fixtures/kmsg/{usb_overcurrent,usb_enum_failure,thermal_throttle,qmi_wwan_probe_fail,tegra_hub_psu_droop}.log` — one realistic kernel-line per IssueDetail value; the parametrized classifier test reads each fixture and asserts the expected enum value. Fixtures make the bench-Jetson regex iteration cycle concrete: when bench observation surfaces a different shape, the fix is "edit fixture; re-run pytest; ship."

### Modified

None — Plan 03-05 is purely additive. The IssueDetail enum extension landed in Plan 03-01 Task 2; the FakeAsyncinotify import surface in `tests/fakes/__init__.py` is owned by Plan 03-01 (we did not add FakeKmsgReader to the package re-export per the plan's parallel-safety guidance — downstream tests import directly from `tests.fakes.kmsg`).

## Decisions Made

See key-decisions in frontmatter — most load-bearing:

1. **Catalog size LOCKED at 5 via test contract gate.** ``test_kmsg_patterns_table_size_locked_at_5`` asserts ``len(KMSG_PATTERNS) == 5``. Adding a 6th regex requires deliberate edits to (1) the regex table, (2) the IssueDetail enum (Plan 03-01 already extended it), AND (3) this test file's count assertion. Per CONTEXT.md Deferred Ideas, catalog growth lands via ADR or Phase 4 follow-up — never as a silent one-line edit.

2. **First-match-wins on overlapping patterns.** Pinned by ``test_classify_returns_first_match_when_overlapping``: a synthetic line containing BOTH 'over-current' and 'device not accepting address' MUST classify as USB_ENUM_FAILURE (the table's first entry). Reordering KMSG_PATTERNS without thinking through this fails CI loudly — the test reviewer will notice.

3. **UNKNOWN distinct from the 5 mapped values.** ``test_unknown_value_distinct_from_other_values`` asserts ``IssueDetail.UNKNOWN not in {detail for _, detail in KMSG_PATTERNS}``. If any pattern entry mapped to UNKNOWN the producer would emit Issues for unclassified lines — exactly the v1 free-form-detail regression we're avoiding. W-04 closed-enum discipline preserved at the test level.

4. **KmsgDedup default window 30.0s LOCKED.** Pinned by ``test_default_window_30_seconds`` asserting emit at t=0, suppress at t=29.99, re-emit at t=30.0 (boundary inclusive on the 'window expired' side per the ``now_monotonic < expires`` comparison). PITFALLS §13.2 prescribes the value; CONTEXT.md E-03 LOCKS it.

5. **EPIPE handled inside the drain loop (NOT escaped to supervisor).** The semantics differ from rtnetlink ENOBUFS: ENOBUFS means socket buffer overflow (close+reopen recovery); EPIPE on /dev/kmsg means the kernel ring buffer wrapped (just keep reading at the new tail). We catch EPIPE inside ``on_readable``, reset ``last_seq`` to None, and ``continue``. Other OSError values escape to the supervisor (E-01) for re-entry — the supervisor is the safety net for unanticipated errno values.

6. **Re.IGNORECASE on every regex.** Bench-Jetson reality: the real Linux kernel writes 'usb 1-3.1: device not accepting address' (lowercase 'usb'); the RESEARCH.md catalog cited 'USB' (capital). Rather than choose one casing, the IGNORECASE flag tolerates both — and it's forward-compatible against any future kernel-message capitalization drift across the 5 regex shapes.

7. **fd_factory shape ``tuple[int, Callable[[int, int], bytes]] | None``.** Tests pass ``(sentinel_fd, fake.read)`` so the producer never opens /dev/kmsg in unit-test paths. Production wires None and ``os.open(_KMSG_DEV, ...)`` runs lazily inside the coroutine. Same testable-defaults pattern as Plan 03-03's ``ipr_factory: tuple[_AsyncIPRouteProto, int] | None`` and Plan 03-04's ``inotify_factory``.

8. **Test path uses loop.call_soon (not loop.add_reader).** The FakeKmsgReader fd is a sentinel (99) not registered with the OS event loop; if we called ``loop.add_reader(99, ...)`` on Windows the ProactorEventLoop would error. The producer branches on fd_factory: production wires ``loop.add_reader(real_fd, on_readable)``; tests wire ``loop.call_soon(on_readable)`` for one-shot drain. Both paths exit via the same finally cleanup.

9. **KmsgDedup.should_emit returns True on EMIT (semantics flipped vs webhook/dedup.py).** The webhook table's ``is_deduped`` returns True on suppression — opposite direction. We follow the producer's natural phrasing: ``if dedup.should_emit(detail, ...): emit_issue(...)``. The test count assertion (``test_first_call_emits``) names this contract.

10. **_KMSG_HEADER_MIN_FIELDS = 2 module constant.** Replaced magic literal ``len(fields) >= 2`` (PLR2004 ruff fix). The constant documents the contract: a kmsg header MUST contain at least priority + sequence to be parseable.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Re.IGNORECASE flag added to all 5 KMSG_PATTERNS regexes**
- **Found during:** Task 1 GREEN (pytest after writing the production code; ``test_classify_fixture[usb_enum_failure]`` failed)
- **Issue:** The RESEARCH.md catalog cited capital-USB shape (``r"USB \S+: device not accepting address"``) but real Linux kernel writes 'usb 1-3.1:' (lowercase). The fixture file (which represents real bench-Jetson observation) didn't match the regex. Per CONTEXT.md 'Claude's Discretion', regex strings are data and may iterate based on bench observation.
- **Fix:** Added ``re.IGNORECASE`` to all 5 patterns (the change is forward-compatible against any future kernel-message capitalization drift across the other 4 shapes too).
- **Files modified:** ``src/spark_modem/kmsg/classifier.py``
- **Verification:** All 9 classifier tests pass; first-match-wins behavior unchanged (the order assertion still holds because the IGNORECASE versions of both patterns still match in the same iteration order).
- **Committed in:** ``e3865a7`` (Task 1 GREEN).

**2. [Rule 1 — Lint] PLR2004 magic value 2 -> _KMSG_HEADER_MIN_FIELDS module constant**
- **Found during:** Task 2 GREEN ruff check
- **Issue:** ``if len(fields) >= 2:`` flagged as PLR2004 (magic value used in comparison).
- **Fix:** Introduced ``_KMSG_HEADER_MIN_FIELDS: Final[int] = 2`` module constant; the comparison references it. The constant's docstring documents the contract: a kmsg header MUST contain at least priority + sequence to be parseable.
- **Verification:** ``ruff check`` clean.
- **Committed in:** ``a1876c8`` (Task 2 GREEN).

**3. [Rule 1 — Lint] SIM105 try/except/pass -> contextlib.suppress in test helper**
- **Found during:** Task 2 GREEN ruff check
- **Issue:** ``try: await task / except asyncio.CancelledError: pass`` flagged as SIM105 (use ``contextlib.suppress``).
- **Fix:** Imported ``contextlib`` at module level; replaced the try/except with ``with contextlib.suppress(asyncio.CancelledError): await task``.
- **Verification:** ``ruff check`` clean; helper still cancels the producer task cleanly without exception escape.
- **Committed in:** ``a1876c8`` (Task 2 GREEN).

### Acceptance-criterion micro-deviation #1 (consistent with Plans 03-01..03-04 precedent)

The plan's acceptance criteria for Task 2 specify:
- ``grep -c "lseek.*SEEK_END" src/spark_modem/event_sources/kmsg_producer.py`` returns **1**

Actual count is **2**: one in the actual ``os.lseek(fd, 0, os.SEEK_END)`` call inside ``_open_kmsg()`` plus one in the module docstring (``"+ ``lseek(SEEK_END)`` + ``loop.add_reader``"``) which calls out the prescribed pattern by name. Decision: keep the documentation; the intent of the acceptance criterion is "the lseek-to-SEEK_END pattern is used exactly once," which is verified by the actual call. Same precedent as Plans 03-01/02/03/04 docstring-vs-usage micro-deviations.

A stricter grep ``grep -c "os.lseek" src/spark_modem/event_sources/kmsg_producer.py`` returns **1** — the one call site.

### Test count modulation (consistent with Plan 03-02/03/04 precedent)

The plan asks for "exactly 5+1 cases" on test_classifier.py, "exactly 7 cases" on test_dedup.py, and "8+ tests" on test_kmsg_producer.py. Actual delivery:
- ``test_classifier.py``: 9 tests (UNKNOWN-fallback + 5 parametrized fixture-classification + table-size-LOCKED + first-match-wins + UNKNOWN-not-in-pattern-targets — every plan-specified case + the table-size contract gate).
- ``test_dedup.py``: 9 tests (7 plan-specified + 2 belt-and-suspenders: ``test_consume_for_unknown_key_returns_zero`` + ``test_custom_window_seconds_honored``).
- ``test_kmsg_producer.py``: 11 tests (8 plan-specified + 3 belt-and-suspenders: ``test_module_imports_cross_platform`` + ``test_run_kmsg_producer_signature_matches_protocols`` + ``test_default_fd_path_opens_dev_kmsg`` linux_only stub).

Same precedent as Plans 03-02/03/04 — additional belt-and-suspenders tests catch boundary conditions the plan-specified cases didn't hit; all stay under the M7 30s budget (suite is 17.84s).

## Authentication Gates

None — Plan 03-05 is pure local code with no external service interactions. The only "external" interface is ``/dev/kmsg`` which a unit test cannot exercise without root + read access to the kernel ring buffer; the FakeKmsgReader injects record sequences in pure-Python.

## Threat Surface Scan

Threat register check passed: every threat in the plan's `<threat_model>` section that was assigned `mitigate` disposition has its mitigation in place:

- **T-03-05-01** (Tampering — free-form kernel-line string entering Issue.detail / W-04 anti-pattern) — mitigated by E-03 closed-enum discipline: ``IssueDetail`` is a StrEnum; classifier returns enum members only; UNKNOWN-classified lines suppress Issue emission (raw line preserved separately for forensic logger). Verified by ``test_unknown_classified_line_does_not_emit`` and ``test_unknown_value_distinct_from_other_values``.
- **T-03-05-02** (DoS — kernel ring-buffer-wrap during high-volume kernel logging / PITFALLS §13.2) — mitigated by EPIPE handling: reset ``last_seq``, continue draining (no exception escape); per-detail 30s dedup collapses repeats; supervisor restart_on_crash is the outer safety net for any unhandled producer error. Verified by ``test_epipe_resets_last_seq_and_continues``.
- **T-03-05-03** (DoS — single producer hot-loops in on_readable callback under attacker-induced kernel-message storm) — mitigated by ``BlockingIOError`` terminating drain loop; ``loop.add_reader`` callback is sync and yields control after drain; 30s dedup window collapses repeats so cycle wake_queue is not flooded; queue drop-on-full semantics are honored. Verified by ``test_blocking_io_error_terminates_drain_loop`` and ``test_dedup_suppresses_repeats_within_window``.
- **T-03-05-04** (Information Disclosure — raw kernel line containing PII leaked to forensic logger) — accepted; daemon runs as root reading the kernel ring buffer; same risk surface as ``journalctl -k``; events.jsonl mode 0640 root:adm constrains read access.
- **T-03-05-05** (Spoofing — local non-root user injecting fake /dev/kmsg messages) — accepted; /dev/kmsg writes are root-only by default; daemon already root, no other suid binary.
- **T-03-05-06** (Tampering — blocking read on /dev/kmsg from asyncio loop / CLAUDE.md anti-pattern catalogue) — mitigated by ``O_RDONLY|O_NONBLOCK`` + ``lseek(SEEK_END)`` + ``add_reader``; no blocking ``read()`` in producer body; verified by structural grep + the BlockingIOError-termination test which proves the producer drains via non-blocking semantics.

No new security-relevant surface introduced beyond the plan's threat model. The producer reads from a kernel-managed file; no inputs flow back to userspace beyond opaque WakeSignal sentinels and IssueDetail enum values.

## Deferred Issues

None — all auto-fix issues stayed within the current task's scope (regex case-sensitivity, PLR2004 magic value, SIM105 try/except cleanup). No pre-existing flaky tests observed in the full-suite run (1767 passed clean, no retries needed).

## Self-Check: PASSED

**Files exist:**
- FOUND: ``src/spark_modem/kmsg/__init__.py``
- FOUND: ``src/spark_modem/kmsg/classifier.py``
- FOUND: ``src/spark_modem/kmsg/dedup.py``
- FOUND: ``src/spark_modem/event_sources/kmsg_producer.py``
- FOUND: ``tests/fakes/kmsg.py``
- FOUND: ``tests/unit/kmsg/__init__.py``
- FOUND: ``tests/unit/kmsg/test_classifier.py``
- FOUND: ``tests/unit/kmsg/test_dedup.py``
- FOUND: ``tests/unit/event_sources/test_kmsg_producer.py``
- FOUND: ``tests/fixtures/kmsg/usb_overcurrent.log``
- FOUND: ``tests/fixtures/kmsg/usb_enum_failure.log``
- FOUND: ``tests/fixtures/kmsg/thermal_throttle.log``
- FOUND: ``tests/fixtures/kmsg/qmi_wwan_probe_fail.log``
- FOUND: ``tests/fixtures/kmsg/tegra_hub_psu_droop.log``

**Commits exist (verified by `git log --oneline -4`):**
- FOUND: ``1a01e2f`` test(03-05): add failing tests for kmsg classifier + dedup + fixtures
- FOUND: ``e3865a7`` feat(03-05): kmsg classifier (regex -> IssueDetail) + per-detail 30s dedup
- FOUND: ``3ec00b1`` test(03-05): add failing tests for kmsg_producer + FakeKmsgReader
- FOUND: ``a1876c8`` feat(03-05): kmsg_producer (/dev/kmsg O_NONBLOCK reader + classifier wiring)

**Final acceptance:**
- ``pytest -q`` reports 1767 passed / 77 skipped / 0 failed in 17.84s
- ``pytest tests/unit/kmsg/ tests/unit/event_sources/test_kmsg_producer.py -x`` reports 28 passed / 1 skipped (the linux_only ``test_default_fd_path_opens_dev_kmsg`` stub)
- ``mypy --strict src/spark_modem/kmsg/ src/spark_modem/event_sources/kmsg_producer.py`` reports 0 issues across 4 source files
- ``ruff check`` + ``ruff format --check`` green on every new file
- ``bash scripts/lint_no_subprocess.sh`` exits 0 (no new direct subprocess calls — kmsg is a syscall, not a subprocess)
- ``python -c "from spark_modem.event_sources.kmsg_producer import run_kmsg_producer; print(callable(run_kmsg_producer))"`` exits 0 on Windows (deferred-/dev/kmsg-open contract)
- ``python -c "from spark_modem.kmsg.classifier import KMSG_PATTERNS; assert len(KMSG_PATTERNS) == 5"`` exits 0 (catalog size LOCKED)
- ``python -c "from spark_modem.kmsg.classifier import classify; from spark_modem.wire.enums import IssueDetail; assert classify('foo') == IssueDetail.UNKNOWN"`` exits 0 (UNKNOWN fallback)
- ``grep -c "KMSG_PATTERNS" src/spark_modem/kmsg/classifier.py`` returns 3 (declaration + 2 docstring/comment references)
- ``grep -c "def classify" src/spark_modem/kmsg/classifier.py`` returns 1
- ``grep -E "IssueDetail\.(USB_OVERCURRENT|USB_ENUM_FAILURE|THERMAL_THROTTLE|QMI_WWAN_PROBE_FAIL|TEGRA_HUB_PSU_DROOP)" src/spark_modem/kmsg/classifier.py | wc -l`` returns 5 (one per pattern)
- ``grep -c "class KmsgDedup" src/spark_modem/kmsg/dedup.py`` returns 1
- ``grep -c "def should_emit" src/spark_modem/kmsg/dedup.py`` returns 1
- ``grep -c "def consume_dedup_count" src/spark_modem/kmsg/dedup.py`` returns 1
- ``grep -c "window_seconds: float = 30.0" src/spark_modem/kmsg/dedup.py`` returns 1 (default 30s LOCKED)
- ``grep -c "time.time" src/spark_modem/kmsg/dedup.py`` returns 0 (monotonic only)
- ``grep -c "time.time" src/spark_modem/kmsg/classifier.py`` returns 0
- ``grep -c "O_RDONLY.*O_NONBLOCK\|O_NONBLOCK.*O_RDONLY" src/spark_modem/event_sources/kmsg_producer.py`` returns 2 (one in code + one in docstring)
- ``grep -c "loop.add_reader" src/spark_modem/event_sources/kmsg_producer.py`` returns 3 (one in code + two in docstring)
- ``grep -c "loop.remove_reader" src/spark_modem/event_sources/kmsg_producer.py`` returns 1 (cleanup in finally)
- ``grep -c "BlockingIOError" src/spark_modem/event_sources/kmsg_producer.py`` returns 4 (one in code + three in docstring/comments)
- ``grep -c "EPIPE" src/spark_modem/event_sources/kmsg_producer.py`` returns 4 (one in code + three in docstring/comments)
- ``grep -c "WakeSignal.KMSG" src/spark_modem/event_sources/kmsg_producer.py`` returns 2 (one in code + one in docstring)
- ``grep -c "IssueDetail.UNKNOWN" src/spark_modem/event_sources/kmsg_producer.py`` returns 1 (the one if-branch in on_readable)
- ``grep -c "subprocess\|os.system\|create_subprocess_exec" src/spark_modem/event_sources/kmsg_producer.py`` returns 0
- ``grep -c "class FakeKmsgReader" tests/fakes/kmsg.py`` returns 1
- All 5 fixture files exist and are non-empty: ``wc -c tests/fixtures/kmsg/*.log`` shows 39, 44, 51, 54, 56 bytes (sum 244)
- M7 budget preserved (17.84s ≤ 30s with ~12.2s slack)

## TDD Gate Compliance

Each task within is `type="auto" tdd="true"`. Per-task TDD gate sequence verified in git log:

| Task | RED commit (test) | GREEN commit (feat) | Gate sequence |
|------|-------------------|---------------------|---------------|
| Task 1 | ``1a01e2f`` test(03-05): failing tests for classifier + dedup + 5 fixtures | ``e3865a7`` feat(03-05): kmsg classifier + per-detail 30s dedup | RED-then-GREEN ✓ |
| Task 2 | ``3ec00b1`` test(03-05): failing tests for kmsg_producer + FakeKmsgReader | ``a1876c8`` feat(03-05): kmsg_producer (/dev/kmsg O_NONBLOCK reader + classifier wiring) | RED-then-GREEN ✓ |

Both tasks demonstrated true RED before GREEN:
- Task 1 RED failed at collection-time with ``ModuleNotFoundError: No module named 'spark_modem.kmsg'``.
- Task 2 RED failed at collection-time with ``ModuleNotFoundError: No module named 'spark_modem.event_sources.kmsg_producer'``.

## Cross-References for Downstream Plans

**Plan 03-06 (lifecycle-integration)** consumes:
- ``run_kmsg_producer`` factory under ``restart_on_crash``. The TaskGroup wiring will spawn it alongside ``run_udev_producer`` (Plan 03-02), ``run_rtnetlink_producer`` (Plan 03-03), and ``run_asyncinotify_producer`` (Plan 03-04). Each producer factory is called as e.g. ``restart_on_crash("kmsg_producer", lambda: run_kmsg_producer(event_queue=q, dedup=dedup, clock=clock, issue_emitter=emitter), ...)``.
- The ``_IssueEmitterProto`` Protocol surface (``emit_host_issue(*, detail: IssueDetail, raw_line: str) -> None``). Plan 03-06 ships the production implementation: probably an extension of the existing event_logger writer + a host-issue accumulator on the cycle driver. The current Protocol shape is the contract.
- The local ``sequence_gaps_total`` counter inside ``run_kmsg_producer`` — Plan 03-06 wires it as the Prometheus metric ``kmsg_sequence_gaps_total`` (NFR-21.1 surface). The counter is currently scoped to the coroutine; Plan 03-06 may promote it to a recorded-metrics seam.
- Cycle scheduler wakes on ``WakeSignal.KMSG`` (already plumbed by Plan 03-01); cycle then does a full re-observation pass which re-reads the host-issue accumulator and surfaces new IssueDetail values into ``status.aggregate_health``.

**Phase 4 destructive actions** consume:
- The 5 host-level ``IssueDetail`` values for destructive-action gating: ``usb_reset`` MAY be suppressed when ``USB_OVERCURRENT`` or ``TEGRA_HUB_PSU_DROOP`` is the active host issue (a hub-wide power problem won't be fixed by resetting one device). ``modem_reset`` MAY be suppressed when ``THERMAL_THROTTLE`` is active (thermal limits suggest waiting, not resetting). The exact gate predicates are Phase 4's concern; Plan 03-05 just lights up the surface.
- ``KmsgDedup.consume_dedup_count(detail)`` — Phase 4 (or Plan 03-06) may surface the suppressed counts as ``kmsg_suppressed_total{detail}`` for NOC visibility into how often kernel-message storms collapse.

---
*Phase: 03-linux-event-sources-lifecycle*
*Completed: 2026-05-08*
