---
phase: 05.2-daemon-startup-hotfix
verdict: PASS
ci_verdict: PASS
bench_verdict: PASS (new failure surfaces in different layer — tracked as Phase 05.3)
ci_run: 25725010483
fix_commit: e49dc7b
bench_install_deb: spark-modem-watchdog_2.0.0-0.gite49dc7b0-1_arm64.deb
bench_verified: 2026-05-12 10:25 UTC
---

# Phase 05.2 — VERIFICATION

## Phase goal (restated)

The .deb produced from a commit containing the `daemon/main.py` Settings-source
fix must install on a bench Jetson, pass both `ExecStartPre` gates
(postinst smoke + `ctl config-check`) using a real (operator-provisioned)
HMAC secret, and **the main `ExecStart` (the daemon itself) must successfully
mkdir `/var/lib/spark-modem-watchdog`, `/run/spark-modem-watchdog`, and
`/var/log/spark-modem-watchdog` without an OSError** — proving the daemon
no longer reaches into the CLI laptop-sandbox `/tmp/spark-modem-cli` paths
that the systemd unit's `ProtectSystem=strict` correctly blocks.

## CI evidence (CONFIRMED)

| Gate | Result |
|------|--------|
| Build .deb (commit e49dc7b) | ✓ |
| Verify .deb meta (38 MiB ≤ 40 MiB) | ✓ |
| V-02 install + verify (a postinst smoke) | ✓ |
| V-02 install + verify (b shims executable + b.1 no /_work/ + b.2 shim exec ≠ 127) | ✓ |
| V-02 install + verify (c HMAC placeholder 0600 root:root) | ✓ |
| V-02 install + verify (d systemd-analyze verify) | ✓ (warn-ignore on `LoadCredential` + `StartLimitIntervalSec` — same as Phase 05.1, expected on systemd 245 per L-04) |

Workflow run: <https://github.com/yotamh96/modem-watchdog/actions/runs/25725010483>

Note: the CI container test step exercises `spark-modem ctl config-check` but
does NOT exercise the daemon's `ExecStart` under a hardened systemd namespace.
This is a known gap — the bug class fixed here would only surface against
the unit's `ProtectSystem=strict` + read-only `/tmp`. Consider adding a
"dry-start the daemon with the production unit" CI gate in a future hardening
pass (out of scope for 05.2).

## Bench Jetson evidence (CONFIRMED 2026-05-12 10:25 UTC)

`sudo apt install ./spark-modem-watchdog_2.0.0-0.gite49dc7b0-1_arm64.deb`
on the bench Jetson with the operator-provisioned HMAC secret already in place
from the prior 10cec6d6 install. systemd ran the unit's three exec phases:

| Phase | Process | Exit | Notes |
|-------|---------|------|-------|
| ExecStartPre #1 — postinst smoke | `postinst_smoke_test.sh` | 0/SUCCESS | All 12 runtime libs + daemon entry points import |
| ExecStartPre #2 — config-check | `spark-modem ctl config-check` | 0/SUCCESS | HMAC secret OK at 0600 root:root, 65 bytes |
| **ExecStart — daemon main** | `spark-modem-watchdog` | **78/CONFIG** | Phase 05.2 fix worked — see below |

**The failure mode changed**, which is the verification signal:

| | Before (10cec6d6) | After (e49dc7b) |
|--|------------------|-----------------|
| Exit code | `1/FAILURE` | `78/CONFIG` |
| Failure | `OSError: [Errno 30] Read-only file system: '/tmp/spark-modem-cli'` at `_ensure_dirs` (line 207) | `unknown fleet triple: failed to compute local fleet triple: qmicli --version stdout did not match libqmi-glib regex` |
| Layer | Filesystem mkdir against systemd `ProtectSystem=strict` | Phase 5 X-03 fleet-triple preflight (`preflight_check_known_fleet_triple`) |

The daemon now successfully:
1. Constructs `Settings()` with production defaults (line 199)
2. Reads `state_root_path` = `/var/lib/spark-modem-watchdog` (line 206)
3. Reads `run_dir` = `/run/spark-modem-watchdog` (line 205)
4. Calls `_ensure_dirs(...)` — succeeds, no EROFS (line 207)
5. Advances to `_production_main` Step 3 preflight (line ~210)
6. Returns `78` (EX_CONFIG) from the structured preflight-failure branch

No `OSError`, no `/tmp/spark-modem-cli` anywhere in the journal — the
Phase 05.2 bug class is fully retired.

## New failure (NOT Phase 05.2 — tracked separately)

The 78/CONFIG that the daemon now produces is a Phase 5 X-03 preflight
rejection: `qmicli --version` on JetPack 5.1.5 / Ubuntu 20.04 / libqmi 1.30.4
prints only the `qmicli 1.30.4` first line with no `Compiled with libqmi-glib
X.Y.Z` line, but the regex in `src/spark_modem/qmi/version.py:30` only
matches the `libqmi-glib` form. Tracked as Phase 05.3 hotfix.

## Verdict

- **CI:** PASS (run 25725010483, commit e49dc7b)
- **Bench Jetson:** PASS for Phase 05.2 scope (failure mode shifted from
  EROFS to a deeper, structured rejection at a different layer — exactly the
  desired transition). New failure surfaces in Phase 5's fleet-triple regex,
  which is outside 05.2's stated scope and tracked in
  `.planning/phases/05.3-libqmi-version-regex-hotfix/`.
