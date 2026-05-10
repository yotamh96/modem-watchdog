---
plan: 04-04
title: policy/ladder.py + per-action timestamps + signal-gate Settings migration
phase: 04
wave: 4
depends_on: [04-03]
files_modified:
  - src/spark_modem/policy/ladder.py
  - src/spark_modem/policy/engine.py
  - src/spark_modem/policy/gates.py
  - src/spark_modem/policy/transitions.py
  - src/spark_modem/wire/state.py
  - src/spark_modem/config/settings.py
  - tests/unit/policy/test_ladder.py
  - tests/unit/policy/test_gates.py
  - tests/unit/policy/test_transitions.py
  - tests/unit/policy/test_engine.py
  - tests/unit/wire/test_state.py
  - tests/unit/config/test_settings.py
autonomous: true
requirements: [FR-23]
must_haves:
  truths:
    - "policy/ladder.py exists as a pure-function module with select_rung(category, counters, config) -> ActionKind | Literal['skip:exhausted']"
    - "Engine wires ladder.select_rung() into _apply_gates_to_action for REGISTRATION and (DATAPATH, SESSION_DISCONNECTED) base actions"
    - "ModemState gains last_action_monotonic_by_kind: dict[ActionKind, float] = Field(default_factory=dict)"
    - "Phase 2 ModemState files (without the new field) load cleanly via the empty-dict default"
    - "gate_same_action_backoff keys on state.last_action_monotonic_by_kind[action] (per-kind, NOT the legacy global timestamp)"
    - "gate_ladder_backoff takes MAX over destructive-kind timestamps in last_action_monotonic_by_kind"
    - "Settings gains 6 new RELOAD_DATA fields: max_soft (3), max_modem (2), max_usb (1), signal_rsrp_floor_dbm (-110), signal_rsrq_floor_db (-15.0), signal_snr_floor_db (0.0)"
    - "policy/transitions.py:is_signal_below_gate signature becomes (snap, config); reads thresholds from Settings; module-level _RSRP_FLOOR_DBM/_RSRQ_FLOOR_DB/_SNR_FLOOR_DB Final constants are deleted"
    - "Engine's per-modem path bumps both last_action_monotonic AND last_action_monotonic_by_kind[counter_bump] in the SAME atomic ModemState.model_copy"
    - "Plan 04-03's getattr defensive reads in _global_driver_reset_eligible are removed (Settings now has the fields); direct ctx.config.signal_*_floor_* reads"
  artifacts:
    - path: "src/spark_modem/policy/ladder.py"
      provides: "Pure-function select_rung() — REGISTRATION ladder progression based on per-action counters"
      contains: "def select_rung"
    - path: "src/spark_modem/wire/state.py"
      provides: "ModemState.last_action_monotonic_by_kind field"
      contains: "last_action_monotonic_by_kind"
    - path: "src/spark_modem/config/settings.py"
      provides: "6 new RELOAD_DATA fields (3 ladder ceilings + 3 signal floors)"
      contains: "max_soft"
    - path: "tests/unit/policy/test_ladder.py"
      provides: "RECOVERY_SPEC §10.2 progression scenarios + ceiling-overflow tests"
  key_links:
    - from: "src/spark_modem/policy/engine.py:_apply_gates_to_action"
      to: "src/spark_modem/policy/ladder.py:select_rung"
      via: "import + invocation"
      pattern: "from spark_modem.policy.ladder import select_rung"
    - from: "src/spark_modem/policy/gates.py:gate_same_action_backoff"
      to: "ModemState.last_action_monotonic_by_kind"
      via: "dict.get keyed on action"
      pattern: "state\\.last_action_monotonic_by_kind\\.get\\(action\\)"
    - from: "src/spark_modem/policy/transitions.py:is_signal_below_gate"
      to: "ctx.config.signal_*_floor_*"
      via: "Settings field reads"
      pattern: "config\\.signal_rsrp_floor_dbm"
---

<objective>
Make the destructive-action machinery operationally correct by:

1. Adding `policy/ladder.py` — a pure-function module that picks the actual
   ladder rung (SOFT_RESET → MODEM_RESET → USB_RESET → exhausted) based on
   per-action counters, given a base action from the decision table. CONTEXT
   B-01 keeps the decision-table flat; the ladder owns rung selection.

2. Adding `ModemState.last_action_monotonic_by_kind` so the same-action and
   ladder backoff gates can discriminate per-kind (CONTEXT B-02). Phase 2's
   single `last_action_monotonic` field is preserved as the wire shape (no
   destructive removal — Phase 2 state files load cleanly).

3. Migrating signal-gate thresholds from module-level `Final` constants in
   `policy/transitions.py` to RELOAD_DATA-tagged Settings fields (CONTEXT
   B-03). SIGHUP retunes the floors; per-cohort tuning in Phase 5 is
   YAML-only.

4. Adding 3 ladder-ceiling Settings (`max_soft=3`, `max_modem=2`, `max_usb=1`)
   per RECOVERY_SPEC §4.1.

5. Removing the defensive `getattr` reads Plan 04-03 left in
   `_global_driver_reset_eligible` (Settings now has the signal-floor fields
   directly).

This plan depends on Plans 04-01 / 04-02 / 04-03 having registered MODEM_RESET
/ USB_RESET / DRIVER_RESET in `actions.dispatcher._REGISTRY` and on Plan 04-03
having shipped 4 Settings fields. Wave 4 ordering ensures the destructive
ActionKinds exist when the ladder progression tests cite them (Wave 1 → 04-01
modem_reset; Wave 2 → 04-02 usb_reset; Wave 3 → 04-03 driver_reset; Wave 4 →
04-04 ladder integration).

Output:
- New: `src/spark_modem/policy/ladder.py`, `tests/unit/policy/test_ladder.py`.
- Extended: `policy/engine.py` (ladder integration in `_apply_gates_to_action`,
  per-kind timestamp bump, removal of getattr defensive reads),
  `policy/gates.py` (re-key both backoff gates on `last_action_monotonic_by_kind`),
  `policy/transitions.py` (signal-gate Settings migration + signature change),
  `wire/state.py` (+1 field), `config/settings.py` (+6 fields).
- Test updates: `test_gates.py` (existing tests reshape `state.last_action_monotonic_by_kind` instead of `last_action_monotonic`), `test_transitions.py` (signature change), `test_engine.py` (per-kind bump assertion), `test_state.py` (new field round-trip), `test_settings.py` (6 new fields).
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
@.planning/phases/04-destructive-actions-hil/04-01-modem-reset-action-PLAN.md
@.planning/phases/04-destructive-actions-hil/04-02-usb-reset-action-PLAN.md
@.planning/phases/04-destructive-actions-hil/04-03-driver-reset-and-eligibility-PLAN.md
@docs/RECOVERY_SPEC.md
@CLAUDE.md

