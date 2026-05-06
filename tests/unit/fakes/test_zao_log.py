"""Tests for tests.fakes.zao_log.FixtureZaoTailer."""

from __future__ import annotations

from tests.fakes.zao_log import FixtureZaoTailer


def test_is_line_active_only_when_in_active_set() -> None:
    zao = FixtureZaoTailer()
    # Default: nothing active.
    assert zao.is_line_active(1) is False
    assert zao.is_line_active(2) is False

    zao.set_active({1, 2})
    assert zao.is_line_active(1) is True
    assert zao.is_line_active(2) is True
    assert zao.is_line_active(3) is False
    assert zao.is_line_active(4) is False


def test_constructor_seeds_active_set() -> None:
    zao = FixtureZaoTailer(active_lines={3})
    assert zao.is_line_active(3) is True
    assert zao.is_line_active(1) is False


def test_set_active_replaces_not_unions() -> None:
    zao = FixtureZaoTailer(active_lines={1})
    zao.set_active({2})
    assert zao.is_line_active(1) is False
    assert zao.is_line_active(2) is True
