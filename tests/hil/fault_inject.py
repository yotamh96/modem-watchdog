"""Software-only fault-injection helpers for HIL scenarios (Plan 04-07).

Per Phase 4 CONTEXT D-02:

- SIM-app issues: ``qmicli --uim-sim-power-off`` / ``--uim-sim-power-on``
- QMI-hung: ``pkill -9 qmi-proxy``
- Registration loss: ``qmicli --dms-set-operating-mode=offline`` /
  ``=online``
- Thermal / usb_overcurrent: synthetic ``/dev/kmsg`` writes (the 5
  closed-enum patterns from Plan 03-05 ``kmsg/classifier.py``)

NO real RF detuning hardware (variable attenuator + antenna switch is out
of project budget). RF-blocked logic is validated via the synthetic-
signal fixture path at the daemon-input layer (Phase 2 fixtures); HIL
adds a config-injected forced-rf_blocked scenario in Plan 04-07.

Module-level helpers (NOT a class), one per fault. Each helper raises on
subprocess failure -- scenario tests MUST handle the exception explicitly
(no silent swallow). The bench Jetson is the production target; failures
in fault injection ARE test failures.

## Subprocess discipline

This module uses ``subprocess.run`` directly. The SP-04 lint scope is
``src/`` only (see ``scripts/lint_no_subprocess.sh:11``); ``tests/`` is
exempt by design. Production code under ``src/spark_modem/`` continues to
use the ``subproc/runner`` wrapper exclusively (CLAUDE.md invariant 3).

The ``--device-open-proxy`` flag is mandatory on every qmicli invocation
(FR-74 / Plan 02-02): Zao owns ``qmi-proxy``; we MUST share its socket
rather than opening the cdc-wdm device directly.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

_KMSG = Path("/dev/kmsg")


async def inject_sim_power_off(cdc_wdm: str) -> None:
    """``qmicli --uim-sim-power-off`` against the modem.

    Causes ``IssueDetail.SIM_POWER_DOWN`` on next observation. Recovery
    via the cheap ``sim_power_on`` action.
    """
    await asyncio.to_thread(
        subprocess.run,
        [
            "qmicli",
            "--device-open-proxy",
            f"--device={cdc_wdm}",
            "--uim-sim-power-off=1",
        ],
        check=True,
        capture_output=True,
    )


async def inject_sim_power_on(cdc_wdm: str) -> None:
    """``qmicli --uim-sim-power-on`` -- recovers from ``inject_sim_power_off``."""
    await asyncio.to_thread(
        subprocess.run,
        [
            "qmicli",
            "--device-open-proxy",
            f"--device={cdc_wdm}",
            "--uim-sim-power-on=1",
        ],
        check=True,
        capture_output=True,
    )


async def inject_qmi_proxy_kill() -> None:
    """``pkill -9 qmi-proxy`` -- triggers SC#4 PROXY_DIED recovery via driver_reset.

    Per PITFALLS §1.1: leaves qmicli clients with stale CIDs; only
    ``driver_reset`` restores the channel. Zao restarts ``qmi-proxy`` on
    its next QMI call.

    ``check=False``: ``pkill`` exits 1 if no process matched, which is
    still acceptable (the modem state ends up in the same place either
    way). ``check=True`` would surface infrastructure errors only.
    """
    await asyncio.to_thread(
        subprocess.run,
        ["pkill", "-9", "qmi-proxy"],
        check=False,
        capture_output=True,
    )


async def inject_kmsg(text: str) -> None:
    """Write a synthetic line to ``/dev/kmsg``.

    Per CONTEXT D-02 / Plan 03-05 closed-enum patterns:

    - ``"<3>usb 1-3.1: device not accepting address"`` -> ``USB_ENUM_FAILURE``
    - ``"<3>tegra-xusb: PSU droop"``                   -> ``TEGRA_HUB_PSU_DROOP``
    - ``"<3>thermal_throttle: trip point exceeded"``    -> ``THERMAL_THROTTLE``
    - ``"<3>qmi_wwan: probe failed"``                   -> ``QMI_WWAN_PROBE_FAIL``
    - ``"<3>usb 1-3.1: over-current condition"``        -> ``USB_OVERCURRENT``

    Requires ``CAP_SYS_ADMIN`` (the workflow runner has it via sudo for
    the support-bundle step).
    """
    if not await asyncio.to_thread(_KMSG.exists):
        raise RuntimeError("/dev/kmsg not available (HIL tier requires Linux)")
    await asyncio.to_thread(_KMSG.write_text, text, encoding="utf-8")


async def inject_offline(cdc_wdm: str) -> None:
    """``qmicli --dms-set-operating-mode=offline`` -- forces NOT_REGISTERED."""
    await asyncio.to_thread(
        subprocess.run,
        [
            "qmicli",
            "--device-open-proxy",
            f"--device={cdc_wdm}",
            "--dms-set-operating-mode=offline",
        ],
        check=True,
        capture_output=True,
    )


async def inject_online(cdc_wdm: str) -> None:
    """``qmicli --dms-set-operating-mode=online`` -- recovers from ``inject_offline``."""
    await asyncio.to_thread(
        subprocess.run,
        [
            "qmicli",
            "--device-open-proxy",
            f"--device={cdc_wdm}",
            "--dms-set-operating-mode=online",
        ],
        check=True,
        capture_output=True,
    )


async def inject_thermal_critical() -> None:
    """Synthetic thermal_critical kmsg write (no real thermal stress on bench)."""
    await inject_kmsg("<2>thermal_throttle: trip point exceeded - CRITICAL\n")
