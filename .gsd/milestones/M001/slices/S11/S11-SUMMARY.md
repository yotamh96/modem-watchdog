---
id: S11
parent: M001
milestone: M001
provides:
  - (none)
requires:
  []
affects:
  []
key_files:
  - docs/adr/0014-v1-retired-pivot.md
  - docs/FLEET_GATES.md
  - docs/MIGRATION.md
  - tools/validate_cutover.py
  - docs/CUTOVER_RUNBOOK.md
  - docs/templates/cutover-phase3-notice.md
  - docs/templates/cutover-phase4-notice.md
  - docs/templates/cutover-phase5-notice.md
  - tests/unit/test_fleet_gates_doc.py
  - tests/unit/test_cutover_runbook_doc.py
key_decisions:
  - Rollback strategy is v2→v2-previous-version only; no v1 .deb will be built (ADR-0014)
  - Gate 3 uses actions_total as proxy for session-disconnect rate (no dedicated counter in v2)
  - Gate 4 uses process_start_time_seconds (Prometheus builtin) rather than a custom metric
  - MIGRATION.md reduced from 6 to 5 phases by collapsing shadow-alongside-v1 phases into direct live deployment
  - Communication templates use {{PLACEHOLDER}} syntax for site-specific values
patterns_established:
  - (none)
observability_surfaces:
  - none
drill_down_paths:
  []
duration: ""
verification_result: passed
completed_at: 2026-05-19T11:13:30.173Z
blocker_discovered: false
---

# S11: Cutover & Fleet Rollout

**Delivered all cutover documentation, health-gate PromQL definitions, post-cutover validation script, operator communication templates, and stale-doc cleanup for fleet rollout — no daemon code changes.**

## What Happened

S11 is a delivery-phase slice producing the operational documentation and tooling needed for fleet rollout. All 7 tasks completed successfully.

**T01 — ADR-0014 and health-gate PromQL definitions.** Wrote `docs/adr/0014-v1-retired-pivot.md` formally recording the v1-retired scope pivot from 2026-05-11. Decision: rollback is v2→v2-previous-version only; no v1 .deb will be built. Created `docs/FLEET_GATES.md` with 4 PromQL canary gate definitions (availability, MTTR, false-positive rate, daemon restarts) — all metric references validated against `metrics_registry.py` via test.

**T02 — MIGRATION.md rewrite.** Rewrote `docs/MIGRATION.md` to reflect v1-retired reality. Removed all shadow-alongside-v1 framing, dead artifacts (99-shadow.yaml, compare_v1_v2.py, -v2 paths), and stale metric names. Reduced from 6 phases to 5 by collapsing shadow phases into direct live deployment phases. Rollback procedure unified as v2→v2-previous at every phase per ADR-0014.

**T03 — FLEET_GATES.md with test.** Created `docs/FLEET_GATES.md` with 4 PromQL canary gate definitions. Gate 3 uses `actions_total` as proxy for session-disconnect rate; Gate 4 uses `process_start_time_seconds` (Prometheus builtin). Test file `tests/unit/test_fleet_gates_doc.py` validates all metric references exist in registry or are builtins.

**T04 — Post-cutover validation script.** Created `tools/validate_cutover.py` — standalone script with 7 checks (service active, modem state, metrics scrape, HMAC config, carrier table SHA, event log growing, cycle interval). Structured JSON output, exit-code-based pass/fail. Passes mypy --strict and ruff check.

**T05 — Stale-doc cleanup.** Removed all "v1 currently keeps" and "alongside v1" phrasing from `.planning/PROJECT.md` and `.planning/ROADMAP.md`. docs/PRD.md needed no edits — its v1 references are architectural/historical.

**T06 — Communication templates.** Created 3 operator notice templates in `docs/templates/` for Phases 3/4/5 (canary, fleet rollout, post-rollout summary) with `{{PLACEHOLDER}}` syntax, matching MIGRATION.md §10 requirements.

**T07 — Cutover runbook.** Created `docs/CUTOVER_RUNBOOK.md` with 7-step per-box cutover procedure (pre-flight, apt install, enable, health verify, validate_cutover.py, monitoring confirm, rollback). Includes prerequisites, troubleshooting, and post-cutover checklist. Test file `tests/unit/test_cutover_runbook_doc.py` (8 tests) validates structure and content.

## Verification

**Slice-level verification (all checks passed):**

1. **File existence** — All key deliverables exist: `docs/adr/0014-v1-retired-pivot.md`, `docs/FLEET_GATES.md`, `docs/MIGRATION.md`, `tools/validate_cutover.py`, `docs/CUTOVER_RUNBOOK.md`, `docs/templates/cutover-phase{3,4,5}-notice.md`.

2. **Stale reference check** — `grep '99-shadow|compare_v1_v2|watchdog-v2\.service|-v2/'` against `docs/MIGRATION.md` returns zero matches. `grep 'v1 currently keeps'` across `docs/*.md` and `.planning/PROJECT.md` returns zero matches. (ADR-0014 references these terms in its Context section, which is expected — it describes what was replaced.)

3. **ADR-0014 cross-references** — `docs/MIGRATION.md` contains 3 ADR-0014 references.

4. **Metric consistency** — `docs/FLEET_GATES.md` contains 10 metric references across the 4 gates, all validated against `metrics_registry.py` by `tests/unit/test_fleet_gates_doc.py`.

5. **validate_cutover.py** — `--help` exits 0; `mypy --strict` reports "Success: no issues found in 1 source file"; `ruff check` reports "All checks passed!".

6. **Unit tests** — `pytest tests/unit/ -q --tb=short`: **1001 passed, 90 skipped, 0 failures** in 43s. No regressions.

## Requirements Advanced

None.

## Requirements Validated

None.

## New Requirements Surfaced

None.

## Requirements Invalidated or Re-scoped

None.

## Operational Readiness

None.

## Deviations

MIGRATION.md phase count reduced from 6 to 5 — the two shadow-alongside-v1 phases were removed since v1 is retired, making renumbering unavoidable. docs/PRD.md needed no edits (plan expected edits) — its v1 references are architectural/historical, not active-state claims.

## Known Limitations

validate_cutover.py cannot be functionally tested on Windows dev machine (checks systemd, modem state, etc.). PromQL gate definitions are not tested against a live Prometheus — only metric name consistency with the registry is verified. Communication templates require operator review for site-specific placeholder population.

## Follow-ups

None.

## Files Created/Modified

- `docs/adr/0014-v1-retired-pivot.md` — New ADR recording v1-retired scope pivot
- `docs/FLEET_GATES.md` — New fleet health-gate PromQL definitions
- `docs/MIGRATION.md` — Rewritten for v1-retired reality
- `tools/validate_cutover.py` — New post-cutover validation script
- `docs/CUTOVER_RUNBOOK.md` — New per-box cutover runbook
- `docs/templates/cutover-phase3-notice.md` — Canary deployment notice template
- `docs/templates/cutover-phase4-notice.md` — Fleet rollout expansion notice template
- `docs/templates/cutover-phase5-notice.md` — Post-rollout summary notice template
- `.planning/PROJECT.md` — Removed stale v1-as-active references
- `.planning/ROADMAP.md` — Removed stale v1-as-active references
- `tests/unit/test_fleet_gates_doc.py` — New test validating FLEET_GATES.md metric consistency
- `tests/unit/test_cutover_runbook_doc.py` — New test validating CUTOVER_RUNBOOK.md structure
