"""Resolve the Git LFS pointer at ``tests/fixtures/replay/v1-30d/``.

Pulls a privacy-redacted snapshot of >=30 days of v1 historical traces
for the HIL replay-harness 30-day agreement gate (Phase 4 SC#4).

Per Phase 4 CONTEXT D-03:

- Sha256[:8]-redacted ICCID/IMSI/IP (same shape as Plan 02-09's
  ``ctl support-bundle``).
- HIL job invokes this in the setup phase; replay-harness from Plan
  02-10 consumes the pulled directory.
- FAILS CLEARLY on missing LFS auth (no silent skip).
- Quarterly refresh cadence documented in
  ``tests/fixtures/replay/v1-30d/README.md``.

## Subprocess discipline

This is a ``tools/`` script (NOT under ``src/spark_modem/``); SP-04 lint
scope excludes anything outside ``src/`` (see
``scripts/lint_no_subprocess.sh:11``). Direct ``subprocess.run`` is
acceptable here.

## Exit codes

- ``0`` -- LFS pull succeeded (or already-up-to-date).
- ``1`` -- LFS not installed, auth failure, or other operational error.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_LFS_DIR = Path("tests/fixtures/replay/v1-30d")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=("Pull v1-30d replay traces from Git LFS for the HIL replay-harness gate."),
    )
    parser.add_argument(
        "--include",
        type=str,
        default=str(_LFS_DIR),
        help="LFS path to pull (default: tests/fixtures/replay/v1-30d/).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (default: cwd).",
    )
    args = parser.parse_args(argv)

    # Verify git-lfs is installed. ``git`` is resolved via PATH on the HIL
    # runner (standard CI tooling); S607 is accepted here because the argv
    # is fully literal and not derived from untrusted input.
    try:
        cp_lfs_check = subprocess.run(
            ["git", "lfs", "version"],  # noqa: S607
            capture_output=True,
            text=True,
            cwd=args.repo_root,
            check=False,
        )
    except FileNotFoundError:
        print(
            "pull_replay_traces: git-lfs not installed. "
            "Install on the HIL runner via "
            "`apt install git-lfs && git lfs install`.",
            file=sys.stderr,
        )
        return 1
    if cp_lfs_check.returncode != 0:
        print(
            f"pull_replay_traces: git-lfs check failed:\n{cp_lfs_check.stderr}",
            file=sys.stderr,
        )
        return 1

    # Pull the LFS-tracked files under the include path. ``args.include``
    # is operator-supplied; the workflow only ever passes the literal
    # default (S603 -- argparse-resolved string passed verbatim to git lfs
    # pull --include, which itself rejects path-traversal). S607 accepted
    # because ``git`` is resolved from PATH on the HIL runner (standard CI).
    cp_pull = subprocess.run(  # noqa: S603
        ["git", "lfs", "pull", "--include", args.include],  # noqa: S607
        capture_output=True,
        text=True,
        cwd=args.repo_root,
        check=False,
    )
    if cp_pull.returncode != 0:
        print(
            "pull_replay_traces: git lfs pull failed:\n"
            f"  stderr: {cp_pull.stderr}\n"
            f"  stdout: {cp_pull.stdout}",
            file=sys.stderr,
        )
        return 1

    print(f"pull_replay_traces: pulled LFS objects under {args.include}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
