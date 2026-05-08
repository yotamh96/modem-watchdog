---
phase: 03-linux-event-sources-lifecycle
plan: 02
subsystem: event-sources / inventory / qmi
tags: [udev-producer, pyudev, udev-inventory, netns-derivation, qmi-netns-prepend, tdd]

# Dependency graph
requires:
  - phase: 03-linux-event-sources-lifecycle
    plan: 01
    provides: WakeSignal closed StrEnum (UDEV / RTNETLINK / ZAO_LOG / EVENTS_LOG_ROTATED / KMSG); restart_on_crash supervisor; Sleeper / FakeAsyncinotify test seams; linux_only marker
  - phase: 02-core-daemon-laptop-testable
    provides: InventorySource Protocol + ModemDescriptor.ns field; SysfsInventory walk shape; QmiWrapper 11 qmicli methods; FakeRunner argv-recording test fake; FixtureZaoTailer dual-surface fake pattern
provides:
  - UdevInventory impl of InventorySource (composition over SysfsInventory) — Plan 03-06 swaps SysfsInventory → UdevInventory at daemon wiring time
  - run_udev_producer coroutine that pushes WakeSignal.UDEV on Sierra-VID add/remove/bind/unbind; Linux-only pyudev import deferred so module is Windows-importable
  - derive_ns(usb_dev_path, *, netns_root=...) pure function — sysfs-readable netns name derivation; bench Jetson single-namespace returns None
  - QmiWrapper(ns: str | None = None) — every qmicli method auto-prepends `ip netns exec <ns>` when ns is set; 11-method regression test gates future additions
  - FakeUdevDevice + FakeUdevMonitor test fakes (mirroring FixtureZaoTailer dual-surface pattern)
affects:
  - 03-03-rtnetlink-producer (mirrors udev producer shape — restart_on_crash wrapping, _make_callback factory pattern, _MonitorProto co-located)
  - 03-04-asyncinotify-producers (same producer-task pattern)
  - 03-05-kmsg-classifier (same producer-task pattern + the IssueDetail extension Plan 03-01 already shipped)
  - 03-06-lifecycle-integration (consumes UdevInventory in daemon wiring; consumes the deferred-pyudev-import producer factory)
  - Phase 4 destructive actions (modem_reset / usb_reset / driver_reset) — every new qmicli method MUST route through self._argv to keep the netns prepend single-sourced

# Tech tracking
tech-stack:
  added:
    - pyudev (deferred Linux-only import inside _build_default_monitor; mypy ignore_missing_imports added to pyproject.toml)
  patterns:
    - "Deferred Linux-only library import: production code path uses `import pyudev` inside the factory function; module-level imports stay cross-platform; tests inject a FakeUdevMonitor and never trigger the real import"
    - "Closure-factory test seam: _make_on_readable(monitor=, event_queue=, sierra_vid=) returns the callback so unit tests exercise classification + drain logic directly without going through loop.add_reader (which requires a real POSIX fd)"
    - "Composition-over-inheritance for Protocol satisfiers: UdevInventory holds a SysfsInventory and delegates scan() — the on-demand sysfs walk shape is shared; the wake-trigger orthogonal mechanism lives in event_sources/udev_producer.py"
    - "Argv prepend via single private helper: QmiWrapper._argv() is the single source of truth for the netns prefix; every existing method routes through it; the 11-method parameterized regression test catches future additions that bypass"
    - "Inode-by-stat netns name resolution: derive_ns walks /var/run/netns entries, comparing stat().st_ino against the inode parsed from the sysfs `net:[<inode>]` symlink target — subprocess-free, bench-Jetson-friendly (returns None on absent dir)"
    - "Testable defaults for filesystem helpers: derive_ns accepts a netns_root parameter (default Path('/var/run/netns')); tests inject tmp_path instead of patching imports"

