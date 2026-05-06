# Migration plan — v1 → v2

| Field         | Value                  |
| ------------- | ---------------------- |
| Status        | Draft                  |
| Owner         | TBD (modem platform)   |
| Last updated  | 2026-05-05             |

This document plans the cutover from the v1 bash toolchain to the v2
daemon. Risk-tolerance is conservative: v1 currently keeps a real
fleet online, so v2 must prove itself before it replaces v1.

---

## 1. Phasing summary

| Phase | What                                                | Duration       | Exit criterion                                                 |
| ----- | --------------------------------------------------- | -------------- | -------------------------------------------------------------- |
| 0     | Build, ship `.deb`, no boxes touched.              | week 0          | `.deb` lints clean; HIL passes.                                |
| 1     | Single bench Jetson, v2 in dry-run alongside v1.   | 1 week          | One full week of `events.jsonl` shows v2's plans match v1's actions on healthy modems; v2 plans are equal-or-safer on faults. |
| 2     | One field box, v2 in dry-run alongside v1.         | 2 weeks         | No false-positive plans (planned action on a healthy line) over 2 weeks. |
| 3     | One field box, v2 active, v1 disabled.             | 2 weeks         | Per-modem availability ≥ baseline; no incident attributable to v2. |
| 4     | 10 % of fleet (canary).                             | 2 weeks         | Same as Phase 3, fleet-wide aggregates.                        |
| 5     | 100 % of fleet.                                     | rolling         | Per-site cutover with rollback button.                         |
| 6     | v1 packages removed from boxes; scripts archived.   | one-shot        | Confirmed nothing references the v1 paths.                     |

Total wall time, optimistic: 6–8 weeks. Pad for at least 2 unexpected
issues per phase.

## 2. Phase 0 — Build and lab validation

Before any box is touched:

- `.deb` for `arm64` builds in CI.
- HIL job (`tests/hil/`) runs against a real bench Jetson with 4
  modems and passes the full scenario list:
  - Boot and reach Healthy.
  - SIM swap detected.
  - SIM `app_state_detected` resolved by `soft_reset`.
  - `not_registered_searching` resolved by `modem_reset` after one
    `soft_reset`.
  - Three-modem QMI hang triggers `driver_reset`.
  - RF event keeps the daemon out of destructive resets.
- v2 dry-run on captured v1 logs (replay traces) shows policy choices
  consistent with v1 on at least 1000 historical cycles.
- Documentation (this set of docs) reviewed and frozen at the
  current branch's commit.

**Go/no-go for phase 1:** all of the above plus a release tag.

## 3. Phase 1 — Bench dry-run alongside v1

Setup on the bench Jetson:

```bash
# v1 stays running as it is.
systemctl status spark-modem-watchdog.service     # v1 (the bash one)

# v2 installed but in dry-run; uses different state and log dirs.
sudo apt install /tmp/spark-modem-watchdog_2.0.0_arm64.deb

sudo mkdir -p /etc/spark-modem-watchdog/conf.d
sudo tee /etc/spark-modem-watchdog/conf.d/99-shadow.yaml <<'EOF'
# Shadow mode: observe and plan, but never act.
dry_run: true
state_dir: /var/lib/spark-modem-watchdog-v2
event_log_path: /var/log/spark-modem-watchdog-v2/events.jsonl
metrics_socket: /run/spark-modem-watchdog-v2/metrics.sock
EOF

sudo systemctl edit spark-modem-watchdog.service
# [Service]
# Environment=SPARK_MODEM_DRY_RUN=true
# (unit name conflict avoided because v1 uses the same name; we
# rename v2's unit to spark-modem-watchdog-v2.service in this phase.)

sudo systemctl daemon-reload
sudo systemctl enable --now spark-modem-watchdog-v2.service
```

In phase 1 the v1 daemon retains exclusive ownership of state/logs at
the canonical paths. v2 writes only to its `-v2` shadow paths.

For seven days, compare v1 and v2:

```bash
# On any cycle, do v1 and v2 see the same issues?
diff \
  <(jq -c '.issues[] | {who: .who, category: .category, detail: .detail}' /var/lib/spark-modem-watchdog/last_diag.json | sort) \
  <(jq -c '.issues[] | {modem: .who.device, category: .category, detail: .detail}' /var/lib/spark-modem-watchdog-v2/last_diag.json | sort)
```

A small comparator tool in `tools/compare_v1_v2.py` runs this every
hour and writes a daily report. The report goes to NOC.

**Go/no-go for phase 2:** ≥ 99 % agreement on issues; v2 plans never
mark a healthy line for action; any disagreement is documented and
either bug-fixed or accepted with rationale.

## 4. Phase 2 — Field box, dry-run

Pick one field box with the most stable modems (low historical
recovery activity) and an attentive on-site contact. Repeat phase 1
in production:

- v1 active.
- v2 in shadow paths, dry-run.
- Daily report compares v1's actions to v2's plans.

Specifically watch for:

- v2 wanting to act on lines v1 considers Zao-active (would mean a
  disagreement on Zao log parsing — a major issue per ADR-0003).
- v2 wanting `driver_reset` more often than v1 (would suggest the
  signal-gate fraction is too loose).
- v2 missing issues v1 catches (would suggest a regression in the
  observer).

