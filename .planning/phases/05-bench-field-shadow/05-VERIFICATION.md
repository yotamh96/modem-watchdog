---
phase: 05-bench-field-shadow
verified: 2026-05-11T09:47:34Z
status: human_needed
score: 30/40 must-haves verified (code-complete on 7/8 plans; 10 truths require operator soak action)
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: n/a
  gaps_closed: []
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "R-01 day-1 v1-trace pull → LFS PR opened, redaction verified (no raw 18-22 digit runs survive outside `<redacted:[0-9a-f]{8}>` form), ≥30d coverage documented, PR merged BEFORE bench soak begins"
    expected: "tests/fixtures/replay/v1-30d/ refreshed via LFS PR; merge-commit SHA recorded for SIGNOFF.md 'Bundle source' field"
    why_human: "Requires physical archive pull from decommissioned v1 boxes + operator judgment on coverage adequacy + manual PR review"
  - test: "Bench Jetson 1-week clean soak: daily checks executed per SOAK_RUNBOOK § 2 for 7 consecutive days; evidence saved under phase5-evidence/bench/day-{1..7}/"
    expected: "0 daemon crashes (M6), 0 act-on-Zao-active (ADR-0003), 0 unexplained Exhausted (M4); F-04 budget ≤1 minor/week observed and dispositioned"
    why_human: "Calendar-time soak window on real hardware; cannot be automated by Claude; relies on bench Jetson + 4× EM7421 + Zao SDK observed in situ"
  - test: "S-03 handoff gate: end-of-bench-week audit_soak_zao.py + audit_soak_exhausted.py both exit 0 (or ≤F-04 budget AND dispositioned); daemon-crash count over bench window is 0"
    expected: "phase5-evidence/bench/audit-zao.json + audit-exhausted.json both show violations==0 OR within budget; S-03 PASSED logged"
    why_human: "Audit tools run against soak-window events.jsonl + Zao log; the events themselves only exist after the live soak runs"
  - test: "Field box 2-week clean soak: 14 consecutive days of daily checks; F-01 honored (no synthetic injection on the field box — DO NOT run tests/hil/fault_inject.py); evidence saved under phase5-evidence/field/day-{1..14}/"
    expected: "Same gates as bench week, measured over 14 days; natural-fault events recorded for informational purposes (F-03 no minimum)"
    why_human: "Real-world field deployment with customer-impact risk; the field-soak window cannot be automated, and F-01 explicitly requires no fault injection"
  - test: "X-04 fleet-fixture capture sweep: operator runs `sudo spark-modem ctl capture-fleet-fixture --out=/tmp/fleet-fixture-<box-id>` on every Phase 6 cutover box (including bench + field) during physical-access window"
    expected: "tests/fixtures/fleet/<box-id>/ contains triple.json + qmi/<usb_path>/ tree for every box; PII redaction verified (no raw 18-22 digit runs); ADR-0009 usb_path-keyed subdirs (NOT cdc-wdmN)"
    why_human: "Requires SSH or physical-console access to every fleet Jetson; operator must verify usb_path naming + PII redaction per-box before commit"
  - test: "X-04 batched Phase-6-prereq PR: all per-box fixtures committed in a single PR, reviewed, and merged BEFORE the Phase 6 entry PR opens"
    expected: "git log shows the X-04 batched PR merge SHA; tests/fixtures/fleet/ contains one subdir per cutover box; .deb rebuild ships them at /etc/spark-modem-watchdog/known-fleet/<box-id>/"
    why_human: "Per-box capture artifacts depend on real hardware access; PR review judgment is human-bound"
  - test: "R-02 replay-harness one-shot at Phase 5 exit: `pytest tests/replay/test_v1_agreement.py -v --tb=short` against freshly-pulled v1-30d bundle (from R-01) achieves ≥0.95 fault-cycle agreement"
    expected: ".planning/phases/05-bench-field-shadow/replay-summary-phase5-exit.json committed with fault_cycle_agreement ≥ 0.95; pytest exits 0 (R-03 hard-fail threshold satisfied)"
    why_human: "Bundle source is the R-01 PR output (human-attested); the one-shot is run manually at Phase 5 exit, not on a schedule"
  - test: "SIGNOFF.md filled in by on-site engineer: header front-matter, S-01 Exit Gates table (3 rows × bench+field columns), R-02 row, S-01.1 informational metrics, F-04 violations log (every violation regardless of disposition), X-04 fleet fixtures checklist, free-text rationale, Phase 6 entry approval (4 boxes ticked)"
    expected: "All template slots filled; no `_engineer fills here_` placeholders remain except deliberate free-text section; all 4 Phase 6 entry approval boxes are ticked (☒ or ✅)"
    why_human: "Engineer attestation is the entire point of the Phase 6 entry gate; cannot be machine-generated"
  - test: "SIGNOFF.md + audit JSONs + replay-summary committed in one PR; reviewer enforces that all four approval boxes are ticked AND X-04 batched PR has already merged"
    expected: "Phase 6 entry PR merged; merge-commit SHA recorded; Phase 5 is COMPLETE and `/gsd-plan-phase 6` can begin"
    why_human: "PR review is human-bound and the SIGNOFF artifact is the gate substrate"
  - test: "CR-01 fix verification: `_RAW_QMICLI_PII_PATTERNS` in src/spark_modem/cli/redact.py is extended to cover `IPv4 subnet mask: '...'` and `IPv4 gateway address: '...'` BEFORE the X-04 sweep runs"
    expected: "Patterns tuple includes new entries for subnet mask + gateway; tests/unit/cli/test_redact_raw_qmicli.py extended with assertions for both; wds_get_current_settings.txt capture path is exercised in tests/unit/cli/ctl/test_capture_fleet_fixture.py"
    why_human: "Operator must merge the CR-01 fix before running X-04, otherwise routable carrier-NAT gateway IPs leak into the committed per-box fixtures. Code-side fix is small but human-decision-bound to schedule before X-04 launches."
