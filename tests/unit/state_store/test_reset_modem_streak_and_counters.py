"""Plan 03-07 Task 1 — StateStore.reset_modem_streak_and_counters.

Pins the FR-4 / E-04 atomic reset semantics:

  - resets _healthy_streak to 0 (CLAUDE.md §"Critical invariants" #7 — SIM
    swap is the ONE legitimate counter-reset signal other than fresh-state
    daemon start)
  - clears all escalation counters in ONE atomic write per RECOVERY_SPEC
    §8 ordering (Issue #9)
  - takes per-modem asyncio.Lock OUTER + per-modem flock INNER (FR-61.1;
    ADR-0012; mirrors save_modem_state's lock discipline)
  - idempotent (calling twice on already-reset state is a no-op)
  - constructs a fresh ModemState shell when no prior state file exists
    (brand-new modem path)
  - serialises concurrent calls on the same usb_path via the per-modem
    asyncio.Lock (T-03-07-01 mitigation)

Module-level pytest.mark.asyncio applies via pyproject pytest-asyncio mode=auto.
"""

from __future__ import annotations

import asyncio
import platform
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from spark_modem.state_store.paths import lockfile_for_modem
from spark_modem.state_store.store import StateStore
from spark_modem.wire.enums import ActionKind
from spark_modem.wire.state import ModemState

IS_POSIX = platform.system() != "Windows"
_WIN_ONLY_FLOCK_REASON = "real flock semantics are POSIX-only"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_store(tmp_path: Path) -> StateStore:
    return StateStore(
        state_root_override=tmp_path / "state",
        run_dir_override=tmp_path / "run",
    )


def _modem_state_with(
    *,
    state: str = "healthy",
    healthy_streak: int = 0,
    counters: dict[ActionKind, int] | None = None,
) -> ModemState:
    """Construct a ModemState with caller-controlled streak + counters."""
    return ModemState.model_validate(
        {
            "state": state,
            "present": True,
            "rf_blocked": False,
            "recovering_level": None,
            "_healthy_streak": healthy_streak,
            "counters": dict(counters) if counters else {},
            "last_action_monotonic": None,
            "last_state_transition_iso": None,
        }
    )


# ---------------------------------------------------------------------------
# 1. Reset streak to zero
# ---------------------------------------------------------------------------


async def test_resets_streak_to_zero(tmp_path: Path) -> None:
    """Pre-populate _healthy_streak=42; reset; load returns _healthy_streak=0."""
    store = _make_store(tmp_path)
    pre = _modem_state_with(healthy_streak=42)
    await store.save_modem_state("2-3.1.1", pre)

    await store.reset_modem_streak_and_counters("2-3.1.1")

    loaded = await store.load_modem_state("2-3.1.1")
    assert loaded.state.healthy_streak == 0


# ---------------------------------------------------------------------------
# 2. Clear all escalation counters
# ---------------------------------------------------------------------------


async def test_clears_all_escalation_counters(tmp_path: Path) -> None:
    """Pre-populate counters={SET_APN: 3, SOFT_RESET: 1}; reset; counters={}."""
    store = _make_store(tmp_path)
    pre = _modem_state_with(
        healthy_streak=5,
        counters={ActionKind.SET_APN: 3, ActionKind.SOFT_RESET: 1},
    )
    await store.save_modem_state("2-3.1.1", pre)

    await store.reset_modem_streak_and_counters("2-3.1.1")

    loaded = await store.load_modem_state("2-3.1.1")
    assert loaded.state.counters == {}


# ---------------------------------------------------------------------------
# 3. Idempotency — reset on already-reset state is a no-op
# ---------------------------------------------------------------------------


async def test_idempotent_when_already_reset(tmp_path: Path) -> None:
    """Calling twice produces the same final state (streak=0, counters={})."""
    store = _make_store(tmp_path)
    pre = _modem_state_with(
        healthy_streak=10,
        counters={ActionKind.SOFT_RESET: 2},
    )
    await store.save_modem_state("2-3.1.1", pre)

    await store.reset_modem_streak_and_counters("2-3.1.1")
    after_first = await store.load_modem_state("2-3.1.1")
    await store.reset_modem_streak_and_counters("2-3.1.1")
    after_second = await store.load_modem_state("2-3.1.1")

    assert after_first.state.healthy_streak == 0
    assert after_first.state.counters == {}
    assert after_second.state.healthy_streak == 0
    assert after_second.state.counters == {}


