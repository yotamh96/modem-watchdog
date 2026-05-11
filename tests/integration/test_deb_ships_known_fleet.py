"""X-03 .deb shipment integration test.

Verifies that the built ``.deb`` ships the known-fleet directory under
``/etc/spark-modem-watchdog/known-fleet/`` AND that the static debian/*
files declare the shipment correctly.

The ``dpkg-deb`` test (Test 1) is conditional: skip on hosts without
``dpkg-deb`` (Windows dev laptop) or without a built artifact. The static
checks (Tests 2-6) run unconditionally, including on Windows dev hosts.

Plan 05-06 / X-03 / RESEARCH Q10:

    debian/install line:  tests/fixtures/fleet /etc/spark-modem-watchdog/known-fleet/
    debian/dirs line:     /etc/spark-modem-watchdog/known-fleet

The daemon's ``preflight_check_known_fleet_triple`` (Plan 05-04) reads
the resulting ``<box-id>/triple.json`` files at startup; this test pins
the packaging contract that makes that directory exist on the target box.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _find_deb() -> Path | None:
    """Locate the most recent built .deb under dist/ or the parent dir
    (where dpkg-buildpackage drops binaries by default).

    Returns None if no built artifact is found locally.
    """
    candidates = list(_REPO_ROOT.glob("dist/*.deb")) + list(_REPO_ROOT.glob("../*.deb"))
    if not candidates:
        return None
    # Most recent by mtime — handles multi-build dev hosts cleanly.
    return max(candidates, key=lambda p: p.stat().st_mtime)


@pytest.mark.skipif(
    shutil.which("dpkg-deb") is None,
    reason="dpkg-deb not on PATH (typical on non-Debian hosts including Windows dev laptops)",
)
def test_deb_contains_known_fleet_path() -> None:
    """When a built .deb is available, its content listing includes the
    known-fleet directory. Skipped on hosts without a freshly built .deb."""
    deb = _find_deb()
    if deb is None:
        pytest.skip("no built .deb under dist/ or ../ — run debian/rules build first")
    result = subprocess.run(
        ["dpkg-deb", "--contents", str(deb)],
        capture_output=True,
        text=True,
        check=True,
    )
    # dpkg-deb --contents output lines look like:
    #   drwxr-xr-x root/root  0 ... ./etc/spark-modem-watchdog/known-fleet/
    #   -rw-r--r-- root/root  234 ... ./etc/spark-modem-watchdog/known-fleet/_test/triple.json
    assert "/etc/spark-modem-watchdog/known-fleet" in result.stdout, (
        f"known-fleet path missing from .deb contents:\n{result.stdout}"
    )


def test_debian_install_declares_known_fleet() -> None:
    """Static check: debian/install ships tests/fixtures/fleet to the
    known-fleet destination (catches accidental revert)."""
    install_path = _REPO_ROOT / "debian" / "spark-modem-watchdog.install"
    install = install_path.read_text(encoding="utf-8")
    assert "tests/fixtures/fleet" in install, (
        "debian/spark-modem-watchdog.install missing tests/fixtures/fleet source"
    )
    assert "/etc/spark-modem-watchdog/known-fleet" in install, (
        "debian/spark-modem-watchdog.install missing "
        "/etc/spark-modem-watchdog/known-fleet destination"
    )


def test_debian_dirs_declares_known_fleet() -> None:
    """Static check: debian/dirs pre-creates the known-fleet directory
    (so dpkg owns it even if tests/fixtures/fleet ever ships empty)."""
    dirs_path = _REPO_ROOT / "debian" / "spark-modem-watchdog.dirs"
    dirs = dirs_path.read_text(encoding="utf-8")
    assert "/etc/spark-modem-watchdog/known-fleet" in dirs, (
        "debian/spark-modem-watchdog.dirs missing /etc/spark-modem-watchdog/known-fleet entry"
    )


def test_example_fleet_fixture_exists_and_is_valid() -> None:
    """The Plan-03 example fixture ships in the .deb so the daemon's
    preflight is never literally empty on first install (T-05-06-01)."""
    path = _REPO_ROOT / "tests" / "fixtures" / "fleet" / "_test" / "triple.json"
    assert path.is_file(), "tests/fixtures/fleet/_test/triple.json missing (Plan 05-03 dependency)"
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("em7421_firmware", "zao_sdk", "libqmi"):
        assert key in data, f"missing required FleetTriple key: {key}"
        assert isinstance(data[key], str) and data[key], f"key {key} must be a non-empty string"


def test_no_known_fleet_references_in_postinst() -> None:
    """RESEARCH Q10 anti-pattern pin: postinst stays scoped to
    ModemManager masking + state dir creation; the known-fleet directory
    is installed declaratively via dh_install."""
    postinst = (_REPO_ROOT / "debian" / "spark-modem-watchdog.postinst").read_text(encoding="utf-8")
    assert "known-fleet" not in postinst, (
        "debian/spark-modem-watchdog.postinst must NOT reference known-fleet (per RESEARCH Q10)"
    )


def test_no_known_fleet_references_in_rules() -> None:
    """RESEARCH Q10 anti-pattern pin: debian/rules does NOT need an
    override_dh_auto_install for known-fleet — declarative debian/install
    handles it."""
    rules = (_REPO_ROOT / "debian" / "rules").read_text(encoding="utf-8")
    assert "known-fleet" not in rules, (
        "debian/rules must NOT reference known-fleet (per RESEARCH Q10)"
    )
