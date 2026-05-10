---
plan: 04-06
title: HIL CI infrastructure scaffold (workflow, fault-injection helpers, LFS trace puller)
phase: 04
wave: 1
depends_on: []
files_modified:
  - .github/workflows/hil.yml
  - tests/hil/__init__.py
  - tests/hil/README.md
  - tests/hil/conftest.py
  - tests/hil/fault_inject.py
  - tools/pull_replay_traces.py
  - tests/fixtures/replay/v1-30d/.gitkeep
  - tests/fixtures/replay/v1-30d/.gitattributes
  - tests/fixtures/replay/v1-30d/README.md
autonomous: true
requirements: [FR-23, FR-24, FR-27]
must_haves:
  truths:
    - ".github/workflows/hil.yml exists with schedule (cron 0 4 * * *) + workflow_dispatch triggers, runs-on: [self-hosted, linux, ARM64, hil-bench], timeout-minutes: 90, concurrency group hil-bench with cancel-in-progress: false (serial; single bench Jetson per CONTEXT D-01)"
    - "Workflow invokes `pytest -m hil tests/hil/ -ra --tb=short` AFTER `python -m tools.pull_replay_traces` setup step"
    - "Workflow uploads support-bundle artefact on failure"
    - "tests/hil/fault_inject.py provides 7 module-level fault helpers covering: SIM power off/on, qmi-proxy kill, kmsg synthetic write, dms operating-mode offline + clear, thermal_critical synthesis, modem-offline-mode-clear (per CONTEXT D-02)"
    - "tools/pull_replay_traces.py is a stand-alone argparse script that resolves the LFS pointer at tests/fixtures/replay/v1-30d/ via `git lfs pull`; fails clearly on missing LFS auth (no silent skip)"
    - "tests/fixtures/replay/v1-30d/.gitattributes registers JSON shards as Git LFS pointers (`*.json filter=lfs diff=lfs merge=lfs -text` scoped to this directory)"
    - "tests/fixtures/replay/v1-30d/README.md documents quarterly refresh cadence, regeneration command, redaction-shape contract (sha256[:8]), and expected fixture-directory shape"
    - "tests/hil/__init__.py + tests/hil/README.md + tests/hil/conftest.py establish the HIL test tier (linux_only + hil markers via pytestmark)"
    - "hil pytest marker is already registered in pyproject.toml:78 (PATTERNS correction #3) — NO pyproject edit needed"
  artifacts:
    - path: ".github/workflows/hil.yml"
      provides: "Nightly + workflow_dispatch HIL CI job"
      contains: "schedule:"
    - path: "tests/hil/fault_inject.py"
      provides: "Software-only fault-injection helpers (qmicli, pkill, kmsg, modprobe)"
      contains: "def inject_qmi_proxy_kill"
    - path: "tools/pull_replay_traces.py"
      provides: "LFS pointer resolver for v1-30d traces"
      contains: "def main"
    - path: "tests/fixtures/replay/v1-30d/README.md"
      provides: "Quarterly refresh runbook"
      contains: "sha256"
    - path: "tests/fixtures/replay/v1-30d/.gitattributes"
      provides: "LFS pointer registration scoped to this dir"
      contains: "filter=lfs"
  key_links:
    - from: ".github/workflows/hil.yml"
      to: "tools/pull_replay_traces.py"
      via: "setup step"
      pattern: "tools.pull_replay_traces"
    - from: ".github/workflows/hil.yml"
      to: "tests/hil/"
      via: "pytest -m hil tests/hil/"
      pattern: "pytest -m hil"
    - from: "tests/hil/scenarios/* (Plan 04-07)"
      to: "tests/hil/fault_inject.py"
      via: "import"
      pattern: "from tests.hil.fault_inject import"
---

<objective>
Land the HIL CI infrastructure: the GitHub Actions workflow, the fault-
injection helper module, the Git LFS trace-pull tool, and the fixture
directory with README + .gitattributes. This plan ships the SCAFFOLD only;
Plan 04-07 lands the actual scenario tests that exercise the fault-inject
helpers. The plan's exit criterion is "HIL workflow runs (no scenarios yet)
on workflow_dispatch and reports a clean skip-no-tests-collected".

Per CONTEXT D-01: Nightly + workflow_dispatch on a self-hosted aarch64 runner
tethered to a bench Jetson with 4 EM7421s on USB hub 2-3.1.{1..4}; serial
concurrency; 90 min timeout; support-bundle artefact on failure.

Per CONTEXT D-02: Software-only fault injection. NO real RF detuning hardware
(out of project budget). qmicli-direct, pkill, scripted SIM power off/on,
dms-set-operating-mode=offline, synthetic /dev/kmsg writes.

Per CONTEXT D-03: 30-day v1 historical traces stored as Git LFS artefact at
`tests/fixtures/replay/v1-30d/`; sha256[:8]-redacted ICCID/IMSI/IP per Plan
02-09's ctl support-bundle redaction shape; quarterly refresh cadence.

