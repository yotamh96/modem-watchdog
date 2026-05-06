---
phase: 02-core-daemon-laptop-testable
plan: 04
subsystem: observer
tags: [inventory, observer, taskgroup, asyncio-timeout, fr-2, fr-10, fr-13, fr-70, fr-71, nfr-4, nfr-10, nfr-11, adr-0003, adr-0009, sysfs, sierra-em7421]

# Dependency graph
requires:
  - phase: 01-foundations-adrs
    provides: BaseWire (frozen, extra='forbid'); Diag/ModemSnapshot/SignalSnapshot/Issue/WhoModem wire types; IssueCategory/IssueDetail/RegistrationState enums
  - phase: 02-01-test-fakes-and-fixture-roots
    provides: FakeRunner (argv->CompletedProcess), FakeClock, FixtureZaoTailer, FixtureInventory shape
  - phase: 02-02-qmi-wrapper
    provides: QmiWrapper (always --device-open-proxy), QmiError, classify(), 7 cheap query methods, 7 parser modules with extra='ignore'
  - phase: 02-03-zao-log-parser
    provides: ZaoLogTailer @runtime_checkable Protocol, ZaoSnapshot.is_line_active(), ZaoSnapshot.unknown(reason=)
provides:
  - InventorySource @runtime_checkable Protocol (single observer-facing seam; Phase 3 swaps SysfsInventory -> UdevInventory transparently)
  - ModemDescriptor BaseWire (line/cdc_wdm/usb_path/ns/iface) -- production type; FixtureInventory now imports it directly (Plan 02-01 promotion delivered)
  - SysfsInventory walking /sys/bus/usb/devices/ for VID:PID 1199:9091 with sysfs_root_override for tests
  - observer.orchestrator.observe_all: TaskGroup-based parallel probe with per-task asyncio.timeout(8s) (FR-70/NFR-4) and per-task try/except (NFR-11)
  - observer.issue_extractor.probe_modem_to_snapshot (I/O wrapper: 7 sequential qmicli queries per modem) + extract_issues (pure RECOVERY_SPEC §4 mapper)
  - observer.diag_builder.build_diag (FR-13: ModemSnapshot[] + ZaoSnapshot + cycle_id -> Diag)
  - 21 new tests: 7 inventory (4 cross-platform + 3 Linux-only sysfs tree) + 14 observer (5 orchestrator, 7 issue_extractor incl. WhoModem self-test, 2 diag_builder)
  - Plan-04 self-test: test_extract_issues_who_uses_modem_usb_path_and_cdc_wdm catches the placeholder-WhoModem bug PLAN flagged (proven correct)
affects: [02-06-actions, 02-08-webhook, 02-09-cli, 02-10-cycle-driver, phase-3-event-sources]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "InventorySource Protocol seam: Phase 2 SysfsInventory + Phase 3 UdevInventory satisfy the same surface (`async def scan() -> list[ModemDescriptor]`); observer/ never changes when Phase 3 lands event-driven discovery (CONTEXT M-01)."
    - "TaskGroup + per-task asyncio.timeout(8s) -- canonical shape from RESEARCH §2.3: TaskGroup parallelises the four probes; each probe wraps its inner work in `async with asyncio.timeout(timeout_s)` AND catches TimeoutError + Exception INSIDE the task so the group never sees an exception escape (NFR-11)."
    - "Zao-active gate runs BEFORE qmicli: `if zao.is_line_active(modem.line)` returns a zero-issue zao_active snapshot; FR-10 / ADR-0003 enforced at the cheapest possible point in the cycle."
    - "Within-modem queries are sequential (qmicli holds a per-device lock per ARCH §4.3); only ACROSS-modem parallelism is exploited."
    - "extract_issues is pure (no I/O, no clock) and decoupled from probe_modem_to_snapshot which owns all qmicli I/O -- preserves the testability of the §4 decision-table mapping."
    - "RECOVERY_SPEC §4 split between observer and policy: observer detects per-modem facts only (APN_EMPTY/RAW_IP_OFF/registration/SIM/operating-mode); policy/ in plan 02-05 handles cross-source detections (apn_mismatch needs carrier table; qmi_channel_hung needs fleet-wide aggregation)."
    - "Slow-probe / boom-probe runner test pattern: subclass FakeRunner, override `run` to async-sleep / raise for a target device argv; confirms per-task isolation without touching real subprocess machinery."

