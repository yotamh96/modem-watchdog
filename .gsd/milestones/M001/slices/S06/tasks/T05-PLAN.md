# T05: 05.1-deb-packaging-hotfix 05

**Slice:** S06 — **Milestone:** M001

## Description

Land the three regression gates that retire the bug class permanently
(D-01: "minimum + regression gate"). After this plan:

- The B-03 postinst smoke imports the daemon + CLI packages (not just the
  10 runtime libs) — bug #1 (spark_modem not on sys.path) cannot recur
  silently. Catches at install time (postinst) AND on every start
  (ExecStartPre) per B-03 belt-and-suspenders.
- The cross-platform unit-file audit gains 3 new assertions (V-04) that
  detect drift between unit ↔ pyproject ↔ install layout. Fails on every
  Windows dev-host pytest invocation if drift surfaces.
- The arm64 GitHub Actions workflow's "Smoke-install in clean container"
  step is REPLACED (not duplicated) with a strict superset that also
  verifies: console scripts present/executable, HMAC placeholder file
  present with right perms, and (the L-04 forcing function)
  `systemd-analyze verify` exits 0 against the unit file in the same
  systemd 245 container the bench Jetson runs.

Implements locked decisions **V-01**, **V-02**, **V-04** (and verifies
**L-04**) from `.planning/phases/05.1-deb-packaging-hotfix/05.1-CONTEXT.md`.

Purpose: regression gate = same class of bug cannot recur silently. The
V-02 CI install test runs on every push to main + every PR; V-01 + V-04
run on every Windows dev-host pytest invocation. Belt + suspenders +
parachute.

Output:
- `scripts/postinst_smoke_test.sh` with 2 import lines added.
- `tests/integration/test_unit_file_audit.py` with 3 new tests + 2 new
  fixtures + 2 new path constants.
- `.github/workflows/build-deb.yml` with the "Smoke-install" step body
  replaced (existing step name optionally updated to reference V-02).

## Must-Haves

- [ ] "scripts/postinst_smoke_test.sh imports spark_modem.daemon.main AND spark_modem.cli.main in addition to the 10 runtime libs"
- [ ] "tests/integration/test_unit_file_audit.py has 3 new V-04 assertions: exec paths anchored, LoadCredential path matches fallback, project-scripts entry points importable"
- [ ] ".github/workflows/build-deb.yml 'Smoke-install in clean container' step is REPLACED with a strict superset that asserts: postinst smoke green, both console scripts present + executable, /etc/spark-modem-watchdog/hmac-secret exists with 0600 mode + root:root + placeholder content, systemd-analyze verify against the unit file exits 0"

## Files

- `scripts/postinst_smoke_test.sh`
- `tests/integration/test_unit_file_audit.py`
- `.github/workflows/build-deb.yml`
