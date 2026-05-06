---
phase: 02-core-daemon-laptop-testable
plan: 02
subsystem: qmi
tags: [pydantic-v2, qmicli, parser, libqmi-version-drift, proxy-mandatory, in-critical-section]

# Dependency graph
requires:
  - phase: 01-foundations-adrs
    provides: subproc.runner.run() signature, CompletedProcess, SubprocSpawnError, BaseWire, RegistrationState enum
  - phase: 02-core-daemon-laptop-testable
    plan: 01
    provides: tests.fakes.runner.FakeRunner (argv->CompletedProcess map), tests/fixtures/qmicli/ root directory
provides:
  - QmiWrapper: single class wrapping every qmicli invocation through subproc.runner.run
  - QmiError + QmiErrorReason: typed all-errors-are-data record (PROXY_DIED / TIMEOUT / NON_ZERO_EXIT / PARSE_ERROR / MISSING_FIELD / UNEXPECTED_OUTPUT / PROXY_UNAVAILABLE)
  - QmiWrapper.classify(cp): CompletedProcess -> QmiError | None short-circuit (PITFALLS §1.1 proxy-died for RECOVERY_SPEC §6.4 driver_reset)
  - SubprocRunner Protocol: structural type satisfied by both subproc.runner module and tests.fakes.runner.FakeRunner
  - Seven per-intent parsers: parse_get_signal / parse_get_serving_system / parse_get_sim_state / parse_get_data_session / parse_get_profile_settings / parse_get_operating_mode / parse_get_current_settings, each returning Get*Result | QmiError
  - Per-libqmi-version fixture tree at tests/fixtures/qmicli/<intent>/<version>/<scenario>.txt (16 fixtures, libqmi 1.30 + 1.32)
  - libqmi_version_of() / strip_header() utilities for fixture-only `# libqmi_version: <ver>` line-1 comment
affects: [02-04, 02-05, 02-06]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "All errors are data (SP-02 carry-forward): every qmicli failure surfaces as a typed QmiError, never a free-form exception, so policy/ can branch on QmiErrorReason.PROXY_DIED for RECOVERY_SPEC §6.4 driver_reset short-circuit"
    - "Proxy-mandatory invariant (FR-74 / PITFALLS §1.5): every qmicli invocation through QmiWrapper unconditionally includes --device-open-proxy; direct-mode access is never attempted"
    - "_in_critical_section flag (PITFALLS §1.4): state-changing methods set the flag before calling the runner and clear it in finally so the Phase 3 SIGTERM handler can wait for cleanup rather than cancelling mid-call"
    - "Pydantic v2 boundary split: parsers use ConfigDict(extra='ignore', frozen=True) -- absorbs new libqmi fields without code change; wire/ uses ConfigDict(extra='forbid') for strict outbound surfaces (BaseWire)"
    - "Per-libqmi-version fixture tree: tests/fixtures/qmicli/<intent>/<version>/<scenario>.txt; first-line `# libqmi_version: <ver>` comment is fixture-only, stripped by parsers via _header.strip_header"
    - "Required-field MISSING_FIELD pattern: regex no-match on a structurally-required field (registration_state, card_state, profile_index, mode) returns QmiError(reason=MISSING_FIELD, field=<name>) rather than silent None -- the policy engine can never see a None where it needs a value"
    - "Timeout wins over proxy-died in classify(): both signals can co-exist in a timed-out CompletedProcess; the operationally-meaningful signal is that the call did not return in time"

