---
phase: 05-bench-field-shadow
plan: 02
subsystem: qmi
tags: [qmi, zao-log, version-detection, fleet-triple, phase-5, pydantic, wire-type]

# Dependency graph
requires:
  - phase: 05-bench-field-shadow
    provides: Plan 05-01 dms_get_revision wrapper method + parse_get_revision parser + qmicli get_revision fixture tree (1.30 + 1.32) — directly imported here for compute_fleet_triple firmware probe
  - phase: 02-cycle-and-recovery
    provides: subproc.runner.run single-entrypoint pattern (SP-04 anchor) + CompletedProcess result dataclass shape
  - phase: 02-cycle-and-recovery
    provides: tests/unit/zao_log/ directory + Phase 2 Zao log parser conventions
provides:
  - detect_libqmi_version() async helper — parses qmicli --version stdout for libqmi-glib 3-part version; raises QmiVersionDetectionFailed on any failure path; routes through subproc.runner.run (SP-04)
  - QmiVersionDetectionFailed RuntimeError subclass — matches PreflightFailed shape (N818 noqa + plan-acceptance-fixed name)
  - detect_zao_sdk_version(path) helper — scans first 64 KiB of a Zao log for one of two banner shapes; returns 3-part version string or None; never raises (FileNotFoundError + OSError both downgrade to None with WARNING log)
  - FleetTriple pydantic BaseModel (frozen + extra=forbid) — byte-reproducible (em7421_firmware, zao_sdk, libqmi) wire shape; consumed by capture-fleet-fixture CLI (Plan 05-03) and preflight_check_known_fleet_triple (Plan 05-04)
  - compute_fleet_triple(wrapper, zao_log_path) async orchestrator — single seam composing the three probes; "unknown" sentinel for SDK absent; QmiError on dms_get_revision surfaces as QmiVersionDetectionFailed (preflight needs failure to surface)
affects:
  - 05-03 (capture-fleet-fixture CLI calls compute_fleet_triple to emit triple.json)
  - 05-04 (preflight_check_known_fleet_triple calls compute_fleet_triple and compares against /etc/spark-modem-watchdog/known-fleet/<sha>/triple.json)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Three-source version-detection seam: libqmi (subproc) + Zao SDK (banner regex) + EM7421 firmware (qmicli wrapper) composed into one FleetTriple pydantic shape — single source of truth for the (firmware, sdk, libqmi) triple across CLI and daemon"
    - "Duck-typed wrapper injection: compute_fleet_triple takes wrapper: object (production QmiWrapper or test FakeWrapper) — avoids import cycle with qmi/wrapper.py while keeping the orchestrator hardware-free testable"
    - "Zao SDK 'unknown' string sentinel — RESEARCH Q3 fallback policy materialised as the literal string 'unknown' in FleetTriple.zao_sdk; preflight (X-03) decides fail-closed semantics, capture (X-02) records for operator follow-up"
    - "64 KiB head-read cap on Zao log scanning (T-05-02-01 DoS mitigation) — pinned by test_banner_outside_head_window_returns_none which writes _HEAD_BYTES+100 bytes of padding before a banner"
    - "Two-candidate banner regex priority order (modern zao_remote_endpoint/X.Y.Z first, legacy zao-remote-endpoint X.Y.Z second) — first-match-wins ordering pinned by test_first_match_wins"

key-files:
  created:
    - src/spark_modem/qmi/version.py (~150 LOC: detect_libqmi_version + QmiVersionDetectionFailed + FleetTriple wire model + compute_fleet_triple orchestrator)
    - src/spark_modem/zao_log/version.py (~75 LOC: detect_zao_sdk_version + _ZAO_BANNER_PATTERNS + _HEAD_BYTES)
    - tests/unit/qmi/test_version.py (~255 LOC: 10 tests — 6 Task 1 detect_libqmi_version + 4 Task 3 FleetTriple/compute)
    - tests/unit/zao_log/test_version.py (~70 LOC: 6 tests — banner-present, no-banner, missing file, banner outside head window, legacy banner shape, first-match-wins)
    - tests/fixtures/qmicli/version/1.30/standard.txt (286 bytes; libqmi-glib 1.30.6 sample)
    - tests/fixtures/qmicli/version/1.32/standard.txt (286 bytes; libqmi-glib 1.32.0 sample)
    - tests/fixtures/zao_log/version/banner_present.txt (3-line synthetic Zao log with zao_remote_endpoint/2.1.0 banner + 2 RASCOW_STAT lines)
    - tests/fixtures/zao_log/version/no_banner.txt (3-line RASCOW_STAT-only log; banner-absent fallback path)
  modified: []

