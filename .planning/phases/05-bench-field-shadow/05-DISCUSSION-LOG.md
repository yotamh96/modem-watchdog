# Phase 5: Bench & Field Shadow - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-11
**Phase:** 05-bench-field-shadow
**Areas discussed:** Replay harness operationalization, Soak window + Phase 6 gating, Fault injection on live field box, Fleet fixture capture mechanism

**Scope pivot recorded during discussion:** User dispositioned "v1 retired across the entire fleet" early in the session, invalidating the original Phase 5 compare-tool framing from ROADMAP SC#1–#3 + MIGRATION §3–4. The initial 4-area gray-area presentation (Compare tool design / Synthetic fault injection / Shadow deployment packaging / Fleet fixture capture + signoff) was re-cut to (Replay harness operationalization / Soak window + Phase 6 gating / Fault injection on live field box / Fleet fixture capture mechanism) before per-area questioning began.

---

## Area-selection (pre-pivot)

| Option | Description | Selected |
|--------|-------------|----------|
| Compare tool design | tools/compare_v1_v2.py data sources, cycle pairing, output, cadence | ✓ |
| Synthetic fault injection in shadow | Reuse Plan 04-06 helpers vs new operator surface; daily scheduling; RF without hardware | ✓ |
| Shadow deployment packaging | Single .deb vs separate; 99-shadow.yaml distribution; dry_run toggle | ✓ |
| Fleet fixture capture + Phase 6 exit signoff | Triple detection probe location, capture mechanism, gate enforcement, signoff | ✓ |

**User's choice:** All four selected.

**Notes:** User then dispositioned "there is no reason to compare v1 and v2" on the first Compare tool question. Clarification: "v1 is not actually running on the field box anymore" → reframed to "v1 retired across the entire fleet." Replaced by replay-only validation gate.

---

## Area-selection (post-pivot)

| Option | Description | Selected |
|--------|-------------|----------|
| Replay harness operationalization | Trace refresh cadence, gate run location, gate %, who pulls traces | ✓ |
| Soak window + Phase 6 gating | Soak metrics, window shape, bench→field handoff, signoff form | ✓ |
| Fault injection on live field box | Field injection y/n, bench coverage source, natural-fault minimum, abort criteria | ✓ |
| Fleet fixture capture mechanism | Probe location, contents, known-set enforcement, capture cadence | ✓ |

**User's choice:** All four selected.

---

## Replay harness operationalization

### Q1: When does the quarterly v1-trace LFS refresh cadence begin?

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 5 day 1 (first refresh now) | Fresh trace pull at Phase 5 kickoff, establishes cadence with skin in the game | ✓ |
| Phase 5 exit only | One refresh before close, quarterly cadence starts post-100% | |
| Skip refresh in Phase 5 | Reuse Phase 4 bundle | |
| No refresh ever | v1 gone → trace bundle frozen forever | |

**User's choice:** Phase 5 day 1.

### Q2: Where does the replay-harness gate run during Phase 5?

| Option | Description | Selected |
|--------|-------------|----------|
| Both — commit-CI + scheduled nightly (recommended) | Two layers: commit catches regressions, nightly catches drift | |
| CI only (every commit) | Simpler; no scheduled job | |
| Scheduled-only nightly | Skip commit gate; rely on existing HIL nightly | |
| One-shot at Phase 5 exit | Manual; no automation | ✓ |

**User's choice:** One-shot at Phase 5 exit (against recommendation; user opting for minimum automation/ceremony).

### Q3: Does the agreement bar move on real-fleet traces?

| Option | Description | Selected |
|--------|-------------|----------|
| Hold at ≥0.95 (recommended) | Same gate Plan 04-07 ships; no code change | ✓ |
| Raise to ≥0.97 | Stricter on production data | |
| Lower to ≥0.90 | Budget for v1-bug behavior v2 deliberately doesn't replicate | |
| Two-tier: ≥0.95 overall + ≥0.99 healthy slice | Both fault and healthy gates | |

**User's choice:** Hold at ≥0.95.

### Q4: Who pulls day-1 fresh traces?

| Option | Description | Selected |
|--------|-------------|----------|
| On-site engineer from field box, runs pull_replay_traces.py, opens PR (recommended) | Per-box archive + redaction pipeline, single PR | ✓ |
| Eng from centralized log archive | If centralized v1 logs exist somewhere | |
| Skip the day-1 pull | Reverses prior decision | |

