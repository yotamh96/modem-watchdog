---
phase: 02-core-daemon-laptop-testable
plan: 06
subsystem: actions
tags: [actions, dispatcher, recovery, fr-22, fr-28, fr-28.1, fr-30, fr-31, fr-32, fr-33, fr-40, nfr-42, set-apn, fix-raw-ip, sim-power-on, soft-reset, set-operating-mode, fix-autosuspend]

# Dependency graph
requires:
  - phase: 01-foundations-adrs
    provides: BaseWire (frozen, extra='forbid'); WhoModem; ActionKind enum (Phase 2 extended); CarrierTable + CarrierEntry; Settings (pydantic v2 BaseSettings); EventLogWriter (append-only JSONL); Event union (ActionPlanned/ActionExecuted/ActionFailed/...); CompletedProcess; FakeRunner / FakeClock test fakes
  - phase: 02-02-qmi-wrapper
    provides: QmiWrapper (always --device-open-proxy), QmiError + QmiErrorReason, classify(); query methods (nas_get_serving_system / wds_get_profile_settings / wds_get_current_settings / dms_get_operating_mode / uim_get_card_status); state-changing methods (dms_set_operating_mode / uim_sim_power_on / wds_modify_profile / wds_set_ip_family); per-intent parsers with extra='ignore'
  - phase: 02-05-policy-engine
    provides: PlannedAction shape (kind/who/reason/dry_run flags); decision-table mapping (consumer of ActionKind enum)
provides:
  - actions/dispatcher.execute_and_verify(kind, who, ctx, *, dry_run=False) -- SINGLE entry point used by both the cycle driver (plan 02-10) and the CLI (plan 02-09)
  - actions/dispatcher._REGISTRY: dict[ActionKind, (ExecuteFn, VerifyFn)] with EXACTLY six cheap-action entries (SET_APN / FIX_RAW_IP / SIM_POWER_ON / SOFT_RESET / SET_OPERATING_MODE / FIX_AUTOSUSPEND); destructive kinds (MODEM_RESET / USB_RESET / DRIVER_RESET) intentionally ABSENT (Phase 4 lands those by appending entries -- pure-data extension)
  - actions/dispatcher.is_registered(kind) + registered_kinds() introspection helpers
  - actions/result.ActionResult / VerifyResult dataclasses (frozen + slots; "all errors are data" contract; with_verify() copy-helper)
  - actions/context.ActionContext frozen dataclass + ClockProto / EventLogWriterProto Protocol seams
  - actions/verify shared helpers: verify_apn_equals / verify_raw_ip_y / verify_sim_state_not_power_down / verify_operating_mode_equals (one qmicli read-back per helper, returns VerifyResult.ok|failed)
  - Six action modules (one file per action) each exporting async execute(who, ctx) and async verify(who, ctx)
  - CarrierTable.lookup(mcc, mnc) -> CarrierEntry|None method on the existing Phase 1 wire type (FR-30)
  - 48 unit tests across 7 files covering registry shape, dry-run gate, verify helpers, and per-action happy + error paths
affects: [02-09-cli, 02-10-cycle-driver, phase-4-destructive-actions]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dispatcher registry pattern: `_REGISTRY: dict[ActionKind, tuple[ExecuteFn, VerifyFn]]` keyed on ActionKind. Phase 4 appends entries, no dispatcher code change. `registered_kinds()` and `is_registered()` are pure reads -- registry is immutable after import."
    - "execute_and_verify is the SINGLE dispatcher entry: emits ActionPlanned (always), short-circuits on dry_run=True with VerifyResult.deferred(), routes to (fn_exec, fn_verify), emits ActionExecuted on success or ActionFailed on failure. CLI and cycle driver share the same gate."
    - "Read-then-write idempotency (FR-31): set_apn / fix_raw_ip / set_operating_mode all read current state via qmicli before writing; if observed value already matches the target, the action skips the write and returns succeeded=True. Verify() re-reads to confirm post-condition (FR-32)."
    - "soft_reset.verify() returns VerifyResult.deferred(detail='next_cycle_observation') -- the modem is rebooting; in-line read-back is impossible. Cycle driver and replay harness use the deferred status to defer outcome judgment to next cycle."
    - "fix_autosuspend uses Path.write_text('on') against `<sysfs_root>/bus/usb/devices/<usb_path>/power/control` -- no qmicli, no subprocess. ActionContext.sysfs_root defaults to /sys (production); tests pass tmp_path. Cross-platform tests (work on Windows dev hosts)."
    - "Typed boundary preserved: actions/* call ctx.qmi.<method>(...) only; never reach into qmi._runner. The SP-04 grep `! grep -E 'ctx\\.qmi\\._runner|qmi_wrapper\\._runner' src/spark_modem/actions/` is clean."
    - "All errors are data: every action returns ActionResult; failure_reason carries canonical strings ('serving_system:proxy_died', 'no_carrier:425/03', 'sysfs_write_error:13', etc.). Actions never raise."
    - "Test plumbing centralised: tests/unit/actions/_helpers.py owns ActionContext + RecordingEventLogger + canned CompletedProcess builders; per-action test files stay focused on argv-shape and outcome assertions."
    - "ActionContext frozen + Protocol seams (ClockProto, EventLogWriterProto): actions never mutate context; tests pass FakeClock + RecordingEventLogger that satisfy the Protocols without monkey-patching."

