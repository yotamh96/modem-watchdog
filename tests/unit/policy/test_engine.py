"""Unit tests for policy.engine.run_cycle -- pure-function orchestrator.

Covers:
  - Per-modem cycle algorithm (RECOVERY_SPEC §8 atomic ordering)
  - Counter decay (ADR-0006: K consecutive healthy -> reset counters)
  - Signal-quality gate marking destructive plans suppressed
  - Cheap actions bypass the signal gate
  - Maintenance window blocks destructive only (C-01)
  - Streak persistence across cycles
  - StateTransition recording for state changes
  - dry_run sets suppressed_by_dry_run
  - Pure-function: idempotent on repeated calls (no side effects)
  - Module-level purity: no subprocess / httpx / asyncio / os.system imports
"""

from __future__ import annotations

import re
from pathlib import Path

from spark_modem.config.settings import Settings
from spark_modem.policy.context import PolicyContext
from spark_modem.policy.engine import run_cycle
from spark_modem.wire.diag import Diag, Issue, ModemSnapshot, SignalSnapshot, WhoModem
from spark_modem.wire.enums import ActionKind, IssueCategory, IssueDetail, SkipReason
from spark_modem.wire.events import ActionSkipped
from spark_modem.wire.globals import GlobalsState
from spark_modem.wire.state import ModemState
from tests.fakes.clock import FakeClock


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "state_root": "/tmp/test-state",
        "run_dir": "/tmp/test-run",
        "events_log_path": "/tmp/events.jsonl",
        "metrics_socket_path": "/tmp/metrics.sock",
        "carriers_yaml_path": "/tmp/carriers.yaml",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _ctx(
    *,
    clock: FakeClock | None = None,
    settings: Settings | None = None,
    maintenance_active: bool = False,
) -> PolicyContext:
    return PolicyContext(
        clock=clock or FakeClock(),
        config=settings or _settings(),
        maintenance_active=maintenance_active,
        expected_modem_count=1,
    )


def _state(
    *,
    state: str = "unknown",
    healthy_streak: int = 0,
    counters: dict[str, int] | None = None,
    last_action_monotonic: float | None = None,
    last_action_monotonic_by_kind: dict[ActionKind, float] | None = None,
    recovering_level: int | None = None,
) -> ModemState:
    payload: dict[str, object] = {
        "state": state,
        "present": True,
        "rf_blocked": False,
        "recovering_level": recovering_level,
        "_healthy_streak": healthy_streak,
        "counters": counters or {},
        "last_action_monotonic": last_action_monotonic,
        "last_action_monotonic_by_kind": last_action_monotonic_by_kind or {},
        "last_state_transition_iso": None,
    }
    return ModemState.model_validate(payload)


def _snap(
    *,
    issues: list[Issue] | None = None,
    rsrp_dbm: int | None = -90,
    rsrq_db: float | None = -10.0,
    snr_db: float | None = 5.0,
    usb_path: str = "2-3.1.1",
) -> ModemSnapshot:
    return ModemSnapshot(
        usb_path=usb_path,
        cdc_wdm="cdc-wdm0",
        signal=SignalSnapshot(rsrp_dbm=rsrp_dbm, rsrq_db=rsrq_db, snr_db=snr_db),
        issues=issues or [],
    )


def _issue(
    category: IssueCategory,
    detail: IssueDetail,
    usb_path: str = "2-3.1.1",
) -> Issue:
    return Issue(
        category=category,
        detail=detail,
        who=WhoModem(usb_path=usb_path, cdc_wdm="cdc-wdm0"),
    )


def _diag(snaps: list[ModemSnapshot]) -> Diag:
    return Diag(
        ts_iso="2026-01-01T00:00:00+00:00",
        cycle_id=1,
        per_modem={s.usb_path: s for s in snaps},
    )


# --- Test 1: clean cycle ----------------------------------------------------


def test_run_cycle_no_issues_returns_no_plans() -> None:
    """Empty issues + good signal -> no plans, healthy_streak bumped to 1."""
    diag = _diag([_snap()])
    result = run_cycle(diag, {"2-3.1.1": _state()}, GlobalsState(), _ctx())
    assert result.plans == []
    assert "2-3.1.1" in result.new_states
    assert result.new_states["2-3.1.1"].state == "healthy"
    assert result.new_states["2-3.1.1"].healthy_streak == 1


# --- Test 2-3: decision table -> PlannedAction round-trip ------------------


