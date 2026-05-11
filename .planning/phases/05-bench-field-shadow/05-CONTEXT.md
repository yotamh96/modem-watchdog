# Phase 5: Bench & Field Shadow - Context

**Gathered:** 2026-05-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 5 delivers v2 onto real hardware and proves it safe enough to flip to
fleet rollout in Phase 6. Originally scoped as "v2 dry-run alongside v1 on
bench Jetson + one field box, gated by ≥95% fault-cycle agreement against
v1" (ROADMAP SC#1–#3 + MIGRATION §3–4). That framing is dead: **v1 is
retired across the entire fleet** (user disposition during this discussion,
2026-05-11). The shadow alongside-v1 design from MIGRATION Phases 1–2 no
longer applies, and `tools/compare_v1_v2.py` is **not** built in this phase.

In the v1-retired world Phase 5 collapses to:

  v2 deployed live on bench Jetson (1 week soak)
  → v2 deployed live on field box (2 week soak)
  → replay-harness ≥0.95 gate against freshly-pulled v1 traces
  → all fleet-cohort triples captured at `tests/fixtures/fleet/<box-id>/`
  → SIGNOFF.md committed
  → Phase 6 (cutover & fleet rollout) starts

The daemon's behavioral surface is locked in Phases 1–4. Phase 5 adds:

- One CLI subcommand (`spark-modem ctl capture-fleet-fixture`)
- One daemon preflight check (refuse-on-unknown-triple)
- The day-1 fresh trace pull workflow (one-shot operator task wiring an
  existing tool)
- The Phase 6 entry-signoff runbook + SIGNOFF.md template
- Bench + field soak runbook (operator-facing)

It does **not** add: the v1/v2 compare tool, shadow-mode `.deb` packaging,
`99-shadow.yaml` distribution, `-v2`-suffixed paths, synthetic fault
injection on the field box.

</domain>

<scope_pivot>
## Scope Pivot vs ROADMAP / MIGRATION

The user's "v1 retired across the entire fleet" disposition during this
discussion invalidates the following pre-existing artifacts. They are
**not** Phase 5's job to fix, but downstream agents should read them
through the pivot lens, not literally:

- **ROADMAP.md Phase 5 SC#1** — references `spark-modem-watchdog-v2.service`,
  `99-shadow.yaml`, `/var/lib/spark-modem-watchdog-v2/`, etc. Stale; v2 runs
  at canonical paths from day 1.
- **ROADMAP.md Phase 5 SC#2** — references `tools/compare_v1_v2.py` hourly
  report. Stale; the tool is not built. Fault-cycle agreement gate
  (≥0.95) survives, but is measured by `tests/replay/test_v1_agreement.py`
  against the freshly-pulled `tests/fixtures/replay/v1-30d/` bundle, not
  a live compare tool.
- **ROADMAP.md Phase 5 SC#3** — references daily synthetic fault injection
  comparing v2 plans to v1 actions. Stale; no field injection, no v1 plans
  to compare against. Bench injection rides Plan 04-07 HIL nightly only.
- **ROADMAP.md Phase 5 SC#4 (fleet fixture capture)** — survives intact and
  is one of Phase 5's primary deliverables.
- **MIGRATION.md Phases 1–2** — entire framing (shadow alongside v1) is
  stale. MIGRATION.md Phases 3+ (cutover / canary / rollout) still
  authoritative for Phase 6/7.
- **PROJECT.md "v1 currently keeps a real fleet online"** + **CLAUDE.md**
  same line — both stale. Not Phase 5's job to rewrite the prose, but
  noted here so downstream agents don't take it literally.
- **PROJECT.md ▸ Migration ▸ Phase 1 / Phase 2 checkboxes** — should be
  reframed during Phase 5 plan execution; "dry-run alongside v1" was the
  original intent and is no longer the work being done.

Recording this pivot in CONTEXT.md (not as an ADR amendment in this phase)
keeps Phase 5 plan-cost minimal. Phase 7 (v1 decommission) or a separate
ADR-0014 candidate is the right place for the doc rewrite, and the user
has not asked for that yet — see Deferred Ideas below.

</scope_pivot>

<decisions>
## Implementation Decisions

### Replay harness operationalization (R-*)

- **R-01:** A day-1 fresh trace pull from real-fleet v1 logs happens at
  Phase 5 kickoff. The on-site engineer archives `/var/log/spark-modem-
  watchdog/` from each (now-decommissioned) v1 box, runs
  `tools/pull_replay_traces.py` locally to apply sha256[:8] ICCID/IMSI/IP
  redaction, and opens a single PR with the LFS payload updating
  `tests/fixtures/replay/v1-30d/`. Plan 04-06's README in that dir already
  documents the redaction contract; Phase 5 just exercises it for the
  first time.
