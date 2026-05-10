---
plan: 04-05
title: ActionSkipped event variant + decision-table/engine integration
phase: 04
wave: 5
depends_on: [04-04]
files_modified:
  - src/spark_modem/wire/enums.py
  - src/spark_modem/wire/events.py
  - src/spark_modem/policy/engine.py
  - src/spark_modem/policy/result.py
  - src/spark_modem/daemon/cycle_driver.py
  - tests/unit/wire/test_events.py
  - tests/unit/wire/test_action_skipped_event.py
  - tests/unit/policy/test_engine.py
  - tests/unit/daemon/test_cycle_driver.py
autonomous: true
requirements: [FR-23]
must_haves:
  truths:
    - "wire/events.py contains a new ActionSkipped variant with kind='action_skipped' discriminator"
    - "wire/enums.py contains a new SkipReason StrEnum with 7 values: signal_below_gate, ladder_backoff, same_action_backoff, exhausted, disconnected, maintenance, dry_run"
    - "wire/enums.py:EventKind contains a new ACTION_SKIPPED value"
    - "Event tagged-union (Annotated[..., Field(discriminator='kind')]) includes ActionSkipped"
    - "Engine emits ActionSkipped events alongside the existing PlannedAction.suppressed_* flags (back-compat preserved per CONTEXT 'ActionSkipped vs PlannedAction.suppressed_* flags back-compat horizon')"
    - "Engine emits ActionSkipped for: signal_below_gate, same_action_backoff, ladder_backoff, exhausted (via _apply_gates_to_action gate-failure paths) AND disconnected, maintenance, exhausted (hard-skip paths) AND dry_run (when dry_run gate fires) AND ladder skip:exhausted from Plan 04-04"
    - "CycleResult gains a skipped: list[ActionSkipped] field; cycle_driver appends each skipped event to event_logger.append() AFTER the atomic state write per RECOVERY_SPEC §8"
    - "PlannedAction.suppressed_by_signal_gate / suppressed_by_backoff / suppressed_by_dry_run flags are unchanged (replay-harness back-compat with Phase 2 fixtures)"
  artifacts:
    - path: "src/spark_modem/wire/events.py"
      provides: "ActionSkipped event variant in the discriminated Event union"
      contains: "class ActionSkipped"
    - path: "src/spark_modem/wire/enums.py"
      provides: "SkipReason StrEnum (7 values) + EventKind.ACTION_SKIPPED"
      contains: "class SkipReason"
    - path: "src/spark_modem/policy/result.py"
      provides: "CycleResult.skipped: list[ActionSkipped] field"
      contains: "skipped: list"
    - path: "src/spark_modem/policy/engine.py"
      provides: "Engine emits ActionSkipped alongside PlannedAction.suppressed_* flags"
    - path: "tests/unit/wire/test_action_skipped_event.py"
      provides: "Round-trip + tagged-union discriminator tests"
  key_links:
    - from: "src/spark_modem/policy/engine.py:run_cycle"
      to: "src/spark_modem/wire/events.py:ActionSkipped"
      via: "construction + append to CycleResult.skipped"
      pattern: "ActionSkipped\\("
    - from: "src/spark_modem/daemon/cycle_driver.py"
      to: "ctx.event_logger.append"
      via: "for skipped in result.skipped"
      pattern: "for .+ in .+\\.skipped"
---

<objective>
Land the ActionSkipped event variant per CONTEXT B-04 / SC#2's literal
"action_skipped event with reason `signal_below_gate`" phrasing. Per
CONTEXT § Discretion item "ActionSkipped event vs PlannedAction.suppressed_*
flags back-compat horizon" — Phase 4 emits BOTH. The new event is the
consumer-friendly shape going forward; the existing PlannedAction flags are
preserved for Plan 02-10's replay harness which already classifies traces
against them.

Purpose:
- Close FR-23 SC#2's "action_skipped event" gap. Phase 2's PlannedAction has
  `suppressed_by_signal_gate / suppressed_by_backoff / suppressed_by_dry_run`
  bool flags but no first-class event variant — operators can't filter the
  events.jsonl stream by skip reason.
- Add `SkipReason` as a closed StrEnum (W-04 discipline) so adding a new
  reason in a future phase is a deliberate enum extension, not a string drift.
- Preserve replay-harness back-compat (no shim needed — the harness reads
  PlannedAction.suppressed_* flags from Phase 2 fixtures and ignores the new
  ActionSkipped events; new fixtures will populate both shapes).

Output:
- Extended: `wire/enums.py` (+1 StrEnum + 1 EventKind value), `wire/events.py`
  (+1 variant + tagged-union update + 1 import line),
  `policy/result.py` (CycleResult gains `skipped` list), `policy/engine.py`
  (every gate-failure / hard-skip / dry-run path constructs ActionSkipped and
  appends to result), `daemon/cycle_driver.py` (dispatches skipped events to
  event_logger.append after the atomic state write).