def test_run_cycle_apn_empty_plans_set_apn() -> None:
    """CONFIG/APN_EMPTY -> set_apn, no suppression with default settings."""
    diag = _diag(
        [_snap(issues=[_issue(IssueCategory.CONFIG, IssueDetail.APN_EMPTY)])]
    )
    result = run_cycle(diag, {"2-3.1.1": _state()}, GlobalsState(), _ctx())
    assert len(result.plans) == 1
    plan = result.plans[0]
    assert plan.kind == ActionKind.SET_APN
    assert plan.reason == "action_planned:set_apn"
    assert plan.suppressed_by_backoff is False
    assert plan.suppressed_by_signal_gate is False
    assert plan.suppressed_by_dry_run is False


def test_run_cycle_sim_pin_required_plans_skip_requires_human() -> None:
    """Decision-table-level skip propagates to PlannedAction.reason."""
    diag = _diag(
        [
            _snap(
                issues=[_issue(IssueCategory.SIM, IssueDetail.SIM_APP_PIN_REQUIRED)]
            )
        ]
    )
    result = run_cycle(diag, {"2-3.1.1": _state()}, GlobalsState(), _ctx())
    assert len(result.plans) == 1
    assert result.plans[0].reason == "skip:requires_human"


# --- Test 4-5: signal gate (RECOVERY_SPEC §6.1) -----------------------------


def test_run_cycle_signal_gate_marks_destructive_skipped() -> None:
    """rf_blocked + destructive issue -> suppressed_by_signal_gate=True."""
    diag = _diag(
        [
            _snap(
                rsrp_dbm=-115,  # below -110 threshold
                issues=[
                    _issue(
                        IssueCategory.QMI,
                        IssueDetail.QMI_CHANNEL_HUNG,  # -> usb_reset (destructive)
                    )
                ],
            )
        ]
    )
    result = run_cycle(diag, {"2-3.1.1": _state()}, GlobalsState(), _ctx())
    assert len(result.plans) == 1
    plan = result.plans[0]
    assert plan.kind == ActionKind.USB_RESET
    assert plan.suppressed_by_signal_gate is True
    # Counter should NOT bump on a gate-suppressed action
    assert ActionKind.USB_RESET not in result.new_states["2-3.1.1"].counters


def test_run_cycle_signal_gate_does_not_mark_cheap_actions() -> None:
    """rf_blocked + cheap issue (set_apn) -> NOT suppressed_by_signal_gate."""
    diag = _diag(
        [
            _snap(
                rsrp_dbm=-115,  # rf_blocked condition
                issues=[_issue(IssueCategory.CONFIG, IssueDetail.APN_EMPTY)],
            )
        ]
    )
    result = run_cycle(diag, {"2-3.1.1": _state()}, GlobalsState(), _ctx())
    assert len(result.plans) == 1
    plan = result.plans[0]
    assert plan.kind == ActionKind.SET_APN
    assert plan.suppressed_by_signal_gate is False
    # set_apn counter bumps because action will execute
    assert result.new_states["2-3.1.1"].counters[ActionKind.SET_APN] == 1


# --- Test 6: streak increment over multiple cycles --------------------------


def test_run_cycle_streak_increments_to_5_after_5_healthy() -> None:
    """5 healthy cycles -> healthy_streak goes 1, 2, 3, 4, 5."""
    state = _state(state="healthy", healthy_streak=0)
    streaks: list[int] = []
    for _ in range(5):
        result = run_cycle(_diag([_snap()]), {"2-3.1.1": state}, GlobalsState(), _ctx())
        state = result.new_states["2-3.1.1"]
        streaks.append(state.healthy_streak)
    assert streaks == [1, 2, 3, 4, 5]


# --- Test 7-8: counter decay (ADR-0006) -------------------------------------


def test_run_cycle_decay_fires_at_k_consecutive_healthy() -> None:
    """Streak reaches K=10 on this cycle -> counters reset, streak = 0."""
    # Default healthy_streak_decay_k=10; if prior streak is 9 and this
    # cycle is healthy, new streak would be 10, which triggers decay.
    state = _state(
        state="healthy",
        healthy_streak=9,
        counters={"soft_reset": 3},
    )
    result = run_cycle(_diag([_snap()]), {"2-3.1.1": state}, GlobalsState(), _ctx())
    new_state = result.new_states["2-3.1.1"]
    assert new_state.counters == {}
    assert new_state.healthy_streak == 0


def test_run_cycle_decay_does_not_fire_below_k() -> None:
    """Streak goes 8 -> 9 (still below K=10); counters unchanged."""
    state = _state(
        state="healthy",
        healthy_streak=8,
        counters={"soft_reset": 3},
    )
    result = run_cycle(_diag([_snap()]), {"2-3.1.1": state}, GlobalsState(), _ctx())
    new_state = result.new_states["2-3.1.1"]
    assert new_state.healthy_streak == 9
    assert new_state.counters[ActionKind.SOFT_RESET] == 3


