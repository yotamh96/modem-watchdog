"""End-to-end destructive actions on real hardware (FR-27 / SC#1).

Per CONTEXT A-05: each of soft_reset, modem_reset, usb_reset,
driver_reset is a separate idempotent function callable individually
via ``spark-modem reset --action=<name> --modem=<usb>``. Two
back-to-back invocations both run; the per-modem flock (ADR-0012)
serialises them; end-state is identical.

This scenario is the bench-Jetson real-hardware counterpart to
``tests/property/test_destructive_idempotency.py`` (which runs against
fakes). The property test gives mathematical confidence that the action
implementations are idempotent; this scenario gives operational
confidence that the qmicli + sysfs + modprobe primitives behave
idempotently on a real EM7421.

Per A-04 verify shape: each action returns
``VerifyResult.deferred(detail="next_cycle_observation")``; recovery is
observed by the next cycle, not in-line.

Each action is exercised twice:
  1. soft_reset on cdc-wdm0; assert exit 0 both runs; state returns
     to healthy after each.
  2. modem_reset on cdc-wdm0; same shape (longer recovery envelope).
  3. usb_reset (child-port) on cdc-wdm0; same shape.
  4. driver_reset --global; same shape; ALL 4 modems return to healthy.

To avoid 4x the real-time cost (each run is ~30-90 s), the scenario
executes them in series with a short ``_wait_for_state`` recovery
between runs. Total wallclock budget: ~10 minutes worst case.

This scenario is gated by ``BENCH_JETSON_DESTRUCTIVE_TESTS_OK=true``
so it does not run on every nightly (the cost is high; the property
test gives daily coverage).
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.hil,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="HIL bench Jetson is Linux/aarch64; tests touch /dev/cdc-wdm and /dev/kmsg.",
    ),
    pytest.mark.skipif(
        os.environ.get("BENCH_JETSON_DESTRUCTIVE_TESTS_OK") != "true",
        reason=(
            "Destructive end-to-end suite is opt-in via "
            "BENCH_JETSON_DESTRUCTIVE_TESTS_OK=true; nightly runs use the "
            "property tests under tests/property/ for daily coverage."
        ),
    ),
    pytest.mark.asyncio,
]

_STATUS_PATH = Path("/var/lib/spark-modem-watchdog/status.json")
_RECOVERY_BUDGET_S = 90.0
_CTL_BIN = "/opt/spark-modem-watchdog/python/bin/spark-modem"


async def _wait_for_state(usb_path: str, expected: str, *, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if await asyncio.to_thread(_STATUS_PATH.exists):
            raw = await asyncio.to_thread(_STATUS_PATH.read_text, encoding="utf-8")
            data = json.loads(raw)
            for modem in data.get("per_modem", []):
                if modem.get("usb_path") == usb_path and modem.get("state") == expected:
                    return
        await asyncio.sleep(2.0)
    raise AssertionError(f"timeout waiting for {usb_path} to reach state={expected}")


async def _wait_all_healthy(usb_paths: list[str], *, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if await asyncio.to_thread(_STATUS_PATH.exists):
            raw = await asyncio.to_thread(_STATUS_PATH.read_text, encoding="utf-8")
            data = json.loads(raw)
            per_modem = {m["usb_path"]: m for m in data.get("per_modem", [])}
            if set(per_modem) == set(usb_paths) and all(
                per_modem[p].get("state") == "healthy" for p in usb_paths
            ):
                return
        await asyncio.sleep(2.0)
    raise AssertionError(f"4 modems did not all reach healthy within {timeout_s}s")


async def _run_ctl(*args: str) -> subprocess.CompletedProcess[bytes]:
    """Invoke ``spark-modem ctl`` (or the equivalent ``spark-modem reset``).

    Returns the CompletedProcess for assertion. Raises if the binary
    cannot be found (the bench Jetson always has it installed via
    ``apt install spark-modem-watchdog``).
    """
    return await asyncio.to_thread(
        subprocess.run,
        [_CTL_BIN, *args],
        check=False,
        capture_output=True,
    )


async def test_soft_reset_back_to_back_idempotent(
    bench_jetson_topology: dict[str, list[str]],
) -> None:
    """soft_reset twice on cdc-wdm0; both exit 0; healthy after each."""
    cdc = bench_jetson_topology["cdc_wdm_paths"][0]
    usb = bench_jetson_topology["usb_paths"][0]

    r1 = await _run_ctl("reset", "--action=soft_reset", f"--modem={cdc}")
    assert r1.returncode == 0, f"first soft_reset failed: {r1.stderr.decode(errors='replace')}"
    await _wait_for_state(usb, "healthy", timeout_s=_RECOVERY_BUDGET_S)

    r2 = await _run_ctl("reset", "--action=soft_reset", f"--modem={cdc}")
    assert r2.returncode == 0, f"second soft_reset failed: {r2.stderr.decode(errors='replace')}"
    await _wait_for_state(usb, "healthy", timeout_s=_RECOVERY_BUDGET_S)


async def test_modem_reset_back_to_back_idempotent(
    bench_jetson_topology: dict[str, list[str]],
) -> None:
    """modem_reset twice on cdc-wdm0; both exit 0; healthy after each."""
    cdc = bench_jetson_topology["cdc_wdm_paths"][0]
    usb = bench_jetson_topology["usb_paths"][0]

    r1 = await _run_ctl("reset", "--action=modem_reset", f"--modem={cdc}")
    assert r1.returncode == 0, f"first modem_reset failed: {r1.stderr.decode(errors='replace')}"
    await _wait_for_state(usb, "healthy", timeout_s=_RECOVERY_BUDGET_S)

    r2 = await _run_ctl("reset", "--action=modem_reset", f"--modem={cdc}")
    assert r2.returncode == 0, f"second modem_reset failed: {r2.stderr.decode(errors='replace')}"
    await _wait_for_state(usb, "healthy", timeout_s=_RECOVERY_BUDGET_S)


async def test_usb_reset_back_to_back_idempotent(
    bench_jetson_topology: dict[str, list[str]],
) -> None:
    """usb_reset twice on cdc-wdm0; both exit 0; healthy after each."""
    cdc = bench_jetson_topology["cdc_wdm_paths"][0]
    usb = bench_jetson_topology["usb_paths"][0]

    r1 = await _run_ctl("reset", "--action=usb_reset", f"--modem={cdc}")
    assert r1.returncode == 0, f"first usb_reset failed: {r1.stderr.decode(errors='replace')}"
    await _wait_for_state(usb, "healthy", timeout_s=_RECOVERY_BUDGET_S)

    r2 = await _run_ctl("reset", "--action=usb_reset", f"--modem={cdc}")
    assert r2.returncode == 0, f"second usb_reset failed: {r2.stderr.decode(errors='replace')}"
    await _wait_for_state(usb, "healthy", timeout_s=_RECOVERY_BUDGET_S)


async def test_driver_reset_back_to_back_idempotent(
    bench_jetson_topology: dict[str, list[str]],
) -> None:
    """driver_reset twice (--global); both exit 0; ALL 4 modems healthy after each."""
    r1 = await _run_ctl("reset", "--action=driver_reset", "--global")
    assert r1.returncode == 0, f"first driver_reset failed: {r1.stderr.decode(errors='replace')}"
    await _wait_all_healthy(bench_jetson_topology["usb_paths"], timeout_s=_RECOVERY_BUDGET_S)

    r2 = await _run_ctl("reset", "--action=driver_reset", "--global")
    assert r2.returncode == 0, f"second driver_reset failed: {r2.stderr.decode(errors='replace')}"
    await _wait_all_healthy(bench_jetson_topology["usb_paths"], timeout_s=_RECOVERY_BUDGET_S)
