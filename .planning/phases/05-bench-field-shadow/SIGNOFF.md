# Phase 5 Sign-off — Bench & Field Shadow

**Status:** Template — fill at Phase 5 exit before opening the Phase 6 entry PR.

| Field                       | Value                                |
| --------------------------- | ------------------------------------ |
| Authored by                 | _on-site engineer name_              |
| Bench Jetson box-id         | _e.g. bench-jetson-01_               |
| Field box box-id            | _e.g. box-il-13_                     |
| Bench soak start (ISO)      | _YYYY-MM-DDTHH:MM:SSZ_               |
| Bench soak end (ISO)        | _YYYY-MM-DDTHH:MM:SSZ_               |
| Field soak start (ISO)      | _YYYY-MM-DDTHH:MM:SSZ_               |
| Field soak end (ISO)        | _YYYY-MM-DDTHH:MM:SSZ_               |

> Soak windows are sequential per CONTEXT.md S-02: 1 week bench, then 2 weeks
> field. Field deploy cannot start until bench week is clean (S-03 handoff).

---

## S-01 Exit Gates

All three must be PASS over BOTH the bench week and the field 2 weeks for
Phase 6 entry. F-04 budget: 1 minor violation per week of any single gate is
permitted, dispositioned, and recorded below (regardless of disposition). A
2nd violation in the same week resets the soak clock.

| Gate                                                   | Bench week | Field 2 weeks | Evidence                                                 |
| ------------------------------------------------------ | ---------- | ------------- | -------------------------------------------------------- |
| #1 Zero daemon crashes / OOM / unhandled exceptions (M6) | ☐ / ☐      | ☐ / ☐         | `journalctl -u spark-modem-watchdog.service --since=…` + count of `daemon_started` events with `reason=CRASH` |
| #2 Zero action planned on Zao-active line (ADR-0003)   | ☐ / ☐      | ☐ / ☐         | `tools/audit_soak_zao.py` JSON output attached as artifact |
| #3 Zero unexplained Exhausted transitions (M4)         | ☐ / ☐      | ☐ / ☐         | `tools/audit_soak_exhausted.py` JSON output attached as artifact |

Mark each cell ✅ (PASS) or ❌ (FAIL). Mark ☐ if not yet evaluated.

---

## R-02 Replay-harness gate

- **Fault-cycle agreement rate:** _XX.X%_
- **Bar (R-03 hard-fail):** ≥95.0%
- **Status:** ☐ PASS / ☐ FAIL
- **Artifact:** `.planning/phases/05-bench-field-shadow/replay-summary-phase5-exit.json` (commit alongside this SIGNOFF)
- **Bundle source:** R-01 day-1 trace pull merge commit: _<short-sha>_

---

## S-01.1 Informational metrics (NOT blocking)

These are captured for record-keeping only. They were verified at smaller
scale in Phase 2; the soak windows record them informationally.

| Metric              | Bench week | Field 2 weeks | NFR target |
| ------------------- | ---------- | ------------- | ---------- |
| Cycle P99 (M5)      | _X.X s_    | _X.X s_       | ≤10 s      |
| RSS (NFR-3)         | _X.X MiB_  | _X.X MiB_     | ≤80 MiB    |

---

## F-04 Violations log

> **Every gate violation MUST be recorded here, regardless of disposition.**
> "Minor" definition (CONTEXT.md F-04 + RESEARCH Q7):
> 1. No customer-visible outage during the violation window.
> 2. Attributable root cause identified within 24h of detection.
> 3. Fixable in <4h of engineering work.
>
> "Dispositioned" definition (RESEARCH Q7):
> 1. Root cause filed in repo issues (link below).
> 2. Fix PR opened (not necessarily merged).
> 3. Audit-trail entry committed here.

| Date (ISO)         | Gate    | Classification | Root cause | Disposition (issue + PR) | Customer outage? |
| ------------------ | ------- | -------------- | ---------- | ------------------------ | ---------------- |
| _none recorded yet_ |         |                |            |                          |                  |

F-04 clock-reset events (a 2nd violation in the same week of the same gate):
none recorded yet.

---

## X-04 Fleet fixtures captured

All fleet boxes (bench + field + every Phase 6 cutover candidate) MUST have a
`tests/fixtures/fleet/<box-id>/triple.json` committed before Phase 6 starts.
Daemon preflight (X-03) refuses to start without a matching entry.

- ☐ Bench Jetson captured: `tests/fixtures/fleet/<bench-box-id>/triple.json`
- ☐ Field box captured: `tests/fixtures/fleet/<field-box-id>/triple.json`
- ☐ All N remaining fleet boxes captured (N = _fill in count_):
  - ☐ box A: …
  - ☐ box B: …
  - …
- ☐ Batched Phase-6-prereq PR opened (link): _https://…_
- ☐ Batched PR merged

---

## Free-text rationale (≤ 1000 words)

> Engineer's narrative: what was observed during the soak windows, why
> you're comfortable signing off, any concerns flagged for Phase 6.
> Automated checks above prove the gates; this section captures the
> judgement that makes Phase 6 entry defensible.

_engineer fills here_

---

## Phase 6 entry approval

All four must hold for Phase 6 entry:

- ☐ All S-01 gates green over both soak windows (table above)
- ☐ R-02 replay-harness agreement rate ≥ 0.95 (artifact attached)
- ☐ Every fleet box has triple in known-set index (X-04 batch merged)
- ☐ All violations in the F-04 log are dispositioned per the definitions above

**Approved by:** _engineer signature / commit author_
**Date (ISO):** _YYYY-MM-DD_

---

*Phase 5: Bench & Field Shadow*
*Template authored by Plan 05-07; engineer-filled at Phase 5 exit.*
