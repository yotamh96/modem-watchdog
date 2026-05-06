"""Observer - TaskGroup + per-task asyncio.timeout(8s) probe orchestrator.

Critical invariants (CLAUDE.md):
  - TaskGroup + per-task asyncio.timeout - NOT gather + wait_for (FR-70).
  - Each per-modem probe catches its own exceptions (NFR-11). The TaskGroup
    never sees an exception escape - one slow modem must not cancel siblings.
  - Zao-active modems return a zao-active ModemSnapshot with zero issues
    BEFORE any qmicli call (FR-10 / ADR-0003).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Final, Protocol

from spark_modem.inventory.descriptor import ModemDescriptor
from spark_modem.observer.issue_extractor import probe_modem_to_snapshot
from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.wire.diag import ModemSnapshot
from spark_modem.zao_log.protocol import ZaoLogTailer

logger = logging.getLogger(__name__)

DEFAULT_PROBE_TIMEOUT_S: Final[float] = 8.0


class ClockProto(Protocol):
    """Subset of the Clock surface used by the orchestrator (test-shimmable)."""

    def monotonic(self) -> float: ...
    def wall_clock_iso(self) -> str: ...


QmiFactory = Callable[[ModemDescriptor], QmiWrapper]


async def observe_all(
    modems: list[ModemDescriptor],
    qmi_factory: QmiFactory,
    zao: ZaoLogTailer,
    clock: ClockProto,
    *,
    timeout_s: float = DEFAULT_PROBE_TIMEOUT_S,
) -> list[ModemSnapshot]:
    """Run all per-modem probes in parallel and return one ModemSnapshot each.

    Order of returned snapshots matches the order of ``modems``.

    Uses ``asyncio.TaskGroup`` for structured concurrency (FR-70). Each
    per-modem probe wraps its own work in ``asyncio.timeout(timeout_s)``
    AND catches all exceptions internally so the TaskGroup never sees an
    exception escape (NFR-11). One slow modem cannot cancel siblings.
    """
    if not modems:
        return []
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(_probe_one(m, qmi_factory, zao, clock, timeout_s)) for m in modems]
    return [t.result() for t in tasks]


async def _probe_one(
    modem: ModemDescriptor,
    qmi_factory: QmiFactory,
    zao: ZaoLogTailer,
    clock: ClockProto,
    timeout_s: float,
) -> ModemSnapshot:
    """Per-modem probe with own try/except - never propagates to TaskGroup.

    Steps:
      1. Check Zao gate: if line is bonding-active under Zao, return
         zao-active snapshot with zero issues (FR-10 / ADR-0003).
      2. Else run qmicli queries through QmiWrapper under
         ``asyncio.timeout(timeout_s)``.
      3. Catch ``TimeoutError`` -> timed_out snapshot.
      4. Catch any other ``Exception`` -> errored snapshot, log + continue
         (NFR-11). The TaskGroup never sees the exception.
    """
    if zao.is_line_active(modem.line):
        return _zao_active_snapshot(modem)
    try:
        async with asyncio.timeout(timeout_s):
            return await probe_modem_to_snapshot(modem, qmi_factory(modem), clock)
    except TimeoutError:
        logger.warning("probe timed out for %s", modem.usb_path)
        return _timed_out_snapshot(modem)
    except Exception:  # NFR-11: never crash the cycle - errors are data
        logger.exception("probe failed for %s", modem.usb_path)
        return _errored_snapshot(modem)


def _zao_active_snapshot(modem: ModemDescriptor) -> ModemSnapshot:
    """FR-10: Zao-active line; never QMI-probe. Empty observation, zero issues."""
    return ModemSnapshot(
        usb_path=modem.usb_path,
        cdc_wdm=modem.cdc_wdm,
        usb_speed=None,
        operating_mode=None,
        sim_state=None,
        registration=None,
        issues=[],
    )


def _timed_out_snapshot(modem: ModemDescriptor) -> ModemSnapshot:
    """No issues recorded - policy treats absent observation as 'unknown'.

    RECOVERY_SPEC §3.1: unknown is action-gated like healthy.
    """
    return ModemSnapshot(
        usb_path=modem.usb_path,
        cdc_wdm=modem.cdc_wdm,
    )


def _errored_snapshot(modem: ModemDescriptor) -> ModemSnapshot:
    """Probe raised an unexpected exception - return empty snapshot, continue."""
    return ModemSnapshot(
        usb_path=modem.usb_path,
        cdc_wdm=modem.cdc_wdm,
    )
