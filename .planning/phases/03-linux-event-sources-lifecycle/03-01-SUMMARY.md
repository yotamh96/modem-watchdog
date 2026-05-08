---
phase: 03-linux-event-sources-lifecycle
plan: 01
subsystem: event-sources
tags: [event-sources, supervisor, taskgroup, wakesignal, kmsg, asyncinotify, fakes, tdd]

# Dependency graph
requires:
  - phase: 01-foundations-adrs
    provides: wire/enums.py StrEnum convention; tests/fakes/ pattern; mypy --strict / ruff gates
  - phase: 02-core-daemon-laptop-testable
    provides: tests/fakes/clock.FakeClock; observer/orchestrator NFR-11 isolation pattern; CycleScheduler.event_queue plumbed as no-op; tests/fakes/zao_log.FixtureZaoTailer state-mutating helper pattern
provides:
  - WakeSignal closed StrEnum on event_queue (E-02) — 5 sources locked
  - Sleeper Protocol + FakeSleeper for FakeClock-driven tests (PITFALLS §14.1)
  - restart_on_crash supervisor (E-01) with bounded backoff + uptime-reset
  - 6 new IssueDetail values (E-03) covering host-level kmsg classification
  - FakeAsyncinotify async-iterable test seam for Plans 03-04 + 03-06
  - linux_only pytest marker registered for Plans 03-02..03-06
affects:
  - 03-02-udev-producer (imports WakeSignal, restart_on_crash)
  - 03-03-rtnetlink-producer (imports WakeSignal, restart_on_crash)
  - 03-04-asyncinotify-producers (imports WakeSignal, restart_on_crash, FakeAsyncinotify)
  - 03-05-kmsg-classifier (imports WakeSignal, restart_on_crash, IssueDetail extension)
  - 03-06-lifecycle-integration (imports all of the above + wires structured event emission)

# Tech tracking
tech-stack:
  added: []  # No new dependencies — pure stdlib (asyncio, enum, logging, typing.Protocol)
  patterns:
    - "Producer-task supervisor: TaskGroup child wrapped in restart_on_crash(name, factory, *, sleeper, event_logger, clock, backoffs, reset_after_uptime_s) — catches Exception only, passes through CancelledError, Pitfall 15 attempt-counter reset on long uptime"
    - "Sleeper Protocol seam: production wires asyncio.sleep adapter; tests inject FakeSleeper that advances FakeClock and yields control"
    - "Closed StrEnum on event_queue payload (WakeSignal) mirrors DaemonStopReason convention from Phase 1"
    - "Co-located ClockProto + EventLogWriterProto in event_sources/supervisor.py — prevents import cycles between event_sources/ and daemon/"

key-files:
  created:
    - src/spark_modem/event_sources/__init__.py
    - src/spark_modem/event_sources/supervisor.py
    - tests/fakes/sleeper.py
    - tests/fakes/asyncinotify.py
    - tests/unit/event_sources/__init__.py
    - tests/unit/event_sources/test_supervisor.py
    - tests/unit/wire/test_enums_phase3.py
  modified:
    - src/spark_modem/wire/enums.py
    - tests/fakes/__init__.py
    - pyproject.toml

