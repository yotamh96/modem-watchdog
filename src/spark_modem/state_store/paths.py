"""Filesystem paths for persistent state and runtime locks.

All paths are configurable via environment variables for test isolation:
  SPARK_MODEM_STATE_ROOT  (default /var/lib/spark-modem-watchdog)
  SPARK_MODEM_RUN_DIR     (default /run/spark-modem-watchdog)

ADR-0009: state files keyed by usb_path at state/by-usb/<usb_path>.json.
ADR-0012: per-modem flock at modem-<usb_path>.lock; state-store flock at
  state.lock; PID lock at lock — all three are separate files.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_STATE_ROOT = "/var/lib/spark-modem-watchdog"
DEFAULT_RUN_DIR = "/run/spark-modem-watchdog"


def state_root() -> Path:
    """Return the state root directory (configurable via SPARK_MODEM_STATE_ROOT)."""
    return Path(os.environ.get("SPARK_MODEM_STATE_ROOT", DEFAULT_STATE_ROOT))


def run_dir() -> Path:
    """Return the runtime directory (configurable via SPARK_MODEM_RUN_DIR)."""
    return Path(os.environ.get("SPARK_MODEM_RUN_DIR", DEFAULT_RUN_DIR))


def state_by_usb_dir(*, root: Path | None = None) -> Path:
    """Return the state/by-usb directory under the state root."""
    return (root or state_root()) / "state" / "by-usb"


def state_file_for_modem(usb_path: str, *, root: Path | None = None) -> Path:
    """Return the state file path for a modem identified by usb_path.

    ADR-0009: state/by-usb/<usb_path>.json keyed by USB topology, NOT cdc-wdmN.

    Raises ValueError if usb_path contains path-traversal sequences ('/' or '..').
    """
    if not usb_path or "/" in usb_path or ".." in usb_path:
        raise ValueError(f"invalid usb_path for state file: {usb_path!r}")
    return state_by_usb_dir(root=root) / f"{usb_path}.json"


def identity_map_path(*, root: Path | None = None) -> Path:
    """Return the identity map file path."""
    return (root or state_root()) / "identity.json"


def globals_path(*, root: Path | None = None) -> Path:
    """Return the globals state file path."""
    return (root or state_root()) / "globals.json"


def lockfile_for_modem(usb_path: str, *, run: Path | None = None) -> Path:
    """Return the per-modem cross-process flock path (FR-61.1, ADR-0012).

    Raises ValueError if usb_path contains path-traversal sequences.
    """
    if not usb_path or "/" in usb_path or ".." in usb_path:
        raise ValueError(f"invalid usb_path for lockfile: {usb_path!r}")
    return (run or run_dir()) / f"modem-{usb_path}.lock"


def state_store_lockfile(*, run: Path | None = None) -> Path:
    """Return the state-store cross-process flock path (FR-61.1, ADR-0012)."""
    return (run or run_dir()) / "state.lock"


def pid_lockfile(*, run: Path | None = None) -> Path:
    """Return the PID lock path — SEPARATE from state.lock and modem-*.lock (FR-61, ADR-0012)."""
    return (run or run_dir()) / "lock"
