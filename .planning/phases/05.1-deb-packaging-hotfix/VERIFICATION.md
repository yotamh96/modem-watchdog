---
phase: 05.1-deb-packaging-hotfix
verified: 2026-05-12T00:00:00Z
status: human_needed
score: 3/4 must-haves verified (automated gates all PASS; V-03 bench Jetson walk not yet performed)
overrides_applied: 0
human_verification:
  - test: "Fill EXIT-CHECKLIST.md on bench Jetson and commit the completed file"
    expected: >
      All 9 V-03 gate rows marked PASS: dpkg -i exits 0; systemctl is-active
      returns "active"; journalctl shows Started... with no ERROR/CRITICAL; PID
      lock and metrics.sock present; all 4 modems reach Healthy within 60s.
      Free-text section captures the L-04 verdict (silent-ignore vs hard-fail vs
      warning-with-degraded on systemd 245 LoadCredential=).
    why_human: >
      Requires a physical bench Jetson (JetPack 5.1.5 / Ubuntu 20.04 / systemd
      245 / aarch64). The V-03 checklist is the ROADMAP success criterion and the
      D-03 EXIT bar for this phase. The code gate (automated CI) is satisfied; the
      deploy gate is not.
---

# Phase 05.1: deb-packaging-hotfix — Verification Report

**Phase Goal (in my own words):** Fix three concrete bugs that prevented the
`.deb` from producing a running daemon on the bench Jetson, and land a
regression gate so the same class of packaging bug cannot recur silently.
Bug 1 (`spark_modem` absent from the bundled venv's `sys.path`), Bug 2 (no
`spark-modem-watchdog` binary for ExecStart — systemd `203/EXEC`), and Bug 3
(no code-side fallback for `LoadCredential=` on Ubuntu 20.04 / systemd 245).

**Verified:** 2026-05-12
**Status:** human_needed — all automated gates pass; V-03 bench Jetson
walk (the ROADMAP success criterion) has not been performed; EXIT-CHECKLIST.md
is still a blank template.
**Re-verification:** No — initial verification.

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | I-01: `spark_modem` package ships into the bundled venv's `site-packages` (not a parallel `lib/` tree off `sys.path`) | VERIFIED | `debian/rules` lines 74-85: Step 3.5 `uv pip install --no-deps --no-build-isolation .` after `requirements.lock`, before the uninstall sweep; `debian/spark-modem-watchdog.install` active-install lines confirmed (old `src/spark_modem /opt/.../lib/` line is now a comment only); `debian/spark-modem-watchdog.dirs` has no `/opt/spark-modem-watchdog/lib` entry |
| 2 | I-02/I-04: `spark-modem-watchdog` console-script entry point exists and is the correct async→sync wrapper | VERIFIED | `pyproject.toml` line 23: `spark-modem-watchdog = "spark_modem.daemon.main:_sync_main"`; `src/spark_modem/daemon/main.py` lines 313-319: `_sync_main()` inlined, returns `asyncio.run(main(argv))`; `if __name__ == "__main__"` updated to call `_sync_main()`; `mypy --strict` clean; V-04 (c) test passes on dev host |
| 3 | L-02: daemon reads the HMAC secret from `CREDENTIALS_DIRECTORY` when set (systemd 247+) and falls back to `/etc/spark-modem-watchdog/hmac-secret` on systemd 245 | VERIFIED | `src/spark_modem/config/settings.py` lines 246-261: `resolve_hmac_secret_path()` reads `os.environ.get("CREDENTIALS_DIRECTORY")` at call time; unit tests 3/3 pass |
| 4 | V-03: EXIT-CHECKLIST.md is committed with every gate row marked PASS by the on-site engineer | HUMAN NEEDED | `EXIT-CHECKLIST.md` is an unfilled template — all 9 Status cells are `☐ PASS / ☐ FAIL`, all Observed cells are `_filled_`, L-04 verdict field is `_engineer fills here_`. **The ROADMAP success criterion is explicitly "the committed EXIT-CHECKLIST.md has every V-03 gate row marked PASS."** This is not yet true. |

