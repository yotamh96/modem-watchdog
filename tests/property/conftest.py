"""Property-test shared fixtures.

This tier uses ``hypothesis`` for property-based testing. Per Phase 4 plan
04-07 (PATTERNS correction #6 -- net-new directory), the conftest lives
alongside the property tests so ``make_ctx``-style helpers can be shared
across hypothesis-driven tests without re-importing from tests/unit/.

Tests in this directory MAY be slow (hypothesis runs many examples); they
run as part of the regular ``pytest -m "unit or integration"`` suite. The
top-level ``tests/conftest.py`` auto-marks tests/unit/ + tests/integration/
+ tests/hil/ by directory; for tests/property/ we apply the ``unit`` marker
locally here (per PATTERNS correction #6 "or use existing unit").
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Auto-mark every property test with ``unit`` so the CI filter
    ``pytest -m "unit or integration"`` picks it up without requiring
    each test author to decorate explicitly.
    """
    del config
    for item in items:
        item.add_marker("unit")


@pytest.fixture
def hypothesis_seed() -> int:
    """Deterministic seed for property-test reproduction."""
    return 42
