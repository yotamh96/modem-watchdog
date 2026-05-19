# Phase 3 — Canary Deployment (10%) Ops Notice

**To:** Fleet operations, NOC  
**When:** Before deploying v2 to the first canary batch  
**Channel:** Fleet management tool changelog + Slack #ops

---

Subject: **spark-modem-watchdog v2 canary deployment — {{DATE}}**

Team,

We are beginning the v2 canary rollout of `spark-modem-watchdog` to **{{N}} boxes (10% of fleet)** starting **{{DATE}}**.

## What is changing

The modem watchdog daemon is being upgraded from v1 (bash scripts) to v2
(Python, packaged as `spark-modem-watchdog.deb`). v1 has already been
retired across the fleet (see [ADR-0014](../adr/0014-v1-retired-pivot.md)).

## Canary scope

| Item                | Detail                                     |
|---------------------|--------------------------------------------|
| Boxes in this batch | {{BOX_LIST}}                               |
| Package version     | `spark-modem-watchdog={{VERSION}}`          |
| Duration            | Minimum 2 weeks                            |
| Health gates        | 4 PromQL gates must pass before expansion  |

Health gate definitions are documented in [FLEET_GATES.md](../FLEET_GATES.md).

## What to expect

- The upgrade is pushed via the fleet management tool (`apt upgrade`).
- The daemon restarts automatically; no manual intervention required.
- Modem recovery behavior is unchanged from the operator's perspective.

## Rollback procedure

If issues are observed on any canary box:

```bash
sudo apt install spark-modem-watchdog={{PREVIOUS_VERSION}}
sudo spark-modem status
sudo spark-modem ctl support-bundle --out=/tmp/sb-rollback-$(date +%F).tgz
```

There is no v1 rollback path. Rollback targets the previous v2 release.

## Contacts

- **Escalation:** {{ESCALATION_CONTACT}}
- **NOC ticket prefix:** `MODEM-V2-CANARY`

---

*Reference: [MIGRATION.md](../MIGRATION.md) Phase 3*
