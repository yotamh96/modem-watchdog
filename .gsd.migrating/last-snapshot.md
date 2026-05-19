# GSD context snapshot (2026-05-19T08:53:53.709Z)

## Active context
Active: M001 / S11 / T01 - ADR-0014 v1-retired pivot

## Top project memories
- [MEM001] (architecture) Rollback strategy for v2 fleet cutover Chose: Rollback is v2-current to v2-previous-version only. No v1 rollback .deb will be built. The apt repo retains the last 3 v2 .deb versions for downgrade.. Rationale: v1 is already retired across the entire fleet (scope pivot locked 2026-05-11 in 05-CONTEXT.md). v1 was never .deb-packaged; building one now from unmaintained bash scripts creates false confidence. T….
- [MEM002] (architecture) Rollback strategy for v2 fleet cutover — whether to build a v1 .deb, document manual v1 reinstall, or define rollback as v2-previous-version only Chose: Rollback is v2-previous-version only (Option C). No v1 .deb will be built. The fleet management tool's apt repo retains the last 3 v2 .deb versions for downgrade. MIGRATION.md removes all v1 .deb rol…. Rationale: v1 is already retired across the entire fleet (scope pivot 2026-05-11). v1 was never .deb-packaged — building one now means packaging unmaintained bash scripts, creating false confidence. The v2 .deb….
