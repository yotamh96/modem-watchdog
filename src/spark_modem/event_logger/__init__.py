"""event_logger — single-writer sync JSON Lines append for events.jsonl."""

from spark_modem.event_logger.writer import EventLogClosedError, EventLogWriter

# Keep the old name as an alias so existing imports don't break during
# Phase 1 — the plan spec uses EventLogClosed; we ship EventLogClosedError
# (ruff N818) and alias for backward compat within this phase.
EventLogClosed = EventLogClosedError

__all__ = ["EventLogClosed", "EventLogClosedError", "EventLogWriter"]
