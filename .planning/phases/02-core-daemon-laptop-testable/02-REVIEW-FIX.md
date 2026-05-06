---
phase: 02-core-daemon-laptop-testable
fixed_at: 2026-05-06T00:00:00Z
review_path: .planning/phases/02-core-daemon-laptop-testable/02-REVIEW.md
iteration: 1
findings_in_scope: 9
fixed: 9
skipped: 0
status: all_fixed
---

# Phase 2: Code Review Fix Report

**Fixed at:** 2026-05-06T00:00:00Z
**Source review:** `.planning/phases/02-core-daemon-laptop-testable/02-REVIEW.md`
**Iteration:** 1

**Summary:**

- Findings in scope: 9 (1 critical + 8 warnings; info findings out of scope)
- Fixed: 9
- Skipped: 0

**Verification (per-fix and post-batch):**

- `mypy --strict src/spark_modem` — clean (103 source files)
- `ruff check src/ tests/` — All checks passed
- `ruff format --check` — only 11 pre-existing unformatted files in
  unmodified parts of the tree; every file I touched is formatted
- Full test suite: `pytest tests/unit tests/integration` — **661 passed,
  49 skipped** (skips are Linux-only POSIX subprocess tests and Linux
  sysfs-tree simulations — irrelevant on Windows dev box)

## Fixed Issues

### CR-01: Webhook X-Spark-Timestamp uses time.monotonic() instead of Unix wall-clock

**Files modified:**

- `src/spark_modem/webhook/poster.py`
- `src/spark_modem/cli/clients.py`
- `tests/fakes/clock.py`
- `tests/unit/webhook/test_poster.py`
- `tests/unit/webhook/test_drain.py`

**Commit:** `02deac5`

**Applied fix:** Added `unix_seconds() -> int` to `ClockProto`, `_CliClock`,
`FakeClock`, and the inline `_StepClock` test helper. Replaced
`int(self._clock.monotonic())` at `webhook/poster.py:241` with
`self._clock.unix_seconds()`. Per FR-44.2 / ADR-0011 and CLAUDE.md
invariant #4 — `monotonic()` is for durations only; wire-format
wall-clock stamps go through `unix_seconds()` / `wall_clock_iso()`.
Added regression test `test_x_spark_timestamp_is_unix_wall_clock_seconds`
that asserts the header equals `clock.unix_seconds()` AND `> 1.7e9`
(catches a regression to monotonic-shaped values).

This was the load-bearing fix — Phase 3 webhook receiver wiring
otherwise rejects every authentic POST as expired.

### WR-01: `exhausted` state has no escape path in transitions.py

**Files modified:**

- `src/spark_modem/policy/transitions.py`
- `tests/unit/policy/test_transitions.py`

**Commit:** `8c400c8`

**Applied fix:** The `exhausted -> healthy` recovery path was served
only by the early-return at the top of `transition()`. Refactoring or
moving that early-return would silently strand modems forever in
`exhausted`, regressing Success Metric M4. Added an explicit
`if not snap.issues and not rf_blocked: return _to_healthy(...)` inside
the `case "exhausted":` arm — equivalent today but defensive against
future refactors. Added two regression tests:
`test_exhausted_to_healthy_on_clear_snapshot` and
`test_exhausted_with_rf_blocked_only_stays_exhausted` (boundary).

### WR-02: Lexicographic ISO-8601 comparison fragile across timezones

**Files modified:**

- `src/spark_modem/cli/ctl/maintenance.py`
- `src/spark_modem/cli/ctl/history.py`

**Commit:** `fece858`

**Applied fix:** Both sites now parse ISO timestamps through
`datetime.fromisoformat` and compare as `datetime` objects rather than
strings. Lexicographic ordering is correct only when both sides are in
the same canonical form (UTC `+00:00`); a future writer or a
hand-edited globals.json with a different timezone offset would
produce ordering bugs (`2026-05-06T01:00:00+00:00` lexicographically
sorts AFTER `2026-05-06T02:00:00+02:00` even though they represent the
same instant). Unparseable values degrade safely (maintenance: falls
back to monotonic-only check; history: skips the event).

### WR-03: WebhookPoster.drain ignores next_retry_monotonic

**Files modified:**

- `src/spark_modem/webhook/poster.py`

**Commit:** `be1da86`

