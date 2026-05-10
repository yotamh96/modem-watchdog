# Phase 4: Destructive Actions & HIL - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-10
**Phase:** 04-destructive-actions-hil
**Areas discussed:** Action implementation + verify/idempotency, Engine wiring: ladder + signal gate, driver_reset eligibility + Zao coordination, HIL CI lane + Phase-3 piggyback + plan slicing

---

## Gray-area selection

| Option | Description | Selected |
|--------|-------------|----------|
| Action implementation + verify/idempotency | modem_reset/usb_reset/driver_reset method + verify shape + idempotency contract + Sierra firmware quirks | ✓ |
| Engine wiring: ladder + signal gate | ladder rung selection + per-action timestamp split + signal-gate threshold ownership + ActionSkipped event | ✓ |
| driver_reset eligibility + Zao coordination | denominator + proxy_died bypass + thermal suppression + Zao coord + cooldown + post-reset counter behaviour | ✓ |
| HIL CI lane + Phase-3 piggyback + plan slicing | execution model + fault-injection toolkit + 30-day v1 traces + plan slicing | ✓ |

**User's choice:** All four areas selected.
**Notes:** No deferred areas; user opted to discuss the full scope.

---

## Action implementation + verify/idempotency

### Q: How should modem_reset be implemented at the qmicli layer?

| Option | Description | Selected |
|--------|-------------|----------|
| Same primitive as soft_reset (--dms-set-operating-mode=reset), distinguished by gating + verification only | Sierra firmware doesn't expose a "harder" DMS reset; difference is operational not protocol | ✓ |
| offline→sleep→online operating-mode cycle | Forces more thorough RF teardown; PITFALLS §1.6 warns of low_power-after-soft_reset | |
| Fresh QmiWrapper method (e.g. dms_full_reset) using --dms-reset action ID | Reduces parser-fixture reuse from Phase 2 | |

**User's choice:** Recommended — same primitive, policy-side distinction.

### Q: How should usb_reset be implemented?

| Option | Description | Selected |
|--------|-------------|----------|
| Sysfs unbind/bind via /sys/bus/usb/drivers/usb/{un,}bind on the device's bus-port path | Cleanest; no new userspace tools; PITFALLS §12.1 prescription | ✓ |
| USBDEVFS_RESET ioctl on /dev/bus/usb/<bus>/<dev> | More invasive; ioctl wrapper needed; closer to physical replug | |
| Authorize toggle (echo 0/1 to /sys/.../authorized) | Less invasive; thin precedent | |
| Parent-hub port unbind | More aggressive; specifically called for stuck-in-bootloader recovery | |

**User's choice:** Recommended — sysfs unbind/bind. Parent-hub variant retained for Sierra-bootloader routing per A-06.

### Q: How should driver_reset be implemented?

| Option | Description | Selected |
|--------|-------------|----------|
| modprobe -r qmi_wwan && modprobe qmi_wwan via subproc.run | Canonical; auto-handles dependencies; needs CAP_SYS_MODULE (preallocated) | ✓ |
| Per-device sysfs unbind from qmi_wwan driver, then unbind/bind module | More surgical but harder idempotency | |
| rmmod qmi_wwan && modprobe qmi_wwan (no auto-deps) | EBUSY risk; no real benefit | |

**User's choice:** Recommended — modprobe -r/+ qmi_wwan.

### Q: What does verify() return for each destructive action?