key-decisions:
  - "WakeSignal members locked at the 5 values from CONTEXT.md E-02 (UDEV / RTNETLINK / ZAO_LOG / EVENTS_LOG_ROTATED / KMSG); StrEnum lowercase-snake_case so producers serialize naturally to events.jsonl"
  - "Sleeper Protocol takes a single async sleep(delay) method; FakeSleeper advances injected FakeClock and yields control via asyncio.sleep(0); production-side adapter is one line and lives downstream"
  - "restart_on_crash signature: (name, factory, *, sleeper, event_logger, clock, backoffs=(1,2,4,8,60), reset_after_uptime_s=300.0); event_logger plumbed but unused in 03-01 — Plan 03-06 wires structured event_source_crashed emission (T-03-01-06 accepted threat)"
  - "CancelledError passthrough is the ONLY way out of restart_on_crash — Exception is always caught and looped; verified by test_supervisor_passes_through_cancelled_error"
  - "USB_OVERCURRENT (host-level kmsg-classified) is DISTINCT from ENUMERATION_OVERCURRENT (per-modem enumeration-time) — closed-enum discipline (W-04); pinned by test_usb_overcurrent_distinct_from_enumeration_overcurrent so a future careless refactor that aliased them fails CI loudly"
  - "FakeAsyncinotify exposes both production-Inotify shape (add_watch / rm_watch / __aenter__ / __aexit__ / __aiter__ / __anext__) AND test-only mutator (inject_event); same dual-surface pattern as Phase 2's FixtureZaoTailer"
  - "pyproject.toml linux_only marker added once here so 4 of the 5 downstream Phase 3 plans (~14 test files) can carry the marker without repeating the registration"

patterns-established:
  - "Pattern: per-producer supervisor with bounded backoff + uptime-reset (Pitfall 15) — chronic-crash producer caps at ~1.7% CPU and one event_source_crashed log per minute; transient crashes still see escalation"
  - "Pattern: Sleeper Protocol injection (PITFALLS §14.1) — every async sleep that drives a test-observable backoff goes through this seam; production wires asyncio.sleep, tests wire FakeSleeper"
  - "Pattern: contract-test gate for closed wire enums — tests/unit/wire/test_enums_phase3.py is the load-bearing assertion that the 5+1 host-level IssueDetail values cannot regress without CI failing loudly"
  - "Pattern: dual-surface fakes (production Protocol + test-only mutator) — FakeAsyncinotify mirrors FixtureZaoTailer; production code never sees the mutator (the Protocol surface omits it)"

requirements-completed: [FR-14]

# Metrics
duration: 12min
completed: 2026-05-08
---

# Phase 3 Plan 01: Event-Source Foundations Summary

**Foundational scaffolding for the 5 Phase 3 producer plans: WakeSignal wire enum, restart_on_crash supervisor, Sleeper / FakeSleeper / FakeAsyncinotify test seams, IssueDetail kmsg-classifier extension, linux_only pytest marker — all locked before any producer ships.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-05-08T13:59:24Z
- **Completed:** 2026-05-08T14:11:53Z
- **Tasks:** 2 (TDD: 4 commits — test/feat/test/feat)
- **Files modified:** 10 (7 created + 3 modified)

## Accomplishments

- Locked the cross-plan contract surface every downstream Phase 3 plan consumes (WakeSignal, restart_on_crash, Sleeper Protocol, IssueDetail extension, FakeAsyncinotify, linux_only marker) — no Plan 03-02..03-06 will hit a "what's the signature of X" round-trip.
- Built restart_on_crash with bounded backoff envelope (1, 2, 4, 8, 60s) cap + Pitfall 15 attempt-counter reset after >=300s clean uptime; verified by 8 supervisor tests including CancelledError-passthrough, envelope-cap, uptime-reset (350s clean → backoff resets to 1.0), and short-uptime-non-reset (<300s preserves escalation).
- Extended IssueDetail with 6 host-level values (USB_OVERCURRENT, USB_ENUM_FAILURE, THERMAL_THROTTLE, QMI_WWAN_PROBE_FAIL, TEGRA_HUB_PSU_DROOP, UNKNOWN) — total enum count 34 → 40, distinct from existing per-modem ENUMERATION_OVERCURRENT and THERMAL_WARN/CRITICAL (W-04 closed-enum discipline).
- All 1696 tests pass in 16.65s (M7 30s budget preserved with ~13s slack); mypy --strict + ruff check + ruff format all green on every new/modified file.

## Task Commits

Each task followed TDD (RED → GREEN), committed atomically:

1. **Task 1 RED — failing supervisor + Sleeper tests** — `fb5e80f` (test)
2. **Task 1 GREEN — supervisor.py + WakeSignal + Sleeper Protocol + linux_only marker** — `6bcceb6` (feat)
3. **Task 2 RED — failing IssueDetail contract + FakeAsyncinotify import** — `ffe321e` (test)
4. **Task 2 GREEN — IssueDetail extension + FakeAsyncinotify + fakes/__init__.py re-export** — `9aa9717` (feat)

## Files Created/Modified

### Created

- `src/spark_modem/event_sources/__init__.py` — package marker; re-exports WakeSignal, restart_on_crash, Sleeper, ClockProto, EventLogWriterProto so downstream producer modules can `from spark_modem.event_sources import …`.
- `src/spark_modem/event_sources/supervisor.py` — WakeSignal StrEnum (5 closed members) + Sleeper / ClockProto / EventLogWriterProto co-located Protocols + `restart_on_crash(name, factory, *, sleeper, event_logger, clock, backoffs=(1,2,4,8,60), reset_after_uptime_s=300.0) -> None`. CancelledError passthrough, Exception catch-all, Pitfall 15 attempt-counter reset.
- `tests/fakes/sleeper.py` — FakeSleeper that records each delay, advances injected FakeClock via `clock.advance(delay)`, and yields control via `asyncio.sleep(0)`.
- `tests/fakes/asyncinotify.py` — FakeAsyncinotify async-iterable + FakeMask IntFlag (MODIFY/MOVE_SELF/DELETE_SELF/CLOSE_WRITE/CREATE/MOVED_TO mirroring asyncinotify.Mask) + frozen FakeInotifyEvent dataclass; `add_watch` / `rm_watch` / `inject_event` / `__aenter__` / `__aexit__` / `__aiter__` / `__anext__`.
- `tests/unit/event_sources/__init__.py` — package marker (empty).
- `tests/unit/event_sources/test_supervisor.py` — 9 tests covering WakeSignal closed-enum shape, StrEnum str() guarantee, CancelledError passthrough, backoff envelope (1, 2, 4, 8, 60, 60), uptime-reset (>=300s → backoff resets to 1.0), short-uptime non-reset (<300s preserves escalation), clean factory return → silent exit, logger.exception emission with source name + "event_source_crashed" marker, Sleeper runtime_checkable.
- `tests/unit/wire/test_enums_phase3.py` — 3 contract tests pinning the 5+1 host-level IssueDetail values, asserting USB_OVERCURRENT != ENUMERATION_OVERCURRENT, asserting UNKNOWN.value == "unknown".

### Modified

- `src/spark_modem/wire/enums.py` — appended a "Host (kmsg classifier — Phase 3 / E-03; D-03)" comment block to IssueDetail with the 6 new values; total members 34 → 40.
- `tests/fakes/__init__.py` — bootstrapped re-export surface (was empty); now re-exports FakeAsyncinotify, FakeInotifyEvent, FakeMask, FakeSleeper.
- `pyproject.toml` — added `"linux_only: requires Linux-specific syscalls (skipif on Windows)"` to `[tool.pytest.ini_options].markers` so all Phase 3 Linux-only test files can carry one consistent marker.

## Decisions Made

See key-decisions in frontmatter — most load-bearing:

1. **WakeSignal closed StrEnum locked at 5 values** — UDEV / RTNETLINK / ZAO_LOG / EVENTS_LOG_ROTATED / KMSG. Per ADR-0002, the queue carries opaque sentinels only; state derives from re-observation. Producers `put_nowait(WakeSignal.UDEV)` and never push state.
2. **`event_logger` parameter plumbed but unused in 03-01** — Plan 03-06 lands the structured `event_source_crashed` Event variant + supervisor wiring. Threat T-03-01-06 documents this acceptance: 03-01 logs via `logger.exception` only; structured emission comes online downstream.
3. **Co-located Protocols (ClockProto, EventLogWriterProto) inside `event_sources/supervisor.py`** — explicitly NOT imported from `daemon/cycle_scheduler` to prevent an import cycle between the event_sources package and the daemon package. Same Phase 1/2 convention as `observer/orchestrator.py`'s ClockProto.
4. **USB_OVERCURRENT distinct from ENUMERATION_OVERCURRENT** — pinned by `test_usb_overcurrent_distinct_from_enumeration_overcurrent`. The host-level (kmsg, hub-wide) signal vs. the per-modem (sysfs, enumeration-time) signal must remain separate so Phase 4 destructive-action gating reads the right channel.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Removed `pytestmark = pytest.mark.asyncio` module-level marker**
- **Found during:** Task 1 verification (pytest produced 3 PytestWarnings)
- **Issue:** Three of the 9 supervisor tests are synchronous (`test_wake_signal_*`, `test_sleeper_protocol_is_runtime_checkable`); a module-level `pytestmark = pytest.mark.asyncio` triggered "test marked with asyncio but not async" warnings. The plan suggested module-level marking ("Mark with `pytestmark = pytest.mark.asyncio` at module level") but pytest-asyncio's `mode=auto` already auto-marks async tests, so the module-level marker is redundant AND triggers warnings on sync tests.
- **Fix:** Removed the module-level `pytestmark` line. mode=auto handles per-test detection cleanly.
- **Files modified:** `tests/unit/event_sources/test_supervisor.py`
- **Verification:** All 9 tests still pass; warnings gone; ruff/mypy clean.
- **Committed in:** `6bcceb6` (Task 1 GREEN commit)

**2. [Rule 1 — Lint] Removed `# noqa: BLE001` comment, replaced with explanatory comment**
- **Found during:** Task 1 GREEN ruff check
- **Issue:** Ruff flagged `# noqa: BLE001` on `except Exception:` as an unused-noqa directive (BLE001 not enabled in our ruleset).
- **Fix:** Replaced the suppression with a plain explanatory comment: `# supervisor catches all Exception to self-heal (E-01)`.
- **Files modified:** `src/spark_modem/event_sources/supervisor.py`
- **Verification:** `ruff check` clean.
- **Committed in:** `6bcceb6` (Task 1 GREEN commit)

