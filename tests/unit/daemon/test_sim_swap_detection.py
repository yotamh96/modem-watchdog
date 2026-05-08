"""Plan 03-07 Task 2 — cycle_driver SIM-swap detection (E-04 / FR-4 / Issue #8).

Pins the SIM-swap pipeline contract:

  - On (usb_path, ICCID) diff at the same usb_path, the cycle driver:
      1. persists the updated identity map (save_identity_map)
      2. calls StateStore.reset_modem_streak_and_counters(usb_path)
      3. emits a STRUCTURED SimSwapped event via event_logger.append
         — NEVER logger.info (Issue #8 explicit gate)
  - ICCID values are sha256[:8]-redacted in the SimSwapped event payload;
    raw ICCIDs never appear in events.jsonl
  - The reset is invoked BEFORE policy.engine.run_cycle so the engine reads
    post-reset ModemState (T-03-07-05 mitigation)
  - Atomic ordering preserved: save_identity_map -> reset -> emit event
    (RECOVERY_SPEC §8 spirit; T-03-07-03 mitigation)
  - Two-modem case: only the swapped modem gets reset + SimSwapped event;
    the unchanged modem's streak/counters are preserved
  - New-modem path (no prior identity for usb_path): identity persisted,
    NO reset, NO SimSwapped event (this is enrollment, not swap)
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any
from unittest.mock import patch

from prometheus_client.registry import CollectorRegistry

from spark_modem.config.settings import Settings
from spark_modem.daemon.cycle_driver import CycleDriver
from spark_modem.event_logger.writer import EventLogWriter
from spark_modem.inventory.descriptor import ModemDescriptor
from spark_modem.policy.result import CycleResult
from spark_modem.state_store.store import StateStore
from spark_modem.status_reporter.metrics_registry import MetricRegistry
from spark_modem.wire.carriers import CarrierTable
from spark_modem.wire.diag import ModemSnapshot
from spark_modem.wire.events import EventAdapter, SimSwapped
from spark_modem.wire.identity import Identity
from tests.fakes.clock import FakeClock
from tests.fakes.runner import FakeRunner
from tests.fakes.zao_log import FixtureZaoTailer

# ---------------------------------------------------------------------------
# Test fakes specific to SIM-swap pipeline mocking
# ---------------------------------------------------------------------------


class _SingleModemInventory:
    """Inventory satisfying ``async scan() -> list[ModemDescriptor]``."""

    def __init__(self, descriptors: list[ModemDescriptor]) -> None:
        self._descriptors = descriptors

    async def scan(self) -> list[ModemDescriptor]:
        return list(self._descriptors)


class _RecordingEventLogger:
    """Records every event passed to ``append``; satisfies EventLogWriterProto."""

    def __init__(self) -> None:
        self.appended: list[Any] = []

    def append(self, event: Any) -> None:
        self.appended.append(event)


# ---------------------------------------------------------------------------
# Helpers for building test cycle drivers
# ---------------------------------------------------------------------------


def _identity_with_iccid(usb_path: str, iccid: str) -> Identity:
    """Build a valid Identity with the given iccid (matches Phase 1 schema)."""
    return Identity(
        usb_path=usb_path,
        iccid=iccid,
        imsi="425010123456789",  # canonical IL test IMSI
        first_seen_iso="2026-01-01T00:00:00+00:00",
        last_seen_iso="2026-01-01T00:00:00+00:00",
    )


def _settings_for(tmp_path: Path) -> Settings:
    return Settings(
        state_root=str(tmp_path / "state"),
        run_dir=str(tmp_path / "run"),
        events_log_path=str(tmp_path / "events.jsonl"),
        metrics_socket_path=str(tmp_path / "metrics.sock"),
        carriers_yaml_path=str(tmp_path / "carriers.yaml"),
    )


def _modem_snapshot_with_iccid(
    usb_path: str,
    cdc_wdm: str,
    iccid: str | None,
) -> ModemSnapshot:
    """Build a ModemSnapshot with an identity_iccid populated."""
    return ModemSnapshot(
        usb_path=usb_path,
        cdc_wdm=cdc_wdm,
        identity_iccid=iccid,
        identity_imsi=("425010123456789" if iccid is not None else None),
    )


def _make_driver(
    *,
    tmp_path: Path,
    descriptors: list[ModemDescriptor],
    event_logger: _RecordingEventLogger | EventLogWriter,
) -> tuple[CycleDriver, StateStore, FakeClock]:
    settings = _settings_for(tmp_path)
    clock = FakeClock(start_monotonic=1000.0)
    runner = FakeRunner()
    inventory = _SingleModemInventory(descriptors)
    zao = FixtureZaoTailer()
    carriers = CarrierTable(carriers=[])
    metrics = MetricRegistry(registry=CollectorRegistry(auto_describe=False))
    store = StateStore(
        state_root_override=tmp_path / "state",
        run_dir_override=tmp_path / "run",
    )
    driver = CycleDriver(
        store=store,
        settings=settings,
        clock=clock,
        runner=runner,
        inventory=inventory,
        zao=zao,
        carrier_table=carriers,
        event_logger=event_logger,  # type: ignore[arg-type]
        metrics=metrics,
        webhook_poster=None,
    )
    return driver, store, clock


def _sha8(iccid: str) -> str:
    return hashlib.sha256(iccid.encode("utf-8")).hexdigest()[:8]


def _empty_cycle_result() -> CycleResult:
    """Return an empty CycleResult — policy is bypassed in these tests."""
    return CycleResult()


# ---------------------------------------------------------------------------
# 1. No swap when ICCID unchanged
# ---------------------------------------------------------------------------


async def test_no_swap_when_iccid_unchanged(tmp_path: Path) -> None:
    """Pre-populate identity map iccid='ABC...'; observe same iccid; no reset, no event."""
    descriptor = ModemDescriptor(
        line=1, cdc_wdm="cdc-wdm0", usb_path="2-3.1.1", ns=None, iface="wwan0"
    )
    recording_logger = _RecordingEventLogger()
    driver, store, _clock = _make_driver(
        tmp_path=tmp_path,
        descriptors=[descriptor],
        event_logger=recording_logger,
    )
    iccid = "8997201700123456789"
    await store.save_identity_map({"2-3.1.1": _identity_with_iccid("2-3.1.1", iccid)})

    canned_snap = _modem_snapshot_with_iccid("2-3.1.1", "cdc-wdm0", iccid)
    with (
        patch(
            "spark_modem.daemon.cycle_driver.observe_all",
            return_value=[canned_snap],
        ),
        patch(
            "spark_modem.daemon.cycle_driver.policy_engine.run_cycle",
            return_value=_empty_cycle_result(),
        ),
        patch.object(
            store,
            "reset_modem_streak_and_counters",
            wraps=store.reset_modem_streak_and_counters,
        ) as mock_reset,
    ):
        await driver.run_one_cycle(cycle_id=1)

    assert mock_reset.call_count == 0, "no reset on identical ICCID"
    sim_swapped = [e for e in recording_logger.appended if isinstance(e, SimSwapped)]
    assert sim_swapped == [], "no SimSwapped event on identical ICCID"


# ---------------------------------------------------------------------------
# 2. Swap detected within ONE cycle (FR-4) emits SimSwapped event
# ---------------------------------------------------------------------------


async def test_swap_detected_within_one_cycle_emits_event(tmp_path: Path) -> None:
    """Pre-populate iccid_old='OLD...'; observe iccid_new='NEW...'; cycle emits SimSwapped."""
    descriptor = ModemDescriptor(
        line=1, cdc_wdm="cdc-wdm0", usb_path="2-3.1.1", ns=None, iface="wwan0"
    )
    recording_logger = _RecordingEventLogger()
    driver, store, _clock = _make_driver(
        tmp_path=tmp_path,
        descriptors=[descriptor],
        event_logger=recording_logger,
    )
    iccid_old = "8997201700111111111"
    iccid_new = "8997201700999999999"
    await store.save_identity_map({"2-3.1.1": _identity_with_iccid("2-3.1.1", iccid_old)})

    canned_snap = _modem_snapshot_with_iccid("2-3.1.1", "cdc-wdm0", iccid_new)
    with (
        patch(
            "spark_modem.daemon.cycle_driver.observe_all",
            return_value=[canned_snap],
        ),
        patch(
            "spark_modem.daemon.cycle_driver.policy_engine.run_cycle",
            return_value=_empty_cycle_result(),
        ),
        patch.object(
            store,
            "reset_modem_streak_and_counters",
            wraps=store.reset_modem_streak_and_counters,
        ) as mock_reset,
    ):
        await driver.run_one_cycle(cycle_id=1)

    # Reset called exactly once with the swapped modem's usb_path.
    mock_reset.assert_called_once_with("2-3.1.1")

    # SimSwapped event emitted with correctly-redacted hashes.
    sim_swapped = [e for e in recording_logger.appended if isinstance(e, SimSwapped)]
    assert len(sim_swapped) == 1
    ev = sim_swapped[0]
    assert ev.usb_path == "2-3.1.1"
    assert ev.iccid_hash_old == _sha8(iccid_old)
    assert ev.iccid_hash_new == _sha8(iccid_new)


# ---------------------------------------------------------------------------
# 3. ICCIDs redacted to sha256[:8]; raw ICCID NEVER in payload (T-03-07-02)
# ---------------------------------------------------------------------------


async def test_iccids_redacted_to_sha256_prefix_8(tmp_path: Path) -> None:
    """Explicit redaction contract: iccid_hash_*.length==8 and raw ICCID absent."""
    descriptor = ModemDescriptor(
        line=1, cdc_wdm="cdc-wdm0", usb_path="2-3.1.1", ns=None, iface="wwan0"
    )
    recording_logger = _RecordingEventLogger()
    driver, store, _clock = _make_driver(
        tmp_path=tmp_path,
        descriptors=[descriptor],
        event_logger=recording_logger,
    )
    iccid_old = "8997201700111000111"
    iccid_new = "8997201700222000222"
    await store.save_identity_map({"2-3.1.1": _identity_with_iccid("2-3.1.1", iccid_old)})

    canned_snap = _modem_snapshot_with_iccid("2-3.1.1", "cdc-wdm0", iccid_new)
    with (
        patch(
            "spark_modem.daemon.cycle_driver.observe_all",
            return_value=[canned_snap],
        ),
        patch(
            "spark_modem.daemon.cycle_driver.policy_engine.run_cycle",
            return_value=_empty_cycle_result(),
        ),
    ):
        await driver.run_one_cycle(cycle_id=1)

    sim_swapped = [e for e in recording_logger.appended if isinstance(e, SimSwapped)]
    assert len(sim_swapped) == 1
    ev = sim_swapped[0]
    assert len(ev.iccid_hash_old) == 8
    assert len(ev.iccid_hash_new) == 8
    assert ev.iccid_hash_old == _sha8(iccid_old)

    # Raw ICCID must NOT appear in the serialised event JSON.
    raw_payload = EventAdapter.dump_json(ev).decode("utf-8")
    assert iccid_old not in raw_payload
    assert iccid_new not in raw_payload


# ---------------------------------------------------------------------------
# 4. Emission via event_logger.append — NEVER logger.info (Issue #8)
# ---------------------------------------------------------------------------


async def test_event_emitted_via_event_logger_append_not_logger_info(
    tmp_path: Path,
    caplog: Any,
) -> None:
    """Issue #8 explicit gate: structured event_logger.append, not log capture.

    The cycle driver must NOT emit the SIM-swap signal as a free-form
    logger.info(...) line whose detail can be parsed only via grepping the
    journal.  Structured emission via event_logger.append(SimSwapped(...))
    is the closed-enum contract.
    """
    descriptor = ModemDescriptor(
        line=1, cdc_wdm="cdc-wdm0", usb_path="2-3.1.1", ns=None, iface="wwan0"
    )
    recording_logger = _RecordingEventLogger()
    driver, store, _clock = _make_driver(
        tmp_path=tmp_path,
        descriptors=[descriptor],
        event_logger=recording_logger,
    )
    iccid_old = "8997201700111111111"
    iccid_new = "8997201700999999999"
    await store.save_identity_map({"2-3.1.1": _identity_with_iccid("2-3.1.1", iccid_old)})

    canned_snap = _modem_snapshot_with_iccid("2-3.1.1", "cdc-wdm0", iccid_new)
    with (
        caplog.at_level(logging.INFO, logger="spark_modem.daemon.cycle_driver"),
        patch(
            "spark_modem.daemon.cycle_driver.observe_all",
            return_value=[canned_snap],
        ),
        patch(
            "spark_modem.daemon.cycle_driver.policy_engine.run_cycle",
            return_value=_empty_cycle_result(),
        ),
    ):
        await driver.run_one_cycle(cycle_id=1)

    # Structured emission happened.
    assert any(isinstance(e, SimSwapped) for e in recording_logger.appended)

    # And no logger.info() line mentions iccid / sim_swap (no log capture path).
    iccid_in_logs = any(
        "iccid" in record.message.lower() or "sim_swap" in record.message.lower()
        for record in caplog.records
    )
    assert not iccid_in_logs, "ICCID/sim_swap must not appear in logger.info output"


# ---------------------------------------------------------------------------
# 5. New modem (no prior identity) — persist identity, no swap event
# ---------------------------------------------------------------------------


async def test_new_modem_no_swap_event_only_persists_identity(tmp_path: Path) -> None:
    """Empty prior identity map; observation has 1 modem; identity persisted,
    no reset, no SimSwapped (this is enrollment, not swap).
    """
    descriptor = ModemDescriptor(
        line=1, cdc_wdm="cdc-wdm0", usb_path="2-3.1.1", ns=None, iface="wwan0"
    )
    recording_logger = _RecordingEventLogger()
    driver, store, _clock = _make_driver(
        tmp_path=tmp_path,
        descriptors=[descriptor],
        event_logger=recording_logger,
    )
    # No save_identity_map call — prior map is empty.
    iccid_new = "8997201700123456789"

    canned_snap = _modem_snapshot_with_iccid("2-3.1.1", "cdc-wdm0", iccid_new)
    with (
        patch(
            "spark_modem.daemon.cycle_driver.observe_all",
            return_value=[canned_snap],
        ),
        patch(
            "spark_modem.daemon.cycle_driver.policy_engine.run_cycle",
            return_value=_empty_cycle_result(),
        ),
        patch.object(
            store,
            "reset_modem_streak_and_counters",
            wraps=store.reset_modem_streak_and_counters,
        ) as mock_reset,
    ):
        await driver.run_one_cycle(cycle_id=1)

    # Identity persisted (load returns the new entry).
    loaded = await store.load_identity_map()
    assert "2-3.1.1" in loaded
    assert loaded["2-3.1.1"].iccid == iccid_new

    # NO reset, NO SimSwapped event — this is enrollment.
    assert mock_reset.call_count == 0
    sim_swapped = [e for e in recording_logger.appended if isinstance(e, SimSwapped)]
    assert sim_swapped == []


# ---------------------------------------------------------------------------
# 6. Two modems, one swap — only the swapped one is reset + emits event
# ---------------------------------------------------------------------------


async def test_two_modems_one_swap_only_resets_swapped_one(tmp_path: Path) -> None:
    """Modem A unchanged, modem B swapped; reset called ONCE with B's usb_path."""
    desc_a = ModemDescriptor(line=1, cdc_wdm="cdc-wdm0", usb_path="2-3.1.1", ns=None, iface="wwan0")
    desc_b = ModemDescriptor(line=2, cdc_wdm="cdc-wdm1", usb_path="2-3.1.2", ns=None, iface="wwan1")
    recording_logger = _RecordingEventLogger()
    driver, store, _clock = _make_driver(
        tmp_path=tmp_path,
        descriptors=[desc_a, desc_b],
        event_logger=recording_logger,
    )
    iccid_a = "8997201700111111111"
    iccid_b_old = "8997201700222222222"
    iccid_b_new = "8997201700999999999"
    await store.save_identity_map(
        {
            "2-3.1.1": _identity_with_iccid("2-3.1.1", iccid_a),
            "2-3.1.2": _identity_with_iccid("2-3.1.2", iccid_b_old),
        }
    )

    snap_a = _modem_snapshot_with_iccid("2-3.1.1", "cdc-wdm0", iccid_a)
    snap_b_new = _modem_snapshot_with_iccid("2-3.1.2", "cdc-wdm1", iccid_b_new)

    with (
        patch(
            "spark_modem.daemon.cycle_driver.observe_all",
            return_value=[snap_a, snap_b_new],
        ),
        patch(
            "spark_modem.daemon.cycle_driver.policy_engine.run_cycle",
            return_value=_empty_cycle_result(),
        ),
        patch.object(
            store,
            "reset_modem_streak_and_counters",
            wraps=store.reset_modem_streak_and_counters,
        ) as mock_reset,
    ):
        await driver.run_one_cycle(cycle_id=1)

    # Reset called exactly once for modem B's usb_path.
    mock_reset.assert_called_once_with("2-3.1.2")

    sim_swapped = [e for e in recording_logger.appended if isinstance(e, SimSwapped)]
    assert len(sim_swapped) == 1
    assert sim_swapped[0].usb_path == "2-3.1.2"


