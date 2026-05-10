---
plan: 04-01
title: modem_reset action + dispatcher registration + CLI unblock
phase: 04
wave: 1
depends_on: []
files_modified:
  - src/spark_modem/actions/modem_reset.py
  - src/spark_modem/actions/dispatcher.py
  - src/spark_modem/cli/reset.py
  - tests/unit/actions/test_modem_reset.py
  - tests/unit/actions/test_dispatcher.py
  - tests/unit/cli/test_reset.py
autonomous: true
requirements: [FR-23, FR-27]
must_haves:
  truths:
    - "ActionKind.MODEM_RESET is registered in actions.dispatcher._REGISTRY"
    - "actions/modem_reset.py exposes async execute() and verify() following the soft_reset shape"
    - "modem_reset's QMI verb is dms_set_operating_mode('reset') (same as soft_reset; the difference is policy-side per A-01)"
    - "verify() returns VerifyResult.deferred(detail='next_cycle_observation') (A-04)"
    - "spark-modem reset --action=modem_reset --modem=cdc-wdm0 stops failing the destructive-action guard"
    - "test_destructive_actions_not_registered (Phase 2 contract test) is replaced by test_destructive_actions_registered"
  artifacts:
    - path: "src/spark_modem/actions/modem_reset.py"
      provides: "MODEM_RESET execute/verify"
      contains: "ActionKind.MODEM_RESET"
    - path: "tests/unit/actions/test_modem_reset.py"
      provides: "modem_reset unit-test stub (4 paths: success, qmi_err, classify_proxy_died, classify_timeout)"
  key_links:
    - from: "src/spark_modem/actions/dispatcher.py:_REGISTRY"
      to: "src/spark_modem/actions/modem_reset.py:execute"
      via: "registry append"
      pattern: "ActionKind\\.MODEM_RESET: \\(modem_reset\\.execute"
    - from: "src/spark_modem/cli/reset.py"
      to: "actions.dispatcher.is_registered"
      via: "registered_kinds() now includes MODEM_RESET so the destructive-guard branch passes through"
      pattern: "is_registered\\(kind\\)"
---

<objective>
Land the simplest of the three Phase 4 destructive actions: `modem_reset`. Per
CONTEXT D-01: "modem_reset is a policy distinction, not a protocol distinction"
— it issues the SAME `qmicli --dms-set-operating-mode=reset` call as
`soft_reset` (Phase 2 ships this verb). The difference is gating (signal-gated
in Plan 04-04), ladder-rung (rung 2 — wired in Plan 04-04), and expected
outage envelope (~30-60 s deferred verify).

Purpose: Unblock SC#1 (FR-27 idempotent CLI-runnable destructive action) and
SC#3 ladder progression (`not_registered_searching → soft_reset → modem_reset`)
ahead of Plan 04-04's ladder integration. The decision-table row
`(QMI, OPERATING_MODE_OFFLINE) → MODEM_RESET` already routes to
ActionKind.MODEM_RESET (Phase 2; verified `decision_table.py:60`); registering
the action makes the dispatcher actually execute it instead of returning
`action_kind_not_registered`.

Output:
- New `src/spark_modem/actions/modem_reset.py` (mirror of `soft_reset.py`)
- `dispatcher._REGISTRY` gains 1 row (MODEM_RESET)
- `cli/reset.py` error message updated (no longer says "Phase 4 destructive")
- 3 test files updated/added: `tests/unit/actions/test_modem_reset.py` (new),
  `tests/unit/actions/test_dispatcher.py` (existing test inverted),
  `tests/unit/cli/test_reset.py` (existing test extended)
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/04-destructive-actions-hil/04-CONTEXT.md
@.planning/phases/04-destructive-actions-hil/04-PATTERNS.md
@docs/RECOVERY_SPEC.md
@CLAUDE.md

<interfaces>
<!-- Verbatim from PATTERNS.md / source — executor uses these directly. -->

