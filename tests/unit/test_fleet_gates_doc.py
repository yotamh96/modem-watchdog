"""Validate docs/FLEET_GATES.md references only metrics from the registry."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from spark_modem.status_reporter.metrics_registry import metric_names

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FLEET_GATES = _REPO_ROOT / "docs" / "FLEET_GATES.md"

_PROMETHEUS_BUILTINS = frozenset({
    "process_start_time_seconds",
    "process_cpu_seconds_total",
    "process_resident_memory_bytes",
    "process_virtual_memory_bytes",
    "process_open_fds",
    "process_max_fds",
})

_HISTOGRAM_SUFFIXES = ("_sum", "_count", "_bucket", "_total", "_created")

_KNOWN_METRICS: frozenset[str] = frozenset(metric_names()) | _PROMETHEUS_BUILTINS


def _strip_histogram_suffix(name: str) -> str:
    for suffix in _HISTOGRAM_SUFFIXES:
        if name.endswith(suffix):
            base = name[: -len(suffix)]
            if base in _KNOWN_METRICS:
                return base
    return name


def _extract_metric_refs(text: str) -> set[str]:
    refs: set[str] = set()
    for block in re.findall(r"```promql\n(.*?)```", text, re.DOTALL):
        for token in re.findall(r"[a-z][a-z0-9_]*(?=[\[{(])", block):
            if token not in {"sum", "rate", "changes", "by"}:
                refs.add(_strip_histogram_suffix(token))
    return refs


@pytest.fixture(scope="module")
def fleet_gates_text() -> str:
    assert _FLEET_GATES.exists(), f"Missing {_FLEET_GATES}"
    return _FLEET_GATES.read_text(encoding="utf-8")


def test_all_metric_refs_exist_in_registry(fleet_gates_text: str) -> None:
    refs = _extract_metric_refs(fleet_gates_text)
    assert refs, "No metric references extracted — parser may be broken"
    unknown = refs - _KNOWN_METRICS
    assert not unknown, f"Unknown metrics in FLEET_GATES.md: {unknown}"


def test_four_gates_defined(fleet_gates_text: str) -> None:
    gate_headings = re.findall(r"^## Gate \d", fleet_gates_text, re.MULTILINE)
    assert len(gate_headings) == 4, f"Expected 4 gates, found {len(gate_headings)}"


def test_each_gate_has_promql_block(fleet_gates_text: str) -> None:
    sections = re.split(r"^## Gate \d", fleet_gates_text, flags=re.MULTILINE)[1:]
    for i, section in enumerate(sections, 1):
        assert "```promql" in section, f"Gate {i} missing PromQL code block"


def test_each_gate_has_threshold(fleet_gates_text: str) -> None:
    sections = re.split(r"^## Gate \d", fleet_gates_text, flags=re.MULTILINE)[1:]
    for i, section in enumerate(sections, 1):
        assert "**Threshold:**" in section, f"Gate {i} missing threshold definition"
