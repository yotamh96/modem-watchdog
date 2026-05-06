"""ActionResult / VerifyResult -- the data the dispatcher returns.

"All errors are data" (Phase 1 SP-02 carry-forward). Every action outcome
is a value, not an exception: succeeded vs failed, with an optional typed
VerifyResult that distinguishes ok / failed / deferred / no_verify.

Frozen + slots dataclasses: cheap to allocate, immutable across async
boundaries, mypy-friendly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind


@dataclass(frozen=True, slots=True)
class VerifyResult:
    """Post-action read-back outcome.

    status:
      - "ok"        : the action's effect was observed via a typed read-back
      - "failed"    : read-back returned a value that does not match
                      the post-condition (or the read-back itself errored)
      - "deferred"  : effect cannot be verified inline (e.g. soft_reset's
                      effect is observed next cycle); not an error
      - "no_verify" : the action does not require a read-back (reserved;
                      Phase 2 ships ok / failed / deferred only).
    """

    status: Literal["ok", "failed", "deferred", "no_verify"]
    detail: str = ""

    @classmethod
    def ok(cls, detail: str = "") -> VerifyResult:
        return cls(status="ok", detail=detail)

    @classmethod
    def failed(cls, detail: str = "") -> VerifyResult:
        return cls(status="failed", detail=detail)

    @classmethod
    def deferred(cls, detail: str = "") -> VerifyResult:
        return cls(status="deferred", detail=detail)

    @classmethod
    def no_verify(cls, detail: str = "") -> VerifyResult:
        return cls(status="no_verify", detail=detail)


@dataclass(frozen=True, slots=True)
class ActionResult:
    """Outcome of a dispatcher.execute_and_verify call.

    succeeded vs failed reflects the EXECUTE phase only; the VERIFY phase
    is captured in verify_result. A succeeded action with verify_result
    status "failed" means the action ran without error but its effect
    was not observed in the read-back -- the policy engine and replay
    harness can branch on that combination.

    dry_run=True means the dispatcher short-circuited at the gate and no
    side effects were produced (FR-28 / FR-28.1).
    """

    kind: ActionKind
    who: WhoModem
    succeeded: bool
    duration_seconds: float
    failure_reason: str | None = None
    verify_result: VerifyResult | None = None
    dry_run: bool = False

    def with_verify(self, verify: VerifyResult) -> ActionResult:
        """Return a copy with verify_result set (frozen dataclass copy)."""
        return ActionResult(
            kind=self.kind,
            who=self.who,
            succeeded=self.succeeded,
            duration_seconds=self.duration_seconds,
            failure_reason=self.failure_reason,
            verify_result=verify,
            dry_run=self.dry_run,
        )