# ---------------------------------------------------------------------------
# 7. Reset called BEFORE policy.engine.run_cycle (T-03-07-05)
# ---------------------------------------------------------------------------


async def test_swap_reset_called_before_policy_engine(tmp_path: Path) -> None:
    """Reset MUST happen before run_cycle so the engine reads post-reset state."""
    descriptor = ModemDescriptor(
        line=1, cdc_wdm="cdc-wdm0", usb_path="2-3.1.1", ns=None, iface="wwan0"
    )
    recording_logger = _RecordingEventLogger()
    driver, store, _clock = _make_driver(
        tmp_path=tmp_path,
        descriptors=[descriptor],
        event_logger=recording_logger,
    )
    iccid_old = "8997201700111111111"
    iccid_new = "8997201700999999999"
    await store.save_identity_map({"2-3.1.1": _identity_with_iccid("2-3.1.1", iccid_old)})

    canned_snap = _modem_snapshot_with_iccid("2-3.1.1", "cdc-wdm0", iccid_new)
    call_order: list[str] = []

    async def _record_reset(usb_path: str) -> None:
        call_order.append("reset_modem_streak_and_counters")

    def _record_run_cycle(*args: Any, **kwargs: Any) -> CycleResult:
        call_order.append("policy.engine.run_cycle")
        return _empty_cycle_result()

    with (
        patch(
            "spark_modem.daemon.cycle_driver.observe_all",
            return_value=[canned_snap],
        ),
        patch(
            "spark_modem.daemon.cycle_driver.policy_engine.run_cycle",
            side_effect=_record_run_cycle,
        ),
        patch.object(store, "reset_modem_streak_and_counters", side_effect=_record_reset),
    ):
        await driver.run_one_cycle(cycle_id=1)

    assert "reset_modem_streak_and_counters" in call_order
    assert "policy.engine.run_cycle" in call_order
    reset_idx = call_order.index("reset_modem_streak_and_counters")
    engine_idx = call_order.index("policy.engine.run_cycle")
    assert reset_idx < engine_idx, (
        "reset must be called BEFORE policy.engine.run_cycle so the engine "
        "reads post-reset ModemState"
    )


