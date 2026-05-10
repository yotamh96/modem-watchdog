# Phase 4: Destructive Actions & HIL — Pattern Map

**Mapped:** 2026-05-10
**Source:** Verified against codebase HEAD; corrects RESEARCH.md where the cited file:line was inaccurate.
**Files analyzed:** 11 new + 11 extended
**Analogs found:** 11/11 (every new file has a verified, real-source analog)

This pattern map is the planner's source of truth for `<read_first>` blocks. Every excerpt below was loaded with `Read` against the cited line range and copied verbatim. Any deviation from RESEARCH.md's prior claim is flagged inline as **(corrected)**.

---

## File Classification

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `src/spark_modem/actions/modem_reset.py` | action | request-response (qmicli) | `actions/soft_reset.py` | exact (same QMI verb) |
| `src/spark_modem/actions/usb_reset.py` | action | file-I/O (sysfs writes) | `actions/fix_autosuspend.py` (sysfs write shape) + `actions/soft_reset.py` (deferred verify) | role+flow exact |
| `src/spark_modem/actions/driver_reset.py` | action (global) | subprocess (modprobe ×2) | `actions/soft_reset.py` (deferred verify) + `subproc/runner.py` (call shape) | role-match (no existing global action) |
| `src/spark_modem/sysfs/__init__.py` + `sysfs/usb_unbind_rebind.py` | utility/IO helper | file-I/O | `inventory/sysfs.py` (Path discipline + `sysfs_root_override`) | role+flow exact |
| `src/spark_modem/policy/ladder.py` | pure-function policy module | transform (lookup) | `policy/decision_table.py` (lookup_action shape) + `policy/transitions.py` (pure module shape) | exact |
| `tools/pull_replay_traces.py` | tool/CLI script | file-I/O + network (LFS) | `tools/gen_replay_fixtures.py` (argparse + Path/seed) | role-match |
| `tests/hil/fault_inject.py` | test helper | subprocess (real) | `tests/fakes/runner.py` (callable surface) — but real-runner; tests/ is SP-04-exempt | role-match |
| `tests/hil/scenarios/test_*.py` | integration test | event-driven | `tests/integration/test_lifecycle.py` (pytestmark + Fake* injection) | exact |
| `.github/workflows/hil.yml` | CI workflow | event-driven (cron) | `.github/workflows/ci.yml` (self-hosted aarch64 + uv bootstrap) | exact |
| `tests/fixtures/replay/v1-30d/README.md` + `.gitattributes` | fixture documentation | static | (no existing README; new pattern; cite `tests/fixtures/replay/.gitkeep` parent shape) | none — net-new |
| Wave-0 stubs (`tests/unit/policy/test_ladder.py`, `tests/unit/actions/test_modem_reset.py`, etc.) | unit test | request-response | `tests/unit/policy/test_engine.py`, `tests/unit/actions/test_soft_reset.py`, `tests/unit/actions/_helpers.py` | exact |

---

## New Files → Closest Analogs

### `src/spark_modem/actions/modem_reset.py`

**Role:** MODEM_RESET execute/verify; reuses `dms_set_operating_mode("reset")`.
**Closest analog:** `src/spark_modem/actions/soft_reset.py:1-50` (entire file)

**Pattern excerpt** (verified `actions/soft_reset.py:14-49`):
```python
from __future__ import annotations

from spark_modem.actions.context import ActionContext
from spark_modem.actions.result import ActionResult, VerifyResult
from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind


async def execute(who: WhoModem, ctx: ActionContext) -> ActionResult:
    start = ctx.clock.monotonic()
    cp = await ctx.qmi.dms_set_operating_mode("reset")
    err = QmiWrapper.classify(cp)
    if err is not None:
        return ActionResult(
            kind=ActionKind.SOFT_RESET,
            who=who,
            succeeded=False,
            duration_seconds=ctx.clock.monotonic() - start,
            failure_reason=f"soft_reset:{err.reason.value}",
            dry_run=False,
        )
    return ActionResult(
        kind=ActionKind.SOFT_RESET,
        who=who,
        succeeded=True,
        duration_seconds=ctx.clock.monotonic() - start,
        failure_reason=None,
        dry_run=False,
    )


async def verify(who: WhoModem, ctx: ActionContext) -> VerifyResult:
    """Deferred -- next-cycle observation surfaces the actual outcome."""
    del who, ctx
    return VerifyResult.deferred(detail="next_cycle_observation")
```

**How Phase 4 deviates:**
- `kind=ActionKind.MODEM_RESET` (not `SOFT_RESET`).
- `failure_reason=f"modem_reset:{err.reason.value}"` (not `soft_reset:`).
- Same QMI verb `dms_set_operating_mode("reset")` per CONTEXT A-01: "modem_reset is a policy distinction, not a protocol distinction." The signal-gating + ladder-rung-2 + 30-60 s outage envelope are **engine-side** (gates.py + ladder.py), not action-side.
- Module docstring should reference RECOVERY_SPEC §4.1 ladder rung 2 + signal gate.

---

### `src/spark_modem/actions/usb_reset.py`

**Role:** USB_RESET execute/verify (child-port + parent-hub variants); writes sysfs only — NO subprocess.
**Closest analogs:**
- `src/spark_modem/actions/fix_autosuspend.py:25-46` (sysfs `Path.write_text` pattern)
- `src/spark_modem/actions/soft_reset.py:46-49` (deferred verify shape)
- `src/spark_modem/inventory/sysfs.py:24-30` (`sysfs_root_override`/`Path("/sys")` discipline)

**Pattern excerpt** (verified `actions/fix_autosuspend.py:25-46`):
```python
async def execute(who: WhoModem, ctx: ActionContext) -> ActionResult:
    start = ctx.clock.monotonic()
    target = _power_control_path(ctx.sysfs_root, who.usb_path)
    try:
        target.write_text("on", encoding="ascii")
    except OSError as exc:
        return ActionResult(
            kind=ActionKind.FIX_AUTOSUSPEND,
            who=who,
            succeeded=False,
            duration_seconds=ctx.clock.monotonic() - start,
            failure_reason=f"sysfs_write_error:{exc.errno}",
            dry_run=False,
        )
    return ActionResult(
        kind=ActionKind.FIX_AUTOSUSPEND,
        who=who,
        succeeded=True,
        duration_seconds=ctx.clock.monotonic() - start,
        failure_reason=None,
        dry_run=False,
    )
```

**Pattern excerpt 2** — sysfs root path computation (verified `actions/fix_autosuspend.py:60-61`):
```python
def _power_control_path(sysfs_root: Path, usb_path: str) -> Path:
    return sysfs_root / "bus" / "usb" / "devices" / usb_path / "power" / "control"
```

**How Phase 4 deviates:**
- Two sysfs targets, not one: `<root>/bus/usb/drivers/usb/unbind` and `<root>/bus/usb/drivers/usb/bind` (NOT under `bus/usb/devices/<usb_path>/`).
- `target` is a fixed driver-binding endpoint; the **payload** to `write_text` is the `usb_path` (e.g. `"2-3.1.1"`), not a literal like `"on"`.
- Two variants:
  - `child-port` (default): write_text receives the leaf `usb_path` verbatim.
  - `parent-hub`: write_text receives `usb_path.rsplit(".", 1)[0]` (e.g. `"2-3.1.1"` → `"2-3.1"`); used when `IssueDetail.SIERRA_BOOTLOADER` per A-06.
- Bind-after-unbind delay: `await asyncio.sleep(rebind_delay_seconds)` between writes (default 0.5 s; configurable via call kwarg).
- `verify()` returns `VerifyResult.deferred(detail="next_cycle_observation")` (NOT `fix_autosuspend`'s read-back of `power/control`; the kernel's re-enumeration of `cdc-wdmN` is the observable, which lands next cycle).
- `kind=ActionKind.USB_RESET`; `failure_reason=f"usb_reset:sysfs_write_error:{exc.errno}"`.
- The actual file-I/O work is delegated to `sysfs/usb_unbind_rebind.py:unbind_rebind()` — this action is a thin wrapper that handles the `WhoModem` boundary, the timing, the ActionResult shape, and decides between child-port and parent-hub from a `target: Literal["child-port", "parent-hub"]` field on the action call (Claude-discretion D-decision).

