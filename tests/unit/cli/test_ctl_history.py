"""Tests for spark_modem.cli.ctl.history — events.jsonl reader + filter."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from spark_modem.cli.ctl.history import (
    filter_events,
    parse_since,
    read_events_with_rotated_siblings,
)
from spark_modem.wire.enums import ActionKind, ActionResult
from spark_modem.wire.events import (
    ActionExecuted,
    ActionPlanned,
    DaemonStarted,
)


def test_parse_since_h_m_s() -> None:
    assert parse_since("2h") == 7200.0
    assert parse_since("30m") == 1800.0
    assert parse_since("300s") == 300.0
    assert parse_since(" 1H ") == 3600.0  # whitespace + uppercase tolerated


def test_parse_since_invalid() -> None:
    with pytest.raises(ValueError, match="invalid --since"):
        parse_since("2 hours")
    with pytest.raises(ValueError, match="invalid --since"):
        parse_since("forever")
    with pytest.raises(ValueError, match="invalid --since"):
        parse_since("h2")


def _make_action_planned(
    *, ts_iso: str, usb_path: str
) -> ActionPlanned:
    return ActionPlanned(
        ts_iso=ts_iso,
        usb_path=usb_path,
        action=ActionKind.SET_APN,
        reason="dispatcher:set_apn",
    )


def test_filter_events_by_usb_path() -> None:
    events = [
        _make_action_planned(
            ts_iso="2026-05-06T00:00:00+00:00", usb_path="2-3.1.1"
        ),
        _make_action_planned(
            ts_iso="2026-05-06T00:00:01+00:00", usb_path="2-3.1.2"
        ),
        _make_action_planned(
            ts_iso="2026-05-06T00:00:02+00:00", usb_path="2-3.1.1"
        ),
    ]
    out = filter_events(events, modem="2-3.1.1", since_seconds=None)
    assert len(out) == 2
    assert all(getattr(e, "usb_path", None) == "2-3.1.1" for e in out)


def test_filter_events_by_since_seconds() -> None:
    """Events with ts older than `since_seconds` are dropped."""
    now = datetime.now(UTC)
    recent_iso = (now - timedelta(seconds=30)).isoformat()
    old_iso = (now - timedelta(hours=2)).isoformat()
    events = [
        _make_action_planned(ts_iso=recent_iso, usb_path="2-3.1.1"),
        _make_action_planned(ts_iso=old_iso, usb_path="2-3.1.1"),
    ]
    # Last 1h only.
    out = filter_events(events, modem=None, since_seconds=3600.0)
    assert len(out) == 1
    assert out[0].ts_iso == recent_iso


def test_filter_events_excludes_no_modem_events_when_filtering_by_modem() -> None:
    """DaemonStarted has no usb_path → filtered out when --modem is set."""
    events: list[ActionPlanned | DaemonStarted] = [
        _make_action_planned(
            ts_iso="2026-05-06T00:00:00+00:00", usb_path="2-3.1.1"
        ),
        DaemonStarted(
            ts_iso="2026-05-06T00:00:01+00:00",
            version="2.0.0",
            bundled_python_version="3.12",
        ),
    ]
    out = filter_events(events, modem="2-3.1.1", since_seconds=None)
    assert len(out) == 1
    assert getattr(out[0], "usb_path", None) == "2-3.1.1"


def test_read_events_handles_missing_file(tmp_path: Path) -> None:
    """Missing primary path produces empty iterator (no rotated siblings either)."""
    out = list(read_events_with_rotated_siblings(tmp_path / "events.jsonl"))
    assert out == []


def test_read_events_handles_corrupt_lines_gracefully(tmp_path: Path) -> None:
    """Corrupt lines are skipped, not raised."""
    primary = tmp_path / "events.jsonl"
    good = ActionPlanned(
        ts_iso="2026-05-06T00:00:00+00:00",
        usb_path="2-3.1.1",
        action=ActionKind.SET_APN,
        reason="r",
    )
    lines = [
        good.model_dump_json(by_alias=True),
        "{not valid json",
        "",  # empty line
        good.model_dump_json(by_alias=True),
    ]
    primary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = list(read_events_with_rotated_siblings(primary))
    assert len(out) == 2  # corrupt line skipped


def test_read_events_with_rotated_siblings_handles_gzip(tmp_path: Path) -> None:
    """Both events.jsonl and events.jsonl.1.gz are read; output is oldest-first."""
    primary = tmp_path / "events.jsonl"
    rotated_gz = tmp_path / "events.jsonl.1.gz"

    new = ActionPlanned(
        ts_iso="2026-05-06T01:00:00+00:00",
        usb_path="2-3.1.2",
        action=ActionKind.SET_APN,
        reason="new",
    )
    old = ActionExecuted(
        ts_iso="2026-05-06T00:00:00+00:00",
        usb_path="2-3.1.1",
        action=ActionKind.SET_APN,
        result=ActionResult.SUCCESS,
        duration_seconds=0.1,
    )

    primary.write_text(new.model_dump_json(by_alias=True) + "\n", encoding="utf-8")
    with gzip.open(rotated_gz, "wb") as fh:
        fh.write(old.model_dump_json(by_alias=True).encode("utf-8") + b"\n")

    out = list(read_events_with_rotated_siblings(primary))
    assert len(out) == 2
    # Oldest-first: rotated .gz comes first.
    assert out[0].ts_iso == "2026-05-06T00:00:00+00:00"
    assert out[1].ts_iso == "2026-05-06T01:00:00+00:00"


def test_read_events_supports_plain_rotated_sibling(tmp_path: Path) -> None:
    """events.jsonl.1 (uncompressed rotation) is also read."""
    primary = tmp_path / "events.jsonl"
    rotated = tmp_path / "events.jsonl.1"
    a = ActionPlanned(
        ts_iso="2026-05-06T00:00:00+00:00",
        usb_path="2-3.1.1",
        action=ActionKind.SET_APN,
        reason="a",
    )
    b = ActionPlanned(
        ts_iso="2026-05-06T01:00:00+00:00",
        usb_path="2-3.1.2",
        action=ActionKind.SET_APN,
        reason="b",
    )
    primary.write_text(b.model_dump_json(by_alias=True) + "\n", encoding="utf-8")
    rotated.write_text(a.model_dump_json(by_alias=True) + "\n", encoding="utf-8")
    out = list(read_events_with_rotated_siblings(primary))
    assert len(out) == 2


def test_read_events_round_trips_through_jsonl(tmp_path: Path) -> None:
    """JSON-decoded output is re-serializable as a dict."""
    primary = tmp_path / "events.jsonl"
    a = ActionPlanned(
        ts_iso="2026-05-06T00:00:00+00:00",
        usb_path="2-3.1.1",
        action=ActionKind.SET_APN,
        reason="r",
    )
    primary.write_text(a.model_dump_json(by_alias=True) + "\n", encoding="utf-8")
    out = list(read_events_with_rotated_siblings(primary))
    assert len(out) == 1
    d = out[0].model_dump(mode="json")
    assert d["kind"] == "action_planned"
    assert json.loads(json.dumps(d))  # round-trips
