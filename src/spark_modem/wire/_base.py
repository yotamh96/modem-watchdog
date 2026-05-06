"""Base wire model.

Every persisted-or-transmitted wire shape inherits BaseWire. This is the
*strict* wire boundary: frozen to prevent post-construction mutation,
extra='forbid' to reject unknown fields, populate_by_name to accept
both attribute names and aliases on input.

The qmicli output parser in `qmi/parsers/` (Phase 2) uses extra='ignore'
instead — see CONTEXT.md W-02 boundary split.
"""

from pydantic import BaseModel, ConfigDict


class BaseWire(BaseModel):
    """Strict wire base: frozen, extra=forbid, populate_by_name."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
    )