---

### `src/spark_modem/actions/driver_reset.py`

**Role:** Global DRIVER_RESET execute/verify (modprobe -r/+ qmi_wwan).
**Closest analogs:**
- `src/spark_modem/actions/soft_reset.py:46-49` (deferred verify)
- `src/spark_modem/qmi/wrapper.py:238-254` (state-changing subproc.run wrapper)
- `src/spark_modem/subproc/runner.py:108-138` (run signature)

**Pattern excerpt** (verified `qmi/wrapper.py:238-254`):
```python
async def dms_set_operating_mode(self, mode: str) -> CompletedProcess:
    """Mutates radio operating mode (online/low_power/persistent_low_power/...)."""
    self._in_critical_section = True
    try:
        return await self._runner.run(
            self._argv(
                [
                    "qmicli",
                    "--device-open-proxy",
                    f"--device={self._device}",
                    f"--dms-set-operating-mode={mode}",
                ]
            ),
            timeout_s=_STATE_CHANGE_TIMEOUT_S,
        )
    finally:
        self._in_critical_section = False
```

**Pattern excerpt 2** — runner signature (verified `subproc/runner.py:108-138`):
```python
async def run(
    argv: list[str],
    *,
    timeout_s: float,
    stdin: bytes | None = None,
    env: dict[str, str] | None = None,
) -> CompletedProcess:
    """Run argv as a subprocess and return a CompletedProcess.

    Per SP-02 'all errors are data', this function returns CompletedProcess
    for any terminating outcome. ...
    """
```

**How Phase 4 deviates:**
- `who` parameter is `WhoModem` per the dispatcher signature, but driver_reset is a HOST-scoped action; engine.py:297-305 already plans driver_reset against `WhoHost()`, so the action body uses `who` only for the ActionResult.who field. **Important:** the dispatcher calls `fn_exec(who, ctx)` always with `WhoModem`; verify the engine path passes a synthetic WhoModem for the host action OR adjust the registry signature. **Recommendation: keep `WhoModem` in the registry, have engine pass a synthetic `WhoModem(usb_path="host", cdc_wdm=None)` for driver_reset.** (Pin in Plan 04-03.)
- TWO subproc calls in sequence; the second runs even if the first "fails" with `module not loaded` (idempotency: A-05).
- `ctx.runner` does NOT exist today — **(corrected from research excerpt 3 which assumed `ctx.runner` exists)**. ActionContext (verified `actions/context.py:47-67`) currently has `qmi`, `clock`, `config`, `carrier_table`, `event_logger`, `sysfs_root` — no `runner`. Plan 04-03 must EITHER add `runner: SubprocRunnerProto` to `ActionContext` OR import `from spark_modem.subproc import runner` directly (cleaner; runner is a module-level `async def run(...)`, not an instance). **Recommendation: import the module directly** — driver_reset.py reads `from spark_modem.subproc.runner import run as subproc_run` and calls `await subproc_run(["modprobe", "-r", "qmi_wwan"], timeout_s=15.0)`. No ActionContext change.
- Stderr classification: `b"in use" in cp_unload.stderr.lower()` → `failure_reason="driver_reset:module_in_use"` returned without attempting load (PITFALLS §1.1 pattern); other unload non-zero codes proceed to load (idempotency). Load-side: any non-zero `failure_reason=f"driver_reset:load_exit_{cp_load.exit_code}"`.
- Verify returns `VerifyResult.deferred(detail="next_cycle_observation")`.

---

### `src/spark_modem/sysfs/__init__.py` + `src/spark_modem/sysfs/usb_unbind_rebind.py`

**Role:** New top-level package — sysfs file-write helpers used by usb_reset (and any future sysfs-only action).
**Closest analog:** `src/spark_modem/inventory/sysfs.py:24-50` (Path discipline + `sysfs_root_override` cross-platform pattern).

**Pattern excerpt** (verified `inventory/sysfs.py:24-50`):
```python
class SysfsInventory:
    """Walks /sys/bus/usb/devices/ for VID:PID 1199:9091 (Sierra EM7421)."""

    def __init__(self, *, sysfs_root_override: Path | None = None) -> None:
        self._sysfs_root = sysfs_root_override or Path("/sys")

    async def scan(self) -> list[ModemDescriptor]:
        """Return a list of ModemDescriptors for every Sierra EM7421 attached.
        ...
        """
        usb_devices_dir = self._sysfs_root / "bus" / "usb" / "devices"
        if not usb_devices_dir.is_dir():
            return []
        descriptors: list[ModemDescriptor] = []
        for entry in sorted(usb_devices_dir.iterdir()):
            ...
```

**How Phase 4 deviates:**
- Module-level `async def unbind_rebind(usb_path, *, target, sysfs_root, rebind_delay_seconds)` (NOT a class). The sysfs helpers are pure stateless functions per CONTEXT A-02 ("plain `open()` + `os.write` to `/sys/bus/usb/drivers/usb/{un,}bind`"). No `__init__` / state.
- `sysfs_root: Path | None = None` parameter mirrors `sysfs_root_override` exactly — `None` defaults to `Path("/sys")`. Tests pass `tmp_path` so unit tests work on Windows dev hosts (per CONTEXT "Windows dev-host friendliness" / Established Patterns).
- Two file writes (unbind, then bind), not a directory walk. The `is_dir()` defensive check has no equivalent — the kernel guarantees the driver-binding endpoints exist on Linux; on Windows / unit tests, `tmp_path`-injected directories are pre-created in test fixtures.
- `target: Literal["child-port", "parent-hub"]` parameter selects the write payload (`usb_path` vs `usb_path.rsplit(".", 1)[0]`) per A-06.
- `__init__.py` re-exports `unbind_rebind` for `from spark_modem.sysfs import unbind_rebind` ergonomics; the choice between single-file and split-file layout is Claude's-discretion (CONTEXT § Discretion item 1).
- Imports: `import asyncio`, `from pathlib import Path`, `from typing import Literal`. NO subprocess, NO qmicli, NO httpx — module is a pure file-I/O leaf.

---

### `src/spark_modem/policy/ladder.py`

**Role:** Pure function `select_rung(category, counters, config) -> ActionKind | Literal["skip:exhausted"]`. Engine calls `lookup_action()` to identify the BASE action; if base is in `{SOFT_RESET, MODEM_RESET, USB_RESET}` and category is `REGISTRATION` (or `DATAPATH/SESSION_DISCONNECTED`), `select_rung()` picks the actual rung based on per-action counters vs. config ceilings.
**Closest analogs:**
- `src/spark_modem/policy/decision_table.py:91-99` (`lookup_action` shape — pure function returning union)
- `src/spark_modem/policy/transitions.py:1-26` (pure-module imports + `Final` constants discipline)

**Pattern excerpt** (verified `policy/decision_table.py:91-99`):
```python
def lookup_action(
    category: IssueCategory, detail: IssueDetail
) -> ActionKind | str | None:
    """Return ActionKind, skip-reason string, or None for unrecognised pairs.

    Unrecognised pairs (e.g. a CONFIG category against a QMI_TIMEOUT detail)
    return None; the caller logs and skips.
    """
    return _DECISION_TABLE.get((category, detail))
```

**Pattern excerpt 2** — pure-module shape (verified `policy/transitions.py:1-26`):
```python
"""State-machine transitions (RECOVERY_SPEC §3, ADR-0008 5+2 shape).

Pure function: (prior, snap, ctx) -> new ModemState.  No I/O.

`match` on ModemState.state -- CLAUDE.md anti-pattern catalogue forbids
if/elif on ModemState.

This module ONLY computes the new (state, present, rf_blocked,
recovering_level) tuple.  ...
"""

from __future__ import annotations

from typing import Final

from spark_modem.policy.context import PolicyContext
from spark_modem.wire.diag import ModemSnapshot
from spark_modem.wire.state import ModemState

# RECOVERY_SPEC §6.1 signal-quality thresholds (Phase 4 may move these
# into Settings; Phase 2 ships them as policy-package constants).
_RSRP_FLOOR_DBM: Final[int] = -110
```