<interfaces>
<!-- Verbatim from PATTERNS.md / source — executor uses these directly. -->

From src/spark_modem/policy/decision_table.py:91-99 (lookup_action shape — analog for ladder.select_rung):
```python
def lookup_action(
    category: IssueCategory, detail: IssueDetail
) -> ActionKind | str | None:
    """Return ActionKind, skip-reason string, or None for unrecognised pairs."""
    return _DECISION_TABLE.get((category, detail))
```

From src/spark_modem/policy/transitions.py:23-42 (current signal-gate to migrate):
```python
_RSRP_FLOOR_DBM: Final[int] = -110
_RSRQ_FLOOR_DB: Final[float] = -15.0
_SNR_FLOOR_DB: Final[float] = 0.0


def is_signal_below_gate(snap: ModemSnapshot) -> bool:
    sig = snap.signal
    if sig.rsrp_dbm is not None and sig.rsrp_dbm < _RSRP_FLOOR_DBM:
        return True
    if sig.rsrq_db is not None and sig.rsrq_db < _RSRQ_FLOOR_DB:
        return True
    return sig.snr_db is not None and sig.snr_db < _SNR_FLOOR_DB
```
Single call-site at policy/transitions.py:65 inside `transition()`:
```python
rf_blocked = is_signal_below_gate(snap)
```

From src/spark_modem/policy/gates.py:72-117 (the two backoff gates to re-key):
```python
def gate_same_action_backoff(state: ModemState, action: ActionKind, clock: ClockProto, config: Settings) -> bool:
    del action  # reserved for Phase 4 per-action timestamp split
    if state.last_action_monotonic is None:
        return False
    elapsed = clock.monotonic() - state.last_action_monotonic
    return elapsed < float(config.backoff_seconds)


def gate_ladder_backoff(state: ModemState, action: ActionKind, clock: ClockProto, config: Settings) -> bool:
    if action not in _DESTRUCTIVE_KINDS:
        return False
    if state.last_action_monotonic is None:
        return False
    elapsed = clock.monotonic() - state.last_action_monotonic
    return elapsed < float(config.ladder_min_interval_seconds)
```

From src/spark_modem/wire/state.py (the field to add — preserve `last_action_monotonic`):
```python
class ModemState(BaseWire):
    schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, ge=1)
    state: StateLiteral
    ...
    counters: dict[ActionKind, int] = Field(default_factory=dict)
    last_action_monotonic: float | None = None
    # NEW (this plan):
    last_action_monotonic_by_kind: dict[ActionKind, float] = Field(default_factory=dict)
```

From src/spark_modem/policy/engine.py:108-184 (the per-modem path that bumps counter_bump — the same atomic copy needs to bump the new dict):
```python
new_state_with_counters = new_state.model_copy(
    update={
        "healthy_streak": new_streak,
        "counters": new_counters,
    }
)
```
After Phase 4: also bump `last_action_monotonic` and `last_action_monotonic_by_kind` when `counter_bump is not None`.

RECOVERY_SPEC §4.1 ladder ceilings:
- MAX_SOFT = 3 (default — `max_soft` Settings field)
- MAX_MODEM = 2 (default — `max_modem` Settings field)
- MAX_USB = 1 (default — `max_usb` Settings field)

RECOVERY_SPEC §10.2 progression scenarios (test fixtures):
- Scenario A: counters={SOFT_RESET: 0} → select_rung returns SOFT_RESET.
- Scenario B: counters={SOFT_RESET: 3} (at ceiling) → select_rung returns MODEM_RESET.
- Scenario C: counters={SOFT_RESET: 3, MODEM_RESET: 2} → select_rung returns USB_RESET.
- Scenario D: counters={SOFT_RESET: 3, MODEM_RESET: 2, USB_RESET: 1} → select_rung returns "skip:exhausted".

Categories where ladder applies (CONTEXT B-01):
- IssueCategory.REGISTRATION (NOT_REGISTERED_SEARCHING / NOT_REGISTERED_IDLE → base SOFT_RESET; ladder owns the rung)
- IssueCategory.DATAPATH with detail SESSION_DISCONNECTED → base MODEM_RESET; ladder picks USB_RESET when MODEM_RESET ceiling exceeded
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add 6 Settings fields (3 ladder ceilings + 3 signal floors); remove Plan 04-03 getattr defensive reads</name>
  <files>
    src/spark_modem/config/settings.py,
    src/spark_modem/policy/engine.py,
    tests/unit/config/test_settings.py
  </files>
  <read_first>
    - src/spark_modem/config/settings.py (the Phase 4 block from Plan 04-03 — append after `modprobe_timeout_seconds`)
    - src/spark_modem/policy/engine.py (the `_global_driver_reset_eligible` body Plan 04-03 wrote; specifically the `getattr(ctx.config, "signal_rsrp_floor_dbm", -110)` defensive reads)
    - .planning/phases/04-destructive-actions-hil/04-03-driver-reset-and-eligibility-PLAN.md (the predicate body)
    - .planning/phases/04-destructive-actions-hil/04-PATTERNS.md § "src/spark_modem/config/settings.py" (the 9 fields total — minus the 4 Plan 04-03 already added = 6 here, but actually 9 - 4 = 5; correction: PATTERNS lists 9 fields under "Phase 4 modification — append 9 new fields" but Plan 04-03 already added 4 (multi_modem_threshold_fraction, expected_modem_count, global_driver_reset_backoff_seconds, modprobe_timeout_seconds is NOT in the PATTERNS 9, so that's a 5th from 04-03's perspective). The 6 fields THIS plan adds are: signal_rsrp_floor_dbm, signal_rsrq_floor_db, signal_snr_floor_db, max_soft, max_modem, max_usb)
  </read_first>
  <behavior>
    - test_default_signal_rsrp_floor_dbm_is_neg_110: `Settings().signal_rsrp_floor_dbm == -110`.
    - test_default_signal_rsrq_floor_db_is_neg_15: `Settings().signal_rsrq_floor_db == -15.0`.
    - test_default_signal_snr_floor_db_is_zero: `Settings().signal_snr_floor_db == 0.0`.
    - test_default_max_soft_is_3: `Settings().max_soft == 3`.
    - test_default_max_modem_is_2: `Settings().max_modem == 2`.
    - test_default_max_usb_is_1: `Settings().max_usb == 1`.
    - test_max_soft_must_be_positive: `Settings(max_soft=0)` raises ValidationError.
    - test_max_modem_must_be_positive: `Settings(max_modem=0)` raises ValidationError.
    - test_max_usb_must_be_positive: `Settings(max_usb=0)` raises ValidationError.
    - test_signal_thresholds_reload_data: each of the 3 signal-floor fields has `json_schema_extra` containing the RELOAD_DATA marker.
    - test_ladder_ceiling_fields_reload_data: each of `max_soft`, `max_modem`, `max_usb` is RELOAD_DATA tagged.
    - test_engine_reads_signal_floors_from_settings_directly: integration test — construct a Diag with 4/4 hung modems, signal at exactly -110/-15/0 (boundary above floor), `_global_driver_reset_eligible` returns True. Then construct Settings with `signal_rsrp_floor_dbm=-100`; same diag now returns False (because -110 < -100). Proves the engine is reading from config, not the deleted module constants.
  </behavior>
  <action>
