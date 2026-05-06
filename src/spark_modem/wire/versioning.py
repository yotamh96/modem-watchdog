"""Schema versioning + non-destructive downgrade.

ADR-0004 (amended in Plan 07): downgrade is non-destructive. A file that
declares schema_version < CURRENT_SCHEMA_VERSION is preserved as
`<original>.from-v<N>.json`; the daemon writes a fresh-default file at
its own version and emits a structured `schema_downgrade_pending` event.

A file that declares schema_version > CURRENT_SCHEMA_VERSION is refused;
the caller (state_store.load) raises SchemaVersionTooNew so the daemon
can refuse to start (FR-63 — invalid input is logged error, not crash).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

CURRENT_SCHEMA_VERSION: int = 1
"""Bump on any schema-incompatible change. Phase 1 ships v1; Phase 2+ may bump."""


class SchemaVersionTooNew(Exception):  # noqa: N818
    """Raised when a persisted file declares a schema_version > CURRENT_SCHEMA_VERSION.

    The daemon refuses to load forward-version files (NFR-43). Caller's
    recovery is `ctl reset-state --modem=<usb_path>` or operator manual
    intervention.

    N818: exception named *TooNew* not *Error* — deliberate API contract
    (plan must_haves require this exact name).
    """

    def __init__(self, *, seen: int, current: int, where: str = "<unknown>") -> None:
        self.seen = seen
        self.current = current
        self.where = where
        super().__init__(
            f"Schema version {seen} > current {current} at {where}; refusing to load (NFR-43)."
        )


SchemaVersionDecision = Literal["current", "downgrade"]


def validate_schema_version(
    *, file_version: int, where: str = "<unknown>"
) -> SchemaVersionDecision:
    """Compare a file's declared schema_version to CURRENT_SCHEMA_VERSION.

    Returns:
      - "current"   when file_version == CURRENT_SCHEMA_VERSION
      - "downgrade" when file_version < CURRENT_SCHEMA_VERSION
        (caller writes the .from-v<N>.json shadow and a fresh default at v<current>)

    Raises SchemaVersionTooNew on file_version > CURRENT_SCHEMA_VERSION.
    """
    if file_version > CURRENT_SCHEMA_VERSION:
        raise SchemaVersionTooNew(seen=file_version, current=CURRENT_SCHEMA_VERSION, where=where)
    if file_version == CURRENT_SCHEMA_VERSION:
        return "current"
    return "downgrade"


def shadow_filename(original: str | Path, *, from_version: int) -> Path:
    """Compute the shadow filename for a non-destructive downgrade.

    e.g. shadow_filename("/var/lib/.../2-3.1.1.json", from_version=0)
         == Path("/var/lib/.../2-3.1.1.from-v0.json")
    """
    p = Path(original)
    # Replace the last suffix (e.g. .json) with .from-v<N>.json.
    suffix = p.suffix or ".json"
    return p.with_suffix(f".from-v{from_version}{suffix}")
