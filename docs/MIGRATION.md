# Migration plan — v2 deployment

| Field         | Value                  |
| ------------- | ---------------------- |
| Status        | Active                 |
| Owner         | TBD (modem platform)   |
| Last updated  | 2026-05-19             |

This document plans the rollout of the v2 daemon to the fleet. v1 (the
bash toolchain) is already retired across all boxes — there is no
side-by-side shadow period. See [ADR-0014](adr/0014-v1-retired-pivot.md)
for the decision record.

Rollback at every phase means downgrading to the previous v2 `.deb`
release (`apt install spark-modem-watchdog=<prev-version>`). The apt
repository retains the last 3 releases. There is no v1 package to fall
back to.

---

## 1. Phasing summary

| Phase | What                                                | Duration       | Exit criterion                                                 |
| ----- | --------------------------------------------------- | -------------- | -------------------------------------------------------------- |
| 0     | Build, ship `.deb`, no boxes touched.              | week 0          | `.deb` lints clean; HIL passes.                                |
| 1     | Single bench Jetson, v2 live.                      | 1 week          | All 4 modems reach Healthy within 60 s of daemon start; one full week of clean `events.jsonl` — no false-positive resets on healthy modems. |
| 2     | One field box, v2 live.                            | 2 weeks         | Per-modem availability ≥ baseline; no incident attributable to v2; no false-positive resets over 2 weeks. |
| 3     | 10 % of fleet (canary).                             | 2 weeks         | Fleet-wide health gates pass (see Phase 3 below).              |
| 4     | 100 % of fleet.                                     | rolling         | Per-site cutover with rollback gate.                           |
| 5     | v1 scripts archived; stale references removed.      | one-shot        | Confirmed nothing references the v1 paths.                     |

Total wall time, optimistic: 5–7 weeks. Pad for at least 2 unexpected
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
- v2 dry-run on captured historical logs (replay traces) shows policy
  choices consistent with expected outcomes on at least 1000 cycles.
- Documentation (this set of docs) reviewed and frozen at the
  current branch's commit.

**Go/no-go for phase 1:** all of the above plus a release tag.

## 3. Phase 1 — Bench Jetson, v2 live

Install and start v2 on the bench Jetson:

```bash
# Install the v2 .deb.
sudo apt install /tmp/spark-modem-watchdog_2.0.0_arm64.deb

# Enable and start the daemon.
sudo systemctl enable --now spark-modem-watchdog.service

# Verify all modems reach Healthy within 60 s.
sudo spark-modem status
```

For seven days, monitor:

- `events.jsonl` for false-positive actions on healthy modems.
- `modem_state_value` metric per modem (see `docs/FLEET_GATES.md`
  when available, or query Prometheus directly): value 4 (exhausted)
  should never appear.
- `cycle_duration_seconds` P99 stays under 10 s (M5 target).

**Go/no-go for phase 2:** one full week with zero false-positive
resets; all modems healthy or recovering-then-healthy with acceptable
MTTR.

## 4. Phase 2 — Field box, v2 live

Pick one field box with the most stable modems (low historical
recovery activity) and an attentive on-site contact.

Per-box cutover procedure:

```bash
# 1) Capture a baseline.
sudo spark-modem ctl support-bundle --out=/tmp/sb-pre-cutover.tgz

# 2) Install v2.
sudo apt install spark-modem-watchdog

# 3) Enable and start.
sudo systemctl enable --now spark-modem-watchdog.service

# 4) Verify healthy.
sudo spark-modem status

# 5) Watch for an hour.
sudo journalctl -u spark-modem-watchdog.service -f
```

Specifically watch for:

- v2 wanting to act on lines that are Zao-active (would mean a
  disagreement on Zao log parsing — a major issue per ADR-0003).
- `modem_state_value` hitting 4 (exhausted) on any modem.
- `actions_total{kind=~"modem_reset|usb_reset|driver_reset"}` rate
  exceeding the historical baseline (signal-gate fraction too loose).

### Rollback (any phase)

```bash
# 1) Downgrade to the previous v2 release.
sudo apt install spark-modem-watchdog=<previous-version>

# 2) Verify.
sudo spark-modem status

# 3) Capture a support bundle from the incident.
sudo spark-modem ctl support-bundle --out=/tmp/sb-rollback-$(date +%F).tgz
```

There is no v1 rollback path. See [ADR-0014](adr/0014-v1-retired-pivot.md).

**Go/no-go for phase 3:** two clean weeks; per-modem availability
within ±0.2 % of the historical baseline.

## 5. Phase 3 — Canary 10 %

Cut over 10 % of the fleet using the fleet management tool. Monitor
the health gates (see `docs/FLEET_GATES.md` when available):

- `modem_state_value == 4` (exhausted) time ≤ baseline across the
  canary cohort over a 24 h window.
- Destructive-reset rate (`actions_total{kind=~"modem_reset|usb_reset|driver_reset"}`)
  ≤ baseline + 10 %.
- Zero daemon crashes (`process_start_time_seconds` `changes()` == 0)
  in any 24 h window.

Rollback for a single canary box is the rollback procedure above.
Rollback for the canary cohort is a fleet-management push of the
previous `.deb` version.

## 6. Phase 4 — Fleet rollout

Roll forward 10 % per day until the fleet is on v2. The fleet-
management tool gates each batch on the previous batch's health
metrics.

Cutover is a no-touch operation per box (the deb upgrade replaces
the unit and restarts).

## 7. Phase 5 — v1 decommission

After 30 days of clean v2 operation:

- Move the v1 source scripts to `archive/v1/` in the repo with a
  README pointing at v2.
- Update the CLAUDE.md to point at the v2 directory.
- Close the v1 issue tracker label.

## 8. Data migration

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

## 9. Risks

| Risk                                                          | Mitigation                                                                       |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| v2's policy disagrees subtly with expected behavior, masked by agreement on healthy cycles only. | Phase 2 explicitly watches *fault* cycles; HIL injects faults. |
| `qmicli` output format on a deployed box differs from the lab. | qmi parser tests run on real captures from each fleet revision; `qmi/parsers.py` raises a structured error on unknown shapes. |
| Field site has a Zao SDK older than tested.                   | Daemon refuses to start with a structured error if Zao log format probe fails; pre-rollout inventory across the fleet identifies any old SDKs. |
| Catastrophic v2 bug with no v1 fallback.                      | Mitigated by 3-phase canary rollout (site, region, fleet) with health-gate holds between phases. Previous v2 `.deb` is always available. See [ADR-0014](adr/0014-v1-retired-pivot.md). |
| State file schema-version mismatch on package downgrade.       | v2 daemon refuses to load future schemas with a structured error. Operator runs `spark-modem ctl reset-state --all` before downgrade. |
| New runtime dep (Python 3.12 venv) breaks old fleet boxes.    | venv is bundled in the `.deb`; no system Python upgrade required. |

## 10. Communication

- Phase 0–1: internal eng + NOC awareness only.
- Phase 2: the chosen field site receives an email + Slack with the
  cutover schedule, rollback contact, and what to expect.
- Phase 3: fleet-wide ops notice via fleet management tool's
  changelog.
- Phase 4: same; with daily progress.
- Phase 5: post-mortem-style summary, regardless of whether anything
  went wrong. Include metrics: MTTR before/after, false-positive
  reset rate before/after, daemon CPU/RSS, support-ticket count.
