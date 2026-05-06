"""spark-modem status — print contents of /var/lib/.../status.json.

Reads the on-disk status.json (FR-41) and re-validates it through the
``StatusReport`` Pydantic model (extra='forbid' — drift in the writer
is detected at the consumer boundary). Prints the validated JSON with
indent=2 to stdout, returns 2 if the file is missing or unparseable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from spark_modem.wire.status import StatusReport


def _status_path(state_root: str | None) -> Path:
    root = Path(state_root) if state_root else Path("/var/lib/spark-modem-watchdog")
    return root / "status.json"


async def run(args: argparse.Namespace) -> int:
    path = _status_path(args.state_root)
    if not path.is_file():
        print(f"status: {path} does not exist", file=sys.stderr)
        return 2
    try:
        report = StatusReport.model_validate_json(path.read_bytes())
    except (OSError, ValidationError, ValueError) as exc:
        print(f"status: failed to parse {path}: {exc}", file=sys.stderr)
        return 2
    print(report.model_dump_json(indent=2))
    return 0
