"""Regression tests for the schema-downgrade-on-load path (NFR-43).

Tests assert:
  - Downgrade from v0 → current: shadow file written, fresh default returned,
    SchemaDowngradePending event emitted. No deadlock (asyncio.timeout(5)).
  - Forward-version (v99) → SchemaVersionTooNew raised; original file unchanged.
  - Current version → clean load, no shadow, no event.
  - GlobalsState downgrade path behaves identically.

DEADLOCK-FREE regression: every load_* call is wrapped in asyncio.timeout(5).
If the public/private lock split is broken (e.g. load_modem_state calls
save_modem_state instead of _save_modem_state_locked), the asyncio.Lock
re-entry deadlocks the event loop and the timeout fires → test fails.

Closes must_have: "regression test asserting the downgrade-on-load path
completes without deadlock within asyncio.timeout(5)."
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from spark_modem.state_store.store import StateStore
from spark_modem.wire.state import ModemState
from spark_modem.wire.versioning import CURRENT_SCHEMA_VERSION, SchemaVersionTooNew


def _make_store(tmp_path: Path) -> StateStore:
    return StateStore(
        state_root_override=tmp_path / "state",
        run_dir_override=tmp_path / "run",
    )


def _modem_v0_payload(usb_path: str) -> bytes:
    """Craft a v0 (past-schema) ModemState JSON payload that bypasses pydantic."""
    doc = {
        "schema_version": 0,
        "_healthy_streak": 0,
        "state": "unknown",
        "present": True,
        "rf_blocked": False,
        "recovering_level": None,
        "counters": {},
        "last_action_monotonic": None,
        "last_state_transition_iso": None,
    }
    return json.dumps(doc).encode("utf-8")


def _globals_v0_payload() -> bytes:
    """Craft a v0 GlobalsState JSON payload."""
    doc = {
        "schema_version": 0,
        "driver_reset_count": 0,
        "last_driver_reset_monotonic": None,
        "last_driver_reset_iso": None,
        "qmi_proxy_uptime_seconds": 0.0,
    }
    return json.dumps(doc).encode("utf-8")


# ---------------------------------------------------------------------------
# ModemState downgrade path
# ---------------------------------------------------------------------------


async def test_modem_state_downgrade_v0_writes_shadow_and_returns_fresh(
    tmp_path: Path,
) -> None:
    """load_modem_state on a v0 file: shadow written, fresh default returned."""
    store = _make_store(tmp_path)
    by_usb = tmp_path / "state" / "state" / "by-usb"
    by_usb.mkdir(parents=True, exist_ok=True)
    (by_usb / "2-3.1.1.json").write_bytes(_modem_v0_payload("2-3.1.1"))

    async with asyncio.timeout(5):
        result = await store.load_modem_state("2-3.1.1")

    # Shadow must exist.
    shadow = by_usb / "2-3.1.1.from-v0.json"
    assert shadow.exists(), f"shadow file {shadow} not created"

    # Fresh default written at current version.
    fresh_path = by_usb / "2-3.1.1.json"
    assert fresh_path.exists()
    fresh_data = json.loads(fresh_path.read_bytes())
    assert fresh_data["schema_version"] == CURRENT_SCHEMA_VERSION

    # Return value has fresh state and a downgrade event.
    assert result.state.state == "unknown"
    assert result.downgrade_event is not None
    assert result.downgrade_event.from_version == 0
    assert result.downgrade_event.to_version == CURRENT_SCHEMA_VERSION
    assert result.downgrade_event.shadow_path == str(shadow)


async def test_modem_state_downgrade_no_deadlock(tmp_path: Path) -> None:
    """Deadlock regression: downgrade completes within asyncio.timeout(5).

    If _save_modem_state_locked re-acquires the asyncio.Lock (calling public
    save_modem_state from inside the lock), asyncio.Lock deadlocks and the
    timeout fires. This test is the gating regression for the public/private
    split invariant.
    """
    store = _make_store(tmp_path)
    by_usb = tmp_path / "state" / "state" / "by-usb"
    by_usb.mkdir(parents=True, exist_ok=True)
    (by_usb / "2-3.1.1.json").write_bytes(_modem_v0_payload("2-3.1.1"))

    # Will hang forever (deadlock) if the public/private split is broken.
    async with asyncio.timeout(5):
        result = await store.load_modem_state("2-3.1.1")

    assert result.downgrade_event is not None


async def test_modem_state_forward_version_raises_schema_too_new(
    tmp_path: Path,
) -> None:
    """load_modem_state on schema_version=99 raises SchemaVersionTooNew."""
    store = _make_store(tmp_path)
    by_usb = tmp_path / "state" / "state" / "by-usb"
    by_usb.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema_version": 99,
        "_healthy_streak": 0,
        "state": "unknown",
        "present": True,
        "rf_blocked": False,
        "recovering_level": None,
        "counters": {},
        "last_action_monotonic": None,
        "last_state_transition_iso": None,
    }
    (by_usb / "2-3.1.1.json").write_bytes(json.dumps(doc).encode("utf-8"))

    # Original file must be unchanged.
    original_content = (by_usb / "2-3.1.1.json").read_bytes()

    with pytest.raises(SchemaVersionTooNew) as excinfo:
        async with asyncio.timeout(5):
            await store.load_modem_state("2-3.1.1")

    assert excinfo.value.seen == 99
    # Original file must NOT have been renamed.
    assert (by_usb / "2-3.1.1.json").read_bytes() == original_content


async def test_modem_state_current_version_loads_cleanly(tmp_path: Path) -> None:
    """load_modem_state on schema_version=CURRENT loads cleanly; no shadow."""
    store = _make_store(tmp_path)
    state = ModemState(
        state="healthy",
        present=True,
        rf_blocked=False,
        recovering_level=None,
        healthy_streak=0,
        counters={},
        last_action_monotonic=None,
        last_state_transition_iso=None,
    )
    await store.save_modem_state("2-3.1.1", state)

    async with asyncio.timeout(5):
        result = await store.load_modem_state("2-3.1.1")

    assert result.downgrade_event is None
    assert result.state.state == "healthy"

    # No shadow file.
    by_usb = tmp_path / "state" / "state" / "by-usb"
    shadows = list(by_usb.glob("*.from-v*.json"))
    assert shadows == []


# ---------------------------------------------------------------------------
# GlobalsState downgrade path
# ---------------------------------------------------------------------------


async def test_globals_state_downgrade_v0_deadlock_free(tmp_path: Path) -> None:
    """load_globals on a v0 file completes within asyncio.timeout(5)."""
    store = _make_store(tmp_path)
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "globals.json").write_bytes(_globals_v0_payload())

    async with asyncio.timeout(5):
        result = await store.load_globals()

    assert result.downgrade_event is not None
    assert result.downgrade_event.from_version == 0

    # Shadow must exist.
    shadow = state_dir / "globals.from-v0.json"
    assert shadow.exists()

    # Fresh default at current version.
    fresh_data = json.loads((state_dir / "globals.json").read_bytes())
    assert fresh_data["schema_version"] == CURRENT_SCHEMA_VERSION