key-files:
  created:
    - src/spark_modem/actions/__init__.py
    - src/spark_modem/actions/result.py
    - src/spark_modem/actions/context.py
    - src/spark_modem/actions/dispatcher.py
    - src/spark_modem/actions/verify.py
    - src/spark_modem/actions/set_apn.py
    - src/spark_modem/actions/fix_raw_ip.py
    - src/spark_modem/actions/sim_power_on.py
    - src/spark_modem/actions/soft_reset.py
    - src/spark_modem/actions/set_operating_mode.py
    - src/spark_modem/actions/fix_autosuspend.py
    - tests/unit/actions/__init__.py
    - tests/unit/actions/_helpers.py
    - tests/unit/actions/test_dispatcher.py
    - tests/unit/actions/test_dry_run.py
    - tests/unit/actions/test_verify.py
    - tests/unit/actions/test_set_apn.py
    - tests/unit/actions/test_fix_raw_ip.py
    - tests/unit/actions/test_sim_power_on.py
    - tests/unit/actions/test_soft_reset.py
    - tests/unit/actions/test_set_operating_mode.py
    - tests/unit/actions/test_fix_autosuspend.py
  modified:
    - src/spark_modem/wire/carriers.py  # +CarrierTable.lookup(mcc, mnc) method (FR-30)
    - src/spark_modem/wire/enums.py     # +ActionKind.SET_OPERATING_MODE, +ActionKind.FIX_AUTOSUSPEND (Rule 3 deviation)

key-decisions:
  - "ActionKind enum extended with SET_OPERATING_MODE and FIX_AUTOSUSPEND (Rule 3 deviation, blocking issue). The Phase 1 enum shipped only seven members (SET_APN/FIX_RAW_IP/SIM_POWER_ON/SOFT_RESET/MODEM_RESET/USB_RESET/DRIVER_RESET); the dispatcher's six-entry registry needed two more cheap-action kinds. Adding the variants is forward-compatible (StrEnum), and the policy engine's decision_table.py was unaffected because no existing decision-table row referenced these new kinds."
  - "CarrierTable.lookup iterates self.carriers (each CarrierEntry carries its own mcc/mnc per Phase 1 schema) rather than the plan's example which assumed a per-table mcc field. The plan's acceptance criterion is shape-agnostic ('returns the matching entry'); the implementation matches `entry.mcc == mcc and entry.mnc == mnc` for every carrier in the list. Comparison is StrictStr equality, so '01' != '1' by design."
  - "The plan-text deliberate duplicate-SET_APN bug in the FIRST `_REGISTRY` definition was removed before initial commit -- the test `test_registered_kinds_has_exactly_six_cheap_actions` asserts the precise frozenset of six kinds, which would fail on a duplicate-induced silent-overwrite. Acceptance criterion `len(registered_kinds()) == 6` enforced inside the test suite AND the plan's static `python -c` smoke check."
  - "Soft-reset uses --dms-set-operating-mode=reset (the qmicli single-pass-reset alias) instead of a dedicated reset opcode. On Sierra EM7421 firmware these are equivalent; the policy engine treats SOFT_RESET as the cheap reset rung and reserves MODEM_RESET (Phase 4) for the destructive ladder."
  - "verify_operating_mode_equals lowercases expected_mode before comparison because parse_get_operating_mode lowercases the parsed mode value. Caller-side _TARGET_MODE = 'online' is already lowercase; the lower() call is defensive against a future caller passing 'ONLINE'."
  - "verify_sim_state_not_power_down passes on any non-'power_down' card_state (including transient 'detected' / 'init' / 'ready') rather than requiring '== ready'. Rationale: uim_sim_power_on may be followed by transient intermediate states before reaching ready; the action succeeded as long as the card is no longer parked in power_down. Strict-equality checks would produce false-failed verifies during normal SIM-app boot."
  - "fix_autosuspend uses Path.write_text/read_text rather than os.write/os.read. No subprocess (SP-04 clean), no FakeRunner involvement, fully cross-platform (tmp_path tests work on Windows). Production target /sys writes are routine OSError on permission-denied; OSError.errno is captured into failure_reason."
  - "Per-action test files use a private `_helpers.py` module (RecordingEventLogger + make_ctx + ok/fail builders) so each test file stays under ~120 LOC and focuses on argv-shape + outcome assertions. _helpers itself is mypy --strict + ruff clean."