# --- Test 9-10: state-transition recording ---------------------------------


def test_run_cycle_records_state_transition() -> None:
    """healthy -> degraded (issue arrives) is recorded as a StateTransition."""
    diag = _diag(
        [_snap(issues=[_issue(IssueCategory.CONFIG, IssueDetail.APN_EMPTY)])]
    )
    state = _state(state="healthy")
    result = run_cycle(diag, {"2-3.1.1": state}, GlobalsState(), _ctx())
    assert len(result.transitions) == 1
    t = result.transitions[0]
    assert t.from_state == "healthy"
    assert t.to_state == "degraded"
    assert t.cause == "config/apn_empty"
    assert t.usb_path == "2-3.1.1"


def test_run_cycle_no_transition_recorded_when_state_unchanged() -> None:
    """healthy -> healthy: no StateTransition recorded."""
    state = _state(state="healthy", healthy_streak=2)
    result = run_cycle(_diag([_snap()]), {"2-3.1.1": state}, GlobalsState(), _ctx())
    assert result.transitions == []


# --- Test 11-12: counter bump policy ---------------------------------------


def test_run_cycle_counter_bumps_on_executed_action() -> None:
    """set_apn passes all gates -> counter bumps from 0 -> 1."""
    diag = _diag(
        [_snap(issues=[_issue(IssueCategory.CONFIG, IssueDetail.APN_EMPTY)])]
    )
    result = run_cycle(diag, {"2-3.1.1": _state()}, GlobalsState(), _ctx())
    assert result.new_states["2-3.1.1"].counters[ActionKind.SET_APN] == 1


def test_run_cycle_counter_does_not_bump_when_skipped_by_gate() -> None:
    """Backoff active -> counter does not bump.

    Phase 4 (B-02): same-action gate keys on the per-kind dict, not the
    legacy global last_action_monotonic. Populate the dict for SET_APN so
    the gate fires.
    """
    # Same-action backoff: last SET_APN action 100s ago, default backoff 300s.
    state = _state(
        state="degraded",
        last_action_monotonic=0.0,
        last_action_monotonic_by_kind={ActionKind.SET_APN: 0.0},
    )
    diag = _diag(
        [_snap(issues=[_issue(IssueCategory.CONFIG, IssueDetail.APN_EMPTY)])]
    )
    clock = FakeClock(start_monotonic=100.0)  # within 300s backoff window
    result = run_cycle(
        diag, {"2-3.1.1": state}, GlobalsState(), _ctx(clock=clock)
    )
    new_state = result.new_states["2-3.1.1"]
    # Counter should NOT bump because backoff suppressed the action
    assert ActionKind.SET_APN not in new_state.counters
    assert result.plans[0].suppressed_by_backoff is True


# --- Test 13: dry_run --------------------------------------------------------


def test_run_cycle_dry_run_marks_suppressed_dry_run() -> None:
    """settings.dry_run=True -> suppressed_by_dry_run on planned action."""
    diag = _diag(
        [_snap(issues=[_issue(IssueCategory.CONFIG, IssueDetail.APN_EMPTY)])]
    )
    settings = _settings(dry_run=True)
    result = run_cycle(
        diag, {"2-3.1.1": _state()}, GlobalsState(), _ctx(settings=settings)
    )
    assert len(result.plans) == 1
    plan = result.plans[0]
    assert plan.suppressed_by_dry_run is True
    # Counter should NOT bump under dry-run
    assert ActionKind.SET_APN not in result.new_states["2-3.1.1"].counters


# --- Test 14: maintenance window (C-01) ------------------------------------


def test_run_cycle_maintenance_blocks_destructive_only() -> None:
    """maintenance + cheap action: runs.  maintenance + destructive: skips."""
    diag = _diag(
        [
            _snap(
                usb_path="2-3.1.1",
                issues=[_issue(IssueCategory.CONFIG, IssueDetail.APN_EMPTY)],
            ),
            _snap(
                usb_path="2-3.1.2",
                issues=[
                    _issue(
                        IssueCategory.DATAPATH,
                        IssueDetail.SESSION_DISCONNECTED,
                        usb_path="2-3.1.2",
                    )
                ],
            ),
        ]
    )
    states = {"2-3.1.1": _state(), "2-3.1.2": _state()}
    result = run_cycle(
        diag, states, GlobalsState(), _ctx(maintenance_active=True)
    )
    plans_by_usb = {p.who.usb_path: p for p in result.plans if p.who.kind == "modem"}
    assert plans_by_usb["2-3.1.1"].kind == ActionKind.SET_APN
    assert plans_by_usb["2-3.1.1"].reason == "action_planned:set_apn"
    # destructive (modem_reset) -> skipped with maintenance reason
    assert plans_by_usb["2-3.1.2"].kind == ActionKind.MODEM_RESET
    assert plans_by_usb["2-3.1.2"].reason == "skip:maintenance"