**Step A — Append 6 fields to `src/spark_modem/config/settings.py`** (after `modprobe_timeout_seconds`, before the `# --- Webhook (RELOAD_DATA) ---` block):

```python
# --- Phase 4 destructive actions: signal floors (RELOAD_DATA) ---

signal_rsrp_floor_dbm: int = Field(
    default=-110,
    json_schema_extra=RELOAD_DATA,
    description="RECOVERY_SPEC §6.1 RSRP floor for rf_blocked (per B-03).",
)
signal_rsrq_floor_db: float = Field(
    default=-15.0,
    json_schema_extra=RELOAD_DATA,
    description="RECOVERY_SPEC §6.1 RSRQ floor for rf_blocked (per B-03).",
)
signal_snr_floor_db: float = Field(
    default=0.0,
    json_schema_extra=RELOAD_DATA,
    description="RECOVERY_SPEC §6.1 SNR floor for rf_blocked (per B-03).",
)

# --- Phase 4 destructive actions: ladder ceilings (RELOAD_DATA) ---

max_soft: int = Field(
    default=3,
    ge=1,
    json_schema_extra=RELOAD_DATA,
    description="RECOVERY_SPEC §4.1 ladder ceiling for SOFT_RESET (per B-01).",
)
max_modem: int = Field(
    default=2,
    ge=1,
    json_schema_extra=RELOAD_DATA,
    description="RECOVERY_SPEC §4.1 ladder ceiling for MODEM_RESET (per B-01).",
)
max_usb: int = Field(
    default=1,
    ge=1,
    json_schema_extra=RELOAD_DATA,
    description="RECOVERY_SPEC §4.1 ladder ceiling for USB_RESET (per B-01).",
)
```