patterns-established:
  - "Action-module shape: each action exposes `async def execute(who: WhoModem, ctx: ActionContext) -> ActionResult` and `async def verify(who: WhoModem, ctx: ActionContext) -> VerifyResult`. The dispatcher imports them by name into _REGISTRY -- no Protocol or registration decorator; the import-time mapping IS the contract."
  - "Action-time `start = ctx.clock.monotonic()` -> early-return helpers `_ok(who, ctx, start)` and `_fail(who, ctx, start, reason)` that compute duration_seconds at construction time. Keeps every code path symmetric without per-branch duration arithmetic."
  - "Frozen dataclass copy via `result.with_verify(verify)` -- ActionResult is frozen+slots so the dispatcher composes execute() output + verify() output by allocating a new dataclass rather than mutating. Mirrors the BaseWire frozen-pydantic pattern."
  - "Negative-test `# NOT registering` in FakeRunner setup: when a test asserts an action SKIPS a qmicli call, leave the argv unregistered -- FakeRunner raises KeyError on unregistered argv, so any leak surfaces immediately. The corollary `assert not any(...)` over runner.calls confirms zero matching argvs even in the negative path."

requirements-completed:
  - FR-22  # Cheap actions ship behind a single dispatcher entry point (execute_and_verify)
  - FR-28  # --dry-run gate honored at dispatch time; ActionResult.dry_run=True with no side effects
  - FR-28.1  # Per-modem dry-run wiring shape ready (gate is at the dispatcher; consumer plan 02-09 supplies the bool|list[str] config layer)
  - FR-30  # APN selection via CarrierTable.lookup(mcc, mnc) backed by Phase 1 YAML loader
  - FR-31  # Profile #1 written ONLY when desired APN differs from current (set_apn read-then-write); also applies to set_operating_mode and fix_raw_ip read-then-write
  - FR-32  # Post-write APN verification via verify_apn_equals (re-reads serving system + profile-1)
  - FR-33  # Carrier-table additions are a YAML edit; no code release required
  - FR-40  # Dispatcher emits ActionPlanned + ActionExecuted/ActionFailed events for every dispatch
  - NFR-42  # Carrier-table lookup is O(N) over self.carriers; new MCC/MNC entries are pure data

# Metrics
metrics:
  duration: "12m 30s"
  tasks_completed: 2
  files_created: 22
  files_modified: 2
  tests_added: 48
  test_pass_rate: "100% (48/48 actions tests; 512 passed, 44 skipped POSIX-only across full suite)"
  completed: 2026-05-06
---

# Phase 2 Plan 06: actions/ cheap action set + dispatcher Summary

Lands the actions/ package: dispatcher + six cheap-action modules
(set_apn / fix_raw_ip / sim_power_on / soft_reset / set_operating_mode /
fix_autosuspend), each exposing execute() and verify() pairs. The
dispatcher's `execute_and_verify(kind, who, ctx, *, dry_run=False)` is
the SINGLE entry point used by both the cycle driver (plan 02-10) and
the CLI (plan 02-09); Phase 4 destructive actions plug into the same
`_REGISTRY` as a pure-data extension.

## The six actions

| Action | execute() summary | verify() summary | Idempotent? |
|---|---|---|---|
| `set_apn` | nas-get-serving-system → CarrierTable.lookup(mcc,mnc) → wds-get-profile-settings → if mismatch: wds-modify-profile(apn=,ip-family=4) | re-runs serving + lookup + verify_apn_equals | yes (FR-31) |
| `fix_raw_ip` | wds-get-current-settings → if raw_ip != 'Y': qmi.wds_set_ip_family(4) | verify_raw_ip_y (re-reads current settings) | yes |
| `sim_power_on` | qmi.uim_sim_power_on(slot=1) | verify_sim_state_not_power_down | (call is naturally idempotent) |
| `soft_reset` | qmi.dms_set_operating_mode("reset") | **VerifyResult.deferred()** -- next-cycle observation | n/a (modem is rebooting) |
| `set_operating_mode` | dms-get-operating-mode → if mode != 'online': dms-set-operating-mode("online") | verify_operating_mode_equals('online') | yes (FR-31) |
| `fix_autosuspend` | `Path.write_text('on')` to `<sysfs_root>/bus/usb/devices/<usb_path>/power/control` | reads back; ok if 'on' | yes |