# --- Test 15: pure-function determinism ------------------------------------


def test_run_cycle_returns_pure_function_no_side_effects() -> None:
    """Calling run_cycle twice with same inputs produces identical results."""
    diag = _diag(
        [_snap(issues=[_issue(IssueCategory.CONFIG, IssueDetail.APN_EMPTY)])]
    )
    state = _state()

    r1 = run_cycle(
        diag, {"2-3.1.1": state}, GlobalsState(), _ctx(clock=FakeClock())
    )
    r2 = run_cycle(
        diag, {"2-3.1.1": state}, GlobalsState(), _ctx(clock=FakeClock())
    )
    # Plans dump identically
    assert [p.model_dump() for p in r1.plans] == [p.model_dump() for p in r2.plans]
    # New states dump identically
    assert {k: v.model_dump() for k, v in r1.new_states.items()} == {
        k: v.model_dump() for k, v in r2.new_states.items()
    }
    # The original state was not mutated
    assert state.healthy_streak == 0
    assert state.counters == {}


# --- Test 16: structural -- no I/O imports in engine.py --------------------


def test_engine_imports_no_io_modules() -> None:
    """CLAUDE.md §1: policy/ must not import subprocess / httpx / asyncio / os.

    Also forbids os.system specifically (anti-pattern catalogue).
    """
    src = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "spark_modem"
        / "policy"
        / "engine.py"
    ).read_text(encoding="utf-8")
    forbidden = (
        re.compile(r"^\s*import\s+subprocess", re.MULTILINE),
        re.compile(r"^\s*import\s+httpx", re.MULTILINE),
        re.compile(r"^\s*import\s+asyncio", re.MULTILINE),
        re.compile(r"^\s*from\s+(subprocess|httpx|asyncio)\s+import", re.MULTILINE),
        re.compile(r"os\.system", re.MULTILINE),
        re.compile(r"create_subprocess_exec", re.MULTILINE),
    )
    for pat in forbidden:
        assert pat.search(src) is None, (
            f"engine.py contains forbidden pattern {pat.pattern!r} "
            f"-- policy/ must be pure (CLAUDE.md §1)"
        )


# --- Test 17: state preservation when state already healthy -----------------


def test_run_cycle_preserves_present_and_rf_flags() -> None:
    """new_state.present and rf_blocked are computed; not blindly carried."""
    diag = _diag([_snap(rsrp_dbm=-115)])  # rf_blocked condition, no issues
    state = _state(state="healthy")
    result = run_cycle(diag, {"2-3.1.1": state}, GlobalsState(), _ctx())
    new = result.new_states["2-3.1.1"]
    assert new.rf_blocked is True
    assert new.present is True
    assert new.state == "healthy"  # rf-only with no issues stays healthy


# --- Test 18: priority across multiple issues -------------------------------


def test_run_cycle_picks_highest_priority_issue() -> None:
    """CONFIG (priority 1) wins over SIM (priority 2) on same modem."""
    snap = _snap(
        issues=[
            _issue(IssueCategory.SIM, IssueDetail.SIM_APP_DETECTED),
            _issue(IssueCategory.CONFIG, IssueDetail.APN_EMPTY),
        ]
    )
    diag = _diag([snap])
    result = run_cycle(diag, {"2-3.1.1": _state()}, GlobalsState(), _ctx())
    assert len(result.plans) == 1
    assert result.plans[0].kind == ActionKind.SET_APN  # CONFIG won


# --- Test 19: streak resets to 0 on non-healthy transition -----------------


def test_run_cycle_streak_resets_on_non_healthy() -> None:
    """healthy_streak=5; an issue arrives -> streak goes to 0."""
    state = _state(state="healthy", healthy_streak=5)
    diag = _diag(
        [_snap(issues=[_issue(IssueCategory.CONFIG, IssueDetail.APN_EMPTY)])]
    )
    result = run_cycle(diag, {"2-3.1.1": state}, GlobalsState(), _ctx())
    assert result.new_states["2-3.1.1"].healthy_streak == 0


# --- Test 20: empty diag handled cleanly -----------------------------------