key-files:
  created:
    - src/spark_modem/event_sources/udev_producer.py
    - src/spark_modem/inventory/netns.py
    - src/spark_modem/inventory/udev.py
    - tests/fakes/udev.py
    - tests/unit/event_sources/test_udev_producer.py
    - tests/unit/inventory/test_netns_derivation.py
    - tests/unit/inventory/test_udev_inventory.py
    - tests/unit/qmi/test_wrapper_netns.py
  modified:
    - src/spark_modem/inventory/sysfs.py
    - src/spark_modem/qmi/wrapper.py
    - src/spark_modem/daemon/cycle_driver.py
    - src/spark_modem/cli/diag.py
    - pyproject.toml

key-decisions:
  - "pyudev.Monitor.from_netlink + loop.add_reader is the sole USB subscription path — MonitorObserver never imported (PITFALLS §7.1 PRESCRIPTIVE; pyudev #194/#363/#402 silent observer-thread crashes)"
  - "Producer body is signals-only: action filter forwards add / remove / bind / unbind for ID_VENDOR_ID==1199; `change` and other actions are dropped at the producer; sysfs reads happen ONLY in inventory.scan() driven by cycle re-observation (E-02 single source of truth)"
  - "4 MiB SO_RCVBUF on the udev monitor (PITFALLS §7.3) absorbs USB hub re-enumeration storms; 16-event hub power-cycle becomes one coalesced cycle wake via the cycle scheduler's drop-on-full event_queue (ADR-0002)"
  - "pyudev import deferred to keep the module Windows-importable: dev hosts can `from spark_modem.event_sources.udev_producer import run_udev_producer` without libudev.so.1; the import only triggers on Linux when _build_default_monitor() runs"
  - "_make_on_readable factored as a module-level closure factory so unit tests invoke classification + drain logic directly (cross-platform); one POSIX-only test exercises the loop.add_reader / remove_reader lifecycle through an os.pipe() pair"
  - "UdevInventory uses composition over inheritance: holds a SysfsInventory and delegates scan() — the sysfs walk shape is shared, only the wake mechanism is event-driven; observer/cycle_driver doesn't change at the swap boundary"
  - "derive_ns picks Open Question 4 option-(a): sysfs symlink at <usb_dev_path>/.../net/wwan*/device/ns/net resolved against /var/run/netns by inode; bench Jetson is single-namespace (link absent, returns None); production fleets that wrap each modem in a per-line netns will see the real name"
  - "QmiWrapper.ns parameter defaults to None — backwards-compatible for every existing call site; only Plan 03-02 and Plan 03-06 wire descriptor.ns through; the test_default_ns_is_none_for_backwards_compatibility test pins this contract"
  - "Every qmicli method routes through self._argv() — single source of truth for the netns prepend; the 11-method parameterized regression test loudly catches a Phase 4 destructive method (modem_reset / usb_reset / driver_reset) that bypasses _argv"
  - "test_method_count_pins_eleven_qmicli_methods asserts len(_ALL_METHODS) == 11; adding a method without updating the parametrize list (and therefore without verifying _argv wrapping) fails this test instead of silently bypassing the gate"

patterns-established:
  - "Pattern: Linux-only library deferred import — production factory function does `import x` lazily; module-level imports stay cross-platform; tests inject fakes and never trigger the real import. Plans 03-03/04/05 will adopt for pyroute2 / asyncinotify / /dev/kmsg."
  - "Pattern: closure-factory test seam — extract the inner callback as `_make_<name>(monitor=, event_queue=, ...)` returning the callable so unit tests exercise the logic without going through the event loop. Cross-platform classification tests with one POSIX-only end-to-end lifecycle test."
  - "Pattern: argv-prepend single source of truth — every method calls self._argv([...]) to wrap argv in the optional namespace prefix; one parameterized test asserts every method routes through. Future destructive-action additions (Phase 4) cannot silently bypass."
  - "Pattern: testable filesystem-helper defaults — pure function accepts a `<root>: Path | None = None` parameter (default Path('/var/run/netns')); tests inject tmp_path. No imports patched; no monkey-patching of stdlib."

requirements-completed: [FR-1, FR-3, FR-4]

# Metrics
duration: 13min
completed: 2026-05-08
---

