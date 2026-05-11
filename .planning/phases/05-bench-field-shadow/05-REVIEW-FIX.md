---
phase: 05-bench-field-shadow
fixed_at: 2026-05-11T10:11:07Z
review_path: .planning/phases/05-bench-field-shadow/05-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 5: Code Review Fix Report

**Fixed at:** 2026-05-11T10:11:07Z
**Source review:** `.planning/phases/05-bench-field-shadow/05-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope (critical + warning): 5
- Fixed: 5
- Skipped: 0

All five in-scope findings (1 Critical + 4 Warning) were fixed atomically.
Six Info-class findings (IN-01 .. IN-06) were out of scope for this iteration
and remain in REVIEW.md as is.

Methodology: TDD discipline at the regression-test level — each fix
landed as RED (failing test asserting the bug) → GREEN (apply patch,
all tests pass) → COMMIT. Every commit individually passes the project
quality gate (ruff check, ruff format, mypy --strict on src/, pytest,
SP-04 invariant).

## Fixed Issues

### CR-01: PII-redaction regex misses `IPv4 gateway address` and `IPv4 subnet mask`

**Files modified:** `src/spark_modem/cli/redact.py`, `tests/unit/cli/test_redact_raw_qmicli.py`
**Commit:** 03f1a2b
**Applied fix:** Replaced the literal `IPv4 address:` pattern with the
generalised label-prefix pattern `IPv4[^:'\n]*:` so every `IPv4 *: '...'`
shape qmicli can emit is now redacted in one expression (address /
subnet mask / gateway address / primary DNS / secondary DNS). Added
four new unit tests (subnet mask, gateway address, primary DNS, plus
a fixture-roundtrip regression against
`tests/fixtures/qmicli/get_current_settings/1.30/raw_ip_y.txt`) that
all FAIL before the fix and PASS after.

### WR-01: Audit tools read full Zao log without size cap (DoS)

**Files modified:** `tools/audit_soak_zao.py`, `tests/unit/tools/test_audit_soak_zao.py`
**Commit:** 3a2dc11
**Applied fix:** Refactored `_parse_zao_blocks` from `Path.read_text()`
(unbounded full-file load) to a stat-then-stream design:

  - Stat the file up-front and raise `RuntimeError` for files larger
    than `_MAX_ZAO_LOG_BYTES` (1 GiB) with a clear operator-visible
    error pointing at log rotation / pre-filtering as the remedy.
  - Iterate the file line-by-line with `with open(...) as fh:` so a
    multi-MiB Zao log no longer balloons RSS during an audit run.

The parser contract is preserved (block ordering, active-line
detection, missing-file -> `[]`). Added three regression tests
(size-cap RuntimeError via monkeypatched cap, 5-block streaming
roundtrip, missing-file fallback).

### WR-02: `_capture_one_modem` failure path may write un-redacted `{exc!s}` to disk

**Files modified:** `src/spark_modem/cli/ctl/capture_fleet_fixture.py`, `tests/unit/cli/ctl/test_capture_fleet_fixture.py`
**Commit:** edfac19
**Applied fix:** Routed the broad-except failure stub through
`redact_pii_from_raw_qmicli` before writing to disk. Previously
`f"... {type(exc).__name__}: {exc!s}\n"` was written raw — if an
underlying exception (a Pydantic ValidationError, a stderr-bearing
RuntimeError, etc.) ever carried PII-shaped text in its `str()`,
that text would land in the captured fixture and ship in the support
bundle. The redacted-stub path now matches the success-path
redaction so the surface is consistent end-to-end.

Added `test_capture_failure_message_is_redacted` that monkeypatches
`subproc_runner.run` to raise a `RuntimeError` whose message embeds
an ICCID-shaped value, exercises `_capture_one_modem` directly, and
asserts every per-verb stub on disk contains a redaction token and
no raw ICCID.

### WR-03: `redact_pii_from_raw_qmicli` does not cover IMEI / MEID / ESN / MSISDN labels

**Files modified:** `src/spark_modem/cli/redact.py`, `tests/unit/cli/test_redact_raw_qmicli.py`
**Commit:** def4c94
**Applied fix:** Added four new patterns to `_RAW_QMICLI_PII_PATTERNS`
covering device-identity labels emitted by `dms_get_ids` (IMEI, MEID,
ESN, MSISDN). The verb is not in `QMICLI_CAPTURE_VERBS` today, but
defense-in-depth: a future verb-list expansion (or any other code
path that feeds raw qmicli stdout through this redactor) must not
silently leak device identity. MSISDN (subscriber phone number) is
the strongest PII of the four — adding it now closes the latent gap
before the next reviewer has to spot it.

All four patterns use the same `(LABEL:\s*')([^']+)(')` shape as the
existing ones. Added five new unit tests (per-label + combined
`dms_get_ids`-shaped roundtrip that exercises `IMEI software version`
as a non-PII sibling that must pass through untouched, plus the four
PII labels which produce exactly four redaction tokens).

### WR-04: ISO-8601 string comparison in `_find_contemporaneous_block` breaks on mixed zone offsets

**Files modified:** `tools/audit_soak_zao.py`, `tests/unit/tools/test_audit_soak_zao.py`
**Commit:** 04d401e
**Applied fix:** Introduced `_normalise_iso_ts` that wraps
`datetime.fromisoformat` (Python 3.12 accepts both `Z` and `+HH:MM`
suffixes). Refactored both string-comparison sites:

  - `_find_contemporaneous_block`: parses both `event_ts` and each
    block `ts_iso` to datetime before comparing.
  - `_audit`: pre-parses `--since-iso` once and compares per-event
    parsed datetimes against it, so the lower-bound filter is also
    robust to mixed zone shapes.

The original bug was that `Z` (0x5A) sorts AFTER `+` (0x2B) under
Python string ordering, so a Zao build that emits `Z` paired with
daemon events that emit `+00:00` (or vice-versa) would silently miss
real M4 violations by classifying them as `no_zao_snapshot_for_cycle`.

Added two regression tests:
  - `test_mixed_zone_offset_z_and_plus_zero_match` — active-line
    violation across mixed zone shapes.
  - `test_mixed_zone_offset_plus_zero_event_z_block_clean` — inactive
    line, same wallclock, must classify as clean (not unknown).

---

## Out-of-scope (Info findings, not addressed this iteration)

These remain in REVIEW.md and may be picked up by `/gsd-code-review-fix
--scope=all` or as opportunistic improvements during Phase 6 work:

- IN-01: Duplicated `if not args.skip_preflight:` guard in
  `daemon/main.py`.
- IN-02: `_DEFAULT_ZAO_LOG_PATH` duplicated across two modules; could
  be promoted to `spark_modem.zao_log.paths`.
- IN-03: `_read_events_as_raw_dicts` is duplicated verbatim across the
  two audit tools; reviewer deferred to Phase 6.
- IN-04: `dms_get_revision` parser regex is not line-anchored; would
  match `Firmware Revision:` if qmicli ever emits one.
- IN-05: `audit_soak_exhausted._resolve_decay_k_default` silently
  swallows `ImportError`/`AttributeError`.
- IN-06: `capture-fleet-fixture` exit-code conflation between "no
  modems" and general failure.

## Verification

**Full repo test suite** (post-fix, all five fixes applied):
- 2050 passed
- 91 skipped (POSIX-only tests on Windows dev laptop)
- 0 failed
- Duration: 25.75s (M7 budget ≤30s — within budget)

**SP-04 invariant** (`grep -r 'create_subprocess_exec' src/` outside
`subproc/` must be empty):
- Only match: `src/spark_modem/subproc/runner.py:146` (the wrapper itself)
- `bash scripts/lint_no_subprocess.sh`: PASS

**Per-commit quality gate** (verified before each commit):
- `ruff check` on touched files
- `ruff format --check` on touched files
- `mypy --strict` on touched src/ files
- `pytest` on touched test files (RED before, GREEN after)
- SP-04 lint script

**Note on pre-existing format/lint debt:** Two pre-existing format
issues in `tests/unit/cli/ctl/test_capture_fleet_fixture.py` (lines
36-41, 63-72, 116-118) and one pre-existing E501 in
`tests/unit/tools/test_audit_soak_zao.py:127` were observed during
the quality gate but NOT touched — they pre-date the Phase 5 review
and are out of scope for this fix iteration. My added lines are
format-clean.

---

_Fixed: 2026-05-11T10:11:07Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
