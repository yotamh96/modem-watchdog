"""SC #5 — random USB renumbering survives state-store cross-check.

Property: cross_check_inventory NEVER silently overwrites state. Either
accepts (consistent) or raises UsbPathMismatch (inconsistent).

Hardware-free: builds a fake-sysfs tree in a tempfile.TemporaryDirectory
so each Hypothesis example gets a completely fresh filesystem state.
(Using tmp_path directly is problematic because it's function-scoped and
shared across all examples in a given test run.)

Closes Phase 1 SC #5 (ROADMAP §"Phase 1: Foundations & ADRs").
Reference: ADR-0009 (state files keyed by usb_path), CONTEXT.md S-02/S-04.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from spark_modem.state_store.errors import UsbPathMismatch
from spark_modem.state_store.inventory import (
    cross_check_inventory,
    walk_sysfs_for_qmi_modems,
)

SIERRA_VID = "1199"
SIERRA_PID_DEFAULT = "9091"


@st.composite
def fake_sysfs_inventory(draw: st.DrawFn) -> tuple[int, list[int]]:
    n = draw(st.integers(min_value=1, max_value=8))
    permutation = draw(st.permutations(list(range(n))))
    return n, permutation


def _build_sysfs_tree(sysfs_root: Path, *, n_modems: int, permutation: list[int]) -> dict[str, str]:
    """Build a fake sysfs tree and return {usb_path: cdc_wdm} mapping."""
    usb_paths = [f"2-3.1.{i + 1}" for i in range(n_modems)]
    cdc_wdms = [f"cdc-wdm{idx}" for idx in permutation]
    for up, cw in zip(usb_paths, cdc_wdms, strict=True):
        dev_dir = sysfs_root / "bus" / "usb" / "devices" / up
        qmi_dir = dev_dir / "qmi" / cw
        qmi_dir.mkdir(parents=True, exist_ok=True)
        (dev_dir / "idVendor").write_text(SIERRA_VID)
        (dev_dir / "idProduct").write_text(SIERRA_PID_DEFAULT)
    return dict(zip(usb_paths, cdc_wdms, strict=True))


@settings(max_examples=50, deadline=400)
@given(case=fake_sysfs_inventory())
def test_inventory_crosscheck_consistent_state_passes(
    case: tuple[int, list[int]],
) -> None:
    """For every consistent (usb_path, cdc_wdm) mapping, cross-check never raises.

    Uses tempfile.TemporaryDirectory to give each example a fresh filesystem
    state (tmp_path is function-scoped and shared across examples).
    """
    n, perm = case
    with tempfile.TemporaryDirectory() as tmpdir:
        sysfs_root = Path(tmpdir) / "sys"
        mapping = _build_sysfs_tree(sysfs_root, n_modems=n, permutation=perm)
        inventory = walk_sysfs_for_qmi_modems(sysfs_root)
        assert inventory == mapping

        # All consistent — no UsbPathMismatch raised.
        for usb_path, cdc_wdm in mapping.items():
            cross_check_inventory(
                file_usb_path=usb_path,
                sysfs_usb_path=usb_path,
                cdc_wdm=cdc_wdm,
            )


@settings(max_examples=30, deadline=400)
@given(
    case=fake_sysfs_inventory(),
    renumber=st.integers(min_value=0, max_value=10_000),
)
def test_inventory_crosscheck_renumbering_raises(
    case: tuple[int, list[int]],
    renumber: int,
) -> None:
    """Simulate USB renumbering: cdc-wdm assignment shuffles between boots.

    For each modem whose cdc-wdm changed, cross-check against the OLD cdc-wdm
    that was baked into the file MUST raise UsbPathMismatch.
    """
    n, perm = case

    if n == 1:
        pytest.skip("Renumbering with n==1 has no permutation effect.")
    rotated = perm[renumber % n :] + perm[: renumber % n]
    if rotated == perm:
        pytest.skip("Rotation collided with identity permutation.")

    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        sysfs_root_v1 = base / "sys_boot1"
        mapping_v1 = _build_sysfs_tree(sysfs_root_v1, n_modems=n, permutation=perm)

        sysfs_root_v2 = base / "sys_boot2"
        mapping_v2 = _build_sysfs_tree(sysfs_root_v2, n_modems=n, permutation=rotated)
        inventory_v2 = walk_sysfs_for_qmi_modems(sysfs_root_v2)
        assert inventory_v2 == mapping_v2

        # For every modem whose cdc-wdm changed, the cross-check MUST raise.
        for usb_path, old_cdc in mapping_v1.items():
            new_cdc = mapping_v2[usb_path]
            if old_cdc == new_cdc:
                continue
            with pytest.raises(UsbPathMismatch) as excinfo:
                cross_check_inventory(
                    file_usb_path=usb_path,
                    sysfs_usb_path=usb_path,
                    cdc_wdm=old_cdc,
                    expected_cdc_wdm=new_cdc,
                )
            assert excinfo.value.file_usb_path == usb_path
            assert excinfo.value.cdc_wdm == old_cdc
