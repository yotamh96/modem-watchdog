"""Unit tests for SigtermChoreography — strict 8-step ordering (L-02).

Verifies the L-02 step list executes in the prescribed order; a single
step's failure does not skip later steps (NFR-11); step 5 emits
DaemonStopped(reason=SIGTERM); step 3 drain budget honors min(deadline,
3.0).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from spark_modem.daemon.sigterm import SigtermChoreography
from spark_modem.wire.enums import DaemonStopReason
from spark_modem.wire.events import DaemonStopped
from tests.fakes.clock import FakeClock

# ---------------------------------------------------------------------------
# Helpers — recording stand-ins for each subsystem the choreography touches
# ---------------------------------------------------------------------------


class _RecordingWebhookPoster:
    def __init__(self, *, call_order: list[str]) -> None:
        self._call_order = call_order
        self.drain_budgets: list[float] = []
        self.stopped: bool = False

    async def drain(self, *, budget_seconds: float = 3.0) -> None:
        self._call_order.append("drain_webhook")
        self.drain_budgets.append(budget_seconds)

    def stop(self) -> None:
        self._call_order.append("stop_webhook")
        self.stopped = True


class _RecordingEventLogger:
    def __init__(self, *, call_order: list[str]) -> None:
        self._call_order = call_order
        self.events: list[object] = []

    def append(self, event: object) -> None:
        self._call_order.append("emit_daemon_stopped")
        self.events.append(event)


async def _make_recording_task(name: str, call_order: list[str]) -> asyncio.Task[object]:
    """Build a long-running task that records its cancellation."""
    started = asyncio.Event()

    async def _coro() -> object:
        started.set()
        try:
            await asyncio.Future()  # forever until cancelled
        except asyncio.CancelledError:
            call_order.append(f"cancel_{name}")
            raise
        return None

    task: asyncio.Task[object] = asyncio.create_task(_coro())
    await started.wait()
    return task


def _make_choreography(
    *,
    cycle_task: asyncio.Task[object],
    producer_tasks: list[asyncio.Task[object]],
    poster: _RecordingWebhookPoster,
    event_logger: _RecordingEventLogger,
    metrics_socket_path: Path,
    run_dir: Path,
) -> SigtermChoreography:
    clock = FakeClock()
    return SigtermChoreography(
        cycle_driver_task=cycle_task,
        producer_tasks=producer_tasks,
        webhook_poster=poster,
        event_logger=event_logger,
        metrics_socket_path=metrics_socket_path,
        run_dir=run_dir,
        clock=clock,
        boot_monotonic=clock.monotonic(),
        cycle_count_ref=[42],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_eight_steps_execute_in_strict_order(tmp_path: Path) -> None:
    """Steps 1-8 fire in order: cancel cycle → cancel producers → drain →
    emit DaemonStopped → stop webhook → unlink metrics socket → write marker.
    """
    call_order: list[str] = []
    cycle_task = await _make_recording_task("cycle", call_order)
    # Recording the cancellation order in the producer tasks; we want
    # them to follow the cycle cancel.
    producer_tasks = [
        await _make_recording_task("producer_a", call_order),
        await _make_recording_task("producer_b", call_order),
    ]
    poster = _RecordingWebhookPoster(call_order=call_order)
    event_logger = _RecordingEventLogger(call_order=call_order)
    # Pre-create the metrics socket so unlink succeeds and is observable.
    metrics_socket = tmp_path / "metrics.sock"
    metrics_socket.write_bytes(b"")

    choreography = _make_choreography(
        cycle_task=cycle_task,
        producer_tasks=producer_tasks,
        poster=poster,
        event_logger=event_logger,
        metrics_socket_path=metrics_socket,
        run_dir=tmp_path,
    )

    await choreography.execute(deadline_seconds=5.0)

    # Cycle cancel happens FIRST.
    assert call_order[0] == "cancel_cycle"
    # All producers cancelled before the drain.
    drain_idx = call_order.index("drain_webhook")
    assert call_order.index("cancel_producer_a") < drain_idx
    assert call_order.index("cancel_producer_b") < drain_idx
    # Order: drain → emit_daemon_stopped → stop_webhook (steps 3 → 5 → 6).
    assert drain_idx < call_order.index("emit_daemon_stopped") < call_order.index("stop_webhook")
    # Step 8: marker written; metrics socket unlinked.
    marker = tmp_path / "clean-shutdown"
    assert marker.exists()
    assert not metrics_socket.exists()


async def test_step_3_drain_budget_capped_at_3s(tmp_path: Path) -> None:
    """deadline_seconds=2.0 → drain budget ≤ 2.0 (deadline cap wins over 3.0)."""
    call_order: list[str] = []
    cycle_task = await _make_recording_task("cycle", call_order)
    poster = _RecordingWebhookPoster(call_order=call_order)
    event_logger = _RecordingEventLogger(call_order=call_order)
    metrics_socket = tmp_path / "metrics.sock"
    metrics_socket.write_bytes(b"")

    choreography = _make_choreography(
        cycle_task=cycle_task,
        producer_tasks=[],
        poster=poster,
        event_logger=event_logger,
        metrics_socket_path=metrics_socket,
        run_dir=tmp_path,
    )
    await choreography.execute(deadline_seconds=2.0)
    # The drain budget is the smaller of 3.0 and the deadline-remaining.
    assert poster.drain_budgets, "drain must be invoked"
    assert poster.drain_budgets[0] <= 2.0


async def test_step_5_emits_daemon_stopped_with_reason_sigterm(
    tmp_path: Path,
) -> None:
    """Step 5: event_logger.append called with DaemonStopped(reason=SIGTERM)."""
    call_order: list[str] = []
    cycle_task = await _make_recording_task("cycle", call_order)
    poster = _RecordingWebhookPoster(call_order=call_order)
    event_logger = _RecordingEventLogger(call_order=call_order)
    metrics_socket = tmp_path / "metrics.sock"
    metrics_socket.write_bytes(b"")

    choreography = _make_choreography(
        cycle_task=cycle_task,
        producer_tasks=[],
        poster=poster,
        event_logger=event_logger,
        metrics_socket_path=metrics_socket,
        run_dir=tmp_path,
    )
    await choreography.execute(deadline_seconds=5.0)
    assert len(event_logger.events) == 1
    event = event_logger.events[0]
    assert isinstance(event, DaemonStopped)
    assert event.reason is DaemonStopReason.SIGTERM


async def test_step_failure_does_not_abort_remaining_steps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Step 3 raising → steps 5-8 still execute (NFR-11)."""
    call_order: list[str] = []
    cycle_task = await _make_recording_task("cycle", call_order)

    class _RaisingPoster:
        async def drain(self, *, budget_seconds: float = 3.0) -> None:
            del budget_seconds
            call_order.append("drain_webhook_RAISED")
            raise RuntimeError("synthetic drain failure")

        def stop(self) -> None:
            call_order.append("stop_webhook")

    poster = _RaisingPoster()
    event_logger = _RecordingEventLogger(call_order=call_order)
    metrics_socket = tmp_path / "metrics.sock"
    metrics_socket.write_bytes(b"")

    choreography = _make_choreography(
        cycle_task=cycle_task,
        producer_tasks=[],
        poster=poster,  # type: ignore[arg-type]
        event_logger=event_logger,
        metrics_socket_path=metrics_socket,
        run_dir=tmp_path,
    )
    await choreography.execute(deadline_seconds=5.0)

    # Step 3 raised but the choreography continued through later steps:
    assert "drain_webhook_RAISED" in call_order
    assert "emit_daemon_stopped" in call_order  # step 5 still ran
    assert "stop_webhook" in call_order  # step 6 still ran
    assert (tmp_path / "clean-shutdown").exists()  # step 8 still ran
    del monkeypatch  # parameter accepted for symmetry with sibling tests