**How Phase 4 deviates:**
- Module imports: `from typing import Literal`, `from spark_modem.config.settings import Settings`, `from spark_modem.wire.enums import ActionKind, IssueCategory`. NO subprocess, NO httpx, NO os, NO asyncio — pure-function discipline (CLAUDE.md invariant 1).
- Signature: `def select_rung(category: IssueCategory, counters: dict[ActionKind, int], config: Settings) -> ActionKind | Literal["skip:exhausted"]` per CONTEXT B-01.
- Body: read `config.max_soft / config.max_modem / config.max_usb` (new Settings fields per B-01; default 3 / 2 / 1 from RECOVERY_SPEC §4.1); compare against `counters[SOFT_RESET]`, `counters[MODEM_RESET]`, `counters[USB_RESET]`. Promotion when any rung's counter is at or above its ceiling.
- Returns `Literal["skip:exhausted"]` when all three rungs are exhausted (consistent with decision_table's `"skip:..."` return convention).
- Test pinning: `tests/unit/policy/test_ladder.py` with one fixture per RECOVERY_SPEC §10.2 progression scenario (CONTEXT B-01).

---

### `tools/pull_replay_traces.py`

**Role:** Resolve Git LFS pointer at `tests/fixtures/replay/v1-30d/` to a privacy-redacted snapshot of ≥30 days of v1 historical traces; called from HIL setup phase.
**Closest analog:** `tools/gen_replay_fixtures.py:1-44` + `:201-216` (script-under-tools/ argparse + Path/seed pattern).

**Pattern excerpt** (verified `tools/gen_replay_fixtures.py:1-44`):
```python
"""Generate >=1000 replay-cycle fixtures for the Phase 2 exit gate.

Output: ``tests/fixtures/replay/<scenario>/<NNN>.json`` -- one fixture
per file.  ...

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
```

**Pattern excerpt 2** — main() shape (verified `tools/gen_replay_fixtures.py:201-216`):
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

**How Phase 4 deviates:**
- No `random.seed` (no synthesis); the script is a **resolver**, not a generator.
- Subprocess discipline: this is a `tools/` script (NOT under `src/spark_modem/`); the SP-04 lint excludes both `src/spark_modem/subproc/` AND anything outside `src/`. So this script may use `subprocess.run(["git", "lfs", "pull", "tests/fixtures/replay/v1-30d/"])` directly. (Verified in `scripts/lint_no_subprocess.sh:11`: lint scope is `src/`.)
- Privacy-redaction shape: ICCID/IMSI/IP via `sha256[:8]` hash — same shape Plan 02-09's `ctl support-bundle` already uses (CONTEXT D-03).
- Failure mode: clear non-zero exit on missing LFS auth (no silent skip per CONTEXT D-03).
- Return type: `int` (0 success, 1 failure) — matches `gen_replay_fixtures.main(argv) -> int`.
- Imports: `argparse`, `subprocess`, `sys`, `Path` — NO spark_modem imports needed (this script is a stand-alone fixture-resolver).

---

### `tests/hil/fault_inject.py`

**Role:** Software-only fault-injection helpers (qmicli-direct, kmsg writes, pkill, modprobe stops).
**Closest analog:** `tests/fakes/runner.py:1-63` (test-tier helper surface; tests/ is SP-04-exempt). Plan 03-09 logrotate test (`tests/integration/test_logrotate_create.py:25-46`) already uses real subprocess wrapped in asyncio.

**Pattern excerpt** (verified `tests/integration/test_logrotate_create.py:25-46`):
```python
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

from spark_modem.event_logger.inotify_reopener import EventLogReopener
from spark_modem.event_logger.writer import EventLogWriter
from spark_modem.wire.events import DaemonStarted

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

**How Phase 4 deviates:**
- Module-level helpers (NOT a class), one per fault: `inject_sim_power_off(cdc_wdm)`, `inject_sim_power_on(cdc_wdm)`, `inject_qmi_proxy_kill()`, `inject_kmsg(text)`, `inject_offline(cdc_wdm)`, `inject_thermal_critical()`, `inject_modem_offline_mode_clear(cdc_wdm)`. Each wraps a real subprocess (via `subprocess.run` direct or `asyncio.to_thread(subprocess.run, ...)` — tests/ is SP-04-exempt by design).
- Imports: `subprocess`, `asyncio`, `pathlib.Path`. (NOT `spark_modem.subproc.runner` — that module is the daemon's discipline, not the test-tier surface.)
- Module-level `pytestmark` is NOT defined here (this is a helper, not a test file); the scenario test files in `tests/hil/scenarios/` set the mark.
- Failure mode: each helper raises on subprocess error (test-tier code does NOT swallow; the scenario test sees the failure).
- **(Corrected from research excerpt 8 which described FakeRunner — FakeRunner is the unit-test analog; for HIL fault_inject the better analog is Plan 03-09's `test_logrotate_create.py` which uses real subprocess.)**

---

### `tests/hil/scenarios/test_*.py` (one file per HIL scenario)

**Role:** Integration test, asyncio + Fake* injection where possible, real-hardware where not. Phase 4 SC#4 list + Phase 3 deferred SCs.
**Closest analog:** `tests/integration/test_lifecycle.py:1-70` (pytestmark + asyncio + real-substrate-with-Fake*-injection pattern).

**Pattern excerpt** (verified `tests/integration/test_lifecycle.py:1-70`):
```python
"""Phase 3 SC #1..#5 integration tests via Fake* injection (Linux dev host).

The 5 success criteria from `.planning/ROADMAP.md` Phase 3:

    SC #1 — 4 modems discovered on fresh boot; READY=1 within 60s
    SC #2 — SIM swap detection latency = one cycle
    SC #3 — SIGTERM-to-exit ≤5s; clean-shutdown marker; DaemonStopped event
    SC #4 — Two ctl reset-state in parallel serialize via state.lock
    SC #5 — Logrotate (both modes) doesn't break inotify; qmi_wwan reload =
            clean state transition
...

Module-level pytestmark = [linux_only, asyncio]: filesystem inode
semantics (rename, truncate-in-place) + real flock are POSIX; Windows
dev hosts skip cleanly. ...
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from spark_modem.config.settings import Settings
from spark_modem.daemon.cycle_driver import CycleDriver
...
from tests.fakes.asyncinotify import FakeAsyncinotify, FakeMask
from tests.fakes.clock import FakeClock
from tests.fakes.runner import FakeRunner
from tests.fakes.sdnotify import FakeSdNotify
from tests.fakes.webhook import FakeWebhookPoster

pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="Filesystem inode semantics + real flock are POSIX (linux_only suite)",
    ),
    pytest.mark.asyncio,
]
```

**How Phase 4 deviates:**
- `pytestmark = [pytest.mark.linux_only, pytest.mark.hil, pytest.mark.skipif(...), pytest.mark.asyncio]` — adds the `hil` marker (registered in `pyproject.toml:78`, **already present** — no pyproject edit needed for the marker; CONTEXT.md "Lint / quality gates" line `pyproject.toml | hil pytest marker registration` should be reclassified as **already-done**).
- HIL scenarios use REAL subprocess (via `tests/hil/fault_inject.py` helpers) instead of `FakeRunner` — they run on the bench Jetson, not the dev laptop.
- One scenario file per Phase-4 SC#4 entry + Phase-3 deferred SC: `test_boot_to_healthy.py`, `test_sim_swap_soft_reset.py`, `test_modem_reset_after_soft.py`, `test_three_modem_qmi_hang_driver_reset.py`, `test_rf_event_no_destructive.py`, `test_pkill_qmi_proxy_recovered.py`, `test_qmi_wwan_reload_clean_transition.py`, `test_sigterm_under_5s.py`, `test_concurrent_ctl_reset_state_flock.py`, `test_watchdogsec_actual_fire.py`.

---

### `.github/workflows/hil.yml`

**Role:** Nightly + workflow_dispatch HIL job on self-hosted aarch64 runner tethered to bench Jetson.
**Closest analog:** `.github/workflows/ci.yml:1-49` (self-hosted aarch64 + uv venv bootstrap).

**Pattern excerpt** (verified `.github/workflows/ci.yml:1-49`):
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

      - name: ruff format --check
        run: .venv/bin/ruff format --check src/ tests/
```

**How Phase 4 deviates:**
- Triggers (CONTEXT D-01): replace `push:`+`pull_request:` with `schedule: [{cron: '0 4 * * *'}]` plus retain `workflow_dispatch:`. (Per-PR HIL is too slow; per-tag-only is too coarse.)
- Runner labels: `[self-hosted, linux, ARM64, hil-bench]` — extra `hil-bench` label routes the job to the specific bench-Jetson tethered runner (not any aarch64 runner).
- Concurrency: `group: hil-bench`, `cancel-in-progress: false` (serial; never parallel; single bench Jetson).
- `timeout-minutes: 90` (CONTEXT D-01: 90 min wall budget; full scenario suite ~45 min, plus replay-harness 30-day gate).
- Job body: `pytest -m hil -ra` (the HIL scenarios run via the registered `hil` marker; CI tests run via `pytest -m "unit or integration"` already at `ci.yml:72`).
- Pre-pytest setup step: `python -m tools.pull_replay_traces` to resolve the LFS pointer (CONTEXT D-03).
- Post-fail artefact upload: `uses: actions/upload-artifact@v4` with `path: /tmp/spark-modem-support-bundle.tar.gz` (the support bundle from `spark-modem ctl support-bundle`).

---

### `tests/fixtures/replay/v1-30d/README.md` + `.gitattributes`

**Role:** README documents quarterly refresh process; `.gitattributes` registers the JSON shards as Git LFS pointers.
**Closest analog:** None in repo (`tests/fixtures/replay/.gitkeep` is the parent shape; no existing README under fixtures).

**Pattern (no analog excerpt — net-new):**
- README.md content is Claude's-discretion (CONTEXT § Discretion item 6); minimum: refresh cadence (quarterly), regeneration command, redaction-shape contract (sha256[:8] for ICCID/IMSI/IP), expected fixture-directory shape (matches `tests/fixtures/replay/<scenario>/<NNN>.json` per Phase 2's `gen_replay_fixtures.py`).
- `.gitattributes` content: `*.json filter=lfs diff=lfs merge=lfs -text` scoped to this directory.
- The README is **committed** (per CONTEXT D-03 "the README content for `tests/fixtures/replay/v1-30d/README.md` IS committed to the repo as the runbook for trace refresh"); only the JSON shards are LFS-tracked.

---

### Wave-0 stubs — `tests/unit/policy/test_ladder.py`, `tests/unit/actions/test_modem_reset.py`, `tests/unit/actions/test_usb_reset.py`, `tests/unit/actions/test_driver_reset.py`, `tests/property/test_destructive_idempotency.py`

**Role:** Unit-test stubs (per Phase 4 plan slicing) that pin the new actions' shapes before implementation.
**Closest analogs:**
- `tests/unit/actions/test_soft_reset.py:1-76` (action unit-test shape — argv shape + outcome assertions)
- `tests/unit/actions/_helpers.py:1-111` (`make_ctx`/`base_argv`/`ok` helpers)
- `tests/unit/policy/test_engine.py:1-90` (policy unit-test ctx pattern)

**Pattern excerpt** — `make_ctx` helper (verified `tests/unit/actions/_helpers.py:70-99`):
```python
def make_ctx(
    runner: FakeRunner,
    *,
    sysfs_root: Path | None = None,
    carrier_table: CarrierTable | None = None,
) -> tuple[ActionContext, RecordingEventLogger, FakeClock]:
    """Wire up an ActionContext with a recording event logger and FakeClock."""
    qmi = QmiWrapper(runner=runner, device=_DEVICE)
    clock = FakeClock()
    logger = RecordingEventLogger()
    ctx = ActionContext(
        qmi=qmi,
        clock=clock,
        config=make_settings(),
        carrier_table=carrier_table if carrier_table is not None else make_carrier_table(),
        event_logger=logger,
        sysfs_root=sysfs_root if sysfs_root is not None else Path("/sys"),
    )
    return ctx, logger, clock


def ok(argv: list[str], stdout: bytes = b"") -> CompletedProcess:
    return CompletedProcess.make(
        argv=argv,
        exit_code=0,
        stdout=stdout,
        stderr=b"",
        duration_monotonic=0.01,
        timed_out=False,
    )
```

**Pattern excerpt 2** — soft_reset test scaffolding (verified `tests/unit/actions/test_soft_reset.py:18-44`):
```python
def _who() -> WhoModem:
    return WhoModem(usb_path="2-3.1.1", cdc_wdm="cdc-wdm0")


def _argv() -> list[str]:
    return [*base_argv(), "--dms-set-operating-mode=reset"]


@pytest.mark.asyncio
async def test_soft_reset_invokes_dms_set_operating_mode_reset() -> None:
    runner = FakeRunner()
    runner.register(_argv(), ok(_argv()))
    ctx, _logger, _clock = make_ctx(runner)
    await soft_reset.execute(_who(), ctx)
    assert any("--dms-set-operating-mode=reset" in arg for call in runner.calls for arg in call)
```

**How Phase 4 deviates:**
- `test_modem_reset.py`: argv assertion identical to `test_soft_reset.py` (same QMI verb); only the `kind` and `failure_reason` strings differ.
- `test_usb_reset.py`: NO `FakeRunner` (action is sysfs-only); use `tmp_path` to create `<tmp_path>/bus/usb/drivers/usb/{unbind,bind}` files; assert `read_text()` on each after the call equals the expected payload (`"2-3.1.1"` for child-port, `"2-3.1"` for parent-hub).
- `test_driver_reset.py`: uses `FakeRunner` registered for `["modprobe", "-r", "qmi_wwan"]` and `["modprobe", "qmi_wwan"]`; assertions cover idempotency (second invocation finds module already removed), stderr classification (`"in use"` returns `module_in_use` failure_reason), and order.
- `test_ladder.py`: uses one fixture per RECOVERY_SPEC §10.2 progression scenario; pure-function test — no FakeRunner, no ctx; just `select_rung(category=..., counters={...}, config=Settings(...))` assertions.
- `test_destructive_idempotency.py` (`tests/property/`): hypothesis-driven; for each destructive action, two back-to-back invocations produce identical observable end-state. Use the same `make_ctx` helper. (`tests/property/` does not currently exist — net-new directory; conftest.py needed.)

---

## Extended Files → Existing Block to Mirror

### `src/spark_modem/actions/dispatcher.py:_REGISTRY`

**Pattern at:** `actions/dispatcher.py:39-46` (verified):
```python
_REGISTRY: dict[ActionKind, tuple[ExecuteFn, VerifyFn]] = {
    ActionKind.SET_APN: (set_apn.execute, set_apn.verify),
    ActionKind.FIX_RAW_IP: (fix_raw_ip.execute, fix_raw_ip.verify),
    ActionKind.SIM_POWER_ON: (sim_power_on.execute, sim_power_on.verify),
    ActionKind.SOFT_RESET: (soft_reset.execute, soft_reset.verify),
    ActionKind.SET_OPERATING_MODE: (set_operating_mode.execute, set_operating_mode.verify),
    ActionKind.FIX_AUTOSUSPEND: (fix_autosuspend.execute, fix_autosuspend.verify),
}
```

**Phase 4 modification:**
- Append three rows (preserving alphabetical-by-old-order convention):
  ```python
  ActionKind.MODEM_RESET: (modem_reset.execute, modem_reset.verify),
  ActionKind.USB_RESET: (usb_reset.execute, usb_reset.verify),
  ActionKind.DRIVER_RESET: (driver_reset.execute, driver_reset.verify),
  ```
- Add three module imports to the existing `from spark_modem.actions import (...)` block (`actions/dispatcher.py:20-27`).
- Update `tests/unit/actions/test_dispatcher.py:37-56` (`test_registered_kinds_has_exactly_six_cheap_actions`): change "exactly six" to "exactly nine"; expand expected frozenset.
- Update `tests/unit/actions/test_dispatcher.py:59-63` (`test_destructive_actions_not_registered`): **delete** — it asserts the OPPOSITE of Phase 4's exit state. (Replace with `test_destructive_actions_registered`.)

---

### `src/spark_modem/wire/enums.py`

**Pattern at:** `wire/enums.py:23-79` (verified):
```python
class IssueDetail(StrEnum):
    """Specific diagnosable issues. See docs/RECOVERY_SPEC.md §4 decision table."""

    # Config
    APN_MISMATCH = "apn_mismatch"
    APN_EMPTY = "apn_empty"
    # SIM
    NO_SIM = "no_sim"
    ...
    # Enumeration / power
    ENUMERATION_MISSING = "enumeration_missing"
    ENUMERATION_ADDRESS_FAIL = "enumeration_address_fail"
    ENUMERATION_OVERCURRENT = "enumeration_overcurrent"
    AUTOSUSPEND_ON = "autosuspend_on"
    # Thermal / Zao
    THERMAL_WARN = "thermal_warn"
    THERMAL_CRITICAL = "thermal_critical"
    ...
```

**Phase 4 modification:**
- Add `SIERRA_BOOTLOADER = "sierra_bootloader"` under the `# Enumeration / power` section group (closed-enum discipline; W-04). The CONTEXT § "Claude's Discretion" item 8 confirms `IssueCategory.ENUMERATION` is reused (no new category).
- New top-level enum after `class DaemonStopReason`:
  ```python
  class SkipReason(StrEnum):
      """ActionSkipped event reason field (Phase 4 B-04)."""
      SIGNAL_BELOW_GATE = "signal_below_gate"
      LADDER_BACKOFF = "ladder_backoff"
      SAME_ACTION_BACKOFF = "same_action_backoff"
      EXHAUSTED = "exhausted"
      DISCONNECTED = "disconnected"
      MAINTENANCE = "maintenance"
      DRY_RUN = "dry_run"
  ```
- Note the `IssueCategory` enum (verified `wire/enums.py:13-20`) only has `CONFIG/SIM/DATAPATH/REGISTRATION/QMI` — no `ENUMERATION` value. **(corrected from CONTEXT.md A-06 wording)**: The decision-table row `(IssueCategory.ENUMERATION, IssueDetail.SIERRA_BOOTLOADER)` cannot be added without first adding `ENUMERATION` to `IssueCategory`. Plan 04-02 must EITHER: (a) add `ENUMERATION = "enumeration"` to `IssueCategory` (ripples to `decision_table.py:_PRIORITY_ORDER`), OR (b) classify Sierra bootloader as `IssueCategory.QMI` since the modem is observed via QMI failure modes when stuck in bootloader. **Recommendation: option (b) — `(IssueCategory.QMI, IssueDetail.SIERRA_BOOTLOADER) → ActionKind.USB_RESET`** with parent-hub variant; keeps the priority-order table unchanged.

---

### `src/spark_modem/wire/events.py`

**Pattern at:** `wire/events.py:30-60` and `:198-216` (verified):
```python
class ActionPlanned(_EventBase):
    """Policy engine decided to attempt an action on a modem."""

    kind: Literal["action_planned"] = "action_planned"
    usb_path: str
    action: ActionKind
    reason: str
    dry_run: bool = False


class ActionExecuted(_EventBase):
    """An action was executed (regardless of outcome)."""

    kind: Literal["action_executed"] = "action_executed"
    usb_path: str
    action: ActionKind
    result: ActionResult
    duration_seconds: float = Field(ge=0.0)
    ...

Event = Annotated[
    ActionPlanned
    | ActionExecuted
    | ActionFailed
    | StateTransition
    | DaemonStarted
    | DaemonStopped
    | SchemaDowngradePending
    | UsbPathMismatch
    | MaintenanceWindowStarted
    | MaintenanceWindowEnded
    | WebhookDropped
    | EventSourceCrashed
    | SimSwapped,
    Field(discriminator="kind"),
]
```

**Phase 4 modification:**
- Add new variant after `ActionFailed`:
  ```python
  class ActionSkipped(_EventBase):
      """A planned action was suppressed by a gate (Phase 4 B-04)."""
      kind: Literal["action_skipped"] = "action_skipped"
      usb_path: str
      suppressed_action: ActionKind
      reason: SkipReason
      cause_category: IssueCategory
      cause_detail: IssueDetail
  ```
- Add `ActionSkipped` to the `Event = Annotated[... | SimSwapped, ...]` tagged union.
- Add `EventKind.ACTION_SKIPPED = "action_skipped"` to `wire/enums.py:126-138` (the `EventKind` enum).
- Import `SkipReason`, `IssueCategory`, `IssueDetail` at the top of `wire/events.py`.
- `replay_harness.py` back-compat shim: continue to read `PlannedAction.suppressed_*` flags (Phase 2 fixtures); ALSO read `ActionSkipped` events on Phase 4+ traces.

---

### `src/spark_modem/wire/state.py:ModemState`

**Pattern at:** `wire/state.py:33-63` (verified):
```python
class ModemState(BaseWire):
    """Per-modem state. Persisted at state/by-usb/<usb_path>.json (ADR-0009)."""

    schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, ge=1)

    # 5 top-level states (ADR-0008).
    state: StateLiteral
    ...
    # Per-action escalation counters (ADR-0006). Decay to zero after K consecutive
    # Healthy cycles; persisted every cycle.
    counters: dict[ActionKind, int] = Field(default_factory=dict)

    # Monotonic timestamp of the last action attempted on this modem (ADR-0007).
    # None on first observation.
    last_action_monotonic: float | None = None
```

**Phase 4 modification:**
- Add field after `last_action_monotonic`:
  ```python
  # FR-25 / FR-25.1 per-action timestamp split (Phase 4 B-02).
  # Phase 2 state files load cleanly via the empty-dict default.
  # gate_same_action_backoff keys on the executed kind (300 s); gate_ladder_backoff
  # uses MAX(timestamps over destructive kinds) (90 s).
  last_action_monotonic_by_kind: dict[ActionKind, float] = Field(default_factory=dict)
  ```
- Field is **additive** (CONTEXT B-02): preserve `last_action_monotonic` for backwards-compat with Phase 2 state files.
- Engine bumps both fields atomically per cycle (RECOVERY_SPEC §8 atomic-write ordering).
- No `model_validator` change needed; pydantic v2 default_factory handles missing-on-load.

---

### `src/spark_modem/policy/decision_table.py`

**Pattern at:** `policy/decision_table.py:35-64` (verified):
```python
_DECISION_TABLE: dict[tuple[IssueCategory, IssueDetail], ActionKind | str] = {
    # config -- priority 1
    (IssueCategory.CONFIG, IssueDetail.APN_EMPTY): ActionKind.SET_APN,
    ...
    # qmi -- priority 5
    (IssueCategory.QMI, IssueDetail.QMI_CHANNEL_HUNG): ActionKind.USB_RESET,
    (IssueCategory.QMI, IssueDetail.OPERATING_MODE_OFFLINE): ActionKind.MODEM_RESET,
    (IssueCategory.QMI, IssueDetail.OPERATING_MODE_LOW_POWER): ActionKind.MODEM_RESET,
    (IssueCategory.QMI, IssueDetail.QMI_PROXY_DIED): ActionKind.DRIVER_RESET,
    (IssueCategory.QMI, IssueDetail.QMI_TIMEOUT): ActionKind.SOFT_RESET,
}
```

**Phase 4 modification:**
- Add one row in the `# qmi -- priority 5` block (per A-06 + the `IssueCategory.ENUMERATION` correction in this PATTERNS):
  ```python
  (IssueCategory.QMI, IssueDetail.SIERRA_BOOTLOADER): ActionKind.USB_RESET,
  ```
  with the parent-hub variant flag carried by the action (the dispatcher passes a `target` parameter via the engine, OR the action introspects `who.usb_path` against an inventory marker — Plan 04-02's call).
- Update `tests/unit/policy/test_decision_table.py` to include the new row in `test_every_decision_table_row_resolves`'s count (`>=18` becomes `>=19`).
- Update `tests/test_recovery_spec.py` to mention `sierra_bootloader` (the `tools/check_spec.py` lint will fail otherwise; verified at `tools/check_spec.py:31-35`).

---

### `src/spark_modem/policy/engine.py:_global_driver_reset_eligible`

**Pattern at:** `policy/engine.py:280-294` (verified — the **placeholder** that always returns False):
```python
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
```

**Pattern at 2:** `policy/engine.py:76-106` (the **call-site short-circuit** Phase 4 just unblocks):
```python
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
        ...
    return CycleResult(plans=plans, transitions=transitions_out, new_states=new_states, new_globals=new_globals)
```

**Phase 4 modification (real predicate body):**
```python
def _global_driver_reset_eligible(
    diag: Diag,
    prior_states: dict[str, ModemState],
    globals_state: GlobalsState,
    ctx: PolicyContext,
) -> bool:
    # C-03: thermal suppression
    host_details = {i.detail for i in diag.host_issues}
    if IssueDetail.THERMAL_WARN in host_details or IssueDetail.THERMAL_CRITICAL in host_details:
        return False
    # C-05: cooldown
    if globals_state.last_driver_reset_monotonic is not None:
        elapsed = ctx.clock.monotonic() - globals_state.last_driver_reset_monotonic
        if elapsed < float(ctx.config.global_driver_reset_backoff_seconds):
            return False
    # C-01: hung_count / expected_count >= multi_modem_threshold_fraction (default 0.75)
    hung_count = sum(
        1 for snap in diag.per_modem.values()
        if any(i.category == IssueCategory.QMI and i.detail == IssueDetail.QMI_CHANNEL_HUNG for i in snap.issues)
    )
    expected = ctx.config.expected_modem_count   # already on PolicyContext at policy/context.py:45
    if expected == 0:
        return False
    if (hung_count / expected) < ctx.config.multi_modem_threshold_fraction:
        return False
    # FR-24 actionable-signal: at least one hung modem has signal above floors
    for snap in diag.per_modem.values():
        if any(i.category == IssueCategory.QMI and i.detail == IssueDetail.QMI_CHANNEL_HUNG for i in snap.issues):
            sig = snap.signal
            if (sig.rsrp_dbm is None or sig.rsrp_dbm >= ctx.config.signal_rsrp_floor_dbm) \
               and (sig.rsrq_db is None or sig.rsrq_db >= ctx.config.signal_rsrq_floor_db) \
               and (sig.snr_db is None or sig.snr_db >= ctx.config.signal_snr_floor_db):
                return True
    return False
```

- ALSO: update the per-modem path (`policy/engine.py:108-184`) to bump `last_action_monotonic_by_kind[counter_bump]` alongside `last_action_monotonic` when `counter_bump is not None`. ATOMIC ordering (RECOVERY_SPEC §8 / CLAUDE.md invariant 8).
- ALSO: emit `ActionSkipped` event ALONGSIDE the existing `PlannedAction.suppressed_*` flags when soft-skip gates fire (B-04). Engine appends to `transitions_out`-style list; needs a new `events_out` list on `CycleResult`. **Cycle-driver wiring**: dispatch `events_out` to `event_logger.append()` after the atomic state write. (Or: `CycleResult` gains `skipped: list[ActionSkipped]`.)

---

### `src/spark_modem/policy/gates.py`

**Pattern at:** `policy/gates.py:72-117` (verified — the gates that need re-keying):
```python
def gate_same_action_backoff(
    state: ModemState,
    action: ActionKind,
    clock: ClockProto,
    config: Settings,
) -> bool:
    """FR-25: skip if same action attempted within backoff_seconds (300s).
    ...
    The `action` parameter is reserved for the Phase 4 split; see also
    `gate_ladder_backoff` which DOES discriminate by action kind.
    """
    del action  # reserved for Phase 4 per-action timestamp split
    if state.last_action_monotonic is None:
        return False
    elapsed = clock.monotonic() - state.last_action_monotonic
    return elapsed < float(config.backoff_seconds)


def gate_ladder_backoff(
    state: ModemState,
    action: ActionKind,
    clock: ClockProto,
    config: Settings,
) -> bool:
    """FR-25.1: cross-action ladder backoff for destructive actions.
    ...
    """
    if action not in _DESTRUCTIVE_KINDS:
        return False
    if state.last_action_monotonic is None:
        return False
    elapsed = clock.monotonic() - state.last_action_monotonic
    return elapsed < float(config.ladder_min_interval_seconds)
```

**Phase 4 modification:**
- `gate_same_action_backoff`: stop deleting `action`; key on the per-kind timestamp:
  ```python
  ts = state.last_action_monotonic_by_kind.get(action)
  if ts is None:
      return False
  return (clock.monotonic() - ts) < float(config.backoff_seconds)
  ```
- `gate_ladder_backoff`: take MAX over destructive kinds (B-02):
  ```python
  if action not in _DESTRUCTIVE_KINDS:
      return False
  destructive_ts = [
      state.last_action_monotonic_by_kind[k]
      for k in _DESTRUCTIVE_KINDS
      if k in state.last_action_monotonic_by_kind
  ]
  if not destructive_ts:
      return False
  return (clock.monotonic() - max(destructive_ts)) < float(config.ladder_min_interval_seconds)
  ```
- Existing tests in `tests/unit/policy/test_gates.py:1-60` (verified) use `last_action_monotonic` directly via `_state(last_action_monotonic=...)` — Phase 4 will need to update test fixtures to populate `last_action_monotonic_by_kind` instead. The Phase 2 `last_action_monotonic` stays on the model (B-02 additive contract) but gates no longer consult it.

---

### `src/spark_modem/policy/transitions.py:is_signal_below_gate`

**Pattern at:** `policy/transitions.py:23-42` (verified — the **module-level** `Final` constants Phase 4 migrates):
```python
# RECOVERY_SPEC §6.1 signal-quality thresholds (Phase 4 may move these
# into Settings; Phase 2 ships them as policy-package constants).
_RSRP_FLOOR_DBM: Final[int] = -110
_RSRQ_FLOOR_DB: Final[float] = -15.0
_SNR_FLOOR_DB: Final[float] = 0.0


def is_signal_below_gate(snap: ModemSnapshot) -> bool:
    """RECOVERY_SPEC §6.1: rsrp < -110 OR rsrq < -15 OR snr < 0.

    rf_blocked is True when the signal is measurably below threshold.
    Missing readings (None) -> return False (not blocked; absence of data
    is not the same as "below threshold" -- the absence-of-data case is
    handled by the observer / Zao gate upstream, not here).
    """
    sig = snap.signal
    if sig.rsrp_dbm is not None and sig.rsrp_dbm < _RSRP_FLOOR_DBM:
        return True
    if sig.rsrq_db is not None and sig.rsrq_db < _RSRQ_FLOOR_DB:
        return True
    return sig.snr_db is not None and sig.snr_db < _SNR_FLOOR_DB
```

**Phase 4 modification:**
- Delete the three `_FLOOR_*` `Final` constants.
- Change signature: `def is_signal_below_gate(snap: ModemSnapshot, config: Settings) -> bool:` — adds the second parameter.
- Body reads from `config.signal_rsrp_floor_dbm`, `config.signal_rsrq_floor_db`, `config.signal_snr_floor_db`.
- `transition()` already has `ctx: PolicyContext` (verified `policy/transitions.py:45-49`); change the single call-site `rf_blocked = is_signal_below_gate(snap)` at line 65 to `rf_blocked = is_signal_below_gate(snap, ctx.config)`.
- Engine's `_global_driver_reset_eligible` now also calls `is_signal_below_gate(snap, ctx.config)` — but inverted (it wants the snap to NOT be below the gate for actionable-signal). **Recommendation:** export a sibling `is_signal_above_floor(snap, config) -> bool` for clarity; or just inline the signal-floor check inside the eligibility predicate (per the body shown above).

---

### `src/spark_modem/config/settings.py`

**Pattern at:** `config/settings.py:70-89` (verified — the existing RELOAD_DATA-tagged backoff fields):
```python
# --- Recovery / backoff (RELOAD_DATA) ---

backoff_seconds: int = Field(
    default=300,
    ge=1,
    json_schema_extra=RELOAD_DATA,
    description="FR-25 same-action backoff (default 300s).",
)
ladder_min_interval_seconds: int = Field(
    default=90,
    ge=1,
    json_schema_extra=RELOAD_DATA,
    description="FR-25.1 cross-action ladder backoff (default 90s).",
)
healthy_streak_decay_k: int = Field(
    default=10,
    ge=1,
    json_schema_extra=RELOAD_DATA,
    description="ADR-0006 K consecutive Healthy cycles before counters decay.",
)
```

**Pattern at 2:** import (verified `config/settings.py:26`):
```python
from spark_modem.config.reload_marker import RELOAD_DATA, RELOAD_RESTART
```

**Phase 4 modification — append 9 new fields (all RELOAD_DATA tagged):**
```python
# --- Phase 4 destructive actions (RELOAD_DATA) ---

signal_rsrp_floor_dbm: int = Field(
    default=-110,
    json_schema_extra=RELOAD_DATA,
    description="RECOVERY_SPEC §6.1 RSRP floor for rf_blocked classification.",
)
signal_rsrq_floor_db: float = Field(
    default=-15.0,
    json_schema_extra=RELOAD_DATA,
    description="RECOVERY_SPEC §6.1 RSRQ floor for rf_blocked classification.",
)
signal_snr_floor_db: float = Field(
    default=0.0,
    json_schema_extra=RELOAD_DATA,
    description="RECOVERY_SPEC §6.1 SNR floor for rf_blocked classification.",
)
global_driver_reset_backoff_seconds: int = Field(
    default=3600,
    ge=1,
    json_schema_extra=RELOAD_DATA,
    description="RECOVERY_SPEC §6.4 driver_reset cooldown (default 3600s).",
)
multi_modem_threshold_fraction: float = Field(
    default=0.75,
    ge=0.0, le=1.0,
    json_schema_extra=RELOAD_DATA,
    description="FR-24 driver_reset eligibility fraction (default 0.75).",
)
expected_modem_count: int = Field(
    default=4,
    ge=1, le=99,
    json_schema_extra=RELOAD_DATA,
    description="FR-24 driver_reset denominator (total fleet size).",
)
max_soft: int = Field(
    default=3,
    ge=1,
    json_schema_extra=RELOAD_DATA,
    description="RECOVERY_SPEC §4.1 ladder ceiling for SOFT_RESET.",
)
max_modem: int = Field(
    default=2,
    ge=1,
    json_schema_extra=RELOAD_DATA,
    description="RECOVERY_SPEC §4.1 ladder ceiling for MODEM_RESET.",
)
max_usb: int = Field(
    default=1,
    ge=1,
    json_schema_extra=RELOAD_DATA,
    description="RECOVERY_SPEC §4.1 ladder ceiling for USB_RESET.",
)
```

- Note: `expected_modem_count` is **already** a `PolicyContext` field at `policy/context.py:45` (`expected_modem_count: int = 4`); Phase 4 makes it config-driven. The cycle driver constructs `PolicyContext(...)` with `expected_modem_count=settings.expected_modem_count`.
- All RELOAD_DATA tagged so SIGHUP retunes them mid-flight (Phase 3 L-03 contract).
- `Settings(frozen=True)` at `config/settings.py:36` is preserved; SIGHUP constructs a new instance.

---

### `src/spark_modem/cli/reset.py`

**Pattern at:** `cli/reset.py:23-51` (verified — the **rejection** Phase 4 unblocks):
```python
async def run(args: argparse.Namespace) -> int:
    try:
        kind = ActionKind(args.action)
    except ValueError:
        valid = sorted(k.value for k in registered_kinds())
        print(
            f"reset: unknown action {args.action!r}; valid: {valid}",
            file=sys.stderr,
        )
        return 2

    if not is_registered(kind):
        valid = sorted(k.value for k in registered_kinds())
        print(
            f"reset: action {kind.value} is destructive (Phase 4); "
            f"Phase 2 supports: {valid}",
            file=sys.stderr,
        )
        return 2

    # Production execution requires a runner + state-store + carrier-table
    # context which is set up by the daemon main (plan 02-10). For Phase 2
    # the CLI prints a stub success — the integration test in plan 02-10
    # exercises the full path.
    print(
        f"reset: would dispatch action={kind.value} modem={args.modem} "
        f"dry_run={args.dry_run}"
    )
    return 0
```

**Phase 4 modification:**
- After Phase 4 plans 01..03 register destructive actions in `_REGISTRY`, the `is_registered(kind)` check naturally lets them through — no `if not is_registered(kind)` branch removal needed (it correctly fails ONLY on truly-unregistered kinds going forward).
- Update the error message (delete "is destructive (Phase 4)" wording) — replace with the canonical Phase-2 wording: `"reset: action {kind.value} is not registered; valid: {valid}"`.
- Add `--target` argparse flag (Claude-discretion item 2):
  ```python
  parser.add_argument(
      "--target",
      choices=["child-port", "parent-hub"],
      default="child-port",
      help="usb_reset variant; parent-hub re-fires the boot transition (PITFALLS §1.6).",
  )
  ```
- Pass `args.target` through to the dispatcher path (Plan 02-10's full execution path) when `kind == ActionKind.USB_RESET`. **Decision point (Plan 04-02):** how the per-action `target` parameter is plumbed — via a new `ActionContext.action_kwargs: dict | None = None` field, OR via an action-specific helper. **Recommendation:** add `target: Literal["child-port", "parent-hub"] = "child-port"` to `ActionContext` (default safe; only usb_reset reads it; other actions ignore) — minimum churn.

---

### `pyproject.toml` (`hil` marker registration)

**Pattern at:** `pyproject.toml:70-80` (verified):
```toml
[tool.pytest.ini_options]
minversion = "8.3"
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = ["-ra", "--strict-markers", "--strict-config", "--import-mode=importlib"]
markers = [
    "unit: hardware-free unit tests",
    "integration: laptop-runnable integration tests",
    "hil: hardware-in-the-loop tests requiring real Jetson",
    "linux_only: requires Linux-specific syscalls (skipif on Windows)",
]
```

**(Corrected from CONTEXT.md "Lint / quality gates extended in Phase 4" line `pyproject.toml | hil pytest marker registration`):**
The `hil` marker is **already registered** at `pyproject.toml:78`. Phase 4 does NOT need a `pyproject.toml` edit for the marker — only the workflow file (`hil.yml`) needs to invoke `pytest -m hil`. The CONTEXT.md's "Phase 4 EXTENDS" table line for pyproject.toml should be removed from the planner's worklist.

---

## Cross-Cutting Conventions

### 1. Pydantic v2 boundary discipline (W-02)

Every wire-shape inherits `BaseWire` (verified `wire/_base.py:15-23`):
```python
class BaseWire(BaseModel):
    """Strict wire base: frozen, extra=forbid, populate_by_name."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
    )
