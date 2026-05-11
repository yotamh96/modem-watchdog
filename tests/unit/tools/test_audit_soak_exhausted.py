"""Unit tests for tools/audit_soak_exhausted.py (S-01 #3 detector).

Each test synthesises a tiny events.jsonl in tmp_path and invokes the
audit's ``main()`` argv-style. Tests cover:

  1. 11 consecutive healthy then exhausted with K=10 -> UNEXPLAINED (exit 1)
  2. Exhausted with triggering hardware-failure detail -> EXPLAINED (exit 0)
  3. Only 3 healthy in a row before exhausted -> EXPLAINED (streak below K)
  4. No exhausted transitions in events.jsonl -> exit 0
  5. --decay-k=3 override turns a 4-healthy-then-exhausted into UNEXPLAINED
  6. Anti-pattern check: tool uses `match` on to_state, not `if/elif`

The events.jsonl shape uses a flat ``usb_path`` field (matching
src/spark_modem/wire/events.py StateTransition schema). Per the plan
the triggering hardware-failure detail rides on an optional
``triggering_issue`` field on the StateTransition event; the audit
treats absence of this field as "no hardware-failure attribution".
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


@pytest.fixture
def audit_module():  # type: ignore[no-untyped-def]
    """Import tools/audit_soak_exhausted.py by file path (tools/ is not a package)."""
    spec = importlib.util.spec_from_file_location(
        "audit_soak_exhausted",
        Path(__file__).parents[3] / "tools" / "audit_soak_exhausted.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["audit_soak_exhausted"] = mod
    spec.loader.exec_module(mod)
    return mod


def _st(ts: str, *, usb_path: str, frm: str, to: str, detail: str | None = None) -> dict:
    """Synthesise a StateTransition event with optional triggering hardware detail."""
    ev: dict = {
        "kind": "state_transition",
        "schema_version": 1,
        "ts_iso": ts,
        "usb_path": usb_path,
        "from_state": frm,
        "to_state": to,
        "cause": "test",
        "dry_run": False,
    }
    if detail is not None:
        ev["triggering_issue"] = {"detail": detail}
    return ev


def _write_events(path: Path, events: list[dict]) -> None:
    with path.open("w") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")


def test_eleven_healthy_then_exhausted_is_unexplained(tmp_path: Path, audit_module) -> None:
    """K=10 (default); 11 consecutive healthy is enough to trigger a decay
    reset, but the modem still ended up exhausted -> bug (ADR-0006 regression).
    """
    events_path = tmp_path / "events.jsonl"
    events = []
    for i in range(11):
        events.append(
            _st(
                f"2026-05-11T00:{i:02d}:00+00:00",
                usb_path="2-3.1.1",
                frm="degraded" if i == 0 else "healthy",
                to="healthy",
            )
        )
    events.append(
        _st("2026-05-11T00:20:00+00:00", usb_path="2-3.1.1", frm="healthy", to="exhausted")
    )
    _write_events(events_path, events)
    out = tmp_path / "report.json"
    rc = audit_module.main(["--events", str(events_path), "--out", str(out)])
    assert rc == 1
    report = json.loads(out.read_text())
    assert report["audited_exhausted"] == 1
    assert report["violations"] == 1
    assert report["details"][0]["classification"] == "unexplained"


def test_hardware_failure_exhausted_is_explained(tmp_path: Path, audit_module) -> None:
    events_path = tmp_path / "events.jsonl"
    events = [
        _st(
            "2026-05-11T00:00:00+00:00",
            usb_path="2-3.1.1",
            frm="healthy",
            to="exhausted",
            detail="enumeration_overcurrent",
        ),
    ]
    _write_events(events_path, events)
    out = tmp_path / "report.json"
    rc = audit_module.main(["--events", str(events_path), "--out", str(out)])
    assert rc == 0
    report = json.loads(out.read_text())
    assert report["audited_exhausted"] == 1
    assert report["violations"] == 0
    assert report["details"][0]["classification"] == "explained_hardware"


def test_short_streak_exhausted_is_explained(tmp_path: Path, audit_module) -> None:
    """Only 3 healthy in a row; insufficient to expect a decay; exhausted
    is the expected outcome of the recovery ladder for a stubborn fault.
    """
    events_path = tmp_path / "events.jsonl"
    events = [
        _st("2026-05-11T00:00:00+00:00", usb_path="2-3.1.1", frm="degraded", to="healthy"),
        _st("2026-05-11T00:01:00+00:00", usb_path="2-3.1.1", frm="healthy", to="healthy"),
        _st("2026-05-11T00:02:00+00:00", usb_path="2-3.1.1", frm="healthy", to="healthy"),
        _st("2026-05-11T00:03:00+00:00", usb_path="2-3.1.1", frm="healthy", to="degraded"),
        _st("2026-05-11T00:04:00+00:00", usb_path="2-3.1.1", frm="degraded", to="recovering"),
        _st("2026-05-11T00:05:00+00:00", usb_path="2-3.1.1", frm="recovering", to="exhausted"),
    ]
    _write_events(events_path, events)
    out = tmp_path / "report.json"
    rc = audit_module.main(["--events", str(events_path), "--out", str(out)])
    assert rc == 0
    report = json.loads(out.read_text())
    assert report["violations"] == 0
    assert report["details"][0]["classification"] == "explained_streak_below_k"


def test_no_exhausted_transitions(tmp_path: Path, audit_module) -> None:
    events_path = tmp_path / "events.jsonl"
    events = [
        _st("2026-05-11T00:00:00+00:00", usb_path="2-3.1.1", frm="degraded", to="healthy"),
        _st("2026-05-11T00:01:00+00:00", usb_path="2-3.1.1", frm="healthy", to="healthy"),
    ]
    _write_events(events_path, events)
    out = tmp_path / "report.json"
    rc = audit_module.main(["--events", str(events_path), "--out", str(out)])
    assert rc == 0
    report = json.loads(out.read_text())
    assert report["audited_exhausted"] == 0
    assert report["violations"] == 0


def test_lower_k_via_cli_flag(tmp_path: Path, audit_module) -> None:
    """With K=3, the 4-healthy-then-exhausted pattern now classifies UNEXPLAINED."""
    events_path = tmp_path / "events.jsonl"
    events = [
        _st("2026-05-11T00:00:00+00:00", usb_path="2-3.1.1", frm="degraded", to="healthy"),
        _st("2026-05-11T00:01:00+00:00", usb_path="2-3.1.1", frm="healthy", to="healthy"),
        _st("2026-05-11T00:02:00+00:00", usb_path="2-3.1.1", frm="healthy", to="healthy"),
        _st("2026-05-11T00:03:00+00:00", usb_path="2-3.1.1", frm="healthy", to="healthy"),
        _st("2026-05-11T00:04:00+00:00", usb_path="2-3.1.1", frm="healthy", to="exhausted"),
    ]
    _write_events(events_path, events)
    out = tmp_path / "report.json"
    rc = audit_module.main(
        ["--events", str(events_path), "--decay-k", "3", "--out", str(out)]
    )
    assert rc == 1
    report = json.loads(out.read_text())
    assert report["violations"] == 1


def test_match_pattern_used_not_if_elif() -> None:
    """Anti-pattern check (CLAUDE.md): branching on ModemState uses `match`,
    not `if/elif`. Grep the tool source for the chain
    ``if history[j].to_state == "healthy": ... elif history[j].to_state == "degraded":``.
    """
    text = (Path(__file__).parents[3] / "tools" / "audit_soak_exhausted.py").read_text()
    # The classifier branches on history[j].to_state -- must use `match`.
    assert "match history[j].to_state" in text or "match t.to_state" in text
    # And not an if/elif chain on the state values:
    forbidden_chain = 'if history[j].to_state == "healthy"'
    assert forbidden_chain not in text