**User's choice:** On-site engineer from field box.

---

## Soak window definition + Phase 6 gating

### Q1: What signals must hold over the soak window?

Multi-select.

| Option | Description | Selected |
|--------|-------------|----------|
| Zero daemon crashes / OOM / unhandled-exception restarts (M6) (recommended) | journalctl query + daemon_started events count | ✓ |
| Zero 'act on Zao-active line' plans (recommended) | Post-hoc events.jsonl query | ✓ |
| Zero unexplained Exhausted from counter accumulation (M4) (recommended) | Replay decay logic against soak events | ✓ |
| P99 cycle ≤10s + RSS ≤80 MiB hold across the window | Fresh measurement as hard exit gate | |

**User's choice:** First three; P99/RSS deliberately excluded as hard gate (verified earlier; informational only).

### Q2: What's the soak window shape?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 week bench + 2 weeks field, sequential (recommended) | MIGRATION.md original shape preserved | ✓ |
| Compress to ~1 week total (3 days bench + 4 days field) | v1-comparison reason for long window is gone | |
| Parallel: bench + field both start day 1 | Both must hit 7 clean days independently | |
| Skip bench, field-box-only 2 weeks | Phase 4 HIL nightly already covers bench | |

**User's choice:** Sequential 1 week + 2 weeks.

### Q3: What gates the bench→field handoff?

| Option | Description | Selected |
|--------|-------------|----------|
| Same 3 gates as Phase 5 exit, on bench-only (recommended) | Symmetric one-rule-two-checkpoints | ✓ |
| Looser bench gate — operator judgment | Bench is for shaking out bugs | |
| Stricter bench gate (+zero unjustified ActionSkipped) | Closer eyes on bench | |
| Bench is informational only — no gate | Field is the only formal gate | |

**User's choice:** Same 3 gates as Phase 5 exit.

### Q4: What form does the Phase 6 entry signoff take?

| Option | Description | Selected |
|--------|-------------|----------|
| SIGNOFF.md checklist + replay-harness CI result attached (recommended) | Hybrid: human judgment + machine-checkable %; matches Plan 04-07 bench-Jetson verify pattern | ✓ |
| Fully automated GitHub Actions check | No human in loop | |
| Fully manual (no committed artifact) | Email/Slack only | |
| SIGNOFF.md + Prom dashboard screenshot + replay-harness result | Heavier paper trail | |

**User's choice:** SIGNOFF.md + replay-harness CI result attached.

---

## Fault injection on live field box

### Q1: Do we inject synthetic faults on the field box?

| Option | Description | Selected |
|--------|-------------|----------|
| No — bench only, field rides natural faults (recommended) | Avoids customer-outage risk entirely | ✓ |
| Yes, cheap actions only — skip destructive scenarios | Verifies cheap action paths | |
| Yes, all 4 scenarios during maintenance windows | Pre-coordinated outage risk | |
| Yes, fully — daily injection accepts outage risk | ROADMAP original framing | |

**User's choice:** No.

### Q2: Bench-only fault injection: HIL nightly enough or add deliberate runs?

| Option | Description | Selected |
|--------|-------------|----------|
| HIL nightly is enough (recommended) | No new Phase 5 fault-injection code | ✓ |
| Add bench-week verbose scenario sweep at day 0 | Plus nightly | |
| Add 4 ROADMAP scenarios as separate daily script | Phase-5-specific daily | |
| Skip bench injection — rely on Phase 4 HIL coverage | Pre-Phase-5 signal only | |

**User's choice:** HIL nightly is enough.

### Q3: Natural-fault minimum for field 2-week soak?

| Option | Description | Selected |
|--------|-------------|----------|
| No minimum (recommended) | 14 days enough; replay-harness covers fault-path coverage | ✓ |
| Soft minimum — surface counts in SIGNOFF.md | Visibility without gate-blocking | |
| Hard minimum — at least N events of K kinds | Statistical confidence; operational risk | |
| Hybrid — at least 1 successful natural recovery + replay-harness | Catches degenerate quiet case | |

**User's choice:** No minimum.

### Q4: Abort criterion for the soak windows?

