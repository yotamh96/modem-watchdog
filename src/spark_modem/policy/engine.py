"""Pure-function policy engine -- RECOVERY_SPEC §8 cycle algorithm.

CLAUDE.md §1 invariant: `import` lines below MUST NOT include subprocess,
httpx, os, asyncio, or anything that touches the kernel/network. The
package-level lint gate (`scripts/lint_no_subprocess.sh`) enforces this.

Cycle ordering per RECOVERY_SPEC §8 / ADR-0006 (in-memory, atomic):

    1. transition(prior, snap) -> new_state shape
    2. healthy_streak: if state == "healthy" then prior + 1 else 0
    3. decay-check: if streak >= K then counters = {} and streak = 0
    4. select_top_priority_issue(snap.issues) -> issue
    5. lookup_action(issue.category, issue.detail) -> ActionKind|skip|None
    6. gates -> PlannedAction (sets suppressed_* flags)
    7. counter bump: only if action passes all gates and is not dry-run
    8. record StateTransition if state changed

Step 6 returns CycleResult; the cycle driver (plan 02-10) writes
`new_states` and `new_globals` atomically (single fsync per modem) AFTER
the dispatcher runs.  A crash between selection and write is safe:
actions are idempotent, counters were not bumped, next cycle re-reads
pre-action state.
"""

from __future__ import annotations

from spark_modem.policy.context import PolicyContext
from spark_modem.policy.decision_table import (
    lookup_action,
    select_top_priority_issue,
)
from spark_modem.policy.gates import (
    gate_disconnected,
    gate_exhausted,
    gate_ladder_backoff,
    gate_maintenance,
    gate_same_action_backoff,
    gate_signal,
)
from spark_modem.policy.result import CycleResult, StateTransition
from spark_modem.policy.transitions import transition
from spark_modem.wire.diag import (
    Diag,
    Issue,
    ModemSnapshot,
    PlannedAction,
    WhoHost,
    WhoModem,
)
from spark_modem.wire.enums import ActionKind
from spark_modem.wire.globals import GlobalsState
from spark_modem.wire.state import ModemState


