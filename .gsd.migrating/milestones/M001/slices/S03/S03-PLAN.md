# S03: Linux Event Sources Lifecycle

**Goal:** Build Wave 1 of Phase 3: the foundational scaffolding every producer and
lifecycle plan downstream consumes.
**Demo:** Build Wave 1 of Phase 3: the foundational scaffolding every producer and
lifecycle plan downstream consumes.

## Must-Haves


## Tasks

- [x] **T01: Plan 01** `est:12min`
  - Build Wave 1 of Phase 3: the foundational scaffolding every producer and
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
- [x] **T02: Plan 02** `est:13min`
  - Wave 2 — pyudev producer + UdevInventory swap + netns end-to-end.
Specifically:

  1. `src/spark_modem/event_sources/udev_producer.py` — `run_udev_producer`
     coroutine using `pyudev.Monitor.from_netlink(Context())` +
     `loop.add_reader(monitor.fileno(), on_readable)` (PITFALLS §7.1
     PRESCRIPTIVE — never `MonitorObserver`). Body: `event_queue.put_nowait(
     WakeSignal.UDEV)` only. NO sysfs reads, NO parsing, NO state
     (E-02).
  2. `src/spark_modem/inventory/udev.py` — `UdevInventory` satisfies the
     existing `InventorySource` Protocol. Internally delegates the sysfs
     walk to `SysfsInventory` (composition; the walk shape is shared).
  3. `src/spark_modem/inventory/netns.py` — `derive_ns(usb_dev_path:
     Path) -> str | None`. Pure function (per PATTERNS.md analog: same
     staticmethod shape as `_find_cdc_wdm` / `_find_wwan_iface`). The
     derivation source is Open Question 4 in RESEARCH.md — pick option
     (a) sysfs `/proc/.../ns/net` of the cdc-wdm worker AND fall back
     to None on file-absent (single-namespace bench is the Phase 3
     reality; production fleet decides later).
  4. `src/spark_modem/inventory/sysfs.py` — replace the literal `ns=None`
     at line 79 with `ns=derive_ns(resolved)`. Single-line edit per
     PATTERNS.md "MODIFIED: inventory/sysfs.py" guidance.
  5. `src/spark_modem/qmi/wrapper.py` — extend `QmiWrapper.__init__`
     with optional `ns: str | None = None`; add a private `_argv(self,
     qmicli_args: list[str]) -> list[str]` helper that prepends `["ip",
     "netns", "exec", self._ns]` when `self._ns is not None`; rewrite
     every existing method's argv-construction call site to route
     through `self._argv([...])`. NEVER `setns()` from asyncio (PITFALLS
     §6.2 — the `ip netns exec` subprocess does its own setns in a
     forked child).
  6. Test seams: `tests/fakes/udev.py` (FakeUdevMonitor), unit tests
     for the producer + UdevInventory + derive_ns + QmiWrapper netns
     prepend.

Purpose: Plans 03-03/04/05 each ship one producer; this plan ships the
udev producer and the netns end-to-end because netns derivation is
inventory-resident (E-05) and qmicli netns-aware invocation is the
direct consumer. Splitting them across two plans would cross a clean
seam unnecessarily.

Output: 5 new production files + 2 modified production files + 4 new
test files.
- [x] **T03: Plan 03** `est:6min`
  - Wave 2 — pyroute2 rtnetlink producer. Smaller than Plan 03-02 because
the producer is "tight read loop, do nothing in body" by design
(PITFALLS §6.1).

Specifically:

  1. `src/spark_modem/event_sources/rtnetlink_producer.py` —
     `run_rtnetlink_producer` coroutine that opens
     `pyroute2.AsyncIPRoute()` via async context manager, sets
     SO_RCVBUF=4MiB, binds to RTMGRP_LINK, loops `async for _msg in
     ipr.get():` pushing `WakeSignal.RTNETLINK` per message.
  2. `tests/fakes/rtnetlink.py` — `FakeAsyncIPRoute` async context
     manager + async-iterable that mirrors the surface
     run_rtnetlink_producer touches.
  3. `tests/unit/event_sources/test_rtnetlink_producer.py` —
     subscription-success, ENOBUFS-propagation, message-iteration
     coverage.

