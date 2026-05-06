"""spark-modem recovery — produce ranked PlannedAction[] for a Diag fixture.

Loads a Diag JSON from ``--diag-fixture=PATH`` (FR-52), invokes the pure
policy engine (``policy.engine.run_cycle``), and prints the ranked
PlannedAction[] either as JSON, JSON-with-transitions, or human-readable
text via ``--explain``. ``--dry-run`` propagates into ``Settings.dry_run``
so every plan carries ``suppressed_by_dry_run=True``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from spark_modem.cli.clients import _CliClock, build_default_settings
from spark_modem.cli.explain import format_plans_explain
from spark_modem.policy.context import PolicyContext
from spark_modem.policy.engine import run_cycle
from spark_modem.wire.diag import Diag
from spark_modem.wire.globals import GlobalsState
from spark_modem.wire.state import ModemState


def _fresh_state() -> ModemState:
    return ModemState.model_validate(
        {
            "state": "unknown",
            "present": True,
            "rf_blocked": False,
            "recovering_level": None,
            "_healthy_streak": 0,
            "counters": {},
            "last_action_monotonic": None,
            "last_state_transition_iso": None,
        }
    )


async def run(args: argparse.Namespace) -> int:
    if args.diag_fixture is None:
        print(
            "recovery: --diag-fixture is required in Phase 2 (laptop mode)",
            file=sys.stderr,
        )
        return 2

    diag_path = Path(args.diag_fixture)
    try:
        # CLI is short-lived; sync read is intentional and bounded (M7 ≤30s budget).
        diag = Diag.model_validate_json(diag_path.read_bytes())  # noqa: ASYNC240
    except OSError as exc:
        print(f"recovery: failed to read {diag_path}: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"recovery: failed to parse {diag_path}: {exc}", file=sys.stderr)
        return 2

    prior_states: dict[str, ModemState] = {
        usb_path: _fresh_state() for usb_path in diag.per_modem
    }

    settings = build_default_settings()
    if args.dry_run:
        settings = settings.model_copy(update={"dry_run": True})

    expected = len(diag.per_modem) or 4
    ctx = PolicyContext(
        clock=_CliClock(),
        config=settings,
        maintenance_active=False,
        expected_modem_count=expected,
    )

    result = run_cycle(diag, prior_states, GlobalsState(), ctx)

    if args.json:
        payload = {
            "plans": [p.model_dump(mode="json") for p in result.plans],
            "transitions": [
                {
                    "usb_path": t.usb_path,
                    "from_state": t.from_state,
                    "to_state": t.to_state,
                    "cause": t.cause,
                }
                for t in result.transitions
            ],
        }
        print(json.dumps(payload, indent=2))
    elif args.explain:
        print(format_plans_explain(result.plans))
    else:
        print(json.dumps([p.model_dump(mode="json") for p in result.plans]))
    return 0