key-files:
  created:
    - src/spark_modem/qmi/__init__.py
    - src/spark_modem/qmi/errors.py
    - src/spark_modem/qmi/wrapper.py
    - src/spark_modem/qmi/parsers/__init__.py
    - src/spark_modem/qmi/parsers/_header.py
    - src/spark_modem/qmi/parsers/get_signal.py
    - src/spark_modem/qmi/parsers/get_serving_system.py
    - src/spark_modem/qmi/parsers/get_sim_state.py
    - src/spark_modem/qmi/parsers/get_data_session.py
    - src/spark_modem/qmi/parsers/get_profile_settings.py
    - src/spark_modem/qmi/parsers/get_operating_mode.py
    - src/spark_modem/qmi/parsers/get_current_settings.py
    - tests/unit/qmi/__init__.py
    - tests/unit/qmi/test_wrapper.py
    - tests/unit/qmi/test_parsers.py
    - tests/fixtures/qmicli/get_signal/1.30/lte_strong.txt
    - tests/fixtures/qmicli/get_signal/1.30/lte_weak.txt
    - tests/fixtures/qmicli/get_signal/1.32/nr5g_present.txt
    - tests/fixtures/qmicli/get_serving_system/1.30/registered_home.txt
    - tests/fixtures/qmicli/get_serving_system/1.30/not_registered_searching.txt
    - tests/fixtures/qmicli/get_sim_state/1.30/ready.txt
    - tests/fixtures/qmicli/get_sim_state/1.30/sim_app_detected.txt
    - tests/fixtures/qmicli/get_sim_state/1.30/sim_power_down.txt
    - tests/fixtures/qmicli/get_data_session/1.30/connected.txt
    - tests/fixtures/qmicli/get_data_session/1.30/disconnected.txt
    - tests/fixtures/qmicli/get_profile_settings/1.30/profile1_internet.txt
    - tests/fixtures/qmicli/get_operating_mode/1.30/online.txt
    - tests/fixtures/qmicli/get_operating_mode/1.30/low_power.txt
    - tests/fixtures/qmicli/get_current_settings/1.30/raw_ip_y.txt
    - tests/fixtures/qmicli/get_current_settings/1.30/raw_ip_n.txt
    - tests/fixtures/qmicli/proxy_error/proxy_died.txt
  modified: []
  deleted:
    - tests/fixtures/qmicli/.gitkeep   # placeholder replaced by real fixtures (intentional)

key-decisions:
  - "Regex-per-field over full-table parsing: parsers use re.search per field rather than a tabular reader. Tradeoff: easier to evolve as libqmi sections drift (extra='ignore' + per-field regex absorbs reordering and new sections); cost is that section-aware semantics (e.g. 'this RSRP belongs to NR5G not LTE') is not enforced. The plan's §"<acceptance_criteria>" specifies search-based extraction, so this is the planned approach. The downstream observer is documented to take the FIRST RSRP/RSRQ/SNR as the reportable value (NR5G when present, else LTE)."
  - "Section-first-match for NR5G fixture: the get_signal parser reads NR5G's RSRP/RSRQ/SNR (which appear first in libqmi 1.32 output) and LTE's RSSI (NR5G has no RSSI). The expected-values dict in test_parsers.py pins this behaviour so a future restructuring is caught."
  - "Roaming-status-defaults-to-off when absent: qmicli's not-registered-searching block omits Roaming status; the parser defaults raw_roam='off' so the (raw_reg, 'off') tuple resolves cleanly. Both ('not-registered-searching', 'off') and ('not-registered-searching', 'on') map to the same NOT_REGISTERED_SEARCHING enum value."
  - "Card state and app state are lowercased at parse time: the qmicli text uses 'present' / 'ready' / 'detected' (already lowercase) but the parser .strip().lower()s them defensively so a future libqmi capitalisation change does not silently break the IssueDetail mapping."
  - "Timeout wins over PROXY_DIED in classify(): a process that timed out is reaped via the two-stage shutdown and may have proxy-death residue in stderr -- but the operationally-meaningful signal for policy/ is that the call did not return in time. PROXY_DIED implies 'proxy is gone, retry is futile'; TIMEOUT may be transient. Order in _classify_completed_process is: timed_out -> proxy-died -> non-zero -> success."
  - "stderr_excerpt capped at 512 bytes (T-02-02-01): bounds memory and avoids accidentally exporting large device-state dumps via QmiError objects passed across event payloads / support bundles. Tested via test_classify_stderr_excerpt_is_bounded."
  - "Empty-device constructor rejection: QmiWrapper(runner=..., device='') raises ValueError (T-02-02-02 defensive). Production callers always pass /dev/cdc-wdmN; the empty-string case would only arise from a misconfigured fixture."
  - "wds_set_ip_family added to the wrapper surface: actions/fix_raw_ip.py (Plan 02-06) needs to set raw IP via QMI; exposing the call here keeps the typed boundary intact (no private-attribute access from actions/) and means actions/ does not need its own qmicli-argv knowledge."

