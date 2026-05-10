# Phase 4: Destructive Actions & HIL - Context

**Gathered:** 2026-05-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 4 implements the four destructive recovery actions (`soft_reset` —
already shipped in Phase 2 as cheap; `modem_reset`, `usb_reset`, global
`driver_reset` — net-new) as idempotent CLI-runnable functions wired
into the policy engine, end-to-end-gates the signal-quality (RSRP/RSRQ/
SNR) and ≥75%-QMI-hung predicates, and proves all of it on a hardware-
in-the-loop bench Jetson with deliberate fault injection. By exit:

1. Each of `soft_reset`, `modem_reset`, `usb_reset`, `driver_reset` is a
   separate idempotent function callable individually via `spark-modem
   reset --action=<name> --modem=cdc-wdm0` (or `--global` for
   `driver_reset`), survives back-to-back invocation without producing a
   different outcome the second time, and returns a structured success/
   failure with deferred verification (next-cycle observation of
   `operating_mode == "online"` and `raw_ip == "Y"`) (FR-27).
2. The signal-quality gate refuses `modem_reset` and `usb_reset` when
   measured RSRP < -110 dBm OR RSRQ < -15 dB OR SNR < 0 dB; the refusal
   emits an `ActionSkipped` event with `reason="signal_below_gate"` and
   the modem state has `rf_blocked=True` (orthogonal flag, ADR-0008);
   cheap actions still run while `rf_blocked` is set; HIL synthetic-RF-
   noise scenario confirms the gate fires (FR-23).
3. Global `driver_reset` fires only when ≥3 of 4 modems are
   simultaneously QMI-hung (denominator is total-4, with Zao-active
   modems counted as 'not-hung') AND at least one of the hung modems
   has actionable signal (RSRP ≥ -110 AND RSRQ ≥ -15 AND SNR ≥ 0) AND
   no `thermal_warn`/`thermal_critical` host issue is active. Cooldown
   3600 s. The HIL three-modem-QMI-hang scenario triggers exactly one
   `driver_reset` (no thrash, no per-modem `usb_reset` race), the
   `qmi_wwan` reload surfaces as a clean state transition, and metrics
   record `actions_total{kind="driver_reset",result="success"}` once
   (FR-24).
4. The HIL CI lane (`tests/hil/`) on a self-hosted aarch64 runner
   tethered to a bench Jetson with 4 EM7421s runs nightly + on demand,
   passing the full MIGRATION.md §2 scenario list end-to-end: boot and
   reach Healthy; SIM swap detected; SIM `app_state_detected` resolved
   by `soft_reset`; `not_registered_searching` resolved by `modem_reset`
   after one `soft_reset` (ladder progression); three-modem QMI hang
   triggers `driver_reset`; an RF event keeps the daemon out of
   destructive resets; `pkill -9 qmi-proxy` mid-cycle is detected via
   stderr `proxy_died` and recovered with one `driver_reset`. Replay-
   harness fault-cycle agreement against ≥30 days of v1 historical
   traces ≥95%.

**Carried forward from prior phases (locked, do not re-discuss):**

- `ActionKind.{MODEM_RESET, USB_RESET, DRIVER_RESET}` enum values exist
  (Phase 1); Phase 4 just appends to `actions/dispatcher.py:_REGISTRY`.
- `_DESTRUCTIVE_KINDS` set in `policy/gates.py`; `gate_signal`,
  `gate_exhausted`, `gate_ladder_backoff`, `gate_same_action_backoff`,
  `gate_disconnected`, `gate_maintenance` already wired and parameterised
  (Phase 2).
- `rf_blocked` orthogonal flag computed in `policy/transitions.py`
  (`is_signal_below_gate` → RSRP < -110 OR RSRQ < -15 OR SNR < 0); cheap
  actions still run when set (RECOVERY_SPEC §6.1).
- Decision table (`policy/decision_table.py`) already routes:
  `qmi_channel_hung → USB_RESET`, `session_disconnected → MODEM_RESET`,
  `qmi_proxy_died → DRIVER_RESET`, `operating_mode_offline → MODEM_RESET`,
  `operating_mode_low_power → MODEM_RESET`, `not_registered_searching →
  SOFT_RESET` (base), `not_registered_idle → SOFT_RESET` (base).
- `_global_driver_reset_eligible()` exists as Phase 2 placeholder
  returning False; engine path for cycle short-circuit + globals counter
  + last-driver-reset timestamp bump is in place
  (`policy/engine.py:76-106`).
- `GlobalsState` carries `driver_reset_count`,
  `last_driver_reset_monotonic`, `last_driver_reset_iso` —
  ready to consume.
- Replay harness (Plan 02-10) classifies safer-vs-less-safe partial
  order for destructive picks against v1 traces; Phase 2 hit 100% on
  952 synthetic fault fixtures.
- `spark-modem reset --action=<kind> --modem=<>` CLI scaffold exists
  (Plan 02-09 `cli/reset.py`); rejects destructive today via
  `is_registered()` check — Phase 4 just unblocks it.
- systemd unit ships `CapabilityBoundingSet=CAP_NET_ADMIN CAP_SYS_ADMIN
  CAP_SYS_MODULE CAP_DAC_READ_SEARCH` preallocated (Plan 03-08 U-01) —
  no unit-file edits needed mid-Phase-4.
- `QmiWrapper.dms_set_operating_mode("reset")` is what existing
  `soft_reset` calls (canonical Sierra single-pass reset).
- Phase 3 deferred bench-Jetson SC#1/#3/#4/#5 hardware verification +
  WatchdogSec=90s actual-fire to "Phase 4 HIL ticket" (STATE.md
  Deferred Items) — Phase 4 absorbs this into the HIL scenario suite.
- ADR-0012 lock model: CLI mutating `reset` invocation acquires the
  same per-modem flock the daemon does — already wired in Plan 02-09
  `ctl reset-state`; Phase 4 just enables destructive action kinds.
- Subprocess discipline: list-form argv only via `subproc/runner`;
  SP-04 lint enforces (Phase 1). Phase 4 adds `subproc.run(["modprobe",
  "-r", "qmi_wwan"])` etc. — same surface, no new subprocess module.

</domain>

<decisions>
## Implementation Decisions

### A. Destructive action implementation (FR-23, FR-24, FR-27)

- **A-01: modem_reset uses the SAME qmicli primitive as soft_reset
  (`--dms-set-operating-mode=reset`).** The Phase 4 distinction is
  policy-side: signal-gated, ladder-rung 2, verifies `operating_mode ==
  "online" + raw_ip == "Y"` on next-cycle observation. Sierra firmware
  does not expose a "harder" DMS reset variant; the difference between
  soft_reset and modem_reset is operational (gate, rung, expected
  outage), not protocol-level. New `actions/modem_reset.py` reuses the
  same `QmiWrapper.dms_set_operating_mode("reset")` call shape;
  registers in `_REGISTRY` keyed on `ActionKind.MODEM_RESET`.