def run_cycle(
    diag: Diag,
    prior_states: dict[str, ModemState],
    globals_state: GlobalsState,
    ctx: PolicyContext,
) -> CycleResult:
    """RECOVERY_SPEC §8 ordering, atomic per modem (in-memory only).

    Pure function: returns `CycleResult` with planned actions, state
    transitions to log, new ModemState dict to persist, and updated
    GlobalsState.  The cycle driver in plan 02-10 calls this function,
    then dispatches the actions, then atomically persists `new_states`
    and `new_globals`.
    """
    plans: list[PlannedAction] = []
    transitions_out: list[StateTransition] = []
    new_states: dict[str, ModemState] = {}

    # 1.5: Phase 4 will add global driver-reset short-circuit here;
    # Phase 2 ships a placeholder check that always returns False so the
    # control flow is in place.  See _global_driver_reset_eligible docstring.
    if _global_driver_reset_eligible(diag, prior_states, globals_state, ctx):
        plans.append(_plan_driver_reset())
        new_globals = globals_state.model_copy(
            update={
                "driver_reset_count": globals_state.driver_reset_count + 1,
                "last_driver_reset_monotonic": ctx.clock.monotonic(),
                "last_driver_reset_iso": ctx.clock.wall_clock_iso(),
            }
        )
        # Per RECOVERY_SPEC §6.4: per-line actions skipped this cycle.
        # State transitions still recorded so observability stays consistent.
        for usb_path, snap in diag.per_modem.items():
            prior = prior_states.get(usb_path) or _fresh_initial_state()
            new_state = transition(prior, snap, ctx)
            new_states[usb_path] = new_state
            if new_state.state != prior.state:
                transitions_out.append(
                    StateTransition(
                        usb_path=usb_path,
                        from_state=prior.state,
                        to_state=new_state.state,
                        cause=_first_issue_label(snap),
                        new_modem_state=new_state,
                    )
                )
        return CycleResult(
            plans=plans,
            transitions=transitions_out,
            new_states=new_states,
            new_globals=new_globals,
        )

    # Per-modem path (no driver_reset short-circuit)
    for usb_path, snap in diag.per_modem.items():
        prior = prior_states.get(usb_path) or _fresh_initial_state()

        # Step 1 -- transition
        new_state = transition(prior, snap, ctx)

        # Step 2 -- streak update (engine-level; transitions does NOT mutate)
        new_streak = (
            (prior.healthy_streak + 1) if new_state.state == "healthy" else 0
        )

        # Step 3 -- decay check
        decayed_counters: dict[ActionKind, int] = dict(prior.counters)
        if new_streak >= ctx.config.healthy_streak_decay_k:
            decayed_counters = {}
            new_streak = 0

        # Step 4 -- top-priority issue
        issue = select_top_priority_issue(list(snap.issues))

        # Step 5 -- decision table lookup
        action_or_skip: ActionKind | str | None = None
        if issue is not None:
            action_or_skip = lookup_action(issue.category, issue.detail)

        # Step 6 -- gates and PlannedAction
        counter_bump: ActionKind | None = None
        if isinstance(action_or_skip, ActionKind):
            plan, would_execute = _apply_gates_to_action(
                action_or_skip,
                new_state,
                ctx,
                _snap_who(snap),
            )
            plans.append(plan)
            if would_execute:
                counter_bump = action_or_skip
        elif isinstance(action_or_skip, str) and action_or_skip.startswith("skip:"):
            # Decision-table-level skip (e.g. skip:requires_human).
            # We use a nominal ActionKind in PlannedAction.kind because the
            # field is non-nullable; the canonical truth is the `reason`.
            plans.append(
                PlannedAction(
                    kind=ActionKind.SOFT_RESET,
                    who=_snap_who(snap),
                    reason=action_or_skip,
                    suppressed_by_backoff=False,
                    suppressed_by_signal_gate=False,
                    suppressed_by_dry_run=False,
                )
            )

        # Step 7 -- counter bump (only if action will actually execute)
        new_counters: dict[ActionKind, int] = dict(decayed_counters)
        if counter_bump is not None:
            new_counters[counter_bump] = new_counters.get(counter_bump, 0) + 1

        new_state_with_counters = new_state.model_copy(
            update={
                "healthy_streak": new_streak,
                "counters": new_counters,
            }
        )
        new_states[usb_path] = new_state_with_counters

        # Step 8 -- transition record
        if new_state_with_counters.state != prior.state:
            transitions_out.append(
                StateTransition(
                    usb_path=usb_path,
                    from_state=prior.state,
                    to_state=new_state_with_counters.state,
                    cause=_first_issue_label(snap),
                    new_modem_state=new_state_with_counters,
                )
            )

    return CycleResult(
        plans=plans,
        transitions=transitions_out,
        new_states=new_states,
        new_globals=globals_state,  # globals only change on driver_reset path
    )


