# S05: Bench Field Shadow

**Goal:** Add the one qmicli verb missing from QmiWrapper that Phase 5 needs for fleet-triple
capture (firmware string): `dms_get_revision`.
**Demo:** Add the one qmicli verb missing from QmiWrapper that Phase 5 needs for fleet-triple
capture (firmware string): `dms_get_revision`.

## Must-Haves


## Tasks

- [x] **T01: Plan 01** `est:~5min`
  - Add the one qmicli verb missing from QmiWrapper that Phase 5 needs for fleet-triple
capture (firmware string): `dms_get_revision`. Add the matching parser and the
per-libqmi-version fixture tree following Plan 02-02's pattern. This is the single
new QMI verb introduced in Phase 5 (per CONTEXT.md X-02 / RESEARCH Q3 §284).

Purpose: Phase 5's `capture-fleet-fixture` (Plan 03) and `preflight_check_known_fleet_triple`
(Plan 04) both call `dms_get_revision` to read the EM7421 firmware version. Without this
wrapper method + parser, neither downstream plan can complete.

Output: One new method on QmiWrapper, one new parser module, two fixture files,
two test files. ~80 LOC production + ~120 LOC test.
- [x] **T02: Plan 02** `est:7min`
  - Build the three-source version-detection helpers that Plans 03 (capture-fleet-fixture)
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
- [x] **T03: Plan 03** `est:~11min`
  - Build the operator-facing CLI verb `spark-modem ctl capture-fleet-fixture --out=<dir>`
that produces the per-box fleet fixture (triple.json + redacted per-modem qmicli outputs
+ zao-log-sample.txt) without requiring the daemon to be running. This is the X-03
chicken-and-egg fix (per CONTEXT.md Claude's Discretion + RESEARCH Q2 §165-213): the
daemon refuses to start on unknown triples, but the engineer needs to capture the
triple on a daemon-less box.

Purpose: X-01 + X-02 deliverables. Output is committed to `tests/fixtures/fleet/<box-id>/`
per box, batched into a single Phase-6-prerequisite PR per CONTEXT.md X-04.

Output: One new CLI module (~200 LOC), one new redaction helper added to redact.py
(~30 LOC), one argparse-subparser block added to cli/main.py (~12 LOC), one new
fixture file with ICCID for PII test, one example fleet fixture committed at
`tests/fixtures/fleet/_test/triple.json` per RESEARCH Q10 §752, two test files.
- [x] **T04: Plan 04** `est:~6min`
  - Add the X-03 daemon preflight check that refuses to start on an unknown
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
- [x] **T05: Plan 05** `est:~7min`
  - Build the two post-hoc soak-audit tools the on-site engineer runs at bench-week-end
and field-2-weeks-end to validate the S-01 #2 and S-01 #3 exit gates:

1. `tools/audit_soak_zao.py` (S-01 #2): "no action planned on Zao-active line."
   Joins `events.jsonl` `ActionPlanned` events with the `ZaoSnapshot` history (from
   the Zao log); for each ActionPlanned, checks whether the modem's line was active
   at the cycle's wallclock. Per RESEARCH Q5 §352-396.

2. `tools/audit_soak_exhausted.py` (S-01 #3): "no unexplained Exhausted transitions."
   Replays policy decay logic against events.jsonl; for each
   StateTransition(new_state='exhausted'), checks whether the modem had ≥K consecutive
   healthy cycles in the lookback window AND counters were not reset (= bug; ADR-0006
   amendment regression). Per RESEARCH Q6 §399-451.

Purpose: These tools quantify S-01 #2 and #3 violations at SIGNOFF time. Plan 07
(SIGNOFF.md template) and Plan 07 (SOAK_RUNBOOK.md) wire them into the operator
soak-exit procedure. Without these tools, the engineer cannot prove the two
non-trivial S-01 gates were green.

Output: Two new Python scripts under `tools/` (SP-04-exempt). One new test directory
`tests/unit/tools/` with `__init__.py` + two test files. ~150 LOC per script + ~150 LOC
per test.
- [x] **T06: Plan 06** `est:~4min`
  - Ship the X-03 known-fleet index directory inside the `.deb` package. Per RESEARCH Q10
§618-651: the simplest path is a one-line addition to `debian/spark-modem-watchdog.install`
that copies the entire `tests/fixtures/fleet/` tree to
`/etc/spark-modem-watchdog/known-fleet/`. dpkg handles atomic install-time replace;
no postinst changes; daemon is read-only.

Purpose: Without this plan, Plan 04's preflight check would have nothing to validate
against on the bench/field box, so the daemon would refuse to start on every fleet
box from Phase 6 onward. The example fixture (`tests/fixtures/fleet/_test/triple.json`)
shipped by Plan 03 ensures the directory is never empty at first install.

Output: 1-line addition to `debian/spark-modem-watchdog.install`, 1-line addition to
`debian/spark-modem-watchdog.dirs`, one integration test that verifies the .deb
contents (skipped on dev hosts without dpkg-deb).
- [x] **T07: Plan 07**
  - Author the two operator-facing markdown artifacts the on-site engineer uses during
Phase 5 execution and at Phase 5 exit: SOAK_RUNBOOK.md (daily checks + soak-exit
procedure) and SIGNOFF.md (Phase 6 entry checklist). Add a single cross-reference
line to docs/RUNBOOK.md. Per RESEARCH Q8/Q9 + CONTEXT.md S-04/F-04.

Purpose: SIGNOFF.md is the Phase 6 entry gate (S-04: the engineer authors + commits
this file with the replay-harness JSON attached). SOAK_RUNBOOK.md is the operator's
source of truth during the 1+2 week soak windows (S-02). Without these, the engineer
has no canonical procedure for the daily checks, the soak-exit audit, or the F-04
violation disposition workflow.

Output: Two new markdown files in the phase directory; one-line addition to
docs/RUNBOOK.md. No code, no tests. Doc-only plan.
- [x] **T08: Plan 08** `est:0min`
  - This is the **operator-facing manual plan** that executes Phase 5 in the real world.
The plan covers the time-bound, hardware-dependent, judgment-bearing steps the on-site
engineer performs over ~3+ weeks: the R-01 day-1 trace pull, the 1-week bench soak,
the S-03 handoff gate, the 2-week field soak, the X-04 fleet-fixture capture sweep,
the R-02 replay-harness one-shot, and the final SIGNOFF.md authoring + commit.

Purpose: Phase 5's exit gate is human-attested. No automated script can declare
"bench Jetson ran clean for 1 week with no daemon crashes" — only the engineer
watching it can. This plan structures their work as a sequenced operator checklist
with explicit success criteria per stage.

Output: Six committed artifacts (LFS PR for v1-30d, X-04 batched fleet-fixture PR,
filled SIGNOFF.md, replay-summary-phase5-exit.json, two audit JSONs). NO code, NO
tests. All steps reference Plan 07's SOAK_RUNBOOK.md as the authoritative procedure;
this plan is the SEQUENCING + ACCEPTANCE OVERLAY.

Schedule: this plan spans ~3-4 weeks calendar time. The executor (Claude) does NOT
run automated commands — every task is a checklist for the human operator.

## Files Likely Touched

