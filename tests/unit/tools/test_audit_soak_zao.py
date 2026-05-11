"""Unit tests for tools/audit_soak_zao.py (S-01 #2 detector).

Each test synthesises a tiny events.jsonl + Zao log pair in tmp_path and
invokes the audit's ``main()`` argv-style. Tests cover:

  1. ActionPlanned on a Zao-ACTIVE line is a violation (exit 1)
  2. ActionPlanned on a Zao-INACTIVE line is clean (exit 0)
  3. No contemporaneous Zao snapshot -> classified as unknown (exit 0)
  4. Mixed violations + clean cycles -> only violations are recorded
  5. Corrupt JSONL line is skipped silently
  6. --since-iso filter excludes events older than the threshold

The events.jsonl shape uses a flat ``usb_path`` field (matching
src/spark_modem/wire/events.py Phase 2 schema). The audit derives
the Zao ``line`` from the trailing dotted suffix of ``usb_path``
(e.g. ``2-3.1.1`` -> line 1) since the production events.jsonl does
NOT carry a ``line`` field on ActionPlanned (only ``usb_path``).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


@pytest.fixture
def audit_module():  # type: ignore[no-untyped-def]
    """Import tools/audit_soak_zao.py by file path (tools/ is not a package)."""
    spec = importlib.util.spec_from_file_location(
        "audit_soak_zao",
        Path(__file__).parents[3] / "tools" / "audit_soak_zao.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["audit_soak_zao"] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_event(path: Path, event: dict) -> None:
    with path.open("a") as fh:
        fh.write(json.dumps(event) + "\n")


def _action_planned(ts: str, *, usb_path: str) -> dict:
    """Synthesise an ActionPlanned event matching wire/events.py shape.

    The flat ``usb_path`` field is the only modem identity carried on the
    wire; the audit derives ``line`` from the trailing segment of
    ``usb_path`` (e.g. ``2-3.1.1`` -> line 1).
    """
    return {
        "kind": "action_planned",
        "schema_version": 1,
        "ts_iso": ts,
        "usb_path": usb_path,
        "action": "soft_reset",
        "reason": "qmi:proxy_died",
        "dry_run": False,
    }


def _write_zao_log(path: Path, blocks: list[tuple[str, dict[int, str]]]) -> None:
    """blocks: [(ts_iso, {line: status, ...}), ...] in chronological order."""
    out_lines = []
    for ts, line_statuses in blocks:
        for ln, st in line_statuses.items():
            out_lines.append(f"{ts} ZaoInfraCtrl RASCOW_STAT line={ln} status={st}")
    path.write_text("\n".join(out_lines) + "\n")


def test_zao_active_action_planned_is_violation(tmp_path: Path, audit_module) -> None:
    events = tmp_path / "events.jsonl"
    _write_event(events, _action_planned("2026-05-11T00:00:00+00:00", usb_path="2-3.1.1"))
    zao_log = tmp_path / "zao.log"
    _write_zao_log(zao_log, [("2026-05-11T00:00:00+00:00", {1: "active", 2: "inactive"})])
    out = tmp_path / "report.json"
    rc = audit_module.main(
        ["--events", str(events), "--zao-log", str(zao_log), "--out", str(out)]
    )
    assert rc == 1
    report = json.loads(out.read_text())
    assert report["violations"] == 1
    detail = report["details"][0]
    assert detail["line"] == 1
    assert detail["usb_path"] == "2-3.1.1"
    assert detail["classification"] == "violation"


def test_zao_inactive_action_planned_is_clean(tmp_path: Path, audit_module) -> None:
    events = tmp_path / "events.jsonl"
    _write_event(events, _action_planned("2026-05-11T00:00:00+00:00", usb_path="2-3.1.1"))
    zao_log = tmp_path / "zao.log"
    _write_zao_log(zao_log, [("2026-05-11T00:00:00+00:00", {1: "inactive", 2: "active"})])
    out = tmp_path / "report.json"
    rc = audit_module.main(
        ["--events", str(events), "--zao-log", str(zao_log), "--out", str(out)]
    )
    assert rc == 0
    report = json.loads(out.read_text())
    assert report["violations"] == 0


def test_no_contemporaneous_zao_block(tmp_path: Path, audit_module) -> None:
    # Event at T=0; Zao log first block is at T=+10s (no snapshot before the event).
    events = tmp_path / "events.jsonl"
    _write_event(events, _action_planned("2026-05-11T00:00:00+00:00", usb_path="2-3.1.1"))
    zao_log = tmp_path / "zao.log"
    _write_zao_log(zao_log, [("2026-05-11T00:00:10+00:00", {1: "active"})])
    out = tmp_path / "report.json"
    rc = audit_module.main(
        ["--events", str(events), "--zao-log", str(zao_log), "--out", str(out)]
    )
    assert rc == 0  # no violation; classified unknown
    report = json.loads(out.read_text())
    assert report["violations"] == 0
    assert report["unknown_no_zao_snapshot"] == 1
    assert report["details"][0]["classification"] == "no_zao_snapshot_for_cycle"


def test_mixed_violations_and_clean(tmp_path: Path, audit_module) -> None:
    events = tmp_path / "events.jsonl"
    _write_event(events, _action_planned("2026-05-11T00:00:00+00:00", usb_path="2-3.1.1"))  # violation
    _write_event(events, _action_planned("2026-05-11T00:01:00+00:00", usb_path="2-3.1.2"))  # clean
    zao_log = tmp_path / "zao.log"
    _write_zao_log(
        zao_log,
        [
            ("2026-05-11T00:00:00+00:00", {1: "active", 2: "inactive"}),
            ("2026-05-11T00:01:00+00:00", {1: "active", 2: "inactive"}),
        ],
    )
    out = tmp_path / "report.json"
    rc = audit_module.main(
        ["--events", str(events), "--zao-log", str(zao_log), "--out", str(out)]
    )
    assert rc == 1
    report = json.loads(out.read_text())
    assert report["violations"] == 1
    violation_lines = [
        d["line"] for d in report["details"] if d.get("classification") == "violation"
    ]
    assert violation_lines == [1]


def test_corrupt_jsonl_line_skipped_silently(tmp_path: Path, audit_module) -> None:
    events = tmp_path / "events.jsonl"
    # First line is malformed JSON; second is a valid action_planned on an
    # INACTIVE Zao line (i.e. NOT a violation). The malformed line must be
    # skipped without crashing or producing a phantom violation.
    events.write_text(
        "{this is not json}\n"
        + json.dumps(_action_planned("2026-05-11T00:00:00+00:00", usb_path="2-3.1.1"))
        + "\n"
    )
    zao_log = tmp_path / "zao.log"
    _write_zao_log(zao_log, [("2026-05-11T00:00:00+00:00", {1: "inactive"})])
    out = tmp_path / "report.json"
    rc = audit_module.main(
        ["--events", str(events), "--zao-log", str(zao_log), "--out", str(out)]
    )
    assert rc == 0
    report = json.loads(out.read_text())
    assert report["violations"] == 0


def test_since_iso_filters_events(tmp_path: Path, audit_module) -> None:
    events = tmp_path / "events.jsonl"
    _write_event(
        events, _action_planned("2026-05-10T00:00:00+00:00", usb_path="2-3.1.1")
    )  # old, ignored
    _write_event(
        events, _action_planned("2026-05-11T00:00:00+00:00", usb_path="2-3.1.1")
    )  # in window, violation
    zao_log = tmp_path / "zao.log"
    _write_zao_log(
        zao_log,
        [
            ("2026-05-10T00:00:00+00:00", {1: "active"}),
            ("2026-05-11T00:00:00+00:00", {1: "active"}),
        ],
    )
    out = tmp_path / "report.json"
    rc = audit_module.main(
        [
            "--events",
            str(events),
            "--zao-log",
            str(zao_log),
            "--since-iso",
            "2026-05-11T00:00:00+00:00",
            "--out",
            str(out),
        ]
    )
    assert rc == 1
    report = json.loads(out.read_text())
    assert report["violations"] == 1


def test_zao_log_size_cap_raises(tmp_path: Path, audit_module, monkeypatch) -> None:
    """Phase 5 WR-01: a Zao log exceeding ``_MAX_ZAO_LOG_BYTES`` is rejected.

    The audit's read path is unbounded by default; an accidentally
    uncompressed or pathological multi-GiB log would consume RAM. The
    parser now stats the file up-front and raises a ``RuntimeError``
    with a clear message above the cap. Validated by monkey-patching
    the cap to a tiny value so the test does not need to materialise
    a multi-GiB file.
    """
    zao_log = tmp_path / "zao.log"
    _write_zao_log(zao_log, [("2026-05-11T00:00:00+00:00", {1: "active"})])
    # Shrink the cap so this 1-block file exceeds it.
    monkeypatch.setattr(audit_module, "_MAX_ZAO_LOG_BYTES", 4)
    with pytest.raises(RuntimeError, match="Zao log"):
        audit_module._parse_zao_blocks(zao_log)


def test_zao_log_streamed_not_fully_read(tmp_path: Path, audit_module) -> None:
    """Phase 5 WR-01: ``_parse_zao_blocks`` reads via streaming (line-by-line).

    Smoke-tests that ``_parse_zao_blocks`` produces the same output for
    a moderately large synthetic log as the on-disk per-line shape would,
    confirming the streaming refactor preserves the parser contract.
    """
    zao_log = tmp_path / "zao.log"
    # Build a log with 5 distinct blocks, each with 4 line statuses.
    blocks_input = [
        (
            f"2026-05-11T00:0{i}:00+00:00",
            {1: "active" if i % 2 == 0 else "inactive", 2: "inactive", 3: "active", 4: "inactive"},
        )
        for i in range(5)
    ]
    _write_zao_log(zao_log, blocks_input)
    blocks = audit_module._parse_zao_blocks(zao_log)
    assert len(blocks) == 5
    # Block 0 (i=0): line 1 active, line 3 active -> {1, 3}.
    assert blocks[0].active_lines == frozenset({1, 3})
    # Block 1 (i=1): line 1 inactive, line 3 active -> {3}.
    assert blocks[1].active_lines == frozenset({3})


def test_zao_log_missing_returns_empty(tmp_path: Path, audit_module) -> None:
    """Missing Zao log path returns ``[]`` (existing contract preserved)."""
    missing = tmp_path / "no_such_log.log"
    assert audit_module._parse_zao_blocks(missing) == []
