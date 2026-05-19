---
id: S05
parent: M001
milestone: M001
provides:
  - QmiWrapper.dms_get_revision() async method (read-only, --device-open-proxy, _DEFAULT_TIMEOUT_S=8s, routes through subproc.runner)
  - parsers.get_revision module exporting GetRevisionResult (frozen pydantic model, extra='ignore') and parse_get_revision(stdout) function
  - tests/fixtures/qmicli/get_revision/{1.30,1.32}/standard.txt — per-libqmi-version sample fixtures
  - Locked fixture-tree set assertion (1.30 + 1.32) preventing accidental version deletion
  - detect_libqmi_version() async helper — parses qmicli --version stdout for libqmi-glib 3-part version; raises QmiVersionDetectionFailed on any failure path; routes through subproc.runner.run (SP-04)
  - QmiVersionDetectionFailed RuntimeError subclass — matches PreflightFailed shape (N818 noqa + plan-acceptance-fixed name)
  - detect_zao_sdk_version(path) helper — scans first 64 KiB of a Zao log for one of two banner shapes; returns 3-part version string or None; never raises (FileNotFoundError + OSError both downgrade to None with WARNING log)
  - FleetTriple pydantic BaseModel (frozen + extra=forbid) — byte-reproducible (em7421_firmware, zao_sdk, libqmi) wire shape; consumed by capture-fleet-fixture CLI (Plan 05-03) and preflight_check_known_fleet_triple (Plan 05-04)
  - compute_fleet_triple(wrapper, zao_log_path) async orchestrator — single seam composing the three probes; "unknown" sentinel for SDK absent; QmiError on dms_get_revision surfaces as QmiVersionDetectionFailed (preflight needs failure to surface)
  - redact_pii_from_raw_qmicli(stdout: bytes) -> bytes — raw-qmicli-stdout redaction helper. Four patterns: ICCID, UIM ID, IMSI, IPv4 address. Determinism preserved (same input -> same output bytes; same value across files yields same <redacted:<hash>> token).
  - spark_modem.cli.ctl.capture_fleet_fixture module — operator-facing CLI verb (X-01 / X-02 deliverable). Exports build_fleet_fixture, run, QMICLI_CAPTURE_VERBS.
  - QMICLI_CAPTURE_VERBS — frozen 7-tuple lock pinned by test_qmicli_capture_verbs_list_is_locked_at_7. Adding/removing a verb is a deliberate change.
  - tests/fixtures/fleet/_test/triple.json — example fleet fixture (RESEARCH Q10 §752) committed in this plan so the directory layout is checked into git from day 1.
  - tests/fixtures/qmicli/uim_get_card_status/1.30/with_iccid.txt — synthetic uim_get_card_status stdout used by the redaction tests (ICCID x3 + IMSI x1 — same value under three labels: UIM ID, ICCID, ICCID).
  - UnknownFleetTriple exception class — RuntimeError subclass; matches PreflightFailed shape (N818 noqa)
  - _load_known_triples(known_fleet_dir: Path) -> list[FleetTriple] — walks <box-id>/triple.json one level deep; skips + warns on malformed entries; never raises
  - _compute_local_triple(*, zao_log_path) async helper — probes SysfsInventory + first descriptor's QmiWrapper.dms_get_revision + Zao log banner via compute_fleet_triple; raises UnknownFleetTriple on no-modems or QmiVersionDetectionFailed
  - preflight_check_known_fleet_triple(*, known_fleet_dir, zao_log_path, local_triple=None) async function — X-03 gate. local_triple=None triggers the production probe path; tests inject directly.
  - daemon/main.py wiring — preflight_check_known_fleet_triple slotted between FR-60 preflight_check (Step 3) and acquire_pid_lock (Step 5); shares --skip-preflight bypass with FR-60 check
  - tools/audit_soak_zao.py — S-01 #2 detector (exit 1 when any ActionPlanned event fired on a Zao-active line)
  - tools/audit_soak_exhausted.py — S-01 #3 detector (exit 1 when any Exhausted transition is unexplained by hardware-failure detail or insufficient healthy-streak)
  - tests/unit/tools/ — new test sub-package (12 tests, ~0.5s)
  - debian/spark-modem-watchdog.install +1 line: tests/fixtures/fleet /etc/spark-modem-watchdog/known-fleet/ — dh_install recursively copies the fleet fixture tree at .deb build time
  - debian/spark-modem-watchdog.dirs +1 line: /etc/spark-modem-watchdog/known-fleet — package-owned directory created before dh_install (so dpkg owns even an empty dir)
  - tests/integration/test_deb_ships_known_fleet.py (124 LOC, 6 tests) — pins the packaging contract: 5 always-on static checks + 1 dpkg-deb --contents check skipped on hosts without dpkg-deb
  - Stub completion marker so GSD tracking can advance past Plan 05-08.
  - Explicit pointer to .planning/phases/05-bench-field-shadow/05-HUMAN-UAT.md as the live tracking surface for the 10 operator-bound items.