**Applied fix:** Documentation-only — the W-01 SLO promises "ONE attempt
per queued item within budget" which is satisfied by the current
behaviour. Honouring per-item backoff in `drain()` would either waste
the shutdown budget on `asyncio.sleep` or risk infinite requeue loops
if the budget expires before any item's backoff clears. Receiver
idempotency is the relevant contract. Updated the `drain()` docstring
to call out the design choice and its rationale explicitly.

### WR-04: re.MULTILINE documented but not used in get_signal.py

**Files modified:**

- `src/spark_modem/qmi/parsers/get_signal.py`

**Commit:** `d3aa37c`

**Applied fix:** Honestly rewrote the comment to describe the actual
"first match in document order across the whole stdout" behaviour. The
EM7421 is LTE-only hardware so the NR5G+LTE bleed never fires in
production. Adding `re.MULTILINE` alone would NOT fix the
cross-section bleed (`re.search` would still return the first match
across the whole input); the real fix needs body-splitting on
`^(LTE|NR5G):$`. The existing canonical NR5G+LTE fixture
(`tests/fixtures/qmicli/get_signal/1.32/nr5g_present.txt`) and matching
parametrised parser test already lock the observable semantics.
Comment now points future contributors at the correct refactor path.

### WR-05: SysfsInventory._line_from_usb_path silently degrades to line=1

**Files modified:**

- `src/spark_modem/inventory/sysfs.py`
- `tests/unit/inventory/test_sysfs.py`

**Commit:** `325b77c`

**Applied fix:** `_line_from_usb_path` now returns `int | None` (`None`
on malformed input) and `scan()` skips descriptors with `line is None`.
Previously the method returned `_LINE_MIN` (=1) for both numeric-out-
of-range and non-numeric tails, which would silently conflate two
distinct USB devices on the same Zao line — a correctness bug for the
FR-10 gate that keys on `line`. Updated `test_line_from_usb_path` to
assert `is None` for `'2-3.1.0'`, `'foo'`, and `'2-3.1.100'`.

### WR-06: Observer surfaces connection_status='disconnected' even when value is missing

**Files modified:**

- `src/spark_modem/observer/issue_extractor.py`
- `tests/unit/observer/test_orchestrator.py`

**Commit:** `6f88e23`

**Applied fix:** No behaviour change in `src/`. The "disconnected only"
behaviour was already correct (intermediate libqmi states such as
`limited`, `flow-controlled`, `connecting`, `disconnecting` are
transient and the policy decision-table has no actionable response),
but it was not pinned by a test. Added an explanatory comment on the
SESSION_DISCONNECTED branch and a parametrised test
`test_extract_issues_intermediate_data_states_do_not_surface` plus the
positive `test_extract_issues_disconnected_session_produces_datapath_issue`
so a future libqmi schema change cannot silently drift the trigger set.

### WR-07: Inconsistent ASYNC240 sync-read suppression in cli/recovery.py

**Files modified:**

- `src/spark_modem/cli/recovery.py`

**Commit:** `b69be89`

**Applied fix:** Pulled the inline `diag_path.read_bytes()  # noqa: ASYNC240`
out of the async `run()` body into a sync helper
`_load_diag_fixture_sync`. Matches the existing
`daemon/main.py:_ensure_dirs` pattern. The `support_bundle.py` and
`history.py` cases the reviewer flagged were actually already fine —
their sync I/O lives in already-sync helper functions called from the
async surface, so no `noqa` was ever needed there. Recovery.py was the
only inconsistent suppression site. No behaviour change.

### WR-08: cli/diag.py default inventory path is relative to CWD

**Files modified:**

- `src/spark_modem/cli/diag.py`
- `src/spark_modem/daemon/main.py`
- `tests/unit/cli/test_diag.py`

**Commit:** `c2e7d3f`

**Applied fix:** Both fix variants the reviewer offered, combined.
Anchored `_DEFAULT_INVENTORY` (cli/diag.py) and `_LAPTOP_INVENTORY_PATH`
(daemon/main.py) to `Path(__file__).resolve().parents[3]` (= repo
root) so the laptop CLI works from any CWD. cli/diag.py also adds an
explicit fail-fast: `inventory file not found: <path>` on stderr +
return code 2 when the file is absent (instead of silently producing
`per_modem: {}`). daemon/main.py constant is module-level so the async
`main()` body stays free of pathlib I/O (ASYNC240). Added regression
test `test_diag_with_missing_inventory_fails_fast`.

## Skipped Issues

None — all in-scope findings were addressed.

---

_Fixed: 2026-05-06T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