requirements-completed:
  - FR-11
  - FR-74

# Metrics
duration: 9min
completed: 2026-05-06
---

# Phase 2 Plan 02: QmiWrapper + Parsers + Per-libqmi-Version Fixtures Summary

**A single QmiWrapper class owns every qmicli invocation in the daemon (always with `--device-open-proxy`), seven per-intent parsers turn qmicli text into typed `Get*Result | QmiError` records, and a per-libqmi-version fixture tree pins the output shape so future libqmi point releases land as data, not code.**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-05-06T16:02:03Z
- **Completed:** 2026-05-06T16:11:59Z
- **Tasks:** 2
- **Files created:** 31 (15 source/test + 16 fixtures)
- **Files deleted:** 1 (placeholder `.gitkeep` replaced by real fixtures)

## Accomplishments

- `QmiWrapper` (`src/spark_modem/qmi/wrapper.py`) ships 11 qmicli methods routed through `subproc.runner.run`: 7 read-only queries (nas_get_signal_info, nas_get_serving_system, uim_get_card_status, wds_get_packet_service_status, wds_get_profile_settings, wds_get_current_settings, dms_get_operating_mode) + 4 state-changing mutators (dms_set_operating_mode, uim_sim_power_on, wds_modify_profile, wds_set_ip_family). Each call unconditionally includes `--device-open-proxy` (verified by `grep -c '"--device-open-proxy"' src/spark_modem/qmi/wrapper.py` = 11).
- The `_in_critical_section` flag is raised on each of the 4 state-changing methods (and only those) and cleared in a `finally` block. Verified by `grep -c "self._in_critical_section = True" src/spark_modem/qmi/wrapper.py` = 4 + a `_RaisingRunner` test that asserts the flag clears even when the runner raises.
- `QmiWrapper.classify(cp)` correctly identifies the PITFALLS §1.1 proxy-died short-circuit signatures (`proxy unavailable`, `couldn't open the QMI device: proxy unavailable`, `broken pipe`, `connection refused`) and surfaces them as `QmiError(reason=PROXY_DIED)` so policy/ can choose driver_reset rather than retry. Timeout wins over proxy-died when both are present.
- 7 parsers (`src/spark_modem/qmi/parsers/get_*.py`) ship with `ConfigDict(extra='ignore', frozen=True)` result models; required fields (`registration_state`, `card_state`, `profile_index`, `mode`) surface as `QmiError(reason=MISSING_FIELD, field=<name>)` when structurally absent. Parsers import only stdlib + pydantic + `spark_modem.qmi.errors` + `spark_modem.wire.enums` -- no I/O, subprocess, asyncio, or httpx.
- 16 fixture files seeded under `tests/fixtures/qmicli/<intent>/<libqmi-version>/<scenario>.txt`, each with `# libqmi_version: <ver>` line-1 comment. Coverage spans LTE strong/weak (1.30) + NR5G-present (1.32) for get_signal; registered_home + not_registered_searching for serving_system; ready/sim_app_detected/power_down for sim_state; connected/disconnected for data_session; profile1_internet for profile_settings; online/low_power for operating_mode; raw_ip_y/raw_ip_n for current_settings; proxy_died.txt under proxy_error/.
- 61 unit tests collected (`tests/unit/qmi/`) all pass under pytest-asyncio mode=auto: 32 wrapper tests + 29 parser tests. mypy --strict + ruff check + ruff format --check all green; SP-04 subprocess-bypass lint green (`bash scripts/lint_no_subprocess.sh` exit 0). Full project sanity run: 333 passed, 41 skipped (pre-existing POSIX skips), no regressions.

