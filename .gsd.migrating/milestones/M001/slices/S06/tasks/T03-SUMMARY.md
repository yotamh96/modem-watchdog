---
id: T03
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
duration: 1m 24s
verification_result: passed
completed_at: 2026-05-12
blocker_discovered: false
---
# T03: 05.1-deb-packaging-hotfix 03

**# Phase 05.1 Plan 03: systemd Unit File ExecStart* Repoint Summary**

## What Happened

# Phase 05.1 Plan 03: systemd Unit File ExecStart* Repoint Summary

**systemd service unit ExecStart/ExecStartPre repointed from never-existed `/opt/.../bin/` wrappers to Plan 05.1-01's console-scripts at `/opt/.../python/bin/`; admission comment replaced with I-01/I-02/I-04 audit trail; all 20 unit-file audit tests pass.**

---

## Performance

- **Duration:** 1m 24s
- **Started:** 2026-05-12T06:42:28Z
- **Completed:** 2026-05-12T06:43:52Z
- **Tasks:** 1
- **Files modified:** 1

---

## Accomplishments

- Eliminated the root cause of systemd 203/EXEC: ExecStart now points at the console-script that Plan 05.1-01 materializes at `/opt/spark-modem-watchdog/python/bin/spark-modem-watchdog`.
- ExecStartPre config-check now calls Plan 05.1-02's `ctl config-check` verb via `/opt/spark-modem-watchdog/python/bin/spark-modem ctl config-check`.
- `LoadCredential=spark-modem-watchdog.hmac-secret:/etc/spark-modem-watchdog/hmac-secret` preserved byte-for-byte (L-01 honored).
- "Phase 4 follow-up: verify wrapper exists" admission comment block retired; replaced with clean I-01/I-02/I-04 decision tag references.

---

## Task Commits

1. **Task 1: Repoint ExecStart* paths to /opt/.../python/bin/ + update comments** - `6a0cb57` (fix)

**Plan metadata:** (docs commit follows in final_commit step)

---

## Files Created/Modified

- `debian/spark-modem-watchdog.service` - ExecStartPre config-check + ExecStart daemon paths changed from `/opt/.../bin/` to `/opt/.../python/bin/`; U-05 comment extended to U-05/L-05; admission comment dropped; 8 lines inserted, 9 deleted (net -1 line)

---

## Exact Before/After Diff (lines 11-23)

### Before

```ini
# FR-60 + B-03 belt-and-suspenders B: smoke-test on every start.
ExecStartPre=/opt/spark-modem-watchdog/libexec/postinst_smoke_test.sh

# U-05: pre-flight Settings validate before main process. Catches bad
# config rollouts BEFORE the main daemon process boots, so a bad
# config doesn't trip StartLimitBurst (PITFALLS §4.2).
ExecStartPre=/opt/spark-modem-watchdog/bin/spark-modem ctl config-check

# Phase 3 wires the real entry point. The wrapper script lives in
# /opt/spark-modem-watchdog/bin/ and is provided by the .deb postinst
# (Phase 4 follow-up: verify wrapper exists; current .deb scaffold may
# need an additional ExecStart shim).
ExecStart=/opt/spark-modem-watchdog/bin/spark-modem-watchdog
```

### After (lines 11-22)

```ini
# FR-60 + B-03 belt-and-suspenders B: smoke-test on every start.
ExecStartPre=/opt/spark-modem-watchdog/libexec/postinst_smoke_test.sh

# U-05 / L-05: pre-flight Settings + HMAC secret validate before main process.
# Catches bad config rollouts (and missing/placeholder HMAC secrets) BEFORE
# the main daemon process boots, so a bad config doesn't trip StartLimitBurst
# (PITFALLS §4.2).
ExecStartPre=/opt/spark-modem-watchdog/python/bin/spark-modem ctl config-check

# Daemon entry point — console-script auto-materialized by [project.scripts]
# in pyproject.toml during override_dh_auto_install (Phase 05.1 I-01/I-02/I-04).
ExecStart=/opt/spark-modem-watchdog/python/bin/spark-modem-watchdog
```

