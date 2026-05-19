# S11: Cutover & Fleet Rollout — Research

**Researched:** 2026-05-19
**Domain:** Operational delivery — no new code-introducing requirements (Phase 6 has 0 FR/NFR IDs). Documentation rewrite, health-gate definitions, validation tooling, and cutover runbook.
**Confidence:** HIGH on what exists and what's missing; MEDIUM on v1 rollback .deb feasibility (v1 was never packaged); HIGH on the v1-retired pivot implications.
**Depth:** Targeted research — known technology, established codebase patterns, but the v1-retired scope pivot from 2026-05-11 invalidates large sections of `docs/MIGRATION.md` and requires a rewrite.

---

## 1. Summary

S11 is a **documentation and tooling delivery slice**, not a code-feature slice. All daemon code is complete through Phase 05.6. The `.deb` builds, installs, and runs on bench Jetson. The gating prerequisite is Phase 5 exit (HUMAN-UAT: 0/10 items passed as of 2026-05-19 — the 3-4 week operator soak campaign has not started).

The critical context change is the **v1-retired pivot** (locked in `05-CONTEXT.md` on 2026-05-11): v1 is already retired across the entire fleet. This invalidates MIGRATION.md Phases 1-2 (shadow-alongside-v1), the `tools/compare_v1_v2.py` tool (never built), `99-shadow.yaml`, and all `-v2`-suffixed paths. The cutover simplifies to: `apt install` the v2 `.deb` → `systemctl enable --now` → verify Healthy within 60s.

### What this slice must deliver

