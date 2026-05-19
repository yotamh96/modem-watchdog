# T02: Plan 02

**Slice:** S05 — **Milestone:** M001

## Description

Build the three-source version-detection helpers that Plans 03 (capture-fleet-fixture)
and 04 (preflight_check_known_fleet_triple) both need: libqmi version (from `qmicli
--version` stdout), Zao SDK version (from the Zao log banner), and EM7421 firmware
(routed through Plan 01's `dms_get_revision`). Surface them as a single
`compute_fleet_triple()` entry point returning a `FleetTriple` typed model (per
RESEARCH Q3 §220-298 and CONTEXT.md X-02/X-03).

Purpose: X-03 daemon preflight needs to compare the local triple against the known
set; X-02 fleet-fixture capture needs to emit the local triple to `triple.json`.
Both call sites read through this single seam so version-string formatting is
consistent across CLI and daemon.

Output: Two new modules (`qmi/version.py`, `zao_log/version.py`), one new typed
model (`FleetTriple` — frozen pydantic), four fixture files (qmicli --version
for 1.30 + 1.32; Zao log banner-present and banner-absent samples), two test
files. ~150 LOC production + ~200 LOC test.