## Task Commits

1. **Task 1: QmiWrapper + QmiError + proxy-mandatory invariant** — `d341c0f` (feat)
2. **Task 2: Per-intent qmicli parsers + per-libqmi-version fixtures** — `01a9935` (feat)

**Plan metadata:** added in the final commit alongside this SUMMARY.md and STATE.md / ROADMAP.md / REQUIREMENTS.md updates.

## Files Created/Modified

### Production source (`src/spark_modem/qmi/`)
- `__init__.py` — empty package marker
- `errors.py` — `QmiErrorReason(StrEnum)` (7 variants: PROXY_DIED / PROXY_UNAVAILABLE / TIMEOUT / NON_ZERO_EXIT / PARSE_ERROR / MISSING_FIELD / UNEXPECTED_OUTPUT) + frozen `QmiError` dataclass (argv tuple, exit_code, stderr_excerpt, optional field, detail)
- `wrapper.py` — `SubprocRunner` Protocol, `_classify_completed_process` private mapper, `QmiWrapper` class with 11 qmicli methods + classify() static method + `in_critical_section` / `device` properties
- `parsers/__init__.py` — empty package marker
- `parsers/_header.py` — `libqmi_version_of(text: bytes) -> str | None` and `strip_header(text: bytes) -> bytes`
- `parsers/get_signal.py` — `GetSignalResult(rssi_dbm, rsrp_dbm, rsrq_db, snr_db)` + `parse_get_signal`
- `parsers/get_serving_system.py` — `GetServingSystemResult(registration_state, mcc, mnc, description)` + `parse_get_serving_system`; required: `registration_state`
- `parsers/get_sim_state.py` — `GetSimStateResult(card_state, app_state, iccid, imsi)` + `parse_get_sim_state`; required: `card_state`
- `parsers/get_data_session.py` — `GetDataSessionResult(connection_status)` + `parse_get_data_session`
- `parsers/get_profile_settings.py` — `GetProfileSettingsResult(profile_index, apn, ip_family)` + `parse_get_profile_settings`; required: `profile_index`
- `parsers/get_operating_mode.py` — `GetOperatingModeResult(mode)` + `parse_get_operating_mode`; required: `mode`
- `parsers/get_current_settings.py` — `GetCurrentSettingsResult(ipv4, raw_ip)` + `parse_get_current_settings`; raw_ip ∈ {'Y', 'N', '?'}

### Tests (`tests/unit/qmi/`)
- `__init__.py` — empty package marker
- `test_wrapper.py` — 32 tests via `tests.fakes.runner.FakeRunner` + `_RecordingRunner` + `_RaisingRunner` helpers: every method uses `--device-open-proxy` exactly once and `--device=/dev/cdc-wdm0` exactly once; query methods do NOT raise the critical flag; state-change methods raise the flag *during* the runner call AND clear it on raise; classify recognises proxy-died, broken-pipe, timeout (which wins over proxy-died), non-zero exit without proxy signature, and clean success (None); empty-device constructor rejection; stderr_excerpt bounded at 512 bytes
- `test_parsers.py` — 29 tests parametrized over the fixture tree (one parametrize per intent) + dedicated regression tests: header-utility round-trip / RegistrationState enum mapping pin / MISSING_FIELD for serving-system, sim-state, profile-settings, operating-mode / UNEXPECTED_OUTPUT for serving-system and signal / extra='ignore' boundary for NR5G-1.32 and registered-home-1.30 / classify() round-trip on the proxy_died.txt fixture