key-decisions:
  - "compute_fleet_triple takes wrapper: object (duck-typed) NOT a QmiWrapper Protocol — avoids the qmi/wrapper.py → qmi/errors.py → subproc/ import cycle that would emerge if version.py grew a Protocol seam alongside its existing qmi/errors.py + parsers/get_revision.py + subproc/ imports; the production QmiWrapper.dms_get_revision (Plan 05-01) already satisfies the structural requirement"
  - "_ZAO_SDK_UNKNOWN_SENTINEL is the literal string 'unknown' (not None, not Optional) on the FleetTriple wire — RESEARCH Q3 fallback policy materialised; preflight (X-03) decides fail-closed semantics, capture (X-02) records for operator follow-up; preserves byte-reproducibility for the X-03 lookup hash"
  - "FleetTriple uses frozen=True + extra='forbid' verbatim (not BaseWire from spark_modem/wire/_base.py) — version.py imports qmi/errors.py, parsers/get_revision.py, subproc/, AND zao_log/version.py already; adding wire/_base.py would deepen the chain unnecessarily and the model_config = ConfigDict(frozen=True, extra='forbid') inline is two lines; the W-02 wire discipline (frozen + forbid) is preserved by direct ConfigDict use"
  - "QmiError surfaces as QmiVersionDetectionFailed (raise, not return) on the firmware probe path — daemon preflight (X-03) needs the failure to surface; a silent fallback to 'unknown' for em7421_firmware would defeat the entire purpose of the known-fleet-triple gate"
  - "QmiVersionDetectionFailed subclasses RuntimeError (matches PreflightFailed shape per CONTEXT.md X-03 — N818 noqa for the public-name-fixed-by-plan-acceptance convention); does NOT subclass PreflightFailed itself (different module, different exit-code semantics; Plan 05-04 will compose them at the preflight call site)"
  - "Two Zao banner regex candidates (modern post-2.0 zao_remote_endpoint/X.Y.Z first, legacy zao-remote-endpoint X.Y.Z second) — locked priority order; first-match-wins ordering pinned by test_first_match_wins; deferred dpkg-query subprocess fallback (RESEARCH Q3 §295) to a future ADR if banner-absent becomes a fleet-wide observation"

patterns-established:
  - "Three-source version-detection seam: a single compute_fleet_triple async function orchestrates libqmi (subproc) + Zao SDK (banner regex over file head) + EM7421 firmware (qmicli wrapper via Plan 05-01) into one FleetTriple. This is the seam Plans 05-03 (capture CLI) and 05-04 (daemon preflight) both consume — version-string formatting cannot drift between CLI and daemon."
  - "tests/fixtures/qmicli/version/{1.30,1.32}/standard.txt fixture pair — mirrors the existing get_revision/{1.30,1.32}/standard.txt layout from Plan 05-01; the per-libqmi-version fixture tree convention is now uniform across qmicli intents."
  - "tests/fixtures/zao_log/version/ new sub-tree under tests/fixtures/zao_log/ — analogous to qmicli/version/; first per-intent split inside zao_log/ (sibling to all_lines_active.log etc. at the parent level)."

requirements-completed:
  - X-03

# Metrics
duration: 7min
completed: 2026-05-11
---

# Phase 5 Plan 02: Three-Source Version Detection (libqmi + Zao SDK + FleetTriple) Summary

**Built the (em7421_firmware, zao_sdk, libqmi) FleetTriple wire shape and three-probe orchestrator that Plans 05-03 (capture-fleet-fixture CLI) and 05-04 (preflight_check_known_fleet_triple) both consume — single seam for version-string formatting across CLI and daemon, with sentinel-based graceful fallback for SDK-absent and hard-fail for firmware-absent (preflight policy depends on it).**

## Performance

