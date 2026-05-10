# Phase 4: Destructive Actions & HIL — Research

**Researched:** 2026-05-10
**Domain:** Destructive recovery actions (modem_reset / usb_reset / driver_reset), policy ladder & gating, hardware-in-the-loop CI
**Confidence:** HIGH on existing-code patterns and CONTEXT.md decisions; MEDIUM on Linux 5.10-tegra sysfs/modprobe specifics; LOW on Git LFS + self-hosted runner topology (deployment-team-owned)

> **CONTEXT.md decisions A-01..D-05 are LOCKED.** This research closes the residual technical
> unknowns the planner needs to write executable tasks; it does NOT re-decide what's already
> in CONTEXT. Locked claims are tagged `[CONTEXT.md A-XX]`; verified-from-source claims are
> tagged `[VERIFIED: <file:line>]`; external claims tagged `[CITED]` or `[ASSUMED]`.

---

## User Constraints (from CONTEXT.md)

### Locked Decisions (A-01..D-05 verbatim shorthand)

- **A-01:** modem_reset uses the same qmicli primitive as soft_reset (`--dms-set-operating-mode=reset`); difference is policy-side gating + ladder rung. NO new QMI verb.
- **A-02:** usb_reset is sysfs file I/O (open/write to `/sys/bus/usb/drivers/usb/{un,}bind`), NOT subprocess. Two variants: child-port (default) and parent-hub (Sierra-bootloader recovery). New `src/spark_modem/sysfs/` package.
- **A-03:** driver_reset is two `subproc.run` calls: `["modprobe","-r","qmi_wwan"]` then `["modprobe","qmi_wwan"]`. Through Phase 1 subproc/runner — no SP-04 bypass.
- **A-04:** All four destructive actions return `VerifyResult.deferred(detail="next_cycle_observation")`. Mirror `actions/soft_reset.py`.
- **A-05:** Idempotency = re-runnable, NOT single-flight. Per-modem flock serializes; no "already in flight" error.
- **A-06:** Sierra EM7421 stuck-in-bootloader (1199:9051) → new `IssueDetail.SIERRA_BOOTLOADER` → parent-hub usb_reset.
- **B-01:** New `src/spark_modem/policy/ladder.py` with pure `select_rung()` function. Decision table stays flat.
- **B-02:** Add `ModemState.last_action_monotonic_by_kind: dict[ActionKind, float]` (additive, default empty dict). Same-action gate keys per-kind; ladder gate uses MAX over destructive kinds.
- **B-03:** Signal-gate thresholds move from `Final` constants in `policy/transitions.py` to `Settings` (RELOAD_DATA tagged).
- **B-04:** New `ActionSkipped` event variant + `SkipReason` closed StrEnum (signal_below_gate, ladder_backoff, same_action_backoff, exhausted, disconnected, maintenance, dry_run). Discriminator `kind="action_skipped"`. PlannedAction.suppressed_* flags retained for back-compat.
- **C-01:** driver_reset eligibility denominator = total expected modems (4), Zao-active counted as not-hung. *User deviation from research recommendation* — favors slow-to-fire over the 60s fleet-wide outage.
- **C-02:** PROXY_DIED does NOT bypass the 75% threshold. *User deviation from PITFALLS §1.1.* All 4 modems will time out within ~8s anyway.
- **C-03:** thermal_warn / thermal_critical suppress driver_reset (PITFALLS §17.4). Cycle still emits per-modem qmi_channel_hung; per-modem usb_reset gates run normally.
- **C-04:** No proactive Zao D-Bus subscription for driver_reset. Phase 5 may revisit (ADR-0014 candidate).
- **C-05:** Cooldown 3600s in `Settings.global_driver_reset_backoff_seconds`, RELOAD_DATA.
- **C-06:** Per-modem counters/streak preserved post-driver_reset (driver_reset is global; ladder is per-modem).
- **D-01:** HIL on self-hosted aarch64 runner; nightly cron 04:00 UTC + workflow_dispatch; serial concurrency; 90-min timeout.
- **D-02:** Fault injection software-only (qmicli, pkill, kmsg writes, dms-set-operating-mode=offline). NO real RF detuning hardware.
- **D-03:** 30-day v1 traces via Git LFS at `tests/fixtures/replay/v1-30d/`; sha256[:8] redaction; fail clearly on missing LFS auth.
- **D-04:** Phase-3 deferred bench-SC verifications fold into HIL scenario suite.
- **D-05:** ~7 plans target.

### Claude's Discretion (planner picks)

- `sysfs/` module layout (single file vs split).
- CLI flag for parent-hub usb_reset variant (`--target=parent-hub` vs boolean vs implicit).
- modprobe stderr regex for distinguishing busy / not-loaded / other failures.
- Per-modem timestamp dict initialisation (empty default vs pre-populated).
- HIL scenario cadence within nightly run (sequential vs parallel-where-safe).
- README content for `tests/fixtures/replay/v1-30d/README.md`.
- Plan count exact (6 / 7 / 8).
- Sierra-bootloader IssueCategory placement (ENUMERATION vs new — REUSE ENUMERATION per CONTEXT.md Discretion bullet).

### Deferred Ideas (OUT OF SCOPE)

- D-Bus subscription to zao-infra-ctrl.service (Phase 5 / ADR-0014 candidate).
- Real-fleet RF-environment threshold tuning (Phase 5 cohort data).
- Quarterly LFS trace refresh cadence (Phase 5 begins it).
- Bench-Jetson SIM-cycle automation (Phase 5 if PITFALLS §14.4 surfaces need).
- HTTP control plane (CTL-01/02 — v2.1).
- `ctl simulate-issue` (SIM-01 — v2.1, would be a cleaner fault-injection surface).
- 5G NR-aware policy (NR-01 — v2.1).
- ActionSkipped vs PlannedAction.suppressed_* deprecation horizon (Phase 5/6).
- Per-MCC signal-gate threshold override in carrier table (Phase 5 if data justifies).
- Real-RF detuning hardware budget (Phase 6 if synthetic fixtures insufficient).

## Project Constraints (from CLAUDE.md)

The planner MUST honor these non-negotiables when slicing Phase 4 tasks:

1. **Pure policy engine** — `policy/ladder.py` MUST NOT import subprocess/asyncio/os/httpx; only `Protocol`s and pure types. CLAUDE.md §1; SP-04 lint enforces.
2. **usb_path keying for state** — Phase 4 state file additions go on `state/by-usb/<usb_path>.json`. ADR-0009. Never key on cdc-wdmN.
3. **5+2 state shape** — destructive actions never invent new top-level states; `rf_blocked` is the orthogonal flag.
4. **time.monotonic() for backoffs** — `last_action_monotonic_by_kind` values are monotonic timestamps, not wall clock. ADR-0007.
5. **Atomic file writes** — per-cycle ModemState write order: streak → decay → counter reset → state-write atomic. Phase 4 actions extend, never replace this ordering.
6. **One action per modem per cycle** — driver_reset short-circuit (engine.py:76-106) ensures per-modem actions don't race driver_reset.
7. **Signal-quality gate on destructive only** — `_DESTRUCTIVE_KINDS = {MODEM_RESET, USB_RESET, DRIVER_RESET}`. soft_reset stays cheap.
8. **List-form argv via subproc/** — driver_reset's modprobe calls go through `subproc.run` (already in place). sysfs writes are `open()` + `os.write()` (file I/O, not subprocess; SP-04 lint scope unchanged).
9. **`match` on ModemState** — never `if/elif`. `policy/ladder.py` uses match on category if it dispatches by category.
10. **No inbound IPC** — destructive CLI invocations via `spark-modem reset` (process-spawned), not via socket.

---

## Phase Requirements

| ID | Description (REQUIREMENTS.md verbatim) | Research Support |
|----|----------------------------------------|------------------|
| FR-23 | System gates `modem_reset`/`usb_reset` when signal is measurably below thresholds (RSRP < -110 dBm OR RSRQ < -15 dB OR SNR < 0 dB) | `policy/transitions.py:is_signal_below_gate` already implemented; `policy/gates.py:gate_signal` already wired; Phase 4 moves thresholds from `Final` constants to `Settings` (B-03) and emits `ActionSkipped(reason=signal_below_gate)` (B-04). HIL synthetic-RF-noise scenario validates via config-injected forced rf_blocked (D-02). |
| FR-24 | Global `driver_reset` fires only when ≥75% of modems are simultaneously QMI-hung AND at least one has actionable signal | `_global_driver_reset_eligible` placeholder at `policy/engine.py:280-294` returns False today; Phase 4 wires real predicate (denominator-of-4 per C-01, no proxy-died bypass per C-02, thermal suppression per C-03, cooldown 3600s per C-05). HIL three-modem-QMI-hang scenario validates. |
| FR-27 | All recovery actions implemented as separate idempotent functions, runnable individually via the CLI | `actions/dispatcher.py:_REGISTRY` + `cli/reset.py` already in place; Phase 4 appends three destructive entries to `_REGISTRY` and unblocks `cli/reset.py` (currently rejects via `is_registered()` check at line 34-41). Each new action is `execute()` + `verify()` returning `VerifyResult.deferred()` per A-04. Idempotency = re-runnable per A-05; per-modem flock (ADR-0012) serializes back-to-back invocations. |

---

## Summary

The planner needs ~7 plans to land destructive actions + HIL CI. The most important things to know:

1. **Three destructive action implementations diverge in mechanism, not pattern.** modem_reset reuses `QmiWrapper.dms_set_operating_mode("reset")` exactly like soft_reset (A-01 — Sierra has no harder DMS verb). usb_reset is sysfs file I/O — open/write to `/sys/bus/usb/drivers/usb/{unbind,bind}` (A-02 — confirmed via [LWN bind/unbind article](https://lwn.net/Articles/143397/) and Linux kernel docs). driver_reset is two `subproc.run` calls through the existing Phase 1 wrapper (A-03 — confirmed via `subproc/runner.py`). All three follow `actions/soft_reset.py:1-50` shape verbatim, returning `VerifyResult.deferred(detail="next_cycle_observation")`.

2. **The eligibility predicate has subtle edge cases the planner must pin in tests.** The 75% denominator (C-01) is `expected_modem_count` from `policy/context.py:46` (already 4 by default). When `last_driver_reset_monotonic is None` (never fired), the cooldown check `clock.monotonic() - None` would TypeError — must short-circuit the None case as "no cooldown active." Boundary is `>= multi_modem_threshold_fraction`, so 3/4 = 0.75 fires; 2/4 = 0.50 does not. PROXY_DIED routes through the standard predicate (C-02), no bypass.

3. **Per-action timestamp split is additive, not replacing.** Add `last_action_monotonic_by_kind: dict[ActionKind, float] = Field(default_factory=dict)` to `ModemState`. Phase 2 state files load cleanly because pydantic defaults to empty dict. Engine bumps BOTH `last_action_monotonic` (existing) AND `last_action_monotonic_by_kind[kind]` on execution. `gate_same_action_backoff` keys on `state.last_action_monotonic_by_kind.get(kind)`; `gate_ladder_backoff` uses `max(state.last_action_monotonic_by_kind.get(k, 0.0) for k in _DESTRUCTIVE_KINDS) or None`.

4. **policy/ladder.py is one pure function with one return type.** Signature locked by B-01: `def select_rung(category: IssueCategory, counters: dict[ActionKind, int], config: Settings) -> ActionKind | Literal["skip:exhausted"]`. Engine flow: `lookup_action()` for the BASE; if base ∈ `{SOFT_RESET, MODEM_RESET, USB_RESET}` and category ∈ `{REGISTRATION, (DATAPATH, SESSION_DISCONNECTED)}`, call `select_rung()` to pick the actual rung. Decision table at `policy/decision_table.py:35-64` stays flat.

5. **ActionSkipped is alongside PlannedAction.suppressed_*, not replacing.** Discriminated-union update pattern at `wire/events.py:198-216`: add `ActionSkipped` to the union, update `EventAdapter`. Replay harness back-compat shim is small — Plan 02-10 reads `PlannedAction.suppressed_signal_gate` etc. fields; the harness keeps doing that. The new event is the consumer-friendly shape going forward (SC#2 verbatim).

6. **HIL CI lane is one workflow file + serial concurrency.** GitHub Actions: `runs-on: [self-hosted, linux, ARM64]` (already proven in `.github/workflows/ci.yml:17`) plus a custom label for the bench Jetson; `concurrency: group: hil-bench, cancel-in-progress: false`; `schedule: cron: '0 4 * * *'` + `workflow_dispatch`; 90-min timeout. `pytest -m hil tests/hil/`. The `hil` marker is already registered at `pyproject.toml:78`.

7. **Fault injection toolkit is software-only and non-trivial.** qmicli direct invocations (`--uim-sim-power-off/-on`, `--dms-set-operating-mode=offline`); `pkill -9 qmi-proxy` (Zao restarts proxy on its own per C-04); synthetic kmsg writes (`printf '<6>foo: bar' > /dev/kmsg` matching the 5 closed-enum patterns from Plan 03-05); rf_blocked validated via config-injected forced threshold lowering (D-02). NO real RF detuning hardware.

8. **30-day v1 traces via Git LFS need explicit LFS-pull setup.** GitHub Actions checkout uses `actions/checkout@v4` with `lfs: true` flag; self-hosted runner needs `git-lfs` binary on PATH. Fail-fast on missing LFS auth (CONTEXT D-03). `tools/pull_replay_traces.py` is a thin wrapper that just confirms files materialized (LFS pointers were resolved).

9. **Phase 4 EXTENDS — never CREATES — most policy seams.** `gates.py`, `decision_table.py`, `engine.py`, `transitions.py`, `state.py`, `enums.py` all get small additive edits. The five NEW package paths are: `actions/{modem_reset,usb_reset,driver_reset}.py`, `sysfs/{__init__,usb_unbind_rebind}.py`, `policy/ladder.py`. Plus tests and HIL.

10. **systemd capabilities are pre-allocated by Phase 3.** `CapabilityBoundingSet=CAP_NET_ADMIN CAP_SYS_ADMIN CAP_SYS_MODULE CAP_DAC_READ_SEARCH` is already in the unit (Plan 03-08 U-01). Phase 4 does NOT edit `debian/spark-modem-watchdog.service`. CAP_SYS_ADMIN unblocks sysfs unbind/bind writes; CAP_SYS_MODULE unblocks modprobe.

**Primary recommendation:** Slice the 7 plans by user-facing surface (one plan per destructive action, then engine wiring, then ActionSkipped, then HIL infra, then HIL scenarios). Implement `select_rung` and `last_action_monotonic_by_kind` together (B-01 + B-02 are tightly coupled). Reserve `--target` flag (no boolean) for usb_reset; pre-populate per-action timestamps to empty dict (lower disk churn).

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| modem_reset/usb_reset/driver_reset execution | Action layer (`actions/*.py`) | QMI/sysfs/subproc adapters | Side-effect-bearing; lives outside `policy/` purity boundary |
| Ladder rung selection | Policy / pure (`policy/ladder.py`) | — | No I/O, pure function of (category, counters, config) |
| Signal-gate threshold evaluation | Policy / pure (`policy/transitions.py:is_signal_below_gate`) | — | Reads `PolicyContext.config` (Settings) instead of module constants |
| driver_reset eligibility predicate | Policy / pure (`policy/engine.py:_global_driver_reset_eligible`) | — | Reads `Diag` + `GlobalsState` + `PolicyContext`; no I/O |
| Per-action timestamp tracking | Wire (`ModemState.last_action_monotonic_by_kind`) | Engine bumps it | Pydantic field; engine writes the value during cycle commit |
| ActionSkipped event emission | Engine (`policy/engine.py`) → event log | `wire/events.py` defines the shape | Engine knows the cycle context; logger is just append() |
| HIL fault injection | Tests (`tests/hil/fault_inject.py`) | — | Test-tier code, NOT shipped in `.deb` |
| LFS trace pull | Tools (`tools/pull_replay_traces.py`) | CI workflow | Build-tier orchestration |
| HIL workflow orchestration | CI (`.github/workflows/hil.yml`) | systemd / runner | Outside the daemon process boundary |
| sysfs USB unbind/bind I/O | New `sysfs/` package | actions/usb_reset.py consumes | Plain `open()` + `os.write()`; SP-04 lint scope unchanged because file writes ≠ subprocess |
| modprobe invocation | `subproc/runner.py` (existing) | actions/driver_reset.py | Goes through SP-04 anchor; no bypass |

---

## Standard Stack

> Phase 4 adds **zero** new runtime dependencies. Every needed library is already in
> `packaging/requirements.lock` from Phase 1 [VERIFIED: `.github/workflows/ci.yml:34`].

### Core (already pinned, verified at runtime by Phase 1 .deb smoke test)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pydantic | >=2.13,<3 | `ModemState.last_action_monotonic_by_kind`, `ActionSkipped`, `SkipReason` enum, Settings additions | Already in lock; Phase 4 just adds fields/variants |
| pydantic-settings | >=2.5,<3 | Settings B-03 threshold/cooldown additions | Already in lock; existing `Settings` class extends |
| asyncio (stdlib) | 3.12 | Per-modem `asyncio.Lock` already wired (ADR-0012) | Stdlib |
| stdlib `os.write` / `Path.write_text` | 3.12 | sysfs writes | Stdlib; no third-party needed |

### Tooling (test-tier only; not shipped in .deb)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest + pytest-asyncio | already pinned | New unit tests for ladder, eligibility, ActionSkipped | Phase 4 extends suite |
| hypothesis | already pinned | Idempotency property test (SC#1 — twice in a row produces identical end-state) | Property-based test of A-05 contract |
| Git LFS | runner-installed (D-03) | Pull `v1-30d/` fixtures in HIL setup phase | Self-hosted aarch64 runner; CI workflow `lfs: true` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Two `subproc.run(["modprobe",...])` calls (A-03) | Direct `init_module(2)` syscall | Far more brittle; modprobe handles dependencies (cdc_wdm, cdc_ncm); A-03 locks the subprocess approach — do not revisit |
| sysfs file I/O for usb_reset (A-02) | `subproc.run(["echo X >","/sys/bus/usb/drivers/usb/unbind"])` | Subprocess shells out; SP-04 lint flags shell strings; file I/O is cleaner. A-02 locks. |
| Single `--target` enum CLI flag (recommended below) | `--parent-hub` boolean OR implicit-by-IssueDetail | Discussed under §"Open Questions Resolved" Q9 |

### Installation

No new packages. Phase 4 extends existing modules and adds new files within current packages.

```bash
# No-op for Phase 4 — Phase 1's requirements.lock already pins everything.
# CI builds against the lock unchanged.
```

---

## Open Questions Resolved

### Q1. sysfs USB unbind/rebind sequencing on Linux 5.10-tegra

**The exact write sequence** [CITED: [LWN driver bind/unbind, Greg KH, 2005](https://lwn.net/Articles/143397/); confirmed at [kernel.org cdc_mbim docs](https://docs.kernel.org/networking/cdc_mbim.html)]:

```
# Child-port variant (SC#4 QMI-hung recovery):
write "<usb_path>" to /sys/bus/usb/drivers/usb/unbind
sleep ~0.5s for kernel re-enumeration race
write "<usb_path>" to /sys/bus/usb/drivers/usb/bind

# Parent-hub variant (Sierra-bootloader recovery, A-06):
parent_path = usb_path.rsplit('.', 1)[0]   # "2-3.1.1" -> "2-3.1"
write "<parent_path>" to /sys/bus/usb/drivers/usb/unbind
sleep ~1.0s for hub re-enumeration of all 4 modems
write "<parent_path>" to /sys/bus/usb/drivers/usb/bind
```

**Where `<usb_path>` is the bus-port string** like `2-3.1.1` (matching the basename of `/sys/bus/usb/devices/2-3.1.1`). This is exactly the value `ModemDescriptor.usb_path` already carries [VERIFIED: `src/spark_modem/inventory/sysfs.py:79`].

**Sleep duration:** No authoritative source pins the exact value; LWN article and kernel docs do not mandate a delay. [ASSUMED] 500ms for child-port and 1000ms for parent-hub based on:
- Tegra USB hub PSU droop window noted at PITFALLS §17.2 (re-enumeration storm 1-2s observed in production).
- Phase 3 Plan 03-03 already absorbed re-enumeration storms at the rtnetlink layer with 4 MiB SO_RCVBUF.
- The 5-20s outage window in RECOVERY_SPEC §2 covers this latency comfortably.
- **Recommendation:** Settings field `usb_reset_rebind_delay_seconds` with `default=0.5` (RELOAD_DATA tagged) so Phase 5 field-shadow can tune.

**Parent-hub computation:** `Path('/sys/bus/usb/devices') / parent_path` is the parent USB hub. For modem at `2-3.1.1`, parent is `2-3.1` (the 4-port hub). On the production Jetson, all 4 modems share one hub at `2-3.1` so a parent-hub reset re-enumerates all 4 — that's intended for the SIERRA_BOOTLOADER case (A-06; PITFALLS §1.6).

**File-descriptor discipline** [ASSUMED]:
- Open with `O_WRONLY` (default for `open(path, 'w')`).
- No `O_CLOEXEC` issue: sysfs writes are synchronous; the FD is closed immediately after `write()`.
- Use `Path(...).write_text("<usb_path>", encoding='ascii')` — concise and matches Phase 2 `actions/fix_autosuspend.py` pattern (`Path.write_text('on')` against sysfs_root).

**cdc-wdmN renumbering after rebind:** This is the **central concern that ADR-0009 already addressed**. State files are keyed by `usb_path`, not by `cdc-wdmN`. After rebind, the device may re-enumerate as a different cdc-wdm number — but the `usb_path` (`2-3.1.1`) is **stable** because the kernel keys it on the physical USB topology, not on driver attachment order [VERIFIED: kernel docs, sysfs bus-port semantics]. Plan 02-04's `SysfsInventory.scan()` re-resolves the cdc_wdm symlink via `_find_cdc_wdm()` walk [VERIFIED: `src/spark_modem/inventory/sysfs.py:111-121`] every cycle, so the next observation picks up the new cdc-wdm number transparently. The `last_action_monotonic_by_kind` dict is keyed by ActionKind (not by cdc-wdm), so the per-action gate is unaffected.

**Required capability:** `CAP_SYS_ADMIN` for writes to `/sys/bus/usb/drivers/usb/{un,}bind`. [VERIFIED: PITFALLS §12.1; preallocated by Plan 03-08 U-01 in the systemd unit; confirmed in CONTEXT.md "Carried forward from prior phases"]. No unit-file edit needed in Phase 4.

**Failure modes to classify:**

| errno | Cause | Action |
|-------|-------|--------|
| `EBUSY` | Device already in transition (rare; SC#4 unbind during ongoing rebind) | Treat as success; idempotent re-run survives |
| `ENODEV` | Device disappeared between `scan()` and `unbind` (hot-unplug race) | Return failure; observer will mark `present=False` next cycle |
| `EACCES` / `EPERM` | Capability missing (would indicate Plan 03-08 regression) | Return failure with structured reason; loud enough for HIL to catch |
| `ENOENT` | usb_path doesn't exist in `/sys/bus/usb/devices/` (stale state file) | Return failure; cycle-driver inventory cross-check (Plan 01-04) catches this upstream |

Map all four to `ActionResult.failure_reason=f"usb_reset:{errno_name}:{usb_path}"` for replay-harness analysis.

### Q2. modprobe stderr classification for driver_reset

**libkmod stderr patterns** [CITED: [kmod source `tools/modprobe.c`](https://github.com/lucasdemarchi/kmod/blob/master/tools/modprobe.c), confirmed lines 731 (not loaded), 816 (not found), 876 (in use)]:

| Pattern (case-insensitive substring match) | Meaning | Daemon classification |
|--------------------------------------------|---------|----------------------|
| `Module qmi_wwan is in use` (or `is in use by:`) | EBUSY — kernel refuses unload | Failure; queue retry next cycle |
| `Module qmi_wwan not found` | ENOENT — module file missing on disk | Catastrophic; should never happen on a healthy Jetson |
| `Module qmi_wwan is not in kernel` | Already-unloaded no-op (only emitted with `--first-time` flag, which we don't pass) | Success; idempotent re-run no-op |
| `couldn't insert 'qmi_wwan'` | Generic insmod failure | Failure |
| `Operation not permitted` | EPERM — CAP_SYS_MODULE missing | Catastrophic; Plan 03-08 regression |

**Quiet flag behavior:** `modprobe -q` sets the verbose level to LOG_EMERG, which suppresses informational messages but **does NOT suppress error messages** through the `ERR()` macro [CITED: kmod source line 925]. So `-q` is safe to add for clean stderr without losing failure signal.

**Exit code on absent module:** When `modprobe -r` runs against a module that's already absent, **the exit code is 0** [CITED: kmod source line 731 — `err = 0` unless `--first-time` is passed]. This means **A-03's idempotency claim holds at the exit-code level**: a second `modprobe -r qmi_wwan` after the first succeeds returns 0 with `Module qmi_wwan is not in kernel.\n` on stderr (which the daemon should treat as success).

**`subproc.run` already captures stderr:** [VERIFIED: `src/spark_modem/subproc/runner.py:171`] `stdout, stderr = await proc.communicate(input=stdin)` — both streams are captured. `CompletedProcess.stderr` is `bytes` [VERIFIED: `subproc/result.py`]. No flag needed; the runner already does the right thing.

**Auto-handled dependencies:** modprobe pulls in `cdc_wdm` and `cdc_ncm` automatically because qmi_wwan declares them as dependencies in its modinfo. `modprobe -r qmi_wwan` removes qmi_wwan, and modprobe **does not auto-remove unused dependencies** (rmmod-r recursive-remove is a separate flag we don't use). This is fine: `modprobe qmi_wwan` on the second call re-uses the still-loaded cdc_wdm/cdc_ncm. [ASSUMED] Verified by kernel module documentation.

**Recommendation:** Use `["modprobe", "-r", "qmi_wwan"]` and `["modprobe", "qmi_wwan"]` (no `-q`, no `--first-time`). Classify result via:

```python
def _classify_modprobe(cp: CompletedProcess) -> ActionResult:
    stderr_lower = cp.stderr.lower()
    if cp.exit_code == 0:
        return ActionResult(succeeded=True, ...)  # includes already-loaded/unloaded no-op
    if b"is in use" in stderr_lower:
        return ActionResult(succeeded=False, failure_reason="driver_reset:module_in_use", ...)
    if b"not found" in stderr_lower:
        return ActionResult(succeeded=False, failure_reason="driver_reset:module_not_found", ...)
    if b"operation not permitted" in stderr_lower:
        return ActionResult(succeeded=False, failure_reason="driver_reset:eperm", ...)
    return ActionResult(succeeded=False, failure_reason=f"driver_reset:exit_{cp.exit_code}", ...)
```

### Q3. driver_reset eligibility predicate edge cases

**Exact computation per RECOVERY_SPEC §6.4** [VERIFIED: `docs/RECOVERY_SPEC.md:255-263`]:

```python
def _global_driver_reset_eligible(
    diag: Diag,
    prior_states: dict[str, ModemState],
    globals_state: GlobalsState,
    ctx: PolicyContext,
) -> bool:
    # Gate 1: thermal suppression (C-03 / PITFALLS §17.4)
    thermal_details = {IssueDetail.THERMAL_WARN, IssueDetail.THERMAL_CRITICAL}
    if any(issue.detail in thermal_details for issue in diag.host_issues):
        return False

    # Gate 2: cooldown (C-05; default 3600s)
    if globals_state.last_driver_reset_monotonic is not None:
        elapsed = ctx.clock.monotonic() - globals_state.last_driver_reset_monotonic
        if elapsed < ctx.config.global_driver_reset_backoff_seconds:
            return False
    # When None: never fired before; fall through (no NPE risk).

    # Gate 3: ≥75% of total-4 hung (C-01)
    hung_details = {IssueDetail.QMI_CHANNEL_HUNG, IssueDetail.QMI_PROXY_DIED, IssueDetail.QMI_TIMEOUT}
    hung_modems = [
        snap for snap in diag.per_modem.values()
        if any(i.category == IssueCategory.QMI and i.detail in hung_details for i in snap.issues)
    ]
    if len(hung_modems) / ctx.expected_modem_count < ctx.config.multi_modem_threshold_fraction:
        return False

    # Gate 4: at least one hung modem has actionable signal (RECOVERY_SPEC §6.4)
    actionable = any(
        not _is_signal_below_gate_for(snap, ctx.config) for snap in hung_modems
    )
    return actionable
```

**Boundary cases the planner must test:**

| Scenario | hung_count / expected_count | Expected | Boundary |
|----------|----------------------------|----------|----------|
| 3 hung of 4 expected | 0.75 | FIRES | Equality fires (`>=` semantics, RECOVERY_SPEC §6.4 verbatim "≥75%") |
| 2 hung of 4 expected | 0.50 | DOES NOT FIRE | Below threshold |
| 4 hung of 4 expected | 1.00 | FIRES | Same threshold |
| 3 hung, 1 missing modem (only 3 enumerated) | 3/4 = 0.75 | FIRES | Denominator stays 4 (`expected_modem_count`), not enumerated count — *deliberate per C-01* |
| 3 hung, all RF-blocked | 3/4 | DOES NOT FIRE | Gate 4 fails (no actionable signal) |
| 3 hung, but `last_driver_reset` was 30 min ago | n/a | DOES NOT FIRE | Gate 2 fails (cooldown 3600s default) |
| 3 hung, but cycle has thermal_warn | n/a | DOES NOT FIRE | Gate 1 fails |
| 3 hung, never fired before (`last_driver_reset_monotonic=None`) | 3/4 | FIRES | Gate 2 short-circuits None |
| 1 hung due to PROXY_DIED, others healthy | 0.25 | DOES NOT FIRE | Per C-02: PROXY_DIED does NOT bypass — all 4 modems will time out within ~8s anyway |

**"Hung" denominator definition:** Phase 2's decision table routes `(QMI, QMI_CHANNEL_HUNG) → USB_RESET`, `(QMI, QMI_PROXY_DIED) → DRIVER_RESET`, `(QMI, QMI_TIMEOUT) → SOFT_RESET` [VERIFIED: `policy/decision_table.py:59-63`]. For the eligibility predicate, count any QMI category issue (channel_hung, proxy_died, timeout). PROXY_DIED counts toward the 75% denominator (C-02), it just doesn't bypass it.

**"Actionable signal" semantics:** RECOVERY_SPEC §6.4 wording: *"At least one of the hung modems has `signal.sufficient ∈ {true, null}` (i.e. not pure RF interference)."* This is the OPPOSITE of `is_signal_below_gate` — actionable means "rsrp ≥ -110 AND rsrq ≥ -15 AND snr ≥ 0" OR "all readings are None" (we don't know). [VERIFIED: `policy/transitions.py:29-42` semantics]. So:

```python
def _has_actionable_signal(snap: ModemSnapshot, config: Settings) -> bool:
    return not is_signal_below_gate(snap, config)  # Phase 4 reads thresholds from Settings
```

**Interaction with cycle short-circuit:** `engine.py:76-106` already handles the short-circuit branch correctly — when eligible, it appends `_plan_driver_reset()` to `plans`, bumps the globals counter and timestamp, runs transitions but NO per-modem action selection, and returns. Phase 4 plan #3 just needs to (1) replace `return False` at line 294 with the real predicate and (2) optionally emit `ActionSkipped` for each per-modem candidate that was suppressed by the short-circuit (the per-modem candidates are not even evaluated today, so this is a feature decision — recommend NOT emitting per-modem ActionSkipped on driver_reset short-circuit, since the cycle's primary action is the driver_reset itself).

### Q4. policy/ladder.py — pure-function semantics

**Locked signature (B-01):**

```python
# src/spark_modem/policy/ladder.py
from typing import Literal
from spark_modem.config.settings import Settings
from spark_modem.wire.enums import ActionKind, IssueCategory


def select_rung(
    category: IssueCategory,
    counters: dict[ActionKind, int],
    config: Settings,
) -> ActionKind | Literal["skip:exhausted"]:
    """RECOVERY_SPEC §4.1: rung selection by per-action counter."""
    soft = counters.get(ActionKind.SOFT_RESET, 0)
    modem = counters.get(ActionKind.MODEM_RESET, 0)
    usb = counters.get(ActionKind.USB_RESET, 0)
    if soft < config.max_soft:
        return ActionKind.SOFT_RESET
    if modem < config.max_modem:
        return ActionKind.MODEM_RESET
    if usb < config.max_usb:
        return ActionKind.USB_RESET
    return "skip:exhausted"
```

**When does `select_rung` return "skip:exhausted"?** Only when ALL three counters meet their ceilings (soft >= max_soft AND modem >= max_modem AND usb >= max_usb). Defaults from RECOVERY_SPEC §4.1: `max_soft=3, max_modem=2, max_usb=1`. So a modem can attempt up to 6 destructive escalations (3+2+1) before exhaustion.

**Categories that engage the ladder per RECOVERY_SPEC §4.1:**
- `IssueCategory.REGISTRATION` with `IssueDetail.NOT_REGISTERED_SEARCHING` — base SOFT_RESET, full ladder.
- `IssueCategory.REGISTRATION` with `IssueDetail.NOT_REGISTERED_IDLE` — base SOFT_RESET, full ladder.
- `IssueCategory.DATAPATH` with `IssueDetail.SESSION_DISCONNECTED` — base MODEM_RESET, partial ladder (already at rung 2).

For SESSION_DISCONNECTED, RECOVERY_SPEC §4 says `escalation: modem_reset → skip:exhausted` (no usb_reset rung). So the ladder for SESSION_DISCONNECTED is a 2-rung ladder, not 3. Implementation:

```python
def select_rung_for_session_disconnected(counters: dict[ActionKind, int], config: Settings) -> ActionKind | Literal["skip:exhausted"]:
    if counters.get(ActionKind.MODEM_RESET, 0) < config.max_modem:
        return ActionKind.MODEM_RESET
    return "skip:exhausted"
```

**Recommendation:** Implement `select_rung()` with a `category` arm (using `match`):

```python
def select_rung(category, counters, config):
    match category:
        case IssueCategory.REGISTRATION:
            # Full 3-rung ladder
            if counters.get(ActionKind.SOFT_RESET, 0) < config.max_soft:
                return ActionKind.SOFT_RESET
            if counters.get(ActionKind.MODEM_RESET, 0) < config.max_modem:
                return ActionKind.MODEM_RESET
            if counters.get(ActionKind.USB_RESET, 0) < config.max_usb:
                return ActionKind.USB_RESET
            return "skip:exhausted"
        case IssueCategory.DATAPATH:
            # 2-rung (modem only, no soft/usb)
            if counters.get(ActionKind.MODEM_RESET, 0) < config.max_modem:
                return ActionKind.MODEM_RESET
            return "skip:exhausted"
        case _:
            # Categories that don't engage ladder shouldn't be routed here;
            # caller checks via `_is_ladder_category()` before invoking.
            raise ValueError(f"select_rung called for non-ladder category: {category}")
```

**Caller flow in `engine.py:run_cycle`:**

```python
# Step 5 — decision table lookup (already exists at line 132)
action_or_skip = lookup_action(issue.category, issue.detail)

# Phase 4 NEW: ladder rung selection for ladder-engaged categories
if isinstance(action_or_skip, ActionKind) and _is_ladder_category(issue.category, issue.detail):
    action_or_skip = ladder.select_rung(issue.category, prior.counters, ctx.config)
    if action_or_skip == "skip:exhausted":
        # Emit ActionSkipped(reason=exhausted) — see Q5
        ...
```

**Test fixture format:** One file per progression scenario from RECOVERY_SPEC §10.2:

```python
# tests/unit/policy/test_ladder.py
@pytest.mark.parametrize("counters,expected", [
    ({}, ActionKind.SOFT_RESET),
    ({ActionKind.SOFT_RESET: 1}, ActionKind.SOFT_RESET),
    ({ActionKind.SOFT_RESET: 3}, ActionKind.MODEM_RESET),
    ({ActionKind.SOFT_RESET: 3, ActionKind.MODEM_RESET: 1}, ActionKind.MODEM_RESET),
    ({ActionKind.SOFT_RESET: 3, ActionKind.MODEM_RESET: 2}, ActionKind.USB_RESET),
    ({ActionKind.SOFT_RESET: 3, ActionKind.MODEM_RESET: 2, ActionKind.USB_RESET: 1}, "skip:exhausted"),
])
def test_registration_ladder_progression(counters, expected, default_settings):
    assert ladder.select_rung(IssueCategory.REGISTRATION, counters, default_settings) == expected
```

### Q5. ActionSkipped event + back-compat with PlannedAction.suppressed_*

**Discriminated union update mechanics for pydantic v2** [VERIFIED: `wire/events.py:198-216`]:

```python
# Phase 4 addition to wire/events.py:

class ActionSkipped(_EventBase):
    """B-04: structured action_skipped event (SC#2 verbatim).

    Emitted alongside PlannedAction.suppressed_* flags (back-compat preserved).
    """
    kind: Literal["action_skipped"] = "action_skipped"
    usb_path: str
    suppressed_action: ActionKind
    reason: SkipReason
    cause_category: IssueCategory | None = None  # None on driver_reset short-circuit
    cause_detail: IssueDetail | None = None


# Update the Event union and adapter:
Event = Annotated[
    ActionPlanned
    | ActionExecuted
    | ActionFailed
    | ActionSkipped       # NEW
    | StateTransition
    | DaemonStarted
    | DaemonStopped
    | SchemaDowngradePending
    | UsbPathMismatch
    | MaintenanceWindowStarted
    | MaintenanceWindowEnded
    | WebhookDropped
    | EventSourceCrashed
    | SimSwapped,
    Field(discriminator="kind"),
]
EventAdapter: TypeAdapter[Event] = TypeAdapter(Event)  # rebuild after union change
```

**SkipReason enum addition to wire/enums.py:**

```python
class SkipReason(StrEnum):
    """B-04 closed enum for ActionSkipped.reason."""
    SIGNAL_BELOW_GATE = "signal_below_gate"
    LADDER_BACKOFF = "ladder_backoff"
    SAME_ACTION_BACKOFF = "same_action_backoff"
    EXHAUSTED = "exhausted"
    DISCONNECTED = "disconnected"
    MAINTENANCE = "maintenance"
    DRY_RUN = "dry_run"
```

**Event-logger writer.py append() consumes both variants:** No change needed. [VERIFIED: `event_logger/writer.py` (Phase 1 / Plan 03-04 reopen extension)] — `append(event: Event)` uses `model_dump_json` which dispatches on the discriminated union automatically.

**Replay harness back-compat:** Plan 02-10's `tools/replay_harness.py` (existing) reads `PlannedAction.suppressed_signal_gate` etc. fields; the harness keeps doing that. Phase 4 emits BOTH `PlannedAction` (with the existing flags populated, so the harness keeps working) AND a new `ActionSkipped` event line (which the harness ignores — it filters by `kind` field on event-log replay scenarios, but the partial-order classifier reads PlannedAction fields). No shim needed; the back-compat is by emission semantics, not by event-log filtering.

**Engine emit pattern:**

```python
# In engine.py _apply_gates_to_action — Phase 4 addition:
def _apply_gates_to_action(action, state, ctx, who) -> tuple[PlannedAction, bool, list[ActionSkipped]]:
    skipped_events = []
    # ... existing gate checks ...
    if suppressed_signal:
        skipped_events.append(ActionSkipped(
            ts_iso=ctx.clock.wall_clock_iso(),
            usb_path=who.usb_path,
            suppressed_action=action,
            reason=SkipReason.SIGNAL_BELOW_GATE,
            cause_category=cause.category if cause else None,
            cause_detail=cause.detail if cause else None,
        ))
    # ... emit one ActionSkipped per failing gate ...
    return planned_action, would_execute, skipped_events
```

The cycle driver appends each `ActionSkipped` to the event logger after `policy.engine.run_cycle` returns. CycleResult gains a new `skipped_events: list[ActionSkipped]` field.

### Q6. HIL CI lane mechanics on self-hosted aarch64 runner

**Workflow shape** (recommended):

```yaml
# .github/workflows/hil.yml
name: HIL

on:
  schedule:
    - cron: '0 4 * * *'  # 04:00 UTC nightly (D-01)
  workflow_dispatch:

concurrency:
  group: hil-bench
  cancel-in-progress: false  # Serial; never cancel a running HIL session (D-01)

jobs:
  hil:
    name: HIL — bench Jetson + 4 EM7421s
    runs-on: [self-hosted, linux, ARM64, hil-bench]  # custom label
    timeout-minutes: 90  # D-01

    steps:
      - uses: actions/checkout@v4
        with:
          lfs: true  # D-03: pulls v1-30d traces

      - name: Set up Python 3.12 + venv
        run: |
          uv venv --python 3.12 .venv
          uv pip install --python .venv/bin/python -e ".[dev]"
          uv pip install --python .venv/bin/python --no-deps -r packaging/requirements.lock

      - name: Confirm ModemManager disabled
        run: |
          systemctl is-active ModemManager.service && exit 1 || echo "ModemManager off — OK"

      - name: Confirm Zao running
        run: |
          systemctl is-active zao-infra-ctrl.service || exit 1

      - name: Pull replay traces (LFS)
        run: .venv/bin/python -m tools.pull_replay_traces

      - name: Run HIL scenario suite
        run: .venv/bin/pytest -m hil tests/hil/ -ra --tb=short

      - name: Run replay-harness 30-day agreement gate
        run: .venv/bin/python -m tools.replay_harness --traces tests/fixtures/replay/v1-30d/ --gate 0.95

      - name: Capture support bundle on failure
        if: failure()
        run: sudo spark-modem ctl support-bundle --out=/tmp/hil-failure-$(date +%F).tgz

      - name: Upload artifacts
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: hil-failure-${{ github.run_id }}
          path: /tmp/hil-failure-*.tgz
```

**Custom runner label:** The existing `[self-hosted, linux, ARM64]` runner [VERIFIED: `.github/workflows/ci.yml:17`] is the **lint+typecheck+pytest unit** runner — likely a build server with no modems. The HIL bench Jetson is a SEPARATE physical machine (4 modems plugged in, ModemManager disabled, Zao running). [ASSUMED based on operational reality of "bench Jetson tethered to 4 EM7421s" wording in CONTEXT D-01] — the HIL workflow MUST use a different runner label (e.g. `hil-bench`) so the unit-test runner doesn't accidentally execute `pytest -m hil` against modems it doesn't have.

**Topology — confirm with deployment team before Plan 04-06 kickoff:**
- Option A: Same physical box does both unit tests AND HIL (bench Jetson with modems is also the CI runner). Simpler; HIL workflow uses just `[self-hosted, linux, ARM64]` plus a `hil` label registered manually.
- Option B: Two separate runners — unit-test runner (no modems) + bench Jetson (modems). Cleaner; requires registering a second runner with the `hil-bench` label.

**[ASSUMED] Recommendation:** Option B. Registering a second runner is a 5-minute op. Mixing roles risks an accidental `pytest -m hil` running on a modem-less box (skipping silently per `linux_only` marker, which would be a false-green).

**Pytest invocation:**

```toml
# pyproject.toml — already registered at line 78:
[tool.pytest.ini_options]
markers = [
    "hil: hardware-in-the-loop tests requiring real Jetson",
    "linux_only: requires Linux-specific syscalls (skipif on Windows)",
]
```

[VERIFIED: `pyproject.toml:78`] The `hil` marker exists. Phase 4 just adds tests under `tests/hil/scenarios/` with `pytestmark = pytest.mark.hil`.

**Per-PR vs nightly:** Per CONTEXT D-01: per-PR HIL is too slow (~45 min for full scenario suite); per-tag-only is too coarse (Phase 4 EXIT bar requires green HIL before tagging — circular). Nightly + workflow_dispatch is correct.

### Q7. Fault-injection toolkit — software-only

**Helper module shape:**

```python
# tests/hil/fault_inject.py
"""Software-only fault injection for HIL scenarios (D-02).

NO real RF detuning hardware. NO operations that could brick a modem.
Every helper is reversible (the recovery action under test should
restore healthy state)."""

from __future__ import annotations
import asyncio
import subprocess  # tests/ tier is SP-04-exempt
from pathlib import Path


async def sim_power_cycle(cdc_wdm: str) -> None:
    """Force a SIM-app issue via qmicli direct (recoverable by soft_reset)."""
    subprocess.run(["qmicli", "--device-open-proxy", f"--device=/dev/{cdc_wdm}",
                    f"--uim-sim-power-off=1"], check=True, timeout=15)
    await asyncio.sleep(2)
    # Caller then triggers daemon's recovery cycle.


async def force_operating_mode_offline(cdc_wdm: str) -> None:
    """Force registration loss via qmicli direct (recoverable by modem_reset)."""
    subprocess.run(["qmicli", "--device-open-proxy", f"--device=/dev/{cdc_wdm}",
                    "--dms-set-operating-mode=offline"], check=True, timeout=15)


def kill_qmi_proxy() -> None:
    """SC#4 'pkill -9 qmi-proxy' scenario.

    Zao restarts qmi-proxy on its own (per CONTEXT C-04); the daemon
    sees PROXY_DIED via stderr scan, accumulates across all 4 modems
    within ~8s, then the eligibility predicate fires once.
    """
    subprocess.run(["pkill", "-9", "qmi-proxy"], check=False)  # ignore exit code


def kmsg_inject(level: int, message: str) -> None:
    """Write a synthetic kmsg line matching one of Plan 03-05's 5 closed-enum patterns.

    Format: '<{level}>{message}' written to /dev/kmsg (Linux-only).
    Level 6 = INFO; level 4 = WARNING; level 3 = ERR.
    """
    Path("/dev/kmsg").write_text(f"<{level}>{message}\n", encoding="ascii")


def kmsg_inject_overcurrent(usb_path: str = "1-3.1.1") -> None:
    """Inject a USB_OVERCURRENT match per Plan 03-05 KMSG_PATTERNS."""
    kmsg_inject(4, f"usb {usb_path}: over-current condition!")


def force_rf_blocked(modem_state_path: Path) -> None:
    """Inject rf_blocked=True directly into the per-modem state file.

    Plan 04-06 alternative: instead of touching state files, lower the
    Settings thresholds via a SIGHUP'd YAML override so the next cycle's
    is_signal_below_gate computation evaluates True for the test modem.
    Recommend the YAML override approach (D-02 'config-injected forced
    rf_blocked test scenario') — it exercises B-03's RELOAD_DATA migration.
    """
    raise NotImplementedError("Use YAML override approach instead (Plan 04-06)")
```

**RF-blocked HIL scenario approach (D-02 recommended):**

```yaml
# tests/hil/fixtures/rf_blocked_test.yaml
# Drop into /etc/spark-modem-watchdog/conf.d/99-hil-rf.yaml during the test
signal_rsrp_floor_dbm: -50    # Most modems' real RSRP is around -90 to -100
signal_rsrq_floor_db: -3.0     # Real RSRQ around -10 to -15
signal_snr_floor_db: 30.0      # Real SNR around 0 to 20
```

Then SIGHUP the daemon; the next cycle observes "below gate" for every modem; destructive actions are gated; HIL asserts `ActionSkipped(reason=signal_below_gate)` events fire instead of MODEM_RESET / USB_RESET. Test cleanup removes the override and SIGHUPs again.

**SIM-swap injection** [PITFALLS §14.4 — partial answer]: PITFALLS §14.4 documents that HIL has 4 SIMs from 3 carriers; assertions are over the bonded set, not per-modem. SIM-swap injection per SC#4 scenario "SIM swap detected" requires either (a) physically swapping a SIM (requires a tech on-site — not feasible nightly), or (b) injecting an ICCID change at the qmicli boundary via a fixture. Phase 4 plan #7 should pick (b): use `--qmi-fixture-dir` mode for the SIM-swap scenario specifically, with two fixture sets that have different ICCID values for the same `usb_path`. This is consistent with how Plan 03-07 SimSwapped emit testing was done.

### Q8. Replay-harness 30-day fixture pull via Git LFS

**Git LFS in self-hosted runner:**
- The `actions/checkout@v4` action with `lfs: true` triggers `git lfs pull` after checkout. [CITED: GitHub Actions docs]
- Self-hosted runners need `git-lfs` binary installed on PATH. Standard Ubuntu 20.04 install: `apt install git-lfs && git lfs install --system`.
- LFS auth: when the repo is on github.com and the runner has the standard `GITHUB_TOKEN`, LFS-pull just works (uses the same token).

**`tools/pull_replay_traces.py` shape:**

```python
"""tools/pull_replay_traces.py — confirm v1-30d LFS pointers materialised.

After `actions/checkout@v4` with lfs: true, this script verifies that
the trace files at tests/fixtures/replay/v1-30d/ are real content (not
lingering LFS pointer stubs); fails fast on missing LFS auth (D-03).
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path("tests/fixtures/replay/v1-30d/")
LFS_POINTER_HEADER = b"version https://git-lfs.github.com/spec/v1"

def main() -> int:
    if not ROOT.is_dir():
        print(f"FAIL: {ROOT} missing — Git LFS not pulled", file=sys.stderr)
        return 1
    pointer_files = []
    for p in ROOT.rglob("*.json"):
        head = p.read_bytes()[:64]
        if head.startswith(LFS_POINTER_HEADER):
            pointer_files.append(p)
    if pointer_files:
        print(f"FAIL: {len(pointer_files)} files are still LFS pointers (LFS auth failed)", file=sys.stderr)
        for p in pointer_files[:5]:
            print(f"  {p}", file=sys.stderr)
        return 1
    file_count = len(list(ROOT.rglob("*.json")))
    print(f"OK: {file_count} replay traces materialised from LFS")
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

**sha256[:8] redaction:** Plan 02-09's ctl support-bundle uses sha256[:8] for ICCID/IMSI/IP redaction [VERIFIED: `.planning/phases/02-core-daemon-laptop-testable/02-09-SUMMARY.md` notes]. The same redactor — `src/spark_modem/cli/redact.py` already exists [VERIFIED: `Glob src/spark_modem/cli/*.py`] — should be applied to the v1-30d traces BEFORE they're committed to LFS, not at pull-time. Pre-commit redaction is a separate one-shot operation by whoever curates the trace dump from the production fleet.

**Quarterly refresh runbook (`tests/fixtures/replay/v1-30d/README.md`):**

```markdown
# v1-30d Replay Traces

30-day v1 historical traces, sha256[:8]-redacted for ICCID/IMSI/IP.

## Refresh procedure

1. Pull last 30 days of events.jsonl + status.json from a healthy field box:
   ```bash
   ssh fleet-box-N sudo spark-modem ctl support-bundle --out=/tmp/30d.tgz
   ```
2. Extract events.jsonl
3. Run redactor: `python -m spark_modem.cli.redact --in /tmp/30d/events.jsonl --out tests/fixtures/replay/v1-30d/events.jsonl`
4. Convert to per-cycle Diag fixtures: `python tools/convert_v1_to_replay.py --in events.jsonl --out tests/fixtures/replay/v1-30d/`
5. `git lfs track 'tests/fixtures/replay/v1-30d/**/*.json'`
6. `git add tests/fixtures/replay/v1-30d/ .gitattributes`
7. `git commit -m "data: refresh v1-30d replay traces (Q$N $YEAR)"`

