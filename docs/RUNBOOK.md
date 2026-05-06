# Runbook — spark-modem-watchdog v2

| Field         | Value                  |
| ------------- | ---------------------- |
| Status        | Draft                  |
| Owner         | TBD (modem platform)   |
| Audience      | Site technicians, NOC, on-call engineers |
| Last updated  | 2026-05-06             |

This runbook covers daily operations: install, observe, diagnose,
recover. It assumes a Jetson Orin NX with the `.deb` package installed
and Zao already running. For dev/test workflows see
[TEST_STRATEGY.md](TEST_STRATEGY.md).

---

## 1. First install

```bash
# 1) Copy the .deb to the box
scp spark-modem-watchdog_2.0.0_arm64.deb nvidia@<jetson>:/tmp/

# 2) Install (root)
ssh nvidia@<jetson>
sudo apt install -y /tmp/spark-modem-watchdog_2.0.0_arm64.deb

# 3) Verify
sudo systemctl status spark-modem-watchdog.service
sudo spark-modem ctl version
```

The post-install script:

- Creates `/var/lib/spark-modem-watchdog/`, `/var/log/spark-modem-watchdog/`,
  `/run/spark-modem-watchdog/` with mode 0750, owner root.
- Installs `spark-modem-watchdog.service` and a `logrotate` snippet.
- Installs the udev rule that disables USB autosuspend on Sierra
  modems (so that fix is permanent, not per-cycle).
- Validates `/etc/spark-modem-watchdog/config.yaml` with
  `spark-modem ctl config-check`. If validation fails, the install
  refuses to enable the service; the operator must fix config first.
- Starts the service unless `--no-start` was passed via debconf.

The first cycle waits `cycle.startup_delay_seconds` (default 30) for
Zao to settle.

## 2. Day-to-day commands

### Status at a glance

```bash
spark-modem status
```

Prints a four-line summary, one per modem:

```
spark-modem-watchdog v2.0.0 — uptime 4d 7h
Cycle 14502 (last 1.34s)  Zao log age 0.7s

  line 1  cdc-wdm0  HEALTHY     ipv4=10.69.92.156/29
  line 2  cdc-wdm1  HEALTHY     ipv4=10.88.115.56/28
  line 3  cdc-wdm2  HEALTHY     ipv4=10.10.4.42/29
  line 4  cdc-wdm3  RECOVERING  level=soft  cause=registration/not_registered_searching  next eligible 13:43:12
```

