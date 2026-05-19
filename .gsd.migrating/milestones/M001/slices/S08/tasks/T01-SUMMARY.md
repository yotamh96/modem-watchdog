---
id: T01
parent: S08
milestone: M001
provides: []
requires: []
affects: []
key_files: []
key_decisions: []
patterns_established: []
observability_surfaces: []
drill_down_paths: []
duration: 
verification_result: passed
completed_at: 2026-05-12
blocker_discovered: false
---
# T01: 05.3-libqmi-version-regex-hotfix 01

**# Plan 05.3-01 — SUMMARY**

## What Happened

# Plan 05.3-01 — SUMMARY

## What was done

Three changes landed in a single hotfix commit:

1. **`src/spark_modem/qmi/version.py`** — `_LIBQMI_VERSION_RE` broadened
   from `r"libqmi-glib\s+(\d+\.\d+\.\d+)"` to
   `r"(?:qmicli|libqmi-glib)\s+(\d+\.\d+\.\d+)"`. Inline comment now
   documents the JetPack `qmicli`-only format, the lockstep-versioning
   rationale between `qmicli` and `libqmi-glib`, and the bench deploy that
   surfaced the bug.

2. **`tests/fixtures/qmicli/version/1.30/jetpack-1.30.4.txt`** — new
   fixture capturing the bench Jetson's exact `qmicli --version` stdout
   (5 substantive lines: qmicli banner + Copyright + GPLv2+ + freedom +
   no warranty). Includes a `#`-comment header with source / capture
   date / distinguishing trait.

3. **`tests/unit/qmi/test_version.py`** — new test
   `test_detect_libqmi_version_parses_jetpack_qmicli_only_format` reads
   the new fixture, stubs `subproc_runner.run` via the existing
   `_make_cp` helper, and asserts the parsed version is `"1.30.4"`.
   Inserted between the existing 1.30 and 1.32 tests to keep the file
   grouped by libqmi version.

## Verification

**Local (dev host):**
- `uv run mypy --strict src/spark_modem/qmi/version.py` — 0 issues
- `uv run ruff check src/spark_modem/qmi/version.py tests/unit/qmi/test_version.py` — clean
- `uv run pytest tests/unit/qmi/test_version.py -q` — **11 passed** (was 10 — the new jetpack test is +1)

**CI:** see VERIFICATION.md (pending push, run number TBD)

**Bench Jetson:** see VERIFICATION.md (pending build + install)

## Regression posture

The existing 1.30 and 1.32 fixtures both include a `qmicli X.Y.Z` line
*and* a `Compiled with libqmi-glib X.Y.Z` line. With the new regex,
`re.search` returns the first match (the `qmicli` line, which appears
earlier in the file). Since qmicli and libqmi-glib ship lockstep, the
matched version string is identical to what the old regex returned. Both
existing `test_detect_libqmi_version_parses_1_30` and `_parses_1_32` still
pass without modification.

The behavior change is strictly additive: stdout shapes that previously
raised `QmiVersionDetectionFailed("did not match libqmi-glib regex...")`
now parse correctly when their only version string is `qmicli X.Y.Z`.
