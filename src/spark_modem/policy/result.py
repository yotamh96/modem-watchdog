"""CycleResult -- what the policy engine returns; consumed by the cycle driver.

The cycle driver in plan 02-10 persists `new_states` and `new_globals`
atomically after calling the action dispatcher; events for `transitions`
and `plans` are emitted to events.jsonl (NFR-20).

Plan 04-05 (Phase 4 B-04) adds `skipped: list[ActionSkipped]` -- consumer-
friendly event variants emitted alongside the legacy PlannedAction.suppressed_*
flags whenever a gate suppresses an action. Cycle driver flushes them via
event_logger.append AFTER the atomic state write per RECOVERY_SPEC §8.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from spark_modem.wire.diag import PlannedAction
from spark_modem.wire.events import ActionSkipped
from spark_modem.wire.globals import GlobalsState
from spark_modem.wire.state import ModemState


@dataclass(frozen=True, slots=True)
class StateTransition:
    """Per-modem state change.

    Consumed by event_logger to emit one events.jsonl line per transition
    (NFR-20). `from_state` and `to_state` are the StateLiteral values
    (`unknown` / `healthy` / `degraded` / `recovering` / `exhausted`);
    `cause` is a canonical "<category>/<detail>" string or `no_issues`.
    """

    usb_path: str
    from_state: str
    to_state: str
    cause: str
    new_modem_state: ModemState


@dataclass(frozen=True, slots=True)
class CycleResult:
    """Output of policy.engine.run_cycle.

    The cycle driver persists `new_states` and `new_globals` atomically
    after calling the action dispatcher; events for `transitions`,
    `plans`, and `skipped` are emitted to events.jsonl.

    Plan 04-05 / Phase 4 B-04: `skipped` carries first-class ActionSkipped
    events emitted alongside the legacy PlannedAction.suppressed_* flags
    on every gate-failure / hard-skip / dry-run path. Empty list when no
    gate fired this cycle. Cycle driver flushes after the atomic state
    write per RECOVERY_SPEC §8 (state authoritative; events.jsonl advisory).
    """

    plans: list[PlannedAction] = field(default_factory=list)
    transitions: list[StateTransition] = field(default_factory=list)
    new_states: dict[str, ModemState] = field(default_factory=dict)
    new_globals: GlobalsState = field(default_factory=GlobalsState)
    skipped: list[ActionSkipped] = field(default_factory=list)