**3. [Rule 1 — Lint] Removed redundant `return` in clean-exit factory**
- **Found during:** Task 1 GREEN ruff check
- **Issue:** PLR1711 — useless `return` at end of function (the test's clean-exit factory had a trailing `return  # clean exit`).
- **Fix:** Removed the bare return; let the function fall off naturally.
- **Files modified:** `tests/unit/event_sources/test_supervisor.py`
- **Verification:** `ruff check` clean; test still semantically equivalent (factory returns None either way).
- **Committed in:** `6bcceb6` (Task 1 GREEN commit)

### Acceptance-criterion micro-deviation

The plan's acceptance criteria for Task 1 specify:
- `grep -r "MonitorObserver" src/spark_modem/event_sources/` returns no results
- `grep -r "signal.signal" src/spark_modem/event_sources/` returns no results

Both checks return ONE match each — but the match is inside the supervisor.py module docstring at line 28, which is **defensive documentation** explicitly citing the anti-patterns by name (`* No ``MonitorObserver``, no ``signal.signal``, no ``subprocess`` —`). No actual usage exists. Decision: keep the documentation; the intent of the acceptance criterion is "no usage of the anti-pattern," not "no mention of the name." The docstring strengthens the contract for future maintainers.

## Authentication Gates

None — Plan 03-01 is pure local code with no external service interactions.

## Threat Surface Scan

Threat register check passed: every threat in the plan's `<threat_model>` section that was assigned `mitigate` disposition has its mitigation in place:

- **T-03-01-01** (chronic-crash supervisor) — mitigated by Pitfall 15 uptime-reset + bounded backoff envelope; verified by `test_supervisor_resets_attempt_after_long_uptime` and `test_supervisor_backoff_envelope_1_2_4_8_60`.
- **T-03-01-02** (raw kmsg line entering wire surface) — mitigated by closed-enum extension; verified by `test_phase3_host_values_present`.
- **T-03-01-03** (TaskGroup-wide cancellation via single-producer Exception) — mitigated by `except Exception` catch (NOT BaseException); verified by `test_supervisor_passes_through_cancelled_error`.
- **T-03-01-04** (test fake leaking into production) — mitigated by tests/fakes/__init__.py re-export surface; production code never imports from `tests.*`. (No automated linter rule yet — Plan 03-06 may add `import-linter`.)
- **T-03-01-05** (free-form WakeSignal payload) — mitigated by closed StrEnum; pydantic validation will reject arbitrary strings at the wire boundary downstream.
- **T-03-01-06** (lost backoff observability via structured event) — accepted; Plan 03-06 wires the structured emission. Phase 03-01 logs via `logger.exception` only.

No new security-relevant surface introduced beyond the plan's threat model.

## Deferred Issues

**1. Pre-existing flaky test**
- **File:** `tests/unit/state_store/test_inventory_crosscheck.py::test_inventory_crosscheck_consistent_state_passes`
- **Symptom:** Failed on one full-suite run, passed in isolation and passed on retry of the full suite.
- **Cause:** Order-dependent / environment-dependent — UNRELATED to Plan 03-01 changes (the test predates this plan and exercises state-store logic untouched here).
- **Action:** Logged here; out-of-scope for Plan 03-01. May warrant a separate hardening pass under a Phase 4 stability sweep.

## Self-Check: PASSED

**Files exist:**
- FOUND: `src/spark_modem/event_sources/__init__.py`
- FOUND: `src/spark_modem/event_sources/supervisor.py`
- FOUND: `tests/fakes/sleeper.py`
- FOUND: `tests/fakes/asyncinotify.py`
- FOUND: `tests/unit/event_sources/__init__.py`
- FOUND: `tests/unit/event_sources/test_supervisor.py`
- FOUND: `tests/unit/wire/test_enums_phase3.py`

**Files modified (verified by `git log`):**
- FOUND: `src/spark_modem/wire/enums.py` modified in `9aa9717`
- FOUND: `tests/fakes/__init__.py` modified in `9aa9717`
- FOUND: `pyproject.toml` modified in `6bcceb6`

**Commits exist (verified by `git log --oneline -8`):**
- FOUND: `fb5e80f` test(03-01): add failing tests for WakeSignal + restart_on_crash supervisor
- FOUND: `6bcceb6` feat(03-01): implement event_sources supervisor + WakeSignal + Sleeper Protocol
- FOUND: `ffe321e` test(03-01): add failing contract tests for Phase 3 IssueDetail + FakeAsyncinotify
- FOUND: `9aa9717` feat(03-01): extend IssueDetail with 6 host-level kmsg values + ship FakeAsyncinotify

**Final acceptance:**
- `pytest -q` reports 1696 passed / 49 skipped / 0 failed in 16.65s
- `mypy --strict src/spark_modem/event_sources/ tests/fakes/sleeper.py tests/fakes/asyncinotify.py` reports 0 issues
- `ruff check` + `ruff format --check` green on every new/modified file
- `pytest --markers | grep linux_only` returns one match
- M7 budget preserved (16.65s ≤ 30s)

## TDD Gate Compliance

Plan 03-01 frontmatter is `type: execute`, but each task within is `type="auto" tdd="true"`. Per-task TDD gate sequence verified in git log:

| Task | RED commit (test) | GREEN commit (feat) | Gate sequence |
|------|-------------------|---------------------|---------------|
| Task 1 | `fb5e80f` test(03-01): add failing tests | `6bcceb6` feat(03-01): implement supervisor | RED-then-GREEN ✓ |
| Task 2 | `ffe321e` test(03-01): add failing contract tests | `9aa9717` feat(03-01): extend IssueDetail | RED-then-GREEN ✓ |

Both tasks demonstrated true RED before GREEN (verified by running pytest after RED commit and observing failure on the new tests; supervisor tests failed at collection-time with `ModuleNotFoundError`; enum tests failed at assertion-time with the missing-values frozenset).