**Score:** 3/4 truths verified (automated code gates); 1 requires human verification (V-03 bench Jetson walk).

### Deferred Items

None. The V-03 bench Jetson walk is not deferred — it is a Phase 05.1 requirement. It simply has not been performed yet. The code changes that enable it are complete.

---

## Bug-Class Retirement Trace

### Bug I-01: `spark_modem` not on `sys.path`

**Root cause:** Phase 1 used `debian/spark-modem-watchdog.install` to copy `src/spark_modem` to `/opt/spark-modem-watchdog/lib/`, a path never added to the bundled venv's `sys.path`.

**Fix verified at:**
- `debian/rules` lines 74-85: `uv pip install . --no-deps --no-build-isolation` inserted between requirements.lock install (Step 3) and the pip uninstall sweep — setuptools survives until this step (I-05 order constraint confirmed by `grep -n "pip uninstall" debian/rules` → line 89, after line 85)
- `debian/spark-modem-watchdog.install`: old `src/spark_modem /opt/.../lib/` install directive removed; replaced with an audit-trail comment block (lines 6-9)
- `debian/spark-modem-watchdog.dirs`: `/opt/spark-modem-watchdog/lib` line removed; file is now 7 lines (no phantom empty dir in the .deb)

**Regression gate:** `scripts/postinst_smoke_test.sh` now imports `spark_modem.daemon.main` and `spark_modem.cli.main` (V-01); V-04 (c) test in `test_unit_file_audit.py` asserts `[project.scripts]` entries are importable from the dev host; V-02 CI reruns the smoke in a clean Ubuntu 20.04 container.

### Bug I-02/I-04: No daemon entry point (systemd `203/EXEC`)

**Root cause:** `pyproject.toml [project.scripts]` contained only `spark-modem`; the unit file `ExecStart` referenced `/opt/spark-modem-watchdog/bin/spark-modem-watchdog` (a path that nothing created).

**Fix verified at:**
- `pyproject.toml` line 23: `spark-modem-watchdog = "spark_modem.daemon.main:_sync_main"` added
- `src/spark_modem/daemon/main.py` lines 313-319: `_sync_main()` sync wrapper inlined, `if __name__ == "__main__"` updated to call it
- `debian/spark-modem-watchdog.service` line 22: `ExecStart=/opt/spark-modem-watchdog/python/bin/spark-modem-watchdog` (points to the console-script materialized by `uv pip install .`)
- Old `/opt/spark-modem-watchdog/bin/` path and "Phase 4 follow-up" admission comment are gone (confirmed: `grep -n "Phase 4 follow-up\|/opt/spark-modem-watchdog/bin/" service` returns no matches in the old pattern context)

**Regression gate:** V-04 (a) test asserts every ExecStart/ExecStartPre binary is anchored in `[project.scripts]` or `debian/.install`; V-02 CI asserts `test -x /opt/.../python/bin/spark-modem-watchdog`.

### Bug L-02: `LoadCredential=` silent on systemd 245

**Root cause:** Ubuntu 20.04 ships systemd 245; `LoadCredential=` was introduced in systemd 247. Behavior on parse (silent-ignore vs hard-fail) was unknown, and there was no code-side fallback.

**Fix verified at:**
- `src/spark_modem/config/settings.py` lines 246-261: `resolve_hmac_secret_path()` checks `os.environ.get("CREDENTIALS_DIRECTORY")`; if unset (systemd 245), reads directly from `/etc/spark-modem-watchdog/hmac-secret`
- `src/spark_modem/cli/ctl/config_check.py`: full `ctl config-check` verb validates the resolved path (existence, not-placeholder, mode 0600, owner root:root)
- `debian/spark-modem-watchdog.service` line 99: `LoadCredential=` directive preserved (L-01 — forward-compat for systemd 247+)
- `debian/spark-modem-watchdog.postinst` lines 46-52: writes placeholder sentinel at `0600 root:root`, with `[[ ! -f ]]` idempotency guard

