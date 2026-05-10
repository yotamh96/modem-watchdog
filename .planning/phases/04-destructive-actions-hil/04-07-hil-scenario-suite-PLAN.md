---
plan: 04-07
title: HIL scenario suite + Phase-3 piggyback + replay-harness 30-day gate
phase: 04
wave: 6
depends_on: [04-01, 04-02, 04-03, 04-04, 04-05, 04-06]
files_modified:
  - tests/hil/scenarios/__init__.py
  - tests/hil/scenarios/test_boot_to_healthy.py
  - tests/hil/scenarios/test_sim_swap.py
  - tests/hil/scenarios/test_soft_reset_sim_app_detected.py
  - tests/hil/scenarios/test_modem_reset_after_soft.py
  - tests/hil/scenarios/test_three_modem_hang.py
  - tests/hil/scenarios/test_rf_event_no_destructive.py
  - tests/hil/scenarios/test_proxy_died_recovery.py
  - tests/hil/scenarios/test_destructive_actions.py
  - tests/hil/scenarios/test_qmi_wwan_reload_clean_transition.py
  - tests/hil/scenarios/test_sigterm_within_5s.py
  - tests/hil/scenarios/test_ctl_reset_state_serialisation.py
  - tests/hil/scenarios/test_watchdog_90s_actual_fire.py
  - tests/property/__init__.py
  - tests/property/conftest.py
  - tests/property/test_destructive_idempotency.py
  - .github/workflows/hil.yml
autonomous: false   # Wave-3 Task 3 is a checkpoint:human-verify on bench Jetson
requirements: [FR-23, FR-24, FR-27]
must_haves:
  truths:
    - "tests/hil/scenarios/ contains 12 scenario files: 7 Phase-4 SC#4 + 4 Phase-3 piggyback + 1 destructive-actions end-to-end"
    - "Each scenario file has pytestmark = [pytest.mark.linux_only, pytest.mark.hil, pytest.mark.skipif(sys.platform == 'win32', ...), pytest.mark.asyncio]"
    - "Each scenario uses real bench-Jetson modems (NO FakeRunner) and tests/hil/fault_inject.py helpers (Plan 04-06)"
    - "tests/property/__init__.py + conftest.py + test_destructive_idempotency.py establish the property test tier (PATTERNS correction #6 — net-new directory)"
    - "test_destructive_idempotency uses hypothesis to verify back-to-back invocations of each destructive action produce identical observable end-state (FR-27 / SC#1)"
    - ".github/workflows/hil.yml is updated to invoke the replay-harness 30-day gate AFTER the scenario suite passes; gate criterion is fault-cycle agreement >=95%"
    - "The replay-harness invocation handles BOTH new fixture-directory layouts (sha256-redacted v1-30d) and the existing Plan 02-10 synthetic fixtures"
    - "Phase 4 EXIT bar: all 12 HIL scenarios green on bench Jetson + replay-harness >=95%; the human-verify checkpoint validates this state"
  artifacts:
    - path: "tests/hil/scenarios/test_three_modem_hang.py"
      provides: "FR-24 driver_reset 75% gate end-to-end"
    - path: "tests/hil/scenarios/test_proxy_died_recovery.py"
      provides: "FR-24 SC#4 pkill -9 qmi-proxy → driver_reset recovery"
    - path: "tests/hil/scenarios/test_rf_event_no_destructive.py"
      provides: "FR-23 signal-gate end-to-end (config-injected forced rf_blocked)"
    - path: "tests/hil/scenarios/test_destructive_actions.py"
      provides: "FR-27 idempotency end-to-end on real hardware (each destructive action runs)"
    - path: "tests/hil/scenarios/test_qmi_wwan_reload_clean_transition.py"
      provides: "Phase 3 deferred SC#5 piggyback"
    - path: "tests/hil/scenarios/test_sigterm_within_5s.py"
      provides: "Phase 3 deferred SC#3 piggyback"
    - path: "tests/hil/scenarios/test_ctl_reset_state_serialisation.py"
      provides: "Phase 3 deferred SC#4 (concurrent flock) piggyback"
    - path: "tests/hil/scenarios/test_watchdog_90s_actual_fire.py"
      provides: "Phase 3 deferred WatchdogSec piggyback"
    - path: "tests/property/test_destructive_idempotency.py"
      provides: "FR-27 / SC#1 hypothesis-driven idempotency property"
  key_links:
    - from: "tests/hil/scenarios/*"
      to: "tests/hil/fault_inject.py"
      via: "import (Plan 04-06)"
      pattern: "from tests.hil.fault_inject import"
    - from: ".github/workflows/hil.yml"
      to: "tools/replay_harness.py"
      via: "post-scenario invocation"
      pattern: "tools.replay_harness|replay_harness\\.py"
---

<objective>
Land the actual HIL scenario suite on top of Plan 04-06's infrastructure
scaffold:

1. **Phase 4 SC#4 scenarios (7 files):** Each maps to one bullet of FR-24
   SC#4 — boot-to-Healthy, SIM swap, SIM-app issue → soft_reset, registration
   loss → modem_reset after soft_reset, three-modem QMI hang → driver_reset,
   RF event keeps daemon out of destructive resets, pkill -9 qmi-proxy →
   driver_reset.

2. **Phase-3 piggyback scenarios (4 files):** Per CONTEXT D-04, the bench
   Jetson run validates Phase 3's deferred SCs alongside Phase 4's net-new
   ones — qmi_wwan reload as clean state transition, SIGTERM ≤5 s with real
   flock, concurrent ctl reset-state serialisation, WatchdogSec=90s actual-fire.

