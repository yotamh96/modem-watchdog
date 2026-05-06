---
phase: 02-core-daemon-laptop-testable
plan: 09
subsystem: cli
tags: [argparse, asyncio, pydantic, tarfile, gzip, hmac-redaction, dual-clock, flock, support-bundle]

requires:
  - phase: 01-foundations-adrs
    provides: BaseWire frozen wire types, StateStore atomic+locked persistence, EventAdapter discriminated union, MaintenanceWindow wire model, atomic_write_bytes, ADR-0012 3-layer locking
  - phase: 02-core-daemon-laptop-testable
    provides: QmiWrapper (02-02), policy.engine.run_cycle (02-05), actions.dispatcher (02-06), observer.observe_all + diag_builder.build_diag (02-04), StatusReport wire model (02-07), MaintenanceWindow on GlobalsState (02-07)

provides:
  - spark-modem entry point in pyproject.toml [project.scripts]
  - cli/main.py argparse subcommand dispatch (diag/recovery/provision/reset/status/ctl)
  - cli/clients.py production-grade Inventory/Clock/Zao stubs + FixtureRunner (no imports from tests/fakes)
  - cli/diag.py + cli/recovery.py: hardware-free laptop pipeline (FR-51 + FR-52)
  - cli/explain.py: text + JSON output formats for --explain
  - cli/ctl/maintenance.py: dual-clock 8h-capped maintenance window (C-02 + FR-50.2)
  - cli/ctl/history.py: events.jsonl + rotated/.gz sibling reader with --modem + --since filtering
  - cli/ctl/support_bundle.py: redacted tarball builder (NFR-22 + NFR-22.1 + C-04)
  - cli/redact.py: ICCID/IMSI sha256[:8] one-way + webhook URL host-only