`spark-modem status --json` returns the full `status.json` from
[SCHEMA.md § status.json](SCHEMA.md#4-statusjson).

### Live event feed

```bash
sudo tail -f /var/log/spark-modem-watchdog/events.jsonl | jq .
```

For human-readable journal:

```bash
sudo journalctl -u spark-modem-watchdog.service -f
```

### Manual diag (no actions taken)

```bash
sudo spark-modem diag             # human
sudo spark-modem diag --json      # machine, same shape as the daemon writes
sudo spark-modem diag --quick     # skip slow per-modem QMI deep checks
sudo spark-modem diag --device=cdc-wdm0
```

### Manual recovery in dry-run

```bash
sudo spark-modem diag --json | sudo spark-modem recovery --from-stdin --dry-run
sudo spark-modem recovery --diag-fixture=/var/lib/spark-modem-watchdog/last_diag.json --dry-run
```

This is what to do when you want to know "what would the daemon do
if I let it"?

### Force a one-shot reset

```bash
sudo spark-modem reset 4 --soft       # SIM cycle (~5s)
sudo spark-modem reset 4 --modem      # firmware reset (~30-60s)
sudo spark-modem reset 4 --usb        # USB rebind (~10-20s)
sudo spark-modem reset --all --driver # global qmi_wwan reload — ALL LINES DOWN
```

The watchdog observes these (via udev / link state events) and
treats them as transient. **It will not double up** if you reset
manually while the daemon is running, because manual resets are
captured as `manual_action` events in `events.jsonl`.

## 3. Common problems and fixes

### "All four modems show DEGRADED right after boot"

Expected for the first 30 s (configurable startup delay). After that:

```bash
# Is Zao up?
systemctl is-active zao-infra-ctrl.service zao-remote-endpoint.service

# Has the Zao log been written recently?
ls -la /var/log/zao-remote-endpoint.log

# Daemon's view of Zao log age:
spark-modem status --json | jq '.zao'
```

If Zao is down, fix Zao first. The watchdog will log
`zao_unit_inactive` and `zao_log_stale` and refuse to take
destructive actions.

### "One line is stuck in RECOVERING for 30 minutes"

Look at the per-modem state and counters:

```bash
sudo cat /var/lib/spark-modem-watchdog/state/cdc-wdm3.json | jq .
sudo grep '"modem":"cdc-wdm3"' /var/log/spark-modem-watchdog/events.jsonl \
    | tail -50 | jq .
```

Possible causes:

- **Signal-gated**: the modem is in `rf_blocked`. Confirm with
  `spark-modem diag --json | jq '.modems[] | select(.device=="cdc-wdm3").signal'`.
  If RSRP is below -110, the radio cannot decode the cell. No software
  action will help. Move the antenna or wait for the RF event to pass.
- **Backoff sticking**: the daemon ran the action recently and is
  waiting. Check `next_action_eligible_at_iso` in `status.json`.
- **Carrier denied**: `registration/denied` is `skip:carrier_denied`
  by policy. Check the IMEI/SIM permissions with the carrier.

### "A line keeps being marked EXHAUSTED then RECOVERING then EXHAUSTED"

This means a real recurring fault. The decay-on-healthy logic
(§ 3.3 of [RECOVERY_SPEC.md](RECOVERY_SPEC.md)) means we only re-enter
exhausted when the modem actually fails again after recovering. To
diagnose:

```bash
# What issues keep coming back?
sudo grep '"modem":"cdc-wdm3"' /var/log/spark-modem-watchdog/events.jsonl \
    | jq -r 'select(.event=="issue_observed") | .category + "/" + .detail' \
    | sort | uniq -c | sort -rn
```

If the dominant issue is `registration/searching`, this is usually
SIM, antenna, or RF environment. Take to NOC.

### "Watchdog isn't running"

```bash
systemctl status spark-modem-watchdog.service
journalctl -u spark-modem-watchdog.service --since '5 minutes ago'
```

Common causes:

- Config validation failed: look for `config_invalid` in the
  journal. Run `sudo spark-modem ctl config-check` and fix the
  reported errors.
- `qmicli` removed or broken: `which qmicli; qmicli --version`.
- Disk full in `/var/lib`: `df -h /var`.
- Schema-version mismatch on a state file (after a downgrade): look
  for `schema_refused` events. Resolve with `spark-modem ctl
  reset-state --device=cdc-wdmN` (after capturing a support bundle).

### "Watchdog is making things worse"

Stop it and investigate:

```bash
sudo systemctl stop spark-modem-watchdog.service
sudo spark-modem diag
sudo spark-modem ctl support-bundle --out=/tmp/sb.tgz
# (Send the support bundle to NOC.)
```

Re-enable when ready:

```bash
sudo systemctl start spark-modem-watchdog.service
```

### "I want to disable recovery temporarily but keep observing"

Edit a drop-in to set dry-run:

```bash
sudo systemctl edit spark-modem-watchdog.service
# Add:
[Service]
Environment=SPARK_MODEM_DRY_RUN=true
# Save, exit.
sudo systemctl restart spark-modem-watchdog.service
```

The daemon will plan actions and log them as `dry_run=true` but not
execute. Status, events, and metrics remain accurate.

## 4. State surgery

These are last-resort operations when state has drifted from reality.

### Reset state for one modem

```bash
sudo spark-modem ctl reset-state --device=cdc-wdm3
```

Clears counters, resets the per-modem state file. The next cycle
re-observes from scratch.

### Reset all per-modem state

```bash
sudo spark-modem ctl reset-state --all
```

### Force reprovision (re-write APN even if it matches)

```bash
sudo spark-modem provision --device=cdc-wdm3 --force --restart-zao
```

### Re-import the carrier table

```bash
sudo spark-modem ctl reload
```

Rereads `/etc/spark-modem-watchdog/config.yaml`, `conf.d/*.yaml`,
and `share/carriers/*.yaml`. Validates; logs reload event; activates
new values for non-restart-only settings.

## 5. Support bundle

For an incident report:

```bash
sudo spark-modem ctl support-bundle --out=/tmp/sb-$(date +%F).tgz
```

The bundle contains:

- Last 200 events from `events.jsonl`
- Current `status.json`
- All `state/*.json` files
- `globals.json`, `identity.json`
- Output of `spark-modem diag --json`
- `journalctl -u spark-modem-watchdog --since '1 hour ago'`
- `dmesg --since '1 hour ago' | grep -iE 'qmi|sierra|cdc_wdm|usb'`
- Output of `lsusb`, `ip netns list`, `systemctl status zao-*`
- Hashes/sizes of the binary and config

The bundle is safe to share — it contains no SIM PIN/PUK and no
webhook secrets.

## 6. Uninstall

```bash
sudo apt remove spark-modem-watchdog               # keep state + logs
sudo apt purge spark-modem-watchdog                # also remove /var/lib + /var/log
```

`apt` does not auto-remove `libqmi-utils`, `usbutils`, `iproute2`,
`uhubctl` because they may be in use. Remove them with
`apt autoremove --purge` if you're sure.

## 7. Alerting playbook (NOC)

Webhook payloads are documented in [SCHEMA.md § 9](SCHEMA.md#9-webhook-payload).

| Transition / event                        | Severity | First action                                                         |
| ----------------------------------------- | -------- | -------------------------------------------------------------------- |
| `healthy -> degraded`                      | info     | Watch — no human action unless it persists.                          |
| `degraded -> recovering`                   | info     | None.                                                                |
| `recovering -> healthy`                    | info     | None (resolved).                                                     |
| `recovering -> exhausted`                  | warn     | Check signal trend; trigger ticket if persistent ≥ 1 h.              |
| `any -> rf_blocked`                        | warn     | Check whether all four lines are blocked (site-wide RF) or one (antenna). |
| `host: enumeration_overcurrent`            | critical | Hub PSU inadequate; site visit.                                      |
| `host: enumeration_address_fail`           | critical | USB power sag; site visit.                                           |
| `zao_log_stale (>5min)`                    | error    | Page Zao on-call.                                                    |

A "ticket if persistent" rule means the alert manager should de-dup:
fire when the state has been continuous for the full window, not
on every cycle.

## 8. Capacity and limits

- Daemon RSS budget: 80 MiB. Page when above 200 MiB.
- `events.jsonl` write rate steady-state: < 200 KiB/min. Page when
  above 5 MiB/min (suggests a tight error loop).
- Cycle duration P99: 10 s. Page when above 30 s.
- `/var/log/spark-modem-watchdog/` retention: 7 days, 100 MiB. After
  rotation, files are gzipped.

## 9. Things that look wrong but aren't

- **Modems with `zao_active=true` show all probe fields as `null`.**
  By design (FR-10, ADR-0003). Probe fields are populated only for
  inactive lines.
- **`spark-modem reset` records `manual_action` events but the daemon
  doesn't take action.** The daemon observes the resulting state via
  events, not via the reset command itself. It will react if the
  reset broke something.
- **An Exhausted modem becomes Healthy without a `state_transition`
  event for `recovering -> healthy`.** Possible after counter decay
  zeroes counters during a Healthy run; the transition is recorded
  but the modem may have been Healthy already. Inspect with
  `events.jsonl` filtered by modem.
- **`signal.sufficient = null`.** Means the modem was not on a serving
  cell at probe time. The daemon proceeds without RF gating; that is
  intentional.

## 10. Self-hosted CI runner setup (`spark`)

The `Build .deb (aarch64)` workflow runs on a self-hosted GitHub
Actions runner installed on a Jetson box (`runner name: spark`,
unprivileged user `nvidia`). The workflow assumes the build toolchain
is already on the host — it does **not** call `sudo apt-get install`
at job time, because the runner user has no passwordless sudo and a
non-interactive `sudo` will hard-fail with:

```
sudo: a terminal is required to read the password
```

### One-time host setup

Run these once per runner host, as a user with sudo:

```bash
# Build deps for the .deb pipeline
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  debhelper devscripts fakeroot dpkg-dev \
  curl ca-certificates

# Smoke-install step uses Docker. Make sure the runner user can
# run docker without sudo:
sudo usermod -aG docker nvidia
# Log the runner user out + back in (or restart the runner service)
# for the group change to take effect.
```

Verify:

```bash
dpkg -l debhelper devscripts fakeroot dpkg-dev curl ca-certificates \
  | tail -n +6   # every row should start with `ii`
sudo -u nvidia docker info >/dev/null && echo "docker ok"
```

### What the runner needs *besides* build tools

- `uv` — installed per-job by the workflow (`curl https://astral.sh/uv/install.sh | sh`).
  Lives under `~nvidia/.local/bin/`. No host action needed.
- Python 3.12 — `uv python install 3.12` per job. Cached under `~nvidia/.local/share/uv/`.
- The GitHub Actions runner agent itself, registered against
  `yotamh96/modem-watchdog` with labels `self-hosted, linux, ARM64`.

### When to re-do this

- New runner host (replacement Jetson, second runner for capacity).
- After a fresh OS reinstall on the existing host.
- When `build-deb.yml` adds a new host-level dependency (record it
  here at the same time as the workflow change).

### What this runner intentionally does *not* have

- No NOPASSWD sudo. Workflows that need root must either run inside
  a container (see the `Smoke-install in clean container` step in
  `build-deb.yml`) or be redesigned. We deliberately keep the runner
  user unprivileged so a compromised workflow cannot reconfigure
  the production Jetson.