- **A-02: usb_reset implemented via sysfs unbind/bind on the device's
  bus-port path.** New module `src/spark_modem/sysfs/` holds the file-
  write helpers (writes `<usb_path>` to `/sys/bus/usb/drivers/usb/unbind`,
  sleeps briefly, writes to `bind`). Needs `CAP_SYS_ADMIN` (preallocated
  by Plan 03-08 U-01). No `subproc.runner` involvement (file writes
  only); SP-04 lint untouched. Two variants: child-port (default) and
  parent-hub (used by `IssueDetail.SIERRA_BOOTLOADER` routing per A-06).
- **A-03: driver_reset implemented via two `subproc.run` calls:
  `["modprobe", "-r", "qmi_wwan"]` then `["modprobe", "qmi_wwan"]`.**
  Auto-handles dependencies (cdc_wdm, cdc_ncm). Needs `CAP_SYS_MODULE`
  (preallocated). Single action wraps both invocations; idempotent
  semantics naturally satisfied (second invocation finds module already
  removed/loaded — no-op). New `actions/driver_reset.py` registers in
  `_REGISTRY` keyed on `ActionKind.DRIVER_RESET`.
- **A-04: All four destructive actions return
  `VerifyResult.deferred(detail="next_cycle_observation")`.** Mirrors
  existing `actions/soft_reset.py` pattern. Dispatcher emits
  `ActionExecuted` on qmicli/sysfs ack; the next cycle's observation is
  the actual verifier — feeds the policy engine which sees either
  cleared issue (success) or persisting issue (failure → escalates to
  next ladder rung). modem_reset's 30-60s outage and usb_reset/
  driver_reset's device-disappearance windows cannot fit in NFR-1's 10 s
  P99 cycle — deferred verification is mandatory, not optional.
- **A-05: Idempotency contract — destructive actions are genuinely
  re-runnable.** Two `spark-modem reset --action=modem_reset
  --modem=cdc-wdm0` calls back-to-back both run to completion; the
  per-modem flock (ADR-0012) serializes them; end-state is identical
  (modem online, raw_ip=Y, healthy after re-registration). No
  "already in flight" failure mode at the dispatcher boundary. Honors
  PRD's "all recovery actions implemented as separate idempotent
  functions, runnable individually via CLI" phrasing (FR-27).
- **A-06: Sierra EM7421 stuck-in-bootloader (1199:9051) handled in
  Phase 4.** New `IssueDetail.SIERRA_BOOTLOADER` enum value;
  `inventory/` matches Sierra-VID `1199:*` (broader than `1199:9091` —
  Phase 3 Plan 03-02 already permits this); decision-table row routes
  `(IssueCategory.ENUMERATION, IssueDetail.SIERRA_BOOTLOADER) →
  ActionKind.USB_RESET` with the parent-hub variant flag set (per
  PITFALLS §1.6: full re-enumeration re-fires the boot transition; a
  child-port reset alone may not unstick the modem). New row in the
  decision table; new IssueDetail enum value (W-04 closed-enum
  discipline).

### B. Engine wiring: ladder + signal gate

