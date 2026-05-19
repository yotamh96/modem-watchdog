# T04: Plan 04

**Slice:** S05 — **Milestone:** M001

## Description

Add the X-03 daemon preflight check that refuses to start on an unknown
(firmware, SDK, libqmi) triple. Per CONTEXT.md X-03 + RESEARCH Q1 §129-159 + Q4 §301-348,
the check reads every `triple.json` under `/etc/spark-modem-watchdog/known-fleet/`
into an in-memory set, computes the local triple via `compute_fleet_triple` (Plan 05-02),
and refuses to start with structured journalctl ERROR + last-config-error marker +
exit code 78 if the local triple is not present.

Purpose: Forces fleet-fixture capture (Plan 03) before any Phase 6 cutover; protects
the fleet from running v2 on a box with an undocumented hardware/SDK combo. Final
gate of the X-* deliverable family.

Output: One new module (`preflight_triple.py`, ~120 LOC), 6 lines of integration
into `daemon/main.py`, unit test + integration test. The known-fleet directory
itself is shipped by Plan 05-06 (.deb install) — this plan validates against an
injected directory path for tests.