| Option | Description | Selected |
|--------|-------------|----------|
| All four destructive actions return VerifyResult.deferred(); next-cycle observation surfaces outcome | Mirrors soft_reset; honors NFR-1 10s P99 cycle (modem_reset's 30-60s outage cannot fit in-cycle) | ✓ |
| modem_reset inline-verifies; usb_reset/driver_reset deferred | Mixed pattern; harder to test uniformly; breaks 10s cycle | |
| All inline-verify with timeouts; cycle pipeline runs destructive actions in separate task | More machinery; arguably better observability | |

**User's choice:** Recommended — all deferred.

### Q: What does SC#1 'invoked twice in a row without producing a different outcome' mean operationally?

| Option | Description | Selected |
|--------|-------------|----------|
| Action is genuinely re-runnable; second call re-executes and produces same observable end-state | Per-modem flock serializes; matches PRD's "idempotent functions runnable individually via CLI" phrasing | ✓ |
| Second call within ladder-backoff window returns succeeded=True with reason='no-op_in_window' | Hides operator intent | |
| Second call rejected with already-in-flight error if first hasn't returned | Adds new error path; inconsistent with idempotent language | |

**User's choice:** Recommended — genuinely re-runnable.

### Q: How should Sierra EM7421 stuck-in-bootloader (1199:9051) be handled in Phase 4?

| Option | Description | Selected |
|--------|-------------|----------|
| Add IssueDetail.SIERRA_BOOTLOADER + parent-hub usb_reset routing now | Per PITFALLS §1.6; matches "fix it once, surface in metrics" philosophy | ✓ |
| Defer to Phase 5 field-shadow when we can observe real rates | Save the enum-value churn if zero incidence | |
| Add IssueDetail.SIERRA_BOOTLOADER but route to standard usb_reset (child port) | Less aggressive; child-port may not unstick | |

**User's choice:** Recommended — add now with parent-hub routing.

---

## Engine wiring: ladder + signal gate

### Q: Where should the ladder rung-selection logic (counter → ActionKind) live?

| Option | Description | Selected |
|--------|-------------|----------|
| New module policy/ladder.py with select_rung() pure function | Co-located with engine + decision_table + gates; spec-testable in isolation | ✓ |
| Inline in engine.run_cycle as a private helper | Single file but engine.py grows; harder to spec-test | |
| Extend decision_table.py with ladder-aware lookup_action() | Couples lookup with state; breaks flat-table spec-as-tests property | |

**User's choice:** Recommended — new policy/ladder.py module.

### Q: How should the per-action timestamp split be structured?

| Option | Description | Selected |
|--------|-------------|----------|
| Add ModemState.last_action_monotonic_by_kind: dict[ActionKind, float] alongside existing last_action_monotonic | Backwards-compat with Phase 2 state files; cleanest gate semantics | ✓ |
| Replace last_action_monotonic with last_action_monotonic_by_kind only | Cleaner long-term but breaks Phase 2 state files | |
| Keep single last_action_monotonic; redefine same-action gate semantics | Avoids schema change; messier semantics | |

**User's choice:** Recommended — additive field.

### Q: Where should signal-gate RSRP/RSRQ/SNR thresholds live?

| Option | Description | Selected |
|--------|-------------|----------|
| Move to Settings (config.signal_rsrp_floor_dbm, etc.), RELOAD_DATA tagged | SIGHUP-tunable per Phase 3 L-03; defaults match RECOVERY_SPEC §6.1 | ✓ |
| Keep as Final constants in transitions.py | Locks values at spec layer; precludes operator-driven recalibration | |
| Per-MCC override in carriers.yaml; default in Settings | Premature; thresholds are physics-driven not carrier policy | |

**User's choice:** Recommended — move to Settings.

### Q: How should the signal-gate skip be surfaced (SC#2 'action_skipped event')?

| Option | Description | Selected |
|--------|-------------|----------|
| Add ActionSkipped event variant to wire/events.py with reason: enum + suppressed_action: ActionKind | First-class variant; matches SC#2 literal phrasing; cleaner consumer side | ✓ |
| Keep existing PlannedAction.suppressed_by_signal_gate flag; emit ActionPlanned with reason='skip:signal_below_gate' | No schema bump but doesn't match SC's wording | |
| Both: add ActionSkipped variant AND keep suppressed_by flags | Belt-and-suspenders; doubled volume | |

**User's choice:** Recommended — new ActionSkipped variant. Existing PlannedAction.suppressed_* flags retained for replay-harness back-compat per CONTEXT.md.

---

## driver_reset eligibility + Zao coordination

### Q: How should Zao-active modems factor into the ≥75% qmi_channel_hung denominator?

| Option | Description | Selected |
|--------|-------------|----------|
| Denominator excludes Zao-active modems (75% of NON-Zao-active modems hung) (Recommended) | Honors "fire when modems we can see are mostly broken" | |
| Denominator is total expected modems (4); Zao-active counted as 'not-hung' | Conservative: with 2 Zao-active + 2 hung, eligibility=50%, doesn't fire | ✓ |
| Denominator is total; Zao-active counted as 'hung' (assume worst) | Aggressive; risks driver_resets without observable evidence | |

**User's choice:** Total-of-4 denominator with Zao-active counted as 'not-hung'. **Deviation from research recommendation** — favors slow-to-fire to honor minimum-impact-recovery.

### Q: Should qmi_proxy_died bypass the ≥75% threshold (PITFALLS §1.1)?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — detected PROXY_DIED on ANY modem fires driver_reset on next cycle, subject to cooldown only (Recommended) | Per PITFALLS §1.1 prevention | |
| No — proxy_died still requires the ≥75% threshold like other QMI hangs | Stricter; relies on all 4 modems timing out within ~8s naturally | ✓ |
| Yes, but only if proxy_died observed on ≥2 modems | Compromise; adds threshold for no diagnostic gain | |

**User's choice:** Stricter — no bypass. **Deviation from PITFALLS §1.1 recommendation** — consistent with the conservative driver_reset profile.

### Q: Should thermal_warn host issue suppress driver_reset (PITFALLS §17.4)?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes — thermal_warn or thermal_critical active in this cycle suppresses driver_reset eligibility | Per PITFALLS §17.4; thermal-throttled USB control transfers cause false QMI hangs | ✓ |
| No — thermal observability is informational only | Risks wasted reset when thermal is the real cause | |
| Yes, but only thermal_critical (not thermal_warn) | warn IS the operational signal that USB transfers are slowing | |

**User's choice:** Recommended — both thermal_warn and thermal_critical suppress.

### Q: How should Zao restart be coordinated with driver_reset?

| Option | Description | Selected |
|--------|-------------|----------|
| No proactive coordination — absorb Zao's own recovery; daemon emits StateTransition + DriverResetExecuted | Simplest; Zao detects failure on next QMI call and restarts qmi-proxy | ✓ |
| Proactive D-Bus coordination | Tighter integration; depends on Zao SDK D-Bus stability (PITFALLS §2.3 low confidence) | |
| Pre-flight check: defer if zao-infra-ctrl.service is reloading | Mostly defensive; smaller surface than option 2 but still adds D-Bus client | |

**User's choice:** Recommended — no proactive coordination. D-Bus subscription deferred to Phase 5 ADR-0014 candidate if needed.

### Q: What's the driver_reset cooldown default and where does it live?

| Option | Description | Selected |
|--------|-------------|----------|
| 3600s (1 hour) default; Settings.global_driver_reset_backoff_seconds, RELOAD_DATA tagged | Matches RECOVERY_SPEC §6.4 verbatim | ✓ |
| 1800s (30 min) default | Tighter window; contradicts spec without ADR amendment | |
| Configurable; no spec default (operator must set) | Fails closed; inconsistent with other settings | |

**User's choice:** Recommended — 3600s default, RELOAD_DATA tagged.

### Q: After driver_reset fires, what happens to per-modem counters and healthy_streak?

| Option | Description | Selected |
|--------|-------------|----------|
| Preserve counters and healthy_streak; treat driver_reset as one cycle's intervention | Per-modem ladder progress is independent; counter decay is the way back per ADR-0006 | ✓ |
| Reset all per-modem _healthy_streak to 0 and counters to {} (clean slate) | Risk: a modem at usb-rung silently drops to soft-rung | |
| Reset only counters (not _healthy_streak) | Surgical but RECOVERY_SPEC §3.3 doesn't currently distinguish | |

**User's choice:** Recommended — preserve.

---

## HIL CI lane + Phase-3 piggyback + plan slicing

### Q: Where does the HIL job execute and at what cadence?

| Option | Description | Selected |
|--------|-------------|----------|
| Self-hosted aarch64 runner from Phase 1 + tethered bench Jetson; nightly schedule + manual trigger | Reuses Phase 1 infra; nightly catches drift between PRs without blocking dev velocity | ✓ |
| Per-PR HIL on PRs touching actions/policy | Path-filtered but indirect breakage missed; concurrent PRs queue | |
| Per-tag-only (release blocking) | Drift surfaces only at release; circular with Phase 4 EXIT bar | |
| Separate HIL workflow on dedicated machine | Decouples but duplicates infra effort | |

**User's choice:** Recommended — self-hosted aarch64 + nightly + manual.

### Q: What's the fault-injection toolkit for the HIL scenarios?

| Option | Description | Selected |
|--------|-------------|----------|
| Mix: qmicli-direct + pkill -9 qmi-proxy + scripted SIM removal + synthetic kmsg writes | Cheapest tool per scenario; software-only; reproducible | ✓ |
| Add real RF detuning (variable attenuator + antenna switch) for SC#2 | Most realistic but $2-5k hardware + drift + flakiness; not in PROJECT.md budget | |
| All synthetic via /dev/kmsg + qmicli-fixture-dir + fake QMI responses | Defeats the point of HIL | |

**User's choice:** Recommended — software-only mixed toolkit.

### Q: Where do the ≥30 days of v1 historical traces live?

| Option | Description | Selected |
|--------|-------------|----------|
| Pull as Git LFS artifact; tools/pull_replay_traces.py grabs latest fleet snapshot on first checkout | Privacy-redacted (sha256[:8]); doesn't bloat repo; LFS surfaces auth issues clearly | ✓ |
| Commit redacted traces directly to repo | Self-contained but tens-to-hundreds of MiB repo bloat | |
| S3 / artifact-store URL fetch in CI | Hidden auth dependency; cryptic errors for new devs | |
| Defer to Phase 5 (Phase 4 ships replay against synthetic 1002 fixtures only) | Contradicts SC#4 explicit requirement | |

**User's choice:** Recommended — Git LFS.

### Q: How should Phase-3 deferred bench-SC verification + plan slicing be structured?

| Option | Description | Selected |
|--------|-------------|----------|
| Fold Phase-3 piggyback into HIL scenario suite; ~7 plans total | Single bench-Jetson run validates both; consistent with Phase 1/2/3 plan scale | ✓ |
| Separate Phase-3 piggyback into its own plan; ~8 plans total | Cleaner attribution; marginal benefit | |
| Fewer, bigger plans (4-5) | Less plan-management overhead but unwieldy plans; deviates from precedent | |

**User's choice:** Recommended — fold Phase-3 into HIL scenarios; ~7 plans.

---

## Claude's Discretion

Areas where the user said "you decide" or where the recommendation note already deferred to planner judgement:

- Exact module layout for `sysfs/` (single file vs split).
- CLI flag shape for parent-hub usb_reset variant (`--target=parent-hub` vs boolean vs implicit-by-IssueDetail).
- modprobe stderr regex for distinguishing busy / not-loaded / other failures.
- Per-modem timestamp dict initialisation on first action (empty default vs pre-populated).
- HIL scenario sequencing within the nightly run (sequential vs parallel-where-safe).
- README content for `tests/fixtures/replay/v1-30d/README.md`.
- Plan count exact (6 / 7 / 8 — 7 is the user-confirmed target, planner may consolidate or split based on natural boundaries).
- Sierra-bootloader IssueCategory placement (ENUMERATION reused, not a new category).

## Deferred Ideas

Mentioned during discussion but belong outside Phase 4 — see CONTEXT.md `<deferred>` section for the full list. Highlights:

- D-Bus subscription to zao-infra-ctrl.service (ADR-0014 candidate if Phase 5 surfaces problems).
- Per-MCC signal-gate threshold override in carrier table.
- Real-RF detuning hardware budget request.
- ActionSkipped vs PlannedAction.suppressed_* flags deprecation horizon.
- HTTP control plane for destructive-action invocation (v2.1).
- 5G NR-aware policy + signal metrics (NR-01, v2.1).
