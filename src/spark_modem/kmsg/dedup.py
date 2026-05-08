"""KmsgDedup — per-detail sliding-window dedup for host Issues (E-03 / FR-14).

Mirrors the shape of ``webhook/dedup.py::DedupTable``. The key is the
``IssueDetail`` enum value; the default window is 30s per CONTEXT.md
E-03. PITFALLS §13.2 prescribes this pattern for high-volume kernel-
message storms (a USB hub power glitch generates 16+ events in 2s on
Tegra carriers).

Implementation choice (RESEARCH.md Open Question 5 / Claude's
discretion): timestamp-of-last-emit (simpler) over true sliding window.
First call after the window expires emits with ``repeat_count``
consumable via ``consume_dedup_count``.

Time source: caller passes ``now_monotonic`` from an injected ``ClockProto``
(CLAUDE.md invariant #4 — ``time.monotonic()`` only; never wall-clock for
durations).

Semantics flipped from ``webhook/dedup.py``: ``should_emit`` returns
True when the caller should EMIT (the producer reads the boolean as
"yes, push the Issue"). The webhook table's ``is_deduped`` returns True
on suppression — opposite direction. We follow the producer's natural
phrasing: ``if dedup.should_emit(detail, ...): emit_issue(...)``.
"""

from __future__ import annotations

from spark_modem.wire.enums import IssueDetail


class KmsgDedup:
    """Per-IssueDetail 30s sliding-window dedup."""

    def __init__(self, *, window_seconds: float = 30.0) -> None:
        self._window = window_seconds
        self._expires_at: dict[IssueDetail, float] = {}
        self._suppressed: dict[IssueDetail, int] = {}

    def should_emit(
        self,
        detail: IssueDetail,
        *,
        now_monotonic: float,
    ) -> bool:
        """Return True iff caller should emit an Issue for this detail.

        First call (or first call after window expiry) opens a new
        window ending at ``now_monotonic + window_seconds`` and returns
        True. Subsequent calls within the window return False and bump
        the suppressed counter for ``consume_dedup_count``.
        """
        expires = self._expires_at.get(detail, 0.0)
        if now_monotonic < expires:
            self._suppressed[detail] = self._suppressed.get(detail, 0) + 1
            return False
        self._expires_at[detail] = now_monotonic + self._window
        return True

    def consume_dedup_count(self, detail: IssueDetail) -> int:
        """Reset and return the suppressed count for ``detail``.

        Caller embeds the returned value in the Issue (or a follow-up
        event) so observers see N suppressions collapsed into one
        emission. Subsequent calls return 0 until the next suppression
        occurs.
        """
        return self._suppressed.pop(detail, 0)