**Important corrections from PATTERNS.md:**
- #3: `hil` pytest marker is ALREADY registered in `pyproject.toml:78`. Do
  NOT add a task to register it. The workflow file just invokes `pytest -m
  hil`.

Output:
- New: `.github/workflows/hil.yml`, `tests/hil/__init__.py`,
  `tests/hil/README.md`, `tests/hil/conftest.py`, `tests/hil/fault_inject.py`,
  `tools/pull_replay_traces.py`, `tests/fixtures/replay/v1-30d/.gitkeep`,
  `tests/fixtures/replay/v1-30d/.gitattributes`,
  `tests/fixtures/replay/v1-30d/README.md`.
- Tests: `tests/hil/` is import-clean (`pytest --collect-only -q tests/hil/`
  succeeds with 0 tests collected); `python -m tools.pull_replay_traces
  --help` succeeds.

This plan does NOT depend on any other Plan 04 plan — `tests/hil/` is a
sibling tier; CI workflow is independent infrastructure.
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
@CLAUDE.md

<interfaces>
<!-- Verbatim from PATTERNS.md / source — executor uses these directly. -->

From .github/workflows/ci.yml:1-49 (the analog — self-hosted aarch64 + uv venv setup):
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint-and-types:
    name: Lint + type-check (aarch64 self-hosted)
    runs-on: [self-hosted, linux, ARM64]
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        run: |
          curl -LsSf https://astral.sh/uv/install.sh | sh
          echo "$HOME/.local/bin" >> "$GITHUB_PATH"

      - name: Set up Python 3.12
        run: uv python install 3.12

      - name: Create venv and install dev deps
        run: |
          uv venv --python 3.12 .venv
          uv pip install --python .venv/bin/python -e ".[dev]"
          uv pip install --python .venv/bin/python --no-deps -r packaging/requirements.lock
```

From tests/integration/test_logrotate_create.py:25-46 (the test-tier real-subprocess analog — tests/ is SP-04-exempt):
```python
import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="logrotate is a POSIX binary; production target is Linux/aarch64",
    ),
    pytest.mark.asyncio,
]

_LOGROTATE_BIN = "/usr/sbin/logrotate"
```

From tools/gen_replay_fixtures.py:201-216 (argparse + main() pattern):
```python
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
    ...
```

From PATTERNS.md § "tests/hil/fault_inject.py":
- Module-level helpers (NOT a class), one per fault.
- Imports: subprocess, asyncio, pathlib.Path. NOT spark_modem.subproc.runner.
- tests/ tier is SP-04-exempt (verified in lint_no_subprocess.sh:11).

PATTERNS.md correction #3:
> The `hil` marker is already registered at `pyproject.toml:78`. Phase 4 does
> NOT need a `pyproject.toml` edit for the marker — only the workflow file
> (`hil.yml`) needs to invoke `pytest -m hil`.

CONTEXT D-01 budget: 90 min wall budget; full scenario suite ~45 min, plus replay-harness 30-day gate.

CONTEXT D-03 redaction shape: ICCID/IMSI/IP via `sha256[:8]` hash — same shape Plan 02-09's `ctl support-bundle` already uses.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create HIL workflow + tests/hil/ scaffold (init, README, conftest, fault_inject)</name>
  <files>
    .github/workflows/hil.yml,
    tests/hil/__init__.py,
    tests/hil/README.md,
    tests/hil/conftest.py,
    tests/hil/fault_inject.py
  </files>
  <read_first>
    - .github/workflows/ci.yml (the analog — copy the venv-bootstrap structure verbatim, change triggers + runner labels + concurrency)
    - tests/integration/test_logrotate_create.py:25-46 (real-subprocess pattern; pytestmark with linux_only + skipif win32)
    - .planning/phases/04-destructive-actions-hil/04-PATTERNS.md § ".github/workflows/hil.yml" + § "tests/hil/fault_inject.py"
    - .planning/phases/04-destructive-actions-hil/04-CONTEXT.md § D-01 (HIL execution model) + § D-02 (fault-injection toolkit)
    - pyproject.toml lines 70-80 (markers — confirm `hil` is already registered; do NOT edit)
    - .planning/research/PITFALLS.md §1.1 (qmi-proxy kill recovery is exercised by inject_qmi_proxy_kill)
  </read_first>
  <action>
**Step A — Create `.github/workflows/hil.yml`:**

```yaml
name: HIL

# Hardware-in-the-loop: nightly run on the bench Jetson tethered runner.
# Per CONTEXT D-01: self-hosted aarch64 + 4 EM7421s on USB hub 2-3.1.{1..4}.
# Serial concurrency (single bench Jetson; never parallel). 90 min budget.

on:
  schedule:
    - cron: "0 4 * * *"   # 04:00 UTC nightly
  workflow_dispatch:

concurrency:
  group: hil-bench
  cancel-in-progress: false   # serial; current run completes before next

