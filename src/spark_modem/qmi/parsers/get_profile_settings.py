"""Parses `qmicli --wds-get-profile-settings=3gpp,N` text output.

libqmi 1.30 output sample::

    [/dev/cdc-wdm0] Profile settings retrieved:
            Profile index: '1'
            APN: 'internet'
            IP family: 'ipv4'
            Authentication: 'none'

``profile_index`` is required (the call's whole point is to return profile
data; if the index is absent the response is structurally broken). ``apn``
is optional (an empty profile reports APN as the empty string '' or omits
the line entirely on some libqmi builds).
"""

from __future__ import annotations

import re
from typing import Final

from pydantic import BaseModel, ConfigDict

from spark_modem.qmi.errors import QmiError, QmiErrorReason
from spark_modem.qmi.parsers._header import strip_header

_ARGV: Final[tuple[str, ...]] = ("qmicli", "--wds-get-profile-settings")

_RESPONSE_HEADER: Final[str] = "Profile settings retrieved"

_RE_PROFILE_INDEX: Final[re.Pattern[str]] = re.compile(r"Profile index:\s*'(\d+)'")
_RE_APN: Final[re.Pattern[str]] = re.compile(r"APN:\s*'([^']*)'")
_RE_IP_FAMILY: Final[re.Pattern[str]] = re.compile(r"IP family:\s*'([^']+)'")

_IP_FAMILY_TO_INT: Final[dict[str, int]] = {
    "ipv4": 4,
    "ipv6": 6,
    "ipv4v6": 7,
    "ipv4-or-ipv6": 7,
}


class GetProfileSettingsResult(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    profile_index: int | None = None
    apn: str | None = None
    ip_family: int | None = None  # 4 / 6 / 7 (libqmi convention)


def parse_get_profile_settings(stdout: bytes) -> GetProfileSettingsResult | QmiError:
    """Parse qmicli get-profile-settings text into typed result or QmiError."""
    body = strip_header(stdout).decode("utf-8", errors="replace")
    if _RESPONSE_HEADER not in body:
        return QmiError(
            reason=QmiErrorReason.UNEXPECTED_OUTPUT,
            argv=_ARGV,
            detail="no profile-settings block in stdout",
        )
    m_idx = _RE_PROFILE_INDEX.search(body)
    if m_idx is None:
        return QmiError(
            reason=QmiErrorReason.MISSING_FIELD,
            argv=_ARGV,
            field="profile_index",
            detail="Profile index line absent from profile-settings block",
        )
    try:
        profile_index = int(m_idx.group(1))
    except (ValueError, TypeError) as exc:
        return QmiError(
            reason=QmiErrorReason.PARSE_ERROR,
            argv=_ARGV,
            detail=f"profile_index not numeric: {exc!r}",
        )

    m_apn = _RE_APN.search(body)
    m_ipf = _RE_IP_FAMILY.search(body)
    ip_family: int | None = None
    if m_ipf is not None:
        raw = m_ipf.group(1).strip().lower()
        ip_family = _IP_FAMILY_TO_INT.get(raw)

    return GetProfileSettingsResult(
        profile_index=profile_index,
        apn=m_apn.group(1) if m_apn else None,
        ip_family=ip_family,
    )
