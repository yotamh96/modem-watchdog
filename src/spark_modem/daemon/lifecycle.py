"""Daemon lifecycle — sd_notify wrapper + clean-shutdown marker + PID lock.

Three Phase 3 lifecycle concerns live here:

  1. ``SdNotifyLifecycle`` (Pattern 6 / L-01): silently no-ops when
     ``$NOTIFY_SOCKET`` is unset (laptop dev hosts) so the same code path
     runs in tests and in production. Methods mirror the four sd_notify
     verbs the daemon emits: READY=1 / STATUS= / WATCHDOG=1 / STOPPING=1.

  2. ``acquire_pid_lock`` (Pattern 8 / L-05 step 5 / FR-61 / FR-61.1):
     thin wrapper around ``state_store.locks.acquire_flock`` against a
     third lock file at ``/run/spark-modem-watchdog/lock`` — separate from
     ``state.lock`` and ``modem-{usb_path}.lock`` per ADR-0012. Released
     by the kernel on death (PITFALLS §4.4: stale-PID file is safe to
     take over).

  3. ``write_clean_shutdown_marker`` + ``classify_prior_run``
     (Pattern 11 / L-04): tmpfs-resident JSON marker classifies the
     PRIOR run on boot. Precedence: ``last-config-error`` (CONFIG_INVALID)
     > ``clean-shutdown`` (SIGTERM) > absent (CRASH). Markers are unlinked
     after read so the next boot starts clean.

CLAUDE.md invariants reinforced:
  * #4: durations use ``time.monotonic()``; ISO stamps via wall-clock.
  * #5: marker writes are atomic (temp + rename + dir fsync).
  * #11: sd_notify is OUTBOUND only; no inbound IPC in v2.0.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Final

from spark_modem.state_store.atomic import atomic_write_bytes
from spark_modem.state_store.errors import StateStoreLocked
from spark_modem.state_store.locks import acquire_flock
from spark_modem.wire.enums import DaemonStopReason

logger = logging.getLogger(__name__)

_CLEAN_SHUTDOWN_MARKER: Final[str] = "clean-shutdown"
_LAST_CONFIG_ERROR: Final[str] = "last-config-error"
_PID_LOCK_FILENAME: Final[str] = "lock"


# ----------------------------------------------------------------------
# sd_notify wrapper (Pattern 6, L-01)
# ----------------------------------------------------------------------


class SdNotifyLifecycle:
    """Async-safe sd_notify wrapper.

    Constructor checks ``$NOTIFY_SOCKET`` and silently no-ops when unset,
    so the same wiring runs on dev hosts (no systemd) and in production
    (systemd Type=notify). PITFALLS §4.1: send only from main daemon PID;
    READY=1 fires only after the FIRST cycle proves the daemon did
    real work; WATCHDOG=1 kicks at cycle-END after status.json is written.
    """

    def __init__(self) -> None:
        # Defer the sdnotify import so the module imports cleanly on dev
        # hosts that don't have the sdnotify wheel installed.
        notifier: object | None = None
        if os.environ.get("NOTIFY_SOCKET"):
            try:
                import sdnotify  # noqa: PLC0415

                notifier = sdnotify.SystemdNotifier()
            except ImportError:  # pragma: no cover — production has the wheel
                logger.warning("sdnotify import failed; lifecycle notifications will no-op")
                notifier = None
        self._notifier = notifier

    @property
    def enabled(self) -> bool:
        """True if sd_notify is wired (running under systemd)."""
        return self._notifier is not None

    def ready(self, status_message: str = "READY") -> None:
        """Send READY=1 + STATUS=<message> (L-01: end of first cycle)."""
        if self._notifier is None:
            return
        # Compound notify per sd_notify protocol: multiple lines per packet.
        self._notify(f"READY=1\nSTATUS={status_message}")

    def status(self, message: str) -> None:
        """Send STATUS=<message> (L-01: per-cycle cadence)."""
        if self._notifier is None:
            return
        self._notify(f"STATUS={message}")

    def watchdog_kick(self) -> None:
        """Send WATCHDOG=1 (L-01: cycle-END after status.json write).

        PITFALLS §4.1: cycle-end placement is load-bearing — firing at
        cycle-start admits a wedged-cycle window where the daemon reports
        healthy while qmicli is hung.
        """
        if self._notifier is None:
            return
        self._notify("WATCHDOG=1")

    def stopping(self, message: str = "Shutting down") -> None:
        """Send STOPPING=1 + STATUS=<message> (L-02: SIGTERM choreography)."""
        if self._notifier is None:
            return
        self._notify(f"STOPPING=1\nSTATUS={message}")

    def _notify(self, payload: str) -> None:
        """Defensive: notify() may raise on socket errors; never propagate."""
        notifier = self._notifier
        if notifier is None:
            return
        try:
            notifier.notify(payload)  # type: ignore[attr-defined]
        except Exception:  # NFR-11: lifecycle notifications never crash the daemon
            logger.exception("sd_notify failed payload=%r", payload[:80])


# ----------------------------------------------------------------------
# PID lock (Pattern 8, L-05 step 5, FR-61, FR-61.1, ADR-0012)
# ----------------------------------------------------------------------


class PidLockHeldError(RuntimeError):
    """Another instance holds /run/.../lock (FR-61 single-instance).

    The held flock means a daemon is already running in this run_dir.
    Kernel-released on the holder's death; the next start retries cleanly.
    """

    def __init__(self, holder_pid: int | None, lock_path: str) -> None:
        super().__init__(
            f"PID lock {lock_path!r} held by pid={holder_pid}"
            if holder_pid is not None
            else f"PID lock {lock_path!r} held"
        )
        self.holder_pid = holder_pid
        self.lock_path = lock_path


@contextlib.contextmanager
def acquire_pid_lock(*, run_dir: Path) -> Iterator[int]:
    """Acquire the daemon-instance PID lock at ``run_dir / 'lock'``.

    Context manager: yields the open fd; releases on exit. The kernel
    auto-releases on death so a stale-PID file from a crashed instance
    is safe to take over.

    Raises:
        PidLockHeldError: when another process holds the lock.
    """
    lock_path = run_dir / _PID_LOCK_FILENAME
    try:
        with acquire_flock(lock_path, blocking=False, write_pid=True) as fd:
            yield fd
    except StateStoreLocked as exc:
        raise PidLockHeldError(exc.holder_pid, str(lock_path)) from exc


# ----------------------------------------------------------------------
# Clean-shutdown marker IO (Pattern 11, L-04)
# ----------------------------------------------------------------------


def write_clean_shutdown_marker(
    *,
    run_dir: Path,
    uptime_seconds: float,
    cycle_count: int,
    exit_reason: str = "sigterm",
) -> None:
    """Write ``/run/.../clean-shutdown`` atomically (L-02 step 8).

    The marker body is JSON: ``{uptime_s, cycle_count, exit_reason}``.
    Tmpfs-resident by design — a planned reboot is functionally
    equivalent to a crash from the daemon's perspective (no in-flight
    state to preserve, prior session is gone). Atomic per CLAUDE.md
    invariant #5.
    """
    target = run_dir / _CLEAN_SHUTDOWN_MARKER
    target.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "uptime_s": float(uptime_seconds),
        "cycle_count": int(cycle_count),
        "exit_reason": str(exit_reason),
    }
    payload = json.dumps(body, sort_keys=True).encode("utf-8")
    atomic_write_bytes(target, payload)


def classify_prior_run(*, run_dir: Path) -> tuple[DaemonStopReason, float]:
    """Classify the prior daemon run by reading + unlinking marker files.

    Precedence (most-specific wins):
      1. ``last-config-error`` exists → ``CONFIG_INVALID``, uptime 0.0.
      2. ``clean-shutdown`` exists    → ``SIGTERM``, uptime from JSON body.
      3. neither                      → ``CRASH``, uptime 0.0.

    Both markers are unlinked after read so the next boot starts clean.
    Phase 3 ships only sigterm/crash/config_invalid; oom + kill are
    Phase 4 territory (require external observation).

    Corrupt JSON in the SIGTERM marker still classifies as SIGTERM
    (the marker exists; the daemon DID emit it) but uptime falls back
    to 0.0.
    """
    config_error_path = run_dir / _LAST_CONFIG_ERROR
    if config_error_path.exists():
        with contextlib.suppress(FileNotFoundError, OSError):
            config_error_path.unlink()
        return DaemonStopReason.CONFIG_INVALID, 0.0

    marker_path = run_dir / _CLEAN_SHUTDOWN_MARKER
    if marker_path.exists():
        uptime = 0.0
        try:
            body = json.loads(marker_path.read_text(encoding="utf-8"))
            uptime = float(body.get("uptime_s", 0.0))
        except (OSError, ValueError, json.JSONDecodeError):
            uptime = 0.0
        with contextlib.suppress(FileNotFoundError, OSError):
            marker_path.unlink()
        return DaemonStopReason.SIGTERM, uptime

    return DaemonStopReason.CRASH, 0.0
