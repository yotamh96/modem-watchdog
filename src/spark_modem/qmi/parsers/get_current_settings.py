"""Parses `qmicli --wds-get-current-settings` text output.

libqmi 1.30 output sample (raw IP)::

    [/dev/cdc-wdm0] Current settings retrieved:
            IP Family: 'ipv4'
            IPv4 address: '10.69.92.156'
            IPv4 subnet mask: '255.255.255.248'
            IPv4 gateway address: '10.69.92.150'
            Raw IP: 'Y'

``raw_ip`` reports as 'Y' / 'N' / '?'. When 'N', the data path is broken
(packets are framed as Ethernet but the qmi_wwan driver expects raw IP);
this triggers ``fix_raw_ip`` recovery (RECOVERY_SPEC §4 row datapath/raw_ip_off).
"""

from __future__ import annotations

import re
from typing import Final

from pydantic import BaseModel, ConfigDict

from spark_modem.qmi.errors import QmiError, QmiErrorReason
from spark_modem.qmi.parsers._header import strip_header

_ARGV: Final[tuple[str, ...]] = ("qmicli", "--wds-get-current-settings")

_RESPONSE_HEADER: Final[str] = "Current settings retrieved"

_RE_IPV4_ADDR: Final[re.Pattern[str]] = re.compile(r"IPv4 address:\s*'([^']+)'")
_RE_RAW_IP: Final[re.Pattern[str]] = re.compile(r"Raw IP:\s*'([YN?])'")


class GetCurrentSettingsResult(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    ipv4: str | None = None
    raw_ip: str | None = None  # 'Y' | 'N' | '?'


def parse_get_current_settings(stdout: bytes) -> GetCurrentSettingsResult | QmiError:
    """Parse qmicli get-current-settings text into typed result or QmiError."""
    body = strip_header(stdout).decode("utf-8", errors="replace")
    if _RESPONSE_HEADER not in body:
        return QmiError(
            reason=QmiErrorReason.UNEXPECTED_OUTPUT,
            argv=_ARGV,
            detail="no current-settings block in stdout",
        )
    m_ipv4 = _RE_IPV4_ADDR.search(body)
    m_raw = _RE_RAW_IP.search(body)
    return GetCurrentSettingsResult(
        ipv4=m_ipv4.group(1) if m_ipv4 else None,
        raw_ip=m_raw.group(1) if m_raw else None,
    )