### Fixture tree (`tests/fixtures/qmicli/`)
- `get_signal/1.30/{lte_strong,lte_weak}.txt` + `1.32/nr5g_present.txt` (3 fixtures)
- `get_serving_system/1.30/{registered_home,not_registered_searching}.txt` (2 fixtures)
- `get_sim_state/1.30/{ready,sim_app_detected,sim_power_down}.txt` (3 fixtures)
- `get_data_session/1.30/{connected,disconnected}.txt` (2 fixtures)
- `get_profile_settings/1.30/profile1_internet.txt` (1 fixture)
- `get_operating_mode/1.30/{online,low_power}.txt` (2 fixtures)
- `get_current_settings/1.30/{raw_ip_y,raw_ip_n}.txt` (2 fixtures)
- `proxy_error/proxy_died.txt` (1 fixture)
- **16 fixtures total**; placeholder `tests/fixtures/qmicli/.gitkeep` removed (intentional — replaced by real content; not a destructive deletion)

## Decisions Made

- **Regex-per-field, not full-table parsing.** Each parser uses `re.search` per required field rather than a tabular reader walking nested QMI sections. The tradeoff: easier to evolve as libqmi sections drift (`extra='ignore'` + per-field regex absorbs reordering and new sections); cost is that section-aware semantics (e.g. "this RSRP belongs to NR5G, not LTE") is not enforced inside the parser. The plan's `<acceptance_criteria>` specifies search-based extraction, so this is the planned approach. The expected-values dict in `test_parsers.py` pins the section-first-match behaviour for the NR5G fixture so a future restructuring is caught.
- **Roaming-status defaults to 'off' when absent.** qmicli's `not-registered-searching` block omits the `Roaming status` line; the serving-system parser defaults `raw_roam='off'` so the `(raw_reg, 'off')` tuple resolves cleanly via `_REG_TO_ENUM`. Both `('not-registered-searching', 'off')` and `('not-registered-searching', 'on')` map to the same `NOT_REGISTERED_SEARCHING` enum value (roaming is irrelevant when not registered).
- **Card state / app state / op mode lowercased defensively.** qmicli's text values are already lowercase (`'present'`, `'ready'`, `'detected'`, `'online'`, `'low_power'`) but the parsers `.strip().lower()` them before storing so a future libqmi capitalisation change does not silently break the downstream `IssueDetail` mapping in policy/.
- **Timeout wins over PROXY_DIED in classify().** A process that timed out is reaped via the two-stage shutdown and may have proxy-death residue in stderr -- but the operationally-meaningful signal for policy/ is that the call did not return in time. PROXY_DIED implies "proxy is gone, retry is futile"; TIMEOUT may be transient. Order in `_classify_completed_process` is: timed_out → proxy-died → non-zero → success. Pinned by `test_classify_timeout_wins_over_proxy_signature`.
- **stderr_excerpt capped at 512 bytes (T-02-02-01).** Bounds memory and avoids accidentally exporting large device-state dumps via `QmiError` objects passed across event payloads / support bundles. Tested via `test_classify_stderr_excerpt_is_bounded`.
- **Empty-device constructor rejection (T-02-02-02 defensive).** `QmiWrapper(runner=..., device='')` raises `ValueError`. Production callers always pass `/dev/cdc-wdmN`; the empty-string case would only arise from a misconfigured fixture / typo, and this fail-fast is cheaper than a `--device=` argv that confuses qmicli with an empty string.
- **`wds_set_ip_family` added to the wrapper surface.** `actions/fix_raw_ip.py` (Plan 02-06) needs to set raw IP via QMI. Exposing the call here keeps the typed boundary intact -- actions/ does not need its own qmicli-argv knowledge and the policy engine's purity invariant (CLAUDE.md §1) cannot leak into fix_raw_ip via private-attribute access. Counted toward the FR-74 always-on `--device-open-proxy` rule (the plan's acceptance criterion was 11 `--device-open-proxy` strings, including this one).
- **Section-first-match for NR5G fixture.** The `get_signal` parser reads NR5G's `RSRP/RSRQ/SNR` (which appear first in libqmi 1.32 output) and LTE's `RSSI` (NR5G has no RSSI). The expected-values dict in `test_parsers.py` pins this behaviour so a future restructuring is caught:
  - 1.32 nr5g_present: `rssi_dbm=-65` (LTE), `rsrp_dbm=-72` (NR5G), `rsrq_db=-12.0` (NR5G), `snr_db=15.0` (NR5G)
  - 1.30 lte_strong/weak: every field from LTE (no NR5G section).