From src/spark_modem/actions/soft_reset.py (the analog — copy the shape):
```python
from __future__ import annotations

from spark_modem.actions.context import ActionContext
from spark_modem.actions.result import ActionResult, VerifyResult
from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind


async def execute(who: WhoModem, ctx: ActionContext) -> ActionResult:
    start = ctx.clock.monotonic()
    cp = await ctx.qmi.dms_set_operating_mode("reset")
    err = QmiWrapper.classify(cp)
    if err is not None:
        return ActionResult(
            kind=ActionKind.SOFT_RESET,
            who=who,
            succeeded=False,
            duration_seconds=ctx.clock.monotonic() - start,
            failure_reason=f"soft_reset:{err.reason.value}",
            dry_run=False,
        )
    return ActionResult(
        kind=ActionKind.SOFT_RESET,
        who=who,
        succeeded=True,
        duration_seconds=ctx.clock.monotonic() - start,
        failure_reason=None,
        dry_run=False,
    )


async def verify(who: WhoModem, ctx: ActionContext) -> VerifyResult:
    """Deferred -- next-cycle observation surfaces the actual outcome."""
    del who, ctx
    return VerifyResult.deferred(detail="next_cycle_observation")
```

From src/spark_modem/actions/dispatcher.py:39-46 (the registry to extend):
```python
_REGISTRY: dict[ActionKind, tuple[ExecuteFn, VerifyFn]] = {
    ActionKind.SET_APN: (set_apn.execute, set_apn.verify),
    ActionKind.FIX_RAW_IP: (fix_raw_ip.execute, fix_raw_ip.verify),
    ActionKind.SIM_POWER_ON: (sim_power_on.execute, sim_power_on.verify),
    ActionKind.SOFT_RESET: (soft_reset.execute, soft_reset.verify),
    ActionKind.SET_OPERATING_MODE: (set_operating_mode.execute, set_operating_mode.verify),
    ActionKind.FIX_AUTOSUSPEND: (fix_autosuspend.execute, fix_autosuspend.verify),
}
```

From src/spark_modem/wire/enums.py:92-114 (ActionKind — MODEM_RESET already exists):
```python
class ActionKind(StrEnum):
    SET_APN = "set_apn"
    FIX_RAW_IP = "fix_raw_ip"
    SIM_POWER_ON = "sim_power_on"
    SOFT_RESET = "soft_reset"
    SET_OPERATING_MODE = "set_operating_mode"
    FIX_AUTOSUSPEND = "fix_autosuspend"
    MODEM_RESET = "modem_reset"   # already declared in Phase 1
    USB_RESET = "usb_reset"
    DRIVER_RESET = "driver_reset"
```

From tests/unit/actions/_helpers.py:70-99 (`make_ctx` — reused in tests):
```python
def make_ctx(
    runner: FakeRunner,
    *,
    sysfs_root: Path | None = None,
    carrier_table: CarrierTable | None = None,
) -> tuple[ActionContext, RecordingEventLogger, FakeClock]:
    qmi = QmiWrapper(runner=runner, device=_DEVICE)
    clock = FakeClock()
    logger = RecordingEventLogger()
    ctx = ActionContext(
        qmi=qmi,
        clock=clock,
        config=make_settings(),
        carrier_table=carrier_table if carrier_table is not None else make_carrier_table(),
        event_logger=logger,
        sysfs_root=sysfs_root if sysfs_root is not None else Path("/sys"),
    )
    return ctx, logger, clock


def ok(argv: list[str], stdout: bytes = b"") -> CompletedProcess:
    return CompletedProcess.make(
        argv=argv,
        exit_code=0,
        stdout=stdout,
        stderr=b"",
        duration_monotonic=0.01,
        timed_out=False,
    )
```

