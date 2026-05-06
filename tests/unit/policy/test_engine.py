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
from spark_modem.wire.enums import ActionKind, IssueCategory, IssueDetail
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
    """Backoff active -> counter does not bump."""
    # Same-action backoff: last_action 100s ago, default backoff 300s.
    state = _state(
        state="degraded",
        last_action_monotonic=0.0,  # 100s before current clock=100
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