**Step B — Remove the `getattr` defensive reads from `policy/engine.py:_global_driver_reset_eligible`** (Plan 04-03 wrote these because the Settings fields didn't exist yet). Replace the lines:
```python
rsrp_floor = getattr(ctx.config, "signal_rsrp_floor_dbm", -110)
rsrq_floor = getattr(ctx.config, "signal_rsrq_floor_db", -15.0)
snr_floor = getattr(ctx.config, "signal_snr_floor_db", 0.0)
```
With direct attribute reads:
```python
rsrp_floor = ctx.config.signal_rsrp_floor_dbm
rsrq_floor = ctx.config.signal_rsrq_floor_db
snr_floor = ctx.config.signal_snr_floor_db
```

**Step C — Tests in `tests/unit/config/test_settings.py`:**
Implement the 12 tests from `<behavior>`. Use the existing settings-test scaffolding pattern.

The integration test `test_engine_reads_signal_floors_from_settings_directly` actually exercises the engine — place it in `tests/unit/policy/test_engine_driver_reset.py` (created by Plan 04-03) by APPENDING a new test function. This couples the test to the ELIGIBILITY-PREDICATE consuming the Settings fields, which is the actual contract.

Per CLAUDE.md: pydantic-frozen Settings preserved; mypy --strict on `policy/engine.py` must remain green after the getattr removal.
  </action>
  <verify>
    <automated>cd /s/spark/modem-watchdog &amp;&amp; .venv/bin/pytest tests/unit/config/test_settings.py tests/unit/policy/test_engine_driver_reset.py -x &amp;&amp; .venv/bin/mypy --strict src/spark_modem/config/settings.py src/spark_modem/policy/engine.py &amp;&amp; .venv/bin/ruff check src/spark_modem/config/settings.py src/spark_modem/policy/engine.py tests/unit/config/test_settings.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -F 'signal_rsrp_floor_dbm: int' src/spark_modem/config/settings.py` returns ≥1 match
    - `grep -F 'signal_rsrq_floor_db: float' src/spark_modem/config/settings.py` returns ≥1 match
    - `grep -F 'signal_snr_floor_db: float' src/spark_modem/config/settings.py` returns ≥1 match
    - `grep -F 'max_soft: int' src/spark_modem/config/settings.py` returns ≥1 match
    - `grep -F 'max_modem: int' src/spark_modem/config/settings.py` returns ≥1 match
    - `grep -F 'max_usb: int' src/spark_modem/config/settings.py` returns ≥1 match
    - `grep -F 'default=-110' src/spark_modem/config/settings.py` returns ≥1 match
    - `grep -F 'default=-15.0' src/spark_modem/config/settings.py` returns ≥1 match
    - `grep -F 'getattr(ctx.config, "signal_' src/spark_modem/policy/engine.py` returns 0 matches (defensive reads removed)
    - `grep -F 'ctx.config.signal_rsrp_floor_dbm' src/spark_modem/policy/engine.py` returns ≥1 match (direct read)
    - `pytest tests/unit/config/test_settings.py -x` exits 0 with ≥12 new tests for the 6 fields
    - `pytest tests/unit/policy/test_engine_driver_reset.py -x` exits 0 (no regression after getattr removal)
    - `mypy --strict src/spark_modem/config/settings.py src/spark_modem/policy/engine.py` exits 0
  </acceptance_criteria>
  <done>
    6 RELOAD_DATA fields added (3 signal floors + 3 ladder ceilings); getattr defensive reads removed from engine; 12+ new settings tests + 1 integration test pass.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Add ModemState.last_action_monotonic_by_kind + re-key both backoff gates + create policy/ladder.py</name>
  <files>
    src/spark_modem/wire/state.py,
    src/spark_modem/policy/gates.py,
    src/spark_modem/policy/ladder.py,
    tests/unit/wire/test_state.py,
    tests/unit/policy/test_gates.py,
    tests/unit/policy/test_ladder.py
  </files>
  <read_first>
    - src/spark_modem/wire/state.py (entire file — the ModemState definition with schema_version, counters, last_action_monotonic)
    - src/spark_modem/policy/gates.py (entire file — both gate functions to re-key)
    - src/spark_modem/policy/decision_table.py:91-99 (lookup_action shape — analog for ladder.select_rung)
    - src/spark_modem/policy/transitions.py:1-26 (pure-module import discipline — ladder.py mirrors)
    - tests/unit/policy/test_gates.py (existing test scaffolds — must update to populate `last_action_monotonic_by_kind`)
    - tests/unit/wire/test_state.py (existing ModemState round-trip tests — extend with new field)
    - .planning/phases/04-destructive-actions-hil/04-PATTERNS.md § "src/spark_modem/policy/ladder.py" + § "src/spark_modem/policy/gates.py" + § "src/spark_modem/wire/state.py:ModemState"
    - docs/RECOVERY_SPEC.md §10.2 (the 4 progression scenarios)
  </read_first>
  <behavior>
    Wire-state field (test_state.py):
    - test_modem_state_default_last_action_monotonic_by_kind_is_empty_dict: `ModemState(state="unknown", present=True, rf_blocked=False, ...).last_action_monotonic_by_kind == {}`.
    - test_modem_state_loads_phase2_json_without_new_field: pydantic `ModemState.model_validate_json(<phase 2 ModemState JSON without the new field>)` — the json shape is the existing wire/state shape minus the new field; assert it parses cleanly with `last_action_monotonic_by_kind == {}` (default_factory satisfies missing-on-load per pydantic v2).
    - test_modem_state_roundtrips_with_populated_dict: `ModemState(..., last_action_monotonic_by_kind={ActionKind.SOFT_RESET: 1234.5, ActionKind.MODEM_RESET: 1300.0})` round-trips through model_dump_json + model_validate_json.

    Re-keyed gates (test_gates.py — update existing tests):
    - test_gate_same_action_backoff_is_per_kind: state.last_action_monotonic_by_kind={SOFT_RESET: now-100} (within 300s), now-1000 for MODEM_RESET; gate_same_action_backoff(state, action=SOFT_RESET, ...) returns True; gate_same_action_backoff(state, action=MODEM_RESET, ...) returns False (MODEM_RESET's last attempt was >300s ago).
    - test_gate_same_action_backoff_returns_false_when_kind_not_in_dict: state.last_action_monotonic_by_kind={}; assert gate_same_action_backoff returns False for any action (no prior attempt of THIS kind).
    - test_gate_ladder_backoff_takes_max_over_destructive_kinds: state with {SOFT_RESET: now-1000, MODEM_RESET: now-50, USB_RESET: now-1000}; gate_ladder_backoff(state, action=USB_RESET, ...) returns True (MODEM_RESET fired 50s ago, within 90s ladder window — the LAST destructive attempt across ALL destructive kinds gates the ladder).
    - test_gate_ladder_backoff_ignores_cheap_actions: state with {SOFT_RESET: now-50}; gate_ladder_backoff(state, action=SOFT_RESET, ...) — but SOFT_RESET is NOT in _DESTRUCTIVE_KINDS, so it should bypass ladder backoff (return False). Verifies the existing `if action not in _DESTRUCTIVE_KINDS: return False` short-circuit.
    - test_gate_ladder_backoff_returns_false_when_no_destructive_history: state.last_action_monotonic_by_kind={SOFT_RESET: now-1} (only cheap kind); gate_ladder_backoff(state, action=USB_RESET, ...) returns False (no destructive timestamps to MAX over).

    Ladder (test_ladder.py — NEW FILE):
    - test_ladder_picks_soft_reset_when_counter_zero: select_rung(IssueCategory.REGISTRATION, counters={}, config=Settings()) returns ActionKind.SOFT_RESET (RECOVERY_SPEC §10.2 Scenario A).
    - test_ladder_promotes_to_modem_reset_at_max_soft: counters={SOFT_RESET: 3}; select_rung returns MODEM_RESET (Scenario B).
    - test_ladder_promotes_to_usb_reset_at_max_modem: counters={SOFT_RESET: 3, MODEM_RESET: 2}; select_rung returns USB_RESET (Scenario C).
    - test_ladder_returns_skip_exhausted_when_all_rungs_at_ceiling: counters={SOFT_RESET: 3, MODEM_RESET: 2, USB_RESET: 1}; select_rung returns "skip:exhausted" (Scenario D).
    - test_ladder_session_disconnected_starts_at_modem_reset: select_rung(IssueCategory.DATAPATH, counters={}, config=Settings()) returns MODEM_RESET (per the (DATAPATH, SESSION_DISCONNECTED) base from decision_table; ladder starts at the BASE rung, not always at SOFT_RESET).
    - test_ladder_picks_usb_reset_when_modem_reset_ceiling_for_datapath: select_rung(IssueCategory.DATAPATH, counters={MODEM_RESET: 2}, config=Settings()) returns USB_RESET.
    - test_ladder_uses_settings_overrides: select_rung(IssueCategory.REGISTRATION, counters={SOFT_RESET: 5}, config=Settings(max_soft=10)) returns SOFT_RESET (5 < 10 ceiling — config-driven).

    Note for `select_rung` API:
    - Inputs: `(category: IssueCategory, counters: dict[ActionKind, int], config: Settings)` per CONTEXT B-01.
    - For REGISTRATION: ladder is SOFT → MODEM → USB → exhausted.
    - For (DATAPATH, SESSION_DISCONNECTED): ladder STARTS at MODEM (base from decision_table), then USB → exhausted. Engine passes the BASE action so ladder can decide the starting rung.
    - **Refinement:** Add a `base: ActionKind` parameter to make the API self-contained — the engine has already done `lookup_action()` so it knows the base; pass it through. Final signature:
      ```python
      def select_rung(
          base: ActionKind,
          counters: dict[ActionKind, int],
          config: Settings,
      ) -> ActionKind | Literal["skip:exhausted"]
      ```
      The engine call shape becomes: `select_rung(base=lookup_action(...), counters=state.counters, config=ctx.config)`.
  </behavior>
  <action>
**Step A — Extend `src/spark_modem/wire/state.py:ModemState`:**
Add ONE field after `last_action_monotonic`:
```python
# FR-25 / FR-25.1 per-action timestamp split (Phase 4 B-02).
# Phase 2 state files (without this field) load cleanly via default_factory.
# gate_same_action_backoff keys on the executed kind (300s);
# gate_ladder_backoff uses MAX(timestamps over destructive kinds) (90s).
last_action_monotonic_by_kind: dict[ActionKind, float] = Field(default_factory=dict)
```
Do NOT remove `last_action_monotonic` — it's preserved for backwards compat (CONTEXT B-02 "additive contract").

**Step B — Re-key gates in `src/spark_modem/policy/gates.py`:**

Replace `gate_same_action_backoff` body:
```python
def gate_same_action_backoff(
    state: ModemState,
    action: ActionKind,
    clock: ClockProto,
    config: Settings,
) -> bool:
    """FR-25: skip if the SAME ActionKind was attempted within backoff_seconds (300s).

    Phase 4 (B-02): keys on per-kind timestamp dict, NOT the legacy
    last_action_monotonic. The per-kind dict is updated atomically by the
    engine each cycle alongside the counter bump (RECOVERY_SPEC §8).
    """
    ts = state.last_action_monotonic_by_kind.get(action)
    if ts is None:
        return False
    return (clock.monotonic() - ts) < float(config.backoff_seconds)
```

Replace `gate_ladder_backoff` body:
```python
def gate_ladder_backoff(
    state: ModemState,
    action: ActionKind,
    clock: ClockProto,
    config: Settings,
) -> bool:
    """FR-25.1: cross-action ladder backoff (90s default).

    Phase 4 (B-02): MAX over destructive-kind timestamps from the per-kind
    dict. The ladder fires its rung-promotion 90 s after ANY destructive
    rung last fired -- prevents soft → modem → soft → modem ping-pong.

    Cheap actions bypass this gate.
    """
    if action not in _DESTRUCTIVE_KINDS:
        return False
    destructive_ts = [
        state.last_action_monotonic_by_kind[k]
        for k in _DESTRUCTIVE_KINDS
        if k in state.last_action_monotonic_by_kind
    ]
    if not destructive_ts:
        return False
    return (clock.monotonic() - max(destructive_ts)) < float(config.ladder_min_interval_seconds)
```

Note: the legacy `state.last_action_monotonic` is no longer consulted by either
gate. The field remains on the wire shape for back-compat (Phase 2 readers
still see it) but is no longer authoritative for gate evaluation. Engine bumps
both fields atomically — see Task 3.

**Step C — Create `src/spark_modem/policy/ladder.py`:**

```python
"""policy/ladder.py — pure-function ladder rung selector (Phase 4 B-01).

Decision table stays flat ((category, detail) -> base ActionKind);
this module owns rung selection based on per-action counters vs.
RECOVERY_SPEC §4.1 ceilings. Engine calls lookup_action() for the base,
then ladder.select_rung() for the actual ladder progression.

CLAUDE.md invariant 1: pure function. No subprocess, no httpx, no os,
no asyncio. Only typing + Settings + ActionKind imports.

RECOVERY_SPEC §10.2 worked examples (test fixtures):
  - counters={} (any rung-1 base) → base
  - counters={SOFT_RESET: 3} (max_soft=3) → MODEM_RESET
  - counters={SOFT_RESET: 3, MODEM_RESET: 2} (max_modem=2) → USB_RESET
  - counters={SOFT_RESET: 3, MODEM_RESET: 2, USB_RESET: 1} (max_usb=1) → "skip:exhausted"
"""

from __future__ import annotations

from typing import Literal

from spark_modem.config.settings import Settings
from spark_modem.wire.enums import ActionKind


_LADDER_RUNGS: tuple[ActionKind, ...] = (
    ActionKind.SOFT_RESET,
    ActionKind.MODEM_RESET,
    ActionKind.USB_RESET,
)


def select_rung(
    base: ActionKind,
    counters: dict[ActionKind, int],
    config: Settings,
) -> ActionKind | Literal["skip:exhausted"]:
    """Pick the actual ladder rung given the BASE action and per-kind counters.

    If the base is not on the destructive ladder (SOFT_RESET / MODEM_RESET /
    USB_RESET), return it unchanged -- non-ladder actions don't escalate.

    Algorithm:
      1. Find the base's index on _LADDER_RUNGS.
      2. Walk rungs from that index forward. For each rung:
         - If counters[rung] >= ceiling for that rung -> promote to next.
         - Else return rung.
      3. If all rungs from base onward are at-or-above ceiling -> "skip:exhausted".
    """
    if base not in _LADDER_RUNGS:
        return base

    ceilings = {
        ActionKind.SOFT_RESET: config.max_soft,
        ActionKind.MODEM_RESET: config.max_modem,
        ActionKind.USB_RESET: config.max_usb,
    }

    start_idx = _LADDER_RUNGS.index(base)
    for rung in _LADDER_RUNGS[start_idx:]:
        if counters.get(rung, 0) >= ceilings[rung]:
            continue  # ceiling reached -- promote
        return rung
    return "skip:exhausted"
```

**Step D — Tests:**

Update `tests/unit/wire/test_state.py` with the 3 ModemState tests from
`<behavior>`. Use a sample Phase-2-shape JSON (without the new field) for the
backwards-compat round-trip test.

Update `tests/unit/policy/test_gates.py`:
- The Phase 2 tests populated `state.last_action_monotonic` to gate-fire. Update each existing test that references `last_action_monotonic` to ALSO populate `last_action_monotonic_by_kind={action_kind: timestamp}` so the gate fires off the new field. Keep the old field populated for back-compat (engine bumps both) but the gate logic now reads the new dict.
- Add the 5 new tests from `<behavior>` covering per-kind discrimination + MAX-over-destructive-kinds.

Create `tests/unit/policy/test_ladder.py` with imports + the 7 test functions
from `<behavior>`.

Per CLAUDE.md: ladder.py is a pure function (no I/O imports); SP-04 lint passes
trivially; mypy --strict on every new and changed file.
  </action>
  <verify>
    <automated>cd /s/spark/modem-watchdog &amp;&amp; .venv/bin/pytest tests/unit/wire/test_state.py tests/unit/policy/test_gates.py tests/unit/policy/test_ladder.py -x &amp;&amp; .venv/bin/mypy --strict src/spark_modem/policy/ladder.py src/spark_modem/policy/gates.py src/spark_modem/wire/state.py &amp;&amp; .venv/bin/ruff check src/spark_modem/policy/ladder.py src/spark_modem/policy/gates.py src/spark_modem/wire/state.py tests/unit/policy/test_ladder.py &amp;&amp; .venv/bin/ruff format --check src/spark_modem/policy/ladder.py</automated>
  </verify>
  <acceptance_criteria>
    - File exists: `src/spark_modem/policy/ladder.py` (≥30 lines, ≤80 lines)
    - `grep -F 'def select_rung' src/spark_modem/policy/ladder.py` returns ≥1 match
    - `grep -F '"skip:exhausted"' src/spark_modem/policy/ladder.py` returns ≥1 match
    - `grep -F 'config.max_soft' src/spark_modem/policy/ladder.py` returns ≥1 match
    - `grep -F 'last_action_monotonic_by_kind: dict[ActionKind, float]' src/spark_modem/wire/state.py` returns ≥1 match
    - `grep -F 'last_action_monotonic: float | None = None' src/spark_modem/wire/state.py` returns ≥1 match (legacy field preserved)
    - `grep -F 'state.last_action_monotonic_by_kind.get(action)' src/spark_modem/policy/gates.py` returns ≥1 match
    - `grep -F 'max(destructive_ts)' src/spark_modem/policy/gates.py` returns ≥1 match
    - `grep -F 'del action' src/spark_modem/policy/gates.py` returns 0 matches (the Phase 2 `del action  # reserved` line is removed)
    - File exists: `tests/unit/policy/test_ladder.py` with ≥7 test functions
    - `pytest tests/unit/wire/test_state.py tests/unit/policy/test_gates.py tests/unit/policy/test_ladder.py -x` exits 0 with all tests collected
    - `mypy --strict src/spark_modem/policy/ladder.py src/spark_modem/policy/gates.py src/spark_modem/wire/state.py` exits 0
    - `bash scripts/lint_no_subprocess.sh` exits 0 (ladder.py is pure-function — no subprocess)
    - `grep -E 'subprocess|asyncio|httpx|^import os' src/spark_modem/policy/ladder.py` returns 0 matches (purity)
  </acceptance_criteria>
  <done>
    ladder.py created as pure function; gates re-keyed on per-kind dict; ModemState gains last_action_monotonic_by_kind with default empty; back-compat with Phase 2 state JSON preserved; all tests pass.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Wire ladder.select_rung() into engine + per-kind timestamp bump + signal-gate Settings migration in transitions.py</name>
  <files>
    src/spark_modem/policy/engine.py,
    src/spark_modem/policy/transitions.py,
    tests/unit/policy/test_engine.py,
    tests/unit/policy/test_transitions.py
  </files>
  <read_first>
    - src/spark_modem/policy/engine.py (entire file — the per-modem path at lines 108-184 is where ladder integration + per-kind bump happens; the `_apply_gates_to_action` at 194-277 is unchanged in this task; the `_global_driver_reset_eligible` already cleaned up in Task 1)
    - src/spark_modem/policy/transitions.py (entire file — the 3 Final constants to delete + the signature change at line 29 + the call-site at line 65)
    - tests/unit/policy/test_engine.py (existing engine tests — must update fixtures that read `state.last_action_monotonic` to also see `last_action_monotonic_by_kind` get bumped)
    - tests/unit/policy/test_transitions.py (existing transitions tests — every call to is_signal_below_gate(snap) becomes is_signal_below_gate(snap, settings))
    - .planning/phases/04-destructive-actions-hil/04-PATTERNS.md § "src/spark_modem/policy/transitions.py:is_signal_below_gate" + § "src/spark_modem/policy/engine.py:_global_driver_reset_eligible"
  </read_first>
  <behavior>
    Signal-gate migration (test_transitions.py — update existing tests):
    - Every existing call to `is_signal_below_gate(snap)` becomes `is_signal_below_gate(snap, settings)` where `settings = Settings()` (default floors).
    - test_is_signal_below_gate_reads_rsrp_from_settings: build Settings with `signal_rsrp_floor_dbm=-100` (stricter than default -110); snap with rsrp_dbm=-105; assert returns True (below stricter floor).
    - test_is_signal_below_gate_reads_rsrq_from_settings: same pattern for rsrq.
    - test_is_signal_below_gate_reads_snr_from_settings: same pattern for snr.
    - test_transition_passes_settings_to_signal_gate: integration — call `transition(prior, snap, ctx)` where ctx.config has custom signal floors; assert the resulting ModemState.rf_blocked reflects the custom floor (proves transition() threads ctx.config through, not the deleted module constants).

    Engine ladder integration (test_engine.py — extend existing):
    - test_engine_uses_ladder_select_rung_for_registration: build a Diag with NOT_REGISTERED_SEARCHING; prior_state with counters={SOFT_RESET: 3}; ctx.config defaults; assert the planned action's kind == ActionKind.MODEM_RESET (ladder promoted from SOFT_RESET base).
    - test_engine_ladder_yields_skip_exhausted_when_all_rungs_full: Diag with NOT_REGISTERED_SEARCHING; prior_state with counters={SOFT_RESET: 3, MODEM_RESET: 2, USB_RESET: 1}; assert PlannedAction has reason starting with "skip:exhausted" or equivalent (engine emits a `skip:exhausted`-shaped PlannedAction).
    - test_engine_bumps_last_action_monotonic_by_kind_atomically: Diag triggering MODEM_RESET; assert resulting ModemState has BOTH `last_action_monotonic == ctx.clock.monotonic()` AND `last_action_monotonic_by_kind[ActionKind.MODEM_RESET] == ctx.clock.monotonic()`. Single model_copy (atomic per RECOVERY_SPEC §8 / CLAUDE.md invariant 8).
    - test_engine_does_not_bump_per_kind_for_skipped_actions: Diag with action that gets gated (e.g. signal-below-gate); assert `last_action_monotonic_by_kind` is unchanged (counter_bump is None when would_execute is False).
    - test_engine_phase_2_states_load_and_run_cleanly: build a ModemState constructed with the Phase 2 shape (no `last_action_monotonic_by_kind` populated); engine.run_cycle returns successfully; the post-cycle state has `last_action_monotonic_by_kind={ActionKind.SOFT_RESET: ...}` after a successful action — proves no NPE on the empty default.
  </behavior>
  <action>
**Step A — Migrate `src/spark_modem/policy/transitions.py`:**

1. Delete the 3 module-level Final constants (lines 22-26):
   ```python
   _RSRP_FLOOR_DBM: Final[int] = -110
   _RSRQ_FLOOR_DB: Final[float] = -15.0
   _SNR_FLOOR_DB: Final[float] = 0.0
   ```
2. Change the import from `from typing import Final` if `Final` is no longer used elsewhere in the file (verify — if `Final` is gone, remove the import too; ruff/mypy will flag unused).
3. Add import: `from spark_modem.config.settings import Settings`.
4. Change `is_signal_below_gate` signature:
   ```python
   def is_signal_below_gate(snap: ModemSnapshot, config: Settings) -> bool:
       """RECOVERY_SPEC §6.1: rsrp < floor OR rsrq < floor OR snr < floor.

       Phase 4 (B-03): floors read from Settings (RELOAD_DATA tagged), not
       module-level Final constants. SIGHUP retunes per cohort.

       Missing readings (None) -> return False (not blocked; absence of data
       is not the same as 'below threshold').
       """
       sig = snap.signal
       if sig.rsrp_dbm is not None and sig.rsrp_dbm < config.signal_rsrp_floor_dbm:
           return True
       if sig.rsrq_db is not None and sig.rsrq_db < config.signal_rsrq_floor_db:
           return True
       return sig.snr_db is not None and sig.snr_db < config.signal_snr_floor_db
   ```
5. Update the single call-site at line 65 (inside `transition()` body): change `rf_blocked = is_signal_below_gate(snap)` → `rf_blocked = is_signal_below_gate(snap, ctx.config)`. The `ctx: PolicyContext` parameter is already in scope; per the existing `del ctx` at line 63, **REMOVE** that `del ctx` line so the executor can read `ctx.config`.

**Step B — Wire ladder + per-kind timestamp bump in `src/spark_modem/policy/engine.py`:**

1. Add import at top:
   ```python
   from spark_modem.policy.ladder import select_rung
   ```

2. In the per-modem path of `run_cycle` (around lines 130-145), update Step 5 + 6:
   - After `action_or_skip = lookup_action(issue.category, issue.detail)`:
   - If `isinstance(action_or_skip, ActionKind)` AND `action_or_skip in {ActionKind.SOFT_RESET, ActionKind.MODEM_RESET, ActionKind.USB_RESET}`:
     - Apply ladder selection: `selected = select_rung(base=action_or_skip, counters=prior.counters, config=ctx.config)`.
     - If `selected == "skip:exhausted"`: emit a PlannedAction with `reason="skip:exhausted"` (mirror the existing skip-string pattern at lines 146-159).
     - Else: `action_or_skip = selected` (the ladder-promoted ActionKind) and proceed to `_apply_gates_to_action`.
   - For ActionKinds NOT on the ladder (SET_APN, FIX_RAW_IP, SIM_POWER_ON, FIX_AUTOSUSPEND, SET_OPERATING_MODE, DRIVER_RESET): bypass the ladder and go straight to `_apply_gates_to_action` (the existing path).

3. Update Step 7 (counter bump + state copy) to ALSO bump the per-kind timestamp dict:
   ```python
   # Step 7 -- counter bump + per-kind timestamp bump (only if would_execute)
   new_counters: dict[ActionKind, int] = dict(decayed_counters)
   new_ts_by_kind: dict[ActionKind, float] = dict(prior.last_action_monotonic_by_kind)
   new_last_action_monotonic = prior.last_action_monotonic
   if counter_bump is not None:
       new_counters[counter_bump] = new_counters.get(counter_bump, 0) + 1
       now = ctx.clock.monotonic()
       new_ts_by_kind[counter_bump] = now
       new_last_action_monotonic = now

   new_state_with_counters = new_state.model_copy(
       update={
           "healthy_streak": new_streak,
           "counters": new_counters,
           "last_action_monotonic": new_last_action_monotonic,
           "last_action_monotonic_by_kind": new_ts_by_kind,
       }
   )
   ```
   Atomic per RECOVERY_SPEC §8 / CLAUDE.md invariant 8: ONE `model_copy` writes streak + counters + both timestamp fields together.

4. Verify the sub-helper `_fresh_initial_state` (around lines 308-325) constructs ModemState with the new field set to `{}`:
   ```python
   "last_action_monotonic_by_kind": {},
   ```
   Append this to the dict literal passed to `ModemState.model_validate({...})`.

**Step C — Tests:**

Update `tests/unit/policy/test_transitions.py` — every `is_signal_below_gate(snap)` call becomes `is_signal_below_gate(snap, settings)`. Add the 4 new tests from `<behavior>`.

Update `tests/unit/policy/test_engine.py` — add the 5 new tests from `<behavior>`. The atomic-bump test is the linchpin: it verifies that BOTH timestamp fields land in the SAME ModemState revision (use `model_dump()` and assert both keys carry the same value when an action executes).

Per CLAUDE.md: pure-engine policy preserved (no new I/O imports); atomic state writes preserved (single model_copy per cycle); match-on-state in transitions.py untouched.
  </action>
  <verify>
    <automated>cd /s/spark/modem-watchdog &amp;&amp; .venv/bin/pytest tests/unit/policy/test_engine.py tests/unit/policy/test_transitions.py tests/unit/policy/test_engine_driver_reset.py tests/unit/policy/test_ladder.py tests/unit/policy/test_gates.py -x &amp;&amp; .venv/bin/mypy --strict src/spark_modem/policy/ &amp;&amp; .venv/bin/ruff check src/spark_modem/policy/ tests/unit/policy/ &amp;&amp; bash scripts/lint_no_subprocess.sh</automated>
  </verify>
  <acceptance_criteria>
    - `grep -F '_RSRP_FLOOR_DBM' src/spark_modem/policy/transitions.py` returns 0 matches (constant deleted)
    - `grep -F '_RSRQ_FLOOR_DB' src/spark_modem/policy/transitions.py` returns 0 matches (constant deleted)
    - `grep -F '_SNR_FLOOR_DB' src/spark_modem/policy/transitions.py` returns 0 matches (constant deleted)
    - `grep -F 'def is_signal_below_gate(snap: ModemSnapshot, config: Settings)' src/spark_modem/policy/transitions.py` returns ≥1 match
    - `grep -F 'config.signal_rsrp_floor_dbm' src/spark_modem/policy/transitions.py` returns ≥1 match
    - `grep -F 'is_signal_below_gate(snap, ctx.config)' src/spark_modem/policy/transitions.py` returns ≥1 match (the call-site update)
    - `grep -F 'from spark_modem.policy.ladder import select_rung' src/spark_modem/policy/engine.py` returns ≥1 match
    - `grep -F 'select_rung(base=' src/spark_modem/policy/engine.py` returns ≥1 match
    - `grep -F '"last_action_monotonic_by_kind"' src/spark_modem/policy/engine.py` returns ≥1 match (the model_copy update key)
    - `grep -F '"last_action_monotonic_by_kind": {}' src/spark_modem/policy/engine.py` returns ≥1 match (_fresh_initial_state default)
    - `pytest tests/unit/policy/ -x` exits 0 (every Phase 2 test that touched transitions / gates / engine still passes after the API changes)
    - `pytest tests/unit/wire/test_state.py -x` exits 0
    - `mypy --strict src/spark_modem/policy/` exits 0
    - `bash scripts/lint_no_subprocess.sh` exits 0
    - Full unit suite: `pytest -m "unit and not linux_only and not hil" -x` exits 0 (no regression — Plans 04-01/02/03 tests still pass)
    - `pytest tests/unit/policy/test_engine_action_execution.py::test_engine_atomically_bumps_legacy_and_per_kind_timestamps -x` exits 0

      Test body must assert (after a successful action execution):
      - state.last_action_monotonic == ctx.clock.monotonic() at action time
      - state.last_action_monotonic_by_kind[executed_kind] == ctx.clock.monotonic() at action time
      - The two values are equal (atomic same-clock-read)
      - The legacy field is bumped even though no gate reads it (back-compat contract for Phase 2 state files)

      If `tests/unit/policy/test_engine_action_execution.py` does not exist yet, this Task adds it as one of the test cases inside that file (alongside the existing test_engine_bumps_last_action_monotonic_by_kind_atomically). Per the legacy back-compat contract: a future engineer must NOT delete the legacy `last_action_monotonic` bump as dead code — Phase 2 state-file replay relies on the field being populated.
  </acceptance_criteria>
  <done>
    Engine wires ladder.select_rung; per-kind timestamps bump atomically alongside counters; signal-gate floors come from Settings (3 module Finals deleted); transition() threads ctx.config through is_signal_below_gate; full policy test suite green.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| daemon process → state-store atomic write | The new `last_action_monotonic_by_kind` dict is part of the per-modem ModemState atomic write (state/by-usb/<usb_path>.json); same temp+rename+fsync discipline as existing fields |
| SIGHUP → Settings reload | Signal-gate thresholds are RELOAD_DATA — operator can adjust floors via SIGHUP; the per-cohort tunability is a feature, not a vulnerability |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-04-01 | T (Tampering) | ModemState backwards-compat (Phase 2 JSON without new field) | mitigate | `Field(default_factory=dict)` ensures missing field defaults to `{}` on load — Phase 2 state files round-trip cleanly. Test `test_modem_state_loads_phase2_json_without_new_field` is the regression gate |
| T-04-04-02 | T (Tampering) | Forged `last_action_monotonic_by_kind` to bypass backoff gate | accept | The state file is owned by the daemon process (root, 0o600 file mode per ADR-0009 / state_store atomic write); an attacker with write access already owns the daemon. Out of scope per NFR-30 |
| T-04-04-03 | E (Elevation) | Operator sets `signal_rsrp_floor_dbm=0` to disable signal gate | accept | Operator can already tune floors via YAML — the SIGHUP reload is the contract. The signal gate is operator-discretion (RECOVERY_SPEC §6.1 documents the trade-off); destructive-action ladder backoff (90 s) plus per-modem flock (ADR-0012) bound the blast radius even if signal gate is fully disabled |
| T-04-04-04 | I (Information disclosure) | last_action_monotonic_by_kind in events.jsonl | accept | The dict is part of ModemState which is included in StateTransition events. Values are monotonic timestamps (no PII / no wall-clock leak). Same surface as existing last_action_monotonic field |
| T-04-04-05 | D (Denial of service) | Ladder lookup with corrupt counters (huge int) | mitigate | `counters[rung] >= ceiling` arithmetic is integer comparison; pydantic v2 accepts dict[ActionKind, int] which mypy/ruff verify; pathological values just collapse to "skip:exhausted" sooner — no DoS |
| T-04-04-06 | R (Repudiation) | Per-kind timestamp atomicity | mitigate | The Step-7 `model_copy(update={...})` writes BOTH legacy and new timestamp fields in ONE pydantic operation; the cycle driver's `state_store.save_modem_state` writes ONE atomic file. RECOVERY_SPEC §8 ordering preserved. Test `test_engine_bumps_last_action_monotonic_by_kind_atomically` is the regression gate |
</threat_model>

<verification>
- All Plan 04-04 task `<verify>` commands pass.
- `pytest -m "unit and not linux_only and not hil" -x` exits 0 (full unit suite — ≥40 new tests across 6 test files).
- `mypy --strict src/spark_modem/` exits 0.
- `ruff check src/spark_modem/ tests/` exits 0.
- `bash scripts/lint_no_subprocess.sh` exits 0.
- `grep -F '_RSRP_FLOOR_DBM' src/spark_modem/` returns 0 matches across the entire src/ tree (Final constant deleted).
- `pytest tests/unit/policy/test_engine_driver_reset.py -x` exits 0 — the predicate from Plan 04-03 still works after the getattr removal.
- The ladder progression contract test (4 RECOVERY_SPEC §10.2 scenarios) is in `test_ladder.py`.
- Phase 2 state file backwards-compat: a hand-crafted JSON without `last_action_monotonic_by_kind` round-trips through `ModemState.model_validate_json` and produces an empty dict default.
</verification>

<success_criteria>
- `policy/ladder.py` exists as a pure-function module with `select_rung(base, counters, config)`.
- `ModemState.last_action_monotonic_by_kind` is a `dict[ActionKind, float]` with `default_factory=dict`; Phase 2 state JSON loads cleanly.
- `gate_same_action_backoff` and `gate_ladder_backoff` BOTH read from `last_action_monotonic_by_kind` (per-kind for same-action, MAX over destructive-kinds for ladder).
- `is_signal_below_gate` takes `(snap, config)` and reads thresholds from `config.signal_*_floor_*`; the 3 module-level Final constants are gone.
- `transition()` threads `ctx.config` through to `is_signal_below_gate`.
- Engine integrates `ladder.select_rung()` for ladder-eligible bases (SOFT/MODEM/USB_RESET); decision-table stays flat.
- Engine bumps `last_action_monotonic` AND `last_action_monotonic_by_kind[counter_bump]` in ONE `model_copy` per cycle (atomic; RECOVERY_SPEC §8).
- Settings gains 6 new RELOAD_DATA fields (3 signal floors + 3 ladder ceilings).
- Plan 04-03's `getattr(ctx.config, "signal_*_floor_*", default)` defensive reads in `_global_driver_reset_eligible` are removed; direct attribute reads.
- 40+ new/updated unit tests across 6 files; all green.
- CLAUDE.md invariants honored: pure-engine policy (no new I/O imports); atomic state writes (single model_copy); match-on-state untouched; per-kind timestamp dict is additive (legacy field preserved).
- Full Phase 1+2+3 + Phase 4 plans 04-01/02/03 regression suite stays green.
</success_criteria>

<output>
After completion, create `.planning/phases/04-destructive-actions-hil/04-04-SUMMARY.md`
documenting: files created (ladder.py + test_ladder.py), files extended
(engine, gates, transitions, state, settings, 4 test files), the 6 new
Settings fields with their RELOAD_DATA tagging, the per-kind timestamp dict
addition with backwards-compat, the gate re-keying (legacy field preserved
on the wire shape but no longer authoritative for gate evaluation), the
signal-gate Settings migration (3 module Finals deleted), the engine ladder
integration, and the atomic-bump contract test. Note that the cycle driver's
`PolicyContext.expected_modem_count = ctx.config.expected_modem_count` wiring
remains a follow-up item if not already wired in Plan 04-03 (Plan 04-04 tests
construct PolicyContext explicitly).
</output>
