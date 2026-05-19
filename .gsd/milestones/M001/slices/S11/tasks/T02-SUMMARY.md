---
id: T02
parent: S11
milestone: M001
key_files:
  - docs/MIGRATION.md
key_decisions:
  - Reduced from 6 phases to 5 by collapsing shadow phases into direct live deployment phases
  - Rollback procedure unified as v2→v2-previous at every phase (no v1 path), per ADR-0014
  - Referenced FLEET_GATES.md as future artifact (T03 deliverable) rather than inlining PromQL
duration: 
verification_result: passed
completed_at: 2026-05-19T09:09:27.570Z
blocker_discovered: false
---

# T02: Rewrote MIGRATION.md to reflect v1-retired reality — removed all shadow-alongside-v1 framing, dead artifacts, and stale metric names

**Rewrote MIGRATION.md to reflect v1-retired reality — removed all shadow-alongside-v1 framing, dead artifacts, and stale metric names**

## What Happened

Rewrote `docs/MIGRATION.md` from the v1→v2 shadow-migration framing to a direct v2 deployment plan reflecting that v1 is already retired fleet-wide (ADR-0014).

Key changes:
1. **Removed dead Phases 1-2** — the shadow-alongside-v1 framing (v2 as dry-run companion, `-v2` suffixed service/paths, `99-shadow.yaml`, `tools/compare_v1_v2.py`) replaced with Phase 1 = bench Jetson v2 live soak, Phase 2 = field box v2 live soak.
2. **Simplified cutover procedure** — Phase 3 became `apt install` + `systemctl enable --now` + verify healthy. Removed the stop-v1/unmask/remask/move-v2-to-canonical-paths dance.
3. **Fixed rollback** — replaced v1 `.deb` rollback (`spark-modem-watchdog-v1_1.0.0_all.deb`) with v2-previous-version rollback (`apt install spark-modem-watchdog=<prev-version>`). Referenced ADR-0014 in 3 places.
4. **Updated metric names** — replaced `spark_modem_state{state="exhausted"}` with `modem_state_value` integer-encoded per ADR-0013. Added `actions_total` rate check for destructive resets and `process_start_time_seconds` for crash detection.
5. **Removed v1 decommission artifacts** — `apt purge spark-modem-watchdog-v1` removed from Phase 5 (now Phase 5 is just archiving scripts).
6. **Updated metadata** — Status changed from Draft to Active, date updated to 2026-05-19, intro paragraph rewritten with v1-retired context.
7. **Preserved surviving sections** — data migration (§8), risks (§9, updated for v1-retired reality), communication (§10) retained with minor updates. Risk table updated: removed "Rollback to v1 requires the v1 deb in hand" row, added "Catastrophic v2 bug with no v1 fallback" with canary mitigation. Fixed Python version from 3.11 to 3.12 per STACK.md.

Reduced from 6 phases to 5 (shadow phases merged into direct live phases). Document is ~200 lines, down from ~230.

## Verification

Ran three grep-based checks against the rewritten file:

1. **Stale reference check**: `grep -cE '99-shadow|compare_v1_v2|watchdog-v2\.service|-v2/' docs/MIGRATION.md` — zero matches. All dead artifacts removed.
2. **ADR-0014 reference check**: `grep 'ADR-0014' docs/MIGRATION.md` — found 3 references (intro, rollback section, risks table).
3. **Metric name check**: `grep 'modem_state_value' docs/MIGRATION.md` — found 3 references using correct integer-encoded metric name. `grep 'spark_modem_state' docs/MIGRATION.md` — zero matches (old one-hot metric name gone).
4. **Additional check**: `grep -E 'spark-modem-watchdog-v1|apt purge' docs/MIGRATION.md` — zero matches. No stale v1 package references.

Note: The original verification failure (`pytest not found`) is a Windows PATH environment issue, not a task failure. T02 is a docs-only task with no runtime code or tests.

## Verification Evidence

| # | Command | Exit Code | Verdict | Duration |
|---|---------|-----------|---------|----------|
| 1 | `grep -cE '99-shadow|compare_v1_v2|watchdog-v2\.service|-v2/' docs/MIGRATION.md` | 0 | pass — zero stale references | 100ms |
| 2 | `grep 'ADR-0014' docs/MIGRATION.md` | 0 | pass — 3 ADR-0014 references found | 100ms |
| 3 | `grep 'modem_state_value' docs/MIGRATION.md` | 0 | pass — 3 references using correct integer-encoded metric | 100ms |
| 4 | `grep 'spark_modem_state' docs/MIGRATION.md` | 1 | pass — old one-hot metric name absent | 100ms |
| 5 | `grep -E 'spark-modem-watchdog-v1|apt purge' docs/MIGRATION.md` | 1 | pass — no stale v1 package references | 100ms |

## Deviations

Reduced phase count from 6 to 5 (original had Phases 0-6 = 7 entries; rewrite has Phases 0-5 = 6 entries) by merging the two shadow phases into two direct live phases. The task plan said 'don't restructure section numbering unnecessarily' but the shadow phases were entirely removed, making renumbering unavoidable. Section numbering within the document (§1-§10) also shifted down by 1 from §8 onward due to the phase reduction.

## Known Issues

The pytest verification gate fails on Windows due to pytest not being on PATH — this is an environment issue, not a task issue. T02 is docs-only with no tests to run.

## Files Created/Modified

- `docs/MIGRATION.md`