def _apply_gates_to_action(
    action: ActionKind,
    state: ModemState,
    ctx: PolicyContext,
    who: WhoModem,
) -> tuple[PlannedAction, bool]:
    """Evaluate gates in RECOVERY_SPEC §6 order.

    Returns (PlannedAction, would_execute).  `would_execute=True` means
    the dispatcher should actually run the action; counter bump happens
    only in that case (FR-26 -- counters bump on execution, not selection).

    Hard-skip gates short-circuit (disconnected, maintenance, exhausted).
    Soft-skip gates accumulate into suppressed_* flags (signal, backoff,
    ladder, dry_run) so the events log can show partial-skip causes.
    """
    # Hard-skip gates short-circuit first; they produce a definitive skip:reason.
    if gate_disconnected(state):
        return (
            PlannedAction(
                kind=action,
                who=who,
                reason="skip:disconnected",
                suppressed_by_backoff=False,
                suppressed_by_signal_gate=False,
                suppressed_by_dry_run=False,
            ),
            False,
        )

    if gate_maintenance(ctx.maintenance_active, action):
        return (
            PlannedAction(
                kind=action,
                who=who,
                reason="skip:maintenance",
                suppressed_by_backoff=False,
                suppressed_by_signal_gate=False,
                suppressed_by_dry_run=False,
            ),
            False,
        )

    if gate_exhausted(state, action):
        return (
            PlannedAction(
                kind=action,
                who=who,
                reason="skip:exhausted",
                suppressed_by_backoff=False,
                suppressed_by_signal_gate=False,
                suppressed_by_dry_run=False,
            ),
            False,
        )

    # Soft-skip gates: accumulate flags but still record the planned kind.
    suppressed_signal = gate_signal(state, action)
    suppressed_backoff = gate_same_action_backoff(state, action, ctx.clock, ctx.config)
    if not suppressed_backoff:
        suppressed_backoff = gate_ladder_backoff(state, action, ctx.clock, ctx.config)

    suppressed_dry_run = ctx.config.dry_run

    would_execute = not (suppressed_signal or suppressed_backoff or suppressed_dry_run)

    if would_execute:
        reason = f"action_planned:{action.value}"
    elif suppressed_dry_run and not (suppressed_signal or suppressed_backoff):
        reason = "skip:dry_run"
    else:
        reason = "skip:gate_failed"

    return (
        PlannedAction(
            kind=action,
            who=who,
            reason=reason,
            suppressed_by_backoff=suppressed_backoff,
            suppressed_by_signal_gate=suppressed_signal,
            suppressed_by_dry_run=suppressed_dry_run,
        ),
        would_execute,
    )


def _global_driver_reset_eligible(
    diag: Diag,
    prior_states: dict[str, ModemState],
    globals_state: GlobalsState,
    ctx: PolicyContext,
) -> bool:
    """RECOVERY_SPEC §6.4 -- Phase 2 placeholder; always False.

    Phase 4 wires the real ≥75 % qmi_channel_hung + actionable-signal
    check end-to-end with the driver_reset action.  Phase 2 returns False
    so the control flow exists; the replay harness in plan 02-10 still
    classifies v1 driver_reset traces against this engine.
    """
    del diag, prior_states, globals_state, ctx
    return False


def _plan_driver_reset() -> PlannedAction:
    return PlannedAction(
        kind=ActionKind.DRIVER_RESET,
        who=WhoHost(),
        reason="action_planned:driver_reset",
        suppressed_by_backoff=False,
        suppressed_by_signal_gate=False,
        suppressed_by_dry_run=False,
    )


def _fresh_initial_state() -> ModemState:
    """First-observation default state (RECOVERY_SPEC §3.1: unknown is bootstrap).

    Used when the cycle driver has no persisted state for a usb_path
    (e.g. brand-new modem just plugged in).
    """
    return ModemState.model_validate(
        {
            "state": "unknown",
            "present": True,
            "rf_blocked": False,
            "recovering_level": None,
            "_healthy_streak": 0,
            "counters": {},
            "last_action_monotonic": None,
            "last_state_transition_iso": None,
        }
    )


def _snap_who(snap: ModemSnapshot) -> WhoModem:
    """Build a WhoModem from a ModemSnapshot."""
    return WhoModem(usb_path=snap.usb_path, cdc_wdm=snap.cdc_wdm)


def _first_issue_label(snap: ModemSnapshot) -> str:
    """Canonical 'category/detail' label for the StateTransition.cause field.

    Returns 'no_issues' when the modem has no issues this cycle (e.g. a
    recovering -> healthy transition with no attached cause).
    """
    if not snap.issues:
        return "no_issues"
    issue: Issue = snap.issues[0]
    return f"{issue.category.value}/{issue.detail.value}"
