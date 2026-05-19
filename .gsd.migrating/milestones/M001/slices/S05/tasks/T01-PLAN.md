# T01: Plan 01

**Slice:** S05 — **Milestone:** M001

## Description

Add the one qmicli verb missing from QmiWrapper that Phase 5 needs for fleet-triple
capture (firmware string): `dms_get_revision`. Add the matching parser and the
per-libqmi-version fixture tree following Plan 02-02's pattern. This is the single
new QMI verb introduced in Phase 5 (per CONTEXT.md X-02 / RESEARCH Q3 §284).

Purpose: Phase 5's `capture-fleet-fixture` (Plan 03) and `preflight_check_known_fleet_triple`
(Plan 04) both call `dms_get_revision` to read the EM7421 firmware version. Without this
wrapper method + parser, neither downstream plan can complete.

Output: One new method on QmiWrapper, one new parser module, two fixture files,
two test files. ~80 LOC production + ~120 LOC test.
