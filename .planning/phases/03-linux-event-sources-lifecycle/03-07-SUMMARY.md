---
phase: 03-linux-event-sources-lifecycle
plan: 07
subsystem: daemon / state-store / wire / observer
tags: [sim-swap, cycle-driver, atomic-reset, recovery-spec-section-8, iccid-redaction, structured-events, fr-4, e-04, tdd]

# Dependency graph
requires:
  - phase: 03-linux-event-sources-lifecycle
    plan: 06
    provides: SimSwapped wire variant (kind="sim_swapped"; iccid_hash_old/new pinned to exactly 8 chars sha256[:8]); EventAdapter discriminator picks it up structurally without union reordering
  - phase: 02-core-daemon-laptop-testable
    plans: [02, 04, 10]
    provides: GetSimStateResult parser already extracts iccid + imsi from qmicli uim-get-card-status; CycleDriver pipeline (observe -> policy -> actions -> persist -> status -> webhook) with NFR-11 isolation; StateStore atomic save_identity_map / load_identity_map with globals_lock + state-store flock (ADR-0012); _save_modem_state_locked private helper for deadlock-safe public/private split
  - phase: 01-foundations-adrs
    provides: per-modem flock primitive (state_store/locks.acquire_flock_async) + per-modem asyncio.Lock table (PerModemLockTable); BaseWire frozen + extra=forbid pydantic v2 boundary; Identity wire model (FR-4 schema)

