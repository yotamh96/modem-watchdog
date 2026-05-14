# Phase 05.6 — Deferred Items

Items discovered during execution that fall outside the current plan's
scope. Tracked here so a future plan can address them.

## 05.6-01

### `tests/hil/scenarios/test_watchdog_90s_actual_fire.py` — needs renaming + budget bump

**Discovered during:** Task 2 (WatchdogSec 90 → 180 unit-file edit).

**What:** The opt-in HIL scenario `test_watchdog_90s_actual_fire.py`
hardcodes the 90-second budget in:

- The filename (`test_watchdog_90s_actual_fire.py`).
- Docstring text (multiple references to "WatchdogSec=90s").
- `_WATCHDOG_BUDGET_S = 100.0` (90s + 10s margin) — now needs to be
  ≥190.0 to give the new WatchdogSec=180s headroom.
- `test_watchdog_90s_fires_when_cycle_wedged` function name.
- `tests/hil/README.md:72` references the filename.
- The companion test `tests/hil/scenarios/test_sigterm_within_5s.py:87`
  has a comment "WatchdogSec=90s + the daemon's 5 s deadline budget".

**Why deferred:** Pre-existing file outside this plan's
`files_modified` list. Renaming a HIL test file + bumping its budget
to ≥190s is a meaningful test-design change for an opt-in destructive
bench-Jetson scenario; the plan acceptance criterion for Task 2 only
called out `test_unit_file_audit.py` ("if it pins the 90s value,
update it... otherwise leave alone"). The HIL test is gated behind
`BENCH_JETSON_DESTRUCTIVE_TESTS_OK=true` so it does not run in the
normal CI gate; the production WatchdogSec value is what bench
Jetsons actually enforce.

**Suggested next plan:** Rename to `test_watchdog_180s_actual_fire.py`,
bump `_WATCHDOG_BUDGET_S = 190.0`, refresh docstrings, update the
README cross-reference, and clean up the `test_sigterm_within_5s.py`
comment. Could roll into 05.6-05 (integration test plan) since both
live in the test suite, or stand alone after Phase 05.6 closes.

### `tests/integration/test_daemon_preflight_triple.py` — pre-existing bitrot vs Phase 05.2 Settings() fix

**Discovered during:** Task 3 (verifying my changes did not break the
existing daemon-preflight-triple integration tests).

**What:** All three tests in this file were failing on `main` BEFORE
my Task 3 edits — confirmed by stashing the working tree and re-
running. Root cause: the tests monkeypatch
`daemon_main.build_default_settings`, but Phase 05.2's hotfix changed
`_production_main` to call `Settings()` directly (not
`build_default_settings()`). The patched factory is dead code; the
real `Settings()` returns production defaults (`/var/lib/...`,
`/run/spark-modem-watchdog/...`) which on Windows resolve to
`S:\var\lib\...` etc, so the test assertions on
`tmp_path/run/last-config-error` always miss.

**Why deferred:** Pre-existing failure documented as such by
`git stash && pytest` reproducing the same `AssertionError` on the
prior commit (`d5326d0`). This plan's `files_modified` list is
`settings.py`, `spark-modem-watchdog.service`, `daemon/main.py` —
not this test file. Fixing it requires deciding the right test
strategy (env-var-driven Settings, or making
`_production_main` accept a Settings instance for testability).

**Suggested next plan:** Either roll into 05.6-05 (integration test
plan; the planner suggested introducing
`tests/integration/test_production_main.py` via a dependency-injection
seam — same seam should let this file get a working monkeypatch);
or split into a tiny standalone test-repair plan that converts the
three tests to env-var-driven `Settings()` instantiation. Acceptance
once fixed: `pytest tests/integration/test_daemon_preflight_triple.py`
exits 0 cross-platform.
