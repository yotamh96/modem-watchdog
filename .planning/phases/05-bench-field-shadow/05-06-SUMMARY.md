---
phase: 05-bench-field-shadow
plan: 06
subsystem: debian-packaging
tags: [debian, packaging, dh-install, x-03, phase-5]

# Dependency graph
requires:
  - phase: 05-bench-field-shadow
    provides: Plan 05-03 example fixture tests/fixtures/fleet/_test/triple.json — shipped via the new debian/install rule so the daemon preflight (Plan 05-04) has at least one entry on first install
  - phase: 05-bench-field-shadow
    provides: Plan 05-04 preflight_check_known_fleet_triple reads /etc/spark-modem-watchdog/known-fleet/<box-id>/triple.json — this plan creates that directory at .deb install time
  - phase: 01-foundations-adrs
    provides: debian/spark-modem-watchdog.install + debian/spark-modem-watchdog.dirs (existing dh_install machinery) — the new entries plug into the existing files unmodified
provides:
  - "debian/spark-modem-watchdog.install +1 line: tests/fixtures/fleet /etc/spark-modem-watchdog/known-fleet/ — dh_install recursively copies the fleet fixture tree at .deb build time"
  - "debian/spark-modem-watchdog.dirs +1 line: /etc/spark-modem-watchdog/known-fleet — package-owned directory created before dh_install (so dpkg owns even an empty dir)"
  - "tests/integration/test_deb_ships_known_fleet.py (124 LOC, 6 tests) — pins the packaging contract: 5 always-on static checks + 1 dpkg-deb --contents check skipped on hosts without dpkg-deb"
affects:
  - 06+ (cutover) — every fleet box's first .deb install now lands /etc/spark-modem-watchdog/known-fleet/_test/triple.json plus any per-box <box-id>/triple.json captured during the X-04 batched-prereq PR, so the daemon preflight has data to validate against
  - X-04 batched-prereq PR (deferred per CONTEXT.md scope_pivot) — when per-box triple.json files land under tests/fixtures/fleet/<box-id>/, the next .deb release ships them automatically (no further debian/install edit needed)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Declarative dh_install for read-only package data — preferred over imperative postinst writes per RESEARCH Q10; dpkg handles atomic upgrade-time replace, package owns the directory, daemon never writes"
    - "Cross-platform-safe integration test via shutil.which + pytest.skip — the dpkg-deb path runs on Debian build hosts and skips cleanly on Windows dev laptops; the static checks (debian/install + debian/dirs + fixture validity + anti-pattern pins) run unconditionally"
    - "Anti-pattern pins as tests — test_no_known_fleet_references_in_postinst and test_no_known_fleet_references_in_rules lock the RESEARCH Q10 design choice so a future refactor can't quietly migrate known-fleet shipment into postinst/rules without the tests failing"

key-files:
  created:
    - tests/integration/test_deb_ships_known_fleet.py (124 LOC, 6 tests; 5 pass + 1 skip on Windows dev host; expected 6 pass on Debian build host with a freshly built .deb)
  modified:
    - debian/spark-modem-watchdog.install (+1 line — tests/fixtures/fleet /etc/spark-modem-watchdog/known-fleet/)
    - debian/spark-modem-watchdog.dirs (+1 line — /etc/spark-modem-watchdog/known-fleet inserted alphabetically between conf.d and /var/lib/...)

key-decisions:
  - "Followed RESEARCH Q10 final recommendation verbatim — ship tests/fixtures/fleet directly as /etc/spark-modem-watchdog/known-fleet/<box-id>/triple.json (no sha-rename, no build-time index synthesis). The daemon's _load_known_triples walks one level deep for triple.json files; this packaging contract feeds that walker exactly the shape it expects."
  - "No changes to debian/spark-modem-watchdog.postinst — the existing postinst stays scoped to ModemManager masking + state-dir creation + the B-03 smoke test. Known-fleet shipment is pure data movement; dh_install handles it before postinst runs."
  - "No changes to debian/rules — declarative debian/install is the simplest path per RESEARCH Q10 §637. The big override_dh_auto_install block in rules already handles the bundled CPython tree + uv pip install + stdlib trim; adding a known-fleet step there would couple two unrelated concerns."
  - "Integration test ships in tests/integration/ alongside test_unit_file_audit.py (cross-platform-safe debian/* parser) rather than under a new tests/packaging/ subtree — the latter would duplicate conftest.py infrastructure for a single test file."

