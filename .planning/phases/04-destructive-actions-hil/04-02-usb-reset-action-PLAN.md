---
plan: 04-02
title: usb_reset action + new sysfs/ module + Sierra-bootloader handling + --target CLI flag
phase: 04
wave: 2
depends_on: [04-01]
files_modified:
  - src/spark_modem/sysfs/__init__.py
  - src/spark_modem/sysfs/usb_unbind_rebind.py
  - src/spark_modem/actions/usb_reset.py
  - src/spark_modem/actions/dispatcher.py
  - src/spark_modem/actions/context.py
  - src/spark_modem/wire/enums.py
  - src/spark_modem/policy/decision_table.py
  - src/spark_modem/cli/reset.py
  - tests/unit/sysfs/__init__.py
  - tests/unit/sysfs/test_usb_unbind_rebind.py
  - tests/unit/actions/test_usb_reset.py
  - tests/unit/actions/test_dispatcher.py
  - tests/unit/policy/test_decision_table.py
  - tests/unit/cli/test_reset.py
  - tests/test_recovery_spec.py
autonomous: true
requirements: [FR-23, FR-27]
must_haves:
  truths:
    - "ActionKind.USB_RESET is registered in actions.dispatcher._REGISTRY"
    - "actions/usb_reset.py writes the modem's bus-port path to /sys/bus/usb/drivers/usb/unbind, sleeps, then writes the same path to /sys/bus/usb/drivers/usb/bind"
    - "Two variants: child-port (default) writes the leaf usb_path; parent-hub writes usb_path.rsplit('.', 1)[0] (per A-06 / PITFALLS §1.6)"
    - "verify() returns VerifyResult.deferred(detail='next_cycle_observation') (A-04)"
    - "IssueDetail.SIERRA_BOOTLOADER exists in wire/enums.py under the # Enumeration / power group"
    - "decision_table contains row (IssueCategory.QMI, IssueDetail.SIERRA_BOOTLOADER) → ActionKind.USB_RESET (per PATTERNS.md correction #4: IssueCategory.ENUMERATION does not exist; reuse QMI)"
    - "spark-modem reset --action=usb_reset --modem=cdc-wdm0 --target=parent-hub is accepted; default --target is child-port"
    - "ActionContext.target field defaults to 'child-port'; usb_reset reads it; other actions ignore"
  artifacts:
    - path: "src/spark_modem/sysfs/__init__.py"
      provides: "Re-exports unbind_rebind"
      contains: "from spark_modem.sysfs.usb_unbind_rebind import unbind_rebind"
    - path: "src/spark_modem/sysfs/usb_unbind_rebind.py"
      provides: "Module-level async def unbind_rebind(usb_path, *, target, sysfs_root, rebind_delay_seconds)"
      contains: "async def unbind_rebind"
    - path: "src/spark_modem/actions/usb_reset.py"
      provides: "USB_RESET execute/verify"
      contains: "ActionKind.USB_RESET"
    - path: "tests/unit/sysfs/test_usb_unbind_rebind.py"
      provides: "sysfs file-write semantics tests (child-port + parent-hub + EBUSY/ENODEV/EACCES paths)"
    - path: "tests/unit/actions/test_usb_reset.py"
      provides: "usb_reset action unit tests with tmp_path-injected sysfs root"
  key_links:
    - from: "src/spark_modem/actions/usb_reset.py"
      to: "src/spark_modem/sysfs/usb_unbind_rebind.py"
      via: "import"
      pattern: "from spark_modem.sysfs import unbind_rebind"
    - from: "src/spark_modem/actions/usb_reset.py"
      to: "ctx.sysfs_root and ctx.target"
      via: "read-only ActionContext fields"
      pattern: "ctx\\.sysfs_root|ctx\\.target"
    - from: "src/spark_modem/policy/decision_table.py"
      to: "src/spark_modem/wire/enums.py:IssueDetail.SIERRA_BOOTLOADER"
      via: "decision-table row"
      pattern: "IssueCategory\\.QMI, IssueDetail\\.SIERRA_BOOTLOADER"
---

<objective>
Land the second destructive action: `usb_reset`. Per CONTEXT A-02, this is
sysfs file I/O — NOT subprocess. SP-04 lint scope unchanged because file
writes aren't subprocess. Per A-06, this plan also adds first-class support
for Sierra EM7421 stuck-in-bootloader (1199:9051): a new
`IssueDetail.SIERRA_BOOTLOADER` enum value, a new decision-table row, and a
`parent-hub` variant of usb_reset that re-fires the boot transition by
unbinding the parent hub (PITFALLS §1.6).

**Important correction from PATTERNS.md #4:** CONTEXT A-06 wording
`(IssueCategory.ENUMERATION, IssueDetail.SIERRA_BOOTLOADER)` cannot be
honored — `IssueCategory.ENUMERATION` does not exist in `wire/enums.py:13-20`.
This plan uses `(IssueCategory.QMI, IssueDetail.SIERRA_BOOTLOADER)` because
the modem is observed via QMI failures when stuck in bootloader.

Purpose:
- Land the second of three destructive actions (FR-23 / FR-27).
- Open the sysfs/ package as the leaf for any future sysfs-only action
  (CONTEXT D-decision item 1: planner picks single-file layout —
  `sysfs/usb_unbind_rebind.py` + `sysfs/__init__.py` re-export).
