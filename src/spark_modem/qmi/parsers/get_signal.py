"""Parses `qmicli --nas-get-signal-info` text output.

libqmi 1.30 output sample (LTE only)::

    [/dev/cdc-wdm0] Successfully got signal info
    LTE:
            RSSI: '-65 dBm'
            RSRQ: '-9 dB'
            RSRP: '-94 dBm'
            SNR: '8.4 dB'

libqmi 1.32+ adds an optional NR5G section above LTE (sometimes without
RSSI). The parser is version-agnostic; ``ConfigDict(extra='ignore')``
absorbs new fields. Required fields that are structurally absent surface as
``QmiError(reason=MISSING_FIELD)`` rather than silent ``None``.
"""

from __future__ import annotations

import re
from typing import Final

from pydantic import BaseModel, ConfigDict

from spark_modem.qmi.errors import QmiError, QmiErrorReason
from spark_modem.qmi.parsers._header import strip_header

_ARGV: Final[tuple[str, ...]] = ("qmicli", "--nas-get-signal-info")


class GetSignalResult(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    rssi_dbm: int | None = None
    rsrp_dbm: int | None = None
    rsrq_db: float | None = None
    snr_db: float | None = None


# Anchor each capture on a single line; ``re.MULTILINE`` lets ``^`` match the
# start of a line so an LTE block doesn't bleed RSSI from a stale NR5G block.
_RE_RSSI: Final[re.Pattern[str]] = re.compile(r"RSSI:\s*'(-?\d+)\s*dBm'")
_RE_RSRP: Final[re.Pattern[str]] = re.compile(r"RSRP:\s*'(-?\d+)\s*dBm'")
_RE_RSRQ: Final[re.Pattern[str]] = re.compile(r"RSRQ:\s*'(-?\d+(?:\.\d+)?)\s*dB'")
_RE_SNR: Final[re.Pattern[str]] = re.compile(r"SNR:\s*'(-?\d+(?:\.\d+)?)\s*dB'")


def _success_marker_present(body: str) -> bool:
    """Return True if the body looks like a Successfully-got-signal response."""
    return (
        "Successfully got signal info" in body
        or "Signal info retrieved" in body
        or "LTE:" in body
        or "NR5G:" in body
    )


def parse_get_signal(stdout: bytes) -> GetSignalResult | QmiError:
    """Parse qmicli get-signal-info text into a GetSignalResult or QmiError."""
    body = strip_header(stdout).decode("utf-8", errors="replace")
    if not _success_marker_present(body):
        return QmiError(
            reason=QmiErrorReason.UNEXPECTED_OUTPUT,
            argv=_ARGV,
            detail="no signal block in stdout",
        )
    m_rssi = _RE_RSSI.search(body)
    m_rsrp = _RE_RSRP.search(body)
    m_rsrq = _RE_RSRQ.search(body)
    m_snr = _RE_SNR.search(body)
    try:
        return GetSignalResult(
            rssi_dbm=int(m_rssi.group(1)) if m_rssi else None,
            rsrp_dbm=int(m_rsrp.group(1)) if m_rsrp else None,
            rsrq_db=float(m_rsrq.group(1)) if m_rsrq else None,
            snr_db=float(m_snr.group(1)) if m_snr else None,
        )
    except (ValueError, TypeError) as exc:
        return QmiError(
            reason=QmiErrorReason.PARSE_ERROR,
            argv=_ARGV,
            detail=f"signal numeric coercion failed: {exc!r}",
        )