jobs:
  hil:
    name: HIL scenario suite (bench Jetson)
    runs-on: [self-hosted, linux, ARM64, hil-bench]
    timeout-minutes: 90
    steps:
      - uses: actions/checkout@v4
        with:
          lfs: false   # explicit pull via tools/pull_replay_traces below

      - name: Install uv
        run: |
          curl -LsSf https://astral.sh/uv/install.sh | sh
          echo "$HOME/.local/bin" >> "$GITHUB_PATH"

      - name: Set up Python 3.12 + venv
        run: |
          uv python install 3.12
          uv venv --python 3.12 .venv
          uv pip install --python .venv/bin/python -e ".[dev]"
          uv pip install --python .venv/bin/python --no-deps -r packaging/requirements.lock

      - name: Pull v1-30d replay traces (Git LFS)
        run: .venv/bin/python -m tools.pull_replay_traces

      - name: Run HIL scenario suite
        run: .venv/bin/pytest -m hil tests/hil/ -ra --tb=short

      - name: Collect support bundle on failure
        if: failure()
        run: |
          sudo /opt/spark-modem-watchdog/python/bin/spark-modem ctl support-bundle \
            --output /tmp/spark-modem-support-bundle.tar.gz || true

      - name: Upload support bundle artefact
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: hil-support-bundle-${{ github.run_id }}
          path: /tmp/spark-modem-support-bundle.tar.gz
          if-no-files-found: warn
          retention-days: 14
```

**Step B — Create `tests/hil/__init__.py`** (empty file — package marker; if the file already exists per PATTERNS Wave-0 stub list at line 1205, leave it alone).

**Step C — Create `tests/hil/README.md`** documenting the HIL tier:

```markdown
# HIL — Hardware-In-the-Loop Test Suite

This tier runs ONLY on the bench Jetson tethered to the `[self-hosted, linux,
ARM64, hil-bench]` runner. Per Phase 4 CONTEXT D-01 / D-02:

- 4× Sierra EM7421 modems on USB hub 2-3.1.{1..4}
- Real qmi-proxy + Zao stack (no fakes)
- Software-only fault injection (NO real RF detuning hardware)
- Serial concurrency (single bench Jetson; never parallel)
- 90 min wall budget per nightly run

## Test markers

Every HIL test file MUST set:

```python
pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.hil,
    pytest.mark.skipif(sys.platform == "win32", reason="..."),
    pytest.mark.asyncio,
]
```

## Running locally (developer dry-run on bench Jetson)

```bash
.venv/bin/pytest -m hil tests/hil/ -ra --tb=short
```

NOTE: This will physically de-enumerate the modems, kill qmi-proxy, etc.
Do NOT run on a production Jetson.

## Scenario index (Plan 04-07 lands these)

- `test_boot_to_healthy.py` — SC#1 piggyback; 4 modems → Healthy in ≤60 s
- `test_sim_swap.py` — Phase 3 SC#2 piggyback
- `test_soft_reset_sim_app_detected.py` — FR-23 SC#4
- `test_modem_reset_after_soft.py` — FR-22 ladder progression
- `test_three_modem_hang.py` — FR-24 driver_reset 75% gate
- `test_rf_event_no_destructive.py` — FR-23 signal gate
- `test_proxy_died_recovery.py` — FR-24 pkill -9 qmi-proxy
- `test_qmi_wwan_reload_clean_transition.py` — Phase 3 piggyback
- `test_sigterm_within_5s.py` — FR-53 piggyback
- `test_ctl_reset_state_serialisation.py` — FR-61.1 piggyback
- `test_watchdog_90s_actual_fire.py` — FR-75 / NFR-13 piggyback
- `test_destructive_actions.py` — FR-27 idempotency end-to-end

## Replay-harness 30-day gate