## Dispatcher registry

`actions.dispatcher._REGISTRY` is exactly six entries: SET_APN,
FIX_RAW_IP, SIM_POWER_ON, SOFT_RESET, SET_OPERATING_MODE,
FIX_AUTOSUSPEND. Destructive kinds (MODEM_RESET, USB_RESET,
DRIVER_RESET) are NOT registered -- Phase 4 lands them by appending
entries with no dispatcher code change. Static check:

```bash
python -c "from spark_modem.actions.dispatcher import registered_kinds; assert len(registered_kinds()) == 6"
```

## The deliberate duplicate-key bug catch

The plan text contained a deliberate duplicate `_REGISTRY` definition
where the first dict had two `ActionKind.SET_APN` entries (silently
overwriting one of the other six action kinds). Fix: removed the first
dict and kept only the second (correct) six-entry definition. The test
`test_registered_kinds_has_exactly_six_cheap_actions` asserts the
precise frozenset of six expected kinds; an executor that left the
duplicate in place would fail this test (one of the expected six would
be missing) AND the static smoke check `assert len(registered_kinds())
== 6` (which would still equal 6 by silent overwrite -- but the
frozenset comparison catches it because one of the OTHER five expected
kinds would be absent).

## CarrierTable.lookup added (FR-30)

Method on the existing Phase 1 `wire/carriers.py` `CarrierTable` type;
iterates `self.carriers` (each `CarrierEntry` carries its own mcc/mnc
per the docs/SCHEMA.md §8 schema; the plan's example assumed a
per-table mcc field, but the actual schema is per-entry, so the
implementation iterates) and returns the first entry matching both
`mcc` and `mnc`, or `None`. Comparison is StrictStr equality.

## Phase 4 hooks

When destructive actions land in Phase 4:

1. Add the new ActionKind enum members (already shipped in this plan:
   SET_OPERATING_MODE, FIX_AUTOSUSPEND; Phase 4 reuses MODEM_RESET,
   USB_RESET, DRIVER_RESET which already exist in the enum).
2. Create `src/spark_modem/actions/{modem_reset,usb_reset,driver_reset}.py`
   each exposing `execute()` + `verify()`.
3. Append three lines to `_REGISTRY` in `dispatcher.py`.

The signal-quality gate (Phase 4) layers on top via the policy engine
BEFORE the dispatcher is called -- the dispatcher itself stays
action-kind-agnostic, so no gate logic touches any action module.
Cheap actions still run during `rf_blocked` (CLAUDE.md invariant 10);
the gate is destructive-only.

## Recoverability

Actions whose verify-failed status is **inline-recoverable** (the next
cycle re-observes the issue and the policy engine re-tries):

- `set_apn` (verify failed → write the APN again next cycle)
- `fix_raw_ip` (verify failed → re-set IP family next cycle)
- `set_operating_mode` (verify failed → re-set mode next cycle)
- `sim_power_on` (verify failed → re-issue power-on next cycle)
- `fix_autosuspend` (verify failed → re-write 'on' next cycle)

Actions whose verify is **deferred** by design:

- `soft_reset` -- modem is rebooting; outcome judgment deferred to
  next-cycle observation. The cycle driver and replay harness consume
  `VerifyResult.status == "deferred"` as "no judgment yet"; the next
  cycle's snapshot determines whether the reset succeeded.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Add SET_OPERATING_MODE + FIX_AUTOSUSPEND to ActionKind enum**

- **Found during:** Task 1 (dispatcher implementation)
- **Issue:** The Phase 1 `wire/enums.ActionKind` enum shipped only seven
  members (SET_APN, FIX_RAW_IP, SIM_POWER_ON, SOFT_RESET, MODEM_RESET,
  USB_RESET, DRIVER_RESET). The dispatcher registry needs two more
  cheap-action kinds (SET_OPERATING_MODE, FIX_AUTOSUSPEND) referenced
  by the plan's interfaces, registry, and tests.
- **Fix:** Added two enum members (`SET_OPERATING_MODE = "set_operating_mode"`
  and `FIX_AUTOSUSPEND = "fix_autosuspend"`) to `ActionKind` with
  updated docstring distinguishing Phase 2 cheap from Phase 4
  destructive. Forward-compatible: the StrEnum is closed but adding
  variants is safe; pre-existing decision_table.py rows did not
  reference either new kind, so the policy engine's decision-table
  coverage is unchanged.
