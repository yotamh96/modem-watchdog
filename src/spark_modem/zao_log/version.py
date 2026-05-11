"""Zao SDK version detection — parses the Zao log banner (Phase 5 X-03).

RESEARCH Q3 spike outcome (A2 in RESEARCH § Assumptions Log): the Zao
SDK does not have a universal version-detection mechanism, but newer
builds write a startup banner near the top of the log. This module
scans the first ``_HEAD_BYTES`` bytes of the Zao log file for two
candidate banner shapes; if neither matches, returns ``None``.

Returning ``None`` is acceptable: the caller (Plan 04 preflight,
Plan 03 capture-fleet-fixture) handles ``None`` by either treating
the SDK component as ``"unknown"`` (preflight: fail closed; capture:
record ``"unknown"`` in ``triple.json`` so the operator can investigate).

The ``dpkg-query`` subprocess fallback (RESEARCH Q3 §295) is NOT
implemented in this plan — it would add a new subprocess dependency
for marginal coverage. Deferred to a future ADR if banner-absent
becomes a fleet-wide observation.

Pure I/O; no subprocess. SP-04 lint scope applies but is trivially
satisfied (file read only).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

# Two banner candidates, scanned in priority order:
#   1. ``zao_remote_endpoint/X.Y.Z`` — modern shape (post-2.0).
#   2. ``zao-remote-endpoint X.Y.Z`` — legacy shape.
# Regex compiled at import; matches first occurrence in head-window.
_ZAO_BANNER_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"zao_remote_endpoint/(\d+\.\d+\.\d+)"),
    re.compile(r"zao-remote-endpoint\s+(\d+\.\d+\.\d+)"),
)

# Read cap: 64 KiB of the log head. The banner, if present, appears on
# the first few lines of the file (within the first ~256 bytes); 64 KiB
# is a wide safety margin without OOM risk (T-05-02-01 mitigation pin).
_HEAD_BYTES: Final[int] = 64 * 1024


def detect_zao_sdk_version(zao_log_path: Path) -> str | None:
    """Return the Zao SDK version string (e.g. ``'2.1.0'``) or ``None``.

    Returns ``None`` when:
      - the file does not exist
      - I/O fails (logged at WARNING)
      - the file head contains no recognised banner

    Never raises. I/O errors are logged at WARNING and treated as
    absent-banner (``None``). The caller decides downstream policy.
    """
    try:
        with zao_log_path.open("rb") as fh:
            head = fh.read(_HEAD_BYTES)
    except FileNotFoundError:
        logger.warning("zao log not found at %s; SDK version = None", zao_log_path)
        return None
    except OSError as exc:
        logger.warning(
            "zao log read failed at %s: %s; SDK version = None", zao_log_path, exc
        )
        return None

    text = head.decode("utf-8", errors="replace")
    for pat in _ZAO_BANNER_PATTERNS:
        m = pat.search(text)
        if m is not None:
            return m.group(1)
    return None
