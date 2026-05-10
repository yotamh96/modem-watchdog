"""HIL pytest fixtures + collection guards.

All tests under ``tests/hil/`` are LINUX-ONLY and HIL-marked. Individual
scenario files inherit nothing from this conftest by default -- they MUST
set their own ``pytestmark`` (see ``tests/hil/README.md``). This conftest
exists to:

  1. Belt-and-suspenders block collection on Windows dev hosts (the
     workflow already runs only on linux/ARM64, but a developer running
     ``pytest`` locally on Windows should not collect HIL tests).
  2. Provide the bench-Jetson topology fixture (Phase 4 CONTEXT D-01).
"""

from __future__ import annotations

import sys

import pytest

# Belt-and-suspenders: skip HIL collection on Windows. The hil-bench
# runner is linux/ARM64; a developer running `pytest` on Windows should
# not even attempt to collect these tests.
collect_ignore_glob: list[str] = []

if sys.platform == "win32":
    collect_ignore_glob = ["**/*.py"]


@pytest.fixture(scope="session")
def bench_jetson_topology() -> dict[str, list[str]]:
    """Bench Jetson topology assumption (per Phase 4 CONTEXT D-01).

    4 modems on USB hub ``2-3.1.{1..4}``. ``usb_paths`` are the modem
    leaf bus-port strings; ``cdc_wdm_paths`` are the corresponding
    ``/dev/cdc-wdmN`` devices (subject to renumbering -- ``usb_path`` is
    the stable key per ADR-0009).
    """
    return {
        "usb_paths": ["2-3.1.1", "2-3.1.2", "2-3.1.3", "2-3.1.4"],
        "cdc_wdm_paths": [
            "/dev/cdc-wdm0",
            "/dev/cdc-wdm1",
            "/dev/cdc-wdm2",
            "/dev/cdc-wdm3",
        ],
    }
