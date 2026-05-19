---
id: T01
parent: S02
milestone: M001
provides:
  - tests/fixtures/{qmicli,zao_log,inventory,diag,replay}/: empty fixture roots
  - tests/fixtures/inventory/four_modems.json: lab USB topology seed
requires: []
affects: []
key_files: []
key_decisions: []
patterns_established: []
observability_surfaces: []
drill_down_paths: []
duration: 5min
verification_result: passed
completed_at: 2026-05-06
blocker_discovered: false
---
# T01: 02-core-daemon-laptop-testable 01

**# Phase 2 Plan 01: Test Fakes & Fixture Roots Summary**

## What Happened

# Phase 2 Plan 01: Test Fakes & Fixture Roots Summary

**Six hardware-free test fakes (FakeRunner, FakeClock, FixtureZaoTailer, FakeWebhookPoster, FixtureInventory, FakeDNSResolver) plus five tracked fixture-root directories — every Wave 2-6 plan can now import from `tests/fakes/` and develop in parallel.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-05-06T15:52:20Z
- **Completed:** 2026-05-06T15:57:25Z
- **Tasks:** 2
- **Files created:** 20

## Accomplishments

- All six Wave-0 fakes named in RESEARCH §6 exist with mypy --strict + ruff + ruff format green
- 19 self-tests (3 runner + 3 clock + 3 zao_log + 3 webhook + 3 inventory + 4 dns) all pass under pytest-asyncio mode=auto
- Every fake mirrors the exact signature of the production callable it stands in for (FakeRunner.run mirrors subproc.runner.run; FakeClock mirrors clock module functions; FakeDNSResolver mirrors DnsCache.resolve)
- tests/fixtures/inventory/four_modems.json seeded with the lab USB topology (VID:PID 1199:9091 at 2-3.1.{1..4}) — Plan 02-04 observer tests can consume this directly
- SP-04 lint gate (`scripts/lint_no_subprocess.sh`) remains green: no fake imports the subprocess module or calls create_subprocess_exec
- Production code does not import from tests/fakes/* (verified by grep; T-02-01-01 mitigation)

## Task Commits

1. **Task 1: FakeRunner, FakeClock, FixtureZaoTailer + self-tests** — `006cc1f` (feat)
2. **Task 2: FakeWebhookPoster, FixtureInventory, FakeDNSResolver, fixture roots, four_modems.json + self-tests** — `efc0bd1` (feat)

**Plan metadata:** added in the final commit alongside this SUMMARY.md and STATE.md update.

## Files Created/Modified

### Test fakes (`tests/fakes/`)
- `runner.py` — `FakeRunner` argv→CompletedProcess map; mirrors `subproc.runner.run()` signature; raises KeyError on unregistered argv
- `clock.py` — `FakeClock` instance-method clock; `advance(seconds)` moves both monotonic and wall clocks forward
- `zao_log.py` — `FixtureZaoTailer` canned `is_line_active(line)` answers; supports `set_active(set[int])` mid-test
- `webhook.py` — `FakeWebhookPoster` records `sent` envelopes; `drain()` is a no-op
- `inventory.py` — `FixtureInventory` reads `<scenario>.json`; defines local `_FixtureModemDescriptor` pydantic v2 shape
- `dns.py` — `FakeDNSResolver` canned IP + `set_fail_next()` one-shot; `set_canned_ip(None)` for persistent failure
- `__init__.py` — empty package marker

### Self-tests (`tests/unit/fakes/`)
- `test_runner.py` — register/run/canned-result, KeyError on unknown argv, calls-recording with defensive copy
- `test_clock.py` — advance increments monotonic exactly, default wall starts 2026-01-01 UTC, negative advance raises
- `test_zao_log.py` — is_line_active checks, constructor seeding, set_active replaces (not unions)
- `test_webhook.py` — enqueue records to sent, order preserved across calls, drain is no-op
- `test_inventory.py` — loads four-modem fixture, rejects extra fields, returns empty when no modems key
- `test_dns.py` — canned IP returned, one-shot fail self-clears, persistent None canned, canned IP changeable mid-test
- `__init__.py` — empty package marker

### Fixture roots (`tests/fixtures/`)
- `qmicli/.gitkeep` — per-libqmi-version qmicli text fixtures (Plan 02-02 will populate)
- `zao_log/.gitkeep` — RASCOW_STAT scenario logs (Plan 02-03 will populate)
- `inventory/.gitkeep` — sysfs inventory snapshots (Plan 02-04 will populate)
- `diag/.gitkeep` — full Diag JSON snapshots (Plan 02-05 will populate)
- `replay/.gitkeep` — ≥1000 synthesized cycles (Plan 02-10 will populate)
- `inventory/four_modems.json` — seeded lab topology (consumed by Plan 02-04)

## Decisions Made

- **Local fixture-only pydantic shape over forward import:** `_FixtureModemDescriptor` lives inside `tests/fakes/inventory.py` (not yet imported from `inventory/protocol.py`). This decouples Plan 02-01 from Plan 02-04 inside Wave 1; when 02-04 lands, the fake is updated to import the production type. Avoids a circular dependency in plan ordering.
- **`del` keyword-only parameters in fakes:** Each fake accepts the full keyword-only signature of its production counterpart (e.g., `timeout_s`, `stdin`, `env` in FakeRunner.run; `loop` in FakeDNSResolver.resolve) and immediately `del`s them. This makes the fake call-surface-identical to production at the type level so SUT code parameterized over a callable doesn't change shape between test and production.
- **Default FakeClock wall start = 2026-01-01:** Matches the project `currentDate` and gives every test a date-stable, self-documenting ISO stamp. Tests can override via `start_wall=` kwarg.
- **One-shot fail flag in FakeDNSResolver:** Models the W-02 contract that a single transient resolve failure must not permanently strand the poster (the production code uses a 600 s `_stale_until` window for the same purpose).
- **Defensive copy on `FakeRunner.calls`:** The `calls` property returns a fresh list of fresh lists, so a test mutating the snapshot does not corrupt subsequent assertions.

## Deviations from Plan

None of consequence. Two micro-deviations worth flagging for completeness:

### Tweak 1: Docstring wording in `tests/fakes/runner.py` to satisfy literal acceptance criterion

- **Found during:** Task 1 verification (acceptance criterion `tests/fakes/runner.py does NOT contain 'subprocess' or 'create_subprocess_exec' (greps return zero matches)`)
- **Issue:** Initial docstring contained the string "subprocess" inside the prose ("…without spawning a real subprocess.") — a substring hit even though the fake never invokes subprocess code.
- **Fix:** Reworded to "without spawning a real child process." Substantive meaning unchanged; literal grep now returns zero matches.
- **Files modified:** `tests/fakes/runner.py`
- **Verification:** `grep -E "subprocess|create_subprocess_exec" tests/fakes/runner.py | wc -l` → 0
- **Committed in:** `006cc1f` (Task 1 commit, before commit was finalized)

### Tweak 2: Expanded test coverage above the plan's minimum

- **Found during:** Task 1 (the plan asked for "7 tests collected"); Task 2 (plan asked for "≥10 tests")
- **Issue:** None — opportunistic additional coverage.
- **Fix:** Added a 3rd test for FixtureZaoTailer (`set_active replaces not unions`), expanded test_clock to include `elapsed_since` assertion, added `test_set_canned_ip_changes_returned_value` to test_dns. Final count: 19 tests collected (vs plan's ≥10). All green.
- **Files modified:** `tests/unit/fakes/test_zao_log.py`, `tests/unit/fakes/test_clock.py`, `tests/unit/fakes/test_dns.py`
- **Verification:** `pytest tests/unit/fakes/ -q` → 19 passed
- **Committed in:** `006cc1f` and `efc0bd1` (part of the respective task commits)

---

**Total deviations:** 2 minor (1 docstring reword, 1 test-count expansion). No deviation rules invoked; no architectural changes; no auth gates.
**Impact on plan:** None — plan executed exactly as designed. Fixes only sharpened compliance with the literal acceptance criteria.

## Issues Encountered

None. Phase 1 foundations are clean; the fakes mirror existing surfaces without ambiguity. Local development environment (`.venv` with Python 3.12.13, pytest 8.4.2, mypy 1.20.2, ruff 0.15.12) had everything needed.

## Threat Model Compliance

The plan's `<threat_model>` registers three accept-disposition threats; all confirmed mitigated by the implementation:

- **T-02-01-01 (Tampering):** `grep -rE "tests\.fakes|tests/fakes" src/spark_modem/` returns zero matches — production code does not import test fakes.
- **T-02-01-02 (Information disclosure):** `tests/fixtures/inventory/four_modems.json` contains only lab USB topology (`2-3.1.{1..4}`) — no PII, ICCID, IMSI, secret, or credential.
- **T-02-01-03 (Elevation of privilege):** `FakeRunner.run` is async-purely-data — never calls `asyncio.create_subprocess_exec` or any kernel-touching API. SP-04 lint gate confirms.

## Verification Block Results (per plan `<verification>`)

| Check | Command | Result |
|-------|---------|--------|
| mypy strict, src + fakes + unit/fakes | `python -m mypy --strict src/ tests/fakes/ tests/unit/fakes/` | Success: no issues found in 45 source files |
| ruff check, src + fakes + unit/fakes | `python -m ruff check src/ tests/fakes/ tests/unit/fakes/` | All checks passed |
| ruff format check | `python -m ruff format --check src/ tests/fakes/ tests/unit/fakes/` | 45 files already formatted |
| pytest fakes ≥10 tests | `python -m pytest tests/unit/fakes/ -q` | 19 passed |
| SP-04 subprocess lint | `bash scripts/lint_no_subprocess.sh` | exit 0 |
| Production does not import fakes | `! grep -r "tests.fakes\|tests/fakes" src/spark_modem/` | exit 0 (no matches) |

## Next Phase Readiness

- Wave 2 plans (02-02 qmi/parsers, 02-03 zao_log, 02-04 observer+inventory, 02-05 policy) can now `from tests.fakes.runner import FakeRunner` and `from tests.fakes.clock import FakeClock` without further setup.
- Fixture roots are in place. Plan 02-02 will populate `tests/fixtures/qmicli/<intent>/<libqmi-version>/*.txt`; Plan 02-03 will populate `tests/fixtures/zao_log/*.log`; Plan 02-04 will reuse `tests/fixtures/inventory/four_modems.json`; Plan 02-05 will write per-cycle fixtures to `tests/fixtures/diag/*.json`; Plan 02-10 will fill `tests/fixtures/replay/<scenario>/<NNN>.json` (≥1000 entries).
- When Plan 02-04 introduces production `inventory/protocol.py` with the canonical `ModemDescriptor`, `tests/fakes/inventory.py` should be updated to import it directly and drop the local `_FixtureModemDescriptor` shape (one-line follow-up; not blocking).
- No blockers, no concerns. Wave 2 is unblocked.

## Self-Check: PASSED

- File `tests/fakes/runner.py` exists — FOUND
- File `tests/fakes/clock.py` exists — FOUND
- File `tests/fakes/zao_log.py` exists — FOUND
- File `tests/fakes/webhook.py` exists — FOUND
- File `tests/fakes/inventory.py` exists — FOUND
- File `tests/fakes/dns.py` exists — FOUND
- All five `tests/fixtures/*/.gitkeep` exist — FOUND
- `tests/fixtures/inventory/four_modems.json` exists — FOUND
- All six `tests/unit/fakes/test_*.py` exist — FOUND
- Commit `006cc1f` exists — FOUND
- Commit `efc0bd1` exists — FOUND

---
*Phase: 02-core-daemon-laptop-testable*
*Completed: 2026-05-06*