- New: `tests/unit/wire/test_action_skipped_event.py`.
- Updated: `tests/unit/wire/test_events.py` (extended union test),
  `tests/unit/policy/test_engine.py` (engine emits ActionSkipped),
  `tests/unit/daemon/test_cycle_driver.py` (cycle driver flushes ActionSkipped to event log).

Wave 2 ordering: depends on Plan 04-04 because the new `skip:exhausted` ladder
skip must also generate an ActionSkipped event (with `reason=exhausted`).
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
@.planning/phases/04-destructive-actions-hil/04-04-ladder-and-signal-gate-PLAN.md
@CLAUDE.md

<interfaces>
<!-- Verbatim from PATTERNS.md / source — executor uses these directly. -->

From src/spark_modem/wire/events.py:1-30 (the existing _EventBase + ActionPlanned shape):
```python
class _EventBase(BaseWire):
    schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, ge=1)
    ts_iso: str


class ActionPlanned(_EventBase):
    kind: Literal["action_planned"] = "action_planned"
    usb_path: str
    action: ActionKind
    reason: str
    dry_run: bool = False
```

From src/spark_modem/wire/events.py (the existing tagged union — extend with ActionSkipped):
```python
Event = Annotated[
    ActionPlanned
    | ActionExecuted
    | ActionFailed
    | StateTransition
    | DaemonStarted
    | DaemonStopped
    | SchemaDowngradePending
    | UsbPathMismatch
    | MaintenanceWindowStarted
    | MaintenanceWindowEnded
    | WebhookDropped
    | EventSourceCrashed
    | SimSwapped,
    Field(discriminator="kind"),
]
```

From src/spark_modem/wire/enums.py:126-138 (the EventKind to extend):
```python
class EventKind(StrEnum):
    ACTION_PLANNED = "action_planned"
    ACTION_EXECUTED = "action_executed"
    ACTION_FAILED = "action_failed"
    STATE_TRANSITION = "state_transition"
    DAEMON_STARTED = "daemon_started"
    DAEMON_STOPPED = "daemon_stopped"
    SCHEMA_DOWNGRADE_PENDING = "schema_downgrade_pending"
    USB_PATH_MISMATCH = "usb_path_mismatch"
    MAINTENANCE_WINDOW_STARTED = "maintenance_window_started"
    MAINTENANCE_WINDOW_ENDED = "maintenance_window_ended"
```

From src/spark_modem/policy/engine.py (the gate-failure paths in `_apply_gates_to_action` — every `return PlannedAction(...)` with a skip reason needs a sibling ActionSkipped):
- gate_disconnected fires → reason "skip:disconnected" → emit ActionSkipped(reason=DISCONNECTED)
- gate_maintenance fires → reason "skip:maintenance" → emit ActionSkipped(reason=MAINTENANCE)
- gate_exhausted fires → reason "skip:exhausted" → emit ActionSkipped(reason=EXHAUSTED)
- soft-skip path: if `suppressed_signal` → emit ActionSkipped(reason=SIGNAL_BELOW_GATE)
- soft-skip path: if `suppressed_backoff` (same_action OR ladder) → emit ActionSkipped(reason=SAME_ACTION_BACKOFF or LADDER_BACKOFF — engine MUST distinguish; the gate test in gates.py knows which fired)
- soft-skip path: if `suppressed_dry_run` AND not (signal or backoff) → emit ActionSkipped(reason=DRY_RUN)

From Plan 04-04 (the new ladder skip:exhausted path):
- engine path emits a PlannedAction with reason="skip:exhausted" when ladder.select_rung returns "skip:exhausted" → also emit ActionSkipped(reason=EXHAUSTED)

