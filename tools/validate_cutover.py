#!/usr/bin/env python3
"""Post-cutover validation for spark-modem-watchdog v2.

Run on each target box after .deb install + service start.
Does NOT import from spark_modem — uses CLI and direct file/socket reads.

Exit codes:
    0  all green
    1  soft failure (non-critical check failed)
    2  hard failure (daemon not running or modem unhealthy)
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

_STATE_ROOT = "/var/lib/spark-modem-watchdog"
_RUN_DIR = "/run/spark-modem-watchdog"
_METRICS_SOCK = f"{_RUN_DIR}/metrics.sock"
_EVENTS_LOG = "/var/log/spark-modem-watchdog/events.jsonl"
_DEFAULT_CYCLE_INTERVAL = 60.0
_EXPECTED_MODEM_COUNT = 4
_HMAC_PLACEHOLDER_SENTINEL = b"REPLACE_THIS_BEFORE_FIRST_START_SEE_RUNBOOK\n"
_HMAC_DEFAULT_PATH = "/etc/spark-modem-watchdog/hmac-secret"
_EVENTS_SAMPLE_DELAY = 5.0
_EXIT_HARD_FAIL = 2
_SHA_PREVIEW_LEN = 16


@dataclass
class CheckResult:
    name: str
    passed: bool
    severity: str  # "hard" or "soft"
    detail: str = ""


@dataclass
class ValidationReport:
    checks: list[CheckResult] = field(default_factory=list)
    exit_code: int = 0

    def add(self, result: CheckResult) -> None:
        self.checks.append(result)
        if not result.passed:
            code = 2 if result.severity == "hard" else 1
            self.exit_code = max(self.exit_code, code)


def _run(argv: list[str], *, timeout: float = 10.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def check_service_active(report: ValidationReport) -> None:
    try:
        proc = _run(["systemctl", "is-active", "spark-modem-watchdog.service"])
        active = proc.stdout.strip() == "active"
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        report.add(CheckResult("service_active", False, "hard", str(exc)))
        return
    report.add(
        CheckResult(
            "service_active",
            active,
            "hard",
            proc.stdout.strip(),
        )
    )


def check_modem_status(report: ValidationReport) -> None:
    try:
        proc = _run(["spark-modem", "status", "--json"])
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        report.add(CheckResult("modem_status", False, "hard", str(exc)))
        return
    if proc.returncode != 0:
        report.add(
            CheckResult(
                "modem_status",
                False,
                "hard",
                f"exit {proc.returncode}: {proc.stderr.strip()}",
            )
        )
        return
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        report.add(CheckResult("modem_status", False, "hard", f"bad JSON: {exc}"))
        return
    modems = data.get("modems", [])
    present = len(modems)
    exhausted = [m for m in modems if m.get("state") == "exhausted"]
    ok = present == _EXPECTED_MODEM_COUNT and len(exhausted) == 0
    report.add(
        CheckResult(
            "modem_status",
            ok,
            "hard",
            f"{present}/{_EXPECTED_MODEM_COUNT} modems present, {len(exhausted)} exhausted",
        )
    )


def check_prometheus_metrics(report: ValidationReport) -> None:
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect(_METRICS_SOCK)
        sock.sendall(b"GET /metrics HTTP/1.0\r\nHost: localhost\r\n\r\n")
        chunks: list[bytes] = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        sock.close()
    except (OSError, TimeoutError) as exc:
        report.add(CheckResult("prometheus_metrics", False, "soft", str(exc)))
        return
    body = b"".join(chunks).decode("utf-8", errors="replace")
    count = body.count("modem_state_value")
    ok = count >= _EXPECTED_MODEM_COUNT
    report.add(
        CheckResult(
            "prometheus_metrics",
            ok,
            "soft",
            f"modem_state_value lines: {count} (expected >= {_EXPECTED_MODEM_COUNT})",
        )
    )


def check_status_freshness(report: ValidationReport, *, cycle_interval: float) -> None:
    status_path = Path(_STATE_ROOT) / "status.json"
    if not status_path.exists():
        report.add(CheckResult("status_freshness", False, "hard", "status.json not found"))
        return
    mtime = status_path.stat().st_mtime
    age = time.time() - mtime
    threshold = 2 * cycle_interval
    ok = age < threshold
    report.add(
        CheckResult(
            "status_freshness",
            ok,
            "hard",
            f"age={age:.1f}s threshold={threshold:.1f}s",
        )
    )


def check_hmac_secret(report: ValidationReport) -> None:
    creddir = os.environ.get("CREDENTIALS_DIRECTORY")
    if creddir:
        path = Path(creddir) / "spark-modem-watchdog.hmac-secret"
    else:
        path = Path(_HMAC_DEFAULT_PATH)
    if not path.exists():
        report.add(CheckResult("hmac_secret", False, "soft", f"{path} not found"))
        return
    try:
        content = path.read_bytes()
    except PermissionError as exc:
        report.add(CheckResult("hmac_secret", False, "soft", str(exc)))
        return
    if content == _HMAC_PLACEHOLDER_SENTINEL:
        report.add(
            CheckResult(
                "hmac_secret",
                False,
                "soft",
                "placeholder sentinel — operator must replace before production use",
            )
        )
        return
    if len(content) == 0:
        report.add(CheckResult("hmac_secret", False, "soft", "secret file is empty"))
        return
    report.add(CheckResult("hmac_secret", True, "soft", "present and not placeholder"))


def check_carrier_table_sha(report: ValidationReport, *, expected_sha: str | None) -> None:
    if expected_sha is None:
        report.add(
            CheckResult(
                "carrier_table_sha",
                True,
                "soft",
                "no expected SHA provided, skipped",
            )
        )
        return
    status_path = Path(_STATE_ROOT) / "status.json"
    if not status_path.exists():
        report.add(CheckResult("carrier_table_sha", False, "soft", "status.json not found"))
        return
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        report.add(CheckResult("carrier_table_sha", False, "soft", str(exc)))
        return
    actual = data.get("carrier_table_sha256", "")
    ok = actual == expected_sha
    report.add(
        CheckResult(
            "carrier_table_sha",
            ok,
            "soft",
            f"expected={expected_sha[:_SHA_PREVIEW_LEN]}… actual={actual[:_SHA_PREVIEW_LEN]}…"
            if len(expected_sha) > _SHA_PREVIEW_LEN
            else f"expected={expected_sha} actual={actual}",
        )
    )


def check_events_growing(report: ValidationReport) -> None:
    events = Path(_EVENTS_LOG)
    if not events.exists():
        report.add(CheckResult("events_growing", False, "soft", "events.jsonl not found"))
        return
    try:
        size1 = events.stat().st_size
    except OSError as exc:
        report.add(CheckResult("events_growing", False, "soft", str(exc)))
        return
    time.sleep(_EVENTS_SAMPLE_DELAY)
    try:
        size2 = events.stat().st_size
    except OSError as exc:
        report.add(CheckResult("events_growing", False, "soft", str(exc)))
        return
    ok = size2 > size1
    report.add(
        CheckResult(
            "events_growing",
            ok,
            "soft",
            f"size1={size1} size2={size2} delta={size2 - size1}",
        )
    )


def validate(
    *,
    cycle_interval: float,
    expected_carrier_sha: str | None,
) -> ValidationReport:
    report = ValidationReport()
    check_service_active(report)
    if report.exit_code == _EXIT_HARD_FAIL:
        return report
    check_modem_status(report)
    check_prometheus_metrics(report)
    check_status_freshness(report, cycle_interval=cycle_interval)
    check_hmac_secret(report)
    check_carrier_table_sha(report, expected_sha=expected_carrier_sha)
    check_events_growing(report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Post-cutover validation for spark-modem-watchdog v2.",
    )
    parser.add_argument(
        "--cycle-interval",
        type=float,
        default=_DEFAULT_CYCLE_INTERVAL,
        help=f"Expected cycle interval in seconds (default: {_DEFAULT_CYCLE_INTERVAL})",
    )
    parser.add_argument(
        "--expected-carrier-sha",
        type=str,
        default=None,
        help="Expected carrier-table SHA256 hex digest",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write structured JSON report to this path (default: stdout)",
    )
    args = parser.parse_args(argv)

    report = validate(
        cycle_interval=args.cycle_interval,
        expected_carrier_sha=args.expected_carrier_sha,
    )

    output = {
        "exit_code": report.exit_code,
        "verdict": {0: "pass", 1: "soft_fail", 2: "hard_fail"}[report.exit_code],
        "checks": [
            {
                "name": c.name,
                "passed": c.passed,
                "severity": c.severity,
                "detail": c.detail,
            }
            for c in report.checks
        ],
    }

    payload = json.dumps(output, indent=2) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)

    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
