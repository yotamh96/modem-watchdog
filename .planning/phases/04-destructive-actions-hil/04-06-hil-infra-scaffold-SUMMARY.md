---
phase: 04-destructive-actions-hil
plan: 06
subsystem: hil-infra
tags: [hil, github-actions, fault-injection, git-lfs, replay-harness, bench-jetson]

# Dependency graph
requires:
  - phase: 01-foundations-adrs
    provides: self-hosted aarch64 runner config (.github/workflows/ci.yml as analog), uv venv bootstrap pattern
  - phase: 02-core-daemon-laptop-testable
    provides: tools/gen_replay_fixtures.py (argparse + main() pattern analog), tests/fixtures/replay/<scenario>/<NNN>.json shape, replay-harness consumer (Plan 02-10)
  - phase: 03-linux-event-sources-lifecycle
    provides: integration test tier (per-module pytestmark linux_only), tests/integration/test_logrotate_create.py (real-subprocess pattern in SP-04-exempt tests/), pyproject.toml hil marker registration
provides:
  - .github/workflows/hil.yml (new) — nightly + workflow_dispatch HIL CI job on [self-hosted, linux, ARM64, hil-bench] with serial concurrency + 90 min budget + support-bundle artefact upload on failure
  - tests/hil/README.md, tests/hil/conftest.py, tests/hil/fault_inject.py — HIL test tier scaffold; 7 module-level async fault-injection helpers
  - tools/pull_replay_traces.py — argparse CLI that resolves the v1-30d Git LFS pointer via `git lfs pull --include`; fails-fast on missing LFS auth
  - tests/fixtures/replay/v1-30d/ — LFS-pointer directory with .gitkeep + .gitattributes (*.json + *.jsonl filter=lfs) + README documenting quarterly refresh + sha256[:8] redaction contract
affects:
  - 04-07 (HIL scenario suite) — consumes everything in this plan: imports `from tests.hil.fault_inject import inject_*` from scenario files; the HIL workflow at .github/workflows/hil.yml is the runner; the v1-30d LFS pointer feeds the replay-harness 30-day agreement gate

# Tech tracking
tech-stack:
  added:
    - "Git LFS as fixture-storage transport for >=30-day v1 trace snapshots (CONTEXT D-03)."
  patterns:
    - "Self-hosted runner label specialisation: ci.yml uses [self-hosted, linux, ARM64]; hil.yml extends to [self-hosted, linux, ARM64, hil-bench] so the bench Jetson is the only physical runner that picks up HIL jobs."
    - "Serial concurrency on shared physical hardware: `concurrency: { group: hil-bench, cancel-in-progress: false }` queues runs so a current run completes before the next picks up — never two simultaneous fault-injection sessions on the same bench Jetson."
    - "Trigger discipline against threat T-04-06-01: workflow uses ONLY `schedule:` and `workflow_dispatch:` — explicitly NOT `pull_request_target` (would expose CAP_SYS_MODULE on the bench Jetson to fork PR authors)."
    - "Fault-injection helpers are module-level async functions (NOT a class), one per fault. Imports `subprocess` directly — tests/ tier is SP-04-exempt by design (lint scope is src/, see scripts/lint_no_subprocess.sh:11). Production src/ continues to route through subproc/runner."
    - "HIL collection guard via tests/hil/conftest.py: `collect_ignore_glob = ['**/*.py']` when `sys.platform == 'win32'` so a Windows dev-host `pytest` never even attempts to collect HIL scenarios."
    - "LFS-pull tooling separated from workflow: tools/pull_replay_traces.py is a stand-alone argparse script — fails clearly with exit 1 on missing git-lfs install or auth (no silent skip per CONTEXT D-03). The workflow invokes it via `python -m tools.pull_replay_traces` in the setup phase."

key-files:
  created:
    - .github/workflows/hil.yml
    - tests/hil/README.md
    - tests/hil/conftest.py
    - tests/hil/fault_inject.py
    - tools/pull_replay_traces.py
    - tests/fixtures/replay/v1-30d/.gitkeep
    - tests/fixtures/replay/v1-30d/.gitattributes
    - tests/fixtures/replay/v1-30d/README.md
  modified: []

