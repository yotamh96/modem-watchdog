"""FakeSdNotify — call-recording fake mirroring SdNotifyLifecycle.

Records every ready / status / watchdog_kick / stopping invocation so
tests can assert call order and content without touching real systemd.
Mirrors the call-recording pattern from ``tests/fakes/runner.py``
(FakeRunner.calls) and ``tests/fakes/webhook.py`` (sent list).

The Phase 3 Issue #5 / PITFALLS §4.1 regression gate uses
``watchdog_calls`` to assert WATCHDOG=1 fires AFTER status.json is
written — see ``tests/unit/daemon/test_lifecycle_sd_notify.py
::test_watchdog_kicks_after_cycle_completion``.
"""

from __future__ import annotations


class FakeSdNotify:
    """Recording fake for SdNotifyLifecycle.

    Surface mirrors the production class (sync methods); tests inspect
    the recording lists / counters directly.
    """

    def __init__(self) -> None:
        self.ready_calls: list[str] = []
        self.status_calls: list[str] = []
        self.watchdog_calls: int = 0
        self.stopping_calls: list[str] = []

    @property
    def enabled(self) -> bool:
        """Test default: enabled=True (production checks $NOTIFY_SOCKET)."""
        return True

    def ready(self, status_message: str = "READY") -> None:
        self.ready_calls.append(status_message)

    def status(self, message: str) -> None:
        self.status_calls.append(message)

    def watchdog_kick(self) -> None:
        self.watchdog_calls += 1

    def stopping(self, message: str = "Shutting down") -> None:
        self.stopping_calls.append(message)
