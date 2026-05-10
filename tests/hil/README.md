# HIL — Hardware-In-the-Loop Test Suite

This tier runs ONLY on the bench Jetson tethered to the
`[self-hosted, linux, ARM64, hil-bench]` runner. Per Phase 4 CONTEXT
D-01 / D-02:

- 4× Sierra EM7421 modems on USB hub `2-3.1.{1..4}`
- Real `qmi-proxy` + Zao stack (no fakes)
- Software-only fault injection (NO real RF detuning hardware)
- Serial concurrency (single bench Jetson; never parallel)
- 90 min wall budget per nightly run

## Topology assumption

| usb_path  | cdc_wdm path     |
|-----------|------------------|
| `2-3.1.1` | `/dev/cdc-wdm0`  |
| `2-3.1.2` | `/dev/cdc-wdm1`  |
| `2-3.1.3` | `/dev/cdc-wdm2`  |
| `2-3.1.4` | `/dev/cdc-wdm3`  |

cdc-wdmN paths are subject to renumbering — usb_path is the stable key
(ADR-0009). The `bench_jetson_topology` fixture in `conftest.py` exposes
both maps to scenarios.

## Test markers

Every HIL test file MUST set, at module scope:

```python
import sys
import pytest

pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.hil,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="HIL tests require real Linux hardware",
    ),
    pytest.mark.asyncio,
]
```

The `hil` marker is registered in `pyproject.toml:78`.

## Running locally (developer dry-run on bench Jetson)

```bash
.venv/bin/pytest -m hil tests/hil/ -ra --tb=short
```

NOTE: This will physically de-enumerate the modems, kill `qmi-proxy`,
write synthetic events to `/dev/kmsg`, etc. Do NOT run on a production
Jetson — the bench Jetson is the only safe target.

The fault-injection helpers live in `tests/hil/fault_inject.py` (Plan
04-06); scenario test files land in `tests/hil/scenarios/` (Plan 04-07).

## Scenario index (Plan 04-07 lands these)

- `test_boot_to_healthy.py` — Phase 3 SC#1 piggyback; 4 modems → Healthy in ≤60 s
- `test_sim_swap.py` — Phase 3 SC#2 piggyback
- `test_soft_reset_sim_app_detected.py` — FR-23 SC#4
- `test_modem_reset_after_soft.py` — FR-22 ladder progression
- `test_three_modem_hang.py` — FR-24 driver_reset 75% gate
- `test_rf_event_no_destructive.py` — FR-23 signal gate
- `test_proxy_died_recovery.py` — FR-24 `pkill -9 qmi-proxy`
- `test_qmi_wwan_reload_clean_transition.py` — Phase 3 piggyback
- `test_sigterm_within_5s.py` — FR-53 piggyback
- `test_ctl_reset_state_serialisation.py` — FR-61.1 piggyback
- `test_watchdog_90s_actual_fire.py` — FR-75 / NFR-13 piggyback
- `test_destructive_actions.py` — FR-27 idempotency end-to-end

## Replay-harness 30-day gate

`tools/replay_harness.py` is invoked AFTER the scenario suite. Pulls
v1-30d traces from LFS via `tools/pull_replay_traces.py`. Pass criterion:
fault-cycle agreement ≥95% (CONTEXT D-03; FR-24 SC#4 last paragraph).
Trace fixtures live at `tests/fixtures/replay/v1-30d/`; refresh cadence
is documented in that directory's README.

## Why nightly + workflow_dispatch (not per-PR)

Per CONTEXT D-01: the full scenario suite runs ~45 min including the
modem-reset wallclocks plus the replay-harness 30-day gate; per-PR HIL
would gate every PR on a 90-min budget. Per-tag-only is too coarse —
the Phase 4 EXIT bar requires a green HIL run BEFORE tagging, which
would be circular if HIL only fires on tag. Nightly + manual dispatch
is the operational compromise.