key-decisions:
  - "PATTERNS correction #3 honored: pyproject.toml NOT modified — the `hil` marker is already registered at pyproject.toml:78 (Plan 03-01 era). Workflow file just invokes `pytest -m hil`."
  - "Trigger set is exactly `schedule: cron 0 4 * * *` + `workflow_dispatch:` — per CONTEXT D-01 (per-PR is too slow at 45+ min; per-tag-only is too coarse because Phase 4 EXIT requires green HIL run BEFORE tagging, which would be circular)."
  - "Software-only fault injection per CONTEXT D-02: 7 module-level helpers cover SIM-app issues (qmicli --uim-sim-power-off/on), QMI-hung (pkill -9 qmi-proxy), registration loss (qmicli --dms-set-operating-mode=offline/online), thermal/usb_overcurrent (synthetic /dev/kmsg writes via the 5 closed-enum patterns from Plan 03-05). NO real RF detuning hardware — RF-blocked logic is validated via synthetic-signal fixtures + a config-injected forced rf_blocked HIL scenario in Plan 04-07."
  - "v1-30d trace storage via Git LFS (CONTEXT D-03): the directory ships .gitkeep + .gitattributes + README today; actual JSON shards land via `git lfs track '*.json'` + commit when the first quarterly refresh produces real fixtures. The README's redaction contract is verbatim (sha256[:8] hash, deterministic per identity) so the same shape Plan 02-09's ctl support-bundle uses is preserved across the project."
  - "tools/pull_replay_traces.py uses S603/S607 noqa with explicit per-line rationale — `git` is resolved from PATH on the HIL runner (standard CI tooling); `args.include` defaults to a literal path and the workflow only ever passes the default. mypy --strict + ruff check + ruff format --check all green."
  - "ASYNC240 fix in fault_inject.py: `_KMSG.exists()` and `_KMSG.write_text()` wrapped in `asyncio.to_thread` — pathlib methods on async functions block the event loop on Linux (synchronous file I/O); the wrap is the canonical fix and matches the pattern subproc/runner uses for blocking system calls."
  - "Deferred: `tools/redact_traces.py` (a programmatic redactor for the manual sha256[:8] redaction step) — README documents the manual procedure; the helper script lands when the first real quarterly refresh requires it (probably Phase 5 bench-shadow)."

patterns-established:
  - "GitHub Actions HIL pattern: separate workflow file per concurrency-isolated runner pool; nightly cron + workflow_dispatch; serial concurrency; explicit lfs:false on checkout + manual `git lfs pull` script in setup. Reusable for any future hardware-tethered CI job."
  - "Fault-injection helpers as module-level async functions (NOT a class) — one helper per fault; raises on infrastructure failure; tests/ tier is SP-04-exempt so direct subprocess.run is acceptable. Plan 04-07 scenarios will import these helpers directly."
  - "Quarterly LFS-fixture refresh runbook in repository: README.md committed alongside .gitattributes + .gitkeep documents the regeneration command, redaction contract (verbatim PII shape), and consumer wiring. Reproducible without tribal knowledge."

requirements-completed: [FR-23, FR-24, FR-27]

# Metrics
duration: 7min
completed: 2026-05-10
---

# Phase 04 Plan 06: HIL CI infrastructure scaffold Summary

**HIL CI lane bootstrapped: nightly + workflow_dispatch GitHub Actions workflow on [self-hosted, linux, ARM64, hil-bench] with serial concurrency + 90 min budget + support-bundle artefact upload on failure; tests/hil/ scaffold with 7 software-only fault-injection helpers; tools/pull_replay_traces.py + Git LFS pointer at tests/fixtures/replay/v1-30d/ for the replay-harness 30-day agreement gate. Plan 04-07 will import the fault helpers + use the workflow + consume the LFS pointer; this plan ships the SCAFFOLD only, no scenarios.**

## Performance

