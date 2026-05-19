# ADR-0014 — v1-Retired Scope Pivot

| Field        | Value                  |
| ------------ | ---------------------- |
| Status       | Accepted               |
| Date         | 2026-05-11             |
| Deciders     | Ops + Eng team         |
| Supersedes   | MIGRATION.md Phases 1-2 (shadow-alongside-v1 strategy) |

## Context

The original migration plan (docs/MIGRATION.md, written 2026-05-05) assumed
v1 and v2 would run side-by-side during a multi-phase shadow period:

- Phase 1: v2 deployed as `spark-modem-watchdog-v2.service` alongside v1.
- Phase 2: v2 active in shadow mode, v1 remains primary.
- Phase 3: cutover — stop v1, move v2 to canonical paths.

This plan required shadow-mode artifacts (`99-shadow.yaml`,
`tools/compare_v1_v2.py`, `-v2`-suffixed systemd unit and paths) and assumed
a rollback path via `spark-modem-watchdog-v1_1.0.0_all.deb`.

By 2026-05-11, v1 had already been retired across the entire fleet. The bash
scripts (`diag.sh`, `recovery.sh`, `auto_profile.sh`, `zao_reset_line.sh`)
are no longer running on any box. v1 was never packaged as a `.deb`; it was
deployed as loose scripts. Building a v1 `.deb` now would mean packaging
unmaintained code that has not run in production for days, creating false
confidence in a rollback path that was never tested.

## Decision

**v2 is the only daemon. v1 will not be rebuilt or repackaged.**

Specifically:

1. The shadow-alongside-v1 migration strategy (MIGRATION.md Phases 1-2) is
   retired. v2 deploys directly to canonical paths:
   - Service: `spark-modem-watchdog.service` (no `-v2` suffix).
   - Install root: `/opt/spark-modem-watchdog/`.
   - State directory: `/var/lib/spark-modem-watchdog/`.

2. Rollback means v2 previous version only (`apt install
   spark-modem-watchdog=<prev-version>`). The apt repository retains the
   last 3 `.deb` releases to support this.

3. No v1 `.deb` will be built. The v1 bash scripts are archived in the
   `v1-legacy` branch for reference only.

4. All `-v2`-suffixed paths, `99-shadow.yaml`, and `tools/compare_v1_v2.py`
   are removed from documentation and will not be built.

## Consequences

- **MIGRATION.md rewrite required.** Phases 1-2 (shadow mode) are dead.
  Phase 3 simplifies to: `apt install` + `systemctl enable --now` + verify
  healthy within 60 s.
- **Rollback story is honest.** Operators know the rollback target is the
  previous v2 `.deb`, not a v1 that was never packaged. This removes a
  false safety net and forces proper canary gating.
- **No shadow-mode code or tooling.** `compare_v1_v2.py` is never built.
  `99-shadow.yaml` is never written. The `-v2`-suffixed systemd unit is
  never created. This eliminates ~200 lines of dead migration tooling from
  the project scope.
- **Fleet cutover simplifies.** Per-box procedure becomes a single `apt
  install` + service enable. Health-gate validation replaces the
  side-by-side comparison as the primary safety mechanism.
- **Risk accepted:** if v2 has a catastrophic bug on a box, the only
  recovery is downgrade to previous v2 version or manual intervention.
  There is no automated path back to bash scripts. This is mitigated by
  the 3-phase canary rollout (site, region, fleet) with health-gate
  holds between phases.

## Revisit when

- A customer or compliance requirement demands a tested rollback to a
  fundamentally different daemon implementation (not just a version
  downgrade). This would require building and qualifying a separate
  rollback package, which is not justified today.