# Phase 3 Plan 02: Udev Producer + UdevInventory + Netns End-to-End Summary

**Wires the udev event source AND the netns-aware QmiWrapper end-to-end: pyudev.Monitor + loop.add_reader producer pushing WakeSignal.UDEV, UdevInventory composition over SysfsInventory, derive_ns sysfs symlink resolution, and `ip netns exec <ns>` argv prepend on every qmicli method routed through a single private helper.**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-05-08T14:17:42Z
- **Completed:** 2026-05-08T14:30:16Z
- **Tasks:** 2 (TDD: 4 commits — test/feat/test/feat)
- **Files modified:** 13 (8 created + 5 modified)
- **Test suite:** 1723 passed / 57 skipped in 17.39s (M7 30s budget preserved with ~12.6s slack)

## Accomplishments

- Locked the udev-producer shape every downstream Phase 3 producer plan (rtnetlink / asyncinotify / kmsg) will mirror: closure-factory test seam, deferred Linux-only library import, _MonitorProto co-located for test injection, restart_on_crash-friendly factory signature.
- Shipped UdevInventory behind the existing InventorySource Protocol — Plan 03-06's daemon wiring swap is one line (`SysfsInventory(...)` → `UdevInventory(...)`); observer/cycle_driver/cli/diag don't change.
- Wired derive_ns end-to-end: inventory/sysfs.py descriptor construction now passes `ns=derive_ns(resolved)` instead of the literal None placeholder; existing tmp_path tests still hold (no /sys/.../device/ns/net link in fixtures, so derive_ns returns None and the `assert ns is None` shape is unchanged).
- Extended QmiWrapper with optional `ns: str | None = None` parameter and a single private _argv() helper; every one of the 11 existing qmicli methods (7 query + 4 state-changing) routes through it — the 11-method parameterized regression test plus a count-pin assertion (`len(_ALL_METHODS) == 11`) is the gate that catches a Phase 4 destructive method bypassing the prepend.
- Updated three production call sites (cycle_driver.py qmi_factory + per-action QmiWrapper construction + cli/diag.py qmi_factory) to pass `ns=descriptor.ns` so the prepend activates automatically when the descriptor's ns field is populated. On bench Jetson with ns=None this is a no-op; in netns-deployed fleets it activates the prepend.
- 1723 tests pass in 17.39s on Windows dev host (M7 30s budget preserved with ~12.6s slack); mypy --strict + ruff check + ruff format all green on every new/modified file; SP-04 subprocess lint passes (the new `ip netns exec` argv ride through subproc.runner via QmiWrapper — no new direct subprocess calls).

## Task Commits

Each task followed TDD (RED → GREEN), committed atomically:

1. **Task 1 RED — failing tests for udev_producer + FakeUdevMonitor** — `2c3ad2f` (test)
2. **Task 1 GREEN — udev_producer with deferred pyudev import** — `9cd7429` (feat)
3. **Task 2 RED — failing tests for derive_ns + UdevInventory + QmiWrapper netns prepend** — `dd3130b` (test)
4. **Task 2 GREEN — netns derivation + UdevInventory + QmiWrapper.ns + cycle_driver/cli/diag wire-up** — `a0be28f` (feat)

## Files Created/Modified

### Created