```
**Apply to:** `ActionSkipped` event variant; new fields on `ModemState`; any other new wire-typed shape.

### 2. Closed-enum / StrEnum convention (W-04)

Every new enum value is added to a closed `StrEnum`; no string literals on the wire. Verified `wire/enums.py:23-79` shape: comment-grouped by category (`# Config`, `# SIM`, `# Enumeration / power`).
**Apply to:** `IssueDetail.SIERRA_BOOTLOADER` (under `# Enumeration / power` group). New `SkipReason` enum follows the same `class … (StrEnum)` shape with one value per skip cause.

### 3. Pure-policy module discipline (CLAUDE.md invariant 1)

`policy/transitions.py:1-26` (verified) sets the import list: `from typing import Final`, `from spark_modem.policy.context import PolicyContext`, `from spark_modem.wire.diag import ModemSnapshot`, `from spark_modem.wire.state import ModemState`. NO subprocess, NO httpx, NO os, NO asyncio.
**Apply to:** new `policy/ladder.py`. Imports must be limited to `typing`, `spark_modem.config.settings`, `spark_modem.wire.enums`. SP-04 lint (`scripts/lint_no_subprocess.sh`) covers this for subprocess; module purity is enforced by the policy-package's mypy + ruff config.

### 4. asyncio + match-on-state (CLAUDE.md anti-patterns)