- **R-02:** The replay-harness gate (`tests/replay/test_v1_agreement.py`
  + R-03 conftest hard-fail) runs **once, manually, at Phase 5 exit** —
  not on every commit in CI, not on a scheduled nightly. Eng triggers it
  before committing SIGNOFF.md.
- **R-03:** The agreement bar stays at **≥0.95** — the same threshold
  Plan 04-07 ships. No change to `tests/replay/conftest.py` R-03 constant.
  No two-tier (healthy vs. fault) slicing.
- **R-04:** The quarterly v1-trace refresh cadence (deferred from Phase 4)
  **begins with this Phase 5 day-1 pull**. Subsequent refresh schedule and
  ownership is a Phase 6/7 concern; Phase 5 only owns the first refresh.

### Soak window + Phase 6 gating (S-*)

- **S-01:** "Clean soak" means all three of these hold over the bench week
  and the field two weeks:
  1. Zero daemon crashes / OOM / unhandled-exception restarts (M6 metric;
     detected by `journalctl` query for failed unit + count of
     `daemon_started` events with reason=CRASH or empty marker
     classification).
  2. Zero "action planned on a Zao-active line" — post-hoc query of
     `events.jsonl` for `action_planned` events whose modem's line was
     Zao-active at the cycle the event was emitted. Origin: ADR-0003.
  3. Zero unexplained `exhausted` state transitions — every `exhausted`
     event must be explainable by genuine non-recoverable hardware, not
     by counter accumulation (M4; ADR-0006 amendment).
- **S-01.1:** P99 cycle ≤10s (M5) and RSS ≤80 MiB (NFR-3) are **not** a
  Phase 5 hard gate. Both were verified in Phase 2 at smaller scale;
  Phase 5 records them informationally but does not block on them.