**L-04 verdict:** NOT YET CAPTURED. The `systemd-analyze verify` step in V-02 CI will capture it when the self-hosted aarch64 runner runs. The free-text section of EXIT-CHECKLIST.md requires the operator to document the journalctl observation (silent-ignore vs warning vs hard-fail). Until a CI run on the real aarch64 runner completes, the L-04 outcome is still open.

**Regression gate:** V-04 (b) test asserts `LoadCredential=` source path == `/etc/spark-modem-watchdog/hmac-secret` (the L-02 fallback path); V-02 CI runs `systemd-analyze verify`.

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pyproject.toml` | `spark-modem-watchdog` in `[project.scripts]` | VERIFIED | Line 23: `spark-modem-watchdog = "spark_modem.daemon.main:_sync_main"` |
| `src/spark_modem/daemon/main.py` | `_sync_main()` sync wrapper | VERIFIED | Lines 313-319 |
| `src/spark_modem/config/settings.py` | `resolve_hmac_secret_path()` with L-02 fallback | VERIFIED | Lines 246-261 |
| `src/spark_modem/cli/ctl/config_check.py` | New file: `ctl config-check` verb with 4 checks | VERIFIED | Full file present; 107 lines; all checks implemented |
| `src/spark_modem/cli/main.py` | `config_check` imported and registered | VERIFIED | Line 26: import; lines 169-174: subparser registration |
| `debian/rules` | Step 3.5 `uv pip install .` in correct order | VERIFIED | Lines 74-85; after requirements.lock, before pip uninstall |
| `debian/spark-modem-watchdog.install` | Old `src/spark_modem .../lib/` directive removed | VERIFIED | Active install lines confirmed; old line is comment only |
| `debian/spark-modem-watchdog.dirs` | `/opt/spark-modem-watchdog/lib` entry removed | VERIFIED | File is 7 lines; lib entry absent |
| `debian/spark-modem-watchdog.service` | ExecStart/ExecStartPre point to `python/bin/` | VERIFIED | Lines 18, 22; `bin/` layer gone; `Phase 4 follow-up` comment gone |
| `debian/spark-modem-watchdog.postinst` | L-03 placeholder block with idempotency guard | VERIFIED | Lines 46-52; `[[ ! -f ]]` guard; `chmod 0600`; `chown root:root` |
| `scripts/postinst_smoke_test.sh` | Two new import entries (V-01) | VERIFIED | Lines 32-35: `spark_modem.daemon.main` and `spark_modem.cli.main` |
| `tests/integration/test_unit_file_audit.py` | 3 new V-04 tests + 2 new fixtures | VERIFIED | Lines 218-303; 23 total tests, all pass |
| `.github/workflows/build-deb.yml` | V-02 strict-superset install step | VERIFIED | Lines 50-94; (a) smoke, (b) executables, (c) HMAC file, (d) systemd-analyze verify |
| `.planning/phases/05.1-deb-packaging-hotfix/EXIT-CHECKLIST.md` | 9-row V-03 operator checklist template | VERIFIED (template only) | Template exists with correct shape; not yet filled by operator |
| `debian/changelog` | `2.0.1-1` entry documenting all 3 bug fixes | VERIFIED | Lines 1-28 of changelog |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `pyproject.toml [project.scripts]` | `spark_modem.daemon.main:_sync_main` | module import | WIRED | V-04 (c) test imports the module and asserts the attribute exists; passes on dev host |
| `debian/rules Step 3.5` | `pyproject.toml [project.scripts]` | `uv pip install .` reads pyproject.toml | WIRED | Step 3.5 uses `--no-build-isolation`; setuptools survives to build backend; console-scripts materialize |
| `debian/spark-modem-watchdog.service ExecStart` | `/opt/.../python/bin/spark-modem-watchdog` | `uv pip install .` materializes console-script | WIRED (deferred to install-time) | Service file points to correct path; path materializes during `override_dh_auto_install`; V-02 CI `test -x` assertion validates at install time |
| `debian/spark-modem-watchdog.service ExecStartPre` | `ctl config-check` verb | `spark-modem` CLI dispatch | WIRED | `src/spark_modem/cli/main.py` line 170-174 registers `config-check`; `async def run()` exists in `config_check.py` |
| `ctl config-check` → `settings.resolve_hmac_secret_path()` | HMAC file path | call at runtime | WIRED | `config_check.py` line 47: `secret_path = settings.resolve_hmac_secret_path()` |
| `debian/spark-modem-watchdog.postinst` | `/etc/spark-modem-watchdog/hmac-secret` | `printf` + `chmod` + `chown` | WIRED | Lines 46-52; L-03 block present; sentinel byte-matches `config_check._HMAC_PLACEHOLDER_SENTINEL` |
| V-04 tests | `debian/spark-modem-watchdog.service` + `pyproject.toml` | `tomllib` + file parse | WIRED | All 3 new V-04 tests pass (23/23 in audit file); runs cross-platform without Linux |

---

## Data-Flow Trace (Level 4)

Not applicable to this phase. The phase introduces no new rendering components or data pipelines — it is packaging/entry-point/config plumbing. The one new datum (HMAC secret path) is a scalar `Path` value; it is validated (not rendered).

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| V-04 unit-file audit (all 23 tests including 3 new V-04 assertions) | `.venv/Scripts/pytest tests/integration/test_unit_file_audit.py -v` | 23 passed, 0 failed | PASS |
| L-02 HMAC path unit tests | `.venv/Scripts/pytest tests/unit/config/test_settings_hmac_path.py -v` | 3 passed | PASS |
| L-05 config-check unit tests | `.venv/Scripts/pytest tests/unit/cli/test_ctl_config_check.py -v` | 3 passed, 6 skipped (Linux stat semantics — expected on Windows) | PASS |
| `mypy --strict src` | `.venv/Scripts/mypy --strict src` | `Success: no issues found in 132 source files` | PASS |
| `ruff check` (Phase 05.1 Python files) | `.venv/Scripts/ruff check src/spark_modem/daemon/main.py settings.py cli/main.py config_check.py test_unit_file_audit.py test_settings_hmac_path.py test_ctl_config_check.py` | All checks passed | PASS |
| Full non-HIL test suite | `.venv/Scripts/pytest tests/ --ignore=tests/hil -q` | 2056 passed, 97 skipped (platform-Linux skips expected on Windows) | PASS |
| V-03 bench Jetson walk | Physical install on Jetson, systemctl start, etc. | Not run | SKIP — requires bench Jetson |
| L-04 verdict (systemd 245 LoadCredential= behavior) | V-02 CI job on self-hosted aarch64 runner | Not yet observed | SKIP — requires CI run on aarch64 runner |

---

## Requirements Coverage

This phase has no formal v1 REQ-IDs (explicitly noted in ROADMAP.md as an inserted hotfix). Indirect ties verified:

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| NFR-30 (root-only secrets) | HMAC secret file must be 0600 root:root | SATISFIED | postinst `chmod 0600`; `config-check` mode + owner validation |
| ADR-0011 (HMAC discipline) | Never baked in, never logged, root-only | SATISFIED | L-03 sentinel explicitly rejected by `config-check`; error messages print path, never bytes |
| FR-60 / B-03 (smoke test) | Import smoke runs at install + start | SATISFIED | V-01 adds daemon package imports to existing smoke |
| NFR-13 (≤60s steady-state) | Healthy within 60s of start | DEFERRED TO V-03 | V-03 row 9 verifies this on bench Jetson |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tests/unit/tools/test_audit_soak_zao.py` | 127 | `E501 Line too long (103 > 100)` | Info | Pre-existing ruff violation from Phase 5 (Plan 05-05); not introduced by Phase 05.1. Not a blocker. |