`tools/replay_harness.py` is invoked AFTER the scenario suite. Pulls v1-30d
traces from LFS via `tools/pull_replay_traces.py`. Pass criterion:
fault-cycle agreement ≥95% (CONTEXT D-03; FR-24 SC#4 last paragraph).
```

**Step D — Create `tests/hil/conftest.py`:**

```python
"""HIL pytest fixtures + marker enforcement."""

from __future__ import annotations

import sys

import pytest


# All tests under tests/hil/ are LINUX-ONLY and HIL-marked. Individual
# scenario files MAY add additional markers but inherit these via collection.
collect_ignore_glob = []

if sys.platform == "win32":
    # Belt-and-suspenders: the workflow runs on linux/ARM64 only, but a
    # developer running pytest on Windows should not collect HIL tests.
    collect_ignore_glob = ["**/*.py"]


@pytest.fixture(scope="session")
def bench_jetson_topology() -> dict[str, list[str]]:
    """Bench Jetson topology assumption (per CONTEXT D-01).

    4 modems on USB hub 2-3.1.{1..4}. usb_path values are the modem leaf
    bus-port strings; cdc_wdm_paths are the corresponding /dev/cdc-wdmN
    devices (subject to renumbering — usb_path is the stable key per
    ADR-0009).
    """
    return {
        "usb_paths": ["2-3.1.1", "2-3.1.2", "2-3.1.3", "2-3.1.4"],
        "cdc_wdm_paths": [
            "/dev/cdc-wdm0",
            "/dev/cdc-wdm1",
            "/dev/cdc-wdm2",
            "/dev/cdc-wdm3",
        ],
    }
```

**Step E — Create `tests/hil/fault_inject.py`:**

```python
"""Software-only fault-injection helpers for HIL scenarios (Plan 04-07).

Per CONTEXT D-02:
  - SIM-app issues: qmicli --uim-sim-power-off / --uim-sim-power-on
  - QMI-hung: pkill -9 qmi-proxy
  - Registration loss: qmicli --dms-set-operating-mode=offline / =online
  - Thermal / usb_overcurrent: synthetic /dev/kmsg writes (5 patterns from Plan 03-05)

Module-level helpers (NOT a class). tests/ tier is SP-04-exempt by design
(verified in scripts/lint_no_subprocess.sh:11).

Each helper raises on subprocess failure -- scenario tests MUST handle the
exception explicitly (no silent swallow). The bench Jetson is the production
target; failures in fault injection ARE test failures.
"""

from __future__ import annotations

import asyncio
import subprocess  # noqa: S404 -- tests/ is SP-04-exempt; this is fault injection

from pathlib import Path


_KMSG = Path("/dev/kmsg")


async def inject_sim_power_off(cdc_wdm: str) -> None:
    """qmicli --uim-sim-power-off against the modem.

    Causes IssueDetail.SIM_POWER_DOWN on next observation. Recovery via cheap
    sim_power_on action.
    """
    await asyncio.to_thread(
        subprocess.run,
        ["qmicli", "--device-open-proxy", f"--device={cdc_wdm}", "--uim-sim-power-off=1"],
        check=True,
        capture_output=True,
    )


async def inject_sim_power_on(cdc_wdm: str) -> None:
    """qmicli --uim-sim-power-on -- recovers from inject_sim_power_off."""
    await asyncio.to_thread(
        subprocess.run,
        ["qmicli", "--device-open-proxy", f"--device={cdc_wdm}", "--uim-sim-power-on=1"],
        check=True,
        capture_output=True,
    )


async def inject_qmi_proxy_kill() -> None:
    """pkill -9 qmi-proxy -- triggers SC#4 PROXY_DIED recovery via driver_reset.

    Per PITFALLS §1.1: leaves qmicli clients with stale CIDs; only driver_reset
    restores the channel. Zao restarts qmi-proxy on its next QMI call.
    """
    await asyncio.to_thread(
        subprocess.run,
        ["pkill", "-9", "qmi-proxy"],
        check=False,   # exit 1 if no process matched -- still acceptable
        capture_output=True,
    )


async def inject_kmsg(text: str) -> None:
    """Write a synthetic line to /dev/kmsg.

    Per CONTEXT D-02 / Plan 03-05 closed-enum patterns:
      - "<3>usb 1-3.1: device not accepting address"      -> USB_ENUM_FAILURE
      - "<3>tegra-xusb: PSU droop"                         -> TEGRA_HUB_PSU_DROOP
      - "<3>thermal_throttle: trip point exceeded"         -> THERMAL_THROTTLE
      - "<3>qmi_wwan: probe failed"                        -> QMI_WWAN_PROBE_FAIL
      - "<3>usb 1-3.1: over-current condition"             -> USB_OVERCURRENT
    """
    if not _KMSG.exists():
        raise RuntimeError("/dev/kmsg not available (HIL tier requires Linux)")
    _KMSG.write_text(text, encoding="utf-8")


async def inject_offline(cdc_wdm: str) -> None:
    """qmicli --dms-set-operating-mode=offline -- forces NOT_REGISTERED state."""
    await asyncio.to_thread(
        subprocess.run,
        ["qmicli", "--device-open-proxy", f"--device={cdc_wdm}", "--dms-set-operating-mode=offline"],
        check=True,
        capture_output=True,
    )


async def inject_online(cdc_wdm: str) -> None:
    """qmicli --dms-set-operating-mode=online -- recovers from inject_offline."""
    await asyncio.to_thread(
        subprocess.run,
        ["qmicli", "--device-open-proxy", f"--device={cdc_wdm}", "--dms-set-operating-mode=online"],
        check=True,
        capture_output=True,
    )


async def inject_thermal_critical() -> None:
    """Synthetic thermal_critical kmsg write (no real thermal stress on bench)."""
    await inject_kmsg("<2>thermal_throttle: trip point exceeded - CRITICAL\n")
```

Per CLAUDE.md: HIL tests are SP-04-exempt (lint scope is `src/`). The
`subprocess.run` calls here are intentional — they exercise the REAL bench
Jetson syscalls. Production code under `src/spark_modem/` continues to use
the `subproc/runner` wrapper exclusively.
  </action>
  <verify>
    <automated>cd /s/spark/modem-watchdog &amp;&amp; .venv/bin/pytest --collect-only -q tests/hil/ &amp;&amp; .venv/bin/python -c "import tests.hil.fault_inject; print(dir(tests.hil.fault_inject))" &amp;&amp; .venv/bin/ruff check tests/hil/ &amp;&amp; .venv/bin/ruff format --check tests/hil/ &amp;&amp; bash scripts/lint_no_subprocess.sh &amp;&amp; .venv/bin/python -c "import yaml; yaml.safe_load(open('.github/workflows/hil.yml'))"</automated>
  </verify>
  <acceptance_criteria>
    - File exists: `.github/workflows/hil.yml`
    - `grep -F 'cron: "0 4 * * *"' .github/workflows/hil.yml` returns ≥1 match
    - `grep -F 'workflow_dispatch:' .github/workflows/hil.yml` returns ≥1 match
    - `grep -F 'runs-on: [self-hosted, linux, ARM64, hil-bench]' .github/workflows/hil.yml` returns ≥1 match
    - `grep -F 'group: hil-bench' .github/workflows/hil.yml` returns ≥1 match
    - `grep -F 'cancel-in-progress: false' .github/workflows/hil.yml` returns ≥1 match
    - `grep -F 'timeout-minutes: 90' .github/workflows/hil.yml` returns ≥1 match
    - `grep -F 'pytest -m hil tests/hil/' .github/workflows/hil.yml` returns ≥1 match
    - `grep -F 'tools.pull_replay_traces' .github/workflows/hil.yml` returns ≥1 match
    - `grep -F 'support-bundle' .github/workflows/hil.yml` returns ≥1 match
    - `grep -F 'upload-artifact' .github/workflows/hil.yml` returns ≥1 match
    - `python -c "import yaml; yaml.safe_load(open('.github/workflows/hil.yml'))"` exits 0 (workflow YAML is parseable)
    - File exists: `tests/hil/__init__.py`
    - File exists: `tests/hil/README.md` (≥40 lines)
    - File exists: `tests/hil/conftest.py`
    - File exists: `tests/hil/fault_inject.py`
    - `grep -F 'async def inject_sim_power_off' tests/hil/fault_inject.py` returns ≥1 match
    - `grep -F 'async def inject_sim_power_on' tests/hil/fault_inject.py` returns ≥1 match
    - `grep -F 'async def inject_qmi_proxy_kill' tests/hil/fault_inject.py` returns ≥1 match
    - `grep -F 'async def inject_kmsg' tests/hil/fault_inject.py` returns ≥1 match
    - `grep -F 'async def inject_offline' tests/hil/fault_inject.py` returns ≥1 match
    - `grep -F 'async def inject_online' tests/hil/fault_inject.py` returns ≥1 match
    - `grep -F 'async def inject_thermal_critical' tests/hil/fault_inject.py` returns ≥1 match
    - `grep -F '"--device-open-proxy"' tests/hil/fault_inject.py` returns ≥1 match (FR-74)
    - `pytest --collect-only -q tests/hil/` exits 0 (Linux dev host) or 5 (Windows — collect_ignore_glob skips); no errors
    - `python -c "import tests.hil.fault_inject"` exits 0 (module imports cleanly on dev host)
    - `ruff check tests/hil/` exits 0
    - `ruff format --check tests/hil/` exits 0
    - `bash scripts/lint_no_subprocess.sh` exits 0 (tests/ tier is SP-04-exempt)
  </acceptance_criteria>
  <done>
    HIL workflow YAML parses; tests/hil/ scaffolding imports cleanly; 7 fault-injection helpers ready for Plan 04-07 scenarios; ruff + SP-04 green.
  </done>
</task>

<task type="auto">
  <name>Task 2: Create tools/pull_replay_traces.py + tests/fixtures/replay/v1-30d/ scaffold (.gitkeep, .gitattributes, README)</name>
  <files>
    tools/pull_replay_traces.py,
    tests/fixtures/replay/v1-30d/.gitkeep,
    tests/fixtures/replay/v1-30d/.gitattributes,
    tests/fixtures/replay/v1-30d/README.md
  </files>
  <read_first>
    - tools/gen_replay_fixtures.py:1-50 + :201-216 (the analog — argparse + main() + Path/seed pattern)
    - .planning/phases/04-destructive-actions-hil/04-PATTERNS.md § "tools/pull_replay_traces.py"
    - .planning/phases/04-destructive-actions-hil/04-CONTEXT.md § D-03 (LFS pull cadence + redaction shape)
    - scripts/lint_no_subprocess.sh:11 (verify lint scope is `src/` — `tools/` is exempt)
    - tests/fixtures/replay/.gitkeep (verify the parent fixture directory pattern)
  </read_first>
  <action>
**Step A — Create `tools/pull_replay_traces.py`:**

```python
"""Resolve the Git LFS pointer at tests/fixtures/replay/v1-30d/ to a privacy-
redacted snapshot of >=30 days of v1 historical traces.

Per CONTEXT D-03:
- Sha256[:8]-redacted ICCID/IMSI/IP (same shape as Plan 02-09's ctl support-
  bundle).
- HIL job invokes this in the setup phase; replay-harness from Plan 02-10
  consumes the pulled directory.
- FAILS CLEARLY on missing LFS auth (no silent skip).
- Quarterly refresh cadence documented in tests/fixtures/replay/v1-30d/README.md.

Subprocess discipline: this is a tools/ script (NOT under src/spark_modem/);
SP-04 lint scope excludes both src/spark_modem/subproc/ and anything outside
src/. So this script may use subprocess.run directly.

Exit codes:
  0 -- LFS pull succeeded (or already-up-to-date).
  1 -- LFS not installed, auth failure, or other operational error.
"""

from __future__ import annotations

import argparse
import subprocess  # noqa: S404 -- tools/ is SP-04-exempt
import sys
from pathlib import Path


_LFS_DIR = Path("tests/fixtures/replay/v1-30d")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pull v1-30d replay traces from Git LFS for the HIL replay-harness gate.",
    )
    parser.add_argument(
        "--include",
        type=str,
        default=str(_LFS_DIR),
        help="LFS path to pull (default: tests/fixtures/replay/v1-30d/).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: cwd).",
    )
    args = parser.parse_args(argv)

    # Verify git-lfs is installed.
    try:
        cp_lfs_check = subprocess.run(
            ["git", "lfs", "version"],
            capture_output=True,
            text=True,
            cwd=args.repo_root,
        )
    except FileNotFoundError:
        print(
            "pull_replay_traces: git-lfs not installed. "
            "Install on the HIL runner via `apt install git-lfs && git lfs install`.",
            file=sys.stderr,
        )
        return 1
    if cp_lfs_check.returncode != 0:
        print(
            f"pull_replay_traces: git-lfs check failed:\n{cp_lfs_check.stderr}",
            file=sys.stderr,
        )
        return 1

    # Pull the LFS-tracked files under the include path.
    cp_pull = subprocess.run(
        ["git", "lfs", "pull", "--include", args.include],
        capture_output=True,
        text=True,
        cwd=args.repo_root,
    )
    if cp_pull.returncode != 0:
        print(
            f"pull_replay_traces: git lfs pull failed:\n"
            f"  stderr: {cp_pull.stderr}\n"
            f"  stdout: {cp_pull.stdout}",
            file=sys.stderr,
        )
        return 1

    print(f"pull_replay_traces: pulled LFS objects under {args.include}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step B — Create `tests/fixtures/replay/v1-30d/.gitkeep`** (empty file — directory marker; ensures the directory is committed even if no traces are checked in initially).

**Step C — Create `tests/fixtures/replay/v1-30d/.gitattributes`:**

```
# Git LFS pointer registration scoped to tests/fixtures/replay/v1-30d/
# Quarterly refresh process documented in README.md.
# Per CONTEXT D-03 (Phase 4).

*.json filter=lfs diff=lfs merge=lfs -text
*.jsonl filter=lfs diff=lfs merge=lfs -text
```

**Step D — Create `tests/fixtures/replay/v1-30d/README.md`:**

```markdown
# v1-30d Replay Traces

This directory contains >=30 days of v1 historical traces, used by the
HIL replay-harness 30-day agreement gate (Phase 4 SC#4 / CONTEXT D-03).

## Status

Initially empty. JSON shards are checked in via Git LFS (see
`.gitattributes`). The `.gitkeep` ensures the directory exists even
when no traces are present.

## Refresh cadence

Quarterly OR on parser changes that invalidate prior fixtures.

## How to refresh

1. SSH into a representative production Jetson with v1 deployed.
2. Run the v1 trace exporter (see docs/MIGRATION.md §0 / Phase 0 trace
   capture procedure):

   ```bash
   sudo /usr/local/bin/diag.sh --capture-trace --since=30d \
     --output=/tmp/v1-30d-traces.tgz
   ```

3. On the dev laptop, extract and redact:

   ```bash
   tar xzf v1-30d-traces.tgz
   python tools/redact_traces.py \
     --input ./v1-30d-traces/ \
     --output tests/fixtures/replay/v1-30d/
   ```

   (`tools/redact_traces.py` is a future helper; until it's written, redact
   manually per the contract below.)

4. Commit the redacted shards via Git LFS:

   ```bash
   git lfs track "tests/fixtures/replay/v1-30d/*.json"
   git add tests/fixtures/replay/v1-30d/
   git commit -m "fixtures(v1-30d): refresh quarterly snapshot"
   git push
   ```

## Redaction contract (per CONTEXT D-03)

ALL of the following fields MUST be replaced with `<redacted:<8-hex-chars>>`
where the 8 hex chars are the first 8 of `sha256(value)`:

- `iccid` (any value matching `^[0-9]{18,22}$`)
- `imsi` (any value matching `^[0-9]{14,15}$`)
- IPv4 addresses (any value matching the standard dotted-quad regex)
- IPv6 addresses (any colon-separated hex value of the right shape)

Same redaction shape as Plan 02-09's `ctl support-bundle` (sha256[:8] hash).
Same identity → same redacted value (deterministic — enables identity
correlation in the redacted output without exposing PII).

The HMAC secret is NEVER copied. The webhook URL hostname is preserved (for
DNS pre-resolve correctness) but the path/query is stripped.

## Fixture-directory shape

Matches `tests/fixtures/replay/<scenario>/<NNN>.json` per Phase 2's
`gen_replay_fixtures.py` shape (each JSON file is one cycle's Diag input +
v1's planned action output). Plan 02-10 replay harness already understands
this shape — point it at this directory.

## How the HIL workflow consumes this directory

1. `.github/workflows/hil.yml` setup step runs `python -m
   tools.pull_replay_traces` (Plan 04-06).
2. `tools/pull_replay_traces.py` invokes `git lfs pull --include
   tests/fixtures/replay/v1-30d/`.
3. The HIL scenario suite (Plan 04-07) invokes the replay harness against
   this directory after the bench-Jetson scenarios complete.
4. Pass criterion: fault-cycle agreement >=95% (per FR-24 SC#4 last
   paragraph + CONTEXT D-03).
```

Per CLAUDE.md: tools/ is SP-04-exempt (lint scope is src/). The script's
direct `subprocess.run` is intentional and audited.
  </action>
  <verify>
    <automated>cd /s/spark/modem-watchdog &amp;&amp; .venv/bin/python -m tools.pull_replay_traces --help &amp;&amp; .venv/bin/ruff check tools/pull_replay_traces.py &amp;&amp; .venv/bin/ruff format --check tools/pull_replay_traces.py &amp;&amp; .venv/bin/mypy --strict tools/pull_replay_traces.py &amp;&amp; bash scripts/lint_no_subprocess.sh &amp;&amp; test -f tests/fixtures/replay/v1-30d/.gitkeep &amp;&amp; test -f tests/fixtures/replay/v1-30d/.gitattributes &amp;&amp; test -f tests/fixtures/replay/v1-30d/README.md</automated>
  </verify>
  <acceptance_criteria>
    - File exists: `tools/pull_replay_traces.py`
    - `grep -F 'def main' tools/pull_replay_traces.py` returns ≥1 match
    - `grep -F 'git lfs pull' tools/pull_replay_traces.py` returns ≥1 match
    - `grep -F 'argparse' tools/pull_replay_traces.py` returns ≥1 match
    - `grep -F 'tests/fixtures/replay/v1-30d' tools/pull_replay_traces.py` returns ≥1 match
    - `python -m tools.pull_replay_traces --help` exits 0 and prints argparse help
    - File exists: `tests/fixtures/replay/v1-30d/.gitkeep`
    - File exists: `tests/fixtures/replay/v1-30d/.gitattributes`
    - File exists: `tests/fixtures/replay/v1-30d/README.md` (≥40 lines)
    - `grep -F 'filter=lfs diff=lfs merge=lfs -text' tests/fixtures/replay/v1-30d/.gitattributes` returns ≥1 match
    - `grep -F 'sha256' tests/fixtures/replay/v1-30d/README.md` returns ≥1 match (redaction shape documented)
    - `grep -F 'Quarterly' tests/fixtures/replay/v1-30d/README.md` returns ≥1 match (refresh cadence)
    - `ruff check tools/pull_replay_traces.py` exits 0
    - `ruff format --check tools/pull_replay_traces.py` exits 0
    - `mypy --strict tools/pull_replay_traces.py` exits 0
    - `bash scripts/lint_no_subprocess.sh` exits 0 (tools/ is SP-04-exempt)
    - `grep -E 'subprocess|create_subprocess_exec' src/spark_modem/` returns 0 matches outside `src/spark_modem/subproc/` (no regression in src/ tree)
  </acceptance_criteria>
  <done>
    pull_replay_traces.py CLI is functional (--help works); LFS pointer directory exists with .gitattributes + README + .gitkeep; mypy + ruff green on the new tool.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| GitHub Actions runner ↔ self-hosted bench Jetson | Workflow runs on a self-hosted runner with physical hardware access (USB hub, qmicli, modprobe). Restricted to repo collaborators only via standard GitHub Actions permissions. NEVER use `pull_request_target` (would expose CAP_SYS_MODULE to fork PR authors) |
| LFS pull authenticates with GitHub credentials | `git lfs pull` uses the actions/checkout token (default GITHUB_TOKEN). Never echo the token; the workflow log redacts it automatically |
| /dev/kmsg writes from fault_inject.inject_kmsg | Real bench Jetson kernel sees synthetic events as if from real drivers; classifier (Plan 03-05) cannot distinguish synthetic from real — that's the point. CAP_SYS_ADMIN is required to write /dev/kmsg, which the workflow runner has (sudo for support-bundle) |
| pkill -9 qmi-proxy from fault_inject.inject_qmi_proxy_kill | Bench Jetson process; qmi-proxy is owned by Zao; killing it triggers Zao's own restart logic |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-06-01 | E (Elevation) | HIL workflow exposed via pull_request_target | mitigate | Workflow uses ONLY `schedule:` and `workflow_dispatch:` triggers — explicitly NOT `pull_request_target` (which would let fork PRs get CAP_SYS_MODULE on the bench Jetson). Acceptance criterion grep checks the trigger list literally |
| T-04-06-02 | T (Tampering) | LFS credential exposure in workflow logs | mitigate | `actions/checkout@v4` with default GITHUB_TOKEN auto-redacts; the workflow never echoes the token; `tools/pull_replay_traces.py` does not print env vars |
| T-04-06-03 | E (Elevation) | path-traversal injection via --include arg to pull_replay_traces.py | mitigate | argparse default value is `tests/fixtures/replay/v1-30d`; the script passes `--include` verbatim to `git lfs pull` which itself validates path-traversal (refuses paths outside the repo). Operator override via `--include` is a deliberate trust grant — the workflow only ever uses the default |
| T-04-06-04 | D (Denial of service) | concurrent HIL runs thrash the bench Jetson | mitigate | `concurrency: group: hil-bench / cancel-in-progress: false` — current run completes before next; queueing is GitHub-managed |
| T-04-06-05 | R (Repudiation) | scenario failures without artefact | mitigate | `actions/upload-artifact@v4` on failure uploads the support bundle (`spark-modem ctl support-bundle`); 14-day retention. PII redaction in support-bundle (Plan 02-09) means sha256[:8]-hashed identities only |
| T-04-06-06 | I (Information disclosure) | v1 trace fixtures contain PII before redaction | mitigate | README documents the redaction contract verbatim; `tools/redact_traces.py` is a future helper but the manual procedure is documented; CI cannot push v1 traces without going through the documented redaction step |
| T-04-06-07 | T (Tampering) | fault_inject helpers issue real subprocess on dev laptops if accidentally invoked | mitigate | Module-level pytestmark with `linux_only` + `hil` markers means scenarios collect ONLY when both markers are explicitly enabled; HIL scenario tests in Plan 04-07 set both. Local `pytest -m "unit or integration"` does NOT collect HIL tests |
</threat_model>

<verification>
- All Plan 04-06 task `<verify>` commands pass.
- `pytest --collect-only -q tests/hil/` exits 0 with 0 tests collected (this plan ships the SCAFFOLD only — Plan 04-07 lands the actual scenarios).
- `python -m tools.pull_replay_traces --help` prints argparse help; exit 0.
- `python -c "import yaml; yaml.safe_load(open('.github/workflows/hil.yml'))"` exits 0 (YAML is parseable).
- `mypy --strict tools/pull_replay_traces.py` exits 0.
- `ruff check tools/pull_replay_traces.py tests/hil/` exits 0.
- `bash scripts/lint_no_subprocess.sh` exits 0 (tools/ + tests/ are SP-04-exempt; src/ tree untouched).
- Manual sanity: workflow file passes `actionlint` if available (`actionlint .github/workflows/hil.yml` — optional check; do not block on actionlint absence).
</verification>

<success_criteria>
- `.github/workflows/hil.yml` exists with the correct triggers (`schedule: cron 0 4 * * *` + `workflow_dispatch`), runner labels (`[self-hosted, linux, ARM64, hil-bench]`), concurrency (`hil-bench` group / cancel-in-progress: false), 90 min timeout, support-bundle artefact upload on failure.
- `tests/hil/__init__.py`, `tests/hil/README.md`, `tests/hil/conftest.py`, `tests/hil/fault_inject.py` exist; `tests/hil/` is import-clean.
- `tests/hil/fault_inject.py` provides 7 module-level async helpers (sim_power_off/on, qmi_proxy_kill, kmsg, offline/online, thermal_critical) — software-only, real subprocess, SP-04-exempt.
- `tools/pull_replay_traces.py` exists; functional via `--help`; uses `git lfs pull --include`; fails clearly on missing LFS auth.
- `tests/fixtures/replay/v1-30d/.gitkeep`, `.gitattributes`, `README.md` exist.
- `.gitattributes` registers `*.json` and `*.jsonl` as LFS-tracked.
- README documents quarterly refresh cadence + sha256[:8] redaction contract + how the HIL workflow consumes the directory.
- PATTERNS correction #3 honored: `pyproject.toml` is NOT modified (`hil` marker already registered).
- CLAUDE.md invariants honored: SP-04 lint scope unchanged (tools/ + tests/ remain exempt; src/ tree untouched); no new subprocess calls in src/spark_modem/.
- Full Phase 1+2+3+04-{01..05} regression suite stays green.
</success_criteria>

<output>
After completion, create `.planning/phases/04-destructive-actions-hil/04-06-SUMMARY.md`
documenting: files created (hil.yml workflow, 4 test/hil/ files, 1 tool, 3
fixture-directory files), the workflow trigger rationale (nightly + dispatch
because per-PR is too slow at 45+ min), the 7 fault-injection helpers, the
LFS pointer setup, the README's quarterly refresh cadence + redaction
contract, the PATTERNS correction #3 (no pyproject edit), and the deferred
items (`tools/redact_traces.py` is a future helper; manual redaction is
documented for now).
</output>
