---
phase: 02-core-daemon-laptop-testable
plan: 03
subsystem: zao-log
tags: [zao, rascow_stat, fr-10, adr-0003, pydantic, protocol, runtime_checkable]

# Dependency graph
requires:
  - phase: 01-foundations-adrs
    provides: BaseWire (frozen, extra=forbid), wire-model patterns
  - phase: 02-01-test-fakes-and-fixture-roots
    provides: tests/fakes/zao_log.FixtureZaoTailer (extended in this plan)
provides:
  - ZaoSnapshot wire model (frozen BaseWire, frozenset[int] active_lines)
  - ZaoLogTailer runtime_checkable Protocol (is_line_active + snapshot)
  - ZaoLogParser file-read fallback (walk-backwards block detection)
  - 5 RASCOW_STAT log fixtures covering all-active / partial / none / stale / multi-block
  - Protocol-satisfaction guarantee for both production parser and test fake
affects: [02-04-observer, phase-3-inotify-tailer]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "runtime_checkable Protocol seam co-located with implementation (zao_log/protocol.py)"
    - "Walk-backwards block detection: ts-prefix anchors a contiguous burst; first non-RASCOW or ts-mismatch ends the run"
    - "ZaoSnapshot.unknown(reason=...) classmethod factory for missing/unparseable logs (T-02-03-04 safe-direction default)"
    - "Canonical-only unknown_reason strings (zao_log_missing / zao_log_io_error:<errno> / zao_log_no_rascow_stat) -- never embeds raw log content (T-02-03-03)"

key-files:
  created:
    - src/spark_modem/zao_log/__init__.py
    - src/spark_modem/zao_log/snapshot.py
    - src/spark_modem/zao_log/protocol.py
    - src/spark_modem/zao_log/parser.py
    - tests/unit/zao_log/__init__.py
    - tests/unit/zao_log/test_parser.py
    - tests/fixtures/zao_log/all_lines_active.log
    - tests/fixtures/zao_log/two_lines_active.log
    - tests/fixtures/zao_log/no_lines_active.log
    - tests/fixtures/zao_log/stale.log
    - tests/fixtures/zao_log/multiple_blocks_use_last.log
  modified:
    - tests/fakes/zao_log.py  # extended to satisfy ZaoLogTailer Protocol surface

key-decisions:
  - "ZaoLogTailer is @runtime_checkable so tests can assert isinstance() on both ZaoLogParser AND FixtureZaoTailer; observer/ in plan 02-04 calls the Protocol surface uniformly"
  - "ZaoSnapshot.active_lines is frozenset[int] (not set) so the wire model stays immutable under BaseWire frozen=True; mutation requires constructing a new snapshot"
  - "Walk-backwards block algorithm reads the full file each call (not last-N-lines) -- Phase 2 cycle cost bounded by logrotate (FR-43, 100 MiB cap); Phase 3's inotify tailer accumulates incrementally"
  - "unknown_reason is a canonical-string sum type (zao_log_missing | zao_log_io_error:<errno> | zao_log_no_rascow_stat); never embeds path or raw log content (T-02-03-03 information-disclosure mitigation)"
  - "ZaoSnapshot.unknown_reason DOES NOT directly skip the FR-10 gate at the ZaoSnapshot layer (is_line_active returns False). Observer/ in plan 02-04 must defensively read snapshot().unknown_reason and skip QMI probing when set (T-02-03-04 safe direction)"
  - "FixtureZaoTailer.snapshot() added (Rule 2 deviation) so the fake matches the new Protocol surface; tests for plan 02-04 will be able to inject canned snapshots without per-test parser construction"

patterns-established:
  - "Protocol seam pattern: zao_log/protocol.py defines the call surface, zao_log/parser.py is the Phase 2 file-read impl, Phase 3 will add an inotify impl behind the same Protocol -- observer/ never branches"
  - "ascii decode with errors='replace' + strict regex = malformed log lines silently skipped (T-02-03-01 tampering mitigation)"
  - "ISO/wall datetime arithmetic for diagnostics (log_age_seconds clamped to >=0); policy/ continues to use monotonic for correctness-critical durations (ADR-0007 split)"

requirements-completed:
  - FR-10

# Metrics
duration: ~4min
completed: 2026-05-06
---

# Phase 2 Plan 03: Zao Log Boundary Summary

**ZaoLogTailer Protocol seam + walk-backwards RASCOW_STAT parser deliver the FR-10/ADR-0003 gate that prevents the daemon from QMI-probing a Zao-active line.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-05-06T16:19:10Z
- **Completed:** 2026-05-06T16:22:45Z
- **Tasks:** 2
- **Files created:** 11
- **Files modified:** 1 (tests/fakes/zao_log.py — Rule 2 deviation, see below)

## Accomplishments

