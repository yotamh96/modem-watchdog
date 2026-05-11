"""Parses `qmicli --dms-get-revision` text output.

libqmi 1.30 output sample::

    [/dev/cdc-wdm0] Device revisions retrieved:
            Revision: 'SWI9X30C_02.38.00.00'
            Boot code: 'SWI9X30C_02.38.00.00'

``revision`` is required for X-02 fleet-fixture capture (Phase 5
CONTEXT.md); absent → MISSING_FIELD.
"""

from __future__ import annotations

import re
from typing import Final

from pydantic import BaseModel, ConfigDict

from spark_modem.qmi.errors import QmiError, QmiErrorReason
from spark_modem.qmi.parsers._header import strip_header

_ARGV: Final[tuple[str, ...]] = ("qmicli", "--dms-get-revision")

_RESPONSE_HEADER: Final[str] = "Device revisions retrieved"

_RE_REVISION: Final[re.Pattern[str]] = re.compile(r"Revision:\s*'([^']+)'")


class GetRevisionResult(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    revision: str | None = None


def parse_get_revision(stdout: bytes) -> GetRevisionResult | QmiError:
    """Parse qmicli get-revision text into typed result or QmiError."""
    body = strip_header(stdout).decode("utf-8", errors="replace")
    if _RESPONSE_HEADER not in body:
        return QmiError(
            reason=QmiErrorReason.UNEXPECTED_OUTPUT,
            argv=_ARGV,
            detail="no revisions block in stdout",
        )
    m = _RE_REVISION.search(body)
    if m is None:
        return QmiError(
            reason=QmiErrorReason.MISSING_FIELD,
            argv=_ARGV,
            field="revision",
            detail="Revision line absent from revisions block",
        )
    # Firmware strings are case-sensitive (SWI9X30C_02.38.00.00); do NOT
    # lower-case (contrast with parse_get_operating_mode which lower-cases
    # mode).
    return GetRevisionResult(revision=m.group(1).strip())