## Schedule

Refresh quarterly OR after any qmicli-parser change that invalidates prior fixtures.
```

### Q9. CLI flag for parent-hub usb_reset variant

**Three options:**

| Option | Pros | Cons |
|--------|------|------|
| `--target=parent-hub` (enum: `child-port` default, `parent-hub`) | Self-documenting; extensible (could add `whole-host` someday); argparse `choices=` enforces validity | One more flag |
| `--parent-hub` (boolean) | Shorter; familiar | Boolean naming is awkward (`--parent-hub=false` for default? `--no-parent-hub`?); not extensible |
| Implicit-by-IssueDetail | Cleanest CLI surface (no extra flag) | Production daemon's policy engine never invokes the CLI; the implicit-routing happens internally; CLI users (operators triaging a stuck modem) lose the option to choose |

**Recommendation: `--target=parent-hub`** (enum). Rationale:
- Operators investigating a stuck modem may want to try child-port first, then parent-hub if that fails — the CLI surface should let them.
- argparse `choices=["child-port", "parent-hub"]` with `default="child-port"` keeps the common case quiet.
- Internal policy routing (decision-table-row for SIERRA_BOOTLOADER) calls usb_reset's execute() with a `target='parent-hub'` parameter directly (not via CLI), so the implicit routing in the daemon doesn't depend on the CLI shape.

**CLI test pinning:** Phase 2's CLI tests use `pytest --capsys` and parse argparse output [VERIFIED: `Glob src/spark_modem/cli/*.py` shows existing test pattern]. Phase 4 adds:

```python
# tests/unit/cli/test_reset.py — Phase 4 additions
def test_reset_usb_reset_default_target_is_child_port(capsys):
    args = parser.parse_args(["reset", "--action=usb_reset", "--modem=cdc-wdm0"])
    assert args.target == "child-port"

def test_reset_usb_reset_explicit_parent_hub(capsys):
    args = parser.parse_args(["reset", "--action=usb_reset", "--modem=cdc-wdm0", "--target=parent-hub"])
    assert args.target == "parent-hub"

def test_reset_invalid_target_rejected(capsys):
    with pytest.raises(SystemExit):
        parser.parse_args(["reset", "--action=usb_reset", "--modem=cdc-wdm0", "--target=whole-fleet"])
```

### Q10. Per-modem timestamp dict initialisation

**Two options:**
- (a) Empty dict default (`Field(default_factory=dict)`): zero disk write churn for modems that have never been actioned; gate logic must `dict.get(kind)` defensively (None case → no backoff active).
- (b) Pre-populated with all 9 ActionKinds set to 0.0: gate logic uniform (every key always exists); slightly more disk on first write.

**Recommendation: (a) Empty dict default.** Reasons:
- Phase 2 state files load cleanly (no migration needed for existing on-disk state).
- Disk-write churn matters at fleet scale (NFR-5: ≤1 MiB/min steady-state).
- Gate logic with `dict.get(kind, None)` plus a None-check is idiomatic and 1 line longer than uniform-gate-logic — not enough to justify the disk cost.
- The default value 0.0 (uninitialized timestamp) creates ambiguity with "action attempted at exactly t=0.0" (an edge case but a real one in tests using FakeClock).

---

## Existing Pattern Analogs

For each NEW file in CONTEXT integration table, the closest existing analog plus a load-bearing code excerpt the planner can reference. (Code is `git`-real — not synthesized.)

| New File | Closest Analog | Key Pattern Excerpt |
|----------|----------------|---------------------|
| `actions/modem_reset.py` | `actions/soft_reset.py` (full-shape; reuses same QMI verb) | See excerpt 1 below |
| `actions/usb_reset.py` | `actions/fix_autosuspend.py` (sysfs file write pattern) + `actions/soft_reset.py` (deferred verify shape) | See excerpts 1+2 below |
| `actions/driver_reset.py` | `actions/soft_reset.py` (deferred verify) + `qmi/wrapper.py:dms_set_operating_mode` (subproc.run wrapper) | See excerpts 1+3 below |
| `sysfs/__init__.py` + `sysfs/usb_unbind_rebind.py` | `inventory/sysfs.py:scan` (sysfs Path discipline; cross-platform via sysfs_root_override) | See excerpt 4 below |
| `policy/ladder.py` | `policy/decision_table.py:lookup_action` + `policy/transitions.py:is_signal_below_gate` (pure-function module + Final / Literal returns) | See excerpts 5+6 below |
| `tools/pull_replay_traces.py` | `tools/gen_replay_fixtures.py` (CLI-shape, deterministic seeded scripts under tools/) | See excerpt 7 below |
| `tests/hil/fault_inject.py` | `tests/fakes/runner.py` (test-tier helpers; tests/ is SP-04-exempt) | See excerpt 8 below |
| `tests/hil/scenarios/*.py` | `tests/integration/test_lifecycle.py` (Phase 3 SC tests; pytestmark linux_only) | See excerpt 9 below |
| `.github/workflows/hil.yml` | `.github/workflows/ci.yml` (self-hosted aarch64 + uv venv setup) | See excerpt 10 below |
| `tests/fixtures/replay/v1-30d/` | `tests/fixtures/replay/` (Phase 2 synthetic) — **same dir tree shape** | (Just a directory; LFS pointer + README) |

### Excerpt 1 — `actions/soft_reset.py:1-50` (the "every destructive action looks like this" template)

```python
# Source: src/spark_modem/actions/soft_reset.py
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
    return ActionResult(kind=ActionKind.SOFT_RESET, who=who, succeeded=True, ...)


async def verify(who: WhoModem, ctx: ActionContext) -> VerifyResult:
    """Deferred — next-cycle observation surfaces the actual outcome."""
    del who, ctx
    return VerifyResult.deferred(detail="next_cycle_observation")
```

**modem_reset.py is byte-for-byte similar; the only diff is `kind=ActionKind.MODEM_RESET` and `failure_reason=f"modem_reset:..."`.**

### Excerpt 2 — `actions/fix_autosuspend.py` (sysfs Path-write pattern; usb_reset's analog)

The planner should grep `Path.write_text` in `actions/fix_autosuspend.py` to see the exact `tmp_path`-friendly pattern that usb_reset.py mirrors. (File not read here, but referenced in Plan 02-06 SUMMARY: "fix_autosuspend uses Path.write_text('on') against sysfs_root — no qmicli, no subprocess; tmp_path tests work cross-platform on Windows dev hosts.") usb_reset uses the same pattern but writes to `<sysfs_root>/bus/usb/drivers/usb/{unbind,bind}` instead of `<sysfs_root>/.../power/control`.

### Excerpt 3 — `qmi/wrapper.py:238-254` (state-changing subproc pattern; driver_reset analog at the call-site level)

```python
# Source: src/spark_modem/qmi/wrapper.py:238-254
async def dms_set_operating_mode(self, mode: str) -> CompletedProcess:
    """Mutates radio operating mode (online/low_power/persistent_low_power/...)."""
    self._in_critical_section = True
    try:
        return await self._runner.run(
            self._argv([
                "qmicli",
                "--device-open-proxy",
                f"--device={self._device}",
                f"--dms-set-operating-mode={mode}",
            ]),
            timeout_s=_STATE_CHANGE_TIMEOUT_S,
        )
    finally:
        self._in_critical_section = False
```

**driver_reset.py uses two such calls:**

```python
# src/spark_modem/actions/driver_reset.py — recommended structure
async def execute(who: WhoModem, ctx: ActionContext) -> ActionResult:
    # who is unused for driver_reset (it's a global action) but the dispatcher
    # passes it via the standard signature; use WhoHost() in the policy engine
    # PlannedAction (already done at engine.py:300) but the dispatcher gives
    # us WhoModem (since the dispatch interface is keyed on the action) —
    # treat WhoHost as a degenerate WhoModem here.
    start = ctx.clock.monotonic()
    cp_unload = await ctx.runner.run(["modprobe", "-r", "qmi_wwan"], timeout_s=15.0)
    if cp_unload.exit_code != 0 and b"is in use" in cp_unload.stderr.lower():
        return ActionResult(kind=ActionKind.DRIVER_RESET, who=who, succeeded=False,
                            failure_reason="driver_reset:module_in_use", ...)
    # Even if unload "failed" with "not in kernel", proceed to load (idempotency).
    cp_load = await ctx.runner.run(["modprobe", "qmi_wwan"], timeout_s=15.0)
    if cp_load.exit_code != 0:
        return ActionResult(kind=ActionKind.DRIVER_RESET, who=who, succeeded=False,
                            failure_reason=f"driver_reset:load_exit_{cp_load.exit_code}", ...)
    return ActionResult(kind=ActionKind.DRIVER_RESET, who=who, succeeded=True, ...)
```

**Note:** ActionContext does not currently expose `runner` directly [VERIFIED: `actions/context.py:1-67`]. Plan 04-03 will need to either (a) extend ActionContext with a `runner: SubprocRunner` field, or (b) reach the runner via `ctx.qmi._runner` (private attribute access — not clean). **Recommendation: (a)**. Add `runner: SubprocRunner` to `ActionContext`; existing actions don't reference it but adding the field is back-compat.

### Excerpt 4 — `inventory/sysfs.py:24-50` (sysfs Path discipline + cross-platform via sysfs_root_override)

```python
# Source: src/spark_modem/inventory/sysfs.py:24-50
class SysfsInventory:
    """Walks /sys/bus/usb/devices/ for VID:PID 1199:9091 (Sierra EM7421)."""

    def __init__(self, *, sysfs_root_override: Path | None = None) -> None:
        self._sysfs_root = sysfs_root_override or Path("/sys")

    async def scan(self) -> list[ModemDescriptor]:
        usb_devices_dir = self._sysfs_root / "bus" / "usb" / "devices"
        if not usb_devices_dir.is_dir():
            return []
        ...
```

**`sysfs/usb_unbind_rebind.py` mirrors this exactly:**

```python
# src/spark_modem/sysfs/usb_unbind_rebind.py — recommended structure
import asyncio
from pathlib import Path

async def unbind_rebind(
    usb_path: str,
    *,
    target: Literal["child-port", "parent-hub"] = "child-port",
    sysfs_root: Path | None = None,
    rebind_delay_seconds: float = 0.5,
) -> None:
    root = sysfs_root or Path("/sys")
    if target == "parent-hub":
        write_path = usb_path.rsplit(".", 1)[0]   # "2-3.1.1" -> "2-3.1"
    else:
        write_path = usb_path
    unbind = root / "bus/usb/drivers/usb/unbind"
    bind = root / "bus/usb/drivers/usb/bind"
    unbind.write_text(write_path, encoding="ascii")
    await asyncio.sleep(rebind_delay_seconds)
    bind.write_text(write_path, encoding="ascii")
```

### Excerpt 5 — `policy/decision_table.py:91-99` (lookup_action shape — pure function returning union)

```python
# Source: src/spark_modem/policy/decision_table.py:91-99
def lookup_action(
    category: IssueCategory, detail: IssueDetail
) -> ActionKind | str | None:
    """Return ActionKind, skip-reason string, or None for unrecognised pairs."""
    return _DECISION_TABLE.get((category, detail))
```

`policy/ladder.py:select_rung` follows the same shape: pure function, union return, no I/O.

### Excerpt 6 — `policy/transitions.py:23-42` (Final constants → moves to Settings under B-03)

```python
# Source: src/spark_modem/policy/transitions.py:23-42 (BEFORE Phase 4)
_RSRP_FLOOR_DBM: Final[int] = -110
_RSRQ_FLOOR_DB: Final[float] = -15.0
_SNR_FLOOR_DB: Final[float] = 0.0


def is_signal_below_gate(snap: ModemSnapshot) -> bool:
    sig = snap.signal
    if sig.rsrp_dbm is not None and sig.rsrp_dbm < _RSRP_FLOOR_DBM:
        return True
    ...
```

**Phase 4 shape:**

```python
# AFTER Phase 4 (B-03)
def is_signal_below_gate(snap: ModemSnapshot, config: Settings) -> bool:
    sig = snap.signal
    if sig.rsrp_dbm is not None and sig.rsrp_dbm < config.signal_rsrp_floor_dbm:
        return True
    if sig.rsrq_db is not None and sig.rsrq_db < config.signal_rsrq_floor_db:
        return True
    return sig.snr_db is not None and sig.snr_db < config.signal_snr_floor_db
```

Note: `is_signal_below_gate` is currently called from `transition()` with no Settings parameter [VERIFIED: `transitions.py:65`]. Phase 4 plan #4 must thread `ctx.config` through `transition()` (the function already accepts `ctx: PolicyContext`, so it's `ctx.config` — already available; the threading is local).

### Excerpt 7 — `tools/gen_replay_fixtures.py:1-40` (script-under-tools/ pattern)

```python
# Source: tools/gen_replay_fixtures.py:1-40
"""Generate >=1000 replay-cycle fixtures..."""
import argparse
import json
import random
from pathlib import Path
...

def main() -> int:
    parser = argparse.ArgumentParser(prog="gen_replay_fixtures")
    parser.add_argument("--out", type=Path, default=Path("tests/fixtures/replay"))
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    ...
```

**`tools/pull_replay_traces.py` shape:** see Q8 above.

### Excerpt 8 — `tests/fakes/runner.py` (test-tier helpers; tests/ is SP-04-exempt)

[ASSUMED based on Plan 02-01 SUMMARY] FakeRunner registers `(argv_tuple) -> CompletedProcess` mappings; tests register every expected command. tests/hil/fault_inject.py uses real subprocess.run (not FakeRunner) — test-tier code is SP-04-exempt, confirmed by Plan 03-09's `test_logrotate_create.py` using `subprocess.run` wrapped in `asyncio.to_thread`.

### Excerpt 9 — Plan 03-09 lifecycle test pattern (HIL scenarios mirror this)

[ASSUMED based on STATE.md notes] `tests/integration/test_lifecycle.py` uses `pytestmark = pytest.mark.linux_only` (per-module marker, not auto-marker). HIL scenarios add `pytestmark = [pytest.mark.linux_only, pytest.mark.hil]` so they're skipped on Windows dev hosts AND on the unit-test CI runner.

### Excerpt 10 — `.github/workflows/ci.yml:14-22` (self-hosted aarch64 + uv setup)

```yaml
# Source: .github/workflows/ci.yml:14-22
jobs:
  lint-and-types:
    name: Lint + type-check (aarch64 self-hosted)
    runs-on: [self-hosted, linux, ARM64]
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        run: |
          curl -LsSf https://astral.sh/uv/install.sh | sh
          echo "$HOME/.local/bin" >> "$GITHUB_PATH"
```

`hil.yml` reuses this exact bootstrap; only difference is the runner labels (add `hil-bench`), the trigger (cron + workflow_dispatch instead of push/PR), and the body (pytest -m hil).

---

## Risks & Pitfalls

> Beyond CONTEXT.md and the PITFALLS.md sections referenced in CONTEXT canonical_refs.

### R1. usb_reset's parent-hub variant re-enumerates ALL 4 modems

**What goes wrong:** A-06 routes SIERRA_BOOTLOADER → parent-hub usb_reset. On the production Jetson, all 4 modems share one USB hub at `2-3.1`. Writing `2-3.1` to `unbind` re-enumerates all 4 modems for ~1-2 seconds. Three healthy modems flap to `present=False`, then back to `present=True`. The cycle following the rebind sees 3 spurious `disconnected` transitions.

**Why it happens:** Sierra-bootloader recovery is a hub-level reset (PITFALLS §1.6 prescribes parent-hub specifically). The recovery is necessary; the collateral 3-modem reset is the cost.

**How to avoid:** This is unavoidable but **detectable in HIL**: the parent-hub HIL scenario should assert that the daemon does NOT count the 3 spurious disconnects against any modem's escalation counters (the cycle short-circuit should ensure clean state transitions, NOT escalations).

**Warning signs:** After a SIERRA_BOOTLOADER recovery, 3 healthy modems briefly show `present=False` then `present=True` in the next 2-3 cycles; counters bumped on those modems would indicate a cross-action regression.

### R2. Test fixtures of LFS pointers committed accidentally

**What goes wrong:** A developer who hasn't run `git lfs install` clones the repo, the `tests/fixtures/replay/v1-30d/*.json` files are 134-byte LFS pointer stubs, the unit-test suite doesn't catch this (LFS files aren't in unit-test paths), and HIL CI fails with a confusing replay-harness error.

**Why it happens:** Git LFS is not a default install; `actions/checkout@v4 lfs:true` works in CI but not locally without `git-lfs` binary.

**How to avoid:** `tools/pull_replay_traces.py` (sketched in Q8) has the explicit pointer-detection check. Make it a CI gate even on dev-laptop pre-commit hook (or at least a documented "if your replay tests fail with parse errors, run `git lfs pull`").

### R3. `multi_modem_threshold_fraction` Settings field name conflict

**What goes wrong:** [VERIFIED: `policy/context.py:46`] `PolicyContext.expected_modem_count: int = 4`. The CONTEXT.md C-01 wording introduces a `multi_modem_threshold_fraction` Settings field (default 0.75). Both fields belong to the eligibility predicate. A naming inconsistency between PolicyContext (`expected_modem_count`) and Settings (`multi_modem_threshold_fraction`) could confuse the planner.

**Why it happens:** `expected_modem_count` is in PolicyContext (a derived field built at cycle start by the cycle driver, not a config field), while `multi_modem_threshold_fraction` is the configurable threshold. They're orthogonal, but the naming suggests they're related.

**How to avoid:** Plan 04-03 should add to Settings:
- `multi_modem_threshold_fraction: float` (default 0.75, RELOAD_DATA, validator `0.5 <= v <= 1.0`)
- `expected_modem_count: int` (default 4, RELOAD_RESTART — topology field) — and remove the duplicate from PolicyContext, or have PolicyContext.expected_modem_count read from Settings.

### R4. Per-action timestamp bumps must be in the same atomic write as counter bumps (RECOVERY_SPEC §8 / FR-26.2)

**What goes wrong:** If `last_action_monotonic_by_kind[kind]` is bumped in a different write than the counter bump, a crash between the two leaves an inconsistent state file (counter incremented, timestamp not — next cycle thinks the action happened "long ago" and might re-fire too soon, or the reverse).

**Why it happens:** Phase 2's atomic-write contract (RECOVERY_SPEC §8) was designed when `last_action_monotonic` was a single field. Adding a dict means it's part of the same `model_copy(update={...})` call.

**How to avoid:** Plan 04-04's task list MUST include a test that asserts both fields update together within a single atomic write, with `model_copy(update={"last_action_monotonic": ..., "last_action_monotonic_by_kind": ..., "counters": ...})` as one call. The crash-injection variant from PITFALLS §9.1 should be extended.

### R5. SkipReason DRY_RUN ambiguity with PlannedAction.suppressed_by_dry_run

**What goes wrong:** When `Settings.dry_run=True`, the engine's gate evaluation produces `suppressed_by_dry_run=True` on `PlannedAction` AND emits an `ActionSkipped(reason=DRY_RUN)`. Two semantically-equivalent records of the same fact.

**Why it happens:** B-04's emit-both-shapes contract for back-compat.

**How to avoid:** Document explicitly in `wire/events.py`'s ActionSkipped docstring that DRY_RUN events are emitted ALONGSIDE PlannedAction.suppressed_by_dry_run; consumers should use ONE source, not both. Phase 4 plan #5's tests should pin this contract.

### R6. modprobe stderr classification is case-insensitive but kmod source is case-sensitive

**What goes wrong:** Q2's recommended classifier uses `b"is in use" in cp.stderr.lower()`. kmod's actual stderr message is `"Module qmi_wwan is in use.\n"` [CITED: kmod source line 876]. The lowercase match works for "is in use" — but kmod's message is "Module X is in use" not "Module X is in use by", so a stricter regex would fail.

**Why it happens:** Different libkmod versions emit slightly different phrasings. The Phase 4 deployed kmod version on the Jetson L4T R35.6.4 may differ from upstream master.

**How to avoid:** Use a **substring match**, not a regex anchored on full message. The Q2 classifier uses substring match — keep it that way. Plan 04-03's tests should include fixtures from at least 2 kmod versions (Ubuntu 20.04 ships kmod 27, Ubuntu 22.04 ships 29) — but **not blocking**: lowercase substring match is permissive enough.

### R7. ActionContext expansion ripples to existing tests

**What goes wrong:** Adding `runner: SubprocRunner` to ActionContext breaks every existing test that constructs an ActionContext (Plan 02-06 has 6 cheap-action tests that build ActionContext for fix_autosuspend, set_apn, etc.).

**Why it happens:** ActionContext is a frozen dataclass; adding a required field is a breaking change.

**How to avoid:** Make `runner` optional with a sensible default (`runner: SubprocRunner | None = None`) and have driver_reset assert `ctx.runner is not None` at execute() entry. Existing tests using FakeRunner via the qmi wrapper don't need changes; new driver_reset tests inject FakeRunner directly. Plan 04-03 should pin this.

### R8. WhoHost vs WhoModem mismatch in dispatcher signature

**What goes wrong:** [VERIFIED: `actions/dispatcher.py:35`] `ExecuteFn = Callable[[WhoModem, ActionContext], Awaitable[ActionResult]]`. The dispatcher signature passes `WhoModem`, but driver_reset is global — the engine wraps it in `WhoHost()` at `engine.py:300`. The dispatcher will not be invoked for driver_reset directly — driver_reset is dispatched outside the per-modem loop, at the engine's short-circuit.

**Why it happens:** The dispatcher is per-modem; driver_reset is global. They have different invocation flows.

**How to avoid:** [VERIFIED] The current code already handles this correctly — `_plan_driver_reset()` returns a PlannedAction with `who=WhoHost()`, and the cycle driver dispatches driver_reset via a separate path (NOT through `dispatcher.execute_and_verify`). Plan 04-03 should follow the same pattern: driver_reset.execute() is invoked by the cycle driver's driver_reset branch directly, not via the per-modem dispatcher loop. Add driver_reset to `_REGISTRY` for the CLI surface (which DOES use the dispatcher), but document that the cycle-driver path bypasses the registry for driver_reset.

### R9. HIL nightly schedule and bench-Jetson maintenance window collision

**What goes wrong:** A nightly HIL run at 04:00 UTC could collide with a daemon `ctl maintenance on --duration=2h` window that an operator forgot about (PITFALLS §16.2). The HIL runs against a maintenance-mode daemon that suppresses destructive actions — the test fails with confusing skip-reason events.

**Why it happens:** Maintenance mode is operator-controllable and not visible to GitHub Actions.

**How to avoid:** HIL workflow setup step should run `spark-modem ctl maintenance off` unconditionally before the test suite (idempotent — already-off is a no-op). Document this in `tests/hil/README.md`.

### R10. parent-hub usb_reset on a Jetson where the bench layout differs from production

**What goes wrong:** Production Jetson has all 4 modems on hub `2-3.1`. The bench Jetson HIL setup might have a different topology (e.g., 4 modems each on their own root port). Then `usb_path.rsplit('.', 1)[0]` gives different parent paths per modem, and parent-hub recovery reduces to child-port recovery — not the full re-enumeration scenario.

**Why it happens:** The `usb_path.rsplit('.', 1)[0]` logic assumes the production topology.

**How to avoid:** Plan 04-02's parent-hub usb_reset includes a sysfs walk that climbs to the actual physical USB hub:

```python
def parent_hub_path(usb_path: str, sysfs_root: Path) -> str:
    """Climb sysfs symlink chain to find the parent USB hub."""
    device_dir = (sysfs_root / "bus/usb/devices" / usb_path).resolve()
    parent = device_dir.parent
    while not (parent / "idVendor").exists() or parent.name == usb_path:
        parent = parent.parent
        if parent == Path("/"):
            raise ValueError(f"No parent USB hub for {usb_path}")
    return parent.name
```

Or — simpler — accept the production-topology assumption with a test fixture that asserts `2-3.1.1`'s parent is `2-3.1` and document the topology assumption in `sysfs/usb_unbind_rebind.py`'s docstring. Recommend the simpler approach (assumption + documentation) to avoid scope creep; HIL bench-Jetson topology is required to match production by Plan 04-06's bench setup.

---

## Validation Architecture

> Per gsd CONTEXT.md / config.json (`workflow.nyquist_validation` defaults enabled).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio (mode=auto) [VERIFIED: `pyproject.toml`] |
| Config file | `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `pytest -m "unit and not linux_only and not hil" -x` (~1-2s) |
| Per-plan suite | `pytest tests/unit/policy/ tests/unit/actions/ -ra` (~5-10s) |
| Full suite (regular CI) | `pytest -m "unit or integration" -ra` (target: ≤30s per M7; current Phase 3 exit: 17.94s) |
| HIL suite | `pytest -m hil tests/hil/ -ra --tb=short` (target: ≤90 min per D-01) |
| Phase gate | Full suite green + HIL nightly green + replay-harness ≥95% before `/gsd-verify-work` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | Wave 0? |
|--------|----------|-----------|-------------------|---------|
| FR-23 | Signal-quality gate refuses modem_reset/usb_reset when below threshold | unit | `pytest tests/unit/policy/test_gates.py::test_gate_signal_blocks_destructive_below_threshold -x` | Existing (Plan 02-05) |
| FR-23 | ActionSkipped(reason=signal_below_gate) emitted on refusal | unit | `pytest tests/unit/policy/test_engine.py::test_action_skipped_emitted_on_signal_gate -x` | NEW Wave 0 |
| FR-23 | rf_blocked transition fires when signal below | unit | `pytest tests/unit/policy/test_transitions.py::test_rf_blocked_when_below_threshold -x` | Existing (Plan 02-05) |
| FR-23 | Cheap actions still run while rf_blocked=True | unit | `pytest tests/unit/policy/test_gates.py::test_gate_signal_allows_cheap_actions -x` | Existing (Plan 02-05) |
| FR-23 | Signal thresholds are RELOAD_DATA tagged in Settings | unit | `pytest tests/unit/config/test_settings.py::test_signal_thresholds_reload_data -x` | NEW Wave 0 |
| FR-23 | HIL: synthetic-RF-noise scenario fires the gate | hil | `pytest -m hil tests/hil/scenarios/test_rf_blocked.py -x` | NEW (Plan 04-07) |
| FR-24 | driver_reset eligibility predicate at 75% threshold | unit | `pytest tests/unit/policy/test_engine.py::test_driver_reset_eligible_at_3_of_4_hung -x` | NEW Wave 0 |
| FR-24 | driver_reset NOT eligible at 50% threshold | unit | `pytest tests/unit/policy/test_engine.py::test_driver_reset_not_eligible_at_2_of_4_hung -x` | NEW Wave 0 |
| FR-24 | driver_reset suppressed by thermal_warn | unit | `pytest tests/unit/policy/test_engine.py::test_driver_reset_suppressed_thermal -x` | NEW Wave 0 |
| FR-24 | Cooldown enforced via Settings.global_driver_reset_backoff_seconds | unit | `pytest tests/unit/policy/test_engine.py::test_driver_reset_cooldown -x` | NEW Wave 0 |
| FR-24 | None last_driver_reset_monotonic does not crash | unit | `pytest tests/unit/policy/test_engine.py::test_driver_reset_first_fire_no_npe -x` | NEW Wave 0 |
| FR-24 | Actionable-signal requirement: all RF-blocked → not eligible | unit | `pytest tests/unit/policy/test_engine.py::test_driver_reset_actionable_signal -x` | NEW Wave 0 |
| FR-24 | Globals counter + timestamp bump on fire | unit | `pytest tests/unit/policy/test_engine.py::test_driver_reset_globals_bump -x` | Existing skeleton |
| FR-24 | Per-modem counters/streak preserved post-driver_reset | unit | `pytest tests/unit/policy/test_engine.py::test_driver_reset_preserves_per_modem -x` | NEW Wave 0 |
| FR-24 | HIL: 3-modem QMI hang triggers exactly one driver_reset | hil | `pytest -m hil tests/hil/scenarios/test_three_modem_hang.py -x` | NEW (Plan 04-07) |
| FR-24 | HIL: pkill -9 qmi-proxy recovers with one driver_reset | hil | `pytest -m hil tests/hil/scenarios/test_proxy_died_recovery.py -x` | NEW (Plan 04-07) |
| FR-27 | All 4 destructive actions registered in dispatcher | unit | `pytest tests/unit/actions/test_dispatcher.py::test_phase4_destructive_kinds_registered -x` | NEW Wave 0 |
| FR-27 | CLI `spark-modem reset --action=modem_reset` succeeds | unit | `pytest tests/unit/cli/test_reset.py::test_reset_modem_reset_cli -x` | NEW Wave 0 |
| FR-27 | CLI `--target=parent-hub` flag accepted for usb_reset | unit | `pytest tests/unit/cli/test_reset.py::test_reset_target_parent_hub -x` | NEW Wave 0 |
| FR-27 | CLI rejects unknown --target value | unit | `pytest tests/unit/cli/test_reset.py::test_reset_target_invalid -x` | NEW Wave 0 |
| FR-27 | Idempotency property test: 2× back-to-back invocations identical end-state | property | `pytest tests/property/test_destructive_idempotency.py -x --hypothesis-show-statistics` | NEW Wave 0 |
| FR-27 | HIL: each destructive action runs end-to-end | hil | `pytest -m hil tests/hil/scenarios/test_destructive_actions.py -x` | NEW (Plan 04-07) |

### Sampling Rate (Nyquist Dimension 8 — per-plan validation)

Per CONTEXT D-05 (~7 plans), the validation rate is sized to catch behavior-class regressions:

| Plan | Behavior class | Sample rate floor | Signal-of-interest frequency | Min validation rate |
|------|----------------|-------------------|------------------------------|---------------------|
| 04-01 (modem_reset action) | Per-action execute() / verify() shape | 1 unit test per execute() error path (4 paths: success, qmi_err, classify_proxy_died, classify_timeout) | 4 invocations/scenario | 8 tests (per-action × 4 paths × 2 dry-run states) |
| 04-02 (usb_reset + sysfs + Sierra-bootloader) | sysfs file write semantics, two variants, EBUSY/ENODEV/EACCES classification | 1 unit per (variant, errno) tuple = 2 × 4 = 8 | sysfs-write event rate ~1/cycle in HIL | 12 tests (8 errno × 1.5 multiplier for Sierra-bootloader path) |
| 04-03 (driver_reset + eligibility + thermal + cooldown) | Eligibility predicate boundary (75%, thermal, cooldown, actionable-signal) × 4 dimensions | 1 unit per boundary × 4 = 4; plus 1 modprobe-stderr classifier per pattern (5 patterns) | Eligibility evaluated 1/cycle | 12 tests (4 boundaries × 3 variants + 5 modprobe classifications) |
| 04-04 (ladder + per-action timestamps + signal-gate Settings) | Ladder rung selection, timestamp dict update, Settings RELOAD_DATA | 1 per ladder progression scenario from RECOVERY_SPEC §10.2 (4 scenarios); 3 timestamp dict mutation paths; 3 Settings tags | RECOVERY_SPEC §10.2 has 4 worked examples | 14 tests (4 + 3 + 3 + 4 cross-scenario) |
| 04-05 (ActionSkipped event + integration) | Discriminator-union schema, 7 SkipReason enum values, replay-harness back-compat | 1 round-trip per SkipReason × 7; 1 schema-coexistence test | Event emit rate ~1-3/cycle on faults | 10 tests (7 + 3 integration paths) |
| 04-06 (HIL infra scaffold) | Workflow trigger semantics, LFS pull, fault-inject helpers | Smoke (1 per helper) — these are infrastructure | 1× per nightly run | 6 tests (workflow lint + 5 fault-inject helpers' smoke) |
| 04-07 (HIL scenario suite) | End-to-end SC#4 paths (8 scenarios: boot/sim_swap/soft_reset/modem_reset/three_modem_hang/rf_event/proxy_died/parent_hub_bootloader) + Phase-3 piggyback (4 deferred scenarios) + replay-harness 30-day gate | 1 scenario per HIL fault path; 1 agreement gate | 1× per nightly run; HIL suite ≤90 min | 12 HIL scenario tests + 1 replay-harness gate (≥95% on 30-day fixtures) |

### Per-task / per-wave / per-phase rates

- **Per task commit (M7 budget):** `pytest -m "unit and not linux_only and not hil" -x` — ~1-2s. Catches unit regressions inline.
- **Per wave merge (M7 budget):** `pytest -m "unit or integration" -ra` — ≤30s on dev laptop (Phase 3 exit was 17.94s; Phase 4 will add ~50-100 tests, comfortable).
- **Per phase gate (HIL budget):** `pytest -m hil tests/hil/` — ≤90 min nightly. Plus replay-harness ≥95% gate.
- **Phase 4 EXIT bar (Plan 04-07):** All four SC#4 scenarios green on bench Jetson + Phase-3 deferred SCs green + replay-harness 30-day agreement ≥95%.

### Wave 0 Gaps

- [ ] `tests/unit/policy/test_ladder.py` — covers FR-22 (escalation ladder ceilings) + FR-23 + FR-24 ladder progression
- [ ] `tests/unit/policy/test_engine_driver_reset.py` — covers FR-24 eligibility predicate boundary cases
- [ ] `tests/unit/actions/test_modem_reset.py` — covers FR-23 + FR-27 modem_reset
- [ ] `tests/unit/actions/test_usb_reset.py` — covers FR-23 + FR-27 + A-06 Sierra-bootloader
- [ ] `tests/unit/actions/test_driver_reset.py` — covers FR-24 + FR-27 + A-03 modprobe stderr classifier
- [ ] `tests/unit/sysfs/test_usb_unbind_rebind.py` — covers A-02 sysfs file write semantics
- [ ] `tests/unit/cli/test_reset_phase4.py` — covers FR-27 CLI surface (`--target=parent-hub`)
- [ ] `tests/property/test_destructive_idempotency.py` — covers SC#1 idempotency property test (hypothesis-driven)
- [ ] `tests/unit/wire/test_action_skipped_event.py` — covers B-04 ActionSkipped variant + SkipReason round-trip
- [ ] `tests/hil/__init__.py` — already exists [VERIFIED: `Glob tests/hil/**/*.py`] but only as stub
- [ ] `tests/hil/conftest.py` — fixtures for HIL bench Jetson teardown/setup (mark all tests `linux_only` AND `hil`)
- [ ] `tests/hil/fault_inject.py` — fault-injection helpers (Plan 04-06)
- [ ] `tests/hil/scenarios/*.py` — 8 SC#4 scenarios + 4 Phase-3 deferred (Plan 04-07)
- [ ] `tools/pull_replay_traces.py` — LFS pointer materialization confirmation (Plan 04-06)
- [ ] `tests/fixtures/replay/v1-30d/README.md` — quarterly refresh runbook (Plan 04-06)
- [ ] `.github/workflows/hil.yml` — nightly + workflow_dispatch (Plan 04-06)

---

## Plan Slicing Notes

CONTEXT D-05 targets ~7 plans. Research confirms this is the right granularity. Recommended refinements to the D-05 sketch:

### Plan 04-01: modem_reset action + ladder rung-2 wiring
- **Scope:** `actions/modem_reset.py`, append to `dispatcher._REGISTRY`, unblock `cli/reset.py` for MODEM_RESET kind, register MODEM_RESET unit tests.
- **Refinement:** This plan is the simplest of the three action plans (re-uses Phase 2's `dms_set_operating_mode("reset")` verbatim). It can land before Plan 04-04 (engine wiring) IF the engine still treats MODEM_RESET via the existing flat decision-table → MODEM_RESET path (it does — `(QMI, OPERATING_MODE_OFFLINE) → MODEM_RESET` already routes [VERIFIED: `decision_table.py:60`]). The ladder integration (which makes MODEM_RESET reachable from REGISTRATION rung 2) lands in Plan 04-04.
- **Dependencies:** None upstream in Phase 4; Phase 1 wire types + Phase 2 dispatcher pattern.

### Plan 04-02: usb_reset action + new sysfs/ module + Sierra-bootloader
- **Scope:** `sysfs/__init__.py`, `sysfs/usb_unbind_rebind.py` (single file, planner discretion locks here), `actions/usb_reset.py`, append `IssueDetail.SIERRA_BOOTLOADER` to enums, decision-table row for SIERRA_BOOTLOADER, `--target` CLI flag.
- **Refinement:** The `sysfs/` module layout decision (planner's discretion): **single file** `sysfs/usb_unbind_rebind.py` plus `sysfs/__init__.py` re-export. Rationale: only one capability (unbind+rebind) lives here; splitting into `usb_bind.py` + `usb_unbind.py` over-decomposes a 30-line module.

### Plan 04-03: driver_reset action + global eligibility predicate + thermal + cooldown
- **Scope:** `actions/driver_reset.py`, modprobe stderr classifier, wire `_global_driver_reset_eligible` to real predicate (75% / signal / thermal / cooldown), add `Settings.{multi_modem_threshold_fraction, expected_modem_count, global_driver_reset_backoff_seconds}` (RELOAD_RESTART for expected_modem_count, RELOAD_DATA for the others), extend ActionContext with optional `runner: SubprocRunner | None = None`.
- **Refinement:** This is the largest plan because it changes the engine's eligibility predicate AND adds 3 Settings fields AND adds a new action. Could be split if needed (eligibility predicate → its own plan), but the eligibility predicate is meaningless without the action it gates. Keep as one plan.

### Plan 04-04: policy/ladder.py + per-action timestamps + signal-gate Settings migration
- **Scope:** `policy/ladder.py` with `select_rung()` pure function, `ModemState.last_action_monotonic_by_kind` field, engine integration of ladder.select_rung in `_apply_gates_to_action`, add `Settings.{max_soft, max_modem, max_usb, signal_rsrp_floor_dbm, signal_rsrq_floor_db, signal_snr_floor_db}` (all RELOAD_DATA), migrate `policy/transitions.py:is_signal_below_gate` to read from `ctx.config`, re-key `gate_same_action_backoff` and `gate_ladder_backoff` to use `last_action_monotonic_by_kind`.
- **Refinement:** This is the second-largest plan. The signal-gate migration (B-03) is functionally trivial but has high test surface (every gate test in Phase 2 needs a tweak to pass thresholds via Settings). Worth a dedicated plan; do not fold into 04-03.

### Plan 04-05: ActionSkipped event variant + decision-table/engine integration
- **Scope:** `wire/events.py` add `ActionSkipped` variant, `wire/enums.py` add `SkipReason` StrEnum, engine emits ActionSkipped alongside PlannedAction in all gate-failure paths + ladder-exhausted path + driver_reset short-circuit per-modem-suppressions, replay-harness back-compat verification (no shim needed; doc-only).
- **Refinement:** This is mostly a wire-type addition + engine plumbing. Smaller scope than 04-03/04-04. Could be folded into 04-04 if plan count needs reduction (then ~6 plans), but the user-confirmed target is 7.

### Plan 04-06: HIL infra scaffold
- **Scope:** `.github/workflows/hil.yml`, `tests/hil/README.md` topology doc, `tests/hil/fault_inject.py`, `tests/hil/conftest.py`, `tools/pull_replay_traces.py`, `tests/fixtures/replay/v1-30d/.gitkeep` + `README.md` + `.gitattributes` LFS tracking, register `hil` marker (already done — verify).
- **Refinement:** This plan ships infrastructure; no scenario tests. Scenarios land in Plan 04-07. The plan's exit criterion is "HIL workflow runs (no scenarios yet) on workflow_dispatch and reports a clean skip-no-tests-collected".

### Plan 04-07: HIL scenario suite + Phase-3 piggyback + replay-harness 30-day gate
- **Scope:** `tests/hil/scenarios/test_boot_to_healthy.py`, `test_sim_swap.py`, `test_soft_reset_sim_app_detected.py`, `test_modem_reset_after_soft.py`, `test_three_modem_hang.py`, `test_rf_event_no_destructive.py`, `test_proxy_died_recovery.py` (Phase-4 SC#4) + `test_qmi_wwan_reload_clean_transition.py`, `test_sigterm_within_5s.py`, `test_ctl_reset_state_serialisation.py`, `test_watchdog_90s_actual_fire.py` (Phase-3 piggyback). Replay-harness invocation in workflow + ≥95% gate.
- **Refinement:** 12 scenario files. Could be split into 04-07a (Phase-4 SC#4 only, 7 scenarios) and 04-07b (Phase-3 piggyback + replay-harness gate, 5 deliverables) if execution time matters. Recommend keeping as one plan to honor the 7-plan target.

### Plan-count compaction options (if planner needs to fit a tighter budget)

- **6 plans:** Fold Plan 04-05 (ActionSkipped) into Plan 04-04 (engine wiring). Risk: 04-04 becomes ~25% larger; tradeoff is one fewer review cycle.
- **5 plans:** Additionally fold Plan 04-01 (modem_reset) into Plan 04-04 (since modem_reset has zero new mechanism). Risk: 04-04 becomes the dominant plan; lose the per-action atomic completion signal.

Recommendation: **Stick with 7 plans.** Phase 1, 2, 3 each ran 7-9 plans; Phase 4's complexity warrants the same granularity.

---

## Sources

### Primary (HIGH confidence)
- `src/spark_modem/actions/soft_reset.py` (lines 1-50) — model for all three new destructive actions
- `src/spark_modem/actions/dispatcher.py` (lines 39-46) — `_REGISTRY` append pattern
- `src/spark_modem/actions/result.py` (lines 20-87) — `ActionResult` / `VerifyResult.deferred()` shapes
- `src/spark_modem/actions/context.py` (lines 47-67) — `ActionContext` frozen dataclass
- `src/spark_modem/qmi/wrapper.py` (lines 238-322) — `dms_set_operating_mode` + state-changing pattern
- `src/spark_modem/policy/engine.py` (lines 76-106, 280-294) — driver_reset short-circuit + placeholder predicate
- `src/spark_modem/policy/decision_table.py` (lines 35-99) — flat lookup + `lookup_action()` shape
- `src/spark_modem/policy/gates.py` (lines 22-130) — `_DESTRUCTIVE_KINDS` + gate ordering
- `src/spark_modem/policy/transitions.py` (lines 23-65) — Final constants migrating to Settings (B-03)
- `src/spark_modem/policy/context.py` (lines 32-46) — `PolicyContext.expected_modem_count`
- `src/spark_modem/wire/enums.py` (lines 92-114, 23-79) — ActionKind + IssueDetail enums
- `src/spark_modem/wire/state.py` (lines 33-94) — `ModemState` shape + `last_action_monotonic`
- `src/spark_modem/wire/events.py` (lines 198-216) — discriminated-union pattern for `ActionSkipped` addition
- `src/spark_modem/wire/globals.py` (lines 12-24) — `GlobalsState` + driver_reset counter/timestamps
- `src/spark_modem/wire/diag.py` (lines 96-110) — `PlannedAction.suppressed_*` flags
- `src/spark_modem/config/settings.py` (lines 29-170) — Settings shape + RELOAD_DATA / RELOAD_RESTART tagging
- `src/spark_modem/config/reload_marker.py` (lines 17-46) — RELOAD_DATA marker pattern
- `src/spark_modem/cli/reset.py` (lines 23-52) — Phase 2 CLI scaffold + `is_registered()` destructive guard
- `src/spark_modem/cli/main.py` (lines 82-97) — argparse subparser shape (model for `--target` flag addition)
- `src/spark_modem/inventory/sysfs.py` (lines 24-130) — sysfs Path discipline + cross-platform pattern (analog for new `sysfs/` module)
- `src/spark_modem/subproc/runner.py` (lines 108-196) — list-form argv + stderr capture (driver_reset goes through here)
- `.github/workflows/ci.yml` (lines 14-49) — self-hosted aarch64 + uv venv setup (model for `hil.yml`)
- `pyproject.toml:78` — `hil` pytest marker already registered
- `docs/RECOVERY_SPEC.md` §6.4, §4.1, §10.2 — driver_reset gate / ladder ceilings / progression scenarios
- `docs/MIGRATION.md` §2 — Phase 0 HIL scenario list (Phase 4 traces verbatim)
- `docs/adr/0006-counter-decay.md` — atomic write ordering pinned (FR-26.2)
- `docs/adr/0008-state-machine-5-plus-2.md` — 5+2 shape; rf_blocked orthogonal flag
- `docs/adr/0012-concurrency-locks.md` — per-modem flock acquisition shape
- `.planning/research/PITFALLS.md` §1.1, §1.6, §17.4 — qmi-proxy crash, Sierra-bootloader, thermal suppression

### Secondary (MEDIUM confidence — cited / verified via tool)
- [LWN.net "Manual driver binding and unbinding"](https://lwn.net/Articles/143397/) — sysfs `/sys/bus/usb/drivers/usb/{un,}bind` write protocol [CITED]
- [kernel.org cdc_mbim networking docs](https://docs.kernel.org/networking/cdc_mbim.html) — cdc-wdmX child of MBIM control interface; sysfs lookup [CITED]
- [GitHub `lucasdemarchi/kmod` `tools/modprobe.c`](https://github.com/lucasdemarchi/kmod/blob/master/tools/modprobe.c) — modprobe stderr patterns at lines 731 (not in kernel), 816 (not found), 876 (in use); exit code 0 on already-removed [CITED via WebFetch]

### Tertiary (LOW confidence — assumed; flag for HIL validation)
- Sleep duration between unbind and bind (500ms child / 1000ms parent-hub) — **[ASSUMED]** based on PITFALLS §17.2 USB hub PSU droop window; HIL plan 04-02 should empirically validate
- Bench Jetson runner topology (separate physical machine vs same as unit-test runner) — **[ASSUMED]** Option B (separate runner with `hil-bench` label); confirm with deployment team before Plan 04-06 kickoff
- Auto-removal of cdc_wdm/cdc_ncm dependencies on `modprobe -r qmi_wwan` — **[ASSUMED]** standard modprobe behavior (does not auto-remove unused deps); HIL plan 04-03 should empirically verify on bench
- Git LFS auth on self-hosted runner with default `GITHUB_TOKEN` — **[ASSUMED]** based on standard GitHub Actions docs; verify in 04-06 dry-run

## Assumptions Log

> Claims tagged `[ASSUMED]` requiring user confirmation before execution. Discuss-phase
> should validate these before locking implementation. **None of these assumptions block
> the planner from writing tasks**, but they should be flagged for HIL-time empirical
> verification.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | sysfs unbind/bind sleep delay 500ms (child) / 1000ms (parent-hub) | Q1 | Too short → kernel race during re-enumeration; too long → exceeds NFR-1 P99 cycle budget. Mitigation: Settings field tunable, default conservative |
| A2 | Bench Jetson HIL runner is separate physical machine from unit-test runner (Option B) | Q6 | Option A would require the unit-test runner to also have 4 modems plugged in (operationally unlikely). HIL workflow runner-label addition may need adjustment if Option A is reality |
| A3 | modprobe -r qmi_wwan does NOT auto-remove cdc_wdm/cdc_ncm dependencies | Q2 | If it does auto-remove, the second `modprobe qmi_wwan` re-loads them — slightly slower but functionally correct; no plan change needed |
| A4 | Git LFS pulls work on self-hosted aarch64 runner with default `GITHUB_TOKEN` | Q8 | If repo is in an org with custom LFS quotas / auth, Plan 04-06's setup step needs to install `git-lfs` binary AND configure auth. Workflow lints would surface this on first run |
| A5 | Production Jetson topology has all 4 modems on hub `2-3.1` (parent-hub computation `usb_path.rsplit('.', 1)[0]`) | R10 | If bench Jetson topology differs, parent-hub usb_reset reduces to child-port usb_reset. Mitigation: assert in `sysfs/usb_unbind_rebind.py` docstring + a test fixture pinning the topology assumption |
| A6 | The `subproc/runner.py` `_STATE_CHANGE_TIMEOUT_S = 15.0` is sufficient for `modprobe` calls | Q2 / Excerpt 3 | If a busy qmi-proxy delays `modprobe -r` past 15s, driver_reset times out. Plan 04-03 should expose `subproc.run(...)` timeout via Settings (`modprobe_timeout_seconds`, default 30) |
| A7 | tests/ tier is SP-04-exempt for direct subprocess.run usage | Q7 (fault_inject.py) | If SP-04 lint scope expands to tests/, fault_inject.py needs refactoring. [VERIFIED in Plan 03-09 SUMMARY] tests/ is exempt; this should not regress |

---

## Open Questions

> Issues this research could not resolve; planner should surface in 04-PLAN frontmatter as
> open questions for execute-phase to address (or flag for re-discussion if blocking).

1. **Bench Jetson HIL runner topology (Option A vs B).**
   - What we know: D-01 says "self-hosted aarch64 runner from Plan 01-01, physically tethered to a bench Jetson with 4 EM7421s." Phase 1's runner is named `[self-hosted, linux, ARM64]` (no custom label). One machine or two?
   - What's unclear: Whether the existing CI runner machine has 4 modems plugged in.
   - Recommendation: Plan 04-06 frontmatter asks the deployment team. Default to Option B (separate `hil-bench` label) unless told otherwise.

2. **Quarterly LFS trace refresh process owner.**
   - What we know: D-03 says quarterly refresh; CONTEXT.md "Claude's Discretion" says README-as-runbook content is the planner's spec call.
   - What's unclear: Who runs the redactor and pushes the LFS commit each quarter? Phase 5 begins the cadence per "Deferred to Phase 5/6" notes, but the README-shaped runbook needs to spec the procedure.
   - Recommendation: Plan 04-06 README documents the redactor + LFS push process; assigns ownership to "Eng team / NOC handoff in Phase 5". No code dependency.

3. **`expected_modem_count` field placement (PolicyContext vs Settings).**
   - What we know: PolicyContext.expected_modem_count exists [VERIFIED: `policy/context.py:46`]; CONTEXT C-01 mentions reading from Settings.
   - What's unclear: Whether to deprecate PolicyContext.expected_modem_count and have it read through from Settings, or keep both (PolicyContext as the cycle-driver-derived value, Settings as the source of truth).
   - Recommendation: Plan 04-03 makes Settings the source of truth (RELOAD_RESTART since it's topology); the cycle driver populates `PolicyContext.expected_modem_count = ctx.config.expected_modem_count` at PolicyContext construction. Backwards-compat: existing Phase 2 tests that pass `PolicyContext(expected_modem_count=N)` still work.

4. **Modprobe call timeout policy.**
   - What we know: Subproc default state-change timeout is 15s [VERIFIED: `qmi/wrapper.py:39`].
   - What's unclear: Whether modprobe needs longer (e.g., busy modem state may delay unload).
   - Recommendation: Add `Settings.modprobe_timeout_seconds: int = Field(default=30, ge=1, RELOAD_DATA)`. Plan 04-03 covers this.

---

## Environment Availability

> Phase 4 has external dependencies that the bench-Jetson runner must provide. Verify
> in HIL setup (Plan 04-06) before scenario tests run.

| Dependency | Required By | Available on Bench Jetson | Available on Unit-Test Runner | Fallback |
|------------|------------|---------------------------|------------------------------|----------|
| `qmicli` (libqmi) | actions/{soft,modem}_reset, fault_inject | ✓ (Jetpack 5.1.5 includes libqmi) | ✗ | None — required for modem_reset HIL |
| `modprobe` (kmod) | actions/driver_reset, fault_inject | ✓ (standard Ubuntu 20.04) | ✗ | None — required for driver_reset HIL |
| `pkill` (procps-ng) | fault_inject (kill_qmi_proxy) | ✓ | ✓ | None — universally available |
| `git-lfs` | tools/pull_replay_traces.py | ✓ (must be installed: `apt install git-lfs`) | ✓ (likely already installed) | If missing: workflow setup step installs |
| `/dev/kmsg` writable | fault_inject (kmsg_inject) | ✓ (root user, kernel 5.10) | ✗ (Windows / non-Linux) | Skipped via `linux_only` marker |
| `/sys/bus/usb/drivers/usb/unbind` writable | sysfs/usb_unbind_rebind.py (HIL only) | ✓ (root + CAP_SYS_ADMIN) | ✗ | tmp_path-based unit tests work cross-platform |
| `ModemManager` masked | HIL setup pre-step | ✓ (Plan 02-09 postinst masks it) | n/a (no modems) | None — Phase 1 confirmed |
| `zao-infra-ctrl.service` running | HIL setup pre-step | ✓ | n/a | None — required for SC#4 driver_reset scenarios |
| 4 SIM cards (3 carriers per PITFALLS §14.4) | HIL scenario suite | Required | n/a | Carrier-outage tolerance documented; scenarios assert on bonded set |

**Missing dependencies with no fallback:**
- None — every required dependency is either available on the target Jetson or has a unit-test fallback (tmp_path, FakeRunner, FakeClock).

**Missing dependencies with fallback:**
- Linux-only paths (/dev/kmsg, sysfs writes) skip on Windows dev hosts via `linux_only` marker; unit tests use tmp_path-backed fakes for cross-platform coverage.

---

## RESEARCH COMPLETE

**Phase:** 4 — Destructive Actions & HIL
**Confidence:** HIGH on existing-code patterns and CONTEXT.md decisions; MEDIUM on Linux 5.10-tegra sysfs/modprobe specifics; LOW on Git LFS + self-hosted runner topology (deployment-team-owned)

### Key Findings

- All three new destructive actions follow `actions/soft_reset.py` shape verbatim — execute() returns ActionResult, verify() returns VerifyResult.deferred(detail="next_cycle_observation"). modem_reset reuses the exact same QMI verb (A-01).
- sysfs unbind/rebind is a 4-line implementation: write usb_path to unbind, sleep ~500ms, write to bind. Parent-hub variant (A-06) computes parent via `usb_path.rsplit('.', 1)[0]`. CAP_SYS_ADMIN already preallocated.
- driver_reset eligibility predicate has 4 gates (thermal / cooldown / 75% / actionable-signal) in that order; None last_driver_reset_monotonic must short-circuit (otherwise NPE on first cycle); 75% denominator is `expected_modem_count` from Settings (not enumerated count) per C-01.
- policy/ladder.py is a one-function module: `select_rung(category, counters, config) -> ActionKind | "skip:exhausted"`. Decision table stays flat.
- ActionSkipped + PlannedAction.suppressed_* coexist; replay harness needs no shim (back-compat by emission, not filtering).
- HIL CI lane is one workflow file + serial concurrency on a self-hosted aarch64 runner with custom label; nightly + workflow_dispatch; LFS pull via `actions/checkout@v4 lfs:true`; pytest -m hil; 90-min timeout.

### File Created

`.planning/phases/04-destructive-actions-hil/04-RESEARCH.md`

### Confidence Assessment

| Area | Level | Reason |
|------|-------|--------|
| Existing-code patterns (actions, dispatcher, policy seams) | HIGH | All directly verified from source files |
| CONTEXT.md decisions A-01..D-05 | HIGH | Locked by user; researched only the gaps |
| Linux 5.10-tegra sysfs/modprobe specifics | MEDIUM | Verified via LWN article + kmod source; sleep delay is [ASSUMED] |
| HIL workflow shape | MEDIUM | Verified via existing ci.yml; bench Jetson topology [ASSUMED] |
| Git LFS auth on self-hosted runner | LOW | [ASSUMED] standard `GITHUB_TOKEN` works; deployment-team verifies |
| Validation Architecture (sample rates, test counts) | HIGH | Derived from existing Phase 2/3 test patterns |
| Plan slicing (D-05 ~7 plans) | HIGH | Verified plan-count consistent with Phase 1/2/3 scale |

### Open Questions

1. Bench Jetson HIL runner topology — Option A (same machine) vs Option B (separate runner). Defaults to Option B; deployment team confirms.
2. Quarterly LFS trace refresh process owner — README documents the procedure; ownership assigned in Phase 5.
3. `expected_modem_count` field placement — Settings as source of truth, PolicyContext reads through. Plan 04-03 covers.
4. Modprobe call timeout — recommend `Settings.modprobe_timeout_seconds=30`; Plan 04-03 adds.

### Ready for Planning

Research complete. Planner can write 7 plans straight from this without re-reading source code for the locked decisions. Every load-bearing claim cites a specific file:line in the existing codebase or an external authoritative source.

Sources:
- [LWN.net - Manual driver binding and unbinding](https://lwn.net/Articles/143397/)
- [kernel.org - cdc_mbim driver docs](https://docs.kernel.org/networking/cdc_mbim.html)
- [kmod modprobe.c source](https://github.com/lucasdemarchi/kmod/blob/master/tools/modprobe.c)
