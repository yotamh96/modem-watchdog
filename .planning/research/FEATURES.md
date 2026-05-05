# FEATURES research — spark-modem-watchdog v2

**Research mode:** Project Research (Features dimension)
**Confidence:** HIGH for ecosystem comparison and table-stakes categorization (verified against 7 product docs); MEDIUM-HIGH for opinionated pushbacks (reasoned from the docs/ themselves + comparable products).

---

## 1. Bottom line up front

The docs/ proposal is **above industry baseline for table-stakes, defensibly opinionated on differentiators, and correctly disciplined about anti-features.** The largest categorical gaps are in NOC-side ergonomics (alert deduplication, multi-transition payloads, signed webhooks) and in fleet-level observability beyond a single box (correctly scoped out as NG3, but creates a hand-off contract not yet pinned down). The proposed 7-state machine is one state too many. Israel-only carriers from day one is a small, real, avoidable cost. Support-bundle and per-modem dry-run are correctly classified as table-stakes; HMAC signing is mis-classified.

---

## 2. Comparable-products comparison

| Capability | ModemManager | mwan3 (OpenWrt) | Cradlepoint NCM | Sierra AirLink ALMS | Peplink SpeedFusion | Robustel R5020 / RCMS | Digi WR54 | docs/ proposal |
|---|---|---|---|---|---|---|---|---|
| Multi-modem support | yes (n) | n/a (per-iface) | yes (dual) | yes (dual) | yes (up to 4) | yes (dual-SIM, single radio) | yes (dual radio) | yes (4) |
| Bonding | no | no (failover only) | session-stick failover | failover | **packet-level bonding** | failover | dual-WAN failover | **delegated to Zao (correct)** |
| Auto-recovery on hung modem | partial (re-init via DBus FSM) | iface-level only (no modem reset) | yes (auto-reboot rules) | yes (cloud-driven) | yes (vendor) | yes ("watchdog") | yes (re-power after 1h dead) | **yes, escalation ladder, signal-gated** |
| Signal-quality gating on resets | no | no (it's a routing layer) | undocumented | undocumented | undocumented | undocumented | no (1h timer is blind) | **yes (differentiator)** |
| Counter decay / prevent permanent-exhausted | no | no | no | no | no | no | no | **yes (differentiator)** |
| Cross-action ladder backoff | no | no | no | no | no | no | no | **yes (differentiator)** |
| Authoritative external-source gating (e.g. Zao log) | no | no (uses ping host) | n/a | n/a | n/a | n/a | n/a | **yes (differentiator)** |
| Per-modem state machine, exposed | yes (13 states, lifecycle) | per-iface up/down | aggregated fleet view | aggregated | aggregated | aggregated | aggregated | **yes (proposed 7)** |
| Webhook/alerting | no (DBus only) | yes (via netifd hooks) | **yes (HMAC-signed)** | yes | yes | yes | yes | yes (HMAC v2.1 in docs) |
| Prometheus / pull metrics | no | no | no (proprietary push) | no | no | no | no | **yes (differentiator vs vendors)** |
| Structured event log (JSONL) replay | no | no | proprietary cloud only | proprietary cloud only | proprietary cloud only | partial | partial | **yes (differentiator)** |
| Support bundle / one-shot diagnostics | partial (`mmcli`) | no | yes ("device logs export") | yes ("on-demand reports") | yes | yes (RCMS log download) | yes | yes |
| CLI control | yes (`mmcli`) | yes (`mwan3`) | partial (web UI primary) | partial | partial | partial | partial (CLI shell) | **yes (single binary, primary)** |
| Carrier APN auto-select | yes (built-in DB) | n/a | yes (cloud DB) | yes | yes | yes | yes | **yes (config-file table)** |
| Dry-run for actions | no | no | no | no | no | no | no | **yes (differentiator)** |
| Hot-reload config | partial | yes | yes | yes | yes | yes | yes | yes (SIGHUP) |
| Spec-as-tests / fixture replay | no | no | no | no | no | no | no | **yes (differentiator)** |

**Headline:** every comparable product ships some recovery story, but **none combine signal-gating + bounded escalation + counter decay + Zao-authoritative gating + dry-run + spec-as-tests.** The docs/ proposal's differentiator stack is real.

---

## 3. Feature categorization

### 3.1 Table stakes (users will quietly leave without these)

| # | Feature | Complexity | In docs? | Notes |
|---|---|---|---|---|
| TS-1 | Auto-discover modems via udev + sysfs | M | ✅ FR-1, FR-2 | Industry baseline. |
| TS-2 | Per-modem health classification | M | ✅ FR-12 | Granularity discussed §4.1. |
| TS-3 | Bounded escalation ladder | M | ✅ FR-22 | Baseline; v1 had it. |
| TS-4 | Same-action backoff | S | ✅ FR-25 | Baseline. |
| TS-5 | One-action-per-modem-per-cycle | S | ✅ FR-20 | Baseline. |
| TS-6 | Idempotent action implementations | S | ✅ FR-27 | Baseline. |
| TS-7 | Atomic file writes for state | S | ✅ FR-62 | Baseline. |
| TS-8 | Carrier APN auto-select (MCC/MNC) | M | ✅ FR-30..33 | YAML-driven is genuinely good. |
| TS-9 | Post-write APN verification | S | ✅ FR-32 | Without it, the feature is theatre. |
| TS-10 | SIM identity persistence + swap detection | M | ✅ FR-3, FR-4 | Baseline for rugged-deployment box. |
| TS-11 | systemd `Type=notify` integration | S | ✅ FR-53 | Baseline. |
| TS-12 | Hot config reload | M | ✅ FR-54 + ARCH §10 | Deferring would be wrong. |
| TS-13 | Single CLI binary with subcommands | M | ✅ FR-50 | Baseline for daemon-on-Linux. |
| TS-14 | `--dry-run` everywhere | M | ✅ FR-28 | Differentiator vs vendors but table-stakes for self-hosted. |
| TS-15 | Structured event log (JSONL) | S | ✅ FR-40 | Baseline for alert-manager customers. |
| TS-16 | Prometheus scrape endpoint | M | ✅ FR-42 | Baseline for NOC persona. |
| TS-17 | logrotate integration | S | ✅ FR-43 | Missing it is the rookie tell. |
| TS-18 | Webhook on state transitions | M | ✅ FR-44 | Baseline for NOC integration. |
| TS-19 | Support bundle (`ctl support-bundle`) | M | ✅ NFR-22 | Confirmed table stakes — see §4.2. |
| TS-20 | PATH preflight + PID lock + atomic writes | S | ✅ FR-60..62 | Baseline. |
| TS-21 | List-form argv | S | ✅ FR-64 | v1 violated this; motivates the rewrite. |
| TS-22 | Schema-version refusal | S | ✅ NFR-43 | Baseline once schemas exist. |
| TS-23 | Fixture-driven hardware-free unit tests | M | ✅ NFR-41 | Baseline-in-2026. |
| TS-24 | Status snapshot file | S | ✅ FR-41 | Baseline. |
| TS-25 | Graceful SIGTERM (≤5 s) | S | ✅ FR-53 | Baseline. |

### 3.2 Differentiators

| # | Feature | Complexity | In docs? | Why it's a differentiator |
|---|---|---|---|---|
| D-1 | **Signal-quality gate on destructive actions** | M | ✅ FR-23, RECOVERY §6.1 | No comparable product does this. Digi's "re-power after 1h" is the anti-pattern this avoids. |
| D-2 | **Counter decay on consecutive Healthy cycles** | M | ✅ FR-26, ADR-0006 | Fixes v1's permanent-Exhausted; novel publicly. |
| D-3 | **Cross-action ladder backoff** | S | ✅ RECOVERY §6.3 | Prevents soft→modem→soft ping-pong. |
| D-4 | **Authoritative external-source gating** (Zao `RASCOW_STAT`) | M | ✅ FR-10, ADR-0003 | Domain-specific, but pattern is generalizable. |
| D-5 | **Spec-as-tests against markdown decision table** | M | ✅ TEST_STRATEGY ref, RECOVERY §11 | Rare in production daemons. |
| D-6 | **Pure-function policy engine** (Diag × State → Action[]) | M | ✅ ARCH §12, RECOVERY §1 | Enables replay, dry-run, deterministic testing. |
| D-7 | **Fixture-replay** (`--diag-fixture`) | S | ✅ FR-52 | Field-engineer answer to "what would daemon have done?". |
| D-8 | **Monotonic-clock backoff** | S | ✅ ADR-0007 | Quietly correct; most production daemons have wall-clock-step bugs. |
| D-9 | **Closed-enum issue taxonomy** | M | ✅ SCHEMA enums | A typo in v1's `detail` silently changed behavior. |
| D-10 | **Global `driver_reset` ≥75% hung AND ≥1 has signal** | S | ✅ FR-24, RECOVERY §6.4 | The "if every hung modem is RF-blocked, cause is RF not driver" insight. |
| D-11 | **Six-phase migration with shadow-mode validation** | L | ✅ MIGRATION.md | Rare discipline. |

### 3.3 Anti-features (correctly NOT building)

| # | Anti-feature | In docs? | Why correct |
|---|---|---|---|
| AF-1 | Cloud control plane / remote management | ✅ NG3 | Adding kills C20/C21 (offline install). |
| AF-2 | GUI / web UI on device | ✅ NG5 | Customer is NOC + shell; UI is dead weight + attack surface. |
| AF-3 | Multi-vendor modem support | ✅ NG4 | Premature abstraction doubles test matrix. |
| AF-4 | Replacing `qmicli` with libqmi bindings | ✅ NG6 + ARCH §5 | qmicli is the contract. |
| AF-5 | Multi-SIM / eSIM management | ✅ §9 | EM7421 is single-SIM. |
| AF-6 | Owning Zao | ✅ NG1 | Scope creep that kills the rewrite. |
| AF-7 | 5G NR-aware policy in v2.0 | ✅ §9 | Right call (observable now, actionable v2.1). |
| AF-8 | Migration of v1 state files | ✅ Out-of-scope | v1 state has no value v2 needs. |
| AF-9 | Hot-plug-of-modems-mid-flight as priority | ✅ §9 | Supported via udev, not SLA'd. |

### 3.4 Anti-features I'd add to docs/ explicit list

| # | Anti-feature | Why call it out |
|---|---|---|
| AF-10 | **No retroactive "re-decision" on past cycles** | Otherwise future maintainers will add a second policy engine via the back door. |
| AF-11 | **No predictive recovery / ML on signal trends** | Adds an ML model to a root daemon; testability collapses. |
| AF-12 | **No auto-firmware-update of EM7421** | Sierra owns their firmware; we don't. Bricked-modem risk. |
| AF-13 | **No cross-box coordination** | Coordination belongs in NOC, not the daemon. Worst-case alert storm. |

---

## 4. Validation of docs/ proposal — pushbacks and confirmations

### 4.1 The 7-state machine — PUSHBACK

**Stance:** Reduce to 5 top-level states. Keep `rf_blocked` and `disconnected` as orthogonal flags, not peers.

**Reasoning:**
- ModemManager has 13 lifecycle states (initializing/enabling/searching/connecting); they orthogonalize cleanly because each is an async-boot step. Yours are health states. Mixing the two is the trap.
- `disconnected` is the predicate "USB device absent" — RECOVERY §3.2's first line is `if not snap.present: return Disconnected()`. That's a guard, not a state. No useful internal data (no level, no counters that decay differently).
- `rf_blocked` is partially a peer (it gates destructive actions across cycles) but partially a substate of degraded/recovering — §6.1 itself notes cheap actions still run. Worked example 10.2 transitions `recovering(modem) → rf_blocked → recovering(usb)` — recovering didn't actually go away, only destructive actions paused.
- **Recommended structure:** 5 top-level states (`unknown`/`healthy`/`degraded`/`recovering(level)`/`exhausted`) + 2 orthogonal flags (`present: bool`, `rf_blocked: bool`). Status output composes them: `state="recovering" level="modem" rf_blocked=true present=true`.
- **Cost of changing now:** small (pre-implementation). Cost of *not* changing: every NOC widget special-cases "what does rf_blocked mean for healthy count?".

**Action for roadmap:** ADR-0008 "Per-modem state machine: top-level states vs orthogonal flags." Resolve before Phase 0.

### 4.2 Support-bundle — CONFIRM

**Stance:** Table stakes for NOC-target product.

- Four comparable NOC-managed products all ship a "log download" or "device export" button.
- P3 persona's UC9 ("Dump per-modem state machine state and inspect counters") is unsolvable without a single command bundling state + status + events + dmesg + journal.
- Without it, the daemon will get blamed for issues it didn't cause.
- **Enhancement to add:** include last 24 h of webhook delivery results (success/fail + http_status). NOC will ask "did you fire the alert?".

### 4.3 HMAC-SHA256 webhook signing — PUSHBACK

**Stance:** Move to v2.0 table stakes.

- 65% of public webhook implementations sign payloads. Receivers increasingly require signatures; shipping unsigned and adding later means every customer integration writes once, then rewrites.
- Implementation cost is trivial: ~30 lines + one config field. NFR-34's `LoadCredential=` design is already done.
- Unsigned-by-default-with-opt-in is *strictly less* compatible than signed-by-default (recipient can ignore the header).
- **Recommended:** `X-Spark-Signature: sha256=<hex>` over raw body bytes + `X-Spark-Timestamp: <unix>` for receiver replay protection.

### 4.4 No HTTP API on Unix socket for v2.0 — CONFIRM

**Stance:** CLI-only is correct.

- v2 already exposes status.json (read), events.jsonl (read), Prometheus on Unix socket, CLI. HTTP API duplicates reads and adds a write path (action triggers) — that's the security-relevant addition.
- ModemManager's DBus interface is a comparable case study of why richer IPC creates ongoing maintenance burden — every method is a stable contract and a security boundary.
- For v2.1 the actual motivation would be `--watch`-mode replacement (PRD Q4). Solvable today via `tail -F events.jsonl | jq …`.
- **Concession to pin down:** explicitly document daemon **never accepts inbound IPC** in v2.0. Prevents creep.

### 4.5 Per-modem dry-run mode — PUSHBACK

**Stance:** Add it. Complexity small, use case real.

- Today's `SPARK_MODEM_DRY_RUN=true` is all-or-nothing. Real field scenario: "modem 4 is showing weird pattern, study it; other three should keep being recovered."
- Implementation: `dry_run: bool | list[str]` where list is device names; gate at action-execution time.
- Per-modem state must surface in status.json and on each `action_planned` event so operators never wonder "is this on?".

### 4.6 Israel-only carriers from day one — PUSHBACK

**Stance:** Add a small global set on day one. Cost is hours, not a release.

- New MCC/MNC entries are pure data. Shipping decision is whether YAML lives in the .deb at v2.0 or arrives via email.
- Minimal day-one set covering big-three US (310/410, 311/480, 312/530), big-three UK (234/10, 234/15, 234/30), big-three DE (262/01, 262/02, 262/03) is ~30 lines.
- Risk of including: one wrong APN embarrasses the team. Mitigate: source from public list; mark non-IL entries `unverified: true`.
- Risk of *not* including: box shipped abroad falls back to `internetg`, silently doesn't connect on Verizon — no diagnostic clue points at carrier table.

---

## 5. Missing features

| # | Feature | Complexity | In docs? | Stance |
|---|---|---|---|---|
| M-1 | Webhook delivery retry (bounded queue, exp backoff) | S | Partial — ARCH §9 says "Drop, log, increment" | Add: 3 attempts before drop. Table stakes for NOC-grade alerting. |
| M-2 | Webhook payload deduplication / coalescing | M | No | Per-transition cooldown (default 60 s); without it alert fatigue kills the webhook in week 1. **Table stakes.** |
| M-3 | Webhook batching for multi-modem incidents | M | No | When 3 modems transition simultaneously (driver_reset), fire 1 batched webhook with a list. **Strongly recommend.** |
| M-4 | `X-Spark-Timestamp` header | S | No | Tied to HMAC §4.3 for replay protection. |
| M-5 | `spark_modem_state_duration_seconds{modem,state}` histogram | S | No | Lets NOC compute MTTR (M2) directly from Prom. **Table stakes.** |
| M-6 | Daemon-restart event-log marker with reason enum | S | Partial — daemon_started/stopped exist; no "why" beyond "sigterm" | Add `reason`: sigterm/crash/config_invalid/oom/kill. **Table stakes.** |
| M-7 | Disk-full graceful behavior, spec'd | M | Partial — ARCH §9 says degraded | Spec: which writes drop (events) vs must complete (status, state). |
| M-8 | `spark_modem_cycle_drift_seconds` self-health metric | S | No | Reveals tight loops to NOC. |
| M-9 | `spark-modem ctl history --modem=cdc-wdm3 --since=1h` | S | Partial — RUNBOOK §3 shows `grep+jq` | First-class subcommand. **Table stakes for P3 persona.** |
| M-10 | Maintenance mode (`spark-modem ctl maintenance on --duration=2h`) | S | No | Suppress webhooks during site visits. **Table stakes** — without it every site visit floods NOC. |
| M-11 | `carrier_table_sha256` in status.json | S | No | Spot inconsistent fleets after YAML update. |
| M-12 | Configurable severity per transition (config-controlled) | S | Partial | RUNBOOK §7 has table; not clear if config. |
| M-13 | `--explain` flag on `diag` | M | ✅ Mentioned RUNBOOK UC3 | Promote to FR. |
| M-14 | JSON Schema export for events.jsonl (`ctl schema events`) | S | No | Pydantic v2 supports model_json_schema(). **Differentiator.** |
| M-15 | Action-result feedback: `action_failed` event | M | Partial — counters bump on execution | Spec: failure surfaces as separate issue, possibly accelerates ladder. |
| M-16 | `chattr +a` on rotated events.jsonl (optional) | S | No | Audit-log immutability for security-sensitive customers. |
| M-17 | `cycle.actions_executed` and `cycle.transitions` in status.json | S | No | "Boring vs busy" dashboards without parsing events. |
| M-18 | Privacy redaction policy (`--redact` for ICCID/IMSI) | S | Partial — RUNBOOK §5 says no PIN/PUK | Carriers may consider ICCID/IMSI PII. |
| M-19 | First-cycle slow allowance footnote on NFR-1 | S | Implicit (startup_delay) | Documentation only. |
| M-20 | qmi-proxy ownership decision (PRD Q2) | M | Open | **Recommend:** assume Zao owns; refuse to start if absent. |
| M-21 | CLI advisory lock during state mutations | S | Partial — FR-61 daemon lock only | Two operators running `ctl reset-state` simultaneously must serialize. |
| M-22 | Telemetry opt-out / privacy mode | S | No | Probably implicit (don't configure webhook). Documentation. |
| M-23 | Identity-map portability (`ctl identity export/import`) | M | No | RMA box swap. **Defer to v2.1.** |
| M-24 | `spark-modem ctl simulate-issue --device=X --issue=Y` | M | No | Cradlepoint and ALMS have it; **table stakes for alert-pipeline testing.** |
| M-25 | Pre-exit alert on schema-version refusal | S | No | After downgrade, emit best-effort webhook before exit 3. |

---

## 6. Dependencies between features

```
M-2 (webhook dedup) ─┬─ M-3 (multi-modem batching) ─── shared transition queue
                     ├─ M-1 (retry) ──── shared bounded queue
                     └─ TS-18 (basic webhook)

M-4 (X-Spark-Timestamp) ── HMAC v2.0 (§4.3)
                        └── systemd LoadCredential= (NFR-34)

M-9 (history CLI) ── events.jsonl rotation (TS-17)

M-5 (state duration histogram) ── per-modem state machine (TS-2)
                               └── monotonic clock (D-8)

M-10 (maintenance mode) ── webhook subsystem (TS-18, M-2)
                       └── status.json field (TS-24)

M-24 (simulate-issue) ── fixture replay (D-7)
                      └── daemon CLI (TS-13)

D-5 (spec-as-tests) ── policy purity (D-6)
                    └── RECOVERY_SPEC §4 decision table

§4.1 state-machine refactor ── status.json shape (TS-24)
                           ├── webhook payload shape (TS-18)
                           ├── ModemState schema (SCHEMA §3)
                           └── MUST resolve before Phase 0
```

---

## 7. MVP priority recommendation

**Phase 0 (must-ship)** — all of TS-1..TS-25 plus:
- D-1, D-2, D-3, D-4, D-6, D-7, D-8, D-9, D-10 (the differentiator stack)
- §4.3 HMAC v2.0 (re-classify from v2.1)
- §4.5 per-modem dry-run
- §4.6 minimal global carrier set
- §4.1 state-machine refactor (5 + 2 flags)
- M-1, M-2, M-5, M-6, M-9, M-10, M-15, M-17, M-21

**Phase 1 (post-shadow-validation):**
- M-3 (webhook batching) — needs real-world flapping data to tune cooldown
- M-14 (schema export) — wait until pydantic models stable
- D-5 (spec-as-tests ramped to every decision-table row)
- D-11 (six-phase migration is itself the phasing)

**Defer to v2.1:**
- HTTP API (§4.4)
- 5G NR-aware policy
- M-23 (identity portability)
- Multi-vendor modem support (NG4)

---

## 8. Confidence assessment

| Area | Level | Reason |
|---|---|---|
| Comparable-product comparison | HIGH | 7 products checked against public docs. |
| Table-stakes categorization | HIGH | Multiple comparable products consistently include each. |
| Differentiators identification | HIGH-MEDIUM | High that they're real differentiators. Medium that they're the *most important* — depends on customer segment. |
| §4.1 state-machine pushback | MEDIUM-HIGH | Reasoned from first principles + ModemManager precedent + the doc's own worked examples. |
| §4.3 HMAC promotion | HIGH | Webhook security literature consistent; competitors do it; cost trivial. |
| §4.6 carrier-table breadth | HIGH | Cost-benefit asymmetric in favor of including more. |
| §4.5 per-modem dry-run | HIGH | Clear operational scenario; small implementation. |
| §4.4 HTTP-API deferral | HIGH | Surface-area arguments first-principles solid. |
| Missing-features list | MEDIUM | Each item reasoned, but priorities depend on customer feedback the docs don't yet have. |

---

## 9. Open questions for product/eng owners

1. **§4.1 state-machine ADR-0008** — 5+2 flags vs 7 top-level states; resolve before Phase 0.
2. **§4.3 HMAC v2.0 or v2.1** — recommend v2.0; security owner confirms.
3. **§4.6 carrier-table scope** — bundle US/UK/DE day one? Ownership (PRD Q7).
4. **M-2 webhook dedup window** — 60 s default, tunable per transition?
5. **M-3 webhook batching** — per-cycle or per-window?
6. **M-20 qmi-proxy ownership** (PRD Q2) — recommend "assume Zao owns; refuse if absent."
7. **M-24 simulate-issue** — any customer asking for it? If not, defer.

---

## 10. Sources

- [ModemManager](https://modemmanager.org/), [state machine reference](https://www.freedesktop.org/software/ModemManager/api/1.4.0/gdbus-org.freedesktop.ModemManager1.Modem.html)
- [mwan3 (DeepWiki)](https://deepwiki.com/openwrt/packages/2.2.1-mwan3-(multi-wan-manager))
- [Cradlepoint NetCloud Manager](https://customer.cradlepoint.com/s/article/NetCloud-Manager-Router-Dashboard), [System Control Settings](https://customer.cradlepoint.com/s/article/Manual-System-Settings-System-Control)
- [Sierra AirLink ALMS](https://doc.airvantage.net/alms/features/), [overview PDF](https://www.motorolasolutions.com/content/dam/msi/images/business/products/public_safety_lte/vehicle-router-solutions/sierrawireless_airlink_managementservice.pdf)
- [Peplink SpeedFusion](https://www.peplink.com/technology/speedfusion-bonding-technology/)
- [Robustel R5020](https://robustel.com/product/r5020/)
- [Digi WR54 user guide](https://www.digi.com/resources/documentation/digidocs/PDFs/90002282.pdf)
- [Webhook security (webhooks.fyi)](https://webhooks.fyi/security/hmac), [fundamentals (Hooklistener)](https://www.hooklistener.com/learn/webhook-security-fundamentals), [HMAC implementation (Prismatic)](https://prismatic.io/blog/how-secure-webhook-endpoints-hmac/)
- [qmicli man page](https://www.freedesktop.org/software/libqmi/man/latest/qmicli.1.html)
- Local docs: `docs/{PRD,RECOVERY_SPEC,RUNBOOK,ARCHITECTURE,SCHEMA}.md` and `.planning/PROJECT.md`
