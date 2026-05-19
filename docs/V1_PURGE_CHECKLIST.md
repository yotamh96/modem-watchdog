# v1 purge checklist — per-box operator verification

| Field        | Value                                    |
| ------------ | ---------------------------------------- |
| Created      | 2026-05-19                               |
| Context      | [ADR-0014](adr/0014-v1-retired-pivot.md) |
| Applies to   | Every Jetson box after v2 deployment     |

Run this checklist on each box after v2 has been running cleanly for at
least 7 days. All checks must pass before the box is considered fully
decommissioned from v1.

---

## 1. Verify no v1 scripts remain at /usr/local/bin/

```bash
for script in diag.sh recovery.sh auto_profile.sh zao_reset_line.sh spark-modem-watchdog.sh; do
  if [ -f "/usr/local/bin/$script" ]; then
    echo "FAIL: /usr/local/bin/$script still present"
  else
    echo "OK:   /usr/local/bin/$script removed"
  fi
done
```

If any script is still present, remove it:

```bash
sudo rm -f /usr/local/bin/{diag.sh,recovery.sh,auto_profile.sh,zao_reset_line.sh,spark-modem-watchdog.sh}
```

## 2. Verify no v1 cron entries

```bash
sudo crontab -l 2>/dev/null | grep -E 'diag\.sh|recovery\.sh|auto_profile\.sh|zao_reset_line\.sh|spark-modem-watchdog\.sh'
```

Expected output: empty (no matches). If any entries appear, remove them:

```bash
sudo crontab -e
# Delete lines referencing v1 scripts, then save.
```

Also check system-wide cron directories:

```bash
grep -rl 'diag\.sh\|recovery\.sh\|auto_profile\.sh\|zao_reset_line\.sh\|spark-modem-watchdog\.sh' \
  /etc/cron.d/ /etc/cron.daily/ /etc/cron.hourly/ 2>/dev/null
```

Expected output: empty. Remove any matching files.

## 3. Verify no v1 systemd units

```bash
systemctl list-unit-files | grep -i 'modem.*watchdog\|modem.*diag\|modem.*recovery'
```

Expected output: only `spark-modem-watchdog.service` (the v2 unit).

If a v1 timer or service is found:

```bash
sudo systemctl disable --now <unit-name>
sudo rm -f /etc/systemd/system/<unit-name>
sudo systemctl daemon-reload
```

## 4. Verify no stale v1 state files

v1 stored state as `KEY=VALUE` text files. Check the common locations:

```bash
for path in \
  /var/lib/spark-modem-watchdog/*.state \
  /var/lib/spark-modem-watchdog/*.txt \
  /tmp/modem_diag_* \
  /tmp/modem_recovery_*; do
  if ls $path 2>/dev/null; then
    echo "FAIL: stale v1 state file(s) found at $path"
  fi
done
```

v2 state files are JSON (`*.json`) under `/var/lib/spark-modem-watchdog/state/`.
Remove any `.state` or `.txt` files that are not part of v2:

```bash
sudo rm -f /var/lib/spark-modem-watchdog/*.state /var/lib/spark-modem-watchdog/*.txt
```

## 5. Verify v2 is running and healthy

```bash
sudo systemctl is-active spark-modem-watchdog.service
# Expected: active

sudo spark-modem status
# Expected: all modems in healthy or recovering state; no exhausted modems.
```

## 6. Sign-off

Record the box hostname, date, and operator name after all checks pass:

```
Box:      ____________________
Date:     ____________________
Operator: ____________________
All checks passed: [ ] Yes
```