**Go/no-go for phase 3:** at least one full week of green daily
reports; on-site engineer comfortable with the daemon's behaviour.

## 5. Phase 3 — Field box, v2 live

Cutover steps:

```bash
# 1) Capture a baseline.
sudo spark-modem ctl support-bundle --out=/tmp/sb-pre-v2.tgz

# 2) Stop and disable v1.
sudo systemctl disable --now spark-modem-watchdog.service        # v1
sudo systemctl mask spark-modem-watchdog.service                  # prevent accidental start

# 3) Move v2 to the canonical paths.
sudo systemctl stop spark-modem-watchdog-v2.service
sudo rm /etc/spark-modem-watchdog/conf.d/99-shadow.yaml
# State/log dirs revert to /var/lib/spark-modem-watchdog/ etc.

# 4) Start v2 live.
sudo systemctl enable --now spark-modem-watchdog.service          # this is now v2's unit
sudo spark-modem status

# 5) Watch for an hour.
sudo tail -f /var/log/spark-modem-watchdog/events.jsonl | jq .
```

### Rollback (within phase 3)

```bash
# 1) Stop v2.
sudo systemctl stop spark-modem-watchdog.service

# 2) Restore v1.
sudo systemctl unmask spark-modem-watchdog.service        # if previously masked
sudo apt install ./spark-modem-watchdog-v1_1.0.0_all.deb  # v1 packaged for emergency reinstall
sudo systemctl enable --now spark-modem-watchdog.service

# 3) Capture a support bundle from the v2 incident.
sudo cp -a /var/lib/spark-modem-watchdog /var/lib/spark-modem-watchdog.v2-rollback-$(date +%F)
```

**Go/no-go for phase 4:** two clean weeks; per-modem availability
within ±0.2 % of the historical baseline.

## 6. Phase 4 — Canary 10 %

Cut over 10 % of the fleet using the fleet management tool. Monitor:

- Aggregate `spark_modem_state{state="exhausted"}` ≤ baseline.
- Aggregate destructive-reset rate ≤ baseline + 10 %.
- Aggregate session-disconnect rate ≤ baseline + 10 %.
- Zero daemon crashes in any 24 h window.

Rollback for a single canary box is the phase-3 procedure. Rollback
for the canary cohort is a fleet-management push of the v1 package.

## 7. Phase 5 — Fleet rollout

Roll forward 10 % per day until the fleet is on v2. The fleet-
management tool gates each batch on the previous batch's health
metrics.

Cutover is a no-touch operation per box (the deb upgrade replaces
the unit and restarts).

## 8. Phase 6 — v1 decommission

After 30 days of clean v2 operation:

- Remove v1 packages from all boxes (`apt purge spark-modem-watchdog-v1`).
- Move the v1 source scripts to `archive/v1/` in the repo with a
  README pointing at v2.
- Update the CLAUDE.md to point at the v2 directory.
- Close the v1 issue tracker label.

## 9. Data migration

v2 does not read v1 state files. There is nothing to migrate:

- Per-modem state in v1 is `KEY=VALUE` text; in v2 it's typed JSON.
  v2 starts fresh on each box (acceptable: v2's state is observable
  history; nothing structural is lost).
- `sim_identity.json` from v1 has the same logical content as v2's
  `identity.json`. The post-install hook MAY copy v1's file to a
  `.bak` in `/var/lib/spark-modem-watchdog/`, but does not parse it.
  v2 re-reads ICCID/IMSI on first cycle.
- `last_diag.json` from v1 is overwritten by v2 (different schema;
  no rollback to v1 needed once v2 is live, because v1 produces a
  fresh one in seconds).

## 10. Risks

| Risk                                                          | Mitigation                                                                       |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| v2's policy disagrees subtly with v1, masked by dry-run agreement on healthy cycles only. | Phase 2 explicitly looks at *fault* cycles; HIL injects faults. |
| `qmicli` output format on a deployed box differs from the lab. | qmi parser tests run on real captures from each fleet revision; `qmi/parsers.py` raises a structured error on unknown shapes. |
| Field site has a Zao SDK older than tested.                   | Daemon refuses to start with a structured error if Zao log format probe fails; phase-1 inventory across the fleet identifies any old SDKs. |
| Rollback to v1 requires the v1 deb in hand.                   | Build `spark-modem-watchdog-v1_1.0.0_all.deb` from the existing scripts in phase 0; mirror to the apt repo. |
| State file schema-version mismatch on package downgrade.       | v2 daemon refuses to load future schemas with a structured error. Operator runs `spark-modem ctl reset-state --all` before downgrade. |
| New runtime dep (Python 3.11 venv) breaks old fleet boxes.    | venv is bundled in the `.deb`; no system Python upgrade. |

## 11. Communication

- Phase 0–2: internal eng + NOC awareness only.
- Phase 3: a known field site receives an email + Slack with the
  cutover schedule, rollback contact, and what to expect.
- Phase 4: fleet-wide ops notice via fleet management tool's
  changelog.
- Phase 5: same; with daily progress.
- Phase 6: post-mortem-style summary, regardless of whether anything
  went wrong. Include metrics: MTTR before/after, false-positive
  reset rate before/after, daemon CPU/RSS, support-ticket count.