- **B-01: New module `src/spark_modem/policy/ladder.py`.** Pure
  function `select_rung(category: IssueCategory, counters:
  dict[ActionKind, int], config: Settings) -> ActionKind |
  Literal["skip:exhausted"]`. Engine calls `lookup_action()` to
  identify the issue's BASE action; if base is in `{SOFT_RESET,
  MODEM_RESET, USB_RESET}` and the issue category is `REGISTRATION` or
  `(DATAPATH, SESSION_DISCONNECTED)`, `ladder.select_rung()` picks the
  actual rung based on per-action counters (`counters[SOFT_RESET]`,
  `counters[MODEM_RESET]`, `counters[USB_RESET]`) against config
  ceilings (`max_soft=3`, `max_modem=2`, `max_usb=1` defaults from
  RECOVERY_SPEC §4.1). Decision table stays a flat `(category, detail)
  → base ActionKind` map (no ladder noise). New tests in
  `tests/unit/policy/test_ladder.py` with one fixture per progression
  scenario from RECOVERY_SPEC §10.2.
- **B-02: Per-action timestamp split.** Add
  `ModemState.last_action_monotonic_by_kind: dict[ActionKind, float]`
  alongside existing `last_action_monotonic` (preserve for backwards-
  compat with Phase 2 state files; pydantic default `{}` via
  `Field(default_factory=dict)`). `gate_same_action_backoff` keys on
  the executed kind for the 300 s gate (FR-25);
  `gate_ladder_backoff` uses `MAX(timestamps over destructive kinds)`
  for the 90 s cross-action gate (FR-25.1). Phase 2 state files load
  cleanly (default empty dict). Engine bumps both `last_action_monotonic`
  AND `last_action_monotonic_by_kind[kind]` on action execution (RECOVERY_SPEC
  §8 atomic-write ordering preserved).
- **B-03: Signal-gate thresholds move from `Final` constants in
  `policy/transitions.py` to `Settings`.** New fields:
  `Settings.signal_rsrp_floor_dbm` (default -110),
  `Settings.signal_rsrq_floor_db` (default -15.0),
  `Settings.signal_snr_floor_db` (default 0.0). All tagged
  RELOAD_DATA (SIGHUP-tunable per Phase 3 L-03;
  `json_schema_extra={'reload': 'data'}` markers). `is_signal_below_gate()`
  reads from `PolicyContext.config`. Phase 5 field-shadow can re-tune per
  cohort if RF environments differ systematically.
- **B-04: New `ActionSkipped` event variant in `wire/events.py`.**
  Fields: `reason: SkipReason` (closed StrEnum:
  `signal_below_gate`, `ladder_backoff`, `same_action_backoff`,
  `exhausted`, `disconnected`, `maintenance`, `dry_run`),
  `suppressed_action: ActionKind`, `cause: Issue`,
  `usb_path: str`, `ts_iso: str`. Engine emits `ActionSkipped` in
  addition to existing `PlannedAction` (PlannedAction stays for
  back-compat with Plan 02-10's replay harness; new event is the
  consumer-friendly shape per SC#2's literal "action_skipped event"
  phrasing). Discriminated-union update to the `Event` tagged-union.

### C. driver_reset eligibility + Zao coordination (FR-24)

- **C-01: Eligibility denominator is total expected modems (4), NOT
  non-Zao-active.** Zao-active modems counted as 'not-hung'. With 2
  Zao-active + 2 hung, eligibility = 2/4 = 50%, doesn't fire.
  `driver_reset` only fires when most of the FLEET (not just the non-
  Zao-active subset) is observably broken. **Conservative deviation**
  from research's recommended denominator-of-non-Zao-active: a 60-second
  fleet-wide outage is heavy; the project's core value is minimum-
  impact recovery, so being slow-to-fire is operationally safer.
  `_global_driver_reset_eligible` reads expected modem count from
  `Settings.expected_modem_count` (default 4) and computes
  `hung_count / expected_count >= multi_modem_threshold_fraction`.
- **C-02: PROXY_DIED does NOT bypass the 75% threshold.**
  Individual-modem `qmi_proxy_died` issues still require the standard
  ≥75% gate. **Stricter than PITFALLS §1.1 recommendation.** Operational
  rationale: when proxy dies, all 4 modems will time out within ~8s
  (one cycle), so the gate fires naturally on the next cycle without
  needing a single-modem bypass. Decision table still routes
  `(QMI, QMI_PROXY_DIED) → DRIVER_RESET` for the per-modem path, but
  `_global_driver_reset_eligible` gates it on the 75% denominator like
  any other QMI hang.
- **C-03: thermal_warn / thermal_critical suppress driver_reset.**
  `_global_driver_reset_eligible` returns False if the cycle's host
  issues include any of `{IssueDetail.THERMAL_WARN,
  IssueDetail.THERMAL_CRITICAL}` (PITFALLS §17.4: Tegra under thermal
  throttle slows USB control transfers; qmicli timeouts spike; daemon
  classifies as `qmi_channel_hung`; root cause is thermal — driver_reset
  doesn't fix thermal). Cycle still emits per-modem qmi_channel_hung
  issues; per-modem `usb_reset` gates run normally (signal-gated +
  ladder-gated). NOC sees the thermal correlation in the same cycle's
  events.
- **C-04: No proactive Zao coordination on driver_reset.** No D-Bus
  subscribe to `zao-infra-ctrl.service` before kicking the driver. After
  modprobe -r/+ qmi_wwan, Zao detects QMI-call failure and restarts
  qmi-proxy on its own. Phase 5 bench-shadow will surface whether this
  creates flakiness; D-Bus subscription is an ADR-0014 candidate IF
  Phase 5 finds problems (PITFALLS §2.3 / §2.4 already flagged this as
  Phase 4-or-later candidate).
- **C-05: driver_reset cooldown.**
  `Settings.global_driver_reset_backoff_seconds` defaults to 3600 s
  (matches RECOVERY_SPEC §6.4). RELOAD_DATA tagged. Engine compares
  `clock.monotonic() - globals_state.last_driver_reset_monotonic`
  against the config value; Phase 2 already wires the timestamp.
- **C-06: Post-driver_reset counter behaviour: preserve.** Per-modem
  `counters` and `_healthy_streak` are NOT reset after a global
  driver_reset. Driver_reset is global, not per-modem; per-modem
  ladder progress is independent. After kernel reload, modems re-
  register and either go healthy (counters decay normally over K=10
  healthy cycles per ADR-0006) or remain hung (per-modem ladder
  continues from current rung). The cycle short-circuit (engine.py
  line 76-106 already implements) ensures per-modem actions don't
  race the driver_reset on the same cycle.

### D. HIL CI lane + Phase-3 piggyback + plan slicing

- **D-01: HIL execution model.** Self-hosted aarch64 runner from
  Plan 01-01, physically tethered to a bench Jetson with 4 EM7421s on
  USB hub 2-3.1.{1..4}. GitHub Actions workflow:
  - Trigger: `schedule: cron: '0 4 * * *'` (nightly 04:00 UTC) +
    `workflow_dispatch` (manual).
  - Concurrency: serial (single bench Jetson; never parallel).
  - Timeout: 90 min.
  - Artefacts: support bundle on failure
    (`spark-modem ctl support-bundle`); replay-harness diff report.
  Per-PR HIL is too slow (full scenario suite is ~45 min including
  modem-reset wallclocks); per-tag-only is too coarse (Phase 4 EXIT
  bar requires the green run before tagging).
- **D-02: Fault-injection toolkit — software-only, mixed.**
  - SIM-app issues: `qmicli --uim-sim-power-off` then `--uim-sim-power-on`.
  - QMI-hung scenarios: `pkill -9 qmi-proxy` (already in SC#4); also
    `qmicli --device-open-proxy` against a manually-detached cdc-wdm
    via prior `usb_reset`.
  - Registration loss: `qmicli --dms-set-operating-mode=offline` then
    let it sit; recover via `=online` or via the daemon's `modem_reset`.
  - Thermal / usb_overcurrent: synthetic kmsg writes via
    `printf '<6>foo: bar' > /dev/kmsg` with the 5 closed-enum patterns
    from Plan 03-05 `kmsg/classifier.py`.
  - **No real RF detuning hardware** (variable attenuator + antenna
    switch ~$2-5k; calibration drift; not in PROJECT.md budget).
    RF-blocked logic is validated via the synthetic-signal fixture
    path at the daemon-input layer (Phase 2 fixtures); HIL adds
    "destructive actions stay gated under rf_blocked=True" via a
    config-injected forced rf_blocked test scenario.
  Fault-injection helpers live in `tests/hil/fault_inject.py`;
  scenario specs in `tests/hil/scenarios/*.py`.
- **D-03: ≥30-day v1 historical traces stored as Git LFS artefact.**
  `tools/pull_replay_traces.py` resolves the LFS pointer at
  `tests/fixtures/replay/v1-30d/` to a privacy-redacted (sha256[:8]-
  hashed ICCID/IMSI/IP via the same redaction shape Plan 02-09's
  ctl support-bundle uses) snapshot. HIL job runs `pull_replay_traces.py`
  in setup phase; fails clearly on missing LFS auth (no silent skip).
  Replay harness from Plan 02-10 already understands fixture-directory
  shape — point it at the pulled directory. Trace pull cadence:
  refresh quarterly OR on parser changes that invalidate prior fixtures;
  documented in `tests/fixtures/replay/v1-30d/README.md` (which IS
  committed to the repo as the runbook for trace refresh).
- **D-04: Phase-3 deferred bench-SC verification folds into HIL
  scenario suite.** Single bench-Jetson run validates both Phase-3
  deferrals (boot-to-Healthy in 60 s; real qmi_wwan reload as clean
  state transition; SIGTERM ≤5 s with real flock release; concurrent
  `ctl reset-state` flock serialisation; WatchdogSec=90 s actual-fire
  under deliberately-wedged qmicli) AND Phase 4's net-new SC#4
  scenarios. Phase-3 scenarios live alongside Phase-4 scenarios in
  `tests/hil/scenarios/`; STATE.md "Deferred Items" entry resolves at
  Phase 4 EXIT.
- **D-05: Plan slicing — ~7 plans.**
  1. **modem_reset action + ladder rung-2 wiring** —
     `actions/modem_reset.py` registering existing
     `dms_set_operating_mode("reset")` qmi call as `MODEM_RESET` with
     deferred-verify shape; CLI `reset --action=modem_reset` unblocked.
  2. **usb_reset action + new `sysfs/` module + Sierra-bootloader
     handling** — `actions/usb_reset.py` calling new
     `sysfs/usb_unbind_rebind.py` (child-port + parent-hub variants);
     new `IssueDetail.SIERRA_BOOTLOADER`; decision-table row;
     inventory `1199:*` already in place from Plan 03-02.
  3. **driver_reset action + global eligibility predicate + thermal
     suppression + cooldown** — `actions/driver_reset.py` (modprobe
     -r/+); wire `_global_driver_reset_eligible` to real predicate
     (75% of total-4 denominator, no proxy-died bypass, thermal
     suppression, cooldown via `Settings.global_driver_reset_backoff_seconds`);
     globals counter + timestamp bump (Phase 2 wires already in place).
  4. **`policy/ladder.py` + per-action timestamps + signal-gate
     threshold migration to `Settings`** — new ladder.select_rung() pure
     function; `ModemState.last_action_monotonic_by_kind` field;
     `Settings.signal_rsrp_floor_dbm/rsrq_floor_db/snr_floor_db`;
     `is_signal_below_gate()` reads from PolicyContext.config; gates
     re-keyed off per-kind timestamps.
  5. **`ActionSkipped` event variant + decision-table and engine
     integration** — `wire/events.py` discriminated-union update;
     `wire/enums.py` `SkipReason` StrEnum; engine emits ActionSkipped
     alongside PlannedAction; replay harness back-compat shim.
  6. **HIL infra scaffold** — GitHub Actions workflow
     (`.github/workflows/hil.yml`); bench-Jetson topology doc at
     `tests/hil/README.md`; `tests/hil/fault_inject.py`;
     `tools/pull_replay_traces.py` + LFS pointer at
     `tests/fixtures/replay/v1-30d/`.
  7. **HIL scenario suite** — `tests/hil/scenarios/` with one file per
     scenario covering Phase 4 SC#4 (boot-to-Healthy; SIM-swap;
     soft_reset resolves SIM detected; modem_reset after one
     soft_reset; three-modem QMI hang triggers driver_reset; RF event
     keeps daemon out of destructive resets; pkill qmi-proxy recovered
     with one driver_reset) PLUS Phase-3 deferred SCs (real qmi_wwan
     reload as clean state transition; SIGTERM ≤5 s with flock
     release; concurrent ctl reset-state serialisation; WatchdogSec=90
     s actual-fire) PLUS replay-harness 30-day agreement gate ≥95%.

### Claude's Discretion

- **Exact module layout for `sysfs/`** — single file
  (`sysfs/usb.py`) vs split (`sysfs/__init__.py` + `usb_bind.py` +
  `usb_unbind.py`). Planner's call based on size.
- **CLI flag for parent-hub usb_reset variant** — `--target=parent-hub`
  vs `--parent-hub` boolean vs implicit-by-IssueDetail. Planner picks
  the cleanest argparse shape; CLI tests pin behaviour.
- **modprobe stderr/stdout handling for driver_reset** — distinguish
  "module busy" vs "module not loaded" vs other failures via
  `subproc.run`'s CompletedProcess.stderr scanning (PITFALLS §1.1
  pattern); exact regex for libkmod messages picked at implementation.
- **Per-modem timestamp dict initialisation on first action** — empty
  dict default OR pre-populated with all 6 cheap + 3 destructive kinds
  set to 0.0. Default-to-empty-dict has lower disk write churn; explicit
  population makes gate logic uniform. Planner's call.
- **HIL scenario cadence within the nightly run** — sequential vs
  parallel-where-safe (only the per-modem scenarios are safe to
  parallelise across cdc-wdm0..3; global scenarios like driver_reset
  must serialise). Planner picks based on wallclock budget.
- **Replay-harness 30-day fixture refresh process documentation** —
  the README content for `tests/fixtures/replay/v1-30d/README.md`
  describing how to regenerate from a fresh fleet pull is the
  planner's spec call.
- **`ActionSkipped` event vs `PlannedAction.suppressed_*` flags
  back-compat horizon** — Phase 4 emits BOTH; whether Phase 5 / 6
  drops the flags is a future decision.
- **Sierra-bootloader observation surface** — whether
  `IssueCategory.ENUMERATION` covers it (current) or it gets a new
  category. Reuse ENUMERATION for now; surfaces the IssueDetail enum
  value, no category churn.
- **Plan count exact** — 7 is the target; planner may consolidate to
  6 or split to 8 based on natural boundaries; 7 is the user-confirmed
  granularity preference matching Phase 1/2/3 scale (7-10 plans each).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor) MUST read these
before planning or implementing Phase 4.** Every entry is a full
relative path so the file can be read directly.

### Phase boundary, requirements, prior decisions

- `.planning/ROADMAP.md` §"Phase 4: Destructive Actions & HIL" — goal,
  3-requirement list (FR-23, FR-24, FR-27), four success criteria
  (SC#1..#4 covering action implementation, signal gate end-to-end,
  driver_reset eligibility, HIL CI lane).
- `.planning/REQUIREMENTS.md` §Traceability — FR-23 / FR-24 / FR-27
  Phase-4-mapped entries verbatim.
- `.planning/PROJECT.md` §"Active" §"Key Decisions" §"Constraints" —
  recovery escalation ladder, per-action escalation counter decay,
  signal-quality gate, hardware target.
- `.planning/STATE.md` "Deferred Items" — Phase-3 bench-SC verification
  + WatchdogSec actual-fire deferred to Phase 4 HIL ticket.
- `.planning/phases/01-foundations-adrs/01-CONTEXT.md` — Phase 1
  ActionKind / IssueCategory / IssueDetail / ModemState shape; wire
  package boundary; `subproc/runner` discipline.
- `.planning/phases/02-core-daemon-laptop-testable/02-CONTEXT.md` —
  Phase 2 actions/dispatcher pattern (M-06); policy/ pure-function
  engine seam; replay-harness shape (Plan 02-10).
- `.planning/phases/03-linux-event-sources-lifecycle/03-CONTEXT.md` —
  Phase 3 systemd hardening (CapabilityBoundingSet preallocation U-01);
  inventory `1199:*` matching (Plan 03-02); kmsg classifier (Plan
  03-05); SIM-swap atomic reset (Plan 03-07).
- `CLAUDE.md` §"Critical invariants" + §"Anti-patterns" — non-
  negotiable rules (one action per cycle; signal-quality gate on
  destructive only; pure policy engine; subproc list-form argv;
  match on ModemState).

### Action implementation (A-01..A-06)

- `docs/RECOVERY_SPEC.md` §2 (action catalogue with cost/idempotency/
  affects/when-useful), §4 (issue→action decision table — every row
  Phase 4 touches), §4.1 (escalation ladder soft→modem→usb→exhausted),
  §6.1 (signal-quality gate threshold values verbatim), §7
  (PlannedAction record shape), §8 (cycle algorithm + atomic-write
  ordering), §9 (idempotency / atomicity), §10.1..10.4 (worked
  examples for SIM-detected → soft_reset, registration ladder, three-
  modem QMI hang → driver_reset, RF event absorption).
- `docs/PRD.md` FR-22 (escalation ladder), FR-23 (signal gate), FR-24
  (driver_reset gate), FR-27 (idempotent functions), FR-28 (--dry-run
  everywhere).
- `docs/adr/0006-counter-decay.md` — counter decay-on-healthy
  semantics; preserve-counters-after-driver_reset rationale.
- `docs/adr/0008-state-machine-5-plus-2.md` — 5+2 ModemState shape;
  rf_blocked orthogonal flag.
- `docs/adr/0012-concurrency-locks.md` — per-modem flock acquisition
  shape used by CLI reset invocation; same-locks-as-daemon discipline.
- `.planning/research/PITFALLS.md` §1.1 (qmi-proxy crash leaves
  clients with stale CIDs — driver_reset is the only recovery; SC#4
  pkill scenario), §1.6 (Sierra EM7421 firmware bugs — stuck-in-
  bootloader, low_power-after-soft_reset, NV-restore-on-power-loss;
  parent-hub usb_reset prescription), §1.4 (qmicli mid-call SIGTERM
  cleanup; in_critical_section flag pattern), §1.5 (--device-open-proxy
  always; FR-74), §17.4 (thermal suppression of driver_reset).
- `src/spark_modem/actions/dispatcher.py` — registry append pattern;
  ActionPlanned / ActionExecuted / ActionFailed event emission shape;
  dry-run gate.
- `src/spark_modem/actions/soft_reset.py` — model for Phase 4
  destructive actions (deferred verify pattern; `dms_set_operating_mode("reset")`
  call shape).
- `src/spark_modem/actions/result.py` — ActionResult /
  VerifyResult shapes including `VerifyResult.deferred()`.
- `src/spark_modem/actions/context.py` — `ActionContext` (qmi /
  clock / config / carrier_table / event_logger / sysfs_root); Phase 4
  destructive actions read `ctx.sysfs_root` for usb_reset.
- `src/spark_modem/qmi/wrapper.py` — `dms_set_operating_mode` (used by
  soft_reset; Phase 4 modem_reset reuses); `_in_critical_section` flag
  set on state-changing calls; `classify()` PROXY_DIED detection.
- `src/spark_modem/wire/enums.py` — `ActionKind`, `IssueCategory`,
  `IssueDetail`; Phase 4 adds `IssueDetail.SIERRA_BOOTLOADER` +
  `SkipReason` enum.
- `src/spark_modem/wire/state.py` — `ModemState`; Phase 4 adds
  `last_action_monotonic_by_kind` field.

### Engine wiring: ladder + signal gate (B-01..B-04)

- `docs/RECOVERY_SPEC.md` §3 (state machine), §3.3 (counter decay),
  §4.1 (escalation ladder ceilings MAX_SOFT=3 / MAX_MODEM=2 /
  MAX_USB=1), §5 (priority order across categories), §6.1 (signal-
  quality gate verbatim values), §6.2 (same-action backoff), §6.3
  (cross-action ladder backoff).
- `src/spark_modem/policy/engine.py` — `run_cycle` 8-step ordering
  per RECOVERY_SPEC §8; `_apply_gates_to_action` gate ordering;
  `_global_driver_reset_eligible` Phase 2 placeholder Phase 4 wires.
- `src/spark_modem/policy/decision_table.py` — flat `(category,
  detail) → ActionKind` map; Phase 4 keeps it flat, ladder.py owns
  rung selection.
- `src/spark_modem/policy/gates.py` — `gate_signal`,
  `gate_same_action_backoff`, `gate_ladder_backoff`, `gate_exhausted`,
  `gate_disconnected`, `gate_maintenance`; Phase 4 keeps shapes,
  re-keys backoff gates off per-kind timestamps.
- `src/spark_modem/policy/transitions.py` — `is_signal_below_gate`;
  Phase 4 reads thresholds from `PolicyContext.config` (Settings)
  instead of module-level constants.
- `src/spark_modem/policy/context.py` — `PolicyContext` already carries
  `config: Settings`; no shape change.
- `src/spark_modem/wire/events.py` — Event tagged union; Phase 4 adds
  `ActionSkipped` variant with `kind="action_skipped"` discriminator.
- `src/spark_modem/wire/diag.py` — `PlannedAction.suppressed_*` flags
  retained for replay-harness back-compat; ActionSkipped is the
  consumer-friendly shape going forward.
- `src/spark_modem/config/settings.py` + `config/reload_marker.py` —
  Phase 4 adds `signal_rsrp_floor_dbm`, `signal_rsrq_floor_db`,
  `signal_snr_floor_db`, `global_driver_reset_backoff_seconds`,
  `multi_modem_threshold_fraction`, `expected_modem_count`,
  `max_soft`, `max_modem`, `max_usb` (all RELOAD_DATA tagged via
  `json_schema_extra={'reload': 'data'}`).

### driver_reset eligibility + Zao coordination (C-01..C-06)

- `docs/RECOVERY_SPEC.md` §6.4 (global driver-reset gate verbatim —
  ≥75% threshold, actionable-signal requirement, cooldown 3600 s).
- `docs/PRD.md` FR-24 (driver_reset gate).
- `docs/adr/0003-zao-authority.md` — never QMI-probe Zao-active line;
  Phase 4 honors this in the eligibility predicate (Zao-active modems
  are 'not-hung' in the denominator).
- `.planning/research/PITFALLS.md` §1.1 (qmi-proxy crash → driver_reset
  recovery; **user explicitly chose NOT to bypass 75% threshold for
  PROXY_DIED**, deviation from research recommendation), §2.3
  (qmi-proxy ownership transition on Zao restart — Phase 4 absorbs
  via Zao's own recovery; D-Bus subscription deferred to ADR-0014
  candidate if Phase 5 surfaces problems), §2.4 (race between Zao
  restart announcement and watchdog observation), §17.4 (thermal
  suppression of driver_reset).
- `src/spark_modem/wire/globals.py` — `GlobalsState.driver_reset_count`,
  `last_driver_reset_monotonic`, `last_driver_reset_iso` already
  wired; Phase 4 reads + bumps.
- `src/spark_modem/policy/engine.py:76-106` — driver_reset short-
  circuit path already implemented; Phase 4 wires
  `_global_driver_reset_eligible` to the real predicate.
- `src/spark_modem/wire/diag.py` — `Issue` / `WhoHost` / `WhoModem`
  surfaces consumed by the eligibility predicate.

### HIL CI lane + Phase-3 piggyback + plan slicing (D-01..D-05)

- `docs/MIGRATION.md` §2 (Phase 0 HIL scenario list — Phase 4's HIL
  scenarios trace to this list verbatim).
- `docs/TEST_STRATEGY.md` §2 (test layers — Phase 4 introduces
  Layer 4 HIL on real Jetson with real modems), §3 (fixture library
  shape), §6 (CI pipeline — Phase 4 adds nightly HIL job alongside
  per-PR unit/integration), §9 (deliberately NOT tested — real udev/
  rtnetlink/kernel covered by HIL).
- `.planning/research/PITFALLS.md` §12.1 (systemd hardening +
  capabilities — CAP_NET_ADMIN + CAP_SYS_ADMIN + CAP_SYS_MODULE +
  CAP_DAC_READ_SEARCH already preallocated by Phase 3 Plan 03-08
  U-01), §14.4 (HIL fixtures depending on a specific carrier — Phase 4
  uses 4-SIM mix; assertion thresholds over the bonded set, not per-
  modem; carrier-outage tolerance documented).
- `tests/hil/__init__.py` — Phase 4 stub directory ready to grow.
- `.github/workflows/` — Phase 1's self-hosted aarch64 runner config;
  Phase 4 adds `hil.yml` workflow.
- `tools/` — Phase 2's `gen_replay_fixtures.py` and replay harness
  shape (Plan 02-10); Phase 4 adds `pull_replay_traces.py` and
  reuses replay harness against the pulled v1-30d directory.
- `tests/fixtures/replay/` — Phase 2 synthetic-fixture root; Phase 4
  adds `v1-30d/` (LFS pointer + README).

### Cross-cutting / boundary discipline

- `scripts/lint_no_subprocess.sh` — SP-04 lint enforces no
  `create_subprocess_exec` / `subprocess.*` / `os.system` outside
  `subproc/`; Phase 4's modprobe calls go through `subproc.run`;
  `sysfs/` writes use plain `open()` + `os.write` (file writes, not
  subprocess) so SP-04 doesn't fire on them.
- `pyproject.toml` `[tool.pytest.ini_options].markers` — Phase 4 adds
  `hil` marker alongside `linux_only` (Plan 03-01); HIL job runs
  `pytest -m hil` exclusively, regular CI `pytest -m "not hil"`.
- `docs/adr/0010-packaging-python-build-standalone.md` — bundled
  CPython 3.12 in `.deb` venv; Phase 4 destructive actions still
  invoke `qmicli` and `modprobe` from system PATH (not bundled).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (from Phase 1 / 2 / 3)

- `src/spark_modem/actions/dispatcher.py` — `_REGISTRY` and
  `execute_and_verify(kind, who, ctx, *, dry_run)`. Phase 4 appends
  `MODEM_RESET / USB_RESET / DRIVER_RESET` entries — no dispatcher
  code change. Dry-run gate, ActionPlanned/Executed/Failed event
  emission already wired.
- `src/spark_modem/actions/soft_reset.py` — model for the four
  destructive actions: `execute() → ActionResult`, `verify() →
  VerifyResult.deferred(detail="next_cycle_observation")`. Phase 4's
  `modem_reset.py` reuses the exact same QmiWrapper call shape.
- `src/spark_modem/actions/result.py` — `ActionResult` /
  `VerifyResult.deferred()`; same shape for all four destructive actions.
- `src/spark_modem/actions/context.py` — `ActionContext` already
  carries `qmi`, `clock`, `config`, `carrier_table`, `event_logger`,
  `sysfs_root`. Phase 4 destructive actions read `ctx.sysfs_root`
  for usb_reset writes; tests inject `tmp_path`.
- `src/spark_modem/qmi/wrapper.py` —
  `dms_set_operating_mode("reset")` (used by soft_reset and modem_reset);
  `_in_critical_section` flag set on state-changing calls (Phase 3
  SIGTERM choreography reads it); `QmiWrapper.classify` returns
  `QmiErrorReason.PROXY_DIED` already.
- `src/spark_modem/policy/engine.py` —
  `_global_driver_reset_eligible()` Phase 2 placeholder ready for
  real-predicate wire; cycle short-circuit + globals counter/timestamp
  bump already implemented.
- `src/spark_modem/policy/gates.py` — `_DESTRUCTIVE_KINDS` set;
  signal/backoff/exhausted/disconnected/maintenance gates fully
  parameterised; Phase 4 re-keys backoff gates off per-kind timestamps
  (small refactor).
- `src/spark_modem/policy/transitions.py` —
  `is_signal_below_gate(snap)` reads RSRP/RSRQ/SNR; Phase 4 changes
  it to read thresholds from PolicyContext.config (move constants to
  Settings).
- `src/spark_modem/policy/context.py` — `PolicyContext` carries
  `config: Settings` and `clock: ClockProto`; no shape change.
- `src/spark_modem/policy/decision_table.py` — flat lookup;
  Phase 4 adds 1 row for `SIERRA_BOOTLOADER`, ladder-rung mapping
  lives in new `policy/ladder.py`.
- `src/spark_modem/wire/enums.py` — `ActionKind`, `IssueCategory`,
  `IssueDetail` closed StrEnums; Phase 4 adds `SIERRA_BOOTLOADER` +
  new `SkipReason` enum.
- `src/spark_modem/wire/state.py` — `ModemState` with
  `last_action_monotonic`; Phase 4 adds `last_action_monotonic_by_kind:
  dict[ActionKind, float] = Field(default_factory=dict)`.
- `src/spark_modem/wire/events.py` — discriminated union of Event
  variants; Phase 4 adds `ActionSkipped` with discriminator
  `kind="action_skipped"`.
- `src/spark_modem/wire/globals.py` — `GlobalsState` with
  driver_reset counter + timestamps; Phase 4 reads + bumps.
- `src/spark_modem/config/settings.py` + `config/reload_marker.py` —
  RELOAD_DATA / RELOAD_RESTART markers; Phase 4 adds 9 new fields
  (3 signal floors, 1 cooldown, 1 threshold fraction, 1 expected
  modem count, 3 ladder ceilings); all RELOAD_DATA tagged.
- `src/spark_modem/cli/reset.py` — already validates
  ActionKind + rejects destructive via `is_registered()`; Phase 4
  unblocks once destructive actions are registered. Phase 4 adds
  `--target=parent-hub` flag for usb_reset (or equivalent) to surface
  the variant.
- `src/spark_modem/state_store/store.py` — atomic-write +
  per-modem flock + state-store flock + 3-layer lock model already in
  place; Phase 4 actions touch state via the existing seam.
- `src/spark_modem/event_logger/writer.py` — append() consumes
  any Event variant; Phase 4 ActionSkipped flows through unchanged.
- `src/spark_modem/subproc/runner.py` — `run(argv, *, timeout_s)`
  shape; Phase 4 driver_reset uses `subproc.run(["modprobe", ...])`
  twice. Two-stage shutdown / `start_new_session=True` already in
  place.
- `tests/fakes/runner.py` — `FakeRunner` for subprocess fakes;
  Phase 4 HIL has its own real-runner path but units use FakeRunner.
- `tests/fakes/clock.py` + Phase 2 ClockProto — Phase 4 ladder /
  backoff tests use FakeClock with monotonic advancement.
- `src/spark_modem/inventory/sysfs.py` (Phase 2 sysfs walks) —
  Phase 4's new `sysfs/` module follows the same file-descriptor /
  Path discipline; cross-platform `skipif(win32)` for Linux-only paths.
- `tools/replay_harness.py` (Plan 02-10) — replay harness already
  classifies safer-vs-less-safe partial order; Phase 4 just points it
  at the LFS-pulled v1-30d directory and runs the agreement gate.

### Established Patterns

- All wire JSON via pydantic v2 `model_dump_json` /
  `model_validate_json`; Phase 4 ActionSkipped + ladder + per-kind
  timestamps follow the same boundary discipline (W-02).
- `asyncio` everywhere; no sync subprocess; no `gather + wait_for`;
  `match` on `ModemState.state`; closed enums for new IssueDetail /
  SkipReason values (anti-pattern catalogue from CLAUDE.md).
- `mypy --strict` + `ruff check` + `ruff format --check` green per
  module — Phase 4 extends to new `actions/modem_reset.py`,
  `actions/usb_reset.py`, `actions/driver_reset.py`,
  `policy/ladder.py`, `sysfs/usb_unbind_rebind.py`,
  `tests/hil/fault_inject.py`, `tools/pull_replay_traces.py`.
- SP-04 lint (`scripts/lint_no_subprocess.sh`) — Phase 4's
  `subproc.run(["modprobe", ...])` flows through `subproc/runner` (no
  bypass); `sysfs/` writes are plain file-descriptor I/O (not
  subprocess). Lint scope unchanged.
- Per-libqmi parser fixtures at
  `tests/fixtures/qmicli/<intent>/<version>/<scenario>.txt` are
  hardware-free; Phase 4 modem_reset reuses Phase 2's
  `dms_set_operating_mode` fixture set.
- Tests: `pytest` + `pytest-asyncio` (`mode=auto`) + `hypothesis` +
  `tmp_path` for filesystem; `FakeClock` for time; no global state.
- Windows dev-host friendliness: Phase 4's `sysfs/` writes are
  `tmp_path`-backed in unit tests; `tests/hil/` is `linux_only`-marked
  AND `hil`-marker-gated (skipif both not present).

### Integration Points

Phase 4 introduces these new package paths:

| Path | Owns |
|------|------|
| `src/spark_modem/actions/modem_reset.py` | MODEM_RESET execute/verify; reuses `dms_set_operating_mode("reset")` |
| `src/spark_modem/actions/usb_reset.py` | USB_RESET execute/verify (child-port + parent-hub variants) |
| `src/spark_modem/actions/driver_reset.py` | DRIVER_RESET execute/verify (modprobe -r/+ qmi_wwan) |
| `src/spark_modem/sysfs/__init__.py` | New package — sysfs file-write helpers |
| `src/spark_modem/sysfs/usb_unbind_rebind.py` | unbind + bind helpers (child-port + parent-hub) |
| `src/spark_modem/policy/ladder.py` | `select_rung(category, counters, config)` pure function |
| `tools/pull_replay_traces.py` | Git LFS pointer resolver for v1-30d traces |
| `tests/hil/fault_inject.py` | Fault-injection helpers (qmicli-direct, kmsg writes, pkill) |
| `tests/hil/scenarios/` | One file per HIL scenario (Phase 4 SC#4 + Phase-3 piggyback) |
| `.github/workflows/hil.yml` | Nightly + workflow_dispatch HIL job |
| `tests/fixtures/replay/v1-30d/` | LFS pointer + README for 30-day v1 historical traces |

Phase 4 EXTENDS these existing files:

| Path | Extension |
|------|-----------|
| `src/spark_modem/actions/dispatcher.py:_REGISTRY` | append 3 destructive entries |
| `src/spark_modem/wire/enums.py` | `IssueDetail.SIERRA_BOOTLOADER` + new `SkipReason` enum |
| `src/spark_modem/wire/events.py` | `ActionSkipped` variant in tagged union |
| `src/spark_modem/wire/state.py:ModemState` | `last_action_monotonic_by_kind` field |
| `src/spark_modem/policy/decision_table.py` | 1 row for SIERRA_BOOTLOADER; existing rows unchanged |
| `src/spark_modem/policy/engine.py:_global_driver_reset_eligible` | placeholder → real predicate (75% / signal / thermal / cooldown); per-kind counter bump on action execution; ActionSkipped emit |
| `src/spark_modem/policy/gates.py` | re-key backoff gates off `last_action_monotonic_by_kind` |
| `src/spark_modem/policy/transitions.py:is_signal_below_gate` | read thresholds from PolicyContext.config |
| `src/spark_modem/config/settings.py` | 9 new RELOAD_DATA fields |
| `src/spark_modem/cli/reset.py` | unblock destructive kinds; `--target=parent-hub` flag for usb_reset |
| `pyproject.toml` | `hil` pytest marker registration |

### Lint / quality gates extended in Phase 4

- `mypy --strict` extends to all new modules above.
- `ruff check` + `ruff format --check` extend.
- Existing `scripts/lint_no_subprocess.sh` continues to enforce; no
  new bypass paths.
- New gate: HIL job on the self-hosted aarch64 runner (`pytest -m
  hil`); separate from per-PR unit + integration suite. Nightly +
  manual workflow_dispatch.
- New gate: replay-harness 30-day agreement ≥95% (Phase 4 EXIT bar);
  runs as part of HIL job.
- New gate: SC#1 idempotency property test — `pytest`
  + `hypothesis` invokes each destructive action twice in a row and
  asserts identical observable end-state.

</code_context>

<specifics>
## Specific Ideas

The user accepted recommendations on most questions and explicitly
deviated on **two** driver_reset-eligibility questions to favor a more
conservative profile. Concrete specifics worth pinning:

- **modem_reset is a policy distinction, not a protocol distinction.**
  soft_reset and modem_reset both call `qmicli
  --dms-set-operating-mode=reset`. The difference is gating (modem_reset
  is signal-gated; soft_reset is not), ladder rung (rung 2 vs rung 1),
  and expected outage (~30-60 s vs ~5 s). Sierra firmware doesn't expose
  a "harder" DMS reset variant, so the spec's outage estimates are
  about how much we expect the modem to mutate, not about which qmicli
  verb we issue.
- **usb_reset is sysfs file I/O, not subprocess.** New `sysfs/` module
  does plain `open()` + `os.write()` to
  `/sys/bus/usb/drivers/usb/{un,}bind`. SP-04 lint scope unchanged
  because file writes aren't subprocess. Two variants: child-port
  (default, for SC#4 QMI-hung recovery) and parent-hub (for
  IssueDetail.SIERRA_BOOTLOADER recovery per A-06).
- **driver_reset is two `subproc.run` calls.** `["modprobe", "-r",
  "qmi_wwan"]` then `["modprobe", "qmi_wwan"]`. Idempotent at the
  invocation level — second run finds module already removed/loaded.
  No new wrapper module; flows through Phase 1 `subproc/runner`.
- **All four destructive actions return VerifyResult.deferred().**
  Mirrors existing soft_reset shape. The next cycle's observation is
  the actual verifier; modem comes back online (or doesn't) by then.
  Honors NFR-1 10 s P99 cycle (modem_reset's 30-60 s outage cannot fit
  in-cycle).
- **Idempotency means re-runnable, not single-flight.** Two
  back-to-back CLI invocations both run; per-modem flock serializes;
  end-state is identical. No "already in flight" failure mode at the
  dispatcher boundary. Honors PRD's "all recovery actions implemented
  as separate idempotent functions" phrasing literally.
- **Sierra-bootloader (1199:9051) gets a first-class IssueDetail and
  parent-hub usb_reset routing.** Inventory matches Sierra-VID `1199:*`
  (already in place from Phase 3 Plan 03-02). New
  `IssueDetail.SIERRA_BOOTLOADER`; new decision-table row; usb_reset
  `parent-hub` variant. PITFALLS §1.6 prescribes parent-hub for
  re-firing the boot transition.
- **policy/ladder.py is a new pure-function module.** `select_rung`
  signature: `(category: IssueCategory, counters: dict[ActionKind,
  int], config: Settings) -> ActionKind | Literal["skip:exhausted"]`.
  Engine calls `lookup_action()` for the base; if base is in
  destructive ladder kinds, ladder.select_rung() picks the actual rung
  based on counters. Decision table stays flat.
- **last_action_monotonic_by_kind is additive, not replacing.** Phase
  2 state files load cleanly (default empty dict via pydantic Field).
  same-action gate keys on the executed kind; ladder gate uses
  MAX(timestamps over destructive kinds). Single-source backwards-
  compat preserved.
- **Signal-gate thresholds move to Settings (RELOAD_DATA).** -110 dBm
  / -15 dB / 0 dB defaults match RECOVERY_SPEC §6.1 verbatim. SIGHUP
  re-tunable per Phase 3 L-03. is_signal_below_gate reads from
  PolicyContext.config.
- **ActionSkipped is a new event variant alongside PlannedAction
  (not replacing).** Discriminated-union update; closed-enum reason
  field; replay harness handles both for backwards-compat with Phase
  2 fixtures. SC#2's literal "action_skipped event" phrasing
  satisfied.
- **driver_reset denominator is total-4, not non-Zao-active.** *User
  deviation from research recommendation* — favors slow-to-fire over
  the 60 s fleet-wide outage. With 2 Zao-active + 2 hung, eligibility
  = 50%, doesn't fire. Project's core value is minimum-impact
  recovery; this choice trades off some recovery latency for
  conservatism on the destructive global action.
- **PROXY_DIED does NOT bypass the 75% threshold.** *User deviation
  from PITFALLS §1.1.* Operational rationale: when proxy dies, all 4
  modems will time out within ~8 s anyway, so the gate fires
  naturally on the next cycle. Per-modem decision table still routes
  proxy-died → DRIVER_RESET, but eligibility predicate gates it on
  the standard threshold. Stricter gate; consistent with the
  conservative driver_reset profile.
- **thermal_warn / thermal_critical suppresses driver_reset.** Per
  PITFALLS §17.4. Cycle still emits per-modem qmi_channel_hung issues;
  per-modem usb_reset gates run normally. NOC sees thermal correlation
  in the same cycle.
- **No proactive Zao coordination on driver_reset.** Zao detects
  failure on its next QMI call after kernel reload; restarts qmi-proxy
  on its own. D-Bus subscription deferred to Phase 5 surfacing /
  ADR-0014 candidate.
- **Cooldown is 3600 s in Settings (RELOAD_DATA).** Matches
  RECOVERY_SPEC §6.4 verbatim.
- **Post-driver_reset: preserve per-modem counters and streak.**
  Driver_reset is global; per-modem ladder progress is independent. A
  modem at usb-rung pre-reset stays at usb-rung post-reset; counter
  decay is the way back per ADR-0006.
- **HIL nightly + workflow_dispatch on the Phase 1 self-hosted
  aarch64 runner.** Tethered bench Jetson with 4 EM7421s. NOT per-PR
  (45 min suite is too slow). NOT per-tag-only (Phase 4 EXIT bar
  requires green run before tagging — circular).
- **Fault injection is software-only.** qmicli-direct, pkill -9
  qmi-proxy, scripted SIM power off/on, dms-set-operating-mode=offline,
  synthetic /dev/kmsg writes. NO real RF detuning hardware. RF-blocked
  validated via synthetic-signal fixtures + config-injected forced
  rf_blocked HIL scenario.
- **30-day v1 traces via Git LFS.** sha256[:8]-redacted ICCID/IMSI/IP;
  LFS pointer at `tests/fixtures/replay/v1-30d/`; pulled in HIL setup
  phase via `tools/pull_replay_traces.py`. Quarterly refresh cadence
  documented in committed README.
- **Phase-3 piggyback folds into HIL scenario suite.** Single
  bench-Jetson run validates Phase-3 deferrals (boot-to-Healthy,
  qmi_wwan reload, SIGTERM ≤5 s, ctl reset-state flock, WatchdogSec=
  90 s actual-fire) AND Phase-4 net-new SC#4 scenarios.
- **~7 plans target.** Per-action × 3 + engine wiring + ActionSkipped +
  HIL infra + HIL scenarios. 1 plan per cleanly-bounded change-set;
  consistent with Phase 1/2/3 scale.

</specifics>

<deferred>
## Deferred Ideas

Items mentioned during analysis or surfaced during scope policing that
belong outside Phase 4. None lost.

### Phase 5 (Bench & Field Shadow)

- Surface real-fleet rate of Sierra EM7421 stuck-in-bootloader
  (1199:9051) — Phase 4 ships the routing; Phase 5 measures.
- D-Bus subscription to zao-infra-ctrl.service state — if Phase 5
  bench-shadow surfaces flakiness from Zao restart racing
  driver_reset, ADR-0014 candidate. Phase 4 absorbs Zao's own
  recovery; this is the safer first cut.
- Real-fleet RF-environment thresholds — RSRP/RSRQ/SNR floors are
  RELOAD_DATA tunable; Phase 5 cohorts may reveal that some
  geographies need different floors. No code change needed; YAML
  edit + SIGHUP.
- Replay-harness trace refresh from real fleet — Phase 4 commits the
  process via tools/pull_replay_traces.py + LFS; Phase 5 begins the
  quarterly refresh cadence. ICCID/IMSI/IP redaction pipeline is the
  same shape as Phase 2 ctl support-bundle's sha256[:8] redaction.
- Bench-Jetson HIL hardware refresh / SIM-cycle process — Phase 4
  ships the HIL job with assumptions about SIM availability; Phase 5
  field-shadow may surface need for SIM-cycle automation
  (PITFALLS §14.4 carrier-outage tolerance).

### v2.1 (already deferred in REQUIREMENTS.md)

- HTTP control plane (CTL-01, CTL-02) — destructive-action invocation
  via HTTP POST. v2.0 keeps CLI-only.
- `ctl simulate-issue` (SIM-01) — would be a cleaner fault-injection
  surface than the synthetic /dev/kmsg writes Phase 4 uses.
- 5G NR-aware policy (NR-01) — RSRP/RSRQ thresholds today are LTE-
  centric; NR has different signal metrics (RSRP/RSRQ exist but
  `ss_sinr_db` is also relevant). Phase 4 keeps LTE-only.

### Tactical / Claude-discretion (handled during planning)

- Exact module layout for `sysfs/` (single file vs split).
- CLI flag shape for parent-hub usb_reset variant (`--target=parent-hub`
  vs boolean vs implicit).
- modprobe stderr regex for distinguishing busy / not-loaded / other
  failures.
- Per-modem timestamp dict initialisation (empty default vs pre-
  populated).
- HIL scenario sequencing within the nightly run (sequential vs
  parallel-where-safe).
- README content for `tests/fixtures/replay/v1-30d/README.md`.
- Plan count exact (6 / 7 / 8).
- Sierra-bootloader IssueCategory placement (ENUMERATION vs new).

### Possibly deferred to Phase 5/6 if Phase 4 bench access slips

- Real-hardware verification of WatchdogSec=90 s actual-fire (Phase 3
  deferred this; Phase 4 absorbs via HIL — but if HIL bench-Jetson is
  unavailable mid-Phase-4, this slips again).
- Real-hardware verification of cross-process flock concurrent ctl
  reset-state serialisation (same).

### Unrelated future work

- ADR-0014 candidate: "D-Bus subscription to zao-infra-ctrl.service for
  qmi-proxy ownership transitions" if Phase 5 surfaces problems.
- Per-MCC signal-gate threshold override in carrier table — premature
  per Phase 4 discussion; revisit if Phase 5 reveals systematic
  carrier-specific RF environments.
- ActionSkipped vs PlannedAction.suppressed_* flags deprecation
  horizon — Phase 4 emits both for back-compat; Phase 5/6 may drop
  flags after consumers migrate.
- ML-on-signal predictive recovery — out-of-scope per PROJECT.md NG /
  AF-11.
- HIL real-RF detuning hardware budget request — Phase 5 may surface
  that synthetic-signal fixtures are insufficient; budget request to
  Phase 6 if so.

</deferred>

---

*Phase: 04-destructive-actions-hil*
*Context gathered: 2026-05-10*