- **Duration:** ~7 min wall-clock (6 commits across 6m 49s of git activity)
- **Started:** 2026-05-11T08:27:37Z (record_start_time before Task 1 RED)
- **Completed:** 2026-05-11T08:34:46Z (Task 3 GREEN commit)
- **Tasks:** 3/3 complete (each as RED+GREEN pair = 6 task-level commits)
- **Files modified:** 8 (all new; 0 modified — Plan 05-01's wrapper changes already in tree)

## Accomplishments

- **`detect_libqmi_version()`** async helper at `src/spark_modem/qmi/version.py:45-71` parses libqmi-glib 3-part version from `qmicli --version` stdout; routes through `subproc.runner.run` (SP-04 invariant preserved); raises `QmiVersionDetectionFailed` on all three failure paths (missing binary / non-zero exit / unparseable stdout) with capped stderr/stdout excerpts (T-05-02-02 mitigation).
- **`detect_zao_sdk_version()`** pure-I/O helper at `src/spark_modem/zao_log/version.py:50-76` scans the first 64 KiB of a Zao log for one of two banner shapes (modern `zao_remote_endpoint/X.Y.Z` first, legacy `zao-remote-endpoint X.Y.Z` second); never raises; FileNotFoundError + OSError both downgrade to `None` with WARNING log. T-05-02-01 (DoS via huge log) mitigated by `_HEAD_BYTES = 64 * 1024` cap.
- **`FleetTriple`** pydantic BaseModel with `ConfigDict(frozen=True, extra="forbid")` — byte-reproducible wire shape that Plans 05-03 + 05-04 serialize/deserialize identically.
- **`compute_fleet_triple(wrapper, zao_log_path)`** async orchestrator composes all three probes; `"unknown"` literal sentinel for Zao SDK absent (caller decides fail-closed); QmiError on firmware probe raises (preflight needs failure to surface, never silent fallback for `em7421_firmware`).
- 16 new tests across 2 files (10 in `tests/unit/qmi/test_version.py`, 6 in `tests/unit/zao_log/test_version.py`), all green in 0.38s.
- Full repo regression: 2001 passed / 90 skipped in 20.88s (well under M7 ≤30s budget).
- ruff + `mypy --strict` clean on all changed source files; SP-04 invariant preserved (`grep -rn 'create_subprocess_exec\|subprocess.run' src/spark_modem/qmi/version.py src/spark_modem/zao_log/version.py` returns 0 matches).

## Task Commits

Each task followed the RED/GREEN cycle per the plan's `tdd="true"` annotation:

1. **Task 1 RED:** add failing tests for `detect_libqmi_version` — `dfcf06c` (test)
2. **Task 1 GREEN:** implement `detect_libqmi_version` + `QmiVersionDetectionFailed` — `8b3eaad` (feat)
3. **Task 2 RED:** add failing tests for `detect_zao_sdk_version` — `1aa83ce` (test)
4. **Task 2 GREEN:** implement `detect_zao_sdk_version` — `920b299` (feat)
5. **Task 3 RED:** add failing tests for `FleetTriple` + `compute_fleet_triple` — `a2dacca` (test)
6. **Task 3 GREEN:** implement `FleetTriple` + `compute_fleet_triple` — `bee44e3` (feat)

No REFACTOR commit was needed for any task — the GREEN code matched the analog shapes (PreflightFailed/preflight_check from `daemon/preflight.py`; pydantic frozen+forbid from `wire/_base.py`) verbatim.

## Files Created/Modified

### Created (8)

- **`src/spark_modem/qmi/version.py`** (151 LOC) — `detect_libqmi_version` + `QmiVersionDetectionFailed` + `FleetTriple` (frozen + extra=forbid) + `compute_fleet_triple` orchestrator + `_ZAO_SDK_UNKNOWN_SENTINEL = "unknown"`. Module docstring documents the X-02 (capture) + X-03 (preflight) callers.
- **`src/spark_modem/zao_log/version.py`** (75 LOC) — `detect_zao_sdk_version` + `_ZAO_BANNER_PATTERNS` (two candidates) + `_HEAD_BYTES = 64 * 1024`. Module docstring documents the deferred dpkg-query subprocess fallback (RESEARCH Q3 §295) and the "unknown" sentinel policy.
- **`tests/unit/qmi/test_version.py`** (~255 LOC, 10 tests) — Task 1 (6 tests: happy 1.30 + happy 1.32 + non-zero exit + unparseable stdout + FileNotFoundError + RuntimeError subclass + argv-shape pin) + Task 3 (4 tests: frozen+extra-forbid contract + happy path + "unknown" sentinel + QmiError on firmware raises). `_FakeWrapper` minimal duck-typed stand-in for `QmiWrapper.dms_get_revision`.
- **`tests/unit/zao_log/test_version.py`** (~70 LOC, 6 tests) — banner-present / no-banner / missing-file / banner-outside-head-window (T-05-02-01 DoS cap pin) / legacy banner shape / first-match-wins.
- **`tests/fixtures/qmicli/version/1.30/standard.txt`** (286 bytes, 9 lines) — synthetic qmicli --version stdout with `qmicli 1.30.6` first line and `Compiled with libqmi-glib 1.30.6` last line (regex matches the latter).
- **`tests/fixtures/qmicli/version/1.32/standard.txt`** (286 bytes, 9 lines) — same shape, 1.32.0 version.
- **`tests/fixtures/zao_log/version/banner_present.txt`** (3 lines) — synthetic Zao log with `zao_remote_endpoint/2.1.0` banner.
- **`tests/fixtures/zao_log/version/no_banner.txt`** (3 lines) — RASCOW_STAT-only synthetic log; banner-absent fallback path.

### Modified (0)

None. Plan 05-01's `qmi/wrapper.py` addition (`dms_get_revision`) is already in tree; this plan only consumes it.

## Decisions Made

- **`compute_fleet_triple` takes `wrapper: object` (duck-typed)** rather than introducing a `QmiWrapperProto` Protocol. Three reasons: (1) `version.py` already imports from `qmi/errors.py`, `qmi/parsers/get_revision.py`, `subproc/runner.py`, and `zao_log/version.py` — a Protocol would deepen the dependency chain unnecessarily; (2) the only method needed from the wrapper is `dms_get_revision`, which is structurally identical between production `QmiWrapper` (Plan 05-01) and the test `_FakeWrapper`; (3) the in-source `# type: ignore[attr-defined]` localises the structural-typing concession to a single line.

- **"unknown" string sentinel for `FleetTriple.zao_sdk`** (not `None`, not `Optional[str]`, not an enum). Rationale: `FleetTriple` is a wire shape that ships via `triple.json` files baked into the `.deb` (X-03); a `None` value would round-trip as JSON `null` and complicate the known-fleet-triple lookup hash. The literal string `"unknown"` is byte-reproducible and self-documenting in `triple.json` output. Preflight (Plan 05-04) decides fail-closed semantics on the sentinel; capture (Plan 05-03) records it for operator follow-up.

- **`FleetTriple` uses inline `ConfigDict(frozen=True, extra="forbid")` instead of inheriting `BaseWire`** from `src/spark_modem/wire/_base.py`. The two-line `model_config` declaration is cheaper than adding another import to `version.py` (already 5 imports deep); the W-02 wire discipline (frozen + extra=forbid) is preserved verbatim.

- **`QmiError` on firmware probe raises `QmiVersionDetectionFailed`** (does NOT fall back to a sentinel). The daemon preflight (X-03) needs the failure to surface — a silent "unknown" for `em7421_firmware` would defeat the entire purpose of the known-fleet-triple gate. The decision applies only to the firmware probe path; the Zao SDK probe IS allowed to fall back to "unknown" because the SDK has no universal detection mechanism (RESEARCH Q3 §288-298).

- **`QmiVersionDetectionFailed` subclasses `RuntimeError`** (matches `PreflightFailed` shape per CONTEXT.md X-03 — `N818` noqa for the public-name-fixed-by-plan-acceptance convention). It does NOT subclass `PreflightFailed` itself: different module, different exit-code semantics; Plan 05-04 will compose them at the preflight call site.

- **Two Zao banner regex candidates scanned in priority order** (modern `zao_remote_endpoint/X.Y.Z` first, legacy `zao-remote-endpoint X.Y.Z` second). First-match-wins ordering is pinned by `test_first_match_wins`. The dpkg-query subprocess fallback (RESEARCH Q3 §295) is NOT implemented in this plan — deferred to a future ADR if banner-absent becomes a fleet-wide observation.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] CompletedProcess field is `duration_monotonic`, not `duration_s`**