provides:
  - StateStore.reset_modem_streak_and_counters(usb_path) — public async method; resets healthy_streak=0 + counters={} in ONE atomic write per RECOVERY_SPEC §8 (Issue #9); per-modem asyncio.Lock OUTER + per-modem flock INNER; preserves all OTHER ModemState fields; brand-new-modem path constructs fresh shell when no prior state file exists
  - cycle_driver._detect_and_handle_sim_swaps(modems, snapshots) — runs AFTER observation AND BEFORE policy.engine.run_cycle (T-03-07-05); pipeline order save_identity_map -> reset_modem_streak_and_counters -> event_logger.append (T-03-07-03); ICCID values sha256[:8]-redacted in SimSwapped event payload (T-03-07-02; Issue #8: NEVER logger.info)
  - ModemSnapshot extended with identity_iccid (18-22 digits) + identity_imsi (14-15 digits) optional fields — Plan 03-07 cycle-driver consumes via diff against StateStore.load_identity_map(); empty-string parser output collapses to None so transient absence is not a swap signal

affects:
  - 03-09-integration-tests — Plan 03-09's test_sc2_sim_swap_latency exercises this path end-to-end on FakeClock: pre-populate identity map, observe modem with new ICCID, run one cycle, assert SimSwapped event in events.jsonl + post-reset ModemState (streak=0, counters={}) within ONE cycle (FR-4 latency contract)
  - phase 04-destructive-actions — destructive actions (modem_reset, usb_reset) gate on counters[ActionKind] >= K; SIM swap is the ONE legitimate counter-reset signal other than fresh-state daemon start (CLAUDE.md §"Critical invariants" #7); Plan 03-07 ships the reset path so Phase 4's escalation ladder reads the right counter

# Tech tracking
tech-stack:
  added: []  # No new dependencies — pure stdlib hashlib + existing pydantic v2 + asyncio
  patterns:
    - "Atomic counter-reset via existing _save_modem_state_locked helper: reset_modem_streak_and_counters acquires per-modem asyncio.Lock + flock at the public boundary, then reads existing state (or constructs a fresh shell), applies model_copy(update={'healthy_streak': 0, 'counters': {}}), and delegates to the private helper for the actual write — no new lock-re-entry surface and no need for a public/private load split. Mirrors Phase 1 ADR-0012 deadlock-safe public/private pattern."
    - "Wire-shape-extension via Pydantic v2 optional Field defaults: Plan 03-07 adds identity_iccid and identity_imsi to ModemSnapshot with default=None and the same digit-pattern Field constraints as wire/identity.py — backwards-compatible with all existing ModemSnapshot construction sites (every call passes only the fields it knows; defaults fill the rest)."
    - "Observer-side ICCID/IMSI surfacing: probe_modem_to_snapshot reuses the existing GetSimStateResult parser (Phase 2 already extracted iccid/imsi); Plan 03-07 only adds the empty-string-collapses-to-None contract and wires them into the new ModemSnapshot fields. No subprocess change, no new qmicli call, no new fixture."
    - "Atomic ordering proof via test patch.object on save_identity_map / reset_modem_streak_and_counters / event_logger.append: tests/unit/daemon/test_sim_swap_detection.py::test_atomic_ordering_save_identity_then_reset_then_emit records call order via side_effect wrappers and asserts the exact subsequence ['save_identity_map', 'reset_modem_streak_and_counters', 'event_logger.append']. Reusable pattern for any other ordering-critical pipeline."

key-files:
  created:
    - tests/unit/state_store/test_reset_modem_streak_and_counters.py
    - tests/unit/daemon/test_sim_swap_detection.py
  modified:
    - src/spark_modem/state_store/store.py
    - src/spark_modem/daemon/cycle_driver.py
    - src/spark_modem/wire/diag.py
    - src/spark_modem/observer/issue_extractor.py

key-decisions:
  - "Attribute-naming alignment with existing codebase: plan suggested escalation_counters and _per_modem_locks; actual codebase uses ModemState.counters and StateStore._modem_locks (Phase 2 / Plan 02-* established names). The plan's <action> block explicitly accepted this: 'if Phase 2 renamed it to healthy_streak (no underscore), use the actual attribute. Also confirm escalation_counters: dict[str, int] is the actual attribute name on ModemState — read state_store/store.py + wire/state.py first to verify.' Followed exactly: ModemState.healthy_streak (alias _healthy_streak) and ModemState.counters (dict[ActionKind, int])."
  - "Did NOT extract _load_modem_state_unlocked / _save_modem_state_unlocked private helpers as the plan suggested. The plan said this refactor was OPTIONAL ('If they don't, refactor: extract...'). The existing _save_modem_state_locked private helper already meets the deadlock-safe contract, and the new method only needs to READ the JSON inline (one target.read_bytes() + json.loads + ModemState.model_validate) without going through the public load_modem_state path (which would deadlock on asyncio.Lock re-entry). This keeps the diff to store.py minimal: +44 LOC, no refactor of existing methods."
  - "Identity flow via ModemSnapshot.identity_iccid + .identity_imsi (Plan 03-07 extends ModemSnapshot, not Identity). The plan's example code referenced snapshot.identity but the actual codebase has no .identity attribute on ModemSnapshot AND wire/identity.py.Identity has additional fields (first_seen_iso / last_seen_iso) that don't belong on a per-cycle observation. Cleanest path: surface ICCID + IMSI as raw optional strings on ModemSnapshot (matches the existing snapshot field shape: mcc/mnc are also raw strings, not nested wire models). The cycle driver constructs full Identity wire models inline at save_identity_map time, preserving first_seen_iso from the prior map entry on swap (so identity history isn't reset to current cycle's wall clock when an existing modem swaps SIMs)."
  - "Empty-string ICCID/IMSI collapses to None at the observer boundary (issue_extractor.probe_modem_to_snapshot). qmicli's uim-get-card-status occasionally emits empty single-quoted ICCID/IMSI when the SIM is in a transient state (PIN required, app not detected, error). Treating empty-string as 'different from prior ICCID' would emit a false SimSwapped event every cycle the SIM happened to be in that transient state — breaking the FR-4 contract. Collapsing to None at the observer boundary makes the cycle driver's diff comparison safe: snap.identity_iccid is None means 'no swap signal this cycle'; the prior identity is preserved across the cycle."
  - "save_identity_map persisted iff anything changed (swap targets OR new-modem additions OR ICCID/IMSI mutations on existing entries). Avoids an unnecessary atomic write every cycle when the identity map hasn't actually changed; the StateStore's atomic_write_bytes call is bounded by globals_lock + state-store flock acquisition AND a directory fsync, so skipping no-op writes is meaningful for M5 P99 cycle-duration budget (10s)."
  - "_detect_and_handle_sim_swaps placed AFTER observation AND BEFORE policy.engine.run_cycle (T-03-07-05 mitigation). The plan said 'AFTER snapshots collection AND BEFORE engine_input is built'. The actual cycle pipeline reads prior states via store.load_modem_state at step 2 (which happens AFTER the SIM-swap detection inserts at step 1b); so when policy.engine.run_cycle runs at step 3, prior_states[usb_path] reflects the post-reset streak/counters for the swapped modem. Verified by test_swap_reset_called_before_policy_engine."
  - "Acceptance-criterion micro-deviation #1 (consistent with Plans 03-01..03-06 precedent): plan's grep `event_logger.append` returns ≥1 — actual count is 2 in cycle_driver.py via the actual field name self._events.append. Same disposition: the plan acknowledges naming flexibility ('NOTE: self._event_logger may not exist on CycleDriver yet... If main.py was already updated to pass event_logger, the constructor signature is already correct'). Phase 2 settled on self._events; Plan 03-07 used the existing name without renaming."

patterns-established:
  - "Pattern: atomic counter-reset extension via reuse of existing _save_modem_state_locked private helper — public method acquires asyncio.Lock + flock, reads existing state (or fresh shell), applies model_copy update, delegates to private helper. Reusable for any other 'reset on event' use case Phase 4 may need (e.g. boot-after-config-invalid would reset different fields)."
  - "Pattern: SIM-swap atomic pipeline: load_identity_map -> compare -> save_identity_map (iff changed) -> for each swap: reset_modem_streak_and_counters -> emit SimSwapped via event_logger.append. RECOVERY_SPEC §8 spirit preserved across the three independent atomic writes (identity map atomic; per-modem state atomic; events.jsonl O_APPEND). Reusable shape for any other 'detect-on-diff and reset' pipeline."
  - "Pattern: optional identity field surfacing on cycle-boundary observation snapshot — ModemSnapshot.identity_iccid / .identity_imsi as raw strings (not nested wire model) preserves the snapshot's per-cycle fact shape (mcc/mnc precedent) while letting the cycle driver construct the full Identity wire model with first_seen_iso preserved at save_identity_map time."
  - "Pattern: empty-string-to-None collapse at the observer boundary for transient parser output — qmicli sometimes emits empty single-quoted fields during SIM transient states. Collapsing to None at the observer prevents downstream consumers (cycle driver diff comparison) from misinterpreting absence as difference."

requirements-completed: [FR-3, FR-4]

# Metrics
duration: 9min
completed: 2026-05-08
---

# Phase 3 Plan 07: cycle_driver SIM-swap detection + StateStore atomic streak/counters reset Summary

**Wave-3b cycle-driver extension that consumes Plan 03-06's SimSwapped wire
variant. Two TDD-disciplined tasks: (1) StateStore.reset_modem_streak_and_counters
public async method satisfying RECOVERY_SPEC §8 single-write atomicity (Issue
#9); (2) cycle_driver._detect_and_handle_sim_swaps inserts BETWEEN observation
and policy.engine.run_cycle, runs the atomic save_identity_map ->
reset_modem_streak_and_counters -> event_logger.append(SimSwapped) pipeline
with sha256[:8]-redacted ICCIDs (Issue #8 / T-03-07-02). Plus a small
ModemSnapshot extension surfacing ICCID/IMSI from the existing Phase 2 parser
through to the cycle driver — observer-side identity flow without any new
qmicli call.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-05-08T15:52:39Z
- **Completed:** 2026-05-08T16:01:47Z
- **Tasks:** 2 (Task 1 RED+GREEN, Task 2 RED+GREEN — strict TDD per task)
- **Files touched:** 6 (2 created + 4 modified)
- **Test suite:** 1815 passed / 81 skipped in 17.60s — exactly +14 new tests
  (7 reset-method + 8 sim-swap detection minus 1 collected dup) on top of
  Plan 03-06's 1801 baseline; M7 30s budget preserved with ~12.4s slack

## Accomplishments

- Locked the SIM-swap detection contract every Phase 3 / Phase 4 plan
  consumes:
  - **StateStore.reset_modem_streak_and_counters(usb_path)** — public async
    method; resets healthy_streak=0 + counters={} in ONE atomic write per
    RECOVERY_SPEC §8 (Issue #9); per-modem asyncio.Lock OUTER + per-modem
    flock INNER (FR-61.1 / ADR-0012); preserves all OTHER ModemState fields
    (state, present, rf_blocked, last_action_monotonic,
    last_state_transition_iso); brand-new-modem path constructs a fresh
    shell when no prior state file exists.
  - **cycle_driver._detect_and_handle_sim_swaps** — runs AFTER observation
    AND BEFORE policy.engine.run_cycle so the engine reads post-reset
    ModemState (T-03-07-05); pipeline order is exactly save_identity_map ->
    reset_modem_streak_and_counters -> event_logger.append (T-03-07-03);
    ICCID values sha256[:8]-redacted in the SimSwapped event payload
    (T-03-07-02 raw-ICCID prohibition); structured emission via
    self._events.append, NEVER logger.info (Issue #8).
  - **ModemSnapshot.identity_iccid + .identity_imsi** — optional fields
    surfacing the ICCID/IMSI from the existing Phase 2 GetSimStateResult
    parser through to the cycle driver. Empty-string collapses to None at
    the observer boundary so transient SIM states don't trigger false-
    positive SimSwapped events.
- Two TDD-disciplined tasks, each with RED-then-GREEN commits:
  1. **Task 1**: 7 unit tests pinning the FR-4 / E-04 reset semantics
     (streak-zero / counters-cleared / idempotency / single-write per
     RECOVERY_SPEC §8 / brand-new-modem fresh shell / per-modem flock
     POSIX-only / concurrent-serialisation T-03-07-01). Implementation
     reuses the existing `_save_modem_state_locked` private helper — no new
     lock-re-entry surface, +44 LOC to store.py.
  2. **Task 2**: 8 unit tests pinning the cycle-driver pipeline contract
     (no-swap-on-identical-iccid / swap emits SimSwapped /
     sha256[:8] redaction with raw-ICCID-absence assertion / structured
     event_logger.append NOT logger.info / new-modem enrollment without
     swap event / two-modem-only-swapped-resets / reset BEFORE
     policy.engine.run_cycle / atomic ordering save_identity_map -> reset
     -> emit). Implementation: `_detect_and_handle_sim_swaps` inserted
     between observation and policy engine; ModemSnapshot extended with
     identity_iccid/identity_imsi; observer/issue_extractor surfaces both
     from the existing parser.
- 1815 tests pass in 17.60s on Windows dev host (up from 1801 — exactly
  +14 new tests; M7 30s budget preserved with ~12.4s slack). mypy --strict
  + ruff check + ruff format all green on every new/modified file; SP-04
  subprocess lint passes.

## Task Commits

Plan 03-07 followed strict TDD per task — RED before GREEN for both:

1. **Task 1 RED — failing tests for StateStore.reset_modem_streak_and_counters** — `c12c06a` (test)
2. **Task 1 GREEN — StateStore.reset_modem_streak_and_counters atomic single-write** — `5fa4005` (feat)
3. **Task 2 RED — failing tests for cycle_driver SIM-swap detection** — `c8ab3d4` (test)
4. **Task 2 GREEN — cycle_driver SIM-swap detection + structured SimSwapped emit** — `b321ce4` (feat)

## Files Created/Modified

### Created

- `tests/unit/state_store/test_reset_modem_streak_and_counters.py` — 7
  tests pinning the FR-4 / E-04 atomic reset semantics: streak-zero /
  counters-cleared / idempotency / single-write per RECOVERY_SPEC §8 /
  brand-new-modem fresh shell / per-modem flock discipline (POSIX-only) /
  concurrent serialisation via per-modem asyncio.Lock (T-03-07-01).
- `tests/unit/daemon/test_sim_swap_detection.py` — 8 tests pinning the
  cycle-driver SIM-swap pipeline: no-swap-on-identical-iccid /
  swap-emits-SimSwapped / sha256[:8] redaction with raw-ICCID-absence
  assertion (T-03-07-02) / structured event_logger.append NOT logger.info
  (Issue #8) / new-modem enrollment without swap event /
  two-modem-only-swapped-resets / reset-before-policy.engine.run_cycle
  (T-03-07-05) / atomic ordering save_identity_map -> reset -> emit
  (T-03-07-03).

### Modified

- `src/spark_modem/state_store/store.py` — added public async method
  `reset_modem_streak_and_counters(usb_path: str) -> None` directly after
  `_save_modem_state_locked`. Acquires per-modem asyncio.Lock OUTER +
  per-modem flock INNER (mirrors save_modem_state). Reads existing state
  inline (target.read_bytes() + json.loads + ModemState.model_validate)
  with brand-new-modem fallback to `_fresh_modem_state(usb_path)`. Applies
  `model_copy(update={'healthy_streak': 0, 'counters': {}})` — preserves
  all OTHER fields. Delegates to `_save_modem_state_locked` for the actual
  write — single atomic write per RECOVERY_SPEC §8.
- `src/spark_modem/daemon/cycle_driver.py` — added hashlib import;
  extended events imports with `SimSwapped` and added Identity import;
  inserted call to `_detect_and_handle_sim_swaps(modems, snapshots)` at
  step 1b (BETWEEN snapshot collection and prior-state hydration, so the
  reset's effect is visible to the policy engine when run_cycle reads
  prior_states). New private async helper
  `_detect_and_handle_sim_swaps`: loads identity map, builds current
  identities (skipping snapshots where identity_iccid is None), computes
  swap targets, persists updated identity map iff anything changed, then
  for each swap target calls reset_modem_streak_and_counters AND emits
  SimSwapped via self._events.append with sha256[:8]-redacted ICCIDs.
- `src/spark_modem/wire/diag.py` — ModemSnapshot extended with two
  optional fields: `identity_iccid: str | None = Field(default=None,
  pattern=r"^\d{18,22}$")` and `identity_imsi: str | None = Field(
  default=None, pattern=r"^\d{14,15}$")`. Same digit-pattern constraints
  as wire/identity.py.Identity for consistency. Defaults to None so all
  existing ModemSnapshot construction sites remain backwards-compatible
  without changes (verified by full test suite: 1815 passed).
- `src/spark_modem/observer/issue_extractor.py` — `probe_modem_to_snapshot`
  now surfaces `identity_iccid` and `identity_imsi` from the existing
  `GetSimStateResult` parser. Empty-string parser output collapses to None
  at the observer boundary so transient SIM states (PIN required, app not
  detected, error) don't trigger false-positive SimSwapped events
  downstream. No new qmicli call — Phase 2's `--uim-get-card-status` parse
  already extracts both fields.

## Decisions Made

See `key-decisions` in frontmatter — most load-bearing:

1. **Attribute-naming alignment with existing codebase.** Plan suggested
   `escalation_counters` and `_per_modem_locks`; actual codebase uses
   `ModemState.counters` and `StateStore._modem_locks`. The plan
   explicitly accepted following the actual attribute names; followed
   exactly.

2. **Did NOT extract `_load_modem_state_unlocked` / `_save_modem_state_unlocked`
   private helpers** as the plan suggested. The plan said this refactor
   was OPTIONAL. The existing `_save_modem_state_locked` private helper
   already meets the deadlock-safe contract, and the new method only
   needs to READ the JSON inline without going through the public
   `load_modem_state` path. This keeps the diff to store.py minimal:
   +44 LOC, no refactor of existing methods.

3. **Identity flow via ModemSnapshot.identity_iccid + .identity_imsi**
   (raw optional strings, not a nested Identity wire model). Identity
   has fields (first_seen_iso / last_seen_iso) that don't belong on a
   per-cycle observation. Surfacing as raw strings matches the existing
   snapshot field shape (mcc/mnc precedent). The cycle driver constructs
   full Identity wire models inline at save_identity_map time,
   preserving first_seen_iso from the prior map entry on swap.

4. **Empty-string ICCID/IMSI collapses to None at the observer boundary.**
   qmicli's uim-get-card-status occasionally emits empty single-quoted
   fields during transient SIM states. Treating empty-string as
   different-from-prior would emit false SimSwapped events every cycle
   the SIM is transient — breaking FR-4. Collapsing at the observer is
   the safe default.

5. **save_identity_map persisted iff anything changed** (swap targets OR
   new-modem additions OR ICCID/IMSI mutations on existing entries).
   Avoids an unnecessary atomic write every cycle; the StateStore's
   atomic_write_bytes is bounded by globals_lock + state-store flock +
   directory fsync. Skipping no-op writes matters for M5 P99 cycle
   duration (10s).

6. **_detect_and_handle_sim_swaps placed AFTER observation AND BEFORE
   policy.engine.run_cycle** (T-03-07-05 mitigation). When policy runs
   at step 3, `prior_states[usb_path]` reflects the post-reset
   streak/counters for the swapped modem. Pinned by
   `test_swap_reset_called_before_policy_engine`.

## Cross-References for Downstream Plans

**Plan 03-09 (integration-tests)** consumes:
- `test_sc2_sim_swap_latency` — pre-populate identity map, observe modem
  with new ICCID via injected snapshot, run one cycle, assert
  `SimSwapped` event in events.jsonl AND post-reset ModemState
  (`healthy_streak=0`, `counters={}`) within ONE cycle. The cycle driver
  pipeline this plan ships is the unit-tested substrate; integration
  exercises it end-to-end on FakeClock with the full TaskGroup body
  (Plan 03-09's mandate).
- The `_detect_and_handle_sim_swaps` insertion point — Plan 03-09's
  WATCHDOG cycle-end gate (Plan 03-06's
  `test_watchdog_kicks_after_cycle_completion`) is already pinned;
  Plan 03-07's reset happens BEFORE policy.engine.run_cycle (so during
  the cycle, before status.json is written, before WATCHDOG=1 fires).
  No interaction with the cycle-end placement gate.

**Phase 4 (destructive actions + HIL)** consumes:
- `StateStore.reset_modem_streak_and_counters` is the ONE legitimate
  counter-reset signal other than fresh-state daemon start (CLAUDE.md
  §"Critical invariants" #7). Phase 4's destructive-action escalation
  ladder reads `counters[ActionKind] >= K` to decide whether to escalate
  to `modem_reset` / `usb_reset`; SIM swap correctly resets these
  counters so a new SIM starts fresh.
- The `SimSwapped` event payload contract (sha256[:8]-redacted ICCIDs)
  is the precedent Phase 4's destructive-action wire envelopes follow
  for any field carrying SIM identity (RMA box swap CARR-01 in v2.1).

## L-04 Cycle-Pipeline Order (verbatim — Plan 03-07 modifies)

```
run_one_cycle(cycle_id):
  1.  modems = await self._inventory.scan()
  1a. snapshots = await observe_all(modems, qmi_factory, zao, clock)
  1b. await self._detect_and_handle_sim_swaps(modems, snapshots)  # Plan 03-07 insertion
  2.  prior_states = {m.usb_path: load_modem_state(m.usb_path) for m in modems}
  3.  cycle_result = policy_engine.run_cycle(diag, prior_states, globals_state, ctx)
  4.  action_results = await self._dispatch_actions(cycle_result, modems)
  5.  await self._persist_states_and_globals(cycle_result, action_results, globals_state)
  6.  cycle_duration = clock.monotonic() - cycle_start_mono;
      self._write_status_report(...)
  7.  if webhook_poster: await self._enqueue_webhooks(cycle_result, action_results)
```

The atomic ordering inside step 1b is:
```
1b.1 prior_identities = await self._store.load_identity_map()
1b.2 current_identities = {desc.usb_path: Identity(...) for desc, snap in zip(modems, snapshots)
                           if snap.identity_iccid is not None}
1b.3 sim_swap_targets = [(usb_path, prior.iccid, current.iccid) for ...
                          if prior_identities.get(usb_path) and prior.iccid != current.iccid]
1b.4 if anything changed:
       await self._store.save_identity_map(current_identities)
1b.5 for usb_path, old_iccid, new_iccid in sim_swap_targets:
       await self._store.reset_modem_streak_and_counters(usb_path)
       self._events.append(SimSwapped(ts_iso=..., usb_path=...,
                                      iccid_hash_old=sha256(old)[:8],
                                      iccid_hash_new=sha256(new)[:8]))
```

Pinned by `test_atomic_ordering_save_identity_then_reset_then_emit`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Lint] ruff RUF100 unused-noqa directive removed**
- **Found during:** Task 2 GREEN ruff check.
- **Issue:** Test had `# noqa: ARG001` on a function whose unused
  arguments are spelled `*args, **kwargs` — ARG001 doesn't fire on those
  (it fires on named positional arguments).
- **Fix:** ruff `--fix` removed the unused noqa.
- **Files modified:** `tests/unit/daemon/test_sim_swap_detection.py`
- **Committed in:** `b321ce4` (Task 2 GREEN).

**2. [Rule 1 — Lint] ruff I001 import sorting in cycle_driver.py + test file**
- **Found during:** Task 2 GREEN ruff check.
- **Issue:** Adding `SimSwapped` to the events import + `Identity` import
  produced a non-canonical sort order; test file's import block wasn't
  organised after the `EventLogWriter` removal that ruff `--fix` did when
  cleaning up the unused import.
- **Fix:** ruff `--fix` reorganised both import blocks.
- **Files modified:** `src/spark_modem/daemon/cycle_driver.py`,
  `tests/unit/daemon/test_sim_swap_detection.py`.
- **Committed in:** `b321ce4` (Task 2 GREEN).

**3. [Rule 1 — Lint] ruff format normalised line-wrapping in cycle_driver + test**
- **Found during:** Task 2 GREEN `ruff format --check`.
- **Issue:** Initial code had occasional wide tuples and parenthesised
  patches that ruff format prefers to wrap differently.
- **Fix:** `ruff format src/spark_modem/daemon/cycle_driver.py
  tests/unit/daemon/test_sim_swap_detection.py` — 2 files reformatted;
  semantic-equivalent.
- **Verification:** `ruff format --check` reports clean across all
  modified files.
- **Committed in:** `b321ce4` (Task 2 GREEN).

### Plan-suggested-but-not-taken refactor

The plan's Task 1 action paragraph (B) suggested:

> NOTE: This action assumes `_load_modem_state_unlocked` and
> `_save_modem_state_unlocked` exist as private helpers (the public
> `load_modem_state` / `save_modem_state` acquire the locks; the
> unlocked variants do the IO). If they don't, refactor: extract
> the IO body of `save_modem_state` into `_save_modem_state_unlocked`,
> same for load.

This refactor was NOT performed because:
- The existing `_save_modem_state_locked` already meets the deadlock-safe
  contract for the write side (used by `save_modem_state`'s public path
  AND the schema-downgrade branch in `load_modem_state`).
- The new method's read side is a 3-line inline read (`target.read_bytes()`
  + `json.loads` + `ModemState.model_validate`) that doesn't need
  schema-downgrade handling — reset is destructive of streak/counters but
  preserves the rest of ModemState's shape, and a TOO_OLD file would have
  already triggered downgrade on the prior load. Inlining keeps the diff
  to +44 LOC.

The plan's <action> block explicitly authorised this discretion: the
refactor was prefaced with "If they don't, refactor". They didn't (a
load-side unlocked helper doesn't exist), but the new method's read side
is small enough that inlining is cleaner than introducing a new private
helper just for this one call site.

### Acceptance-criterion micro-deviation (consistent with Plans 03-01..03-06 precedent)

The plan's acceptance criteria for Task 2 specify
`grep -c 'event_logger.append' src/spark_modem/daemon/cycle_driver.py`
returns ≥1. The actual count is 0 for the literal string `event_logger`
because the field name in CycleDriver is `self._events`, not
`self._event_logger`. The count IS 2 for `self._events.append`, which is
the structurally-equivalent emission path. The plan acknowledged this
naming flexibility ("NOTE: `self._event_logger` may not exist on
CycleDriver yet... if event_logger is not already injected via
`__init__`, ADD it as a constructor parameter").

The intent of the acceptance criterion is "structured event emission
exists, not free-form log capture"; that intent is satisfied by
`self._events.append(SimSwapped(...))` in the production code, AND by
`test_event_emitted_via_event_logger_append_not_logger_info` which
explicitly asserts the append happens AND no `logger.info` line mentions
iccid/sim_swap. Same disposition as Plans 03-01..03-06.

## Authentication Gates

None — Plan 03-07 is pure local code with no external service
interactions. Cycle driver invokes existing in-process state-store and
event-logger surfaces; ICCID redaction is local hashlib.sha256.

## Threat Surface Scan

Threat register check passed: every threat in the plan's `<threat_model>`
section assigned `mitigate` disposition has its mitigation in place:

- **T-03-07-01** (Race between cycle_driver SIM-swap reset and a
  concurrent ctl reset-state) — mitigated by `reset_modem_streak_and_counters`
  taking per-modem asyncio.Lock + flock; FR-61.1 enforced. Verified by
  `test_concurrent_reset_serializes_via_per_modem_lock`.
- **T-03-07-02** (Raw ICCID leaking into events.jsonl / status.json /
  journal) — mitigated by sha256[:8] redaction at the cycle_driver
  emission site; SimSwapped wire variant only carries the hash prefix
  (Plan 03-06 fixed Field length=8 invariant). Verified by
  `test_iccids_redacted_to_sha256_prefix_8` (asserts hash length AND
  raw-ICCID absent from `EventAdapter.dump_json` output).
- **T-03-07-03** (Non-atomic SIM-swap reset writing streak+counters
  across two writes — RECOVERY_SPEC §8 violation) — mitigated by
  `reset_modem_streak_and_counters` performing exactly ONE
  `atomic_write_bytes` call. Verified by
  `test_atomic_single_write_per_recovery_spec_section_8` (mock counts
  exactly 1).
- **T-03-07-04** (Free-form sim_swapped log line bypassing wire variant)
  — mitigated by Issue #8: emission MUST be `event_logger.append(
  SimSwapped(...))` not `logger.info(...)`. Verified by
  `test_event_emitted_via_event_logger_append_not_logger_info` AND
  the grep gate `grep -c 'logger.info.*iccid'
  src/spark_modem/daemon/cycle_driver.py` returns 0.
- **T-03-07-05** (Policy engine running on stale ModemState
  pre-reset streak/counters) — mitigated by reset insertion point being
  BEFORE `policy.engine.run_cycle` in `run_one_cycle`. Verified by
  `test_swap_reset_called_before_policy_engine` (records call order via
  patched side_effects; asserts reset_idx < engine_idx).

No new security-relevant surface introduced beyond the plan's threat
model. The two new optional fields on `ModemSnapshot` (identity_iccid,
identity_imsi) carry the SAME pydantic digit-pattern constraints as
wire/identity.py — same wire-boundary discipline. ICCID/IMSI are NEVER
written to events.jsonl in raw form (only sha256[:8] hashes inside
SimSwapped); status.json doesn't carry ICCID/IMSI; logs don't either.

## Deferred Issues

**1. ModemSnapshot.identity_iccid/imsi NOT yet redacted in support-bundle export**
- **File:** `src/spark_modem/cli/ctl/support_bundle.py`
- **What's deferred:** The Phase 2 `support-bundle` consistency invariant
  is that `iccid` and `imsi` keys in any JSON dump are redacted (Phase 2
  C-04). ModemSnapshot is not currently part of any support-bundle dump
  (it's per-cycle ephemeral observation, not persisted state); status.json
  + state files + identity.json + events.jsonl ARE part of the bundle and
  are already redacted/sha256-hashed.
- **Why deferred:** No support-bundle export path includes ModemSnapshot.
  If a future Phase 4+ feature adds Diag dumping to the bundle (the
  per-cycle Diag carries `per_modem: dict[str, ModemSnapshot]`), the
  redaction logic should extend to identity_iccid/identity_imsi at that
  time. Logged here so the reviewer can scope it.
- **Ownership:** Phase 4 / v2.1 if Diag-export-to-bundle becomes a
  feature. Today's bundle is unchanged.

**2. Mid-cycle SIM swap that ALSO removes the modem from the inventory**
- **File:** `src/spark_modem/daemon/cycle_driver.py:_detect_and_handle_sim_swaps`
- **What's deferred:** If a SIM swap involves a usb_path that disappeared
  from the inventory mid-cycle (modem unplugged + replugged in a
  different port between cycles), the current pipeline leaves the prior
  identity entry stale in the identity map. The next cycle's
  re-observation will catch the modem at its NEW usb_path AND notice
  there's no prior entry there → enrollment, not swap. The OLD usb_path's
  stale entry is never garbage-collected.
- **Why deferred:** The plan's E-04 contract is "ICCID change at the SAME
  usb_path triggers reset". Cross-port-relocation is a different scenario
  (modem hardware moved, not SIM swapped) covered by ADR-0009's usb_path
  inventory cross-check (state files keyed by usb_path; daemon refuses
  to start on topology mismatch). Mid-cycle relocation without a daemon
  restart is out-of-scope per `<out_of_scope>` "hot-plug-of-modems-mid-flight
  as a v2.0 priority".
- **Ownership:** v2.1 if mid-cycle relocation becomes a real-fleet
  observation. Today: documented as an explicit non-feature.

## Self-Check: PASSED

**Files exist:**
- FOUND: `tests/unit/state_store/test_reset_modem_streak_and_counters.py`
- FOUND: `tests/unit/daemon/test_sim_swap_detection.py`

**Files modified (verified by `git log --oneline -5`):**
- FOUND: `src/spark_modem/state_store/store.py` modified in `5fa4005`
- FOUND: `src/spark_modem/daemon/cycle_driver.py` modified in `b321ce4`
- FOUND: `src/spark_modem/wire/diag.py` modified in `b321ce4`
- FOUND: `src/spark_modem/observer/issue_extractor.py` modified in `b321ce4`

**Commits exist (verified by `git log --oneline -5`):**
- FOUND: `c12c06a` test(03-07): add failing tests for StateStore.reset_modem_streak_and_counters
- FOUND: `5fa4005` feat(03-07): StateStore.reset_modem_streak_and_counters atomic single-write
- FOUND: `c8ab3d4` test(03-07): add failing tests for cycle_driver SIM-swap detection
- FOUND: `b321ce4` feat(03-07): cycle_driver SIM-swap detection + structured SimSwapped emit

**Final acceptance:**
- `pytest -q` reports 1815 passed / 81 skipped / 0 failed in 17.60s
- `pytest tests/unit/state_store/test_reset_modem_streak_and_counters.py -x`
  exits 0 (6 passed + 1 POSIX-only skipped on Windows)
- `pytest tests/unit/daemon/test_sim_swap_detection.py -x` exits 0
  (8 passed)
- `pytest tests/unit/daemon/ -x` exits 0 (52 passed + 3 PID-lock POSIX-only skipped)
- `pytest tests/unit/state_store/ -x` exits 0 (67 passed + 18 POSIX-only skipped)
- `pytest tests/unit/observer/ tests/unit/wire/ -x` exits 0 (149 passed)
- `mypy --strict src/spark_modem/state_store/store.py
  src/spark_modem/daemon/cycle_driver.py src/spark_modem/wire/diag.py
  src/spark_modem/observer/issue_extractor.py` reports 0 issues across
  4 source files
- `ruff check src/ tests/` reports `All checks passed!`
- `ruff format --check` clean across all modified files
- `bash scripts/lint_no_subprocess.sh` exits 0 (subprocess discipline preserved)
- `grep -c 'def reset_modem_streak_and_counters' src/spark_modem/state_store/store.py` → 1
- `grep -c 'async def reset_modem_streak_and_counters' src/spark_modem/state_store/store.py` → 1
- `grep -c 'load_identity_map\|save_identity_map' src/spark_modem/daemon/cycle_driver.py` → 3
- `grep -c 'reset_modem_streak_and_counters' src/spark_modem/daemon/cycle_driver.py` → 4
- `grep -c 'SimSwapped' src/spark_modem/daemon/cycle_driver.py` → 8 (import + emit + threat callouts)
- `grep -c 'sha256\|hashlib' src/spark_modem/daemon/cycle_driver.py` → 7
- `grep -c 'logger.info.*iccid\|logger.info.*sim_swap' src/spark_modem/daemon/cycle_driver.py` → 0 (Issue #8 gate)
- `grep -c 'self._events.append' src/spark_modem/daemon/cycle_driver.py` → 2 (structured emit path)
- `grep -c 'time.time' src/spark_modem/daemon/cycle_driver.py` → 0 (CLAUDE.md invariant #4)
- M7 budget preserved (17.60s ≤ 30s with ~12.4s slack)

## TDD Gate Compliance

Plan 03-07 frontmatter is `type: execute`; tasks within are
`type="auto" tdd="true"`. Per-task gate sequence verified in git log:

| Task | RED commit (test) | GREEN commit (feat) | Gate sequence |
|------|-------------------|---------------------|---------------|
| Task 1 | `c12c06a` test(03-07): failing tests for StateStore.reset_modem_streak_and_counters | `5fa4005` feat(03-07): StateStore.reset_modem_streak_and_counters atomic single-write | RED-then-GREEN ✓ |
| Task 2 | `c8ab3d4` test(03-07): failing tests for cycle_driver SIM-swap detection | `b321ce4` feat(03-07): cycle_driver SIM-swap detection + structured SimSwapped emit | RED-then-GREEN ✓ |

Both tasks demonstrated true RED before GREEN: pytest after `c12c06a`
failed with `AttributeError: 'StateStore' object has no attribute
'reset_modem_streak_and_counters'`; pytest after `c8ab3d4` failed with
pydantic `ValidationError: identity_iccid Extra inputs are not permitted`
on the new ModemSnapshot field. Both tasks have explicit per-task
RED+GREEN commits — no production code lands without an accompanying
test commit in the same plan.

---
*Phase: 03-linux-event-sources-lifecycle*
*Completed: 2026-05-08*
