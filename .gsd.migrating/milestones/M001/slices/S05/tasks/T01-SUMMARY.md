---
id: T01
parent: S05
milestone: M001
provides:
  - QmiWrapper.dms_get_revision() async method (read-only, --device-open-proxy, _DEFAULT_TIMEOUT_S=8s, routes through subproc.runner)
  - parsers.get_revision module exporting GetRevisionResult (frozen pydantic model, extra='ignore') and parse_get_revision(stdout) function
  - tests/fixtures/qmicli/get_revision/{1.30,1.32}/standard.txt — per-libqmi-version sample fixtures
  - Locked fixture-tree set assertion (1.30 + 1.32) preventing accidental version deletion
requires: []
affects: []
key_files: []
key_decisions: []
patterns_established: []
observability_surfaces: []
drill_down_paths: []
duration: ~5min
verification_result: passed
completed_at: 2026-05-11
blocker_discovered: false
---
# T01: Plan 01

**# Phase 5 Plan 01: Add `dms_get_revision` QMI verb Summary**

## What Happened

# Phase 5 Plan 01: Add `dms_get_revision` QMI verb Summary

**Added the single qmicli verb Phase 5 needs for fleet-triple capture (EM7421 firmware string) — wrapper method, case-preserving parser, per-libqmi-version fixture tree (1.30 + 1.32), 8 unit tests covering happy/error/cross-version paths.**

## Performance

- **Duration:** ~5 min wall-clock (4 commits across 4m 28s of git activity)
- **Started:** 2026-05-11T11:00:05+03:00 (first task commit)
- **Completed:** 2026-05-11T11:04:33+03:00 (last task commit)
- **Tasks:** 2/2 complete (each as RED+GREEN pair = 4 task-level commits)
- **Files modified:** 6 (1 modified, 5 created)

## Accomplishments

- New `QmiWrapper.dms_get_revision()` async method inserted as the 8th read-only verb at `src/spark_modem/qmi/wrapper.py:236-255`, between `dms_get_operating_mode` (ends 234) and the state-changing-methods block (now 256). Read-only contract verified: does NOT set `_in_critical_section`.
- New `src/spark_modem/qmi/parsers/get_revision.py` (56 LOC): `GetRevisionResult` pydantic model (`extra="ignore"`, `frozen=True`) + `parse_get_revision(stdout)` returning `GetRevisionResult` on success or `QmiError(UNEXPECTED_OUTPUT | MISSING_FIELD)` on degenerate inputs. Firmware string is preserved verbatim (NOT lowercased — deliberate deviation from `parse_get_operating_mode`).
- Per-libqmi-version fixture pair at `tests/fixtures/qmicli/get_revision/{1.30,1.32}/standard.txt`, byte-shape identical to the existing `get_operating_mode/1.30/online.txt` (TABs, trailing newline, version-header line). 136 bytes each.
- 8 new tests across 2 files (4 parser core + 2 parser cross-version + 2 wrapper), all green in 0.41s.
- Full repo regression check: `tests/unit/qmi/` 84/84 green; full suite 1973 passed, 90 skipped in 26.25s (within M7 ≤30s budget).
- ruff and `mypy --strict` clean on all changed source files; SP-04 invariant preserved (`grep -r 'create_subprocess_exec' src/spark_modem/ | grep -v subproc/` returns 0 matches).

## Task Commits

