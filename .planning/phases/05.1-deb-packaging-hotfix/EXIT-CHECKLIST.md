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

## Annotation — Initial deploy walk 2026-05-12 (Phases 05.1 → 05.5 hotfix chain)

This template stays a template — the rows above remain for the on-site
engineer to fill at the eventual real Phase 05.1 exit. This annotation
records what was *actually* observed during the first attempted deploy
walk on 2026-05-12, which surfaced a chain of bugs that required
Phases 05.1, 05.2, 05.3, 05.4, and 05.5 to all complete before the
EXIT bar could even be attempted in earnest.

**Five sequential bugs caught at deploy time:**

| # | Bug class | Surface error | Fix landed in |
|---|-----------|---------------|---------------|
| 1 | `spark_modem` not on sys.path inside bundled venv | postinst smoke `ModuleNotFoundError` (well actually caught at .deb build time) | Phase 05.1 (3 hotfix chain: setuptools install, __pycache__ scrub, shim shebang sed) |
| 2 | Daemon `_production_main` used CLI laptop-sandbox factory | `OSError: [Errno 30] Read-only file system: '/tmp/spark-modem-cli'` against `ProtectSystem=strict` | Phase 05.2 |
| 3 | libqmi version regex required `libqmi-glib X.Y.Z` footer absent from JetPack 1.30.4 | `qmicli --version stdout did not match libqmi-glib regex` | Phase 05.3 |
| 4 | `dms_get_revision` parser required plural `Device revisions retrieved` header | `dms_get_revision returned QmiError: no revisions block in stdout` | Phase 05.4 |
| 5 | Firmware probe single-shot against qmi-proxy CID race with Zao | Same `no revisions block in stdout` (parser correct but qmicli failing upstream) | Phase 05.5 (3-attempt retry with stderr capture) |

**After all five hotfixes, the deploy walk reached:**

- Step 1 (CI build) — PASS for every iteration of the hotfix chain
- Step 2 (dpkg -i) — PASS from .deb gite49dc7b onward
- Step 3 (operator HMAC) — PASS (`openssl rand -hex 32` + 0600 root:root)
- Step 4 (systemctl start exit 0) — PASS; both ExecStartPre + ExecStart return 0
- Step 5 (is-active) — **NOT PASS**: systemd reports `Result: 'protocol'`
  because the daemon's main process exits 0 cleanly without sending
  `sd_notify READY=1`
- Steps 6 - 9 — NOT REACHABLE pending step 5

**Root cause of step 5 failure:** `src/spark_modem/daemon/main.py` lines
261-306 — Plan 03-09 left a documented placeholder in `_production_main`
where the production TaskGroup + cycle loop + sd_notify wiring was
supposed to land. The placeholder returns 0 immediately after acquiring
the PID lock. Plan 03-09 was marked "completed approved-with-deferral"
but only the lifecycle scaffold (preflight, PID lock, sd_notify
wrapper, sigterm handler modules) landed — the actual integration into
the production main was deferred and never completed.

**Tracked as:** Phase 05.6 (production-main-loop wiring). The Phase
05.1 EXIT bar above remains the real exit gate; it cannot be met
until Phase 05.6 lands.

**L-04 verdict observed (CI V-02 + bench):** systemd 245 emits a
WARN on `LoadCredential=` (silent-ignore branch). The L-02 code-side
fallback handles it; no drop-in override needed.

---

*Phase 05.1: deb-packaging-hotfix*
*Template authored by Plan 05.1-04; engineer-filled at Phase 05.1 exit.*
*Annotation added 2026-05-12 after the hotfix-chain deploy walk.*