def test_run_cycle_empty_diag_returns_empty_result() -> None:
    """No modems in diag -> empty plans, empty transitions, empty new_states."""
    diag = Diag(ts_iso="2026-01-01T00:00:00+00:00", cycle_id=1, per_modem={})
    result = run_cycle(diag, {}, GlobalsState(), _ctx())
    assert result.plans == []
    assert result.transitions == []
    assert result.new_states == {}


# --- Test 21: globals untouched on per-modem path --------------------------


def test_run_cycle_globals_passthrough_when_no_driver_reset() -> None:
    """No driver_reset path -> new_globals is the input GlobalsState unchanged."""
    g = GlobalsState(driver_reset_count=2, last_driver_reset_monotonic=42.0)
    diag = _diag([_snap()])
    result = run_cycle(diag, {"2-3.1.1": _state()}, g, _ctx())
    assert result.new_globals.driver_reset_count == 2
    assert result.new_globals.last_driver_reset_monotonic == 42.0


# --- Plan 04-04 Task 3: ladder integration + atomic per-kind timestamp bump --


def test_engine_uses_ladder_select_rung_for_registration() -> None:
    """B-01: REGISTRATION ladder rung-2 promotion fires when SOFT_RESET counter
    is at the max_soft ceiling.

    Diag with NOT_REGISTERED_SEARCHING; prior counters at SOFT_RESET=3 (==
    max_soft default 3); ladder.select_rung promotes to MODEM_RESET.
    """
    diag = _diag(
        [
            _snap(
                issues=[
                    _issue(IssueCategory.REGISTRATION, IssueDetail.NOT_REGISTERED_SEARCHING)
                ]
            )
        ]
    )
    state = _state(
        state="degraded",
        counters={ActionKind.SOFT_RESET: 3},  # at ceiling -- promote
    )
    result = run_cycle(diag, {"2-3.1.1": state}, GlobalsState(), _ctx())
    assert len(result.plans) == 1
    assert result.plans[0].kind == ActionKind.MODEM_RESET


def test_engine_ladder_yields_skip_exhausted_when_all_rungs_full() -> None:
    """B-01: counters at every ceiling -> ladder returns 'skip:exhausted'.

    The engine emits a PlannedAction with reason starting with 'skip:exhausted'
    (mirroring the decision-table-level skip-string pattern).
    """
    diag = _diag(
        [
            _snap(
                issues=[
                    _issue(IssueCategory.REGISTRATION, IssueDetail.NOT_REGISTERED_SEARCHING)
                ]
            )
        ]
    )
    state = _state(
        state="degraded",
        counters={
            ActionKind.SOFT_RESET: 3,
            ActionKind.MODEM_RESET: 2,
            ActionKind.USB_RESET: 1,
        },
    )
    result = run_cycle(diag, {"2-3.1.1": state}, GlobalsState(), _ctx())
    assert len(result.plans) == 1
    plan = result.plans[0]
    assert plan.reason == "skip:exhausted"
    # Counters should NOT bump on a skip:exhausted plan -- prior counters
    # carry forward unchanged (no rung-N+1 increment).
    new_counters = result.new_states["2-3.1.1"].counters
    assert new_counters[ActionKind.SOFT_RESET] == 3
    assert new_counters[ActionKind.MODEM_RESET] == 2
    assert new_counters[ActionKind.USB_RESET] == 1
    # Per-kind timestamp dict also untouched.
    assert result.new_states["2-3.1.1"].last_action_monotonic_by_kind == {}


def test_engine_atomically_bumps_legacy_and_per_kind_timestamps() -> None:
    """B-02 / I-03 fix: engine bumps BOTH last_action_monotonic and
    last_action_monotonic_by_kind[executed_kind] in ONE atomic model_copy.

    This test is the back-compat contract:
      - state.last_action_monotonic == ctx.clock.monotonic() at action time
      - state.last_action_monotonic_by_kind[executed_kind] == same value
      - The two values are EQUAL (atomic same-clock-read)
      - The legacy field is bumped even though no gate reads it (Phase 2
        state-file replay relies on the field being populated -- a future
        engineer must NOT delete this bump as dead code)

    Use SET_APN as the executed action -- it's a cheap action that runs
    cleanly without ladder/signal interference.
    """
    diag = _diag(
        [_snap(issues=[_issue(IssueCategory.CONFIG, IssueDetail.APN_EMPTY)])]
    )
    clock = FakeClock(start_monotonic=12345.0)
    result = run_cycle(diag, {"2-3.1.1": _state()}, GlobalsState(), _ctx(clock=clock))
    new_state = result.new_states["2-3.1.1"]
    expected_ts = 12345.0

    # Per-kind dict has the bump for the executed kind.
    assert ActionKind.SET_APN in new_state.last_action_monotonic_by_kind
    assert new_state.last_action_monotonic_by_kind[ActionKind.SET_APN] == expected_ts

    # Legacy field is bumped to the SAME value (back-compat contract).
    assert new_state.last_action_monotonic == expected_ts

    # The two timestamps are equal -- atomic same-clock-read in one model_copy.
    assert new_state.last_action_monotonic == new_state.last_action_monotonic_by_kind[
        ActionKind.SET_APN
    ]