# ---------------------------------------------------------------------------
# 8. Atomic ordering: save_identity_map -> reset -> event_logger.append
# ---------------------------------------------------------------------------


async def test_atomic_ordering_save_identity_then_reset_then_emit(tmp_path: Path) -> None:
    """Order is exactly save_identity_map -> reset -> event_logger.append.

    RECOVERY_SPEC §8 spirit (T-03-07-03 mitigation): identity map persisted
    first; then atomic counter reset; then event emission so events.jsonl is
    a chronological projection of post-reset state.
    """
    descriptor = ModemDescriptor(
        line=1, cdc_wdm="cdc-wdm0", usb_path="2-3.1.1", ns=None, iface="wwan0"
    )
    recording_logger = _RecordingEventLogger()
    driver, store, _clock = _make_driver(
        tmp_path=tmp_path,
        descriptors=[descriptor],
        event_logger=recording_logger,
    )
    iccid_old = "8997201700111111111"
    iccid_new = "8997201700999999999"
    await store.save_identity_map({"2-3.1.1": _identity_with_iccid("2-3.1.1", iccid_old)})

    canned_snap = _modem_snapshot_with_iccid("2-3.1.1", "cdc-wdm0", iccid_new)
    call_order: list[str] = []

    real_save_identity_map = store.save_identity_map
    real_reset = store.reset_modem_streak_and_counters
    real_append = recording_logger.append

    async def _record_save_identity_map(
        identities: dict[str, Identity],
        *,
        wait_for_flock: bool = True,
    ) -> None:
        call_order.append("save_identity_map")
        await real_save_identity_map(identities, wait_for_flock=wait_for_flock)

    async def _record_reset(usb_path: str) -> None:
        call_order.append("reset_modem_streak_and_counters")
        await real_reset(usb_path)

    def _record_append(event: Any) -> None:
        if isinstance(event, SimSwapped):
            call_order.append("event_logger.append")
        real_append(event)

    with (
        patch(
            "spark_modem.daemon.cycle_driver.observe_all",
            return_value=[canned_snap],
        ),
        patch(
            "spark_modem.daemon.cycle_driver.policy_engine.run_cycle",
            return_value=_empty_cycle_result(),
        ),
        patch.object(store, "save_identity_map", side_effect=_record_save_identity_map),
        patch.object(
            store,
            "reset_modem_streak_and_counters",
            side_effect=_record_reset,
        ),
        patch.object(recording_logger, "append", side_effect=_record_append),
    ):
        await driver.run_one_cycle(cycle_id=1)

    # The three SIM-swap-related calls happen in exactly this order.
    sim_swap_subset = [
        c
        for c in call_order
        if c
        in {
            "save_identity_map",
            "reset_modem_streak_and_counters",
            "event_logger.append",
        }
    ]
    assert sim_swap_subset == [
        "save_identity_map",
        "reset_modem_streak_and_counters",
        "event_logger.append",
    ]
