"""kmsg classifier — regex matrix mapping kernel lines to IssueDetail (E-03).

The 5 enum values (``USB_OVERCURRENT``, ``USB_ENUM_FAILURE``,
``THERMAL_THROTTLE``, ``QMI_WWAN_PROBE_FAIL``, ``TEGRA_HUB_PSU_DROOP``)
are LOCKED per CONTEXT.md E-03; regex strings are Claude's-discretion
data and may iterate based on bench-Jetson observation. Add new
regex/enum pairs ONLY via ADR or Phase 4 follow-up; never bury new enum
values without trace.

UNKNOWN is the fallback — the producer preserves the raw line in a
separate forensic field and discards the UNKNOWN classification (no
Issue emitted). W-04 closed-enum discipline.
"""

from __future__ import annotations

import re
from typing import Final

from spark_modem.wire.enums import IssueDetail

# Source: regex shapes derived from Linux kernel sources
# (drivers/usb/core/{hub.c,driver.c}) and Tegra L4T kernel patches; treat
# as data, not contract — bench-Jetson observation may iterate the
# patterns. The IssueDetail enum members on the right side are LOCKED
# (E-03); only the regex on the left side is Claude's discretion.
KMSG_PATTERNS: Final[tuple[tuple[re.Pattern[str], IssueDetail], ...]] = (
    (
        # Real Linux kernel writes ``usb 1-3.1: device not accepting
        # address 17`` (lowercase ``usb``); RESEARCH.md cited the
        # capital-``USB`` shape. Case-insensitive flag tolerates both.
        re.compile(r"usb \S+: device not accepting address", re.IGNORECASE),
        IssueDetail.USB_ENUM_FAILURE,
    ),
    (
        re.compile(r"over-current.*on port", re.IGNORECASE),
        IssueDetail.USB_OVERCURRENT,
    ),
    (
        re.compile(r"thermal.*throttl(ing|ed)", re.IGNORECASE),
        IssueDetail.THERMAL_THROTTLE,
    ),
    (
        re.compile(r"qmi_wwan.*probe.*fail(ed)?", re.IGNORECASE),
        IssueDetail.QMI_WWAN_PROBE_FAIL,
    ),
    (
        re.compile(r"tegra-xusb.*power.*loss", re.IGNORECASE),
        IssueDetail.TEGRA_HUB_PSU_DROOP,
    ),
)


def classify(line: str) -> IssueDetail:
    """Return the canonical IssueDetail for a kernel ring-buffer line.

    Scans ``KMSG_PATTERNS`` in order; first match wins (deterministic
    iteration order per the tuple definition). When no pattern matches
    returns ``IssueDetail.UNKNOWN``; the caller (kmsg_producer)
    preserves the raw line in a separate forensic field for debugging
    and discards the UNKNOWN classification — no Issue is emitted.
    W-04 closed-enum discipline preserved.
    """
    for pattern, detail in KMSG_PATTERNS:
        if pattern.search(line):
            return detail
    return IssueDetail.UNKNOWN