Purpose: The link-state subsystem ships in its own plan (Wave 2) so
udev/inotify/kmsg can run in parallel. ENOBUFS handling is a
self-healing concern: rather than try-except in the producer, we let
the OSError escape so the supervisor (Plan 03-01) restarts the factory
and emits the structured event.

Output: 1 new production file + 1 new test fake + 1 new test file.
- [x] **T04: Plan 04** `est:13min`
  - Wave 2 — asyncinotify-backed log rotation handling for BOTH our own
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
- [x] **T05: Plan 05** `est:9min`
  - Wave 2 — `/dev/kmsg` reader + closed-enum regex classifier (E-03) +
per-detail 30s dedup window for FR-14 host-level issue surfacing.

Specifically:

  1. `src/spark_modem/kmsg/__init__.py` — package marker.
  2. `src/spark_modem/kmsg/classifier.py` — `KMSG_PATTERNS:
     tuple[tuple[Pattern[str], IssueDetail], ...]` table mapping
     regex to IssueDetail enum (the 5 host-level values from Plan
     03-01 Task 2). `def classify(line: str) -> IssueDetail`
     scans patterns in order, returns first match or
     `IssueDetail.UNKNOWN`.
  3. `src/spark_modem/kmsg/dedup.py` — `KmsgDedup.should_emit(detail)`
     analog of `webhook/dedup.py::DedupTable` (Phase 2): per-detail
     30s window; first call returns True; subsequent calls within
     window return False and bump repeat_count; first call after
     window expires returns True with the suppressed repeat_count
     accessible.
  4. `src/spark_modem/event_sources/kmsg_producer.py` —
     `run_kmsg_producer` opens `/dev/kmsg` with `O_RDONLY|O_NONBLOCK`,
     `lseek(SEEK_END)` to skip historical buffer, registers
     `loop.add_reader(fd, on_readable)`. on_readable drains in a
     loop (`os.read(fd, 8192)` until BlockingIOError), parses
     `<priority>,<seq>,<ts>,<flags>;<message>` format, classifies
     the message, dedups, emits Issue (via injected `IssueEmitter`
     Protocol) + pushes WakeSignal.KMSG.
  5. Tests: classifier table coverage (one fixture per IssueDetail
     value), dedup window behavior (FakeClock), producer flow
     end-to-end with FakeKmsgReader.

Purpose: FR-14 is the only Phase 3 requirement that introduces a
brand-new wire surface (host-level Issue.detail values). Splitting
classifier + dedup + producer into one plan keeps the closed-enum
contract and the dedup window in one cohesive change. Phase 4
destructive-action gating (e.g. suppress usb_reset when
USB_OVERCURRENT is the active host issue) reads from this surface.

Output: 4 new production files + 1 modified package marker + 4 new
test files + 5 new fixture files.
- [x] **T06: Plan 06** `est:17min`
  - Wave 3a — daemon-side lifecycle modules + main.py rewrite + wire/events.py
