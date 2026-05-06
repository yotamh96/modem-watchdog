---
phase: 01-foundations-adrs
plan: "06"
subsystem: clock, config, event_logger, carriers
tags:
  - python
  - clock
  - config
  - yaml
  - event-logger
  - carrier-table
dependency_graph:
  requires:
    - 01-01 (packaging/requirements.in — pydantic-settings pin)
    - 01-03 (wire/carriers.py CarrierTable validator + hostile fixtures)
  provides:
    - clock.monotonic / elapsed_since / wall_clock_iso (ADR-0007 surface)
    - config.Settings (pydantic-settings BaseSettings, env_prefix=SPARK_MODEM_)
    - config.deep_merge / load_yaml_layer (YAML conf.d/* merger)
    - config.RELOAD_DATA / RELOAD_RESTART / restart_required_fields (SIGHUP marker)
    - event_logger.EventLogWriter / EventLogClosedError (O_APPEND JSON Lines)
    - debian/conf.d/00-carriers.yaml (day-one IL/US/GB/DE carrier table)
  affects:
    - 01-02 (debian/spark-modem-watchdog.install adds carrier YAML install line)
    - Phase 2+ (clock/config/event_logger are the primary API surface)
    - Phase 3 (SIGHUP reload reads restart_required_fields; logrotate closes EventLogWriter)
tech_stack:
  added:
    - pydantic-settings==2.14.0 (installed; already pinned in packaging/requirements.in)
    - types-PyYAML==6.0.12 (mypy stubs for yaml module)
  patterns:
    - time.monotonic() behind clock.monotonic() indirection (ADR-0007)
    - Field(json_schema_extra={"reload": "restart|data"}) annotation convention
    - os.open(O_WRONLY|O_CREAT|O_APPEND) for atomic append-only JSON Lines
    - deep_merge: dict recurse, list/scalar replace (no extend)
key_files:
  created:
    - src/spark_modem/clock/clock.py
    - src/spark_modem/clock/__init__.py
    - src/spark_modem/event_logger/writer.py
    - src/spark_modem/event_logger/__init__.py
    - src/spark_modem/config/yaml_merge.py
    - src/spark_modem/config/reload_marker.py
    - src/spark_modem/config/settings.py
    - src/spark_modem/config/__init__.py
    - debian/conf.d/00-carriers.yaml
    - tests/unit/clock/__init__.py
    - tests/unit/clock/test_clock.py
    - tests/unit/event_logger/__init__.py
    - tests/unit/event_logger/test_writer.py
    - tests/unit/config/__init__.py
    - tests/unit/config/test_yaml_merge.py
    - tests/unit/config/test_reload_marker.py
    - tests/unit/config/test_settings.py
    - tests/integration/test_default_carrier_table.py
  modified: []
decisions:
  - "EventLogClosedError (ruff N818 rename from EventLogClosed); alias kept for compat"
  - "Settings model_validator enforces NFR-33 http-only block cross-field (field_validator sees URL, model_validator sees allow_http)"
  - "clock uses datetime.UTC alias (Python 3.12 UP017) instead of timezone.utc"
  - "types-PyYAML installed as dev dep for mypy --strict on yaml_merge.py"
  - "time.monotonic() in subproc/runner.py pre-dates clock/ (Plan 05); deferred migration to deferred-items"
metrics:
  duration_minutes: 11
  completed_date: "2026-05-06"
  tasks_completed: 3
  files_created: 18
  tests_added: 67
---

# Phase 1 Plan 06: clock, config, event_logger, carriers — Summary

**One-liner:** Monotonic clock abstraction (ADR-0007), pydantic-settings BaseSettings with RELOAD_DATA/RESTART markers, O_APPEND JSON Lines writer, and day-one IL/US/GB/DE carrier YAML validating against CarrierTable.

## What Was Built

### Task 1 — clock/ + event_logger/

**clock/clock.py** exposes three functions:
- `monotonic() -> float` — wraps `time.monotonic()`; all duration arithmetic must go through here (ADR-0007)
- `elapsed_since(t0) -> float` — `max(0.0, monotonic() - t0)`; clamped to zero for future t0
- `wall_clock_iso(*, tz=None) -> str` — `datetime.now(UTC).isoformat()`; for events.jsonl and webhook payloads

**event_logger/writer.py** — `EventLogWriter`:
- Opens with `os.open(O_WRONLY|O_CREAT|O_APPEND, 0o640)` — NFR-30 file mode
- `append(event: Event)` issues exactly one `os.write(fd, json_bytes + b"\n")`; events are typically < 500 bytes, under PIPE_BUF atomic threshold on Linux
- Raises `EventLogClosedError` (renamed per ruff N818; alias `EventLogClosed` kept) on closed writer
- Context-manager shaped; `fileno()` exposes the fd for Phase 3 inotify watcher

### Task 2 — config/

**yaml_merge.py**: `deep_merge(base, override)` (dict recurse, list/scalar replace) + `load_yaml_layer(conf_d_dir)` (lexical *.yaml glob, skip non-parseable files, return merged dict).

**reload_marker.py**: `RELOAD_DATA = {"reload": "data"}`, `RELOAD_RESTART = {"reload": "restart"}` as `json_schema_extra` values; `restart_required_fields(model_cls)` and `data_reloadable_fields(model_cls)` read them back from `model_fields`.

**settings.py**: `Settings(BaseSettings)` with:
- `env_prefix="SPARK_MODEM_"`, `extra="forbid"`, `frozen=True`
- Topology fields (`state_root`, `run_dir`, `events_log_path`, `metrics_socket_path`, `startup_delay_seconds`) tagged `RELOAD_RESTART`
- Data fields (`backoff_seconds`, `ladder_min_interval_seconds`, `healthy_streak_decay_k`, `webhook_*`, `maintenance_max_seconds`, `dry_run`, `carriers_yaml_path`) tagged `RELOAD_DATA`
- `field_validator` rejects non-http/https `webhook_url`; `model_validator` rejects `http://` when `webhook_allow_http=False` (NFR-33)
- `Settings.from_yaml_layer(yaml_dict)` applies a deep-merged YAML layer as kwargs

### Task 3 — debian/conf.d/00-carriers.yaml

12 entries, all MCCs and MNCs as quoted strings (prevents YAML 1.1 octal and Norway-problem coercions):

| Country | MCC/MNC | APN | Verified |
|---------|---------|-----|----------|
| IL | 425/01 | internetg | true |
| IL | 425/02 | internetg | true |
| IL | 425/03 | internetg | true |
| US | 310/410 | broadband | false |
| US | 311/480 | vzwinternet | false |
| US | 312/530 | fast.t-mobile.com | false |
| GB | 234/10 | m-bb.o2.co.uk | false |
| GB | 234/15 | internet | false |
| GB | 234/30 | everywhere | false |
| DE | 262/01 | internet.t-d1.de | false |
| DE | 262/02 | web.vodafone.de | false |
| DE | 262/03 | internet | false |

## Commits

| Hash | Description |
|------|-------------|
| c050b96 | feat(01-06): clock/ and event_logger/ thin modules with TDD |
| 2fa58f1 | feat(01-06): config/ — Settings + YAML merger + reload-marker convention |
| b746dd3 | feat(01-06): debian/conf.d/00-carriers.yaml + integration test |

## Test Results

- `tests/unit/clock/` — 10 tests
- `tests/unit/event_logger/` — 11 tests
- `tests/unit/config/` — 38 tests (yaml_merge: 10, reload_marker: 6, settings: 22)
- `tests/integration/test_default_carrier_table.py` — 8 tests
- **Total: 67 tests, all pass, wall time 0.67s** (target: < 2s)

## Quality Gates

- `mypy --strict src/spark_modem/clock/ src/spark_modem/config/ src/spark_modem/event_logger/` — 0 errors (8 source files)
- `ruff check` — clean on all new source and test files
- `ruff format --check` — clean
- `bash scripts/lint_no_subprocess.sh` — passes (no subprocess in any new module)

## Requirements Closed

- **FR-30.1** — day-one IL/US/UK/DE carriers landed in shipped config
- **FR-33.1** — hostile-input fixtures from Plan 03 still reject (regression cover in integration test)
- **FR-54** — configuration precedence infrastructure: YAML merger + pydantic-settings + reload markers; CLI layer Phase 2, SIGHUP listener Phase 3
- **FR-72** — Clock and EventLogWriter are concrete classes; Protocol shadows deferred to Phase 2
- **FR-73** — clock.monotonic() indirection; policy/ will not import time directly
- **Phase 1 SC #3** — carrier table covers IL (verified) + US/UK/DE (unverified), 12 entries, parses via CarrierTable.model_validate
- **Phase 1 SC #4 (partial)** — mypy --strict + ruff green on clock/, config/, event_logger/

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] pydantic-settings missing from venv**
- **Found during:** Task 1 pre-flight
- **Issue:** `pydantic-settings>=2.5,<3` is pinned in `packaging/requirements.in` (Plan 01) but was not yet installed in the dev venv
- **Fix:** `uv pip install "pydantic-settings>=2.5,<3"` — installed 2.14.0
- **Files modified:** none (venv only)

**2. [Rule 3 - Blocking] types-PyYAML missing for mypy --strict**
- **Found during:** Task 2 mypy check
- **Issue:** `yaml` module has no bundled stubs; mypy --strict fails with `import-untyped`
- **Fix:** `uv pip install types-PyYAML` — installed 6.0.12
- **Files modified:** none (venv only)

**3. [Rule 1 - Bug] os.get_blocking() not available on Windows**
- **Found during:** Task 1 test run
- **Issue:** `os.get_blocking(fd)` raises `OSError` on Windows dev host; production target is Linux/aarch64
- **Fix:** Replaced with `os.fstat(fd)` which is cross-platform; still proves fd is valid and open
- **Files modified:** `tests/unit/event_logger/test_writer.py`

**4. [Rule 1 - Bug] ruff N818 — EventLogClosed not ending in Error**
- **Found during:** Task 1 ruff check
- **Issue:** ruff N818 requires exception class names to end with `Error`
- **Fix:** Renamed to `EventLogClosedError`; added `EventLogClosed = EventLogClosedError` alias in `__init__.py` so plan-spec import names continue to work
- **Files modified:** `src/spark_modem/event_logger/writer.py`, `src/spark_modem/event_logger/__init__.py`

**5. [Rule 1 - Bug] Various ruff lint fixes (UP037, SIM105, PLC0415, F401, B017)**
- **Found during:** Task 1 and Task 2 ruff check
- **Fix:** Applied all suggested fixes: removed string quotes from return type annotations, used `contextlib.suppress(OSError)`, moved imports to top level, removed unused imports, used specific exception types in `pytest.raises`

### Out-of-Scope Observations (deferred)

- `src/spark_modem/subproc/runner.py` uses `time.monotonic()` directly (Plan 05 predates clock/). Migration to `clock.monotonic()` is a Phase 2 task since runner.py is a pre-existing module not touched by Plan 06. Logged to deferred-items.

## Cross-Plan Ownership Confirmation

Plan 06 did **NOT** modify:
- `packaging/requirements.in` (Plan 01 owns the pydantic-settings pin)
- `packaging/requirements.lock` (Plan 01 owns)
- `scripts/postinst_smoke_test.sh` (Plan 02 owns)
- `debian/spark-modem-watchdog.install` (Plan 02 adds the carrier YAML install line)

## Known Stubs

None — all data is wired. The `Settings.from_yaml_layer()` classmethod is fully functional.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries beyond those in the plan's threat model (T-06-01 through T-06-07).

## Self-Check: PASSED

All 10 source/config files found on disk. All 3 task commits verified in git log (c050b96, 2fa58f1, b746dd3).