def test_engine_does_not_bump_per_kind_for_skipped_actions() -> None:
    """B-02: when an action is gated (would_execute=False), per-kind dict is
    UNCHANGED -- no spurious bump.

    Use the signal gate to suppress: rf_blocked=True + destructive issue.
    """
    diag = _diag(
        [
            _snap(
                rsrp_dbm=-115,  # below floor -> rf_blocked
                issues=[_issue(IssueCategory.QMI, IssueDetail.QMI_CHANNEL_HUNG)],
            )
        ]
    )
    result = run_cycle(diag, {"2-3.1.1": _state()}, GlobalsState(), _ctx())
    new_state = result.new_states["2-3.1.1"]
    # The signal-gate suppressed the destructive plan; per-kind dict stays empty.
    assert new_state.last_action_monotonic_by_kind == {}
    # Legacy field also untouched (None on first observation).
    assert new_state.last_action_monotonic is None


def test_engine_phase_2_states_load_and_run_cleanly() -> None:
    """B-02: Phase 2 ModemState (no last_action_monotonic_by_kind populated)
    flows through engine without NPE; post-cycle state has the per-kind dict
    populated for the executed kind.
    """
    # Construct a Phase-2-shape ModemState (no per-kind dict explicitly set).
    state = ModemState.model_validate(
        {
            "state": "degraded",
            "present": True,
            "rf_blocked": False,
            "recovering_level": None,
            "_healthy_streak": 0,
            "counters": {},
            "last_action_monotonic": None,
            "last_state_transition_iso": None,
        }
    )
    assert state.last_action_monotonic_by_kind == {}  # default empty dict

    diag = _diag(
        [_snap(issues=[_issue(IssueCategory.CONFIG, IssueDetail.APN_EMPTY)])]
    )
    clock = FakeClock(start_monotonic=999.0)
    result = run_cycle(diag, {"2-3.1.1": state}, GlobalsState(), _ctx(clock=clock))
    new_state = result.new_states["2-3.1.1"]
    assert new_state.last_action_monotonic_by_kind[ActionKind.SET_APN] == 999.0
    assert new_state.last_action_monotonic == 999.0


# --- Plan 04-05: ActionSkipped event emission on every gate-failure path -----


def test_engine_emits_action_skipped_on_signal_gate() -> None:
    """B-04 / FR-23 SC#2: rf_blocked + destructive issue -> ActionSkipped with
    reason=SIGNAL_BELOW_GATE. Emitted ALONGSIDE PlannedAction.suppressed_by_signal_gate
    (back-compat for replay harness).
    """
    diag = _diag(
        [
            _snap(
                rsrp_dbm=-115,  # below -110 -> rf_blocked
                issues=[_issue(IssueCategory.QMI, IssueDetail.QMI_CHANNEL_HUNG)],
            )
        ]
    )
    result = run_cycle(diag, {"2-3.1.1": _state()}, GlobalsState(), _ctx())
    assert len(result.skipped) == 1
    s = result.skipped[0]
    assert isinstance(s, ActionSkipped)
    assert s.reason == SkipReason.SIGNAL_BELOW_GATE
    assert s.suppressed_action == ActionKind.USB_RESET
    assert s.cause_category == IssueCategory.QMI
    assert s.cause_detail == IssueDetail.QMI_CHANNEL_HUNG
    assert s.usb_path == "2-3.1.1"


def test_engine_preserves_planned_action_suppressed_flags_alongside_action_skipped() -> None:
    """CONTEXT B-04 'back-compat horizon': PlannedAction.suppressed_by_signal_gate
    is STILL set even though ActionSkipped is now emitted. Replay harness from
    Plan 02-10 reads suppressed_* flags and must not regress.
    """
    diag = _diag(
        [
            _snap(
                rsrp_dbm=-115,
                issues=[_issue(IssueCategory.QMI, IssueDetail.QMI_CHANNEL_HUNG)],
            )
        ]
    )
    result = run_cycle(diag, {"2-3.1.1": _state()}, GlobalsState(), _ctx())
    # Both surfaces fire on the same skip:
    assert len(result.skipped) == 1
    assert result.skipped[0].reason == SkipReason.SIGNAL_BELOW_GATE
    assert len(result.plans) == 1
    assert result.plans[0].suppressed_by_signal_gate is True