key-files:
  created:
    - src/spark_modem/inventory/__init__.py
    - src/spark_modem/inventory/descriptor.py
    - src/spark_modem/inventory/protocol.py
    - src/spark_modem/inventory/sysfs.py
    - src/spark_modem/observer/__init__.py
    - src/spark_modem/observer/orchestrator.py
    - src/spark_modem/observer/issue_extractor.py
    - src/spark_modem/observer/diag_builder.py
    - tests/unit/inventory/__init__.py
    - tests/unit/inventory/test_sysfs.py
    - tests/unit/observer/__init__.py
    - tests/unit/observer/test_orchestrator.py
    - tests/unit/observer/test_diag_builder.py
    - tests/fixtures/inventory/four_modems_one_zao_active.json
    - tests/fixtures/inventory/two_modems.json
    - tests/fixtures/sysfs/four_modems/sys/bus/usb/devices/.gitkeep
  modified:
    - tests/fakes/inventory.py  # _FixtureModemDescriptor removed; imports production ModemDescriptor

key-decisions:
  - "Per-parser type-safe `_safe_parse_*` helpers (one per parser) instead of one generic helper. mypy --strict cannot infer the discriminated success type from a single function because each parser returns a different concrete type; duplicating the 4-line wrapper is cheaper than carrying a TypeVar zoo."
  - "Slow/boom probe tests subclass FakeRunner instead of monkey-patching: subclass overrides keep the FakeRunner.run signature intact for mypy --strict and document the per-test divergence inline."
  - "_line_from_usb_path uses the trailing dotted component with a 1..99 inclusive band -- production maps 2-3.1.{1..4} -> line {1..4} cleanly. Out-of-range or non-numeric tails degenerate to 1 so the ModemDescriptor's ge=1 constraint never fails on a real Sierra device whose path doesn't fit the 4-modem hub assumption."
  - "Zao-active short-circuit returns a fresh ModemSnapshot built only from descriptor fields (usb_path/cdc_wdm) with usb_speed/operating_mode/sim_state/registration explicitly None and issues=[]. No risk of leaking stale data; FR-10 honored even if Zao is wrong about the line."
  - "_timed_out_snapshot and _errored_snapshot are intentionally identical in behaviour for Phase 2 -- both produce an empty ModemSnapshot with no issues. The functions stay separate so Phase 3 can differentiate (e.g. tip the timed-out path to drive a watchdog metric without surface-changing the errored path)."
  - "extract_issues uses `del signal` -- the SignalSnapshot is recorded on the wire but signal-quality gating happens in policy/gates.py (ADR-0014 referenced via CLAUDE.md invariant 1: observer surfaces facts; policy gates them). signal_dbm metrics are emitted from the snapshot, not from extract_issues."

patterns-established:
  - "Per-task try/except in TaskGroup probes: any future fan-out work in observer/ MUST catch its own exceptions inside the task; bare TaskGroup over the whole observer is a CLAUDE.md anti-pattern (cancels siblings on first failure)."
  - "Sysfs walker constructor override: SysfsInventory takes `*, sysfs_root_override: Path | None = None` (mirrors StateStore). Tests build a tmp_path sysfs tree and never touch /sys."
  - "Issue + WhoModem construction at top of pure mappers: `who = WhoModem(usb_path=modem.usb_path, cdc_wdm=modem.cdc_wdm)` is built once and reused for every issue in the function -- avoids the placeholder-WhoModem bug class that the PLAN's self-test catches."

requirements-completed:
  - FR-2  # Resolve each modem to (line, cdc_wdm, usb_path, ns, iface) via sysfs -- SysfsInventory + ModemDescriptor wire model
  - FR-13  # Emit typed Diag snapshot every cycle -- build_diag wraps ModemSnapshot[] into Diag(BaseWire)
  - FR-70  # TaskGroup + per-task asyncio.timeout(8s) -- observe_all + _probe_one
  - FR-71  # Per-modem isolation -- per-task try/except (state-store flock unchanged from Phase 1)
  - NFR-4  # Per-modem QMI probes run in parallel -- TaskGroup creates one task per modem
  - NFR-10  # Recovers from any single transient error -- per-probe TimeoutError/Exception absorbed; siblings unaffected (verified test_one_slow_probe_does_not_cancel_siblings + test_exception_in_probe_does_not_propagate_to_taskgroup)

# Metrics
duration: 25min
completed: 2026-05-06
---

# Phase 2 Plan 4: Observer + Inventory Summary

**InventorySource Protocol + SysfsInventory walker + asyncio.TaskGroup-based per-modem probe orchestrator with per-task asyncio.timeout(8s); observer enforces FR-10 Zao gate before qmicli and exception isolation per NFR-11.**

## Performance