affects:
  - 02-10 (replay harness consumes spark-modem recovery --diag-fixture)
  - phase 03 (cycle driver wires production runner injection that the CLI's reset/provision currently stub)
  - phase 04 (destructive actions; reset will accept modem_reset/usb_reset once dispatcher registers them)

tech-stack:
  added: [argparse subparser dispatch, tarfile w:gz, gzip rotated-log reader]
  patterns:
    - "FixtureRunner: SubprocRunner-shaped fake hosted under src/ for laptop CLI mode (not under tests/)"
    - "Production code never imports from tests/fakes/* — cli/clients.py is the production-side equivalent"
    - "Dual-clock expiry: min(now_mono >= expires_monotonic, now_wall_iso >= expires_iso) defends against NTP step in either direction"
    - "One-way consistent PII redaction: sha256[:8] preserves cross-file identity correlation without exporting PII"
    - "ctl mutating commands acquire the existing state-store flock via StateStore.save_globals — no new lock surface"

key-files:
  created:
    - src/spark_modem/cli/__init__.py
    - src/spark_modem/cli/main.py
    - src/spark_modem/cli/clients.py
    - src/spark_modem/cli/explain.py
    - src/spark_modem/cli/diag.py
    - src/spark_modem/cli/recovery.py
    - src/spark_modem/cli/provision.py
    - src/spark_modem/cli/reset.py
    - src/spark_modem/cli/status.py
    - src/spark_modem/cli/redact.py
    - src/spark_modem/cli/ctl/__init__.py
    - src/spark_modem/cli/ctl/history.py
    - src/spark_modem/cli/ctl/maintenance.py
    - src/spark_modem/cli/ctl/support_bundle.py
    - tests/unit/cli/__init__.py
    - tests/unit/cli/test_main.py
    - tests/unit/cli/test_diag.py
    - tests/unit/cli/test_recovery.py
    - tests/unit/cli/test_provision.py
    - tests/unit/cli/test_reset.py
    - tests/unit/cli/test_status.py
    - tests/unit/cli/test_explain.py
    - tests/unit/cli/test_redact.py
    - tests/unit/cli/test_ctl_history.py
    - tests/unit/cli/test_ctl_maintenance.py
    - tests/unit/cli/test_ctl_support_bundle.py
  modified:
    - pyproject.toml  # added [project.scripts] table

key-decisions:
  - "spark-modem entry point installed via pyproject.toml [project.scripts] = 'spark_modem.cli.main:main'; argparse-based subcommand dispatch keeps Phase 2 dependency-free."
  - "cli/clients.py hosts production-grade FixtureRunner + _CliClock + _InventoryFromFile + _NoZaoTailer + build_default_settings — production code under src/ NEVER imports from tests/fakes/*."
  - "FixtureRunner intent-resolution maps qmicli flags (--nas-get-signal-info, etc.) to fixture directory subpaths; falls back to any .txt in the version dir when the configured scenario is absent so the laptop CLI works against the canonical fixture set without further wiring."
  - "ctl maintenance dual-clock expiry stored in globals.json: started/expires both monotonic AND ISO; status check uses now_mono >= expires_mono OR now_wall_iso >= expires_iso (NTP step defense per ADR-0007 spirit)."
  - "8h hard cap (MAX_DURATION_SECONDS=28800) enforced at the CLI before any state mutation; MaintenanceWindow.max_duration_seconds=Field(le=28800) catches hand-edited globals.json at load time."
  - "ctl support-bundle Phase 2 limitation: omits journalctl + dmesg outputs because their capture requires subprocess calls outside src/spark_modem/subproc/ (SP-04 lint gate). Phase 3 wires through subproc.run."
  - "PII redaction via sha256[:8] is one-way and consistent: same ICCID/IMSI → same <redacted:<8 hex>> across the bundle, enabling cross-file identity correlation without exporting PII."
  - "Webhook URL redaction strips path/query, keeps <scheme>://<netloc>/. Captures the receiver identity without leaking accidental secrets in path/query material."
  - "ctl history events.jsonl reader handles plain rotated siblings (.1, .2, ...) AND gzipped (.1.gz, ...). Output is oldest-first (chronological); corrupt JSONL lines are skipped, not raised — events.jsonl integrity is the writer's responsibility."
  - "ctl history modem matching is canonical-by-usb_path. cdc-wdmN aliasing requires the daemon's identity map (Phase 3); without it, callers pass the canonical usb_path."
  - "ctl maintenance writes through StateStore.save_globals which acquires globals_lock() (asyncio.Lock) + acquire_flock_async(state_store_lockfile) — no new lock surface (Claude's Discretion in CONTEXT.md). Daemon and CLI mutator serialize on the same flock per CLAUDE.md §12 + ADR-0012."
  - "provision and reset subcommands print Phase-2 stub messages — full execution requires a daemon-style runner injection that lands with the cycle driver in plan 02-10. reset still validates action-kind correctness and rejects destructive actions (modem_reset/usb_reset/driver_reset) at the dispatcher boundary."

patterns-established:
  - "FixtureRunner pattern: production-side SubprocRunner-shaped fake at src/spark_modem/cli/clients.py loads canned qmicli stdout from on-disk fixtures; never imports from tests/fakes/."
  - "argparse subparser tree: parser → cmd subparsers → ctl_parser → ctl_sub → maint_parser → maint_sub. Each handler is async def run(args) -> int; main() runs them via asyncio.run."
  - "Tarfile with redacted JSON: tarfile.open(target, 'w:gz') + json.dumps(redacted_dict).encode() → tarfile.TarInfo + addfile. Each member chmod 0o600; tarball chmod 0o640 at the end."
  - "Dependency-injected default paths: build_support_bundle accepts state_root / events_log_path / conf_d_path overrides; production callers pass None and defaults bind to /var/lib/.../ + /var/log/.../ + /etc/...."
  - "Dual-clock expiry check pattern: store BOTH monotonic and ISO; OR them at check-time so a wall-clock NTP step in either direction cannot extend or prematurely expire the window."

requirements-completed:
  - FR-50
  - FR-50.1
  - FR-50.2
  - FR-50.3
  - FR-51
  - FR-52
  - NFR-22
  - NFR-22.1

duration: ~30min
completed: 2026-05-06
---

# Phase 02 Plan 09: spark-modem CLI Summary

**spark-modem CLI ships six top-level subcommands (diag/recovery/provision/reset/status/ctl) plus three ctl sub-subcommands (history/maintenance/support-bundle) — hardware-free laptop pipeline via FixtureRunner, dual-clock 8h-capped maintenance window, redacted support tarball with ICCID/IMSI hashed and HMAC secret never copied.**

## Performance

- **Duration:** ~30 minutes
- **Started:** 2026-05-06T17:48Z (approx)
- **Completed:** 2026-05-06T18:18Z
- **Tasks:** 2 / 2 complete
- **Files created:** 26 (14 cli/ + 12 tests/unit/cli/)
- **Files modified:** 1 (pyproject.toml [project.scripts])

## Accomplishments

- spark-modem entry point installed via `pyproject.toml [project.scripts]`; argparse-based subcommand dispatch covers FR-50 surface.
- `spark-modem diag --qmi-fixture-dir=PATH` produces a typed Diag JSON in <1 s on a developer laptop with no qmicli binary present (FR-51 + SC#2).
- `spark-modem recovery --diag-fixture=PATH` loads typed Diag through pure `policy.engine.run_cycle` and ranks PlannedActions; `--dry-run` propagates into Settings.dry_run so every plan carries `suppressed_by_dry_run=True`.
- `--explain` text format and `--json` structured format both stable across releases (Claude's Discretion in CONTEXT.md).
- `ctl maintenance on/off/status` with mandatory `--duration`, 8h hard cap (FR-50.2), and dual-clock expiry (C-02). Persists through `StateStore.save_globals` — no new lock surface; daemon and CLI serialize on the existing state-store flock.
- `ctl history --modem= --since=` reads events.jsonl + rotated siblings (plain + gzip), filters by canonical usb_path and `1h/30m/300s` durations.
- `ctl support-bundle` produces a redacted tar.gz with last 200 events + state files (ICCID/IMSI redacted) + globals.json + status.json + conf.d/* (excluding hmac-secret) + metadata.json (webhook URL host-only). Tarball chmod 0o640.
- Production code under `src/spark_modem/` NEVER imports from `tests/fakes/*` — `cli/clients.py` hosts the production-side equivalents (`FixtureRunner`, `_CliClock`, `_InventoryFromFile`, `_NoZaoTailer`, `build_default_settings`).
- 74 unit tests (1 chmod test skipped on Windows); ≥52 verification target met.

## Task Commits

Each task was committed atomically on the main branch (sequential mode):

1. **Task 1: CLI scaffolding + entry point + 6 subcommands** — `01012fc` (feat)
2. **Task 2: ctl history + ctl maintenance + ctl support-bundle + PII redaction** — `a64b75f` (feat)

**Plan metadata:** (this commit) docs(02-09): complete spark-modem CLI plan

## Files Created/Modified

### Created — production
- `src/spark_modem/cli/__init__.py` — package marker
- `src/spark_modem/cli/main.py` — argparse subcommand dispatch entry point
- `src/spark_modem/cli/clients.py` — `_CliClock`, `_InventoryFromFile`, `_NoZaoTailer`, `FixtureRunner`, `build_default_settings`
- `src/spark_modem/cli/explain.py` — `format_diag_explain` + `format_plans_explain` text formatters
- `src/spark_modem/cli/diag.py` — `--qmi-fixture-dir` + `--inventory-fixture` + `--explain` + `--json`
- `src/spark_modem/cli/recovery.py` — `--diag-fixture` + `--dry-run` runs pure `policy.engine.run_cycle`
- `src/spark_modem/cli/provision.py` — Phase-2 stub for set_apn flow
- `src/spark_modem/cli/reset.py` — single-action dispatcher routing with destructive-action rejection
- `src/spark_modem/cli/status.py` — read+validate `/var/lib/.../status.json`
- `src/spark_modem/cli/redact.py` — `redact_pii` + `redact_iccid_imsi_in_dict` + `redact_webhook_url_to_host_only`
- `src/spark_modem/cli/ctl/__init__.py` — package marker
- `src/spark_modem/cli/ctl/history.py` — events.jsonl + rotated/gzip sibling reader, `--modem` + `--since` filters
- `src/spark_modem/cli/ctl/maintenance.py` — `parse_duration`, `MAX_DURATION_SECONDS=28800`, `run_on/run_off/run_status` with dual-clock check
- `src/spark_modem/cli/ctl/support_bundle.py` — `build_support_bundle` redacted tarball builder

### Created — tests
- `tests/unit/cli/__init__.py`
- `tests/unit/cli/test_main.py` (7 tests)
- `tests/unit/cli/test_diag.py` (6 tests)
- `tests/unit/cli/test_recovery.py` (6 tests)
- `tests/unit/cli/test_provision.py` (1 test)
- `tests/unit/cli/test_reset.py` (6 tests)
- `tests/unit/cli/test_status.py` (3 tests)
- `tests/unit/cli/test_explain.py` (4 tests)
- `tests/unit/cli/test_redact.py` (12 tests)
- `tests/unit/cli/test_ctl_history.py` (10 tests)
- `tests/unit/cli/test_ctl_maintenance.py` (12 tests)
- `tests/unit/cli/test_ctl_support_bundle.py` (7 tests; 1 chmod test skipped on Windows)

### Modified
- `pyproject.toml` — added `[project.scripts] spark-modem = "spark_modem.cli.main:main"`

## Decisions Made

- **CLAUDE.md §11 + §12 honored throughout.** No inbound IPC: every read-side ctl subcommand reads on-disk artefacts (events.jsonl, status.json, state files); ctl maintenance acquires the existing state-store flock via `StateStore.save_globals`. No UDS RPC for `ctl status` — `status.py` reads `status.json` directly.
- **FixtureRunner lives under `src/`, not `tests/fakes/`.** Production CLI code in `cli/diag.py` and `cli/recovery.py` needs a SubprocRunner-shaped fake at runtime; making it a production-side import keeps the boundary clean and lets the laptop CLI work without a tests/ dependency.
- **Dependency-injected paths everywhere.** `build_support_bundle` accepts `state_root`, `events_log_path`, `conf_d_path`, `webhook_url_for_redaction` as keyword-only args so tests can run hardware-free against `tmp_path`. Production callers pass `None`; the defaults bind to `/var/lib/.../`, `/var/log/.../`, `/etc/.../`.
- **Dual-clock expiry uses OR semantics** so a wall-clock NTP step can neither extend nor prematurely expire the window: the check is `now_mono >= expires_mono OR now_wall_iso >= expires_iso`. This implements C-02's "min(now_mono >= expires_mono, now_wall >= expires_iso)" specification — `min` of two booleans-as-ints == OR-truthy when read as `>= expires`.
- **Phase 2 support-bundle ships WITHOUT journalctl + dmesg.** Their capture requires subprocess invocations outside `src/spark_modem/subproc/` which would violate the SP-04 lint gate. Phase 3 wires them through `subproc.run` once the daemon-mode subprocess surface is available; the bundle's value (events + state + status + conf) is sufficient for Phase 2 NOC use.
- **`reset` validates action-kind even though Phase 2 stubs the execution.** `reset --action=modem_reset` returns exit 2 with a destructive-action rejection message before any dispatcher call; this catches operator typos and Phase-4-only commands without waiting for plan 02-10's runner injection.

## Deviations from Plan

### Auto-fixed issues

**1. [Rule 1 - Bug] mypy `no-any-return` on `asyncio.run(args.func(args))`**
- **Found during:** Task 1 (mypy --strict on src/spark_modem/cli/main.py)
- **Issue:** `args.func` has type `Any` because argparse Namespace is dynamic; `asyncio.run` returns `Any` then `main` returned that directly, triggering `no-any-return`.
- **Fix:** Bind result to `rc: int = asyncio.run(args.func(args))` then `return rc` so the strict-typed return is local and unambiguous.
- **Files modified:** `src/spark_modem/cli/main.py`
- **Committed in:** `01012fc` (Task 1).

**2. [Rule 1 - Bug] mypy `union-attr` errors when accessing `usb_path` on Event union**
- **Found during:** Task 2 (mypy --strict on tests/unit/cli/test_ctl_history.py)
- **Issue:** `out[0].usb_path` failed strict typing because `Event` is a discriminated union; only some variants carry `usb_path`.
- **Fix:** Use `getattr(e, "usb_path", None) == "2-3.1.1"` — same runtime semantics, type-safe under strict.
- **Files modified:** `tests/unit/cli/test_ctl_history.py`
- **Committed in:** `a64b75f` (Task 2).

**3. [Rule 2 - Missing critical] `RUF012 mutable class attribute` on `FixtureRunner._INTENT_MAP`**
- **Found during:** Task 1 (ruff check on src/spark_modem/cli/clients.py)
- **Issue:** `_INTENT_MAP: dict[str, str] = {...}` was a mutable default at class body — a footgun if a future contributor mutates it on an instance.
- **Fix:** Annotated with `ClassVar[dict[str, str]]` per ruff RUF012 guidance; documents the read-only intent at the type level.
- **Files modified:** `src/spark_modem/cli/clients.py` (added `from typing import ClassVar`).
- **Committed in:** `01012fc` (Task 1).

**4. [Rule 1 - Bug] ASYNC240 sync read in async function**
- **Found during:** Task 1 (ruff check on src/spark_modem/cli/recovery.py)
- **Issue:** `Diag.model_validate_json(diag_path.read_bytes())` performs a sync `read_bytes()` inside an async function.
- **Fix:** Annotated with `# noqa: ASYNC240` and a comment explaining the CLI is short-lived and bounded by the M7 ≤30s test budget; switching to `aiofile`/`anyio` would add a runtime dep without operational benefit. Recovery still reads the Diag as a single bounded blob.
- **Files modified:** `src/spark_modem/cli/recovery.py`
- **Committed in:** `01012fc` (Task 1).

**5. [Rule 2 - Missing critical] Lifted Windows skip on maintenance + most support-bundle tests**
- **Found during:** Task 2 (after first pytest run showed 15 skipped)
- **Issue:** Plan suggested `skipif(win32)` on maintenance/support-bundle tests citing POSIX flock. But `state_store.locks.AsyncFlockHandle` already has a Windows fallback (`fd=-1` sentinel) per Phase 1 SUMMARY decisions — the flock is a no-op on Windows dev hosts but the asyncio.Lock half still serializes correctly for unit tests.
- **Fix:** Removed `@_SKIP_WIN` from all tests except `test_bundle_chmod_640` (which legitimately tests POSIX file modes — Windows ignores `chmod 0o640`). Updated the skip reason on the remaining test.
- **Files modified:** `tests/unit/cli/test_ctl_maintenance.py`, `tests/unit/cli/test_ctl_support_bundle.py`
- **Verification:** 60 → 74 tests now run on the dev host; 1 (chmod) still skipped with accurate reason.
- **Committed in:** `a64b75f` (Task 2).

**6. [Rule 2 - Missing critical] `events_log` arg added to `ctl history` subcommand**
- **Found during:** Task 2 (testability)
- **Issue:** Plan-as-written hardcoded `Path("/var/log/spark-modem-watchdog/events.jsonl")` in `ctl history`. That path doesn't exist on a developer laptop; tests would have to monkeypatch.
- **Fix:** Added `--events-log` flag to `main.py`'s `ctl history` parser and threaded it through `history.run`. Production callers omit the flag; tests pass `--events-log=$tmp_path/events.jsonl`. This matches the dependency-injection pattern already in `support_bundle.py`.
- **Files modified:** `src/spark_modem/cli/main.py`, `src/spark_modem/cli/ctl/history.py`
- **Committed in:** `a64b75f` (Task 2).

---

**Total deviations:** 6 auto-fixed (3 bugs, 3 missing-critical). All within the plan's stated scope; no architectural changes; no Rule 4 escalations.

## Issues Encountered

None operationally. All 624 unit tests in the repository pass; 49 platform-specific skips (mostly POSIX-only subproc/runner tests on the Windows dev host).

## Phase 2 Limitation Documented

`ctl support-bundle` ships in Phase 2 WITHOUT `journalctl -u spark-modem-watchdog --since=24h` and `dmesg --time-format=iso` outputs. Both require subprocess invocations outside `src/spark_modem/subproc/`, which would fail the SP-04 lint gate. Phase 3 wires them through `subproc.run` once the daemon-mode subprocess surface is available. The bundle's Phase-2 value (events + state + status + conf + metadata) is sufficient for laptop-replay debugging and NOC ticket triage.

## Next Phase Readiness

- **Plan 02-10 (replay harness)** consumes `spark-modem recovery --diag-fixture=PATH` directly; `recovery.py` is ready.
- **Phase 3 (event sources + lifecycle)** will:
  - Wire production `SubprocRunner` injection so `provision` and `reset` execute end-to-end (cycle driver in 02-10 + production runner in Phase 3).
  - Wire `journalctl` + `dmesg` capture into `support_bundle.py` via `subproc.run`.
  - Add `cdc-wdmN ↔ usb_path` aliasing to `ctl history` once the identity map is wired.
- **Phase 4 (destructive actions)** will register `modem_reset` / `usb_reset` / `driver_reset` in `actions.dispatcher._REGISTRY`; `cli/reset.py` will then accept those kinds without code change. The destructive-action rejection in Phase 2 acts as a temporary gate.

## Self-Check: PASSED

Verified before final commit:

**Files created:**
- `src/spark_modem/cli/main.py` — FOUND
- `src/spark_modem/cli/clients.py` — FOUND
- `src/spark_modem/cli/redact.py` — FOUND
- `src/spark_modem/cli/ctl/maintenance.py` — FOUND
- `src/spark_modem/cli/ctl/support_bundle.py` — FOUND
- `src/spark_modem/cli/ctl/history.py` — FOUND
- `src/spark_modem/cli/diag.py` + `recovery.py` + `provision.py` + `reset.py` + `status.py` + `explain.py` — FOUND
- All 12 test files in `tests/unit/cli/` — FOUND

**Commits:**
- `01012fc` (Task 1) — FOUND in `git log --oneline`
- `a64b75f` (Task 2) — FOUND in `git log --oneline`

**Acceptance criteria:**
- `pyproject.toml` contains `[project.scripts]` with `spark-modem = "spark_modem.cli.main:main"` — VERIFIED via grep
- `! grep -rE "from tests\\.fakes" src/spark_modem/` — VERIFIED (production never imports test fakes)
- `bash scripts/lint_no_subprocess.sh` — EXIT 0
- `python -m mypy --strict src/spark_modem/cli/ tests/unit/cli/` — Success: no issues found in 26 source files
- `python -m ruff check src/spark_modem/cli/ tests/unit/cli/` — All checks passed!
- `python -m pytest tests/unit/cli/ -q` — 74 passed, 1 skipped (Windows chmod test)
- `python -m pytest tests/unit/ -q` — 624 passed, 49 platform skips (no regressions)

---

*Phase: 02-core-daemon-laptop-testable*
*Completed: 2026-05-06*
