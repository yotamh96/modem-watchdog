# PITFALLS research — spark-modem-watchdog v2

**Domain:** On-device LTE modem health watchdog / recovery daemon
**Hardware:** NVIDIA Jetson Orin NX, 4× Sierra EM7421, USB 3 hub, Tegra L4T R35.6.4
**Stack:** Single-process Python 3.12 asyncio daemon, `python-build-standalone`-bundled venv, qmicli wrapper, Zao bonding integration
**Researched:** 2026-05-05
**Overall confidence:** HIGH on libqmi/qmi-proxy, asyncio/subprocess, prometheus cardinality, systemd; MEDIUM on Sierra EM7421 firmware specifics, Tegra USB3-hub interactions; LOW on Zao SDK internals (we are guessing about a closed-source counterparty).

---

## How to read this document

The seven ADRs in `docs/adr/` already enumerate the **known** pitfalls — language hybrid, free-form `detail`, never-decay counters, wall-clock backoff, polling-only, command injection, no tests. Those are not repeated here. This document catalogues the **next-tier** pitfalls: things that bite production cellular-modem watchdogs but are not in the docs/, plus places where the v2 rewrite will likely **introduce new pitfalls** beyond the ones it explicitly fixes.

Each pitfall has:
- **Probability** (low / med / high) — how likely it bites in production
- **Severity** (low / med / high) — how bad it is when it does
- **Origin** — `[v1-carryover]` (existed before, ADRs may not catch all variants), `[new-in-v2]` (rewrite-introduced), `[domain]` (intrinsic to this product space)
- **Warning signs** — concrete metric / log / event that surfaces it
- **Prevention** — code/design/test artifact that prevents it
- **Phase** — Phase 0 (build/HIL), Phase 1 (bench shadow), Phase 2 (field shadow), Phase 3 (one box live), Phase 4 (canary), Phase 5 (rollout), Post-launch

Critical → Moderate → Minor ordering inside each section. Sections roughly correspond to the 18 categories in the question.

---

## 1. qmicli / libqmi / qmi-proxy pitfalls

### 1.1 qmi-proxy crash leaves clients with stale CIDs (CRITICAL) [v1-carryover]
**Prob: med · Sev: high**

When `qmi-proxy` dies, libqmi cannot transparently rebuild the proxy because allocated client IDs (CIDs) and outstanding transaction IDs are lost with it. Subsequent `qmicli --device-open-proxy` calls either time out or return `Internal` errors with no clean way for the daemon to recover except a `driver_reset` (qmi_wwan reload).

**Warning signs:**
- Burst of `qmicli` exit non-zero with `couldn't create client for the 'dms' service: QMI protocol error (3): 'Internal'` in the journal.
- `spark_modem_qmi_probe_duration_seconds` P99 climbs above the 8 s task timeout for ≥2 modems simultaneously.
- `spark_modem_actions_total{kind="driver_reset"}` increment without a clear preceding event.

**Prevention:**
- Detect `Internal` / `ClientIdsExhausted` / `couldn't create client` substrings in qmicli stderr in `qmi/parsers.py`; map to a typed `QmiError(reason="proxy_died")`.
- `qmi-proxy` death is the only error pattern that should bypass per-modem same-action backoff and trigger a global `driver_reset` even with <75% modems hung — extend RECOVERY §6.4 with a `qmi_proxy_died` short-circuit.
- Phase 0 fixture: capture qmicli stderr after `pkill -9 qmi-proxy` mid-call; assert parser maps it to the right error type.
- Phase 0 HIL: kill qmi-proxy mid-cycle and verify daemon recovers with one `driver_reset`, not a thrash.

**Phase:** Phase 0 fixture; Phase 0 HIL scenario.

---

### 1.2 qmicli output drift between libqmi 1.30 and 1.32+ (CRITICAL) [domain]
**Prob: med · Sev: high**

The docs/ commits to wrapping `qmicli` text output. libqmi 1.30 (Ubuntu 20.04 focal-updates) prints e.g. `Operating mode: 'online'`; 1.32 added structured fields for some commands and reformatted `--nas-get-signal-info` to include 5G/NR sections that 1.30 does not emit. A field box updated via apt-cache to a libqmi point-release that adds a field can break the parser silently if we accept "extra fields = warn but proceed". A field box that *removes* a field we depend on (rare but happens, e.g. `serving_system` reformatting in 1.32.4) silently regresses observation.

**Warning signs:**
- `events.jsonl` `error` events from `module:"qmi"` operation `parse` with `error:"unknown_section"`.
- `spark_modem_qmi_probe_duration_seconds{intent="get_signal"}` distribution shifts measurably between fleet revisions.
- A specific modem's `signal` field in `Diag` becomes `null` on a subset of boxes after a cohort upgrade.

**Prevention:**
- Pin libqmi version expectation in config (`qmi.expected_libqmi_version: "1.30"`); on startup, run `qmicli --version`, log `qmi_version` event; fail-warn (not fail-closed) on mismatch.
- `qmi/parsers.py` has a fixture per supported libqmi version; CI runs the parser against all of them.
- Capture qmicli output verbatim via `--qmi-fixture-dir=PATH` flag (FR-51) on a real fleet box once per release for replay.
- A new field is `extra=ignore` in pydantic; a missing field is a typed `MissingField` error, **not** a silent `None`.
- Phase 0: record fixtures from 1.30, 1.30.4, 1.32 (if any field box has it).

**Phase:** Phase 0 fixture capture; Phase 1 daily compare report flags drift.

---

### 1.3 qmicli locale dependency (MODERATE) [domain]
**Prob: low · Sev: high**

qmicli's text output uses `gettext` and follows `LC_MESSAGES` / `LC_ALL`. A box with `LANG=he_IL.UTF-8` (Israel deployment!) or `LC_ALL=C.UTF-8` formats `Operating mode: 'online'` as `מצב הפעלה:` (Hebrew) or as the unset-locale variant. The parser would silently see no matches.

**Warning signs:**
- All four modems report `qmi.responsive=false` immediately after a system locale change or a re-imaged box.
- `LANG`/`LC_ALL` in `journalctl -u spark-modem-watchdog --no-pager | grep -i lang` matches a non-C/POSIX value.

**Prevention:**
- The `subproc` wrapper unconditionally sets `env={"LC_ALL": "C", "LANG": "C", **subset_of_required_path_env}` for every qmicli call.
- Document this in `qmi/wrapper.py` with a comment pointing at this pitfall.
- Phase 0 unit test: spawn qmicli in a subshell with `LC_ALL=he_IL.UTF-8` and assert the wrapper still gets parseable output.

**Phase:** Phase 0 fixture/unit; Phase 2 field check (Israeli boxes).

---

### 1.4 qmicli SIGPIPE on long pipelines / killed mid-call (MODERATE) [domain]
**Prob: med · Sev: med**

