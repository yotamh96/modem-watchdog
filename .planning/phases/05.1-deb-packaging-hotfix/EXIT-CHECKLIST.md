# Phase 05.1 EXIT Checklist — deb-packaging-hotfix

**Status:** Template — fill at Phase 05.1 exit before unblocking Plan 05-08 Task 2 (bench soak window).

> **Forcing function:** Phase 05.1 EXIT bar (V-03 in
> `.planning/phases/05.1-deb-packaging-hotfix/05.1-CONTEXT.md`):
> bench Jetson runs the new `.deb`, daemon reaches `active (running)` with
> `sd_notify READY=1`, every row below is PASS, this file is committed.

| Field                       | Value                                |
| --------------------------- | ------------------------------------ |
| Authored by                 | _on-site engineer name_              |
| Bench Jetson box-id         | _e.g. bench-jetson-01_               |
| .deb commit SHA             | _short-sha (from merged hotfix branch)_ |
| .deb build run URL          | _GitHub Actions URL_                 |
| Install timestamp (ISO)     | _YYYY-MM-DDTHH:MM:SSZ_               |
| EXIT timestamp (ISO)        | _YYYY-MM-DDTHH:MM:SSZ_               |

---

## V-03 Exit Gates (operator-filled)

Every row must be PASS for Phase 05.1 EXIT. Mark each Status cell ☐ PASS
or ☐ FAIL; fill Observed with the literal command output (truncate to a
representative excerpt if multi-line — see Notes).

| # | Step | Status | Command | Expected | Observed | Notes |
|---|------|--------|---------|----------|----------|-------|
| 1 | `.deb` built from merged hotfix branch | ☐ PASS / ☐ FAIL | `gh run view <run-id>` | green build; artifact `spark-modem-watchdog-arm64-deb` uploaded | _filled_ | |
| 2 | scp + `dpkg -i` returns 0 | ☐ PASS / ☐ FAIL | `scp spark-modem-watchdog_*_arm64.deb bench-jetson:/tmp/ && ssh bench-jetson 'sudo dpkg -i /tmp/spark-modem-watchdog_*_arm64.deb'` | dpkg exits 0; postinst smoke green; placeholder HMAC secret written at /etc/spark-modem-watchdog/hmac-secret (0600 root:root) | _filled_ | |
| 3 | Operator provisions `/etc/spark-modem-watchdog/hmac-secret` | ☐ PASS / ☐ FAIL | `head -c 32 /dev/urandom \| base64 \| sudo install -m 0600 -o root -g root /dev/stdin /etc/spark-modem-watchdog/hmac-secret` | file overwritten; `sudo stat -c '%a %u:%g' /etc/spark-modem-watchdog/hmac-secret` returns `600 0:0` | _filled_ | non-automatable (L-03) |
| 4 | `systemctl start spark-modem-watchdog.service` returns 0 | ☐ PASS / ☐ FAIL | `sudo systemctl start spark-modem-watchdog.service && echo OK` | exit 0; ExecStartPre smoke + config-check both green; ExecStart fires | _filled_ | |
| 5 | `systemctl is-active` reports `active` | ☐ PASS / ☐ FAIL | `systemctl is-active spark-modem-watchdog.service` | `active` | _filled_ | sd_notify READY=1 already fired |
| 6 | `journalctl` shows `Started ...` + no ERROR/CRITICAL | ☐ PASS / ☐ FAIL | `journalctl -u spark-modem-watchdog.service --since='5 min ago' -p err` | empty / no ERROR or CRITICAL lines; `Started ...` line present in -p info | _filled_ | inspect for warnings about LoadCredential= on systemd 245 (L-04 may surface a journalctl warning here per CONTEXT.md L-04 third branch) |
| 7 | `/run/spark-modem-watchdog/lock` present + owned by root | ☐ PASS / ☐ FAIL | `sudo stat -c '%n %a %u:%g' /run/spark-modem-watchdog/lock` | `/run/spark-modem-watchdog/lock 600 0:0` (or 0640; matches RuntimeDirectoryMode=0750) | _filled_ | |
| 8 | `/run/spark-modem-watchdog/metrics.sock` scrape | ☐ PASS / ☐ FAIL | `sudo curl --unix-socket /run/spark-modem-watchdog/metrics.sock http://x/metrics \| head -20` | valid Prometheus text containing `modem_state_value`, `cycle_duration_seconds`, `actions_total` | _filled_ | |
| 9 | Daemon reaches Healthy on all 4 modems within 60s (NFR-13) | ☐ PASS / ☐ FAIL | `sudo cat /var/lib/spark-modem-watchdog/status.json \| jq '.modems[] \| select(.state != "healthy") \| .modem'` after ≤60s | jq output is empty (every modem state == "healthy") | _filled_ | M5 readiness; verifies the end-to-end production path |

---

## Free-text rationale (≤500 words)

> Engineer's narrative: what was observed, anything that needed a retry,
> anything the next plan-phase should know. Especially: L-04 verdict
> (silent-ignore vs hard-fail vs warning-with-degraded — see step 6
> journalctl observation).

_engineer fills here_

---

## Phase 05.1 EXIT approval

All three must hold for Phase 05.1 EXIT:

- ☐ Every row in the V-03 gate table above is PASS
- ☐ The committed `.deb` matches the merged hotfix branch (commit SHA in header table)
- ☐ Free-text rationale captures the L-04 verdict so future plans can act on it

**Approved by:** _engineer signature / commit author_
**Date (ISO):** _YYYY-MM-DD_

---

*Phase 05.1: deb-packaging-hotfix*
*Template authored by Plan 05.1-04; engineer-filled at Phase 05.1 exit.*
