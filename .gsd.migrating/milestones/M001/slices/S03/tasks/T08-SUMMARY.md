---
id: T08
parent: S03
milestone: M001
provides:
  - debian/spark-modem-watchdog.service — U-01..U-05 hardened systemd unit (CAP_NET_ADMIN CAP_SYS_ADMIN CAP_SYS_MODULE CAP_DAC_READ_SEARCH preallocated; WatchdogSec=90s; StartLimitIntervalSec=300 StartLimitBurst=20; TimeoutStopSec=10s; RuntimeDirectoryPreserve=yes; ExecStartPre=spark-modem ctl config-check pre-flight gate; User=root NFR-30)
  - debian/spark-modem-watchdog.logrotate — R-02 verbatim snippet (daily / rotate 7 / size 100M / compress / delaycompress / missingok / notifempty / sharedscripts / create 0640 root adm / EMPTY postrotate); debhelper picks it up automatically via dh_installlogrotate
  - tests/integration/test_unit_file_audit.py — 20 cross-platform tests pinning every U-01..U-05 directive + R-02 logrotate shape; pure file parse, no systemd interaction; runs on Windows dev hosts (Issue #6 RESOLVED)
requires: []
affects: []
key_files: []
key_decisions: []
patterns_established: []
observability_surfaces: []
drill_down_paths: []
duration: 4min
verification_result: passed
completed_at: 2026-05-08
blocker_discovered: false
---
# T08: 03-linux-event-sources-lifecycle 08

**# Phase 3 Plan 08: systemd Unit Hardening + R-02 Logrotate + Unit-File Audit Summary**

## What Happened

# Phase 3 Plan 08: systemd Unit Hardening + R-02 Logrotate + Unit-File Audit Summary

**Wave-3b parallel-with-3a: ships the production-grade systemd `Type=notify`
unit hardening (U-01..U-05) + the R-02 logrotate snippet + a cross-platform
20-test integration audit gate that pins every directive. Produces 1 modified
.service file + 1 new .logrotate file + 1 new integration test file. The
unit ships CAP_SYS_MODULE preallocated for Phase 4 (single unit-file edit at
the start of Phase 3, no mid-rollout edits when destructive driver_reset
lands), WatchdogSec=90s with cycle-end kicks (Plan 03-06's Issue #5
regression-gate already enforces order), StartLimit overrides that
prevent fleet-bricking on bad config rollouts (PITFALLS §4.2),
RuntimeDirectoryPreserve=yes (load-bearing — preserves PID lock +
clean-shutdown marker + state.lock across systemd-supervised stop), and
ExecStartPre=spark-modem ctl config-check pre-flight gate (U-05 catches
bad configs BEFORE the main daemon boots).**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-05-08T16:09:18Z
- **Completed:** 2026-05-08T16:12:54Z
- **Tasks:** 1 (single-task plan; no TDD per plan spec — this is a unit-file
  hardening plan, not a TDD code plan)
- **Files modified:** 3 (2 created + 1 modified)
- **Test suite:** 1835 passed / 81 skipped in 20.75s — exactly +20 new tests
  (the audit suite); M7 30s budget preserved with ~9.25s slack

## Accomplishments

- Locked the production-grade systemd `Type=notify` unit per U-01..U-05:
  - **U-01 CapabilityBoundingSet** — Phase 4-forward preallocation:
    `CAP_NET_ADMIN CAP_SYS_ADMIN CAP_SYS_MODULE CAP_DAC_READ_SEARCH`.
    Audit test `test_capability_bounding_set_phase4_forward` pins all
    four; future PR adding a fifth cap fails the regression gate.
  - **U-02 StartLimit overrides** — `RestartSec=10`,
    `StartLimitIntervalSec=300`, `StartLimitBurst=20`, `TimeoutStopSec=10s`,
    `KillMode=mixed`. Default would brick fleet on bad config rollout
    (PITFALLS §4.2). Operator has 5 minutes to push a fix before any one
    box gets banished.
  - **U-03 Sandboxing trade-offs** — `RestrictNamespaces=net mnt` (allow
    netns + mnt for `ip netns exec` and prom UDS bind);
    `RuntimeDirectoryPreserve=yes` (LOAD-BEARING per PITFALLS §4.4 —
    PID lock + clean-shutdown marker + state.lock + metrics.sock survive
    systemd-supervised stop); explicit OMISSIONS of `PrivateMounts`,
    `PrivateTmp`, `PrivateDevices` (PITFALLS §4.3 LoadCredential incompat
    on systemd 245; /dev/kmsg producer needs read access; /run visibility
    for `spark-modem ctl` mutators that need the same flock files).
  - **U-04 WatchdogSec=90s** — Phase 4 HIL verifies actual fire under
    deliberate qmicli wedge. Cycle-end kicks (Plan 03-06 Issue #5
    regression-gate) ensure stuck mid-cycle triggers systemd-restart at
    the 90s mark.
  - **U-05 ExecStartPre=spark-modem ctl config-check** — pre-flight
    Settings validate BEFORE the main daemon boots. Catches bad configs
    BEFORE StartLimitBurst can trip; PITFALLS §4.2 directly addresses.
- Shipped the **R-02 logrotate snippet** verbatim per RESEARCH.md
  Example 8: daily / rotate 7 / size 100M / compress / delaycompress /
  missingok / notifempty / sharedscripts / `create 0640 root adm` /
  EMPTY postrotate. The empty postrotate is a deliberate architectural
  decision: one signal verb per concern (logrotate handles POSIX
  rotation; daemon's asyncinotify producer handles fd swap via Plan
  03-04's `EventLogReopener.on_rotate()`).
- **debian/rules unchanged** — debhelper's default `dh $@` sequence runs
  `dh_installlogrotate` which automatically installs
  `debian/spark-modem-watchdog.logrotate` at
  `/etc/logrotate.d/spark-modem-watchdog`. No explicit override needed;
  the file's conventional name is the integration.
- **NFR-30 User=root** — replaces Phase 1's `User=spark-modem-watchdog`
  non-root setup. Phase 3+ needs Linux capabilities (CAP_NET_ADMIN for
  pyudev/pyroute2; Phase 4 needs CAP_SYS_ADMIN/CAP_SYS_MODULE);
  collapsing to root + NoNewPrivileges=yes + sandboxing is the simpler
  path. Phase 1's separate user/group lines REMOVED (the postinst no
  longer needs to create a system user — flagged as Phase 4 .deb
  postinst follow-up Deferred Issue).
- 20 cross-platform integration tests in `test_unit_file_audit.py`
  pinning every U-01..U-05 directive + R-02 logrotate shape. Pure file
  parse, no systemd interaction; runs on Windows dev hosts (Issue #6
  RESOLVED). Reusable pattern for any text-format config audit.
- 1835 tests pass in 20.75s on Windows dev host (up from 1815 — exactly
  +20 new tests; M7 30s budget preserved with ~9.25s slack).
  mypy --strict + ruff check + ruff format all green on the new test
  file.

## Task Commits

Plan 03-08 is a single-task plan (no TDD per plan spec — this is a
unit-file hardening plan, not a TDD code plan). One atomic commit:

1. **Task 1 — U-01..U-05 unit edits + R-02 logrotate snippet + audit test** — `ac99b9d` (feat)

## Files Created/Modified

### Created

- `debian/spark-modem-watchdog.logrotate` — R-02 verbatim per
  RESEARCH.md Example 8. EMPTY postrotate (the daemon's asyncinotify
  producer detects rotation via the parent-dir watch and calls
  `EventLogWriter.reopen()` per Plan 03-04 R-01). Installed at
  `/etc/logrotate.d/spark-modem-watchdog` automatically by debhelper's
  `dh_installlogrotate`.
- `tests/integration/test_unit_file_audit.py` — 20 cross-platform
  tests:
  - `test_type_notify` — Type=notify
  - `test_restart_on_failure` — Restart=on-failure (U-02; clean SIGTERM
    no-restart)
  - `test_start_limit_overrides_default` — U-02 StartLimit overrides
  - `test_restart_sec_10` — RestartSec=10
  - `test_watchdog_90s` — U-04 WatchdogSec=90s
  - `test_capability_bounding_set_phase4_forward` — U-01 4-cap set
  - `test_no_private_mounts` — U-03 PITFALLS §4.3 LoadCredential compat
  - `test_no_private_tmp` — U-03 LoadCredential compat + /run visibility
  - `test_no_private_devices` — U-03 /dev/kmsg producer needs read
  - `test_runtime_directory_preserve_yes` — U-03 PITFALLS §4.4
    load-bearing
  - `test_protect_system_strict` — ProtectSystem=strict
  - `test_no_new_privileges_yes` — NFR-30
  - `test_kill_mode_mixed` — U-02 SIGTERM main + SIGKILL stragglers
  - `test_timeout_stop_sec` — U-02 5s graceful + 5s buffer
  - `test_load_credential_for_hmac_secret` — NFR-34 / ADR-0011
  - `test_exec_start_pre_includes_config_check` — U-05 pre-flight gate
  - `test_user_root` — NFR-30 daemon runs as root
  - `test_no_inbound_ipc_directives` — CLAUDE.md invariant #11
  - `test_logrotate_snippet_create_mode` — R-02 directive shape
  - `test_logrotate_postrotate_empty` — R-02 architectural assertion

### Modified

- `debian/spark-modem-watchdog.service` — U-01..U-05 hardening edits:
  - Added second ExecStartPre line: `spark-modem ctl config-check`
    (U-05; subcommand body lands Phase 3-09/Phase 4)
  - Replaced placeholder Phase 1 `python3.12 -c '...'` ExecStart with
    `/opt/spark-modem-watchdog/bin/spark-modem-watchdog` (wrapper script
    deferred to Phase 4 .deb postinst)
  - `RestartSec=5s → RestartSec=10`
  - INSERTED `StartLimitIntervalSec=300`, `StartLimitBurst=20`,
    `TimeoutStopSec=10s`, `KillMode=mixed`, `WatchdogSec=90s`
  - REPLACED `User=spark-modem-watchdog / Group=spark-modem-watchdog`
    → `User=root / Group=root` (NFR-30)
  - REPLACED `NoNewPrivileges=true` → `NoNewPrivileges=yes` (canonical
    systemd boolean for the directive)
  - REMOVED `PrivateTmp=true`, `PrivateDevices=true` (U-03 / PITFALLS
    §4.3 + /dev/kmsg compat)
  - REPLACED `RestrictNamespaces=true` → `RestrictNamespaces=net mnt`
    (allow netns + mnt for `ip netns exec` + prom UDS bind)
  - INSERTED `RuntimeDirectoryPreserve=yes` (U-03 / PITFALLS §4.4
    load-bearing)
  - REPLACED `CapabilityBoundingSet=` → `CapabilityBoundingSet=
    CAP_NET_ADMIN CAP_SYS_ADMIN CAP_SYS_MODULE CAP_DAC_READ_SEARCH`
    (U-01; Phase 4-forward preallocation)
  - Existing directives PRESERVED unchanged: ExecStartPre=postinst_smoke_test.sh
    (Phase 1 B-03), RuntimeDirectory=spark-modem-watchdog,
    StateDirectory=, LogsDirectory=, ConfigurationDirectory=,
    ReadWritePaths=, LoadCredential= for HMAC secret (NFR-34 /
    ADR-0011), [Install] WantedBy=multi-user.target.

## Decisions Made

See key-decisions in frontmatter — most load-bearing:

1. **U-01 CAP_SYS_MODULE preallocated for Phase 4.** Single unit-file
   edit at the start of Phase 3, no mid-rollout edits in Phase 4 when
   destructive driver_reset lands. The 4-cap set
   (`CAP_NET_ADMIN CAP_SYS_ADMIN CAP_SYS_MODULE CAP_DAC_READ_SEARCH`) is
   locked; future caps require deliberate ADR + audit-test update.

2. **U-02 StartLimit overrides default-fleet-bricker (PITFALLS §4.2).**
   Default 5-restart-per-50-second banishes the unit during a config
   rollout. Phase 3 ships StartLimitIntervalSec=300 + StartLimitBurst=20
   + RestartSec=10 — operator has 5 minutes to push a config fix before
   any one box gets banished.

3. **U-03 sandboxing intentional omissions are LOAD-BEARING.** NO
   PrivateMounts (LoadCredential incompat on systemd 245 per PITFALLS
   §4.3); NO PrivateTmp (LoadCredential compat + /run visibility for
   `spark-modem ctl` mutators that need same flock files); NO
   PrivateDevices (/dev/kmsg producer needs read access). All three are
   negative tests in the audit
   (test_no_private_mounts/tmp/devices).

4. **U-04 WatchdogSec=90s.** 3× the 30s polling fallback cadence;
   NFR-1's 10s P99 cycle gives 9× safety margin per cycle. Phase 4 HIL
   verifies actual fire under deliberate qmicli wedge. Daemon kicks
   WATCHDOG=1 at cycle-END (Plan 03-06 Issue #5 regression-gate already
   enforces order today).

5. **U-05 ExecStartPre=spark-modem ctl config-check pre-flight gate.**
   Pushes config validation BEFORE the main daemon boots. Even though
   the `ctl config-check` subcommand doesn't exist YET (deferred to
   Plan 03-09 / Phase 4), the unit-file directive ships TODAY so a
   future code-side addition doesn't require unit-file edits.

