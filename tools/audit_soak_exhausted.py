"""Audit a soak window for S-01 #3 violations.

S-01 #3 (Phase 5 CONTEXT.md): Zero unexplained ``exhausted`` state
transitions (M4: zero Exhausted states caused by counter accumulation).

Every state_transition event with to_state='exhausted' is classified
as EXPLAINED or UNEXPLAINED by replaying the decay heuristic from
ADR-0006 / RECOVERY_SPEC §8 against the events.jsonl history.

A transition is UNEXPLAINED when the modem had >= K consecutive
``to_state='healthy'`` events immediately preceding the exhausted
transition (= regression of ADR-0006 amendment; counters should have
decayed; M4 violation).

A transition is EXPLAINED when:
  - the triggering_issue.detail attached to the StateTransition shows
    a hardware-failure variant (ENUMERATION_OVERCURRENT,
    ENUMERATION_ADDRESS_FAIL, USB_OVERCURRENT, THERMAL_THROTTLE,
    TEGRA_HUB_PSU_DROOP); OR
  - the healthy streak in the lookback was less than K (insufficient
    to expect a decay; exhausted is the expected ladder outcome for a
    stubborn fault).

## Subprocess discipline

This is a ``tools/`` script (NOT under ``src/spark_modem/``); SP-04 lint
scope excludes anything outside ``src/`` (see
``scripts/lint_no_subprocess.sh:11``). Direct ``subprocess.run`` is
acceptable here; this script does not need it.

## Exit codes

- ``0`` -- no unexplained transitions / clean soak window.
- ``1`` -- unexplained transitions found.
- ``2`` -- operational error (bad input path, etc.).
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

# NOTE: tools/ is SP-04-exempt and audit-only. We deliberately do NOT
# import ``read_events_with_rotated_siblings`` from
# ``spark_modem.cli.ctl.history`` because it yields validated pydantic
# ``Event`` objects, and the audit operates over raw dicts so the
# Event union can evolve without breaking the audit. We read
# events.jsonl directly as JSONL. See audit_soak_zao.py for the
# canonical helper.


def _read_events_as_raw_dicts(events_log: Path) -> Iterator[dict[str, object]]:
    """Yield events from events.jsonl + rotated siblings as raw dicts.

    See ``audit_soak_zao._read_events_as_raw_dicts`` for the design
    rationale. Implementation is duplicated rather than shared because
    tools/ scripts do not import each other (no shared ``tools/_lib.py``
    in Phase 5; deferred as a refactor for Phase 6+).
    """
    candidates: list[Path] = [events_log]
    for i in range(1, 10):
        sib = events_log.with_suffix(f".jsonl.{i}")
        if sib.is_file():
            candidates.append(sib)
        sibgz = events_log.with_suffix(f".jsonl.{i}.gz")
        if sibgz.is_file():
            candidates.append(sibgz)

    for path in reversed(candidates):
        if not path.is_file():
            continue
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rb") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    yield obj


# Default decay threshold K from ADR-0006. Best-effort import from the
# production policy module so the audit stays in sync if the constant
# is later promoted to a module-level Final. The current Phase 1-4
# codebase carries K as ``Settings.healthy_streak_decay_k`` (default
# 10); a future refactor that adds ``_DECAY_K_DEFAULT`` to
# ``spark_modem.policy.engine`` will be picked up here automatically.
# Until then, the import fails cleanly and we fall back to the literal.
def _resolve_decay_k_default() -> int:
    """Best-effort lookup of the production decay constant.

    Tries (in order):
      1. ``spark_modem.policy.engine._DECAY_K_DEFAULT`` (forward-compat;
         not currently present in Phase 1-4 codebase).
      2. ``spark_modem.config.settings.Settings`` model field default
         for ``healthy_streak_decay_k`` (the production value).
      3. Hardcoded literal ``10`` (matches ADR-0006 amendment default).

    Uses ``getattr`` rather than a bare ``from ... import`` so the
    audit stays import-clean against the current production module
    shape and tracks future renames.
    """
    try:
        from spark_modem.policy import engine as _engine  # noqa: PLC0415

        k = getattr(_engine, "_DECAY_K_DEFAULT", None)
        if isinstance(k, int):
            return k
    except ImportError:
        pass
    try:
        from spark_modem.config.settings import Settings  # noqa: PLC0415

        default = Settings.model_fields["healthy_streak_decay_k"].default
        if isinstance(default, int):
            return default
    except (ImportError, KeyError, AttributeError):
        pass
    return 10


_K_DEFAULT: int = _resolve_decay_k_default()


# IssueDetail values that legitimize an exhausted state (hardware failure).
# Source: src/spark_modem/wire/enums.py IssueDetail enum (Phase 1/3) +
# RESEARCH Q6. Conservative -- a NEW IssueDetail variant added in a
# future plan will be classified UNEXPLAINED by this audit (operator
# disposition via F-04 audit trail; see threat T-05-05-05 disposition
# in the plan threat_model).
_HARDWARE_FAILURE_DETAILS: frozenset[str] = frozenset(
    {
        "enumeration_overcurrent",
        "enumeration_address_fail",
        "usb_overcurrent",
        "thermal_throttle",
        "tegra_hub_psu_droop",
    }
)


@dataclass
class _Transition:
    ts_iso: str
    from_state: str
    to_state: str
    cause: str | None
    triggering_detail: str | None


@dataclass
class _AuditResult:
    audited_exhausted: int = 0
    violations: int = 0
    details: list[dict[str, object]] = field(default_factory=list)


def _parse_events(events_path: Path, since_iso: str | None) -> dict[str, list[_Transition]]:
    """Group state_transition events by modem usb_path; sort each list by ts."""
    per_modem: dict[str, list[_Transition]] = defaultdict(list)
    for raw in _read_events_as_raw_dicts(events_path):
        if raw.get("kind") != "state_transition":
            continue
        ts = raw.get("ts_iso")
        if not isinstance(ts, str):
            continue
        if since_iso is not None and ts < since_iso:
            continue
        usb_path = raw.get("usb_path")
        if not isinstance(usb_path, str):
            continue
        triggering = raw.get("triggering_issue")
        triggering_detail: str | None = None
        if isinstance(triggering, dict):
            detail_val = triggering.get("detail")
            if isinstance(detail_val, str):
                triggering_detail = detail_val
        from_state = raw.get("from_state", "unknown")
        to_state = raw.get("to_state", "unknown")
        cause_val = raw.get("cause")
        per_modem[usb_path].append(
            _Transition(
                ts_iso=ts,
                from_state=from_state if isinstance(from_state, str) else "unknown",
                to_state=to_state if isinstance(to_state, str) else "unknown",
                cause=cause_val if isinstance(cause_val, str) else None,
                triggering_detail=triggering_detail,
            )
        )
    for history in per_modem.values():
        history.sort(key=lambda t: t.ts_iso)
    return per_modem


def _classify_exhausted(
    history: list[_Transition], idx: int, k: int
) -> tuple[str, dict[str, object]]:
    """Classify the transition at ``history[idx]`` (to_state='exhausted').

    Returns ``(classification, detail_dict)``.
    ``classification`` is one of:
      - ``"explained_hardware"``
      - ``"explained_streak_below_k"``
      - ``"unexplained"``
    """
    triggering = history[idx].triggering_detail
    if triggering is not None and triggering in _HARDWARE_FAILURE_DETAILS:
        return (
            "explained_hardware",
            {
                "ts_iso": history[idx].ts_iso,
                "classification": "explained_hardware",
                "triggering_detail": triggering,
            },
        )

    # Walk backward, count consecutive transitions whose to_state is "healthy".
    # Using `match` per CLAUDE.md anti-pattern catalogue (no if/elif on
    # ModemState string values; see policy/transitions.py:69-100 precedent).
    healthy_streak = 0
    for j in range(idx - 1, -1, -1):
        match history[j].to_state:
            case "healthy":
                healthy_streak += 1
            case _:
                break

    if healthy_streak >= k:
        # >= K consecutive healthy. Counters should have decayed; this is a bug.
        return (
            "unexplained",
            {
                "ts_iso": history[idx].ts_iso,
                "classification": "unexplained",
                "healthy_streak_in_window": healthy_streak,
                "K": k,
            },
        )
    return (
        "explained_streak_below_k",
        {
            "ts_iso": history[idx].ts_iso,
            "classification": "explained_streak_below_k",
            "healthy_streak_in_window": healthy_streak,
            "K": k,
        },
    )


def _audit(events_path: Path, since_iso: str | None, k: int) -> _AuditResult:
    result = _AuditResult()
    per_modem = _parse_events(events_path, since_iso)
    for usb_path, history in per_modem.items():
        for idx, t in enumerate(history):
            if t.to_state != "exhausted":
                continue
            result.audited_exhausted += 1
            classification, detail = _classify_exhausted(history, idx, k)
            detail["usb_path"] = usb_path
            result.details.append(detail)
            if classification == "unexplained":
                result.violations += 1
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Audit a soak window for S-01 #3 violations (unexplained Exhausted transitions)."
        ),
    )
    parser.add_argument(
        "--events",
        type=Path,
        required=True,
        help="Path to events.jsonl (rotated siblings auto-discovered)",
    )
    parser.add_argument(
        "--since-iso",
        type=str,
        default=None,
        help="Optional ISO-8601 lower bound; events older are skipped",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output JSON report path",
    )
    parser.add_argument(
        "--decay-k",
        type=int,
        default=_K_DEFAULT,
        help=f"Decay threshold K (default: {_K_DEFAULT})",
    )
    args = parser.parse_args(argv)

    if not args.events.exists():
        print(
            f"audit_soak_exhausted: events path not found: {args.events}",
            file=sys.stderr,
        )
        return 2

    result = _audit(args.events, args.since_iso, args.decay_k)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(
            {
                "audited_exhausted": result.audited_exhausted,
                "violations": result.violations,
                "details": result.details,
                "K": args.decay_k,
            },
            indent=2,
        )
        + "\n"
    )

    return 1 if result.violations > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
