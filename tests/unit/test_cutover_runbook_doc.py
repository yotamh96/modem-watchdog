"""Validate docs/CUTOVER_RUNBOOK.md covers all required sections."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNBOOK = _REPO_ROOT / "docs" / "CUTOVER_RUNBOOK.md"


@pytest.fixture(scope="module")
def runbook_text() -> str:
    assert _RUNBOOK.exists(), f"Missing {_RUNBOOK}"
    return _RUNBOOK.read_text(encoding="utf-8")


def test_all_seven_steps_present(runbook_text: str) -> None:
    for step_num in range(1, 8):
        assert re.search(
            rf"^## Step {step_num}\b", runbook_text, re.MULTILINE
        ), f"Missing Step {step_num} heading"


def test_no_v1_rollback_references(runbook_text: str) -> None:
    v1_rollback_patterns = [
        r"rollback\s+to\s+v1",
        r"v1\s+\.deb",
        r"v1\s+package",
        r"spark-modem-watchdog-v1",
        r"downgrade\s+to\s+v1",
    ]
    for pattern in v1_rollback_patterns:
        matches = re.findall(pattern, runbook_text, re.IGNORECASE)
        assert not matches, (
            f"Stale v1 rollback reference found: {matches!r} (pattern: {pattern})"
        )


def test_rollback_is_v2_to_v2_prev(runbook_text: str) -> None:
    assert "previous v2" in runbook_text.lower() or "previous v2" in runbook_text, (
        "Rollback section must reference v2→v2-prev strategy"
    )


def test_references_adr_0014(runbook_text: str) -> None:
    assert "ADR-0014" in runbook_text, "Must reference ADR-0014"


def test_references_validate_cutover(runbook_text: str) -> None:
    assert "validate_cutover" in runbook_text, (
        "Must reference validate_cutover.py from T04"
    )


def test_prerequisites_section(runbook_text: str) -> None:
    assert "## Prerequisites" in runbook_text, "Missing Prerequisites section"


def test_troubleshooting_section(runbook_text: str) -> None:
    assert "## Troubleshooting" in runbook_text, "Missing Troubleshooting section"


def test_escalation_placeholder(runbook_text: str) -> None:
    assert "{{ESCALATION_CONTACT}}" in runbook_text or "escalation" in runbook_text.lower(), (
        "Must include escalation contact placeholder or reference"
    )
