"""SC#4 (5) — three-modem QMI hang triggers driver_reset (no thrash).

Per docs/MIGRATION.md §2 #5 + RECOVERY_SPEC §6.4: when >=75% of the
fleet is QMI-hung (3 of 4) AND at least one hung modem has actionable
signal AND no thermal warning is active, the engine fires exactly ONE
``driver_reset``. This validates the Plan 04-03 ``_global_driver_reset_eligible``
predicate end-to-end.

CONTEXT C-01: denominator is total expected modems (4), not non-Zao-active.
CONTEXT C-02: PROXY_DIED does NOT bypass the 75% gate -- it fires
naturally when all 4 modems time out.

The scenario simulates the hang by injecting offline on three of four
modems. Per RESEARCH.md the cleanest fault is ``inject_offline`` on
modems 0..2; modem 3 stays online. With 3/4 hung + actionable signal on
the hung set, ``_global_driver_reset_eligible`` returns True and a
single driver_reset fires.

Assertions:
  - Exactly ONE ``action_executed{kind=driver_reset}`` event in the
    test window.
  - NO ``action_executed{kind=usb_reset}`` per-modem events (engine
    cycle short-circuit per ``policy/engine.py:76-106`` prevents
    per-modem actions on the same cycle as a global driver_reset).
  - All 4 modems return to ``state == "healthy"`` within 90 s.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import time
from pathlib import Path

import pytest

from tests.hil.fault_inject import inject_offline, inject_online

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
_RECOVERY_BUDGET_S = 90.0


async def _read_events_after(start_iso: str) -> list[dict[str, object]]:
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
        if isinstance(ev, dict):
            ts = ev.get("ts_iso", "")
            if isinstance(ts, str) and ts >= start_iso:
                out.append(ev)
    return out


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
    raise AssertionError(f"not all 4 modems reached healthy within {timeout_s}s")


async def test_three_modem_hang_fires_single_driver_reset(
    bench_jetson_topology: dict[str, list[str]],
) -> None:
    """3-of-4 QMI-hung scenario fires exactly one driver_reset; no per-modem race."""
    from datetime import UTC, datetime  # noqa: PLC0415

    cdc_wdms = bench_jetson_topology["cdc_wdm_paths"]
    start_iso = datetime.now(UTC).isoformat()

    # Hang 3 of 4 modems by forcing them offline.
    for cdc in cdc_wdms[:3]:
        await inject_offline(cdc)

    # The 75% gate fires on the next cycle (~5 s); driver_reset takes
    # ~10-30 s for module reload + re-enumeration; modems re-register.
    try:
        await _wait_all_healthy(bench_jetson_topology["usb_paths"], timeout_s=_RECOVERY_BUDGET_S)
    finally:
        # Cleanup: ensure all modems are back online (driver_reset may
        # have done this implicitly, but be defensive).
        for cdc in cdc_wdms[:3]:
            # Modems may already be online post-driver_reset; suppress
            # the CalledProcessError that fault_inject raises in that case.
            with contextlib.suppress(Exception):
                await inject_online(cdc)

    events = await _read_events_after(start_iso)
    driver_resets = [
        e
        for e in events
        if e.get("kind") == "action_executed" and e.get("action_kind") == "driver_reset"
    ]
    usb_resets = [
        e
        for e in events
        if e.get("kind") == "action_executed" and e.get("action_kind") == "usb_reset"
    ]

    assert len(driver_resets) == 1, (
        f"expected exactly 1 driver_reset (no thrash); got {len(driver_resets)}"
    )
    assert not usb_resets, (
        f"per-modem usb_reset must NOT race the global driver_reset on the "
        f"same cycle (engine.py:76-106 short-circuit); got {len(usb_resets)}"
    )
