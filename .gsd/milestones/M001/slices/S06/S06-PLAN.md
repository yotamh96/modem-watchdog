# S06: Deb Packaging Hotfix

**Goal:** Land the install-pipeline + entry-point fixes for the Phase 05.
**Demo:** Land the install-pipeline + entry-point fixes for the Phase 05.

## Must-Haves


## Tasks

- [x] **T01: Plan 01**
  - Land the install-pipeline + entry-point fixes for the Phase 05.1 hotfix. After
this plan, `dpkg-deb -c <built deb>` shows `spark_modem/` installed into the
bundled venv's `python/lib/python3.12/site-packages/` (not under
`/opt/spark-modem-watchdog/lib/`), and the bundled venv's `python/bin/`
contains both `spark-modem` and `spark-modem-watchdog` console-script
shims that import cleanly.

Implements locked decisions **I-01**, **I-02**, **I-04**, **I-05** (and honors **D-02**: no `requirements.lock` churn — the 10 runtime libs stay pinned exactly where Phase 1 placed them) from
`.planning/phases/05.1-deb-packaging-hotfix/05.1-CONTEXT.md`.

Purpose: bug #1 (`spark_modem` not on `sys.path` of the bundled venv) and
bug #2 (`spark-modem-watchdog` daemon entry point missing → systemd 203/EXEC)
are eliminated by **shipping `spark_modem` through `uv pip install .` into
the bundled venv's site-packages** and **declaring the daemon entry point in
`[project.scripts]`** so the console-script auto-materializes at
`/opt/spark-modem-watchdog/python/bin/spark-modem-watchdog`.

Output:
- `pyproject.toml` with the new console-script entry.
- `src/spark_modem/daemon/main.py` with `_sync_main()` inlined between
  `async def main` and `if __name__ == "__main__"`.
- `debian/rules` with a new `Step 3.5` block running `uv pip install .` AFTER
  step 3 (runtime libs) and BEFORE the pip uninstall sweep (setuptools must
  still be present — load-bearing per I-05).
- `debian/spark-modem-watchdog.install` with the offending source-tree line
  removed and an audit-trail comment added.
- `debian/spark-modem-watchdog.dirs` with `/opt/spark-modem-watchdog/lib`
  removed (otherwise dh_installdirs creates a phantom empty dir).
- [x] **T02: Plan 02**
  - Land the HMAC-secret discipline + the `ctl config-check` verb body for the
Phase 05.1 hotfix. After this plan, the daemon and CLI both know how to
resolve the HMAC secret path (with the systemd 245 fallback), the
`spark-modem ctl config-check` verb exists and validates Settings + HMAC
secret pre-flight, and the postinst writes a placeholder file that
config-check explicitly rejects so a fresh install cannot accidentally boot
with a default secret.

