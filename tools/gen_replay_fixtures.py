"""Generate >=1000 replay-cycle fixtures for the Phase 2 exit gate.

Output: ``tests/fixtures/replay/<scenario>/<NNN>.json`` -- one fixture
per file.  Each fixture carries a single per-modem ``Diag`` snapshot
plus the prior ``ModemState`` and the action(s) v1 took on the same
input (the partial-order classifier in ``tests/replay/test_v1_agreement``
compares v2's plans against this expectation).

JSON shape::

    {
        "scenario": "registration_searching",
        "fault_cycle": true,
        "v1_succeeded": true,
        "diag": <Diag.model_dump>,
        "prior_state": <ModemState.model_dump by_alias=True>,
        "expected_v1_actions": ["soft_reset"]
    }

Distribution target (R-01):
  - >=950/1000 fault cycles spread across the 7 fault scenarios
    (RECOVERY_SPEC §4 rows + top-15 PITFALLS scenarios)
  - <=50/1000 healthy filler cycles

Determinism: the generator seeds ``random.seed(args.seed)`` once.  Same
seed + same count produces byte-identical fixture files (T-02-10-04).

Usage::

    python -m tools.gen_replay_fixtures --count 1000 --out tests/fixtures/replay
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from spark_modem.wire.diag import Diag, Issue, ModemSnapshot, SignalSnapshot, WhoModem
from spark_modem.wire.enums import IssueCategory, IssueDetail
from spark_modem.wire.state import ModemState

# Scenarios as 7-tuples:
#   (scenario_name, category, detail, expected_v1_action_str,
#    signal_mode, prior_state_name, v1_succeeded)
#
# v1_succeeded controls the partial-order classifier's "less-safe"
# verdict: when v1 needed a destructive action and succeeded, v2 is
# NOT allowed to choose a cheaper action (would have failed in
# production); when v1 failed or signal was bad, v2 picking cheaper is
# "safer" not "less-safe".
_FAULT_SCENARIOS: list[tuple[str, IssueCategory, IssueDetail, str, str, str, bool]] = [
    (
        "registration_searching",
        IssueCategory.REGISTRATION,
        IssueDetail.NOT_REGISTERED_SEARCHING,
        "soft_reset",
        "good",
        "unknown",
        True,
    ),
    (
        "sim_app_detected",
        IssueCategory.SIM,
        IssueDetail.SIM_APP_DETECTED,
        "soft_reset",
        "good",
        "unknown",
        True,
    ),
    (
        "raw_ip_off",
        IssueCategory.DATAPATH,
        IssueDetail.RAW_IP_OFF,
        "fix_raw_ip",
        "good",
        "unknown",
        True,
    ),
    (
        "apn_empty",
        IssueCategory.CONFIG,
        IssueDetail.APN_EMPTY,
        "set_apn",
        "good",
        "unknown",
        True,
    ),
    (
        "operating_mode_low_power",
        IssueCategory.QMI,
        IssueDetail.OPERATING_MODE_LOW_POWER,
        "modem_reset",
        "good",
        "unknown",
        True,
    ),
    (
        "proxy_died",
        IssueCategory.QMI,
        IssueDetail.QMI_PROXY_DIED,
        "driver_reset",
        "good",
        "unknown",
        True,
    ),
    (
        "rf_blocked_during_recovery",
        IssueCategory.REGISTRATION,
        IssueDetail.NOT_REGISTERED_SEARCHING,
        "soft_reset",
        "rf_blocked",
        "recovering",
        False,
    ),
]

_HEALTHY_SCENARIO: tuple[str, IssueCategory, IssueDetail, str, str, str, bool] = (
    "healthy",
    IssueCategory.CONFIG,  # unused for healthy
    IssueDetail.APN_EMPTY,  # unused for healthy
    "no_action",
    "good",
    "healthy",
    True,
)


def _make_diag(usb_path: str, scenario_tuple: tuple[Any, ...]) -> dict[str, Any]:
    name = scenario_tuple[0]
    cat = scenario_tuple[1]
    detail = scenario_tuple[2]
    signal_mode = scenario_tuple[4]

    if name == "healthy":
        issues: list[Issue] = []
        sig = SignalSnapshot(rsrp_dbm=-90, rsrq_db=-10.0, snr_db=8.0)
    else:
        who = WhoModem(usb_path=usb_path, cdc_wdm="cdc-wdm0")
        issues = [Issue(category=cat, detail=detail, who=who)]
        if signal_mode == "rf_blocked":
            sig = SignalSnapshot(rsrp_dbm=-118, rsrq_db=-19.0, snr_db=-3.0)
        else:
            sig = SignalSnapshot(rsrp_dbm=-90, rsrq_db=-10.0, snr_db=8.0)

    snap = ModemSnapshot(
        usb_path=usb_path,
        cdc_wdm="cdc-wdm0",
        signal=sig,
        issues=issues,
    )
    diag = Diag(
        ts_iso="2026-01-01T00:00:00+00:00",
        cycle_id=0,
        per_modem={usb_path: snap},
    )
    return diag.model_dump(mode="json")


def _make_prior(scenario_tuple: tuple[Any, ...]) -> dict[str, Any]:
    prior_state = scenario_tuple[5]
    signal_mode = scenario_tuple[4]
    state_blob: dict[str, Any] = {
        "state": prior_state,
        "present": True,
        "rf_blocked": signal_mode == "rf_blocked",
        "recovering_level": 1 if prior_state == "recovering" else None,
        "_healthy_streak": 0,
        "counters": {},
        "last_action_monotonic": None,
        "last_state_transition_iso": None,
    }
    st = ModemState.model_validate(state_blob)
    return st.model_dump(mode="json", by_alias=True)


def _build_fixture(
    scenario_tuple: tuple[Any, ...],
    *,
    usb_path: str,
    fault_cycle: bool,
) -> dict[str, Any]:
    expected_action = scenario_tuple[3]
    v1_succeeded = scenario_tuple[6]
    return {
        "scenario": scenario_tuple[0],
        "fault_cycle": fault_cycle,
        "v1_succeeded": v1_succeeded,
        "diag": _make_diag(usb_path, scenario_tuple),
        "prior_state": _make_prior(scenario_tuple),
        "expected_v1_actions": ([expected_action] if expected_action != "no_action" else []),
    }


def _write_fixture(target: Path, fixture: dict[str, Any]) -> None:
    target.write_text(json.dumps(fixture, indent=2, sort_keys=True), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate replay-cycle fixtures for the Phase 2 exit gate.",
    )
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("tests/fixtures/replay"),
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)

    random.seed(args.seed)
    out_root: Path = args.out
    out_root.mkdir(parents=True, exist_ok=True)

    # Distribution: 95% fault cycles split equally across the 7 fault
    # scenarios; 5% healthy fillers.  Use ceiling division on per_fault
    # so total >= args.count (acceptance criterion: >=1000 fixtures
    # for --count=1000).
    healthy_count = max(1, args.count // 20)  # ~5%
    fault_total = args.count - healthy_count
    per_fault = -(-fault_total // len(_FAULT_SCENARIOS))  # ceiling div

    total_written = 0

    for scenario_tuple in _FAULT_SCENARIOS:
        scen_name = scenario_tuple[0]
        scen_dir = out_root / scen_name
        scen_dir.mkdir(parents=True, exist_ok=True)
        for i in range(per_fault):
            fixture = _build_fixture(
                scenario_tuple,
                usb_path="2-3.1.1",
                fault_cycle=True,
            )
            _write_fixture(scen_dir / f"{i:03d}.json", fixture)
            total_written += 1

    # Healthy fillers (<=5%).
    healthy_dir = out_root / "healthy"
    healthy_dir.mkdir(parents=True, exist_ok=True)
    for i in range(healthy_count):
        fixture = _build_fixture(
            _HEALTHY_SCENARIO,
            usb_path="2-3.1.1",
            fault_cycle=False,
        )
        _write_fixture(healthy_dir / f"{i:03d}_clean_cycle.json", fixture)
        total_written += 1

    print(f"wrote {total_written} fixtures to {out_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
