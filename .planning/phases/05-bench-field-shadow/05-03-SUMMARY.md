---
phase: 05-bench-field-shadow
plan: 03
subsystem: cli
tags: [cli, fleet-fixture, pii-redaction, phase-5, capture-verb, ctl-subcommand]

# Dependency graph
requires:
  - phase: 05-bench-field-shadow
    provides: Plan 05-01 dms_get_revision wrapper + parse_get_revision parser (firmware probe path)
  - phase: 05-bench-field-shadow
    provides: Plan 05-02 FleetTriple wire shape + compute_fleet_triple orchestrator + detect_zao_sdk_version helper
  - phase: 02-cycle-and-recovery
    provides: cli/redact.py redact_pii primitive (sha256[:8] determinism); subproc.runner.run single-entrypoint pattern (SP-04); cli/main.py argparse subparser dispatch scaffold
  - phase: 03-linux-event-sources-lifecycle
    provides: SysfsInventory (production inventory used by the CLI run() dispatcher)
provides:
  - redact_pii_from_raw_qmicli(stdout: bytes) -> bytes — raw-qmicli-stdout redaction helper. Four patterns: ICCID, UIM ID, IMSI, IPv4 address. Determinism preserved (same input -> same output bytes; same value across files yields same <redacted:<hash>> token).
  - spark_modem.cli.ctl.capture_fleet_fixture module — operator-facing CLI verb (X-01 / X-02 deliverable). Exports build_fleet_fixture, run, QMICLI_CAPTURE_VERBS.
  - QMICLI_CAPTURE_VERBS — frozen 7-tuple lock pinned by test_qmicli_capture_verbs_list_is_locked_at_7. Adding/removing a verb is a deliberate change.
  - tests/fixtures/fleet/_test/triple.json — example fleet fixture (RESEARCH Q10 §752) committed in this plan so the directory layout is checked into git from day 1.
  - tests/fixtures/qmicli/uim_get_card_status/1.30/with_iccid.txt — synthetic uim_get_card_status stdout used by the redaction tests (ICCID x3 + IMSI x1 — same value under three labels: UIM ID, ICCID, ICCID).
