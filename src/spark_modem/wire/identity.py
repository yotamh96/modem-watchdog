"""Identity map (ICCID/IMSI <-> usb_path).

Persisted as a single identity.json keyed by usb_path. SIM swap detection
(FR-4) compares stored ICCID against the live SIM at the same usb_path.
"""

from __future__ import annotations

from pydantic import Field

from spark_modem.wire._base import BaseWire
from spark_modem.wire.versioning import CURRENT_SCHEMA_VERSION

# USB path: integer-dot syntax matching sysfs (e.g. "2-3.1.1").
# Format: <bus>-<port>[.<port>...] where all parts are decimal integers.
_USB_PATH_PATTERN = r"^\d+(-\d+(\.\d+)*)?$"


class Identity(BaseWire):
    """One row of the identity map; keyed by usb_path in the parent map."""

    schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, ge=1)
    usb_path: str = Field(pattern=_USB_PATH_PATTERN, min_length=1, max_length=64)
    # ICCID: 18-22 decimal digits (ITU-T E.118).
    iccid: str = Field(pattern=r"^\d{18,22}$")
    # IMSI: 14-15 decimal digits (ITU-T E.212).
    imsi: str = Field(pattern=r"^\d{14,15}$")
    first_seen_iso: str
    last_seen_iso: str