`policy/transitions.py:74-117` (verified) uses `match prior.state: case "unknown": ...` exhaustively. **Apply to:** any new state-shape switching in policy/ladder.py (none anticipated; ladder is a counter-based progression, not a state machine).

### 5. Atomic write convention (CLAUDE.md invariant 5)

`state_store/atomic.py:109-156` (verified): temp + fsync + rename + directory-fsync. Every `state/by-usb/<usb_path>.json` write goes through `atomic_write_bytes`. **Apply to:** Phase 4's per-cycle write that bumps `counters[kind]` AND `last_action_monotonic_by_kind[kind]` AND `last_action_monotonic` — must be ONE atomic write per cycle (RECOVERY_SPEC §8 / CLAUDE.md invariant 8). The state_store seam already enforces this; the policy engine just hands the new `ModemState` to `StateStore.save_modem_state(usb_path, new_state)`.

### 6. SP-04 subprocess discipline

`scripts/lint_no_subprocess.sh:11` (verified) scopes lint to `src/`; `tests/` and `tools/` are exempt. **Apply to:**
- `actions/driver_reset.py`: must call `from spark_modem.subproc.runner import run as subproc_run` (NOT direct `subprocess.run`).
- `actions/usb_reset.py` + `sysfs/usb_unbind_rebind.py`: file I/O ONLY (`Path.write_text`); SP-04 doesn't fire on file writes.
- `tools/pull_replay_traces.py`: may use `subprocess.run` directly (lint scope excludes `tools/`).
- `tests/hil/fault_inject.py`: may use `subprocess.run` directly (lint scope excludes `tests/`).

