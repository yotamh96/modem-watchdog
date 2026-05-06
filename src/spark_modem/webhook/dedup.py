"""DedupTable — per-(modem, kind) cooldown with dedup_count accumulation.

FR-44.4 / ADR-0011: the default 60s coalescing window
(``config.webhook_dedup_seconds``) suppresses repeated transitions of the
same (modem_usb_path, payload_kind) pair within the window. The first
call OPENS the window and is NOT deduped; subsequent calls within the
window are suppressed and counted; the next non-deduped emission can
read the suppressed count via ``consume_dedup_count`` and embed it in
the outgoing envelope's ``dedup_count`` field.

Stateful but pure-Python (no I/O, no clock import — caller passes
``now_monotonic``). The cycle driver constructs one instance and shares
it across cycles.
"""

from __future__ import annotations


class DedupTable:
    """Per-(modem, kind) cooldown table with suppressed-count accumulation."""

    def __init__(self, *, window_seconds: float = 60.0) -> None:
        self._window = window_seconds
        self._expires_at: dict[tuple[str, str], float] = {}
        self._suppressed: dict[tuple[str, str], int] = {}

    def is_deduped(
        self,
        modem: str,
        kind: str,
        *,
        now_monotonic: float,
    ) -> bool:
        """If True, caller skips emission and the suppressed counter is bumped.

        First call (or first call after window expiry) opens a new window
        ending at ``now_monotonic + window_seconds`` and returns False.
        """
        key = (modem, kind)
        expires = self._expires_at.get(key, 0.0)
        if now_monotonic < expires:
            self._suppressed[key] = self._suppressed.get(key, 0) + 1
            return True
        self._expires_at[key] = now_monotonic + self._window
        return False

    def consume_dedup_count(self, modem: str, kind: str) -> int:
        """Reset and return the suppressed count for this (modem, kind).

        Caller embeds the returned value in the envelope's ``dedup_count``
        field at emission time. Subsequent calls return 0 until the next
        suppression occurs.
        """
        key = (modem, kind)
        return self._suppressed.pop(key, 0)
