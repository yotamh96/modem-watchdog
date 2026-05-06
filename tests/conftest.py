"""Auto-apply unit/integration/hil markers based on test file location.

Tests are organized by directory (tests/unit/, tests/integration/, tests/hil/)
rather than by individual @pytest.mark decorators. This hook lets the CI
filter `-m "unit or integration"` and `-m "not hil"` work without requiring
every test author to remember to decorate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from spark_modem.config.settings import Settings

_MARKER_DIRS = ("unit", "integration", "hil")


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    del config
    for item in items:
        parts = Path(str(item.fspath)).parts
        for marker in _MARKER_DIRS:
            if marker in parts:
                item.add_marker(marker)
                break


@pytest.fixture
def settings() -> Settings:
    """Default Settings instance for tests.

    Topology fields use /tmp paths (POSIX-only at runtime; tests that
    actually touch the filesystem use tmp_path overrides).  Recovery
    defaults (backoff_seconds=300, ladder_min_interval_seconds=90,
    healthy_streak_decay_k=10) are inherited from the model.
    """
    return Settings(
        state_root="/tmp/test-state",
        run_dir="/tmp/test-run",
        events_log_path="/tmp/events.jsonl",
        metrics_socket_path="/tmp/metrics.sock",
        carriers_yaml_path="/tmp/carriers.yaml",
    )
