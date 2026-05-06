"""Auto-apply unit/integration/hil markers based on test file location.

Tests are organized by directory (tests/unit/, tests/integration/, tests/hil/)
rather than by individual @pytest.mark decorators. This hook lets the CI
filter `-m "unit or integration"` and `-m "not hil"` work without requiring
every test author to remember to decorate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

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
