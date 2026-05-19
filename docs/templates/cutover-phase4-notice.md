# Phase 4 — Fleet Rollout (100%) Ops Notice

**To:** Fleet operations, NOC  
**When:** After canary health gates pass; before each expansion batch  
**Channel:** Fleet management tool changelog + Slack #ops (daily during rollout)

---

Subject: **spark-modem-watchdog v2 fleet rollout — batch {{BATCH}} — {{DATE}}**

Team,

Canary health gates have passed. We are expanding the v2 rollout to the
full fleet at a pace of **10% per day**.

## Current batch

| Item                | Detail                                     |
|---------------------|--------------------------------------------|
| Batch number        | {{BATCH}} of {{TOTAL_BATCHES}}             |
| Boxes in this batch | {{BOX_COUNT}} boxes ({{CUMULATIVE_PCT}}% cumulative) |
| Package version     | `spark-modem-watchdog={{VERSION}}`          |

## Health gate status (from canary)

All 4 gates passed prior to expansion:

1. Exhausted-time <= baseline
2. Destructive-reset rate <= baseline + 10%
3. Session-disruption rate <= baseline + 10%
4. Zero daemon crashes in 24h

Gate definitions: [FLEET_GATES.md](../FLEET_GATES.md).

## Daily progress

This notice is sent with each batch. Cumulative progress:

- Batch 1: {{PCT}}% — {{DATE}}
- Batch 2: {{PCT}}% — {{DATE}}
- ...

## Rollback procedure

Per-box rollback to the previous v2 release:

```bash
sudo apt install spark-modem-watchdog={{PREVIOUS_VERSION}}
sudo spark-modem status
sudo spark-modem ctl support-bundle --out=/tmp/sb-rollback-$(date +%F).tgz
```

Cohort rollback: push the previous `.deb` version via fleet management tool
to affected boxes.

## Contacts

- **Escalation:** {{ESCALATION_CONTACT}}
- **NOC ticket prefix:** `MODEM-V2-ROLLOUT`

---

*Reference: [MIGRATION.md](../MIGRATION.md) Phase 4*
