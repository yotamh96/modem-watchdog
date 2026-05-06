"""Tests for spark_modem.config.yaml_merge — deep merge for conf.d/*.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from spark_modem.config.yaml_merge import deep_merge, load_yaml_layer


def test_deep_merge_leaf_override() -> None:
    result = deep_merge({"a": 1, "b": {"c": 2}}, {"b": {"c": 3}})
    assert result == {"a": 1, "b": {"c": 3}}


def test_deep_merge_list_replaces_not_extends() -> None:
    result = deep_merge({"a": [1, 2]}, {"a": [3]})
    assert result == {"a": [3]}


def test_deep_merge_type_change_allowed() -> None:
    result = deep_merge({"a": 1}, {"a": {"b": 2}})
    assert result == {"a": {"b": 2}}


def test_deep_merge_does_not_mutate_inputs() -> None:
    base: dict[str, Any] = {"a": {"b": 1}}
    override: dict[str, Any] = {"a": {"c": 2}}
    result = deep_merge(base, override)
    assert result == {"a": {"b": 1, "c": 2}}
    assert base == {"a": {"b": 1}}
    assert override == {"a": {"c": 2}}


def test_load_yaml_layer_lexical_order(tmp_path: Path) -> None:
    (tmp_path / "00-base.yaml").write_text("key: base_value\n", encoding="utf-8")
    (tmp_path / "99-overrides.yaml").write_text("key: override_value\n", encoding="utf-8")
    result = load_yaml_layer(tmp_path)
    assert result == {"key": "override_value"}


def test_load_yaml_layer_ignores_non_yaml_files(tmp_path: Path) -> None:
    (tmp_path / "00-base.yaml").write_text("key: value\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# doc\n", encoding="utf-8")
    (tmp_path / "backup.bak").write_text("key: bad\n", encoding="utf-8")
    result = load_yaml_layer(tmp_path)
    assert result == {"key": "value"}


def test_load_yaml_layer_empty_directory(tmp_path: Path) -> None:
    result = load_yaml_layer(tmp_path)
    assert result == {}


def test_load_yaml_layer_nonexistent_directory(tmp_path: Path) -> None:
    result = load_yaml_layer(tmp_path / "does_not_exist")
    assert result == {}


def test_load_yaml_layer_norway_problem_parses_as_false(tmp_path: Path) -> None:
    """YAML parses NO as bool False — the merger is shape-agnostic; validator catches it."""
    (tmp_path / "00-test.yaml").write_text("country: NO\n", encoding="utf-8")
    result = load_yaml_layer(tmp_path)
    # YAML 1.1 parses bare NO as False; the merger does NOT fix this.
    assert result == {"country": False}


def test_load_yaml_layer_merges_multiple_files(tmp_path: Path) -> None:
    (tmp_path / "00-a.yaml").write_text("a: 1\nb: 2\n", encoding="utf-8")
    (tmp_path / "10-b.yaml").write_text("b: 20\nc: 30\n", encoding="utf-8")
    result = load_yaml_layer(tmp_path)
    assert result == {"a": 1, "b": 20, "c": 30}