patterns-established:
  - "Plan 05-06 closes the X-* deliverable family on the packaging side — X-01 (capture verb in Plan 05-03), X-02 (PII redaction baked into the verb), X-03 (daemon gate in Plan 05-04 + packaging shipment in Plan 05-06) — every fleet box's first apt install now lands the read-only known-fleet directory the daemon needs"
  - "Anti-pattern pinning via tests — the two test_no_known_fleet_references_in_{postinst,rules} cases lock the RESEARCH Q10 design choice into the test suite; future refactors that try to migrate known-fleet shipment into postinst or override_dh_auto_install will fail these tests and force a deliberate design revisit"

requirements-completed:
  - X-03

# Metrics
duration: ~4min
completed: 2026-05-11
---

# Phase 5 Plan 06: `.deb` ships /etc/spark-modem-watchdog/known-fleet/ via debian/install Summary

**Shipped the packaging side of X-03: dh_install copies tests/fixtures/fleet to /etc/spark-modem-watchdog/known-fleet/ at .deb build time, debian/dirs pre-creates the directory, and 6 integration tests pin the contract — postinst and debian/rules stay untouched per RESEARCH Q10. The X-* deliverable family is now complete end-to-end (capture verb → preflight gate → packaging shipment).**

## Performance

- **Duration:** ~4 min wall-clock (2 commits across ~3m 41s of git activity)
- **Started:** 2026-05-11T09:10:54Z
- **Completed:** 2026-05-11T09:14:35Z
- **Tasks:** 2/2 complete
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments

- **`debian/spark-modem-watchdog.install`** (`debian/spark-modem-watchdog.install:10`) — appended one declarative dh_install rule: `tests/fixtures/fleet /etc/spark-modem-watchdog/known-fleet/`. dh_install recursively copies the source directory tree, preserving the `<box-id>/triple.json` shape that Plan 05-04's `_load_known_triples` walks.
- **`debian/spark-modem-watchdog.dirs`** (`debian/spark-modem-watchdog.dirs:2`) — inserted `/etc/spark-modem-watchdog/known-fleet` alphabetically between `/etc/spark-modem-watchdog/conf.d` and `/var/lib/spark-modem-watchdog`. dpkg owns the directory even when `tests/fixtures/fleet/` is small (T-05-06-01 belt-and-suspenders).
- **`tests/integration/test_deb_ships_known_fleet.py`** (124 LOC, 6 tests) — pins the packaging contract end-to-end:
  - `test_deb_contains_known_fleet_path` — runs `dpkg-deb --contents` against the most recent built .deb under `dist/` or `../`; skipped via `shutil.which("dpkg-deb") is None` on hosts without dpkg-deb (Windows dev laptop) and via `pytest.skip` on hosts without a built artifact.
  - `test_debian_install_declares_known_fleet` — asserts `tests/fixtures/fleet` and `/etc/spark-modem-watchdog/known-fleet` are both present in `debian/spark-modem-watchdog.install` (catches accidental revert).
  - `test_debian_dirs_declares_known_fleet` — asserts `/etc/spark-modem-watchdog/known-fleet` is present in `debian/spark-modem-watchdog.dirs`.
  - `test_example_fleet_fixture_exists_and_is_valid` — asserts `tests/fixtures/fleet/_test/triple.json` exists and parses as JSON with non-empty `em7421_firmware`, `zao_sdk`, `libqmi` string fields (Plan 05-03 dependency + T-05-06-01 mitigation pin).
  - `test_no_known_fleet_references_in_postinst` — anti-pattern pin per RESEARCH Q10 §647-650.
  - `test_no_known_fleet_references_in_rules` — anti-pattern pin per RESEARCH Q10 §637.
- **No changes to `debian/spark-modem-watchdog.postinst`** (verified via `git diff HEAD~2 HEAD -- debian/spark-modem-watchdog.postinst` returns empty). Postinst stays scoped to user/group creation + ModemManager masking + state-dir creation + B-03 smoke test.
- **No changes to `debian/rules`** (verified via `git diff HEAD~2 HEAD -- debian/rules` returns empty). The existing `override_dh_auto_install` for the bundled CPython tree is untouched.
- **Plan 05-04 ↔ Plan 05-06 contract pinned** — the daemon reads `/etc/spark-modem-watchdog/known-fleet/<box-id>/triple.json` (preflight_triple.py:46 + 78-89); this plan ships exactly that path layout via dh_install's directory-copy semantics. No path drift.

