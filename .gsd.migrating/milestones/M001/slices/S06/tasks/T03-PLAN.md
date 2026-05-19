# T03: 05.1-deb-packaging-hotfix 03

**Slice:** S06 — **Milestone:** M001

## Description

Repoint the systemd unit file's two ExecStart* paths from the never-existed
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

## Must-Haves

- [ ] "debian/spark-modem-watchdog.service ExecStart references /opt/spark-modem-watchdog/python/bin/spark-modem-watchdog (not /opt/spark-modem-watchdog/bin/spark-modem-watchdog)"
- [ ] "debian/spark-modem-watchdog.service ExecStartPre 'config-check' references /opt/spark-modem-watchdog/python/bin/spark-modem (not /opt/spark-modem-watchdog/bin/spark-modem)"
- [ ] "debian/spark-modem-watchdog.service still contains LoadCredential=spark-modem-watchdog.hmac-secret:/etc/spark-modem-watchdog/hmac-secret (L-01 preserved)"
- [ ] "Every other directive in the service unit is unchanged (U-01..U-05 hardening intact)"

## Files

- `debian/spark-modem-watchdog.service`