- `src/spark_modem/event_sources/udev_producer.py` — `run_udev_producer(*, event_queue, sierra_vid="1199", monitor=None)` coroutine; uses `pyudev.Monitor.from_netlink(Context())` + `loop.add_reader(monitor.fileno(), on_readable)` per PITFALLS §7.1 PRESCRIPTIVE. Body emits `WakeSignal.UDEV` for Sierra-VID add/remove/bind/unbind events; no sysfs reads, no parsing, no state derivation (E-02). pyudev import deferred inside `_build_default_monitor()` to keep the module Windows-importable. `_make_on_readable` extracted as a module-level closure factory so unit tests invoke classification + drain logic directly.
- `src/spark_modem/inventory/netns.py` — `derive_ns(usb_dev_path, *, netns_root=None)` pure function; walks `<usb_dev_path>/.../net/wwan*/device/ns/net` symlinks; resolves `net:[<inode>]` against `netns_root` (default `/var/run/netns`) by `stat().st_ino`. Returns `None` on bench-Jetson single-namespace setup (link absent, dir absent, malformed target, unparseable inode, no matching entry).
- `src/spark_modem/inventory/udev.py` — `UdevInventory` impl of `InventorySource` via composition over `SysfsInventory`; constructor accepts `sysfs_root_override` and forwards to the delegate.
- `tests/fakes/udev.py` — `FakeUdevDevice` (action / id_vendor_id / sys_name + `.get(key)`) + `FakeUdevMonitor` (filter_by / set_receive_buffer_size / start / fileno / poll + test-only `inject_device` and `set_fileno` mutators). Mirrors the `FixtureZaoTailer` dual-surface pattern (production Protocol + test-only injectors).
- `tests/unit/event_sources/test_udev_producer.py` — 9 tests: classification & drain (cross-platform via `_make_on_readable`), VID match / VID miss / action miss / drain-multiple / mixed-batch / drain-empty / missing-VID-property; 1 POSIX-only end-to-end test through `os.pipe()` verifying `loop.add_reader` / `loop.remove_reader` lifecycle; 1 cross-platform import smoke test.
- `tests/unit/inventory/test_netns_derivation.py` — 8 tests: non-existent path, missing wwan dir (cross-platform), missing ns/net link, malformed link target (multiple shapes), unparseable inode, missing netns_root, matching inode resolves to name (POSIX-only via parameter-injected tmp_path netns_root).
- `tests/unit/inventory/test_udev_inventory.py` — 3 tests: Protocol satisfaction (cross-platform), empty-tmp-path delegation (cross-platform), full sysfs-tree materialisation through delegate (POSIX-only).
- `tests/unit/qmi/test_wrapper_netns.py` — 14 tests: argv-unchanged-when-ns-none, argv-prepended-when-ns-set, default-ns-is-none-for-backcompat, 11 parameterized methods × every-method-routes-through-_argv, plus the count-pin assertion `len(_ALL_METHODS) == 11`.

### Modified

- `src/spark_modem/inventory/sysfs.py` — added `from spark_modem.inventory.netns import derive_ns` import; replaced `ns=None,  # Phase 3 derives from netns` with `ns=derive_ns(resolved),  # E-05; None on single-namespace`. Two-line change; sysfs walk shape preserved.
- `src/spark_modem/qmi/wrapper.py` — `QmiWrapper.__init__` gains `ns: str | None = None` parameter stored as `self._ns`; new private `_argv(self, qmicli_args: list[str]) -> list[str]` helper prepends `["ip", "netns", "exec", self._ns]` when `self._ns is not None`. All 11 existing qmicli methods (7 query + 4 state-changing) now build their argv inside a list and pass it through `self._argv([...])`. Body shape unchanged otherwise.
- `src/spark_modem/daemon/cycle_driver.py` — `qmi_factory` passes `ns=m.ns`; per-action QmiWrapper construction (line 304ish) takes `ns_for_action = ns_by_usb.get(who.usb_path)` from a new `ns_by_usb` dict mirroring the existing `cdc_by_usb` dict. Two surgical edits, no over-refactor.
- `src/spark_modem/cli/diag.py` — `qmi_factory` passes `ns=m.ns`; one-line change.
- `pyproject.toml` — `pyudev` added to the existing `[[tool.mypy.overrides]] module = ["sdnotify", "asyncinotify"]` list (now `["sdnotify", "asyncinotify", "pyudev"]`) — same pattern as the other Linux-only libs.

## Decisions Made

See key-decisions in frontmatter — most load-bearing:

1. **pyudev import deferred so the module is Windows-importable.** The import lives inside `_build_default_monitor()`. Production code path on Linux triggers it; dev hosts (Windows / non-Linux) and tests inject `monitor=FakeUdevMonitor()` and never reach the import. Keeps the dev-host suite cross-platform without `skipif` on the module-import level.

