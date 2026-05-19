---
id: S09
parent: M001
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
# S09: Dms Revision Parser Hotfix

**# Plan 05.4-01 — SUMMARY**

## What Happened

# Plan 05.4-01 — SUMMARY

## What was done

Three changes in a single hotfix commit:

1. **`src/spark_modem/qmi/parsers/get_revision.py`** — replaced the
   substring constant `_RESPONSE_HEADER: Final[str] = "Device revisions
   retrieved"` with a regex `_RE_RESPONSE_HEADER: Final[re.Pattern[str]]
   = re.compile(r"Device revisions? retrieved")`. The early-return check
   in `parse_get_revision` now uses `_RE_RESPONSE_HEADER.search(body) is
   None`. The module docstring documents both the plural (Revision +
   Boot code) and singular (Revision only) header forms with a callout
   to the 2026-05-12 bench Jetson discovery.

2. **`tests/fixtures/qmicli/get_revision/1.30/jetpack-singular.txt`** —
   new fixture captured verbatim from the bench Jetson with a 4-line
   `#`-comment header naming source / modem / capture date /
   distinguishing trait, then the singular `Device revision retrieved:`
   header line, then the tab-indented Revision line.

3. **`tests/unit/qmi/parsers/test_get_revision.py`** — new test
   `test_parser_accepts_singular_revision_header_jetpack` between the
   1.30 and 1.32 happy-path tests. Loads the new fixture and asserts
   the result is `GetRevisionResult(revision="SWI9X50C_01.14.03.00
   b06bd3 jenkins 2020/09/23 10:53:35")`. The build-id + jenkins path
   are part of the expected string — `parse_get_revision` does not
   trim, it just captures the contents between the single quotes.

## Verification

**Local (dev host):**
- `uv run mypy --strict src/spark_modem/qmi/parsers/get_revision.py` — 0 issues
- `uv run ruff check ...` — clean
- `uv run pytest tests/unit/qmi/parsers/test_get_revision.py tests/unit/qmi/test_version.py -q`
  → **18 passed** in 1.25s (was 17 — +1 for the new jetpack-singular test)

**CI:** see VERIFICATION.md (pending push, run number TBD)

**Bench Jetson:** see VERIFICATION.md (pending build + install)

## Regression posture

The existing happy-path tests load fixtures with plural headers
(`get_revision/1.30/standard.txt`, `get_revision/1.32/standard.txt`).
Both still pass because the new regex `revisions?` still matches the
plural form. The MISSING_FIELD test hardcodes the plural form too and
also continues to pass.

The behavior change is strictly additive: stdout shapes that previously
returned `QmiError(UNEXPECTED_OUTPUT, detail='no revisions block in
stdout')` now parse correctly when the header is singular and only a
single `Revision:` line follows.