From tests/unit/actions/test_soft_reset.py:18-44 (test scaffold to mirror):
```python
def _who() -> WhoModem:
    return WhoModem(usb_path="2-3.1.1", cdc_wdm="cdc-wdm0")


def _argv() -> list[str]:
    return [*base_argv(), "--dms-set-operating-mode=reset"]


@pytest.mark.asyncio
async def test_soft_reset_invokes_dms_set_operating_mode_reset() -> None:
    runner = FakeRunner()
    runner.register(_argv(), ok(_argv()))
    ctx, _logger, _clock = make_ctx(runner)
    await soft_reset.execute(_who(), ctx)
    assert any("--dms-set-operating-mode=reset" in arg for call in runner.calls for arg in call)
```

From src/spark_modem/cli/reset.py:23-51 (current error message to update):
```python
if not is_registered(kind):
    valid = sorted(k.value for k in registered_kinds())
    print(
        f"reset: action {kind.value} is destructive (Phase 4); "
        f"Phase 2 supports: {valid}",
        file=sys.stderr,
    )
    return 2
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Create actions/modem_reset.py + register in dispatcher</name>
  <files>
    src/spark_modem/actions/modem_reset.py,
    src/spark_modem/actions/dispatcher.py,
    tests/unit/actions/test_modem_reset.py
  </files>
  <read_first>
    - src/spark_modem/actions/soft_reset.py (the EXACT analog — same QMI verb, copy the shape)
    - src/spark_modem/actions/dispatcher.py (the _REGISTRY block at lines 39-46 + import block at lines 20-27)
    - tests/unit/actions/test_soft_reset.py (the test scaffold to mirror)
    - tests/unit/actions/_helpers.py (make_ctx + ok + base_argv helpers)
    - .planning/phases/04-destructive-actions-hil/04-PATTERNS.md § "src/spark_modem/actions/modem_reset.py" (full diff spec)
    - docs/RECOVERY_SPEC.md §4.1 (the ladder: soft_reset is rung 1, modem_reset is rung 2 — same QMI verb, different policy)
  </read_first>
  <behavior>
    - test_modem_reset_invokes_dms_set_operating_mode_reset: FakeRunner-registered argv `[*base_argv(), "--dms-set-operating-mode=reset"]` returns ok; assert the runner saw exactly that argv; assert returned ActionResult.kind == ActionKind.MODEM_RESET, succeeded == True, dry_run == False, failure_reason is None.
    - test_modem_reset_classifies_proxy_died: FakeRunner returns CompletedProcess with stderr containing the QmiWrapper PROXY_DIED-classifier signature (b"could not connect to qmi-proxy" or b"proxy died" — match the existing soft_reset proxy-died test pattern verbatim from `tests/unit/actions/test_soft_reset.py`); assert succeeded == False, failure_reason starts with "modem_reset:" (NOT "soft_reset:").
    - test_modem_reset_classifies_timeout: FakeRunner returns timed_out=True CompletedProcess; assert succeeded == False, failure_reason == "modem_reset:timeout".
    - test_modem_reset_verify_is_deferred: call verify(who, ctx); assert returned VerifyResult.kind == "deferred" with detail == "next_cycle_observation".
    - test_modem_reset_registered_in_dispatcher: assert ActionKind.MODEM_RESET in actions.dispatcher.registered_kinds().
  </behavior>
  <action>
Create `src/spark_modem/actions/modem_reset.py` as a verbatim mirror of `actions/soft_reset.py` with these EXACT substitutions:
- Module docstring: replace the soft_reset docstring with one that names this as RECOVERY_SPEC §4.1 ladder rung 2 (signal-gated in Plan 04-04). Reference A-01 ("modem_reset is a policy distinction, not a protocol distinction").
- All three occurrences of `ActionKind.SOFT_RESET` → `ActionKind.MODEM_RESET`.
- The `failure_reason` literal `f"soft_reset:{err.reason.value}"` → `f"modem_reset:{err.reason.value}"`.
- Keep the QMI verb identical: `await ctx.qmi.dms_set_operating_mode("reset")` (same primitive per A-01).
- Keep the `verify()` body identical: `return VerifyResult.deferred(detail="next_cycle_observation")` (A-04).

Then extend `src/spark_modem/actions/dispatcher.py`:
1. Add `modem_reset` to the import list at lines 20-27 (alphabetically after `fix_raw_ip` to preserve sort):
   ```python
   from spark_modem.actions import (
       fix_autosuspend,
       fix_raw_ip,
       modem_reset,
       set_apn,
       set_operating_mode,
       sim_power_on,
       soft_reset,
   )
   ```
2. Append exactly one row to `_REGISTRY` (after `FIX_AUTOSUSPEND`):
   ```python
   ActionKind.MODEM_RESET: (modem_reset.execute, modem_reset.verify),
   ```
   Do NOT add USB_RESET or DRIVER_RESET — those land in Plans 04-02 and 04-03.

Create `tests/unit/actions/test_modem_reset.py`:
- Mirror `test_soft_reset.py` structure (imports, `_who()`, `_argv()` helpers, pytest.mark.asyncio).
- Use `make_ctx` and `ok` from `tests/unit/actions/_helpers.py`.
- Implement the 5 tests from the `<behavior>` block above.
- Per A-01, the argv assertion is identical to the soft_reset version (same `--dms-set-operating-mode=reset` verb).

Per CLAUDE.md: list-form argv via the existing `subproc.runner` chain (no new subprocess code; QmiWrapper already handles the call). Pure file-level addition; SP-04 lint scope unchanged.
  </action>
  <verify>
    <automated>cd /s/spark/modem-watchdog &amp;&amp; .venv/bin/pytest tests/unit/actions/test_modem_reset.py -x &amp;&amp; .venv/bin/mypy --strict src/spark_modem/actions/modem_reset.py src/spark_modem/actions/dispatcher.py &amp;&amp; .venv/bin/ruff check src/spark_modem/actions/modem_reset.py src/spark_modem/actions/dispatcher.py tests/unit/actions/test_modem_reset.py &amp;&amp; .venv/bin/ruff format --check src/spark_modem/actions/modem_reset.py</automated>
  </verify>
  <acceptance_criteria>
    - File exists: `src/spark_modem/actions/modem_reset.py` (≥30 lines, ≤80 lines)
    - File contains: `async def execute(who: WhoModem, ctx: ActionContext) -> ActionResult:`
    - File contains: `async def verify(who: WhoModem, ctx: ActionContext) -> VerifyResult:`
    - File contains: `ActionKind.MODEM_RESET` (3 occurrences — execute success branch, execute failure branch, return ActionResult kind argument)
    - File contains: `await ctx.qmi.dms_set_operating_mode("reset")` (verbatim — same primitive as soft_reset per A-01)
    - File contains: `f"modem_reset:{err.reason.value}"` (NOT `f"soft_reset:..."`)
    - File contains: `VerifyResult.deferred(detail="next_cycle_observation")`
    - `grep -F 'ActionKind.MODEM_RESET: (modem_reset.execute' src/spark_modem/actions/dispatcher.py` returns ≥1 match
    - `grep -F 'modem_reset' src/spark_modem/actions/dispatcher.py` returns ≥2 matches (1 import line + 1 registry line)
    - `pytest tests/unit/actions/test_modem_reset.py -x` exits 0 with ≥5 tests collected
    - `mypy --strict src/spark_modem/actions/modem_reset.py` exits 0
    - `ruff check src/spark_modem/actions/modem_reset.py src/spark_modem/actions/dispatcher.py tests/unit/actions/test_modem_reset.py` exits 0
    - `ruff format --check src/spark_modem/actions/modem_reset.py` exits 0
    - `bash scripts/lint_no_subprocess.sh` exits 0 (SP-04 still passes — no new subprocess calls)
  </acceptance_criteria>
  <done>
    modem_reset.py registered, dispatcher imports it, 5 unit tests pass, mypy + ruff + SP-04 green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Update existing dispatcher / CLI tests for the new registration; clarify CLI error message</name>
  <files>
    src/spark_modem/cli/reset.py,
    tests/unit/actions/test_dispatcher.py,
    tests/unit/cli/test_reset.py
  </files>
  <read_first>
    - src/spark_modem/cli/reset.py (entire file, ~52 lines — the destructive-guard branch at lines 23-51)
    - tests/unit/actions/test_dispatcher.py (specifically `test_registered_kinds_has_exactly_six_cheap_actions` at ~lines 37-56 and `test_destructive_actions_not_registered` at ~lines 59-63 — see PATTERNS.md "Phase 4 modification" section for `dispatcher._REGISTRY`)
    - tests/unit/cli/test_reset.py (the existing CLI happy-path test for `reset --action=set_apn`)
    - .planning/phases/04-destructive-actions-hil/04-PATTERNS.md § "src/spark_modem/cli/reset.py" (the exact wording change)
  </read_first>
  <behavior>
    - test_registered_kinds_has_exactly_seven_kinds (renamed from `_six_cheap_actions`): assert `actions.dispatcher.registered_kinds()` returns frozenset of length 7 containing the 6 Phase-2 cheap actions PLUS `ActionKind.MODEM_RESET`.
    - test_modem_reset_registered (replaces the obsolete `test_destructive_actions_not_registered`): assert `is_registered(ActionKind.MODEM_RESET)` is True; assert `is_registered(ActionKind.USB_RESET)` is False (still — Plan 04-02 lands USB_RESET); assert `is_registered(ActionKind.DRIVER_RESET)` is False (still — Plan 04-03 lands DRIVER_RESET).
    - test_reset_modem_reset_cli_smoke: argparse parses `reset --action=modem_reset --modem=cdc-wdm0`; CLI run() returns 0; the printed line includes `action=modem_reset` and `modem=cdc-wdm0`.
    - test_reset_unknown_action_still_rejected: argparse parses `reset --action=quantum_tunnel`; CLI returns exit code 2; stderr contains `unknown action`.
  </behavior>
  <action>
Update `src/spark_modem/cli/reset.py` lines 32-39 ONLY (the rejection branch when `is_registered(kind)` is False). Replace the existing message:
```python
print(
    f"reset: action {kind.value} is destructive (Phase 4); "
    f"Phase 2 supports: {valid}",
    file=sys.stderr,
)
```
with the canonical Phase-4 wording:
```python
print(
    f"reset: action {kind.value} is not registered; valid: {valid}",
    file=sys.stderr,
)
```
This branch fires only on truly-unregistered kinds going forward. After Plan 04-01 lands MODEM_RESET, the `is_registered` check still rejects USB_RESET / DRIVER_RESET until Plans 04-02 / 04-03 land. Do NOT add the `--target` flag yet — that ships in Plan 04-02.

Update `tests/unit/actions/test_dispatcher.py`:
1. Rename `test_registered_kinds_has_exactly_six_cheap_actions` → `test_registered_kinds_has_exactly_seven_kinds`.
2. Update its body's expected frozenset from 6 to 7 entries (add `ActionKind.MODEM_RESET`).
3. Update the length assertion from `len(...) == 6` to `len(...) == 7`.
4. DELETE the existing `test_destructive_actions_not_registered` test (it now asserts the OPPOSITE of Phase 4's exit state — see PATTERNS.md § "Phase 4 modification").
5. Add a NEW test `test_modem_reset_registered_phase4` that asserts `is_registered(ActionKind.MODEM_RESET) is True`, `is_registered(ActionKind.USB_RESET) is False`, `is_registered(ActionKind.DRIVER_RESET) is False`. This documents that Plan 04-01 ships ONE destructive action; Plans 04-02 / 04-03 ship the other two — the test will need adjustment in those plans (each adds their own kind to the True-list).

Extend `tests/unit/cli/test_reset.py` with:
1. `test_reset_modem_reset_cli_smoke` per `<behavior>` above. Use the same argparse-construction pattern the existing happy-path test uses (parser construction in cli/reset.py); call `await run(args)` (or sync wrapper); assert return value == 0 and capture stdout for the dispatch-stub line.
2. `test_reset_unknown_action_still_rejected` — parses `--action=quantum_tunnel`, asserts return code 2 and stderr contains `unknown action`. (This is a regression test for the OTHER rejection branch — argparse-level, NOT the destructive guard.)

Per CLAUDE.md: CLI mutating commands acquire same flock as daemon (already wired by Phase 2 ctl reset-state pattern; not changed in this plan). No subprocess; no qmicli; this is pure CLI plumbing + test reshaping.
  </action>
  <verify>
    <automated>cd /s/spark/modem-watchdog &amp;&amp; .venv/bin/pytest tests/unit/actions/test_dispatcher.py tests/unit/cli/test_reset.py -x &amp;&amp; .venv/bin/mypy --strict src/spark_modem/cli/reset.py &amp;&amp; .venv/bin/ruff check src/spark_modem/cli/reset.py tests/unit/actions/test_dispatcher.py tests/unit/cli/test_reset.py</automated>
  </verify>
  <acceptance_criteria>
    - `grep -F 'is destructive (Phase 4)' src/spark_modem/cli/reset.py` returns 0 matches (old wording removed)
    - `grep -F 'is not registered; valid:' src/spark_modem/cli/reset.py` returns ≥1 match (new wording)
    - `grep -F 'test_registered_kinds_has_exactly_seven_kinds' tests/unit/actions/test_dispatcher.py` returns ≥1 match
    - `grep -F 'test_registered_kinds_has_exactly_six_cheap_actions' tests/unit/actions/test_dispatcher.py` returns 0 matches
    - `grep -F 'test_destructive_actions_not_registered' tests/unit/actions/test_dispatcher.py` returns 0 matches (deleted)
    - `grep -F 'test_modem_reset_registered_phase4' tests/unit/actions/test_dispatcher.py` returns ≥1 match
    - `grep -F 'test_reset_modem_reset_cli_smoke' tests/unit/cli/test_reset.py` returns ≥1 match
    - `pytest tests/unit/actions/test_dispatcher.py tests/unit/cli/test_reset.py -x` exits 0
    - `mypy --strict src/spark_modem/cli/reset.py` exits 0
    - `ruff check src/spark_modem/cli/reset.py tests/unit/actions/test_dispatcher.py tests/unit/cli/test_reset.py` exits 0
    - Full unit suite: `pytest -m "unit and not linux_only and not hil" -x` exits 0 (no regression in Phase 2/3 tests)
  </acceptance_criteria>
  <note>
    The dispatcher kind-count assertion test is renamed in each successive plan
    (04-01 → 7, 04-02 → 8, 04-03 → 9) to track the registry growth across waves.
    This rename is intentional; verification of plan 04-NN runs only against the
    state of the registry at that plan's commit time. Wave ordering (04-01 →
    04-02 → 04-03 sequential) guarantees the assertion is correct at execution.
  </note>
  <done>
    Dispatcher contract test asserts 7 registered kinds (MODEM_RESET + 6 cheap); destructive-rejection test inverted; CLI message updated; full unit suite green.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| CLI → daemon (per-modem flock) | `spark-modem reset --action=modem_reset` acquires the same per-modem flock the daemon uses (ADR-0012) — already wired via Plan 02-09 `ctl reset-state` pattern; this plan inherits it |
| daemon process → qmicli subprocess (via subproc/runner) | List-form argv only; LC_ALL=C; start_new_session; `--device-open-proxy` always (FR-74); existing Phase 1/2 discipline |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-01-01 | T (Tampering) | actions/modem_reset.py | mitigate | qmicli argv built via `QmiWrapper._argv()` (Phase 2 list-form discipline; no shell strings); same primitive as the existing soft_reset which has been audit-clean for two phases |
| T-04-01-02 | E (Elevation) | dispatcher._REGISTRY | mitigate | MODEM_RESET registered behind the existing dispatcher dry-run gate (FR-28) and behind the policy engine's signal gate (Plan 04-04) and ladder gate (Plan 04-04); CLI direct invocation still acquires per-modem flock per ADR-0012 |
| T-04-01-03 | I (Information disclosure) | cli/reset.py error message | accept | New error message `is not registered; valid: {valid}` lists registered kinds — public information already surfaced by `--help` and `dispatcher.registered_kinds()`; no PII / secrets exposed |
| T-04-01-04 | D (Denial of service) | back-to-back invocations | accept | Per A-05 modem_reset is genuinely re-runnable; per-modem flock serializes; the modem's natural ~30-60 s outage envelope is the rate-limit; ladder backoff (Plan 04-04) adds a 90 s cross-action floor |
| T-04-01-05 | R (Repudiation) | dispatcher event emission | mitigate | dispatcher already emits ActionPlanned + ActionExecuted/ActionFailed (events.jsonl) on every kind including the new MODEM_RESET; no per-kind code change needed |
</threat_model>

<verification>
- All Plan 04-01 task `<verify>` commands pass.
- `pytest -m "unit and not linux_only and not hil" -x` (full unit suite) exits 0.
- `pytest tests/unit/actions/ tests/unit/cli/test_reset.py -ra` exits 0.
- `mypy --strict src/spark_modem/` exits 0.
- `ruff check src/spark_modem/ tests/` exits 0.
- `ruff format --check src/spark_modem/ tests/` exits 0.
- `bash scripts/lint_no_subprocess.sh` exits 0 (SP-04: no new subprocess calls).
- `grep -F 'ActionKind.MODEM_RESET' src/spark_modem/actions/dispatcher.py` returns ≥2 matches (import row + _REGISTRY row).
- Manual sanity: `spark-modem reset --action=modem_reset --modem=cdc-wdm0 --dry-run` (or equivalent invocation through `python -m spark_modem.cli.main`) returns exit code 0 and prints a dispatch-stub line; same command with `--action=usb_reset` still returns 2 with the new "is not registered" message.
</verification>

<success_criteria>
- ActionKind.MODEM_RESET is registered in `actions.dispatcher._REGISTRY`.
- `actions/modem_reset.py` mirrors `actions/soft_reset.py` shape with the 4 verbatim substitutions (kind enum, failure_reason prefix, module docstring, file path).
- `cli/reset.py` no longer contains the "is destructive (Phase 4)" message.
- `tests/unit/actions/test_dispatcher.py` asserts exactly 7 registered ActionKinds.
- The new test file `tests/unit/actions/test_modem_reset.py` covers ≥5 paths
  (success, qmi_err proxy_died, qmi_err timeout, verify deferred, dispatcher
  registration). Plan 04-04 will extend with ladder progression tests.
- CLAUDE.md invariants honored: pure-engine policy untouched, list-form argv,
  match-on-state untouched, atomic state writes (none in this plan), per-modem
  flock unchanged.
- Full Phase 1+2+3 regression suite stays green (≥1835 tests + 5 new = ≥1840).
</success_criteria>

<output>
After completion, create `.planning/phases/04-destructive-actions-hil/04-01-SUMMARY.md`
documenting: files created/extended, the 5 new tests added, the test count
delta (was 6 cheap registered, now 7 = 6 cheap + MODEM_RESET), the dispatcher
contract assertion change (6 → 7), and a note that USB_RESET / DRIVER_RESET
remain unregistered until Plans 04-02 / 04-03 ship.
</output>