3. **One end-to-end destructive-actions test (1 file):** Each of soft_reset
   / modem_reset / usb_reset / driver_reset runs against a real EM7421;
   verifies FR-27 idempotency (back-to-back) on real hardware.

4. **Property test for idempotency (1 file):** Hypothesis-driven; runs
   against fakes (NOT bench Jetson) for fast feedback. Per PATTERNS correction
   #6, `tests/property/` is a net-new directory; this plan creates the
   `__init__.py` + `conftest.py` skeleton too.

5. **Replay-harness 30-day gate in workflow:** The HIL workflow's final
   step invokes `tools/replay_harness.py` against the LFS-pulled v1-30d
   directory; pass criterion is fault-cycle agreement ≥95% per CONTEXT D-03.

6. **Phase 4 EXIT human-verify checkpoint:** A `checkpoint:human-verify` task
   that captures the developer manually triggering the HIL workflow on the
   bench Jetson and confirming all 12 scenarios + the replay gate pass.

This plan is the LAST plan of Phase 4 and depends on every preceding plan
(04-01..04-06): destructive ActionKinds registered (04-01/02/03), engine
ladder + signal gate (04-04), ActionSkipped event variant (04-05), HIL infra
(04-06).
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
@.planning/phases/04-destructive-actions-hil/04-RESEARCH.md
@.planning/phases/04-destructive-actions-hil/04-06-hil-infra-scaffold-PLAN.md
@docs/RECOVERY_SPEC.md
@docs/MIGRATION.md
@CLAUDE.md

<interfaces>
<!-- Verbatim from PATTERNS.md / source — executor uses these directly. -->

From tests/integration/test_lifecycle.py:1-70 (the integration-test scaffold; HIL scenarios deviate by using REAL fault_inject helpers instead of FakeRunner):
```python
"""Phase 3 SC #1..#5 integration tests via Fake* injection (Linux dev host).
...
Module-level pytestmark = [linux_only, asyncio]: filesystem inode
semantics (rename, truncate-in-place) + real flock are POSIX; Windows
dev hosts skip cleanly. ...
"""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from spark_modem.config.settings import Settings
from spark_modem.daemon.cycle_driver import CycleDriver
...

pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="Filesystem inode semantics + real flock are POSIX (linux_only suite)",
    ),
    pytest.mark.asyncio,
]
```

HIL scenario pytestmark (PATTERNS § "tests/hil/scenarios/test_*.py"):
```python
pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.hil,
    pytest.mark.skipif(sys.platform == "win32", reason="..."),
    pytest.mark.asyncio,
]
```

From tests/hil/conftest.py (the bench Jetson topology fixture from Plan 04-06):
```python
@pytest.fixture(scope="session")
def bench_jetson_topology() -> dict[str, list[str]]:
    return {
        "usb_paths": ["2-3.1.1", "2-3.1.2", "2-3.1.3", "2-3.1.4"],
        "cdc_wdm_paths": ["/dev/cdc-wdm0", "/dev/cdc-wdm1", "/dev/cdc-wdm2", "/dev/cdc-wdm3"],
    }
```

From tests/hil/fault_inject.py (Plan 04-06 helpers — 7 functions):
```python
async def inject_sim_power_off(cdc_wdm: str) -> None: ...
async def inject_sim_power_on(cdc_wdm: str) -> None: ...
async def inject_qmi_proxy_kill() -> None: ...
async def inject_kmsg(text: str) -> None: ...
async def inject_offline(cdc_wdm: str) -> None: ...
async def inject_online(cdc_wdm: str) -> None: ...
async def inject_thermal_critical() -> None: ...
```

