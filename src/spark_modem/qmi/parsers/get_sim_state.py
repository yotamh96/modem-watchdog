"""Parses `qmicli --uim-get-card-status` text output.

libqmi 1.30 output sample (ready)::

    [/dev/cdc-wdm0] Successfully got card status
    Slot [1]:
            Card state: 'present'
            Applications: '1'
                    Application [0]:
                            Application type:  'usim'
                            Application state: 'ready'
                            ICCID: '8997201700123456789'
                            IMSI: '425030123456789'

``card_state`` is required for the policy engine; absent → MISSING_FIELD.
``app_state`` / ``iccid`` / ``imsi`` are optional (libqmi omits them when
the card is power-down or absent).
"""

from __future__ import annotations

import re
from typing import Final

from pydantic import BaseModel, ConfigDict

from spark_modem.qmi.errors import QmiError, QmiErrorReason
from spark_modem.qmi.parsers._header import strip_header

_ARGV: Final[tuple[str, ...]] = ("qmicli", "--uim-get-card-status")

_RESPONSE_HEADER: Final[str] = "Successfully got card status"

_RE_CARD_STATE: Final[re.Pattern[str]] = re.compile(r"Card state:\s*'([^']+)'")
_RE_APP_STATE: Final[re.Pattern[str]] = re.compile(r"Application state:\s*'([^']+)'")
_RE_ICCID: Final[re.Pattern[str]] = re.compile(r"ICCID:\s*'([^']*)'")
_RE_IMSI: Final[re.Pattern[str]] = re.compile(r"IMSI:\s*'([^']*)'")


class GetSimStateResult(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    card_state: str | None = None
    app_state: str | None = None
    iccid: str | None = None
    imsi: str | None = None


def parse_get_sim_state(stdout: bytes) -> GetSimStateResult | QmiError:
    """Parse qmicli get-card-status text into typed result or QmiError."""
    body = strip_header(stdout).decode("utf-8", errors="replace")
    if _RESPONSE_HEADER not in body:
        return QmiError(
            reason=QmiErrorReason.UNEXPECTED_OUTPUT,
            argv=_ARGV,
            detail="no card-status block in stdout",
        )
    m_card = _RE_CARD_STATE.search(body)
    if m_card is None:
        return QmiError(
            reason=QmiErrorReason.MISSING_FIELD,
            argv=_ARGV,
            field="card_state",
            detail="Card state line absent from card-status block",
        )
    m_app = _RE_APP_STATE.search(body)
    m_iccid = _RE_ICCID.search(body)
    m_imsi = _RE_IMSI.search(body)
    return GetSimStateResult(
        card_state=m_card.group(1).strip().lower(),
        app_state=m_app.group(1).strip().lower() if m_app else None,
        iccid=m_iccid.group(1) if m_iccid else None,
        imsi=m_imsi.group(1) if m_imsi else None,
    )