### 7. pytest-asyncio + FakeClock + tmp_path convention

Verified `tests/unit/actions/_helpers.py:70-99` (`make_ctx`) + `tests/fakes/clock.py:17-65` (`FakeClock.advance(seconds)`).
**Apply to:** every Wave-0 unit-test stub. Use `make_ctx(runner, sysfs_root=tmp_path)` for usb_reset (filesystem-bound); use `FakeClock` for ladder backoff timing tests.

### 8. ActionResult / VerifyResult shape

Verified `actions/result.py:54-87`: frozen dataclass with `kind`, `who`, `succeeded`, `duration_seconds`, `failure_reason: str | None`, `verify_result: VerifyResult | None`, `dry_run`.
**Apply to:** all four new destructive actions; the `failure_reason` field uses the canonical `f"{action_kind}:{specific_reason}"` shape (per `soft_reset.py:33`'s `f"soft_reset:{err.reason.value}"`).

### 9. Subproc runner timeout discipline

Verified `qmi/wrapper.py:251` uses `_STATE_CHANGE_TIMEOUT_S` (the long timeout) for state-changing calls. **Apply to:** `driver_reset.py`'s two modprobe calls — use `timeout_s=15.0` (~15 s; modprobe should complete in <2 s, gives 7× margin) per RESEARCH.md Q2 recommendation. Hard-cap consistent with NFR-1 (P99 cycle ≤10 s — driver_reset's deferred-verify shape decouples it from the cycle budget).

