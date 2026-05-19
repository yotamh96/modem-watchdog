# Phase 5 — Fleet Rollout Complete / v1 Decommission Summary

**To:** Fleet operations, NOC, engineering  
**When:** After 100% of fleet is on v2 and v1 artifacts are archived  
**Channel:** Fleet management tool changelog + Slack #ops + email

---

Subject: **spark-modem-watchdog v2 fleet rollout complete — {{DATE}}**

Team,

The v2 rollout of `spark-modem-watchdog` is **complete**. All
**{{TOTAL_BOXES}} boxes** are running v2. v1 bash scripts have been
archived and are no longer deployed anywhere in the fleet.

## Rollout summary

| Metric                          | Value                    |
|---------------------------------|--------------------------|
| Rollout start (canary)          | {{CANARY_START_DATE}}    |
| Rollout end (100%)              | {{ROLLOUT_END_DATE}}     |
| Total duration                  | {{DURATION}}             |
| Boxes upgraded                  | {{TOTAL_BOXES}}          |
| Rollbacks triggered             | {{ROLLBACK_COUNT}}       |

## Before / after metrics

| Metric                          | v1 baseline    | v2 observed    |
|---------------------------------|----------------|----------------|
| Median MTTR (SIM)               | {{V1_VAL}}     | {{V2_VAL}}     |
| Median MTTR (registration)      | {{V1_VAL}}     | {{V2_VAL}}     |
| Median MTTR (QMI-hung)          | {{V1_VAL}}     | {{V2_VAL}}     |
| False-positive reset rate       | {{V1_VAL}}     | {{V2_VAL}}     |
| Daemon CPU (P95)                | N/A            | {{V2_VAL}}     |
| Daemon RSS (P95)                | N/A            | {{V2_VAL}}     |
| Support tickets (rollout period)| {{COUNT}}      | —              |

## v1 decommission

- v1 source scripts archived to `archive/v1/` with pointer README
- v1 issue tracker label closed
- No v1 artifacts remain on any fleet box

See [ADR-0014](../adr/0014-v1-retired-pivot.md) for the v1-retired decision.

## Ongoing operations

- Rollback path: previous v2 `.deb` via `apt install spark-modem-watchdog={{PREVIOUS_VERSION}}`
- Health monitoring: existing PromQL gates remain active ([FLEET_GATES.md](../FLEET_GATES.md))
- Runbook: [MIGRATION.md](../MIGRATION.md) Phase 5

## Contacts

- **Post-rollout issues:** {{ESCALATION_CONTACT}}
- **NOC ticket prefix:** `MODEM-V2` (standard prefix going forward)

---

*Reference: [MIGRATION.md](../MIGRATION.md) Phase 5*
