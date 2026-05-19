# T01: Plan 01

**Slice:** S03 — **Milestone:** M001

## Description

Build Wave 1 of Phase 3: the foundational scaffolding every producer and
lifecycle plan downstream consumes. Specifically:

  1. Create `src/spark_modem/event_sources/` package with the
     `restart_on_crash(name, factory, *, sleeper, event_logger,
     backoffs)` supervisor (Pattern 1 / E-01) and the closed
     `WakeSignal(StrEnum)` (E-02 — UDEV / RTNETLINK / ZAO_LOG /
     EVENTS_LOG_ROTATED / KMSG).
  2. Extend `wire/enums.py::IssueDetail` with the 5 host-level values
     plus `UNKNOWN` (E-03). This is the wire contract Plan 03-05's
     classifier maps regex to.
  3. Create the shared `tests/fakes/asyncinotify.py` and
     `tests/fakes/sleeper.py` fakes. Sleeper is consumed by the
     supervisor; FakeAsyncinotify is consumed by Plans 03-04 (Zao log +
     events.jsonl reopener) and 03-06 (lifecycle integration tests).
  4. Add the `linux_only` pytest marker to `pyproject.toml` so every
     downstream Linux-only test (~14 test files) can carry a single
     consistent marker.

Purpose: Wave 0 of the phase. Every other plan (03-02..03-06) imports
WakeSignal, may use restart_on_crash, and at least three import
FakeAsyncinotify. Lock these contracts before any producer ships so
downstream plans never hit a "what's the signature of X" round-trip.

Output: 8 new files + 1 modified (pyproject.toml markers) + 1 modified
(wire/enums.py append).