- **Duration:** ~7 min (431 s)
- **Started:** 2026-05-10T11:23:21Z
- **Completed:** 2026-05-10T11:30:32Z
- **Tasks:** 2 (both `type="auto"`)
- **Files created:** 8 (1 workflow YAML + 4 tests/hil/ files + 1 tool + 3 fixture-directory files)
- **Files modified:** 0 (per CONTEXT correction #3, pyproject.toml is NOT touched — hil marker already registered)

## Accomplishments

### Task 1 — HIL workflow + tests/hil/ scaffold

- New `.github/workflows/hil.yml` (62 LOC):
  - Triggers: `schedule: cron "0 4 * * *"` (nightly 04:00 UTC) + `workflow_dispatch:` (manual). Explicitly NOT `pull_request_target` (T-04-06-01 mitigation).
  - Runs on `[self-hosted, linux, ARM64, hil-bench]` (the bench Jetson tethered to 4× EM7421 on USB hub 2-3.1.{1..4}).
  - `concurrency: { group: hil-bench, cancel-in-progress: false }` — serial; current run completes before next.
  - 90 min `timeout-minutes`.
  - Setup: uv install + venv + dev deps + locked runtime; `lfs: false` on checkout (explicit pull).
  - Pull v1-30d traces step: `python -m tools.pull_replay_traces`.
  - Run step: `pytest -m hil tests/hil/ -ra --tb=short`.
  - On failure: collect support bundle via `spark-modem ctl support-bundle` and upload as artefact `hil-support-bundle-${{ github.run_id }}` with 14-day retention.
- New `tests/hil/README.md` (90 lines): topology table, marker contract (linux_only + hil + skipif win32 + asyncio per scenario), local-run warning, scenario index for Plan 04-07, replay-harness 30-day gate context, why-nightly rationale.
- New `tests/hil/conftest.py` (46 lines): `collect_ignore_glob = ["**/*.py"]` when `sys.platform == "win32"` (Windows dev-host belt-and-suspenders); `bench_jetson_topology` session fixture exposing usb_paths + cdc_wdm_paths to scenarios.
- New `tests/hil/fault_inject.py` (147 lines): 7 module-level async helpers
  - `inject_sim_power_off(cdc_wdm)` — `qmicli --uim-sim-power-off=1` (causes IssueDetail.SIM_POWER_DOWN)
  - `inject_sim_power_on(cdc_wdm)` — recovery from above
  - `inject_qmi_proxy_kill()` — `pkill -9 qmi-proxy` (PROXY_DIED → driver_reset path; `check=False` because pkill exits 1 if no process matched)
  - `inject_kmsg(text)` — synthetic `/dev/kmsg` writes via `asyncio.to_thread` wrap (5 closed-enum patterns from Plan 03-05)
  - `inject_offline(cdc_wdm)` — `qmicli --dms-set-operating-mode=offline` (NOT_REGISTERED)
  - `inject_online(cdc_wdm)` — recovery from above
  - `inject_thermal_critical()` — synthetic thermal_critical kmsg write
  - All qmicli calls include `--device-open-proxy` (FR-74 / Plan 02-02 mandatory).

### Task 2 — tools/pull_replay_traces.py + v1-30d fixture scaffold

- New `tools/pull_replay_traces.py` (109 LOC): argparse CLI with two flags (`--include` defaulting to `tests/fixtures/replay/v1-30d`, `--repo-root` defaulting to cwd); two `subprocess.run` calls — `git lfs version` (install check) then `git lfs pull --include <path>`; fails clearly with stderr-formatted error + exit 1 on missing git-lfs install OR pull failure (no silent skip per CONTEXT D-03). `mypy --strict` green, `ruff check` + `ruff format --check` green, `--help` works.
- New `tests/fixtures/replay/v1-30d/.gitkeep` — empty directory marker so the dir is committed before any LFS shards land.
- New `tests/fixtures/replay/v1-30d/.gitattributes` — `*.json filter=lfs diff=lfs merge=lfs -text` + same for `*.jsonl`; LFS pointer registration scoped to this dir only.
- New `tests/fixtures/replay/v1-30d/README.md` (82 lines): documents the SSH-into-prod-jetson + `diag.sh --capture-trace --since=30d` regeneration command; redaction contract verbatim (ICCID 18-22 digits, IMSI 14-15 digits, IPv4/IPv6 — all replaced with `<redacted:<8-hex>>` where the hex is `sha256(value)[:8]`, deterministic per identity); fixture-directory shape matches Phase 2's `gen_replay_fixtures.py` output; quarterly refresh cadence pinned; how the HIL workflow consumes the directory documented end-to-end.

## Verification

All Plan 04-06 verify automation passed:

| Check                                                       | Result |
|-------------------------------------------------------------|--------|
| `pytest --collect-only -q tests/hil/`                       | 0 collected (this plan = scaffold only; Plan 04-07 lands scenarios) |
| `python -c "import tests.hil.fault_inject"`                 | 7 helpers importable, names match |
| `ruff check tests/hil/ tools/pull_replay_traces.py`         | All checks passed |
| `ruff format --check tests/hil/ tools/pull_replay_traces.py`| 4 files already formatted |
| `mypy --strict tools/pull_replay_traces.py`                 | Success: no issues found in 1 source file |
| `bash scripts/lint_no_subprocess.sh`                        | exit 0 (SP-04 — tools/ + tests/ are exempt; src/ tree untouched) |
| `python -c "import yaml; yaml.safe_load(open('.github/workflows/hil.yml'))"` | YAML parses; triggers, concurrency, runner, timeout all correct |
| `python -m tools.pull_replay_traces --help`                 | Argparse help printed; exit 0 |
| `pytest -m "unit and not linux_only and not hil"`           | 790 pass / 80 skip / 0 fail / 11.91s (M7 30s budget preserved) |

Real SP-04 violations in `src/` outside `subproc/`: **0** (verified via `grep -rE 'create_subprocess_exec\|create_subprocess_shell\|subprocess\.(run\|Popen\|call\|check_call\|check_output)\|os\.system' src/ --include='*.py' \| grep -v '^src/spark_modem/subproc/'`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Ruff lint fixes during Task 1 verification**

- **Found during:** Task 1 lint stage (`ruff check tests/hil/`)
- **Issues:**
  - I001 — un-sorted import block in `tests/hil/conftest.py` (blank line between import and comment).
  - RUF100 — unused `noqa: S404` directive in `tests/hil/fault_inject.py` (S404 is not in the project's ruff lint selectors `["E","F","W","I","N","UP","B","S","ASYNC","ANN","RET","SIM","PTH","PL","RUF"]`; it's specifically excluded — `S404` is the bandit "import subprocess" check which the project does not flag).
  - ASYNC240 ×2 — `_KMSG.exists()` and `_KMSG.write_text()` called from async function in `fault_inject.py:inject_kmsg`. Per ruff: pathlib methods are blocking I/O and must be wrapped in `asyncio.to_thread` (or use trio.Path / anyio.path).
- **Fix:**
  - conftest.py: removed extra blank line between import and `collect_ignore_glob` comment.
  - fault_inject.py: removed unused `# noqa: S404` directive (the import is unflagged).
  - fault_inject.py:inject_kmsg: wrapped `_KMSG.exists()` and `_KMSG.write_text(...)` in `await asyncio.to_thread(...)` so the synchronous pathlib calls don't block the event loop.
- **Files modified:** `tests/hil/conftest.py`, `tests/hil/fault_inject.py`
- **Commit:** 71c9f7d
- **Rationale:** Rule 3 — these blocked Task 1 from passing the verify command.

**2. [Rule 3 - Blocking] Ruff S603/S607 lint suppression in tools/pull_replay_traces.py**

- **Found during:** Task 2 lint stage (`ruff check tools/pull_replay_traces.py`)
- **Issue:** Ruff's bandit-derived rules flagged `subprocess.run(["git", ...])` calls — S603 (subprocess call with possibly-untrusted input — `args.include` is operator-supplied) and S607 (partial executable path — `git` is resolved from PATH).
- **Fix:** Added explicit per-line `# noqa: S603` / `# noqa: S607` directives with comment rationale. The argv lists are literal (S607 — `git` from PATH is the standard CI convention; absolute path would be inappropriate here because the runner installs git via apt at an unspecified location). `args.include` defaults to a literal path and the workflow only ever passes the default; if an operator manually invokes with a malicious `--include`, that's their trust grant. `git lfs pull` itself rejects path-traversal attempts at the LFS layer.
- **Files modified:** `tools/pull_replay_traces.py`
- **Commit:** 4125568
- **Threat-register cross-reference:** matches T-04-06-03 mitigation in the plan's threat model.

**3. [Rule 3 - Blocking] Ruff format auto-formatting on `argparse.ArgumentParser(description=(...))`**

- **Found during:** Task 2 format stage (`ruff format --check tools/pull_replay_traces.py`)
- **Issue:** I had originally split the description string across two lines (concatenated literal); ruff format collapses single-string-concat into one line because the result fits under line-length=100.
- **Fix:** Collapsed the description tuple into the one-line literal that ruff prefers.
- **Files modified:** `tools/pull_replay_traces.py`
- **Commit:** 4125568

No Rule 4 (architectural) deviations. No Rule 1 (bug) or Rule 2 (missing critical functionality) deviations. Plan executed essentially as written; the three above are routine lint adjustments that the planner could not have predicted (ruff's ASYNC240 is recent and wasn't in the planner's analog excerpts; S603/S607 are bandit rules that fire only when subprocess argv touches user-derived input or PATH-resolved binaries).

## Threat Surface Update

The plan's threat register T-04-06-01..07 covers all surfaces this plan introduces. No new threat-flag surfaces discovered during execution:

- T-04-06-01 (workflow exposed via pull_request_target) — verified: triggers list is `[schedule, workflow_dispatch]` only.
- T-04-06-02 (LFS credential exposure) — verified: workflow uses `actions/checkout@v4` with default GITHUB_TOKEN auto-redaction; tools/pull_replay_traces.py never echoes env vars.
- T-04-06-03 (path-traversal via --include) — verified: argparse default is the literal LFS dir; `git lfs pull` rejects out-of-repo paths.
- T-04-06-04 (concurrent HIL runs thrash bench) — verified: `cancel-in-progress: false` queues runs.
- T-04-06-05 (scenario failures without artefact) — verified: `actions/upload-artifact@v4` on `if: failure()`, 14-day retention.
- T-04-06-06 (PII in v1 traces before redaction) — verified: README documents the redaction contract verbatim; manual procedure prescribed until `tools/redact_traces.py` lands.
- T-04-06-07 (fault_inject helpers misfire on dev laptops) — verified: tests/hil/conftest.py belt-and-suspenders skips collection on win32; scenario tests in Plan 04-07 will set per-module `pytestmark = [linux_only, hil, skipif(win32)]`.

## Artefact-Trail (commits)

- **71c9f7d** `feat(04-06): add HIL workflow + tests/hil/ scaffold` — Task 1 (4 files: hil.yml + 3 tests/hil/ files; tests/hil/__init__.py was pre-existing from Plan 03-09 era and intentionally not touched).
- **4125568** `feat(04-06): add tools/pull_replay_traces.py + v1-30d LFS scaffold` — Task 2 (4 files: tool + .gitkeep + .gitattributes + README).

## Deferred Items

- `tools/redact_traces.py` — programmatic implementation of the sha256[:8] redaction contract documented in the v1-30d README. Manual procedure is sufficient for Phase 4; the helper script lands when the first real quarterly refresh requires it (likely Phase 5 bench-shadow when v1 traces actually flow into the directory).
- Real workflow execution on the bench Jetson — this plan ships the workflow YAML + scaffold; the first actual run on the [self-hosted, linux, ARM64, hil-bench] runner will validate end-to-end pulls + collection. Plan 04-07 (HIL scenario suite) will trigger it via workflow_dispatch.
- `tools/replay_harness.py` integration with the v1-30d directory — Plan 02-10 already implements the replay harness against `tests/fixtures/replay/<scenario>/<NNN>.json`; pointing it at the LFS-pulled v1-30d directory is a one-line change in Plan 04-07 (the harness is fixture-directory-shape-agnostic).

## Self-Check: PASSED

Verified post-write:

- `.github/workflows/hil.yml` — exists, 62 lines, YAML parses, all required fields present.
- `tests/hil/README.md` — exists, 90 lines (≥40 required).
- `tests/hil/conftest.py` — exists, 46 lines, ruff + format clean.
- `tests/hil/fault_inject.py` — exists, 147 lines, 7 helpers, ruff + format clean, importable on Windows dev host.
- `tools/pull_replay_traces.py` — exists, 109 LOC, mypy --strict + ruff + format clean, --help works.
- `tests/fixtures/replay/v1-30d/.gitkeep` — exists, 0 bytes (intentional).
- `tests/fixtures/replay/v1-30d/.gitattributes` — exists, registers `*.json` and `*.jsonl` as LFS-tracked.
- `tests/fixtures/replay/v1-30d/README.md` — exists, 82 lines, documents quarterly refresh + sha256 redaction + workflow consumer.
- Commits: 71c9f7d (Task 1) and 4125568 (Task 2) both present in `git log`.
- M7 30s budget: unit suite at 11.91s — preserved with 18s headroom.
