# T05: Plan 05

**Slice:** S03 — **Milestone:** M001

## Description

Wave 2 — `/dev/kmsg` reader + closed-enum regex classifier (E-03) +
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