affects:
  - 05-04 (preflight_check_known_fleet_triple consumes triple.json files produced by this verb; the on-disk JSON layout produced here is the contract preflight reads)
  - X-04 (Phase 5 capture sweep — the operator's `spark-modem ctl capture-fleet-fixture --out=...` invocation lands here)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "X-03 chicken-and-egg fix materialised as a `ctl <verb>` subcommand — capture-fleet-fixture runs WITHOUT the daemon (no daemon.main imports; no preflight participation; SysfsInventory scanned directly in run()). Engineer can capture the fleet triple on a daemon-less box."
    - "ADR-0009 keying for the captured fixture tree: per-modem subdir is `qmi/<usb_path>/` (e.g. `2-3.1.1`), NEVER `cdc-wdmN`. cdc-wdm referenced ONLY for the qmicli `--device=/dev/cdc-wdmN` interpolation; pinned by test_modem_subdirs_match_usb_path_shape."
    - "PII redaction at capture time (Phase 5 X-02): every captured qmicli stdout flows through redact_pii_from_raw_qmicli before write_bytes. UIM ID added alongside ICCID (Rule 2 — same identity in two labels of the same stdout would otherwise leak)."
    - "QMICLI_CAPTURE_VERBS as a frozen 7-tuple lock — modification of the verb set is a deliberate change pinned by test_qmicli_capture_verbs_list_is_locked_at_7 (frozenset comparison catches both addition and removal)."
    - "ASYNC240 compliance via sync helper extraction + asyncio.to_thread wrapping — five sync helpers (_zao_log_rascow_tail, _write_modem_verb_output, _build_triple_dict, _write_triple_and_sample, _prepare_out_dirs) so pathlib I/O never runs on the event loop; mirrors the Phase 4 fault_inject.py pattern."

key-files:
  created:
    - src/spark_modem/cli/ctl/capture_fleet_fixture.py (~210 LOC)
    - tests/unit/cli/test_redact_raw_qmicli.py (~70 LOC, 7 tests)
    - tests/unit/cli/ctl/__init__.py (empty, new test sub-package)
    - tests/unit/cli/ctl/test_capture_fleet_fixture.py (~210 LOC, 7 tests)
    - tests/integration/test_fleet_fixture_roundtrip.py (~145 LOC, 3 tests)
    - tests/fixtures/qmicli/uim_get_card_status/1.30/with_iccid.txt (17 lines, ICCID x3 + IMSI x1)
    - tests/fixtures/fleet/_test/triple.json (example layout fixture per RESEARCH Q10 §752)
  modified:
    - src/spark_modem/cli/redact.py (added `import re`, `_RAW_QMICLI_PII_PATTERNS` tuple, `redact_pii_from_raw_qmicli` function; +48 LOC)
    - src/spark_modem/cli/main.py (added `from spark_modem.cli.ctl import capture_fleet_fixture as ctl_capture_fleet` import + `ctl capture-fleet-fixture --out` subparser block + `# noqa: PLR0915` on `_build_parser`; +14 LOC)

key-decisions:
  - "UIM ID added alongside ICCID in the redaction pattern set (Rule 2 deviation from plan-text §216-228 which only specified ICCID/IMSI/IPv4). Real qmicli uim_get_card_status stdout carries the ICCID value under BOTH `UIM ID:` and `ICCID:` labels (verified via the synthetic fixture and existing tests/fixtures/qmicli/get_sim_state/1.30/*.txt fixtures); omitting UIM ID would leak the same identifier under a different label. The pattern is `(UIM ID:\\s*')([^']+)(')` — same shape as the other three."
  - "QMICLI_CAPTURE_VERBS list locked at exactly 7 (CONTEXT.md X-02 §163-170 upper-bound was 8). Dropped: `wds_get_packet_service_status` (datapath state is volatile and depends on network conditions at capture time, not box config — not useful for triple-matching/fixture coverage). Lock pinned by test_qmicli_capture_verbs_list_is_locked_at_7."
  - "build_fleet_fixture is the orchestrator seam (sync-friendly, dependency-injected via descriptors + zao_log_path + box_id). `run()` is the argparse dispatcher and the only place SysfsInventory is constructed — keeps the orchestrator unit-testable without sysfs."
  - "Capture verb does NOT import `daemon.main` (X-03 chicken-and-egg fix — pinned by grep in success_criteria #4). The verb constructs SysfsInventory + QmiWrapper directly; no preflight participation."
  - "Re-running capture on the same out_dir is INTENTIONALLY non-idempotent on `first_seen_iso` (datetime.now() per call) but IS idempotent on the identity triple (em7421_firmware/zao_sdk/libqmi). Verified by test_capture_is_idempotent; the operator can re-run capture without worrying about appendix behavior, but timestamps reflect when each capture happened."
  - "On-disk triple.json schema is the contract for Plan 05-04 (preflight): schema_version=1, em7421_firmware, zao_sdk, libqmi, first_seen_box_id, first_seen_iso, _comment. ISO timestamp uses `.replace('+00:00', 'Z')` for the canonical 'Z'-suffixed form preflight expects."
  - "PII fixture (tests/fixtures/qmicli/uim_get_card_status/1.30/with_iccid.txt) created at this canonical path (NOT under the existing get_sim_state/ tree) so the fixture's purpose is named in its path: it's the canonical input for the PII redaction tests at the X-02 capture seam."

patterns-established:
  - "Operator-facing ctl verb that bypasses the daemon (X-03 fix) — capture-fleet-fixture is the first ctl subcommand that runs inventory + QMI probes without daemon coupling. Future X-04/X-05 verbs (e.g. ctl preflight-self-check) can follow the same shape."
  - "Sync-helper extraction for ASYNC240 compliance — five small sync functions wrap each pathlib I/O surface; the async caller wraps in `asyncio.to_thread`. Cleaner than per-line `# noqa: ASYNC240` and matches the Phase 4 fault_inject.py + Plan 04-07 HIL scenario pattern."
  - "tests/fixtures/fleet/_test/triple.json — first commit under tests/fixtures/fleet/ (the directory layout is now greppable and review-able from day 1); real per-box fixtures land via the X-04 sweep before Phase 6."

requirements-completed:
  - X-01
  - X-02

# Metrics
duration: ~11min
completed: 2026-05-11
---

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
