# T08: 03-linux-event-sources-lifecycle 08

**Slice:** S03 — **Milestone:** M001

## Description

Wave 3b — systemd unit hardening (U-01..U-05) + logrotate snippet (R-02)
+ unit-file-audit integration test that pins every directive.

Specifically:

  1. Edit `debian/spark-modem-watchdog.service` to apply U-01..U-05 in full
     (preallocated Phase 4 caps, StartLimit overrides, WatchdogSec=90s,
     RuntimeDirectoryPreserve=yes, ExecStartPre=config-check, drop
     PrivateMounts/PrivateTmp/PrivateDevices for /dev/kmsg compat).
  2. Write `debian/spark-modem-watchdog.logrotate` per R-02 verbatim
     (create mode, rotate 7, size 100M, EMPTY postrotate).
  3. Write `tests/integration/test_unit_file_audit.py` that parses the
     .service file as plain text and asserts every directive — cross-platform
     (no linux_only marker; pure file parse).

This plan was carved out of the original Plan 03-06 to keep that plan
focused on lifecycle modules + main.py rewrite. The systemd / logrotate
files have no source-code dependency on Plans 03-06/03-07, so this plan
runs in parallel with Plan 03-07 (no file overlap).

Output: 1 modified .service file + 1 new .logrotate file + 1 new
integration test file.

## Must-Haves

- [ ] "systemd unit ships U-01..U-05 directives in full (CONTEXT.md U-01..U-05)."
- [ ] "logrotate snippet ships in `create` mode with EMPTY postrotate (R-02; daemon detects rotation via asyncinotify)."
- [ ] "Unit-file-audit integration test parses the .service file and asserts every directive — runs cross-platform (no linux_only marker; pure file parse)."
- [ ] "Daemon runs as root with NoNewPrivileges=yes; CapabilityBoundingSet preallocates Phase 4 caps (NFR-30)."
- [ ] "WatchdogSec=90s ships in unit (Phase 4 HIL verifies actual fire under deliberate qmicli wedge)."

## Files

- `debian/spark-modem-watchdog.service`
- `debian/spark-modem-watchdog.logrotate`
- `tests/integration/test_unit_file_audit.py`
