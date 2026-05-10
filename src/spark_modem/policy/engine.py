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
from spark_modem.policy.ladder import select_rung
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
from spark_modem.wire.enums import ActionKind, IssueCategory, IssueDetail
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
        new_streak = (prior.healthy_streak + 1) if new_state.state == "healthy" else 0

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

        # Step 5.5 -- ladder rung selection (Plan 04-04 B-01).
        # Decision table is flat; ladder.select_rung() picks the actual rung
        # for ladder-eligible base ActionKinds (SOFT/MODEM/USB_RESET) based
        # on per-kind counters vs. config ceilings. Non-ladder kinds pass
        # through unchanged. Returns ActionKind | "skip:exhausted" -- both
        # shapes are accepted by the Step-6 isinstance dispatch below.
        if isinstance(action_or_skip, ActionKind):
            action_or_skip = select_rung(
                base=action_or_skip,
                counters=decayed_counters,
                config=ctx.config,
            )

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
            # Decision-table-level skip (e.g. skip:requires_human) OR
            # ladder-level skip (skip:exhausted from select_rung).
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

        # Step 7 -- counter bump + per-kind timestamp bump (only if action
        # will actually execute). Per RECOVERY_SPEC §8 / CLAUDE.md invariant 8:
        # ONE atomic model_copy writes streak + counters + BOTH timestamp
        # fields together. The legacy last_action_monotonic is bumped even
        # though no gate reads it -- back-compat contract for Phase 2 state
        # files (a future engineer must NOT delete this bump as dead code).
        new_counters: dict[ActionKind, int] = dict(decayed_counters)
        new_ts_by_kind: dict[ActionKind, float] = dict(prior.last_action_monotonic_by_kind)
        new_last_action_monotonic: float | None = prior.last_action_monotonic
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
    """RECOVERY_SPEC §6.4 -- Phase 4 real predicate (Plan 04-03).

    Four gates, evaluated in order; any False short-circuits:

      1. Thermal suppression (C-03 / PITFALLS §17.4): host_issues includes
         THERMAL_WARN or THERMAL_CRITICAL -> not eligible. Driver_reset
         doesn't fix thermal throttling; firing it just unbinds 4 modems
         on a hot box.
      2. Cooldown (C-05 / RECOVERY_SPEC §6.4): elapsed since last fire <
         global_driver_reset_backoff_seconds -> not eligible. None
         last-fire timestamp short-circuits to allow (first-fire path;
         the comparison must NOT be evaluated against None).
      3. ≥75% denominator (C-01): hung_count / expected_modem_count >=
         multi_modem_threshold_fraction. Denominator is the EXPECTED total
         (Settings.expected_modem_count threaded into PolicyContext by
         the cycle driver), NOT the enumerated count -- Zao-active and
         missing modems are counted as 'not-hung' per the user's
         conservative deviation from the research recommendation.
      4. Actionable signal (FR-24): at least one hung modem has rsrp >=
         floor AND rsrq >= floor AND snr >= floor (None readings count as
         'not above floor' -- conservative; missing-data must not fire a
         destructive global action).

    PROXY_DIED issues (C-02): the per-modem decision-table row still
    routes proxy_died -> DRIVER_RESET, but this eligibility predicate
    gates ALL driver_reset paths on the standard 75% threshold (no
    per-modem bypass -- user deviation from PITFALLS §1.1).
    """
    del prior_states  # unused; cycle driver path doesn't depend on prior states

    # Gate 1: thermal suppression (C-03)
    host_details = {issue.detail for issue in diag.host_issues}
    if IssueDetail.THERMAL_WARN in host_details or IssueDetail.THERMAL_CRITICAL in host_details:
        return False

    # Gate 2: cooldown (C-05). None last-fire short-circuits to allow.
    if globals_state.last_driver_reset_monotonic is not None:
        elapsed = ctx.clock.monotonic() - globals_state.last_driver_reset_monotonic
        if elapsed < float(ctx.config.global_driver_reset_backoff_seconds):
            return False

    # Gate 3: ≥75% denominator (C-01). Denominator is EXPECTED, not enumerated.
    expected = ctx.expected_modem_count
    if expected <= 0:
        return False
    hung_count = sum(
        1
        for snap in diag.per_modem.values()
        if any(
            issue.category == IssueCategory.QMI and issue.detail == IssueDetail.QMI_CHANNEL_HUNG
            for issue in snap.issues
        )
    )
    if (hung_count / expected) < ctx.config.multi_modem_threshold_fraction:
        return False

    # Gate 4: actionable signal (FR-24). At least one hung modem must clear
    # all three floors. Plan 04-04 landed the Settings fields; direct read
    # (RECOVERY_SPEC §6.1 verbatim defaults are now Settings defaults).
    rsrp_floor = ctx.config.signal_rsrp_floor_dbm
    rsrq_floor = ctx.config.signal_rsrq_floor_db
    snr_floor = ctx.config.signal_snr_floor_db
    for snap in diag.per_modem.values():
        if not any(
            issue.category == IssueCategory.QMI and issue.detail == IssueDetail.QMI_CHANNEL_HUNG
            for issue in snap.issues
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
            "last_action_monotonic_by_kind": {},
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
