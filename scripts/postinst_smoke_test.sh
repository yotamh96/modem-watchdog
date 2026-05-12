#!/usr/bin/env bash
# B-03 smoke test: prove all 10 runtime libraries import under the bundled python.
# Called from debian/postinst (fail-the-install) AND systemd ExecStartPre=
# (fail-the-start). Either failure surfaces independently — diagnostic.
# Closes FR-60.
set -euo pipefail

PYTHON="${SPARK_MODEM_PYTHON:-/opt/spark-modem-watchdog/python/bin/python3.12}"

if [[ ! -x "$PYTHON" ]]; then
  echo "ERROR: bundled python missing or not executable: $PYTHON" >&2
  exit 2
fi

"$PYTHON" -c '
import sys
libs = [
    "pydantic",
    "pydantic_settings",
    "yaml",
    "prometheus_client",
    "pyudev",
    "pyroute2",
    "asyncinotify",
    "httpx",
    "sdnotify",
    "psutil",
    # Phase 05.1 V-01: the daemon + CLI must be importable for the
    # .deb to be functional. These imports catch the bug class
    # "spark_modem not on sys.path of the bundled venv" — the
    # original Phase 1 smoke only imported the 10 runtime libs,
    # never the daemon package itself, which is how bug #1 slipped
    # through Phase 1 CI.
    "spark_modem.daemon.main",
    "spark_modem.cli.main",
]
failures = []
for name in libs:
    try:
        __import__(name)
    except Exception as e:
        failures.append((name, type(e).__name__, str(e)))
if failures:
    print("FAIL: import smoke test failed for:", file=sys.stderr)
    for n, etype, msg in failures:
        print(f"  - {n}: {etype}: {msg}", file=sys.stderr)
    sys.exit(1)
print(f"OK: all {len(libs)} runtime libs + daemon entry points import under {sys.executable}")
sys.exit(0)
' || exit 1