### 10. WhoModem / WhoHost discriminated union

Verified `wire/diag.py:24-38`: `Who = Annotated[WhoModem | WhoHost, Field(discriminator="kind")]`. The dispatcher's `_REGISTRY` value type uses `WhoModem` (not `Who`) — `actions/dispatcher.py:35-36` (`ExecuteFn = Callable[[WhoModem, ActionContext], ...]`). **Constraint for driver_reset:** since the registry is keyed on `WhoModem`, the engine must construct a synthetic `WhoModem(usb_path="host", cdc_wdm=None)` when invoking driver_reset; the action's body uses `who` only for the ActionResult.who field. Alternatively, expand `ExecuteFn`'s parameter to `Who`, but that's a 9-call-site change. **Recommendation: synthetic WhoModem.**

---

## No Analog Found

| File | Role | Reason |
|------|------|--------|
| `tests/property/__init__.py` + `tests/property/conftest.py` + `tests/property/test_destructive_idempotency.py` | property test | `tests/property/` does not currently exist — net-new directory. Use `tests/unit/actions/_helpers.py` for `make_ctx` reuse and `hypothesis` strategies for fault parameters; pyproject.toml's `markers` table needs a `property` marker added (or use existing `unit`). |
| `tests/fixtures/replay/v1-30d/README.md` | static doc | No existing README under fixtures; net-new pattern. |
| `tests/fixtures/replay/v1-30d/.gitattributes` | LFS pointer config | No existing `.gitattributes` scoped to fixtures; net-new. |

