# Per-box cutover runbook — spark-modem-watchdog v2

| Field         | Value                  |
| ------------- | ---------------------- |
| Status        | Draft                  |
| Owner         | TBD (modem platform)   |
| Audience      | Site technicians, NOC  |
| Last updated  | 2026-05-19             |

Operator-facing step-by-step for cutting a single Jetson Orin NX box
over to the v2 daemon. v1 is already retired across the fleet — there
is no side-by-side period. See [ADR-0014](adr/0014-v1-retired-pivot.md)
for background.

Rollback at every step means downgrading to the previous v2 `.deb`
release. There is no v1 rollback path.

---

## Prerequisites

- SSH access to the target box (user `nvidia`, sudo-capable).
- The v2 `.deb` is available in the fleet apt repository (or copied
  to the box as a local `.deb` file).
- Zao services (`zao-infra-ctrl.service`, `zao-remote-endpoint.service`)
  are running and healthy.
- `/etc/spark-modem-watchdog/config.yaml` has been reviewed and matches
  the box's modem/SIM configuration.
- HMAC webhook secret is deployed via `LoadCredential=` or placed at
  `/etc/spark-modem-watchdog/hmac.key`.
- Prometheus scrape target is configured for the box's metrics socket
  (`/run/spark-modem-watchdog/metrics.sock`).
- Escalation contact: {{ESCALATION_CONTACT}} (replace before use).

**Expected total duration:** 5–10 minutes per box under normal conditions.

---

## Step 1 — Pre-flight checks

Verify box connectivity and readiness before touching the daemon.

```bash
# Confirm SSH connectivity.
ssh nvidia@<jetson> hostname

# Verify Zao is running.
ssh nvidia@<jetson> sudo systemctl is-active \
  zao-infra-ctrl.service zao-remote-endpoint.service

# Check all 4 USB modems are enumerated.
ssh nvidia@<jetson> lsusb | grep -c '1199:9091'
# Expected: 4

# Verify disk space (need ~50 MB for .deb + state).
ssh nvidia@<jetson> df -h /var /opt
```

**Duration:** ~1 minute.
**Abort if:** Zao is not active, fewer than 4 modems enumerated, or
disk is critically low.

---

## Step 2 — Install the v2 .deb

```bash
# From fleet apt repo (preferred):
sudo apt update
sudo apt install spark-modem-watchdog

# OR from local .deb:
sudo apt install /tmp/spark-modem-watchdog_2.x.x_arm64.deb
```

The post-install script creates state/log directories, installs the
systemd unit, udev rules, and validates `config.yaml`. If validation
fails, the install refuses to enable the service — fix config first.

**Duration:** ~1 minute.
**Abort if:** config validation fails (fix config, re-run install).

---

## Step 3 — Enable and start the service

```bash
sudo systemctl enable --now spark-modem-watchdog.service
```

The daemon starts, waits `cycle.startup_delay_seconds` (default 30 s)
for Zao to settle, then begins its first diagnostic cycle.

**Duration:** ~30 seconds for service start; first cycle completes
within the startup delay + one cycle interval.

---

## Step 4 — Verify modem health

Wait up to 60 seconds, then confirm all 4 modems reach `Healthy`.

```bash
# Human-readable status:
sudo spark-modem status

# Machine-readable (for scripting):
sudo spark-modem status --json | jq '.modems[] | {line, state}'
```

All four modems should show `HEALTHY`. A modem in `RECOVERING` is
acceptable if it transitions to `HEALTHY` within 90 seconds. A modem
in `DEGRADED` during the startup delay is expected.

**Duration:** ≤60 seconds.
**Abort if:** any modem is stuck in `EXHAUSTED` or `DEGRADED` after
90 seconds. Investigate before proceeding — see Troubleshooting below.

---

## Step 5 — Run post-cutover validation

```bash
sudo python3 /opt/spark-modem-watchdog/tools/validate_cutover.py
```

The script runs 7 automated checks (service active, modems healthy,
state files present, metrics socket responding, event log populated,
Prometheus scrape OK, HMAC secret configured). Output is structured
JSON with a per-check pass/fail verdict.