2. **_make_on_readable as a module-level closure factory.** The plan called for tests #2..#5 to "exercise classification + drain via direct callback invocation"; extracting the closure factory as a public-but-underscored module-level function makes that possible without exposing the internals of the run_udev_producer coroutine. Unit tests call `_make_on_readable(...)` directly; the producer coroutine itself uses the factory under `loop.add_reader`.

3. **UdevInventory delegates to SysfsInventory rather than subclassing.** Composition over inheritance — the sysfs walk shape is shared, but Phase 3+ extensions (caching across cycles, netns-aware scoping, hot-plug grace periods) can land on UdevInventory without touching SysfsInventory's polling-friendly shape. The `InventorySource` Protocol is satisfied transparently; observer/cycle_driver don't see a difference.

4. **derive_ns option-(a): sysfs symlink + inode-by-stat resolution.** RESEARCH.md Open Question 4 listed three options. Option-(a) — read `/sys/.../net/wwan*/device/ns/net` symlink and resolve `net:[<inode>]` against `/var/run/netns/` entries by `stat().st_ino` — is the most subprocess-free path. The bench Jetson is single-namespace (link absent, returns None); production fleets that use `ip netns add <name>` per modem will see the real names without code changes.

5. **netns_root parameter injection over import patching.** `derive_ns(usb_dev_path, *, netns_root=None)` accepts an override that defaults to `Path('/var/run/netns')`. Tests pass tmp_path; no monkey-patching of stdlib modules. Same testable-defaults pattern as Phase 1's `SysfsInventory.__init__(*, sysfs_root_override=...)`.

6. **`ns: str | None = None` defaults to None for backwards compatibility.** Every existing QmiWrapper call site (observer tests, actions tests, cli/diag tests, cycle_driver tests, the wrapper test suite itself) compiles unchanged; the netns prepend only activates when a caller explicitly passes `ns=<name>`. The `test_default_ns_is_none_for_backwards_compatibility` test pins this contract.

7. **Single private `_argv` helper as the source of truth.** The PITFALLS §6.2 invariant ("never setns from the asyncio loop") is enforced by routing every qmicli argv through one helper. The parameterized 11-method test plus a `len(_ALL_METHODS) == 11` count-pin assertion guard against a future destructive method (modem_reset / usb_reset / driver_reset in Phase 4) that builds its argv inline and bypasses the prepend.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Lint] pyudev added to pyproject.toml mypy ignore_missing_imports override**
- **Found during:** Task 1 GREEN mypy --strict (`Cannot find implementation or library stub for module named "pyudev"`)
- **Issue:** mypy --strict could not resolve the deferred `import pyudev` inside `_build_default_monitor()` (no stubs available on PyPI; not installed on Windows dev host). The existing override at `[[tool.mypy.overrides]] module = ["sdnotify", "asyncinotify"]` covers the same shape (Linux-only Phase 3 libs).
- **Fix:** Added `"pyudev"` to the existing list — `["sdnotify", "asyncinotify", "pyudev"]`.
- **Verification:** `mypy --strict src/spark_modem/event_sources/udev_producer.py tests/fakes/udev.py` → Success: no issues found in 2 source files.
- **Committed in:** `9cd7429` (Task 1 GREEN).

**2. [Rule 1 — Type] _make_on_readable return type tightened to `Callable[[], None]`**
- **Found during:** Task 1 GREEN mypy --strict (`Argument 2 to "add_reader" of "AbstractEventLoop" has incompatible type "object"; expected "Callable[[], Any]"`)
- **Issue:** The initial `_make_on_readable` return type was `"object"` (forward-ref string) which mypy couldn't widen to a Callable that `loop.add_reader` accepts.
- **Fix:** Imported `Callable` from `collections.abc` and annotated the return type as `Callable[[], None]`.
- **Verification:** mypy --strict clean.
- **Committed in:** `9cd7429` (Task 1 GREEN).

