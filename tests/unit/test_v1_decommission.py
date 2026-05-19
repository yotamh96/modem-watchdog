"""Validate v1 decommission artifacts produced by slice S12."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def archive_readme() -> str:
    p = _REPO_ROOT / "archive" / "v1" / "README.md"
    assert p.exists(), f"Missing {p}"
    return p.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def purge_checklist() -> str:
    p = _REPO_ROOT / "docs" / "V1_PURGE_CHECKLIST.md"
    assert p.exists(), f"Missing {p}"
    return p.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def postmortem_template() -> str:
    p = _REPO_ROOT / "docs" / "MIGRATION_POSTMORTEM_TEMPLATE.md"
    assert p.exists(), f"Missing {p}"
    return p.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def adr_readme() -> str:
    p = _REPO_ROOT / "docs" / "adr" / "README.md"
    assert p.exists(), f"Missing {p}"
    return p.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def docs_readme() -> str:
    p = _REPO_ROOT / "docs" / "README.md"
    assert p.exists(), f"Missing {p}"
    return p.read_text(encoding="utf-8")


def test_archive_readme_exists(archive_readme: str) -> None:
    assert "ADR-0014" in archive_readme
    for script in [
        "diag.sh",
        "recovery.sh",
        "auto_profile.sh",
        "zao_reset_line.sh",
        "spark-modem-watchdog.sh",
    ]:
        assert script in archive_readme, f"Missing v1 script name: {script}"
    assert "2026-05-11" in archive_readme, "Missing retirement date"


def test_purge_checklist_exists(purge_checklist: str) -> None:
    assert "/usr/local/bin/" in purge_checklist
    assert "Sign-off" in purge_checklist or "sign-off" in purge_checklist.lower()


def test_postmortem_template_exists(postmortem_template: str) -> None:
    assert "MTTR" in postmortem_template
    assert "Lessons" in postmortem_template
    assert "Sign-off" in postmortem_template or "Sign-Off" in postmortem_template


def test_adr_readme_has_0014(adr_readme: str) -> None:
    assert "ADR-0014" in adr_readme
    assert "0014-v1-retired-pivot" in adr_readme


def test_docs_readme_no_stale_v1(docs_readme: str) -> None:
    assert "scripts in the parent directory" not in docs_readme
    assert "archive/v1" in docs_readme


def test_docs_readme_has_all_adrs(docs_readme: str) -> None:
    for n in range(8, 15):
        tag = f"ADR-{n:04d}"
        assert tag in docs_readme, f"Missing {tag} in docs/README.md"


def test_no_v1_as_active_in_docs() -> None:
    v1_active_patterns = [
        r"v1\s+currently",
        r"scripts\s+in\s+the\s+parent\s+directory",
        r"v1\s+works\s+in\s+production",
        r"v1\s+is\s+deployed",
    ]
    docs_dir = _REPO_ROOT / "docs"
    violations: list[str] = []
    for md_file in sorted(docs_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        for pattern in v1_active_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                violations.append(f"{md_file.name}: {matches!r} (pattern: {pattern})")
    assert not violations, "Stale v1-as-active references found:\n" + "\n".join(violations)
