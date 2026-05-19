# T09: Plan 09

**Slice:** S03 — **Milestone:** M001

## Description

Wave 3c — integration tests + bench-Jetson human-verify checkpoint. Depends
on Plans 03-06 (lifecycle modules + main.py), 03-07 (cycle_driver SIM-swap
detection), 03-08 (systemd unit + logrotate snippet) — this plan is the
phase exit gate.

Specifically:

  1. Establish the integration test tier:
     `tests/integration/__init__.py` (package marker) and
     `tests/integration/conftest.py` (shared fixtures only — does NOT
     auto-add linux_only marker per Issue #6 RESOLVED).
  2. `tests/integration/test_lifecycle.py` covers SC #1..#5 end-to-end
     via Fake* injection. Module-level
     `pytestmark = pytest.mark.linux_only` so Windows dev hosts skip
     cleanly.
  3. `tests/integration/test_logrotate_create.py` exercises real
     logrotate cron via subprocess. Module-level
     `pytestmark = pytest.mark.linux_only`.
  4. CHECKPOINT — bench Jetson hardware verification of the 4 hardware-only
     SC paths (NFR-12, NFR-13, SC #1, SC #4, SC #5 real-hardware portions).

This plan was carved out of the original Plan 03-06 to keep that plan
focused on lifecycle modules + main.py rewrite. Integration tests
naturally come last because they exercise the prior plans' outputs.

Output: 4 new integration test files; checkpoint blocks phase exit.