# ---------------------------------------------------------------------------
# 4. Single atomic write per RECOVERY_SPEC §8
# ---------------------------------------------------------------------------


async def test_atomic_single_write_per_recovery_spec_section_8(tmp_path: Path) -> None:
    """reset_modem_streak_and_counters performs exactly ONE atomic_write_bytes call.

    RECOVERY_SPEC §8 ordering: streak update -> decay check -> counter reset
    -> state-write is ONE atomic write per cycle.  The reset is a flavor of
    that single atomic write where streak=0 and counters={}.
    """
    store = _make_store(tmp_path)
    pre = _modem_state_with(
        healthy_streak=7,
        counters={ActionKind.SET_APN: 2},
    )
    await store.save_modem_state("2-3.1.1", pre)

    # Record atomic_write_bytes calls during the reset only.
    with patch(
        "spark_modem.state_store.store.atomic_write_bytes",
        wraps=__import__(
            "spark_modem.state_store.store",
            fromlist=["atomic_write_bytes"],
        ).atomic_write_bytes,
    ) as mock_write:
        await store.reset_modem_streak_and_counters("2-3.1.1")

    # Exactly one atomic write — streak update + counter reset are part of
    # the same single atomic write per RECOVERY_SPEC §8.
    assert mock_write.call_count == 1


# ---------------------------------------------------------------------------
# 5. Brand-new modem (no prior state file) — fresh shell
# ---------------------------------------------------------------------------


async def test_handles_missing_state_file_creates_fresh(tmp_path: Path) -> None:
    """Empty tmp_path; reset; no exception; state file now exists with streak=0."""
    store = _make_store(tmp_path)

    # No prior save_modem_state call — the state file does not exist yet.
    await store.reset_modem_streak_and_counters("2-3.1.1")

    loaded = await store.load_modem_state("2-3.1.1")
    assert loaded.state.healthy_streak == 0
    assert loaded.state.counters == {}


# ---------------------------------------------------------------------------
# 6. Lock discipline — per-modem flock INSIDE asyncio.Lock (POSIX only)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    sys.platform == "win32",
    reason=_WIN_ONLY_FLOCK_REASON,
)
async def test_takes_per_modem_flock_inside_asyncio_lock(tmp_path: Path) -> None:
    """The per-modem flock file is created at modem-{usb_path}.lock during reset.

    FR-61.1: per-modem flock is SEPARATE from state.lock (state-store flock)
    and SEPARATE from /run/.../lock (PID lock).  ADR-0012 lock discipline.
    """
    store = _make_store(tmp_path)
    await store.reset_modem_streak_and_counters("2-3.1.1")

    expected_flock = lockfile_for_modem("2-3.1.1", run=tmp_path / "run")
    assert expected_flock.exists(), (
        f"per-modem flock file {expected_flock} must be created during reset"
    )
    # Sanity: it is NOT the state-store flock or the PID lock.
    assert expected_flock.name == "modem-2-3.1.1.lock"


# ---------------------------------------------------------------------------
# 7. Concurrent reset on the same usb_path serialises (T-03-07-01)
# ---------------------------------------------------------------------------


async def test_concurrent_reset_serializes_via_per_modem_lock(tmp_path: Path) -> None:
    """Two parallel reset_modem_streak_and_counters for the SAME usb_path
    serialise via the per-modem asyncio.Lock; both complete; atomic_write_bytes
    invoked exactly twice (no lost-update).
    """
    store = _make_store(tmp_path)
    pre = _modem_state_with(healthy_streak=3, counters={ActionKind.SOFT_RESET: 1})
    await store.save_modem_state("2-3.1.1", pre)

    with patch(
        "spark_modem.state_store.store.atomic_write_bytes",
        wraps=__import__(
            "spark_modem.state_store.store",
            fromlist=["atomic_write_bytes"],
        ).atomic_write_bytes,
    ) as mock_write:
        await asyncio.gather(
            store.reset_modem_streak_and_counters("2-3.1.1"),
            store.reset_modem_streak_and_counters("2-3.1.1"),
        )

    # Each parallel call performs its own atomic write — exactly two
    # writes total (no lost-update, no merge).
    assert mock_write.call_count == 2
    # Final state still reset.
    loaded = await store.load_modem_state("2-3.1.1")
    assert loaded.state.healthy_streak == 0
    assert loaded.state.counters == {}