1. **MIGRATION.md rewrite** — remove dead Phases 1-2 framing; rewrite Phases 3-5 procedures to reflect v1-retired reality (no unmask/remask dance, no shadow config removal, no `-v2` path migration).
2. **Per-box cutover runbook** — operator-facing step-by-step for the simplified cutover (extracted/simplified from rewritten MIGRATION.md §5).
3. **Health-gate PromQL definitions** — concrete queries for the 4 canary gates (ROADMAP SC#2): exhausted-time, destructive-reset rate, session-disconnect rate, daemon-crash count.
4. **Post-cutover validation script** (`tools/validate_cutover.py`) — automated per-box health check after cutover (daemon up, all modems Healthy, metrics scrape working, webhook delivery test).
5. **ADR-0014** — formal record of the v1-retired pivot decision (candidate noted in `05-CONTEXT.md` but never written).
6. **Communication templates** — Phase 3 site email, Phase 4/5 ops notices (MIGRATION.md §11 references these but they don't exist).
7. **Stale-doc cleanup** — update `docs/PRD.md` ("v1 currently keeps a real fleet online"), `.planning/PROJECT.md`, and `ROADMAP.md` Phase 5 SC#1-3 to reflect the pivot.

### What this slice does NOT deliver

- Fleet management tool (external NOC/SRE infrastructure — S11 defines the contract/interface, not the tool).
- v1 rollback `.deb` — MIGRATION.md §5 references `spark-modem-watchdog-v1_1.0.0_all.deb` for emergency rollback. v1 was never packaged as a `.deb`. Since v1 is already retired, the rollback story changes: rollback = `apt remove spark-modem-watchdog` + manually re-deploy v1 bash scripts (or accept that v1 rollback is no longer viable, since v1 is already gone). **This is the highest-risk open question** — the planner must decide whether to (a) build a v1 `.deb` from the legacy bash scripts, (b) document a manual v1 rollback procedure, or (c) accept that rollback is v2→v2-previous-version only.
- Canary batch orchestration automation (fleet-management tool's job).
- Code changes to the daemon or CLI.

---

## 2. Existing Infrastructure Audit

### What's ready (complete, tested, deployed)

| Artifact | Status | Path |
|---|---|---|
| systemd unit file | Complete (Phase 05.6) | `debian/spark-modem-watchdog.service` |
| Post-install script | Complete | `debian/spark-modem-watchdog.postinst` |
| Daemon entry point | Complete (Phase 05.6) | `src/spark_modem/daemon/main.py` |
| `.deb` build pipeline | Complete | `scripts/build_deb.sh` + `.github/workflows/build-deb.yml` |
| CI container install verification | Complete (Phase 05.1 V-02) | `.github/workflows/build-deb.yml` |
| Day-one carrier table (IL/US/GB/DE) | Shipped | `debian/conf.d/00-carriers.yaml` |
| Known-fleet preflight check | Complete (Phase 5 X-03) | `src/spark_modem/daemon/preflight_triple.py` |
| Prometheus metrics surface | Complete (ADR-0013) | `src/spark_modem/status_reporter/metrics_registry.py` |
| Replay-harness exit gate | Complete (Phase 2 R-01..R-03) | `tests/replay/test_v1_agreement.py` |
| Soak audit tools | Complete | `tools/audit_soak_zao.py`, `tools/audit_soak_exhausted.py` |
| Operator runbook (steady-state) | Draft | `docs/RUNBOOK.md` |
| Soak runbook (Phase 5) | Complete | `.planning/phases/05-bench-field-shadow/SOAK_RUNBOOK.md` |
| HMAC webhook signing | Complete (ADR-0011) | LoadCredential= + placeholder in postinst |

### What's missing (S11 deliverables)

| Gap | Why it matters | Priority |
|---|---|---|
| MIGRATION.md rewrite | Current doc references dead artifacts (99-shadow.yaml, compare_v1_v2.py, -v2 paths); operators will be confused | P0 |
| Post-cutover validation script | No automated way to verify a box is healthy after cutover | P0 |
| Health-gate PromQL definitions | ROADMAP SC#2 references 4 fleet-aggregate gates but no concrete queries exist | P0 |
| ADR-0014 (v1-retired pivot) | Decision is locked in 05-CONTEXT.md but not formally recorded | P1 |
| Per-box cutover runbook | Operators need a simplified step-by-step (current MIGRATION.md §5 is stale) | P1 |
| Communication templates | MIGRATION.md §11 references them; they don't exist | P2 |
| Stale-doc cleanup (PRD, PROJECT.md, ROADMAP SC#1-3) | "v1 currently keeps a real fleet online" is wrong; creates confusion | P2 |

---

## 3. v1-Retired Pivot Impact on MIGRATION.md

The scope pivot from 2026-05-11 (`05-CONTEXT.md` §scope_pivot) means:

### Dead sections (rewrite or remove)

- **Phase 0 §2** — "HIL job runs against bench Jetson" is fine; "v2 dry-run on captured v1 logs" framing needs updating (replay-harness is the mechanism, not shadow-mode).
- **Phase 1 §3** — entirely dead. `spark-modem-watchdog-v2.service`, `99-shadow.yaml`, `-v2` shadow paths, `tools/compare_v1_v2.py` hourly compare — none of this was built. Replace with: "v2 deployed live on bench Jetson for 1-week soak."
- **Phase 2 §4** — same; dead. Replace with: "v2 deployed live on field box for 2-week soak."
- **Phase 3 §5** — partially stale. The "Stop and disable v1" / "Move v2 to canonical paths" / "Remove 99-shadow.yaml" dance is dead because v2 already runs at canonical paths. Simplify to: `apt install` + `systemctl enable --now` + verify.
- **Rollback §5** — references `spark-modem-watchdog-v1_1.0.0_all.deb` which doesn't exist and may not be buildable.
- **Phase 4 §6** — `spark_modem_state{state="exhausted"}` metric name is wrong (actual metric is `modem_state_value{modem}` with integer encoding per ADR-0013). PromQL must use the integer encoding.
- **Phase 6 §8** — references `apt purge spark-modem-watchdog-v1` — there is no v1 `.deb` to purge.

### Surviving sections (update metric names only)

- **Phase 4 §6** — canary gates concept survives; metric names and PromQL need updating.
- **Phase 5 §7** — fleet-management tool gating concept survives.
- **§9 Data migration** — still correct (v2 starts fresh).
- **§10 Risks** — mostly still valid; "v1 deb in hand" risk is now moot (or elevated — depends on rollback decision).
- **§11 Communication** — plan survives; templates need writing.

---

## 4. Health-Gate PromQL Definitions

The Prometheus metrics surface (`src/spark_modem/status_reporter/metrics_registry.py`) provides these relevant metrics for fleet gates:

| Metric | Type | Labels | Purpose |
|---|---|---|---|
| `modem_state_value` | Gauge | `{modem}` | Integer-encoded state (0=unknown, 1=healthy, 2=degraded, 3=recovering, 4=exhausted) |
| `state_duration_seconds` | Histogram | `{modem, state}` | Time spent in each state (MTTR computation) |
| `actions_total` | Counter | `{kind, modem, result}` | Recovery action counts by type |
| `cycle_duration_seconds` | Histogram | (none) | Per-cycle wall-clock duration |
| `webhook_delivery_total` | Counter | `{result}` | Webhook delivery outcomes |
| `cycle_drift_seconds` | Gauge | (none) | Cycle scheduling health |
| `daemon_self_health` | Counter | `{kind}` | RSS tripwire events |

### Gate definitions (ROADMAP SC#2)

**Gate 1: Exhausted-time ≤ baseline**
```promql
# Per-modem time-in-exhausted over 24h window.
# ADR-0013: modem_state_value == 4 means exhausted.
sum by (modem) (
  rate(state_duration_seconds_sum{state="exhausted"}[24h])
)
```

**Gate 2: Destructive-reset rate ≤ baseline + 10%**
```promql
# Destructive actions: modem_reset, usb_reset, driver_reset.
sum(rate(actions_total{kind=~"modem_reset|usb_reset|driver_reset"}[24h]))
```

**Gate 3: Session-disconnect rate ≤ baseline + 10%**
This gate is trickiest — the daemon doesn't directly export a "session disconnect" metric. The proxy is transitions out of `healthy` state:
```promql
# Approximation: state transitions from healthy→degraded imply session disruption.
# Requires recording-rule or query against state_duration_seconds histogram.
# Alternative: count actions_total with any kind (each action implies a disruption).
sum(rate(actions_total[24h]))
```
**Risk:** The "session-disconnect rate" gate as written in MIGRATION.md may not be directly expressible from v2 metrics. The planner should decide whether to (a) add a dedicated `session_disconnect_total` counter, (b) use `actions_total` as a proxy, or (c) redefine the gate in terms of available metrics. Recommendation: (b) — `actions_total` is a strict superset of session disruptions caused by v2.

**Gate 4: Zero daemon crashes in 24h**
```promql
# This is a systemd-level check, not a Prom query.
# journalctl -u spark-modem-watchdog --since '24 hours ago' | grep -c 'Main process exited'
# Or: check `process_start_time_seconds` gauge resets.
changes(process_start_time_seconds[24h]) == 0
```
**Note:** `process_start_time_seconds` is a default metric from `prometheus_client`. If the daemon restarts, this gauge resets, and `changes()` detects it.

---

## 5. Post-Cutover Validation Script Design

`tools/validate_cutover.py` — run on each box after `.deb` install + service start.

**Checks:**
1. `systemctl is-active spark-modem-watchdog.service` → `active`
2. `spark-modem status --json` → all 4 modems present, none `exhausted`
3. Prometheus UDS scrape (`curl --unix-socket /run/spark-modem-watchdog/metrics.sock`) → non-empty response with `modem_state_value` for all 4 modems
4. `status.json` exists and is recent (mtime < 2× cycle interval)
5. HMAC secret is not the placeholder sentinel
6. Carrier-table SHA matches expected fleet value
7. Known-fleet triple check (daemon started successfully = triple is known)
8. `events.jsonl` is being written (size increasing)

**Exit codes:** 0 = all green, 1 = soft failure (non-critical check failed), 2 = hard failure (daemon not running or modem unhealthy).

**Pattern:** Follow existing `tools/audit_soak_*.py` style — standalone script, structured JSON output, exit-code-based pass/fail.

---

## 6. Rollback Strategy (Open Question)

MIGRATION.md §5 assumes `spark-modem-watchdog-v1_1.0.0_all.deb` exists for emergency rollback. Reality:

- v1 is a collection of bash scripts (`diag.sh`, `recovery.sh`, `auto_profile.sh`, `zao_reset_line.sh`) that were never `.deb`-packaged.
- v1 is already retired across the fleet.
- Building a v1 `.deb` now means packaging legacy bash scripts that haven't been maintained since the v2 rewrite began.

**Options:**

| Option | Effort | Risk | Recommendation |
|---|---|---|---|
| A: Build v1 `.deb` from legacy scripts | Medium (packaging + testing) | Medium (scripts may be stale) | No — v1 is dead code, packaging it creates false confidence |
| B: Document manual v1 reinstall procedure | Low (just docs) | High (untested, scripts may not work on current fleet state) | No — same false confidence problem |
| C: Rollback = v2 previous version only | Zero effort | Low (v2 `.deb` is well-tested, `apt install` downgrade works) | **Yes** — honest rollback story; v2 `.deb` pipeline is proven |

**Recommendation:** Option C. Rollback from v2.0.0 is to v2.0.0-rc.N (the last known-good `.deb`). The MIGRATION.md rewrite should state this explicitly and remove the v1 `.deb` references. The fleet management tool's apt repo should retain the last 3 v2 `.deb` versions.

---

## 7. Natural Seams (Independent Work Units)

| # | Task | Dependencies | Files | Verify |
|---|---|---|---|---|
| T1 | ADR-0014: v1-retired pivot | None | `docs/adr/0014-v1-retired-pivot.md` | File exists, follows ADR template (0001-0013 pattern) |
| T2 | MIGRATION.md rewrite | T1 (references ADR-0014) | `docs/MIGRATION.md` | `grep -c '99-shadow\|compare_v1_v2\|watchdog-v2\|-v2/' docs/MIGRATION.md` == 0; all Phase procedures updated |
| T3 | Health-gate PromQL definitions | None | New file: `docs/FLEET_GATES.md` or section in MIGRATION.md | PromQL queries parse (syntax-valid); reference only metrics in `metrics_registry.py` |
| T4 | Post-cutover validation script | None | `tools/validate_cutover.py` | `python tools/validate_cutover.py --help` exits 0; mypy + ruff clean |
| T5 | Stale-doc cleanup | T1, T2 | `docs/PRD.md`, `.planning/PROJECT.md`, `.planning/ROADMAP.md` | `grep -c 'v1 currently keeps' docs/PRD.md .planning/PROJECT.md` == 0 |
| T6 | Communication templates | T2 | `docs/templates/` or section in MIGRATION.md | Templates exist for Phase 3/4/5 notices |
| T7 | Per-box cutover runbook | T2 | `docs/CUTOVER_RUNBOOK.md` or section in rewritten MIGRATION.md | Step-by-step procedure matches v1-retired reality; no stale references |

**First proof:** T2 (MIGRATION.md rewrite) — it's the highest-value deliverable and unblocks T5/T6/T7. T4 (validation script) is the highest-risk code artifact and can run in parallel.

**Parallelizable:** T1 + T3 + T4 can all start independently. T2 can start after T1. T5/T6/T7 depend on T2.

---

## 8. Implementation Landscape

### Existing patterns to follow

- **ADR format:** `docs/adr/0001-language-python.md` through `0013-metric-surface.md`. Standard ADR template: Status, Context, Decision, Consequences.
- **Audit tool pattern:** `tools/audit_soak_zao.py` and `tools/audit_soak_exhausted.py` — standalone Python scripts with argparse, structured JSON output, sys.exit(0/1).
- **Documentation style:** All `docs/*.md` files use the same header format (Status/Owner/Last-updated table).

### Constraints

- **No code changes to `src/spark_modem/`** — this is a delivery phase; the daemon is feature-complete.
- **Phase 5 exit is the hard prerequisite** — S11 deliverables can be prepared now but the actual cutover cannot begin until the operator soak campaign (HUMAN-UAT items 1-10) completes. The planner should note this: S11 tasks are "prepare the cutover materials" not "execute the cutover."
- **Fleet management tool is external** — S11 defines the contract (health-gate PromQL, batch-gating interface) but does not build the tool.
- **The validation script must not import from `spark_modem`** — it runs on the target box where the daemon is installed at `/opt/spark-modem-watchdog/`, not from the dev tree. It should use subprocess calls to `spark-modem` CLI and direct file/socket reads. Alternatively, it can be a bash script like the existing `postinst_smoke_test.sh`.

### Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Phase 5 soak hasn't started (0/10 HUMAN-UAT) | S11 deliverables are ready but can't be validated in production | Prepare all materials; gate actual fleet cutover on Phase 5 exit |
| "Session-disconnect rate" gate not directly expressible from v2 metrics | Gate 3 of ROADMAP SC#2 may need redefinition | Use `actions_total` as proxy; document the approximation |
| v1 rollback story is a fiction (no v1 `.deb` exists) | Operators may expect v1 rollback availability | Explicitly document v2→v2-prev as the rollback path; remove v1 `.deb` references |
| MIGRATION.md rewrite scope creep | Touching a 230-line doc that other docs reference | Scope to: remove dead phases, update metric names, fix rollback story, add v1-retired context. Don't restructure unnecessarily. |
| Carrier-table convergence unverified on non-IL boxes | Day-one carrier table includes US/GB/DE marked `unverified: true` | Document as a known limitation; convergence monitoring via `carrier_table_sha256` in `status.json` |

---

## 9. Skill Recommendations

- **write-docs** — for the MIGRATION.md rewrite and communication templates (multi-doc coherence matters).
- **observability** — for health-gate PromQL definitions and validation script design.
- **review** — for the final MIGRATION.md rewrite (catch stale references).

No external library documentation lookups needed — all tooling uses stdlib + existing project dependencies.

---

## 10. Verification Plan

| Check | Command | Expected |
|---|---|---|
| No stale shadow refs in MIGRATION.md | `grep -cE '99-shadow\|compare_v1_v2\|watchdog-v2\.service\|-v2/' docs/MIGRATION.md` | 0 |
| ADR-0014 exists | `test -f docs/adr/0014-v1-retired-pivot.md` | true |
| Validation script runs | `python tools/validate_cutover.py --help` | exit 0 |
| Health gates reference real metrics | `grep -oP 'modem_state_value\|actions_total\|state_duration_seconds\|process_start_time_seconds' docs/FLEET_GATES.md \| sort -u` | subset of metrics_registry.py names |
| No stale "v1 currently keeps" | `grep -rc 'v1 currently keeps' docs/ .planning/` | 0 |
| Type check clean | `uv run mypy --strict tools/validate_cutover.py` | 0 errors |
| Lint clean | `uv run ruff check tools/validate_cutover.py` | 0 errors |
| Existing tests still pass | `uv run pytest tests/unit/ -q` | all pass, no regressions |
