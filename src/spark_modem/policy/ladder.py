"""policy/ladder.py -- pure-function ladder rung selector (Phase 4 B-01).

Decision table (policy/decision_table.py) stays flat: (category, detail) ->
base ActionKind. This module owns rung selection based on per-action counters
vs. RECOVERY_SPEC §4.1 ceilings. Engine calls lookup_action() for the base,
then ladder.select_rung() for the actual ladder progression.

CLAUDE.md invariant 1 (pure-function policy): no subprocess, no httpx, no os,
no asyncio. Only typing + Settings + ActionKind imports. The package-level
SP-04 lint script enforces no kernel-touching primitives in this file.

RECOVERY_SPEC §10.2 worked examples (test fixtures in test_ladder.py):
  - counters={} (any rung-1 base)              -> base (SOFT_RESET typical)
  - counters={SOFT_RESET: 3} (== max_soft)     -> MODEM_RESET
  - counters={SOFT_RESET: 3, MODEM_RESET: 2}   -> USB_RESET
  - counters={SOFT_RESET: 3, MODEM_RESET: 2,
              USB_RESET: 1}                    -> "skip:exhausted"

DATAPATH path: (DATAPATH, SESSION_DISCONNECTED) base is MODEM_RESET. The
ladder respects that base by starting at the rung-2 index; the SOFT_RESET
rung is BELOW the base and the ladder doesn't walk backwards.

Non-ladder ActionKinds (SET_APN, FIX_RAW_IP, SIM_POWER_ON, FIX_AUTOSUSPEND,
SET_OPERATING_MODE, DRIVER_RESET) pass through unchanged -- this module
only owns the destructive triplet escalation.
"""

from __future__ import annotations

from typing import Literal

from spark_modem.config.settings import Settings
from spark_modem.wire.enums import ActionKind

# RECOVERY_SPEC §4.1 ladder, in escalation order.
_LADDER_RUNGS: tuple[ActionKind, ...] = (
    ActionKind.SOFT_RESET,
    ActionKind.MODEM_RESET,
    ActionKind.USB_RESET,
)


def select_rung(
    base: ActionKind,
    counters: dict[ActionKind, int],
    config: Settings,
) -> ActionKind | Literal["skip:exhausted"]:
    """Pick the actual ladder rung given the BASE action and per-kind counters.

    Algorithm (RECOVERY_SPEC §4.1):
      1. If `base` is not on the destructive ladder, return it unchanged --
         non-ladder actions don't escalate.
      2. Otherwise, walk rungs from `base`'s index forward. For each rung:
           - If counters[rung] >= ceiling[rung] -> promote (continue).
           - Else return rung (this is the active rung this cycle).
      3. If all rungs from `base` onward are at-or-above their ceilings ->
         return "skip:exhausted".

    The ladder is config-driven: ceilings come from Settings (max_soft /
    max_modem / max_usb), all RELOAD_DATA-tagged so SIGHUP can retune.
    """
    if base not in _LADDER_RUNGS:
        return base

    ceilings: dict[ActionKind, int] = {
        ActionKind.SOFT_RESET: config.max_soft,
        ActionKind.MODEM_RESET: config.max_modem,
        ActionKind.USB_RESET: config.max_usb,
    }

    start_idx = _LADDER_RUNGS.index(base)
    for rung in _LADDER_RUNGS[start_idx:]:
        if counters.get(rung, 0) >= ceilings[rung]:
            continue  # ceiling reached -- promote to next rung
        return rung
    return "skip:exhausted"
