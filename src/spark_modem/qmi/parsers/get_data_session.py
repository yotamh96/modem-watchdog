"""Parses `qmicli --wds-get-packet-service-status` text output.

libqmi 1.30 output sample::

    [/dev/cdc-wdm0] Connection status: 'connected'

The qmicli short form prints a single ``Connection status: '...'`` line.
``connection_status`` is structurally optional (the call rarely fails to
include it, but if it does the parser surfaces UNEXPECTED_OUTPUT).
"""

from __future__ import annotations

import re
from typing import Final

from pydantic import BaseModel, ConfigDict

from spark_modem.qmi.errors import QmiError, QmiErrorReason
from spark_modem.qmi.parsers._header import strip_header

_ARGV: Final[tuple[str, ...]] = ("qmicli", "--wds-get-packet-service-status")

_RE_CONNECTION_STATUS: Final[re.Pattern[str]] = re.compile(r"Connection status:\s*'([^']+)'")


class GetDataSessionResult(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    connection_status: str | None = None


def parse_get_data_session(stdout: bytes) -> GetDataSessionResult | QmiError:
    """Parse qmicli get-packet-service-status text into typed result or QmiError."""
    body = strip_header(stdout).decode("utf-8", errors="replace")
    m = _RE_CONNECTION_STATUS.search(body)
    if m is None:
        return QmiError(
            reason=QmiErrorReason.UNEXPECTED_OUTPUT,
            argv=_ARGV,
            detail="no Connection status line in stdout",
        )
    return GetDataSessionResult(connection_status=m.group(1).strip().lower())