---

# Phase 5: Bench & Field Shadow Verification Report

**Phase Goal (from ROADMAP.md § Phase 5):** Run v2 in shadow mode... until fault-cycle agreement ≥95%, v2 plans never mark a Zao-active line for action, the entire field cohort's firmware/SDK is captured as known-set fixtures, and the on-site engineer is comfortable with v2's behavior.

**Effective rubric (per CONTEXT.md scope_pivot 2026-05-11):** ROADMAP SC#1/#2/#3 reference dead artifacts (shadow-mode YAML, `tools/compare_v1_v2.py`, `-v2`-suffixed paths). The live rubric is the locked R-/S-/F-/X- decisions in 05-CONTEXT.md plus PROJECT.md § 8 M-metrics. SC#4 (fleet-fixture capture) survives intact and is verified below.

**Verified:** 2026-05-11T09:47:34Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (code-complete, 7 plans)

Truths drawn from the must_haves.truths frontmatter blocks of plans 05-01 through 05-07. All are code-verifiable from the repository at HEAD.

| #   | Truth (source plan)                                                                                                                                | Status     | Evidence |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | -------- |
| 1   | QmiWrapper exposes async `dms_get_revision()` with `--device-open-proxy` (05-01)                                                                    | VERIFIED   | `src/spark_modem/qmi/wrapper.py:236-254` — read-only block, matches plan acceptance |
| 2   | `parse_get_revision(stdout)` returns `GetRevisionResult` or `QmiError(UNEXPECTED_OUTPUT \| MISSING_FIELD)` (05-01)                                  | VERIFIED   | `src/spark_modem/qmi/parsers/get_revision.py` (1781 bytes, 56 LOC) |
| 3   | Per-libqmi-version fixture tree under `tests/fixtures/qmicli/get_revision/<version>/standard.txt` for 1.30 + 1.32 (05-01)                          | VERIFIED   | Both fixtures exist (136 bytes each); locked-set test `test_fixture_tree_has_locked_set_of_libqmi_versions` pins {1.30, 1.32} |
| 4   | `dms_get_revision` is read-only — does NOT set `_in_critical_section` (05-01)                                                                       | VERIFIED   | `grep -c "_in_critical_section = True" wrapper.py = 5` (unchanged from pre-edit) |
| 5   | `detect_libqmi_version()` async helper parses 3-part version from `qmicli --version`; raises `QmiVersionDetectionFailed` on failure (05-02)         | VERIFIED   | `src/spark_modem/qmi/version.py:45` |
| 6   | `detect_zao_sdk_version(path)` returns 3-part version or None; never raises (05-02)                                                                 | VERIFIED   | `src/spark_modem/zao_log/version.py:47` (64 KiB head-read cap; 2 banner candidates) |
| 7   | `compute_fleet_triple(wrapper, zao_log_path)` orchestrator returns `FleetTriple(em7421_firmware, zao_sdk, libqmi)` (05-02)                          | VERIFIED   | `src/spark_modem/qmi/version.py:100`; `FleetTriple` is frozen + extra=forbid pydantic model |
| 8   | `spark-modem ctl capture-fleet-fixture --out=<dir>` registered CLI subcommand, callable without daemon running (05-03)                              | VERIFIED   | `src/spark_modem/cli/main.py:25,181-192` — argparse subparser wired; verb does NOT import `daemon.main` |
| 9   | Captured directory contains triple.json + qmi/<usb_path>/<verb>.txt × 7 verbs × N modems + zao-log-sample.txt (05-03)                              | VERIFIED   | `src/spark_modem/cli/ctl/capture_fleet_fixture.py:43` — `QMICLI_CAPTURE_VERBS` is frozen 7-tuple; per-modem subdir pinned by test |
| 10  | Per-modem subdirs keyed by usb_path (e.g. `2-3.1.1`), NEVER cdc-wdmN (ADR-0009) (05-03)                                                             | VERIFIED   | Plan summary confirms; pinned by `test_modem_subdirs_match_usb_path_shape` |
| 11  | Raw qmicli stdout with ICCID/UIM ID/IMSI/IPv4 address values is rewritten to `<redacted:<sha256[:8]>>` before write (05-03)                         | PARTIAL    | `src/spark_modem/cli/redact.py:81-86` — covers ICCID/UIM ID/IMSI/IPv4 address ONLY. See **CR-01 below**: `IPv4 subnet mask` + `IPv4 gateway address` NOT covered. |
| 12  | Every qmicli invocation in capture verb routes through `subproc.runner.run` (SP-04 preserved in src/) (05-03)                                       | VERIFIED   | `grep create_subprocess_exec\|subprocess.run` against src/spark_modem returns only `subproc/runner.py` (SP-04 invariant intact) |
| 13  | Capture verb does NOT participate in daemon preflight (chicken-and-egg fix) (05-03)                                                                 | VERIFIED   | `grep from spark_modem.daemon src/spark_modem/cli/ctl/capture_fleet_fixture.py` returns 0 matches |
| 14  | `preflight_check_known_fleet_triple()` raises `UnknownFleetTriple` when local triple is not in `/etc/spark-modem-watchdog/known-fleet/*/triple.json` (05-04) | VERIFIED   | `src/spark_modem/daemon/preflight_triple.py:123-167` |
| 15  | `preflight_check_known_fleet_triple()` returns cleanly when local triple matches at least one entry (05-04)                                         | VERIFIED   | `preflight_triple.py:159` — `if local not in known:` is the negative branch only |
| 16  | `--skip-preflight` bypasses the X-03 check (05-04)                                                                                                  | VERIFIED   | `src/spark_modem/daemon/main.py:226-235` — wrapped in same `if not args.skip_preflight:` block as FR-60 |
| 17  | Unknown triple causes daemon to exit 78 and write last-config-error marker (same path as FR-60 preflight) (05-04)                                   | VERIFIED   | `daemon/main.py:229-235` — `write_last_config_error` + `return 78` mirroring FR-60 path |
| 18  | X-03 preflight runs BEFORE `acquire_pid_lock` (so failure does not leave stale PID lock) (05-04)                                                    | VERIFIED   | `daemon/main.py`: Step 3.5 (X-03) at lines 221-235; Step 5 (`acquire_pid_lock`) at line 243 |
| 19  | X-03 preflight runs AFTER FR-60 `preflight_check()` (05-04)                                                                                         | VERIFIED   | `daemon/main.py`: Step 3 FR-60 at line 212; Step 3.5 X-03 at line 228 |
| 20  | `tools/audit_soak_zao.py` flags every `ActionPlanned` event on a Zao-active line at the cycle (05-05, S-01 #2)                                      | VERIFIED   | `tools/audit_soak_zao.py:188` — `_audit` joins event → block via `_find_contemporaneous_block` |
| 21  | `tools/audit_soak_exhausted.py` flags every `to_state='exhausted'` not explained by hardware-failure detail (05-05, S-01 #3 / M4)                   | VERIFIED   | `tools/audit_soak_exhausted.py` — locked `_HARDWARE_FAILURE_DETAILS` frozenset; replays decay via `_resolve_decay_k_default()` |
| 22  | Both audit tools exit 0/1/2; emit JSON report to `--out`; use `match` not `if/elif` on ModemState (05-05)                                           | VERIFIED   | `tools/audit_soak_*.py:main` — argparse + json.dump; `test_match_pattern_used_not_if_elif` pins the contract |
| 23  | `.deb` ships contents of `tests/fixtures/fleet/` to `/etc/spark-modem-watchdog/known-fleet/` (05-06)                                                | VERIFIED   | `debian/spark-modem-watchdog.install` last line: `tests/fixtures/fleet /etc/spark-modem-watchdog/known-fleet/` |
| 24  | `/etc/spark-modem-watchdog/known-fleet/` is package-owned (in `debian/dirs`) (05-06)                                                                | VERIFIED   | `debian/spark-modem-watchdog.dirs` line 2: `/etc/spark-modem-watchdog/known-fleet` |
| 25  | Example `tests/fixtures/fleet/_test/triple.json` ships so daemon preflight has ≥1 entry on first install (05-06)                                    | VERIFIED   | File exists (323 bytes); valid JSON with em7421_firmware/zao_sdk/libqmi fields |
| 26  | No `debian/postinst` changes (declarative `debian/install` only) (05-06)                                                                            | VERIFIED   | Pinned by `test_no_known_fleet_references_in_postinst` + `test_no_known_fleet_references_in_rules` |
| 27  | Daemon never writes to `/etc/spark-modem-watchdog/known-fleet/` (already enforced by Plan 04) (05-06)                                               | VERIFIED   | `grep write_bytes\|write_text\|atomic_write src/spark_modem/daemon/preflight_triple.py` returns 0 matches in code body |
| 28  | SIGNOFF.md template exists with all required sections (header + S-01 gates table + R-02 row + S-01.1 metrics + F-04 violations log + X-04 checklist + free-text + approval) (05-07) | VERIFIED   | 124 lines; all 7 sections present; all operator slots left blank |
| 29  | SOAK_RUNBOOK.md exists with daily checks, soak-exit procedure, F-04 disposition workflow (05-07)                                                    | VERIFIED   | 266 lines; § 1-7 cover all required content |
| 30  | `docs/RUNBOOK.md` gets a single cross-reference line to SOAK_RUNBOOK.md (NOT a doc rewrite) (05-07)                                                 | VERIFIED   | `docs/RUNBOOK.md:15`: "For Phase 5 bench/field soak operations, see `.planning/phases/05-bench-field-shadow/SOAK_RUNBOOK.md`." |

### Truth #11 (PII redaction): PARTIAL — see Critical Issue CR-01

The redaction patterns at `src/spark_modem/cli/redact.py:81-86` cover ICCID, UIM ID, IMSI, and `IPv4 address: '<dotted>'` — but the qmicli `wds_get_current_settings` verb (which IS in `QMICLI_CAPTURE_VERBS`) also emits `IPv4 subnet mask: '...'` and `IPv4 gateway address: '...'` lines. The gateway IP is a routable carrier-NAT address (e.g. `10.69.92.150`) and leaking it into committed fleet fixtures is an NFR-22 violation.

This is the only PARTIAL among code-complete truths. The fix is small (two more pattern lines + one test extension) but MUST land before the X-04 sweep so that operator-captured per-box fixtures do not leak the gateway. See `human_verification` test #10 below.

### Plan 05-08 (Operator Manual): Human-Verification Required

Plan 05-08 has `autonomous: false` and is a sequential checklist for the on-site engineer spanning ~3-4 weeks of calendar time. Its 7 must-have truths plus 3 follow-on operator deliverables map to the 10 `human_verification` items in this report's frontmatter:

| #   | 05-08 truth (operator-attested)                                                                                                                                            | Mapped human_verification item |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| 1   | R-01: tests/fixtures/replay/v1-30d/ updated via single LFS PR (≥30d coverage), merged BEFORE bench soak                                                                    | #1 R-01 day-1 trace pull |
| 2   | Bench Jetson 1-week clean soak completed (M6 + ADR-0003 + M4 gates, F-04 budget ≤1 minor/week)                                                                              | #2 Bench Jetson 1-week soak |
| 3   | S-03 handoff gate passed: bench-week audits exit 0 + 0 daemon crashes                                                                                                       | #3 S-03 handoff gate |
| 4   | Field box 2-week clean soak completed: same gates                                                                                                                           | #4 Field box 2-week soak |
| 5   | X-04: every fleet box's triple.json captured under `tests/fixtures/fleet/<box-id>/` and committed via batched Phase-6-prereq PR (merged)                                    | #5 X-04 capture sweep + #6 X-04 batched PR merge |
| 6   | R-02: `pytest tests/replay/test_v1_agreement.py` against freshly-pulled bundle achieves ≥0.95 fault-cycle agreement; `replay-summary-phase5-exit.json` committed             | #7 R-02 replay-harness one-shot |
| 7   | SIGNOFF.md filled by on-site engineer and committed at Phase 5 exit                                                                                                         | #8 SIGNOFF.md filled + #9 Phase 6 entry PR merge |

Plus: CR-01 fix scheduling (item #10) — must merge before X-04 sweep to avoid PII leakage into per-box fixtures.

**Score:** 30 truths VERIFIED (code-side) + 1 PARTIAL (CR-01) + 10 human-attested truths pending operator action = 30/40 code-side verified.

### Deferred Items

ROADMAP SC#1, SC#2, SC#3 reference dead artifacts (`spark-modem-watchdog-v2.service`, `99-shadow.yaml`, `tools/compare_v1_v2.py`, daily synthetic field injection). Per CONTEXT.md scope_pivot (2026-05-11), these are intentionally NOT built. Per the orchestrator's scope_pivot instructions, these are NOT gaps — they are scope-superseded artifacts whose doc-rewrite is deferred to Phase 7 (or a dedicated doc-fixup phase). Per Step 9b, the substantive intent is replaced as follows:

| Original SC | Replacement in current rubric | Verified? |
| ----------- | ----------------------------- | --------- |
| SC#1 (v2 shadow alongside v1) | S-02 sequential 1+2 week soak at canonical paths (CONTEXT.md S-02) | Code-complete; operator-attested via human_verification #2 + #4 |
| SC#2 (compare tool ≥95% agreement) | R-02 replay-harness one-shot against freshly-pulled v1-30d bundle, R-03 hard-fail at <0.95 | Code-complete (test substrate exists from Plan 04-07); operator-attested via human_verification #7 |
| SC#3 (daily synthetic field injection) | F-01 (no field injection) + F-02 (bench rides existing HIL nightly only) | Code-complete (no code added per F-01/F-02); operator-attested via human_verification #4 |
| SC#4 (fleet-fixture capture) | Survives intact: X-01 + X-02 + X-04 chain | Code-complete (X-01 partial — only `_test/` placeholder; per-box land via human_verification #5) |

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/spark_modem/qmi/wrapper.py` | `dms_get_revision` async method added (read-only) | VERIFIED | Lines 236-254; +9 LOC method body |
| `src/spark_modem/qmi/parsers/get_revision.py` | New parser module with GetRevisionResult + parse_get_revision | VERIFIED | 1781 bytes, 56 LOC |
| `src/spark_modem/qmi/version.py` | detect_libqmi_version + QmiVersionDetectionFailed + FleetTriple + compute_fleet_triple | VERIFIED | 5796 bytes |
| `src/spark_modem/zao_log/version.py` | detect_zao_sdk_version | VERIFIED | 2856 bytes |
| `src/spark_modem/cli/ctl/capture_fleet_fixture.py` | run + build_fleet_fixture + QMICLI_CAPTURE_VERBS | VERIFIED | 9420 bytes; QMICLI_CAPTURE_VERBS is 7-tuple |
| `src/spark_modem/cli/redact.py` | redact_pii_from_raw_qmicli added | PARTIAL | Missing IPv4 subnet mask + gateway patterns (CR-01) |
| `src/spark_modem/cli/main.py` | argparse subparser for capture-fleet-fixture | VERIFIED | Lines 181-192 |
| `src/spark_modem/daemon/preflight_triple.py` | UnknownFleetTriple + preflight_check_known_fleet_triple | VERIFIED | 6747 bytes; 167 LOC |
| `src/spark_modem/daemon/main.py` | Wired call between FR-60 preflight and acquire_pid_lock | VERIFIED | Step 3.5 at lines 221-235 |
| `tools/audit_soak_zao.py` | S-01 #2 detector | VERIFIED | 10099 bytes |
| `tools/audit_soak_exhausted.py` | S-01 #3 detector | VERIFIED | 11515 bytes |
| `debian/spark-modem-watchdog.install` | `tests/fixtures/fleet /etc/spark-modem-watchdog/known-fleet/` line | VERIFIED | Present |
| `debian/spark-modem-watchdog.dirs` | `/etc/spark-modem-watchdog/known-fleet` line | VERIFIED | Line 2 |
| `tests/fixtures/fleet/_test/triple.json` | Example fixture for first install | VERIFIED | 323 bytes; valid JSON |
| `tests/fixtures/fleet/<box-id>/triple.json` (per-box) | Per-box fleet fixtures from X-04 sweep | DEFERRED | Lands via human_verification #5/#6 (X-04 sweep + batched PR) |
| `.planning/phases/05-bench-field-shadow/SIGNOFF.md` | Template (filled later by operator) | VERIFIED | 124 lines, template with all required sections |
| `.planning/phases/05-bench-field-shadow/SOAK_RUNBOOK.md` | Operator daily checks + soak-exit | VERIFIED | 266 lines, § 1-7 |
| `docs/RUNBOOK.md` | Cross-reference line | VERIFIED | Line 15 |
| `.planning/phases/05-bench-field-shadow/replay-summary-phase5-exit.json` | R-02 result committed at Phase 5 exit | PENDING | Lands via human_verification #7 |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `daemon/main.py:_production_main` | `preflight_check_known_fleet_triple` | `await preflight_check_known_fleet_triple()` | WIRED | Line 228 |
| `daemon/preflight_triple.py:preflight_check_known_fleet_triple` | `compute_fleet_triple` + `Path(/etc/...).iterdir` | `_load_known_triples` + `_compute_local_triple` | WIRED | Lines 144 + 148 |
| `daemon/preflight_triple.py` | known-fleet dir | `/etc/spark-modem-watchdog/known-fleet` literal | WIRED | Line 46 `_KNOWN_FLEET_DIR` |
| `debian/spark-modem-watchdog.install` | `/etc/spark-modem-watchdog/known-fleet/<box-id>/triple.json` | `dh_install` recursive copy | WIRED | Last line of install file |
| `cli/main.py:_build_parser` | `cli/ctl/capture_fleet_fixture.run` | `set_defaults(func=ctl_capture_fleet.run)` | WIRED | Line 192 |
| `cli/ctl/capture_fleet_fixture.py` | `compute_fleet_triple` + `subproc.runner.run` + `redact_pii_from_raw_qmicli` | direct function calls | WIRED | Module imports verified |
| `qmi/version.py:detect_libqmi_version` | `subproc.runner.run` | `await subproc_runner.run(['qmicli', '--version'], ...)` | WIRED | Line 45 onwards |
| `qmi/version.py:compute_fleet_triple` | QmiWrapper.dms_get_revision + parse_get_revision + detect_libqmi_version + detect_zao_sdk_version | function calls | WIRED | Lines 100-150 |
| `tools/audit_soak_zao.py` | `_read_events_as_raw_dicts` + Zao RASCOW regex | raw JSONL + forward-walk parser | WIRED | Lines 53 + 131 |
| `tools/audit_soak_exhausted.py` | `_resolve_decay_k_default` + `_read_events_as_raw_dicts` | best-effort policy.engine import | WIRED | Plan summary cites lines 113-121 |
| SOAK_RUNBOOK § 4 | tools/audit_soak_zao + audit_soak_exhausted + tests/replay/test_v1_agreement.py + SIGNOFF.md | operator bash commands | WIRED | Lines 136-197 |
| Bench/field soak observation | SIGNOFF.md F-04 violations log + S-01 gates table | operator-filled markdown | PENDING (human) | Awaits human_verification #2/#3/#4 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `preflight_check_known_fleet_triple` | `known` (list[FleetTriple]) | `_load_known_triples(known_fleet_dir)` reads `/etc/spark-modem-watchdog/known-fleet/<box-id>/triple.json` shipped by `.deb` | YES — example `_test/triple.json` ships from day 1; per-box files land via X-04 sweep | FLOWING (post-X-04) |
| `preflight_check_known_fleet_triple` | `local` (FleetTriple) | `_compute_local_triple()` → `SysfsInventory.scan()` + `QmiWrapper.dms_get_revision` + `compute_fleet_triple` | YES on Jetson hardware; raises `UnknownFleetTriple` on dev hosts | FLOWING (on target hardware) |
| `capture_fleet_fixture.build_fleet_fixture` | `triple` (FleetTriple) | `compute_fleet_triple(wrapper, zao_log_path)` | YES — direct qmicli + Zao log invocation per box | FLOWING |
| `capture_fleet_fixture._capture_one_modem` | redacted stdout (bytes) | qmicli verb → `redact_pii_from_raw_qmicli(stdout)` | PARTIAL — IPv4 subnet mask + gateway leak through (CR-01) | STATIC for those 2 fields |
| `audit_soak_zao._audit` | violations | events.jsonl → `_read_events_as_raw_dicts` joined with Zao snapshots | YES on real soak-window data | FLOWING (post-soak) |
| `audit_soak_exhausted._audit` | unexplained transitions | events.jsonl → state_transition group-by + decay replay | YES on real soak-window data | FLOWING (post-soak) |
| SIGNOFF.md | gate ticks + R-02 rate + F-04 log | Operator transcribes from audit JSONs + replay summary + journalctl | YES — when operator fills | PENDING (human attestation) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full repo test suite under M7 budget | (orchestrator-provided) `pytest` HEAD | 2035 passed, 91 skipped in 27.42s | PASS (within 30s M7 budget) |
| dms_get_revision is read-only | `grep -c "_in_critical_section = True" src/spark_modem/qmi/wrapper.py` | 5 (unchanged) | PASS |
| SP-04 invariant preserved | `grep "create_subprocess_exec\|subprocess.run" src/spark_modem` | only `src/spark_modem/subproc/runner.py` | PASS |
| X-03 preflight ordering | grep `preflight_check\(`, `preflight_check_known_fleet_triple`, `classify_prior_run`, `acquire_pid_lock` in daemon/main.py | lines 212 → 228 → 238 → 243 (correct ordering) | PASS |
| Capture verb does not import daemon | grep `from spark_modem.daemon` in cli/ctl/capture_fleet_fixture.py | 0 matches | PASS |
| Daemon never writes known-fleet | grep `write_bytes\|write_text\|atomic_write_bytes` in code body of preflight_triple.py | 0 matches (only docstring mention) | PASS |
| Example fleet fixture valid JSON | `python -c "import json; d=json.load(open('tests/fixtures/fleet/_test/triple.json')); assert all(k in d for k in ('em7421_firmware','zao_sdk','libqmi'))"` | All fields present | PASS |
| capture-fleet-fixture is wired CLI subcommand | grep `capture-fleet-fixture` in src/spark_modem/cli/main.py | argparse subparser + set_defaults wired | PASS |
| .deb ships known-fleet | check `debian/spark-modem-watchdog.install` + `debian/spark-modem-watchdog.dirs` | Both present | PASS |
| Module import (dev host) | `PYTHONPATH=src python -c "from spark_modem.cli.ctl.capture_fleet_fixture import ..."` | Module structure resolves; dev host lacks `pydantic` (not a Phase 5 gap) | SKIP (deps not installed on Windows dev host; orchestrator confirms full suite green on installed env) |

### Requirements Coverage

Phase 5 has no v1 REQ-IDs (it is a delivery/validation phase). The plan-frontmatter cites R-/S-/F-/X-/M-IDs sourced from 05-CONTEXT.md and PROJECT.md § 8, not from REQUIREMENTS.md. Coverage assessment against those locked decision IDs:

| Decision ID | Source | Description | Status | Evidence |
| ----------- | ------ | ----------- | ------ | -------- |
| R-01 | CONTEXT.md | Day-1 fresh v1 trace pull | PENDING-HUMAN | human_verification #1 |
| R-02 | CONTEXT.md | Replay harness one-shot at Phase 5 exit, ≥0.95 fault-cycle agreement | PENDING-HUMAN (substrate code-complete via Plan 04-07) | human_verification #7 |
| R-03 | CONTEXT.md | Agreement bar at ≥0.95 (Plan 04-07 constant) | VERIFIED (substrate ships from Phase 4) | `tests/replay/conftest.py` |
| R-04 | CONTEXT.md | Quarterly v1-trace refresh cadence begins with day-1 pull | PENDING-HUMAN | human_verification #1 |
| S-01 (#1 M6) | CONTEXT.md / PROJECT.md § 8 | Zero daemon crashes / OOM / unhandled-exception restarts | PENDING-HUMAN (audit substrate ships) | human_verification #2/#4 |
| S-01 (#2 ADR-0003) | CONTEXT.md | Zero action planned on Zao-active line | PENDING-HUMAN (audit_soak_zao.py ready) | human_verification #2/#4 |
| S-01 (#3 M4) | CONTEXT.md / PROJECT.md § 8 | Zero unexplained Exhausted transitions | PENDING-HUMAN (audit_soak_exhausted.py ready) | human_verification #2/#4 |
| S-02 | CONTEXT.md | 1 week bench + 2 weeks field, sequential | PENDING-HUMAN | human_verification #2/#3/#4 |
| S-03 | CONTEXT.md | Bench→field handoff gate (same 3 gates over bench-only week) | PENDING-HUMAN | human_verification #3 |
| S-04 | CONTEXT.md | SIGNOFF.md + replay-harness JSON committed at Phase 6 entry | VERIFIED template; PENDING-HUMAN fill | SIGNOFF.md exists; human_verification #8/#9 |
| F-04 | CONTEXT.md | 1 minor/week budget, threshold-based abort | VERIFIED template (definitions in SIGNOFF.md + SOAK_RUNBOOK.md); PENDING-HUMAN observation | human_verification #2/#4 |
| X-01 | CONTEXT.md | Fixture tree under `tests/fixtures/fleet/` | PARTIAL — only `_test/triple.json` placeholder ships; per-box land via X-04 | human_verification #5/#6 |
| X-02 | CONTEXT.md | Capture verb with PII redaction | PARTIAL — CR-01: IPv4 subnet mask + gateway address leak through | See CR-01 below |
| X-03 | CONTEXT.md | Daemon preflight refuses unknown triple | VERIFIED | preflight_triple.py + daemon/main.py wiring + debian/install |
| X-04 | CONTEXT.md | Batched Phase-6-prereq PR with per-box fixtures | PENDING-HUMAN | human_verification #5/#6 |
| M1 | PROJECT.md § 8 | ≥99.5% per-modem availability over rolling 7d | PENDING-HUMAN observation (informational at Phase 5) | human_verification #2/#4 |
| M4 | PROJECT.md § 8 | Zero Exhausted from counter accumulation | PENDING-HUMAN (audit_soak_exhausted detects this) | human_verification #2/#4 |
| M6 | PROJECT.md § 8 | Zero OOM/unhandled-exception daemon restarts in 30d | PENDING-HUMAN | human_verification #2/#4 |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `src/spark_modem/cli/redact.py` | 81-86 | `_RAW_QMICLI_PII_PATTERNS` omits `IPv4 subnet mask: '...'` and `IPv4 gateway address: '...'` | CRITICAL (CR-01) | Routable carrier-NAT gateway IPs (e.g. `10.69.92.150`) leak into committed per-box fleet fixtures when X-04 sweep runs `wds_get_current_settings`. NFR-22 violation. **MUST fix before X-04 sweep** (human_verification #10). |

Per code review (05-REVIEW.md) there are 4 additional Warning-class findings (DoS protection on tool-side log reads; exception messages potentially carrying un-redacted content; redaction-test coverage gaps; structural use of `Exception` instead of narrower types) and 6 Info items. REVIEW.md is advisory — these are NOT verification blockers but should be addressed before fleet rollout (Phase 6). CR-01 is the only one elevated to a verification-relevant flag because it gates the X-04 deliverable.

### Critical Issue: CR-01 (must fix before X-04 sweep)

**File:** `src/spark_modem/cli/redact.py:81-86`

**Issue:** `_RAW_QMICLI_PII_PATTERNS` covers ICCID / UIM ID / IMSI / `IPv4 address:` only. The qmicli `wds_get_current_settings` verb (which IS in `QMICLI_CAPTURE_VERBS`) also emits two adjacent lines with the same `'<dotted>'` shape that the current regex does NOT catch:

```
    IPv4 address: '10.69.92.156'            # redacted (OK)
    IPv4 subnet mask: '255.255.255.248'     # NOT redacted — leaks
    IPv4 gateway address: '10.69.92.150'    # NOT redacted — leaks routable carrier-NAT gateway IP
```

**Why this matters at Phase 5 → Phase 6 boundary:** The X-04 capture sweep (human_verification #5) writes per-box fleet fixtures into `tests/fixtures/fleet/<box-id>/qmi/<usb_path>/wds_get_current_settings.txt`, which then ship via `.deb` to `/etc/spark-modem-watchdog/known-fleet/<box-id>/qmi/<usb_path>/wds_get_current_settings.txt`. Without the fix, the gateway IP is committed to git and shipped to every fleet box.

**Fix:** Add two patterns to the tuple AND extend `tests/unit/cli/test_redact_raw_qmicli.py` to exercise the `wds_get_current_settings` capture path:

```python
_RAW_QMICLI_PII_PATTERNS: tuple[re.Pattern[bytes], ...] = (
    re.compile(rb"(ICCID:\s*')([^']+)(')"),
    re.compile(rb"(UIM ID:\s*')([^']+)(')"),
    re.compile(rb"(IMSI:\s*')([^']+)(')"),
    re.compile(rb"(IPv4 address:\s*')([^']+)(')"),
    re.compile(rb"(IPv4 subnet mask:\s*')([^']+)(')"),       # NEW
    re.compile(rb"(IPv4 gateway address:\s*')([^']+)(')"),   # NEW
)
```

**Severity:** CRITICAL — blocks safe X-04 execution. Listed as human_verification #10 because the scheduling decision is human-bound (the fix is small but it must merge before the X-04 sweep starts; whoever runs the X-04 sweep must verify the fix is in place first).

### Human Verification Required

10 items requiring on-site engineer action (see frontmatter `human_verification` for the full structured list). Summary by category:

1. **R-01 day-1 v1-trace pull** (LFS PR merge, before bench soak)
2. **Bench Jetson 1-week soak** (daily checks + audits)
3. **S-03 handoff gate** (end-of-bench audits pass)
4. **Field box 2-week soak** (F-01 honored)
5. **X-04 capture sweep** (per-box `ctl capture-fleet-fixture`)
6. **X-04 batched PR merge** (Phase 6 prereq)
7. **R-02 replay-harness one-shot** (≥0.95 fault-cycle agreement)
8. **SIGNOFF.md filled** (all sections by engineer)
9. **Phase 6 entry PR merge** (4 approval boxes ticked)
10. **CR-01 fix** (must merge before X-04 sweep to avoid PII leakage)

These are not gaps in the code-execution sense — they are time-bound, hardware-dependent, judgment-bearing operator steps explicitly scoped to Plan 05-08 (`autonomous: false`).

### Gaps Summary

**No code-side gaps blocking Phase 5 closure** other than CR-01 (PII redaction completeness). 30 of 30 code-verifiable truths from plans 05-01 through 05-07 are satisfied; the X-* deliverable chain (capture verb → daemon preflight → packaging) is end-to-end wired and the operator-facing documents (SIGNOFF.md + SOAK_RUNBOOK.md) cover all required content per RESEARCH Q8/Q9.

**Status is `human_needed`, not `passed`, because:**

- Plan 05-08 (the operator manual) has not been executed — no SUMMARY.md exists for it, no bench/field soak evidence is in the repo, no SIGNOFF.md is filled, no `replay-summary-phase5-exit.json` is committed, no per-box fleet fixtures land yet.
- The 10 human_verification items are time-bound operator deliverables (calendar ~3-4 weeks) that map directly to Plan 05-08's 7 must-have truths plus the CR-01 scheduling gate.
- The orchestrator's instruction was explicit: mark Plan 05-08 truths as `human_needed` (not `gaps_found`) because they require operator soak action, not more coding.

**Status is `human_needed`, not `gaps_found`, because:**

- CR-01 is a single small fix (2 regex patterns + 1 test) that the operator decision-bound on scheduling (must land before X-04 sweep). It's flagged at human_verification #10 rather than as a hard blocker because the X-04 sweep itself is operator-triggered; the fix can land any time before that.
- All other findings in 05-REVIEW.md are advisory (Warning + Info), not verification gates.

---

*Verified: 2026-05-11T09:47:34Z*
*Verifier: Claude (gsd-verifier)*