- **Found during:** Task 1 RED (writing the test stub `_make_cp` helper)
- **Issue:** The plan's test code at Task 1 Step D snippet used `CompletedProcess(argv=tuple(argv), ..., duration_s=0.0)`. The actual `src/spark_modem/subproc/result.py:14-31` dataclass has field `duration_monotonic: float` — using `duration_s` would have failed with `TypeError: CompletedProcess.__init__() got an unexpected keyword argument 'duration_s'` at test collection time.
- **Fix:** Built `CompletedProcess` instances via the `.make()` classmethod (the standard idiom across `tests/unit/qmi/test_wrapper.py`) with `duration_monotonic=0.0`. Factored into a `_make_cp(*, argv, exit_code, stdout, stderr=b"")` test helper for terseness.
- **Files modified:** `tests/unit/qmi/test_version.py` (helper + 8 usages)
- **Verification:** RED phase confirmed `ModuleNotFoundError` (not `TypeError`); GREEN phase confirmed 6/6 then 10/10 tests pass.
- **Committed in:** `dfcf06c` (Task 1 RED) — applied at test-authoring time before any GREEN code, so no commit-history scar.

**2. [Rule 3 — Blocking] `pytest-asyncio mode=auto` removes the need for `@pytest.mark.asyncio` decorators**