Implements locked decisions **L-02**, **L-03**, **L-05** (and honors **D-04**: this plan contains the entire "tiny daemon-side hook" surface — `settings.py` resolver + the new `cli/ctl/config_check.py` verb body. All other plans in Phase 05.1 are glue under `debian/`, `scripts/`, `.github/`, or `.planning/`) from
`.planning/phases/05.1-deb-packaging-hotfix/05.1-CONTEXT.md`. L-01 stays in
the unit file (Plan 03's responsibility); L-04 verification is performed by
the CI install test (Plan 05).

Purpose:
- Bug #3 (systemd-245 LoadCredential incompatibility) is closed by the
  code-side fallback in `settings.py`: a single HMAC file on disk at
  `/etc/spark-modem-watchdog/hmac-secret` serves BOTH systemd 247+ (which
  populates `CREDENTIALS_DIRECTORY`) AND systemd 245 (which doesn't — the
  daemon reads directly from the fallback path).
- The pre-flight verb (`ctl config-check`) gives ExecStartPre something
  meaningful to call: it surfaces "operator forgot to provision the real
  secret" / "wrong mode" / "wrong owner" BEFORE the main daemon ever boots,
  so a bad install doesn't trip StartLimitBurst (PITFALLS §4.2).
- The postinst-managed placeholder makes the "operator forgot" state visible:
  the file always exists, but `ctl config-check` refuses to boot with the
  literal sentinel.

Output:
- `src/spark_modem/config/settings.py` with a new `resolve_hmac_secret_path()`
  method.
- `src/spark_modem/cli/ctl/config_check.py` — NEW file, full verb body.
- `src/spark_modem/cli/main.py` with `ctl config-check` registered in the
  argparse tree.
- `debian/spark-modem-watchdog.postinst` with an idempotent HMAC placeholder
  write block.
- [x] **T03: 05.1-deb-packaging-hotfix 03** `est:1m 24s`
  - Repoint the systemd unit file's two ExecStart* paths from the never-existed
`/opt/spark-modem-watchdog/bin/` wrappers to the console-scripts that Plan
05.1-01 now materializes at `/opt/spark-modem-watchdog/python/bin/`. Drop the
in-file "Phase 4 follow-up: verify wrapper exists" admission comment block —
replace with audit-trail commentary referencing the locked I-01/I-02/I-04
decisions.

Implements locked decision **I-03** from
`.planning/phases/05.1-deb-packaging-hotfix/05.1-CONTEXT.md`. L-01
(LoadCredential= stays) is honored by NOT touching line 100.

Purpose: this is the literal fix for bug #2 (`systemctl start ...` returns
203/EXEC). Without Plan 05.1-01's `[project.scripts]` daemon entry, this
edit would still fail (the path wouldn't exist). With Plan 05.1-01's edit
already applied, the new path is correct.

Output: `debian/spark-modem-watchdog.service` with the three relevant
lines (12 ExecStartPre smoke, 17 ExecStartPre config-check, 23 ExecStart
daemon) all pointing into `/opt/spark-modem-watchdog/python/bin/` for the
two python-script lines; the smoke-test line at line 12 keeps its
`/opt/spark-modem-watchdog/libexec/` path (it's a shell script shipped via
`debian/spark-modem-watchdog.install`).
- [x] **T04: 05.1-deb-packaging-hotfix 04** `est:2min`
  - Author the operator-facing EXIT-CHECKLIST.md template that the on-site
engineer fills + commits as the Phase 05.1 EXIT gate. Mirror the shape of
Phase 5's SIGNOFF.md (CONTEXT.md decision V-03 explicitly invokes the same
pattern).

Implements locked decision **V-03** from
`.planning/phases/05.1-deb-packaging-hotfix/05.1-CONTEXT.md`.

Purpose: phase 05.1 has no ROADMAP-shaped Success Criteria block (D-03:
EXIT bar pattern, not a full SC block). The forcing function is a
structured operator-filled checklist with 9 rows — one per V-03 step from
CONTEXT.md L-162..173. The committed checklist is the phase-exit artifact.

This plan creates the TEMPLATE; the actual fill-in happens out-of-band on
the bench Jetson by the on-site engineer (single-operator workflow per
CONTEXT.md specifics).

Output: `.planning/phases/05.1-deb-packaging-hotfix/EXIT-CHECKLIST.md` with
header table, 9-row gate table, approval footer, footer reference.
- [x] **T05: 05.1-deb-packaging-hotfix 05**
  - Land the three regression gates that retire the bug class permanently
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
- [x] **T06: Plan 06** `est:2min`
  - Land the two documentation/metadata changes that finalize the phase plan:

1. Rewrite ROADMAP.md Phase 05.1's placeholder Goal line (currently
   `Goal: [Urgent work - to be planned]`) and populate the Plans list to
   reflect the 6 plans `/gsd-plan-phase 05.1` produced. CONTEXT.md
   "Roadmap housekeeping" deferred-ideas section explicitly defers this to
   plan-phase, not discuss-phase.

2. Add a `2.0.1-1` entry to `debian/changelog` per CONTEXT.md "Claude's
   Discretion" (PEP-440 patch bump chosen over `2.0.0+hotfix.1` for
   simplicity and broad tooling compatibility — both are valid Debian
   version strings; 2.0.1 is the cleaner shape).

Purpose: future readers of ROADMAP.md (Phase 6 planner, future operators)
need to see what Phase 05.1 actually delivered. Future `apt-cache policy`
consumers need to see the version reflects the hotfix. Without this plan,
the Phase 05.1 entry stays as `[Urgent work - to be planned]` and the .deb
ships as `2.0.0-1` indistinguishable from the pre-hotfix package.

Output:
- `.planning/ROADMAP.md` Phase 05.1 entry rewritten.
- `debian/changelog` with a new top entry.

## Files Likely Touched

- `debian/spark-modem-watchdog.service`
- `.planning/phases/05.1-deb-packaging-hotfix/EXIT-CHECKLIST.md`
- `scripts/postinst_smoke_test.sh`
- `tests/integration/test_unit_file_audit.py`
- `.github/workflows/build-deb.yml`