- **Duration:** ~25 minutes
- **Started:** 2026-05-06T16:45 (after plan 02-05 completion)
- **Completed:** 2026-05-06T19:58 (per task 2 commit timestamp)
- **Tasks:** 2 of 2
- **Files created:** 16
- **Files modified:** 1 (tests/fakes/inventory.py)
- **Tests added:** 21 (7 inventory + 14 observer)
- **Total project test count:** 422 -> 436 (+14 observer; 7 inventory tests existed in this plan only)

## Accomplishments

- Inventory subsystem complete: ModemDescriptor wire type, InventorySource Protocol, SysfsInventory production walker, FixtureInventory updated to use the production type. The Plan 02-01 promotion documented in 02-01-SUMMARY landed here.
- Observer subsystem complete: TaskGroup + per-task `asyncio.timeout(8s)` orchestrator (FR-70/NFR-4), per-task exception isolation (NFR-11), Zao-active short-circuit (FR-10/ADR-0003), pure RECOVERY_SPEC §4 issue extractor, and one-Diag-per-cycle builder (FR-13).
- Self-test enforcement: the PLAN's deliberately-placed `WhoModem(usb_path="", cdc_wdm=None)` placeholder hint was deleted in implementation; `test_extract_issues_who_uses_modem_usb_path_and_cdc_wdm` proves the implementation uses the modem-derived WhoModem.

## Task Commits

1. **Task 1: Inventory + SysfsInventory + sysfs walker tests** - `c7b798f` (feat)
2. **Task 2: Observer orchestrator + Diag builder + Issue extractor + 14 tests** - `6b19b1a` (feat)

## Files Created/Modified

### `src/spark_modem/inventory/`
- `descriptor.py` -- `ModemDescriptor(BaseWire)` with line/cdc_wdm/usb_path/ns/iface (FR-2; ADR-0009 keying anchor at usb_path)
- `protocol.py` -- `InventorySource(Protocol, runtime_checkable)` with `async def scan() -> list[ModemDescriptor]`
- `sysfs.py` -- `SysfsInventory(sysfs_root_override=...)` walking `/sys/bus/usb/devices/` for VID:PID 1199:9091; skips devices not yet enumerated (no cdc-wdm child)

### `src/spark_modem/observer/`
- `orchestrator.py` -- `observe_all` (TaskGroup) + `_probe_one` (per-task asyncio.timeout + try/except) + zao_active/timed_out/errored snapshot factories
- `issue_extractor.py` -- `probe_modem_to_snapshot` (7 qmicli queries sequentially per modem) + `_safe_parse_*` (per-parser dispatch) + pure `extract_issues` mapping observed facts -> RECOVERY_SPEC §4 Issues
- `diag_builder.py` -- `build_diag` (one Diag per cycle, per-modem dict keyed by usb_path)

### Tests
- `tests/unit/inventory/test_sysfs.py` -- 7 tests (4 cross-platform: empty root, line derivation, both Protocol isinstances; 3 Linux-only: 4-modem tree, non-Sierra skip, missing-cdc-wdm skip)
- `tests/unit/observer/test_orchestrator.py` -- 14 tests: 5 orchestrator behavioural + 6 extract_issues per-category + 1 placeholder-WhoModem self-test + 1 module-import sanity + 1 (the asyncio import sanity)
- `tests/unit/observer/test_diag_builder.py` -- 2 tests (per-modem packing, empty list)

### Fixtures
- `tests/fixtures/inventory/four_modems_one_zao_active.json` -- four-modem topology used by orchestrator's Zao-skip test
- `tests/fixtures/inventory/two_modems.json` -- two-modem topology
- `tests/fixtures/sysfs/four_modems/sys/bus/usb/devices/.gitkeep` -- documentary tree root; tests materialise temp sysfs trees per-test under tmp_path

### Modified
- `tests/fakes/inventory.py` -- removed local `_FixtureModemDescriptor`; now imports `spark_modem.inventory.descriptor.ModemDescriptor`. `scan()` returns `list[ModemDescriptor]`.

## Decisions Made

(see frontmatter `key-decisions` for the audit-precise list)

Headlines:

- **Per-parser `_safe_parse_*` helpers, not a generic dispatcher.** mypy --strict cannot narrow the success-type from a TypeVar over `(GetSignalResult | QmiError)` style unions; copy-paste is the cheapest type-safe option.
- **Sub-class FakeRunner for slow / exception probes.** Mirrors the FakeRunner public surface so mypy --strict stays clean and the test's intent is local.
- **Zao-active snapshot is built fresh from descriptor fields only.** No risk of leaking stale state; FR-10 enforced even if Zao reports the wrong line.
- **`_timed_out_snapshot` and `_errored_snapshot` are equivalent today.** Functions stay separate so Phase 3 can split them (timed-out drives a watchdog metric; errored doesn't).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Replaced PLAN's placeholder dummies with the canonical `WhoModem` build**
- **Found during:** Task 2 (issue_extractor.py implementation)
- **Issue:** PLAN intentionally placed two dummy `who = WhoModem(usb_path="" , ...)` lines marked "placeholder fix below" as a read-the-comments trap.
- **Fix:** Deleted the dummies and used `who = WhoModem(usb_path=modem.usb_path, cdc_wdm=modem.cdc_wdm)` at the top of `extract_issues` (immediately after removing `del modem`).
- **Files modified:** `src/spark_modem/observer/issue_extractor.py`
- **Verification:** `test_extract_issues_who_uses_modem_usb_path_and_cdc_wdm` asserts `who.usb_path == modem.usb_path` for every issue; passes (would fail with empty-string usb_path if the placeholder had survived).
- **Committed in:** `6b19b1a` (Task 2)

**2. [Rule 2 - Critical functionality] Added `pytest.mark.skipif(win32)` to sysfs-tree tests only, not the whole file**
- **Found during:** Task 1 (test_sysfs.py initial draft)
- **Issue:** PLAN guidance suggested skipping tests 2-4 on Windows; the cross-platform tests (1, 5, 6, 7) must still run on Windows dev hosts.
- **Fix:** Module-level `_SKIP_WIN_SYSFS = pytest.mark.skipif(...)` decorator applied to `test_finds_four_em7421_modems`, `test_skips_non_sierra_vendor`, `test_skips_modem_without_cdc_wdm`. Other tests run unconditionally.
- **Files modified:** `tests/unit/inventory/test_sysfs.py`
- **Verification:** Windows pytest run reports `4 passed, 3 skipped`.
- **Committed in:** `c7b798f` (Task 1)

**3. [Rule 1 - Bug fix] PLR2004 magic-number lint flagged 1/99 line-range constants in SysfsInventory**
- **Found during:** Task 1 (ruff check)
- **Issue:** `return value if 1 <= value <= 99 else 1` triggers PLR2004 (magic value).
- **Fix:** Extracted `_LINE_MIN: Final[int] = 1`, `_LINE_MAX: Final[int] = 99` module-level constants and updated the comparison.
- **Files modified:** `src/spark_modem/inventory/sysfs.py`
- **Verification:** ruff check passes; `test_line_from_usb_path` still green.
- **Committed in:** `c7b798f` (Task 1)

**4. [Rule 1 - Bug fix] ruff PLR0912 (too many branches) on `extract_issues` -- annotated, not refactored**
- **Found during:** Task 2 (ruff check)
- **Issue:** `extract_issues` has one branch per RECOVERY_SPEC §4 row by design (>12 branches).
- **Fix:** `# noqa: PLR0912 - one branch per RECOVERY_SPEC §4 row by design`. Refactoring into a dispatch table would obscure the §4-to-Issue mapping that's the whole point of the function.
- **Files modified:** `src/spark_modem/observer/issue_extractor.py`
- **Verification:** ruff check passes; the function's per-category structure is preserved for human review.
- **Committed in:** `6b19b1a` (Task 2)

**5. [Rule 1 - Bug fix] Async test functions instead of `asyncio.run()` calls**
- **Found during:** Task 1 (ruff PLC0415 on inline `import asyncio`)
- **Issue:** Initial draft used `asyncio.run(inv.scan())` inside sync test bodies, which forced an inline import.
- **Fix:** Switched to `async def test_*` (pytest-asyncio mode=auto handles them); top-level `import asyncio` only where genuinely needed (the slow-runner subclass).
- **Files modified:** `tests/unit/inventory/test_sysfs.py`
- **Verification:** ruff clean, tests still pass.
- **Committed in:** `c7b798f` (Task 1)

## RECOVERY_SPEC §4 split: observer vs policy

| §4 row | Detected here | Detected in policy/ |
|---|---|---|
| `config/apn_empty` | `extract_issues` if profile.apn is None or "" | -- |
| `config/apn_mismatch` | -- | requires carrier table; lives in `policy/decision_table.py` |
| `sim/sim_card_*`, `sim/sim_app_*` | `extract_issues` from GetSimStateResult | -- |
| `datapath/raw_ip_off` | `extract_issues` if current.raw_ip == "N" | -- |
| `datapath/session_disconnected` | `extract_issues` if data.connection_status == "disconnected" | -- |
| `registration/not_registered_*` | `extract_issues` from RegistrationState enum | -- |
| `qmi/qmi_proxy_died` | `extract_issues` from QmiError(reason=PROXY_DIED) | (already short-circuited at QmiWrapper.classify) |
| `qmi/qmi_timeout` | `extract_issues` from QmiError(reason=TIMEOUT) | -- |
| `qmi/qmi_channel_hung` | -- | fleet-wide aggregation (>=75 % of modems QMI-failing); plan 02-05 |
| `qmi/operating_mode_*` | `extract_issues` from GetOperatingModeResult | -- |

## Phase 2 / Phase 3 swap plan

The InventorySource Protocol seam means Phase 3 plugs in `UdevInventory` (pyudev.Monitor + `add_reader(monitor.fileno())`) without touching observer/. The Phase 3 inventory will additionally push events to the cycle driver's `event_queue` (M-02), but the observe-time `scan()` call signature stays identical. SysfsInventory remains useful as a startup primer and a fallback when the netlink monitor is briefly unavailable.

## Verification

- `python -m mypy --strict src/spark_modem/inventory/ src/spark_modem/observer/ tests/unit/inventory/ tests/unit/observer/` -- exits 0 (13 source files)
- `python -m ruff check src/spark_modem/inventory/ src/spark_modem/observer/ tests/unit/inventory/ tests/unit/observer/ tests/fakes/inventory.py` -- All checks passed
- `python -m ruff format --check ...` -- 7 files already formatted
- `python -m pytest tests/unit/inventory/ tests/unit/observer/ -q` -- 18 passed, 3 skipped (Linux-only sysfs tests skipped on Windows dev host)
- `python -m pytest tests/unit/ -q` -- 436 passed, 44 skipped (no regressions)
- `bash scripts/lint_no_subprocess.sh` -- exits 0
- `! grep -E "asyncio\.gather|asyncio\.wait_for" src/spark_modem/observer/` -- no anti-patterns
- `! grep "create_subprocess_exec" src/spark_modem/observer/` -- observer never spawns subprocesses (all I/O routes through QmiWrapper -> subproc.runner)

Acceptance-grep gates from PLAN:

- `grep -q "asyncio.TaskGroup()" src/spark_modem/observer/orchestrator.py` -- yes
- `grep -q "asyncio.timeout(timeout_s)" src/spark_modem/observer/orchestrator.py` -- yes
- `grep -c "except TimeoutError" src/spark_modem/observer/orchestrator.py` -- 1
- `grep -c "except Exception" src/spark_modem/observer/orchestrator.py` -- 1
- `grep -q "is_line_active(modem.line)" src/spark_modem/observer/orchestrator.py` -- yes (FR-10 gate present)
- `grep -q "WhoModem(usb_path=modem.usb_path, cdc_wdm=modem.cdc_wdm)" src/spark_modem/observer/issue_extractor.py` -- yes (placeholder bug fixed)
- `grep -q "_SIERRA_VID = \"1199\"" src/spark_modem/inventory/sysfs.py` -- yes
- `grep -q "_EM7421_PID = \"9091\"" src/spark_modem/inventory/sysfs.py` -- yes

## Self-Check: PASSED

**Created files:**

- `src/spark_modem/inventory/__init__.py` -- FOUND
- `src/spark_modem/inventory/descriptor.py` -- FOUND
- `src/spark_modem/inventory/protocol.py` -- FOUND
- `src/spark_modem/inventory/sysfs.py` -- FOUND
- `src/spark_modem/observer/__init__.py` -- FOUND
- `src/spark_modem/observer/orchestrator.py` -- FOUND
- `src/spark_modem/observer/issue_extractor.py` -- FOUND
- `src/spark_modem/observer/diag_builder.py` -- FOUND
- `tests/unit/inventory/__init__.py` -- FOUND
- `tests/unit/inventory/test_sysfs.py` -- FOUND
- `tests/unit/observer/__init__.py` -- FOUND
- `tests/unit/observer/test_orchestrator.py` -- FOUND
- `tests/unit/observer/test_diag_builder.py` -- FOUND
- `tests/fixtures/inventory/four_modems_one_zao_active.json` -- FOUND
- `tests/fixtures/inventory/two_modems.json` -- FOUND
- `tests/fixtures/sysfs/four_modems/sys/bus/usb/devices/.gitkeep` -- FOUND

**Commits:**

- `c7b798f` -- FOUND (feat: Task 1)
- `6b19b1a` -- FOUND (feat: Task 2)