- Exit code 0: all green — proceed.
- Exit code 1: soft failure — a non-critical check failed; review and
  decide whether to proceed or fix.
- Exit code 2: hard failure — daemon not running or modems unhealthy;
  do not proceed.

**Duration:** ~5 seconds.
**Abort if:** exit code 2. Fix the issue, re-run the script.

---

## Step 6 — Monitor observability

Verify Prometheus scrape is flowing and check the Grafana dashboard.

```bash
# Confirm metrics socket exists.
ls -la /run/spark-modem-watchdog/metrics.sock

# Spot-check a metric (from the box itself):
curl --unix-socket /run/spark-modem-watchdog/metrics.sock \
  http://localhost/metrics | grep modem_state_value

# Watch the live event feed for 2–3 cycles:
sudo tail -f /var/log/spark-modem-watchdog/events.jsonl | jq .

# Or via journalctl:
sudo journalctl -u spark-modem-watchdog.service -f
```

On the monitoring side:

- Confirm the box appears as a Prometheus target (Status → Targets).
- Check the Grafana modem dashboard shows data for this box.
- Verify `modem_state_value` is not 4 (exhausted) for any modem.

**Duration:** 2–5 minutes of observation.

---

## Step 7 — Rollback (if needed)

If the cutover must be reverted, downgrade to the previous v2 `.deb`.
There is no v1 rollback — see [ADR-0014](adr/0014-v1-retired-pivot.md).

```bash
# 1) Downgrade to the previous v2 release.
sudo apt install spark-modem-watchdog=<previous-version>

# 2) Verify the service restarted with the older version.
sudo spark-modem status

# 3) Capture a support bundle for incident review.
sudo spark-modem ctl support-bundle --out=/tmp/sb-rollback-$(date +%F).tgz
```

The apt repository retains the last 3 `.deb` releases. List available
versions with `apt list -a spark-modem-watchdog`.

---

## Troubleshooting

### Modem stuck in DEGRADED after startup delay

```bash
# Check Zao status — Zao must be running for bonding detection.
sudo systemctl is-active zao-infra-ctrl.service zao-remote-endpoint.service

# Check Zao log freshness:
sudo spark-modem status --json | jq '.zao'
```

If Zao is down, fix Zao first. The watchdog will not take destructive
actions without a valid Zao log.

### Modem stuck in RECOVERING

```bash
# Check if signal-gated (rf_blocked):
sudo spark-modem diag --json | jq '.modems[] | {device, signal}'

# Check backoff timer:
sudo spark-modem status --json | jq '.modems[] | select(.state=="recovering")'
```

If RSRP is below −110 dBm, the radio environment is the issue — no
software action will help.

### Config validation fails during install

```bash
sudo spark-modem ctl config-check
```

Fix the reported errors in `/etc/spark-modem-watchdog/config.yaml` and
re-run the install.

### Validate script reports hard failure

```bash
# Re-check the service:
sudo systemctl status spark-modem-watchdog.service

# Check the journal for errors:
sudo journalctl -u spark-modem-watchdog.service --since '5 minutes ago'
```

Common causes: missing `qmicli`, disk full, schema-version mismatch
on leftover state files. See [RUNBOOK.md](RUNBOOK.md) § 3 for details.

### Need to disable recovery temporarily

```bash
sudo systemctl edit spark-modem-watchdog.service
# Add:
#   [Service]
#   Environment=SPARK_MODEM_DRY_RUN=true
sudo systemctl restart spark-modem-watchdog.service
```

The daemon logs planned actions as `dry_run=true` but does not execute
them. Re-enable by removing the drop-in and restarting.

---

## Post-cutover checklist

- [ ] All 4 modems showing `HEALTHY` in `spark-modem status`.
- [ ] `validate_cutover.py` exited with code 0.
- [ ] Prometheus target is UP and scraping metrics.
- [ ] Grafana dashboard shows data for this box.
- [ ] Event log (`events.jsonl`) is being written.
- [ ] No `modem_state_value == 4` (exhausted) in first 30 minutes.
- [ ] Escalation contact confirmed and reachable.
