---
id: T05
parent: S05
milestone: M001
provides:
  - tools/audit_soak_zao.py — S-01 #2 detector (exit 1 when any ActionPlanned event fired on a Zao-active line)
  - tools/audit_soak_exhausted.py — S-01 #3 detector (exit 1 when any Exhausted transition is unexplained by hardware-failure detail or insufficient healthy-streak)
  - tests/unit/tools/ — new test sub-package (12 tests, ~0.5s)
requires: []
affects: []
key_files: []
key_decisions: []
patterns_established: []
observability_surfaces: []
drill_down_paths: []
duration: ~7min
verification_result: passed
completed_at: 2026-05-11
blocker_discovered: false
---
# T05: Plan 05

**# Phase 5 Plan 05: Soak Audit Tools Summary**

## What Happened

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