def test_engine_emits_action_skipped_on_same_action_backoff() -> None:
    """B-04: same-action backoff fires -> ActionSkipped(reason=SAME_ACTION_BACKOFF)."""
    state = _state(
        state="degraded",
        last_action_monotonic_by_kind={ActionKind.SET_APN: 0.0},
    )
    diag = _diag(
        [_snap(issues=[_issue(IssueCategory.CONFIG, IssueDetail.APN_EMPTY)])]
    )
    clock = FakeClock(start_monotonic=100.0)  # within 300s default backoff window
    result = run_cycle(
        diag, {"2-3.1.1": state}, GlobalsState(), _ctx(clock=clock)
    )
    assert len(result.skipped) == 1
    s = result.skipped[0]
    assert s.reason == SkipReason.SAME_ACTION_BACKOFF
    assert s.suppressed_action == ActionKind.SET_APN
    # Back-compat: PlannedAction.suppressed_by_backoff still True.
    assert result.plans[0].suppressed_by_backoff is True


def test_engine_emits_action_skipped_on_ladder_backoff() -> None:
    """B-04: cross-action ladder backoff fires -> ActionSkipped(reason=LADDER_BACKOFF).

    Setup: prior SOFT_RESET timestamp 50s ago, 90s ladder window not yet expired;
    new cycle wants to fire MODEM_RESET (different destructive kind) -- the
    ladder gate suppresses it.
    """
    state = _state(
        state="degraded",
        last_action_monotonic_by_kind={ActionKind.SOFT_RESET: 0.0},
    )
    diag = _diag(
        [
            _snap(
                issues=[
                    _issue(IssueCategory.DATAPATH, IssueDetail.SESSION_DISCONNECTED)
                ]
            )
        ]
    )
    clock = FakeClock(start_monotonic=50.0)  # 50s < 90s default ladder window
    result = run_cycle(
        diag, {"2-3.1.1": state}, GlobalsState(), _ctx(clock=clock)
    )
    assert len(result.skipped) == 1
    s = result.skipped[0]
    assert s.reason == SkipReason.LADDER_BACKOFF
    assert s.suppressed_action == ActionKind.MODEM_RESET
    assert result.plans[0].suppressed_by_backoff is True


def test_engine_emits_action_skipped_on_exhausted_state() -> None:
    """B-04: state==exhausted + destructive kind -> ActionSkipped(reason=EXHAUSTED).

    The hard-skip exhausted gate fires when ModemState.state == 'exhausted'
    AND the chosen action is not in the cheap allowlist (set_apn / fix_raw_ip).
    """
    state = _state(state="exhausted")
    diag = _diag(
        [_snap(issues=[_issue(IssueCategory.QMI, IssueDetail.QMI_CHANNEL_HUNG)])]
    )
    result = run_cycle(diag, {"2-3.1.1": state}, GlobalsState(), _ctx())
    assert len(result.skipped) == 1
    s = result.skipped[0]
    assert s.reason == SkipReason.EXHAUSTED
    assert s.suppressed_action == ActionKind.USB_RESET


def test_engine_emits_action_skipped_on_disconnected() -> None:
    """B-04: state.present=False -> ActionSkipped(reason=DISCONNECTED) for
    any kind chosen by the decision table."""
    payload: dict[str, object] = {
        "state": "degraded",
        "present": False,  # disconnected gate fires
        "rf_blocked": False,
        "recovering_level": None,
        "_healthy_streak": 0,
        "counters": {},
        "last_action_monotonic": None,
        "last_action_monotonic_by_kind": {},
        "last_state_transition_iso": None,
    }
    state = ModemState.model_validate(payload)
    diag = _diag(
        [_snap(issues=[_issue(IssueCategory.CONFIG, IssueDetail.APN_EMPTY)])]
    )
    result = run_cycle(diag, {"2-3.1.1": state}, GlobalsState(), _ctx())
    assert len(result.skipped) == 1
    s = result.skipped[0]
    assert s.reason == SkipReason.DISCONNECTED
    assert s.suppressed_action == ActionKind.SET_APN


