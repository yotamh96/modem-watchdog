"""libqmi version detection — parses `qmicli --version` stdout.

Phase 5 X-03 daemon preflight uses this to compute the local libqmi
version for the (firmware, sdk, libqmi) triple check against
``/etc/spark-modem-watchdog/known-fleet/``.

All subprocess calls route through ``subproc.runner.run`` (SP-04).

This module is the single seam for version-string formatting so the
CLI capture path and the daemon preflight path always agree byte-for-byte.

Task 3 of Plan 05-02 extends this module with ``FleetTriple`` (frozen
pydantic) and ``compute_fleet_triple`` (orchestrator) — see the bottom
of the file once that task lands.
"""

from __future__ import annotations

import re
from typing import Final

from spark_modem.subproc import runner as subproc_runner

_LIBQMI_VERSION_RE: Final[re.Pattern[str]] = re.compile(
    r"libqmi-glib\s+(\d+\.\d+\.\d+)", re.IGNORECASE
)
_DEFAULT_TIMEOUT_S: Final[float] = 2.0
_STDOUT_EXCERPT_BYTES: Final[int] = 512
_STDERR_EXCERPT_BYTES: Final[int] = 512


class QmiVersionDetectionFailed(RuntimeError):  # noqa: N818 — matches PreflightFailed shape
    """Raised when qmicli --version stdout cannot be parsed or the call fails.

    Subclass of ``RuntimeError`` so callers that catch ``RuntimeError`` only
    (or its descendants) still see the failure as a runtime problem.
    """


async def detect_libqmi_version(*, timeout_s: float = _DEFAULT_TIMEOUT_S) -> str:
    """Return the libqmi-glib version string (e.g. ``'1.30.6'``).

    Raises ``QmiVersionDetectionFailed`` if qmicli is missing, the call
    exits non-zero, or stdout does not contain a ``libqmi-glib X.Y.Z``
    substring. Always routes through ``subproc.runner.run`` (SP-04
    invariant; argv is hardcoded list ``["qmicli", "--version"]`` so no
    injection surface).
    """
    try:
        cp = await subproc_runner.run(["qmicli", "--version"], timeout_s=timeout_s)
    except FileNotFoundError as exc:
        raise QmiVersionDetectionFailed(
            "qmicli binary not on PATH (FR-60)"
        ) from exc
    if cp.exit_code != 0:
        raise QmiVersionDetectionFailed(
            f"qmicli --version exit_code={cp.exit_code} "
            f"stderr={cp.stderr[:_STDERR_EXCERPT_BYTES]!r}"
        )
    m = _LIBQMI_VERSION_RE.search(cp.stdout.decode("utf-8", errors="replace"))
    if m is None:
        raise QmiVersionDetectionFailed(
            f"qmicli --version stdout did not match libqmi-glib regex: "
            f"{cp.stdout[:_STDOUT_EXCERPT_BYTES]!r}"
        )
    return m.group(1)