| Option | Description | Selected |
|--------|-------------|----------|
| Any one of 3 hard-gate violations OR daemon-won't-start (recommended) | Zero-tolerance | |
| Threshold-based: 1 minor violation per week budget | Realistic; allows judgment | ✓ |
| Operator judgment only | No mechanical abort | |
| Customer-visible outage attributable to v2 | Most permissive | |

**User's choice:** Threshold-based budget (against zero-tolerance recommendation; "minor" and "dispositioned" definitions deferred to planning).

---

## Fleet fixture capture mechanism

### Q1: Where does the (firmware, Zao SDK, libqmi) triple detection probe live?

| Option | Description | Selected |
|--------|-------------|----------|
| New ctl subcommand: `spark-modem ctl capture-fleet-fixture --out=<dir>` (recommended) | Self-contained; explicit; reuses qmi/ wrappers | ✓ |
| Extend `ctl support-bundle` to also capture the triple | Adds branching to tested CLI surface | |
| Daemon emits triple to status.json at startup; operator copies | Status.json schema bump | |
| Standalone shell script in tools/ | Duplicates daemon's version-detection | |

**User's choice:** New ctl subcommand.

### Q2: What does a captured fleet fixture contain?

| Option | Description | Selected |
|--------|-------------|----------|
| triple.json + qmicli sample dir + zao-log-sample (no PII) (recommended) | Feeds per-libqmi-version pattern | ✓ |
| Minimal: triple.json only | Smallest diff | |
| Maximal: + 1 hour events.jsonl + status.json snapshot | Best forensic value; PII risk | |
| triple.json + one qmicli sample (dms_get_revision only) | Middle ground | |

**User's choice:** triple.json + qmicli sample dir + zao-log-sample.

### Q3: How is the 'known set' enforced as Phase 6 entry gate?

| Option | Description | Selected |
|--------|-------------|----------|
| Daemon refuses to start if triple is outside known set (recommended) | Strong runtime enforcement | ✓ |
| Soft warn + Phase 6 deploy PR CI check blocks if unknown | Two layers, less strict | |
| Manual spreadsheet — no automation | Lowest code; drift risk | |
| Manifest-only + PR template checkbox | Human-in-loop only | |

**User's choice:** Daemon refuses to start (new daemon preflight behavior added by Phase 5).

### Q4: Who captures fleet fixtures and at what point in Phase 5→Phase 6 flow?

| Option | Description | Selected |
|--------|-------------|----------|
| On-site eng captures during/after field-box deploy; one PR per box batched into single Phase 6 prereq PR (recommended) | Physical access window of Phase 6 prep | ✓ |
| Capture during Phase 6 per-box deploy, blocking | Automated; self-healing | |
| Capture pre-Phase 5 (bench + field shadow boxes count); rest in Phase 6 | 2 fixtures pre-Phase 5 | |
| Capture per UNIQUE triple, not per box | Smaller repo footprint; identity risk | |

**User's choice:** On-site eng, per-box PRs batched.

---

## Claude's Discretion

Areas deferred to planning where Claude has flexibility (not user decisions, will be resolved by planner/researcher):

- Exact qmicli verb list for X-02 fixture capture (6–8 range)
- Known-set index shape in the .deb (sha-named files vs index.json vs YAML vs Python module)
- The X-03 chicken-and-egg mechanism (--no-preflight flag vs companion show-triple vs implicit bypass)
- SIGNOFF.md template structure
- "Minor violation" and "dispositioned" definitions for F-04 budget
- "Act on Zao-active line" post-hoc query mechanism (S-01 #2)
- "Unexplained Exhausted" detection mechanism (S-01 #3)
- R-02 one-shot trigger mechanism (manual pytest vs runbook step)

## Deferred Ideas

See `05-CONTEXT.md` § Deferred Ideas. Highlights:

- ROADMAP/MIGRATION/PROJECT/CLAUDE.md doc-rewrite housekeeping for v1-retired pivot
- ADR-0014 candidate to record the pivot
- `tools/compare_v1_v2.py` explicitly NOT built
- Shadow `.deb` packaging story explicitly NOT built (no 99-shadow.yaml, no -v2 paths)
- v2.1 candidates carried from Phase 4 04-CONTEXT.md (D-Bus zao-infra-ctrl subscription, per-MCC signal floors, ctl simulate-issue)