- `ZaoSnapshot` frozen wire-style record carrying `active_lines: frozenset[int]`, `last_block_iso`, `log_age_seconds`, and `unknown_reason`. `is_line_active(line_idx)` is the FR-10 gate observer/ calls before QMI-probing.
- `ZaoLogTailer` `@runtime_checkable` Protocol co-located in `zao_log/protocol.py`. Both the production parser AND `tests.fakes.zao_log.FixtureZaoTailer` satisfy it; observer/ in plan 02-04 will use the Protocol surface uniformly.
- `ZaoLogParser` Phase 2 file-read implementation: walks the log backwards from EOF and collects a contiguous run of `RASCOW_STAT` lines that share a single ISO timestamp prefix (the "block"). Earlier blocks are discarded; only the latest is reported. Phase 3's inotify-backed tailer will replace this without touching any caller.
- Five log fixtures (`all_lines_active`, `two_lines_active`, `no_lines_active`, `stale`, `multiple_blocks_use_last`) plus 9 parametrized parser tests including runtime_checkable isinstance assertions for both backends.
- Missing/unparseable logs return `ZaoSnapshot.unknown(reason=<canonical>)` rather than raising — the daemon stays up (T-02-03-01).

## Walk-backwards block algorithm

The Zao log emits a RASCOW_STAT block as a burst of consecutive lines that share the *same* ISO-8601 timestamp prefix. The parser:

1. Reads the entire file (`Path.read_bytes()` then `decode("ascii", errors="replace")`).
2. Iterates `reversed(lines)`. For each line, applies the strict regex `_RASCOW_RE` (anchored timestamp + `RASCOW_STAT` + `line=N` + `status=K`).
3. The first matching line fixes `block_ts` (the timestamp anchor for "this block").
4. Subsequent matching lines extend the block iff their `ts == block_ts`. A timestamp mismatch ends the walk.
5. A non-matching (non-RASCOW) line ends the walk *only after* `block_ts` is set; before that, it is silently skipped (lets the parser scan past trailing non-RASCOW logs at the file tail).
6. If `collected` is empty after the walk, returns `ZaoSnapshot.unknown(reason="zao_log_no_rascow_stat")`.

This pattern picks the LATEST block specifically — verified by `multiple_blocks_use_last.log` (an earlier all-active block at `10:00:00` is followed by a later partial block at `10:00:31`; the parser returns `frozenset({2, 3})`, NOT `frozenset({1, 2, 3, 4})`).

## Phase 3 swap-in

Phase 3 ships `ZaoLogInotifyTailer` (or similar) using `asyncinotify` per the project STACK.md. It will accumulate RASCOW_STAT lines incrementally as Zao writes them, avoiding the per-cycle full-file read. Critically:

- It satisfies the same `ZaoLogTailer` Protocol (`is_line_active` + `snapshot`).
- `observer/` in plan 02-04 imports the Protocol and accepts ANY satisfier — no branching on backend.
- The pyproject already has `asyncinotify` in the mypy ignore-missing-imports list, so the Phase 3 implementation can land cleanly.

## Task Commits

1. **Task 1: ZaoSnapshot wire model + ZaoLogTailer Protocol** — `c5141a7` (feat)
2. **Task 2: ZaoLogParser + 5 fixtures + 9 parametrized tests** — `f234c06` (feat)

(Plan-level metadata commit will follow this SUMMARY.)

## Files Created/Modified

**Created:**
- `src/spark_modem/zao_log/__init__.py` — package marker
- `src/spark_modem/zao_log/snapshot.py` — `ZaoSnapshot` frozen wire model + `unknown(reason=...)` factory
- `src/spark_modem/zao_log/protocol.py` — `ZaoLogTailer` runtime_checkable Protocol
- `src/spark_modem/zao_log/parser.py` — `ZaoLogParser` walk-backwards file-read implementation
- `tests/unit/zao_log/__init__.py` — test package marker
- `tests/unit/zao_log/test_parser.py` — 9 parametrized parser tests (5 fixtures + missing-file + 2 protocol-satisfaction + 1 unknown-factory)
- `tests/fixtures/zao_log/all_lines_active.log` — 4× active in one block
- `tests/fixtures/zao_log/two_lines_active.log` — lines 1+3 active, 2+4 inactive
- `tests/fixtures/zao_log/no_lines_active.log` — block present, all inactive
- `tests/fixtures/zao_log/stale.log` — booting/initializing, no RASCOW_STAT line
- `tests/fixtures/zao_log/multiple_blocks_use_last.log` — earlier all-active block + later partial block (parser must pick the later)

**Modified:**
- `tests/fakes/zao_log.py` — `FixtureZaoTailer.snapshot()` added (Rule 2 deviation, see below)

## Decisions Made

