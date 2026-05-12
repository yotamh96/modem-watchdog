---
phase: 05.2-daemon-startup-hotfix
verdict: PENDING_BENCH_DEPLOY
ci_verdict: PASS
ci_run: 25725010483
fix_commit: e49dc7b
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

## Bench Jetson evidence (PENDING — append below once available)

After `sudo apt install ./spark-modem-watchdog_2.0.0-0.gite49dc7b-1_arm64.deb`
on the bench Jetson with the operator-provisioned HMAC secret in place:

```
systemctl status spark-modem-watchdog --no-pager --lines=0
journalctl -u spark-modem-watchdog --since "30 sec ago" --no-pager | tail -40
```

Expected:
- `Active: active (running)`
- `sd_notify READY=1` event in the journal
- No `OSError: [Errno 30] Read-only file system: '/tmp/spark-modem-cli'`
- The daemon either steady-states or fails at a different (non-05.2) layer
  (Zao not running, modems not enumerated, rtnetlink, etc.) — those failure
  modes are outside Phase 05.2 scope.

## Verdict

- **CI:** PASS (run 25725010483, commit e49dc7b)
- **Bench Jetson:** PENDING (record outcome inline above when available;
  flip top-level `verdict: PENDING_BENCH_DEPLOY` to `PASS` or
  `PARTIAL_NEW_FAILURE_DIFFERENT_LAYER` accordingly)
