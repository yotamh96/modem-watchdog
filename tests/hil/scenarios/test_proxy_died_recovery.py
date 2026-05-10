"""SC#4 (7) — pkill -9 qmi-proxy mid-cycle recovered with one driver_reset.

Per docs/MIGRATION.md §2 #7 + PITFALLS §1.1: when ``qmi-proxy`` is
killed, all qmicli clients (including the daemon) are left with stale
CIDs. The only recovery is ``driver_reset`` (modprobe -r/+ qmi_wwan,
which forces qmi-proxy to be re-spawned by Zao on its next QMI call).

Per CONTEXT C-02 (user deviation from PITFALLS §1.1 recommendation):
PROXY_DIED does NOT bypass the 75% gate. When proxy dies, all 4 modems
will time out within ~8 s anyway (one cycle), so the gate fires
naturally on the NEXT cycle. The scenario validates this: a single
``driver_reset`` recovers the fleet; no per-modem ladder thrash.

Assertions:
  - Exactly ONE ``action_executed{kind=driver_reset}`` event.
  - All 4 modems return to ``state == "healthy"`` within 90 s.
  - The qmi_proxy_died IssueDetail surfaced in events.jsonl on at least
    one modem (the daemon classified the failure correctly).
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import pytest

from tests.hil.fault_inject import inject_qmi_proxy_kill

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
    raise AssertionError(f"4 modems did not all reach healthy within {timeout_s}s")


async def test_pkill_qmi_proxy_recovered_with_one_driver_reset(
    bench_jetson_topology: dict[str, list[str]],
) -> None:
    """pkill -9 qmi-proxy -> all 4 modems hung -> single driver_reset -> healthy."""
    from datetime import UTC, datetime  # noqa: PLC0415

    start_iso = datetime.now(UTC).isoformat()

    await inject_qmi_proxy_kill()

    # Recovery: cycle observes 4/4 hung -> driver_reset fires once ->
    # Zao restarts qmi-proxy on its next QMI call -> modems re-register.
    await _wait_all_healthy(bench_jetson_topology["usb_paths"], timeout_s=_RECOVERY_BUDGET_S)

    events = await _read_events_after(start_iso)
    driver_resets = [
        e
        for e in events
        if e.get("kind") == "action_executed" and e.get("action_kind") == "driver_reset"
    ]
    assert len(driver_resets) == 1, f"expected exactly 1 driver_reset; got {len(driver_resets)}"

    # The daemon should have classified at least one modem's failure as
    # qmi_proxy_died (the canonical IssueDetail for proxy failure).
    proxy_died_issues = [
        e
        for e in events
        if e.get("kind") == "issue_observed" and e.get("issue_detail") == "qmi_proxy_died"
    ]
    assert proxy_died_issues, (
        "expected at least one issue_observed{issue_detail=qmi_proxy_died} "
        "in events.jsonl after pkill -9 qmi-proxy"
    )
