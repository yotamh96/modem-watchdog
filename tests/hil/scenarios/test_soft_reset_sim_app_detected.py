"""SC#4 (3) — SIM ``app_state_detected`` resolved by soft_reset.

Per docs/MIGRATION.md §2 #3 + RECOVERY_SPEC §10.1: a SIM in the
``app_state_detected`` state (UIM application not yet bound to the
modem) should be resolved by the cheap ``soft_reset`` action.

Provoking ``app_state_detected`` reliably on the bench requires power-
cycling the SIM via ``inject_sim_power_off`` then ``inject_sim_power_on``.
The window between power-on and re-attach surfaces the
``IssueDetail.SIM_POWER_DOWN`` -> ``SOFT_RESET`` decision-table row
(``policy/decision_table.py``); after the soft_reset, the modem
re-registers and returns to ``healthy``.

The scenario asserts:
  - At least ONE ``action_executed{kind=soft_reset}`` event for
    ``cdc-wdm0`` after the fault was injected.
  - No destructive action (modem_reset / usb_reset / driver_reset) ran
    -- the cheap soft_reset is the canonical recovery for this issue.
  - Modem returns to ``state == "healthy"`` within 60 s of recovery.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import pytest

from tests.hil.fault_inject import inject_sim_power_off, inject_sim_power_on

pytestmark = [
    pytest.mark.linux_only,
    pytest.mark.hil,
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="HIL bench Jetson is Linux/aarch64; tests touch /dev/cdc-wdm and /dev/kmsg.",
    ),
    pytest.mark.asyncio,
]

_STATUS_PATH = Path("/var/lib/spark-modem-watchdog/status.json")
_EVENTS_PATH = Path("/var/log/spark-modem-watchdog/events.jsonl")
_RECOVERY_BUDGET_S = 60.0
_DESTRUCTIVE_KINDS = {"modem_reset", "usb_reset", "driver_reset"}


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


async def _read_events_after(start_mono_iso: str) -> list[dict[str, object]]:
    """Read events.jsonl; return events with ts_iso lexicographically >= start.

    Uses ts_iso (RFC-3339, lex-sortable) instead of monotonic for
    cross-process ordering -- the daemon and test see different monotonic
    clocks but agree on wall-clock ISO.
    """
    if not await asyncio.to_thread(_EVENTS_PATH.exists):
        return []
    raw = await asyncio.to_thread(_EVENTS_PATH.read_text, encoding="utf-8")
    out: list[dict[str, object]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(ev, dict):
            continue
        ts = ev.get("ts_iso", "")
        if isinstance(ts, str) and ts >= start_mono_iso:
            out.append(ev)
    return out


async def test_soft_reset_resolves_sim_power_down(
    bench_jetson_topology: dict[str, list[str]],
) -> None:
    """soft_reset fires for the SIM_POWER_DOWN issue; modem returns to healthy.

    No destructive action runs -- soft_reset is rung 1.
    """
    cdc_wdm = bench_jetson_topology["cdc_wdm_paths"][0]
    usb_path = bench_jetson_topology["usb_paths"][0]

    # Capture wall-clock at start so we can filter events to this run.
    from datetime import UTC, datetime  # noqa: PLC0415

    start_iso = datetime.now(UTC).isoformat()

    await inject_sim_power_off(cdc_wdm)
    # Daemon observes SIM_POWER_DOWN within one cycle; let it observe.
    await asyncio.sleep(3.0)
    await inject_sim_power_on(cdc_wdm)

    # Wait for recovery -- soft_reset should fire and modem returns to healthy.
    await _wait_for_state(usb_path, "healthy", timeout_s=_RECOVERY_BUDGET_S)

    def _is_soft_reset_for(e: dict[str, object], path: str) -> bool:
        if e.get("kind") != "action_executed":
            return False
        if e.get("action_kind") != "soft_reset":
            return False
        who = e.get("who")
        return isinstance(who, dict) and who.get("usb_path") == path

    events = await _read_events_after(start_iso)
    soft_resets = [e for e in events if _is_soft_reset_for(e, usb_path)]
    assert soft_resets, (
        f"expected at least one action_executed{{kind=soft_reset, "
        f"who.usb_path={usb_path}}} after SIM power cycle; events.jsonl had none"
    )

    destructive = [
        e
        for e in events
        if e.get("kind") == "action_executed" and e.get("action_kind") in _DESTRUCTIVE_KINDS
    ]
    assert not destructive, (
        f"no destructive action_executed expected for SIM_POWER_DOWN; "
        f"got {[e.get('action_kind') for e in destructive]}"
    )
