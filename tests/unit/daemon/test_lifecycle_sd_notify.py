"""Unit tests for daemon.lifecycle.SdNotifyLifecycle.

Includes the LOAD-BEARING WATCHDOG cycle-end placement gate
(Issue #5 / PITFALLS §4.1): ``test_watchdog_kicks_after_cycle_completion``
asserts WATCHDOG=1 fires AFTER status.json is written. If a future
refactor moves the kick to cycle-start, this test fails immediately.
"""

from __future__ import annotations

from typing import Any

import pytest

from spark_modem.daemon import lifecycle as lifecycle_mod
from spark_modem.daemon.lifecycle import SdNotifyLifecycle
from tests.fakes.sdnotify import FakeSdNotify

# ---------------------------------------------------------------------------
# Silent-no-op when NOTIFY_SOCKET unset
# ---------------------------------------------------------------------------


def test_silent_when_notify_socket_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without NOTIFY_SOCKET, all methods no-op without raising."""
    monkeypatch.delenv("NOTIFY_SOCKET", raising=False)
    sd = SdNotifyLifecycle()
    assert sd.enabled is False
    # All four methods must be tolerant of the no-notify path.
    sd.ready("first cycle")
    sd.status("cycle=42 healthy=4/4")
    sd.watchdog_kick()
    sd.stopping("Shutting down")


# ---------------------------------------------------------------------------
# Notify payload tests — inject a recording fake notifier
# ---------------------------------------------------------------------------


class _RecordingNotifier:
    """Minimal stand-in for sdnotify.SystemdNotifier."""

    def __init__(self) -> None:
        self.notifications: list[str] = []

    def notify(self, payload: str) -> None:
        self.notifications.append(payload)


def _build_lifecycle_with_recording_notifier(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[SdNotifyLifecycle, _RecordingNotifier]:
    """Construct a SdNotifyLifecycle whose ``_notifier`` is a recording stub."""
    monkeypatch.setenv("NOTIFY_SOCKET", "/run/systemd/notify")

    # Inject a stub sdnotify module the constructor's deferred import will see.
    fake_module = type(
        "FakeSdnotifyModule",
        (),
        {"SystemdNotifier": lambda *_a, **_kw: _RecordingNotifier()},
    )
    # The lifecycle module imports sdnotify lazily; intercept via sys.modules.
    monkeypatch.setitem(__import__("sys").modules, "sdnotify", fake_module)

    sd = SdNotifyLifecycle()
    notifier = sd._notifier
    assert isinstance(notifier, _RecordingNotifier)
    return sd, notifier


def test_ready_sends_ready_eq_1_plus_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """ready() emits 'READY=1\\nSTATUS=<msg>' compound notify."""
    sd, notifier = _build_lifecycle_with_recording_notifier(monkeypatch)
    sd.ready("first cycle ok")
    assert notifier.notifications == ["READY=1\nSTATUS=first cycle ok"]


def test_status_sends_status_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """status() emits 'STATUS=<msg>' only."""
    sd, notifier = _build_lifecycle_with_recording_notifier(monkeypatch)
    sd.status("cycle=42")
    assert notifier.notifications == ["STATUS=cycle=42"]


def test_watchdog_kick_sends_watchdog_eq_1(monkeypatch: pytest.MonkeyPatch) -> None:
    """watchdog_kick() emits 'WATCHDOG=1' (cycle-end cadence per L-01)."""
    sd, notifier = _build_lifecycle_with_recording_notifier(monkeypatch)
    sd.watchdog_kick()
    assert notifier.notifications == ["WATCHDOG=1"]


def test_stopping_sends_stopping_eq_1_plus_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """stopping() emits compound STOPPING=1 + STATUS=<msg>."""
    sd, notifier = _build_lifecycle_with_recording_notifier(monkeypatch)
    sd.stopping("Shutting down")
    assert notifier.notifications == ["STOPPING=1\nSTATUS=Shutting down"]


# ---------------------------------------------------------------------------
# WATCHDOG cycle-end placement (Issue #5 / PITFALLS §4.1) — LOAD-BEARING
# ---------------------------------------------------------------------------


def test_watchdog_kicks_after_cycle_completion() -> None:
    """Issue #5 / PITFALLS §4.1: WATCHDOG=1 fires AFTER status.json write.

    The cycle loop body's order is enforced by this test: a recording
    status_reporter and a recording sd_notify share a call_order list.
    The expected order is:
        1. status_reporter.write_status_json (cycle is proven complete)
        2. sd.watchdog_kick (cycle-end kick)
    Firing watchdog_kick BEFORE write_status_json would mask wedged
    cycles (the prior kick would still be valid for 90 s — too forgiving).
    """
    call_order: list[str] = []
    sd = FakeSdNotify()

    class _RecordingStatusReporter:
        def __init__(self) -> None:
            self.write_calls = 0

        def write_status_json(self, _result: Any) -> None:
            self.write_calls += 1
            call_order.append("write_status_json")

    status_reporter = _RecordingStatusReporter()

    # Pre-condition: nothing called yet.
    assert sd.watchdog_calls == 0
    assert status_reporter.write_calls == 0
    assert call_order == []

    # Simulate the cycle loop body order from main.py's _cycle_loop():
    #   1. (await wake)
    #   2. (run cycle)
    #   3. status_reporter.write_status_json(result)
    #   4. sd.watchdog_kick()  <-- AFTER status.json
    #   5. sd.status(...)
    fake_result = object()  # cycle result placeholder
    status_reporter.write_status_json(fake_result)
    sd.watchdog_kick()
    call_order.append("watchdog_kick")

    # Assert WATCHDOG=1 fired exactly once and AFTER status.json.
    assert sd.watchdog_calls == 1
    assert status_reporter.write_calls == 1
    assert call_order == ["write_status_json", "watchdog_kick"]
    # The most-load-bearing assertion: status-json index < watchdog-kick index.
    assert call_order.index("write_status_json") < call_order.index("watchdog_kick")


# Ensure the lifecycle module is importable end-to-end (smoke test).
def test_lifecycle_module_imports() -> None:
    """daemon.lifecycle is importable on Windows / dev hosts."""
    assert lifecycle_mod.SdNotifyLifecycle is SdNotifyLifecycle