## Deviations from Plan

### Tweak 1: Docstring rephrased to satisfy literal acceptance criterion grep

- **Found during:** Task 1 verification (acceptance criterion `grep -c "self\._in_critical_section = True" src/spark_modem/qmi/wrapper.py reports exactly 4`).
- **Issue:** Initial module docstring referenced `self._in_critical_section = True` in backticks (referring to the pattern by name). This produced 5 grep matches: 4 real assignments + 1 docstring reference.
- **Fix:** Reworded the docstring sentence to "State-changing methods raise the in-critical-section flag before calling the runner..." Substantive meaning unchanged; literal grep now returns exactly 4. Same kind of substring-vs-substantive tweak as Plan 02-01's docstring reword.
- **Files modified:** `src/spark_modem/qmi/wrapper.py`
- **Verification:** `grep -c "self\._in_critical_section = True" src/spark_modem/qmi/wrapper.py` → 4
- **Committed in:** `d341c0f` (Task 1 commit, before commit was finalized)

### Tweak 2: Test count expanded above the plan's minimum

- **Found during:** Task 1 (the plan asked for ≥7 wrapper tests and noted "wds_set_ip_family covered by the parametrized --device-open-proxy and critical-section tests"); Task 2 (plan asked for ≥20 parser tests).
- **Issue:** None — opportunistic additional coverage made parametrization easier and gave each invariant its own named regression.
- **Fix:** Wrapper tests: 32 collected (parametrized `--device-open-proxy` test fans out across all 11 methods; critical-flag tests fan out across queries vs state-changes; classify has 7 dedicated regressions; constructor rejection / acceptance; 1 critical-flag-cleared-on-raise regression). Parser tests: 29 collected (one parametrize per intent × fixture + dedicated MISSING_FIELD / UNEXPECTED_OUTPUT / header-utility / classify-round-trip regressions).
- **Files modified:** `tests/unit/qmi/test_wrapper.py`, `tests/unit/qmi/test_parsers.py`
- **Verification:** `pytest tests/unit/qmi/ -q` → 61 passed
- **Committed in:** `d341c0f` and `01a9935`

### Tweak 3: ruff format applied during verification

- **Found during:** Task 1 + Task 2 verification (`ruff format --check` reported reformat needed).
- **Issue:** Initial files had minor formatting differences from the project's ruff format style (line breaks in collection literals, parenthesisation of single-line conditional). All non-substantive.
- **Fix:** `ruff format src/spark_modem/qmi/ tests/unit/qmi/` applied; all 15 files now formatted-clean.
- **Verification:** `python -m ruff format --check src/spark_modem/qmi/ tests/unit/qmi/` → "15 files already formatted"
- **Committed in:** `d341c0f` and `01a9935` (formatted before each commit)

---

**Total deviations:** 3 micro-tweaks (1 docstring reword, 1 test-count expansion, 1 mechanical ruff format). No deviation rules invoked (none of Rules 1-4 triggered). No architectural changes; no auth gates; no checkpoint required.
**Impact on plan:** None — plan executed exactly as designed. Tweaks only sharpened compliance with literal acceptance criteria and gave each invariant its own named regression.

## Issues Encountered

