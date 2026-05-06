"""Carrier table (MCC, MNC -> APN lookup).

FR-30 / FR-30.1 / FR-33 / FR-33.1: editable without code release; loads from
/etc/spark-modem-watchdog/conf.d/00-carriers.yaml; hostile-input fixtures
cover the YAML "Norway problem", leading-zero MNCs, MNC-as-int, etc.
"""

from __future__ import annotations

from pydantic import Field, StrictStr

from spark_modem.wire._base import BaseWire
from spark_modem.wire.versioning import CURRENT_SCHEMA_VERSION


class CarrierEntry(BaseWire):
    """One row of the carrier table."""

    # ISO 3166-1 alpha-2; canonical form is uppercase. We REJECT mixed-case
    # rather than coerce — input cleanliness over tolerance for the wire.
    country: StrictStr = Field(pattern=r"^[A-Z]{2}$")

    # ITU-T E.212 MCC: exactly 3 decimal digits, persisted as a string so YAML's
    # number coercion can't strip a leading zero (PITFALLS §11.2).
    mcc: StrictStr = Field(pattern=r"^\d{3}$")

    # MNC: 2 or 3 decimal digits as a string. `mnc: 01` (leading zero) MUST be
    # written as a quoted string in YAML; a bare `01` is an octal literal in
    # YAML 1.1 — the StrictStr rejects an int with a clear "must be a string"
    # error.
    mnc: StrictStr = Field(pattern=r"^\d{2,3}$")

    apn: StrictStr = Field(min_length=1, max_length=63)
    carrier_name: StrictStr = Field(min_length=1, max_length=63)
    unverified: bool = False


class CarrierTable(BaseWire):
    """Full carrier table; loaded from YAML and validated at daemon start."""

    schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, ge=1)
    carriers: list[CarrierEntry]