requires: []
affects: []
key_files: []
key_decisions:
  - dms_get_revision is a read-only verb — does NOT set _in_critical_section (count of _in_critical_section = True occurrences unchanged at 5)
  - parse_get_revision preserves case on the revision string (NOT lowercased) — firmware identifiers like SWI9X30C_02.38.00.00 are case-sensitive; deliberate deviation from the get_operating_mode analog which lowercases mode
  - Per-libqmi-version fixture tree (1.30 + 1.32) mirrors get_operating_mode and get_signal layouts byte-for-byte (TABs between key/value, single trailing newline, # libqmi_version: <ver> header line)
  - Locked-set assertion on the fixture tree — adding a new libqmi version is a deliberate extension; deleting one is caught as a regression by test_fixture_tree_has_locked_set_of_libqmi_versions
  - compute_fleet_triple takes wrapper: object (duck-typed) NOT a QmiWrapper Protocol — avoids the qmi/wrapper.py → qmi/errors.py → subproc/ import cycle that would emerge if version.py grew a Protocol seam alongside its existing qmi/errors.py + parsers/get_revision.py + subproc/ imports; the production QmiWrapper.dms_get_revision (Plan 05-01) already satisfies the structural requirement
  - _ZAO_SDK_UNKNOWN_SENTINEL is the literal string 'unknown' (not None, not Optional) on the FleetTriple wire — RESEARCH Q3 fallback policy materialised; preflight (X-03) decides fail-closed semantics, capture (X-02) records for operator follow-up; preserves byte-reproducibility for the X-03 lookup hash
  - FleetTriple uses frozen=True + extra='forbid' verbatim (not BaseWire from spark_modem/wire/_base.py) — version.py imports qmi/errors.py, parsers/get_revision.py, subproc/, AND zao_log/version.py already; adding wire/_base.py would deepen the chain unnecessarily and the model_config = ConfigDict(frozen=True, extra='forbid') inline is two lines; the W-02 wire discipline (frozen + forbid) is preserved by direct ConfigDict use
  - QmiError surfaces as QmiVersionDetectionFailed (raise, not return) on the firmware probe path — daemon preflight (X-03) needs the failure to surface; a silent fallback to 'unknown' for em7421_firmware would defeat the entire purpose of the known-fleet-triple gate
  - QmiVersionDetectionFailed subclasses RuntimeError (matches PreflightFailed shape per CONTEXT.md X-03 — N818 noqa for the public-name-fixed-by-plan-acceptance convention); does NOT subclass PreflightFailed itself (different module, different exit-code semantics; Plan 05-04 will compose them at the preflight call site)
  - Two Zao banner regex candidates (modern post-2.0 zao_remote_endpoint/X.Y.Z first, legacy zao-remote-endpoint X.Y.Z second) — locked priority order; first-match-wins ordering pinned by test_first_match_wins; deferred dpkg-query subprocess fallback (RESEARCH Q3 §295) to a future ADR if banner-absent becomes a fleet-wide observation
  - UIM ID added alongside ICCID in the redaction pattern set (Rule 2 deviation from plan-text §216-228 which only specified ICCID/IMSI/IPv4). Real qmicli uim_get_card_status stdout carries the ICCID value under BOTH `UIM ID:` and `ICCID:` labels (verified via the synthetic fixture and existing tests/fixtures/qmicli/get_sim_state/1.30/*.txt fixtures); omitting UIM ID would leak the same identifier under a different label. The pattern is `(UIM ID:\\s*')([^']+)(')` — same shape as the other three.
  - QMICLI_CAPTURE_VERBS list locked at exactly 7 (CONTEXT.md X-02 §163-170 upper-bound was 8). Dropped: `wds_get_packet_service_status` (datapath state is volatile and depends on network conditions at capture time, not box config — not useful for triple-matching/fixture coverage). Lock pinned by test_qmicli_capture_verbs_list_is_locked_at_7.
  - build_fleet_fixture is the orchestrator seam (sync-friendly, dependency-injected via descriptors + zao_log_path + box_id). `run()` is the argparse dispatcher and the only place SysfsInventory is constructed — keeps the orchestrator unit-testable without sysfs.
  - Capture verb does NOT import `daemon.main` (X-03 chicken-and-egg fix — pinned by grep in success_criteria #4). The verb constructs SysfsInventory + QmiWrapper directly; no preflight participation.
  - Re-running capture on the same out_dir is INTENTIONALLY non-idempotent on `first_seen_iso` (datetime.now() per call) but IS idempotent on the identity triple (em7421_firmware/zao_sdk/libqmi). Verified by test_capture_is_idempotent; the operator can re-run capture without worrying about appendix behavior, but timestamps reflect when each capture happened.
  - On-disk triple.json schema is the contract for Plan 05-04 (preflight): schema_version=1, em7421_firmware, zao_sdk, libqmi, first_seen_box_id, first_seen_iso, _comment. ISO timestamp uses `.replace('+00:00', 'Z')` for the canonical 'Z'-suffixed form preflight expects.
  - PII fixture (tests/fixtures/qmicli/uim_get_card_status/1.30/with_iccid.txt) created at this canonical path (NOT under the existing get_sim_state/ tree) so the fixture's purpose is named in its path: it's the canonical input for the PII redaction tests at the X-02 capture seam.
  - UnknownFleetTriple subclasses RuntimeError (NOT PreflightFailed) — matches the shape per CONTEXT.md X-03 and follows Plan 05-02's QmiVersionDetectionFailed convention; different module + different framing means inheritance from PreflightFailed would conflate exit-code semantics. Compose at the call site in daemon/main.py with a sibling try/except block, not via an inheritance chain.
  - Test-injection via local_triple: FleetTriple | None = None — production callers pass None and the function calls _compute_local_triple which hits sysfs + qmicli + Zao log; tests pass local_triple directly. Avoids any need to monkeypatch SysfsInventory / QmiWrapper / compute_fleet_triple in unit tests; mirrors Plan 05-02's wrapper: object duck-typing decision.
  - _load_known_triples is pure I/O (sync, not async) — pathlib operations on local filesystem are fast and the directory has at most ~10 entries (1 per fleet box). Wrapping in asyncio.to_thread would be over-engineering; the production preflight path runs once at startup, before READY=1, so blocking the event loop for ~1ms is acceptable.
  - ValidationError from pydantic FleetTriple construction caught as ValueError (its parent class) in the same except tuple as JSONDecodeError + KeyError — keeps the skip-and-warn branch single-pathed; ValidationError is a ValueError subclass so the same handler runs for missing-required-field + bad-value-type cases.
  - Step 3.5 placement in _production_main — preflight_check_known_fleet_triple runs AFTER FR-60 preflight_check and BEFORE classify_prior_run + acquire_pid_lock. RESEARCH Q4 §307-321 reason: failure must not leave a stale PID lock (lock not yet held); failure must not lose the boot classifier's view of the prior run (classifier runs next; this preflight is just another way to mark CONFIG_INVALID on this boot).
  - Same --skip-preflight guard shared with FR-60 — wrapped inside the existing if not args.skip_preflight: block (preserves spark-modem-watchdog --laptop --skip-preflight workflow on non-Jetson dev hosts). Verified by test_skip_preflight_bypasses_triple_check (Task 2 Test 2).
  - Event shape: plan example used who.usb_path / who.line; actual wire/events.py ActionPlanned + StateTransition variants carry flat usb_path with NO line field (Rule 3 deviation). Audit derives line from the trailing dotted segment of usb_path (2-3.1.N -> N).
  - _DECAY_K_DEFAULT does not exist as a module-level constant in policy/engine.py; the production source-of-truth is Settings.healthy_streak_decay_k (default 10). audit_soak_exhausted ships a 3-tier _resolve_decay_k_default() helper that probes both names before falling back to the literal.
  - Both audit scripts duplicate _read_events_as_raw_dicts rather than sharing a tools/_lib.py — duplication is intentional (deferred shared-helper to Phase 6+); current scope keeps tools/ as a flat directory of standalone one-shot scripts (matches tools/pull_replay_traces.py shape).
  - audit_soak_exhausted hardware-failure detail set is conservative — adding a NEW IssueDetail variant in a future plan will classify a triggered Exhausted as UNEXPLAINED (operator disposition via F-04 audit trail; threat T-05-05-05 accept disposition).
  - Audits are READ-ONLY against events.jsonl + Zao log; never call StateStore.save_* or atomic_write_bytes. Verification grep returns zero matches in both tools.
  - Followed RESEARCH Q10 final recommendation verbatim — ship tests/fixtures/fleet directly as /etc/spark-modem-watchdog/known-fleet/<box-id>/triple.json (no sha-rename, no build-time index synthesis). The daemon's _load_known_triples walks one level deep for triple.json files; this packaging contract feeds that walker exactly the shape it expects.
  - No changes to debian/spark-modem-watchdog.postinst — the existing postinst stays scoped to ModemManager masking + state-dir creation + the B-03 smoke test. Known-fleet shipment is pure data movement; dh_install handles it before postinst runs.
  - No changes to debian/rules — declarative debian/install is the simplest path per RESEARCH Q10 §637. The big override_dh_auto_install block in rules already handles the bundled CPython tree + uv pip install + stdlib trim; adding a known-fleet step there would couple two unrelated concerns.
  - Integration test ships in tests/integration/ alongside test_unit_file_audit.py (cross-platform-safe debian/* parser) rather than under a new tests/packaging/ subtree — the latter would duplicate conftest.py infrastructure for a single test file.
  - 2026-05-11: User explicitly chose to advance Phase 5 in tracking with Plan 05-08 marked Claude-side-complete. Rationale: the plan is by design operator-bound (~3-4 weeks calendar), and VERIFICATION.md is already `status: human_needed` with the 10 operator items persisted in 05-HUMAN-UAT.md. Pending items remain visible via `/gsd-progress` and `/gsd-audit-uat` until the on-site engineer commits SIGNOFF.md.
  - No Claude work was performed for this plan. The plan's own success criteria gate Phase 5 EXIT on the SIGNOFF.md merge — that gate is unchanged and will be enforced at PR-review time, independent of this SUMMARY existing.
patterns_established:
  - TDD discipline at task granularity: separate RED commit (failing tests only) and GREEN commit (implementation that makes tests pass) per task, with the test file and source file landing in different commits
  - tests/unit/qmi/parsers/ as a new sub-package — established to isolate parser-specific tests (focused happy/error paths) from the omnibus tests/unit/qmi/test_parsers.py (fixture-parametrized smoke matrix)
  - Three-source version-detection seam: a single compute_fleet_triple async function orchestrates libqmi (subproc) + Zao SDK (banner regex over file head) + EM7421 firmware (qmicli wrapper via Plan 05-01) into one FleetTriple. This is the seam Plans 05-03 (capture CLI) and 05-04 (daemon preflight) both consume — version-string formatting cannot drift between CLI and daemon.
  - tests/fixtures/qmicli/version/{1.30,1.32}/standard.txt fixture pair — mirrors the existing get_revision/{1.30,1.32}/standard.txt layout from Plan 05-01; the per-libqmi-version fixture tree convention is now uniform across qmicli intents.
  - tests/fixtures/zao_log/version/ new sub-tree under tests/fixtures/zao_log/ — analogous to qmicli/version/; first per-intent split inside zao_log/ (sibling to all_lines_active.log etc. at the parent level).
  - Operator-facing ctl verb that bypasses the daemon (X-03 fix) — capture-fleet-fixture is the first ctl subcommand that runs inventory + QMI probes without daemon coupling. Future X-04/X-05 verbs (e.g. ctl preflight-self-check) can follow the same shape.
  - Sync-helper extraction for ASYNC240 compliance — five small sync functions wrap each pathlib I/O surface; the async caller wraps in `asyncio.to_thread`. Cleaner than per-line `# noqa: ASYNC240` and matches the Phase 4 fault_inject.py + Plan 04-07 HIL scenario pattern.
  - tests/fixtures/fleet/_test/triple.json — first commit under tests/fixtures/fleet/ (the directory layout is now greppable and review-able from day 1); real per-box fixtures land via the X-04 sweep before Phase 6.
  - X-03 preflight is the final gate in the X-* deliverable family (X-01 fixture tree, X-02 capture verb, X-03 known-fleet gate) — the (capture-verb, daemon-preflight) pair forms a complete fleet-coverage loop: engineer captures a triple.json via the Plan 05-03 ctl verb, ships it via dpkg in Plan 05-06, and the daemon refuses to start until that ship completes
  - Plan 05-04 closes the X-* chain end-to-end on the dev host — integration test (`test_matching_triple_passes_preflight`) verifies the round-trip: write triple.json via dict-shaped JSON → _load_known_triples loads it → preflight matches local_triple → daemon proceeds. The contract between Plan 05-03's emit and Plan 05-04's consume is now byte-pinned.
  - tests/unit/tools/ as a new test sub-package — first tests under that path; sibling to tests/unit/qmi/parsers/ (Plan 05-01)
  - tools/ script TDD discipline at task granularity: RED commit (failing tests; tool file absent -> FileNotFoundError) → GREEN commit (implementation that makes the 6 tests pass); test fixture imports via importlib.util.spec_from_file_location because tools/ is not a Python package
  - Plan 05-06 closes the X-* deliverable family on the packaging side — X-01 (capture verb in Plan 05-03), X-02 (PII redaction baked into the verb), X-03 (daemon gate in Plan 05-04 + packaging shipment in Plan 05-06) — every fleet box's first apt install now lands the read-only known-fleet directory the daemon needs
  - Anti-pattern pinning via tests — the two test_no_known_fleet_references_in_{postinst,rules} cases lock the RESEARCH Q10 design choice into the test suite; future refactors that try to migrate known-fleet shipment into postinst or override_dh_auto_install will fail these tests and force a deliberate design revisit
  - Deferred-stub SUMMARY: when a plan is autonomous=false and the entire task list is checkpoint:human-action, the executor records the deferral here and lets HUMAN-UAT.md carry the live state.
observability_surfaces: []
drill_down_paths: []
duration: 0min
verification_result: passed
completed_at: 2026-05-11
blocker_discovered: false
---
# S05: Bench Field Shadow

**# Phase 5 Plan 01: Add `dms_get_revision` QMI verb Summary**

## What Happened

# Phase 5 Plan 01: Add `dms_get_revision` QMI verb Summary

**Added the single qmicli verb Phase 5 needs for fleet-triple capture (EM7421 firmware string) — wrapper method, case-preserving parser, per-libqmi-version fixture tree (1.30 + 1.32), 8 unit tests covering happy/error/cross-version paths.**

## Performance

- **Duration:** ~5 min wall-clock (4 commits across 4m 28s of git activity)
- **Started:** 2026-05-11T11:00:05+03:00 (first task commit)
- **Completed:** 2026-05-11T11:04:33+03:00 (last task commit)
- **Tasks:** 2/2 complete (each as RED+GREEN pair = 4 task-level commits)
- **Files modified:** 6 (1 modified, 5 created)

## Accomplishments

- New `QmiWrapper.dms_get_revision()` async method inserted as the 8th read-only verb at `src/spark_modem/qmi/wrapper.py:236-255`, between `dms_get_operating_mode` (ends 234) and the state-changing-methods block (now 256). Read-only contract verified: does NOT set `_in_critical_section`.
- New `src/spark_modem/qmi/parsers/get_revision.py` (56 LOC): `GetRevisionResult` pydantic model (`extra="ignore"`, `frozen=True`) + `parse_get_revision(stdout)` returning `GetRevisionResult` on success or `QmiError(UNEXPECTED_OUTPUT | MISSING_FIELD)` on degenerate inputs. Firmware string is preserved verbatim (NOT lowercased — deliberate deviation from `parse_get_operating_mode`).
- Per-libqmi-version fixture pair at `tests/fixtures/qmicli/get_revision/{1.30,1.32}/standard.txt`, byte-shape identical to the existing `get_operating_mode/1.30/online.txt` (TABs, trailing newline, version-header line). 136 bytes each.
- 8 new tests across 2 files (4 parser core + 2 parser cross-version + 2 wrapper), all green in 0.41s.
- Full repo regression check: `tests/unit/qmi/` 84/84 green; full suite 1973 passed, 90 skipped in 26.25s (within M7 ≤30s budget).
- ruff and `mypy --strict` clean on all changed source files; SP-04 invariant preserved (`grep -r 'create_subprocess_exec' src/spark_modem/ | grep -v subproc/` returns 0 matches).

## Task Commits

Each task was committed atomically as a TDD RED/GREEN pair (per the plan's `tdd="true"` annotation on both tasks):

1. **Task 1 RED: add failing tests for dms_get_revision wrapper + parser** — `1977b67` (test)
2. **Task 1 GREEN: implement dms_get_revision wrapper + parser + libqmi 1.30 fixture** — `03f8f5a` (feat)
3. **Task 2 RED: add failing cross-version drift tests for get_revision parser** — `2d19a61` (test)
4. **Task 2 GREEN: add libqmi 1.32 fixture for get_revision parser** — `419bb53` (feat)

No REFACTOR commit was needed for either task — the GREEN code matched the analog's shape verbatim with the single deliberate deviation (case preservation) documented in-source.

## Files Created/Modified

- `src/spark_modem/qmi/wrapper.py` — added `async def dms_get_revision()` at line 236, immediately after `dms_get_operating_mode` and before the `# ---- state-changing methods` comment (now at line 256). 9-line method body + 6-line docstring.
- `src/spark_modem/qmi/parsers/get_revision.py` — new parser module (56 LOC). Imports mirror `get_operating_mode.py`; only structural differences are `_RESPONSE_HEADER = "Device revisions retrieved"`, `_RE_REVISION = re.compile(r"Revision:\s*'([^']+)'")`, `GetRevisionResult` class name, `revision: str | None = None` field, MISSING_FIELD `field="revision"`, and the in-source comment explaining why the firmware string is NOT lowercased.
- `tests/fixtures/qmicli/get_revision/1.30/standard.txt` — 4-line fixture (libqmi_version banner + response header + Revision/Boot-code lines). 136 bytes.
- `tests/fixtures/qmicli/get_revision/1.32/standard.txt` — byte-identical to 1.30 modulo the version-header banner; locks Phase 5's per-libqmi-version drift contract.
- `tests/unit/qmi/parsers/__init__.py` — empty file, establishes the new test sub-package.
- `tests/unit/qmi/parsers/test_get_revision.py` — 6 tests: happy-path 1.30, UNEXPECTED_OUTPUT, MISSING_FIELD(field='revision'), frozen+extra-ignore behaviour, happy-path 1.32, locked fixture-tree set.
- `tests/unit/qmi/test_wrapper_dms_get_revision.py` — 2 tests: argv shape (--device-open-proxy, --device=<dev>, --dms-get-revision) and read-only `_in_critical_section` contract.

## Decisions Made

- **Read-only verb, no `_in_critical_section` wrapping.** `dms_get_revision` is purely informational (firmware string read); follows the same pattern as `dms_get_operating_mode` / `nas_get_signal_info` / etc. State-changing methods are only the four 4 already in place (`dms_set_operating_mode`, `uim_sim_power_on`, `wds_modify_profile`, `wds_set_ip_family`) + Phase 4's destructive 1 = 5 occurrences of `_in_critical_section = True`. New method preserves that count.
- **Firmware string is NOT lowercased.** `SWI9X30C_02.38.00.00` is a case-sensitive identifier — the parser preserves it verbatim. Deliberate deviation from `parse_get_operating_mode` which lowercases `Mode: 'online'` → `"online"`. Reason called out in an inline comment in `parsers/get_revision.py` so future readers don't "fix" it.
- **Per-libqmi-version fixture pair landed atomically with the parser** rather than only 1.30 in Task 1 + 1.32 deferred. Both versions ship now because Plan 05-04's `preflight_check_known_fleet_triple` will need to test against the cross-version drift contract from day one (closes RESEARCH Q3).
- **Locked-set assertion on fixture tree.** `test_fixture_tree_has_locked_set_of_libqmi_versions` pins `{1.30, 1.32}` so deletion of either is a test failure. Adding a future 1.34 fixture is a deliberate extension (one-line edit to the assertion).

## Deviations from Plan

None — plan executed exactly as written. The only intra-plan deviation worth noting is the deliberate `revision NOT lowercased` decision, which was explicitly called out in the plan's Task-1 action block (Step A note: "revision is NOT lowercased (firmware strings preserve case; see action note)"), so it is plan-conformant rather than a Rule-1/2/3 auto-fix.

No auto-fixes were applied; no authentication gates encountered; no architectural decisions needed (Rule 4 did not fire).

## TDD Gate Compliance

Both tasks are `type="auto" tdd="true"`. The plan-level type is `execute` (not `tdd`), so the plan-level RED/GREEN/REFACTOR gate does not apply, but each individual task followed the RED → GREEN cycle:

| Task | RED commit | GREEN commit | REFACTOR |
| ---- | ---------- | ------------ | -------- |
| 1    | `1977b67` (test)  | `03f8f5a` (feat) | not needed |
| 2    | `2d19a61` (test)  | `419bb53` (feat) | not needed |

Each RED commit was verified to fail (`ModuleNotFoundError` / `AttributeError` / `FileNotFoundError` / locked-set assertion mismatch) before the GREEN commit was written.

## Verification Summary

| Check | Status |
| ----- | ------ |
| `pytest tests/unit/qmi/parsers/test_get_revision.py tests/unit/qmi/test_wrapper_dms_get_revision.py -q` | 8 passed in 0.41s |
| `pytest tests/unit/qmi/ -q` (full qmi subset) | 84 passed in 0.75s |
| `pytest -q` (full repo suite) | 1973 passed, 90 skipped in 26.25s (under M7 30s budget) |
| `ruff check src/spark_modem/qmi/` | All checks passed |
| `mypy --strict src/spark_modem/qmi/parsers/get_revision.py src/spark_modem/qmi/wrapper.py` | Success: no issues found in 2 source files |
| `grep -rn 'create_subprocess_exec' src/spark_modem/ \| grep -v subproc/` (SP-04 invariant) | 0 matches |
| `grep -c "_in_critical_section = True" src/spark_modem/qmi/wrapper.py` (read-only contract) | 5 (unchanged from pre-edit) |
| `ls tests/fixtures/qmicli/get_revision/ \| sort \| tr '\n' ' '` | `1.30 1.32 ` |

## Threat Surface Scan

No new threat surface introduced beyond what the plan's `<threat_model>` already disposes:

- T-05-01-01 (Tampering of parser against malformed stdout) — mitigated by returning `QmiError(UNEXPECTED_OUTPUT)`; verified by `test_parser_no_header_returns_unexpected_output`. `ConfigDict(extra='ignore', frozen=True)` blocks injection via extra fields; verified by `test_result_is_frozen_and_ignores_extra_fields`.
- T-05-01-02 (Firmware string leak) — accepted; firmware version is not PII; intentionally captured for fleet fixtures.
- T-05-01-03 (DoS via pathological regex backtracking) — mitigated by `[^']+` negated character class in `_RE_REVISION`; `subproc.runner` enforces stdout size cap upstream.

No new endpoints, auth paths, or trust boundaries were created. No `threat_flag` entries needed.

## Self-Check

Verifying SUMMARY claims against actual repo state.

**Files created — all present:**
- `S:/spark/modem-watchdog/src/spark_modem/qmi/parsers/get_revision.py` — FOUND
- `S:/spark/modem-watchdog/tests/fixtures/qmicli/get_revision/1.30/standard.txt` — FOUND
- `S:/spark/modem-watchdog/tests/fixtures/qmicli/get_revision/1.32/standard.txt` — FOUND
- `S:/spark/modem-watchdog/tests/unit/qmi/parsers/__init__.py` — FOUND
- `S:/spark/modem-watchdog/tests/unit/qmi/parsers/test_get_revision.py` — FOUND
- `S:/spark/modem-watchdog/tests/unit/qmi/test_wrapper_dms_get_revision.py` — FOUND

**Commits cited — all present in git log:**
- `1977b67` — FOUND (test: RED for Task 1)
- `03f8f5a` — FOUND (feat: GREEN for Task 1)
- `2d19a61` — FOUND (test: RED for Task 2)
- `419bb53` — FOUND (feat: GREEN for Task 2)

## Self-Check: PASSED

# Phase 5 Plan 02: Three-Source Version Detection (libqmi + Zao SDK + FleetTriple) Summary

**Built the (em7421_firmware, zao_sdk, libqmi) FleetTriple wire shape and three-probe orchestrator that Plans 05-03 (capture-fleet-fixture CLI) and 05-04 (preflight_check_known_fleet_triple) both consume — single seam for version-string formatting across CLI and daemon, with sentinel-based graceful fallback for SDK-absent and hard-fail for firmware-absent (preflight policy depends on it).**

## Performance

- **Duration:** ~7 min wall-clock (6 commits across 6m 49s of git activity)
- **Started:** 2026-05-11T08:27:37Z (record_start_time before Task 1 RED)
- **Completed:** 2026-05-11T08:34:46Z (Task 3 GREEN commit)
- **Tasks:** 3/3 complete (each as RED+GREEN pair = 6 task-level commits)
- **Files modified:** 8 (all new; 0 modified — Plan 05-01's wrapper changes already in tree)

## Accomplishments

- **`detect_libqmi_version()`** async helper at `src/spark_modem/qmi/version.py:45-71` parses libqmi-glib 3-part version from `qmicli --version` stdout; routes through `subproc.runner.run` (SP-04 invariant preserved); raises `QmiVersionDetectionFailed` on all three failure paths (missing binary / non-zero exit / unparseable stdout) with capped stderr/stdout excerpts (T-05-02-02 mitigation).
- **`detect_zao_sdk_version()`** pure-I/O helper at `src/spark_modem/zao_log/version.py:50-76` scans the first 64 KiB of a Zao log for one of two banner shapes (modern `zao_remote_endpoint/X.Y.Z` first, legacy `zao-remote-endpoint X.Y.Z` second); never raises; FileNotFoundError + OSError both downgrade to `None` with WARNING log. T-05-02-01 (DoS via huge log) mitigated by `_HEAD_BYTES = 64 * 1024` cap.
- **`FleetTriple`** pydantic BaseModel with `ConfigDict(frozen=True, extra="forbid")` — byte-reproducible wire shape that Plans 05-03 + 05-04 serialize/deserialize identically.
- **`compute_fleet_triple(wrapper, zao_log_path)`** async orchestrator composes all three probes; `"unknown"` literal sentinel for Zao SDK absent (caller decides fail-closed); QmiError on firmware probe raises (preflight needs failure to surface, never silent fallback for `em7421_firmware`).
- 16 new tests across 2 files (10 in `tests/unit/qmi/test_version.py`, 6 in `tests/unit/zao_log/test_version.py`), all green in 0.38s.
- Full repo regression: 2001 passed / 90 skipped in 20.88s (well under M7 ≤30s budget).
- ruff + `mypy --strict` clean on all changed source files; SP-04 invariant preserved (`grep -rn 'create_subprocess_exec\|subprocess.run' src/spark_modem/qmi/version.py src/spark_modem/zao_log/version.py` returns 0 matches).

## Task Commits

Each task followed the RED/GREEN cycle per the plan's `tdd="true"` annotation:

1. **Task 1 RED:** add failing tests for `detect_libqmi_version` — `dfcf06c` (test)
2. **Task 1 GREEN:** implement `detect_libqmi_version` + `QmiVersionDetectionFailed` — `8b3eaad` (feat)
3. **Task 2 RED:** add failing tests for `detect_zao_sdk_version` — `1aa83ce` (test)
4. **Task 2 GREEN:** implement `detect_zao_sdk_version` — `920b299` (feat)
5. **Task 3 RED:** add failing tests for `FleetTriple` + `compute_fleet_triple` — `a2dacca` (test)
6. **Task 3 GREEN:** implement `FleetTriple` + `compute_fleet_triple` — `bee44e3` (feat)

No REFACTOR commit was needed for any task — the GREEN code matched the analog shapes (PreflightFailed/preflight_check from `daemon/preflight.py`; pydantic frozen+forbid from `wire/_base.py`) verbatim.

## Files Created/Modified

### Created (8)

- **`src/spark_modem/qmi/version.py`** (151 LOC) — `detect_libqmi_version` + `QmiVersionDetectionFailed` + `FleetTriple` (frozen + extra=forbid) + `compute_fleet_triple` orchestrator + `_ZAO_SDK_UNKNOWN_SENTINEL = "unknown"`. Module docstring documents the X-02 (capture) + X-03 (preflight) callers.
- **`src/spark_modem/zao_log/version.py`** (75 LOC) — `detect_zao_sdk_version` + `_ZAO_BANNER_PATTERNS` (two candidates) + `_HEAD_BYTES = 64 * 1024`. Module docstring documents the deferred dpkg-query subprocess fallback (RESEARCH Q3 §295) and the "unknown" sentinel policy.
- **`tests/unit/qmi/test_version.py`** (~255 LOC, 10 tests) — Task 1 (6 tests: happy 1.30 + happy 1.32 + non-zero exit + unparseable stdout + FileNotFoundError + RuntimeError subclass + argv-shape pin) + Task 3 (4 tests: frozen+extra-forbid contract + happy path + "unknown" sentinel + QmiError on firmware raises). `_FakeWrapper` minimal duck-typed stand-in for `QmiWrapper.dms_get_revision`.
- **`tests/unit/zao_log/test_version.py`** (~70 LOC, 6 tests) — banner-present / no-banner / missing-file / banner-outside-head-window (T-05-02-01 DoS cap pin) / legacy banner shape / first-match-wins.
- **`tests/fixtures/qmicli/version/1.30/standard.txt`** (286 bytes, 9 lines) — synthetic qmicli --version stdout with `qmicli 1.30.6` first line and `Compiled with libqmi-glib 1.30.6` last line (regex matches the latter).
- **`tests/fixtures/qmicli/version/1.32/standard.txt`** (286 bytes, 9 lines) — same shape, 1.32.0 version.
- **`tests/fixtures/zao_log/version/banner_present.txt`** (3 lines) — synthetic Zao log with `zao_remote_endpoint/2.1.0` banner.
- **`tests/fixtures/zao_log/version/no_banner.txt`** (3 lines) — RASCOW_STAT-only synthetic log; banner-absent fallback path.

### Modified (0)

None. Plan 05-01's `qmi/wrapper.py` addition (`dms_get_revision`) is already in tree; this plan only consumes it.

## Decisions Made

- **`compute_fleet_triple` takes `wrapper: object` (duck-typed)** rather than introducing a `QmiWrapperProto` Protocol. Three reasons: (1) `version.py` already imports from `qmi/errors.py`, `qmi/parsers/get_revision.py`, `subproc/runner.py`, and `zao_log/version.py` — a Protocol would deepen the dependency chain unnecessarily; (2) the only method needed from the wrapper is `dms_get_revision`, which is structurally identical between production `QmiWrapper` (Plan 05-01) and the test `_FakeWrapper`; (3) the in-source `# type: ignore[attr-defined]` localises the structural-typing concession to a single line.

- **"unknown" string sentinel for `FleetTriple.zao_sdk`** (not `None`, not `Optional[str]`, not an enum). Rationale: `FleetTriple` is a wire shape that ships via `triple.json` files baked into the `.deb` (X-03); a `None` value would round-trip as JSON `null` and complicate the known-fleet-triple lookup hash. The literal string `"unknown"` is byte-reproducible and self-documenting in `triple.json` output. Preflight (Plan 05-04) decides fail-closed semantics on the sentinel; capture (Plan 05-03) records it for operator follow-up.

- **`FleetTriple` uses inline `ConfigDict(frozen=True, extra="forbid")` instead of inheriting `BaseWire`** from `src/spark_modem/wire/_base.py`. The two-line `model_config` declaration is cheaper than adding another import to `version.py` (already 5 imports deep); the W-02 wire discipline (frozen + extra=forbid) is preserved verbatim.

- **`QmiError` on firmware probe raises `QmiVersionDetectionFailed`** (does NOT fall back to a sentinel). The daemon preflight (X-03) needs the failure to surface — a silent "unknown" for `em7421_firmware` would defeat the entire purpose of the known-fleet-triple gate. The decision applies only to the firmware probe path; the Zao SDK probe IS allowed to fall back to "unknown" because the SDK has no universal detection mechanism (RESEARCH Q3 §288-298).

- **`QmiVersionDetectionFailed` subclasses `RuntimeError`** (matches `PreflightFailed` shape per CONTEXT.md X-03 — `N818` noqa for the public-name-fixed-by-plan-acceptance convention). It does NOT subclass `PreflightFailed` itself: different module, different exit-code semantics; Plan 05-04 will compose them at the preflight call site.

- **Two Zao banner regex candidates scanned in priority order** (modern `zao_remote_endpoint/X.Y.Z` first, legacy `zao-remote-endpoint X.Y.Z` second). First-match-wins ordering is pinned by `test_first_match_wins`. The dpkg-query subprocess fallback (RESEARCH Q3 §295) is NOT implemented in this plan — deferred to a future ADR if banner-absent becomes a fleet-wide observation.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] CompletedProcess field is `duration_monotonic`, not `duration_s`**

- **Found during:** Task 1 RED (writing the test stub `_make_cp` helper)
- **Issue:** The plan's test code at Task 1 Step D snippet used `CompletedProcess(argv=tuple(argv), ..., duration_s=0.0)`. The actual `src/spark_modem/subproc/result.py:14-31` dataclass has field `duration_monotonic: float` — using `duration_s` would have failed with `TypeError: CompletedProcess.__init__() got an unexpected keyword argument 'duration_s'` at test collection time.
- **Fix:** Built `CompletedProcess` instances via the `.make()` classmethod (the standard idiom across `tests/unit/qmi/test_wrapper.py`) with `duration_monotonic=0.0`. Factored into a `_make_cp(*, argv, exit_code, stdout, stderr=b"")` test helper for terseness.
- **Files modified:** `tests/unit/qmi/test_version.py` (helper + 8 usages)
- **Verification:** RED phase confirmed `ModuleNotFoundError` (not `TypeError`); GREEN phase confirmed 6/6 then 10/10 tests pass.
- **Committed in:** `dfcf06c` (Task 1 RED) — applied at test-authoring time before any GREEN code, so no commit-history scar.

**2. [Rule 3 — Blocking] `pytest-asyncio mode=auto` removes the need for `@pytest.mark.asyncio` decorators**

- **Found during:** Task 1 RED (writing the first async test)
- **Issue:** The plan's Step D test snippet decorated every async test with `@pytest.mark.asyncio`. `pyproject.toml [tool.pytest.ini_options]` already sets `asyncio_mode = "auto"`, and the existing `tests/unit/daemon/test_preflight.py` (the plan's named analog) uses plain `async def` without the decorator. Adding the decorator with `strict-markers` enabled would not have errored, but would have left a redundant directive that future maintainers would either propagate or strip.
- **Fix:** Dropped the `@pytest.mark.asyncio` decorator on every async test, matching `test_preflight.py`. `pytestmark = pytest.mark.asyncio` was also not needed.
- **Files modified:** `tests/unit/qmi/test_version.py` (10 tests), `tests/unit/zao_log/test_version.py` (6 tests — only one of these is async-free; this fix applies to none in zao_log/test_version.py since all are sync, but the same scrutiny was applied).
- **Verification:** Pytest collection succeeds; all tests pass.
- **Committed in:** `dfcf06c` + `1aa83ce` (applied at test-authoring time)

**3. [Rule 1 — Bug] PLC0415 in-function imports flagged by ruff after Task 3 GREEN**

- **Found during:** Task 3 GREEN (post-implementation lint sweep)
- **Issue:** During Task 3 RED authoring, I deliberately placed `from spark_modem.qmi.version import FleetTriple` (and `compute_fleet_triple`) inside the four new test functions to make the RED-phase test failure crisp (`ImportError` at the call site, not at module collection). Once GREEN landed, the in-function imports tripped ruff `PLC0415` (5 errors).
- **Fix:** Hoisted the imports to the module top alongside `QmiVersionDetectionFailed` + `detect_libqmi_version`; module now imports `FleetTriple` + `compute_fleet_triple` + `QmiVersionDetectionFailed` + `detect_libqmi_version` together. Also hoisted the `ValidationError` import from `pydantic`.
- **Files modified:** `tests/unit/qmi/test_version.py`
- **Verification:** `ruff check src/spark_modem/qmi/version.py src/spark_modem/zao_log/version.py tests/unit/qmi/test_version.py tests/unit/zao_log/test_version.py` exits 0; 10/10 tests still pass.
- **Committed in:** `bee44e3` (Task 3 GREEN, alongside the implementation)

**4. [Rule 1 — Bug] E501 line-too-long on `_make_cp` signature**

- **Found during:** Task 1 GREEN (post-implementation lint sweep)
- **Issue:** The 105-character `_make_cp(*, argv, exit_code, stdout, stderr=b"") -> CompletedProcess:` signature exceeded the project's `line-length = 100` (`pyproject.toml [tool.ruff]`).
- **Fix:** Reformatted the signature across multiple lines (each parameter on its own line).
- **Files modified:** `tests/unit/qmi/test_version.py`
- **Verification:** `ruff check tests/unit/qmi/test_version.py` exits 0.
- **Committed in:** `8b3eaad` (Task 1 GREEN, alongside the implementation)

---

**Total deviations:** 4 auto-fixed (2 blocking, 2 bugs — all caught at test-authoring or post-GREEN lint time before any commit landed broken)

**Impact on plan:** All deviations are mechanical fixes against literal-plan-text-vs-real-code drift (CompletedProcess field name; decorator-vs-auto mode) or lint compliance (PLC0415; E501). No scope creep; no architectural decisions needed; Rule 4 did not fire. The 05-05 executor's caveat about plan-text symbol assumptions ("event-shape `who`/`line` vs flat `usb_path`; `_DECAY_K_DEFAULT` missing from `policy/engine.py`") is the analog: plan text describes the contract, real code defines it; when they disagree the real code wins.

## Issues Encountered

- **System reminder noise on Edit-after-Write:** the `PreToolUse:Edit hook` flagged each Edit on `version.py` and `test_version.py` even after I had just Read or Written them in the same session. This is environmental friction, not a correctness issue — every Edit succeeded; I Re-Read each file to satisfy the hook and continued. Captured here so the orchestrator agent does not retry on this signal.
- **No active git pre-commit hook on this Windows dev host:** `.git/hooks/pre-commit` is absent, so ruff/mypy/SP-04 lint did not run automatically. I ran them manually after each task GREEN. Production builds catch the same gates in CI; the gap is dev-host-only.

## TDD Gate Compliance

All three tasks are `type="auto" tdd="true"`. Plan-level type is `execute` (not `tdd`), so plan-level RED→GREEN→REFACTOR gates do not apply, but each task followed the RED → GREEN cycle:

| Task | RED commit | GREEN commit | REFACTOR |
| ---- | ---------- | ------------ | -------- |
| 1    | `dfcf06c` (test)  | `8b3eaad` (feat) | not needed |
| 2    | `1aa83ce` (test)  | `920b299` (feat) | not needed |
| 3    | `a2dacca` (test)  | `bee44e3` (feat) | not needed |

Each RED commit was verified to fail before the GREEN commit was authored:

- Task 1 RED: `ModuleNotFoundError: No module named 'spark_modem.qmi.version'`
- Task 2 RED: `ModuleNotFoundError: No module named 'spark_modem.zao_log.version'`
- Task 3 RED: `ImportError: cannot import name 'FleetTriple' from 'spark_modem.qmi.version'` (6 Task-1 tests still pass; only the 4 new Task-3 tests fail — clean intra-file RED)

## Verification Summary

| Check | Status |
| ----- | ------ |
| `pytest tests/unit/qmi/test_version.py tests/unit/zao_log/test_version.py -q` | 16 passed in 0.38s |
| `pytest tests/unit/zao_log/test_version.py tests/unit/qmi/test_version.py tests/unit/qmi/parsers/test_get_revision.py tests/unit/qmi/test_wrapper_dms_get_revision.py -q` (Plans 01+02 unit subset) | 24 passed in 0.43s |
| `pytest -q` (full repo suite) | 2001 passed, 90 skipped in 20.88s (M7 30s budget) |
| `ruff check src/spark_modem/qmi/version.py src/spark_modem/zao_log/version.py tests/unit/qmi/test_version.py tests/unit/zao_log/test_version.py` | All checks passed |
| `mypy --strict src/spark_modem/qmi/version.py src/spark_modem/zao_log/version.py` | Success: no issues found in 2 source files |
| `grep -rn 'create_subprocess_exec\|subprocess.run' src/spark_modem/qmi/version.py src/spark_modem/zao_log/version.py` (SP-04 invariant) | 0 matches (exit=1, grep convention) |
| `grep -c "class FleetTriple" src/spark_modem/qmi/version.py` | 1 |
| `grep -c "async def compute_fleet_triple" src/spark_modem/qmi/version.py` | 1 |
| `grep -c '"unknown"' src/spark_modem/qmi/version.py` | 1 (the sentinel string in `_ZAO_SDK_UNKNOWN_SENTINEL`) |
| `grep -c "async def detect_libqmi_version" src/spark_modem/qmi/version.py` | 1 |
| `grep -c "def detect_zao_sdk_version" src/spark_modem/zao_log/version.py` | 1 |

## Threat Surface Scan

No new threat surface introduced beyond the plan's `<threat_model>` dispositions:

- **T-05-02-01 (DoS via huge Zao log file):** mitigated by 64 KiB head-read cap (`_HEAD_BYTES`); pinned by `test_banner_outside_head_window_returns_none` which writes `_HEAD_BYTES + 100` bytes of padding before a banner and asserts `None` is returned.
- **T-05-02-02 (Tampering / malformed qmicli stdout):** mitigated by `QmiVersionDetectionFailed` raised on non-zero exit AND unparseable stdout, with capped stderr/stdout excerpts (512 B each — bounded memory). Verified by `test_non_zero_exit_raises` + `test_unparseable_stdout_raises`.
- **T-05-02-03 (Spoofing fake Zao log banner):** accepted; threat model is local-only.
- **T-05-02-04 (Information disclosure — FleetTriple shipped via .deb):** accepted; version strings are not PII.
- **T-05-02-05 (Subprocess injection in `detect_libqmi_version`):** mitigated by hardcoded argv list `["qmicli", "--version"]` (no external string interpolation); SP-04 + list-form argv invariant preserved. Verified by `test_detect_libqmi_version_parses_1_30` asserting `seen_argv == [["qmicli", "--version"]]`.

No new endpoints, auth paths, or trust boundaries created. No `threat_flag` entries needed.

## Known Stubs

None. The `"unknown"` sentinel string in `FleetTriple.zao_sdk` is intentional — Plan 05-04 (preflight_check_known_fleet_triple) decides fail-closed semantics on it, Plan 05-03 (capture-fleet-fixture CLI) records it in `triple.json` for operator follow-up. Documented in module docstring + `key-decisions` above.

## Next Phase Readiness

- **05-03 (capture-fleet-fixture CLI)** can now `from spark_modem.qmi.version import compute_fleet_triple, FleetTriple` and write `FleetTriple.model_dump_json()` to `triple.json`. No further version-detection code needed in 05-03 — it is purely a CLI orchestration plus PII redaction.
- **05-04 (preflight_check_known_fleet_triple)** can now `from spark_modem.qmi.version import compute_fleet_triple, FleetTriple, QmiVersionDetectionFailed` and compare the local triple against `/etc/spark-modem-watchdog/known-fleet/<sha>/triple.json` files. Fail-closed semantics on `zao_sdk == "unknown"` is the X-03 decision Plan 05-04 will make.
- **No blockers.** The `_FakeWrapper` shape established here can be reused by Plans 05-03 + 05-04 for their own hardware-free unit tests (compose with `tests/fakes/runner.FakeRunner` for the libqmi probe stub).

## Self-Check

Verifying SUMMARY claims against actual repo state.

**Files created — all present:**

- `S:/spark/modem-watchdog/src/spark_modem/qmi/version.py` — FOUND
- `S:/spark/modem-watchdog/src/spark_modem/zao_log/version.py` — FOUND
- `S:/spark/modem-watchdog/tests/unit/qmi/test_version.py` — FOUND
- `S:/spark/modem-watchdog/tests/unit/zao_log/test_version.py` — FOUND
- `S:/spark/modem-watchdog/tests/fixtures/qmicli/version/1.30/standard.txt` — FOUND
- `S:/spark/modem-watchdog/tests/fixtures/qmicli/version/1.32/standard.txt` — FOUND
- `S:/spark/modem-watchdog/tests/fixtures/zao_log/version/banner_present.txt` — FOUND
- `S:/spark/modem-watchdog/tests/fixtures/zao_log/version/no_banner.txt` — FOUND

**Commits cited — all present in git log:**

- `dfcf06c` — FOUND (test: RED for Task 1)
- `8b3eaad` — FOUND (feat: GREEN for Task 1)
- `1aa83ce` — FOUND (test: RED for Task 2)
- `920b299` — FOUND (feat: GREEN for Task 2)
- `a2dacca` — FOUND (test: RED for Task 3)
- `bee44e3` — FOUND (feat: GREEN for Task 3)

## Self-Check: PASSED

---
*Phase: 05-bench-field-shadow*
*Completed: 2026-05-11*

# Phase 5 Plan 03: capture-fleet-fixture CLI verb Summary

**Shipped the `spark-modem ctl capture-fleet-fixture --out=<dir>` CLI verb that captures the per-box fleet triple + 7 redacted qmicli outputs per modem + a Zao log RASCOW_STAT sample — the X-01 + X-02 deliverable that closes the X-03 chicken-and-egg gap (engineer can capture fixtures on a daemon-less box).**

## Performance

- **Duration:** ~11 min wall-clock (5 commits across the plan)
- **Started:** 2026-05-11T08:41:25Z
- **Completed:** 2026-05-11T08:52:52Z (approximate; epoch math gives 687s)
- **Tasks:** 3/3 complete
- **Files modified:** 9 (2 modified, 7 created)
- **Test growth:** +17 tests across the plan-scope (7 redact + 7 capture verb + 3 integration); full repo suite now 2018 passed in 20.26s (up from 2001 at Plan 05-02 close), well under the M7 ≤30s budget

## Accomplishments

- **`redact_pii_from_raw_qmicli(stdout: bytes) -> bytes`** at `src/spark_modem/cli/redact.py:84` — raw-qmicli-stdout redaction helper covering four patterns (ICCID, UIM ID, IMSI, IPv4 address). Determinism preserved: same value -> same `<redacted:<sha256[:8]>>` token; cross-file identity correlation survives without exporting PII.
- **`capture_fleet_fixture.py`** at `src/spark_modem/cli/ctl/capture_fleet_fixture.py` (~210 LOC) — full CLI module exporting `build_fleet_fixture` (the sync-friendly orchestrator) + `run` (argparse dispatcher) + `QMICLI_CAPTURE_VERBS` (frozen 7-tuple). Produces the contract directory tree per CONTEXT.md X-04: `triple.json + qmi/<usb_path>/<verb>.txt × 7 × N modems + zao-log-sample.txt`.
- **`spark-modem ctl capture-fleet-fixture --out=<dir>`** registered in `src/spark_modem/cli/main.py:181-192` with `--out REQUIRED`. argparse rejects invocation without --out (exit 2 via `pytest.raises(SystemExit)`).
- **PII redaction at capture time** — every qmicli stdout flows through `redact_pii_from_raw_qmicli` before `write_bytes`. UIM ID added alongside ICCID (Rule 2 deviation; see Deviations).
- **ADR-0009 keying enforced** — per-modem fixture subdirs are `qmi/<usb_path>/` (e.g. `2-3.1.1`); cdc-wdmN appears ONLY as the qmicli `--device=/dev/cdc-wdmN` interpolation. Pinned by `test_modem_subdirs_match_usb_path_shape`.
- **X-03 chicken-and-egg fix shipped** — `capture-fleet-fixture` is a standalone ctl subcommand; does NOT import `daemon.main`; does NOT participate in preflight. Engineer can capture the fleet triple on a daemon-less box. Verified by `grep -rn 'from spark_modem.daemon' src/spark_modem/cli/ctl/capture_fleet_fixture.py` returning 0 matches.
- **QMICLI_CAPTURE_VERBS frozen at 7** — locked-set assertion `test_qmicli_capture_verbs_list_is_locked_at_7` pins the exact 7-name set. CONTEXT.md X-02 upper bound was 8; dropped `wds_get_packet_service_status` (volatile datapath state).
- **`tests/fixtures/fleet/_test/triple.json`** committed today (per RESEARCH Q10 §752) so the directory layout is in git from day 1; real per-box fixtures land via the X-04 sweep before Phase 6.
- **17 new tests across 3 files**, all green in 0.92s; full repo suite 2018 passed / 90 skipped in 20.26s (M7 ≤30s budget preserved).
- **ruff + mypy --strict clean** on all changed source files; SP-04 invariant preserved (`grep -rEn 'subprocess.run|create_subprocess_exec' src/spark_modem/cli/ctl/capture_fleet_fixture.py src/spark_modem/cli/redact.py` returns 0 matches).

## Locked QMICLI_CAPTURE_VERBS (Phase 5 X-02)

The 7-verb capture set, in declaration order:

| # | Module name              | qmicli arg                    | Rationale |
|---|--------------------------|-------------------------------|-----------|
| 1 | `dms_get_revision`       | `--dms-get-revision`          | EM7421 firmware string (the `em7421_firmware` component of FleetTriple) |
| 2 | `dms_get_operating_mode` | `--dms-get-operating-mode`    | Online / low-power / persistent-low-power — affects RF-block flag |
| 3 | `uim_get_card_status`    | `--uim-get-card-status`       | SIM presence + ICCID/IMSI identity (PII; redacted) |
| 4 | `nas_get_signal_info`    | `--nas-get-signal-info`       | RSRP/RSRQ/SNR/RSSI — signal-gate context |
| 5 | `nas_get_serving_system` | `--nas-get-serving-system`    | Registration state + MCC/MNC — carrier-table cross-check |
| 6 | `wds_get_current_settings` | `--wds-get-current-settings` | Data session state + IPv4 (PII; redacted) |
| 7 | `wds_get_profile_settings` | `--wds-get-profile-settings` | APN — APN-correctness gate |

**Dropped vs. CONTEXT.md X-02 §164-169 upper bound (8 verbs):**

- `wds_get_packet_service_status` — datapath connection state is volatile and depends on network conditions at the moment of capture, not on box config. Not useful for triple-matching or fixture-coverage purposes (which are the Phase 5 reasons to capture). Decision pinned by `test_qmicli_capture_verbs_list_is_locked_at_7`.

## Test-Fixture Substitutions

The plan's Task 2 §765-773 referenced four fixture filenames inside the patched-runner mapping that did not match what is actually on disk. Substitutions made:

| Plan-text path                                       | Real path used                                        | Reason |
|------------------------------------------------------|-------------------------------------------------------|--------|
| `tests/fixtures/qmicli/get_serving_system/1.30/registered.txt` | `.../get_serving_system/1.30/registered_home.txt` | Plan-text fixture name not present; `registered_home.txt` is the actual name |
| `tests/fixtures/qmicli/get_current_settings/1.30/connected.txt` | `.../get_current_settings/1.30/raw_ip_y.txt`     | Plan-text fixture name not present; `raw_ip_y.txt` exists |
| `tests/fixtures/qmicli/get_profile_settings/1.30/default.txt` | `.../get_profile_settings/1.30/profile1_internet.txt` | Plan-text fixture name not present; `profile1_internet.txt` exists |
| `tests/fixtures/qmicli/version/1.30/standard.txt`    | unchanged (exists)                                    | — |

Documented in the docstring of the `_patched_runner` pytest fixture so the substitutions are auditable in-source. None of the test assertions depend on the specific content of these files — only that they exist and contain non-ICCID/IMSI bytes (the PII redaction test exercises only `uim_get_card_status.txt` per modem).

## Example fleet fixture committed (RESEARCH Q10 §752)

`tests/fixtures/fleet/_test/triple.json`:

```json
{
  "schema_version": 1,
  "em7421_firmware": "SWI9X30C_02.38.00.00",
  "zao_sdk": "2.1.0",
  "libqmi": "1.30.6",
  "first_seen_box_id": "_test",
  "first_seen_iso": "2026-05-11T00:00:00Z",
  "_comment": "Example fixture committed in Plan 05-03; real per-box fixtures are added during X-04 capture sweep before Phase 6."
}
```

The `_test/` prefix signals "this is the example, not a real box". Plan 05-04 will consume this same shape from `/etc/spark-modem-watchdog/known-fleet/<sha>/triple.json`; the schema is the inter-plan contract.

## X-03 chicken-and-egg fix audit trail

The capture verb is decoupled from daemon startup:

- `grep -rn 'from spark_modem.daemon' src/spark_modem/cli/ctl/capture_fleet_fixture.py` returns 0 matches.
- `grep -rn 'preflight' src/spark_modem/cli/ctl/capture_fleet_fixture.py` returns 0 matches.
- The `run()` dispatcher constructs `SysfsInventory()` directly (no PID lock, no `daemon.main` entry); on a dev laptop the inventory is empty and the verb exits 1 with a helpful message.
- An engineer with physical access to a daemon-less Jetson can run `spark-modem ctl capture-fleet-fixture --out=/tmp/box-N` and obtain a `triple.json` to seed `/etc/spark-modem-watchdog/known-fleet/<sha>/` before starting the daemon.

## Task Commits

| Task | Phase  | Commit  | Type    | What landed |
|------|--------|---------|---------|-------------|
| 1    | RED    | `f42a225` | test    | 7 failing tests for `redact_pii_from_raw_qmicli` + new fixture `uim_get_card_status/1.30/with_iccid.txt` |
| 1    | GREEN  | `a40daef` | feat    | `redact_pii_from_raw_qmicli` impl with 4 patterns (ICCID/UIM ID/IMSI/IPv4) |
| 2    | RED    | `721c5c6` | test    | 7 failing tests for `capture_fleet_fixture` CLI verb + new test sub-package `tests/unit/cli/ctl/` + example `tests/fixtures/fleet/_test/triple.json` |
| 2    | GREEN  | `a5ebdb4` | feat    | `capture_fleet_fixture.py` module + `cli/main.py` argparse wiring |
| 3    | —      | `018d210` | test    | 3 integration tests (triple.json roundtrip, Zao sample filter, idempotency) |

No REFACTOR commits needed — Task 1 + Task 3 were one-pass; Task 2's lint clean-up (ASYNC240 / RUF100 / PLR0915) was folded into the GREEN commit at the same authoring boundary.

## Files Created/Modified

### Created (7)

- **`src/spark_modem/cli/ctl/capture_fleet_fixture.py`** (~210 LOC). Module docstring documents X-01/X-02 + X-03 chicken-and-egg fix. Exports `build_fleet_fixture`, `run`, `QMICLI_CAPTURE_VERBS`. Five sync helpers (`_zao_log_rascow_tail`, `_write_modem_verb_output`, `_build_triple_dict`, `_write_triple_and_sample`, `_prepare_out_dirs`) so all pathlib I/O wraps in `asyncio.to_thread`.
- **`tests/unit/cli/test_redact_raw_qmicli.py`** (~70 LOC, 7 tests). ICCID/IMSI/IPv4 redaction; determinism (same input → same output); repeated value → same hash; non-PII passthrough byte-identical; UIM fixture roundtrip (defensive: no 18-digit run survives).
- **`tests/unit/cli/ctl/__init__.py`** (empty, establishes the new test sub-package).
- **`tests/unit/cli/ctl/test_capture_fleet_fixture.py`** (~210 LOC, 7 tests). Tree shape; FleetTriple JSON deserialisation; usb_path keying (ADR-0009); PII redaction in captured uim stdout; argparse dispatch resolution; --out required; QMICLI_CAPTURE_VERBS locked at 7.
- **`tests/integration/test_fleet_fixture_roundtrip.py`** (~145 LOC, 3 tests, `pytest.mark.integration`). Triple roundtrip via FleetTriple; Zao log sample is RASCOW_STAT-only; capture is idempotent on identity fields.
- **`tests/fixtures/qmicli/uim_get_card_status/1.30/with_iccid.txt`** (17 lines). Synthetic representative qmicli stdout with ICCID appearing 3× (UIM ID + ICCID + ICCID) + IMSI 1×; matches the byte shape of real `qmicli --uim-get-card-status` output.
- **`tests/fixtures/fleet/_test/triple.json`** (7 fields, per RESEARCH Q10 §752 — example fleet fixture committed in this plan so the directory layout is greppable from day 1).

### Modified (2)

- **`src/spark_modem/cli/redact.py`** (+48 LOC). Added `import re`, `_RAW_QMICLI_PII_PATTERNS` tuple (4 patterns: ICCID/UIM ID/IMSI/IPv4), `redact_pii_from_raw_qmicli` function. Existing `redact_pii` / `redact_iccid_imsi_in_dict` / `redact_webhook_url_to_host_only` untouched.
- **`src/spark_modem/cli/main.py`** (+14 LOC). Added `from spark_modem.cli.ctl import capture_fleet_fixture as ctl_capture_fleet` import (alphabetized with other ctl imports); added `ctl capture-fleet-fixture --out` subparser block immediately after `ctl support-bundle`; added `# noqa: PLR0915` on `_build_parser` with rationale comment (argparse subparser wiring is intentionally a single block).

## Decisions Made

- **UIM ID added alongside ICCID** (Rule 2 deviation from plan-text). Real qmicli `uim_get_card_status` stdout carries the ICCID value under both `UIM ID:` and `ICCID:` labels (verified in `tests/fixtures/qmicli/get_sim_state/1.30/*.txt` — `UIM ID: '<digits>'` appears alongside `ICCID: '<digits>'`). Without the UIM ID pattern, the same identifier would leak unredacted on every captured `uim_get_card_status.txt`. Pin: `test_uim_fixture_roundtrip` asserts `b"8997201700123456789" not in out` after redaction.

- **QMICLI_CAPTURE_VERBS frozen at 7** (CONTEXT.md X-02 §163-170 upper bound was 8). Dropped `wds_get_packet_service_status` because datapath connection state is volatile (depends on network conditions at capture time) and not useful for triple-matching/fixture coverage. The lock is pinned by `test_qmicli_capture_verbs_list_is_locked_at_7` using `frozenset(name for name, _ in QMICLI_CAPTURE_VERBS) == frozenset({...7 names...})`.

- **`build_fleet_fixture` is the orchestrator seam, `run` is the dispatcher**. `build_fleet_fixture(out_path, descriptors, zao_log_path, box_id)` is sync-friendly and dependency-injected — every unit/integration test uses it directly with hand-built descriptors. `run(args)` is the argparse dispatcher and the only call site that constructs `SysfsInventory`; this keeps the orchestrator unit-testable without sysfs.

- **No daemon coupling** — capture verb does NOT import `daemon.main`, does NOT participate in preflight, does NOT acquire the daemon PID lock. The X-03 chicken-and-egg fix is the literal absence of these imports.

- **ISO-8601 timestamp uses `.replace('+00:00', 'Z')`** for the canonical 'Z'-suffixed form. `datetime.now(UTC).isoformat()` returns `2026-05-11T08:52:52.123456+00:00`; preflight (Plan 05-04) will parse timestamps with the `Z` form.

- **Five sync helpers + `asyncio.to_thread`** rather than blanket `# noqa: ASYNC240` over every pathlib call. The helpers are small (1-3 lines each) and named for what they do (`_zao_log_rascow_tail`, `_write_modem_verb_output`, `_build_triple_dict`, `_write_triple_and_sample`, `_prepare_out_dirs`). Cleaner than per-line noqa and matches the Phase 4 fault_inject.py + HIL scenario pattern.

- **Re-capture into same dir is idempotent on identity, not on timestamp**. The `first_seen_iso` field is `datetime.now()` per call so a second capture writes a fresh timestamp; the `em7421_firmware`/`zao_sdk`/`libqmi` triple is identical (verified by `test_capture_is_idempotent`). Operator semantics: re-running is safe; the timestamp reflects WHEN the capture happened, not when the box first existed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 — Critical] UIM ID added to redaction pattern set (PII coverage gap)**

- **Found during:** Task 1 GREEN (running the test_uim_fixture_roundtrip assertion against the literal plan-text 3-pattern set)
- **Issue:** Plan-text §216-228 specified only three redaction patterns (ICCID / IMSI / IPv4 address). Real qmicli `uim_get_card_status` stdout carries the ICCID identifier under both `UIM ID: '<digits>'` AND `ICCID: '<digits>'` labels (verified in the existing `tests/fixtures/qmicli/get_sim_state/1.30/*.txt` Phase 2 fixtures). The test_uim_fixture_roundtrip assertion failed because the `UIM ID: '8997201700123456789'` line survived redaction even though all three `ICCID:` lines were redacted.
- **Fix:** Added `re.compile(rb"(UIM ID:\\s*')([^']+)(')")` to `_RAW_QMICLI_PII_PATTERNS` (immediately after the ICCID pattern). Same shape as the other three patterns; preserves the prefix + closing quote; replaces the value with `<redacted:<hash>>`.
- **Files modified:** `src/spark_modem/cli/redact.py` (added one tuple entry)
- **Verification:** All 7 redact tests pass; `test_uim_fixture_roundtrip` confirms `b"8997201700123456789" not in out` AND `b"425010012345678" not in out`.
- **Committed in:** `a40daef` (Task 1 GREEN, alongside the implementation).

**2. [Rule 3 — Blocking] `CompletedProcess(..., duration_s=0.0)` does not exist; real field is `duration_monotonic`**

- **Found during:** Task 2 RED (writing the `_patched_runner` fake) — same defect Plan 05-02 caught.
- **Issue:** Plan-text Task 2 §638-642 and Task 3 §852-856 both used `CompletedProcess(argv=tuple(argv), exit_code=0, stdout=..., stderr=b"", duration_s=0.0)`. The actual `src/spark_modem/subproc/result.py:14-31` dataclass has `duration_monotonic: float`. Using `duration_s` would have raised `TypeError: __init__() got an unexpected keyword argument 'duration_s'` at test collection time.
- **Fix:** Constructed CompletedProcess via the `.make()` classmethod (the standard idiom across the codebase) with `duration_monotonic=0.0`. Also passed `stdin` + `env` kwargs in the fake `run` signature to match the production `SubprocRunner.run` Protocol.
- **Files modified:** `tests/unit/cli/ctl/test_capture_fleet_fixture.py` + `tests/integration/test_fleet_fixture_roundtrip.py` (both `_patched_runner` fixtures).
- **Verification:** RED phase failed with `ModuleNotFoundError` (the intended failure mode), not `TypeError`; GREEN phase all tests pass.
- **Committed in:** `721c5c6` (Task 2 RED) and `018d210` (Task 3) — applied at test-authoring time before any GREEN code, so no commit-history scar.

**3. [Rule 3 — Blocking] ASYNC240 lint failures on pathlib I/O in async functions**

- **Found during:** Task 2 GREEN (post-implementation `ruff check` sweep)
- **Issue:** Ruff `ASYNC240` flagged three `pathlib.Path` method calls inside `async def` (`read_bytes`, `mkdir`, `write_bytes`, `write_text`). Existing modules (e.g. `src/spark_modem/cli/ctl/support_bundle.py`) use the same pattern without firing — but ruff 0.15.12's ASYNC ruleset has tightened. The fix discipline established in Plans 04-06 / 04-07 is to wrap blocking pathlib in `asyncio.to_thread` (event-loop hygiene).
- **Fix:** Extracted five sync helpers (`_zao_log_rascow_tail`, `_write_modem_verb_output`, `_build_triple_dict`, `_write_triple_and_sample`, `_prepare_out_dirs`); each is a 1-3-line sync function named for what it does. Async callers wrap in `asyncio.to_thread`. Also wrapped the final `target.resolve()` call in `run()` since `Path.resolve()` hits the filesystem on POSIX.
- **Files modified:** `src/spark_modem/cli/ctl/capture_fleet_fixture.py` (added 5 sync helpers; restructured `build_fleet_fixture` to call them via to_thread).
- **Verification:** `ruff check src/spark_modem/cli/ctl/capture_fleet_fixture.py` exits 0; all 7 Task 2 tests still pass after the refactor.
- **Committed in:** `a5ebdb4` (Task 2 GREEN, alongside the implementation).

**4. [Rule 3 — Blocking] RUF100 `# noqa: BLE001` unused (rule not enabled)**

- **Found during:** Task 2 GREEN (post-implementation `ruff check` sweep)
- **Issue:** I had added `# noqa: BLE001` to both `except Exception` clauses, but `BLE` is not in the project's `select = [...]` list (`pyproject.toml`: `["E", "F", "W", "I", "N", "UP", "B", "S", "ASYNC", "ANN", "RET", "SIM", "PTH", "PL", "RUF"]`). Ruff flagged the directives as unused.
- **Fix:** Removed both `# noqa: BLE001` directives; replaced with comment rationale on the next line ("Broad-except deliberate: ...") to preserve the design intent.
- **Files modified:** `src/spark_modem/cli/ctl/capture_fleet_fixture.py` (2 noqa removals + 2 inline rationale comments).
- **Verification:** `ruff check` exits 0; no behavior change.
- **Committed in:** `a5ebdb4` (Task 2 GREEN).

**5. [Rule 3 — Blocking] RUF002 multiplication-sign `×` in docstring**

- **Found during:** Task 2 GREEN (post-implementation `ruff check` sweep)
- **Issue:** The module docstring at `capture_fleet_fixture.py:8` used the Unicode `×` (MULTIPLICATION SIGN) — ruff RUF002 flags this as ambiguous (suggests LATIN SMALL LETTER X). The plan-text used `×` in the same place (line 9 of the plan), so it would not have been caught at planning time.
- **Fix:** Replaced `×` with `x` in the docstring tree diagram.
- **Files modified:** `src/spark_modem/cli/ctl/capture_fleet_fixture.py` (1 line in the module docstring).
- **Verification:** `ruff check` exits 0.
- **Committed in:** `a5ebdb4` (Task 2 GREEN).

**6. [Rule 3 — Blocking] PLR0915 too-many-statements on `_build_parser`**

- **Found during:** Task 2 GREEN (post-implementation `ruff check` sweep on `cli/main.py`)
- **Issue:** Adding the `ctl capture-fleet-fixture` subparser block pushed `_build_parser` from 49 to 52 statements (threshold 50). The function is an argparse builder by design — one block per subcommand registration; extracting it would not improve readability.
- **Fix:** Added `# noqa: PLR0915 - argparse subparser wiring is a single block by design` to the function signature.
- **Files modified:** `src/spark_modem/cli/main.py` (1-line noqa directive).
- **Verification:** `ruff check` exits 0; no behavior change.
- **Committed in:** `a5ebdb4` (Task 2 GREEN).

---

**Total deviations:** 6 auto-fixed (1 Rule 2 critical, 5 Rule 3 blocking lint/mechanical). No scope creep; no architectural decisions; Rule 4 did not fire.

**Impact on plan:** Deviation 1 (UIM ID) is the only behavioral fix — it expanded the PII pattern set to 4 (from the plan-text's 3) so the redaction is correct against real qmicli stdout. The other 5 are lint/idiom corrections against literal plan-text-vs-real-code drift (CompletedProcess field name, ASYNC240 on pathlib, BLE001 ignore rule, multiplication-sign character, PLR0915 statement count). Plan 05-02's deviation log called this drift pattern out explicitly: "plan text describes the contract, real code defines it; when they disagree the real code wins."

## Issues Encountered

- **`PreToolUse:Edit` hook noise on Edit-after-Edit on the same file:** the hook flagged each Edit on `redact.py` / `capture_fleet_fixture.py` / `main.py` after I had just Read or Written them in the same session. Same friction Plan 05-02 SUMMARY documented. Every Edit succeeded; ignoring the hook reminder is correct here.
- **No active git pre-commit hook on this Windows dev host:** `.git/hooks/pre-commit` is absent, so ruff/mypy/SP-04 lint did not run automatically. I ran them manually after each task GREEN. Production builds catch the same gates in CI.

## TDD Gate Compliance

All three tasks are `type="auto" tdd="true"`. Plan-level type is `execute`, so plan-level RED→GREEN→REFACTOR gates do not apply; each task followed the RED → GREEN cycle:

| Task | RED commit | GREEN commit | REFACTOR |
| ---- | ---------- | ------------ | -------- |
| 1    | `f42a225` (test)  | `a40daef` (feat) | not needed |
| 2    | `721c5c6` (test)  | `a5ebdb4` (feat) | not needed (lint fixes folded into GREEN) |
| 3    | `018d210` (test)  | (no GREEN — pure-test plan against existing impl) | n/a |

Task 3 is a pure-test addition on top of Task 2's implementation — no implementation code lands in Task 3, so it has no GREEN counterpart commit. The RED phase for Task 3 ran the tests against the already-shipped `build_fleet_fixture` and they passed first-time (an `expected-to-fail-but-actually-passes` situation per TDD doctrine that means the implementation already supports the integration assertion). Per the TDD fail-fast rule, I investigated: each integration test asserts a different property (triple round-trip, RASCOW_STAT filter, idempotency) that the unit tests don't cover, so the tests are meaningful additional coverage; the implementation legitimately satisfies them.

RED-phase failure verification:

- Task 1 RED: `ImportError: cannot import name 'redact_pii_from_raw_qmicli' from 'spark_modem.cli.redact'`
- Task 2 RED: `ModuleNotFoundError: No module named 'spark_modem.cli.ctl.capture_fleet_fixture'`
- Task 3 RED: tests passed first-time against Task 2 GREEN's implementation (additive integration coverage; see paragraph above)

## Verification Summary

| Check | Status |
| ----- | ------ |
| `pytest tests/unit/cli/test_redact_raw_qmicli.py tests/unit/cli/ctl/test_capture_fleet_fixture.py tests/integration/test_fleet_fixture_roundtrip.py -q` (full plan-scope) | **17 passed in 0.92s** |
| `pytest tests/unit/cli/ -q` (existing cli test regression) | **94 passed, 1 skipped in 1.52s** (1 skip = POSIX-only chmod test on Windows) |
| `pytest -q` (full repo suite — M7 ≤30s budget) | **2018 passed, 90 skipped in 20.26s** |
| `ruff check src/spark_modem/cli/` | All checks passed |
| `ruff check tests/integration/test_fleet_fixture_roundtrip.py` | All checks passed |
| `mypy --strict src/spark_modem/cli/ctl/capture_fleet_fixture.py src/spark_modem/cli/redact.py src/spark_modem/cli/main.py` | Success: no issues found in 3 source files |
| `grep -rEn 'create_subprocess_exec\|subprocess\.run' src/spark_modem/cli/ctl/capture_fleet_fixture.py src/spark_modem/cli/redact.py` (SP-04 invariant) | 0 matches |
| `grep -rn 'from spark_modem.daemon' src/spark_modem/cli/ctl/capture_fleet_fixture.py` (X-03 chicken-and-egg) | 0 matches |
| `grep -c "def redact_pii_from_raw_qmicli" src/spark_modem/cli/redact.py` | 1 |
| `grep -c "QMICLI_CAPTURE_VERBS" src/spark_modem/cli/ctl/capture_fleet_fixture.py` | 3 (declaration + 2 references) |
| `grep "ctl_capture_fleet" src/spark_modem/cli/main.py \| wc -l` | 2 (import + set_defaults) |
| `grep "capture-fleet-fixture" src/spark_modem/cli/main.py \| wc -l` | 2 (subparser name + help) |
| `python -c "import json; d=json.load(open('tests/fixtures/fleet/_test/triple.json')); assert d['schema_version']==1 and 'em7421_firmware' in d and 'zao_sdk' in d and 'libqmi' in d"` | Exits 0 |

## Threat Surface Scan

The plan's `<threat_model>` covers seven threats (T-05-03-01 .. T-05-03-07). Disposition verification:

- **T-05-03-01 (ICCID/IMSI leakage in `uim_get_card_status.txt`):** mitigated — `redact_pii_from_raw_qmicli` applied to every captured stdout; UIM ID added to pattern set (Rule 2 deviation). Pinned by `test_uim_capture_redacts_pii` + `test_uim_fixture_roundtrip`.
- **T-05-03-02 (IPv4 leak in `wds_get_current_settings.txt`):** mitigated — `IPv4 address:` pattern covered. Pinned by `test_ipv4_redacted`. The real fixture used in tests (`raw_ip_y.txt`) contains `IPv4 address: '10.69.92.156'` — verified redacted in captured output.
- **T-05-03-03 (Spoofing — operator runs capture on wrong box):** accepted; operator-driven by design (X-04); SIGNOFF.md (Plan 07) attestation is the secondary gate.
- **T-05-03-04 (Subprocess injection in qmicli argv):** mitigated — argv is list-form; `descriptor.cdc_wdm` is pydantic-validated against `r"^cdc-wdm\\d+$"`; no shell interpolation. Verified by grep-search.
- **T-05-03-05 (SP-04 bypass):** mitigated — capture verb lives under `src/spark_modem/cli/ctl/`; SP-04 lint scope applies; explicit grep returns 0.
- **T-05-03-06 (DoS via hostile huge Zao log):** accepted — Zao log is operator-controlled root-owned; not an attacker surface. `_capture_zao_log_sample` reads the whole file but the typical Zao log is 1-10 MiB.
- **T-05-03-07 (Daemon-coupling defect — accidental preflight trigger):** mitigated — capture verb is a ctl subcommand; `grep -rn 'from spark_modem.daemon' src/spark_modem/cli/ctl/capture_fleet_fixture.py` returns 0 matches.

No threat-flag entries needed — the capture verb's surface is internal to the CLI; no new network endpoints, no new auth paths, no new trust boundaries.

## Known Stubs

None. The capture verb is a complete X-01 / X-02 deliverable; the implementation is exercised end-to-end by 7 unit tests + 3 integration tests against real Phase 2 qmicli fixtures + Phase 5 version fixtures.

The `_test/` example fleet fixture at `tests/fixtures/fleet/_test/triple.json` is INTENTIONALLY a placeholder for the layout (RESEARCH Q10 §752); real per-box fixtures land via the X-04 capture sweep before Phase 6. This is not a stub; it is the example committed by design.

## Next Phase Readiness

- **Plan 05-04 (preflight_check_known_fleet_triple)** can now consume `triple.json` files produced by `capture-fleet-fixture`. The schema_version + 3-field triple shape is the inter-plan contract. The `first_seen_iso` ISO-8601-with-Z format is the timestamp format preflight will parse.
- **Plan X-04 (Phase 5 capture sweep)** can now invoke `spark-modem ctl capture-fleet-fixture --out=tests/fixtures/fleet/<box-id>` on each bench/field Jetson; the produced directory tree lands under `tests/fixtures/fleet/<box-id>/` and is committed alongside the `_test/` example.
- **No blockers.** The verb works end-to-end; PII redaction is verified; ADR-0009 keying is enforced; SP-04 is preserved; X-03 chicken-and-egg is solved.

## Self-Check

Verifying SUMMARY claims against actual repo state.

**Files created — all present:**

- `S:/spark/modem-watchdog/src/spark_modem/cli/ctl/capture_fleet_fixture.py` — FOUND
- `S:/spark/modem-watchdog/tests/unit/cli/test_redact_raw_qmicli.py` — FOUND
- `S:/spark/modem-watchdog/tests/unit/cli/ctl/__init__.py` — FOUND
- `S:/spark/modem-watchdog/tests/unit/cli/ctl/test_capture_fleet_fixture.py` — FOUND
- `S:/spark/modem-watchdog/tests/integration/test_fleet_fixture_roundtrip.py` — FOUND
- `S:/spark/modem-watchdog/tests/fixtures/qmicli/uim_get_card_status/1.30/with_iccid.txt` — FOUND
- `S:/spark/modem-watchdog/tests/fixtures/fleet/_test/triple.json` — FOUND

**Files modified — both present and contain the new symbols:**

- `S:/spark/modem-watchdog/src/spark_modem/cli/redact.py` — FOUND; `grep -c "def redact_pii_from_raw_qmicli"` = 1
- `S:/spark/modem-watchdog/src/spark_modem/cli/main.py` — FOUND; `grep "ctl_capture_fleet" | wc -l` = 2

**Commits cited — all present in git log:**

- `f42a225` — FOUND (test: RED for Task 1)
- `a40daef` — FOUND (feat: GREEN for Task 1)
- `721c5c6` — FOUND (test: RED for Task 2)
- `a5ebdb4` — FOUND (feat: GREEN for Task 2)
- `018d210` — FOUND (test: Task 3 integration)

## Self-Check: PASSED

---
*Phase: 05-bench-field-shadow*
*Completed: 2026-05-11*

# Phase 5 Plan 04: X-03 Daemon Preflight (preflight_check_known_fleet_triple) Summary

**Shipped the X-03 daemon preflight gate: daemon refuses to start when the local (em7421_firmware, zao_sdk, libqmi) triple is not in the dpkg-managed known-fleet index — final gate of the X-* deliverable family, locking the contract between Plan 05-03's capture verb and the daemon's startup path.**

## Performance

- **Duration:** ~6 min wall-clock (4 commits across 5m 42s of git activity)
- **Started:** 2026-05-11T08:59:16Z (record_start_time before Task 1 RED)
- **Completed:** 2026-05-11T09:04:59Z (after Task 2 GREEN)
- **Tasks:** 2/2 complete (each RED+GREEN pair = 4 task-level commits)
- **Files modified:** 5 (3 created, 2 modified)

## Accomplishments

- **`UnknownFleetTriple`** RuntimeError subclass at `src/spark_modem/daemon/preflight_triple.py:53` — matches PreflightFailed shape (N818 noqa); composed at the call site in `daemon/main.py` rather than via inheritance.
- **`_load_known_triples(known_fleet_dir)`** at `preflight_triple.py:64` — walks `<box-id>/triple.json` one level deep; skips + warns on `JSONDecodeError`/`KeyError`/`ValueError` (pydantic ValidationError absorbed as ValueError subclass); never raises; returns `[]` on missing directory (caller handles).
- **`_compute_local_triple(*, zao_log_path)`** at `preflight_triple.py:97` — production probe path: SysfsInventory().scan() → first descriptor's QmiWrapper.dms_get_revision → `compute_fleet_triple` (Plan 05-02) → translates `QmiVersionDetectionFailed` to `UnknownFleetTriple`; raises if no Sierra modems found on sysfs.
- **`preflight_check_known_fleet_triple(*, known_fleet_dir, zao_log_path, local_triple=None)`** at `preflight_triple.py:121` — X-03 gate. `local_triple=None` triggers production probe path; tests pass `local_triple` directly. Empty/missing index AND no-match cases both raise `UnknownFleetTriple` with operator-actionable messages including local triple values and the remedy command (`spark-modem ctl capture-fleet-fixture --out=/tmp/fixture`).
- **Daemon wiring at `daemon/main.py:222-234`** — Step-3.5 X-03 preflight block immediately after the FR-60 block (Step 3) and before `classify_prior_run` (Step 4) / `acquire_pid_lock` (Step 5). Failure path mirrors FR-60: `write_last_config_error` + `logger.error(...)` + `return 78` (EX_CONFIG). Boot classifier reads marker on next boot and emits `DaemonRestart(reason=CONFIG_INVALID)`.
- **Same `--skip-preflight` bypass** — wrapped inside the same `if not args.skip_preflight:` guard so `spark-modem-watchdog --laptop --skip-preflight` still works on non-Jetson dev hosts.
- **READY=1 is never reached on triple mismatch** — _production_main returns 78 BEFORE acquiring the PID lock, BEFORE constructing `SdNotifyLifecycle`, and therefore BEFORE the placeholder `READY=1` wiring Plan 03-09 will land. The systemd unit (`Type=notify`) marks the boot as failed because READY was never sent. Verified end-to-end by `test_unknown_triple_exits_78_and_writes_marker`.
- **PID lock leakage prevented** — the new preflight slots BEFORE `acquire_pid_lock`; failure exits cleanly without ever holding the lock (T-05-04-06 mitigated).
- **Daemon NEVER writes to `/etc/spark-modem-watchdog/known-fleet/`** — grep against the module body returns zero code-level write paths (T-05-04-05 mitigated).
- 12 new tests across 2 files (9 unit + 3 integration), all green in 0.65s.
- Full repo regression: **2030 passed / 90 skipped in 21.68s** (up from 2018; well under M7 ≤30s budget).
- `ruff check` + `mypy --strict` clean on all changed source files; SP-04 invariant preserved (`grep -rEn 'create_subprocess_exec|subprocess.run' src/spark_modem/daemon/preflight_triple.py` returns 0 matches).

## Final placement of X-03 preflight block

`daemon/main.py` startup order BEFORE this plan (unchanged Step numbers from Phase 3):

```
Step 1   argparse                            (line ~183)
Step 2   build Settings                      (lines 187-199)
Step 3   FR-60 preflight (preflight_check)   (lines 205-215)
Step 4   classify_prior_run                  (line 218)
Step 5   acquire_pid_lock                    (line 223)
```

After this plan:

```
Step 1   argparse                                                 (line ~183)
Step 2   build Settings                                           (lines 187-199)
Step 3   FR-60 preflight (preflight_check)                        (lines 205-215)
Step 3.5 X-03 preflight (preflight_check_known_fleet_triple)      (lines 217-228)  ← NEW
Step 4   classify_prior_run                                       (line 231 was 218)
Step 5   acquire_pid_lock                                         (line 236 was 223)
```

The two preflight blocks are structurally identical (both gated on `if not args.skip_preflight:`, both catching their respective exception class, both calling `write_last_config_error` + `logger.error` + `return 78`). No other changes to main.py — the existing FR-60 block, PID lock acquisition, sd_notify wiring, and TaskGroup placeholder all remain unchanged.

## Test-injection adjustments for `_production_main` args shape

`_production_main` reads only `args.skip_preflight` directly — the outer `main()` dispatches `args.laptop` before reaching production main. The integration test's `_make_args` helper sets both `skip_preflight` (test parameter) and `laptop=False` (defensive default) on a vanilla `argparse.Namespace`. No additional fields were required; all 3 integration tests pass.

## Confirmation: ZERO writes to /etc/spark-modem-watchdog/known-fleet/

```text
$ grep -rEn 'write_bytes|write_text|atomic_write_bytes|open\(.*['\"]w['\"]' \
    src/spark_modem/daemon/preflight_triple.py
# Returns: only docstring matches (anti-pattern documentation), zero code-level writes
```

Daemon is read-only against the known-fleet directory by design (dpkg-managed; Plan 05-06 ships it). T-05-04-05 mitigated.

## Task Commits

Each task followed the RED → GREEN cycle (no REFACTOR needed):

1. **Task 1 RED:** add failing tests for `preflight_check_known_fleet_triple` — `3cfe990` (test)
2. **Task 1 GREEN:** implement `preflight_check_known_fleet_triple` module — `3849261` (feat)
3. **Task 2 RED:** add failing integration tests for daemon main.py wiring — `6ac7296` (test)
4. **Task 2 GREEN:** wire `preflight_check_known_fleet_triple` into `_production_main` — `16dc6b3` (feat)

## Files Created/Modified

### Created (3)

- **`src/spark_modem/daemon/preflight_triple.py`** (167 LOC). Module docstring documents X-03 contract, exit-code-78 + last-config-error marker semantics, dpkg-managed read-only invariant, and one-level-deep directory walk. Exports `UnknownFleetTriple`, `preflight_check_known_fleet_triple`; private helpers `_load_known_triples` + `_compute_local_triple`. Module constants `_KNOWN_FLEET_DIR` (`/etc/spark-modem-watchdog/known-fleet`) + `_DEFAULT_ZAO_LOG_PATH` (`/var/log/zao-remote-endpoint.log`).
- **`tests/unit/daemon/test_preflight_triple.py`** (150 LOC, 9 tests). Cases: RuntimeError subclass; empty-dir raises (`empty or missing`); missing-dir raises (`empty or missing`); matching triple passes; mismatching triple raises (`unknown fleet triple`); multi-entry one-match passes; malformed entry skipped + warned; all-malformed raises (falls into empty branch); nested triple.json NOT picked up. `_LOCAL` constant + `_write_triple` helper share the FleetTriple shape across tests.
- **`tests/integration/test_daemon_preflight_triple.py`** (~200 LOC, 3 tests). Cases: unknown-triple exits 78 + marker contains either branch's message; `--skip-preflight` bypasses the triple check (assert called["triple_check"] == 0); matching-triple proceeds past preflight to PID lock acquisition (sentinel exception from `acquire_pid_lock`). `patched_environment` fixture monkeypatches `build_default_settings` (binds Settings paths to tmp_path) + `preflight_check` (FR-60 no-op stub).

### Modified (2)

- **`src/spark_modem/daemon/main.py`** (+18 LOC). Added `UnknownFleetTriple` + `preflight_check_known_fleet_triple` import block (alphabetised with the existing preflight imports); added Step-3.5 X-03 preflight block immediately after the FR-60 block; added structured logger.error line for the unknown-triple case.
- **`.planning/ROADMAP.md`** (2 checkboxes). Flipped both `05-03-PLAN.md` (missed by 05-03's executor — see ROADMAP NOTE in this plan's prompt) AND `05-04-PLAN.md` to `[x]`. `gsd-sdk query roadmap.update-plan-progress 05 05-04 complete` returned `updated: false / no matching checkbox found` because Phase 5's roadmap uses plain bullet shape, not the per-plan checkbox shape the CLI recognises (orchestrator predicted this); direct edit per the prompt's fallback.

## Decisions Made

- **`UnknownFleetTriple` subclasses `RuntimeError` directly (not `PreflightFailed`).** Matches the shape per CONTEXT.md X-03 and follows Plan 05-02's `QmiVersionDetectionFailed` convention. Different module + different framing (X-03 vs FR-60) — inheritance would conflate the call-site try/except pattern. `daemon/main.py` composes them with sibling try/except blocks.

- **Test-injection via `local_triple: FleetTriple | None = None` parameter.** Production callers pass `None` and `_compute_local_triple` hits sysfs + qmicli + Zao log; tests pass `local_triple` directly. Eliminates the need to monkeypatch `SysfsInventory` / `QmiWrapper` / `compute_fleet_triple` in unit tests. Direct echo of Plan 05-02's `wrapper: object` duck-typing decision.

- **`_load_known_triples` is sync (not async).** Pathlib operations on local filesystem are fast (~1ms); directory has at most ~10 entries (1 per fleet box); production preflight runs ONCE at startup before READY=1. Wrapping in `asyncio.to_thread` would be over-engineering. ASYNC240 not triggered because the function is plain sync `def`, not `async def`.

- **`ValidationError` caught as `ValueError`** in the malformed-entry except tuple. Pydantic's `ValidationError` is a `ValueError` subclass, so the existing `(json.JSONDecodeError, KeyError, ValueError)` catch tuple absorbs it without needing a pydantic-specific import. Keeps the skip-and-warn branch single-pathed.

- **Step 3.5 placement: AFTER FR-60 preflight, BEFORE classify_prior_run + acquire_pid_lock.** RESEARCH Q4 §307-321: failure must not leave a stale PID lock (lock not yet held); failure must not lose the boot classifier's view of the prior run (classifier just hasn't run yet — this preflight is another way to mark CONFIG_INVALID on the current boot). The marker that this preflight writes will be read by the NEXT boot's classifier.

- **Same `--skip-preflight` guard shared with FR-60** — wrapped inside the existing `if not args.skip_preflight:` block. Single flag toggles both gates; preserves the laptop / dev workflow. Verified by `test_skip_preflight_bypasses_triple_check`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Test file ruff lints: N818 + PLC0415 on `_Sentinel` / inline `import contextlib`**

- **Found during:** Task 2 GREEN (post-implementation ruff sweep on `tests/integration/test_daemon_preflight_triple.py`)
- **Issue:** The plan-text Task 2 §622-630 used `class _Sentinel(Exception): pass` and `import contextlib` inside the test functions. Ruff `N818` flagged the exception name (should end in `Error`), and `PLC0415` flagged the two inline imports (should be at module top).
- **Fix:** Renamed both occurrences of `_Sentinel` → `_SentinelError`; hoisted `import contextlib` to the module's top-of-file import block (between `argparse` and `json` alphabetically).
- **Files modified:** `tests/integration/test_daemon_preflight_triple.py`.
- **Verification:** `ruff check tests/integration/test_daemon_preflight_triple.py` exits 0; 3/3 tests still pass.
- **Committed in:** `16dc6b3` (Task 2 GREEN, alongside the daemon main.py wiring).

**2. [Rule 2 — Critical] `monkeypatch` on `daemon_main.build_default_settings`, not env vars**

- **Found during:** Task 2 RED (writing the `patched_environment` fixture)
- **Issue:** Plan-text Task 2 §556-577 used `monkeypatch.setenv("SPARK_MODEM_RUN_DIR", ...)` and similar to bind paths to tmp_path. `build_default_settings` (`src/spark_modem/cli/clients.py:98`) HARDCODES `state_root="/tmp/spark-modem-cli"` (not read from env), so the env vars would be ignored — and the test would write `last-config-error` into `/tmp/spark-modem-cli/run/` on POSIX (or fail outright on Windows where `/tmp` doesn't resolve).
- **Fix:** Used `monkeypatch.setattr(daemon_main, "build_default_settings", fake_build_default_settings)` where `fake_build_default_settings` constructs a `Settings` instance bound to `tmp_path` (state_root + run_dir + events_log_path all under the test's tmp_path). This is the cleanest seam — the `daemon_main` module imports `build_default_settings` at module load time, so `setattr` on the module-level binding swaps the symbol cleanly.
- **Files modified:** `tests/integration/test_daemon_preflight_triple.py` (`patched_environment` fixture).
- **Verification:** 3/3 integration tests pass; `last-config-error` lands in the test's tmp_path/run/ directory; no `/tmp/spark-modem-cli` writes.
- **Committed in:** `6ac7296` (Task 2 RED, applied at test-authoring time).

---

**Total deviations:** 2 auto-fixed (1 Rule 2 critical, 1 Rule 3 blocking lint). No scope creep; no architectural decisions; Rule 4 did not fire.

**Impact on plan:** Deviation 1 is mechanical lint cleanup; Deviation 2 is a small but important seam change (module-attr patch vs env-var patch). The plan-text's env-var approach would have silently written to `/tmp/spark-modem-cli` on POSIX and failed on Windows — Plan 05-02's deviation log called this drift pattern out exactly: "plan text describes the contract, real code defines it; when they disagree the real code wins."

## Issues Encountered

- **`PreToolUse:Edit` hook noise on Edit-after-Edit on the same file:** the hook flagged each Edit on `main.py`, `test_daemon_preflight_triple.py`, and `ROADMAP.md` after they were already read in the session. Same friction Plans 05-02 + 05-03 SUMMARYs documented. Every Edit succeeded.
- **No active git pre-commit hook on this Windows dev host:** `.git/hooks/pre-commit` absent so ruff/mypy/SP-04 lint did not run automatically. Ran them manually after each task GREEN.

## TDD Gate Compliance

All 2 tasks are `type="auto" tdd="true"`. Plan-level type is `execute` (not `tdd`), so plan-level RED→GREEN→REFACTOR gates do not apply, but each task followed the RED → GREEN cycle:

| Task | RED commit | GREEN commit | REFACTOR |
| ---- | ---------- | ------------ | -------- |
| 1    | `3cfe990` (test) | `3849261` (feat) | not needed |
| 2    | `6ac7296` (test) | `16dc6b3` (feat) | not needed (lint fixes folded into GREEN) |

RED-phase failure verification:

- Task 1 RED: `ModuleNotFoundError: No module named 'spark_modem.daemon.preflight_triple'`
- Task 2 RED: `AttributeError: module 'spark_modem.daemon.main' has no attribute 'preflight_check_known_fleet_triple'`

## Verification Summary

| Check | Status |
| ----- | ------ |
| `pytest tests/unit/daemon/test_preflight_triple.py tests/integration/test_daemon_preflight_triple.py -q` (plan scope) | **12 passed in 0.65s** |
| `pytest tests/integration/test_lifecycle.py -q` (no regression to lifecycle suite) | 6 skipped (POSIX-only on Windows; expected) |
| `pytest -q` (full repo suite — M7 ≤30s budget) | **2030 passed, 90 skipped in 21.68s** (M7 30s budget preserved) |
| `ruff check src/spark_modem/daemon/preflight_triple.py src/spark_modem/daemon/main.py tests/unit/daemon/test_preflight_triple.py tests/integration/test_daemon_preflight_triple.py` | All checks passed |
| `mypy --strict src/spark_modem/daemon/preflight_triple.py src/spark_modem/daemon/main.py` | Success: no issues found in 2 source files |
| `bash scripts/lint_no_subprocess.sh` (SP-04 invariant) | exit 0; 0 violations |
| `grep -rEn 'create_subprocess_exec\|subprocess\.run' src/spark_modem/daemon/preflight_triple.py` | 0 matches |
| `grep -c "async def preflight_check_known_fleet_triple" src/spark_modem/daemon/preflight_triple.py` | 1 |
| `grep -c "class UnknownFleetTriple" src/spark_modem/daemon/preflight_triple.py` | 1 |
| `grep -c "preflight_check_known_fleet_triple" src/spark_modem/daemon/main.py` | 2 (import + call) |
| `grep -n "preflight_check_known_fleet_triple\|preflight_check[^_]" src/spark_modem/daemon/main.py` | line 52 (preflight_check import) BEFORE line 57 (preflight_check_known_fleet_triple import); line 212 (preflight_check call) BEFORE line 228 (preflight_check_known_fleet_triple call) — ordering invariant satisfied |

## Threat Surface Scan

The plan's `<threat_model>` covers six threats (T-05-04-01 .. T-05-04-06). Disposition verification:

- **T-05-04-01 (DoS via corrupted/missing known-fleet):** mitigated — empty-dir + missing-dir + all-malformed paths all raise structured `UnknownFleetTriple` with operator-actionable messages (test_empty_known_dir_raises, test_missing_known_dir_raises, test_malformed_triple_only_raises). Plan 05-06 will ship an example fixture so the post-install state is never literally empty.
- **T-05-04-02 (Tampering — operator hand-edits triple.json):** accepted; operator with sudo can also `--skip-preflight`. Out of Phase 5 scope.
- **T-05-04-03 (Information disclosure — firmware/SDK leak in journalctl):** accepted; version strings are not PII (per Plan 05-02 T-05-02-04).
- **T-05-04-04 (Daemon-startup regression — `--skip-preflight` workflow broken):** mitigated — new check gated by same `if not args.skip_preflight:` block; pinned by `test_skip_preflight_bypasses_triple_check`.
- **T-05-04-05 (Privilege escalation — daemon writes to /etc/spark-modem-watchdog/known-fleet/):** mitigated — grep returns 0 write-path references in the module body (docstring matches only). Daemon is read-only by design.
- **T-05-04-06 (PID lock leakage on preflight failure):** mitigated — preflight slots BEFORE `acquire_pid_lock`; failure exits cleanly without holding the lock. Implicitly verified by `test_unknown_triple_exits_78_and_writes_marker` (marker written; `acquire_pid_lock` monkeypatched out and never invoked).

No new threat surface beyond plan dispositions. No `threat_flag` entries needed — the new module is internal preflight; no network endpoints, no auth paths, no new trust boundaries.

## Known Stubs

None. The preflight is a complete X-03 deliverable. The production path (when `local_triple=None`) calls `_compute_local_triple` which hits SysfsInventory + QmiWrapper + Zao log via `compute_fleet_triple` (Plan 05-02); on a dev host without modems it cleanly raises `UnknownFleetTriple("no Sierra modems found on sysfs; ...")` — not a stub, but the documented dev-host behavior. All test cases inject `local_triple` directly to exercise the gate logic without hardware.

The `/etc/spark-modem-watchdog/known-fleet/` directory does NOT exist on a dev host; Plan 05-06 (`debian/spark-modem-watchdog.install` modification) will ship it via dpkg. Until then, a non-test-mode daemon would hit the "empty or missing" branch — which is the correct behavior, just unfortunate UX for an out-of-band dev install. Documented behavior, not a stub.

## Next Phase Readiness

- **Plan 05-06 (.deb install)** can now ship `/etc/spark-modem-watchdog/known-fleet/` via `debian/spark-modem-watchdog.install` (or `.dirs`) knowing the daemon will read its `<box-id>/triple.json` files at startup and fail closed on mismatch. The contract is one-level-deep `<box-id>/triple.json`.
- **Phase 6 (cutover)** can rely on the X-03 gate to prevent v2 from starting on an undocumented box. The operator workflow becomes: capture fixture via `spark-modem ctl capture-fleet-fixture` → commit `triple.json` to `tests/fixtures/fleet/<box-id>/` → next .deb release ships it under `/etc/spark-modem-watchdog/known-fleet/` → daemon starts cleanly.
- **No blockers.** The X-* deliverable family (X-01 capture verb, X-02 PII redaction, X-03 daemon gate) is complete end-to-end on dev host; remaining Phase 5 plans are .deb install (05-06), operator docs (05-07), and manual soak workflow (05-08).

## Self-Check

Verifying SUMMARY claims against actual repo state.

**Files created — all present:**

- `S:/spark/modem-watchdog/src/spark_modem/daemon/preflight_triple.py` — FOUND
- `S:/spark/modem-watchdog/tests/unit/daemon/test_preflight_triple.py` — FOUND
- `S:/spark/modem-watchdog/tests/integration/test_daemon_preflight_triple.py` — FOUND

**Files modified — both present and contain the new symbols:**

- `S:/spark/modem-watchdog/src/spark_modem/daemon/main.py` — FOUND; `grep -c "preflight_check_known_fleet_triple" = 2`
- `S:/spark/modem-watchdog/.planning/ROADMAP.md` — FOUND; 05-03 and 05-04 lines both checked

**Commits cited — all present in git log:**

- `3cfe990` — FOUND (test: RED for Task 1)
- `3849261` — FOUND (feat: GREEN for Task 1)
- `6ac7296` — FOUND (test: RED for Task 2)
- `16dc6b3` — FOUND (feat: GREEN for Task 2)

## Self-Check: PASSED

---
*Phase: 05-bench-field-shadow*
*Completed: 2026-05-11*

# Phase 5 Plan 05: Soak Audit Tools Summary

**Two post-hoc soak-audit tools (`audit_soak_zao.py` for S-01 #2 / ADR-0003 and `audit_soak_exhausted.py` for S-01 #3 / M4 / ADR-0006-amendment) that the on-site engineer runs at bench-week-end and field-2-weeks-end to validate the two non-trivial Phase 5 exit gates from events.jsonl + Zao log replay; 12 unit tests covering the classification matrix; SP-04 exempt; both scripts emit JSON reports and exit non-zero on violations.**

## Performance

- **Duration:** ~7 min wall-clock (4 commits across 7m 12s of git activity, 11:14:24 → 11:21:36 +0300)
- **Started:** 2026-05-11T11:14:24+03:00 (Task 1 RED commit)
- **Completed:** 2026-05-11T11:21:36+03:00 (Task 2 GREEN commit)
- **Tasks:** 2/2 complete (each as RED+GREEN pair = 4 task-level commits)
- **Files modified:** 5 created, 0 modified

## Accomplishments

- **`tools/audit_soak_zao.py`** (~280 LOC) — Reads events.jsonl + rotated siblings as raw dicts, parses Zao log forward into a sorted list of `_ZaoBlock(ts_iso, active_lines)` snapshots, joins by ts_iso (latest block with `ts_iso <= event.ts_iso`), and classifies each `action_planned` event as violation / no_zao_snapshot_for_cycle / clean. Exit 1 on any violation, 0 otherwise (2 on operational error). Supports `--since-iso` lower-bound filter.
- **`tools/audit_soak_exhausted.py`** (~310 LOC) — Groups `state_transition` events by `usb_path`, walks each modem's history forward looking for `to_state='exhausted'` transitions, and classifies each as `explained_hardware` (triggering_issue.detail is in the locked hardware-failure set), `explained_streak_below_k` (insufficient consecutive `to_state='healthy'` lookback), or `unexplained` (>=K healthy then exhausted = ADR-0006 regression). Exit 1 on any unexplained, 0 otherwise. Supports `--decay-k` override for sensitivity sweeps.
- **`tests/unit/tools/`** — New test sub-package (first tests under `tests/unit/tools/`). 12 tests in 0.51s; covers the full classification matrix for both audit tools plus an anti-pattern grep test (`test_match_pattern_used_not_if_elif`) that pins the `match`-not-`if/elif` contract on `audit_soak_exhausted.py`.
- **Read-only contract preserved.** No `StateStore.save_*` or `atomic_write_bytes` calls in either tool — verified by `grep -rEn 'StateStore.save|atomic_write_bytes' tools/audit_soak_*.py` returning zero (T-05-05-04 mitigation).
- **Full unit suite green.** 928 pass / 83 skip / 0 fail in 14.62s on Windows dev host (well under M7 30s budget).

## `_HARDWARE_FAILURE_DETAILS` set

Final locked frozenset values (from `tools/audit_soak_exhausted.py:113-121`, sourced verbatim from `src/spark_modem/wire/enums.py` IssueDetail enum):

```
{
    "enumeration_overcurrent",
    "enumeration_address_fail",
    "usb_overcurrent",
    "thermal_throttle",
    "tegra_hub_psu_droop",
}
```

Conservative: a NEW IssueDetail variant added in a future plan will classify a triggered Exhausted as UNEXPLAINED rather than silently EXPLAINED (operator disposition via F-04 audit trail; threat T-05-05-05 accept disposition).

## `_DECAY_K_DEFAULT` resolution

The audit script attempts to import the production decay constant in three stages via `_resolve_decay_k_default()`:

1. **`spark_modem.policy.engine._DECAY_K_DEFAULT`** — forward-compat; **not currently present** in the Phase 1-4 codebase. The helper uses `getattr` so the `ImportError` / `AttributeError` path is silent.
2. **`Settings.model_fields["healthy_streak_decay_k"].default`** — the actual current production source-of-truth at `src/spark_modem/config/settings.py:84-89`. Defaults to **10** today.
3. **Literal `10`** — ADR-0006 default; final fallback.

On the current codebase, stage 2 wins and resolves `_K_DEFAULT = 10`. A future refactor that promotes the constant to a module-level `Final` will be picked up at stage 1 automatically without audit-script edits.

## Raw-dict event reader (intentional, not pydantic)

Both tools define their own private `_read_events_as_raw_dicts` helper rather than reusing `spark_modem.cli.ctl.history.read_events_with_rotated_siblings`. Rationale (from the audit module docstrings):

> The history.py function yields validated pydantic ``Event`` objects via ``EventAdapter.validate_json``, which would couple the audit to the daemon's Event union. The audit's value proposition is that it does NOT break when the Event union shape evolves. We read events.jsonl directly as JSONL and skip non-dict / malformed lines silently.

Verification grep: `read_events_with_rotated_siblings` appears in each tool only inside the design-rationale comment block (non-comment occurrences = 0).

## Task Commits

Each task was committed atomically as a TDD RED/GREEN pair (per the plan's `tdd="true"` annotation on both tasks):

1. **Task 1 RED:** `5d25835` — failing tests for `audit_soak_zao.py` (S-01 #2 detector)
2. **Task 1 GREEN:** `60cc96e` — implement `audit_soak_zao.py` (6 tests pass)
3. **Task 2 RED:** `dd15fb4` — failing tests for `audit_soak_exhausted.py` (S-01 #3 detector)
4. **Task 2 GREEN:** `11a185c` — implement `audit_soak_exhausted.py` (6 tests pass)

No REFACTOR commit was needed — both GREEN implementations matched the plan's analog shape with the deviations called out in-source (event shape, decay-K resolution).

## Files Created/Modified

- `tools/audit_soak_zao.py` — new 300-line SP-04-exempt one-shot script; argparse + `main(argv) -> int` + 0/1/2 exit-code contract + JSON report at `--out`. Docstring declares SP-04 exemption verbatim from `tools/pull_replay_traces.py:18-21`.
- `tools/audit_soak_exhausted.py` — new 334-line SP-04-exempt one-shot script; same skeleton as audit_soak_zao + `_resolve_decay_k_default()` policy-module probe + `match`-on-to_state classifier (CLAUDE.md anti-pattern catalogue).
- `tests/unit/tools/__init__.py` — empty, establishes new test sub-package.
- `tests/unit/tools/test_audit_soak_zao.py` — 6 tests: violation, clean, no contemporaneous snapshot, mixed, corrupt JSONL, `--since-iso` filter. ~180 LOC.
- `tests/unit/tools/test_audit_soak_exhausted.py` — 6 tests: 11-healthy-then-exhausted (unexplained), hardware-failure (explained), short-streak (explained), no exhausted, `--decay-k` override, anti-pattern grep. ~180 LOC.

## Decisions Made

- **Event shape adjustment (Rule 3 deviation).** Plan's example tests used `who.usb_path` / `who.line`, but `src/spark_modem/wire/events.py` ActionPlanned and StateTransition variants carry a flat `usb_path` with NO `line` field. Audit derives line from the trailing dotted segment of `usb_path` (`2-3.1.N` -> N). Bench hardware always wires lines 1..4 to `2-3.1.{1..4}` (CLAUDE.md "Hardware target"); audit refuses to fabricate a line for malformed paths and classifies them as `unknown_line_derivation`.
- **Decay K resolution via dynamic getattr.** Plan's example code imported `_DECAY_K_DEFAULT` directly with `try/except`, but mypy strict + ruff format kept disagreeing on how to place the `# type: ignore[attr-defined]` on a parenthesized multi-line import. Switched to a `_resolve_decay_k_default()` helper that uses `getattr` for the forward-compat shim (stays import-clean against current module shape) and probes the Settings model field default as the canonical production fallback. Three-tier lookup keeps the audit working across refactors.
- **No shared `tools/_lib.py`.** `_read_events_as_raw_dicts` is duplicated across both tools; the plan explicitly defers a shared helper to "Phase 6+". This keeps tools/ as a flat directory of standalone one-shot scripts (matches `tools/pull_replay_traces.py` shape).
- **Both audits READ-ONLY.** Verified by `grep -rEn 'StateStore.save|atomic_write_bytes' tools/audit_soak_*.py` returning zero matches. Audits NEVER mutate state files (T-05-05-04 mitigation).
- **`match` not `if/elif` on ModemState.** The classifier in `audit_soak_exhausted.py` uses `match history[j].to_state:` per CLAUDE.md anti-pattern catalogue (precedent: `src/spark_modem/policy/transitions.py:69-100`). Test 6 (`test_match_pattern_used_not_if_elif`) pins this by grep-asserting the source.

## Deviations from Plan

### Rule 3 (blocking) — Event shape correction

**Found during:** Task 1 (RED test authoring)
**Issue:** Plan's example tests synthesized events with a `who={"usb_path": "...", "line": 1}` nested field, but `src/spark_modem/wire/events.py` ActionPlanned and StateTransition variants carry only a flat `usb_path` (no `who`, no `line`).
**Fix:** Tests use the actual flat schema. Audit derives `line` from the trailing dotted segment of `usb_path` via `_USB_PATH_LINE_RE = re.compile(r"\.(\d+)$")`. Documented in module docstring; called out in this SUMMARY's key-decisions.
**Files modified:** `tools/audit_soak_zao.py`, `tests/unit/tools/test_audit_soak_zao.py`, `tools/audit_soak_exhausted.py`, `tests/unit/tools/test_audit_soak_exhausted.py`
**Commits:** `5d25835`, `60cc96e`, `dd15fb4`, `11a185c`

### Rule 3 (blocking) — Decay-K constant resolution

**Found during:** Task 2 (GREEN implementation lint sweep)
**Issue:** Plan's example code imported `_DECAY_K_DEFAULT` from `spark_modem.policy.engine`, but that constant does not exist there — the actual production source-of-truth is `Settings.healthy_streak_decay_k` (default 10). Furthermore, mypy strict + ruff format disagreed on placement of `# type: ignore[attr-defined]` on a parenthesized multi-line import.
**Fix:** Replaced the bare `try: from ... import ... as _K_DEFAULT` with a `_resolve_decay_k_default()` helper that probes three sources via `getattr`: `policy.engine._DECAY_K_DEFAULT` (forward-compat), `Settings.healthy_streak_decay_k` field default (current production), literal 10 (final fallback). Two `# noqa: PLC0415` directives for the intentional lazy imports inside the helper.
**Files modified:** `tools/audit_soak_exhausted.py`
**Commits:** `11a185c`

No auto-fixes for bugs (Rule 1) or missing critical functionality (Rule 2) were applied. No authentication gates encountered (no external auth surface). No architectural decisions needed (Rule 4 did not fire).

## TDD Gate Compliance

Both tasks are `type="auto" tdd="true"`. The plan-level type is `execute` (not `tdd`), so the plan-level RED/GREEN/REFACTOR gate does not apply. Each individual task followed the RED → GREEN cycle:

| Task | RED commit | GREEN commit | REFACTOR |
| ---- | ---------- | ------------ | -------- |
| 1    | `5d25835` (test)  | `60cc96e` (feat) | not needed |
| 2    | `dd15fb4` (test)  | `11a185c` (feat) | not needed |

Each RED commit was verified to fail with `FileNotFoundError` (tool file absent) before the GREEN commit landed.

## Verification Summary

| Check | Status |
| ----- | ------ |
| `pytest tests/unit/tools/test_audit_soak_zao.py -q` | 6 passed in 0.44s |
| `pytest tests/unit/tools/test_audit_soak_exhausted.py -q` | 6 passed in 0.45s |
| `pytest tests/unit/tools/ -q` (full plan scope) | 12 passed in 0.51s |
| `pytest tests/unit/ -q` (full unit suite regression) | 928 passed, 83 skipped in 14.62s (M7 30s budget preserved) |
| `python tools/audit_soak_zao.py --help` | exit 0; --events / --zao-log / --since-iso / --out flags present |
| `python tools/audit_soak_exhausted.py --help` | exit 0; --events / --since-iso / --out / --decay-k flags present |
| `ruff check tools/audit_soak_zao.py tools/audit_soak_exhausted.py` | All checks passed |
| `ruff format --check tools/audit_soak_*.py` | 1 file already formatted, 1 file already formatted |
| `mypy --strict tools/audit_soak_zao.py tools/audit_soak_exhausted.py` | Success: no issues found |
| `grep -rEn 'StateStore.save\|atomic_write_bytes' tools/audit_soak_*.py` | 0 matches (read-only contract) |
| `grep -c '_read_events_as_raw_dicts' tools/audit_soak_zao.py` | 2 (definition + use site) |
| `grep -c '_read_events_as_raw_dicts' tools/audit_soak_exhausted.py` | 3 (definition + use site + docstring cross-reference) |
| `grep -E "if (history\[j\]\|t)\.to_state ==" tools/audit_soak_exhausted.py` | 0 matches (no if/elif on state) |
| `grep -c "match history\[j\]\.to_state" tools/audit_soak_exhausted.py` | 1 (the canonical match block) |
| `grep -c "## Subprocess discipline" tools/audit_soak_zao.py tools/audit_soak_exhausted.py` | 1 each (SP-04 exemption docstring) |
| `grep -c "from spark_modem.policy" tools/audit_soak_exhausted.py` | 1 (imports policy module safely via _resolve_decay_k_default) |

## Threat Surface Scan

No new threat surface introduced beyond the plan's `<threat_model>` dispositions:

- **T-05-05-01** (Tampering / corrupt JSONL crashes audit) — *mitigated*. `_read_events_as_raw_dicts` skips malformed lines silently via `json.JSONDecodeError` catch and additionally skips non-dict values defensively. Test 5 (`test_corrupt_jsonl_line_skipped_silently`) pins.
- **T-05-05-02** (Info disclosure / PII in audit report) — *mitigated*. Reports contain `usb_path`, `line`, `ts_iso`, `classification`, `triggering_detail` only — no ICCID/IMSI/IP. The events.jsonl input is already PII-redacted at write time (Phase 2 event_logger contract).
- **T-05-05-03** (DoS / huge events.jsonl OOMs audit) — *accept*. Audits are one-shot operator commands on dev laptop / box with ample memory; 30-day events.jsonl is typically 10-100 MiB.
- **T-05-05-04** (Integrity / audit mutates state) — *mitigated*. No `StateStore.save_*` or `atomic_write_bytes` calls; verified by grep returning zero matches.
- **T-05-05-05** (Tampering / false-negative exhausted classification missing a hardware-detail enum value) — *accept*. `_HARDWARE_FAILURE_DETAILS` is a frozenset; a new IssueDetail variant added in a future plan will classify the exhausted as UNEXPLAINED (conservative — false-positive over false-negative). Operator dispositions via F-04 audit trail.

No new endpoints, auth paths, or trust boundaries were created. No `threat_flag` entries needed.

## Self-Check

Verifying SUMMARY claims against actual repo state.

**Files created — all present:**
- `S:/spark/modem-watchdog/tools/audit_soak_zao.py` — FOUND
- `S:/spark/modem-watchdog/tools/audit_soak_exhausted.py` — FOUND
- `S:/spark/modem-watchdog/tests/unit/tools/__init__.py` — FOUND
- `S:/spark/modem-watchdog/tests/unit/tools/test_audit_soak_zao.py` — FOUND
- `S:/spark/modem-watchdog/tests/unit/tools/test_audit_soak_exhausted.py` — FOUND

**Commits cited — all present in git log:**
- `5d25835` — FOUND (test: RED for Task 1)
- `60cc96e` — FOUND (feat: GREEN for Task 1)
- `dd15fb4` — FOUND (test: RED for Task 2)
- `11a185c` — FOUND (feat: GREEN for Task 2)

## Self-Check: PASSED

# Phase 5 Plan 06: `.deb` ships /etc/spark-modem-watchdog/known-fleet/ via debian/install Summary

**Shipped the packaging side of X-03: dh_install copies tests/fixtures/fleet to /etc/spark-modem-watchdog/known-fleet/ at .deb build time, debian/dirs pre-creates the directory, and 6 integration tests pin the contract — postinst and debian/rules stay untouched per RESEARCH Q10. The X-* deliverable family is now complete end-to-end (capture verb → preflight gate → packaging shipment).**

## Performance

- **Duration:** ~4 min wall-clock (2 commits across ~3m 41s of git activity)
- **Started:** 2026-05-11T09:10:54Z
- **Completed:** 2026-05-11T09:14:35Z
- **Tasks:** 2/2 complete
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments

- **`debian/spark-modem-watchdog.install`** (`debian/spark-modem-watchdog.install:10`) — appended one declarative dh_install rule: `tests/fixtures/fleet /etc/spark-modem-watchdog/known-fleet/`. dh_install recursively copies the source directory tree, preserving the `<box-id>/triple.json` shape that Plan 05-04's `_load_known_triples` walks.
- **`debian/spark-modem-watchdog.dirs`** (`debian/spark-modem-watchdog.dirs:2`) — inserted `/etc/spark-modem-watchdog/known-fleet` alphabetically between `/etc/spark-modem-watchdog/conf.d` and `/var/lib/spark-modem-watchdog`. dpkg owns the directory even when `tests/fixtures/fleet/` is small (T-05-06-01 belt-and-suspenders).
- **`tests/integration/test_deb_ships_known_fleet.py`** (124 LOC, 6 tests) — pins the packaging contract end-to-end:
  - `test_deb_contains_known_fleet_path` — runs `dpkg-deb --contents` against the most recent built .deb under `dist/` or `../`; skipped via `shutil.which("dpkg-deb") is None` on hosts without dpkg-deb (Windows dev laptop) and via `pytest.skip` on hosts without a built artifact.
  - `test_debian_install_declares_known_fleet` — asserts `tests/fixtures/fleet` and `/etc/spark-modem-watchdog/known-fleet` are both present in `debian/spark-modem-watchdog.install` (catches accidental revert).
  - `test_debian_dirs_declares_known_fleet` — asserts `/etc/spark-modem-watchdog/known-fleet` is present in `debian/spark-modem-watchdog.dirs`.
  - `test_example_fleet_fixture_exists_and_is_valid` — asserts `tests/fixtures/fleet/_test/triple.json` exists and parses as JSON with non-empty `em7421_firmware`, `zao_sdk`, `libqmi` string fields (Plan 05-03 dependency + T-05-06-01 mitigation pin).
  - `test_no_known_fleet_references_in_postinst` — anti-pattern pin per RESEARCH Q10 §647-650.
  - `test_no_known_fleet_references_in_rules` — anti-pattern pin per RESEARCH Q10 §637.
- **No changes to `debian/spark-modem-watchdog.postinst`** (verified via `git diff HEAD~2 HEAD -- debian/spark-modem-watchdog.postinst` returns empty). Postinst stays scoped to user/group creation + ModemManager masking + state-dir creation + B-03 smoke test.
- **No changes to `debian/rules`** (verified via `git diff HEAD~2 HEAD -- debian/rules` returns empty). The existing `override_dh_auto_install` for the bundled CPython tree is untouched.
- **Plan 05-04 ↔ Plan 05-06 contract pinned** — the daemon reads `/etc/spark-modem-watchdog/known-fleet/<box-id>/triple.json` (preflight_triple.py:46 + 78-89); this plan ships exactly that path layout via dh_install's directory-copy semantics. No path drift.

## Verification Summary

| Check | Status |
| ----- | ------ |
| `pytest tests/integration/test_deb_ships_known_fleet.py -v` (plan scope) | **5 passed, 1 skipped in 0.30s** (dpkg-deb test skipped on Windows — expected) |
| `pytest tests/integration/ -q` (no regression to integration suite) | **39 passed, 8 skipped in 0.75s** (skips are pre-existing POSIX-only cases + the new dpkg-deb skip) |
| `pytest -q` (full repo — M7 ≤30s gate) | **2035 passed, 91 skipped in 18.35s** — up from 2030 baseline (+5 new tests; 6th is the skip). M7 budget preserved (18.35s ≤ 30s). |
| `ruff check tests/integration/test_deb_ships_known_fleet.py` | All checks passed |
| `ruff format --check tests/integration/test_deb_ships_known_fleet.py` | 1 file already formatted |
| `mypy --strict tests/integration/test_deb_ships_known_fleet.py` | Success: no issues found in 1 source file |
| `grep -c "tests/fixtures/fleet /etc/spark-modem-watchdog/known-fleet" debian/spark-modem-watchdog.install` | 1 |
| `grep -c "^/etc/spark-modem-watchdog/known-fleet$" debian/spark-modem-watchdog.dirs` | 1 |
| `grep -c "known-fleet" debian/spark-modem-watchdog.postinst` | 0 |
| `grep -c "known-fleet" debian/rules` | 0 |
| `git diff --numstat` on the two debian/* files | each shows `+1 -0` (pure one-line addition; existing content untouched) |
| `ls tests/fixtures/fleet/_test/triple.json` | FOUND (Plan 05-03 dependency satisfied) |

## Did the dpkg-deb integration test run or skip on this host?

**SKIPPED.** The test host is Windows 11 (per env.OS Version); `shutil.which("dpkg-deb")` returns `None`, so the `@pytest.mark.skipif` decorator skips `test_deb_contains_known_fleet_path` cleanly with reason "dpkg-deb not on PATH (typical on non-Debian hosts including Windows dev laptops)". The other 5 tests (static debian/* parses + fixture validity + anti-pattern pins) ran unconditionally and all passed.

On a Debian build host running `dpkg-buildpackage -b` (or in CI), the test would discover the built `.deb` under `../*.deb` (where dpkg-buildpackage drops binaries by default) and assert `/etc/spark-modem-watchdog/known-fleet` is in the `dpkg-deb --contents` output. The dh_install rule guarantees this on every build; the test is the regression gate.

## Decisions Made

- **Followed RESEARCH Q10 final recommendation verbatim** — ship `tests/fixtures/fleet` directly as `/etc/spark-modem-watchdog/known-fleet/<box-id>/triple.json` (no sha-rename, no build-time index synthesis). The two alternative options from Q10 (override_dh_auto_install with explicit copy+rename, or a `tools/build_fleet_index.py` build-time tool) were both rejected by the research as more complex than necessary; this plan inherits that decision.

- **No changes to debian/postinst** — RESEARCH Q10 §647-650 is explicit: postinst stays scoped to ModemManager masking + state-dir creation; data shipment goes through dh_install. The test `test_no_known_fleet_references_in_postinst` pins this design as a regression gate.

- **No changes to debian/rules** — RESEARCH Q10 §637 is explicit: declarative `debian/install` is the simplest path; no `override_dh_auto_install` extension is needed for the read-only fleet index. The test `test_no_known_fleet_references_in_rules` pins this design as a regression gate.

- **Integration test sits in `tests/integration/` alongside `test_unit_file_audit.py`** — both tests are cross-platform-safe debian/* parsers; they share the same `_REPO_ROOT = Path(__file__).resolve().parents[2]` pattern. A dedicated `tests/packaging/` subtree would duplicate conftest.py infrastructure for one test file.

- **Two redundant assertions in `test_debian_install_declares_known_fleet`** — separately check that `tests/fixtures/fleet` (source) and `/etc/spark-modem-watchdog/known-fleet` (destination) are both in the install file. If a future refactor renames either side of the dh_install rule, the failure message points at the exact half that changed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 — Blocking] Ruff RUF100 + E501 lint errors in the initial test file**

- **Found during:** Task 2 post-implementation lint sweep.
- **Issue:** The integration test file initially shipped with (a) a `# noqa: S603` comment on the `subprocess.run` call — but `S603` is not enabled in this project's ruff config, so RUF100 flagged the noqa as unused; and (b) one assertion message that exceeded the 100-char line limit. Plan text described the file shape at the level of "what tests to write", not character-by-character formatting; these lint failures only surface after writing real code.
- **Fix:** Removed the unused `noqa: S603` directive (the call is fine without it — argv list, no shell, trusted args is project policy anyway); split the long assertion message across two adjacent string literals.
- **Files modified:** `tests/integration/test_deb_ships_known_fleet.py` (pre-commit, before the Task 2 commit was created).
- **Verification:** `ruff check` exits 0; `ruff format --check` exits 0; all 6 tests still pass (5 + 1 skip).
- **Committed in:** `bea9597` (Task 2 commit; lint fixes folded in before the commit was created — no second commit needed since the file was not yet on disk in git at the time the lint fix was applied).

**2. [Rule 3 — Cosmetic] Ruff `format` rewrap of multi-line `assert ... , (...)` triples**

- **Found during:** Task 2 post-implementation `ruff format --check` sweep.
- **Issue:** Three `assert path.is_file(), ("..." )` and `assert isinstance(...) and data[key], ("...")` triples were written with parenthesized continuations across two lines each. Ruff's formatter prefers the single-line form (lines were short enough to fit). Plus one `read_text(encoding="utf-8")` call that ruff wanted on a single line. Purely stylistic; no logic change.
- **Fix:** Ran `ruff format` to auto-collapse the assertions into single-line form. File is now stable under `ruff format --check`.
- **Files modified:** `tests/integration/test_deb_ships_known_fleet.py`.
- **Verification:** `ruff check` exits 0; `ruff format --check` exits 0; all 6 tests still pass.
- **Committed in:** `bea9597` (Task 2 commit; format fix folded in before the commit was created).

---

**Total deviations:** 2 auto-fixed (both Rule 3 lint/format). No scope creep; no architectural decisions; Rule 4 did not fire.

**Impact on plan:** Both deviations are cosmetic Python/lint hygiene. Plan text described the test file at the level of "behavior + 6 test bodies"; the lint passes are project hygiene that any new file must satisfy. Plan-text fidelity preserved on all behavioral assertions.

## Issues Encountered

- **`PreToolUse:Edit` hook noise on Edit-after-Write on the same file:** the hook flagged the post-Write Edit calls on `tests/integration/test_deb_ships_known_fleet.py` even though the file was just created via Write in the same session, and earlier Edits on `debian/spark-modem-watchdog.install` and `debian/spark-modem-watchdog.dirs` even though both files were Read at the start of execution. Same friction Plans 05-02 through 05-05 SUMMARYs documented. Every Edit succeeded.
- **Line-ending warnings (`LF will be replaced by CRLF`)** — Windows git autoCRLF behavior; the staged files are committed with LF as required for cross-platform debian/* parsing. Not a real issue.
- **No active git pre-commit hook on this Windows dev host:** `.git/hooks/pre-commit` absent so ruff/mypy/SP-04 lint did not run automatically. Ran them manually after Task 2.

## TDD Gate Compliance

Plan-level type is `execute` (not `tdd`), and individual tasks are `type="auto"` without explicit `tdd="true"` markers — so plan-level RED→GREEN→REFACTOR gates do not apply. The plan is structured as "write the data shipment first, then write the test that pins it", which is the natural shape for a packaging change where the production artifact (the debian/* files) is itself the source-of-truth and the test is verification.

| Task | Commit | Kind |
| ---- | ------ | ---- |
| 1    | `3407457` | `feat` (debian/* additions) |
| 2    | `bea9597` | `test` (integration test pinning the contract) |

No RED phase commit (would be a failing test against the not-yet-shipped debian/install line). The Task 1 → Task 2 ordering means the test was always green against the committed state, which is the correct shape for an `execute`-type plan.

## Threat Surface Scan

The plan's `<threat_model>` covers four threats (T-05-06-01 .. T-05-06-04). Disposition verification:

- **T-05-06-01 (DoS via empty/corrupted known-fleet at install time)** — **mitigated.** Plan 05-03's `tests/fixtures/fleet/_test/triple.json` is committed and shipped via the new dh_install rule (Test 4 of the integration test pins its existence + valid FleetTriple shape). Plan 05-04's empty-dir error path emits an operator-actionable journalctl message pointing at the `spark-modem ctl capture-fleet-fixture` capture command.
- **T-05-06-02 (Privilege escalation — daemon writes to /etc/spark-modem-watchdog/known-fleet/)** — **mitigated.** Plan 05-04's acceptance criterion already enforced zero write paths in `src/spark_modem/daemon/preflight_triple.py`; this plan doesn't add new write paths. Directory ownership is `root:root 0755` (dh_install default); files are `root:root 0644`. Daemon runs as root but never invokes write helpers against the known-fleet path.
- **T-05-06-03 (Tampering — operator hand-edits triple.json on the box)** — **accepted.** Threat actor has sudo; bypass via `--skip-preflight` is equally easy. Audit trail via git-blame on `tests/fixtures/fleet/<box-id>/`.
- **T-05-06-04 (Repudiation — dpkg upgrade silently replaces known-fleet entries with an older set)** — **accepted.** dpkg upgrade is atomic; if the new .deb's known-fleet is smaller than the old set, that's a deliberate scope change. Provenance tracked via .deb changelog + git history.

No new threat surface beyond plan dispositions. No network endpoints, no auth paths, no new trust boundaries — this is declarative file-copy packaging metadata.

## Known Stubs

None. The two debian/* additions are real shipping rules; the integration test exercises real paths (no mock filesystems). The example fixture `tests/fixtures/fleet/_test/triple.json` is a complete FleetTriple committed in Plan 05-03 — not a placeholder; it ships unaltered.

## Next Phase Readiness

- **X-* deliverable family complete end-to-end** — X-01 (capture verb in Plan 05-03), X-02 (PII redaction inside the verb), X-03 (daemon gate in Plan 05-04 + packaging shipment in this plan) all green.
- **X-04 batched-prereq PR (deferred to pre-Phase-6 physical access window per CONTEXT.md §X-04)** — when the on-site engineer captures per-box fixtures via `spark-modem ctl capture-fleet-fixture` and commits them to `tests/fixtures/fleet/<box-id>/`, the next `.deb` release will ship them automatically via the dh_install rule landed in this plan. No further debian/install or debian/rules edit needed.
- **Plan 05-07 (operator-facing soak runbook)** can reference the now-shipped path `/etc/spark-modem-watchdog/known-fleet/` directly — the chain "daemon refuses to start on unknown triple → operator runs `spark-modem ctl capture-fleet-fixture` → commits triple.json → next apt install ships it" is closed.
- **Plan 05-08 (SIGNOFF.md template + manual replay-harness exit gate)** is unaffected by this plan — the .deb shipment is structurally orthogonal to the SIGNOFF artifact.
- **No blockers.** Phase 5 remaining plans (05-07, 05-08) are pure docs + ops runbook + SIGNOFF template — no further code or packaging work expected in Phase 5.

## Self-Check

Verifying SUMMARY claims against actual repo state.

**Files created — present:**

- `S:/spark/modem-watchdog/tests/integration/test_deb_ships_known_fleet.py` — FOUND

**Files modified — both present with the +1 line each:**

- `S:/spark/modem-watchdog/debian/spark-modem-watchdog.install` — FOUND; `grep -c "tests/fixtures/fleet /etc/spark-modem-watchdog/known-fleet" = 1`
- `S:/spark/modem-watchdog/debian/spark-modem-watchdog.dirs` — FOUND; `grep -c "^/etc/spark-modem-watchdog/known-fleet$" = 1`

**Files NOT modified (must stay untouched):**

- `S:/spark/modem-watchdog/debian/spark-modem-watchdog.postinst` — `grep -c known-fleet = 0`; `git diff HEAD~2 HEAD -- debian/spark-modem-watchdog.postinst` returns empty
- `S:/spark/modem-watchdog/debian/rules` — `grep -c known-fleet = 0`; `git diff HEAD~2 HEAD -- debian/rules` returns empty

**Commits cited — all present in git log:**

- `3407457` — FOUND (`feat(05-06): ship /etc/spark-modem-watchdog/known-fleet/ via debian/install`)
- `bea9597` — FOUND (`test(05-06): add .deb shipment integration test for known-fleet directory`)

## Self-Check: PASSED

---
*Phase: 05-bench-field-shadow*
*Completed: 2026-05-11*

# Phase 5 Plan 07: Soak runbook + Phase 6 entry signoff template Summary

Authored the two operator-facing markdown artifacts the on-site engineer
uses across the 3+ week Phase 5 execution: SIGNOFF.md (Phase 6 entry
checklist, fillable template) and SOAK_RUNBOOK.md (daily checks +
soak-exit procedure + F-04 disposition workflow). Added a single
cross-reference line to docs/RUNBOOK.md. Doc-only plan; no code, no
tests.

## Tasks Completed

### Task 1: SIGNOFF.md template — commit `39a98b2`

Created `.planning/phases/05-bench-field-shadow/SIGNOFF.md` (124 lines)
with all 7 required sections per RESEARCH Q8:

1. Header front-matter (engineer name + bench/field box-ids + 4 ISO timestamps)
2. **S-01 Exit Gates** — 3 rows wired to evidence sources:
   - #1 Zero daemon crashes / OOM / unhandled exceptions (M6) →
     journalctl + `daemon_started` event count
   - #2 Zero action planned on Zao-active line (ADR-0003) →
     `tools/audit_soak_zao.py` JSON artifact
   - #3 Zero unexplained Exhausted transitions (M4) →
     `tools/audit_soak_exhausted.py` JSON artifact
3. **R-02 Replay-harness gate** — bar pinned at ≥95.0% fault-cycle
   agreement (R-03 hard-fail threshold)
4. **S-01.1 Informational metrics** (M5 cycle P99, NFR-3 RSS — explicitly
   non-blocking)
5. **F-04 Violations log** — table with verbatim "minor" + "dispositioned"
   definitions; explicit rule that every violation must be recorded
   regardless of disposition
6. **X-04 Fleet fixtures captured** — checklist of every fleet box +
   batched Phase-6-prereq PR open/merged status
7. **Free-text rationale (≤1000 words)** + **Phase 6 entry approval**
   signature block (4 mandatory boxes)

All operator-fillable slots left blank.

### Task 2: SOAK_RUNBOOK.md — commit `945e674`

Created `.planning/phases/05-bench-field-shadow/SOAK_RUNBOOK.md`
(266 lines) with all 7 required sections per RESEARCH Q9:

1. Front-matter table (status, owner, audience, scope, last-updated)
   + scope-context callout flagging v1-retired pivot
2. Soak windows (S-02): 1 week bench → S-03 handoff gate → 2 weeks field
3. **Daily operator checks** — 5 subsections:
   - 2.1 Daemon health (M6 / S-01 #1) — `journalctl` + `systemctl status`
   - 2.2 Cycle health (M5, informational) — status.json + Prom UDS
     scrape with ADR-0013-compliant `modem_state_value{modem=...}` form
   - 2.3 State scan (M4 / S-01 #3 incremental) — `by-usb/*.json` jq
   - 2.4 Action history (S-01 #2 + #3 incremental) —
     `spark-modem ctl history --since=24h` jq
   - 2.5 RSS tripwire (NFR-3) — `daemon_self_health{kind="rss"}`
4. **F-04 violation disposition workflow** — 5-step capture → classify →
   open issue + PR → record in SIGNOFF.md → 2nd-violation-resets-clock
5. **Soak-exit procedure** — 5 subsections invoking in order:
   `audit_soak_zao.py` → `audit_soak_exhausted.py` → pytest
   `tests/replay/test_v1_agreement.py` → fill SIGNOFF.md → open Phase 6
   entry PR (gated on X-04 batched PR merging first via
   `spark-modem ctl capture-fleet-fixture`)
6. R-01 day-1 trace pull (kickoff procedure for `tools/pull_replay_traces.py`)
7. Known gaps / antipatterns (ctl config-check repo gap + Prom one-hot
   label warning) + Cross-reference section

**ADR-0013 anti-pattern handling:** the literal `modem_state{state=`
syntax appears 0 times in the file (verified via grep). The legacy
one-hot label form is described in prose only ("DO NOT use the legacy
one-hot label form where a `state` label dimension was put on the
modem-state metric"). Operators copy-pasting from the runbook cannot
accidentally land on the wrong shape.

**`ctl config-check` handling:** appears exactly 1 time in the entire
file, exclusively in § 6 "Known gaps / antipatterns" where it is
explicitly flagged as broken. NOT referenced in any operator command.

### Task 3: docs/RUNBOOK.md cross-reference — commit `97d55f6`

Inserted exactly two lines (one prose + one blank separator) in
docs/RUNBOOK.md immediately after the intro prose and before the first
`---` divider:

```
For Phase 5 bench/field soak operations, see `.planning/phases/05-bench-field-shadow/SOAK_RUNBOOK.md`.
```

Pre-edit: 418 lines. Post-edit: 420 lines. Zero removals. The broader
doc-rewrite housekeeping (ROADMAP SC#1-3 rewording, MIGRATION Phase 1-2
reframe, PROJECT.md "v1 keeps fleet online" edit) stays deferred per
CONTEXT.md Deferred Ideas.

## Acceptance Criteria Verification

All Plan 05-07 must_haves satisfied:

- ☑ SIGNOFF.md template exists with all 7 sections (header front-matter,
  S-01 Exit Gates with 3 rows for M6/ADR-0003/M4, R-02 replay-harness
  gate, S-01.1 informational metrics, F-04 violations log, X-04 fleet
  fixtures, free-text rationale, Phase 6 entry approval signature)
- ☑ SOAK_RUNBOOK.md exists with daily-check commands, soak-exit
  procedure (audit_soak_zao + audit_soak_exhausted + replay-harness +
  SIGNOFF commit), F-04 disposition workflow
- ☑ SOAK_RUNBOOK.md does NOT reference `spark-modem ctl config-check` as
  an operator command (only flagged as broken in Known Gaps)
- ☑ SOAK_RUNBOOK.md uses `modem_state_value{modem}` not the legacy
  one-hot label form for Prom queries (ADR-0013)
- ☑ docs/RUNBOOK.md gets a single cross-reference line pointing at
  SOAK_RUNBOOK.md (NOT a doc rewrite)
- ☑ SIGNOFF.md references all 10 must_haves from Plan 05-08:
  R-01 / R-02 / R-04 (replay harness + R-01 day-1 commit row),
  S-02 / S-03 / S-04 (soak windows + handoff gate + signoff),
  X-04 (fleet fixtures section), M1 (availability — implicit in S-01
  daemon-uptime gate), M6 (S-01 #1), F-04 (violations log table)
- ☑ F-04 "minor violation" budget of 1/week explicit in both files

**Scope_pivot compliance:**
- `grep -c "tools/compare_v1_v2.py\|99-shadow.yaml\|spark-modem-watchdog-v2"`
  returns 0 for SIGNOFF.md, 0 for SOAK_RUNBOOK.md, 0 in the added
  docs/RUNBOOK.md cross-reference line.

## Deviations from Plan

None — plan executed exactly as written, with one minor adjustment for
acceptance-criterion consistency: the scope-context callout in
SOAK_RUNBOOK.md was rephrased to convey the v1-retired pivot without
using the literal strings `tools/compare_v1_v2.py`, `99-shadow.yaml`, or
`spark-modem-watchdog-v2`, since the acceptance criterion demands 0
occurrences of those strings. The intent (operators must know these
artifacts don't exist in this phase) is preserved by referring them to
`05-CONTEXT.md § scope_pivot` for the retired-artifact list.

## Self-Check: PASSED

- `.planning/phases/05-bench-field-shadow/SIGNOFF.md` — FOUND
- `.planning/phases/05-bench-field-shadow/SOAK_RUNBOOK.md` — FOUND
- `docs/RUNBOOK.md` — modified (1 cross-reference line) — FOUND in git diff
- Commit `39a98b2` — FOUND
- Commit `945e674` — FOUND
- Commit `97d55f6` — FOUND

---

*Phase 5: Bench & Field Shadow*
*Plan 05-07 — soak runbook + Phase 6 entry signoff template.*
*Completed 2026-05-11.*

# Phase 05 Plan 08: Operator Soak — Deferred to Human Operator

**Plan 05-08 is operator-bound by design; this SUMMARY exists only to unblock GSD tracking. Real Phase 5 exit is gated on the on-site engineer's SIGNOFF.md merge, not on this file.**

## Why a stub

Plan 05-08's own objective states:

> "Schedule: this plan spans ~3-4 weeks calendar time. The executor (Claude) does NOT run automated commands — every task is a checklist for the human operator."

All six tasks are `<task type="checkpoint:human-action" gate="blocking">`:

1. R-01 day-1 v1-trace pull + LFS PR merge
2. Bench Jetson 1-week clean soak + S-03 handoff
3. Field box 2-week clean soak (F-01 natural-faults-only)
4. X-04 fleet-fixture capture sweep + batched PR merge
5. R-02 replay-harness one-shot at Phase 5 exit
6. SIGNOFF.md fill + commit + Phase 6 entry PR merge

There is nothing for an executor agent to do that would not fabricate evidence (fake `phase5-evidence/bench/day-N/` files, fake merge SHAs, fake `replay-summary-phase5-exit.json` values, etc.).

## Where the live state lives

| Artifact                                                            | Role                                                                        |
|---------------------------------------------------------------------|-----------------------------------------------------------------------------|
| `.planning/phases/05-bench-field-shadow/05-HUMAN-UAT.md`            | 10 pending operator items; surfaces in `/gsd-progress` + `/gsd-audit-uat`. |
| `.planning/phases/05-bench-field-shadow/SIGNOFF.md`                 | Template awaiting engineer fill-in; merge is the real Phase 5 exit gate.   |
| `.planning/phases/05-bench-field-shadow/SOAK_RUNBOOK.md`            | Authoritative procedure for the operator (delivered by Plan 05-07).        |
| `.planning/phases/05-bench-field-shadow/05-VERIFICATION.md`         | `status: human_needed`; 30/40 must-haves verified (10 operator-bound).     |

When the operator returns with evidence, the correct entry point is `/gsd-verify-work 5` against `05-HUMAN-UAT.md`, then a follow-up commit of SIGNOFF.md + audit JSONs + replay-summary.

## Performance

- **Duration:** 0 min (no Claude execution)
- **Started:** 2026-05-11
- **Completed:** 2026-05-11 (deferral marker only)
- **Tasks:** 0 of 6 Claude-actionable (all 6 are human-action checkpoints)
- **Files modified:** 1 (this stub)

## Accomplishments

- Tracking advanced past Plan 05-08 without fabricating soak evidence.
- HUMAN-UAT.md explicitly named as the live tracking surface.
- Phase 5 exit gate (SIGNOFF.md merge) preserved intact for the on-site engineer.

## Task Commits

None. No executor work was performed. This SUMMARY is the only artifact this plan produces; the rest are produced by the operator outside the GSD execution loop.

## Files Created/Modified

- `.planning/phases/05-bench-field-shadow/05-08-SUMMARY.md` — this deferral marker.

## What Phase 6 should assume

- Plan 05-08's 6 operator tasks may still be running calendar-time when Phase 6 planning begins.
- The X-04 batched PR merge (Task 4) and the SIGNOFF.md merge (Task 6) MUST land before any Phase 6 cutover .deb ships, regardless of what STATE.md / ROADMAP.md say about Phase 5 completion. The .deb build needs `tests/fixtures/fleet/<box-id>/triple.json` for every Phase-6 box.
- The CR-01 redact.py extension (HUMAN-UAT item 10) blocks the X-04 sweep. Schedule it before Task 4 in real-world execution order.

## Self-Check: PASSED

Stub written transparently. No fabricated evidence. No requirements claimed completed. Live tracking pointer (HUMAN-UAT.md) named explicitly.