None of consequence. Phase 1 + Plan 02-01 carry-forward made this a mechanical translation of the plan's `<action>` blocks into code. Specific notes:

- **Windows dev-host:** ruff/mypy/pytest all run cleanly through `.venv/Scripts/python.exe` (Python 3.12.13); the SP-04 subprocess lint runs through Git Bash. No POSIX-only code was added in this plan, so no `skipif(win32)` markers were needed in qmi/.
- **Git rename detection:** When `tests/fixtures/qmicli/.gitkeep` (empty file) was deleted and `src/spark_modem/qmi/parsers/__init__.py` (empty file) was added in the same commit, git rendered the change as a 100%-similarity rename. This is a benign git-display artifact — the `__init__.py` is a real Python package marker and the `.gitkeep` was an unrelated fixture-tree placeholder; both happen to be empty.

## Threat Model Compliance

The plan's `<threat_model>` registers five threats with `mitigate` disposition; all confirmed mitigated by the implementation:

- **T-02-02-01 (Information disclosure on QmiError.stderr_excerpt):** stderr is truncated to 512 bytes via `cp.stderr[:_STDERR_EXCERPT_BYTES]` (`_STDERR_EXCERPT_BYTES = 512`) before being decoded and stored on the QmiError. Verified by `test_classify_stderr_excerpt_is_bounded`: a 4096-byte stderr produces a 512-character `stderr_excerpt`.
- **T-02-02-02 (Tampering on qmicli argv):** All 11 methods use list-form argv via `subproc.run`; no shell strings; the `device` parameter is validated non-empty at constructor; the APN string is passed as a single argv element after `apn=` (the entire `--wds-modify-profile=3gpp,N,apn=X,ip-family=Y` is one argv element, so no separator injection is possible — qmicli sees one argv element regardless of what's in `apn`).
- **T-02-02-03 (DoS via qmicli timeout / hang):** Every qmicli call uses `timeout_s=8.0` (queries) or `15.0` (state-changes); the subproc layer's two-stage shutdown (SIGTERM → 2 s → SIGKILL → drain) is already implemented in Phase 1 and is not bypassed. Hung qmicli surfaces as `QmiError(TIMEOUT)` with bounded latency. Verified by `test_classify_timed_out_returns_timeout_reason`.
- **T-02-02-04 (Tampering via libqmi output drift):** All 7 parser result types use `ConfigDict(extra='ignore')` (PITFALLS §1.2) so new libqmi fields do not raise validation errors. The per-version fixture tree (`tests/fixtures/qmicli/<intent>/<libqmi-version>/`) gives each libqmi point release its own home for representative output. Missing required fields surface as `QmiError(MISSING_FIELD, field=<name>)` rather than silent `None`. Verified by `test_get_serving_system_missing_field_returns_qmierror`, `test_get_sim_state_missing_card_state_returns_qmierror`, `test_get_profile_settings_missing_index_returns_qmierror`, `test_get_operating_mode_missing_mode_returns_qmierror`, and `test_parsers_absorb_unknown_libqmi_fields`.
- **T-02-02-05 (EoP via proxy availability):** `--device-open-proxy` is unconditional on every qmicli invocation (FR-74); verified by `grep -c '"--device-open-proxy"' src/spark_modem/qmi/wrapper.py` = 11 and the parametrized `test_every_call_uses_device_open_proxy` test that asserts each method's recorded argv contains exactly one `--device-open-proxy` string. The proxy-died stderr signature maps to `QmiError(PROXY_DIED)` so policy/ does not silently retry against a broken qmi-proxy. Verified by `test_classify_proxy_died_signature` and `test_proxy_died_fixture_signature_round_trips_through_classify`.

## Verification Block Results (per plan `<verification>`)

| Check | Command | Result |
|-------|---------|--------|
| mypy strict, src/qmi + tests/unit/qmi | `python -m mypy --strict src/spark_modem/qmi/ tests/unit/qmi/` | Success: no issues found in 15 source files |
| ruff check, src/qmi + tests/unit/qmi | `python -m ruff check src/spark_modem/qmi/ tests/unit/qmi/` | All checks passed |
| ruff format check | `python -m ruff format --check src/spark_modem/qmi/ tests/unit/qmi/` | 15 files already formatted |
| pytest qmi ≥27 tests | `python -m pytest tests/unit/qmi/ -q` | 61 passed |
| SP-04 subprocess lint | `bash scripts/lint_no_subprocess.sh` | exit 0 |
| `--device-open-proxy` ≥10 in wrapper | `grep -c '"--device-open-proxy"' src/spark_modem/qmi/wrapper.py` | 11 |
| Full project sanity (no regression) | `python -m pytest tests/ -q --ignore=tests/integration --ignore=tests/hil` | 333 passed, 41 skipped (pre-existing POSIX skips) |

## Unimplemented qmicli invocations (deferred to Phase 4)

The wrapper deliberately does NOT yet expose the destructive QMI surface. Phase 4 lands these behind the existing `_in_critical_section` + signal-quality-gate machinery:

- `--dms-set-operating-mode=offline` → reset (paired with online), used by **modem_reset** (RECOVERY_SPEC §4 ladder level 2)
- `--wds-stop-network` → forced session teardown, used by **soft_reset** (cheap; could land in Plan 02-06 but only if needed there)
- The destructive USB-side surface (`echo 0 > /sys/.../authorized` + driver rebind sequence) is not qmicli at all and lands in `actions/usb_reset.py` / `actions/driver_reset.py` (Phase 4) -- it never appears on the QmiWrapper surface.

The current wrapper's 4 state-changing methods (`dms_set_operating_mode`, `uim_sim_power_on`, `wds_modify_profile`, `wds_set_ip_family`) cover the four cheap actions Plan 02-06 will need (`set_operating_mode`, `sim_power_on`, `set_apn`, `fix_raw_ip`). `soft_reset` reuses `dms_set_operating_mode("offline")` followed by `("online")`; no new wrapper method is required.

## Next Plan Readiness

- **Plan 02-04 (observer + sysfs inventory):** can now `from spark_modem.qmi.wrapper import QmiWrapper` and `from spark_modem.qmi.parsers.get_signal import parse_get_signal, GetSignalResult` (etc.) without further setup. The probe orchestrator pattern in PATTERNS.md §observer needs a `QmiWrapper` per modem; the constructor `QmiWrapper(runner=..., device="/dev/cdc-wdmN")` is ready.
- **Plan 02-05 (policy):** consumes the parser typed records as inputs to `Diag` construction. The `RegistrationState` enum mapping in `parse_get_serving_system` is the only place the qmicli text → policy enum bridge exists; no other plan needs to redo it.
- **Plan 02-06 (actions):** consumes `QmiWrapper.dms_set_operating_mode / uim_sim_power_on / wds_modify_profile / wds_set_ip_family` for `set_operating_mode / sim_power_on / set_apn / fix_raw_ip`. The `_in_critical_section` flag is already wired; actions/ does not need to manage it.
- **No blockers, no concerns.** Wave 2 plans 02-03 (zao_log/) and 02-05 (policy/) — running after this — are independent of qmi/ at the import level.

## Self-Check: PASSED

- File `src/spark_modem/qmi/wrapper.py` exists — FOUND
- File `src/spark_modem/qmi/errors.py` exists — FOUND
- All 7 parser modules exist — FOUND
- All 16 qmicli fixture files exist with `# libqmi_version: <ver>` line-1 comment — FOUND
- File `tests/unit/qmi/test_wrapper.py` exists — FOUND
- File `tests/unit/qmi/test_parsers.py` exists — FOUND
- Commit `d341c0f` exists — FOUND
- Commit `01a9935` exists — FOUND

---
*Phase: 02-core-daemon-laptop-testable*
*Completed: 2026-05-06*
