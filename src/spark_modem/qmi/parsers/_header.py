"""Fixture-only header reader: extracts `# libqmi_version: <ver>` from line 1.

Production qmicli stdout never has this header; only fixture files do. The
parsers themselves do not call this directly to look up the version (they are
version-agnostic via `extra='ignore'`); they only call ``strip_header`` to
remove the version comment line before parsing the body.

The test parametrizer uses ``libqmi_version_of`` to label each fixture run
in pytest output (e.g. ``[get_signal-1.30-lte_strong]``).
"""

from __future__ import annotations

import re
from typing import Final

_HEADER_RE: Final[re.Pattern[bytes]] = re.compile(rb"^# libqmi_version:\s*([0-9.]+)\s*$")


def libqmi_version_of(text: bytes) -> str | None:
    """Return the libqmi version string from line 1 of a fixture body.

    Returns '1.30' / '1.32' / ... or None when absent (production stdout).
    """
    first_line = text.split(b"\n", 1)[0]
    m = _HEADER_RE.match(first_line)
    return m.group(1).decode("ascii") if m else None


def strip_header(text: bytes) -> bytes:
    """Strip the `# libqmi_version: <ver>` header line from a fixture body.

    If no header is present (production qmicli stdout), the input is returned
    unchanged. If the header is present but the body has no further newline,
    an empty bytes is returned.
    """
    if libqmi_version_of(text) is None:
        return text
    if b"\n" not in text:
        return b""
    return text.split(b"\n", 1)[1]