PATTERNS.md § "src/spark_modem/wire/events.py" specifies the variant shape:
```python
class ActionSkipped(_EventBase):
    """A planned action was suppressed by a gate (Phase 4 B-04)."""
    kind: Literal["action_skipped"] = "action_skipped"
    usb_path: str
    suppressed_action: ActionKind
    reason: SkipReason
    cause_category: IssueCategory
    cause_detail: IssueDetail
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add SkipReason StrEnum + EventKind.ACTION_SKIPPED + ActionSkipped event variant + tagged-union update</name>
  <files>
    src/spark_modem/wire/enums.py,
    src/spark_modem/wire/events.py,
    tests/unit/wire/test_action_skipped_event.py,
    tests/unit/wire/test_events.py
  </files>
  <read_first>
    - src/spark_modem/wire/enums.py (entire file — 165 lines; locate the EventKind class at lines 126-138 and the closing of the StrEnum sequence)
    - src/spark_modem/wire/events.py (entire file — locate the existing event variants and the tagged-union assembly)
    - src/spark_modem/wire/_base.py (BaseWire ConfigDict — frozen=True, extra=forbid, populate_by_name=True)
    - tests/unit/wire/test_events.py (the existing tagged-union round-trip / discriminator tests — these need extension)
    - .planning/phases/04-destructive-actions-hil/04-PATTERNS.md § "src/spark_modem/wire/events.py" + § "src/spark_modem/wire/enums.py"
  </read_first>
  <behavior>
    - test_skip_reason_has_seven_values: assert `set(SkipReason) == {SkipReason.SIGNAL_BELOW_GATE, SkipReason.LADDER_BACKOFF, SkipReason.SAME_ACTION_BACKOFF, SkipReason.EXHAUSTED, SkipReason.DISCONNECTED, SkipReason.MAINTENANCE, SkipReason.DRY_RUN}` — exactly 7 entries.
    - test_skip_reason_string_values_canonical: SkipReason.SIGNAL_BELOW_GATE.value == "signal_below_gate"; SkipReason.LADDER_BACKOFF.value == "ladder_backoff"; ...; SkipReason.DRY_RUN.value == "dry_run". Exact string forms pinned.
    - test_event_kind_action_skipped_value: assert EventKind.ACTION_SKIPPED.value == "action_skipped".
    - test_action_skipped_round_trip: construct ActionSkipped(ts_iso="2026-05-10T12:00:00Z", usb_path="2-3.1.1", suppressed_action=ActionKind.MODEM_RESET, reason=SkipReason.SIGNAL_BELOW_GATE, cause_category=IssueCategory.REGISTRATION, cause_detail=IssueDetail.NOT_REGISTERED_SEARCHING); model_dump_json + model_validate_json round-trip; assert all fields preserved.
    - test_action_skipped_kind_discriminator_routes_correctly: dump an ActionSkipped to JSON; pass through `TypeAdapter(Event).validate_json(json_bytes)`; assert isinstance result is ActionSkipped (the tagged union routes by kind discriminator).
    - test_action_skipped_rejects_unknown_reason: ActionSkipped(... reason="quantum_tunnel" ...) raises pydantic ValidationError (closed-enum discipline; reason is StrEnum-typed).
    - test_action_skipped_per_skip_reason_round_trip: parametrize over all 7 SkipReason values; for each, construct + round-trip + assert reason field equals the original.
    - test_event_tagged_union_includes_action_skipped: count the variants in the `Event` union by parsing each in-tree variant via TypeAdapter; assert ActionSkipped is reachable. (Test pattern: dump each known variant, route through the union, assert isinstance.)
  </behavior>
  <action>
**Step A — Extend `src/spark_modem/wire/enums.py`:**

1. Add `EventKind.ACTION_SKIPPED = "action_skipped"` to the EventKind class:
   ```python
   class EventKind(StrEnum):
       ACTION_PLANNED = "action_planned"
       ACTION_EXECUTED = "action_executed"
       ACTION_FAILED = "action_failed"
       ACTION_SKIPPED = "action_skipped"   # NEW (Phase 4 B-04)
       STATE_TRANSITION = "state_transition"
       ...
   ```

2. Add a NEW `SkipReason` StrEnum class. Place it AFTER `DaemonStopReason` (the last StrEnum in the file):
   ```python
   class SkipReason(StrEnum):
       """ActionSkipped event reason field (Phase 4 B-04).

       Closed-enum discipline (W-04): adding a new value is a deliberate
       schema extension, never a runtime string. Engine maps gate-failure
       paths to these values 1:1 -- see policy/engine.py for the mapping.
       """

       SIGNAL_BELOW_GATE = "signal_below_gate"
       LADDER_BACKOFF = "ladder_backoff"
       SAME_ACTION_BACKOFF = "same_action_backoff"
       EXHAUSTED = "exhausted"
       DISCONNECTED = "disconnected"
       MAINTENANCE = "maintenance"
       DRY_RUN = "dry_run"
   ```

**Step B — Extend `src/spark_modem/wire/events.py`:**

1. Update the imports at top:
   ```python
   from spark_modem.wire.enums import (
       ActionKind,
       ActionResult,
       DaemonStopReason,
       DowngradeReason,
       IssueCategory,    # NEW
       IssueDetail,      # NEW
       SkipReason,       # NEW
   )
   ```

2. Add the ActionSkipped variant after `ActionFailed` (around line 60):
   ```python
   class ActionSkipped(_EventBase):
       """A planned action was suppressed by a gate (Phase 4 B-04 / FR-23).

       Emitted alongside the existing PlannedAction.suppressed_* flags for
       backwards compat with Plan 02-10 replay-harness fixtures. The
       `reason` field maps 1:1 to gate-failure paths in policy/engine.py.
       """

       kind: Literal["action_skipped"] = "action_skipped"
       usb_path: str
       suppressed_action: ActionKind
       reason: SkipReason
       cause_category: IssueCategory
       cause_detail: IssueDetail
   ```

3. Update the `Event = Annotated[...]` tagged-union ALPHABETICALLY (between ActionPlanned and ActionExecuted by lexical order — but the existing union is in author order; preserve the author-order pattern: add ActionSkipped after ActionFailed):
   ```python
   Event = Annotated[
       ActionPlanned
       | ActionExecuted
       | ActionFailed
       | ActionSkipped       # NEW
       | StateTransition
       | DaemonStarted
       | DaemonStopped
       | SchemaDowngradePending
       | UsbPathMismatch
       | MaintenanceWindowStarted
       | MaintenanceWindowEnded
       | WebhookDropped
       | EventSourceCrashed
       | SimSwapped,
       Field(discriminator="kind"),
   ]
   ```

4. Verify (do NOT add code, just verify) that the module-level `EVENT_TYPE_ADAPTER = TypeAdapter(Event)` (or whatever the existing TypeAdapter constant is) automatically picks up the new variant via the union — pydantic's discriminated union builds the lookup at class-definition time.

**Step C — Tests:**

Create `tests/unit/wire/test_action_skipped_event.py` with the 7 tests from `<behavior>` (excluding the union-coverage test which goes in test_events.py). Use the same `BaseWire`-construction patterns as existing event-variant tests.

Extend `tests/unit/wire/test_events.py` with `test_event_tagged_union_includes_action_skipped` (and any existing union-coverage tests that count variants need the count incremented — the existing `Event` union had 13 variants; now 14).

Per CLAUDE.md / W-02: BaseWire (frozen=True, extra=forbid, populate_by_name=True) is preserved; mypy --strict is the gate.
  </action>
  <verify>
    <automated>cd /s/spark/modem-watchdog &amp;&amp; .venv/bin/pytest tests/unit/wire/test_action_skipped_event.py tests/unit/wire/test_events.py -x &amp;&amp; .venv/bin/mypy --strict src/spark_modem/wire/enums.py src/spark_modem/wire/events.py &amp;&amp; .venv/bin/ruff check src/spark_modem/wire/enums.py src/spark_modem/wire/events.py tests/unit/wire/test_action_skipped_event.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -F 'class SkipReason(StrEnum)' src/spark_modem/wire/enums.py` returns ≥1 match
    - `grep -F 'SIGNAL_BELOW_GATE = "signal_below_gate"' src/spark_modem/wire/enums.py` returns ≥1 match
    - `grep -F 'LADDER_BACKOFF = "ladder_backoff"' src/spark_modem/wire/enums.py` returns ≥1 match
    - `grep -F 'SAME_ACTION_BACKOFF = "same_action_backoff"' src/spark_modem/wire/enums.py` returns ≥1 match
    - `grep -F 'EXHAUSTED = "exhausted"' src/spark_modem/wire/enums.py` returns ≥1 match
    - `grep -F 'DISCONNECTED = "disconnected"' src/spark_modem/wire/enums.py` returns ≥1 match
    - `grep -F 'MAINTENANCE = "maintenance"' src/spark_modem/wire/enums.py` returns ≥1 match
    - `grep -F 'DRY_RUN = "dry_run"' src/spark_modem/wire/enums.py` returns ≥1 match (within SkipReason class — distinguish from any DaemonStopReason member by checking class context)
    - `grep -F 'ACTION_SKIPPED = "action_skipped"' src/spark_modem/wire/enums.py` returns ≥1 match
    - `grep -F 'class ActionSkipped(_EventBase)' src/spark_modem/wire/events.py` returns ≥1 match
    - `grep -F 'kind: Literal["action_skipped"]' src/spark_modem/wire/events.py` returns ≥1 match
    - `grep -F '| ActionSkipped' src/spark_modem/wire/events.py` returns ≥1 match (in the tagged-union assembly)
    - File exists: `tests/unit/wire/test_action_skipped_event.py` with ≥7 tests
    - `pytest tests/unit/wire/test_action_skipped_event.py tests/unit/wire/test_events.py -x` exits 0
    - `mypy --strict src/spark_modem/wire/enums.py src/spark_modem/wire/events.py` exits 0
    - `ruff check src/spark_modem/wire/ tests/unit/wire/` exits 0
    - Full unit suite: `pytest -m "unit and not linux_only and not hil" -x` exits 0 (no Phase 2/3 wire-test regression — the new ActionSkipped variant adds to the union without breaking existing variants)
  </acceptance_criteria>
  <done>
    SkipReason StrEnum (7 values) + EventKind.ACTION_SKIPPED + ActionSkipped event variant landed; tagged-union routes correctly; round-trips clean; mypy + ruff green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Extend CycleResult.skipped + engine emits ActionSkipped on every skip path + cycle_driver flushes to event_logger</name>
  <files>
    src/spark_modem/policy/result.py,
    src/spark_modem/policy/engine.py,
    src/spark_modem/daemon/cycle_driver.py,
    tests/unit/policy/test_engine.py,
    tests/unit/daemon/test_cycle_driver.py
  </files>
  <read_first>
    - src/spark_modem/policy/result.py (entire file — the CycleResult dataclass to extend)
    - src/spark_modem/policy/engine.py (entire file — every gate-failure / hard-skip / dry-run path that constructs PlannedAction; specifically `_apply_gates_to_action` at lines 194-277 returns 4 hard-skip PlannedActions + 1 soft-skip path; the per-modem ladder skip:exhausted path lands from Plan 04-04)
    - src/spark_modem/daemon/cycle_driver.py (locate the event_logger.append calls — every CycleResult.skipped item must be appended after the atomic state write; the existing `for transition in result.transitions: event_logger.append(transition)` is the analog)
    - tests/unit/policy/test_engine.py (existing engine tests — the gate-failure tests need extending with ActionSkipped assertions)
    - tests/unit/daemon/test_cycle_driver.py (existing cycle-driver tests — the event-logger contract test needs extending)
  </read_first>
  <behavior>
    Engine emits ActionSkipped (test_engine.py — extend):
    - test_engine_emits_action_skipped_on_signal_gate: Diag triggering MODEM_RESET on a modem with rf_blocked=True; assert CycleResult.skipped contains exactly ONE ActionSkipped with reason=SkipReason.SIGNAL_BELOW_GATE, suppressed_action=ActionKind.MODEM_RESET, cause_category=IssueCategory.QMI (or whatever the issue category is), cause_detail=<original detail>.
    - test_engine_emits_action_skipped_on_same_action_backoff: state with last_action_monotonic_by_kind={SOFT_RESET: now-100}; Diag triggering SOFT_RESET; assert ActionSkipped with reason=SkipReason.SAME_ACTION_BACKOFF.
    - test_engine_emits_action_skipped_on_ladder_backoff: state with last_action_monotonic_by_kind={MODEM_RESET: now-50}; Diag triggering USB_RESET (a destructive action ≠ MODEM_RESET); assert ActionSkipped with reason=SkipReason.LADDER_BACKOFF (per Plan 04-04 ladder gate; 50s < 90s default).
    - test_engine_emits_action_skipped_on_exhausted_state: state with state="exhausted"; Diag triggering MODEM_RESET; assert ActionSkipped with reason=SkipReason.EXHAUSTED.
    - test_engine_emits_action_skipped_on_disconnected: state with present=False; Diag triggering any action; assert ActionSkipped with reason=SkipReason.DISCONNECTED.
    - test_engine_emits_action_skipped_on_maintenance: ctx.maintenance_active=True; Diag triggering MODEM_RESET; assert ActionSkipped with reason=SkipReason.MAINTENANCE. (Cheap actions still run during maintenance; assert NO ActionSkipped emitted for SET_APN.)
    - test_engine_emits_action_skipped_on_dry_run: ctx.config.dry_run=True; Diag triggering SOFT_RESET (no other gate fires); assert ActionSkipped with reason=SkipReason.DRY_RUN.
    - test_engine_emits_action_skipped_on_ladder_skip_exhausted: state with counters={SOFT_RESET: 3, MODEM_RESET: 2, USB_RESET: 1}; Diag with NOT_REGISTERED_SEARCHING; assert ActionSkipped with reason=SkipReason.EXHAUSTED (Plan 04-04 ladder.select_rung returned "skip:exhausted").
    - test_engine_skipped_list_empty_when_no_gate_fires: Diag triggering successful SOFT_RESET; assert CycleResult.skipped == [].
    - test_engine_preserves_planned_action_suppressed_flags_alongside_action_skipped: same fixture as test_engine_emits_action_skipped_on_signal_gate; assert PlannedAction.suppressed_by_signal_gate == True (back-compat preserved per CONTEXT B-04).

    Cycle driver flushes (test_cycle_driver.py — extend):
    - test_cycle_driver_appends_action_skipped_to_event_logger: build a CycleResult with `skipped=[ActionSkipped(...)]`; run cycle_driver's commit pipeline; assert RecordingEventLogger captured the ActionSkipped event AFTER the state-store write but BEFORE the next probe (RECOVERY_SPEC §8 ordering).
    - test_cycle_driver_does_not_skip_event_log_on_zero_skipped: CycleResult with skipped=[]; cycle_driver runs; recording event logger has no ActionSkipped events but ALL OTHER events (StateTransition etc.) are emitted as before — proves the empty list doesn't break the pipeline.
  </behavior>
  <action>
