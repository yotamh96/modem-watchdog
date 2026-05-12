"""libqmi version detection + FleetTriple (X-02 / X-03).

Phase 5 X-03 daemon preflight uses this to compute the local libqmi
version for the ``(em7421_firmware, zao_sdk, libqmi)`` triple check
against ``/etc/spark-modem-watchdog/known-fleet/``; Phase 5 X-02
fleet-fixture capture (Plan 05-03) uses ``compute_fleet_triple`` to
emit the local triple to ``triple.json``.

All subprocess calls route through ``subproc.runner.run`` (SP-04).

This module is the single seam for version-string formatting so the
CLI capture path and the daemon preflight path always agree byte-for-byte.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

from spark_modem.qmi.errors import QmiError
from spark_modem.qmi.parsers.get_revision import parse_get_revision
from spark_modem.subproc import runner as subproc_runner
from spark_modem.subproc.result import CompletedProcess
from spark_modem.zao_log.version import detect_zao_sdk_version

# Phase 05.5: firmware probe retry budget. The qmi-proxy CID allocation
# races with Zao's continuous NAS/UIM queries — bench Jetson 2026-05-12
# observed roughly a 25% per-call failure rate with "Service mismatch
# (requested 'dms', got 'nas'/'uim')" or "endpoint hangup" stderr. Three
# attempts brings cumulative success > 99%; 0.5s spacing between attempts
# is empirically enough for the in-flight Zao query to release its CID.
_FIRMWARE_PROBE_ATTEMPTS: Final[int] = 3
_FIRMWARE_PROBE_BACKOFF_S: Final[float] = 0.5


_LIBQMI_VERSION_RE: Final[re.Pattern[str]] = re.compile(
    # Accept BOTH the `qmicli X.Y.Z` first line (always present) AND the
    # `Compiled with libqmi-glib X.Y.Z` footer (only on builds that include it).
    # The JetPack 5.1.5 / Ubuntu 20.04 libqmi 1.30.4 build prints ONLY the
    # `qmicli` line — no `libqmi-glib` footer. The two strings carry the same
    # version (qmicli is a frontend for libqmi-glib and they ship lockstep
    # from the same source tree), so matching either is correct. Bench Jetson
    # deploy 2026-05-12 (commit e49dc7b .deb) caught this with a Phase 5 X-03
    # preflight rejection — Phase 05.3 hotfix.
    r"(?:qmicli|libqmi-glib)\s+(\d+\.\d+\.\d+)",
    re.IGNORECASE,
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


# ---- FleetTriple wire type (X-02 / X-03) -----------------------------

_ZAO_SDK_UNKNOWN_SENTINEL: Final[str] = "unknown"


class FleetTriple(BaseModel):
    """The ``(em7421_firmware, zao_sdk, libqmi)`` triple identifying a fleet
    box's software stack. Phase 5 X-02 (capture) + X-03 (preflight).

    Frozen + ``extra='forbid'`` because this is a wire type that ships via
    ``triple.json`` files baked into the ``.deb`` and must be reproducible
    byte-identical across capture and preflight call sites.

    ``zao_sdk`` is either a 3-part version string (e.g. ``'2.1.0'``) or the
    literal sentinel ``'unknown'`` when no Zao banner was found in the log
    (RESEARCH Q3 §288-298: graceful fallback). Downstream preflight policy
    decides whether to fail closed on the sentinel.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    em7421_firmware: str
    zao_sdk: str
    libqmi: str


async def compute_fleet_triple(
    *,
    wrapper: object,
    zao_log_path: Path,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> FleetTriple:
    """Compute the local ``(firmware, sdk, libqmi)`` triple.

    Args:
        wrapper: A ``QmiWrapper`` instance (or test fake) with an async
            ``dms_get_revision() -> CompletedProcess`` method. Duck-typed
            to keep this module decoupled from ``qmi/wrapper.py`` (and
            avoid the corresponding import cycle through ``subproc/``).
        zao_log_path: Path to the Zao log file for SDK detection.
        timeout_s: libqmi detection timeout (firmware probe uses the
            wrapper's own default).

    Returns:
        ``FleetTriple`` with all three fields populated. ``zao_sdk`` is
        the string ``'unknown'`` if no Zao banner was found (caller
        decides downstream policy).

    Raises:
        ``QmiVersionDetectionFailed``: when either libqmi detection or
        the firmware probe fails (the daemon preflight needs the firmware
        string; a silent fallback would defeat X-03's purpose).
    """
    libqmi = await detect_libqmi_version(timeout_s=timeout_s)

    # Duck-typed: wrapper must have ``async def dms_get_revision() -> CompletedProcess``.
    # See Plan 05-01 SUMMARY for the production QmiWrapper.dms_get_revision signature.
    #
    # Phase 05.5: retry on transient qmi-proxy failures. When qmicli's CID
    # allocation races with Zao's concurrent NAS/UIM queries, qmicli exits
    # non-zero with stderr like "CID allocation failed ... Service mismatch
    # (requested 'dms', got 'nas')" or "endpoint hangup" and stdout empty.
    # The parser correctly returns UNEXPECTED_OUTPUT in that case (no
    # `Device revision retrieved` header in the empty body) but the actual
    # cause is upstream contention, not a parser issue. Retry up to
    # _FIRMWARE_PROBE_ATTEMPTS times with _FIRMWARE_PROBE_BACKOFF_S spacing
    # so the in-flight Zao request can release its CID.
    revision: str | None = None
    last_error: str = "unreachable"
    for attempt in range(_FIRMWARE_PROBE_ATTEMPTS):
        cp: CompletedProcess = await wrapper.dms_get_revision()  # type: ignore[attr-defined]
        if cp.exit_code != 0:
            stderr_excerpt = cp.stderr[:_STDERR_EXCERPT_BYTES]
            last_error = (
                f"qmicli exit_code={cp.exit_code} stderr={stderr_excerpt!r}"
            )
        else:
            parsed = parse_get_revision(cp.stdout)
            if isinstance(parsed, QmiError):
                last_error = (
                    f"parser returned QmiError: reason={parsed.reason.value} "
                    f"detail={parsed.detail!r}"
                )
            elif parsed.revision is None:
                last_error = (
                    "parser returned revision=None "
                    "(impossible if MISSING_FIELD raised)"
                )
            else:
                revision = parsed.revision
                break
        # Don't sleep after the final attempt — sleep is between retries only.
        if attempt < _FIRMWARE_PROBE_ATTEMPTS - 1:
            await asyncio.sleep(_FIRMWARE_PROBE_BACKOFF_S)

    if revision is None:
        raise QmiVersionDetectionFailed(
            f"dms_get_revision failed after {_FIRMWARE_PROBE_ATTEMPTS} attempts: "
            f"{last_error}"
        )

    zao_sdk = detect_zao_sdk_version(zao_log_path)

    return FleetTriple(
        em7421_firmware=revision,
        zao_sdk=zao_sdk if zao_sdk is not None else _ZAO_SDK_UNKNOWN_SENTINEL,
        libqmi=libqmi,
    )