1. **`active_lines` as `frozenset[int]`, not `set[int]`** — pydantic BaseWire is frozen=True; the contained collections must also be hashable / immutable for principled wire boundaries. `frozenset` is the natural fit for "membership query, no mutation."
2. **Single `_RASCOW_RE` regex, anchored** — the ISO timestamp is captured as a single named group `ts`; the `^` anchor + ISO format prevents matching against malformed lines that happen to contain the substring `RASCOW_STAT line=...`.
3. **Walk-backwards over fully-read bytes (not seek + last-N-bytes)** — readability + simplicity beat marginal IO win at Phase 2; logrotate's 100 MiB cap (FR-43) bounds the cost. Phase 3's inotify accumulator avoids the re-read entirely.
4. **`unknown_reason` is canonical-string-only** — `zao_log_missing` / `zao_log_io_error:<errno>` / `zao_log_no_rascow_stat`. Never includes the file path or raw log content (T-02-03-03 information-disclosure mitigation).
5. **`FixtureZaoTailer.snapshot()` returns synthetic `ZaoSnapshot` with `unknown_reason=None`** — calling `is_line_active` on the synthetic snapshot delegates to the in-memory `_active_lines` set, matching the legacy fake behavior. Plan 02-04 tests can now use either the production parser or the fake without divergent call surfaces.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] Extended FixtureZaoTailer to satisfy ZaoLogTailer Protocol**
- **Found during:** Task 2 (writing `test_protocol_satisfied_by_fixture_tailer`)
- **Issue:** Plan 02-03 task 2 acceptance criteria (test 8) require `assert isinstance(FixtureZaoTailer(...), ZaoLogTailer)`, AND the plan frontmatter `must_haves.key_links` declares: `from: tests/fakes/zao_log.py to: src/spark_modem/zao_log/protocol.py via: FixtureZaoTailer satisfies ZaoLogTailer Protocol pattern: is_line_active|snapshot`. The Phase 1 / Plan 02-01 fake only had `is_line_active`; `runtime_checkable` Protocol membership requires every method to be present (else `isinstance` returns False). Without `snapshot()`, the Protocol-satisfaction test would fail AND observer/ in plan 02-04 would not be able to swap fake for production via duck typing.
- **Fix:** Added `snapshot()` method returning a synthetic `ZaoSnapshot` constructed from the configured `_active_lines` set, with `last_block_iso=None`, `log_age_seconds=None`, `unknown_reason=None`. Updated module docstring to reference the new Protocol explicitly.
- **Files modified:** `tests/fakes/zao_log.py`
- **Verification:** `python -m mypy --strict tests/fakes/zao_log.py` exits 0; `python -m pytest tests/unit/zao_log/test_parser.py::test_protocol_satisfied_by_fixture_tailer` passes; full unit suite (`python -m pytest`) reports `350 passed, 41 skipped` (no regressions).
- **Committed in:** `f234c06` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical functionality)
**Impact on plan:** The deviation is required by the plan itself (must_haves.key_links declares FixtureZaoTailer must satisfy the new Protocol). Adding `snapshot()` is the minimum change to honor the cross-file contract; the legacy `is_line_active` and `set_active` surface is preserved for backward compatibility with any callers that already exist. No scope creep.

## Threat surface scan

The plan's `<threat_model>` already enumerates T-02-03-01..04. No new security-relevant surface was introduced beyond what the threat register already covers; the implementation honors all four mitigations:

- **T-02-03-01 (Tampering):** ascii decode with `errors="replace"` + strict regex; non-RASCOW lines silently skipped; parse failures return `ZaoSnapshot.unknown()` rather than raising (verified by `test_stale_returns_unknown`).
- **T-02-03-02 (Large file DoS):** Accepted per FR-43 logrotate cap. No mitigation in this plan.
- **T-02-03-03 (Info disclosure):** `unknown_reason` carries only canonical strings; verified by code inspection (no f-strings interpolating `path` or log content).
- **T-02-03-04 (FR-10 bypass on unknown log):** `is_line_active(line)` returns `False` when `unknown_reason` is set (because `active_lines` is empty in that case). Observer/ in plan 02-04 MUST additionally consult `snapshot().unknown_reason` and skip QMI probing when set; the Protocol exposes `snapshot()` for exactly this purpose.

## Issues Encountered

None — both tasks executed cleanly. The only judgment call was the FixtureZaoTailer extension (documented as Rule 2 deviation above).

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **Plan 02-04 (observer/) unblocked.** It can now `from spark_modem.zao_log.protocol import ZaoLogTailer` and accept either `ZaoLogParser` (production) or `FixtureZaoTailer` (tests). The FR-10 gate is `if zao.is_line_active(modem.line_idx): return ModemSnapshot.zao_active(...)` (per RESEARCH.md §2.3).
- **Plan 02-04 should also defensively check `snapshot().unknown_reason`** — when the Zao log is missing/unparseable, the safe direction is to skip QMI probing rather than risk racing with Zao on a line whose state we cannot determine (T-02-03-04).
- **Phase 3 swap-in is purely additive** — adding an `asyncinotify`-backed `ZaoLogInotifyTailer` behind the same Protocol leaves observer/ untouched.

## Self-Check: PASSED

All 12 created files exist on disk; both task commits (`c5141a7`, `f234c06`) are present in `git log --oneline --all`. The modified file `tests/fakes/zao_log.py` was confirmed updated via `Read` after the edit.

---
*Phase: 02-core-daemon-laptop-testable*
*Completed: 2026-05-06*
