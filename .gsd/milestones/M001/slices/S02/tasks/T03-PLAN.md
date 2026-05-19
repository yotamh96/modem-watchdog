# T03: 02-core-daemon-laptop-testable 03

**Slice:** S02 — **Milestone:** M001

## Description

Plan 02-03 lands the Zao log boundary needed for FR-10 (the `RASCOW_STAT`
gate that prevents the daemon from QMI-probing a Zao-active line).

Phase 2 ships the file-read fallback (`ZaoLogParser.snapshot()` walks the
log backward to find the most recent `RASCOW_STAT` block); Phase 3 swaps
in an inotify-backed implementation behind the same `ZaoLogTailer` Protocol
surface — Phase 2 callers (observer/) never need to change.

Purpose: the observer (plan 02-04) calls `tailer.is_line_active(line_idx)`
before invoking qmicli on any modem. If the line is bonding-active under
Zao, we must not probe — Zao requires exclusive access (`ModemManager` is
masked for the same reason).

Output: `zao_log/protocol.py` + `parser.py` + `snapshot.py` plus five log
fixture scenarios + parametrized parser tests.

## Must-Haves

- [ ] "ZaoLogTailer Protocol exposes is_line_active(line_idx: int) -> bool and snapshot() -> ZaoSnapshot."
- [ ] "ZaoLogParser.snapshot() returns the LATEST RASCOW_STAT block (walks backwards from EOF)."
- [ ] "ZaoSnapshot.is_line_active(line_idx) returns True iff that line was 'active' in the most recent block."
- [ ] "An empty / missing log file returns ZaoSnapshot.unknown(reason=...) with empty active set."
- [ ] "Phase 3 inotify swap is invisible to callers (Protocol surface preserved)."

## Files

- `src/spark_modem/zao_log/__init__.py`
- `src/spark_modem/zao_log/protocol.py`
- `src/spark_modem/zao_log/parser.py`
- `src/spark_modem/zao_log/snapshot.py`
- `tests/unit/zao_log/__init__.py`
- `tests/unit/zao_log/test_parser.py`
- `tests/fixtures/zao_log/all_lines_active.log`
- `tests/fixtures/zao_log/two_lines_active.log`
- `tests/fixtures/zao_log/no_lines_active.log`
- `tests/fixtures/zao_log/stale.log`
- `tests/fixtures/zao_log/multiple_blocks_use_last.log`