From docs/MIGRATION.md §2 (the canonical SC#4 list):
1. Boot to Healthy: 4 modems → Healthy in ≤60 s
2. SIM swap detected within one cycle
3. SIM `app_state_detected` resolved by soft_reset
4. `not_registered_searching` resolved by modem_reset after one soft_reset
5. Three-modem QMI hang triggers driver_reset (no thrash, no per-modem usb_reset race)
6. RF event keeps daemon out of destructive resets (cheap actions still run)
7. `pkill -9 qmi-proxy` mid-cycle is detected and recovered with one driver_reset
8. Replay-harness fault-cycle agreement against ≥30 days of v1 traces ≥95%

Plan 02-10 replay harness location and shape: `tools/replay_harness.py` (Phase 2; reads `tests/fixtures/replay/<scenario>/<NNN>.json` shape). Phase 4 points it at `tests/fixtures/replay/v1-30d/`.

`spark-modem ctl support-bundle` (Plan 02-09) is invoked on failure to capture the events.jsonl + state + status snapshot.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create the 12 HIL scenario test files + tests/property/ skeleton + idempotency property test</name>
  <files>
    tests/hil/scenarios/__init__.py,
    tests/hil/scenarios/test_boot_to_healthy.py,
    tests/hil/scenarios/test_sim_swap.py,
    tests/hil/scenarios/test_soft_reset_sim_app_detected.py,
    tests/hil/scenarios/test_modem_reset_after_soft.py,
    tests/hil/scenarios/test_three_modem_hang.py,
    tests/hil/scenarios/test_rf_event_no_destructive.py,
    tests/hil/scenarios/test_proxy_died_recovery.py,
    tests/hil/scenarios/test_destructive_actions.py,
    tests/hil/scenarios/test_qmi_wwan_reload_clean_transition.py,
    tests/hil/scenarios/test_sigterm_within_5s.py,
    tests/hil/scenarios/test_ctl_reset_state_serialisation.py,
    tests/hil/scenarios/test_watchdog_90s_actual_fire.py,
    tests/property/__init__.py,
    tests/property/conftest.py,
    tests/property/test_destructive_idempotency.py
  </files>
  <read_first>
    - tests/hil/conftest.py (Plan 04-06 — `bench_jetson_topology` session fixture)
    - tests/hil/fault_inject.py (Plan 04-06 — the 7 helpers; one helper per fault path)
    - tests/integration/test_lifecycle.py (the integration-test analog; HIL scenarios share the asyncio-with-pytestmark shape but use REAL fault injection instead of fakes)
    - tests/unit/actions/_helpers.py:70-99 (`make_ctx`/`ok` helpers — used by the property test for fast feedback against fakes)
    - .planning/phases/04-destructive-actions-hil/04-PATTERNS.md § "tests/hil/scenarios/test_*.py" + § "Wave-0 stubs" + § "No Analog Found" (tests/property/ net-new)
    - .planning/phases/04-destructive-actions-hil/04-RESEARCH.md § "Sampling Rate" Plan 04-07 row (12 scenarios + 1 replay-gate)
    - docs/MIGRATION.md §2 (canonical SC#4 list verbatim)
    - docs/RECOVERY_SPEC.md §10 (worked examples — fault scenarios cite the same input/output shape)
  </read_first>
  <action>
**Step A — Create `tests/hil/scenarios/__init__.py`** (empty package marker).

**Step B — Create `tests/property/__init__.py`** (empty package marker — PATTERNS correction #6).

**Step C — Create `tests/property/conftest.py`:**

```python
"""Property-test shared fixtures.

This tier uses hypothesis for property-based testing. Per Phase 4 plan
04-07 (PATTERNS correction #6 -- net-new directory), the conftest provides
shared `make_ctx`-style helpers reusing tests/unit/actions/_helpers.py.

Tests in this directory MAY be slow (hypothesis runs many examples); they
run as part of `pytest -m "unit or integration"` (no separate marker
needed for the property tier — they ARE unit tests, just hypothesis-driven).
"""

from __future__ import annotations

import pytest


@pytest.fixture
def hypothesis_seed() -> int:
    """Deterministic seed for property-test reproduction."""
    return 42
```

**Step D — Create the 12 HIL scenario files.** Each follows this template
(replace BODY with scenario-specific logic):

```python
"""<scenario name> — <Phase 4 SC# or Phase 3 piggyback ID> (HIL).

<one-paragraph description of what this scenario proves>.

Per CONTEXT D-04: this scenario lives in tests/hil/scenarios/ and runs ONLY
on the bench-Jetson runner (linux_only + hil markers).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from tests.hil.fault_inject import (
    inject_sim_power_off,
    # ... only the helpers this scenario needs
)


pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.hil,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="HIL bench Jetson is Linux/aarch64; tests touch /dev/cdc-wdm and /dev/kmsg.",
    ),
    pytest.mark.asyncio,
]


_SUPPORT_BUNDLE = Path("/tmp/spark-modem-support-bundle.tar.gz")


# BODY: scenario test functions go here.
```

For EACH scenario file, the test body invokes the relevant fault_inject
helper(s), polls `spark-modem status` (or reads `/var/lib/spark-modem-watchdog/
status.json` directly), and asserts the expected state transition completed
within the documented latency budget. Use the asyncio-friendly pattern:

```python
async def _wait_for_state(usb_path: str, expected_state: str, *, timeout: float = 60.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    status_path = Path("/var/lib/spark-modem-watchdog/status.json")
    while asyncio.get_event_loop().time() < deadline:
        if status_path.exists():
            data = json.loads(status_path.read_text(encoding="utf-8"))
            for modem in data.get("per_modem", []):
                if modem.get("usb_path") == usb_path and modem.get("state") == expected_state:
                    return
        await asyncio.sleep(2.0)
    raise AssertionError(f"timeout waiting for {usb_path} to reach {expected_state}")
```

The 12 scenario files (with their key assertions):

1. **test_boot_to_healthy.py**: `systemctl restart spark-modem-watchdog`; assert all 4 modems reach state="healthy" within 60 s; assert `READY=1` was sent (look for `daemon_started` event in events.jsonl).

2. **test_sim_swap.py**: requires manual SIM swap by the operator BEFORE the test runs (Phase 4 VALIDATION.md "Manual-Only Verifications" — keep this scenario as `pytest.mark.skip("requires manual SIM swap")` OR mark `xfail` with a reason; the developer triggers manually). Document the procedure in the docstring; the test itself reads the SimSwapped event from events.jsonl after the manual step.

3. **test_soft_reset_sim_app_detected.py**: `await inject_sim_power_off(cdc_wdm0); await asyncio.sleep(2)` (let the daemon observe sim_app_detected after re-power); the cheap action sim_power_on should fire → modem returns to healthy. Assert: no destructive action fired (no `action_executed{kind=soft_reset|modem_reset|usb_reset}` in events.jsonl since the test start). NOTE: per CONTEXT, `app_state_detected` is the SC#4 trigger — but cheap `sim_power_on` is the actual recovery; soft_reset only fires if sim_power_on doesn't resolve. Adjust scenario to provoke a state where soft_reset is the chosen action (e.g. inject_offline + observe).

4. **test_modem_reset_after_soft.py**: `await inject_offline(cdc_wdm0); wait for soft_reset; if not recovered after 90 s wait window (the ladder cross-action gate from Plan 04-04), assert modem_reset fires next; modem reaches healthy after another 60-90 s`. This exercises the ladder progression FR-22 SC#4.

5. **test_three_modem_hang.py**: simulate 3 of 4 modems QMI-hung. Per RESEARCH the cleanest fault is `await inject_offline(cdc_wdm0); inject_offline(cdc_wdm1); inject_offline(cdc_wdm2)` then wait. With 3/4 hung + at least one with actionable signal, `_global_driver_reset_eligible` returns True → driver_reset fires once. Assert: events.jsonl contains exactly ONE `action_executed{kind=driver_reset}` in the test window; assert no per-modem `usb_reset` fired (the cycle short-circuit prevents per-modem actions on the same cycle); assert `actions_total{kind="driver_reset",result="success"}` Prometheus counter incremented by 1 (scrape `/run/spark-modem-watchdog/metrics.sock`).

6. **test_rf_event_no_destructive.py**: this is the CONFIG-INJECTED forced rf_blocked test (per CONTEXT D-02 last paragraph — no real RF detuning hardware). Write a temporary `99-test-rf.yaml` to `/etc/spark-modem-watchdog/conf.d/` setting `signal_rsrp_floor_dbm: 999` (impossible-to-meet floor) and SIGHUP the daemon; modem state.rf_blocked goes True; trigger any issue that would otherwise fire MODEM_RESET (e.g. inject_offline); assert ActionSkipped(reason=signal_below_gate) emitted in events.jsonl; assert no destructive action_executed events. Cleanup: remove the YAML and SIGHUP again.

7. **test_proxy_died_recovery.py**: `await inject_qmi_proxy_kill()`; observe per-modem `qmi_proxy_died` issues classified across all 4 modems; per CONTEXT C-02, the daemon does NOT bypass the 75% threshold for proxy_died — but ALL 4 will time out within ~8 s anyway, so the next cycle has 4/4 hung → driver_reset fires; assert exactly ONE driver_reset; assert qmi-proxy is restarted by Zao (verify by re-checking the qmicli channels are responsive); modems return to healthy within 90 s.

8. **test_destructive_actions.py**: end-to-end FR-27 idempotency on real hardware. For each of `soft_reset`, `modem_reset`, `usb_reset`, run `spark-modem reset --action=<kind> --modem=cdc-wdm0` twice in a row; assert exit 0 both times; assert modem returns to healthy after each run; assert end-state (operating_mode=online + raw_ip=Y) is identical between the two runs. For `driver_reset`, run `spark-modem reset --action=driver_reset --global` twice; assert similar. Per A-05: "back-to-back invocations both run; per-modem flock serializes; end-state identical". This scenario is the canonical SC#1 idempotency exercise.

9. **test_qmi_wwan_reload_clean_transition.py** (Phase 3 piggyback): `await asyncio.to_thread(subprocess.run, ["modprobe", "-r", "qmi_wwan"], check=True); await asyncio.sleep(1); await asyncio.to_thread(subprocess.run, ["modprobe", "qmi_wwan"], check=True)`. Assert daemon does NOT crash (read /proc/<pid>/status to confirm still running); assert state transitions through `disconnected → recovering → healthy` in events.jsonl (NFR-12). This piggyback validates the Phase 3 deferred SC#5.

10. **test_sigterm_within_5s.py** (Phase 3 piggyback): get the daemon PID; `await asyncio.to_thread(subprocess.run, ["systemctl", "stop", "spark-modem-watchdog"])`; measure wallclock; assert exit happens within 5 s; assert `daemon_stopped` event with reason="sigterm" in events.jsonl (FR-53). Restart the daemon at end of test.

11. **test_ctl_reset_state_serialisation.py** (Phase 3 piggyback): launch two `spark-modem ctl reset-state --modem=cdc-wdm0` invocations concurrently via `asyncio.gather`; assert both complete with exit 0; assert no "lost update" — the per-modem state file's `counters` dict was reset exactly once (read state file before and after). Per FR-61.1.

12. **test_watchdog_90s_actual_fire.py** (Phase 3 piggyback): SIGSTOP the qmicli child of the daemon (find via `pgrep -P <daemon-pid> qmicli`); wait 90 s; assert `systemctl status spark-modem-watchdog` reports `Result: watchdog`; assert daemon was restarted (PID changed); assert `daemon_started` event followed by recovery transitions in events.jsonl. Per FR-75 / NFR-13. NOTE: this is destructive to the bench Jetson's ongoing operation; mark with `pytest.mark.skipif(<env var BENCH_JETSON_DESTRUCTIVE_TESTS_OK != "true">)` so it runs only when explicitly enabled.

**Step E — Create `tests/property/test_destructive_idempotency.py`:**

```python
"""Property-test: each destructive action is genuinely re-runnable (FR-27 / SC#1).

Hypothesis-driven: parametrize over the three destructive ActionKinds (driver_reset
is global and not parametrized here -- the scenario test_destructive_actions.py on
the bench Jetson covers it). For each ActionKind, run execute() twice in a row
against the SAME ActionContext; assert the second invocation produces the same
ActionResult.kind and same overall outcome (succeeded value).

Uses fakes (FakeRunner + tmp_path sysfs_root) -- runs in the regular
`pytest -m "unit or integration"` suite, not the HIL suite. The HIL scenario
test_destructive_actions.py is the bench-Jetson-real-hardware counterpart.
"""

from __future__ import annotations

from pathlib import Path

import hypothesis
import pytest
from hypothesis import strategies as st

from spark_modem.actions import driver_reset, modem_reset, usb_reset
from spark_modem.actions.context import ActionContext
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind
from tests.unit.actions._helpers import make_ctx, ok
from tests.fakes.runner import FakeRunner


@hypothesis.given(
    usb_leaf=st.integers(min_value=1, max_value=4),
)
@pytest.mark.asyncio
async def test_modem_reset_back_to_back_idempotent(usb_leaf: int, tmp_path: Path) -> None:
    runner = FakeRunner()
    # Register the qmicli reset call to return ok both times
    argv = ["qmicli", "--device-open-proxy", "--device=/dev/cdc-wdm0",
            "--dms-set-operating-mode=reset"]
    runner.register(argv, ok(argv))
    runner.register(argv, ok(argv))   # second invocation; FakeRunner is sequential

    ctx, _logger, _clock = make_ctx(runner, sysfs_root=tmp_path)
    who = WhoModem(usb_path=f"2-3.1.{usb_leaf}", cdc_wdm="cdc-wdm0")

    r1 = await modem_reset.execute(who, ctx)
    r2 = await modem_reset.execute(who, ctx)
    assert r1.kind == r2.kind == ActionKind.MODEM_RESET
    assert r1.succeeded == r2.succeeded
    # Both runs went through; FakeRunner saw 2 invocations
    assert len(runner.calls) == 2


@hypothesis.given(
    usb_leaf=st.integers(min_value=1, max_value=4),
    target=st.sampled_from(["child-port", "parent-hub"]),
)
@pytest.mark.asyncio
async def test_usb_reset_back_to_back_idempotent(
    usb_leaf: int, target: str, tmp_path: Path
) -> None:
    runner = FakeRunner()
    ctx_base, _logger, _clock = make_ctx(runner, sysfs_root=tmp_path)
    # Construct ActionContext with the target field
    from dataclasses import replace
    ctx = replace(ctx_base, target=target)

    # Pre-create the sysfs targets
    drivers_dir = tmp_path / "bus" / "usb" / "drivers" / "usb"
    drivers_dir.mkdir(parents=True, exist_ok=True)
    (drivers_dir / "unbind").write_text("")
    (drivers_dir / "bind").write_text("")

    who = WhoModem(usb_path=f"2-3.1.{usb_leaf}", cdc_wdm="cdc-wdm0")

    r1 = await usb_reset.execute(who, ctx)
    r2 = await usb_reset.execute(who, ctx)
    assert r1.kind == r2.kind == ActionKind.USB_RESET
    assert r1.succeeded == r2.succeeded


@hypothesis.given(
    usb_leaf=st.integers(min_value=1, max_value=4),
)
@pytest.mark.asyncio
async def test_driver_reset_back_to_back_idempotent(
    usb_leaf: int, tmp_path: Path
) -> None:
    runner = FakeRunner()
    # Register both modprobe argvs twice (back-to-back)
    runner.register(["modprobe", "-r", "qmi_wwan"], ok(["modprobe", "-r", "qmi_wwan"]))
    runner.register(["modprobe", "qmi_wwan"], ok(["modprobe", "qmi_wwan"]))
    runner.register(["modprobe", "-r", "qmi_wwan"], ok(["modprobe", "-r", "qmi_wwan"]))
    runner.register(["modprobe", "qmi_wwan"], ok(["modprobe", "qmi_wwan"]))

    ctx, _logger, _clock = make_ctx(runner, sysfs_root=tmp_path)
    who = WhoModem(usb_path=f"2-3.1.{usb_leaf}", cdc_wdm="cdc-wdm0")

    r1 = await driver_reset.execute(who, ctx)
    r2 = await driver_reset.execute(who, ctx)
    assert r1.kind == r2.kind == ActionKind.DRIVER_RESET
    assert r1.succeeded == r2.succeeded
```

NOTE: This property test runs against FAKES — production qmicli/modprobe
behavior on real hardware is verified by `test_destructive_actions.py` in the
HIL tier. Hypothesis adds confidence that the action implementations are
mathematically idempotent (same input → same outcome) without flake from
real-network/real-hardware variance.

Per CLAUDE.md / per Wave 3: this plan does NOT modify src/ — it only adds
test files. SP-04 lint scope is unaffected. The bench Jetson scenarios use
real subprocess (tests/ tier is SP-04-exempt by Plan 03-09 precedent and
`scripts/lint_no_subprocess.sh:11` scope).
  </action>
  <verify>
    <automated>cd /s/spark/modem-watchdog &amp;&amp; .venv/bin/pytest --collect-only -q tests/hil/scenarios/ tests/property/ &amp;&amp; .venv/bin/pytest tests/property/ -x &amp;&amp; .venv/bin/ruff check tests/hil/scenarios/ tests/property/ &amp;&amp; .venv/bin/ruff format --check tests/hil/scenarios/ tests/property/ &amp;&amp; bash scripts/lint_no_subprocess.sh</automated>
  </verify>
  <acceptance_criteria>
    - File exists: `tests/hil/scenarios/__init__.py`
    - File exists: `tests/property/__init__.py`
    - File exists: `tests/property/conftest.py`
    - File exists: `tests/property/test_destructive_idempotency.py`
    - 12 files exist under `tests/hil/scenarios/`: test_boot_to_healthy.py, test_sim_swap.py, test_soft_reset_sim_app_detected.py, test_modem_reset_after_soft.py, test_three_modem_hang.py, test_rf_event_no_destructive.py, test_proxy_died_recovery.py, test_destructive_actions.py, test_qmi_wwan_reload_clean_transition.py, test_sigterm_within_5s.py, test_ctl_reset_state_serialisation.py, test_watchdog_90s_actual_fire.py
    - `grep -lF 'pytest.mark.hil' tests/hil/scenarios/test_*.py | wc -l` returns 12 (every scenario file has the hil mark)
    - `grep -lF 'pytest.mark.linux_only' tests/hil/scenarios/test_*.py | wc -l` returns 12
    - `grep -lF 'sys.platform == "win32"' tests/hil/scenarios/test_*.py | wc -l` returns 12 (all have skipif win32)
    - `grep -lF 'from tests.hil.fault_inject import' tests/hil/scenarios/test_*.py | wc -l` ≥10 (most scenarios use at least one fault helper; 2 scenarios may not — boot_to_healthy and sim_swap which is manual-trigger)
    - `pytest --collect-only -q tests/hil/scenarios/` exits 0 with ≥12 tests collected (Linux dev host) OR collects nothing on Windows (collect_ignore_glob in conftest)
    - `pytest --collect-only -q tests/property/` exits 0 with ≥3 tests collected
    - `pytest tests/property/ -x` exits 0 (idempotency property tests pass against fakes)
    - `ruff check tests/hil/scenarios/ tests/property/` exits 0
    - `ruff format --check tests/hil/scenarios/ tests/property/` exits 0
    - `bash scripts/lint_no_subprocess.sh` exits 0 (tests/ tier remains SP-04-exempt)
    - `pytest -m hil --collect-only -q` returns the 12 HIL scenarios (the marker filter works)
    - `pytest -m "not hil" --collect-only -q tests/hil/` returns 0 (the not-hil filter excludes them)
  </acceptance_criteria>
  <done>
    12 HIL scenario files + tests/property/ skeleton + 3 hypothesis idempotency tests; all collected by pytest with correct markers; property tests pass against fakes.
  </done>
</task>

<task type="auto">
  <name>Task 2: Update .github/workflows/hil.yml to invoke replay-harness 30-day gate after scenario suite</name>
  <files>
    .github/workflows/hil.yml
  </files>
  <read_first>
    - .github/workflows/hil.yml (Plan 04-06 ships the workflow without the replay-harness step; Plan 04-07 appends it)
    - tools/replay_harness.py (or whatever Plan 02-10 named it — find via `grep -lF replay_harness tools/`)
    - tests/fixtures/replay/v1-30d/README.md (the consumer documentation Plan 04-06 wrote)
    - .planning/phases/04-destructive-actions-hil/04-CONTEXT.md § D-03 (>=95% gate criterion)
  </read_first>
  <action>
Locate the existing HIL workflow file at `.github/workflows/hil.yml` (Plan 04-06 created it). Find the step `Run HIL scenario suite` and APPEND a new step AFTER it (before the failure-artefact upload steps). Insert:

```yaml
      - name: Replay-harness 30-day fault-cycle agreement gate
        run: |
          .venv/bin/python -m tools.replay_harness \
            --fixtures-dir tests/fixtures/replay/v1-30d/ \
            --min-fault-cycle-agreement 0.95 \
            --report-output /tmp/replay-harness-report.json
        # Exit code 0 = >=95% agreement met
        # Exit code 1 = <95% — blocks Phase 4 EXIT bar

      - name: Upload replay-harness report
        if: always()   # upload report whether pass or fail for diagnostics
        uses: actions/upload-artifact@v4
        with:
          name: replay-harness-report-${{ github.run_id }}
          path: /tmp/replay-harness-report.json
          if-no-files-found: warn
          retention-days: 14
```

The exact CLI flags (`--fixtures-dir`, `--min-fault-cycle-agreement`,
`--report-output`) MAY need to be adjusted to match the actual
`tools/replay_harness.py` flag surface from Plan 02-10. Read
`tools/replay_harness.py` (find via `grep -lF replay_harness tools/`) and
adjust the workflow invocation to use the actual flag names. If the existing
harness doesn't take a `--min-fault-cycle-agreement` arg, either:
  (a) extend the harness with a small flag addition (single-line change), or
  (b) wrap the invocation in a shell `if` reading the report-output JSON's
      agreement field and exiting non-zero if <0.95.

Document the chosen approach in the workflow YAML comment.

The replay-harness gate is the **Phase 4 EXIT bar criterion** per CONTEXT D-03
and FR-24 SC#4 last paragraph. If the gate fails, the workflow run is red and
Phase 4 cannot exit.

Per CLAUDE.md: this is a workflow YAML edit only; no src/ changes; SP-04 lint
unaffected.
  </action>
  <verify>
    <automated>cd /s/spark/modem-watchdog &amp;&amp; .venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/hil.yml'))" &amp;&amp; grep -F 'replay-harness' .github/workflows/hil.yml &amp;&amp; grep -F 'replay-harness-report' .github/workflows/hil.yml</automated>
  </verify>
  <acceptance_criteria>
    - `.github/workflows/hil.yml` contains a step named `Replay-harness 30-day fault-cycle agreement gate`
    - `grep -F 'tools.replay_harness' .github/workflows/hil.yml` returns ≥1 match (the invocation)
    - `grep -F 'tests/fixtures/replay/v1-30d' .github/workflows/hil.yml` returns ≥1 match (the input directory)
    - `grep -F '0.95' .github/workflows/hil.yml` returns ≥1 match (the agreement threshold)
    - `grep -F 'replay-harness-report' .github/workflows/hil.yml` returns ≥1 match (the artefact upload)
    - `python -c "import yaml; yaml.safe_load(open('.github/workflows/hil.yml'))"` exits 0 (YAML still parseable after edit)
    - The replay-harness step is positioned AFTER the `Run HIL scenario suite` step (verify by reading workflow line ordering — the gate runs only if scenarios pass)
    - The replay-harness-report artefact upload uses `if: always()` so the report is captured for diagnostics whether the gate passes or fails
  </acceptance_criteria>
  <done>
    Workflow gates Phase 4 EXIT on replay-harness fault-cycle agreement >=95%; report uploaded as artefact; YAML parses cleanly.
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 3: Phase 4 EXIT — bench-Jetson HIL run + replay-harness gate green</name>
  <what-built>
    Phase 4 has shipped:
    - 3 destructive actions (modem_reset, usb_reset, driver_reset) registered in dispatcher.
    - Engine ladder (policy/ladder.py) with per-action counters; signal-gate Settings (RELOAD_DATA); ActionSkipped event variant.
    - HIL workflow (.github/workflows/hil.yml) with 12 bench-Jetson scenarios + replay-harness 30-day fault-cycle agreement gate (>=95%).
    - Sierra-bootloader handling via parent-hub usb_reset variant (--target=parent-hub CLI flag).
    - All Phase 1+2+3 invariants preserved (pure-engine policy, list-form argv, atomic state writes, per-modem flock, match-on-state, etc.).

    Plan 04-07 Tasks 1+2 have been merged. The HIL workflow file exists and is valid YAML; 12 scenarios are collected by `pytest -m hil`; the property tests (tests/property/) pass against fakes.

    What's left is the actual bench-Jetson hardware run — which Claude cannot do because Phase 4 EXIT is the integration of REAL EM7421 modems on REAL USB hub 2-3.1.{1..4} on the REAL Jetson Orin NX. This is the deliberate `checkpoint:human-verify` per CONTEXT D-04 absorption of Phase 3 deferred SCs + Phase 4 net-new SCs.
  </what-built>
  <how-to-verify>
    On a developer machine with access to the bench Jetson:

    1. **Verify the HIL workflow runs cleanly via workflow_dispatch:**
       - Navigate to https://github.com/<repo>/actions/workflows/hil.yml
       - Click "Run workflow" → select branch (the integration branch with all Phase 4 plans merged) → click "Run workflow".
       - Wait for the run to complete (≤90 min wall budget per CONTEXT D-01).

    2. **Verify all 12 HIL scenarios passed.** In the workflow run summary, click on the `hil` job; expand the "Run HIL scenario suite" step; verify the pytest output shows `12 passed` (or close — `test_sim_swap.py` may be marked skipped/xfail depending on whether the SIM swap was performed manually, and `test_watchdog_90s_actual_fire.py` may be skipped if `BENCH_JETSON_DESTRUCTIVE_TESTS_OK` env var was not set on the runner). Acceptable: ≥10 of 12 scenarios PASSED outright; the others SKIPPED with documented reason.

    3. **Verify the replay-harness gate passed.** Expand the "Replay-harness 30-day fault-cycle agreement gate" step; verify exit code 0; verify the printed agreement percentage is ≥95.0%.

    4. **Verify no regressions in the unit/integration suite.** From the same integration branch, locally run:
       ```bash
       cd /path/to/spark-modem-watchdog
       .venv/bin/pytest -m "unit or integration" -ra
       ```
       Verify exit 0; verify test count is ≥1875 (Phase 3 was 1835; Phase 4 adds ~50-100 unit tests across plans 04-01..06).

    5. **Sanity-check the bench Jetson is in a clean post-test state.** SSH into the bench Jetson:
       ```bash
       systemctl status spark-modem-watchdog   # active (running)
       cat /var/lib/spark-modem-watchdog/status.json | jq .aggregate  # all 4 modems healthy
       lsusb | grep "1199:9091" | wc -l   # = 4 (no modem stuck in bootloader after the HIL run)
       ```

    6. **If any of steps 1-5 fail:**
       - Download the support-bundle artefact from the workflow run.
       - Open an issue with title "Phase 4 EXIT bar failure" and attach the support bundle + replay-harness-report.json.
       - Resume signal: "blocked — bench Jetson failure: <summary>".

    7. **If all pass:** Resume signal: "approved — Phase 4 EXIT". Update STATE.md "Deferred Items" to mark the Phase 3 piggyback row as RESOLVED. Update ROADMAP.md to mark Phase 4 as complete.
  </how-to-verify>
  <resume-signal>Type "approved — Phase 4 EXIT" or describe issues</resume-signal>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| HIL workflow → bench Jetson via self-hosted runner | Real CAP_SYS_MODULE, CAP_SYS_ADMIN; nightly fault injection physically de-enumerates modems; restricted to repo collaborators only (Plan 04-06 mitigation T-04-06-01) |
| Replay-harness consumes redacted v1-30d traces | LFS-pulled fixtures contain sha256[:8]-redacted ICCID/IMSI/IP per Plan 04-06 README; the harness itself reads JSON shards and produces a report — no PII flows out |
| HIL scenarios → events.jsonl writes | Each scenario triggers daemon-side state transitions and event emissions; events.jsonl is the audit trail; logrotate (Plan 03-04) bounds growth |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-07-01 | E (Elevation) | scenario test injects malicious /dev/kmsg pattern that triggers downstream action | mitigate | All `inject_kmsg` calls use literal patterns matching the Plan 03-05 closed-enum classifier (5 patterns LOCKED). Pattern injection is bounded; malicious patterns produce `IssueDetail.UNKNOWN` which does NOT route to any action |
| T-04-07-02 | D (Denial of service) | concurrent HIL runs thrash the bench Jetson | mitigate | Plan 04-06 workflow enforces `concurrency: group: hil-bench / cancel-in-progress: false` — serial; current run completes before next |
| T-04-07-03 | T (Tampering) | scenario writes to bench Jetson conf.d/ leak across runs | mitigate | `test_rf_event_no_destructive.py` writes a temporary `99-test-rf.yaml` and removes it in cleanup; the test framework's tmp_path semantics don't apply (real /etc), so the test MUST use a try/finally to ensure cleanup. Acceptance criterion grep verifies the cleanup branch exists |
| T-04-07-04 | I (Information disclosure) | bench Jetson SIM ICCID surfaces in events.jsonl during HIL scenarios | mitigate | Phase 3 SimSwapped event already redacts ICCID to sha256[:8] (Plan 03-07 wiring); HIL events.jsonl inherits the same redaction. Support-bundle artefact (Plan 02-09) further redacts on artefact upload |
| T-04-07-05 | R (Repudiation) | scenario test passes when daemon was never actually exercised | mitigate | Each scenario asserts BOTH the cause-event (the fault was injected) AND the recovery-event (the daemon responded) by reading events.jsonl. A test that injects a fault but doesn't see the daemon's recovery transition is a FAIL, not a SKIP |
| T-04-07-06 | E (Elevation) | tests/property/ idempotency test runs against real subprocess instead of fakes | mitigate | Property test imports from `tests.fakes.runner` — never touches real subprocess; the asyncio mode + FakeRunner ensure no real qmicli/modprobe invocation. The HIL scenario `test_destructive_actions.py` is the real-hardware counterpart and lives in tests/hil/ (correctly gated by hil marker) |
</threat_model>

<verification>
- All Plan 04-07 task `<verify>` commands pass.
- `pytest -m "unit or integration" -ra` exits 0 (full unit + integration suite — Phase 4 added ~50-100 tests; total ≥1875).
- `pytest -m hil --collect-only -q` returns ≥12 collected scenarios.
- `pytest tests/property/ -x` exits 0 (property test idempotency green).
- `python -c "import yaml; yaml.safe_load(open('.github/workflows/hil.yml'))"` exits 0.
- `ruff check tests/hil/ tests/property/` exits 0; `ruff format --check tests/hil/ tests/property/` exits 0.
- `bash scripts/lint_no_subprocess.sh` exits 0 (src/ tree untouched).
- **Phase 4 EXIT bar (Task 3 checkpoint):** human verifies the HIL workflow on the bench Jetson — all 12 scenarios pass + replay-harness gate ≥95%.
</verification>

<success_criteria>
- 12 HIL scenario files exist in `tests/hil/scenarios/`, each with the correct pytestmark (linux_only + hil + skipif win32 + asyncio).
- 7 Phase-4 SC#4 scenarios + 4 Phase-3 piggyback scenarios + 1 destructive-actions end-to-end scenario.
- `tests/property/` exists with `__init__.py` + `conftest.py` + `test_destructive_idempotency.py` (3 hypothesis tests covering modem_reset / usb_reset / driver_reset back-to-back invocation).
- `.github/workflows/hil.yml` runs the replay-harness 30-day fault-cycle agreement gate AFTER the scenario suite, with ≥95% pass criterion; report uploaded as artefact whether pass or fail.
- The Phase 4 EXIT human-verify checkpoint task captures the bench Jetson run + Phase 3 deferred SC resolution.
- CLAUDE.md invariants honored: src/ tree untouched (this plan is tests + workflow only); SP-04 lint scope unaffected; tests/ tier exempt by Plan 03-09 precedent.
- Full Phase 1+2+3+04-{01..06} regression suite stays green (pre-checkpoint).
- Phase 4 EXIT achieved when the human approves the checkpoint.
</success_criteria>

<output>
After completion, create `.planning/phases/04-destructive-actions-hil/04-07-SUMMARY.md`
documenting: 12 scenario files (with which Phase 4 SC# / Phase 3 deferral
each maps to), the property test tier creation (PATTERNS correction #6
honored), the workflow's replay-harness gate addition, the human-verify
checkpoint outcome ("approved — Phase 4 EXIT" or any deferral notes), the
Phase 3 deferred-items resolution (STATE.md update), and any flake
observations from the first nightly HIL runs (which scenarios needed
retries, what was the steady-state pass rate).

After the human checkpoint approves Phase 4 EXIT, also:
- Update STATE.md "Deferred Items" — mark the Phase 4 HIL row as RESOLVED.
- Update ROADMAP.md — mark Phase 4 row in the Progress table as Complete with completion date.
</output>