- Add the `--target=parent-hub` CLI surface (A-06) so an operator can
  manually re-fire a Sierra-bootloader-stuck modem.

Output:
- New package: `src/spark_modem/sysfs/` (`__init__.py` + `usb_unbind_rebind.py`).
- New action: `src/spark_modem/actions/usb_reset.py`.
- Extended: `actions/dispatcher.py` (+1 row), `actions/context.py` (+1 field),
  `wire/enums.py` (+1 IssueDetail value), `policy/decision_table.py` (+1 row),
  `cli/reset.py` (+1 argparse flag).
- Tests: 12 new unit tests (8 errno × 1.5 multiplier per RESEARCH.md
  per-plan rate floor).
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

From src/spark_modem/actions/fix_autosuspend.py:25-46 (the closest sysfs-write analog):
```python
async def execute(who: WhoModem, ctx: ActionContext) -> ActionResult:
    start = ctx.clock.monotonic()
    target = _power_control_path(ctx.sysfs_root, who.usb_path)
    try:
        target.write_text("on", encoding="ascii")
    except OSError as exc:
        return ActionResult(
            kind=ActionKind.FIX_AUTOSUSPEND,
            who=who,
            succeeded=False,
            duration_seconds=ctx.clock.monotonic() - start,
            failure_reason=f"sysfs_write_error:{exc.errno}",
            dry_run=False,
        )
    return ActionResult(
        kind=ActionKind.FIX_AUTOSUSPEND,
        who=who,
        succeeded=True,
        ...
    )
```

From src/spark_modem/inventory/sysfs.py:24-30 (the `sysfs_root_override` discipline):
```python
class SysfsInventory:
    def __init__(self, *, sysfs_root_override: Path | None = None) -> None:
        self._sysfs_root = sysfs_root_override or Path("/sys")
```

From src/spark_modem/actions/context.py:47-67 (the ActionContext to extend with `target`):
```python
@dataclass(frozen=True)
class ActionContext:
    qmi: QmiWrapper
    clock: ClockProto
    config: Settings
    carrier_table: CarrierTable
    event_logger: EventLogWriterProto
    sysfs_root: Path = field(default_factory=lambda: Path("/sys"))
```