## Verification Summary

| Check | Status |
| ----- | ------ |
| `pytest tests/integration/test_deb_ships_known_fleet.py -v` (plan scope) | **5 passed, 1 skipped in 0.30s** (dpkg-deb test skipped on Windows — expected) |
| `pytest tests/integration/ -q` (no regression to integration suite) | **39 passed, 8 skipped in 0.75s** (skips are pre-existing POSIX-only cases + the new dpkg-deb skip) |
| `pytest -q` (full repo — M7 ≤30s gate) | **2035 passed, 91 skipped in 18.35s** — up from 2030 baseline (+5 new tests; 6th is the skip). M7 budget preserved (18.35s ≤ 30s). |
| `ruff check tests/integration/test_deb_ships_known_fleet.py` | All checks passed |
| `ruff format --check tests/integration/test_deb_ships_known_fleet.py` | 1 file already formatted |
| `mypy --strict tests/integration/test_deb_ships_known_fleet.py` | Success: no issues found in 1 source file |
| `grep -c "tests/fixtures/fleet /etc/spark-modem-watchdog/known-fleet" debian/spark-modem-watchdog.install` | 1 |
| `grep -c "^/etc/spark-modem-watchdog/known-fleet$" debian/spark-modem-watchdog.dirs` | 1 |
| `grep -c "known-fleet" debian/spark-modem-watchdog.postinst` | 0 |
| `grep -c "known-fleet" debian/rules` | 0 |
| `git diff --numstat` on the two debian/* files | each shows `+1 -0` (pure one-line addition; existing content untouched) |
| `ls tests/fixtures/fleet/_test/triple.json` | FOUND (Plan 05-03 dependency satisfied) |

## Did the dpkg-deb integration test run or skip on this host?

**SKIPPED.** The test host is Windows 11 (per env.OS Version); `shutil.which("dpkg-deb")` returns `None`, so the `@pytest.mark.skipif` decorator skips `test_deb_contains_known_fleet_path` cleanly with reason "dpkg-deb not on PATH (typical on non-Debian hosts including Windows dev laptops)". The other 5 tests (static debian/* parses + fixture validity + anti-pattern pins) ran unconditionally and all passed.

On a Debian build host running `dpkg-buildpackage -b` (or in CI), the test would discover the built `.deb` under `../*.deb` (where dpkg-buildpackage drops binaries by default) and assert `/etc/spark-modem-watchdog/known-fleet` is in the `dpkg-deb --contents` output. The dh_install rule guarantees this on every build; the test is the regression gate.

## Decisions Made

- **Followed RESEARCH Q10 final recommendation verbatim** — ship `tests/fixtures/fleet` directly as `/etc/spark-modem-watchdog/known-fleet/<box-id>/triple.json` (no sha-rename, no build-time index synthesis). The two alternative options from Q10 (override_dh_auto_install with explicit copy+rename, or a `tools/build_fleet_index.py` build-time tool) were both rejected by the research as more complex than necessary; this plan inherits that decision.

- **No changes to debian/postinst** — RESEARCH Q10 §647-650 is explicit: postinst stays scoped to ModemManager masking + state-dir creation; data shipment goes through dh_install. The test `test_no_known_fleet_references_in_postinst` pins this design as a regression gate.

- **No changes to debian/rules** — RESEARCH Q10 §637 is explicit: declarative `debian/install` is the simplest path; no `override_dh_auto_install` extension is needed for the read-only fleet index. The test `test_no_known_fleet_references_in_rules` pins this design as a regression gate.

- **Integration test sits in `tests/integration/` alongside `test_unit_file_audit.py`** — both tests are cross-platform-safe debian/* parsers; they share the same `_REPO_ROOT = Path(__file__).resolve().parents[2]` pattern. A dedicated `tests/packaging/` subtree would duplicate conftest.py infrastructure for one test file.

- **Two redundant assertions in `test_debian_install_declares_known_fleet`** — separately check that `tests/fixtures/fleet` (source) and `/etc/spark-modem-watchdog/known-fleet` (destination) are both in the install file. If a future refactor renames either side of the dh_install rule, the failure message points at the exact half that changed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Ruff RUF100 + E501 lint errors in the initial test file**

- **Found during:** Task 2 post-implementation lint sweep.
- **Issue:** The integration test file initially shipped with (a) a `# noqa: S603` comment on the `subprocess.run` call — but `S603` is not enabled in this project's ruff config, so RUF100 flagged the noqa as unused; and (b) one assertion message that exceeded the 100-char line limit. Plan text described the file shape at the level of "what tests to write", not character-by-character formatting; these lint failures only surface after writing real code.
- **Fix:** Removed the unused `noqa: S603` directive (the call is fine without it — argv list, no shell, trusted args is project policy anyway); split the long assertion message across two adjacent string literals.
- **Files modified:** `tests/integration/test_deb_ships_known_fleet.py` (pre-commit, before the Task 2 commit was created).
- **Verification:** `ruff check` exits 0; `ruff format --check` exits 0; all 6 tests still pass (5 + 1 skip).
- **Committed in:** `bea9597` (Task 2 commit; lint fixes folded in before the commit was created — no second commit needed since the file was not yet on disk in git at the time the lint fix was applied).

**2. [Rule 3 — Cosmetic] Ruff `format` rewrap of multi-line `assert ... , (...)` triples**

- **Found during:** Task 2 post-implementation `ruff format --check` sweep.
- **Issue:** Three `assert path.is_file(), ("..." )` and `assert isinstance(...) and data[key], ("...")` triples were written with parenthesized continuations across two lines each. Ruff's formatter prefers the single-line form (lines were short enough to fit). Plus one `read_text(encoding="utf-8")` call that ruff wanted on a single line. Purely stylistic; no logic change.
- **Fix:** Ran `ruff format` to auto-collapse the assertions into single-line form. File is now stable under `ruff format --check`.
- **Files modified:** `tests/integration/test_deb_ships_known_fleet.py`.
- **Verification:** `ruff check` exits 0; `ruff format --check` exits 0; all 6 tests still pass.
- **Committed in:** `bea9597` (Task 2 commit; format fix folded in before the commit was created).

---

**Total deviations:** 2 auto-fixed (both Rule 3 lint/format). No scope creep; no architectural decisions; Rule 4 did not fire.

**Impact on plan:** Both deviations are cosmetic Python/lint hygiene. Plan text described the test file at the level of "behavior + 6 test bodies"; the lint passes are project hygiene that any new file must satisfy. Plan-text fidelity preserved on all behavioral assertions.

## Issues Encountered

- **`PreToolUse:Edit` hook noise on Edit-after-Write on the same file:** the hook flagged the post-Write Edit calls on `tests/integration/test_deb_ships_known_fleet.py` even though the file was just created via Write in the same session, and earlier Edits on `debian/spark-modem-watchdog.install` and `debian/spark-modem-watchdog.dirs` even though both files were Read at the start of execution. Same friction Plans 05-02 through 05-05 SUMMARYs documented. Every Edit succeeded.
- **Line-ending warnings (`LF will be replaced by CRLF`)** — Windows git autoCRLF behavior; the staged files are committed with LF as required for cross-platform debian/* parsing. Not a real issue.
- **No active git pre-commit hook on this Windows dev host:** `.git/hooks/pre-commit` absent so ruff/mypy/SP-04 lint did not run automatically. Ran them manually after Task 2.

## TDD Gate Compliance

Plan-level type is `execute` (not `tdd`), and individual tasks are `type="auto"` without explicit `tdd="true"` markers — so plan-level RED→GREEN→REFACTOR gates do not apply. The plan is structured as "write the data shipment first, then write the test that pins it", which is the natural shape for a packaging change where the production artifact (the debian/* files) is itself the source-of-truth and the test is verification.

| Task | Commit | Kind |
| ---- | ------ | ---- |
| 1    | `3407457` | `feat` (debian/* additions) |
| 2    | `bea9597` | `test` (integration test pinning the contract) |

No RED phase commit (would be a failing test against the not-yet-shipped debian/install line). The Task 1 → Task 2 ordering means the test was always green against the committed state, which is the correct shape for an `execute`-type plan.

## Threat Surface Scan

The plan's `<threat_model>` covers four threats (T-05-06-01 .. T-05-06-04). Disposition verification:

- **T-05-06-01 (DoS via empty/corrupted known-fleet at install time)** — **mitigated.** Plan 05-03's `tests/fixtures/fleet/_test/triple.json` is committed and shipped via the new dh_install rule (Test 4 of the integration test pins its existence + valid FleetTriple shape). Plan 05-04's empty-dir error path emits an operator-actionable journalctl message pointing at the `spark-modem ctl capture-fleet-fixture` capture command.
- **T-05-06-02 (Privilege escalation — daemon writes to /etc/spark-modem-watchdog/known-fleet/)** — **mitigated.** Plan 05-04's acceptance criterion already enforced zero write paths in `src/spark_modem/daemon/preflight_triple.py`; this plan doesn't add new write paths. Directory ownership is `root:root 0755` (dh_install default); files are `root:root 0644`. Daemon runs as root but never invokes write helpers against the known-fleet path.
- **T-05-06-03 (Tampering — operator hand-edits triple.json on the box)** — **accepted.** Threat actor has sudo; bypass via `--skip-preflight` is equally easy. Audit trail via git-blame on `tests/fixtures/fleet/<box-id>/`.
- **T-05-06-04 (Repudiation — dpkg upgrade silently replaces known-fleet entries with an older set)** — **accepted.** dpkg upgrade is atomic; if the new .deb's known-fleet is smaller than the old set, that's a deliberate scope change. Provenance tracked via .deb changelog + git history.

No new threat surface beyond plan dispositions. No network endpoints, no auth paths, no new trust boundaries — this is declarative file-copy packaging metadata.

## Known Stubs

None. The two debian/* additions are real shipping rules; the integration test exercises real paths (no mock filesystems). The example fixture `tests/fixtures/fleet/_test/triple.json` is a complete FleetTriple committed in Plan 05-03 — not a placeholder; it ships unaltered.

## Next Phase Readiness

- **X-* deliverable family complete end-to-end** — X-01 (capture verb in Plan 05-03), X-02 (PII redaction inside the verb), X-03 (daemon gate in Plan 05-04 + packaging shipment in this plan) all green.
- **X-04 batched-prereq PR (deferred to pre-Phase-6 physical access window per CONTEXT.md §X-04)** — when the on-site engineer captures per-box fixtures via `spark-modem ctl capture-fleet-fixture` and commits them to `tests/fixtures/fleet/<box-id>/`, the next `.deb` release will ship them automatically via the dh_install rule landed in this plan. No further debian/install or debian/rules edit needed.
- **Plan 05-07 (operator-facing soak runbook)** can reference the now-shipped path `/etc/spark-modem-watchdog/known-fleet/` directly — the chain "daemon refuses to start on unknown triple → operator runs `spark-modem ctl capture-fleet-fixture` → commits triple.json → next apt install ships it" is closed.
- **Plan 05-08 (SIGNOFF.md template + manual replay-harness exit gate)** is unaffected by this plan — the .deb shipment is structurally orthogonal to the SIGNOFF artifact.
- **No blockers.** Phase 5 remaining plans (05-07, 05-08) are pure docs + ops runbook + SIGNOFF template — no further code or packaging work expected in Phase 5.

## Self-Check

Verifying SUMMARY claims against actual repo state.

**Files created — present:**

- `S:/spark/modem-watchdog/tests/integration/test_deb_ships_known_fleet.py` — FOUND

**Files modified — both present with the +1 line each:**

- `S:/spark/modem-watchdog/debian/spark-modem-watchdog.install` — FOUND; `grep -c "tests/fixtures/fleet /etc/spark-modem-watchdog/known-fleet" = 1`
- `S:/spark/modem-watchdog/debian/spark-modem-watchdog.dirs` — FOUND; `grep -c "^/etc/spark-modem-watchdog/known-fleet$" = 1`

**Files NOT modified (must stay untouched):**

- `S:/spark/modem-watchdog/debian/spark-modem-watchdog.postinst` — `grep -c known-fleet = 0`; `git diff HEAD~2 HEAD -- debian/spark-modem-watchdog.postinst` returns empty
- `S:/spark/modem-watchdog/debian/rules` — `grep -c known-fleet = 0`; `git diff HEAD~2 HEAD -- debian/rules` returns empty

**Commits cited — all present in git log:**

- `3407457` — FOUND (`feat(05-06): ship /etc/spark-modem-watchdog/known-fleet/ via debian/install`)
- `bea9597` — FOUND (`test(05-06): add .deb shipment integration test for known-fleet directory`)

## Self-Check: PASSED

---
*Phase: 05-bench-field-shadow*
*Completed: 2026-05-11*
