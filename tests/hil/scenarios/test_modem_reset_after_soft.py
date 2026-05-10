"""SC#4 (4) — registration loss resolved by modem_reset after one soft_reset.

Per docs/MIGRATION.md §2 #4 + RECOVERY_SPEC §10.2: when
``not_registered_searching`` persists despite a soft_reset (rung 1),
the engine must promote to modem_reset (rung 2) and the modem returns
to ``healthy`` after re-registration. This validates the Plan 04-04
ladder progression FR-22.

The scenario uses ``inject_offline`` to force the modem into the
NOT_REGISTERED state. The first cycle attempts a SOFT_RESET (rung 1).
If the issue persists past the same-action backoff (300 s) AND the
ladder cross-action gate (90 s) clear, the engine promotes to MODEM_RESET.

NOTE: Real-time wallclock for this scenario is bounded by the bigger of
(a) Settings.same_action_backoff_seconds (300 s default) for cross-cycle
gate clearing, and (b) ``modem_reset``'s ~30-60 s outage envelope. Total
budget ~5 minutes. The scenario uses a deliberately compressed cycle by
SIGHUP-tuning ``same_action_backoff_seconds`` down to 30 s for the
duration of this test (RELOAD_DATA-tagged per Plan 04-04 / Phase 3
L-03), then restoring afterwards.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import subprocess
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
_TUNING_CONF = Path("/etc/spark-modem-watchdog/conf.d/99-test-ladder-progression.yaml")
_LADDER_PROGRESSION_BUDGET_S = 240.0


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


def _sighup_daemon() -> None:
    """SIGHUP the daemon so it reloads RELOAD_DATA settings (Phase 3 L-03)."""
    pid_text = Path("/run/spark-modem-watchdog/spark-modem-watchdog.pid").read_text()
    os.kill(int(pid_text.strip()), signal.SIGHUP)


async def test_modem_reset_after_one_soft_reset(
    bench_jetson_topology: dict[str, list[str]],
) -> None:
    """Ladder rung-1 soft_reset followed by rung-2 modem_reset; modem heals."""
    from datetime import UTC, datetime  # noqa: PLC0415

    cdc_wdm = bench_jetson_topology["cdc_wdm_paths"][0]
    usb_path = bench_jetson_topology["usb_paths"][0]

    start_iso = datetime.now(UTC).isoformat()

    # Compress the same-action backoff so the test fits in <5 min wallclock.
    await asyncio.to_thread(
        _TUNING_CONF.write_text,
        "same_action_backoff_seconds: 30\n",
        encoding="utf-8",
    )
    _sighup_daemon()
    try:
        await inject_offline(cdc_wdm)
        # Wait for ladder progression: soft_reset (rung 1) -> 30 s gate ->
        # modem_reset (rung 2). Budget covers both attempts plus modem
        # boot envelope (~60 s).
        await _wait_for_state(usb_path, "healthy", timeout_s=_LADDER_PROGRESSION_BUDGET_S)
    finally:
        # Cleanup: remove tuning override, restore online state, SIGHUP.
        if await asyncio.to_thread(_TUNING_CONF.exists):
            await asyncio.to_thread(_TUNING_CONF.unlink)
        # modem_reset may have already restored online state.
        with contextlib.suppress(subprocess.CalledProcessError):
            await inject_online(cdc_wdm)
        _sighup_daemon()

    def _is_action_for(e: dict[str, object], kind: str, path: str) -> bool:
        if e.get("kind") != "action_executed":
            return False
        if e.get("action_kind") != kind:
            return False
        who = e.get("who")
        return isinstance(who, dict) and who.get("usb_path") == path

    events = await _read_events_after(start_iso)
    soft_resets = [e for e in events if _is_action_for(e, "soft_reset", usb_path)]
    modem_resets = [e for e in events if _is_action_for(e, "modem_reset", usb_path)]
    assert soft_resets, "expected at least one rung-1 soft_reset before rung-2 modem_reset"
    assert modem_resets, "expected ladder promotion to modem_reset (rung 2)"
