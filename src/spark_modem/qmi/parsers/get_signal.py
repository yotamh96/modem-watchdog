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


# WR-04 (Phase 2 review): document the actual semantics — "first match in
# document order across the whole stdout".  ``re.search`` returns the
# earliest occurrence regardless of band-section heading, so on a
# libqmi 1.32+ NR5G+LTE response the NR5G block wins for RSRP/RSRQ/SNR
# and the LTE block wins for RSSI (NR5G typically omits RSSI).  EM7421 is
# LTE-only hardware (PROJECT.md "Hardware target") so this never fires
# in production; the canonical NR5G+LTE fixture
# ``tests/fixtures/qmicli/get_signal/1.32/nr5g_present.txt`` locks the
# observable semantics for both the parser and any future reader.
#
# A future change that needs band-aware extraction (e.g. multi-band
# Sierra successor) should split the body on ``^(LTE|NR5G):$`` first and
# search inside the LTE section, NOT add ``re.MULTILINE`` here — line
# anchoring alone does not fix the cross-section bleed (``re.search``
# would still return the first match across the whole input).
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