- **Found during:** Task 1 RED (writing the first async test)
- **Issue:** The plan's Step D test snippet decorated every async test with `@pytest.mark.asyncio`. `pyproject.toml [tool.pytest.ini_options]` already sets `asyncio_mode = "auto"`, and the existing `tests/unit/daemon/test_preflight.py` (the plan's named analog) uses plain `async def` without the decorator. Adding the decorator with `strict-markers` enabled would not have errored, but would have left a redundant directive that future maintainers would either propagate or strip.
- **Fix:** Dropped the `@pytest.mark.asyncio` decorator on every async test, matching `test_preflight.py`. `pytestmark = pytest.mark.asyncio` was also not needed.
- **Files modified:** `tests/unit/qmi/test_version.py` (10 tests), `tests/unit/zao_log/test_version.py` (6 tests — only one of these is async-free; this fix applies to none in zao_log/test_version.py since all are sync, but the same scrutiny was applied).
- **Verification:** Pytest collection succeeds; all tests pass.
- **Committed in:** `dfcf06c` + `1aa83ce` (applied at test-authoring time)

**3. [Rule 1 — Bug] PLC0415 in-function imports flagged by ruff after Task 3 GREEN**

- **Found during:** Task 3 GREEN (post-implementation lint sweep)
- **Issue:** During Task 3 RED authoring, I deliberately placed `from spark_modem.qmi.version import FleetTriple` (and `compute_fleet_triple`) inside the four new test functions to make the RED-phase test failure crisp (`ImportError` at the call site, not at module collection). Once GREEN landed, the in-function imports tripped ruff `PLC0415` (5 errors).
- **Fix:** Hoisted the imports to the module top alongside `QmiVersionDetectionFailed` + `detect_libqmi_version`; module now imports `FleetTriple` + `compute_fleet_triple` + `QmiVersionDetectionFailed` + `detect_libqmi_version` together. Also hoisted the `ValidationError` import from `pydantic`.
- **Files modified:** `tests/unit/qmi/test_version.py`
- **Verification:** `ruff check src/spark_modem/qmi/version.py src/spark_modem/zao_log/version.py tests/unit/qmi/test_version.py tests/unit/zao_log/test_version.py` exits 0; 10/10 tests still pass.
- **Committed in:** `bee44e3` (Task 3 GREEN, alongside the implementation)

**4. [Rule 1 — Bug] E501 line-too-long on `_make_cp` signature**

- **Found during:** Task 1 GREEN (post-implementation lint sweep)
- **Issue:** The 105-character `_make_cp(*, argv, exit_code, stdout, stderr=b"") -> CompletedProcess:` signature exceeded the project's `line-length = 100` (`pyproject.toml [tool.ruff]`).
- **Fix:** Reformatted the signature across multiple lines (each parameter on its own line).
- **Files modified:** `tests/unit/qmi/test_version.py`
- **Verification:** `ruff check tests/unit/qmi/test_version.py` exits 0.
- **Committed in:** `8b3eaad` (Task 1 GREEN, alongside the implementation)

