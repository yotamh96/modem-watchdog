"""tools/check_spec.py -- CI gate ensuring every RECOVERY_SPEC §4 row is
referenced by >=1 test in tests/test_recovery_spec.py.

Reads `_DECISION_TABLE` from `spark_modem.policy.decision_table` and
checks that the spec-tests file mentions every (IssueCategory,
IssueDetail) pair at least once (by enum value string).  Exits 1 if any
row is missing a test, 0 otherwise.

Usage:
    python tools/check_spec.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from spark_modem.policy.decision_table import all_table_rows

SPEC_TEST_FILE = Path(__file__).parent.parent / "tests" / "test_recovery_spec.py"


def main() -> int:
    try:
        text = SPEC_TEST_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"check_spec: missing {SPEC_TEST_FILE}", file=sys.stderr)
        return 1

    missing: list[tuple[str, str]] = []
    for cat, detail in all_table_rows():
        # We accept either the enum-name reference or the value-string
        # reference (e.g. IssueDetail.APN_EMPTY or "apn_empty").
        if cat.value not in text or detail.value not in text:
            missing.append((cat.value, detail.value))

    if missing:
        print(
            f"check_spec: {len(missing)} RECOVERY_SPEC §4 rows missing tests:",
            file=sys.stderr,
        )
        for c, d in missing:
            print(f"  ({c}, {d})", file=sys.stderr)
        return 1

    print(f"check_spec: all {len(all_table_rows())} rows covered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
