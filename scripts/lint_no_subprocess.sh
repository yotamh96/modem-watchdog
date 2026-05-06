#!/usr/bin/env bash
# SP-04: enforce that all subprocess invocation flows through src/spark_modem/subproc/.
# Anti-pattern catalogue: subprocess.run, subprocess.Popen, subprocess.call,
# subprocess.check_call, subprocess.check_output, asyncio.create_subprocess_exec,
# asyncio.create_subprocess_shell, os.system. (CLAUDE.md §"Anti-patterns".)
set -euo pipefail

PATTERN='create_subprocess_exec|create_subprocess_shell|subprocess\.(run|Popen|call|check_call|check_output)|os\.system'

# Collect violations: anything matching PATTERN inside src/, NOT under src/spark_modem/subproc/.
VIOLATIONS=$(grep -rEn "$PATTERN" src/ \
  --include='*.py' \
  2>/dev/null \
  | grep -v '^src/spark_modem/subproc/' \
  || true)

if [[ -n "$VIOLATIONS" ]]; then
  echo "ERROR: subprocess invocation outside src/spark_modem/subproc/" >&2
  echo "$VIOLATIONS" >&2
  echo "" >&2
  echo "All subprocess calls MUST go through src/spark_modem/subproc/runner.py (SP-04)." >&2
  exit 1
fi

exit 0