- **S-02:** Soak window shape = **1 week bench Jetson + 2 weeks field box,
  sequential** (MIGRATION.md's original timing preserved). Field deploy
  cannot start until bench week is clean.
- **S-03:** The bench→field handoff gate is **the same 3 gates as Phase 5
  exit, measured over the bench-only week**. Symmetric one-rule-two-
  checkpoints design.
- **S-04:** Phase 6 entry signoff = `.planning/phases/05-bench-field-
  shadow/SIGNOFF.md` checklist + attached replay-harness result. The
  on-site engineer authors and commits SIGNOFF.md; the replay-harness
  JSON output (from R-02) is committed alongside it as evidence. Phase 6
  PR cannot merge without both.

### Fault injection (F-*)

- **F-01:** **No synthetic fault injection on the field box.** The 2-week
  field soak rides natural-fault occurrence only. Avoids the
  "synthetic-fault triggers a destructive reset which causes a customer-
  visible outage" risk class entirely.
- **F-02:** Bench-week fault injection rides **Plan 04-07's existing HIL
  nightly cron unchanged** — the nightly already exercises 12 scenarios
  (incl. SIM-app, registration, QMI-hang, RF-via-synthetic-signal). No
  Phase 5 fault-injection code added. Bench nightly pass/fail is part of
  the bench soak signal.
- **F-03:** **No natural-fault minimum** on the field box. The 14-day
  field soak does not require any minimum number or kind of natural
  recovery events to exit. Fault-path coverage is provided offline by the
  replay-harness gate against the 30-day trace bundle.
- **F-04:** Abort criterion for the soak windows is **threshold-based**,
  not zero-tolerance: a budget of **1 minor violation per week** (of any
  of the 3 S-01 gates, or daemon-won't-start) is permitted, investigated,
  and dispositioned without resetting the soak clock. A 2nd violation in
  the same week resets the clock. Definitions of "minor violation" and
  "dispositioned" flow to planning — see Claude's Discretion below.

### Fleet fixture capture (X-*)

- **X-01:** New CLI subcommand `spark-modem ctl capture-fleet-fixture
  --out=<dir>` — operator runs once per fleet box to emit the per-box
  fixture directory. Reuses the existing `qmi/` wrapper module (Plan
  02-02's `QmiWrapper.dms_get_revision` etc.) and Plan 02-03's
  `ZaoLogParser`. Lands under `src/spark_modem/cli/` following the
  `ctl <verb>` argparse subparser pattern Plan 02-09 established.
- **X-02:** A captured fleet fixture contains (no PII):
  - `triple.json` — `{em7421_firmware, zao_sdk, libqmi}` strings,
    captured at one wallclock moment.
  - `qmi/<modem_usb_path>/<verb>.txt` — raw stdout of 6–8 qmicli verbs
    per modem: `dms_get_revision`, `dms_get_operating_mode`,
    `uim_get_card_status`, `nas_get_signal_info`, `wds_get_current_
    settings`, `nas_get_serving_system`, `wds_get_packet_service_status`,
    `wds_get_profile_settings` (final list locked during planning).
    ICCID/IMSI/IP fields scrubbed at capture time.
  - `zao-log-sample.txt` — last 50 RASCOW_STAT lines from the Zao log.
- **X-03:** **Daemon preflight refuses to start if its current
  (firmware, SDK, libqmi) triple is outside the known set.** On preflight
  the daemon computes the local triple, hashes it, looks it up against
  the captured fleet-fixture index (baked into the `.deb` at
  `/etc/spark-modem-watchdog/known-fleet/<sha>.json` or similar — exact
  shape decided in planning). Unknown → structured `journalctl` ERROR +
  `sd_notify STATUS=` + non-zero exit. Forces fixture capture before any
  fleet box can run v2 in Phase 6. **This is a new behavior added by
  Phase 5 to the daemon's preflight surface.**
- **X-04:** Capture timing: the on-site engineer runs
  `capture-fleet-fixture` on **each fleet box during the physical access
  window for Phase 6 prep**, committing one PR per box. All per-box PRs
  are batched into a single Phase 6 prerequisite PR. Phase 6 cannot
  start until that batched PR merges. The bench Jetson and the field-
  shadow box are captured as part of this batch (they count toward the
  known set even though they were used in Phase 5 itself).

### Claude's Discretion

- The exact list of qmicli verbs in X-02 (6–8 range; locked at planning).
- The shape of the known-set index baked into the `.deb` (X-03: directory
  of `<sha>.json` files vs single index.json vs Python module import vs
  YAML). Lowest-friction choice that doesn't bloat the `.deb`.
- The mechanism for the on-site engineer to query a box's current triple
  *without* the daemon (so they can capture before the daemon will
  start — chicken-and-egg). Options: `spark-modem ctl capture-fleet-
  fixture --no-preflight`, or a separate `spark-modem ctl show-triple`,
  or the capture command bypasses preflight by design.
- SIGNOFF.md template structure — checklist items per S-01 gate, where
  the replay-harness JSON output is referenced, free-text rationale
  section shape.
- Definitions of "minor violation" and "dispositioned" for the F-04
  abort threshold. "Minor" likely means: gate violation that did not
  cause customer-visible outage AND had an attributable root cause AND
  the root cause is fixable in <4h. "Dispositioned" likely means: root
  cause filed in repo issues + fix PR opened (not necessarily merged).
  Final wording in planning.
- The shape of the "act on Zao-active line" post-hoc query (S-01 #2):
  reuse an existing pytest test against an events.jsonl + Zao log pair,
  or a new `spark-modem ctl audit-soak --since=<duration>` subcommand,
  or a one-off Python script in `tools/`. Lowest-friction wins.
- Mechanism for the "unexplained Exhausted" detection (S-01 #3) — replay
  decay logic against the soak-window events; reuses
  `policy.transitions` and `policy.gates` modules; likely a tools/ script.
- The "run-once at Phase 5 exit" R-02 mechanism — manual `pytest
  tests/replay/ -v --replay-fresh` or a dedicated runbook step.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 5 scope anchor (read these first to understand what's being built)

- `.planning/ROADMAP.md` § "Phase 5: Bench & Field Shadow" — phase goal,
  depends-on, success criteria (read through the v1-retired pivot above;
  SC#1/#2/#3 reference dead artifacts).
- `docs/MIGRATION.md` § 3 + § 4 (Phases 1–2 — stale framing; reference
  for the original intent only).
- `docs/MIGRATION.md` § 10 row 1 — the "dry-run agreement biased toward
  healthy cycles" risk; origin of the ≥0.95 gate.
- `.planning/research/PITFALLS.md` § 15.1 — the fault-cycle-agreement
  rationale and the "≥95% on fault cycles, not aggregate ≥99%" decision.

### Replay-harness substrate (R-* decisions hinge on these)

- `tests/replay/test_v1_agreement.py` — the test file the gate runs from
  (Plan 02-10 + Plan 04-07 wire it).
- `tests/replay/conftest.py` — Plan 04-07's R-03 hard-fail at <0.95
  fault-cycle agreement (the threshold constant in this file).
- `tests/fixtures/replay/v1-30d/README.md` — Plan 04-06's redaction
  contract (sha256[:8] for ICCID/IMSI/IP).
- `tools/pull_replay_traces.py` — Plan 04-06's LFS pull tool that R-01
  exercises.
- `.github/workflows/hil.yml` — Plan 04-06's HIL nightly cron the bench
  week rides (F-02).

### Existing daemon surface the new code plugs into (X-* decisions)

- `src/spark_modem/qmi/wrapper.py` — `QmiWrapper.dms_get_revision` /
  `uim_get_card_status` / etc. for X-02 fixture capture.
- `src/spark_modem/zao_log/` — Plan 02-03's `ZaoLogParser` for the
  X-02 zao-log-sample.txt step.
- `src/spark_modem/cli/` — Plan 02-09 `ctl <verb>` argparse subparser
  pattern; X-01 lands here.
- `src/spark_modem/daemon/main.py` — Plan 03-06 preflight surface
  (kernel-module probe + topology probe); X-03 adds the third probe.
- `src/spark_modem/cli/clients.py` — `build_default_settings` + fake
  client patterns for testing the new capture subcommand.
- `tests/fixtures/qmicli/<intent>/<version>/<scenario>.txt` — Plan
  02-02's per-libqmi-version fixture tree pattern; X-02 mirrors its
  shape for `tests/fixtures/fleet/<box-id>/qmi/<modem>/<verb>.txt`.
- `tests/hil/fault_inject.py` — Plan 04-06's helpers; F-02 rides these
  via the existing HIL nightly, no new code added.

### ADRs / specs that govern the gates we measure against

- `docs/adr/0006-counter-decay-on-healthy.md` (amended in Phase 1) — the
  "unexplained Exhausted" criterion (S-01 #3) is rooted here.
- `docs/adr/0008-state-machine-5-plus-2.md` — `exhausted` state shape
  the S-01 #3 query examines.
- `docs/adr/0003-zao-log-authoritative.md` — the "no action on Zao-
  active line" rule S-01 #2 enforces.
- `docs/adr/0013-prom-metric-surface.md` — `modem_state_value{modem}`
  + `cycle_duration_seconds` + `daemon_self_health` metrics the soak
  monitoring reads.
- `.planning/PROJECT.md` § 8 (Success metrics) — M4 / M5 / M6 metric
  definitions referenced by S-01 / S-01.1.
- `docs/RECOVERY_SPEC.md` § 8 — the streak+decay+counter-reset+state-
  write atomic ordering that "unexplained Exhausted" detection must
  understand.

### Adjacent surfaces (read for context, not for direct change)

- `.planning/phases/04-destructive-actions-hil/04-CONTEXT.md` §
  "Phase 5 (Bench & Field Shadow)" deferred items — the Phase 4
  handoff list (real-fleet 1199:9051 stuck-bootloader rate measurement,
  RF-floor tuning per geography, Zao restart-race observation,
  bench-Jetson SIM-cycle automation possibly).
- `docs/RUNBOOK.md` — operator-facing daemon ops doc; new Phase 5
  bench/field soak runbook lands as an amendment or new section here.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`tools/pull_replay_traces.py`** (Plan 04-06) — already implements the
  LFS pull + sha256[:8] redaction + commit-shape contract for v1 traces.
  R-01 just runs it; no code change.
- **`tests/replay/test_v1_agreement.py`** + **`tests/replay/conftest.py`
  R-03 hook** (Plans 02-10 + 04-07) — the gate substrate. R-02 just
  triggers it; no code change beyond the freshly-pulled bundle.
- **`tests/hil/fault_inject.py`** + **`.github/workflows/hil.yml`** (Plan
  04-06) — the bench fault-injection harness. F-02 rides it unchanged.
- **`src/spark_modem/qmi/wrapper.py`** (Plan 02-02) — 11 qmicli methods
  including all the verbs X-02 needs (`dms_get_revision`,
  `uim_get_card_status`, `nas_get_signal_info`,
  `wds_get_current_settings`, ...). The new capture subcommand
  composes these.
- **`src/spark_modem/cli/ctl.py`** (Plan 02-09) — `ctl <verb>` argparse
  subparser pattern; `capture-fleet-fixture` lands as another verb.
- **`src/spark_modem/cli/clients.py`** (Plan 02-09) — `build_default_
  settings` + `FixtureRunner` / `_InventoryFromFile` / `_NoZaoTailer`
  fakes for hardware-free unit tests of the new subcommand.
- **`src/spark_modem/daemon/main.py`** (Plan 03-06) — preflight surface
  (`preflight_check_kernel_modules`, `preflight_check_topology`); X-03
  adds `preflight_check_known_fleet_triple`.
- **`src/spark_modem/state_store/locks.py`** (Plan 01-04) — atomic
  temp+rename+fsync helpers if any new file lands in `/etc/spark-modem-
  watchdog/known-fleet/` post-install.
- **PII redaction sha256[:8] discipline** (Plan 02-09 `ctl support-
  bundle`) — the X-02 "no PII" requirement uses the same shape.

### Established Patterns

- **`ctl <verb>` CLI subcommands** are argparse subparsers under
  `src/spark_modem/cli/ctl.py`. New verb adds an `argparse_subparser` +
  `cmd_<verb>(args)` function + entry in the dispatch dict. ~30 LOC
  scaffold, plus the verb body. Hardware-free unit tested via
  `cli/clients.py` fakes.
- **Per-libqmi-version fixture tree** at `tests/fixtures/qmicli/<intent>
  /<version>/<scenario>.txt` (Plan 02-02). X-02 mirrors the shape under
  `tests/fixtures/fleet/<box-id>/qmi/<modem>/<verb>.txt`.
- **Daemon preflight checks** (Plan 03-06) — synchronous, called from
  `daemon/main.py` before sd_notify READY=1. Each check returns a
  `PreflightResult` enum + structured `journalctl` ERROR on failure
  + non-zero exit. X-03 follows this shape.
- **Plan 04-07 hardware-loop gate pattern** — "exit gate contingent on
  first green nightly HIL run" (Plan 04-07 EXIT). Phase 5 reuses the
  same idiom for "exit gate contingent on SIGNOFF.md + replay-harness
  artifact merged".

### Integration Points

- **`.deb` postinst** (Plan 01-02) — currently masks `ModemManager.
  service`. X-03 adds: install the known-fleet index files under
  `/etc/spark-modem-watchdog/known-fleet/`. The fixture-capture
  subcommand emits them; the .deb build pipeline collects them from
  `tests/fixtures/fleet/*/triple.json` (or similar) into the package.
- **systemd unit** (Plan 03-08) — no change. Preflight runs via
  `ExecStartPre=` already wired for `spark-modem ctl config-check`;
  X-03's new check is a startup-internal preflight, not a separate
  `ExecStartPre`. (Decision deferred to planning if the new check
  should be its own `ExecStartPre` step instead.)
- **`docs/RUNBOOK.md`** — gets the new "Phase 5 bench/field soak
  runbook" amendment + SIGNOFF.md template reference.
- **`.planning/phases/05-bench-field-shadow/SIGNOFF.md`** (new) — the
  operator-facing checklist the on-site engineer commits before Phase 6.
- **CI workflows** — no Phase 5-specific CI change. The existing
  replay-harness in `tests/replay/` already runs in CI on every push;
  Phase 5 just refreshes the bundle it runs against (LFS PR).

</code_context>

<specifics>
## Specific Ideas

- The on-site engineer is the single human in the Phase 5 loop. They:
  archive v1 logs (R-01), run the replay-harness one-shot at exit (R-02),
  monitor bench week (S-03), green-light field deploy, monitor field
  weeks, run `capture-fleet-fixture` per box (X-04), commit per-box PRs
  + batched-Phase-6-prereq PR, author SIGNOFF.md. Plan task assignment
  should reflect this concentration.
- The X-03 chicken-and-egg of "daemon refuses to start until triple is
  in known set, but the engineer needs to capture the triple on a
  daemon-less box" must be solved. Likely: `capture-fleet-fixture`
  doesn't require the daemon to be running; it shells out to qmicli
  directly via the existing `subproc.runner.run` wrapper. Whether this
  bypasses the same SP-04 lint gates the daemon does — confirm in
  planning.
- F-04's 1-violation-per-week budget is generous; the user explicitly
  chose this over zero-tolerance. The audit trail must record every
  violation regardless of disposition, so reviewers can revisit the
  judgment.
- "No injection on field box" (F-01) is a deliberate conservatism
  choice — Phase 5 originally specified daily synthetic injection in
  the field per ROADMAP SC#3. The user disposition is to drop it; the
  cost is less fault-path coverage in real conditions, the benefit is
  zero customer-outage risk from synthetic injection.
- Quarterly v1-trace refresh ownership (post-Phase-5) is not nailed
  down; R-04 only commits to the day-1 refresh.

</specifics>

<deferred>
## Deferred Ideas

### Doc-rewrite housekeeping (out of Phase 5; flagged for Phase 7 or a dedicated doc-fixup phase)

- **ROADMAP.md Phase 5 SC#1 / SC#2 / SC#3 rewording** — they describe
  the original shadow-vs-v1 framing and the `tools/compare_v1_v2.py`
  deliverable, neither of which exists in the v1-retired world. Phase 5
  plan execution will simply not satisfy these literally; the SCs need
  rewording or a "superseded by CONTEXT.md scope_pivot" annotation.
- **MIGRATION.md Phases 1–2 framing** — stale by the same reasoning.
  Either rewrite as "v2 live + soak (no v1 to compare against)" or
  annotate inline.
- **PROJECT.md "v1 currently keeps a real fleet online"** — single-line
  edit but consequential; same line appears in `CLAUDE.md`. Both stale.
- **PROJECT.md ▸ Migration ▸ Phase 1 / Phase 2 checkboxes** — reword
  from "v2 dry-run alongside v1" to "v2 live soak (v1 retired)".
- **ADR-0014 candidate** — "v1 retired before Phase 5; shadow-vs-v1
  design from MIGRATION.md Phases 1–2 is moot". Records the pivot for
  posterity. Lightweight; could land as part of Phase 5 if user later
  decides, but not committed to Phase 5 scope today.

### Not built in Phase 5 (was central to original spec)

- **`tools/compare_v1_v2.py`** — explicitly NOT built. The replay-harness
  in `tests/replay/` is the sole agreement-judgment substrate. If a
  future "soak monitoring dashboard" is wanted (Prom-query + events.jsonl
  scan to show the 3 soak gates), it can live there, but that is not
  Phase 5's job and was not asked for.
- **Shadow `.deb` packaging story** — no `99-shadow.yaml`, no `spark-
  modem-watchdog-v2.service` rename, no `-v2`-suffixed paths. v2 runs
  at the canonical `/var/lib/spark-modem-watchdog/`, `/var/log/spark-
  modem-watchdog/`, `/run/spark-modem-watchdog/` from day 1.
- **Field-box synthetic fault injection** — F-01 disposition. The
  Phase 4 fault-injection helpers (`tests/hil/fault_inject.py`) are
  bench-only; no field-side variant is built.

### v2.1 candidates (carried forward from Phase 4 04-CONTEXT.md)

- **Real-fleet 1199:9051 stuck-bootloader rate measurement** — Phase 4
  shipped the routing; Phase 5 could measure during the 2-week field
  soak via the existing `events.jsonl`, but this is informational, not
  gate-bearing.
- **D-Bus subscription to zao-infra-ctrl.service** — ADR-0014 candidate
  if Phase 5 bench/field soak surfaces flakiness from Zao restart races.
- **Real-fleet RF-environment thresholds** — RSRP/RSRQ/SNR floors are
  RELOAD_DATA tunable; Phase 5 cohorts may reveal that some geographies
  need different floors. YAML edit + SIGHUP, no code.
- **`ctl simulate-issue`** (SIM-01) — operator-facing fault injection
  surface. Deferred from Phase 4 to v2.1; remains deferred since F-01
  said no field injection.
- **Per-MCC signal-gate threshold override in carrier table** — same
  story: Phase 5 may reveal need; revisit in v2.1.

### Tactical / planning-time

- The exact list of qmicli verbs in X-02 (6–8 range).
- Known-set index shape in the `.deb` (X-03): directory of `<sha>.json`
  vs single index.json vs YAML vs Python module.
- "Minor violation" and "dispositioned" definitions for F-04 budget.
- "Act on Zao-active line" post-hoc query mechanism (S-01 #2).
- "Unexplained Exhausted" detection mechanism (S-01 #3).
- SIGNOFF.md template structure.
- The X-03 chicken-and-egg fix: `--no-preflight` flag on capture-fleet-
  fixture vs `ctl show-triple` companion vs capture bypasses preflight.

### Unrelated future work

- **Phase 5 replay-harness as CI gate going forward** — R-02 ran it
  one-shot; whether Phase 6 / 7 wire it into commit-CI is a Phase 6
  decision, not a Phase 5 one.

</deferred>

---

*Phase: 05-bench-field-shadow*
*Context gathered: 2026-05-11*
