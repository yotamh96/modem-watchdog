"""Phase 3 kmsg subsystem — classifier + dedup (E-03 / FR-14).

The producer (``event_sources/kmsg_producer.py``) reads ``/dev/kmsg`` in
non-blocking mode, parses the structured
``<priority>,<seq>,<ts>,<flags>;<message>`` format, then routes the
message through:

  1. ``classifier.classify(line) -> IssueDetail`` — closed enum;
     5 host-level values + UNKNOWN (E-03 LOCKED).
  2. ``dedup.KmsgDedup.should_emit(detail)`` — per-detail 30s
     sliding-window dedup (PITFALLS §13.2).

Closed-enum discipline (W-04 anti-pattern: free-form ``detail`` strings).
The raw kernel line is preserved by the producer in a separate forensic
field for debugging and NEVER enters the ``Issue.detail`` field.

Phase 4 destructive-action gating reads the IssueDetail values produced
by this subsystem (e.g. suppress ``usb_reset`` while
``USB_OVERCURRENT`` is the active host issue).
"""