No anti-patterns found in any Phase 05.1 modified files. Specifically:
- No `TODO/FIXME/PLACEHOLDER` markers in production code paths
- No `return null` / empty-array stubs in the new `config_check.py`
- No hardcoded empty data flowing to rendering
- The word "placeholder" appears in `config_check.py` only in an error message describing the sentinel value that must NOT be present — correct intent, not a stub

---

## Human Verification Required

### 1. V-03 Bench Jetson Walk

**Test:** On the bench Jetson (JetPack 5.1.5 / Ubuntu 20.04 / systemd 245 / aarch64):
1. Build `.deb` from the hotfix branch; confirm CI artifact green
2. `scp` to bench Jetson; `sudo dpkg -i spark-modem-watchdog_2.0.1-1_arm64.deb` exits 0; postinst smoke reports "OK: all 12 runtime libs + daemon entry points import"
3. Provision HMAC secret: `head -c 32 /dev/urandom | base64 | sudo install -m 0600 -o root -g root /dev/stdin /etc/spark-modem-watchdog/hmac-secret`; confirm `stat -c '%a %u:%g'` returns `600 0:0`
4. `sudo systemctl start spark-modem-watchdog.service` exits 0; `ExecStartPre` smoke and `config-check` both pass; `ExecStart` fires
5. `systemctl is-active spark-modem-watchdog.service` returns `active`
6. `journalctl -u spark-modem-watchdog.service --since='5 min ago' -p err` returns empty; `Started ...` line visible at info level; CAPTURE any journalctl warning about `LoadCredential=` (the L-04 verdict)
7. `/run/spark-modem-watchdog/lock` present, owned by root
8. `sudo curl --unix-socket /run/spark-modem-watchdog/metrics.sock http://x/metrics | head -20` returns valid Prometheus text with `modem_state_value`, `cycle_duration_seconds`, `actions_total`
9. After ≤60s: `sudo cat /var/lib/spark-modem-watchdog/status.json | jq '.modems[] | select(.state != "healthy") | .modem'` returns empty (all modems Healthy)

