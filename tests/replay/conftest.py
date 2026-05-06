"""Replay-suite fixture loader + verdict accumulator (R-03).

The ``pytest_sessionfinish`` hook computes the fault-cycle agreement
rate from the verdicts the per-fixture tests recorded and HARD FAILS
the build at <95%.  It also writes ``artifacts/replay-summary.json``
with the per-fixture breakdown for CI archiving.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_DIR = Path("tests/fixtures/replay")


_ACCUMULATED_VERDICTS: list[dict[str, object]] = []


def _all_fixtures() -> list[Path]:
    """Return every ``*.json`` under tests/fixtures/replay, sorted."""
    if not FIXTURE_DIR.is_dir():
        return []
    # Skip the restart_mid_streak fixtures here -- they have a dedicated
    # test (test_streak_restart.py) that handles the round-trip pre/post
    # pair, not the per-cycle classifier.
    return sorted(p for p in FIXTURE_DIR.rglob("*.json") if "restart_mid_streak" not in p.parts)


@pytest.fixture(scope="session")
def fixture_paths() -> list[Path]:
    """Session-scoped list of every replay fixture on disk."""
    return _all_fixtures()


def fixture_paths_for_parametrize() -> list[Path]:
    """Module-level helper for ``@pytest.mark.parametrize``.

    Cannot be a pytest fixture because parametrize args are evaluated
    at collection time, before fixture resolution.
    """
    return _all_fixtures()


def record_verdict(scenario: str, fault_cycle: bool, classification: str) -> None:
    """Per-fixture test calls this with its verdict.

    Verdict values: ``agree | safer | less-safe | different-issue | both-skip``.
    The session-finish hook aggregates these into the R-03 ≥95% gate.
    """
    _ACCUMULATED_VERDICTS.append(
        {
            "scenario": scenario,
            "fault_cycle": fault_cycle,
            "classification": classification,
        },
    )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """R-03 hard fail at <95% fault-cycle agreement.

    Writes ``artifacts/replay-summary.json`` with the verdict breakdown
    so CI can archive the audit trail (T-02-10-03: gitignored, no PII).
    Sets ``session.exitstatus`` to non-zero on gate breach.
    """
    del exitstatus  # we override session.exitstatus directly below
    if not _ACCUMULATED_VERDICTS:
        return
    fault_verdicts = [v for v in _ACCUMULATED_VERDICTS if v["fault_cycle"]]
    if not fault_verdicts:
        return

    agreed = sum(
        1 for v in fault_verdicts if v["classification"] in ("agree", "safer", "both-skip")
    )
    rate = agreed / len(fault_verdicts)

    artifacts_dir = Path("artifacts")
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "total_fixtures": len(_ACCUMULATED_VERDICTS),
        "fault_cycles": len(fault_verdicts),
        "agreed": agreed,
        "agreement_rate": rate,
        "verdicts": _ACCUMULATED_VERDICTS,
    }
    (artifacts_dir / "replay-summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    if rate < 0.95:
        session.exitstatus = 1
        # Print so the failure is visible in CI logs even if no test
        # individually failed.
        print(
            f"\nREPLAY GATE FAILED: fault-cycle agreement {rate:.1%} < 95% (R-03)",
        )
