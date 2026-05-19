# T06: Plan 06

**Slice:** S03 — **Milestone:** M001

## Description

Wave 3a — daemon-side lifecycle modules + main.py rewrite + wire/events.py
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
