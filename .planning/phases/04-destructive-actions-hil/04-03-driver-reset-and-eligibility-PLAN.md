---
plan: 04-03
title: driver_reset action + global eligibility predicate + thermal suppression + cooldown
phase: 04
wave: 3
depends_on: [04-02]
files_modified:
  - src/spark_modem/actions/driver_reset.py
  - src/spark_modem/actions/dispatcher.py
  - src/spark_modem/policy/engine.py
  - src/spark_modem/config/settings.py
  - tests/unit/actions/test_driver_reset.py
  - tests/unit/actions/test_dispatcher.py
  - tests/unit/policy/test_engine_driver_reset.py
  - tests/unit/config/test_settings.py
autonomous: true
requirements: [FR-24, FR-27]
must_haves:
  truths:
    - "ActionKind.DRIVER_RESET is registered in actions.dispatcher._REGISTRY"
    - "actions/driver_reset.py issues two subproc.run calls in sequence: ['modprobe', '-r', 'qmi_wwan'] then ['modprobe', 'qmi_wwan']"
    - "driver_reset stderr classifier: 'in use' (case-insensitive) on unload returns failure_reason='driver_reset:module_in_use' WITHOUT attempting load (PITFALLS §1.1)"
    - "Other unload non-zero exits proceed to load (idempotency: A-05); load failure returns failure_reason='driver_reset:load_exit_<code>'"
    - "_global_driver_reset_eligible is wired from placeholder to real predicate with 4 gates evaluated in order: thermal_suppression → cooldown → 75% denominator → actionable-signal"
    - "Settings gains 4 new RELOAD_DATA fields: multi_modem_threshold_fraction (0.75), expected_modem_count (4), global_driver_reset_backoff_seconds (3600), modprobe_timeout_seconds (30)"
    - "PolicyContext.expected_modem_count is populated FROM Settings.expected_modem_count (cycle driver responsibility documented; in-plan tests construct PolicyContext explicitly)"
    - "First-cycle path: globals_state.last_driver_reset_monotonic is None → cooldown gate short-circuits to allow eligibility (does NOT crash on None comparison)"
  artifacts:
    - path: "src/spark_modem/actions/driver_reset.py"
      provides: "DRIVER_RESET execute/verify (modprobe -r/+ qmi_wwan)"
      contains: "ActionKind.DRIVER_RESET"
    - path: "src/spark_modem/policy/engine.py"
      provides: "Real _global_driver_reset_eligible predicate replacing the Phase 2 placeholder"
      contains: "multi_modem_threshold_fraction"
    - path: "src/spark_modem/config/settings.py"
      provides: "4 new RELOAD_DATA-tagged fields for driver_reset eligibility"
      contains: "global_driver_reset_backoff_seconds"
    - path: "tests/unit/policy/test_engine_driver_reset.py"
      provides: "12 boundary-condition tests for the eligibility predicate"
  key_links:
    - from: "src/spark_modem/actions/driver_reset.py"
      to: "src/spark_modem/subproc/runner.py:run"
      via: "module import (PATTERNS correction #1: ActionContext does NOT have a runner field)"
      pattern: "from spark_modem.subproc.runner import run"
    - from: "src/spark_modem/policy/engine.py:_global_driver_reset_eligible"
      to: "ctx.config.{multi_modem_threshold_fraction, expected_modem_count, global_driver_reset_backoff_seconds, signal_*_floor_*}"
      via: "Settings consultation"
      pattern: "ctx\\.config\\.multi_modem_threshold_fraction"
---

<objective>
Land the third destructive action (`driver_reset`) AND wire the engine's
`_global_driver_reset_eligible` predicate from its Phase 2 placeholder
(`return False`) to the real 4-gate logic per CONTEXT C-01..C-05. Per A-03,
driver_reset is two `subproc.run` calls (`["modprobe", "-r", "qmi_wwan"]` then
`["modprobe", "qmi_wwan"]`); the sequence flows through the existing
`subproc/runner` module — SP-04 lint is satisfied because the import is from
the sanctioned subproc package.

