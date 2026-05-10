"""SC#4 (6) — RF event keeps daemon out of destructive resets.

Per docs/MIGRATION.md §2 #6 + RECOVERY_SPEC §6.1: when the signal
quality is below the configured floors (RSRP < -110 OR RSRQ < -15 OR
SNR < 0), the modem state has ``rf_blocked=True`` and the engine
refuses to fire ``modem_reset`` / ``usb_reset`` (FR-23). Cheap actions
still run.

Per CONTEXT D-02: there is NO real RF detuning hardware on the bench
(variable attenuator + antenna switch is out of project budget). This
scenario uses a CONFIG-INJECTED forced rf_blocked: a temporary YAML
override sets ``signal_rsrp_floor_dbm: 999`` (impossible-to-meet floor).
The daemon's ``is_signal_below_gate`` reads this from
``PolicyContext.config`` (Plan 04-04) and flips the modem's
``rf_blocked`` flag to True regardless of measured RSRP.

We then provoke an issue that would otherwise route to MODEM_RESET
(``inject_offline``), and assert:

  - At least one ``action_skipped`` event with
    ``reason="signal_below_gate"`` in events.jsonl.
  - NO ``action_executed{kind in (modem_reset, usb_reset, driver_reset)}``
    in the test window (the destructive ladder is fully gated).
  - Cheap actions (e.g. ``set_operating_mode`` or others routed to
    cheap kinds) MAY still fire -- the gate is destructive-only.

Cleanup is mandatory (T-04-07-03): the temporary
``99-test-rf.yaml`` MUST be unlinked + SIGHUP reissued in
``finally`` so cross-run contamination is impossible.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
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

_EVENTS_PATH = Path("/var/log/spark-modem-watchdog/events.jsonl")
_TEST_RF_CONF = Path("/etc/spark-modem-watchdog/conf.d/99-test-rf-gate.yaml")
_OBSERVATION_BUDGET_S = 30.0


def _sighup_daemon() -> None:
    pid_text = Path("/run/spark-modem-watchdog/spark-modem-watchdog.pid").read_text()
    os.kill(int(pid_text.strip()), signal.SIGHUP)


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


async def test_rf_blocked_gates_destructive_actions(
    bench_jetson_topology: dict[str, list[str]],
) -> None:
    """Forced rf_blocked=True: destructive actions skipped; ActionSkipped emitted."""
    from datetime import UTC, datetime  # noqa: PLC0415

    cdc_wdm = bench_jetson_topology["cdc_wdm_paths"][0]
    start_iso = datetime.now(UTC).isoformat()

    # Inject the impossible signal floor; SIGHUP so the daemon's
    # SighupSwapper picks up the RELOAD_DATA settings (Plan 03-06 L-03).
    await asyncio.to_thread(
        _TEST_RF_CONF.write_text,
        "signal_rsrp_floor_dbm: 999\n",
        encoding="utf-8",
    )
    try:
        _sighup_daemon()
        # Let SIGHUP propagate (Plan 03-06 SighupSwapper applies on next
        # cycle boundary; cycle is 5 s default).
        await asyncio.sleep(7.0)

        # Now force an issue that would otherwise route to MODEM_RESET.
        await inject_offline(cdc_wdm)

        # Wait for the daemon to observe the issue + emit ActionSkipped.
        deadline = time.monotonic() + _OBSERVATION_BUDGET_S
        action_skipped: list[dict[str, object]] = []
        while time.monotonic() < deadline:
            await asyncio.sleep(2.0)
            events = await _read_events_after(start_iso)
            action_skipped = [
                e
                for e in events
                if e.get("kind") == "action_skipped" and e.get("reason") == "signal_below_gate"
            ]
            if action_skipped:
                break
        assert action_skipped, (
            "expected at least one action_skipped{reason=signal_below_gate} "
            "after forced-rf_blocked + inject_offline (FR-23 / SC#4 #6)"
        )

        # Re-read final event set; assert NO destructive action_executed.
        events = await _read_events_after(start_iso)
        destructive = [
            e
            for e in events
            if e.get("kind") == "action_executed"
            and e.get("action_kind") in {"modem_reset", "usb_reset", "driver_reset"}
        ]
        assert not destructive, (
            f"no destructive action_executed expected under rf_blocked=True; "
            f"got {[e.get('action_kind') for e in destructive]}"
        )
    finally:
        # T-04-07-03 mitigation: cleanup must happen on every exit path.
        if await asyncio.to_thread(_TEST_RF_CONF.exists):
            await asyncio.to_thread(_TEST_RF_CONF.unlink)
        with contextlib.suppress(FileNotFoundError, ProcessLookupError):
            _sighup_daemon()
        # Modems may already be online post-recovery; suppress fault_inject
        # CalledProcessError that surfaces in that case.
        with contextlib.suppress(Exception):
            await inject_online(cdc_wdm)
