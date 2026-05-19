# T09: 02-core-daemon-laptop-testable 09

**Slice:** S02 — **Milestone:** M001

## Description

Plan 02-09 ships the `spark-modem` CLI: six subcommands plus the three
`ctl` sub-subcommands (history, maintenance, support-bundle).

The CLI hits ALL of Phase 2's underlying subsystems:
- `diag` ← inventory + observer + zao_log + qmi (Plan 02-04 / 02-02 / 02-03)
- `recovery` ← policy.engine.run_cycle (Plan 02-05)
- `provision`, `reset` ← actions.dispatcher.execute_and_verify (Plan 02-06)
- `status` ← reads `/var/lib/spark-modem-watchdog/status.json` (Plan 02-07)
- `ctl history` ← reads `/var/log/spark-modem-watchdog/events.jsonl` (Phase 1 + new logrotate-rotated-siblings reader)
- `ctl maintenance` ← writes `globals.json` via state_store (Phase 1)
- `ctl support-bundle` ← assembles + redacts a tarball (NFR-22 + C-04)

`diag --qmi-fixture-dir=PATH` and `recovery --diag-fixture=PATH` are the
hardware-free fast paths: they swap a `FixtureRunner` (a small variant of
FakeRunner that loads canned qmicli output from per-version fixture files
on disk) into the QmiWrapper plumbing.

Output: `cli/` package + entry point in pyproject.toml + parametrized tests
covering happy paths and error paths (mandatory --duration on maintenance,
8h cap rejection, no carrier match, etc.).

## Must-Haves

- [ ] "spark-modem entry point installed via pyproject.toml [project.scripts]; argparse-based subcommand dispatch."
- [ ] "spark-modem diag --qmi-fixture-dir=PATH produces a typed Diag JSON in <1s on a developer laptop (FR-51 + SC#2)."
- [ ] "spark-modem diag --explain prints human-readable per-modem decision rationale (FR-50.3 + Claude's Discretion text format)."
- [ ] "spark-modem diag --json emits machine-readable JSON alongside (Claude's Discretion)."
- [ ] "spark-modem recovery --diag-fixture=PATH loads a Diag JSON and returns ranked PlannedAction[] (FR-52)."
- [ ] "spark-modem reset --action=<kind> --modem=cdc-wdmN routes to actions.dispatcher.execute_and_verify."
- [ ] "ctl history --modem=cdc-wdmN --since=1h reads events.jsonl + rotated siblings; filters by usb_path (canonical) or device alias (FR-50.1)."
- [ ] "ctl maintenance on --duration mandatory, max 8h hard cap, dual-clock expiry stored in globals.json (FR-50.2 + C-02)."
- [ ] "ctl maintenance acquires the existing state-store flock before reading/writing globals.json (Claude's Discretion: no new lock surface)."
- [ ] "ctl support-bundle produces a redacted tarball with last 200 events + state/by-usb/*.json + globals.json + status.json + last 24h webhook deliveries; ICCID/IMSI redacted to <redacted:<sha256[:8]>>; HMAC secret never copied (NFR-22 + NFR-22.1 + C-04)."

## Files

- `src/spark_modem/cli/__init__.py`
- `src/spark_modem/cli/main.py`
- `src/spark_modem/cli/diag.py`
- `src/spark_modem/cli/recovery.py`
- `src/spark_modem/cli/provision.py`
- `src/spark_modem/cli/reset.py`
- `src/spark_modem/cli/status.py`
- `src/spark_modem/cli/explain.py`
- `src/spark_modem/cli/ctl/__init__.py`
- `src/spark_modem/cli/ctl/history.py`
- `src/spark_modem/cli/ctl/maintenance.py`
- `src/spark_modem/cli/ctl/support_bundle.py`
- `src/spark_modem/cli/redact.py`
- `src/spark_modem/cli/clients.py`
- `pyproject.toml`
- `tests/unit/cli/__init__.py`
- `tests/unit/cli/test_main.py`
- `tests/unit/cli/test_diag.py`
- `tests/unit/cli/test_recovery.py`
- `tests/unit/cli/test_provision.py`
- `tests/unit/cli/test_reset.py`
- `tests/unit/cli/test_status.py`
- `tests/unit/cli/test_explain.py`
- `tests/unit/cli/test_ctl_history.py`
- `tests/unit/cli/test_ctl_maintenance.py`
- `tests/unit/cli/test_ctl_support_bundle.py`
- `tests/unit/cli/test_redact.py`