**Important corrections from PATTERNS.md:**
1. `ActionContext.runner` does NOT exist (correction #1). `driver_reset.py`
   must import the runner module directly: `from spark_modem.subproc.runner
   import run as subproc_run`.
2. The signal-floor Settings fields (`signal_rsrp_floor_dbm`,
   `signal_rsrq_floor_db`, `signal_snr_floor_db`) are NOT added in this plan —
   they ship in Plan 04-04 (B-03 signal-gate Settings migration). For the
   actionable-signal check in `_global_driver_reset_eligible` here, the
   predicate body reads `ctx.config.signal_*_floor_*` — Plan 04-03 ships the
   predicate WITH these reads, but Plan 04-04 owns adding the fields. Wave 1
   parallel plans (04-03 + 04-04) means the order doesn't matter inside the
   wave; the EXECUTOR sees both diffs by the time the wave merges. To keep
   THIS plan independently testable, hard-code -110 / -15 / 0.0 inline as a
   defensive read (`getattr(ctx.config, "signal_rsrp_floor_dbm", -110)`) so
   tests pass even if Plan 04-04 hasn't landed yet. Plan 04-04 then removes
   the `getattr` defensive reads.

Purpose:
- Land driver_reset (FR-24 / FR-27) — the global destructive action.
- Make `_global_driver_reset_eligible` actually work (Phase 2 short-circuit
  was wired but predicate always returned False).
- Add the 4 Settings fields the eligibility predicate needs.
- Wire the modprobe stderr classifier (PITFALLS §1.1 pattern).

Output:
- New: `src/spark_modem/actions/driver_reset.py`.
- Extended: `actions/dispatcher.py` (+1 row), `policy/engine.py`
  (`_global_driver_reset_eligible` predicate body rewritten),
  `config/settings.py` (+4 RELOAD_DATA fields).
- Tests: 12 new tests in `tests/unit/policy/test_engine_driver_reset.py`,
  ≥6 in `tests/unit/actions/test_driver_reset.py`, settings tests for the new fields.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/04-destructive-actions-hil/04-CONTEXT.md
@.planning/phases/04-destructive-actions-hil/04-PATTERNS.md
@docs/RECOVERY_SPEC.md
@CLAUDE.md

<interfaces>
<!-- Verbatim from PATTERNS.md / source — executor uses these directly. -->

From src/spark_modem/subproc/runner.py:108-138 (the runner — `run` is a module-level async function, NOT an instance method):
```python
async def run(
    argv: list[str],
    *,
    timeout_s: float,
    stdin: bytes | None = None,
    env: dict[str, str] | None = None,
) -> CompletedProcess:
    """Run argv as a subprocess and return a CompletedProcess.

    Per SP-02 'all errors are data', this function returns CompletedProcess
    for any terminating outcome. ..."""
```

From src/spark_modem/policy/engine.py:280-294 (the placeholder body to REPLACE):
```python
def _global_driver_reset_eligible(
    diag: Diag,
    prior_states: dict[str, ModemState],
    globals_state: GlobalsState,
    ctx: PolicyContext,
) -> bool:
    """RECOVERY_SPEC §6.4 -- Phase 2 placeholder; always False.

    Phase 4 wires the real ≥75 % qmi_channel_hung + actionable-signal
    check end-to-end with the driver_reset action. ..."""
    del diag, prior_states, globals_state, ctx
    return False
```

From src/spark_modem/policy/engine.py:76-106 (the call-site short-circuit — DO NOT modify; just read for context):
```python
if _global_driver_reset_eligible(diag, prior_states, globals_state, ctx):
    plans.append(_plan_driver_reset())
    new_globals = globals_state.model_copy(
        update={
            "driver_reset_count": globals_state.driver_reset_count + 1,
            "last_driver_reset_monotonic": ctx.clock.monotonic(),
            "last_driver_reset_iso": ctx.clock.wall_clock_iso(),
        }
    )
    ...
```

From src/spark_modem/config/settings.py:70-89 (existing RELOAD_DATA pattern to mirror — append after `healthy_streak_decay_k`):
```python
backoff_seconds: int = Field(
    default=300,
    ge=1,
    json_schema_extra=RELOAD_DATA,
    description="FR-25 same-action backoff (default 300s).",
)
ladder_min_interval_seconds: int = Field(
    default=90,
    ge=1,
    json_schema_extra=RELOAD_DATA,
    description="FR-25.1 cross-action ladder backoff (default 90s).",
)
healthy_streak_decay_k: int = Field(
    default=10,
    ge=1,
    json_schema_extra=RELOAD_DATA,
    description="ADR-0006 K consecutive Healthy cycles before counters decay.",
)
```

From src/spark_modem/policy/context.py:42-46 (PolicyContext — already has expected_modem_count):
```python
clock: ClockProto
config: Settings
maintenance_active: bool = False
expected_modem_count: int = 4
```

From src/spark_modem/wire/globals.py (GlobalsState — already has the fields driver_reset reads/writes):
```python
class GlobalsState(BaseWire):
    driver_reset_count: int = 0
    last_driver_reset_monotonic: float | None = None
    last_driver_reset_iso: str | None = None
    ...
```

From src/spark_modem/wire/diag.py (the per-modem snapshot the predicate consumes):
```python
class ModemSnapshot(BaseWire):
    issues: list[Issue]
    signal: SignalSnapshot   # rsrp_dbm, rsrq_db, snr_db (all Optional)
    ...

class Issue(BaseWire):
    category: IssueCategory
    detail: IssueDetail
    ...
```

Driver reset modprobe stderr patterns (verified via WebFetch from kmod tools/modprobe.c):
- "in use" (line 876) — module currently in use; cannot remove
- "not found" / "module not in kernel" (line 731 / 816) — already removed; treat as success for idempotency
- exit code 0 — success in either case
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add 4 Settings fields + extend Settings unit tests</name>
  <files>
    src/spark_modem/config/settings.py,
    tests/unit/config/test_settings.py
  </files>
  <read_first>
    - src/spark_modem/config/settings.py:60-128 (existing RELOAD_DATA blocks — extend after `healthy_streak_decay_k`)
    - src/spark_modem/config/reload_marker.py (the RELOAD_DATA / RELOAD_RESTART markers)
    - tests/unit/config/test_settings.py (existing settings test patterns — extend with new fields)
    - .planning/phases/04-destructive-actions-hil/04-PATTERNS.md § "src/spark_modem/config/settings.py"
  </read_first>
  <behavior>
    - test_default_multi_modem_threshold_fraction_is_0_75: `Settings()` defaults `.multi_modem_threshold_fraction == 0.75`.
    - test_multi_modem_threshold_fraction_must_be_0_to_1: `Settings(multi_modem_threshold_fraction=1.5)` raises pydantic ValidationError.
    - test_default_expected_modem_count_is_4: `Settings()` defaults `.expected_modem_count == 4`.
    - test_expected_modem_count_must_be_positive: `Settings(expected_modem_count=0)` raises ValidationError.
    - test_default_global_driver_reset_backoff_seconds_is_3600: `Settings()` defaults `.global_driver_reset_backoff_seconds == 3600`.
    - test_default_modprobe_timeout_seconds_is_30: `Settings()` defaults `.modprobe_timeout_seconds == 30`.
    - test_phase4_driver_reset_fields_are_reload_data: assert each of the 4 new fields has `json_schema_extra` containing the RELOAD_DATA marker (use `Settings.model_fields["multi_modem_threshold_fraction"].json_schema_extra` and check the dict content against `reload_marker.RELOAD_DATA`).
    - test_phase4_driver_reset_fields_yaml_roundtrip: build a YAML-shaped dict including the 4 fields with non-default values; `Settings.from_yaml_layer(yaml_dict)` returns Settings with those values applied.
  </behavior>
  <action>
Append a new "## --- Phase 4 destructive actions (RELOAD_DATA) ---" block to `src/spark_modem/config/settings.py` AFTER `healthy_streak_decay_k` (around line 89) and BEFORE the "## --- Webhook (RELOAD_DATA) ---" block. Add EXACTLY these 4 fields with the EXACT defaults / validators / descriptions:

```python
# --- Phase 4 destructive actions: driver_reset eligibility (RELOAD_DATA) ---

multi_modem_threshold_fraction: float = Field(
    default=0.75,
    ge=0.0,
    le=1.0,
    json_schema_extra=RELOAD_DATA,
    description="FR-24 driver_reset eligibility fraction (default 0.75; per C-01).",
)
expected_modem_count: int = Field(
    default=4,
    ge=1,
    le=99,
    json_schema_extra=RELOAD_DATA,
    description="FR-24 driver_reset denominator (total fleet size; per C-01).",
)
global_driver_reset_backoff_seconds: int = Field(
    default=3600,
    ge=1,
    json_schema_extra=RELOAD_DATA,
    description="RECOVERY_SPEC §6.4 driver_reset cooldown (default 3600s; per C-05).",
)
modprobe_timeout_seconds: int = Field(
    default=30,
    ge=1,
    json_schema_extra=RELOAD_DATA,
    description="A-03 driver_reset modprobe -r/+ qmi_wwan timeout (per RESEARCH A6).",
)
```

Note: per RESEARCH plan-slicing notes, `expected_modem_count` is tagged
RELOAD_DATA here (NOT RELOAD_RESTART). Rationale: yes, it's a topology field,
but treating it as RELOAD_DATA lets ops adjust during scale-up without restart;
restart is the correct response only when Settings drift could lead to a
deeply-incoherent runtime — for `expected_modem_count` an in-cycle re-read is
benign (the cycle driver re-reads `Settings.expected_modem_count` per cycle to
populate `PolicyContext.expected_modem_count` per the cycle-driver contract).

The signal-floor fields (`signal_rsrp_floor_dbm`, `signal_rsrq_floor_db`,
`signal_snr_floor_db`) and ladder-ceiling fields (`max_soft`, `max_modem`,
`max_usb`) are NOT added by this plan — they're owned by Plan 04-04. Do NOT
add them here even if you "see them missing" in the Phase 4 module list.

Extend `tests/unit/config/test_settings.py` with the 8 tests from `<behavior>`.
Use the existing settings-test fixture/scaffolding.

Per CLAUDE.md: pure-data extension; mypy --strict must remain green; pydantic
v2 frozen=True is preserved.
  </action>
  <verify>
    <automated>cd /s/spark/modem-watchdog &amp;&amp; .venv/bin/pytest tests/unit/config/test_settings.py -x &amp;&amp; .venv/bin/mypy --strict src/spark_modem/config/settings.py &amp;&amp; .venv/bin/ruff check src/spark_modem/config/settings.py tests/unit/config/test_settings.py &amp;&amp; .venv/bin/ruff format --check src/spark_modem/config/settings.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -F 'multi_modem_threshold_fraction: float' src/spark_modem/config/settings.py` returns ≥1 match
    - `grep -F 'expected_modem_count: int' src/spark_modem/config/settings.py` returns ≥1 match
    - `grep -F 'global_driver_reset_backoff_seconds: int' src/spark_modem/config/settings.py` returns ≥1 match
    - `grep -F 'modprobe_timeout_seconds: int' src/spark_modem/config/settings.py` returns ≥1 match
    - `grep -F 'default=0.75' src/spark_modem/config/settings.py` returns ≥1 match (multi_modem_threshold_fraction)
    - `grep -F 'default=3600' src/spark_modem/config/settings.py` returns ≥1 match (global_driver_reset_backoff_seconds)
    - `grep -F 'json_schema_extra=RELOAD_DATA' src/spark_modem/config/settings.py | wc -l` is ≥4 more than baseline (4 new RELOAD_DATA fields)
    - `grep -F 'signal_rsrp_floor_dbm' src/spark_modem/config/settings.py` returns 0 matches (Plan 04-04's territory; NOT in this plan)
    - `grep -F 'max_soft' src/spark_modem/config/settings.py` returns 0 matches (Plan 04-04's territory)
    - `pytest tests/unit/config/test_settings.py -x` exits 0 with ≥8 new tests collected
    - `mypy --strict src/spark_modem/config/settings.py` exits 0
    - `ruff check src/spark_modem/config/settings.py tests/unit/config/test_settings.py` exits 0
  </acceptance_criteria>
  <done>
    4 RELOAD_DATA Settings fields added; pydantic ValidationError on out-of-range; 8 new tests pass.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Create actions/driver_reset.py + register in dispatcher + driver_reset unit tests</name>
  <files>
    src/spark_modem/actions/driver_reset.py,
    src/spark_modem/actions/dispatcher.py,
    tests/unit/actions/test_driver_reset.py,
    tests/unit/actions/test_dispatcher.py
  </files>
  <read_first>
    - src/spark_modem/actions/soft_reset.py (the deferred-verify analog)
    - src/spark_modem/subproc/runner.py:108-196 (`run` signature + CompletedProcess fields)
    - src/spark_modem/qmi/wrapper.py:238-254 (state-changing subproc.run call shape)
    - src/spark_modem/actions/dispatcher.py (current state — already has MODEM_RESET from Plan 04-01 and USB_RESET from Plan 04-02)
    - src/spark_modem/wire/diag.py (`WhoModem` shape — used as a synthetic host placeholder per PATTERNS Cross-Cutting #10)
    - .planning/phases/04-destructive-actions-hil/04-PATTERNS.md § "src/spark_modem/actions/driver_reset.py" + § "Cross-Cutting Conventions" #9 (15 s timeout — but note Settings ships 30 s default)
    - .planning/research/PITFALLS.md §1.1 (qmi-proxy crash → driver_reset recovery)
  </read_first>
  <behavior>
    - test_driver_reset_invokes_modprobe_remove_then_load: FakeRunner registered for `["modprobe", "-r", "qmi_wwan"]` → ok exit 0 + empty stderr; `["modprobe", "qmi_wwan"]` → ok exit 0; call execute(synthetic_who, ctx); assert succeeded == True, kind == ActionKind.DRIVER_RESET; assert FakeRunner.calls captured both argvs IN ORDER.
    - test_driver_reset_returns_module_in_use_on_unload_in_use: FakeRunner returns CompletedProcess(exit_code=1, stderr=b"modprobe: ERROR: Module qmi_wwan is in use.\n") for the unload; assert succeeded == False, failure_reason == "driver_reset:module_in_use"; assert FakeRunner.calls did NOT include the load argv (the load attempt is skipped per PITFALLS §1.1 / A-03).
    - test_driver_reset_proceeds_to_load_on_unload_module_not_found: FakeRunner returns exit_code=1 stderr=b"modprobe: FATAL: Module qmi_wwan not found.\n" for unload (already removed — idempotent path); load returns ok; assert succeeded == True (overall succeeded; idempotent re-run found module already removed).
    - test_driver_reset_returns_load_failure_on_load_exit_nonzero: unload ok (exit 0); load returns CompletedProcess(exit_code=2, stderr=b"some error"); assert succeeded == False, failure_reason == "driver_reset:load_exit_2".
    - test_driver_reset_uses_modprobe_timeout_from_settings: monkey-patch `subproc.runner.run` to record kwargs; assert each invocation uses `timeout_s=settings.modprobe_timeout_seconds` (default 30.0 — convert int to float at the call site).
    - test_driver_reset_verify_is_deferred: call verify(); assert VerifyResult.kind == "deferred" with detail == "next_cycle_observation".
    - test_driver_reset_uses_synthetic_whomodem_for_host_action: dispatcher invokes execute with `WhoModem(usb_path="host", cdc_wdm=None)`; assert ActionResult.who has usb_path == "host" (per PATTERNS Cross-Cutting #10 recommendation).

    Dispatcher contract update:
    - test_registered_kinds_has_exactly_nine_kinds (replaces _eight_kinds from Plan 04-02): expected length 9 (6 cheap + MODEM_RESET + USB_RESET + DRIVER_RESET).
    - test_all_destructive_actions_registered_phase4_03 (replaces partial test): assert all 3 destructive kinds registered True.
  </behavior>
  <action>
**Step A — Create `src/spark_modem/actions/driver_reset.py`:**

```python
"""driver_reset -- modprobe -r qmi_wwan && modprobe qmi_wwan. Verify is DEFERRED.

Per A-03: two `subproc.run` calls in sequence. Idempotent at invocation level
— second run finds module already removed/loaded.

Per PATTERNS correction #1: ActionContext does NOT have a runner field.
This module imports `run` from `spark_modem.subproc.runner` directly.

Per PATTERNS Cross-Cutting #10: dispatcher signature requires WhoModem, but
driver_reset is host-scoped — engine constructs a synthetic
`WhoModem(usb_path="host", cdc_wdm=None)` for the registry call. The action's
body uses `who` only for the ActionResult.who field.

Stderr classifier (PITFALLS §1.1, kmod tools/modprobe.c lines 731/816/876):
  - 'in use' → module_in_use; do NOT attempt load (would just re-fire).
  - 'not found' / 'module not in kernel' → already-removed; PROCEED to load.
  - other unload non-zero exit codes → also PROCEED to load (idempotency: A-05).
  - load non-zero → failure_reason='driver_reset:load_exit_<code>'.

Needs CAP_SYS_MODULE (preallocated by Plan 03-08 U-01).
"""

from __future__ import annotations

from spark_modem.actions.context import ActionContext
from spark_modem.actions.result import ActionResult, VerifyResult
from spark_modem.subproc.runner import run as subproc_run
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind


_UNLOAD_ARGV = ["modprobe", "-r", "qmi_wwan"]
_LOAD_ARGV = ["modprobe", "qmi_wwan"]


async def execute(who: WhoModem, ctx: ActionContext) -> ActionResult:
    start = ctx.clock.monotonic()
    timeout_s = float(ctx.config.modprobe_timeout_seconds)

    cp_unload = await subproc_run(_UNLOAD_ARGV, timeout_s=timeout_s)
    if cp_unload.exit_code != 0:
        stderr_lc = cp_unload.stderr.lower()
        if b"in use" in stderr_lc:
            return ActionResult(
                kind=ActionKind.DRIVER_RESET,
                who=who,
                succeeded=False,
                duration_seconds=ctx.clock.monotonic() - start,
                failure_reason="driver_reset:module_in_use",
                dry_run=False,
            )
        # 'not found' / 'module not in kernel' / other non-zero -> proceed to load
        # for idempotency (A-05). Falling through.

    cp_load = await subproc_run(_LOAD_ARGV, timeout_s=timeout_s)
    if cp_load.exit_code != 0:
        return ActionResult(
            kind=ActionKind.DRIVER_RESET,
            who=who,
            succeeded=False,
            duration_seconds=ctx.clock.monotonic() - start,
            failure_reason=f"driver_reset:load_exit_{cp_load.exit_code}",
            dry_run=False,
        )

    return ActionResult(
        kind=ActionKind.DRIVER_RESET,
        who=who,
        succeeded=True,
        duration_seconds=ctx.clock.monotonic() - start,
        failure_reason=None,
        dry_run=False,
    )


async def verify(who: WhoModem, ctx: ActionContext) -> VerifyResult:
    """Deferred -- next-cycle observation surfaces the actual outcome."""
    del who, ctx
    return VerifyResult.deferred(detail="next_cycle_observation")
```

**Step B — Extend `actions/dispatcher.py`:**
- Add `driver_reset` to the import list (alphabetical: between `fix_raw_ip` and `modem_reset`):
  ```python
  from spark_modem.actions import (
      driver_reset,
      fix_autosuspend,
      fix_raw_ip,
      modem_reset,
      set_apn,
      set_operating_mode,
      sim_power_on,
      soft_reset,
      usb_reset,
  )
  ```
- Append ONE row to `_REGISTRY` (after USB_RESET):
  ```python
  ActionKind.DRIVER_RESET: (driver_reset.execute, driver_reset.verify),
  ```

**Step C — Tests (`tests/unit/actions/test_driver_reset.py`):**
- Use `make_ctx` from `_helpers.py`; the FakeRunner-based ActionContext satisfies the test boundary; the action consumes `ctx.config.modprobe_timeout_seconds` (which `make_settings()` returns the default 30 for now — Plan 04-03's Task 1 added that field).
- Implement the 7 tests from `<behavior>`.
- Synthetic WhoModem for host-scoped action: `WhoModem(usb_path="host", cdc_wdm=None)` (cdc_wdm field accepts None per existing wire schema; verify by reading `src/spark_modem/wire/diag.py:WhoModem`).
- For the timeout-monkeypatch test, monkeypatch `spark_modem.actions.driver_reset.subproc_run` (the renamed import) — this avoids touching the `subproc.runner` module globally.

**Step D — Update `tests/unit/actions/test_dispatcher.py`:**
- Rename `test_registered_kinds_has_exactly_eight_kinds` → `test_registered_kinds_has_exactly_nine_kinds` (count delta from Plan 04-02).
- Update expected frozenset to 9 entries.
- Update `test_destructive_actions_partially_registered_phase4_02` → `test_all_destructive_actions_registered_phase4_03`: assert MODEM_RESET, USB_RESET, DRIVER_RESET all `is_registered() is True`.

Per CLAUDE.md: SP-04 lint passes — `from spark_modem.subproc.runner import run` is the SANCTIONED subprocess path (Phase 1's single wrapper module). No new subprocess code outside `subproc/`.
  </action>
  <verify>
    <automated>cd /s/spark/modem-watchdog &amp;&amp; .venv/bin/pytest tests/unit/actions/test_driver_reset.py tests/unit/actions/test_dispatcher.py -x &amp;&amp; .venv/bin/mypy --strict src/spark_modem/actions/driver_reset.py src/spark_modem/actions/dispatcher.py &amp;&amp; .venv/bin/ruff check src/spark_modem/actions/driver_reset.py tests/unit/actions/test_driver_reset.py &amp;&amp; .venv/bin/ruff format --check src/spark_modem/actions/driver_reset.py &amp;&amp; bash scripts/lint_no_subprocess.sh</automated>
  </verify>
  <acceptance_criteria>
    - File exists: `src/spark_modem/actions/driver_reset.py`
    - `grep -F 'from spark_modem.subproc.runner import run as subproc_run' src/spark_modem/actions/driver_reset.py` returns ≥1 match
    - `grep -F '"modprobe", "-r", "qmi_wwan"' src/spark_modem/actions/driver_reset.py` returns ≥1 match (list-form argv per CLAUDE.md / FR-64)
    - `grep -F '"modprobe", "qmi_wwan"' src/spark_modem/actions/driver_reset.py` returns ≥1 match
    - `grep -F '"driver_reset:module_in_use"' src/spark_modem/actions/driver_reset.py` returns ≥1 match
    - `grep -F '"driver_reset:load_exit_' src/spark_modem/actions/driver_reset.py` returns ≥1 match
    - `grep -F 'ctx.config.modprobe_timeout_seconds' src/spark_modem/actions/driver_reset.py` returns ≥1 match
    - `grep -F 'ActionKind.DRIVER_RESET: (driver_reset.execute' src/spark_modem/actions/dispatcher.py` returns ≥1 match
    - `pytest tests/unit/actions/test_driver_reset.py -x` exits 0 with ≥7 tests collected
    - `pytest tests/unit/actions/test_dispatcher.py::test_registered_kinds_has_exactly_nine_kinds -x` exits 0
    - `mypy --strict src/spark_modem/actions/driver_reset.py` exits 0
    - `ruff check src/spark_modem/actions/driver_reset.py tests/unit/actions/test_driver_reset.py` exits 0
    - `bash scripts/lint_no_subprocess.sh` exits 0 (subproc.runner is the sanctioned path)
    - No bare `subprocess.run`, `os.system`, or `create_subprocess_exec` in `src/spark_modem/actions/driver_reset.py` (`grep -E 'subprocess\.|os\.system|create_subprocess_exec' src/spark_modem/actions/driver_reset.py` returns 0)
  </acceptance_criteria>
  <note>
    The dispatcher kind-count assertion test is renamed in each successive plan
    (04-01 → 7, 04-02 → 8, 04-03 → 9) to track the registry growth across waves.
    This rename is intentional; verification of plan 04-NN runs only against the
    state of the registry at that plan's commit time. Wave ordering (04-01 →
    04-02 → 04-03 sequential) guarantees the assertion is correct at execution.
  </note>
  <done>
    driver_reset.py executes the modprobe -r/+ qmi_wwan sequence via subproc.runner; stderr classifier handles in_use / not_found / load_failure; dispatcher contract = 9 kinds; SP-04 green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Wire _global_driver_reset_eligible to real predicate (4 gates) + 12 boundary unit tests</name>
  <files>
    src/spark_modem/policy/engine.py,
    tests/unit/policy/test_engine_driver_reset.py
  </files>
  <read_first>
    - src/spark_modem/policy/engine.py (entire file — the placeholder at 280-294, the call-site at 76-106, the imports)
    - src/spark_modem/policy/context.py (PolicyContext.expected_modem_count is already there at line 45)
    - src/spark_modem/wire/diag.py (Diag, ModemSnapshot, Issue, SignalSnapshot)
    - src/spark_modem/wire/globals.py (GlobalsState.last_driver_reset_monotonic — Optional[float])
    - src/spark_modem/wire/enums.py (IssueDetail.THERMAL_WARN, IssueDetail.THERMAL_CRITICAL, IssueDetail.QMI_CHANNEL_HUNG)
    - .planning/phases/04-destructive-actions-hil/04-PATTERNS.md § "src/spark_modem/policy/engine.py:_global_driver_reset_eligible" (the body to implement)
    - docs/RECOVERY_SPEC.md §6.4 (the gate verbatim)
    - .planning/research/PITFALLS.md §17.4 (thermal suppression rationale)
  </read_first>
  <behavior>
    Predicate body — 4 gates, evaluated IN ORDER (any False short-circuits):
    1. test_driver_reset_suppressed_by_thermal_warn: build a Diag with `host_issues=[Issue(category=..., detail=IssueDetail.THERMAL_WARN, ...)]` and 4 modems all qmi_channel_hung; assert eligible == False.
    2. test_driver_reset_suppressed_by_thermal_critical: same with THERMAL_CRITICAL; eligible == False.
    3. test_driver_reset_first_fire_no_npe: build globals_state with `last_driver_reset_monotonic=None`; 4/4 hung modems with good signal; assert eligible == True (None must short-circuit cooldown branch — DO NOT raise NPE on None comparison).
    4. test_driver_reset_cooldown_blocks_within_3600s: globals_state.last_driver_reset_monotonic=clock.monotonic()-1800.0 (30 minutes ago); 4/4 hung; assert eligible == False (within 3600s cooldown).
    5. test_driver_reset_cooldown_allows_after_3600s: globals_state.last_driver_reset_monotonic=clock.monotonic()-3700.0; 4/4 hung; assert eligible == True.
    6. test_driver_reset_eligible_at_3_of_4_hung_with_good_signal: 3 hung modems with rsrp=-95,rsrq=-10,snr=5; 1 healthy; assert eligible == True (3/4 = 0.75 ≥ threshold).
    7. test_driver_reset_NOT_eligible_at_2_of_4_hung: 2 hung, 2 healthy; assert eligible == False (2/4 = 0.5 < 0.75).
    8. test_driver_reset_denominator_is_expected_count_NOT_enumerated: 3 hung, 0 healthy, 1 missing-from-Diag (only 3 modems present); ctx.expected_modem_count=4; assert eligible == True (3/4 = 0.75 — denominator is expected, not enumerated; per C-01 "Conservative deviation").
    9. test_driver_reset_denominator_with_zao_active: 3 hung, 1 Zao-active modem (NO QMI_CHANNEL_HUNG issue — Zao manages it); assert eligible == True (Zao-active counted as 'not-hung' per C-01; 3 hung / 4 expected = 0.75).
    10. test_driver_reset_NOT_eligible_when_all_hung_modems_rf_blocked: 4/4 hung, ALL with rsrp=-120,rsrq=-20,snr=-5 (below floors); assert eligible == False (no actionable signal).
    11. test_driver_reset_eligible_when_one_hung_modem_has_actionable_signal: 4/4 hung, 3 with terrible signal, 1 with rsrp=-100,rsrq=-10,snr=5; assert eligible == True (per FR-24: "at least one of them has actionable signal").
    12. test_driver_reset_handles_missing_signal_readings_as_no_actionable_signal: 4/4 hung; signal readings all None (sig.rsrp_dbm=None, sig.rsrq_db=None, sig.snr_db=None); assert eligible == False (None readings cannot prove actionable signal — conservative).
  </behavior>
  <action>
**Replace the body of `_global_driver_reset_eligible` in `src/spark_modem/policy/engine.py`:**

Find the existing placeholder (around line 280-294) and replace it with:

```python
def _global_driver_reset_eligible(
    diag: Diag,
    prior_states: dict[str, ModemState],
    globals_state: GlobalsState,
    ctx: PolicyContext,
) -> bool:
    """RECOVERY_SPEC §6.4 -- Phase 4 real predicate.

    Four gates, evaluated in order; any False short-circuits:
      1. Thermal suppression (C-03 / PITFALLS §17.4): host_issues includes
         THERMAL_WARN or THERMAL_CRITICAL -> not eligible.
      2. Cooldown (C-05 / RECOVERY_SPEC §6.4): elapsed since last fire <
         global_driver_reset_backoff_seconds -> not eligible. None last-fire
         short-circuits to allow.
      3. ≥75% denominator (C-01): hung_count / expected_modem_count >=
         multi_modem_threshold_fraction. Denominator is the EXPECTED total
         (Settings.expected_modem_count, threaded into PolicyContext by the
         cycle driver), NOT the enumerated count -- Zao-active and missing
         modems are counted as 'not-hung' per the user's conservative deviation.
      4. Actionable signal (FR-24): at least one hung modem has rsrp >= floor
         AND rsrq >= floor AND snr >= floor (None readings count as 'not above
         floor' -- conservative).

    PROXY_DIED issues (C-02): the per-modem decision-table row still routes
    proxy_died → DRIVER_RESET, but this eligibility predicate gates ALL
    driver_reset paths on the standard 75% threshold (no per-modem bypass --
    user deviation from PITFALLS §1.1).
    """
    # Gate 1: thermal suppression
    host_details = {issue.detail for issue in diag.host_issues}
    if (
        IssueDetail.THERMAL_WARN in host_details
        or IssueDetail.THERMAL_CRITICAL in host_details
    ):
        return False

    # Gate 2: cooldown
    if globals_state.last_driver_reset_monotonic is not None:
        elapsed = ctx.clock.monotonic() - globals_state.last_driver_reset_monotonic
        if elapsed < float(ctx.config.global_driver_reset_backoff_seconds):
            return False

    # Gate 3: ≥75% denominator. Denominator is expected, not enumerated.
    expected = ctx.expected_modem_count
    if expected <= 0:
        return False
    hung_count = sum(
        1
        for snap in diag.per_modem.values()
        if any(
            i.category == IssueCategory.QMI and i.detail == IssueDetail.QMI_CHANNEL_HUNG
            for i in snap.issues
        )
    )
    if (hung_count / expected) < ctx.config.multi_modem_threshold_fraction:
        return False

    # Gate 4: actionable signal -- at least one hung modem has signal above all 3 floors.
    # Plan 04-04 will land Settings.signal_*_floor_* fields. Until then, use
    # getattr defensive reads with RECOVERY_SPEC §6.1 verbatim defaults so this
    # plan tests independently of Plan 04-04's merge order.
    rsrp_floor = getattr(ctx.config, "signal_rsrp_floor_dbm", -110)
    rsrq_floor = getattr(ctx.config, "signal_rsrq_floor_db", -15.0)
    snr_floor = getattr(ctx.config, "signal_snr_floor_db", 0.0)
    for snap in diag.per_modem.values():
        if not any(
            i.category == IssueCategory.QMI and i.detail == IssueDetail.QMI_CHANNEL_HUNG
            for i in snap.issues
        ):
            continue
        sig = snap.signal
        if (
            sig.rsrp_dbm is not None
            and sig.rsrp_dbm >= rsrp_floor
            and sig.rsrq_db is not None
            and sig.rsrq_db >= rsrq_floor
            and sig.snr_db is not None
            and sig.snr_db >= snr_floor
        ):
            return True
    return False
```

Add the missing imports at the top of `policy/engine.py` if they aren't present:
- `from spark_modem.wire.enums import ActionKind, IssueCategory, IssueDetail` — `IssueCategory` and `IssueDetail` may need to be added to the existing `wire.enums` import line (verify with the executor; the file already imports `ActionKind`).

**Tests (`tests/unit/policy/test_engine_driver_reset.py` — NEW FILE):**

Create the file with imports and a per-test `_make_ctx` / `_make_diag` builder, then implement the 12 tests from `<behavior>`. Use `FakeClock` from `tests/fakes/clock.py` for the cooldown timing tests; advance the FakeClock between the globals_state's `last_driver_reset_monotonic` timestamp and the eligibility evaluation.

Helper signature:
```python
def _make_ctx(*, expected_modem_count: int = 4, config_overrides: dict | None = None) -> PolicyContext:
    settings_kwargs = {
        "multi_modem_threshold_fraction": 0.75,
        "expected_modem_count": expected_modem_count,
        "global_driver_reset_backoff_seconds": 3600,
        "modprobe_timeout_seconds": 30,
    }
    if config_overrides:
        settings_kwargs.update(config_overrides)
    settings = Settings(**settings_kwargs)
    return PolicyContext(
        clock=FakeClock(),
        config=settings,
        maintenance_active=False,
        expected_modem_count=expected_modem_count,
    )

def _make_hung_modem(usb_path: str, *, rsrp=-95, rsrq=-10, snr=5) -> tuple[str, ModemSnapshot]:
    snap = ModemSnapshot(
        ...,  # build per existing test patterns
        issues=[Issue(category=IssueCategory.QMI, detail=IssueDetail.QMI_CHANNEL_HUNG, ...)],
        signal=SignalSnapshot(rsrp_dbm=rsrp, rsrq_db=rsrq, snr_db=snr, ...),
    )
    return usb_path, snap
```

Read existing `tests/unit/policy/test_engine.py` to find the canonical builder
shapes for ModemSnapshot / Issue / SignalSnapshot — reuse those helper
patterns (do NOT introduce a new pydantic model construction style).

Per CLAUDE.md: pure-policy preserved (engine still imports nothing from
subprocess/asyncio/os). The predicate is a pure function. The cycle driver
populates `PolicyContext.expected_modem_count` from
`Settings.expected_modem_count` — that wiring change lives in cycle_driver
and is OUT OF SCOPE for this plan; tests construct PolicyContext explicitly
with the expected count.
  </action>
  <verify>
    <automated>cd /s/spark/modem-watchdog &amp;&amp; .venv/bin/pytest tests/unit/policy/test_engine_driver_reset.py -x &amp;&amp; .venv/bin/pytest tests/unit/policy/test_engine.py -x &amp;&amp; .venv/bin/mypy --strict src/spark_modem/policy/engine.py &amp;&amp; .venv/bin/ruff check src/spark_modem/policy/engine.py tests/unit/policy/test_engine_driver_reset.py &amp;&amp; bash scripts/lint_no_subprocess.sh</automated>
  </verify>
  <acceptance_criteria>
    - File exists: `tests/unit/policy/test_engine_driver_reset.py` with ≥12 test functions
    - `grep -F 'IssueDetail.THERMAL_WARN' src/spark_modem/policy/engine.py` returns ≥1 match
    - `grep -F 'ctx.config.global_driver_reset_backoff_seconds' src/spark_modem/policy/engine.py` returns ≥1 match
    - `grep -F 'ctx.config.multi_modem_threshold_fraction' src/spark_modem/policy/engine.py` returns ≥1 match
    - `grep -F 'ctx.expected_modem_count' src/spark_modem/policy/engine.py` returns ≥1 match (uses PolicyContext field, not Settings directly)
    - `grep -F 'last_driver_reset_monotonic is not None' src/spark_modem/policy/engine.py` returns ≥1 match (None short-circuit)
    - `grep -F 'getattr(ctx.config, "signal_rsrp_floor_dbm"' src/spark_modem/policy/engine.py` returns ≥1 match (defensive read until Plan 04-04 lands)
    - `grep -F 'return False' src/spark_modem/policy/engine.py | wc -l` is ≥4 (4 short-circuit paths in the predicate)
    - `pytest tests/unit/policy/test_engine_driver_reset.py -x` exits 0 with all 12 tests passing
    - `pytest tests/unit/policy/test_engine.py -x` exits 0 (no Phase 2 regression)
    - `mypy --strict src/spark_modem/policy/engine.py` exits 0
    - `bash scripts/lint_no_subprocess.sh` exits 0 (engine still pure — no new subprocess imports)
    - Full unit suite: `pytest -m "unit and not linux_only and not hil" -x` exits 0
  </acceptance_criteria>
  <done>
    `_global_driver_reset_eligible` returns True only when all 4 gates pass; 12 boundary tests cover the predicate; first-fire (None last-driver-reset) does not crash; pure-engine discipline preserved.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| daemon → kernel module space (modprobe) | `modprobe -r/+ qmi_wwan` requires CAP_SYS_MODULE (preallocated by Plan 03-08 U-01); kernel module loader is trusted; modprobe's argv is the trust boundary |
| daemon process → subproc/runner subprocess wrapper | List-form argv ONLY (FR-64 / SP-03); `["modprobe", "-r", "qmi_wwan"]` is a literal — no external input |
| Phase 4 HIL bench Jetson → real qmi_wwan kernel module | driver_reset disconnects the entire bonded uplink for 5-30 s; HIL workflow must serialise (concurrency `cancel-in-progress: false` per Plan 04-06) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-03-01 | T (Tampering) | modprobe argv injection | mitigate | argv is a static module-level list (`_UNLOAD_ARGV = ["modprobe", "-r", "qmi_wwan"]`); no string formatting against external input; `subproc.runner.run` enforces list-form by signature (`argv: list[str]`); SP-04 lint enforces no `subprocess` import outside `subproc/` |
| T-04-03-02 | E (Elevation) | unauthorized driver_reset invocation | mitigate | CLI path goes through `cli/reset.py` which acquires the same per-modem flock the daemon does (ADR-0012, Plan 02-09 wiring). Engine path gated by 4-stage eligibility predicate (thermal / cooldown / 75% / actionable-signal); cannot fire from a single-modem fault. systemd unit U-01 confines CAP_SYS_MODULE to the daemon process only |
| T-04-03-03 | D (Denial of service) | driver_reset thrash (cooldown bypass) | mitigate | Cooldown gate enforces 3600 s minimum interval via `globals_state.last_driver_reset_monotonic`; the field is bumped atomically in the same cycle the action plans (engine.py:76-106 — already wired in Phase 2). 12 boundary tests verify cooldown enforcement |
| T-04-03-04 | D (Denial of service) | thermal cascade | mitigate | Thermal-suppression gate (C-03 / PITFALLS §17.4): when host_issues include THERMAL_WARN/CRITICAL, driver_reset is skipped because the root cause is thermal — driver_reset wouldn't fix it and would just unbind 4 modems on a hot box |
| T-04-03-05 | I (Information disclosure) | modprobe stderr leak | accept | `cp_unload.stderr` is examined for "in use" substring only; the bytes are NOT logged or surfaced (failure_reason is the canonical `module_in_use` / `load_exit_<code>` string). Operator stderr inspection requires support-bundle which already has PII-redaction (Plan 02-09) |
| T-04-03-06 | R (Repudiation) | driver_reset event audit trail | mitigate | `globals_state.driver_reset_count` increments and `last_driver_reset_monotonic` / `last_driver_reset_iso` are bumped atomically (engine.py:76-106 already wired). Dispatcher emits ActionPlanned + ActionExecuted/ActionFailed events for every driver_reset |
| T-04-03-07 | T (Tampering) | malicious thermal_critical injection bypass | accept | Thermal issues come from kmsg classifier (Plan 03-05) which reads /dev/kmsg only — no external input path. Anyone with kernel-write privs to /dev/kmsg already owns the box. Out of scope for v2.0 |
</threat_model>

<verification>
- All Plan 04-03 task `<verify>` commands pass.
- `pytest -m "unit and not linux_only and not hil" -x` exits 0 (full unit suite).
- `pytest tests/unit/policy/test_engine_driver_reset.py tests/unit/actions/test_driver_reset.py tests/unit/config/test_settings.py -ra` exits 0 with ≥27 new tests collected (12 + 7 + 8).
- `mypy --strict src/spark_modem/` exits 0.
- `ruff check src/spark_modem/ tests/` exits 0.
- `bash scripts/lint_no_subprocess.sh` exits 0 (driver_reset goes through subproc.runner; no SP-04 violation).
- `grep -E 'subprocess\.|os\.system|create_subprocess_exec' src/spark_modem/actions/driver_reset.py` returns 0 matches.
- Manual sanity: construct a Diag with 3/4 hung modems + healthy signal + None last-driver-reset; `_global_driver_reset_eligible(diag, ..., ctx)` returns True.
</verification>

<success_criteria>
- `actions/driver_reset.py` exists; uses `subproc.runner.run` (NOT bare subprocess); two argvs in sequence; stderr classifier handles "in use" / "not found" / "load failure".
- Dispatcher contract test asserts 9 registered ActionKinds (6 cheap + MODEM_RESET + USB_RESET + DRIVER_RESET).
- `Settings` gains exactly 4 RELOAD_DATA fields: `multi_modem_threshold_fraction` (0.75), `expected_modem_count` (4), `global_driver_reset_backoff_seconds` (3600), `modprobe_timeout_seconds` (30).
- `_global_driver_reset_eligible` is a pure function with 4 gates (thermal → cooldown → 75% → actionable-signal), evaluated in that order; first-fire (None last_driver_reset) does NOT NPE.
- The predicate body uses `getattr(ctx.config, "signal_*_floor_*", default)` defensively until Plan 04-04 lands the Settings fields; Plan 04-04 will remove the getattr.
- 12+7+8 = 27 new unit tests across 3 files, all green.
- CLAUDE.md invariants honored: list-form argv (FR-64); pure-engine policy (no I/O imports); SP-04 lint passes; per-modem flock unchanged; atomic state writes unchanged (this plan doesn't touch state-store).
- Full Phase 1+2+3 regression suite stays green.
</success_criteria>

<output>
After completion, create `.planning/phases/04-destructive-actions-hil/04-03-SUMMARY.md`
documenting: files created (driver_reset.py, test_engine_driver_reset.py),
files extended (dispatcher, engine, settings, test_dispatcher, test_settings),
the 4 new Settings fields with their defaults, the predicate's 4-gate
ordering, the count delta on the dispatcher contract test (8 → 9), the
PATTERNS correction #1 application (no `ctx.runner` — direct module import),
the defensive `getattr` reads for signal-floor fields (Plan 04-04 cleans up).
Note that the cycle driver wiring `PolicyContext.expected_modem_count =
Settings.expected_modem_count` is OUT OF SCOPE here; tests construct
PolicyContext explicitly. That wiring lands in Plan 04-04 or as a follow-up.
</output>
