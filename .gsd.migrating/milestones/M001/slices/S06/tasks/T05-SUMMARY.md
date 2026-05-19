---
id: T05
parent: S06
milestone: M001
provides: []
requires: []
affects: []
key_files: []
key_decisions: []
patterns_established: []
observability_surfaces: []
drill_down_paths: []
duration: 
verification_result: passed
completed_at: 
blocker_discovered: false
---
# T05: 05.1-deb-packaging-hotfix 05

**# Phase 05.1 Plan 05: Regression Gate — V-01, V-04, V-02 Summary**

## What Happened

# Phase 05.1 Plan 05: Regression Gate — V-01, V-04, V-02 Summary

**One-liner:** Extended B-03 postinst smoke with daemon/CLI imports (V-01), added three unit-file audit assertions for drift detection (V-04), and replaced the CI smoke-install step with a strict-superset aarch64 docker install test including `systemd-analyze verify` (V-02 / L-04).

## What Was Built

### Task 1: B-03 Postinst Smoke Extension (V-01)

`scripts/postinst_smoke_test.sh` — two new entries appended after the 10 existing runtime-lib imports:

**Before (libs list, 10 entries):**
```python
libs = [
    "pydantic", "pydantic_settings", "yaml", "prometheus_client",
    "pyudev", "pyroute2", "asyncinotify", "httpx", "sdnotify", "psutil",
]
...
print(f"OK: all {len(libs)} runtime libs import under {sys.executable}")
```

**After (libs list, 12 entries):**
```python
libs = [
    "pydantic", "pydantic_settings", "yaml", "prometheus_client",
    "pyudev", "pyroute2", "asyncinotify", "httpx", "sdnotify", "psutil",
    # Phase 05.1 V-01: the daemon + CLI must be importable for the
    # .deb to be functional. These imports catch the bug class
    # "spark_modem not on sys.path of the bundled venv" — the
    # original Phase 1 smoke only imported the 10 runtime libs,
    # never the daemon package itself, which is how bug #1 slipped
    # through Phase 1 CI.
    "spark_modem.daemon.main",
    "spark_modem.cli.main",
]
...
print(f"OK: all {len(libs)} runtime libs + daemon entry points import under {sys.executable}")
```

This catches bug class "spark_modem not on sys.path" at install time (postinst) AND on every start (ExecStartPre). Both call sites pick up the change automatically — no wiring change needed.

### Task 2: V-04 Unit-File Audit Extensions

`tests/integration/test_unit_file_audit.py` — 3 new test functions + 2 new fixtures + 2 new path constants added. Pytest count: **18 → 23 passed**.

**New path constants (module top):**
- `_PYPROJECT_PATH` — points to `pyproject.toml`
- `_INSTALL_PATH` — points to `debian/spark-modem-watchdog.install`

**New fixtures:**
- `project_scripts() -> dict[str, str]` — parses `[project.scripts]` via `tomllib`
- `install_map_dest_paths() -> list[str]` — parses the dest column of the `.install` file

**New tests:**

| Test | Spec | What it checks |
|------|------|----------------|
| `test_v04_exec_paths_anchored` | V-04 (a) | Every ExecStart/ExecStartPre binary is either a `[project.scripts]` console-script at `/opt/.../python/bin/<name>` or a file shipped by `debian/.install` |
| `test_v04_load_credential_path_matches_fallback` | V-04 (b) | `LoadCredential=` source path == `/etc/spark-modem-watchdog/hmac-secret` (the L-02 fallback path) |
| `test_v04_project_scripts_entry_points_importable` | V-04 (c) | Every `[project.scripts]` entry parses as `module:attr`, the module imports cleanly, and the attr exists |

Cross-platform — no `linux_only` marker. Runs on Windows dev host. mypy `--strict` and ruff clean.

### Task 3: V-02 CI Install Test Replacement

`.github/workflows/build-deb.yml` — "Smoke-install in clean container" step (lines 50-69) REPLACED with "Install + verify in clean Ubuntu 20.04 arm64 container (Phase 05.1 V-02)" (lines 50-94).

**Replaced step body summary (old step was 20 lines; new is 44 lines):**

The new step adds to the existing docker `apt install + smoke` pattern:
- **(a)** Re-runs `/opt/spark-modem-watchdog/libexec/postinst_smoke_test.sh` (B-03 belt-and-suspenders)
- **(b)** `test -x /opt/spark-modem-watchdog/python/bin/spark-modem` and `spark-modem-watchdog`
- **(c)** Checks `/etc/spark-modem-watchdog/hmac-secret` exists, is mode `600`, owner `0:0`, and contains `REPLACE_THIS_BEFORE_FIRST_START_SEE_RUNBOOK`
- **(d)** `systemd-analyze verify /lib/systemd/system/spark-modem-watchdog.service 2>&1` — the L-04 forcing function

Key implementation detail: outer single-quote heredoc (`bash -lc '...'`) with `'"$(basename $DEB)"'` splice so the deb filename is expanded by the GHA runner shell, not inside the docker container.

The workflow trigger (`on:`), `runs-on`, and `upload-artifact` step are unchanged.

## Pytest Count Before/After

| Scope | Before Plan 05 | After Plan 05 |
|-------|---------------|---------------|
| `test_unit_file_audit.py` | 20 tests | 23 tests |
| V-04 tests only | 0 | 3 passed |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Moved local imports to module top-level (ruff PLC0415)**

- **Found during:** Task 2 verification
- **Issue:** Plan specified `import tomllib` inside the fixture body and `import importlib` inside the test body as local imports. Ruff's `PLC0415` rule (selected via `PL` in pyproject.toml) flags imports not at module top-level.
- **Fix:** Moved both `import tomllib` and `import importlib` to the module-level import block at the top of `test_unit_file_audit.py`. The plan note "local import is acceptable" was superseded by the project's ruff configuration — CLAUDE.md rules take precedence.
- **Files modified:** `tests/integration/test_unit_file_audit.py`
- **Commit:** `0f3152f`

## L-04 Verdict Note

**IMPORTANT:** The L-04 verdict (whether systemd 245 silent-ignores, warns-with-degraded, or hard-fails `LoadCredential=` parsing) surfaces on the next push to main when the aarch64 self-hosted runner picks up this workflow.

- **If hard-fail:** `systemd-analyze verify` exits non-zero, the V-02 CI step fails, and a follow-up commit adds a postinst-managed drop-in override at `/etc/systemd/system/spark-modem-watchdog.service.d/10-systemd245-no-loadcredential.conf` per CONTEXT.md L-04 second branch.
- **If silent-ignore or warning:** V-02 step passes; the `2>&1` redirect makes any stderr warning visible in the CI log. Operators should capture this in `EXIT-CHECKLIST.md` step 6 (journalctl evidence).

The L-02 code-side fallback (already landed in Plan 05.1-02) handles silent-ignore and warning cases without further action.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The three files modified are: a shell script, a test file, and a CI workflow definition. No new trust boundary surfaces.

## Self-Check: PASSED

All files found and commits verified:

| Item | Status |
|------|--------|
| `scripts/postinst_smoke_test.sh` | FOUND |
| `tests/integration/test_unit_file_audit.py` | FOUND |
| `.github/workflows/build-deb.yml` | FOUND |
| `.planning/phases/05.1-deb-packaging-hotfix/05.1-05-SUMMARY.md` | FOUND |
| commit `18fc5a0` (Task 1 — V-01 smoke) | FOUND |
| commit `0f3152f` (Task 2 — V-04 tests) | FOUND |
| commit `cc60a5c` (Task 3 — V-02 workflow) | FOUND |
