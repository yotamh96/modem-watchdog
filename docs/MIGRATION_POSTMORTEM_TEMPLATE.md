# Migration postmortem — v2 deployment

<!-- PLACEHOLDER template: replace all {{...}} values before submitting. -->

| Field         | Value                          |
| ------------- | ------------------------------ |
| Date          | {{DATE}}                       |
| Author        | {{AUTHOR}}                     |
| Reviewers     | {{REVIEWERS}}                  |
| Fleet size    | {{FLEET_SIZE}} boxes           |

## 1. Timeline

| Phase | Description               | Start date       | End date         | Duration     | Notes                |
| ----- | ------------------------- | ---------------- | ---------------- | ------------ | -------------------- |
| 0     | Build & lab validation    | {{P0_START}}     | {{P0_END}}       | {{P0_DAYS}}  | {{P0_NOTES}}         |
| 1     | Bench Jetson, v2 live     | {{P1_START}}     | {{P1_END}}       | {{P1_DAYS}}  | {{P1_NOTES}}         |
| 2     | Field box, v2 live        | {{P2_START}}     | {{P2_END}}       | {{P2_DAYS}}  | {{P2_NOTES}}         |
| 3     | Canary 10 %               | {{P3_START}}     | {{P3_END}}       | {{P3_DAYS}}  | {{P3_NOTES}}         |
| 4     | Fleet rollout 100 %       | {{P4_START}}     | {{P4_END}}       | {{P4_DAYS}}  | {{P4_NOTES}}         |
| 5     | v1 decommission & archive | {{P5_START}}     | {{P5_END}}       | {{P5_DAYS}}  | {{P5_NOTES}}         |

Total wall time: {{TOTAL_WALL_TIME}}

## 2. Incident log

Record every incident that occurred during the migration, even minor ones.
If no incidents occurred, leave the single "None" row and note that in the
lessons-learned section.

| # | Date         | Phase | Severity   | Summary               | Root cause            | Resolution            | Duration   |
|---|------------- | ----- | ---------- | --------------------- | --------------------- | --------------------- | ---------- |
| 1 | {{INC_DATE}} | {{INC_PHASE}} | {{INC_SEV}} | {{INC_SUMMARY}} | {{INC_ROOT_CAUSE}} | {{INC_RESOLUTION}} | {{INC_DUR}} |

Rollbacks performed: {{ROLLBACK_COUNT}} (describe each in the rows above).

## 3. Before / after metrics

All values measured over a rolling 7-day window unless noted otherwise.

| Metric                              | v1 baseline          | v2 post-migration    | Delta   | Target (PRD)       |
| ----------------------------------- | -------------------- | -------------------- | ------- | ------------------ |
| Per-modem availability              | {{V1_AVAILABILITY}}  | {{V2_AVAILABILITY}}  | {{DELTA_AVAILABILITY}} | >= 99.5 % (M1)   |
| Median MTTR — SIM fault (s)         | {{V1_MTTR_SIM}}      | {{V2_MTTR_SIM}}      | {{DELTA_MTTR_SIM}}     | <= 60 s (M2)      |
| Median MTTR — registration fault (s)| {{V1_MTTR_REG}}      | {{V2_MTTR_REG}}      | {{DELTA_MTTR_REG}}     | <= 90 s (M2)      |
| Median MTTR — QMI-hung fault (s)    | {{V1_MTTR_QMI}}      | {{V2_MTTR_QMI}}      | {{DELTA_MTTR_QMI}}     | <= 180 s (M2)     |
| False-positive destructive resets   | {{V1_FP_RATE}}       | {{V2_FP_RATE}}       | {{DELTA_FP_RATE}}      | <= 5 % (M3)       |
| Exhausted states (counter accum.)   | {{V1_EXHAUSTED}}     | {{V2_EXHAUSTED}}     | {{DELTA_EXHAUSTED}}    | 0 (M4)            |
| P99 cycle duration (s)              | {{V1_P99_CYCLE}}     | {{V2_P99_CYCLE}}     | {{DELTA_P99_CYCLE}}    | <= 10 s (M5)      |
| Daemon CPU usage (%)                | {{V1_CPU}}           | {{V2_CPU}}           | {{DELTA_CPU}}          | —                 |
| Daemon RSS (MiB)                    | {{V1_RSS}}           | {{V2_RSS}}           | {{DELTA_RSS}}          | —                 |
| Support tickets (modem-related)     | {{V1_TICKETS}}       | {{V2_TICKETS}}       | {{DELTA_TICKETS}}      | —                 |

## 4. Lessons learned

### What went well

- {{LESSON_WELL_1}}
- {{LESSON_WELL_2}}
- {{LESSON_WELL_3}}

### What could be improved

- {{LESSON_IMPROVE_1}}
- {{LESSON_IMPROVE_2}}
- {{LESSON_IMPROVE_3}}

### Action items for future migrations

| Action                         | Owner            | Due date         |
| ------------------------------ | ---------------- | ---------------- |
| {{ACTION_1}}                   | {{ACTION_1_OWNER}} | {{ACTION_1_DUE}} |
| {{ACTION_2}}                   | {{ACTION_2_OWNER}} | {{ACTION_2_DUE}} |

## 5. Sign-off

| Role                  | Name                 | Date             | Signature |
| --------------------- | -------------------- | ---------------- | --------- |
| Engineering lead      | {{ENG_LEAD}}         | {{ENG_LEAD_DATE}} | _________ |
| NOC / Operations lead | {{OPS_LEAD}}         | {{OPS_LEAD_DATE}} | _________ |
| Fleet management      | {{FLEET_LEAD}}       | {{FLEET_LEAD_DATE}} | _________ |
| Project sponsor       | {{SPONSOR}}          | {{SPONSOR_DATE}} | _________ |

**Migration outcome:** {{OUTCOME — Successful / Successful with issues / Partial / Rolled back}}

**Recommended follow-up:** {{FOLLOWUP}}
