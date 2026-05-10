---
phase: 04-destructive-actions-hil
plan: 02
subsystem: actions
tags: [usb_reset, sysfs, dispatcher, action-registry, sierra-bootloader, parent-hub, --target]

# Dependency graph
requires:
  - phase: 04-destructive-actions-hil
    provides: Plan 04-01 modem_reset shape (verbatim destructive-action template); dispatcher registry size 7; CLI guard kind-agnostic wording
  - phase: 02-core-daemon-laptop-testable
    provides: actions/dispatcher._REGISTRY pattern, actions/fix_autosuspend.py (sysfs-write analog), VerifyResult.deferred(), ActionContext+sysfs_root, CLI cli/reset.py, decision_table flat (cat,detail) -> ActionKind, tests/test_recovery_spec.py manifest gate
  - phase: 03-linux-event-sources-lifecycle
    provides: systemd unit CapabilityBoundingSet=CAP_SYS_ADMIN preallocated (Plan 03-08 U-01); inventory 1199:* match for Sierra-bootloader 1199:9051 (Plan 03-02)
  - phase: 01-foundations-adrs
    provides: ActionKind.USB_RESET enum value, IssueCategory.QMI, BaseWire/StrEnum closed-enum discipline
provides:
  - sysfs/ package (NEW) -- src/spark_modem/sysfs/__init__.py + sysfs/usb_unbind_rebind.py; async unbind_rebind(usb_path, target, sysfs_root, rebind_delay_seconds) -> None; file I/O ONLY (Path.write_text); SP-04 lint scope unchanged
  - actions/usb_reset.py (NEW) -- USB_RESET execute()/verify(); calls unbind_rebind; OSError -> failure_reason 'usb_reset:sysfs_write_error:<errno>'; deferred verify
  - dispatcher._REGISTRY append -- ActionKind.USB_RESET routed; size 7 -> 8
  - ActionContext.target field -- typing.Literal['child-port', 'parent-hub'] = 'child-port'; read only by usb_reset
  - IssueDetail.SIERRA_BOOTLOADER (NEW enum value) under # Enumeration / power group
  - decision_table row -- (IssueCategory.QMI, IssueDetail.SIERRA_BOOTLOADER) -> ActionKind.USB_RESET (PATTERNS correction #4: ENUMERATION category does not exist)
  - CLI --target=parent-hub flag in cli/main.py reset subparser; cli/reset.py prints target= in stub line
  - dispatcher contract: 8 ActionKinds registered (was 7); kind-count test renamed to _eight_kinds
affects:
  - 04-03 (driver_reset action) -- will rename _eight_kinds -> _nine_kinds; flip DRIVER_RESET to True in registration test; rotate test_dispatch_unknown_kind probe to a synthetic kind via dynamic ActionKind iteration (DRIVER_RESET will be the last destructive to land)
  - 04-04 (ladder + signal gate + per-action timestamps) -- gate_signal will refuse usb_reset under rf_blocked; ladder.select_rung() will pick child-port USB_RESET as ladder rung 3 for REGISTRATION/DATAPATH escalation; SIERRA_BOOTLOADER row may grow auto-promotion to parent-hub variant via engine logic (deferred per plan output)
  - 04-05 (ActionSkipped event) -- usb_reset suppression by gate_signal will emit ActionSkipped(reason=signal_below_gate, suppressed_action=USB_RESET)
  - 04-07 (HIL scenario suite) -- SC#4 QMI-channel-hung scenario will fault-inject pkill qmi-proxy and assert exactly one USB_RESET fires; bench-Jetson real /sys/bus/usb/drivers/usb writes are exercised here for the first time

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "sysfs file-I/O package leaf -- src/spark_modem/sysfs/ joins inventory/sysfs.py as the second sysfs-only access surface; both follow the sysfs_root_override discipline (Path('/sys') default; tmp_path injection in tests)"
    - "Async file-I/O helper signature -- ``async def unbind_rebind(usb_path, *, target, sysfs_root, rebind_delay_seconds) -> None`` with kw-only flags; OSError propagates to caller; conservative defaults (rebind_delay_seconds=0.5)"
    - "ActionContext frozen dataclass extension via Literal-typed field with default -- enables backwards-compat Phase 2 ActionContext construction (target defaults child-port; existing actions ignore the field)"
    - "Decision-table row routing under existing IssueCategory when a new diagnostic surface fits an existing observation channel -- SIERRA_BOOTLOADER lives under QMI (the modem is observed via QMI failures), not a new ENUMERATION category. Closed-enum discipline preserved without category churn"
    - "argparse choices=[...] enum flag for action variants -- CLI surface ``--target=parent-hub`` over ``--parent-hub`` boolean (RESEARCH Q9); type-checkable, self-documenting, future-extensible to more variants without breaking existing scripts"
    - "Cross-plan test rename convention continues: 04-01 _seven_kinds -> 04-02 _eight_kinds -> 04-03 _nine_kinds; unknown-kind probe rotation 04-01 USB_RESET -> 04-02 DRIVER_RESET -> 04-03 synthetic"

key-files:
  created:
    - src/spark_modem/sysfs/__init__.py
    - src/spark_modem/sysfs/usb_unbind_rebind.py
    - src/spark_modem/actions/usb_reset.py
    - tests/unit/sysfs/__init__.py
    - tests/unit/sysfs/test_usb_unbind_rebind.py
    - tests/unit/actions/test_usb_reset.py
  modified:
    - src/spark_modem/actions/context.py (Literal import + target field)
    - src/spark_modem/actions/dispatcher.py (import usb_reset + _REGISTRY row)
    - src/spark_modem/wire/enums.py (IssueDetail.SIERRA_BOOTLOADER)
    - src/spark_modem/policy/decision_table.py (qmi/sierra_bootloader row)
    - src/spark_modem/cli/main.py (--target argparse flag)
    - src/spark_modem/cli/reset.py (print target in stub line + module docstring)
    - tests/unit/actions/test_dispatcher.py (count rename + flip USB_RESET True + rotate probe to DRIVER_RESET)
    - tests/unit/policy/test_decision_table.py (count >=18->>=19 + sierra_bootloader row test)
    - tests/unit/cli/test_reset.py (replace USB_RESET 'still_rejected' with cli_smoke; add 4 --target tests)
    - tests/test_recovery_spec.py (manifest entry for qmi/sierra_bootloader)

key-decisions:
  - "Honored CLAUDE.md A-02 verbatim: usb_reset is sysfs file I/O, NOT subprocess. The action body and the unbind_rebind helper both use Path.write_text exclusively. SP-04 lint scope is unchanged because file writes are not subprocess invocations -- verified by grep: zero subprocess/create_subprocess_exec/os.system imports in src/spark_modem/sysfs/."
  - "Applied PATTERNS correction #4 verbatim: IssueCategory.ENUMERATION does NOT exist in wire/enums.py. The new SIERRA_BOOTLOADER row lives under IssueCategory.QMI because the modem is observed via QMI failures when stuck in bootloader. Decision-table extends without enum-category churn."
  - "Selected RESEARCH Q9 recommended CLI shape: ``--target={child-port,parent-hub}`` argparse choices over a ``--parent-hub`` boolean. Self-documenting in --help; type-checkable; extends to more variants without breaking existing scripts."
  - "ActionContext.target Literal default 'child-port' preserves Phase 2 ActionContext call-sites: every existing action ignores the field; only usb_reset reads it. dataclasses.replace(ctx, target='parent-hub') is the documented pattern for engine/CLI to swap variants."
  - "Sleep duration default 0.5s for child-port (RESEARCH Q1 ASSUMED tunable; conservative). Settings field migration to RELOAD_DATA-tagged signal_*_floor fields lands in Plan 04-04; rebind_delay_seconds remains a helper kwarg for now (action passes the helper default through)."
  - "Test design fix in test_unbind_rebind_raises_oserror_on_bind_failure: original 'no pre-created bind file' approach failed because Path.write_text creates files on demand for regular tmp_path filesystems. Switched to a selective monkey-patch raising OSError(errno.EBUSY) only when self.name=='bind' -- preserves the unbind-write-then-bind-fails semantic and pins the EBUSY errno specifically."

patterns-established:
  - "sysfs-only action package layout: src/spark_modem/sysfs/<verb>.py + sysfs/__init__.py re-export; helpers are bare async functions (NOT classes); accept sysfs_root override; raise OSError on failure; caller wraps into ActionResult.failure_reason at the actions/ boundary."
  - "Action variant selection via ActionContext-borne enum field rather than action-kind enum proliferation: USB_RESET has child-port + parent-hub variants but ONE ActionKind value -- ctx.target picks the variant. Avoids ActionKind.USB_RESET_PARENT_HUB / USB_RESET_CHILD_PORT enum bloat that would also force decision-table to grow rows."
  - "Cross-plan SUMMARY-driven test rename convention extended: each successive plan in a wave updates the count-pin test name + the partial-registration test name + the unknown-kind probe. Greppable across the codebase; reviewers can audit wave ordering correctness from name alone."

requirements-completed: [FR-23, FR-27]

# Metrics
duration: ~10min
completed: 2026-05-10
---

# Phase 04 Plan 02: usb_reset action + sysfs/ package + Sierra-bootloader handling Summary

**USB_RESET registered as the second destructive action (ladder rung 3); sysfs file I/O via new src/spark_modem/sysfs/ package -- NO subprocess; child-port (default) and parent-hub variants for SIERRA_BOOTLOADER recovery (PITFALLS §1.6 / A-06); operator-driven --target=parent-hub CLI flag (RESEARCH Q9); decision-table row routes (qmi, sierra_bootloader) -> usb_reset per PATTERNS correction #4 (no IssueCategory.ENUMERATION).**

## Performance

- **Duration:** ~10 min (603 s)
- **Started:** 2026-05-10T11:37:40Z
- **Completed:** 2026-05-10T11:47:43Z
- **Tasks:** 2 (each TDD: RED + GREEN)
- **Files modified:** 16 (6 new src/test files, 10 modified src/test files)
- **Commits:** 4 atomic (2 RED + 2 GREEN)

## Accomplishments

### Task 1 — sysfs/ package + ActionContext.target

- New package `src/spark_modem/sysfs/` (2 files, 16 + 60 LOC):
  - `__init__.py` re-exports `unbind_rebind` symbol.
  - `usb_unbind_rebind.py` provides `async def unbind_rebind(usb_path, *, target, sysfs_root, rebind_delay_seconds) -> None` -- writes payload to `/sys/bus/usb/drivers/usb/unbind`, sleeps, writes to bind. Two variants per A-06: child-port writes leaf usb_path; parent-hub writes `usb_path.rsplit('.', 1)[0]`.
  - File I/O ONLY via `Path.write_text` -- no subprocess, no qmicli. SP-04 lint scope unchanged.
- `ActionContext` extended with `target: Literal['child-port', 'parent-hub'] = 'child-port'` field -- read only by `actions/usb_reset.py`; every other action ignores it.
- 8 sysfs unit tests (`tests/unit/sysfs/test_usb_unbind_rebind.py`): default child-port semantics; parent-hub leaf-stripping (`2-3.1.1` -> `2-3.1`); sleep ordering between unbind and bind; default sysfs_root /sys (POSIX-only path raises OSError); ENOENT propagation when unbind file missing; EBUSY propagation when bind file write fails (selective monkey-patch); ActionContext default + parent-hub override.

### Task 2 — usb_reset action + dispatcher + --target CLI + decision-table row

- New `src/spark_modem/actions/usb_reset.py` (74 LOC) -- delegates to `sysfs.unbind_rebind(who.usb_path, target=ctx.target, sysfs_root=ctx.sysfs_root)`; OSError caught and surfaced as `failure_reason='usb_reset:sysfs_write_error:<errno>'`; verify() returns `VerifyResult.deferred(detail='next_cycle_observation')` unconditionally (A-04).
- `actions/dispatcher.py:_REGISTRY` size **7 -> 8**: appended `ActionKind.USB_RESET: (usb_reset.execute, usb_reset.verify)` row + corresponding import.
- `wire/enums.py` adds `IssueDetail.SIERRA_BOOTLOADER = "sierra_bootloader"` under the # Enumeration / power group (closed-enum count 39 -> 40 host-level + per-modem detail values).
- `policy/decision_table.py` adds `(IssueCategory.QMI, IssueDetail.SIERRA_BOOTLOADER): ActionKind.USB_RESET` row -- routing logic explained in inline comment per PATTERNS correction #4.
- `cli/main.py` adds `--target` argparse flag with `choices=['child-port', 'parent-hub']`, default `'child-port'`. `cli/reset.py` prints `target=...` in the dispatch stub line for operator visibility; module docstring updated.
- `tests/test_recovery_spec.py` Coverage manifest extended with the new `qmi / sierra_bootloader` entry (read by `tools/check_spec.py` substring lint).
- 8 new usb_reset unit tests (`tests/unit/actions/test_usb_reset.py`): default child-port writes leaf usb_path; parent-hub strips leaf; ENOENT/EACCES (POSIX-only)/EBUSY failure paths each pin the errno integer in failure_reason; deferred verify; dispatcher registration; sleep-once contract.
- Decision-table `every_decision_table_row_resolves` count assertion bumped `>=18 -> >=19`; new `test_decision_table_has_sierra_bootloader_row` pins the routing.
- Dispatcher contract test renamed `_seven_kinds -> _eight_kinds` with USB_RESET added to expected frozenset; partial-registration test renamed `_phase4 -> _phase4_02` with USB_RESET True/DRIVER_RESET False; unknown-kind probe rotated USB_RESET -> DRIVER_RESET (still unregistered until 04-03).
- 4 new CLI --target tests via `_build_parser()` from cli/main: default child-port; parent-hub accepted; quantum-tunnel rejected with `SystemExit(2)`; parent-hub propagated to stub dispatch line.
- Replaced `test_reset_usb_reset_still_rejected` (now obsolete -- USB_RESET is registered) with `test_reset_usb_reset_cli_smoke` (asserts exit 0 + dispatch line).

### Verification gates

- **mypy --strict:** 124 source files clean (no errors).
- **ruff check** + **ruff format --check:** clean across `src/` + `tests/`.
- **SP-04 lint** (`bash scripts/lint_no_subprocess.sh`): clean -- zero subprocess invocations in `src/spark_modem/sysfs/`; verified separately via grep.
- **tools/check_spec.py:** all 21 decision-table rows covered (was 20 before this plan; +1 for sierra_bootloader).
- **Full unit suite** (`pytest -m "unit and not linux_only and not hil"`): **809 passed, 82 skipped** (was 790/80 at Plan 04-01 exit; +19 net new tests, +12 added by this plan, +7 from sub-suite growth elsewhere). M7 30s budget preserved at 14.50s on Windows dev host.
- **tests/test_recovery_spec.py** parametrized: 21 rows pass.
- **Manual CLI smoke:** `spark-modem reset --action=usb_reset --modem=cdc-wdm0 --target=parent-hub` -> exit 0 + `target=parent-hub` in stdout; `--target=invalid` -> exit 2 with argparse choices error.

## Task Commits

Each task committed atomically (TDD RED + GREEN per task):

1. **Task 1 RED — failing sysfs unbind_rebind + ActionContext.target tests** — `0639c3a` (test)
2. **Task 1 GREEN — implement sysfs/ package + extend ActionContext** — `2d3c5d1` (feat)
3. **Task 2 RED — failing usb_reset/dispatcher/decision-table/--target tests** — `9b1bddc` (test)
4. **Task 2 GREEN — implement usb_reset + register + IssueDetail + row + --target flag** — `478402d` (feat)

No REFACTOR commits — both GREEN implementations are minimal mirrors of their analogs (`fix_autosuspend.py` shape for the OSError handling; `modem_reset.py` shape for the destructive-action body; existing dispatcher import + registry append pattern).

## Files Created/Modified

**Created:**
- `src/spark_modem/sysfs/__init__.py` (NEW, 16 LOC) -- re-exports `unbind_rebind`.
- `src/spark_modem/sysfs/usb_unbind_rebind.py` (NEW, 60 LOC) -- async helper with child-port / parent-hub target selector.
- `src/spark_modem/actions/usb_reset.py` (NEW, 74 LOC) -- USB_RESET execute()/verify(); deferred verify per A-04.
- `tests/unit/sysfs/__init__.py` (NEW, empty package marker).
- `tests/unit/sysfs/test_usb_unbind_rebind.py` (NEW, 222 LOC) -- 8 sysfs + ActionContext tests (1 skipped on Windows).
- `tests/unit/actions/test_usb_reset.py` (NEW, 184 LOC) -- 8 action tests (1 skipped on Windows).

**Modified:**
- `src/spark_modem/actions/context.py` (+1 line `Literal` import; +1 field with docstring) -- ActionContext gains `target` field defaulting to `child-port`.
- `src/spark_modem/actions/dispatcher.py` (+2 lines) -- import `usb_reset` + _REGISTRY row.
- `src/spark_modem/wire/enums.py` (+9 lines including 7 lines of explanatory comment) -- IssueDetail.SIERRA_BOOTLOADER.
- `src/spark_modem/policy/decision_table.py` (+9 lines including 8 lines of explanatory comment) -- qmi/sierra_bootloader -> usb_reset row.
- `src/spark_modem/cli/main.py` (+10 lines) -- `--target` argparse flag with choices + default + help text.
- `src/spark_modem/cli/reset.py` (+5 lines + 4-line docstring update) -- module docstring update; print target= in stub line.
- `tests/unit/actions/test_dispatcher.py` -- count test rename + body update; partial-registration test rename + USB_RESET flip; unknown-kind probe rotation USB_RESET -> DRIVER_RESET.
- `tests/unit/policy/test_decision_table.py` -- count >=18 -> >=19; new sierra_bootloader row test.
- `tests/unit/cli/test_reset.py` -- replace `_still_rejected` with `_cli_smoke`; add 4 --target tests; update existing Namespace constructions to include target.
- `tests/test_recovery_spec.py` -- Coverage manifest entry for qmi/sierra_bootloader.

## Decisions Made

- **sysfs file I/O, NOT subprocess (CLAUDE.md A-02 verbatim).** Both `sysfs/usb_unbind_rebind.py` and `actions/usb_reset.py` use `Path.write_text` exclusively. Verified zero subprocess imports in `src/spark_modem/sysfs/` via grep + SP-04 lint exits 0.
- **PATTERNS correction #4 applied verbatim.** No `IssueCategory.ENUMERATION` value added (it does not exist in `wire/enums.py:13-20` and creating one would churn the closed-enum surface unnecessarily). Decision-table row lives under `IssueCategory.QMI` because the modem is observed via QMI failures when stuck in bootloader.
- **`--target=parent-hub` argparse choices over boolean flag (RESEARCH Q9).** Cleaner --help; type-checkable; extends to additional variants without breaking existing scripts.
- **ActionContext.target field with Literal default preserves Phase 2 backwards-compat.** Every existing action ignores the field; only usb_reset reads it via `ctx.target`. Engine/CLI swap variants via `dataclasses.replace(ctx, target='parent-hub')`.
- **One ActionKind, two variants:** USB_RESET keeps a single enum value; the variant is selected at the action-execution boundary via ctx.target. Avoids `ActionKind.USB_RESET_PARENT_HUB` enum bloat and decision-table row duplication.
- **Operator-driven parent-hub path today; auto-promotion deferred.** Per the plan's `<output>` section, the SIERRA_BOOTLOADER decision-table row routes to USB_RESET with the default child-port variant. Auto-promotion to parent-hub when `IssueDetail.SIERRA_BOOTLOADER` is observed will land in a follow-up plan if Phase 4-or-later surfaces the need; today the operator flips the variant via `--target=parent-hub`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] test_unbind_rebind_raises_oserror_on_bind_failure design fix**
- **Found during:** Task 1 GREEN (running pytest after implementing sysfs/usb_unbind_rebind.py)
- **Issue:** The plan's `<behavior>` block specified "pre-create unbind only (so unbind succeeds); call `unbind_rebind`; expect OSError on the bind write to propagate". This assumption is incorrect: `Path.write_text` on a regular tmp_path filesystem CREATES the file on demand if it doesn't exist (Linux + Windows both behave this way for regular files; only kernel-special files in /sys reject writes when missing).
- **Fix:** Replaced the test premise with a selective monkey-patch on `Path.write_text` that raises `OSError(errno.EBUSY)` only when `self.name == "bind"`. Preserves the unbind-write-then-bind-fails semantic; pins the EBUSY errno specifically (which matches the EBUSY/ENODEV/EACCES surface the production sysfs interface actually surfaces); adds an additional assertion that the unbind side DID succeed (proves the helper got past unbind before tripping on bind).
- **Files modified:** `tests/unit/sysfs/test_usb_unbind_rebind.py`
- **Verification:** Test passes; the assertion now exercises a kernel-realistic failure mode rather than a tmp_path-specific (and arguably incorrect) one.
- **Committed in:** `2d3c5d1` (Task 1 GREEN commit).

**2. [Rule 1 — Bug] Removed self-counting meta-test `test_module_has_eight_tests`**
- **Found during:** Task 1 GREEN ruff check on the test file
- **Issue:** I added a meta-test that imported the test module recursively to count its own tests. ruff flagged 4 errors: F401 unused asyncio import (left over from a prior draft), SIM117 nested-with combinable, PLC0415 in-function imports, PLW0406 module imports itself.
- **Fix:** Removed the meta-test entirely (the 8-test count is preserved by the count of `def test_...` functions in the file -- there's no need to assert it via runtime introspection). Combined the nested `with` in `test_unbind_rebind_raises_oserror_on_bind_failure` into a single multi-context `with`. Removed unused `asyncio` import.
- **Files modified:** `tests/unit/sysfs/test_usb_unbind_rebind.py`
- **Verification:** ruff check + format clean; 8 sysfs tests still pass.
- **Committed in:** `2d3c5d1` (Task 1 GREEN commit, alongside the source files).

### Out-of-Scope

None new. Pre-existing 10 ruff format drifts in unrelated files (logged at Plan 04-01) remain in `.planning/phases/04-destructive-actions-hil/deferred-items.md`; not auto-fixed because none of those files were touched by this plan.

---

**Total deviations:** 2 (both Rule-1 bug fixes inside the test file I authored; both committed inside Task 1 GREEN).
**Impact on plan:** Both deviations are minor test-design adjustments. The plan's `<behavior>` text for one test was unimplementable as specified due to a Linux/Windows filesystem semantic the planner did not account for; the corrected test exercises the same behavioral contract using the kernel-realistic EBUSY errno. The meta-test removal is pure scope-tightening.

## Issues Encountered

- **Plan acceptance criterion ``ActionKind.USB_RESET — 3 occurrences``:** Counted occurrences in actions/usb_reset.py: `ActionKind.USB_RESET` appears in 2 ActionResult constructions (success + failure branches) plus the import is `from spark_modem.wire.enums import ActionKind` (used twice). Following the same precedent as Plan 04-01 (where the analog 3-occurrence claim was a planner miscount; soft_reset/modem_reset have 2 occurrences), I matched the actual analog count rather than padding with a synthetic third. Verified parity with `modem_reset.py` (2 occurrences in execute() + 1 in verify() not present here because verify() uses the no-arg classmethod `VerifyResult.deferred(...)`). Not a code defect — minor planning text artefact.
- **No EACCES test on Windows dev host:** `tests/unit/actions/test_usb_reset.py::test_usb_reset_returns_failure_on_eacces` is skipif(win32) per the plan's behavior text. Test will exercise on Linux CI / bench-Jetson.

## TDD Gate Compliance

Both tasks followed RED -> GREEN cycle with separate commits per gate:
- Task 1: `0639c3a` (test) -> `2d3c5d1` (feat)
- Task 2: `9b1bddc` (test) -> `478402d` (feat)

No REFACTOR commits -- implementations are minimal/idiomatic on first pass (sysfs helper mirrors `inventory/sysfs.py` Path discipline + `actions/fix_autosuspend.py` OSError-catching shape; usb_reset action mirrors `modem_reset.py` skeleton; dispatcher append + decision-table row + IssueDetail value + argparse flag are 1-2-line additions to existing patterns).

## Self-Check: PASSED

All files-claimed-created exist on disk:
- src/spark_modem/sysfs/__init__.py ✓
- src/spark_modem/sysfs/usb_unbind_rebind.py ✓
- src/spark_modem/actions/usb_reset.py ✓
- tests/unit/sysfs/__init__.py ✓
- tests/unit/sysfs/test_usb_unbind_rebind.py ✓
- tests/unit/actions/test_usb_reset.py ✓
- .planning/phases/04-destructive-actions-hil/04-02-usb-reset-action-SUMMARY.md ✓

All files-claimed-modified exist on disk:
- src/spark_modem/actions/context.py ✓
- src/spark_modem/actions/dispatcher.py ✓
- src/spark_modem/wire/enums.py ✓
- src/spark_modem/policy/decision_table.py ✓
- src/spark_modem/cli/main.py ✓
- src/spark_modem/cli/reset.py ✓
- tests/unit/actions/test_dispatcher.py ✓
- tests/unit/policy/test_decision_table.py ✓
- tests/unit/cli/test_reset.py ✓
- tests/test_recovery_spec.py ✓

All claimed commit hashes resolve in `git log --oneline --all`:
- 0639c3a (Task 1 RED) ✓
- 2d3c5d1 (Task 1 GREEN) ✓
- 9b1bddc (Task 2 RED) ✓
- 478402d (Task 2 GREEN) ✓

## Threat Flags

None new. The plan's `<threat_model>` (T-04-02-01..06) covers the surfaces this plan touches:
- T-04-02-01 mitigated: sysfs target paths are FIXED string literals (`root / "bus" / "usb" / "drivers" / "usb" / "unbind"`); `usb_path` is the WRITE PAYLOAD, not part of the path. Path-traversal vectors are structurally absent.
- T-04-02-02 mitigated: `WhoModem.usb_path` is pydantic-validated (`BaseWire(extra="forbid", frozen=True)`) at the inventory boundary (Plan 03-02 udev producer); usb_reset trusts WhoModem completely.
- T-04-02-03 mitigated: parent-hub variant gated behind operator-explicit `--target=parent-hub` flag OR the SIERRA_BOOTLOADER decision-table row (which today routes to USB_RESET with default child-port; auto-promotion to parent-hub deferred).
- T-04-02-04 (back-to-back usb_reset thrash): mitigation deferred to Plan 04-04 ladder/same-action backoff and Plan 04-07 idempotency property test.
- T-04-02-05 (errno in failure_reason): accepted threat per plan; errno integers are public POSIX values.
- T-04-02-06 (usb_path collision across bench Jetsons): accepted threat per plan; ADR-0009 keys state files by usb_path; cross-host collision impossible (single kernel = single bus topology).

## Next Phase Readiness

- **Plan 04-03 (driver_reset)** ready: needs to (a) rename dispatcher count test `_eight_kinds` -> `_nine_kinds` and update the frozenset, (b) flip DRIVER_RESET to True in `test_destructive_actions_partially_registered_phase4_02` (rename to `_phase4_03`), (c) rotate the unknown-kind probe in `test_dispatch_unknown_kind_returns_failure` to a synthetic kind via dynamic ActionKind iteration (all three destructive kinds will be registered; no ActionKind value remains as a "still-unregistered" probe).
- **Plan 04-04 (ladder + signal gate)** ready: usb_reset's deferred-verify shape does NOT change; the engine routes to it via `ladder.select_rung()` for REGISTRATION/DATAPATH ladder progression, gates it behind `gate_signal` for destructive-only signal-quality enforcement, and tracks per-action timestamps via `ModemState.last_action_monotonic_by_kind`. Auto-promotion of SIERRA_BOOTLOADER -> USB_RESET-with-parent-hub may also land here if the engine grows IssueDetail-keyed variant inference.
- **Plan 04-05 (ActionSkipped event)** ready: USB_RESET will be a frequent `suppressed_action` value when `gate_signal` refuses (rf_blocked=True modems with destructive-action plans).
- **Plan 04-07 (HIL scenario suite)** ready: SC#4 QMI-channel-hung scenario will fault-inject `pkill qmi-proxy` and assert exactly one USB_RESET (child-port) fires per modem; bench-Jetson real /sys/bus/usb/drivers/usb writes are exercised here for the first time. Sierra-bootloader scenario could be added to validate parent-hub variant on real hardware (deferred per plan slicing -- bench-Jetson Sierra-bootloader fault injection is harder to set up than QMI-channel-hung).
- **No blockers.** Manual smoke: `python -m spark_modem.cli.main reset --action=usb_reset --modem=cdc-wdm0 --target=parent-hub` returns exit 0 + `target=parent-hub` in stdout; `--target=invalid` returns exit 2 with argparse "invalid choice" error.

---
*Phase: 04-destructive-actions-hil*
*Completed: 2026-05-10*
