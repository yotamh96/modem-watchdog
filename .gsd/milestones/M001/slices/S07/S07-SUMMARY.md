---
id: S07
parent: M001
milestone: M001
provides: []
requires: []
affects: []
key_files: []
key_decisions: []
patterns_established: []
observability_surfaces: []
drill_down_paths: []
duration: 
verification_result: passed
completed_at: 2026-05-12
blocker_discovered: false
---
# S07: Daemon Startup Hotfix

**# Plan 05.2-01 — SUMMARY**

## What Happened

# Plan 05.2-01 — SUMMARY

## What was done

Single commit (`e49dc7b`, `fix(daemon): use Settings() directly in production main`)
on the main branch, applied in the same session that closed Phase 05.1.

**Changes:**

1. `src/spark_modem/daemon/main.py`:
   - Added new import line: `from spark_modem.config.settings import Settings`
   - Replaced `settings = build_default_settings()` with `settings = Settings()`
     inside `_production_main`'s Step 2 try-block (around line 199 in the
     pre-fix file)
   - Added an inline multi-line comment documenting the bench Jetson deploy
     failure (2026-05-12 EROFS on `/tmp/spark-modem-cli`) and the reason
     for the swap

2. `_laptop_main` is unchanged. The CLI laptop-sandbox factory
   `build_default_settings()` is still used at line 119 for the `--laptop`
   integration-test wiring, which is correct for fixture-driven dev runs.

## Verification

**Local (dev host):**
- `uv run mypy --strict src/spark_modem/daemon/main.py` — 0 issues
- `uv run ruff check src/spark_modem/daemon/main.py` — clean

**CI (`build-deb.yml` run 25725010483, HEAD e49dc7b):**
- Build .deb: ✓ (3m33s)
- Verify .deb meta: ✓ (38 MiB)
- V-02 install + verify in clean Ubuntu 20.04 arm64 container: ✓ (including
  the new V-02 sub-gates from Phase 05.1: no `/_work/` in shims; shim
  trampoline exec works end-to-end)
- Upload artifact: ✓

**Bench Jetson (pending — recorded in VERIFICATION.md once user confirms):**
- `apt install ./spark-modem-watchdog_2.0.0-0.gite49dc7b-1_arm64.deb` followed
  by `systemctl start spark-modem-watchdog.service` must reach
  `Active: active (running)` with `sd_notify READY=1` in the journal.

## Bug class retired

Production daemon main no longer reaches into CLI-only laptop-sandbox state.
The settings construction path is now consistent with the systemd unit's
ReadWritePaths / namespace hardening: the daemon mkdirs `/var/lib/`,
`/run/`, and `/var/log/` subtrees that the unit declares writable, and never
touches `/tmp/` (which `ProtectSystem=strict` correctly renders read-only).

## Why retroactive

The fix was committed inline during the Phase 05.1 deploy walk, before the
phase 05.2 directory existed. The plan and this summary are the retroactive
planning trail. The work itself is real and shippable; only the GSD
documentation is catching up.
