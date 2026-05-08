"""Phase 3 integration test conftest — shared fixtures only.

Issue #6 RESOLVED: this conftest does NOT auto-add the ``linux_only``
marker via ``pytest_collection_modifyitems``. Each integration test
file declares its own ``pytestmark = pytest.mark.linux_only`` at module
level when needed (``test_lifecycle.py`` + ``test_logrotate_create.py``
do; ``test_unit_file_audit.py`` intentionally does NOT — it parses
static files cross-platform).

Auto-marking via ``collection_modifyitems`` was tried earlier and
rejected because it conflicts with files that intentionally run
cross-platform (Plan 03-08's audit gate).
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def integration_run_dir(tmp_path: Path) -> Path:
    """Fresh /run-style scratch dir per test; mirrors production layout."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    return run_dir


@pytest.fixture
def integration_state_root(tmp_path: Path) -> Path:
    """Fresh state/ root per test; mirrors /var/lib/spark-modem-watchdog/."""
    state_root = tmp_path / "state"
    (state_root / "by-usb").mkdir(parents=True)
    return state_root
