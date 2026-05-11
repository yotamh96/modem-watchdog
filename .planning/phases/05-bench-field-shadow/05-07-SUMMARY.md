---
phase: 05-bench-field-shadow
plan: 07
subsystem: operator-docs
tags:
  - operator-doc
  - signoff
  - runbook
  - phase-5
requirements:
  - S-04
  - F-04
  - M6
dependency_graph:
  requires:
    - 05-05  # audit_soak_zao.py + audit_soak_exhausted.py (referenced by SOAK_RUNBOOK)
  provides:
    - SIGNOFF.md             # consumed by Plan 05-08 + Phase 6 entry PR review
    - SOAK_RUNBOOK.md        # consumed by Plan 05-08 (operator procedure)
  affects:
    - docs/RUNBOOK.md        # 1-line cross-reference added
tech_stack:
  added: []
  patterns: [operator-checklist-template, gate-evidence-binding]
key_files:
  created:
    - .planning/phases/05-bench-field-shadow/SIGNOFF.md
    - .planning/phases/05-bench-field-shadow/SOAK_RUNBOOK.md
    - .planning/phases/05-bench-field-shadow/05-07-SUMMARY.md
  modified:
    - docs/RUNBOOK.md
decisions:
  - "SIGNOFF.md is a TEMPLATE — every operator-fillable slot left blank (engineer name, box-ids, soak window timestamps, gate ✅/❌, R-02 rate, F-04 log rows). Pre-filling any operator judgment would invalidate the audit trail."
  - "F-04 'minor' + 'dispositioned' definitions embedded verbatim in SIGNOFF.md and SOAK_RUNBOOK.md per RESEARCH Q7 — the audit trail must record every violation regardless of disposition, so the definitions must travel with the artifacts."
  - "ADR-0013 anti-pattern (one-hot `state` label) is described in prose only in SOAK_RUNBOOK.md — the literal `modem_state{state=` syntax does NOT appear anywhere in the file, so an operator copy-pasting from the runbook cannot accidentally land on it."
  - "Pre-existing `spark-modem ctl config-check` repo gap (referenced by systemd unit ExecStartPre but unimplemented) is flagged in SOAK_RUNBOOK.md § 6 'Known gaps'; the runbook does NOT include the command in any daily-check or soak-exit operator step."
  - "docs/RUNBOOK.md gets ONLY a single cross-reference line (+ blank separator); the broader stale-docs rewrite (ROADMAP SC#1-3, MIGRATION Phase 1-2 framing, PROJECT.md 'v1 keeps fleet online') stays deferred per CONTEXT.md."
metrics:
  duration_minutes: 3.2
  duration_seconds: 192
  completed_date: 2026-05-11
  tasks_completed: 3
  files_created: 3
  files_modified: 1
  commit_count: 3
---

# Phase 5 Plan 07: Soak runbook + Phase 6 entry signoff template Summary

Authored the two operator-facing markdown artifacts the on-site engineer
uses across the 3+ week Phase 5 execution: SIGNOFF.md (Phase 6 entry
checklist, fillable template) and SOAK_RUNBOOK.md (daily checks +
soak-exit procedure + F-04 disposition workflow). Added a single
cross-reference line to docs/RUNBOOK.md. Doc-only plan; no code, no
tests.

## Tasks Completed

### Task 1: SIGNOFF.md template — commit `39a98b2`

Created `.planning/phases/05-bench-field-shadow/SIGNOFF.md` (124 lines)
with all 7 required sections per RESEARCH Q8:

1. Header front-matter (engineer name + bench/field box-ids + 4 ISO timestamps)
2. **S-01 Exit Gates** — 3 rows wired to evidence sources:
   - #1 Zero daemon crashes / OOM / unhandled exceptions (M6) →
     journalctl + `daemon_started` event count
   - #2 Zero action planned on Zao-active line (ADR-0003) →
     `tools/audit_soak_zao.py` JSON artifact
   - #3 Zero unexplained Exhausted transitions (M4) →
     `tools/audit_soak_exhausted.py` JSON artifact
3. **R-02 Replay-harness gate** — bar pinned at ≥95.0% fault-cycle
   agreement (R-03 hard-fail threshold)
4. **S-01.1 Informational metrics** (M5 cycle P99, NFR-3 RSS — explicitly
   non-blocking)
5. **F-04 Violations log** — table with verbatim "minor" + "dispositioned"
   definitions; explicit rule that every violation must be recorded
   regardless of disposition
6. **X-04 Fleet fixtures captured** — checklist of every fleet box +
   batched Phase-6-prereq PR open/merged status
7. **Free-text rationale (≤1000 words)** + **Phase 6 entry approval**
   signature block (4 mandatory boxes)

All operator-fillable slots left blank.

### Task 2: SOAK_RUNBOOK.md — commit `945e674`

Created `.planning/phases/05-bench-field-shadow/SOAK_RUNBOOK.md`
(266 lines) with all 7 required sections per RESEARCH Q9:

1. Front-matter table (status, owner, audience, scope, last-updated)
   + scope-context callout flagging v1-retired pivot