extension for two new variants (EventSourceCrashed + SimSwapped). This plan
delivers everything that's unit-testable on Windows via FakeSdNotify +
FakePIDLock + asyncio.Event signal injection. The cycle_driver SIM-swap
detection lives in Plan 03-07 (depends on this plan's wire variants);
systemd unit hardening lives in Plan 03-08; integration tests + bench-Jetson
checkpoint live in Plan 03-09.

Specifically:

  1. Lifecycle modules: preflight.py + lifecycle.py + sigterm.py + sighup.py.
  2. main.py rewrite: long-lived TaskGroup with 5 producers + cycle driver
     + 2 signal watchers; WATCHDOG=1 fires at cycle END not start.
  3. wire/events.py: add EventSourceCrashed + SimSwapped Event variants
     (closes Open Question 2 from RESEARCH.md — supervisor emits structured
     events; cycle driver in Plan 03-07 emits SimSwapped).
  4. Test seams: FakeSdNotify, FakePIDLock; 5 unit test files for the
     daemon-side modules.

Output: 5 new daemon modules + 1 modified daemon module (main.py) +
1 modified wire module (events.py) + 2 new test fakes + 6 new test files.
- [x] **T07: 03-linux-event-sources-lifecycle 07** `est:9min`
  - Wave 3b — cycle_driver SIM-swap detection + StateStore atomic streak/counters
reset. Depends on Plan 03-06's SimSwapped wire variant.

Specifically:

  1. Add `StateStore.reset_modem_streak_and_counters(usb_path: str)` public
     method that takes the per-modem asyncio.Lock + flock and resets
     `_healthy_streak` + all escalation counters in ONE atomic write per
     RECOVERY_SPEC §8 ordering. (Issue #9.)
  2. Insert SIM-swap detection into `daemon/cycle_driver.py` per-cycle
     pipeline: load identity map, compare against current observation,
     persist updated map, call `reset_modem_streak_and_counters` for each
     swapped usb_path, emit SimSwapped event with sha256[:8]-redacted ICCIDs.
  3. Two unit tests: one for the StateStore method (atomic ordering), one
     for the cycle-driver integration (E-04 / FR-4 latency = one cycle;
     SimSwapped event emitted via event_logger.append, NOT logger.info).

This plan was carved out of the original Plan 03-06 to keep that plan
focused on lifecycle modules + main.py rewrite. SIM-swap detection is its
own concern (state-store extension + cycle-driver integration); splitting
keeps each plan within context budget.

Output: 1 modified state-store module + 1 modified daemon module + 2 new
test files.
- [x] **T08: 03-linux-event-sources-lifecycle 08** `est:4min`
  - Wave 3b — systemd unit hardening (U-01..U-05) + logrotate snippet (R-02)
+ unit-file-audit integration test that pins every directive.

Specifically:

  1. Edit `debian/spark-modem-watchdog.service` to apply U-01..U-05 in full
     (preallocated Phase 4 caps, StartLimit overrides, WatchdogSec=90s,
     RuntimeDirectoryPreserve=yes, ExecStartPre=config-check, drop
     PrivateMounts/PrivateTmp/PrivateDevices for /dev/kmsg compat).
  2. Write `debian/spark-modem-watchdog.logrotate` per R-02 verbatim
     (create mode, rotate 7, size 100M, EMPTY postrotate).
  3. Write `tests/integration/test_unit_file_audit.py` that parses the
     .service file as plain text and asserts every directive — cross-platform
     (no linux_only marker; pure file parse).

This plan was carved out of the original Plan 03-06 to keep that plan
focused on lifecycle modules + main.py rewrite. The systemd / logrotate
files have no source-code dependency on Plans 03-06/03-07, so this plan
runs in parallel with Plan 03-07 (no file overlap).

Output: 1 modified .service file + 1 new .logrotate file + 1 new
integration test file.
- [x] **T09: Plan 09** `est:~2min (continuation agent only; Tasks 1-2 took ~6min in the prior agent run; total wallclock ~8min for the plan including the human-verify pause + continuation handoff)`
  - Wave 3c — integration tests + bench-Jetson human-verify checkpoint. Depends
on Plans 03-06 (lifecycle modules + main.py), 03-07 (cycle_driver SIM-swap
detection), 03-08 (systemd unit + logrotate snippet) — this plan is the
phase exit gate.

Specifically:

  1. Establish the integration test tier:
     `tests/integration/__init__.py` (package marker) and
     `tests/integration/conftest.py` (shared fixtures only — does NOT
     auto-add linux_only marker per Issue #6 RESOLVED).
  2. `tests/integration/test_lifecycle.py` covers SC #1..#5 end-to-end
     via Fake* injection. Module-level
     `pytestmark = pytest.mark.linux_only` so Windows dev hosts skip
     cleanly.
  3. `tests/integration/test_logrotate_create.py` exercises real
     logrotate cron via subprocess. Module-level
     `pytestmark = pytest.mark.linux_only`.
  4. CHECKPOINT — bench Jetson hardware verification of the 4 hardware-only
     SC paths (NFR-12, NFR-13, SC #1, SC #4, SC #5 real-hardware portions).

This plan was carved out of the original Plan 03-06 to keep that plan
focused on lifecycle modules + main.py rewrite. Integration tests
naturally come last because they exercise the prior plans' outputs.

Output: 4 new integration test files; checkpoint blocks phase exit.

## Files Likely Touched

- `src/spark_modem/daemon/cycle_driver.py`
- `src/spark_modem/state_store/store.py`
- `tests/unit/daemon/test_sim_swap_detection.py`
- `tests/unit/state_store/test_reset_modem_streak_and_counters.py`
- `debian/spark-modem-watchdog.service`
- `debian/spark-modem-watchdog.logrotate`
- `tests/integration/test_unit_file_audit.py`
