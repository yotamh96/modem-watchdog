"""Parses `qmicli --dms-get-operating-mode` text output.

libqmi 1.30 output sample::

    [/dev/cdc-wdm0] Operating mode retrieved:
            Mode: 'online'
            HW restricted: 'no'

``mode`` is required for the policy engine (it gates the OPERATING_MODE_*
issue detail family in RECOVERY_SPEC §4); absent → MISSING_FIELD.
"""

from __future__ import annotations

import re
from typing import Final

from pydantic import BaseModel, ConfigDict

from spark_modem.qmi.errors import QmiError, QmiErrorReason
from spark_modem.qmi.parsers._header import strip_header

_ARGV: Final[tuple[str, ...]] = ("qmicli", "--dms-get-operating-mode")

_RESPONSE_HEADER: Final[str] = "Operating mode retrieved"

_RE_MODE: Final[re.Pattern[str]] = re.compile(r"Mode:\s*'([^']+)'")


class GetOperatingModeResult(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    mode: str | None = None


def parse_get_operating_mode(stdout: bytes) -> GetOperatingModeResult | QmiError:
    """Parse qmicli get-operating-mode text into typed result or QmiError."""
    body = strip_header(stdout).decode("utf-8", errors="replace")
    if _RESPONSE_HEADER not in body:
        return QmiError(
            reason=QmiErrorReason.UNEXPECTED_OUTPUT,
            argv=_ARGV,
            detail="no operating-mode block in stdout",
        )
    m = _RE_MODE.search(body)
    if m is None:
        return QmiError(
            reason=QmiErrorReason.MISSING_FIELD,
            argv=_ARGV,
            field="mode",
            detail="Mode line absent from operating-mode block",
        )
    return GetOperatingModeResult(mode=m.group(1).strip().lower())