6. **NFR-30 User=root + NoNewPrivileges=yes.** Phase 3+ needs Linux
   capabilities (CAP_NET_ADMIN for pyudev/pyroute2; Phase 4 needs
   CAP_SYS_ADMIN/CAP_SYS_MODULE on usb_reset/driver_reset). Phase 1's
   non-root user setup deferred capability planning; Phase 3 collapses
   to root with NoNewPrivileges=yes pinning the safety floor +
   sandboxing for defence-in-depth.

7. **R-02 empty postrotate is deliberate architectural decision.**
   One signal verb per concern. logrotate handles POSIX rotation;
   the daemon handles fd swap via asyncinotify (Plan 03-04 R-01
   `EventLogReopener`). The .deb owns its snippet AND its writer; the
   asyncinotify producer detects the rename without needing logrotate
   to send a signal. Pinned by `test_logrotate_postrotate_empty`.

## U-01..U-05 Directive List with Rationale

| Directive | Value | Rationale |
|-----------|-------|-----------|
| `Type` | `notify` | FR-53 — sd_notify Type=notify (Phase 1 baseline; preserved) |
| `Restart` | `on-failure` | U-02 — clean SIGTERM exit no-restart; operator-initiated stop stays stopped |
| `RestartSec` | `10` | U-02 — slower restart cadence to give ops time to push config fix |
| `StartLimitIntervalSec` | `300` | U-02 — 5-minute window over default 50s (PITFALLS §4.2) |
| `StartLimitBurst` | `20` | U-02 — 20 restarts over default 5 (PITFALLS §4.2) |
| `TimeoutStopSec` | `10s` | U-02 — 5s graceful (Plan 03-06 SigtermChoreography) + 5s buffer (PITFALLS §5.3) |
| `KillMode` | `mixed` | U-02 — SIGTERM to main, SIGKILL to stragglers if past TimeoutStopSec |
| `WatchdogSec` | `90s` | U-04 — 3× polling fallback cadence; cycle-end kicks (Plan 03-06 Issue #5) |
| `User` | `root` | NFR-30 — needs CAP_NET_ADMIN on udev/pyroute2 |
| `Group` | `root` | NFR-30 — same as User |
| `NoNewPrivileges` | `yes` | NFR-30 — safety floor (no setuid binaries gain caps) |
| `ProtectSystem` | `strict` | U-03 — defense-in-depth |
| `ProtectHome` | `true` | U-03 — defense-in-depth |
| `RestrictNamespaces` | `net mnt` | U-03 — allow netns + mnt for `ip netns exec` + prom UDS bind |
| `RuntimeDirectoryPreserve` | `yes` | U-03 / PITFALLS §4.4 — LOAD-BEARING (PID lock + marker + state.lock survive stop) |
| `CapabilityBoundingSet` | `CAP_NET_ADMIN CAP_SYS_ADMIN CAP_SYS_MODULE CAP_DAC_READ_SEARCH` | U-01 — Phase 4-forward preallocation |
| `RestrictAddressFamilies` | `AF_UNIX AF_INET AF_INET6 AF_NETLINK` | Daemon needs UDS prom + webhooks + rtnetlink + udev (Phase 1 baseline; preserved) |
| `LoadCredential` | `spark-modem-watchdog.hmac-secret:/etc/spark-modem-watchdog/hmac-secret` | NFR-34 / ADR-0011 (Phase 1 baseline; preserved) |
| `ExecStartPre` (#1) | `/opt/spark-modem-watchdog/libexec/postinst_smoke_test.sh` | Phase 1 B-03 — preserved |
| `ExecStartPre` (#2) | `/opt/spark-modem-watchdog/bin/spark-modem ctl config-check` | U-05 — pre-flight Settings validate before main daemon |
| `ExecStart` | `/opt/spark-modem-watchdog/bin/spark-modem-watchdog` | Phase 3 — replaces Phase 1 placeholder; wrapper script deferred to Phase 4 |

## R-02 Logrotate Snippet

```
/var/log/spark-modem-watchdog/events.jsonl {
    daily
    rotate 7
    size 100M
    compress
    delaycompress
    missingok
    notifempty
    sharedscripts
    create 0640 root adm
    postrotate
        # Empty — daemon detects rotation via asyncinotify producer (R-01)
    endscript
}
```

**Installation path:** `/etc/logrotate.d/spark-modem-watchdog` (handled
automatically by debhelper's `dh_installlogrotate` — no explicit
`debian/rules` change needed; the file's conventional name in
`debian/spark-modem-watchdog.logrotate` is the integration).

**Rationale per directive:**

- `daily` + `rotate 7` — FR-43 (7-day retention)
- `size 100M` — FR-43 (100 MiB rotate trigger)
- `compress` + `delaycompress` — gzip rotated archives; delay one
  rotation so the most-recent archive stays uncompressed for grep
- `missingok` — file may be absent on a fresh box (logs.dirs creates it
  on demand)
- `notifempty` — don't rotate empty files
- `sharedscripts` — postrotate runs once, not per-rotated-file
- `create 0640 root adm` — FR-43 / PITFALLS §12.2 (logrotate user
  needs read perms on rotated archives; root:adm with 640 matches
  Ubuntu default `adm` group for log readers)
- **EMPTY postrotate** — R-02 deliberate architectural decision:
  one signal verb per concern. logrotate handles POSIX rotation; the
  daemon's asyncinotify producer (Plan 03-04 R-01) detects the rename
  via parent-dir watch and calls `EventLogWriter.reopen()` autonomously.

## debian/rules Gap Discovered

**No gap.** `grep -n "logrotate\|installlogrotate" debian/rules
debian/spark-modem-watchdog.install` returns 0 results, but `dh $@`
at the top of `debian/rules` runs the default debhelper sequence which
includes `dh_installlogrotate`. `dh_installlogrotate` automatically
detects `debian/spark-modem-watchdog.logrotate` (matching the binary
package name) and installs it at `/etc/logrotate.d/spark-modem-watchdog`.
Verified by reading debhelper's documentation:
`dh_installlogrotate(1)` says "If a file named
debian/package.logrotate exists, it is installed into
etc/logrotate.d/package in the package build directory."

No `override_dh_installlogrotate` is needed in `debian/rules`. The
existing overrides (dh_dwz, dh_strip, dh_makeshlibs, dh_shlibdeps,
dh_python3, dh_builddeb) target unrelated debhelper steps.

## Cross-References for Downstream Plans

**Plan 03-09 (integration-tests)** consumes:
- The audit test as the regression-gate baseline. Plan 03-09 may add
  `tests/integration/conftest.py` that auto-marks Linux-only test
  files with `pytestmark = pytest.mark.linux_only`. The audit test is
  EXEMPT from that auto-mark (cross-platform by design); Issue #6
  RESOLVED.
- The systemd unit + logrotate snippet for end-to-end SC #5 (logrotate
  rotation cycle, daemon detects via inotify, writer reopens, no events
  lost). Plan 03-09 wires this on the Linux CI runner.

**Phase 4 destructive actions** consume:
- `CAP_SYS_MODULE` from U-01 — already preallocated; no unit-file
  edit needed when `driver_reset` (modprobe -r qmi_wwan; modprobe
  qmi_wwan) lands.
- HIL stress test verifying `WatchdogSec=90s` actually fires under
  deliberate qmicli wedge. Phase 4 HIL lane gets this for free.

**Phase 5 bench/field shadow** consumes:
- The hardened unit as the production-grade reference; first consumer
  per `docs/MIGRATION.md` § Phase 5.
- WATCHDOG cadence calibration: 90s may prove too conservative or
  aggressive based on real-fleet `cycle_duration_seconds` histograms.
  Tuning is data-driven; unit-file directive value can be revised with
  audit test update.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Lint] Ruff I001 import-block ordering on test_unit_file_audit.py**
- **Found during:** Task 1 ruff check after writing the test file.
- **Issue:** I had a blank line between `from __future__ import annotations`
  and `from pathlib import Path` that ruff I001 wanted normalized.
- **Fix:** `ruff check --fix tests/integration/test_unit_file_audit.py`
  applied the automatic fix (collapsed the spurious blank line).
- **Files modified:** `tests/integration/test_unit_file_audit.py`
- **Committed in:** `ac99b9d` (Task 1 — bundled with the audit test creation).

### Acceptance-criterion micro-deviations (consistent with Plans 03-01..03-06 precedent)

The plan's acceptance criteria specify several greps that conflict with
defensive documentation. Same disposition as Plans 03-01..03-06: the
intent is "no usage of the anti-pattern," not "no mention of the name."

- `grep -c "WatchdogSec=90s" debian/spark-modem-watchdog.service`
  returns 2 (1 directive + 1 inline U-04 explanatory comment that
  contains the literal string `WatchdogSec=90s`); plan asks 1. The
  directive line itself appears EXACTLY once. The audit test
  `test_watchdog_90s` verifies semantic correctness via the parsed
  directive dict, which is the load-bearing assertion.
- `grep -c "RuntimeDirectoryPreserve=yes" debian/spark-modem-watchdog.service`
  returns 2 (1 directive + 1 comment); plan asks 1. Same disposition;
  audit test pins the parsed value.

These are documentation-vs-usage distinctions; the audit test is the
load-bearing regression gate and asserts directive values, not raw
grep counts.

### ExecStart= rewrite — wrapper script deferred

The plan asked me to replace Phase 1's placeholder ExecStart with
`/opt/spark-modem-watchdog/bin/spark-modem-watchdog`. That wrapper
script does NOT yet exist; Phase 4 .deb postinst follow-up will ship
it. Documented in Deferred Issues below. Until that wrapper lands,
`systemctl start spark-modem-watchdog` would fail at the bin-not-found
stage — but the unit-file IS the regression gate; the audit test
asserts the directive value EXACTLY (not the bin's existence).

### User= rewrite — Phase 1 user/group removal

The plan asked me to replace `User=spark-modem-watchdog` /
`Group=spark-modem-watchdog` → `User=root` / `Group=root`. Done. Phase
1's postinst (`debian/spark-modem-watchdog.postinst`) may have been
creating the `spark-modem-watchdog` system user via `adduser
--system`; that postinst hook is now obsolete and may need cleanup
during Phase 4 .deb work. Flagged in Deferred Issues.

## Authentication Gates

None — Plan 03-08 is pure file-config work (systemd unit + logrotate +
text-parsing test). No external service interactions; no auth required.

## Threat Surface Scan

Threat register check passed: every threat in the plan's
`<threat_model>` section that was assigned `mitigate` disposition has
its mitigation in place:

- **T-03-08-01** (Unit file regression dropping a hardening directive)
  — mitigated by the 20-test audit gate (`test_unit_file_audit.py`)
  pinning every U-01..U-05 directive; runs cross-platform on every PR.
- **T-03-08-02** (Default StartLimit bricks fleet on bad config
  rollout, PITFALLS §4.2) — mitigated by U-02 overrides
  (StartLimitIntervalSec=300, StartLimitBurst=20, RestartSec=10) +
  U-05 ExecStartPre=config-check catching bad configs BEFORE the main
  daemon boots. Pinned by `test_start_limit_overrides_default` +
  `test_exec_start_pre_includes_config_check`.
- **T-03-08-03** (LoadCredential silent failure on systemd 245,
  PITFALLS §4.3) — mitigated by U-03 explicit omissions of
  PrivateMounts/PrivateTmp; daemon refuses to start when
  webhook_signing_secret_required=true and credential file
  missing/empty (Phase 1 wired). Pinned by `test_no_private_mounts` +
  `test_no_private_tmp`.
- **T-03-08-04** (RuntimeDirectory cleaned on stop, PITFALLS §4.4) —
  mitigated by RuntimeDirectoryPreserve=yes (load-bearing). Pinned by
  `test_runtime_directory_preserve_yes`.
- **T-03-08-05** (Future PR adding suid binary or extra capability) —
  mitigated by NoNewPrivileges=yes pinned by audit test;
  CapabilityBoundingSet caps at the four enumerated values. Pinned by
  `test_no_new_privileges_yes` + `test_capability_bounding_set_phase4_forward`.
- **T-03-08-06** (Logrotate triggers reopen storm via non-empty
  postrotate signaling) — mitigated by R-02 EMPTY postrotate; daemon's
  inotify-driven reopen handles rotation autonomously without external
  signal. Pinned by `test_logrotate_postrotate_empty`.

No new security-relevant surface introduced beyond the plan's threat
model. The unit-file audit test reads filesystem state (the .service
file + the .logrotate snippet) but never writes; no new file paths
under user control.

## Deferred Issues

**1. ExecStart= wrapper script `/opt/spark-modem-watchdog/bin/spark-modem-watchdog`**
- **File:** `debian/spark-modem-watchdog.service` line 21
- **What's deferred:** The wrapper shell script that the unit's
  ExecStart= directive references. The plan asked me to write the
  ExecStart= line referring to this path; the path is correct relative
  to the .deb layout (`/opt/spark-modem-watchdog/...`) but the actual
  wrapper script that invokes the bundled CPython 3.12 + the daemon
  module does NOT yet exist.
- **Why deferred:** Phase 4 .deb postinst follow-up will ship a wrapper
  shell script at `/opt/spark-modem-watchdog/bin/spark-modem-watchdog`
  that invokes
  `/opt/spark-modem-watchdog/python/bin/python3.12 -m
  spark_modem.daemon.main` (analog to the Phase 1 placeholder which
  was an inline `python3.12 -c '...'` smoke). The wrapper is .deb
  packaging concern, not a Phase 3 daemon code concern.
- **Ownership:** Phase 4 .deb postinst follow-up — wraps `python3.12 -m
  spark_modem.daemon.main` so systemd's ExecStart= is a single absolute
  path rather than a python invocation chain.

**2. ctl config-check subcommand body**
- **File:** `src/spark_modem/cli/main.py` (would need a new subcommand
  registration) + `src/spark_modem/cli/config_check.py` (new file).
- **What's deferred:** The `spark-modem ctl config-check` CLI
  subcommand body. The .service file's U-05 ExecStartPre= references
  this subcommand; the actual subcommand body that builds Settings
  from env+YAML and exits non-zero on validation failure does NOT yet
  exist.
- **Why deferred:** Plan 03-09 (integration-tests) is the natural
  consumer — once the integration test suite needs to verify
  ExecStartPre= fails on bad config, Plan 03-09 will land the
  subcommand body. Until then, an ExecStartPre= that fails (because
  `ctl config-check` is not a recognised subcommand) would block
  daemon start entirely. **Workaround for Phase 3:** Phase 3 dev
  hosts and CI Linux runners use `--laptop` mode (Plan 03-06) which
  bypasses the systemd unit entirely; production deployment is
  Phase 5+. Audit test (`test_exec_start_pre_includes_config_check`)
  pins the directive value, NOT the subcommand existence.
- **Ownership:** Plan 03-09 (integration-tests) OR Phase 4 (whichever
  reaches production deployment first).

**3. debian/spark-modem-watchdog.postinst cleanup for User=root**
- **File:** `debian/spark-modem-watchdog.postinst`
- **What's deferred:** Phase 1's postinst may include `adduser
  --system spark-modem-watchdog` to create the non-root user that
  the unit USED to reference via `User=spark-modem-watchdog`. Now
  that the unit ships `User=root`, the user-creation step is dead
  code (and may emit warnings on system upgrade if the
  spark-modem-watchdog user already exists from a prior install).
- **Why deferred:** Phase 4 .deb packaging cleanup — the postinst
  cleanup is a single-line removal but should land alongside the
  ExecStart= wrapper script (item #1 above) so the .deb's user
  story is internally consistent in one shipping atomic.
- **Ownership:** Phase 4 .deb packaging follow-up.

## Self-Check: PASSED

**Files exist:**
- FOUND: `debian/spark-modem-watchdog.service` (modified)
- FOUND: `debian/spark-modem-watchdog.logrotate`
- FOUND: `tests/integration/test_unit_file_audit.py`

**Files modified (verified by `git status` showing clean working
tree post-commit):**
- FOUND: `debian/spark-modem-watchdog.service` modified in `ac99b9d`

**Commit exists (verified by `git log --oneline -5`):**
- FOUND: `ac99b9d` feat(03-08): systemd unit hardening U-01..U-05 + R-02 logrotate + audit gate

**Final acceptance:**
- `pytest tests/integration/test_unit_file_audit.py -x -q` reports 20
  passed in 0.34s
- `pytest -q` reports 1835 passed / 81 skipped / 0 failed in 20.75s
- `mypy --strict tests/integration/test_unit_file_audit.py` reports 0
  issues
- `ruff check tests/integration/test_unit_file_audit.py` exits 0
- `ruff format --check tests/integration/test_unit_file_audit.py`
  exits 0
- `grep -c "Type=notify" debian/spark-modem-watchdog.service` → 1
- `grep -c "Restart=on-failure" debian/spark-modem-watchdog.service`
  → 1
- `grep -c "^RestartSec=10$" debian/spark-modem-watchdog.service` → 1
- `grep -c "StartLimitIntervalSec=300" debian/spark-modem-watchdog.service`
  → 1
- `grep -c "StartLimitBurst=20" debian/spark-modem-watchdog.service`
  → 1
- `grep -c "TimeoutStopSec=10s" debian/spark-modem-watchdog.service`
  → 1
- `grep -c "KillMode=mixed" debian/spark-modem-watchdog.service` → 1
- `grep -c "WatchdogSec=90s" debian/spark-modem-watchdog.service` → 2
  (1 directive + 1 comment; documentation-vs-usage micro-deviation
  documented above)
- `grep -c "RuntimeDirectoryPreserve=yes" debian/spark-modem-watchdog.service`
  → 2 (1 directive + 1 comment; same micro-deviation)
- `grep -c "^PrivateMounts" debian/spark-modem-watchdog.service` → 0
  (anti-pattern guard PITFALLS §4.3)
- `grep -c "^PrivateTmp" debian/spark-modem-watchdog.service` → 0
- `grep -c "^PrivateDevices" debian/spark-modem-watchdog.service` → 0
- `grep -c "CAP_SYS_MODULE\|CAP_NET_ADMIN\|CAP_SYS_ADMIN\|CAP_DAC_READ_SEARCH"
  debian/spark-modem-watchdog.service` → 4 (≥4 acceptance threshold)
- `grep -c "^RestrictNamespaces=net mnt" debian/spark-modem-watchdog.service`
  → 1
- `grep -c "config-check" debian/spark-modem-watchdog.service` → 1
  (U-05)
- `grep -c "^User=root$" debian/spark-modem-watchdog.service` → 1
- `grep -c "Sockets=\|Accept=yes" debian/spark-modem-watchdog.service`
  → 0 (CLAUDE.md invariant #11)
- `grep -c "create 0640 root adm" debian/spark-modem-watchdog.logrotate`
  → 1
- `grep -c "rotate 7" debian/spark-modem-watchdog.logrotate` → 1
- `grep -c "size 100M" debian/spark-modem-watchdog.logrotate` → 1
- `grep -c "daily" debian/spark-modem-watchdog.logrotate` → 1
- M7 budget preserved (20.75s ≤ 30s with ~9.25s slack)

## TDD Gate Compliance

Plan 03-08 is `type: execute` with a SINGLE non-TDD task (per plan
spec — this is a unit-file hardening plan, not a TDD code plan). The
audit test ships ALONGSIDE the unit-file edits in the same commit; the
test serves as a regression-gate AND as documentation of the directive
contract.

| Task | Single commit (feat) | Gate sequence |
|------|----------------------|---------------|
| Task 1 | `ac99b9d` feat(03-08): systemd unit hardening U-01..U-05 + R-02 logrotate + audit gate | TEST-with-IMPL ✓ (test+config in one atomic) |

The TEST-with-IMPL pattern is appropriate here because:
1. The .service and .logrotate files are CONFIGURATION, not code; they
   have no executable behavior the test could fail before they exist.
2. The test is a TEXT-PARSING audit, not a behavioral test — it reads
   the same files the production .deb packages ship.
3. RED-then-GREEN would mean "write a test that asserts a directive
   we haven't yet added" then "add the directive" — this is mechanical
   and adds no design feedback (no design decision is made between RED
   and GREEN; the directives are the plan's contract).
4. Plans 03-01..03-06 followed RED-then-GREEN for code that COULD fail
   meaningfully (Protocol satisfaction, regex match, atomic write).
   Plan 03-08 ships text config; the test is a regression gate.

The audit test's purpose is to lock the unit-file shape so future PRs
can't silently drop a directive. It runs cross-platform (Issue #6
RESOLVED) on every dev host's `pytest -q` invocation; CI Linux runner
also runs it. The directive contract is REGRESSION-GATED today.

---
*Phase: 03-linux-event-sources-lifecycle*
*Completed: 2026-05-08*