- **Files modified:** `src/spark_modem/wire/enums.py`
- **Commit:** c608775

**2. [Rule 3 - Blocking] Adapt CarrierTable.lookup to per-entry schema**

- **Found during:** Task 1 (carrier-table loader update)
- **Issue:** The plan's example `lookup` method body assumed
  `CarrierTable.mcc` (a per-table MCC) but the actual Phase 1 schema is
  `carriers: list[CarrierEntry]` where each entry carries its own
  mcc/mnc.
- **Fix:** Implemented `lookup(mcc, mnc)` to iterate `self.carriers`
  and return the first matching entry. The plan's acceptance criterion
  was shape-agnostic ('returns the matching entry'). All carrier-table
  fixtures and existing wire tests continue to pass (12 carriers
  fixture round-trips cleanly).
- **Files modified:** `src/spark_modem/wire/carriers.py`
- **Commit:** c608775

**3. [Rule 1 - Bug] Remove deliberate duplicate-SET_APN _REGISTRY definition**

- **Found during:** Task 1 (per plan instruction)
- **Issue:** Plan text contained a deliberate duplicate-key bug --
  first `_REGISTRY` definition had two `SET_APN` entries (silent
  overwrite). The plan instructed the executor to delete the first
  dict and keep only the second.
- **Fix:** Implemented dispatcher.py with a single, correct six-entry
  `_REGISTRY` definition. The test
  `test_registered_kinds_has_exactly_six_cheap_actions` asserts the
  precise frozenset of expected kinds and would fail on the bug.
- **Files modified:** `src/spark_modem/actions/dispatcher.py` (initial impl)
- **Commit:** c608775

**4. [Rule 1 - Bug] Tweak fix_raw_ip docstring to drop literal "_runner"**

- **Found during:** Task 2 acceptance verification
- **Issue:** The fix_raw_ip module docstring said "actions/ never
  reaches into ``ctx.qmi._runner``" -- a documentation note, but the
  plan's acceptance grep `! grep -E "ctx\.qmi\._runner|qmi_wrapper\._runner"`
  matched the docstring text. False positive.
- **Fix:** Rephrased the docstring to "the wrapper's private runner
  attribute" -- preserves intent, satisfies the grep.
- **Files modified:** `src/spark_modem/actions/fix_raw_ip.py`
- **Commit:** ec44d1d

### Authentication Gates

None. This plan is a pure-Python module addition with no external
auth surface.

## Self-Check: PASSED

**Files created (22) — all present:**

- src/spark_modem/actions/__init__.py
- src/spark_modem/actions/result.py
- src/spark_modem/actions/context.py
- src/spark_modem/actions/dispatcher.py
- src/spark_modem/actions/verify.py
- src/spark_modem/actions/set_apn.py
- src/spark_modem/actions/fix_raw_ip.py
- src/spark_modem/actions/sim_power_on.py
- src/spark_modem/actions/soft_reset.py
- src/spark_modem/actions/set_operating_mode.py
- src/spark_modem/actions/fix_autosuspend.py
- tests/unit/actions/__init__.py
- tests/unit/actions/_helpers.py
- tests/unit/actions/test_dispatcher.py
- tests/unit/actions/test_dry_run.py
- tests/unit/actions/test_verify.py
- tests/unit/actions/test_set_apn.py
- tests/unit/actions/test_fix_raw_ip.py
- tests/unit/actions/test_sim_power_on.py
- tests/unit/actions/test_soft_reset.py
- tests/unit/actions/test_set_operating_mode.py
- tests/unit/actions/test_fix_autosuspend.py

**Files modified (2):**
- src/spark_modem/wire/carriers.py (CarrierTable.lookup added)
- src/spark_modem/wire/enums.py (ActionKind.SET_OPERATING_MODE + FIX_AUTOSUSPEND added)

**Commits exist:**
- c608775 — feat(02-06): add actions/ scaffold + dispatcher + 6 cheap action modules
- ec44d1d — test(02-06): cover all six cheap actions with execute+verify pairs

**Verification gates pass:**
- mypy --strict (23 source files): clean
- ruff check + ruff format --check (22 files): clean
- pytest tests/unit/actions/: 48 passed
- bash scripts/lint_no_subprocess.sh (SP-04): clean
- Full regression: 512 passed, 44 skipped POSIX-only on Windows dev host
- `python -c "from spark_modem.actions.dispatcher import registered_kinds; assert len(registered_kinds()) == 6"`: passes
