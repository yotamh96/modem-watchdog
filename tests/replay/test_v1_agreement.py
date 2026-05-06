"""Phase 2 EXIT GATE -- replay every on-disk fixture (R-01..R-03).

For each fixture:
  1. Load Diag + prior_state + expected_v1_actions.
  2. Run policy.engine.run_cycle.
  3. Classify: agree | safer | less-safe | different-issue | both-skip
     using the cost ordering R-02.
  4. Record verdict in conftest accumulator.

The conftest's pytest_sessionfinish hard-fails the build at <95%
fault-cycle agreement (R-03) and writes
``artifacts/replay-summary.json`` with the verdict breakdown.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from spark_modem.config.settings import Settings
from spark_modem.policy.context import PolicyContext
from spark_modem.policy.engine import run_cycle
from spark_modem.wire.diag import Diag, PlannedAction
from spark_modem.wire.globals import GlobalsState
from spark_modem.wire.state import ModemState
from tests.fakes.clock import FakeClock
from tests.replay.conftest import fixture_paths_for_parametrize, record_verdict

# R-02 partial-order cost ordering.  Cheap actions sort before
# destructive ones; v2 picking a strictly cheaper action when v1 needed
# the destructive one (and v1 succeeded) classifies as "less-safe".
_COST_ORDER: tuple[str, ...] = (
    "no_action",
    "set_apn",
    "fix_raw_ip",
    "sim_power_on",
    "soft_reset",
    "modem_reset",
    "usb_reset",
    "driver_reset",
)

_DESTRUCTIVE_THRESHOLD: int = _COST_ORDER.index("modem_reset")


def _cost(action_str: str) -> int:
    """Return the cost rank for ``action_str``; -1 for unknown actions."""
    try:
        return _COST_ORDER.index(action_str)
    except ValueError:
        return -1


def _v2_active_kinds(v2_plans: list[PlannedAction]) -> list[str]:
    """Filter out suppressed / skip plans -- only actions that would EXECUTE."""
    return [
        p.kind.value
        for p in v2_plans
        if not (p.suppressed_by_backoff or p.suppressed_by_signal_gate or p.suppressed_by_dry_run)
        and not p.reason.startswith("skip:")
    ]


def _classify_with_both_acting(
    v1_actions: list[str],
    v2_kinds: list[str],
    v1_succeeded: bool | None,
) -> str:
    """Both v1 and v2 chose at least one action AND the sets differ."""
    v1_max = max(_cost(a) for a in v1_actions)
    v2_max = max(_cost(a) for a in v2_kinds)
    if v2_max < v1_max:
        # v2 chose cheaper -- safer ONLY if v1 needed the destructive
        # (v1_succeeded means destructive worked -> cheaper would
        # have failed -> less-safe).  v1_succeeded False/None means
        # destructive also failed; cheaper is at least as good.
        if v1_succeeded is True and v1_max >= _DESTRUCTIVE_THRESHOLD:
            return "less-safe"
        return "safer"
    if v2_max > v1_max:
        return "less-safe"
    # Equal cost but different kinds -- e.g. modem_reset vs usb_reset
    # at the same rung.  Not a regression on cost.
    return "different-issue"


def _classify(
    v2_plans: list[PlannedAction],
    v1_actions: list[str],
    v1_succeeded: bool | None,
) -> str:
    """R-02 partial-order verdict classifier.

    Returns one of: ``agree | safer | less-safe | different-issue | both-skip``.
    """
    v2_kinds = _v2_active_kinds(v2_plans)
    v1_set = set(v1_actions)
    v2_set = set(v2_kinds)

    if not v2_kinds and not v1_actions:
        return "both-skip"
    if v1_set == v2_set:
        return "agree"
    if v1_actions and v2_kinds:
        return _classify_with_both_acting(v1_actions, v2_kinds, v1_succeeded)
    if not v2_kinds and v1_actions:
        return "less-safe"  # v2 missed an issue v1 caught
    # v2_kinds and not v1_actions -- v2 acting where v1 didn't.
    return "different-issue"


@pytest.fixture
def replay_settings() -> Settings:
    """Fresh Settings instance per test -- avoids global mutability."""
    return Settings(
        state_root="/tmp/test-state",
        run_dir="/tmp/test-run",
        events_log_path="/tmp/events.jsonl",
        metrics_socket_path="/tmp/metrics.sock",
        carriers_yaml_path="/tmp/carriers.yaml",
    )


@pytest.mark.parametrize(
    "fixture_path",
    fixture_paths_for_parametrize(),
    ids=lambda p: str(p.relative_to(Path("tests/fixtures/replay"))).replace(
        "\\",
        "/",
    ),
)
def test_v1_agreement(fixture_path: Path, replay_settings: Settings) -> None:
    """Per-cycle classifier; less-safe is the only HARD failure on faults."""
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    diag = Diag.model_validate(raw["diag"])
    prior_state = ModemState.model_validate(raw["prior_state"])
    usb_path = next(iter(diag.per_modem.keys()))
    prior_states = {usb_path: prior_state}
    v1_actions: list[str] = list(raw["expected_v1_actions"])
    v1_succeeded: bool | None = raw.get("v1_succeeded")
    fault_cycle: bool = bool(raw["fault_cycle"])

    ctx = PolicyContext(
        clock=FakeClock(),
        config=replay_settings,
        maintenance_active=False,
        expected_modem_count=1,
    )
    result = run_cycle(diag, prior_states, GlobalsState(), ctx)
    verdict = _classify(result.plans, v1_actions, v1_succeeded)
    record_verdict(raw["scenario"], fault_cycle, verdict)

    if fault_cycle:
        assert verdict != "less-safe", (
            f"{fixture_path}: v2={[p.kind.value for p in result.plans]} "
            f"v1={v1_actions} verdict={verdict}"
        )
