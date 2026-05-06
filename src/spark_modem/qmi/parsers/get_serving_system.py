"""Parses `qmicli --nas-get-serving-system` text output.

libqmi 1.30 output sample (registered home)::

    [/dev/cdc-wdm0] Successfully got serving system:
            Registration state: 'registered'
            CS: 'detached'
            PS: 'attached'
            Roaming status: 'off'
            Current PLMN:
                    MCC: '425'
                    MNC: '03'
                    Description: 'Pelephone'

The parser maps the qmicli ``Registration state`` + ``Roaming status`` pair
to ``wire.enums.RegistrationState``: 'registered' + roaming='off' →
REGISTERED_HOME; 'registered' + roaming='on' → REGISTERED_ROAMING; the
not-registered variants map directly. Returns ``QmiError(MISSING_FIELD)`` if
``Registration state`` is structurally absent (the policy engine depends on
it).
"""

from __future__ import annotations

import re
from typing import Final

from pydantic import BaseModel, ConfigDict

from spark_modem.qmi.errors import QmiError, QmiErrorReason
from spark_modem.qmi.parsers._header import strip_header
from spark_modem.wire.enums import RegistrationState

_ARGV: Final[tuple[str, ...]] = ("qmicli", "--nas-get-serving-system")

_RESPONSE_HEADER: Final[str] = "Successfully got serving system"

_RE_REG_STATE: Final[re.Pattern[str]] = re.compile(r"Registration state:\s*'([^']+)'")
_RE_ROAMING: Final[re.Pattern[str]] = re.compile(r"Roaming status:\s*'([^']+)'")
_RE_MCC: Final[re.Pattern[str]] = re.compile(r"MCC:\s*'(\d+)'")
_RE_MNC: Final[re.Pattern[str]] = re.compile(r"MNC:\s*'(\d+)'")
_RE_DESCRIPTION: Final[re.Pattern[str]] = re.compile(r"Description:\s*'([^']*)'")

_REG_TO_ENUM: Final[dict[tuple[str, str], RegistrationState]] = {
    ("registered", "off"): RegistrationState.REGISTERED_HOME,
    ("registered", "on"): RegistrationState.REGISTERED_ROAMING,
    ("not-registered-searching", "off"): RegistrationState.NOT_REGISTERED_SEARCHING,
    ("not-registered-searching", "on"): RegistrationState.NOT_REGISTERED_SEARCHING,
    ("not-registered-idle", "off"): RegistrationState.NOT_REGISTERED_IDLE,
    ("not-registered-idle", "on"): RegistrationState.NOT_REGISTERED_IDLE,
    ("denied", "off"): RegistrationState.NOT_REGISTERED_DENIED,
    ("denied", "on"): RegistrationState.NOT_REGISTERED_DENIED,
    ("not-registered-denied", "off"): RegistrationState.NOT_REGISTERED_DENIED,
    ("not-registered-denied", "on"): RegistrationState.NOT_REGISTERED_DENIED,
}


class GetServingSystemResult(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    registration_state: RegistrationState | None = None
    mcc: str | None = None
    mnc: str | None = None
    description: str | None = None


def parse_get_serving_system(stdout: bytes) -> GetServingSystemResult | QmiError:
    """Parse qmicli get-serving-system text into typed result or QmiError."""
    body = strip_header(stdout).decode("utf-8", errors="replace")
    if _RESPONSE_HEADER not in body:
        return QmiError(
            reason=QmiErrorReason.UNEXPECTED_OUTPUT,
            argv=_ARGV,
            detail="no serving-system block in stdout",
        )
    m_reg = _RE_REG_STATE.search(body)
    if m_reg is None:
        return QmiError(
            reason=QmiErrorReason.MISSING_FIELD,
            argv=_ARGV,
            field="registration_state",
            detail="Registration state line absent from output",
        )
    raw_reg = m_reg.group(1).strip().lower()
    m_roam = _RE_ROAMING.search(body)
    raw_roam = m_roam.group(1).strip().lower() if m_roam else "off"
    enum_value = _REG_TO_ENUM.get((raw_reg, raw_roam), RegistrationState.UNKNOWN)

    m_mcc = _RE_MCC.search(body)
    m_mnc = _RE_MNC.search(body)
    m_desc = _RE_DESCRIPTION.search(body)
    return GetServingSystemResult(
        registration_state=enum_value,
        mcc=m_mcc.group(1) if m_mcc else None,
        mnc=m_mnc.group(1) if m_mnc else None,
        description=m_desc.group(1) if m_desc else None,
    )
