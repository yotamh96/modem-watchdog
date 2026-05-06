"""ModemDescriptor - the (line, cdc_wdm, usb_path, ns, iface) 5-tuple per FR-2."""

from __future__ import annotations

from pydantic import Field

from spark_modem.wire._base import BaseWire


class ModemDescriptor(BaseWire):
    """One detected modem from inventory.

    Fields are FR-2 verbatim: line / cdc_wdm / usb_path / ns / iface.
    ADR-0009 keying: usb_path is the canonical identity; cdc_wdm renumbers
    across reboots and must not be used for state-file naming.
    """

    line: int = Field(ge=1, le=99, description="Zao line index, 1..N")
    cdc_wdm: str = Field(pattern=r"^cdc-wdm\d+$")
    usb_path: str = Field(min_length=1, max_length=64)
    ns: str | None = Field(default=None, description="netns name (e.g. 'line1') or None")
    iface: str | None = Field(default=None, description="netif name (e.g. 'wwan0') or None")