Fill all 9 rows of EXIT-CHECKLIST.md (Status, Observed, Notes), write the free-text rationale with the L-04 verdict, sign the approval footer, and commit the file.

**Expected:** Every row PASS; committed EXIT-CHECKLIST.md with engineer signature.

**Why human:** Requires physical bench Jetson hardware, `dpkg`, `systemctl`, live modems, and the L-04 systemd-245 behavior that only manifests on a real Ubuntu 20.04 aarch64 system.

---

## Gaps Summary

There are no code gaps. Every bug fix is implemented, wired, and tested in code. The single outstanding item is the V-03 bench Jetson walk — the ROADMAP success criterion for this phase — which is an operator-gate by design (D-03). The EXIT-CHECKLIST.md is a blank template waiting for the on-site engineer.

**Note on ROADMAP plan checkboxes:** Plans 02-06 remain unchecked (`[ ]`) in ROADMAP.md despite their SUMMARY.md files confirming completion. This is a cosmetic documentation inconsistency only — all implementation is present and passing. The checkboxes would normally be updated when the phase is formally closed (operator commits the filled EXIT-CHECKLIST.md).

**Note on pyproject.toml version:** The `version` field in `pyproject.toml` is still `2.0.0` while `debian/changelog` correctly reflects `2.0.1-1`. This is not a defect — the pyproject.toml version and the Debian package version are managed separately in this project's workflow, and the changelog is the authoritative version for the `.deb` artifact.

---

## Verdict: PARTIAL (code-complete; operator EXIT gate pending)

All automated verification gates pass:
- V-01: postinst smoke extended (PASS)
- V-04: 3 new unit-file audit assertions (23/23 PASS)
- V-02: strict-superset CI install step shipped (L-04 verdict pending first aarch64 CI run)
- `mypy --strict src`: 132 files, 0 issues
- `ruff check` (Phase 05.1 files): all checks passed
- Full test suite: 2056 passed, 97 skipped (Linux platform skips expected on Windows)

The ROADMAP success criterion is the bench Jetson EXIT (V-03). That gate is not yet passed. Phase 05.1 should be recorded as **code-complete, operator-gate pending**.

---

_Verified: 2026-05-12_
_Verifier: Claude (gsd-verifier)_