---

**Total deviations:** 4 auto-fixed (2 blocking, 2 bugs — all caught at test-authoring or post-GREEN lint time before any commit landed broken)

**Impact on plan:** All deviations are mechanical fixes against literal-plan-text-vs-real-code drift (CompletedProcess field name; decorator-vs-auto mode) or lint compliance (PLC0415; E501). No scope creep; no architectural decisions needed; Rule 4 did not fire. The 05-05 executor's caveat about plan-text symbol assumptions ("event-shape `who`/`line` vs flat `usb_path`; `_DECAY_K_DEFAULT` missing from `policy/engine.py`") is the analog: plan text describes the contract, real code defines it; when they disagree the real code wins.

## Issues Encountered

- **System reminder noise on Edit-after-Write:** the `PreToolUse:Edit hook` flagged each Edit on `version.py` and `test_version.py` even after I had just Read or Written them in the same session. This is environmental friction, not a correctness issue — every Edit succeeded; I Re-Read each file to satisfy the hook and continued. Captured here so the orchestrator agent does not retry on this signal.
- **No active git pre-commit hook on this Windows dev host:** `.git/hooks/pre-commit` is absent, so ruff/mypy/SP-04 lint did not run automatically. I ran them manually after each task GREEN. Production builds catch the same gates in CI; the gap is dev-host-only.

## TDD Gate Compliance

All three tasks are `type="auto" tdd="true"`. Plan-level type is `execute` (not `tdd`), so plan-level RED→GREEN→REFACTOR gates do not apply, but each task followed the RED → GREEN cycle:

| Task | RED commit | GREEN commit | REFACTOR |
| ---- | ---------- | ------------ | -------- |
| 1    | `dfcf06c` (test)  | `8b3eaad` (feat) | not needed |
| 2    | `1aa83ce` (test)  | `920b299` (feat) | not needed |
| 3    | `a2dacca` (test)  | `bee44e3` (feat) | not needed |

Each RED commit was verified to fail before the GREEN commit was authored:

- Task 1 RED: `ModuleNotFoundError: No module named 'spark_modem.qmi.version'`
- Task 2 RED: `ModuleNotFoundError: No module named 'spark_modem.zao_log.version'`
- Task 3 RED: `ImportError: cannot import name 'FleetTriple' from 'spark_modem.qmi.version'` (6 Task-1 tests still pass; only the 4 new Task-3 tests fail — clean intra-file RED)

## Verification Summary

| Check | Status |
| ----- | ------ |
| `pytest tests/unit/qmi/test_version.py tests/unit/zao_log/test_version.py -q` | 16 passed in 0.38s |
| `pytest tests/unit/zao_log/test_version.py tests/unit/qmi/test_version.py tests/unit/qmi/parsers/test_get_revision.py tests/unit/qmi/test_wrapper_dms_get_revision.py -q` (Plans 01+02 unit subset) | 24 passed in 0.43s |
| `pytest -q` (full repo suite) | 2001 passed, 90 skipped in 20.88s (M7 30s budget) |
| `ruff check src/spark_modem/qmi/version.py src/spark_modem/zao_log/version.py tests/unit/qmi/test_version.py tests/unit/zao_log/test_version.py` | All checks passed |
| `mypy --strict src/spark_modem/qmi/version.py src/spark_modem/zao_log/version.py` | Success: no issues found in 2 source files |
| `grep -rn 'create_subprocess_exec\|subprocess.run' src/spark_modem/qmi/version.py src/spark_modem/zao_log/version.py` (SP-04 invariant) | 0 matches (exit=1, grep convention) |
| `grep -c "class FleetTriple" src/spark_modem/qmi/version.py` | 1 |
| `grep -c "async def compute_fleet_triple" src/spark_modem/qmi/version.py` | 1 |
| `grep -c '"unknown"' src/spark_modem/qmi/version.py` | 1 (the sentinel string in `_ZAO_SDK_UNKNOWN_SENTINEL`) |
| `grep -c "async def detect_libqmi_version" src/spark_modem/qmi/version.py` | 1 |
| `grep -c "def detect_zao_sdk_version" src/spark_modem/zao_log/version.py` | 1 |