def test_engine_emits_action_skipped_on_maintenance() -> None:
    """B-04: maintenance_active + destructive -> ActionSkipped(reason=MAINTENANCE).

    Cheap actions still run during maintenance: ensure NO ActionSkipped for SET_APN.
    """
    diag = _diag(
        [
            _snap(
                usb_path="2-3.1.1",
                issues=[_issue(IssueCategory.CONFIG, IssueDetail.APN_EMPTY)],
            ),
            _snap(
                usb_path="2-3.1.2",
                issues=[
                    _issue(
                        IssueCategory.DATAPATH,
                        IssueDetail.SESSION_DISCONNECTED,
                        usb_path="2-3.1.2",
                    )
                ],
            ),
        ]
    )
    states = {"2-3.1.1": _state(), "2-3.1.2": _state()}
    result = run_cycle(
        diag, states, GlobalsState(), _ctx(maintenance_active=True)
    )
    # Only the destructive (modem_reset) modem should produce an ActionSkipped.
    assert len(result.skipped) == 1
    s = result.skipped[0]
    assert s.reason == SkipReason.MAINTENANCE
    assert s.suppressed_action == ActionKind.MODEM_RESET
    assert s.usb_path == "2-3.1.2"


def test_engine_emits_action_skipped_on_dry_run() -> None:
    """B-04: dry_run=True (and no other gate) -> ActionSkipped(reason=DRY_RUN)."""
    diag = _diag(
        [_snap(issues=[_issue(IssueCategory.CONFIG, IssueDetail.APN_EMPTY)])]
    )
    settings = _settings(dry_run=True)
    result = run_cycle(
        diag, {"2-3.1.1": _state()}, GlobalsState(), _ctx(settings=settings)
    )
    assert len(result.skipped) == 1
    s = result.skipped[0]
    assert s.reason == SkipReason.DRY_RUN
    assert s.suppressed_action == ActionKind.SET_APN
    # Back-compat: suppressed_by_dry_run flag still True on PlannedAction.
    assert result.plans[0].suppressed_by_dry_run is True


def test_engine_emits_action_skipped_on_ladder_skip_exhausted() -> None:
    """B-04: ladder.select_rung returns 'skip:exhausted' (Plan 04-04) ->
    ActionSkipped(reason=EXHAUSTED).

    Setup per RECOVERY_SPEC §4.1: SOFT_RESET counter at max_soft (3),
    MODEM_RESET counter at max_modem (2), USB_RESET counter at max_usb (1) ->
    ladder returns skip:exhausted on a registration issue.
    """
    state = _state(
        state="degraded",
        counters={
            ActionKind.SOFT_RESET: 3,
            ActionKind.MODEM_RESET: 2,
            ActionKind.USB_RESET: 1,
        },
    )
    diag = _diag(
        [
            _snap(
                issues=[
                    _issue(IssueCategory.REGISTRATION, IssueDetail.NOT_REGISTERED_SEARCHING)
                ]
            )
        ]
    )
    result = run_cycle(diag, {"2-3.1.1": state}, GlobalsState(), _ctx())
    assert len(result.skipped) == 1
    s = result.skipped[0]
    assert s.reason == SkipReason.EXHAUSTED
    # The ladder.select_rung path uses the BASE action (SOFT_RESET for
    # registration) as the suppressed_action -- this is the rung the engine
    # would have selected before the ladder said "no further rung available".
    assert s.suppressed_action == ActionKind.SOFT_RESET


def test_engine_skipped_list_empty_when_no_gate_fires() -> None:
    """B-04: clean cycle with executable action -> CycleResult.skipped == []."""
    diag = _diag(
        [_snap(issues=[_issue(IssueCategory.CONFIG, IssueDetail.APN_EMPTY)])]
    )
    result = run_cycle(diag, {"2-3.1.1": _state()}, GlobalsState(), _ctx())
    assert result.skipped == []


def test_engine_skipped_list_empty_on_no_issues() -> None:
    """B-04: no issues -> no plans, no skipped events."""
    diag = _diag([_snap()])
    result = run_cycle(diag, {"2-3.1.1": _state()}, GlobalsState(), _ctx())
    assert result.plans == []
    assert result.skipped == []


def test_engine_skipped_list_empty_on_decision_table_skip() -> None:
    """B-04: decision-table-level skip strings (skip:requires_human, etc.) are
    NOT mapped to SkipReason -- they are upstream of the gate machinery.

    A SIM_APP_PIN_REQUIRED issue routes to skip:requires_human (decision table);
    no ActionSkipped is emitted because no gate fired (no action was selected).
    """
    diag = _diag(
        [
            _snap(
                issues=[_issue(IssueCategory.SIM, IssueDetail.SIM_APP_PIN_REQUIRED)]
            )
        ]
    )
    result = run_cycle(diag, {"2-3.1.1": _state()}, GlobalsState(), _ctx())
    # The PlannedAction with reason='skip:requires_human' is still emitted
    # (back-compat); ActionSkipped list is empty.
    assert len(result.plans) == 1
    assert result.plans[0].reason == "skip:requires_human"
    assert result.skipped == []