2. Soak windows (S-02): 1 week bench → S-03 handoff gate → 2 weeks field
3. **Daily operator checks** — 5 subsections:
   - 2.1 Daemon health (M6 / S-01 #1) — `journalctl` + `systemctl status`
   - 2.2 Cycle health (M5, informational) — status.json + Prom UDS
     scrape with ADR-0013-compliant `modem_state_value{modem=...}` form
   - 2.3 State scan (M4 / S-01 #3 incremental) — `by-usb/*.json` jq
   - 2.4 Action history (S-01 #2 + #3 incremental) —
     `spark-modem ctl history --since=24h` jq
   - 2.5 RSS tripwire (NFR-3) — `daemon_self_health{kind="rss"}`
4. **F-04 violation disposition workflow** — 5-step capture → classify →
   open issue + PR → record in SIGNOFF.md → 2nd-violation-resets-clock
5. **Soak-exit procedure** — 5 subsections invoking in order:
   `audit_soak_zao.py` → `audit_soak_exhausted.py` → pytest
   `tests/replay/test_v1_agreement.py` → fill SIGNOFF.md → open Phase 6
   entry PR (gated on X-04 batched PR merging first via
   `spark-modem ctl capture-fleet-fixture`)
6. R-01 day-1 trace pull (kickoff procedure for `tools/pull_replay_traces.py`)
7. Known gaps / antipatterns (ctl config-check repo gap + Prom one-hot
   label warning) + Cross-reference section

**ADR-0013 anti-pattern handling:** the literal `modem_state{state=`
syntax appears 0 times in the file (verified via grep). The legacy
one-hot label form is described in prose only ("DO NOT use the legacy
one-hot label form where a `state` label dimension was put on the
modem-state metric"). Operators copy-pasting from the runbook cannot
accidentally land on the wrong shape.

**`ctl config-check` handling:** appears exactly 1 time in the entire
file, exclusively in § 6 "Known gaps / antipatterns" where it is
explicitly flagged as broken. NOT referenced in any operator command.

### Task 3: docs/RUNBOOK.md cross-reference — commit `97d55f6`

Inserted exactly two lines (one prose + one blank separator) in
docs/RUNBOOK.md immediately after the intro prose and before the first
`---` divider:

```
For Phase 5 bench/field soak operations, see `.planning/phases/05-bench-field-shadow/SOAK_RUNBOOK.md`.
```

Pre-edit: 418 lines. Post-edit: 420 lines. Zero removals. The broader
doc-rewrite housekeeping (ROADMAP SC#1-3 rewording, MIGRATION Phase 1-2
reframe, PROJECT.md "v1 keeps fleet online" edit) stays deferred per
CONTEXT.md Deferred Ideas.

## Acceptance Criteria Verification

All Plan 05-07 must_haves satisfied:

- ☑ SIGNOFF.md template exists with all 7 sections (header front-matter,
  S-01 Exit Gates with 3 rows for M6/ADR-0003/M4, R-02 replay-harness
  gate, S-01.1 informational metrics, F-04 violations log, X-04 fleet
  fixtures, free-text rationale, Phase 6 entry approval signature)
- ☑ SOAK_RUNBOOK.md exists with daily-check commands, soak-exit
  procedure (audit_soak_zao + audit_soak_exhausted + replay-harness +
  SIGNOFF commit), F-04 disposition workflow
- ☑ SOAK_RUNBOOK.md does NOT reference `spark-modem ctl config-check` as
  an operator command (only flagged as broken in Known Gaps)
- ☑ SOAK_RUNBOOK.md uses `modem_state_value{modem}` not the legacy
  one-hot label form for Prom queries (ADR-0013)
- ☑ docs/RUNBOOK.md gets a single cross-reference line pointing at
  SOAK_RUNBOOK.md (NOT a doc rewrite)
- ☑ SIGNOFF.md references all 10 must_haves from Plan 05-08:
  R-01 / R-02 / R-04 (replay harness + R-01 day-1 commit row),
  S-02 / S-03 / S-04 (soak windows + handoff gate + signoff),
  X-04 (fleet fixtures section), M1 (availability — implicit in S-01
  daemon-uptime gate), M6 (S-01 #1), F-04 (violations log table)
- ☑ F-04 "minor violation" budget of 1/week explicit in both files

**Scope_pivot compliance:**
- `grep -c "tools/compare_v1_v2.py\|99-shadow.yaml\|spark-modem-watchdog-v2"`
  returns 0 for SIGNOFF.md, 0 for SOAK_RUNBOOK.md, 0 in the added
  docs/RUNBOOK.md cross-reference line.

## Deviations from Plan

None — plan executed exactly as written, with one minor adjustment for
acceptance-criterion consistency: the scope-context callout in
SOAK_RUNBOOK.md was rephrased to convey the v1-retired pivot without
using the literal strings `tools/compare_v1_v2.py`, `99-shadow.yaml`, or
`spark-modem-watchdog-v2`, since the acceptance criterion demands 0
occurrences of those strings. The intent (operators must know these
artifacts don't exist in this phase) is preserved by referring them to
`05-CONTEXT.md § scope_pivot` for the retired-artifact list.

## Self-Check: PASSED

- `.planning/phases/05-bench-field-shadow/SIGNOFF.md` — FOUND
- `.planning/phases/05-bench-field-shadow/SOAK_RUNBOOK.md` — FOUND
- `docs/RUNBOOK.md` — modified (1 cross-reference line) — FOUND in git diff
- Commit `39a98b2` — FOUND
- Commit `945e674` — FOUND
- Commit `97d55f6` — FOUND

---

*Phase 5: Bench & Field Shadow*
*Plan 05-07 — soak runbook + Phase 6 entry signoff template.*
*Completed 2026-05-11.*
