"""ctl config-check — pre-flight Settings + HMAC secret validate (U-05 / L-05).

Run by systemd ExecStartPre BEFORE the main daemon boots. Surface clear
structured errors to stderr; return non-zero exit so systemd fails the
unit start before StartLimitBurst is consumed (PITFALLS §4.2).

L-05 checks the HMAC secret file:
  (a) exists at the path Settings.resolve_hmac_secret_path() returns,
  (b) is NOT the placeholder sentinel (L-03 writes this; operator must
      replace before first start),
  (c) is mode 0600, owner root, group root (NFR-30 / ADR-0011),
  (d) is non-empty.

All four failures emit a distinct `config-check: ...` message to stderr.
Exit codes:
  0 — green
  2 — any validation failure
"""

from __future__ import annotations

import argparse
import os
import stat
import sys

from pydantic import ValidationError

from spark_modem.config.settings import Settings

_HMAC_PLACEHOLDER_SENTINEL = b"REPLACE_THIS_BEFORE_FIRST_START_SEE_RUNBOOK\n"
_MODE_0600 = 0o600


async def run(args: argparse.Namespace) -> int:  # noqa: PLR0911
    """Validate Settings + HMAC secret. Return 0 on green, 2 on any failure."""
    del args  # config-check takes no flags

    # (1) Settings construct — surfaces env-var/YAML validation failures.
    try:
        settings = Settings()
    except ValidationError as exc:
        print(f"config-check: settings invalid: {exc}", file=sys.stderr)
        return 2

    # (2) HMAC secret path resolution + existence check.
    secret_path = settings.resolve_hmac_secret_path()
    try:
        st = os.stat(secret_path)  # noqa: PTH116
    except FileNotFoundError:
        print(
            f"config-check: HMAC secret file not found at {secret_path} "
            f"(L-03 postinst placeholder missing; reinstall or hand-provision)",
            file=sys.stderr,
        )
        return 2
    except PermissionError as exc:
        print(
            f"config-check: HMAC secret file at {secret_path} unreadable: {exc}",
            file=sys.stderr,
        )
        return 2

    # (3) Size / placeholder check.
    if st.st_size == 0:
        print(
            f"config-check: HMAC secret file at {secret_path} is empty",
            file=sys.stderr,
        )
        return 2
    try:
        content = secret_path.read_bytes()
    except OSError as exc:
        print(
            f"config-check: HMAC secret file at {secret_path} unreadable: {exc}",
            file=sys.stderr,
        )
        return 2
    if content == _HMAC_PLACEHOLDER_SENTINEL:
        print(
            f"config-check: HMAC secret file at {secret_path} contains the "
            f"placeholder sentinel — operator must replace before first start "
            f"(see docs/RUNBOOK.md HMAC-secret provisioning).",
            file=sys.stderr,
        )
        return 2

    # (4) Mode + ownership check (NFR-30 / ADR-0011 "root-only").
    if stat.S_IMODE(st.st_mode) != _MODE_0600:
        print(
            f"config-check: HMAC secret file at {secret_path} has mode "
            f"{oct(stat.S_IMODE(st.st_mode))}; expected 0o600 (0600 root:root)",
            file=sys.stderr,
        )
        return 2
    if st.st_uid != 0 or st.st_gid != 0:
        print(
            f"config-check: HMAC secret file at {secret_path} has owner "
            f"{st.st_uid}:{st.st_gid}; expected 0:0 (root:root)",
            file=sys.stderr,
        )
        return 2

    # All checks passed.
    print(f"config-check: OK ({secret_path}, mode 0600 root:root, {st.st_size} bytes)")
    return 0