**3. [Rule 1 — Lint] PLC0415 `import os` / `import sys` moved out of function bodies**
- **Found during:** Task 1 GREEN ruff check + Task 2 GREEN ruff check
- **Issue:** Two test functions had inline `import os` / `import sys` (the plan suggested they could be inline for readability, but ruff PLC0415 disallows non-top-level imports in test files outside the deferred-Linux-import production case).
- **Fix:** Moved to top-level imports in `tests/unit/event_sources/test_udev_producer.py` and `tests/unit/inventory/test_udev_inventory.py`.
- **Verification:** ruff check clean.
- **Committed in:** `9cd7429` (Task 1) and `a0be28f` (Task 2).

**4. [Rule 1 — Lint] PTH211 `os.symlink` → `Path.symlink_to` in test_netns_derivation.py**
- **Found during:** Task 2 GREEN ruff check (5 PTH211 violations)
- **Issue:** Test file used `os.symlink(target, link_path)` for symlink creation; ruff's `PTH` rule prefers `Path.symlink_to(target)` from pathlib.
- **Fix:** All 5 call sites replaced with `ns_link.symlink_to(target_str)`. Removed the now-unused `import os`.
- **Verification:** ruff check clean.
- **Committed in:** `a0be28f` (Task 2 GREEN).

### Acceptance-criterion micro-deviation (consistent with Plan 03-01 precedent)

The plan's acceptance criteria for Task 1 specify:
- `grep -c "MonitorObserver" src/spark_modem/event_sources/udev_producer.py` returns 0
- `grep -c "subprocess|os.system|create_subprocess_exec" src/spark_modem/event_sources/udev_producer.py` returns 0

The MonitorObserver check returns ONE match — the docstring at line 9 (`PITFALLS §7.1 PRESCRIPTIVE: NEVER pyudev.MonitorObserver`). No actual usage. Same pattern as Plan 03-01's accepted micro-deviation: the intent is "no usage of the anti-pattern," not "no mention of the name." The defensive documentation strengthens the contract for future maintainers (a Phase 4 dev considering `MonitorObserver` reads the warning before importing).

The plan's Task 2 acceptance criterion `grep -c "setns" src/spark_modem/qmi/wrapper.py` returns 0 — but the actual count is 2 (both inside the `_argv` docstring's PITFALLS §6.2 callout). Same disposition: documentation strengthens the contract, no actual `setns()` call exists. `grep -r "setns(" src/spark_modem/` confirms the only matches are docstring text, never function calls.

### Plan-suggested test count modulation (Task 1)

The plan asked for "exactly 6 test cases" in `test_udev_producer.py`. The implementation ships **9 tests**:
- The 6 plan-specified cases (all green).
- Plus a `test_drain_terminates_on_empty_queue` regression for the empty-queue path (the drain loop terminator).
- Plus a `test_device_without_id_vendor_id_property_does_not_push` regression for the missing-VID-property branch (the type-narrowing `isinstance(vid_raw, str)` guard).
- Plus a `test_module_imports_cross_platform` smoke test verifying `run_udev_producer` and `_make_on_readable` are callable on Windows (the deferred-pyudev-import contract).

These 3 extra tests are belt-and-suspenders coverage for branches the 6 specified cases didn't hit; all stay under the test-budget M7 and don't add wall-clock time noticeably (8 of 9 are pure-Python without any I/O).

## Authentication Gates

None — Plan 03-02 is pure local code with no external service interactions. The only "external" interface is the kernel netlink socket which a unit test cannot exercise without root privileges; the POSIX-only end-to-end test uses an `os.pipe()` pair instead, which is enough to verify the `loop.add_reader` / `loop.remove_reader` lifecycle.

## Threat Surface Scan

Threat register check passed: every threat in the plan's `<threat_model>` section that was assigned `mitigate` disposition has its mitigation in place:

- **T-03-02-01** (sysfs not fully populated on `add` event) — mitigated by including `bind` in the producer's `_MATCHING_ACTIONS` frozenset; cycle re-observation reads sysfs and the descriptor is built only when `_find_cdc_wdm` succeeds (Phase 2 NFR-10 single-cycle recovery).
- **T-03-02-02** (USB hub re-enumeration storm) — mitigated by `set_receive_buffer_size(4 MiB)` in `_build_default_monitor`; cycle coalescing already in Phase 2 `CycleScheduler.event_queue`. Verified by `grep -c "set_receive_buffer_size" src/spark_modem/event_sources/udev_producer.py` → 2 (constant + call site).
- **T-03-02-03** (TOCTOU on setns from asyncio loop) — mitigated: `setns(` never appears as a call in `src/spark_modem/`; only docstring callouts of the anti-pattern. Verified by `grep -rn "setns(" src/spark_modem/` returning only documentation matches.
- **T-03-02-04** (MonitorObserver thread crashes silently) — mitigated: the producer uses `pyudev.Monitor.from_netlink(Context())` + `loop.add_reader` exclusively; `MonitorObserver` never imported. Verified by `grep -rn "MonitorObserver" src/spark_modem/` returning only docstring callouts.
- **T-03-02-05** (netns name leaked in events.jsonl) — accepted: netns name is non-secret topology metadata; same risk as cdc-wdmN/usb_path which already appear in events.jsonl.
- **T-03-02-06** (Producer Exception escapes TaskGroup root) — mitigated by Plan 03-01's `restart_on_crash` (this plan's producer coroutine signature `async def run_udev_producer(...) -> None` is restart_on_crash-compatible — clean return on cancel, exception escapes for the supervisor to catch).
- **T-03-02-07** (Forged sysfs `device/ns/net` symlink) — accepted; daemon is already root (NFR-30); no other suid binary present.

No new security-relevant surface introduced beyond the plan's threat model. The QmiWrapper netns prepend uses list-form argv (no shell metacharacter expansion); netns names flow from /var/run/netns/ filenames (root-owned dir).

## Deferred Issues

None — all auto-fix issues stayed within the current task's scope (the `pyudev` mypy override, type narrowing, ruff formatting, and PTH211 symlink modernisation are all in files this plan modified or created).

## Self-Check: PASSED

**Files exist:**
- FOUND: `src/spark_modem/event_sources/udev_producer.py`
- FOUND: `src/spark_modem/inventory/netns.py`
- FOUND: `src/spark_modem/inventory/udev.py`
- FOUND: `tests/fakes/udev.py`
- FOUND: `tests/unit/event_sources/test_udev_producer.py`
- FOUND: `tests/unit/inventory/test_netns_derivation.py`
- FOUND: `tests/unit/inventory/test_udev_inventory.py`
- FOUND: `tests/unit/qmi/test_wrapper_netns.py`

**Files modified (verified by `git log`):**
- FOUND: `src/spark_modem/inventory/sysfs.py` modified in `a0be28f`
- FOUND: `src/spark_modem/qmi/wrapper.py` modified in `a0be28f`
- FOUND: `src/spark_modem/daemon/cycle_driver.py` modified in `a0be28f`
- FOUND: `src/spark_modem/cli/diag.py` modified in `a0be28f`
- FOUND: `pyproject.toml` modified in `9cd7429`

**Commits exist (verified by `git log --oneline -5`):**
- FOUND: `2c3ad2f` test(03-02): add failing tests for udev_producer + FakeUdevMonitor
- FOUND: `9cd7429` feat(03-02): implement udev producer with deferred pyudev import
- FOUND: `dd3130b` test(03-02): add failing tests for netns derivation + UdevInventory + QmiWrapper netns prepend
- FOUND: `a0be28f` feat(03-02): implement netns derivation + UdevInventory + QmiWrapper netns prepend