Net change: 13 lines → 12 lines (-1). Two `bin/` paths replaced with `python/bin/` paths; 3-line "Phase 4 follow-up" admission comment block (5 lines) condensed to 2-line audit-trail comment; U-05 comment extended to U-05/L-05 with HMAC mention.

---

## Decisions Made

1. **I-03 (executed):** `/opt/spark-modem-watchdog/bin/` layer dropped entirely from the unit file. All python-script invocations now reference `/opt/spark-modem-watchdog/python/bin/` directly — one fewer abstraction layer, cleanest pairing with the pip-install path.
2. **L-01 (honored):** `LoadCredential=` line at line 99 preserved byte-for-byte. This is the forward-compatible path for Ubuntu 22.04+ / systemd 247+ boxes; code-side fallback (L-02, Plan 05.1-02) handles systemd 245.
3. Smoke-test ExecStartPre (`/opt/spark-modem-watchdog/libexec/postinst_smoke_test.sh`) untouched — it is a shell script shipped via `debian/spark-modem-watchdog.install`, not a console-script.

---

## Verification Results

| Check | Expected | Result |
|-------|----------|--------|
| `grep -cF "/opt/spark-modem-watchdog/bin/" service` | 0 | PASS |
| `grep -cF "/opt/.../python/bin/spark-modem-watchdog" service` | 1 | PASS |
| `grep -cF "/opt/.../python/bin/spark-modem ctl config-check" service` | 1 | PASS |
| `grep -cF "/opt/.../libexec/postinst_smoke_test.sh" service` | 1 | PASS |
| `grep -cF "LoadCredential=...hmac-secret" service` | 1 | PASS |
| `grep -cF "Phase 4 follow-up" service` | 0 | PASS |
| `grep -cF "Phase 05.1 I-01/I-02/I-04" service` | 1 | PASS |
| `pytest tests/integration/test_unit_file_audit.py -v` | 20 passed | PASS (20 passed, 0 failed) |

All acceptance criteria satisfied.

---

## Deviations from Plan

None — plan executed exactly as written.

---

## Issues Encountered

None.

---

## Known Stubs

None. The word "placeholder" appears in a comment about catching placeholder HMAC secrets (correct intent), not as a data stub.

---

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes introduced. This edit removes a broken path and replaces it with the correct path — the trust boundary (`systemd unit → daemon binary`) is unchanged in nature, only corrected in destination. All four threat register entries (T-05.1-10 through T-05.1-13) are mitigated:

- **T-05.1-10** (203/EXEC DoS): ExecStart now resolves to the console-script Plan 05.1-01 materializes.
- **T-05.1-11** (path drift elevation): `/opt/.../bin/` layer eliminated; V-04 audit (Plan 05.1-05) will enforce anchoring.
- **T-05.1-12** (LoadCredential tampering): acceptance criteria grep-assert confirmed; existing `test_load_credential_for_hmac_secret` passes.
- **T-05.1-13** (sandbox directive tampering): all 20 existing audit tests pass, confirming sandbox directives unchanged.

---

## Next Phase Readiness

Wave 2 of Phase 05.1 is complete. Plan 05.1-04 (EXIT-CHECKLIST.md) and Plan 05.1-05 (V-02 CI + V-04 unit-file audit extension) are unblocked. The three-bug fix set (Plans 01-03) is now fully committed:

1. **Bug #1 fixed (Plan 01):** `spark_modem` package ships into bundled venv via `uv pip install .`
2. **Bug #2 fixed (Plans 01 + 03):** `spark-modem-watchdog` console-script declared AND unit file points at it
3. **Bug #3 mitigated (Plans 02 + 03):** HMAC-secret fallback (L-02) + config-check validator (L-05) + unit file ExecStartPre wired correctly

---

*Phase: 05.1-deb-packaging-hotfix*
*Completed: 2026-05-12*

## Self-Check: PASSED

- S:\spark\modem-watchdog\debian\spark-modem-watchdog.service: exists, contains `python/bin/spark-modem-watchdog` at line 22
- S:\spark\modem-watchdog\.planning\phases\05.1-deb-packaging-hotfix\05.1-03-SUMMARY.md: exists
- Commit 6a0cb57 (Task 1): confirmed in git log
- Commit d996199 (docs metadata): confirmed in git log
