"""QMI error data class -- 'all errors are data' (SP-02 carry-forward).

Every qmicli outcome that is not a healthy success is represented as a typed
QmiError carrying enough structured detail (reason enum, argv, exit_code,
stderr_excerpt, optional field name) for downstream policy/ to branch on the
specific failure reason without parsing free-form text.

PROXY_DIED is special: PITFALLS §1.1 requires a short-circuit so the policy
engine can choose driver_reset rather than retrying against a broken
qmi-proxy (RECOVERY_SPEC §6.4 extension). The `_PROXY_DIED_SIGNATURES` matcher
in `wrapper.py` scans stderr for the canonical phrases libqmi emits when the
proxy is gone.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class QmiErrorReason(StrEnum):
    """Closed enum of QMI failure reasons (PITFALLS §1.1 / §1.2)."""

    PROXY_DIED = "proxy_died"  # qmi-proxy crashed mid-call (PITFALLS §1.1)
    PROXY_UNAVAILABLE = "proxy_unavailable"
    TIMEOUT = "timeout"  # subproc CompletedProcess.timed_out=True
    NON_ZERO_EXIT = "non_zero_exit"  # qmicli exited non-zero
    PARSE_ERROR = "parse_error"  # qmicli output was structurally invalid
    MISSING_FIELD = "missing_field"  # required field absent from output
    UNEXPECTED_OUTPUT = "unexpected_output"


@dataclass(frozen=True, slots=True)
class QmiError:
    """Typed failure record returned by QmiWrapper.classify() and parsers.

    Frozen + slots: cheap to allocate, immutable, mypy-friendly. argv is a
    tuple so the QmiError can be safely passed across async tasks without
    aliasing concerns.

    Attributes:
        reason: The QmiErrorReason enum variant.
        argv: Argv list of the qmicli call that produced the error.
        exit_code: subprocess exit code (None for parser-only errors).
        stderr_excerpt: At most 512 bytes of stderr (T-02-02-01 mitigation:
            bounds memory and avoids exporting large device-state dumps).
        field: For MISSING_FIELD, the structurally-absent field name.
        detail: Free-form supplementary detail (parser context, etc.).
    """

    reason: QmiErrorReason
    argv: tuple[str, ...]
    exit_code: int | None = None
    stderr_excerpt: str = ""
    field: str | None = None  # for MISSING_FIELD
    detail: str = ""