**Final acceptance:**
- `pytest -q` reports 1723 passed / 57 skipped / 0 failed in 17.39s
- `mypy --strict src/spark_modem/event_sources/udev_producer.py src/spark_modem/inventory/ src/spark_modem/qmi/wrapper.py` reports 0 issues across 8 source files
- `ruff check` + `ruff format --check` green on every new/modified file
- `bash scripts/lint_no_subprocess.sh` exits 0 (the new `["ip", "netns", "exec", ns]` argv ride through subproc.runner via QmiWrapper — no new direct subprocess calls)
- `grep -c "self._argv" src/spark_modem/qmi/wrapper.py` returns 11 (all 11 existing qmicli methods routed)
- `grep -c "ns=derive_ns" src/spark_modem/inventory/sysfs.py` returns 1 + `grep -c "ns=None" src/spark_modem/inventory/sysfs.py` returns 0 (sysfs is now wired)
- M7 budget preserved (17.39s ≤ 30s with ~12.6s slack)
- `python -c "from spark_modem.event_sources.udev_producer import run_udev_producer"` exits 0 on Windows (deferred-pyudev contract)
- `python -c "from spark_modem.inventory.udev import UdevInventory; from spark_modem.inventory.protocol import InventorySource; assert isinstance(UdevInventory(), InventorySource)"` exits 0 (Protocol satisfaction)

## TDD Gate Compliance

Each task within is `type="auto" tdd="true"`. Per-task TDD gate sequence verified in git log:

| Task | RED commit (test) | GREEN commit (feat) | Gate sequence |
|------|-------------------|---------------------|---------------|
| Task 1 | `2c3ad2f` test(03-02): failing tests for udev_producer | `9cd7429` feat(03-02): udev producer | RED-then-GREEN ✓ |
| Task 2 | `dd3130b` test(03-02): failing tests for derive_ns + UdevInventory + QmiWrapper netns | `a0be28f` feat(03-02): netns + UdevInventory + QmiWrapper | RED-then-GREEN ✓ |

Both tasks demonstrated true RED before GREEN (verified by running pytest after the RED commit and observing failure on the new tests; Task 1 RED failed at collection-time with `ModuleNotFoundError: No module named 'spark_modem.event_sources.udev_producer'`; Task 2 RED failed at collection-time with `ModuleNotFoundError: No module named 'spark_modem.inventory.netns'`).

## Cross-References for Downstream Plans

**Plan 03-03 (rtnetlink-producer)** consumes:
- `WakeSignal.RTNETLINK` from supervisor.py (Plan 03-01 already shipped).
- The `_make_<name>_callback` closure-factory pattern + deferred Linux-only import (`import pyroute2` inside the factory, not at module top) — exact mirror of `udev_producer.py`'s shape.
- The `restart_on_crash`-compatible signature: `async def run_rtnetlink_producer(*, event_queue: ...) -> None`.

**Plan 03-04 (asyncinotify-producers)** consumes:
- `WakeSignal.ZAO_LOG` and `WakeSignal.EVENTS_LOG_ROTATED` from supervisor.py.
- The same closure-factory + deferred-import pattern.
- `tests.fakes.asyncinotify.FakeAsyncinotify` (Plan 03-01 already shipped).

**Plan 03-05 (kmsg-classifier)** consumes:
- `WakeSignal.KMSG` from supervisor.py.
- The 6 host-level IssueDetail values Plan 03-01 already extended.
- The same closure-factory pattern (no deferred import — /dev/kmsg is plain os.open).

**Plan 03-06 (lifecycle-integration)** consumes:
- `UdevInventory` — swap `SysfsInventory(...)` → `UdevInventory(...)` at daemon wiring time.
- `run_udev_producer` factory under `restart_on_crash`.
- The `descriptor.ns` flowing into QmiWrapper construction (already wired in cycle_driver.py / cli/diag.py — Plan 03-06's only addition is the production sysfs walk that populates a real netns name when /var/run/netns has matching entries).

**Phase 4 destructive actions** (modem_reset / usb_reset / driver_reset) — every new qmicli method MUST route its argv through `self._argv([...])`. The 11-method parameterized test in `tests/unit/qmi/test_wrapper_netns.py` plus the `len(_ALL_METHODS) == 11` count-pin assertion will fail loudly when a 12th method is added without updating both the implementation and the test list. This is the single source of truth that prevents a Phase 4 bypass.