From src/spark_modem/wire/enums.py:23-79 (IssueDetail — extend the # Enumeration / power group):
```python
class IssueDetail(StrEnum):
    ...
    # Enumeration / power
    ENUMERATION_MISSING = "enumeration_missing"
    ENUMERATION_ADDRESS_FAIL = "enumeration_address_fail"
    ENUMERATION_OVERCURRENT = "enumeration_overcurrent"
    AUTOSUSPEND_ON = "autosuspend_on"
    ...
```

From src/spark_modem/policy/decision_table.py:35-64 (the table to extend; row added under # qmi -- priority 5):
```python
_DECISION_TABLE: dict[tuple[IssueCategory, IssueDetail], ActionKind | str] = {
    ...
    # qmi -- priority 5
    (IssueCategory.QMI, IssueDetail.QMI_CHANNEL_HUNG): ActionKind.USB_RESET,
    (IssueCategory.QMI, IssueDetail.OPERATING_MODE_OFFLINE): ActionKind.MODEM_RESET,
    (IssueCategory.QMI, IssueDetail.OPERATING_MODE_LOW_POWER): ActionKind.MODEM_RESET,
    (IssueCategory.QMI, IssueDetail.QMI_PROXY_DIED): ActionKind.DRIVER_RESET,
    (IssueCategory.QMI, IssueDetail.QMI_TIMEOUT): ActionKind.SOFT_RESET,
}
```

From src/spark_modem/cli/reset.py (current parser — `--target` flag to add):
```python
parser.add_argument("--action", required=True, ...)
parser.add_argument("--modem", required=True, ...)
parser.add_argument("--dry-run", action="store_true", ...)
# NEW (this plan):
parser.add_argument(
    "--target",
    choices=["child-port", "parent-hub"],
    default="child-port",
    help="usb_reset variant; parent-hub re-fires the boot transition (PITFALLS §1.6).",
)
```

Sysfs write protocol (verified against LWN.net /Articles/143397/ + kernel.org cdc_mbim docs):
- Unbind: `echo "<usb_path>" > /sys/bus/usb/drivers/usb/unbind`
- Bind:   `echo "<usb_path>" > /sys/bus/usb/drivers/usb/bind`
- Sleep between them: 500ms (child-port) / 1000ms (parent-hub) — RESEARCH.md A1 [ASSUMED]; conservative.
- Child-port: `usb_path = "2-3.1.1"` (the modem's leaf bus-port).
- Parent-hub: `usb_path.rsplit(".", 1)[0] = "2-3.1"` (the hub one level up).
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Create sysfs/ package + unbind_rebind helper + sysfs unit tests + extend ActionContext.target</name>
  <files>
    src/spark_modem/sysfs/__init__.py,
    src/spark_modem/sysfs/usb_unbind_rebind.py,
    src/spark_modem/actions/context.py,
    tests/unit/sysfs/__init__.py,
    tests/unit/sysfs/test_usb_unbind_rebind.py
  </files>
  <read_first>
    - src/spark_modem/inventory/sysfs.py (Path discipline + sysfs_root_override pattern; lines 24-130)
    - src/spark_modem/actions/fix_autosuspend.py (the sysfs-write analog with try/except OSError; entire 62-line file)
    - src/spark_modem/actions/context.py (entire file — the ActionContext dataclass to extend)
    - .planning/phases/04-destructive-actions-hil/04-PATTERNS.md § "src/spark_modem/sysfs/__init__.py + src/spark_modem/sysfs/usb_unbind_rebind.py"
    - .planning/research/PITFALLS.md §1.6 (Sierra EM7421 stuck-in-bootloader → parent-hub usb_reset prescription)
  </read_first>
  <behavior>
    - test_unbind_rebind_writes_usb_path_to_unbind_then_bind_child_port: pre-create `<tmp>/bus/usb/drivers/usb/{unbind,bind}` files; call `await unbind_rebind("2-3.1.1", target="child-port", sysfs_root=tmp_path, rebind_delay_seconds=0.0)`; assert `(tmp_path/"bus/usb/drivers/usb/unbind").read_text(encoding="ascii") == "2-3.1.1"` and `(tmp_path/"bus/usb/drivers/usb/bind").read_text(encoding="ascii") == "2-3.1.1"`.
    - test_unbind_rebind_parent_hub_strips_leaf_segment: same setup; call with `target="parent-hub"`; assert both files contain `"2-3.1"` (NOT `"2-3.1.1"`).
    - test_unbind_rebind_sleeps_between_writes: monkey-patch `asyncio.sleep` to record args; call with `rebind_delay_seconds=0.5`; assert `asyncio.sleep` was awaited exactly once with argument `0.5` BETWEEN the unbind and bind writes (verify ordering by also recording write-call order).
    - test_unbind_rebind_default_sysfs_root_is_slash_sys: call without `sysfs_root` kwarg on a non-Linux dev host inside a tmp_path-scoped chdir; expect OSError on the actual `/sys` path (because `/sys/bus/usb/drivers/usb/unbind` does not exist on Windows / is read-only without CAP_SYS_ADMIN); the test asserts the OSError type, NOT a successful write — this proves the default is `/sys` and not silently swallowed. Use `pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only default-path semantics")` for the part that exercises the real path.
    - test_unbind_rebind_raises_oserror_on_unbind_failure: setup tmp_path WITHOUT pre-creating `unbind` (FileNotFoundError); call `unbind_rebind`; expect OSError to propagate (caller in `actions/usb_reset.py` is responsible for wrapping into ActionResult.failure_reason — see Task 2).
    - test_unbind_rebind_raises_oserror_on_bind_failure: pre-create `unbind` only (so unbind succeeds); call `unbind_rebind`; expect OSError on the bind write to propagate.

    ActionContext extension:
    - test_action_context_default_target_is_child_port: construct ActionContext(...) with the existing required positional/keyword fields; assert `ctx.target == "child-port"`.
    - test_action_context_target_can_be_parent_hub: same construction with `target="parent-hub"`; assert `ctx.target == "parent-hub"`.
  </behavior>
  <action>
Create new package `src/spark_modem/sysfs/`:

1. `src/spark_modem/sysfs/__init__.py`:
   ```python
   """sysfs file-I/O helpers (no subprocess; no qmicli)."""

   from spark_modem.sysfs.usb_unbind_rebind import unbind_rebind

   __all__ = ["unbind_rebind"]
   ```

2. `src/spark_modem/sysfs/usb_unbind_rebind.py`:
   ```python
   """USB driver unbind/rebind via sysfs file writes (CAP_SYS_ADMIN; preallocated by Plan 03-08 U-01).

   Per A-02 / A-06 / PITFALLS §1.6:
   - child-port (default): writes the modem's leaf bus-port path (e.g. "2-3.1.1")
     to /sys/bus/usb/drivers/usb/{unbind,bind}. Recovers SC#4 QMI-hung modems.
   - parent-hub: writes the parent hub bus-port (e.g. "2-3.1") to the same files.
     Re-fires the Sierra EM7421 boot transition for IssueDetail.SIERRA_BOOTLOADER.

   File I/O only; SP-04 lint untouched (no subprocess, no qmicli).

   Reference: LWN.net /Articles/143397/ "Manual driver binding and unbinding".
   """

   from __future__ import annotations

   import asyncio
   from pathlib import Path
   from typing import Literal


   async def unbind_rebind(
       usb_path: str,
       *,
       target: Literal["child-port", "parent-hub"] = "child-port",
       sysfs_root: Path | None = None,
       rebind_delay_seconds: float = 0.5,
   ) -> None:
       """Write usb_path to drivers/usb/unbind, sleep, then write to drivers/usb/bind.

       Raises OSError on any underlying file-write failure; caller wraps into
       ActionResult.failure_reason at the actions/usb_reset.py boundary.
       """
       root = sysfs_root if sysfs_root is not None else Path("/sys")
       payload = usb_path if target == "child-port" else usb_path.rsplit(".", 1)[0]
       unbind_path = root / "bus" / "usb" / "drivers" / "usb" / "unbind"
       bind_path = root / "bus" / "usb" / "drivers" / "usb" / "bind"
       unbind_path.write_text(payload, encoding="ascii")
       await asyncio.sleep(rebind_delay_seconds)
       bind_path.write_text(payload, encoding="ascii")
   ```

3. Extend `src/spark_modem/actions/context.py`:
   - Add to imports at the top: `from typing import Literal` (if not already imported).
   - Add ONE new field to `ActionContext` dataclass AFTER `sysfs_root`:
     ```python
     target: Literal["child-port", "parent-hub"] = "child-port"
     ```
   - Update the docstring inside `ActionContext` to mention `target` reads by `actions/usb_reset.py` (other actions ignore).

4. Create `tests/unit/sysfs/__init__.py` (empty file — package marker).

5. Create `tests/unit/sysfs/test_usb_unbind_rebind.py` implementing the 8 tests in the `<behavior>` block above. Use `pytest.mark.asyncio` and `tmp_path` fixtures. The 6 sysfs-helper tests + 2 ActionContext-default tests live here for cohesion (alternative is to split ActionContext tests into `tests/unit/actions/test_context.py` — but no such file exists today; keeping them with the sysfs-helper tests is the lower-overhead option).

Per CLAUDE.md invariants: no subprocess in `src/spark_modem/sysfs/`; pure file I/O via `Path.write_text`. Module is Windows-importable (no `/sys` reads at import time).
  </action>
  <verify>
    <automated>cd /s/spark/modem-watchdog &amp;&amp; .venv/bin/pytest tests/unit/sysfs/test_usb_unbind_rebind.py -x &amp;&amp; .venv/bin/mypy --strict src/spark_modem/sysfs/ src/spark_modem/actions/context.py &amp;&amp; .venv/bin/ruff check src/spark_modem/sysfs/ tests/unit/sysfs/ &amp;&amp; .venv/bin/ruff format --check src/spark_modem/sysfs/ &amp;&amp; bash scripts/lint_no_subprocess.sh</automated>
  </verify>
  <acceptance_criteria>
    - File exists: `src/spark_modem/sysfs/__init__.py` (≤10 lines)
    - File exists: `src/spark_modem/sysfs/usb_unbind_rebind.py` (≥30 lines, ≤80 lines)
    - `grep -F 'async def unbind_rebind' src/spark_modem/sysfs/usb_unbind_rebind.py` returns ≥1 match
    - `grep -F 'target: Literal["child-port", "parent-hub"]' src/spark_modem/sysfs/usb_unbind_rebind.py` returns ≥1 match
    - `grep -F 'usb_path.rsplit(".", 1)[0]' src/spark_modem/sysfs/usb_unbind_rebind.py` returns ≥1 match (parent-hub computation)
    - `grep -F 'await asyncio.sleep(rebind_delay_seconds)' src/spark_modem/sysfs/usb_unbind_rebind.py` returns ≥1 match
    - `grep -F 'target: Literal["child-port", "parent-hub"]' src/spark_modem/actions/context.py` returns ≥1 match (the new field)
    - `grep -F '"child-port"' src/spark_modem/actions/context.py` returns ≥1 match (the default value)
    - File exists: `tests/unit/sysfs/__init__.py`
    - File exists: `tests/unit/sysfs/test_usb_unbind_rebind.py` with ≥8 test functions
    - `pytest tests/unit/sysfs/test_usb_unbind_rebind.py -x` exits 0 with ≥8 tests collected
    - `mypy --strict src/spark_modem/sysfs/ src/spark_modem/actions/context.py` exits 0
    - `ruff check src/spark_modem/sysfs/ tests/unit/sysfs/` exits 0
    - `ruff format --check src/spark_modem/sysfs/` exits 0
    - `bash scripts/lint_no_subprocess.sh` exits 0 (SP-04: NO subprocess in sysfs/)
    - `grep -rE 'subprocess|create_subprocess_exec|os\.system' src/spark_modem/sysfs/` returns 0 matches
  </acceptance_criteria>
  <done>
    sysfs/ package created with `unbind_rebind`; ActionContext gains `target` field with default "child-port"; 8 sysfs unit tests pass; SP-04 / mypy / ruff green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Create actions/usb_reset.py + register in dispatcher + add IssueDetail.SIERRA_BOOTLOADER + decision-table row + --target CLI flag + recovery-spec lint update</name>
  <files>
    src/spark_modem/actions/usb_reset.py,
    src/spark_modem/actions/dispatcher.py,
    src/spark_modem/wire/enums.py,
    src/spark_modem/policy/decision_table.py,
    src/spark_modem/cli/reset.py,
    tests/unit/actions/test_usb_reset.py,
    tests/unit/actions/test_dispatcher.py,
    tests/unit/policy/test_decision_table.py,
    tests/unit/cli/test_reset.py,
    tests/test_recovery_spec.py
  </files>
  <read_first>
    - src/spark_modem/actions/fix_autosuspend.py (sysfs-write action analog — entire file)
    - src/spark_modem/actions/dispatcher.py (the _REGISTRY block at lines 39-46 + import block at 20-27 — already extended in Plan 04-01 with MODEM_RESET)
    - src/spark_modem/wire/enums.py:23-79 (IssueDetail enum — extend the # Enumeration / power group)
    - src/spark_modem/policy/decision_table.py:35-64 (the # qmi -- priority 5 block)
    - src/spark_modem/cli/reset.py (entire file — argparse setup)
    - tests/test_recovery_spec.py (the manifest the `tools/check_spec.py` lint reads — must mention `sierra_bootloader`)
    - tools/check_spec.py:31-35 (the substring lint that fails CI if a new IssueDetail is missing from the test manifest)
    - .planning/phases/04-destructive-actions-hil/04-PATTERNS.md § "src/spark_modem/actions/usb_reset.py" + § "src/spark_modem/wire/enums.py" + § "src/spark_modem/policy/decision_table.py" + § "src/spark_modem/cli/reset.py"
  </read_first>
  <behavior>
    Action body (test_usb_reset.py):
    - test_usb_reset_default_target_is_child_port: tmp_path-injected sysfs_root; pre-create `<tmp>/bus/usb/drivers/usb/{unbind,bind}` files; ActionContext default `target="child-port"`; call `await usb_reset.execute(WhoModem(usb_path="2-3.1.1", cdc_wdm="cdc-wdm0"), ctx)`; assert succeeded == True, kind == ActionKind.USB_RESET, dry_run == False; assert `(tmp_path/"bus/usb/drivers/usb/unbind").read_text() == "2-3.1.1"`.
    - test_usb_reset_parent_hub_target_strips_leaf: same setup with ActionContext `target="parent-hub"`; assert unbind file content == `"2-3.1"`.
    - test_usb_reset_returns_failure_on_oserror: tmp_path without pre-created unbind file (FileNotFoundError); assert succeeded == False, failure_reason starts with `"usb_reset:sysfs_write_error:"` and contains the errno (e.g. `:2` for ENOENT).
    - test_usb_reset_returns_failure_on_eacces: pre-create unbind file with mode 0o400 (read-only); skipif win32 (chmod semantics differ); assert succeeded == False, failure_reason contains `:13` (EACCES).
    - test_usb_reset_returns_failure_on_ebusy: monkey-patch `Path.write_text` to raise `OSError(errno.EBUSY, ...)`; assert failure_reason contains `:16` (EBUSY).
    - test_usb_reset_verify_is_deferred: call verify(); assert VerifyResult.kind == "deferred" with detail == "next_cycle_observation".
    - test_usb_reset_registered_in_dispatcher: assert ActionKind.USB_RESET in actions.dispatcher.registered_kinds().
    - test_usb_reset_uses_short_rebind_delay_under_test: monkey-patch `asyncio.sleep` to capture call args; assert at most 1 sleep call; assert the sleep duration equals 0.5 by default (or matches the value the action passes — pin in implementation).

    Decision-table tests (test_decision_table.py — extend existing):
    - test_decision_table_has_sierra_bootloader_row: assert `lookup_action(IssueCategory.QMI, IssueDetail.SIERRA_BOOTLOADER) == ActionKind.USB_RESET`.
    - Update `test_every_decision_table_row_resolves` row count: prior assertion `>=18` becomes `>=19`.

    CLI tests (test_reset.py — extend existing):
    - test_reset_target_flag_default_is_child_port: parse `reset --action=usb_reset --modem=cdc-wdm0`; assert `args.target == "child-port"`.
    - test_reset_target_parent_hub_accepted: parse `reset --action=usb_reset --modem=cdc-wdm0 --target=parent-hub`; assert `args.target == "parent-hub"`.
    - test_reset_target_invalid_rejected: parse `reset --action=usb_reset --modem=cdc-wdm0 --target=quantum-tunnel`; assert argparse SystemExit(2).
    - test_reset_usb_reset_cli_smoke: parse `reset --action=usb_reset --modem=cdc-wdm0`; CLI run() returns 0; printed line contains `action=usb_reset` and `modem=cdc-wdm0`.

    Dispatcher contract test (test_dispatcher.py — update prior 04-01 contract):
    - Update `test_registered_kinds_has_exactly_seven_kinds` → `test_registered_kinds_has_exactly_eight_kinds`: expected length 8 (6 cheap + MODEM_RESET + USB_RESET).
    - Update `test_modem_reset_registered_phase4` → `test_destructive_actions_partially_registered_phase4_02`: assert MODEM_RESET and USB_RESET registered True, DRIVER_RESET still False.
  </behavior>
  <action>
**Step A — Extend `wire/enums.py`:**
- Add ONE new IssueDetail value under the `# Enumeration / power` group (after `AUTOSUSPEND_ON`):
  ```python
  SIERRA_BOOTLOADER = "sierra_bootloader"
  ```
- Per PATTERNS.md correction #4: do NOT add an `IssueCategory.ENUMERATION` value. The decision-table row lives under `IssueCategory.QMI` because the modem is observed via QMI failures when stuck in bootloader.

**Step B — Extend `policy/decision_table.py`:**
- Add ONE new row in the `# qmi -- priority 5` block (anywhere after `QMI_TIMEOUT`):
  ```python
  (IssueCategory.QMI, IssueDetail.SIERRA_BOOTLOADER): ActionKind.USB_RESET,
  ```
- Note: the parent-hub variant is selected by the CLI `--target=parent-hub` flag and the ActionContext.target field (Task 1). The decision-table row itself is just `USB_RESET` — the action body inspects `ctx.target` to decide child vs parent. (Future Phase-4-or-later: if the engine wants to AUTO-promote `SIERRA_BOOTLOADER` rows to parent-hub without operator intervention, that's a follow-up; this plan ships the operator-driven path first per A-06.)

**Step C — Update `tests/test_recovery_spec.py`:**
- The `tools/check_spec.py` lint (verified at lines 31-35) does substring-match against the test-file's "Coverage manifest" docstring. Add one line to that manifest:
  ```
  - (qmi, sierra_bootloader) → usb_reset (parent-hub variant per CLI --target / A-06)
  ```
  Place it under the existing qmi-priority-5 block in the manifest. Without this edit the `tools/check_spec.py` check fails CI.

**Step D — Create `src/spark_modem/actions/usb_reset.py`:**
```python
"""usb_reset -- sysfs unbind+rebind. Verify is DEFERRED (next-cycle observation).

Per A-02 / A-06: file I/O only, NO subprocess. Two variants selected via
`ctx.target`:
  - "child-port" (default): writes the leaf usb_path to /sys/bus/usb/drivers/usb/{un,}bind.
  - "parent-hub": writes the parent hub usb_path (rsplit on '.') for SIERRA_BOOTLOADER per PITFALLS §1.6.

CAP_SYS_ADMIN preallocated by Plan 03-08 U-01; sysfs_root tmp_path-injected in tests.
"""

from __future__ import annotations

from spark_modem.actions.context import ActionContext
from spark_modem.actions.result import ActionResult, VerifyResult
from spark_modem.sysfs import unbind_rebind
from spark_modem.wire.diag import WhoModem
from spark_modem.wire.enums import ActionKind


async def execute(who: WhoModem, ctx: ActionContext) -> ActionResult:
    start = ctx.clock.monotonic()
    try:
        await unbind_rebind(
            who.usb_path,
            target=ctx.target,
            sysfs_root=ctx.sysfs_root,
        )
    except OSError as exc:
        return ActionResult(
            kind=ActionKind.USB_RESET,
            who=who,
            succeeded=False,
            duration_seconds=ctx.clock.monotonic() - start,
            failure_reason=f"usb_reset:sysfs_write_error:{exc.errno}",
            dry_run=False,
        )
    return ActionResult(
        kind=ActionKind.USB_RESET,
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

**Step E — Extend `actions/dispatcher.py`:**
- Add `usb_reset` to the import list (alphabetical ordering preserved):
  ```python
  from spark_modem.actions import (
      fix_autosuspend,
      fix_raw_ip,
      modem_reset,
      set_apn,
      set_operating_mode,
      sim_power_on,
      soft_reset,
      usb_reset,
  )
  ```
- Append ONE row to `_REGISTRY` (after MODEM_RESET):
  ```python
  ActionKind.USB_RESET: (usb_reset.execute, usb_reset.verify),
  ```

**Step F — Extend `cli/reset.py`:**
- Find the argparse parser construction (existing `add_argument` calls for `--action`, `--modem`, `--dry-run`).
- Add ONE new argument (placement: after `--dry-run`):
  ```python
  parser.add_argument(
      "--target",
      choices=["child-port", "parent-hub"],
      default="child-port",
      help="usb_reset variant; parent-hub re-fires the boot transition (PITFALLS §1.6).",
  )
  ```
- Update the dispatch-stub print line to also include `target={args.target}` (purely informational; the actual ActionContext.target is set when the daemon-style runner constructs ActionContext for the dispatcher invocation — this CLI prints what would be passed).

**Step G — Tests:**
- Create `tests/unit/actions/test_usb_reset.py` with the 8 action tests from `<behavior>`. Use `make_ctx(runner=FakeRunner(), sysfs_root=tmp_path)` from `_helpers.py`; pre-create the unbind/bind files via `(tmp_path/"bus/usb/drivers/usb").mkdir(parents=True, exist_ok=True); (tmp_path/"bus/usb/drivers/usb/unbind").write_text(""); (tmp_path/"bus/usb/drivers/usb/bind").write_text("")`. For the `target="parent-hub"` test, construct ActionContext with `target="parent-hub"` (use `dataclasses.replace(ctx, target="parent-hub")`).
- Extend `tests/unit/policy/test_decision_table.py` with `test_decision_table_has_sierra_bootloader_row` and update the row-count assertion.
- Extend `tests/unit/cli/test_reset.py` with the 4 new CLI tests.
- Update `tests/unit/actions/test_dispatcher.py`: rename the count-pin test, expand expected frozenset to 8, update the partial-registration test.

Per CLAUDE.md: pure-policy untouched (decision_table is data); list-form argv N/A (no subprocess); match-on-state untouched; per-modem flock not changed (existing CLI ctl-reset-state pattern from Plan 02-09 governs).
  </action>
  <verify>
    <automated>cd /s/spark/modem-watchdog &amp;&amp; .venv/bin/pytest tests/unit/actions/test_usb_reset.py tests/unit/actions/test_dispatcher.py tests/unit/policy/test_decision_table.py tests/unit/cli/test_reset.py tests/unit/sysfs/ -x &amp;&amp; .venv/bin/mypy --strict src/spark_modem/actions/usb_reset.py src/spark_modem/wire/enums.py src/spark_modem/policy/decision_table.py src/spark_modem/cli/reset.py &amp;&amp; .venv/bin/ruff check src/spark_modem/actions/usb_reset.py tests/unit/actions/test_usb_reset.py &amp;&amp; .venv/bin/ruff format --check src/spark_modem/actions/usb_reset.py &amp;&amp; bash scripts/lint_no_subprocess.sh &amp;&amp; .venv/bin/python tools/check_spec.py</automated>
  </verify>
  <acceptance_criteria>
    - File exists: `src/spark_modem/actions/usb_reset.py`
    - `grep -F 'from spark_modem.sysfs import unbind_rebind' src/spark_modem/actions/usb_reset.py` returns ≥1 match
    - `grep -F 'ActionKind.USB_RESET' src/spark_modem/actions/usb_reset.py` returns ≥3 matches (3 ActionResult constructions)
    - `grep -F 'usb_reset:sysfs_write_error:' src/spark_modem/actions/usb_reset.py` returns ≥1 match
    - `grep -F 'VerifyResult.deferred(detail="next_cycle_observation")' src/spark_modem/actions/usb_reset.py` returns ≥1 match
    - `grep -F 'SIERRA_BOOTLOADER = "sierra_bootloader"' src/spark_modem/wire/enums.py` returns ≥1 match
    - `grep -F '(IssueCategory.QMI, IssueDetail.SIERRA_BOOTLOADER): ActionKind.USB_RESET' src/spark_modem/policy/decision_table.py` returns ≥1 match
    - `grep -F 'IssueCategory.ENUMERATION' src/spark_modem/policy/decision_table.py` returns 0 matches (per PATTERNS correction #4 — we do NOT add this category)
    - `grep -F 'ActionKind.USB_RESET: (usb_reset.execute' src/spark_modem/actions/dispatcher.py` returns ≥1 match
    - `grep -F '"--target"' src/spark_modem/cli/reset.py` returns ≥1 match
    - `grep -F 'choices=["child-port", "parent-hub"]' src/spark_modem/cli/reset.py` returns ≥1 match
    - `grep -F 'sierra_bootloader' tests/test_recovery_spec.py` returns ≥1 match (recovery-spec lint)
    - `pytest tests/unit/actions/test_usb_reset.py -x` exits 0 with ≥8 tests collected
    - `pytest tests/unit/policy/test_decision_table.py -x` exits 0 with the new SIERRA_BOOTLOADER row test
    - `pytest tests/unit/cli/test_reset.py -x` exits 0 with the 4 new --target tests
    - `pytest tests/unit/actions/test_dispatcher.py::test_registered_kinds_has_exactly_eight_kinds -x` exits 0
    - `mypy --strict src/spark_modem/actions/usb_reset.py src/spark_modem/wire/enums.py src/spark_modem/policy/decision_table.py src/spark_modem/cli/reset.py` exits 0
    - `ruff check src/spark_modem/actions/usb_reset.py tests/unit/actions/test_usb_reset.py` exits 0
    - `bash scripts/lint_no_subprocess.sh` exits 0 (SP-04: usb_reset uses sysfs file I/O ONLY, NO subprocess)
    - `python tools/check_spec.py` exits 0 (recovery-spec manifest mentions `sierra_bootloader`)
    - Full unit suite: `pytest -m "unit and not linux_only and not hil" -x` exits 0 (no regression)
  </acceptance_criteria>
  <note>
    The dispatcher kind-count assertion test is renamed in each successive plan
    (04-01 → 7, 04-02 → 8, 04-03 → 9) to track the registry growth across waves.
    This rename is intentional; verification of plan 04-NN runs only against the
    state of the registry at that plan's commit time. Wave ordering (04-01 →
    04-02 → 04-03 sequential) guarantees the assertion is correct at execution.
  </note>
  <done>
    usb_reset registered, IssueDetail.SIERRA_BOOTLOADER added under # Enumeration / power group, decision-table row routes (QMI, SIERRA_BOOTLOADER) → USB_RESET, --target CLI flag accepted, recovery-spec lint passes, ≥12 unit tests added across 4 files.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| daemon process → kernel sysfs | `Path.write_text` to `/sys/bus/usb/drivers/usb/{un,}bind` requires CAP_SYS_ADMIN (preallocated by Plan 03-08 U-01) — kernel is trusted; the data we write IS the trust boundary |
| CLI / ActionContext → sysfs file I/O | `usb_path` value flows from inventory (Phase 2 sysfs walk / Phase 3 udev) into `usb_reset.execute` and is written verbatim to the kernel |
| daemon → bench Jetson hardware (Phase 4 HIL) | usb_reset's sysfs writes physically de-enumerate and re-enumerate the modem; CAP_SYS_ADMIN means an attacker who can call this can drop USB devices system-wide |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-02-01 | T (Tampering) | sysfs unbind/bind path-traversal | mitigate | The sysfs target paths are FIXED string literals (`unbind_path = root / "bus" / "usb" / "drivers" / "usb" / "unbind"`); `usb_path` is the WRITE PAYLOAD, not part of the path. Defense: even if `usb_path` contains `..` or `\0`, it's just bytes written to a fixed kernel-controlled file; the kernel validates the bus-port string format before acting (rejects malformed values with EINVAL). Add a unit-test (test_unbind_rebind_kernel_rejects_invalid_payload via `Path.write_text` raising OSError on invalid kernel string) — already covered by the EBUSY/EACCES paths |
| T-04-02-02 | T (Tampering) | inventory → usb_reset usb_path injection | mitigate | The `usb_path` passed in is a `WhoModem.usb_path` field (Phase 1 wire type, pydantic-validated via `BaseWire(extra="forbid", frozen=True)`); inventory only emits values from sysfs walks, never from external input. usb_reset trusts WhoModem completely — that trust is established at the inventory boundary (Plan 03-02 udev producer). |
| T-04-02-03 | E (Elevation) | parent-hub variant unbinds 4 modems | mitigate | parent-hub variant is gated behind operator-explicit `--target=parent-hub` CLI flag OR the SIERRA_BOOTLOADER decision-table row (which fires only when QMI observation reports the modem as enumerated-as-bootloader). Default is child-port (single-modem impact). The decision-table row uses `IssueCategory.QMI` per PATTERNS correction #4, ensuring the priority-order table doesn't accidentally promote bootloader recovery above DATAPATH/REGISTRATION cheap actions |
| T-04-02-04 | D (Denial of service) | back-to-back usb_reset thrashes the modem | mitigate | Same per-modem flock as Plan 04-01 (ADR-0012); ladder backoff (Plan 04-04) adds 90 s cross-action floor; same-action backoff (Plan 04-04 re-keying gates.py) adds 300 s same-kind floor; idempotency-test (Plan 04-07 property test) verifies 2× back-to-back is identical-end-state |
| T-04-02-05 | I (Information disclosure) | OSError errno in failure_reason | accept | `failure_reason=f"usb_reset:sysfs_write_error:{exc.errno}"` exposes errno integer (EBUSY=16, EACCES=13, ENOENT=2 etc.). These are public POSIX values; no PII / secrets. Operators need this for diagnosis |
| T-04-02-06 | S (Spoofing) | usb_path collision across bench Jetsons | accept | usb_path is bus-port (e.g. "2-3.1.1") — unique per kernel-instance, not globally unique. ADR-0009 keys state files by usb_path; cross-host collision impossible (single kernel = single bus topology). |
</threat_model>

<verification>
- All Plan 04-02 task `<verify>` commands pass.
- `pytest -m "unit and not linux_only and not hil" -x` (full unit suite) exits 0.
- `pytest tests/unit/sysfs/ tests/unit/actions/ tests/unit/policy/ tests/unit/cli/ -ra` exits 0 (≥12 new tests added).
- `mypy --strict src/spark_modem/` exits 0.
- `ruff check src/spark_modem/ tests/` exits 0; `ruff format --check src/spark_modem/ tests/` exits 0.
- `bash scripts/lint_no_subprocess.sh` exits 0.
- `python tools/check_spec.py` exits 0.
- `grep -F 'IssueCategory.ENUMERATION' src/spark_modem/wire/enums.py src/spark_modem/policy/decision_table.py` returns 0 matches (PATTERNS correction #4 applied).
- Manual sanity: `python -m spark_modem.cli.main reset --action=usb_reset --modem=cdc-wdm0 --target=parent-hub` returns exit 0 and prints `target=parent-hub`; `--target=invalid` returns exit 2.
</verification>

<success_criteria>
- `src/spark_modem/sysfs/` is a new top-level package with `unbind_rebind` async helper.
- `actions/usb_reset.py` exists; calls `unbind_rebind` via `ctx.sysfs_root` + `ctx.target`; returns deferred VerifyResult.
- `IssueDetail.SIERRA_BOOTLOADER` exists in wire/enums.py.
- `decision_table` routes `(QMI, SIERRA_BOOTLOADER) → USB_RESET` (per PATTERNS correction #4).
- ActionContext gains `target: Literal["child-port", "parent-hub"] = "child-port"` field.
- CLI `reset --target` flag accepted; argparse rejects unknown values with exit 2.
- Dispatcher contract test asserts 8 registered ActionKinds (6 cheap + MODEM_RESET + USB_RESET).
- 12+ new unit tests, all green.
- SP-04 lint passes — usb_reset uses file I/O only, NO subprocess.
- recovery-spec manifest lint passes (`sierra_bootloader` mentioned in `tests/test_recovery_spec.py`).
- CLAUDE.md invariants honored: pure-engine untouched, atomic file writes (none in this plan; sysfs writes don't go through state-store), match-on-state untouched.
- Full Phase 1+2+3 regression suite stays green.
</success_criteria>

<output>
After completion, create `.planning/phases/04-destructive-actions-hil/04-02-SUMMARY.md`
documenting: files created (sysfs/__init__.py, sysfs/usb_unbind_rebind.py,
actions/usb_reset.py), files extended (dispatcher, context, enums,
decision_table, cli/reset, recovery-spec test manifest), the 12+ new tests,
the dispatcher contract delta (7 → 8), the IssueDetail count delta, and the
PATTERNS correction #4 application (no IssueCategory.ENUMERATION; reused QMI).
Note that the `--target=parent-hub` operator path is wired today; auto-promotion
of SIERRA_BOOTLOADER decision-table rows to parent-hub mode is deferred to a
future plan (see CONTEXT Deferred Ideas).
</output>