## Threat Surface Scan

No new threat surface introduced beyond the plan's `<threat_model>` dispositions:

- **T-05-02-01 (DoS via huge Zao log file):** mitigated by 64 KiB head-read cap (`_HEAD_BYTES`); pinned by `test_banner_outside_head_window_returns_none` which writes `_HEAD_BYTES + 100` bytes of padding before a banner and asserts `None` is returned.
- **T-05-02-02 (Tampering / malformed qmicli stdout):** mitigated by `QmiVersionDetectionFailed` raised on non-zero exit AND unparseable stdout, with capped stderr/stdout excerpts (512 B each — bounded memory). Verified by `test_non_zero_exit_raises` + `test_unparseable_stdout_raises`.
- **T-05-02-03 (Spoofing fake Zao log banner):** accepted; threat model is local-only.
- **T-05-02-04 (Information disclosure — FleetTriple shipped via .deb):** accepted; version strings are not PII.
- **T-05-02-05 (Subprocess injection in `detect_libqmi_version`):** mitigated by hardcoded argv list `["qmicli", "--version"]` (no external string interpolation); SP-04 + list-form argv invariant preserved. Verified by `test_detect_libqmi_version_parses_1_30` asserting `seen_argv == [["qmicli", "--version"]]`.

No new endpoints, auth paths, or trust boundaries created. No `threat_flag` entries needed.

## Known Stubs

None. The `"unknown"` sentinel string in `FleetTriple.zao_sdk` is intentional — Plan 05-04 (preflight_check_known_fleet_triple) decides fail-closed semantics on it, Plan 05-03 (capture-fleet-fixture CLI) records it in `triple.json` for operator follow-up. Documented in module docstring + `key-decisions` above.

## Next Phase Readiness

- **05-03 (capture-fleet-fixture CLI)** can now `from spark_modem.qmi.version import compute_fleet_triple, FleetTriple` and write `FleetTriple.model_dump_json()` to `triple.json`. No further version-detection code needed in 05-03 — it is purely a CLI orchestration plus PII redaction.
- **05-04 (preflight_check_known_fleet_triple)** can now `from spark_modem.qmi.version import compute_fleet_triple, FleetTriple, QmiVersionDetectionFailed` and compare the local triple against `/etc/spark-modem-watchdog/known-fleet/<sha>/triple.json` files. Fail-closed semantics on `zao_sdk == "unknown"` is the X-03 decision Plan 05-04 will make.
- **No blockers.** The `_FakeWrapper` shape established here can be reused by Plans 05-03 + 05-04 for their own hardware-free unit tests (compose with `tests/fakes/runner.FakeRunner` for the libqmi probe stub).

## Self-Check

Verifying SUMMARY claims against actual repo state.

**Files created — all present:**

- `S:/spark/modem-watchdog/src/spark_modem/qmi/version.py` — FOUND
- `S:/spark/modem-watchdog/src/spark_modem/zao_log/version.py` — FOUND
- `S:/spark/modem-watchdog/tests/unit/qmi/test_version.py` — FOUND
- `S:/spark/modem-watchdog/tests/unit/zao_log/test_version.py` — FOUND
- `S:/spark/modem-watchdog/tests/fixtures/qmicli/version/1.30/standard.txt` — FOUND
- `S:/spark/modem-watchdog/tests/fixtures/qmicli/version/1.32/standard.txt` — FOUND
- `S:/spark/modem-watchdog/tests/fixtures/zao_log/version/banner_present.txt` — FOUND
- `S:/spark/modem-watchdog/tests/fixtures/zao_log/version/no_banner.txt` — FOUND

**Commits cited — all present in git log:**

- `dfcf06c` — FOUND (test: RED for Task 1)
- `8b3eaad` — FOUND (feat: GREEN for Task 1)
- `1aa83ce` — FOUND (test: RED for Task 2)
- `920b299` — FOUND (feat: GREEN for Task 2)
- `a2dacca` — FOUND (test: RED for Task 3)
- `bee44e3` — FOUND (feat: GREEN for Task 3)

## Self-Check: PASSED

---
*Phase: 05-bench-field-shadow*
*Completed: 2026-05-11*
