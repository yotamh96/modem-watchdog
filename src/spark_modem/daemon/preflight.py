"""Preflight gate — FR-60 PATH check + Settings validate (L-05 step 3).

Runs BEFORE PID lock acquisition. On any failure: write
``/run/spark-modem-watchdog/last-config-error`` and return non-zero exit
code. The boot classifier (``lifecycle.classify_prior_run``) reads this
file at the next boot to classify the prior run as ``CONFIG_INVALID``
per L-04.

All subprocess calls go through ``subproc.runner.run`` (SP-04 lint).
The two preflight binaries are:
  * ``qmicli`` — the QMI client every Phase 2 cheap action invokes.
  * ``ip``    — the netlink front-end Phase 3 ``ip netns exec`` calls.

If either is absent from PATH the daemon refuses to start (FR-60). On
the bench Jetson both ship via the system package set; the preflight
catches box mis-provisioning during Phase 5 rollout.
"""

from __future__ import annotations

import logging
from pathlib import Path

from spark_modem.subproc import runner as subproc_runner

logger = logging.getLogger(__name__)


class PreflightFailed(RuntimeError):  # noqa: N818 — public name fixed by plan acceptance
    """Raised when a required external binary is missing from PATH (FR-60).

    Plan 03-06 acceptance criterion pins ``class PreflightFailed`` (no
    ``Error`` suffix); ruff N818 suppressed at the class declaration.
    """


_PREFLIGHT_BINARIES: tuple[tuple[str, list[str]], ...] = (
    ("qmicli", ["--version"]),
    ("ip", ["--version"]),
)
_PREFLIGHT_TIMEOUT_S: float = 2.0


async def preflight_check() -> None:
    """Verify every required binary is present on PATH.

    Calls ``subproc_runner.run`` for each binary; ``FileNotFoundError``
    from the spawn layer indicates the binary is not installed (FR-60).
    Other ``OSError`` subclasses propagate to the caller (the daemon
    ``main()`` translates them into ``last-config-error`` + non-zero
    exit).
    """
    for binary, args in _PREFLIGHT_BINARIES:
        try:
            await subproc_runner.run([binary, *args], timeout_s=_PREFLIGHT_TIMEOUT_S)
        except FileNotFoundError as exc:
            raise PreflightFailed(f"required binary {binary!r} not on PATH (FR-60)") from exc


def write_last_config_error(*, run_dir: Path, message: str) -> None:
    """Write ``/run/.../last-config-error`` atomically (L-04).

    The boot classifier (``lifecycle.classify_prior_run``) reads this
    file on the next boot and classifies the prior run as
    ``DaemonStopReason.CONFIG_INVALID``, then unlinks. Atomic write per
    CLAUDE.md invariant #5 — never partial-write a marker.
    """
    # Local import — atomic_write_bytes lives in state_store/, importing it
    # at module scope would create a stale subgraph with state_store on
    # cyclic-import-sensitive code paths.
    from spark_modem.state_store.atomic import atomic_write_bytes  # noqa: PLC0415

    target = run_dir / "last-config-error"
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(target, message.encode("utf-8"))