**Step A — Extend `src/spark_modem/policy/result.py`:**
Locate the CycleResult dataclass (or BaseWire / dataclass — read the file to determine the shape). Add a new field:
```python
skipped: list[ActionSkipped] = Field(default_factory=list)
```
Add the import `from spark_modem.wire.events import ActionSkipped` at the top.

If CycleResult is a frozen pydantic model, the default_factory lets cycle_driver code construct CycleResult with NO `skipped=` kwarg and get an empty list; existing call sites in test_engine.py / replay_harness don't break.

**Step B — Engine emits ActionSkipped on every skip path:**

1. Modify `_apply_gates_to_action` to return a SECOND value: a list of ActionSkipped events to emit alongside the PlannedAction. Update its return type:
   ```python
   def _apply_gates_to_action(
       action: ActionKind,
       state: ModemState,
       ctx: PolicyContext,
       who: WhoModem,
       cause_category: IssueCategory,    # NEW — needed for ActionSkipped fields
       cause_detail: IssueDetail,        # NEW
   ) -> tuple[PlannedAction, bool, list[ActionSkipped]]:
   ```

2. Build ActionSkipped events at every skip-path return:
   - **Disconnected** (line 211-222): construct `ActionSkipped(reason=SkipReason.DISCONNECTED, ...)` and return as the third tuple element.
   - **Maintenance** (line 224-235): construct `ActionSkipped(reason=SkipReason.MAINTENANCE, ...)`.
   - **Exhausted** (line 237-248): construct `ActionSkipped(reason=SkipReason.EXHAUSTED, ...)`.
   - **Soft-skip path** (lines 250-277): MAY emit MULTIPLE ActionSkipped (e.g. signal AND backoff both fire on the same action). Construct an ActionSkipped per fired suppression flag:
     - if `suppressed_signal`: append ActionSkipped(reason=SIGNAL_BELOW_GATE, ...)
     - if `suppressed_backoff` (need to distinguish: which gate fired? use the existing `gate_same_action_backoff` and `gate_ladder_backoff` calls — they already separate the two; the `suppressed_backoff` boolean on PlannedAction conflates them, but the engine can call the gates SEPARATELY):
       ```python
       suppressed_same = gate_same_action_backoff(state, action, ctx.clock, ctx.config)
       suppressed_ladder = (not suppressed_same) and gate_ladder_backoff(state, action, ctx.clock, ctx.config)
       ```
       Append ActionSkipped(reason=SAME_ACTION_BACKOFF) if `suppressed_same`; append ActionSkipped(reason=LADDER_BACKOFF) if `suppressed_ladder`.
     - if `suppressed_dry_run` AND would_execute would have been True (i.e. only dry_run blocked): append ActionSkipped(reason=DRY_RUN).
   - The PlannedAction suppression flags remain unchanged — they're set from the same booleans (back-compat per CONTEXT B-04).

