"""Daemon entry point + cycle scheduler + cycle driver (Plan 02-10).

Phase 2 ships the cycle-driver integration point that wires every Phase 2
subsystem (observer + policy + actions + state-store + status_reporter +
webhook + metrics + event_logger) into a single ``CycleDriver``.

Phase 3 adds:
  - ``sd_notify`` Type=notify integration (FR-75)
  - signal handlers via ``loop.add_signal_handler`` (graceful SIGTERM ≤5s)
  - PID lock at ``/run/spark-modem-watchdog/lock``
  - real event-driven sources via the ``CycleScheduler.event_queue`` arm
    (udev / rtnetlink / inotify producers)
"""
