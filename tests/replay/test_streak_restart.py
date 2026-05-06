"""FR-26.1 proof: streak persists across simulated daemon restart.

Uses the two ``restart_mid_streak/*.json`` fixtures + a serialize/
deserialize round-trip in between to simulate a daemon restart.

Pre-cycle: state has _healthy_streak=5 + counters={soft_reset:1}.
Post-cycle simulates the daemon being restarted at streak=9 (the
serialized state survives across restart per ADR-0006 amendment); the
next cycle reaches K=10 and the decay branch fires (counters reset to
{}, streak resets to 0).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from spark_modem.config.settings import Settings
from spark_modem.policy.context import PolicyContext
from spark_modem.policy.engine import run_cycle
from spark_modem.wire.diag import Diag
from spark_modem.wire.globals import GlobalsState
from spark_modem.wire.state import ModemState
from tests.fakes.clock import FakeClock


@pytest.fixture
def replay_settings() -> Settings:
    return Settings(
        state_root="/tmp/test-state",
        run_dir="/tmp/test-run",
        events_log_path="/tmp/events.jsonl",
        metrics_socket_path="/tmp/metrics.sock",
        carriers_yaml_path="/tmp/carriers.yaml",
    )


def _load_fixture(path: Path) -> dict[str, object]:
    raw: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return raw


def test_streak_persists_across_simulated_restart(
    replay_settings: Settings,
) -> None:
    """FR-26.1: round-trip through model_dump_json/model_validate must
    preserve _healthy_streak; the next cycle then reaches K=10 -> decay."""
    pre = _load_fixture(
        Path("tests/fixtures/replay/restart_mid_streak/000_pre.json"),
    )
    post = _load_fixture(
        Path("tests/fixtures/replay/restart_mid_streak/001_post.json"),
    )

    # ---- Pre-cycle: streak=5 + counters={soft_reset:1} -> healthy cycle.
    diag_pre = Diag.model_validate(pre["diag"])
    prior_pre = ModemState.model_validate(pre["prior_state"])
    usb_path = next(iter(diag_pre.per_modem.keys()))
    ctx = PolicyContext(
        clock=FakeClock(),
        config=replay_settings,
        maintenance_active=False,
        expected_modem_count=1,
    )
    result_pre = run_cycle(diag_pre, {usb_path: prior_pre}, GlobalsState(), ctx)
    new_state_pre = result_pre.new_states[usb_path]
    assert new_state_pre.healthy_streak == pre["expected_post_cycle_streak"]
    # Counters preserved across the healthy cycle (decay only fires at K=10).
    assert new_state_pre.counters == pre["expected_post_cycle_counters"]

    # ---- Simulate restart: serialize -> deserialize via JSON round-trip.
    round_tripped = ModemState.model_validate(
        json.loads(new_state_pre.model_dump_json(by_alias=True)),
    )
    assert round_tripped.healthy_streak == new_state_pre.healthy_streak
    assert round_tripped.counters == new_state_pre.counters

    # ---- Post-cycle: prior streak=9 (would have been written to disk
    # several cycles after restart); the next cycle reaches K=10 -> decay.
    diag_post = Diag.model_validate(post["diag"])
    prior_post = ModemState.model_validate(post["prior_state"])
    assert prior_post.healthy_streak == 9
    result_post = run_cycle(
        diag_post,
        {usb_path: prior_post},
        GlobalsState(),
        ctx,
    )
    new_state_post = result_post.new_states[usb_path]
    # FR-26: K=10 -> decay fires; counters reset; streak resets to 0.
    assert new_state_post.healthy_streak == 0
    assert new_state_post.counters == {}, (
        f"Expected counters decayed; got {new_state_post.counters}"
    )