3. Update the call-site in `run_cycle` (around line 137-145):
   ```python
   plan, would_execute, skipped_events = _apply_gates_to_action(
       action_or_skip,
       new_state,
       ctx,
       _snap_who(snap),
       issue.category,  # cause_category
       issue.detail,    # cause_detail
   )
   plans.append(plan)
   skipped_out.extend(skipped_events)   # accumulate per-modem skipped events
   if would_execute:
       counter_bump = action_or_skip
   ```
   Add `skipped_out: list[ActionSkipped] = []` at the top of `run_cycle` next to the existing `plans: list[PlannedAction] = []` and `transitions_out: list[StateTransition] = []`.

4. For the ladder `skip:exhausted` path from Plan 04-04 (engine.py per-modem path lines 130-145 after Plan 04-04's ladder integration): when ladder.select_rung returns "skip:exhausted", emit an ActionSkipped(reason=SkipReason.EXHAUSTED, suppressed_action=action_or_skip /* the BASE action */, cause_category=issue.category, cause_detail=issue.detail) alongside the PlannedAction with reason "skip:exhausted".

5. For the existing decision-table-level skip strings (e.g. `skip:requires_human`, `skip:no_card`, `skip:hardware`, `skip:carrier_denied` — Phase 2's `_DECISION_TABLE` returns these): these are NOT mapped to SkipReason values (they're upstream of the gate machinery; SkipReason is for GATE-failure paths). Do NOT emit ActionSkipped for these — the existing PlannedAction with `reason=action_or_skip` (e.g. "skip:requires_human") remains the source of truth. Document this exclusion in a comment.

6. Return `CycleResult(plans=..., transitions=..., new_states=..., new_globals=..., skipped=skipped_out)` in the per-modem path. The driver_reset short-circuit path (lines 76-106) uses the existing `CycleResult` shape with `skipped=[]` (no per-modem gates fire on driver_reset).

**Step C — Cycle driver flush:**
In `src/spark_modem/daemon/cycle_driver.py`, locate the event-logger dispatch loop (where `for transition in result.transitions: event_logger.append(transition)` is). Add a sibling loop AFTER the atomic state write per RECOVERY_SPEC §8:
```python
# Emit ActionSkipped events (Phase 4 B-04). Order: state write FIRST,
# event log SECOND -- if the daemon crashes between, a re-run reads the
# pre-action state and re-derives the gate decisions; events.jsonl is
# advisory, ModemState is authoritative.
for skipped in result.skipped:
    event_logger.append(skipped)
```

**Step D — Tests:**

Extend `tests/unit/policy/test_engine.py` with the 10 tests from `<behavior>`. Use the existing engine-test scaffolding (build Diag + prior_states + ctx, call run_cycle, inspect CycleResult).

Extend `tests/unit/daemon/test_cycle_driver.py` with the 2 cycle-driver tests from `<behavior>`. Use RecordingEventLogger from `tests/unit/actions/_helpers.py`.

Per CLAUDE.md: pure-engine policy preserved (no new I/O imports in engine.py or result.py); atomic state writes preserved (single model_copy per cycle from Plan 04-04 unchanged); RECOVERY_SPEC §8 ordering preserved (state write before event-log append).
  </action>
  <verify>
    <automated>cd /s/spark/modem-watchdog &amp;&amp; .venv/bin/pytest tests/unit/policy/test_engine.py tests/unit/daemon/test_cycle_driver.py tests/unit/wire/test_action_skipped_event.py -x &amp;&amp; .venv/bin/mypy --strict src/spark_modem/policy/ src/spark_modem/daemon/cycle_driver.py &amp;&amp; .venv/bin/ruff check src/spark_modem/policy/ src/spark_modem/daemon/cycle_driver.py &amp;&amp; bash scripts/lint_no_subprocess.sh</automated>
  </verify>
  <acceptance_criteria>
    - `grep -F 'skipped: list[ActionSkipped]' src/spark_modem/policy/result.py` returns ≥1 match
    - `grep -F 'from spark_modem.wire.events import ActionSkipped' src/spark_modem/policy/result.py` returns ≥1 match (or in policy/engine.py)
    - `grep -F 'list[ActionSkipped]' src/spark_modem/policy/engine.py` returns ≥1 match (the _apply_gates_to_action return type / skipped_out accumulator)
    - `grep -F 'reason=SkipReason.SIGNAL_BELOW_GATE' src/spark_modem/policy/engine.py` returns ≥1 match
    - `grep -F 'reason=SkipReason.SAME_ACTION_BACKOFF' src/spark_modem/policy/engine.py` returns ≥1 match
    - `grep -F 'reason=SkipReason.LADDER_BACKOFF' src/spark_modem/policy/engine.py` returns ≥1 match
    - `grep -F 'reason=SkipReason.EXHAUSTED' src/spark_modem/policy/engine.py` returns ≥1 match (at least once for hard-skip; possibly twice if ladder skip:exhausted path is separate)
    - `grep -F 'reason=SkipReason.DISCONNECTED' src/spark_modem/policy/engine.py` returns ≥1 match
    - `grep -F 'reason=SkipReason.MAINTENANCE' src/spark_modem/policy/engine.py` returns ≥1 match
    - `grep -F 'reason=SkipReason.DRY_RUN' src/spark_modem/policy/engine.py` returns ≥1 match
    - `grep -F 'for skipped in result.skipped' src/spark_modem/daemon/cycle_driver.py` returns ≥1 match (the dispatch loop)
    - `grep -F 'event_logger.append(skipped)' src/spark_modem/daemon/cycle_driver.py` returns ≥1 match
    - `grep -F 'suppressed_by_signal_gate' src/spark_modem/policy/engine.py` returns ≥1 match (PlannedAction back-compat flags PRESERVED — not removed)
    - `pytest tests/unit/policy/test_engine.py -x` exits 0 with the 10 new tests passing
    - `pytest tests/unit/daemon/test_cycle_driver.py -x` exits 0 with the 2 new tests passing
    - `pytest tests/unit/policy/test_engine_driver_reset.py -x` exits 0 (no regression on the Plan 04-03 predicate tests)
    - `mypy --strict src/spark_modem/policy/ src/spark_modem/daemon/cycle_driver.py` exits 0
    - `ruff check src/spark_modem/policy/ src/spark_modem/daemon/cycle_driver.py` exits 0
    - `bash scripts/lint_no_subprocess.sh` exits 0 (engine remains pure)
    - Full unit suite: `pytest -m "unit and not linux_only and not hil" -x` exits 0 (no regression — replay harness against Phase 2 fixtures still passes because PlannedAction.suppressed_* flags are unchanged)
  </acceptance_criteria>
  <done>
    Engine emits ActionSkipped on all 7 skip-reason paths; CycleResult.skipped accumulator threaded through; cycle_driver flushes to event_logger after state write per RECOVERY_SPEC §8; PlannedAction.suppressed_* flags preserved for replay-harness back-compat; full test suite green.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| daemon → events.jsonl writer | New ActionSkipped events flow through the existing EventLogWriter (Plan 03-04 reopener + Plan 02-08 webhook coupling); no new write surface |
| Replay harness consuming Phase 2 fixtures | New ActionSkipped events are EMITTED ALONGSIDE existing PlannedAction.suppressed_* flags; Plan 02-10 replay harness is unchanged — reads suppressed_* flags as before |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-05-01 | T (Tampering) | Forged ActionSkipped event in events.jsonl | accept | events.jsonl is owned by the daemon (root, 0o640 file mode per Plan 02-07); attacker with write access already owns the daemon. Out of scope per NFR-30 |
| T-04-05-02 | I (Information disclosure) | cause_category + cause_detail leak in events.jsonl | accept | These are closed-enum values (IssueCategory + IssueDetail) — no PII / signal values / bytes. Same disclosure surface as existing StateTransition.cause field |
| T-04-05-03 | D (Denial of service) | events.jsonl size growth from emitting ActionSkipped per gate-failure | mitigate | Events emit at most ONCE per modem per cycle (one per gate path). With ~10 cycles/min and 4 modems, worst case is 40 ActionSkipped events/min during sustained gate failure. logrotate Plan 03-04 handles rotation; size bounded by retention policy |
| T-04-05-04 | E (Elevation) | Replay harness back-compat regression | mitigate | PlannedAction.suppressed_by_* flags PRESERVED per CONTEXT B-04 explicit guidance; replay harness reads only those flags from Phase 2 fixtures; Plan 02-10's harness contract unchanged. Test gate: `pytest tools/replay_harness.py-related tests` (or whatever the regression harness is — locate via `grep replay_harness tests/`) must stay green |
| T-04-05-05 | R (Repudiation) | Decision-table-level skip strings (skip:requires_human / skip:no_card / etc.) NOT mapped to SkipReason | accept | Documented in code comment: SkipReason is for GATE-failure paths only. Decision-table skips are upstream (no action selected); the PlannedAction with reason="skip:requires_human" is sufficient audit trail |
</threat_model>

<verification>
- All Plan 04-05 task `<verify>` commands pass.
- `pytest -m "unit and not linux_only and not hil" -x` exits 0 (full unit suite — ≥17 new tests across 4 test files).
- `mypy --strict src/spark_modem/` exits 0.
- `ruff check src/spark_modem/ tests/` exits 0.
- `bash scripts/lint_no_subprocess.sh` exits 0.
- `grep -F 'PlannedAction.suppressed_by_signal_gate' tools/replay_harness.py` (or whatever the harness file is): if it exists, returns ≥1 match (back-compat preserved).
- Phase 2 replay harness regression test (whatever the test file is — find via `grep replay_harness tests/ -r --include='*.py' -l`): exits 0.
</verification>

<success_criteria>
- `wire/enums.py:SkipReason` is a closed StrEnum with exactly 7 values matching the canonical strings.
- `wire/enums.py:EventKind.ACTION_SKIPPED = "action_skipped"`.
- `wire/events.py:ActionSkipped` is a BaseWire-derived event variant in the discriminated `Event` union.
- `policy/result.py:CycleResult.skipped: list[ActionSkipped]` field with default empty list.
- Engine emits ActionSkipped on all 7 skip-reason paths (signal, same_action, ladder, exhausted (×2 — hard-skip + ladder), disconnected, maintenance, dry_run).
- Engine PRESERVES PlannedAction.suppressed_* flags (replay-harness back-compat per CONTEXT B-04).
- `daemon/cycle_driver.py` flushes CycleResult.skipped to event_logger AFTER the atomic state write (RECOVERY_SPEC §8 ordering).
- ≥17 new unit tests across 4 files; all green.
- CLAUDE.md invariants honored: pure-engine policy preserved (no new I/O imports); atomic state writes preserved; tagged-union discriminator dispatches correctly via pydantic v2 discriminated union.
- Full Phase 1+2+3+04-{01,02,03,04} regression suite stays green.
</success_criteria>

<output>
After completion, create `.planning/phases/04-destructive-actions-hil/04-05-SUMMARY.md`
documenting: files created (test_action_skipped_event.py), files extended
(enums, events, result, engine, cycle_driver, test_events, test_engine,
test_cycle_driver), the SkipReason enum's 7 values, the dual-emit contract
(ActionSkipped + PlannedAction.suppressed_* flags both emitted for back-compat
horizon), the 10 engine emit paths, and the cycle-driver flush ordering per
RECOVERY_SPEC §8. Note that decision-table-level skip strings
(skip:requires_human / skip:no_card / etc.) are deliberately NOT mapped to
SkipReason — they're upstream of gate failure.
</output>