If we ever `qmicli ... | jq ...` (we shouldn't, but `support-bundle` might), and the consumer exits early, qmicli gets SIGPIPE on its stdout write. A SIGPIPE during a QMI request **after** the modem has accepted a state-changing command (e.g. `--dms-set-operating-mode=online`) but **before** qmicli has read the response can leave the modem in a half-committed state. Same risk if the asyncio cycle cancels `proc.communicate()` mid-write.

**Warning signs:**
- `events.jsonl` shows `action_executed result:"timeout"` immediately followed (next cycle) by a contradictory `qmi.operating_mode` reading.
- CI / replay: mismatched action_planned vs action_executed pairs.

**Prevention:**
- Never pipe qmicli output to anything; always read into a Python buffer in `subproc.run()`.
- For state-changing actions, the wrapper opts into `_in_critical_section=True`; if the asyncio task is cancelled during this window, **wait for the subprocess** (don't kill it) before propagating cancellation. See [cpython#139373: Process.communicate is unsafe to cancel](https://github.com/python/cpython/issues/139373) for the upstream behavior we are working around.
- Tests: hypothesis-driven cancellation test that injects `CancelledError` at every await point in the action wrapper; assert no half-state.

**Phase:** Phase 0 unit; Phase 0 HIL action-cancellation scenario.

---

### 1.5 `--device-open-proxy` vs direct ownership conflict (MODERATE) [domain]
**Prob: med · Sev: high**

If `qmi-proxy` is running (Zao started it), passing direct `--device=/dev/cdc-wdmN` without `--device-open-proxy` to qmicli grabs exclusive ownership and Zao loses its session. PRD Q2 explicitly leaves daemon-vs-Zao qmi-proxy ownership unresolved. The current docs/ ARCH §1 says "qmi-proxy (started by Zao) — multiplexes QMI access; we route through it when available." But "when available" is not specified — what if it's down because Zao is restarting? What if it just crashed?

**Warning signs:**
- Zao log emits `RASCOW_STAT line=N active=0` simultaneously with our `action_planned kind=qmi_*` for that line.
- `events.jsonl` shows our actions correlated with Zao bonding loss for a previously-active line.
- NOC sees a brief uplink interruption without a corresponding qmi/registration issue.

**Prevention:**
- `qmi/wrapper.py` always passes `--device-open-proxy`. If proxy is unavailable (qmicli reports it), the wrapper raises `QmiError(reason="proxy_unavailable")` — caller must NOT fall back to direct mode without an explicit policy decision.
- Decide PRD Q2 in Phase 0: **assume Zao owns; refuse to start qmicli direct mode** is the recommended answer (consistent with `FEATURES.md` M-20).
- Add metric `spark_modem_qmi_proxy_available` (gauge 0/1) updated each cycle.
- Phase 1: run a forced-Zao-restart test on bench; assert daemon does not race Zao for ownership.

**Phase:** Phase 0 ADR; Phase 1 bench scenario.

---

### 1.6 EM7421 firmware-specific quirks beyond raw_ip-flip (MODERATE) [domain]
**Prob: med · Sev: med**

The docs/ acknowledge the raw_ip flip-after-reset bug. Other Sierra EM74xx/EM7421-class quirks documented on Sierra's forum and in libqmi issues:

- **EM7421 stuck in bootloader after `--dms-reset`** under specific firmware revisions ([Sierra forum #35431](https://forum.sierrawireless.com/t/em7421-stuck-on-bootloader/35431)). Modem enumerates with VID:PID `1199:9091` momentarily, then re-enumerates as `1199:9051` (bootloader). Our inventory keys on `1199:9091` and would mark the modem disconnected; we'd never recover it.
- **`--dms-set-operating-mode=offline` followed quickly by `=online`** sometimes leaves the modem in `low-power` until USB rebind on certain EM7421 firmware. Our `soft_reset` does this exact dance.
- **NV-restore on power-loss** can wipe profile #1 APN unpredictably; we'll provision once, then mysteriously see `apn_empty` after a power blip on a subset of modems.

**Warning signs:**
- `lsusb` on a "missing" modem shows `1199:9051` (bootloader) — we'll see `enumeration_missing` for the wwan device.
- After `soft_reset`, `qmi.operating_mode == "low_power"` despite the script having issued `online`.
- After power loss, `profile1_apn` is empty on a set of modems that were previously provisioned.

**Prevention:**
- Inventory matches Sierra-VID `1199:*` (any PID), not just `1199:9091`. A `1199:9051` device is a "modem in bootloader" — emit `enumeration/sierra_bootloader` issue (new enum value) and trigger `usb_reset` on the parent hub port (rationale: a USB reset re-fires the boot transition).
- After every `soft_reset` and `modem_reset`, the next-cycle observation MUST verify `operating_mode == "online"` and `raw_ip == "Y"`; if either is wrong, treat as fix-up issue (not a fresh issue) — this is what the docs/ already do for raw_ip; extend to operating-mode.
- Identity map persists `(usb_path → first_seen_apn)`; after re-provision, log `provision_drift` if the recovered APN differs from the first-seen one (suggests NV wipe).
- Phase 0 HIL: capture `lsusb` after a `--dms-reset` in tight sequence on each EM7421 firmware variant the fleet has.

**Phase:** Phase 0 HIL; Phase 1 fleet-firmware inventory.

---

### 1.7 qmicli "in-flight" races during fast `--qmi-fixture-dir` toggle (MINOR) [new-in-v2]
**Prob: low · Sev: low**

The fixture mode swap (FR-51 + RUNBOOK §2 dry-run) lets an operator point the daemon at recorded output. If they swap mid-cycle (e.g. via SIGHUP reload), an in-flight `qmicli` call returns real data while the next one returns fixture data. The cycle could complete with mixed sources.

**Warning signs:**
- A cycle's `Diag` has fields from two different worlds (e.g. real signal, fake registration).
- Fixture-mode toggle config-reload events bracket a cycle.

**Prevention:**
- Fixture-mode is restart-only, not SIGHUP-reloadable. Document in ARCH §10. Also rejects mode swap through a config-validation rule that requires a process restart.

**Phase:** Phase 0 unit (config-validation test).

---

## 2. Zao integration pitfalls

### 2.1 InfraCtrl.script returns 0 while not applying (CRITICAL) [domain]
**Prob: med · Sev: high**

Soliton's `InfraCtrl.script` is a wrapper around Zao's bonding controller. Field experience with similar vendor scripts: they exit 0 on "command accepted by daemon" not on "change applied to modem." We then mark `provisioned: true`, but the next cycle reads `profile1_apn` and gets the old value. This was indirectly mentioned in PRD §5.2 ("post-write APN verification") for APN — but there are other InfraCtrl.script invocations (per ARCH §1, "we invoke it rather than writing profiles ourselves") and they aren't explicitly verified.

**Warning signs:**
- `events.jsonl` `action_executed result:"ok"` for `set_apn` followed in the next cycle by the same `apn_mismatch` issue.
- `spark_modem_apn_writes_total{result="verified_ok"}` decoupled from `set_apn` action count (the latter rises while the former plateaus).

**Prevention:**
- ALL InfraCtrl.script invocations have an explicit post-action verification step in their `actions/*.py` implementation, not just APN write.
- Add metric `spark_modem_infractrl_invocations_total{op,result}` distinguishing `result=accepted` (exit 0) from `result=verified` (post-read confirmed).
- Phase 0 HIL: explicit "InfraCtrl ack but no apply" fixture (mock InfraCtrl.script always exits 0; assert daemon catches the drift on next cycle).

**Phase:** Phase 0 HIL; Phase 2 field-fault report includes verification stats.

---

### 2.2 Zao log surface drift beyond RASCOW_STAT (CRITICAL) [v1-carryover]
**Prob: med · Sev: high**

ADR-0003 anticipates `RASCOW_STAT` parsing as the canary for Zao log format change. But Zao writes other lines we may grow to depend on — link-state changes, profile-write acknowledgements, error codes. Any one of these drifts could break parsing without invalidating `RASCOW_STAT`.

**Warning signs:**
- `zao_log` parser emits `error event:"unknown_line_kind"` for ≥1% of recent lines.
- `spark_modem_zao_log_age_seconds` is fresh, but `spark_modem_active_lines` lags reality.

**Prevention:**
- `zao_log/parser.py` parses only the `RASCOW_STAT` lines (and any other lines we explicitly need). Other lines are accepted-but-ignored, with a counter `zao_log_unknown_lines_total` for visibility — not an error.
- New Zao SDK qualification adds known-line fixtures to `tests/fixtures/zao_log/`.
- Document in ADR-0003 update: "we parse only RASCOW_STAT today; growing the parsed surface is a schema-version bump."

**Phase:** Phase 0 fixture set; Phase 0 ADR-0003 amendment.

---

### 2.3 qmi-proxy ownership transition on Zao restart (CRITICAL) [domain]
**Prob: med · Sev: high**

Zao starts qmi-proxy. If `zao-infra-ctrl.service` restarts, qmi-proxy may or may not restart with it (depends on the unit dependency graph in the SDK). Between Zao stop and Zao start, qmi-proxy could exit (orphaned by the unit teardown), and then Zao starts a fresh one. Any qmicli call from the daemon during the gap fails.

**Warning signs:**
- `journalctl -u zao-infra-ctrl.service` `Stopped`/`Started` bracketing `events.jsonl` qmi error bursts.
- `spark_modem_qmi_probe_duration_seconds` distribution suddenly bimodal (fast successes + 8 s timeouts).

**Prevention:**
- Subscribe via systemd D-Bus (or `JobRemoved` events) to `zao-infra-ctrl.service` state changes; on `inactive`/`reloading`, suspend QMI probes for `zao_restart_grace_seconds` (default 15 s).
- Track `qmi-proxy` process via `psutil.process_iter()` filtered to the proxy command line; expose `spark_modem_qmi_proxy_uptime_seconds` gauge.
- Phase 0 HIL: `systemctl restart zao-infra-ctrl.service` mid-cycle test; assert daemon does not generate spurious `qmi_channel_hung` issues during the grace window.

**Phase:** Phase 0 HIL; Phase 1 bench validation.

---

### 2.4 Race between Zao restart announcement and watchdog observation (MODERATE) [new-in-v2]
**Prob: med · Sev: med**

Zao restarts → in 30 s polling fallback v2 cycle, RASCOW_STAT log is stale (>5s) → daemon emits `zao_log_stale` → falls back to direct probing of all lines → races Zao on its way back up → cascade of `qmi_channel_hung` alerts on lines Zao is in the middle of bringing up.

**Warning signs:**
- After Zao's `daemon_started` (its own log), the watchdog emits `zao_log_stale` followed by `qmi_channel_hung` for ≥2 lines within 30 s.

**Prevention:**
- Zao restart is observable via systemd D-Bus before the log-staleness threshold elapses. Use `JobRemoved` watch as the primary signal; log-staleness is fallback only.
- Configurable `zao.startup_quiet_period_seconds: 60` after observed Zao start: no probes, no actions; the daemon waits for a fresh `RASCOW_STAT` line before resuming.

**Phase:** Phase 0 HIL.

---

### 2.5 Zao SDK older than 2.1.0 in field (MODERATE) [domain]
**Prob: med · Sev: high**

PRD Q3 marks Zao 2.1.0+ supported; older SDKs may print RASCOW_STAT in a slightly different format. The fleet inventory may not be uniform at v2 cutover.

**Warning signs:**
- `zao_log_unknown_lines_total` non-zero on a subset of boxes after Phase 4 canary; cluster by site reveals an older SDK image.

**Prevention:**
- Phase 0 fleet sweep (no code, just data): inventory Zao SDK version on every box; freeze the cutover schedule per cohort.
- Daemon emits `zao_sdk_version_unrecognized` event on startup if it cannot identify a known prefix in the first 100 RASCOW_STAT lines; Phase 1 daily report surfaces this.

**Phase:** Phase 0 fleet sweep; Phase 4 canary triage rule.

---

## 3. Per-modem state file pitfalls

### 3.1 cdc-wdmN renumbering after USB rebind breaks state-file/identity match (CRITICAL) [v1-carryover]
**Prob: med · Sev: high**

Per `ARCH §6`, state files live under `state/cdc-wdmN.json` keyed by device name. But identity (FR-3) is keyed by `usb_path`. After a USB unbind/rebind storm or a kernel-induced renumbering (which happens on Tegra after some hot-plug sequences), the cdc-wdm number assigned to a USB port can change. State file `cdc-wdm0.json` could then describe what is now the modem at `2-3.1.3` (formerly cdc-wdm2).

**Warning signs:**
- After a `usb_reset --all` or a power-cycle, state files retain the old `usb_path` field while the file *name* stays cdc-wdm0; `inventory` logs `state_file_usb_path_mismatch`.
- `spark_modem_state{state="recovering"}` for the wrong modem (operator confusion).

**Prevention:**
- State file naming MUST key by stable usb_path (e.g. `state/2-3.1.1.json`), not cdc-wdmN. The doc currently keys by cdc-wdmN; **change this in Phase 0**.
- Migration on daemon start: if file is named cdc-wdmN.json with internal `usb_path=X`, migrate to `X.json`; old file is removed.
- Loading: on startup, the inventory cross-checks (file usb_path) ↔ (current sysfs usb_path) ↔ (current cdc-wdm device); mismatch is an error, not silent.
- Phase 0 unit: hypothesis-driven test that randomly permutes cdc-wdm assignments and verifies state-file→modem mapping survives.

**Phase:** Phase 0 SCHEMA amendment; Phase 0 unit.

---

### 3.2 Concurrent writers: daemon vs `ctl reset-state` (CRITICAL) [new-in-v2]
**Prob: med · Sev: high**

FR-61 specifies a daemon PID lock on `/run/spark-modem-watchdog/lock`, but `ctl reset-state` does not appear to acquire it (it's a CLI subprocess that mutates state files). Operator runs `spark-modem ctl reset-state --device=cdc-wdm3` while the daemon is mid-cycle and writing the same state file. Atomic-write (temp + rename, FR-62) prevents *partial* JSON, but it does not prevent a *lost update* — whichever rename happens last wins, silently.

**Warning signs:**
- `events.jsonl` shows `action_executed kind=soft_reset modem=cdc-wdm3` followed by counters that don't reflect the bump (because reset-state's rename came after).
- Operator-initiated state-store mutations correlate with cycle anomalies in the next 30 s.

**Prevention:**
- All state-store mutations (daemon or CLI) acquire an `flock(2)` advisory lock on `/run/spark-modem-watchdog/state.lock` (separate from the daemon-singleton lock). The daemon holds it during the commit phase only; CLI holds it for the duration of its mutation.
- `ctl reset-state` first sends SIGUSR1 to the daemon (or uses a richer IPC) to ask "release state lock"; daemon releases between cycles. Or simpler: ctl waits up to N seconds for the lock, then errors out clearly.
- Phase 0 unit: hypothesis test with two concurrent writers (asyncio + thread); assert no lost updates.
- Cross-reference `FEATURES.md` M-21.

**Phase:** Phase 0 design (FR-61.1 added); Phase 0 unit; Phase 0 HIL stress.

---

### 3.3 Partial JSON / fsync on power loss (MODERATE) [v1-carryover]
**Prob: low · Sev: high**

FR-62 says "atomic file writes (temp + rename)." On ext4 with default mount options, `rename(2)` is atomic from the application's view but a power loss between the temp-file write and a `fsync(parent_dir)` can leave **neither** file (rename succeeded in directory entry, data not flushed) — if the kernel was running a delayed allocation (`auto_da_alloc`). The daemon would see "no state file" on boot — which is "fresh state" — losing all decay/identity data. Tegra root often runs F2FS on the SOM-eMMC; F2FS has stronger atomicity for renames but weaker durability without explicit fsync.

**Warning signs:**
- After uncontrolled power loss, the daemon emits `state_file_missing_treating_as_fresh` for one or more modems.
- After rotation, identity.json is empty / cdc-wdmN.json is empty.

**Prevention:**
- `state_store/file_writer.py` does: write temp, `fsync(temp_fd)`, `os.replace(temp, target)`, `fsync(parent_dir_fd)`. Each step is a separate syscall with explicit error handling.
- Test: pytest fixture that simulates SIGKILL between each step (using a fault-injecting `FileWriter`); assert recovery semantics.
- HIL: actual hardware power-cycle test; assert state files are intact.

**Phase:** Phase 0 unit; Phase 0 HIL.

---

### 3.4 Schema-version-on-past-load (downgrade) is destructive (MODERATE) [new-in-v2]
**Prob: low · Sev: high**

NFR-43 / SCHEMA §10 says daemon refuses *future* schema_versions. The future direction is well-handled. The *past* direction is hand-waved: "MAY accept lower schema_version only if explicit migration code exists for the gap. Otherwise: refuse." But a downgrade (Phase 4 canary rollback to v1.0.0 from v1.1.0) hits state files written by v1.1.0 — and ARCH §9 says "Backup to `<file>.corrupt-<ts>; reset to defaults." This is destructive: a rollback wipes counter history and identity map.

**Warning signs:**
- During canary rollback, `events.jsonl` `state_file_refused_schema schema:2 our_schema:1` events; followed by `_healthy_streak=0` for all modems and `identity.json` repopulating from scratch.
- Identity map ICCID/IMSI columns regress to "first seen now."

**Prevention:**
- Schema-bump policy: never bump a schema across a migration phase boundary. Document in ADR-0004 amendment.
- Downgrade path: schema-mismatch is not "corrupt"; it's "from-future." Keep the file as-is, write a `<file>.from-v<N>.json` shadow, daemon starts with **fresh defaults** but logs `schema_downgrade_pending`. Operator runs `ctl migrate-state --from=v2 --to=v1` to attempt backwards migration if available, else `ctl reset-state --all` consciously.
- The reverse pattern ("schema refused future") is **non-destructive** in v2 (file is left intact); make sure the past-load case is symmetrical.

**Phase:** Phase 0 SCHEMA amendment; Phase 4 canary rollback drill.

---

### 3.5 "Backup to .corrupt-<ts>; reset to defaults" is too aggressive (MINOR) [new-in-v2]
**Prob: low · Sev: med**

ARCH §9 specifies this for "State file corrupted: JSON load fails." In practice, most "corrupt" cases are partial-write recoverable (read the temp file if present), or the file is fine but a new pydantic field broke the load. Resetting to defaults loses identity info and counter context unnecessarily.

**Warning signs:**
- After any minor schema/dependency change, identity map silently empties on a subset of boxes.

**Prevention:**
- Three-tier load: (a) load target file → success; (b) load `<target>.tmp` (pre-rename leftover) if present → log `state_recovered_from_tmp`; (c) **only** then back up + reset.
- Pydantic validation failure is distinct from JSON parse failure — for the former, fall back to a partial-load that preserves what is parseable (identity, _healthy_streak, last_action) and resets only the fields that fail to validate.

**Phase:** Phase 0 design; Phase 0 unit.

---

## 4. systemd integration pitfalls

### 4.1 Type=notify race condition with sd_notify dropping (MODERATE) [domain]
**Prob: low · Sev: high**

[systemd#2737](https://github.com/systemd/systemd/issues/2737) documents that systemd looks up `/proc/${sending_pid}/cgroup` to route the sd_notify message. If the sending process exits between `sd_notify(READY=1)` and systemd's lookup (or, more relevantly here, if a fork happens — which `asyncio.subprocess` does), the lookup can fail, READY is dropped, and systemd either kills the unit on TimeoutStartSec (90 s default) or marks it failed.

**Warning signs:**
- Boot-time `systemctl status spark-modem-watchdog.service` reports `start operation timed out` despite the daemon being up.
- `journalctl -b -u spark-modem-watchdog.service` shows our `daemon_started` event ~2 s in but systemd never marks `Active`.

**Prevention:**
- Send `READY=1` from the **main daemon PID**, not from a child / subprocess / asyncio worker thread. The `sdnotify` library writes to `$NOTIFY_SOCKET` which is per-process — easy to get wrong if the daemon spawns workers before becoming Ready.
- Send READY only after the first cycle has completed (all four modems probed, status.json written) — meaningful readiness, not just "Python interpreter started." NFR-13 says steady state in 60 s; budget the readiness signal at 45 s.
- `WatchdogSec=90s` in the unit + periodic `WATCHDOG=1` after each cycle. If a cycle hangs, systemd restarts.
- Phase 0 boot test: 50 boots; assert systemd reports `Active (running)` within 60 s on every one.

**Phase:** Phase 0 boot test; Phase 0 unit (mock $NOTIFY_SOCKET).

---

### 4.2 Restart=on-failure with crashing-fast loops (MODERATE) [domain]
**Prob: med · Sev: med**

If a config bug or a dependency crash causes the daemon to crash within 1 s of start, systemd's default rate limit (DefaultStartLimitIntervalSec=10s, DefaultStartLimitBurst=5) banishes the unit after 5 quick restarts. The fleet hits this on a bad config push and we lose all four modems' watchdog coverage on every box at once.

**Warning signs:**
- `systemctl is-failed spark-modem-watchdog` returns `failed` after a config rollout; `journalctl -u spark-modem-watchdog.service` shows `start request repeated too quickly`.

**Prevention:**
- Unit hardcodes `StartLimitIntervalSec=300` + `StartLimitBurst=20` + `RestartSec=10` to give the operator time to push a fix across the fleet before banishment kicks in.
- Pre-flight config validation in `ExecStartPre=` catches bad configs before the main process runs (FR-60 already does PATH check; extend to config validation).
- Fleet rollout tooling validates config locally with `spark-modem ctl config-check` before pushing.

**Phase:** Phase 0 unit file design; Phase 5 rollout SOP.

---

### 4.3 LoadCredential= + ExecStartPre + PrivateMounts incompatibility (MODERATE) [domain]
**Prob: low · Sev: med**

[systemd#18116](https://github.com/systemd/systemd/issues/18116) documents that `LoadCredential=` (NFR-34 webhook secret) interacts badly with `ExecStartPre=` and `PrivateMounts=`. On older systemd versions (Ubuntu 20.04 ships systemd 245; the bug landed 247-ish, with cleanups continuing through 250), the credential file may not be visible to the main process if `PrivateMounts=yes`.

**Warning signs:**
- Daemon starts, but `webhook_signing_secret` is empty/None in the loaded config; webhooks fire unsigned.
- `journalctl` for our service shows `LoadCredential failed` warnings.

**Prevention:**
- Skip `PrivateMounts=` and rely on `ProtectSystem=strict` + `ProtectHome=true` for sandboxing on Ubuntu 20.04.
- If the credential file is missing/empty, daemon refuses to start when `alerts.webhook.signing.required=true`, else it logs a warning and disables signing.
- Test on Ubuntu 20.04 + systemd 245 explicitly in Phase 0 (not just on a dev laptop with newer systemd).

**Phase:** Phase 0 unit file test; Phase 1 bench.

---

### 4.4 RuntimeDirectory cleanup interferes with PID lock (MODERATE) [new-in-v2]
**Prob: low · Sev: med**

`RuntimeDirectory=spark-modem-watchdog` cleans the directory on stop (including the lock file at `/run/spark-modem-watchdog/lock`). On rapid restart, the lock file is gone — fine. But if the daemon is killed `kill -9` (operator panic), `RuntimeDirectory=` won't clean up because systemd lost the unit's identity. The next daemon start sees a stale lock with a PID that may now belong to an unrelated process.

**Warning signs:**
- Post-`kill -9` recovery: daemon refuses to start with `pid_lock_held` and an unrelated PID.

**Prevention:**
- PID-lock check uses `flock(2)` not just PID-exists. `flock()` is automatically released on process death (kernel-level), so a stale-PID file with a missing flock means "safe to take over."
- `RuntimeDirectoryPreserve=yes` so the dir survives unit stop; explicit `ExecStartPre=rm -f /run/.../lock` is wrong and brittle.

**Phase:** Phase 0 unit (kill -9 recovery); Phase 0 unit-file design.

---

### 4.5 systemd journal rate-limiting hides events (MINOR) [domain]
**Prob: med · Sev: low**

systemd's journal default rate-limit (`RateLimitIntervalSec=30s, RateLimitBurst=10000` per service) is high but our daemon under an incident can spew thousands of lines in seconds. Lines past the limit are silently dropped from the journal (still in events.jsonl).

**Warning signs:**
- `journalctl -u spark-modem-watchdog.service --since "1 minute ago"` shows fewer lines than `events.jsonl` for the same window during an incident.

**Prevention:**
- The `journalctl` view is human-supplementary; events.jsonl is canonical. Document in RUNBOOK.
- Hard-cap human-log volume in our `logging` JSONFormatter: `info` and below to journal; `error`/`critical` always to journal; everything to events.jsonl.

**Phase:** Phase 0 RUNBOOK amendment; Phase 0 logging design.

---

## 5. asyncio + subprocess pitfalls

### 5.1 Process.communicate() unsafe to cancel — stdout/stderr loss (CRITICAL) [domain]
**Prob: med · Sev: high**

[cpython#139373](https://github.com/python/cpython/issues/139373) documents that cancelling `process.communicate()` may result in stdout/stderr loss. Our policy is per-task 8 s timeout via `asyncio.wait_for()`, which raises CancelledError into the task. The qmicli call is mid-flight; we cancel; communicate() raises; we never see the partial output even if qmicli already wrote the full response.

**Warning signs:**
- Cycles where 1-2 modems' QMI probes fail with `timeout` despite qmicli having printed full output to stdout (visible in strace if you happen to be running it).
- Inconsistent reproductions — depends on the exact moment of cancellation relative to qmicli's write.

**Prevention:**
- The `subproc.run()` wrapper does NOT use `asyncio.wait_for()` around `communicate()`. Instead: spawn process, wait for stdout/stderr with `await proc.wait()` and an explicit `loop.call_later(timeout, lambda: proc.terminate())`. After terminate fires, do a final `await proc.communicate()` with a small 1 s grace period to drain whatever's already there.
- Or: use `asyncio.timeout()` (3.11+, available on 3.12) which is shielded better than `wait_for` and includes proper cancellation propagation.
- Phase 0 unit: 100 random-timing cancellation tests; assert no stdout loss when qmicli completed before cancellation arrived.

**Phase:** Phase 0 unit; Phase 0 design of `subproc/`.

---

### 5.2 PID lifetime race: send_signal kills wrong process (CRITICAL) [domain]
**Prob: low · Sev: high**

[cpython#127049](https://github.com/python/cpython/issues/127049) documents that on Linux, `Process.send_signal/terminate/kill` can target an already-freed PID after the kernel reused it. The race is small, but we send terminate/kill to qmicli on every timeout — at fleet scale and high cycle rate, the cumulative probability becomes non-trivial.

**Warning signs:**
- `journalctl -k` shows qmi-proxy or other daemon's children unexpectedly killed; correlated with our timeout events.
- Fleet-level: a small steady rate of unexplained "qmi-proxy died" / "Zao child killed" entries, no fleet-wide attribution.

**Prevention:**
- Until cpython fixes it, avoid `terminate/kill` after `wait()` returns (the bug is post-wait), and prefer process-group kill if possible (`os.killpg(os.getpgid(pid), SIGTERM)`) — but qmicli isn't in its own group by default. Use `start_new_session=True` in the subprocess wrapper so qmicli is in its own process group; kill the group not the PID.
- Wrap `terminate()` in a check that the proc is still alive (`returncode is None`) — small race window remains but smaller.

**Phase:** Phase 0 design of `subproc/`.

---

### 5.3 asyncio shutdown hangs with cancelled subprocesses (MODERATE) [domain]
**Prob: med · Sev: med**

[cpython#125502](https://github.com/python/cpython/issues/125502) documents `asyncio.run` sometimes hangs forever with cancelled subprocesses. SIGTERM arrives, we cancel all tasks, but a subprocess transport is still tracked by the loop; `loop.close()` blocks. systemd's `TimeoutStopSec=` (default 90 s) eventually does `SIGKILL`, but we miss the FR-53 "graceful SIGTERM within 5 s" SLA on every shutdown that catches a cycle mid-subprocess.

**Warning signs:**
- `events.jsonl` `daemon_stopped reason:"sigterm"` events with `cycle_drain_seconds > 5`.
- systemd journal shows `Stopping spark-modem-watchdog.service... Killed.` (i.e. SIGKILL after timeout).

**Prevention:**
- SIGTERM handler: (a) cancel cycle; (b) explicitly `await proc.wait()` for every tracked subprocess with a 3 s budget; (c) SIGKILL stragglers; (d) close transports; (e) close loop.
- Track subprocesses in a `set[Process]` so the shutdown can iterate.
- `TimeoutStopSec=10s` in the unit + `KillMode=mixed` (SIGTERM to main, SIGKILL to children). FR-53 says graceful within 5 s; budget the kill at 8 s to be safe.

**Phase:** Phase 0 design; Phase 0 boot test (50 SIGTERM cycles).

---

### 5.4 asyncio default subprocess buffering with chatty qmicli (MODERATE) [domain]
**Prob: med · Sev: med**

`asyncio.create_subprocess_exec(stdout=PIPE)` uses a `StreamReader` with default 64 KiB high-water mark. qmicli's `--nas-get-signal-info` on a 5G-aware modem with multiple cells can print >64 KiB. The reader pauses, qmicli's stdout fills its pipe (typically 64 KiB pipe buffer), qmicli blocks on `write(2)`, our cycle stalls without timeout firing because the subprocess hasn't exited.

**Warning signs:**
- Cycles intermittently exceed 8 s for `get_signal` on specific firmware revisions; correlates with verbose output sizes.
- `spark_modem_qmi_probe_duration_seconds{intent="get_signal"}` has a long tail.

**Prevention:**
- Pass `limit=1024*1024` to `create_subprocess_exec` (1 MiB high-water mark) for QMI calls.
- Bound qmicli output: where possible, use the more-targeted `--nas-get-signal-info` (we already do), not `--nas-get-system-info` (verbose).
- Phase 0 fixture: capture the largest known qmicli output and assert the wrapper handles 256 KiB without stalling.

**Phase:** Phase 0 unit.

---

### 5.5 BrokenPipeError on stdin write (MINOR) [domain]
**Prob: low · Sev: low**

If we ever write to qmicli stdin (we shouldn't for read-only ops; we might for some interactive variants) and qmicli has already exited, the write raises `BrokenPipeError` which we'd see as a generic exception.

**Warning signs:**
- `events.jsonl` `error operation:"qmi" reason:"BrokenPipeError"` (rare).

**Prevention:**
- All qmicli calls are stdin=DEVNULL. The wrapper enforces this; passing `stdin=` is a programming error.

**Phase:** Phase 0 design.

---

## 6. Network namespace and netlink pitfalls

### 6.1 rtnetlink ENOBUFS during event storms (CRITICAL) [domain]
**Prob: med · Sev: high**

pyroute2 docs explicitly warn: "you must consume all incoming messages in time, otherwise a buffer overflow happens on the socket and the only way to fix that is to close() the failed socket and open a new one." A `usb_reset --all` during a recovery cycle (or a Tegra USB hub re-enumeration storm) generates dozens of link-state changes per second across 4 namespaces × 4 modems. If our consumer task gets behind by even 1 s, ENOBUFS hits.

**Warning signs:**
- `events.jsonl` `error module:"rtnetlink" reason:"ENOBUFS"` followed by silent loss of link-state events.
- Daemon misses a wwan up event and stays in `Disconnected` for the full polling deadline (30 s).

**Prevention:**
- The rtnetlink consumer task does **only** "drain queue → push event onto asyncio.Queue → loop." No parsing or business logic in the consumer. Keep the read loop as tight as possible.
- On ENOBUFS detection, close socket and reopen; emit `rtnetlink_resubscribed` event; force a full inventory refresh on next cycle (we may have missed an add/remove).
- `SO_RCVBUF` socket option set to 4 MiB explicitly (kernel default is 256 KiB — too small under our event budget).
- Phase 0 stress test: simulate 10 link-state changes per second for 60 s on bench; assert no event loss.

**Phase:** Phase 0 unit; Phase 0 HIL stress.

---

### 6.2 setns under asyncio: thread vs process mode (MODERATE) [new-in-v2]
**Prob: med · Sev: med**

The 4 modems live in 4 namespaces (`line1..line4`). Some operations need to run inside a namespace (`ip netns exec lineN ip addr show wwan0`). `setns(2)` changes the **calling thread's** namespace. In a single-thread asyncio loop, that means switching the loop's thread namespace — which silently affects every other coroutine that resumes during that window. This is a classic asyncio + thread-local-state bug.

**Warning signs:**
- During a netns operation, an unrelated rtnetlink subscription (which lives in the loop) starts seeing events from the wrong namespace.
- Per-modem probe results occasionally swap modems (modem A's results report under modem B).

**Prevention:**
- Never call `setns()` from the asyncio loop. Use `asyncio.subprocess` to spawn `ip netns exec lineN <cmd>` (which forks a child that does its own setns). The child runs in the right namespace, the loop stays in the host namespace.
- pyroute2's `IPRoute(netns="lineN")` opens the netlink socket inside the namespace via fork-and-setns under the hood — preferred for monitoring but verify it doesn't pollute the parent.
- Phase 0 unit: parallel asyncio.gather of 4 per-namespace probes; assert results match modem identity.

**Phase:** Phase 0 design; Phase 0 unit.

---

### 6.3 pyroute2 socket leaks when generators not closed (MINOR) [domain]
**Prob: low · Sev: low**

pyroute2's IPRoute objects own netlink sockets; when used as iterators over events, GC-only cleanup is unreliable, and an exception during iteration can orphan the socket. Repeated subscribe/unsubscribe (e.g. on Zao restart) leaks netlink sockets, eventually hitting the per-process FD limit.

**Warning signs:**
- `lsof -p $(pidof spark-modem-watchdog) | wc -l` grows over hours.
- `OSError: [Errno 24] Too many open files` after a long uptime.

**Prevention:**
- Always use `IPRoute()` as a context manager (`async with`), never as a bare iterator. Pyroute2 supports it.
- Periodic self-check: `psutil.Process().num_fds()`; tripwire at 1024 — log self-health warning.
- Cross-reference ARCH §15 Q4 (FD-leak tripwire is already mentioned but not pinned to rtnetlink specifically).

**Phase:** Phase 0 self-check design.

---

### 6.4 netns teardown during a probe (MINOR) [new-in-v2]
**Prob: low · Sev: med**

Zao restart can recreate `lineN` namespaces. If our probe is mid-`ip netns exec lineN qmicli ...` when Zao destroys the namespace, the qmicli child errors out with `ENOENT` on the namespace fd.

**Warning signs:**
- During Zao restart, our qmicli probes fail with `setns: No such file or directory`.

**Prevention:**
- Already covered by §2.3 (suspend probes during Zao restart grace).
- Defense-in-depth: classify `setns ENOENT` as a transient error, retry next cycle; don't escalate to `qmi_channel_hung`.

**Phase:** Phase 0 unit.

---

## 7. udev pitfalls

### 7.1 MonitorObserver thread crashes silently (CRITICAL) [domain]
**Prob: med · Sev: high**

[pyudev#194](https://github.com/pyudev/pyudev/issues/194) and [#402](https://github.com/pyudev/pyudev/issues/402) document that pyudev's MonitorObserver thread can crash silently under bulk USB events. A USB hub power glitch generates 4× modem add/remove events in tight succession; the observer thread crashes; we never know. From that point on, no udev events arrive and we depend entirely on the polling fallback (30 s).

**Warning signs:**
- A modem hot-plug event isn't reflected in the `Diag` snapshot for >30 s.
- `spark_modem_udev_events_total` counter plateaus while obvious add/remove activity is visible in `journalctl -k`.

**Prevention:**
- Wrap MonitorObserver in a supervisor: thread alive check every 5 s; on death, restart. The restart pattern is non-trivial because pyudev observers can't be restarted ([pyudev#363](https://github.com/pyudev/pyudev/issues/363)) — must create a new observer.
- Skip MonitorObserver entirely; use `pyudev.Monitor` in poll mode with an asyncio file-descriptor reader (`loop.add_reader(monitor.fileno(), ...)`) — keeps everything in the main loop, no thread to die.
- Heartbeat: `spark_modem_udev_observer_heartbeat_seconds` gauge updated each event or every 30 s; tripwire at 60 s.

**Phase:** Phase 0 design (use add_reader pattern); Phase 0 stress test (100 hot-plug events in 10 s).

---

### 7.2 sysfs not fully populated when `add` event fires (MODERATE) [domain]
**Prob: med · Sev: med**

The kernel's udev `add` event fires when the device is registered, but `iSerialNumber`, `idVendor`, and especially `cdc-wdmN` symlinks under `/sys/class/usb/...` may not be in place yet — a 50–200 ms window. Our `inventory.py` tries to read `usb_path` and `device` and gets EAGAIN/ENOENT/empty.

**Warning signs:**
- `events.jsonl` `error module:"inventory" reason:"sysfs_attribute_missing"` shortly after a USB add event.
- A modem temporarily absent from `Diag.modems[]` despite being plugged in.

**Prevention:**
- Wait for the `bind` event, not `add`, for cdc-wdm devices (bind fires when the driver has fully attached).
- Or: retry the inventory query 3× with 100 ms backoff before declaring failure.
- Phase 0 HIL: scripted hot-plug; assert inventory reflects the modem within 1 s.

**Phase:** Phase 0 unit; Phase 0 HIL.

---

### 7.3 USB hub power cycle event storm (MODERATE) [v1-carryover]
**Prob: high · Sev: med**

Tegra's USB hub PSU (RUNBOOK §7) under load can droop, the hub re-enumerates all 4 modems, generating 4 remove events + 4 add events + 4 bind events + 4 link-state events = 16+ events in ~2 s. The cycle queue (asyncio.Queue) fills, we may run multiple cycles immediately, and observation thrashes.

**Warning signs:**
- `dmesg` shows `usb: device not accepting address` or hub power-related lines; coincident with our `cycle_count` spiking.
- `spark_modem_actions_total{kind="driver_reset"}` fires within 30 s of hub re-enumeration (because all 4 modems briefly look QMI-hung).

**Prevention:**
- Coalesce events: ADR-0002 already says "Coalesce: if events arrive while a cycle is running, run exactly one more cycle when current cycle finishes." Verify implementation is robust — at most 1 cycle queued, regardless of event count.
- Hub re-enumeration grace window: if ≥3 modems disappear and reappear within 5 s, suppress `qmi_channel_hung` classification for 30 s (it's hub recovery, not a per-modem fault).

**Phase:** Phase 0 unit (ADR-0002 coalescing); Phase 1 bench hub-stress.

---

### 7.4 Devices that vanish before fully appearing (MINOR) [domain]
**Prob: low · Sev: low**

A modem can fail USB enumeration, generate `add` immediately followed by `remove` without ever exposing `cdc-wdm`. Our `add` handler fires; sysfs is incomplete; eventually `remove` fires. We may accumulate a phantom modem in inventory.

**Warning signs:**
- `Diag.expected_modems == 4` but `Diag.detected_modems == 5` momentarily.

**Prevention:**
- Inventory keys on `usb_path`; `add` for a path already present is a refresh, not a new entry.
- After 5 s of `add` without a successful `cdc-wdm` resolution, garbage-collect the entry.

**Phase:** Phase 0 unit.

---

## 8. inotify on Zao log pitfalls

### 8.1 logrotate breaks the watch invisibly (CRITICAL) [domain]
**Prob: high · Sev: high**

ARCH §15 Q2 says "re-open on `IN_MOVE_SELF`/`IN_DELETE_SELF`; full re-read on rotation." The trap: `logrotate` with `copytruncate` (the default for some Zao SDK packages) doesn't move the file — it copies and truncates in place. Inode stays the same, no `IN_MOVE_SELF` fires. But our offset is now past EOF (truncate), and we silently consume nothing until the file grows again past our offset. `IN_MODIFY` fires but the events are off.

**Warning signs:**
- After daily logrotate, `spark_modem_zao_log_age_seconds` plateaus despite the live file being written.
- `events.jsonl` shows a 24h gap in zao_log_*.* events that aligns with logrotate cron schedule.

**Prevention:**
- On every read, compare `os.stat(path).st_size` against our last-known offset. If `st_size < offset`, the file was truncated; reset offset to 0.
- On `IN_MODIFY`, opportunistically check `st_dev/st_ino` against the last-known watched-inode; on change, re-open.
- Coordinate with field engineering: prefer `create` mode in logrotate (configures Zao's logger to reopen its FD on SIGHUP); document in MIGRATION.
- Phase 0 fixture: simulate `copytruncate` rotation; assert daemon picks up post-rotation lines within 1 cycle.

**Phase:** Phase 0 unit; Phase 1 bench (real logrotate cron).

---

### 8.2 Watching a path that doesn't exist at startup (MODERATE) [new-in-v2]
**Prob: med · Sev: med**

If the daemon starts before Zao has created its log file (boot ordering), `inotify_add_watch(/var/log/zao-remote-endpoint.log)` fails with ENOENT. The naive implementation gives up.

**Warning signs:**
- On reboot, daemon emits `zao_log_unwatchable` and never recovers; stale forever.

**Prevention:**
- Watch the **directory** (`/var/log/`) for `IN_CREATE`; when the file appears, switch to watching the file. Same logic applies to file deletion mid-flight.
- Or: poll for file existence every 5 s during the startup grace window; once present, switch to inotify mode.

**Phase:** Phase 0 unit; Phase 0 boot test.

---

### 8.3 Multiple writes batched into a single IN_MODIFY (MODERATE) [domain]
**Prob: high · Sev: low**

Zao writes RASCOW_STAT in bursts; the kernel coalesces multiple writes into one `IN_MODIFY` event. If our handler reads only "what's new since the last event," we may miss intermediate states.

**Warning signs:**
- Edge cases where the daemon thinks a line is `inactive` but RASCOW_STAT has a more recent `active` line we haven't read.

**Prevention:**
- On every `IN_MODIFY` event, read **everything new since last offset** in a loop until EOF. Don't assume one event = one new line.

**Phase:** Phase 0 unit.

---

### 8.4 inotify watch FD exhaustion during tight restart loops (MINOR) [domain]
**Prob: low · Sev: med**

Each `inotify_init() + inotify_add_watch()` consumes an FD. Combined with §4.2 (Restart=on-failure crash loop), we can leak watches if the daemon doesn't close cleanly. Default `fs.inotify.max_user_watches` is 8192 — high, but cumulative across the system.

**Warning signs:**
- `cat /proc/sys/fs/inotify/max_user_instances` exhausted; new daemons fail to add watches.

**Prevention:**
- Always use `asyncinotify.Inotify()` as an async context manager.
- Cleanup on shutdown.
- Self-check: `len(os.listdir(f"/proc/{os.getpid()}/fd"))` for the watch-related FDs; tripwire.

**Phase:** Phase 0 design.

---

## 9. Backoff / state machine pitfalls in production

### 9.1 _healthy_streak persistence vs decay race (CRITICAL) [new-in-v2]
**Prob: med · Sev: high**

ADR-0006 says decay happens when streak reaches K, then both streak and counters reset. Implementation traps: (a) streak is incremented in `transition()` (called before action selection), (b) decay check happens after action selection, (c) state file is written at the end of cycle. If a crash happens between (b) and (c), the next cycle re-reads the streak from disk (one less than what it was in memory) and the modem is one cycle further from decay than it should be.

**Warning signs:**
- Replay tests show modems that should have decayed at cycle N didn't decay until cycle N+1 or later.
- Production: an `Exhausted → Healthy → Exhausted` cycle where decay was expected to fire midway and didn't.

**Prevention:**
- Streak update + decay computation + counter reset + state-write are a single atomic operation. The cycle pseudo-code in RECOVERY §8 should be amended to make the order explicit: transitions → actions → counter bump → streak increment OR decay-and-reset → atomic state file write.
- Never mutate streak in two separate cycle phases.
- Replay test (`tests/replay/test_counter_decay.py` per ADR-0006 already exists; **add a crash-injection variant** that kills the process between bump and write; assert recovery is correct).

**Phase:** Phase 0 unit (crash injection); Phase 0 replay.

---

### 9.2 Daemon restart resets _healthy_streak silently (CRITICAL) [new-in-v2]
**Prob: high · Sev: high**

If `_healthy_streak` is computed in-memory only (not persisted), every daemon restart (apt upgrade, systemd Restart=on-failure) resets it to 0. A modem that was 9 cycles into a 10-cycle decay window goes back to 0 every time. In production with healthy modems and frequent restarts, decay never happens — and v2 has just re-introduced v1's permanent-Exhausted bug in a new disguise.

**Warning signs:**
- After a daemon restart, `state/cdc-wdmN.json` shows `_healthy_streak: 0` for modems that were healthy throughout the restart.
- `counters_decayed` events become rare on boxes with frequent restarts.

**Prevention:**
- `_healthy_streak` is persisted in `state/cdc-wdmN.json` (per SCHEMA §3 it already is — verify the implementation actually loads it on startup).
- Cross-cycle invariant test: pytest fixture restarts the daemon mid-streak; assert post-restart streak is preserved.
- Phase 0 replay test that includes a daemon restart in the middle of a 12-cycle decay fixture.

**Phase:** Phase 0 unit; Phase 0 replay.

---

### 9.3 Hot-loop / runaway cycle (cycle_drift) (MODERATE) [new-in-v2]
**Prob: med · Sev: high**

If event coalescing breaks (§7.3, ADR-0002), the daemon could run cycles back-to-back at >1Hz. Effects: NFR-2 (1% CPU) violated, qmicli rate-limited or rate-limiting itself, NOC sees a flood of state-transition events. `FEATURES.md` M-8 suggested adding `spark_modem_cycle_drift_seconds` — agreed.

**Warning signs:**
- `spark_modem_cycle_duration_seconds` median <1 s (fine) but `cycle_count_per_minute` >> 30 (we're cycling much faster than the 30 s polling deadline).
- CPU usage of daemon process spikes to >5%.

**Prevention:**
- Enforce minimum cycle interval (e.g. 1 s) regardless of events; coalesce event triggers.
- New metric: `spark_modem_cycle_drift_seconds` = (actual cycle interval - configured polling interval). Negative means hot-loop.
- Self-circuit-breaker: if cycle rate exceeds N/min for M minutes, log emergency and emit a webhook; daemon refuses to cycle for 5 s and re-evaluates.

**Phase:** Phase 0 design; Phase 0 unit.

---

### 9.4 Counter overflow in metrics labels (MODERATE) [new-in-v2]
**Prob: med · Sev: med**

Counters in state are bounded by MAX_* + decay; counters in Prometheus are unbounded. `spark_modem_actions_total{kind, modem, result}` grows monotonically — that's fine, that's how counters work. **But** `spark_modem_state{modem, state}` is a gauge with `state` as a label (one-hot), which means 6 labels per modem × 4 modems = 24 series per box. Add `kind` and `result` to actions and we're at hundreds of series per box × thousands of boxes = millions in Prometheus. NFR-21 says use state as label — that's the cardinality problem.

**Warning signs:**
- NOC's Prometheus reports cardinality alerts; per-job series count balloons after fleet rollout.
- `prometheus_client` self-metric `up` for our scrape targets shows scrape duration creeping.

**Prevention:**
- Use `Enum` (built-in to prometheus_client for state labels): `spark_modem_state{modem}` with value being the enum's index; cardinality is per-modem, not per-modem×state.
- Alternative: a single gauge `spark_modem_state_value{modem}` whose value is an integer code for the state.
- Monotone counters keep their cardinality; gauges with one-hot labels do not.
- Phase 0 review: every metric in NFR-21 and ARCH §11.2 enumerated; cardinality ceiling per-box documented.

**Phase:** Phase 0 metrics design review.

---

### 9.5 RfBlocked → Recovering → Exhausted transition without a destructive try (MINOR) [new-in-v2]
**Prob: low · Sev: med**

RECOVERY §6.1 gates destructive actions when RF is bad. But §6.6 says Exhausted means "all ladder rungs spent." If a modem is in `recovering(modem)` and RF goes bad, we skip; if RF stays bad for the full cycle window where decay would otherwise fire, the modem can transition `recovering → rf_blocked → degraded → recovering(soft) → ...` without ever advancing the ladder. Counter never bumps. But the cross-action backoff §6.3 may still fire. Result: a stuck modem that the policy can't help, no ladder progress, alerts fire forever.

**Warning signs:**
- A modem with consistent `RfBlocked` state for >1h, oscillating between `rf_blocked` and `recovering(soft)`.
- `spark_modem_state_duration_seconds{state="rf_blocked"}` long-tailed for individual modems.

**Prevention:**
- Document: rf_blocked is a terminal state for destructive recovery; only signal recovery exits it. This is the correct behavior. Add a status hint: `rf_blocked` modems should fire an `any -> rf_blocked` webhook (already in alerts) so NOC engages a human (antenna check). Reword ADR-0005 / RECOVERY.md to make this explicit.
- Per-modem time-in-state metric (FEATURES M-5) catches the long tail.

**Phase:** Phase 0 RUNBOOK amendment; Phase 1 dashboard design.

---

## 10. Webhook / alerting pitfalls

### 10.1 DNS resolution blocking the event loop (CRITICAL) [domain]
**Prob: med · Sev: high**

httpx with default settings uses a synchronous `socket.getaddrinfo()` for DNS resolution **on first request** unless you configure an async resolver (`anyio` backend defaults). On a Jetson with broken or slow DNS (which is common — boxes are LTE-bonded, DNS goes through Zao's tunnel), a single webhook POST can block the event loop for seconds or longer. Our cycle stalls; QMI probes timeout; the daemon misses real issues.

**Warning signs:**
- `cycle_duration_seconds` spikes correlated with `webhook_total` events.
- `events.jsonl` `webhook_failed reason:"dns_timeout"` aligns with `cycle_drift` warnings.

**Prevention:**
- Webhook delivery runs in a **separate asyncio task** (fire-and-forget via `asyncio.create_task` + bounded queue), never inline with the cycle.
- httpx client configured with explicit timeouts: `httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=10.0)`. Connect timeout includes DNS.
- Webhook URL DNS pre-resolved at config-load time and cached; refresh every 60 s. The cached IP is used directly (`url=https://1.2.3.4/...` with `Host: noc.example.invalid` header); fall back to fresh resolution on cache miss.
- Phase 0 unit: DNS-failure injection; assert cycle duration unaffected.

**Phase:** Phase 0 design; Phase 0 unit.

---

### 10.2 TLS handshake hang (MODERATE) [domain]
**Prob: low · Sev: high**

Without explicit `read` timeout, an httpx request to a misbehaving HTTPS server (TLS server-hello sent, then silence) hangs indefinitely.

**Warning signs:**
- httpx tasks accumulate (`asyncio.all_tasks()` count grows); webhook queue backlogs.

**Prevention:**
- Explicit timeouts (see 10.1).
- Bounded webhook queue (max 100 pending); on overflow, drop oldest, log `webhook_dropped`.

**Phase:** Phase 0 design.

---

### 10.3 Webhook URL drift between hot-reload and in-flight delivery (MODERATE) [new-in-v2]
**Prob: low · Sev: low**

Operator hot-reloads config (SIGHUP) while a webhook is in flight. The in-flight delivery completes against the old URL; a queued one fires against the new URL. Surprising, but maybe correct — depends on operator intent.

**Warning signs:**
- `webhook_sent` events with mixed URLs around config-reload events.

**Prevention:**
- Document: "URL change applies to webhooks queued after the reload." Match SIGHUP semantics for other reload-time settings.
- The webhook task captures the URL at enqueue time, not at fire time.

**Phase:** Phase 0 design (documentation).

---

### 10.4 Header injection from cause/detail in webhook payload (MINOR) [domain]
**Prob: low · Sev: low**

If `cause` ever flows into an HTTP header (it shouldn't; it's body-only), and an attacker controls `cause` (they can't easily — it's enum-bounded), we could be vulnerable to CRLF injection.

**Warning signs:**
- N/A in practice; this is a defense-in-depth concern.

**Prevention:**
- Webhook code only puts data into the JSON body; headers are statically constructed.
- Pydantic enum-bound `cause` (already done) prevents arbitrary strings.

**Phase:** Phase 0 design (code review check).

---

### 10.5 Receiver returns 200 but corrupts payload (MINOR) [domain]
**Prob: low · Sev: low**

A poorly-implemented webhook receiver may return 200 OK but discard/corrupt the body. We have no end-to-end verification.

**Warning signs:**
- NOC complains about missing alerts despite our `webhook_total{result="sent"}` matching.

**Prevention:**
- Out of scope for v2.0. NOC integration test is a fleet-management responsibility.
- Document: "200 OK = receiver accepted; we don't verify they processed correctly."

**Phase:** Post-launch.

---

## 11. Configuration pitfalls

### 11.1 Drop-in lex order surprises (MODERATE) [domain]
**Prob: med · Sev: med**

`/etc/spark-modem-watchdog/conf.d/*.yaml` sorted lexically (ARCH §10). Naming traps: `10-thresholds.yaml`, `100-overrides.yaml`, `2-emergency.yaml` — lex order is `10-, 100-, 2-, 20-` (ASCII), so `2-emergency.yaml` runs *after* `100-`, and an emergency config gets clobbered by routine drop-ins. Operators with shell habits expect numeric sort.

**Warning signs:**
- After an emergency drop-in is added, the change doesn't apply; operator confusion.

**Prevention:**
- Validation step in config-load: warn if any drop-in starts with a non-zero-padded number (`2-` rather than `02-`).
- Document in RUNBOOK: "Always two-digit prefix (`05-`, `10-`, `20-`) or three-digit if you ship many."

**Phase:** Phase 0 unit; Phase 0 RUNBOOK.

---

### 11.2 YAML "Norway problem" / leading-zero / octal traps (MODERATE) [domain]
**Prob: low · Sev: high**

YAML 1.1 (PyYAML default) parses `NO`, `OFF`, `False`, `false`, `No` as boolean false. Country codes, MNCs, region codes can collide. `NO` (Norway) becomes `false`. `MNC: 02` becomes integer `2` if not quoted (we want string `"02"`). `0o10` becomes octal 8.

**Warning signs:**
- `carrier_table` validation fails on Norwegian MCCs because `NO` decoded to `false`.
- MNCs lose leading zeros in match logic.

**Prevention:**
- pydantic v2 validation enforces `mnc: str` (with regex `r"^\d{2,3}$"`) — wrong-typed YAML values are rejected with a clear error, not silently coerced.
- Carrier table schema has unit tests with hostile inputs (`NO`, `02`, `0x10`, `"0o10"`).
- Use `yaml.safe_load` (already implied) but check PyYAML 6.x default (YAML 1.1) semantics; consider `ruamel.yaml` (YAML 1.2) for stricter parsing — defer; pydantic catches the wrong types.

**Phase:** Phase 0 unit (carrier-table fixtures); Phase 0 design.

---

### 11.3 Env var namespacing collisions (MODERATE) [new-in-v2]
**Prob: med · Sev: med**

`SPARK_MODEM_CYCLE_INTERVAL_SECONDS` vs `SPARK_MODEM_CYCLE__INTERVAL_SECONDS` (double underscore for nested keys is a common pydantic-settings convention). Operators can't tell which is right; one wins, the other is ignored silently.

**Warning signs:**
- A config-set-via-env doesn't apply; the related `config.yaml` value remains effective.

**Prevention:**
- Pick one convention (`SPARK_MODEM__SECTION__KEY` or flat `SPARK_MODEM_KEY`); document it; reject unknown env vars with a warning at startup.
- pydantic-settings has explicit `env_nested_delimiter`; pick `__` and document.
- Startup logs every `SPARK_MODEM_*` env var consumed (and any unmatched) so the operator can verify.

**Phase:** Phase 0 design.

---

### 11.4 Hot-reload partial application (MODERATE) [new-in-v2]
**Prob: med · Sev: high**

SIGHUP reloads config. If the new config is invalid (e.g. one carrier entry has a bad APN), pydantic raises during validation. The current implementation might apply some of the changes before validation completes, leaving the daemon in a half-updated state.

**Warning signs:**
- Post-SIGHUP, `status.json` shows `config.last_reload_ok: false` but observed behavior reflects partial new values.
- Operator runs `ctl reload`, sees error, restarts daemon to recover.

**Prevention:**
- SIGHUP reload is fully transactional: load + validate the new config tree against pydantic; if validation passes, swap atomically; if it fails, log, leave old config in place, emit `config_reload_rejected` event with reasons.
- Cross-reference PRD Q6: pin the SIGHUP semantics.

**Phase:** Phase 0 design; Phase 0 unit.

---

### 11.5 pydantic v2 strict-mode vs operator-friendly coercion (MINOR) [new-in-v2]
**Prob: med · Sev: low**

pydantic v2 strict mode rejects `mnc: 02` (int) where `str` is expected. v1-friendly coercion accepts it. We need to pick one. Strict is stricter (catches typos) but more annoying.

**Warning signs:**
- Operators write `mnc: 02` in YAML, get a confusing "type error" instead of having it just work.

**Prevention:**
- Use validators that explicitly coerce (`@field_validator("mnc", mode="before")` that `str(value)` if int) for common operator-friendly cases. Strict elsewhere.
- Keep error messages actionable: include "did you mean `mnc: \"02\"`?" in the validation message.

**Phase:** Phase 0 design.

---

## 12. Permissions / SELinux / AppArmor / sandbox pitfalls

### 12.1 systemd hardening + setns + sysfs unbind (CRITICAL) [new-in-v2]
**Prob: med · Sev: high**

The daemon runs as root but a hardened systemd unit (`ProtectSystem=strict`, `ProtectKernelModules=true`, `RestrictNamespaces=true`, `CapabilityBoundingSet=`) can disallow `setns`, `unshare`, sysfs writes, modprobe — exactly the operations recovery needs. `usb_reset` (which writes to `/sys/bus/usb/drivers/usb/{un,}bind`) needs `CAP_SYS_ADMIN`; `driver_reset` (rmmod/modprobe qmi_wwan) needs `CAP_SYS_MODULE`.

**Warning signs:**
- `usb_reset` actions silently fail with EPERM; daemon escalates further.
- `journalctl` shows `audit: denied` lines for sysfs writes.

**Prevention:**
- Systemd unit explicitly `CapabilityBoundingSet=CAP_NET_ADMIN CAP_SYS_ADMIN CAP_SYS_MODULE CAP_DAC_READ_SEARCH` (minimum needed).
- `ProtectSystem=full` (allows /var); `ProtectHome=true`; `RestrictNamespaces=net mnt` (allow netns).
- Phase 0 HIL test: every action runs under the production unit hardening; no EPERM.

**Phase:** Phase 0 unit-file; Phase 0 HIL.

---

### 12.2 logrotate user lacks read on events.jsonl (MODERATE) [new-in-v2]
**Prob: low · Sev: med**

The daemon writes events.jsonl owned by `root:root` mode 0640 (or 0600). logrotate runs as root (default) — fine. But if anyone configures logrotate to run as `_logrotate` or via `su` directive, the rotation fails silently.

**Warning signs:**
- Events log grows past 100 MiB; rotation never happens; disk slowly fills.

**Prevention:**
- logrotate snippet in the .deb explicitly sets `create 0640 root adm` and runs as root.
- Self-check: at startup, daemon reads `/var/log/spark-modem-watchdog/events.jsonl.1.gz` mtime; if older than 7 days × max log size hit, log warning.

**Phase:** Phase 0 design.

---

### 12.3 NoNewPrivileges= breaks subprocess setuid features (MINOR) [new-in-v2]
**Prob: low · Sev: low**

If the unit sets `NoNewPrivileges=yes`, qmicli (which doesn't need privilege escalation) is fine, but any helper that's setuid will fail.

**Warning signs:**
- A helper behaves unexpectedly; we shouldn't have any setuid helpers anyway.

**Prevention:**
- Set `NoNewPrivileges=yes` (defense-in-depth); document any future helper requirements.

**Phase:** Phase 0 unit-file.

---

## 13. Observability pitfalls

### 13.1 Cardinality explosion via `state` label one-hot (CRITICAL) [new-in-v2]
**Prob: high · Sev: high**

See §9.4. The single biggest observability pitfall is the metric design itself. NFR-21 specifies `spark_modem_state{modem,state}` with state as label — that's per-state-per-modem-per-box, and Prometheus retention multiplies this further. Across thousands of boxes, this can crash a small Prometheus.

**Warning signs:**
- Pre-launch: NOC's Prometheus reports cardinality alerts during Phase 4.
- WAL compaction time on Prometheus grows dramatically.

**Prevention:**
- Replace with `prometheus_client.Enum` (renders as gauge with one-of values, single series per (modem) tuple).
- Or use `spark_modem_state_value{modem}` integer-encoded.
- Pre-Phase-4 dry-run: feed a synthetic ingest of fleet-scale metrics into the NOC Prometheus and measure cardinality + ingest rate.

**Phase:** Phase 0 metric redesign; Phase 4 fleet-scale review.

---

### 13.2 Event log rate spike during incidents (MODERATE) [v1-carryover]
**Prob: high · Sev: med**

During a real incident, events.jsonl write rate spikes to MB/s. RUNBOOK §8 says page above 5 MiB/min — but we need to *prevent* that, not just alert.

**Warning signs:**
- `disk_full` events; events.jsonl write rate > 5 MiB/min.

**Prevention:**
- Event-deduplication: same `(modem, category, detail)` issue within `event_dedup_window_seconds` (default 30 s) bumps a counter on the previous event rather than emitting a new line. Spec the field as `repeat_count: int`.
- Per-event-type rate limit: max 1 `cycle_start` per second; max 100 `issue_observed` per cycle.
- Tripwire metric `spark_modem_events_dropped_total` so we know when we're shedding.

**Phase:** Phase 0 design; Phase 0 unit.

---

### 13.3 Metrics socket orphaned after daemon crash (MODERATE) [new-in-v2]
**Prob: med · Sev: low**

`/run/spark-modem-watchdog/metrics.sock` (Unix socket) — if the daemon crashes hard, the socket file stays. Next start, `bind(2)` fails with EADDRINUSE.

**Warning signs:**
- After a crash, daemon refuses to start with `metrics_socket_bind_failed`.

**Prevention:**
- Daemon's startup unconditionally `unlink()`s the socket path before `bind()`; safe because `RuntimeDirectory=` and `flock` ensure no other instance.
- OR systemd socket activation (`spark-modem-watchdog-metrics.socket`) — overkill, defer.

**Phase:** Phase 0 design.

---

### 13.4 Prometheus scrape timeout > cycle interval (MINOR) [new-in-v2]
**Prob: low · Sev: low**

If NOC's Prometheus is configured with a 60 s scrape timeout while our cycle is 30 s, a slow scrape (e.g. during fault) overlaps cycles. Not a daemon-side bug, but worth surfacing.

**Warning signs:**
- Prometheus drops scrapes for our targets; fleet visibility holes.

**Prevention:**
- Document recommended scrape interval (15 s) and timeout (10 s) in NOC integration docs.
- Daemon's metrics endpoint is fast (< 100 ms) by design — never block for I/O.

**Phase:** Post-launch documentation.

---

### 13.5 Missing `spark_modem_cycle_drift_seconds` (MINOR) [new-in-v2]
**Prob: med · Sev: low**

Already covered in §9.3 / FEATURES M-8. Without this metric, hot-loop conditions are invisible to NOC.

**Phase:** Phase 0 metric addition.

---

## 14. Testing pitfalls

### 14.1 FakeClock not advancing under `await asyncio.sleep()` (CRITICAL) [new-in-v2]
**Prob: high · Sev: high**

TEST_STRATEGY §8 mandates `FakeClock`; tests never call `time.monotonic`. But our code uses `await asyncio.sleep(N)` which uses the **real** event loop clock. A test that advances FakeClock by 60 s does not advance asyncio.sleep — so any code that combines `clock.now_monotonic()` with `await asyncio.sleep()` for backoff has a clock divergence in tests.

**Warning signs:**
- Tests that pass at trivial durations but fail under property-based / replay tests with longer durations.
- Flaky cycle-related tests.

**Prevention:**
- All sleeps go through a `Sleeper` protocol injected with the clock. Production: `await asyncio.sleep(N)`. Test: a fake that advances FakeClock and yields control.
- Or use `pytest-asyncio` with `pytest.mark.asyncio(loop_scope="function")` and a custom event loop with controllable time. Several libraries (e.g. `aiotools`) provide this.

**Phase:** Phase 0 design.

---

### 14.2 pytest-asyncio flakiness on busy CI runners (MODERATE) [domain]
**Prob: med · Sev: med**

`asyncio.gather` with timeouts depends on real wall-time on shared CI runners. A loaded GitHub Actions runner can stretch a 1 s timeout into 5 s, breaking timing-sensitive tests.

**Warning signs:**
- CI test suite occasionally fails with timeout-sensitive tests; passes on rerun.

**Prevention:**
- Time-sensitive assertions use generous bounds (10× expected) or use FakeClock.
- pytest-asyncio default timeout per-test (configurable in pyproject.toml).
- Property tests use `hypothesis.settings(deadline=None)` to bypass deadline.

**Phase:** Phase 0 CI tuning.

---

### 14.3 Hypothesis tests find pathological state machine inputs (MODERATE) [domain]
**Prob: med · Sev: med**

Property test `test_no_action_on_healthy` (TEST_STRATEGY §5) generates random Diags. Hypothesis is good at finding edge cases — too good. A pathological generated Diag (e.g. signal_dbm = -∞, registration = unknown, …) takes 30+ seconds to shrink and report, blowing the test budget.

**Warning signs:**
- CI hypothesis tests timeout on minor PRs.

**Prevention:**
- Per-test `hypothesis.settings(max_examples=200, deadline=2000)`.
- Use `hypothesis.assume()` to filter out pathological inputs upstream rather than letting them shrink for minutes.
- Use `pytest --hypothesis-show-statistics` to track trends.

**Phase:** Phase 0 CI tuning.

---

### 14.4 HIL fixtures depending on a specific carrier (MINOR) [domain]
**Prob: low · Sev: low**

HIL tests run on bench Jetson with real SIMs. Carrier outage → tests fail; we lose CI signal until carrier returns.

**Warning signs:**
- HIL nightly fails for 30+ min for no apparent reason.

**Prevention:**
- HIL has 4 SIMs from 3 carriers; assertion thresholds are over the bonded set, not per-modem.
- Document carrier outage as a known false-positive in HIL runbook.

**Phase:** Phase 0 HIL.

---

### 14.5 Fixture drift across libqmi versions (MODERATE) [domain]
**Prob: med · Sev: med**

See §1.2. Captured fixtures from libqmi 1.30 don't represent 1.32 output. Tests pass; production breaks.

**Prevention:** see §1.2. Phase 0 records fixtures from each libqmi version the fleet has.

**Phase:** Phase 0 fixture set.

---

## 15. Migration pitfalls (the actual fleet rollout)

### 15.1 Phase 1 dry-run agreement biased toward healthy cycles (CRITICAL) [domain]
**Prob: high · Sev: high**

Phase 1 (MIGRATION §3) compares v1 actions with v2 plans. In a healthy fleet most cycles are no-action. v1 and v2 trivially agree on "do nothing." False confidence. The dry-run agreement metric is dominated by healthy cycles.

**Warning signs:**
- Phase 1 daily report says "≥ 99% agreement" but Phase 3 surfaces unexpected behavior on faults.

**Prevention:**
- The compare tool weights fault cycles heavily; computes separate metrics for "agreement on healthy" and "agreement on faults"; gates Phase 2 on the latter being ≥ 95%, not the aggregate.
- Inject synthetic faults during Phase 1 (e.g. once per day, Zao log briefly held back, qmicli blocked) so agreement is measured on real signal.
- MIGRATION §10 row 1 mentions this risk; pin the metric.

**Phase:** Phase 0 compare-tool design; Phase 1 mandatory fault injection.

---

### 15.2 Phase 3 cutover triggers schema-version mismatch on rollback (CRITICAL) [new-in-v2]
**Prob: med · Sev: high**

If v2 introduces a v3 schema between Phase 3 and Phase 4 (it shouldn't, but it might via a bugfix), rollback to v1 finds v3 state files it can't read. ARCH §9 says reset-to-defaults — destructive.

**Warning signs:**
- Phase 3 rollback wipes counter history and identity map.

**Prevention:**
- Schema-bump-during-migration is forbidden (see §3.4).
- The phase-3 rollback playbook (MIGRATION §5) explicitly captures state directory before downgrade; v1 starts fresh on a state directory with mismatched schema; old state files are preserved at `/var/lib/spark-modem-watchdog.v2-rollback-<date>` for forensics.
- This is already in MIGRATION §5; verify the operator follows the script.

**Phase:** Phase 3 rollback rehearsal.

---

### 15.3 Identity-map drift between v1 and v2 (MODERATE) [new-in-v2]
**Prob: low · Sev: med**

v1's `sim_identity.json` may contain entries our parser doesn't expect (different field names, extra fields). MIGRATION §9 says "post-install hook MAY copy v1's file to a `.bak`" — but doesn't read it. v2 starts from scratch; first-cycle ICCID detection fills v2's identity.json. Edge case: a SIM swap that happened *between* v1 last-write and v2 first-cycle is invisible.

**Warning signs:**
- Identity drift between v1 backup and v2 initial reading; SIM swap detection fires "first time we see this ICCID" for ICCIDs that v1 had recorded.

**Prevention:**
- Document: "SIM swaps observed during the v1→v2 cutover window are not detected as swaps; they are seen as initial provisioning." Operationally acceptable.
- For each box, post-install hook *parses* v1's identity file (best-effort) and pre-populates v2's identity.json; on first cycle v2 reads ICCID and confirms. Mismatch logged but treated as initial provisioning.

**Phase:** Phase 0 post-install hook design; Phase 3 cutover rehearsal.

---

### 15.4 apt repo serves both packages, customer downgrade hits v2 state (MODERATE) [new-in-v2]
**Prob: low · Sev: med**

Operator runs `apt install spark-modem-watchdog=1.0.0` on a box that has been on 2.0.0. v2 state files are present; v1 reads its own format files (`/var/lib/spark-modem-watchdog/state/cdc-wdmN.txt` — different file extension entirely). v1 starts with empty state. Counters reset, identity map regrowing. Not catastrophic but an information-loss event.

**Warning signs:**
- Inadvertent downgrades silently lose state history.

**Prevention:**
- v2's post-install hook checks for v1 state files and refuses to overwrite without `--force`; same in reverse.
- Document: "Downgrade is supported but state is reset; capture support bundle first."

**Phase:** Phase 0 post-install hook design; Phase 3 RUNBOOK addition.

---

### 15.5 Carrier table lex-sort during fleet rollout (MINOR) [new-in-v2]
**Prob: low · Sev: low**

Carrier table updates (FR-33) propagate via fleet management. If two updates are in flight (e.g. add MNC X, then add MNC Y), and the fleet rollout is uneven, some boxes have only X, some have X+Y. Inconsistent carrier behavior across fleet.

**Warning signs:**
- Different SIMs on different boxes get different APN selections.

**Prevention:**
- `carrier_table_sha256` in status.json (FEATURES M-11). NOC dashboard shows fleet-wide divergence.

**Phase:** Phase 0 metric addition.

---

## 16. Operational pitfalls

### 16.1 Daemon executing action while operator runs manual reset (CRITICAL) [new-in-v2]
**Prob: med · Sev: high**

RUNBOOK §2 says "spark-modem reset 4 --soft" works manually; the daemon is supposed to "observe these (via udev/link state events)." But a real race: operator types `spark-modem reset 4 --soft`; the daemon, mid-cycle, decides it should run `modem_reset` on cdc-wdm3. Both run simultaneously. Two QMI commands fight; the modem may end up in unspecified state.

**Warning signs:**
- After a manual reset, the modem behaves erratically; events.jsonl shows daemon-issued action overlapping the manual one.
- `manual_action` event timestamp within seconds of `action_executed`.

**Prevention:**
- Manual reset acquires the same `flock` as state mutations (§3.2) and additionally requires the daemon to surrender its action lock for that modem before proceeding. CLI tells operator: "Daemon is mid-cycle; waiting" / "Daemon owns this modem; pass --force to override."
- The daemon's per-modem action wrapper acquires a per-modem advisory lock (flock on `/run/spark-modem-watchdog/modem-{device}.lock`) before invoking any subprocess; CLI same. Mutual exclusion at modem-level granularity.
- Cross-reference FEATURES M-21.

**Phase:** Phase 0 design (per-modem lock); Phase 0 unit.

---

### 16.2 Maintenance mode forgotten in "on" (CRITICAL) [domain]
**Prob: med · Sev: high**

FEATURES M-10 proposes `spark-modem ctl maintenance on --duration=2h`. Without auto-expiry, an operator turns it on and forgets. Webhooks suppressed for hours/days. NOC misses real events.

**Warning signs:**
- Boxes silently in maintenance mode for >24 h; no webhooks fired.

**Prevention:**
- Maintenance mode REQUIRES `--duration` flag (no infinite). Maximum 8 h, configurable.
- Auto-expiry; daemon emits `maintenance_expired` event on transition.
- `status.json` and metrics expose `maintenance_until_iso`; NOC dashboards alert if any box is in maintenance.

**Phase:** Phase 0 design (M-10 implementation).

---

### 16.3 Operators running multiple ctl commands concurrently (MODERATE) [v1-carryover]
**Prob: med · Sev: med**

Two engineers, two SSH sessions, both run `ctl reset-state --all`. Not destructive (idempotent), but `ctl provision --restart-zao` from both at once could trigger Zao restart races.

**Warning signs:**
- `manual_action` events overlap; Zao restarts within seconds of each other.

**Prevention:**
- `ctl` subcommands acquire the `flock` (§3.2 + §16.1). Concurrent runs serialize.
- Privileged commands (`provision --restart-zao`, `reset --driver`) require an `--i-know` flag for unattended use; default-prompt for interactive.

**Phase:** Phase 0 design.

---

### 16.4 Log retention shorter than incident window (MODERATE) [domain]
**Prob: med · Sev: med**

`logrotate` default 7 days, 100 MiB (FR-43). A real incident is sometimes only investigated days later (after escalation). 7 days isn't enough for a Friday-evening incident reviewed Tuesday.

**Warning signs:**
- Forensics request fails because events.jsonl has rolled past the incident time.

**Prevention:**
- 14 days, 200 MiB default. Operator-tunable. Document tradeoff.
- Support bundle (NFR-22) includes events from the rotated `.gz` files automatically; the operator doesn't have to know to capture both.

**Phase:** Phase 0 default-config; Phase 0 support-bundle test.

---

### 16.5 support-bundle exceeds ssh timeout (MINOR) [domain]
**Prob: low · Sev: low**

`ctl support-bundle` packages dmesg + journal + state — can be slow on a heavily-loaded box. SSH session times out before the bundle completes.

**Warning signs:**
- Engineer reports support-bundle "hangs"; bundle never produced.

**Prevention:**
- Streaming output: `ctl support-bundle --out=/tmp/sb.tgz &` then ssh-poll for completion.
- Document: "On slow boxes, run via `nohup` or `tmux`."
- Bundle has a verbose progress log on stderr.

**Phase:** Post-launch.

---

## 17. Hardware-specific pitfalls

### 17.1 Sierra EM7421 firmware variation across the fleet (CRITICAL) [domain]
**Prob: high · Sev: med**

The 4 modems on a single box are usually the same firmware; **across the fleet** firmware varies (boxes commissioned at different times). Sierra EM7421 firmware revisions through SWI9X30C_*.* introduce small behavior changes (NR field reporting, raw_ip default, autosuspend defaults).

**Warning signs:**
- Per-firmware-revision differences in `qmi_*` or signal field availability.

**Prevention:**
- Phase 0 fleet inventory: `swi_setusbcomp -e | grep VERSION` per modem per box; record `fw_revision` in state.
- Per-firmware-revision fixtures in tests/fixtures/qmicli/.
- Document supported firmware range; refuse to start on unsupported firmware (warn-only, not fail-closed, in v2.0).

**Phase:** Phase 0 fleet sweep; Phase 0 fixture; Phase 4 canary firmware-cohort review.

---

### 17.2 Tegra USB hub PSU droop under simultaneous load (CRITICAL) [domain]
**Prob: high · Sev: high**

RUNBOOK §7 mentions this. 4 modems peaking simultaneously (e.g. on cold start, all powering radios) draw enough current to droop the hub's 5V rail; one or more re-enumerates. We see `enumeration_address_fail` and over-current in dmesg.

**Warning signs:**
- `host_issues` containing `enumeration_overcurrent` or `enumeration_address_fail` — often clustered in time.
- Multiple modems disappear from inventory simultaneously.

**Prevention:**
- Stagger startup: on first cycle after boot, daemon issues `set_apn`/`fix_raw_ip` actions sequentially across modems with 5 s spacing rather than all-parallel.
- This is a hardware fix (better PSU), but the daemon can mitigate by avoiding simultaneous radio activations.
- Already an "alert NOC, site visit" item in §7. Keep that; add daemon mitigation.

**Phase:** Phase 0 design (staggered startup); Phase 1 bench validation.

---

### 17.3 Thermal throttling masquerading as modem issue (MODERATE) [domain]
**Prob: med · Sev: med**

Tegra under thermal throttling slows USB control transfers. qmicli timeouts spike. Daemon classifies as `qmi_channel_hung` and may issue `driver_reset`. Real issue: throttle. Reset doesn't help.

**Warning signs:**
- `dmesg` shows `tegra_actmon` thermal entries coincident with `qmi_channel_hung` events.
- Cycle duration variance correlates with measured SOC temperature.

**Prevention:**
- Read `/sys/class/thermal/thermal_zone*/temp` each cycle; emit `host/thermal_warn` issue when above 70°C.
- Recovery decision-table: when `host/thermal_warn` is active, suppress `driver_reset` (it won't help).
- This is partially in the docs (RECOVERY §4 has thermal_warn = informational); make sure the **suppression logic** is wired up.

**Phase:** Phase 0 unit; Phase 0 HIL (thermal stress).

---

### 17.4 USB 3 fallback to USB 2 (MINOR) [domain]
**Prob: low · Sev: low**

Marginal cabling/hub conditions cause a modem to negotiate USB 2 at 480 Mbps instead of 5 Gbps. Functionally fine for cellular data; informationally a yellow flag.

**Warning signs:**
- `Diag.modems[].usb_speed_mbps == 480` (was 5000).

**Prevention:**
- Already tracked; surface as informational in metrics (gauge); not actioned. Field engineering escalation.

**Phase:** Phase 0 metric.

---

## 18. Python 3.12 (python-build-standalone) pitfalls

### 18.1 glibc symbol mismatch on Tegra L4T (MODERATE) [new-in-v2]
**Prob: low · Sev: high**

python-build-standalone targets glibc 2.17 baseline (per STACK.md). Ubuntu 20.04 on Tegra ships glibc 2.31. Jetson L4T R35.x specifically can have non-vanilla glibc patches (NVIDIA pinned versions). Edge case: a CPython native module compiled against a `manylinux_2_17` wheel could `dlopen` a symbol that exists in 2.31 but not in PSF's 2.17-compiled ctypes layer.

**Warning signs:**
- Daemon fails to start with `ImportError: undefined symbol: ...` on Jetson but works on dev laptop.

**Prevention:**
- Phase 0 must produce a working .deb installed and started on a real Jetson before *any* HIL tests. Smoke test: `import pydantic, pyudev, pyroute2, asyncinotify, httpx, prometheus_client, psutil`.
- Pin python-build-standalone exact build-tag per release; recapture on each rebuild.

**Phase:** Phase 0 smoke test; Phase 0 HIL.

---

### 18.2 PEP 668 EXTERNALLY-MANAGED interaction (MINOR) [new-in-v2]
**Prob: low · Sev: low**

If we ever `pip install` from inside the venv (e.g. operator running `pip install foo`), PEP 668's EXTERNALLY-MANAGED marker (which python-build-standalone ships) blocks. Operator confused.

**Warning signs:**
- An operator tries to add a library at runtime and gets `error: externally-managed-environment`.

**Prevention:**
- Document: "Don't `pip install` into /opt/spark-modem-watchdog/venv. Modifications require a new .deb."
- Remove or override EXTERNALLY-MANAGED in the .deb post-install hook? Probably no — keeping it is safer.

**Phase:** Phase 0 RUNBOOK.

---

### 18.3 Relocated venv path mismatch (MODERATE) [new-in-v2]
**Prob: low · Sev: high**

`python -m venv` records absolute paths in scripts, .pth files, and shebang lines. If we build the venv on a builder host at `/build/.../venv` and ship it to install at `/opt/spark-modem-watchdog/venv`, those paths must match. python-build-standalone has known relocation semantics (uses the bundled python's `python_home` discovery).

**Warning signs:**
- `bin/spark-modem` fails with `ModuleNotFoundError: pydantic` despite the venv being present.
- Shebang line points at `/build/...`.

**Prevention:**
- Build the venv at the **destination path** (use `dpkg-buildpackage`'s `DESTDIR` properly so the venv is created at `/opt/...` from the start).
- Or: use `--upgrade-deps --without-pip` and rely on python-build-standalone's relocation logic.
- Phase 0 build process must produce a .deb that installs *and works* on a fresh Jetson.

**Phase:** Phase 0 build pipeline; Phase 0 smoke test.

---

### 18.4 .deb upgrade overwrites /opt/.../venv while daemon is running (MODERATE) [new-in-v2]
**Prob: med · Sev: med**

`apt upgrade spark-modem-watchdog` replaces files in /opt/.../venv. The running daemon's loaded modules are file-backed (.pyc files); replacing them mid-execution can cause `ImportError` if Python loads a module lazily after the upgrade. systemd's `Restart=on-failure` then restarts.

**Warning signs:**
- During upgrade, daemon crashes once with `ImportError: cannot import name X from Y`; restarts cleanly.

**Prevention:**
- Pre-stop the daemon in `prerm`; replace files; restart in `postinst`. Standard Debian package practice. Verify the maintainer scripts do this.
- Confirm: the .deb's `DEBIAN/preinst` stops the unit before file replacement; `postinst` starts after.

**Phase:** Phase 0 .deb policy; Phase 0 upgrade test.

---

### 18.5 Certifi staleness in long-lived .deb (MINOR) [new-in-v2]
**Prob: low · Sev: med**

httpx uses certifi for the trust bundle. A box installed with .deb v2.0.0 in Phase 4 may be running for 6-12 months without a rebuild. Certifi is updated quarterly; outdated trust bundles can fail validation against newly-rotated webhook receiver TLS certificates.

**Warning signs:**
- After NOC rotates its webhook TLS cert, our boxes start failing with `[SSL: CERTIFICATE_VERIFY_FAILED]`.

**Prevention:**
- Pin certifi version in requirements.lock; rebuild .deb quarterly with refreshed lock.
- Or: configure httpx to use the system trust store (`ca_bundle = "/etc/ssl/certs/ca-certificates.crt"`). On Ubuntu the system bundle gets `apt update` refreshes — but the daemon doesn't.
- Document: "Webhook TLS rotation requires a v2.x.y point release across the fleet within 90 days."

**Phase:** Phase 0 .deb policy.

---

### 18.6 aarch64 wheel availability for new deps (MINOR) [new-in-v2]
**Prob: low · Sev: med**

Adding a new dep in v2.1 that doesn't have an aarch64 wheel forces source-build at install time, which:
- Fails offline (C20 violated).
- Adds gcc/build-essential to the build host.

**Warning signs:**
- Build pipeline fails on a new dep with `error: Microsoft Visual C++ ...` (lol no, but: `error: command 'aarch64-linux-gnu-gcc' failed`).

**Prevention:**
- Vendor any new dep into the .deb (precompile into the venv on the build host); reject deps that don't have aarch64 wheels.
- CI gate: `uv pip install --no-binary :none:` failure is a blocker (only allow pre-built wheels).

**Phase:** Post-launch policy.

---

## Cross-cutting: phase mapping summary

| Phase | Critical pitfalls covered | Tests/checks added | Exit-criterion adjustments |
|-------|--------------------------|---------------------|----------------------------|
| Phase 0 (build/HIL) | 1.1, 1.2, 1.6, 2.1, 2.3, 3.1, 3.2, 3.3, 4.1, 4.4, 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 7.1, 7.2, 7.3, 8.1, 8.2, 8.3, 9.1, 9.2, 9.3, 10.1, 10.2, 11.1, 11.2, 11.3, 11.4, 12.1, 13.1, 13.2, 13.3, 14.1, 14.2, 14.3, 16.1, 16.2, 17.2, 17.3, 18.1, 18.3, 18.4 | Crash-injection unit tests; cancellation unit tests; cardinality review; metric inventory; HIL kill-qmi-proxy; Tegra-thermal-stress | "Smoke test on real Jetson passes" — concrete bar |
| Phase 1 (bench shadow) | 1.2 (parser drift), 2.4 (Zao restart races), 4.3 (LoadCredential) | Synthetic-fault injection in compare tool; weighted agreement metric | "Fault-cycle agreement ≥95%" not "aggregate ≥99%" |
| Phase 2 (field shadow) | 1.3 (locale), 2.5 (SDK older), 17.1 (FW variation) | Per-box firmware/SDK inventory | "All boxes' firmware/SDK in known set" |
| Phase 3 (one box live) | 3.4 (downgrade), 15.2, 15.3, 15.4, 16.4 | State capture before cutover; rollback rehearsal | "Rollback-to-v1 in <10 minutes verified" |
| Phase 4 (canary) | 13.1 (cardinality), 15.1 (dry-run bias), 17.1, 17.2 | Prom-cardinality test at 10% scale; thermal monitoring | "Prom WAL compaction time within budget at fleet ingest" |
| Phase 5 (rollout) | 15.5 (carrier-table drift), 18.5 (certifi rotation) | Carrier-table SHA in metrics; quarterly rebuild policy | "Carrier-table SHA convergence ≤1h after rollout" |
| Post-launch | 1.4 (SIGPIPE), 13.4 (scrape interval), 16.5 (ssh timeout), 18.6 (wheels) | Documentation; integration-doc handoff | n/a |

---

## What the docs/ already addresses (NOT in this list)

For traceability, here is the docs/ baseline that this PITFALLS document deliberately does not duplicate:

- Free-form `detail` strings → ADR-0004 (closed enums).
- Heterogeneous `who` field → ADR-0004 (tagged union).
- Counters never decay → ADR-0006 (decay on healthy streak).
- Same-action backoff but ping-pong escalation → RECOVERY §6.3 (cross-action ladder backoff).
- Wall-clock backoff → ADR-0007 (monotonic clock).
- Polling-only architecture → ADR-0002 (event-driven core).
- Command injection in heredocs → FR-64 (list-form argv).
- No tests, no fixtures → TEST_STRATEGY.md (full strategy).
- No log rotation, no metrics → FR-43, NFR-21.
- `.bak` files instead of git → repo policy.
- raw_ip flip-after-reset on EM7421 → docs/ acknowledged (we extended in §1.6 with bootloader, NV-wipe, low-power-stuck variants).
- qmicli text output stability concern → ARCH §15 Q1 (we extended in §1.2 with concrete drift scenarios + locale pitfall).
- inotify on Zao log rotation → ARCH §15 Q2 (we extended in §8.1 with copytruncate trap).
- pyudev libudev pinning → ARCH §15 Q3 (we extended in §7.1 with MonitorObserver thread crash).
- FD leaks → ARCH §15 Q4 (we extended in §6.3 with rtnetlink-specific case).
- Heterogeneous BSPs → ARCH §15 Q5 (we extended in §17.1 with firmware-revision plan).

---

## Sources

**HIGH-confidence (verified in upstream issue trackers / official docs):**

- [cpython#127049 — asyncio Process race kills unrelated PID](https://github.com/python/cpython/issues/127049) — basis for §5.2.
- [cpython#139373 — Process.communicate is unsafe to cancel](https://github.com/python/cpython/issues/139373) — basis for §5.1, §1.4.
- [cpython#125502 — asyncio.run hangs with cancelled subprocesses](https://github.com/python/cpython/issues/125502) — basis for §5.3.
- [cpython#103847 — asyncio.create_subprocess_exec ignores CancelledError](https://github.com/python/cpython/issues/103847) — basis for §5.1.
- [systemd#2737 — Race condition causing sd_notify messages to get dropped](https://github.com/systemd/systemd/issues/2737) — basis for §4.1.
- [systemd#18116 — LoadCredential, PrivateMounts, ExecStartPre interaction](https://github.com/systemd/systemd/issues/18116) — basis for §4.3.
- [pyudev#194 — Stack trace from MonitorObserver thread](https://github.com/pyudev/pyudev/issues/194) — basis for §7.1.
- [pyudev#402 — Monitor failure on embedded system](https://github.com/pyudev/pyudev/issues/402) — basis for §7.1.
- [pyudev#363 — Can't restart a MonitorObserver](https://github.com/pyudev/pyudev/issues/363) — basis for §7.1.
- [pyroute2 — Netlink debugging](https://docs.pyroute2.org/debug.html) — ENOBUFS handling, basis for §6.1.
- [libqmi-devel — qmi-proxy crashing](https://lists.freedesktop.org/archives/libqmi-devel/2021-January/003512.html) — basis for §1.1.
- [modemmanager-devel — Random MM and/or qmi-proxy hang](https://www.mail-archive.com/modemmanager-devel@lists.freedesktop.org/msg05135.html) — basis for §1.1.
- [inotify(7) man page](https://man7.org/linux/man-pages/man7/inotify.7.html) — basis for §8.x.
- [Sierra EM7421 stuck on bootloader (forum #35431)](https://forum.sierrawireless.com/t/em7421-stuck-on-bootloader/35431) — basis for §1.6.
- [Tegra-xusb 3530000.xhci controller firmware hang](https://forums.developer.nvidia.com/t/tegra-xusb-3530000-xhci-controller-firmware-hang/183788) — basis for §17.2.
- [Prometheus client_python — Multiprocess Mode](https://prometheus.github.io/client_python/multiprocess/) — basis for §13.1, §9.4.
- [Cloudflare — How we run Prometheus at scale](https://blog.cloudflare.com/how-cloudflare-runs-prometheus-at-scale/) — cardinality scaling, basis for §13.1.
- [httpx#2756 — AsyncClient hostname resolution after fork](https://github.com/encode/httpx/discussions/2756) — basis for §10.1.
- [PEP 668 — Marking Python base environments as externally managed](https://peps.python.org/pep-0668/) — basis for §18.2.
- [astral-sh/python-build-standalone releases](https://github.com/astral-sh/python-build-standalone/releases) — basis for §18.x.

**MEDIUM-confidence (reasoned from multiple secondary sources):**

- [pyinotify livereload #37 — inode change problem](https://github.com/lepture/python-livereload/issues/37) — basis for §8.1.
- [Sierra EM7421 firmware](https://forum.sierrawireless.com/t/em7421-firmware/30169) — basis for §1.6.
- [Sierra EM7421 firmware upgrade](https://forum.sierrawireless.com/t/em7421-firmware-upgrade/34798) — basis for §17.1.
- [Mastering Quectel Modem Troubleshooting with qmicli](https://medium.com/@milind.gunjan/mastering-quectel-modem-troubleshooting-with-qmicli-a3a65f5ece6b) — generic QMI pitfalls, basis for §1.x.

**LOW-confidence (single source / reasoned from analogy):**

- Zao SDK internals (we are guessing about a closed-source counterparty); §2.1, §2.2, §2.3 are based on patterns from comparable vendor scripts (mwan3, Cradlepoint MM hooks).
- Specific EM7421 firmware NV-wipe behavior (§1.6 third bullet) — reasoned from Sierra's documented NV-restore semantics; not directly verified.

---

*Pitfalls research for: spark-modem-watchdog v2*
*Researched: 2026-05-05*
*Author: GSD project researcher (PITFALLS dimension)*
