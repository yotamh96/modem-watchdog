"""Unit tests for observer.diag_builder.build_diag (FR-13)."""

from __future__ import annotations

from spark_modem.observer.diag_builder import build_diag
from spark_modem.wire.diag import ModemSnapshot
from spark_modem.zao_log.snapshot import ZaoSnapshot
from tests.fakes.clock import FakeClock


def test_build_diag_packs_per_modem_dict() -> None:
    """Two ModemSnapshots -> Diag.per_modem keyed by usb_path; cycle_id matches."""
    clock = FakeClock()
    snap_a = ModemSnapshot(usb_path="2-3.1.1", cdc_wdm="cdc-wdm0")
    snap_b = ModemSnapshot(usb_path="2-3.1.2", cdc_wdm="cdc-wdm1")
    zao = ZaoSnapshot.unknown(reason="test")

    diag = build_diag([snap_a, snap_b], zao, cycle_id=42, clock=clock)

    assert diag.cycle_id == 42
    assert diag.ts_iso == clock.wall_clock_iso()
    assert set(diag.per_modem.keys()) == {"2-3.1.1", "2-3.1.2"}
    assert diag.per_modem["2-3.1.1"].cdc_wdm == "cdc-wdm0"
    assert diag.per_modem["2-3.1.2"].cdc_wdm == "cdc-wdm1"
    assert diag.host_issues == []


def test_build_diag_empty_snapshots() -> None:
    """Empty list -> empty per_modem dict."""
    clock = FakeClock()
    zao = ZaoSnapshot.unknown(reason="test")

    diag = build_diag([], zao, cycle_id=0, clock=clock)

    assert diag.per_modem == {}
    assert diag.cycle_id == 0
