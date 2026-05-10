"""SC#4 (2) — SIM swap detected within one cycle.

Per docs/MIGRATION.md §2 #2: when a SIM is physically swapped, the
daemon must surface a ``SimSwapped`` event within one cycle.

The SIM swap itself REQUIRES manual operator action (physical card
extraction / insertion); per Phase 4 VALIDATION's "Manual-Only
Verifications" guidance, this scenario is gated by an environment
variable ``BENCH_JETSON_SIM_SWAP_PERFORMED=true`` so the suite skips
cleanly when no operator was on hand.

Operator procedure (documented for runbook completeness):
  1. Note the current ICCID hash for cdc-wdm0 from
     ``/var/lib/spark-modem-watchdog/state/by-usb/2-3.1.1.json``.
  2. ``systemctl stop spark-modem-watchdog`` (avoid mid-cycle race).
  3. Physically remove + insert a DIFFERENT SIM card in modem 0 (slot 1).
  4. Set ``BENCH_JETSON_SIM_SWAP_PERFORMED=true``.
  5. ``systemctl start spark-modem-watchdog``.
  6. Run this scenario via ``pytest -m hil tests/hil/scenarios/test_sim_swap.py``.

The test reads events.jsonl post-restart and asserts at least one
``sim_swapped`` event with redacted ICCID hashes (sha256[:8]) was
emitted (Plan 03-07 wiring).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
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
        os.environ.get("BENCH_JETSON_SIM_SWAP_PERFORMED") != "true",
        reason=(
            "Requires manual SIM swap by operator before the daemon was "
            "restarted; set BENCH_JETSON_SIM_SWAP_PERFORMED=true to enable."
        ),
    ),
    pytest.mark.asyncio,
]

_EVENTS_PATH = Path("/var/log/spark-modem-watchdog/events.jsonl")


async def test_sim_swap_emits_sim_swapped_event() -> None:
    """A sim_swapped event lands in events.jsonl within one cycle."""
    # Wait one cycle plus a small margin (default cycle is 5 s).
    await asyncio.sleep(8.0)

    raw = await asyncio.to_thread(_EVENTS_PATH.read_text, encoding="utf-8")
    sim_swap_events: list[dict[str, object]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(ev, dict) and ev.get("kind") == "sim_swapped":
            sim_swap_events.append(ev)

    assert sim_swap_events, (
        "expected at least one sim_swapped event after operator-performed "
        "SIM swap; events.jsonl had none. Verify the new SIM was actually "
        "different and the daemon completed at least one observation cycle."
    )

    # Per Plan 03-07 / T-03-07-02: ICCIDs are sha256[:8]-redacted (8 hex
    # chars). The redaction shape MUST be in place; raw 18-22-digit ICCIDs
    # in events.jsonl would be a privacy leak.
    for ev in sim_swap_events:
        old = ev.get("iccid_hash_old", "")
        new = ev.get("iccid_hash_new", "")
        assert isinstance(old, str) and len(old) == 8, (
            f"sim_swapped.iccid_hash_old must be 8-hex-char redacted; got {old!r}"
        )
        assert isinstance(new, str) and len(new) == 8, (
            f"sim_swapped.iccid_hash_new must be 8-hex-char redacted; got {new!r}"
        )
        assert old != new, "SIM swap event with identical hashes is not a swap"
