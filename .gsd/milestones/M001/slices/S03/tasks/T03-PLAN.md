# T03: Plan 03

**Slice:** S03 — **Milestone:** M001

## Description

Wave 2 — pyroute2 rtnetlink producer. Smaller than Plan 03-02 because
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