---

## Metadata

**Analog search scope:** `src/spark_modem/`, `tests/`, `tools/`, `.github/workflows/`, `scripts/`, `pyproject.toml`.
**Files read for verification:** 24 (every cited line range loaded with `Read`; no excerpt synthesized).
**Corrections from RESEARCH.md:**
1. `actions/fix_autosuspend.py` is a real file at `src/spark_modem/actions/fix_autosuspend.py:1-62` — RESEARCH.md Excerpt 2 said "(File not read here, but referenced in Plan 02-06 SUMMARY)"; verified directly. The pattern used IS `Path.write_text` per RESEARCH.md's claim.
2. RESEARCH.md Excerpt 3 assumed `ctx.runner` exists; verified `actions/context.py:47-67` shows it does NOT. PATTERNS.md recommends importing `from spark_modem.subproc.runner import run as subproc_run` directly.
3. RESEARCH.md Excerpts 8/9 were marked `[ASSUMED]`; PATTERNS.md replaces with verified excerpts from `tests/fakes/runner.py:1-63` and `tests/integration/test_lifecycle.py:1-70`.
4. CONTEXT.md A-06 wording "decision-table row routes `(IssueCategory.ENUMERATION, IssueDetail.SIERRA_BOOTLOADER)`" cannot be honored — `IssueCategory.ENUMERATION` does not exist in `wire/enums.py:13-20`. PATTERNS.md recommends `(IssueCategory.QMI, IssueDetail.SIERRA_BOOTLOADER)` since the modem is observed via QMI failures when stuck in bootloader.
5. CONTEXT.md "Phase 4 EXTENDS" table lists `pyproject.toml | hil pytest marker registration` — the `hil` marker is **already registered** at `pyproject.toml:78`. No edit needed.
6. CONTEXT.md B-03 mentions `expected_modem_count` as a new Settings field — verified `policy/context.py:45` already has this on PolicyContext. Phase 4 adds it to Settings (the source-of-truth) and threads through cycle driver.

**Pattern extraction date:** 2026-05-10

## PATTERN MAPPING COMPLETE
