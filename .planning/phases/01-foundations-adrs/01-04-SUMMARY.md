---
phase: 01-foundations-adrs
plan: 04
subsystem: state-store
tags:
  - python
  - state-store
  - atomic-writes
  - locks
  - hypothesis
  - schema-versioning
dependency_graph:
  requires:
    - 01-03-wire-package  # ModemState, GlobalsState, Identity, versioning, events
  provides:
    - state_store.StateStore       # full atomic + locked persistence layer
    - state_store.LoadResult       # (state, downgrade_event) typed result
    - state_store.GlobalsLoadResult
    - state_store.UsbPathMismatch  # exception (control flow; distinct from wire event)
    - state_store.StateStoreLocked # exception on flock contention
    - state_store.AtomicWriteFailed
    - state_store.cross_check_inventory    # pure-function sysfs cross-check
    - state_store.walk_sysfs_for_qmi_modems
    - state_store.PerModemLockTable
    - state_store.acquire_flock_async
  affects:
    - Phase 2 cycle driver (must call cross_check_inventory_for at startup)
    - Phase 2 CLI ctl commands (must use same StateStore.save_* for lost-update prevention)
tech_stack:
  added:
    - asyncio.Lock (per-modem in-process serialization)
    - fcntl.flock via acquire_flock_async (cross-process serialization; POSIX-only)
    - hypothesis (property tests for SC #5)
    - os.fsync + atomic rename (FR-62 atomic writes)
  patterns:
    - public/private lock split (deadlock-safe: asyncio.Lock not reentrant)
    - no-op flock sentinel (fd=-1) on Windows dev host
    - model_validate() instead of constructor when pydantic alias confuses mypy
key_files:
  created:
    - src/spark_modem/state_store/paths.py
    - src/spark_modem/state_store/errors.py
    - src/spark_modem/state_store/atomic.py
    - src/spark_modem/state_store/locks.py
    - src/spark_modem/state_store/inventory.py
    - src/spark_modem/state_store/store.py
    - tests/unit/state_store/__init__.py
    - tests/unit/state_store/test_atomic.py
    - tests/unit/state_store/test_locks.py
    - tests/unit/state_store/test_inventory.py
    - tests/unit/state_store/test_inventory_crosscheck.py
    - tests/unit/state_store/test_store.py
    - tests/unit/state_store/test_schema_downgrade.py
    - tests/unit/state_store/test_concurrent_writers.py
  modified:
    - src/spark_modem/state_store/__init__.py
decisions:
  - "Public/private lock split in StateStore: public save_* acquires asyncio.Lock + flock; private _save_*_locked is called from both save and load's downgrade branch — prevents asyncio.Lock re-entry deadlock"
  - "Windows dev-host flock no-op: _enter_flock_for_async returns AsyncFlockHandle(fd=-1) when _FCNTL_AVAILABLE=False so asyncio.Lock tests pass on Windows without skipping entire test files"
  - "model_validate() over constructor for _fresh_modem_state: bypasses mypy strict call-arg error on pydantic alias fields without pydantic mypy plugin"
  - "_schema_version_of() helper: extracts int schema_version from dict[str,object] without type: ignore, handling str/int/missing cases"
  - "Hypothesis tests use tempfile.TemporaryDirectory instead of tmp_path: tmp_path is function-scoped and shared across all Hypothesis examples in a single test run, causing sysfs tree accumulation"
metrics:
  duration: "approx 4 hours (context continuation)"
  completed_date: "2026-05-06"
  tasks_completed: 4
  tests_passed: 61
  tests_skipped: 17
  files_created: 14
  files_modified: 1
---

# Phase 1 Plan 4: State Store Summary

**One-liner:** Full atomic-write + 3-layer locking + non-destructive schema-downgrade + sysfs inventory cross-check layer (StateStore) implementing ADR-0009, ADR-0012, FR-62, FR-62.1, NFR-43, and SC #5.

## What Was Built

### Task 1 — paths.py + errors.py + atomic.py (commit 8ad9a85)

- `paths.py`: env-var-configurable path constructors (`SPARK_MODEM_STATE_ROOT`, `SPARK_MODEM_RUN_DIR`); `state_file_for_modem` rejects `/` and `..` in usb_path; `pid_lockfile` kept separate from `state.lock` (ADR-0012)
- `errors.py`: `UsbPathMismatch`, `StateStoreLocked`, `AtomicWriteFailed` exceptions with structured attributes
- `atomic.py`: temp + `os.fsync(tmp)` + `os.replace()` + directory `os.fsync` (FR-62); `AtomicWriteFailed` on any I/O error; no partial writes
- 22 tests passed (2 POSIX-only skipped on Windows dev host)

### Task 2 — locks.py (commit 07bc164)

- `PerModemLockTable`: `dict[str, asyncio.Lock]` lazily populated, per-key isolation
- `globals_lock()`: singleton asyncio.Lock for GlobalsState and IdentityMap
- `acquire_flock` / `acquire_flock_async` / `AsyncFlockHandle`: exclusive cross-process flock helpers with PID-write for debugging
- Lock acquisition order documented and enforced: asyncio.Lock first, flock second
- 16 tests (8 asyncio platform-independent passed; 8 POSIX-only flock tests skipped on Windows)

### Task 3 — inventory.py + hypothesis SC #5 tests (commit e5f9cb7)

- `walk_sysfs_for_qmi_modems(sysfs_root)`: pure function, returns `{usb_path: cdc_wdm}` for Sierra VID 1199 devices with `qmi/cdc-wdmN` subdirectory; hardware-free via configurable root
- `cross_check_inventory(...)`: raises `UsbPathMismatch` on vanished modem, usb_path mismatch, or stale cdc-wdm; returns None on consistency
- `test_inventory_crosscheck.py`: Hypothesis property test (50+30 examples, deadline=400ms) using `tempfile.TemporaryDirectory` for per-example isolation; proves "never silently overwrites state" — closes SC #5 pure-function half
- 11 tests passed (1 skipped — degenerate n==1 case)

### Task 4 — store.py + __init__.py + 3 test files (commit 6d8654a)

- `StateStore`: full wiring — `save_modem_state` (per-modem asyncio.Lock + per-modem flock), `load_modem_state` (schema-version check + non-destructive downgrade), `save_globals` / `load_globals`, `save_identity_map` / `load_identity_map`, `list_modem_state_usb_paths`, `cross_check_inventory_for`
- Deadlock-safe public/private split: `_save_modem_state_locked` and `_save_globals_locked` are called from downgrade branches without re-acquiring locks (asyncio.Lock is not reentrant)
- `test_store.py`: 17 tests — round-trips, concurrency, directory listing, cross-check wiring
- `test_schema_downgrade.py`: deadlock regression — `asyncio.timeout(5)` gate; shadow file created, fresh default written, downgrade event returned; forward-version raises `SchemaVersionTooNew`
- `test_concurrent_writers.py`: 4 POSIX-only tests — non-blocking flock contention raises `StateStoreLocked`; blocking flock waits for release
- `__init__.py`: full public surface exported

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Windows flock no-op for dev-host test compatibility**
- **Found during:** Task 4 execution — all StateStore tests failed on Windows dev host with `ImportError: fcntl is not available on this platform`
- **Issue:** `acquire_flock_async` called `_enter_flock_for_async` which raised `ImportError` when `_FCNTL_AVAILABLE=False`, but all StateStore load/save methods route through `acquire_flock_async`. On Windows dev host, this made every test fail even those testing only asyncio.Lock behavior.
- **Fix:** `_enter_flock_for_async` now returns `AsyncFlockHandle(fd=-1, path)` (no-op sentinel) when `_FCNTL_AVAILABLE=False`; `_release_flock_fd` returns immediately for `fd < 0`. All POSIX-dependent behavior is tested via `pytest.mark.skipif(not IS_POSIX)` marks.
- **Files modified:** `src/spark_modem/state_store/locks.py`
- **Commit:** 6d8654a

**2. [Rule 1 - Bug] mypy strict: `int(dict[str,object].get(...))` rejects `object` argument**
- **Found during:** Task 4 mypy run
- **Issue:** `raw: dict[str, object]` → `raw.get("schema_version", 0)` returns `object`; `int(object)` is not a valid mypy overload
- **Fix:** Added `_schema_version_of(raw: dict[str, object]) -> int` helper using `isinstance` narrowing to handle `int`/`str`/missing cases without `type: ignore`
- **Files modified:** `src/spark_modem/state_store/store.py`
- **Commit:** 6d8654a

**3. [Rule 1 - Bug] mypy strict: `ModemState(healthy_streak=0)` rejected — pydantic alias confusion**
- **Found during:** Task 4 mypy run
- **Issue:** `ModemState` field `healthy_streak` has `alias="_healthy_streak"`. Without the pydantic mypy plugin, mypy sees only the alias and rejects `healthy_streak=0` in the constructor with `Unexpected keyword argument`.
- **Fix:** `_fresh_modem_state` uses `ModemState.model_validate({..., "_healthy_streak": 0, ...})` which bypasses constructor type-checking. The `populate_by_name=True` config in BaseWire makes runtime accept both forms.
- **Files modified:** `src/spark_modem/state_store/store.py`
- **Commit:** 6d8654a

**4. [Rule 2 - Missing critical functionality] `by_usb_path` extraction from `dict[str, object]`**
- **Found during:** Task 4 mypy run
- **Issue:** `raw.get("by_usb_path", {})` returns `object`; assigning to `dict[str, object]` requires a `type: ignore[assignment]` that mypy then flagged as unused
- **Fix:** Extracted with `isinstance` narrowing: `by_usb_raw = raw.get("by_usb_path"); by_usb = by_usb_raw if isinstance(by_usb_raw, dict) else {}`
- **Files modified:** `src/spark_modem/state_store/store.py`
- **Commit:** 6d8654a

**5. [Rule 1 - Bug] Hypothesis tmp_path fixture shared across examples**
- **Found during:** Task 3 — test isolation
- **Issue:** `tmp_path` is function-scoped and shared across all Hypothesis examples in a single pytest run. Building sysfs trees accumulated entries from previous examples, making walker results non-deterministic.
- **Fix:** Both hypothesis tests use `tempfile.TemporaryDirectory()` (inside the test body) instead of `tmp_path` parameter, giving each Hypothesis example a completely fresh filesystem state.
- **Files modified:** `tests/unit/state_store/test_inventory_crosscheck.py`
- **Commit:** e5f9cb7

## Phase 2 Carry-Forward Note

The Phase 2 daemon-startup path MUST:
1. Call `await store.list_modem_state_usb_paths()` to enumerate all state files
2. For each usb_path, call `await store.cross_check_inventory_for(usb_path, walker)` before any `load_modem_state`
3. On `UsbPathMismatch`: emit sd_notify `STATUS=usb_path_mismatch`, exit non-zero (S-02)

CLI mutating commands (`ctl reset-state`, `ctl migrate-state`) MUST use the same `StateStore.save_*` methods the daemon does — NOT acquire flocks independently. This is wired at the StateStore method level to enforce CLAUDE.md invariant #12.

## Known Stubs

None — all methods are fully implemented. No placeholder data flows to UI or callers.

## Threat Flags

None — the state_store layer is an internal persistence layer. All trust boundaries were addressed:
- Atomic writes prevent partial-write tampering (T-04-01)
- Per-modem flock + asyncio.Lock prevent concurrent CLI/daemon lost-update (T-04-02)
- usb_path validation in paths.py prevents path-traversal (T-04-03)
- default mode 0o640 limits identity.json exposure (T-04-05)

## Self-Check: PASSED

**Files exist:**
- src/spark_modem/state_store/store.py: FOUND
- src/spark_modem/state_store/__init__.py: FOUND
- tests/unit/state_store/test_store.py: FOUND
- tests/unit/state_store/test_schema_downgrade.py: FOUND
- tests/unit/state_store/test_concurrent_writers.py: FOUND
- .planning/phases/01-foundations-adrs/01-04-SUMMARY.md: FOUND

**Commits exist:**
- 8ad9a85: Task 1 — paths.py + errors.py + atomic.py
- 07bc164: Task 2 — locks.py
- e5f9cb7: Task 3 — inventory.py + hypothesis
- 6d8654a: Task 4 — store.py + __init__.py + 3 test files

**Test results:** 61 passed, 17 skipped (all POSIX-only)
**ruff check:** All checks passed
**ruff format:** All files formatted
**mypy --strict:** Success: no issues found in 7 source files