Each task was committed atomically as a TDD RED/GREEN pair (per the plan's `tdd="true"` annotation on both tasks):

1. **Task 1 RED: add failing tests for dms_get_revision wrapper + parser** — `1977b67` (test)
2. **Task 1 GREEN: implement dms_get_revision wrapper + parser + libqmi 1.30 fixture** — `03f8f5a` (feat)
3. **Task 2 RED: add failing cross-version drift tests for get_revision parser** — `2d19a61` (test)
4. **Task 2 GREEN: add libqmi 1.32 fixture for get_revision parser** — `419bb53` (feat)

No REFACTOR commit was needed for either task — the GREEN code matched the analog's shape verbatim with the single deliberate deviation (case preservation) documented in-source.

## Files Created/Modified

- `src/spark_modem/qmi/wrapper.py` — added `async def dms_get_revision()` at line 236, immediately after `dms_get_operating_mode` and before the `# ---- state-changing methods` comment (now at line 256). 9-line method body + 6-line docstring.
- `src/spark_modem/qmi/parsers/get_revision.py` — new parser module (56 LOC). Imports mirror `get_operating_mode.py`; only structural differences are `_RESPONSE_HEADER = "Device revisions retrieved"`, `_RE_REVISION = re.compile(r"Revision:\s*'([^']+)'")`, `GetRevisionResult` class name, `revision: str | None = None` field, MISSING_FIELD `field="revision"`, and the in-source comment explaining why the firmware string is NOT lowercased.
- `tests/fixtures/qmicli/get_revision/1.30/standard.txt` — 4-line fixture (libqmi_version banner + response header + Revision/Boot-code lines). 136 bytes.
- `tests/fixtures/qmicli/get_revision/1.32/standard.txt` — byte-identical to 1.30 modulo the version-header banner; locks Phase 5's per-libqmi-version drift contract.
- `tests/unit/qmi/parsers/__init__.py` — empty file, establishes the new test sub-package.
- `tests/unit/qmi/parsers/test_get_revision.py` — 6 tests: happy-path 1.30, UNEXPECTED_OUTPUT, MISSING_FIELD(field='revision'), frozen+extra-ignore behaviour, happy-path 1.32, locked fixture-tree set.
- `tests/unit/qmi/test_wrapper_dms_get_revision.py` — 2 tests: argv shape (--device-open-proxy, --device=<dev>, --dms-get-revision) and read-only `_in_critical_section` contract.

## Decisions Made

- **Read-only verb, no `_in_critical_section` wrapping.** `dms_get_revision` is purely informational (firmware string read); follows the same pattern as `dms_get_operating_mode` / `nas_get_signal_info` / etc. State-changing methods are only the four 4 already in place (`dms_set_operating_mode`, `uim_sim_power_on`, `wds_modify_profile`, `wds_set_ip_family`) + Phase 4's destructive 1 = 5 occurrences of `_in_critical_section = True`. New method preserves that count.
- **Firmware string is NOT lowercased.** `SWI9X30C_02.38.00.00` is a case-sensitive identifier — the parser preserves it verbatim. Deliberate deviation from `parse_get_operating_mode` which lowercases `Mode: 'online'` → `"online"`. Reason called out in an inline comment in `parsers/get_revision.py` so future readers don't "fix" it.
- **Per-libqmi-version fixture pair landed atomically with the parser** rather than only 1.30 in Task 1 + 1.32 deferred. Both versions ship now because Plan 05-04's `preflight_check_known_fleet_triple` will need to test against the cross-version drift contract from day one (closes RESEARCH Q3).
- **Locked-set assertion on fixture tree.** `test_fixture_tree_has_locked_set_of_libqmi_versions` pins `{1.30, 1.32}` so deletion of either is a test failure. Adding a future 1.34 fixture is a deliberate extension (one-line edit to the assertion).

## Deviations from Plan

None — plan executed exactly as written. The only intra-plan deviation worth noting is the deliberate `revision NOT lowercased` decision, which was explicitly called out in the plan's Task-1 action block (Step A note: "revision is NOT lowercased (firmware strings preserve case; see action note)"), so it is plan-conformant rather than a Rule-1/2/3 auto-fix.

No auto-fixes were applied; no authentication gates encountered; no architectural decisions needed (Rule 4 did not fire).

## TDD Gate Compliance

Both tasks are `type="auto" tdd="true"`. The plan-level type is `execute` (not `tdd`), so the plan-level RED/GREEN/REFACTOR gate does not apply, but each individual task followed the RED → GREEN cycle:

| Task | RED commit | GREEN commit | REFACTOR |
| ---- | ---------- | ------------ | -------- |
| 1    | `1977b67` (test)  | `03f8f5a` (feat) | not needed |
| 2    | `2d19a61` (test)  | `419bb53` (feat) | not needed |

Each RED commit was verified to fail (`ModuleNotFoundError` / `AttributeError` / `FileNotFoundError` / locked-set assertion mismatch) before the GREEN commit was written.

## Verification Summary

| Check | Status |
| ----- | ------ |
| `pytest tests/unit/qmi/parsers/test_get_revision.py tests/unit/qmi/test_wrapper_dms_get_revision.py -q` | 8 passed in 0.41s |
| `pytest tests/unit/qmi/ -q` (full qmi subset) | 84 passed in 0.75s |
| `pytest -q` (full repo suite) | 1973 passed, 90 skipped in 26.25s (under M7 30s budget) |
| `ruff check src/spark_modem/qmi/` | All checks passed |
| `mypy --strict src/spark_modem/qmi/parsers/get_revision.py src/spark_modem/qmi/wrapper.py` | Success: no issues found in 2 source files |
| `grep -rn 'create_subprocess_exec' src/spark_modem/ \| grep -v subproc/` (SP-04 invariant) | 0 matches |
| `grep -c "_in_critical_section = True" src/spark_modem/qmi/wrapper.py` (read-only contract) | 5 (unchanged from pre-edit) |
| `ls tests/fixtures/qmicli/get_revision/ \| sort \| tr '\n' ' '` | `1.30 1.32 ` |

## Threat Surface Scan

No new threat surface introduced beyond what the plan's `<threat_model>` already disposes:

- T-05-01-01 (Tampering of parser against malformed stdout) — mitigated by returning `QmiError(UNEXPECTED_OUTPUT)`; verified by `test_parser_no_header_returns_unexpected_output`. `ConfigDict(extra='ignore', frozen=True)` blocks injection via extra fields; verified by `test_result_is_frozen_and_ignores_extra_fields`.
- T-05-01-02 (Firmware string leak) — accepted; firmware version is not PII; intentionally captured for fleet fixtures.
- T-05-01-03 (DoS via pathological regex backtracking) — mitigated by `[^']+` negated character class in `_RE_REVISION`; `subproc.runner` enforces stdout size cap upstream.

No new endpoints, auth paths, or trust boundaries were created. No `threat_flag` entries needed.

## Self-Check

Verifying SUMMARY claims against actual repo state.

**Files created — all present:**
- `S:/spark/modem-watchdog/src/spark_modem/qmi/parsers/get_revision.py` — FOUND
- `S:/spark/modem-watchdog/tests/fixtures/qmicli/get_revision/1.30/standard.txt` — FOUND
- `S:/spark/modem-watchdog/tests/fixtures/qmicli/get_revision/1.32/standard.txt` — FOUND
- `S:/spark/modem-watchdog/tests/unit/qmi/parsers/__init__.py` — FOUND
- `S:/spark/modem-watchdog/tests/unit/qmi/parsers/test_get_revision.py` — FOUND
- `S:/spark/modem-watchdog/tests/unit/qmi/test_wrapper_dms_get_revision.py` — FOUND

**Commits cited — all present in git log:**
- `1977b67` — FOUND (test: RED for Task 1)
- `03f8f5a` — FOUND (feat: GREEN for Task 1)
- `2d19a61` — FOUND (test: RED for Task 2)
- `419bb53` — FOUND (feat: GREEN for Task 2)

## Self-Check: PASSED
