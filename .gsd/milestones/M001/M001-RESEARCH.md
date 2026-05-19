# Project Research Summary — spark-modem-watchdog v2

**Project:** spark-modem-watchdog v2 (Python rewrite of v1 bash modem-recovery toolchain)
**Domain:** Long-running root-privileged single-process asyncio daemon on aarch64 Linux (NVIDIA Jetson Orin NX, Ubuntu 20.04 / L4T R35.6.4); 4× Sierra EM7421 LTE modems behind Soliton Zao bonding
**Researched:** 2026-05-05
**Overall confidence:** HIGH for stack, architecture, table-stakes/anti-features, and known-issue pitfalls; MEDIUM for opinionated pushbacks (state-machine refactor, HMAC promotion, per-modem locks); LOW only on closed-source counterparties (Zao SDK internals) and unverified Sierra EM7421 firmware variants.

The four parallel research files read the existing `docs/` (PRD, ARCHITECTURE, RECOVERY_SPEC, SCHEMA, RUNBOOK, MIGRATION, TEST_STRATEGY, GLOSSARY, ADRs 0001–0007) and produced a delta-vs-validation review, not a fresh design. The docs/ proposal stands up well; the deltas below are the items the roadmap must absorb before Phase 0 starts coding.

---

## 1. TL;DR

- **Python version is resolved.** Bundle CPython 3.12 in the .deb venv via `astral-sh/python-build-standalone` (aarch64-unknown-linux-gnu, glibc 2.17 baseline). Closes PROJECT.md Q8 with HIGH confidence. ADR-0001's "ship the runtime we tested with" stance is correct; only the sourcing tactic is novel. Python 3.8 and deadsnakes are dead options — pydantic v2.11 dropped 3.8 in March 2025; deadsnakes dropped focal in April 2025.
- **State files must key by `usb_path`, not `cdc-wdmN`.** Real footgun on USB renumbering / hub re-enumeration; surfaces in both ARCHITECTURE Q14 and PITFALLS §3.1. The docs/ already key the *identity map* by usb_path correctly; SCHEMA §3 / ARCH §6 must extend the same rule to per-modem state files. Phase 0 amendment, before any state-store code is written.
- **State machine is one state too many.** FEATURES §4.1 recommends 5 top-level states (`unknown`/`healthy`/`degraded`/`recovering(level)`/`exhausted`) plus 2 orthogonal flags (`present`, `rf_blocked`) instead of the docs/ 7. Forces ADR-0008 and a SCHEMA shape change; affects status.json and webhook payloads. Resolve before Phase 0.
- **HMAC webhook signing belongs in v2.0, not v2.1.** FEATURES §4.3 makes the cost/benefit argument; PRD Q5 should be re-decided. ~30 LOC + one config field. NFR-34's `LoadCredential=` design already exists.
- **TaskGroup + per-task `asyncio.timeout`, not `gather` + `wait_for`.** ARCHITECTURE Q2 / anti-pattern #2. Modernize the per-modem-probe primitive on Python 3.12; cleaner cancellation, NFR-11 satisfied.
- **Per-modem `asyncio.Lock` plus a globals lock**, not the docs/ single state-store lock. ARCHITECTURE Q3. ~10 LOC; protects NFR-1's 10s budget against fsync stalls. MEDIUM confidence — both designs work.
- **Carrier table should bundle US/UK/DE day-one** (FEATURES §4.6). Cost is hours; embarrassment of an out-of-IL box silently failing on Verizon is real.
- **Three "new in v2" pitfall classes the rewrite introduces** that ADRs do not yet address: (a) cardinality explosion via `state` one-hot label (PITFALLS §13.1), (b) `_healthy_streak` non-persistence resetting decay across daemon restarts (§9.2), (c) concurrent CLI + daemon state mutations (§3.2 / §16.1). Each requires a Phase 0 design item.

---

## 2. Stack recommendation

**Python version (closes PROJECT.md Q8):** Bundle CPython 3.12.x in the .deb venv via `astral-sh/python-build-standalone`. Confidence: **HIGH**. Source `cpython-3.12.<patch>+<datetag>-aarch64-unknown-linux-gnu-install_only.tar.gz`, glibc 2.17 baseline (Ubuntu 20.04 ships 2.31 — comfortable margin). Ubuntu 20.04 standard support ended 31 May 2025; deadsnakes does not publish 3.11+ for focal; `pydantic >=2.11` requires Python >=3.9. Python 3.13 deferred (free-threaded transition risk + thinner aarch64 wheel ecosystem); 3.14 too new (beta).

**Pinned library set** (canonical, Phase 0 lock target):

| Library | Pin | Why |
|---|---|---|
| `pydantic` | `>=2.13,<3` | Wire formats, ADR-0004 |
| `PyYAML` | `>=6.0.2,<7` | Layered config (FR-54) |
| `prometheus-client` | `>=0.25,<1` | Metrics over UDS (NFR-21) |
| `pyudev` | `>=0.24.4,<1` | udev add/remove (FR-1, ARCH §8); needs libudev >=151 (focal ships 245) |
| `pyroute2` | `>=0.9.6,<1` | rtnetlink link-state — use **`AsyncIPRoute`** (asyncio-native; not NDB, not sync IPRoute) |
| `asyncinotify` | `>=4.0.10,<5` | inotify on Zao log + kmsg rotation; replaces docs/ silence |
| `httpx` | `>=0.27,<1` | Webhook POST (FR-44); fills docs/ gap |
| `sdnotify` | `>=0.3.2,<1` | `Type=notify` (FR-53) — pure-Python, prefer over `systemd-python` |
| `psutil` | `>=5.9,<7` | RSS tripwire (NFR-3); fills docs/ gap |
| `jeepney` | `>=0.9.0` | dbus, **deferred to v2.1** if/when systemd D-Bus watching lands |

**Dev:** `ruff >=0.6,<1` (drop `black`); `mypy >=1.13,<2 --strict`; `pytest >=8.3,<9`; `pytest-asyncio >=0.24,<1` (`mode=auto`); `hypothesis >=6.110,<7`; `pytest-cov >=5,<7`; `uv >=0.5,<1` (build-time only).

**Packaging recipe** (custom debhelper rule, replaces `dh-virtualenv` which assumes a system Python we deliberately won't reuse):

1. Download pinned `python-build-standalone` tarball (SHA256 in `debian/python.sha256`); unpack to `debian/<pkg>/opt/spark-modem-watchdog/python/`.
2. `python/bin/python3.12 -m venv venv` against destdir.
3. `uv pip install --no-deps -r requirements.lock` into the venv.
4. `python -m compileall` (warm pyc cache for NFR-13).
5. Generate `bin/spark-modem` and `libexec/spark-modem-watchdog` shims; install systemd unit, default config, logrotate snippet, post-install hook.

Estimated .deb size **~30–35 MiB**. Security-update story: rebuild .deb on each CPython security release (4–6× per year on stable branches).

**Phase 0 spike requirements** (MEDIUM confidence on full integration):

- Working .deb installs and runs on a real Jetson **before any HIL tests**. Smoke test: `import` all 9 runtime libs in the bundled 3.12.
- Validate venv path-relocation (PITFALLS §18.3): build at destination path, not builder path.
- Validate Prom-over-UDS recipe end-to-end with `curl --unix-socket` (ARCHITECTURE Q9).

---

## 3. Feature scope refinements

The docs/ proposal is **above industry baseline for table-stakes, defensibly opinionated on differentiators, and correctly disciplined about anti-features**. Six explicit pushbacks:

| # | Pushback | Stance | Action |
|---|---|---|---|
| §4.1 | 7-state machine | **Reduce to 5 + 2 flags.** `disconnected` is a guard not a state; `rf_blocked` is partly orthogonal (cheap actions still run when set). Worked example 10.2 transitions `recovering(modem) → rf_blocked → recovering(usb)` — recovering didn't disappear. | **ADR-0008** before Phase 0. SCHEMA, status.json, webhook payload all reshape. |
| §4.3 | HMAC v2.1 | **Promote to v2.0.** Receivers increasingly require signatures; cost ~30 LOC; signed-by-default is strictly more compatible than unsigned. | Re-classify PRD Q5; add `X-Spark-Signature: sha256=<hex>` + `X-Spark-Timestamp: <unix>` (M-4). |
| §4.5 | All-or-nothing dry-run | **Per-modem dry-run.** `dry_run: bool \| list[str]`; gate at action-execution time; surface in status.json + each `action_planned` event. | Phase 0 design + FR amendment. |
| §4.6 | IL-only carriers | **Bundle US/UK/DE day-one.** ~30 lines YAML; mark non-IL `unverified: true`; box shipped abroad otherwise falls back to `internetg` and silently fails on Verizon. | Phase 0 default-config additions. |
| §4.4 | No HTTP API on UDS | **Confirm.** CLI-only is correct for v2.0; explicitly document daemon **never accepts inbound IPC** in v2.0 to prevent creep. | Defer Q1 to v2.1. |
| §4.2 | Support-bundle scope | **Confirm + extend.** Include last 24 h of webhook delivery results. | NFR-22 amendment. |

**Confirmed table-stakes** (TS-1..TS-25, all in docs/): udev discovery, per-modem health classification, bounded escalation ladder, signal-quality gate, idempotent actions, atomic state writes, carrier APN auto-select with post-write verification, SIM identity persistence, systemd `Type=notify`, hot config reload, Prometheus scrape, structured events.jsonl + logrotate, webhooks, support-bundle, fixture-driven hardware-free tests, schema-version refusal.

**Confirmed differentiators** (D-1..D-11): signal-quality gate, counter decay, cross-action ladder backoff, Zao authoritative gating, spec-as-tests, pure-function policy engine, fixture replay, monotonic-clock backoff, closed-enum issue taxonomy, global driver_reset gate, six-phase migration with shadow validation. **None of the 7 comparable products combine signal-gating + bounded escalation + counter decay + Zao-authoritative gating + dry-run + spec-as-tests.**

**Anti-features to add to docs/ explicit list:** AF-10 no retroactive re-decision; AF-11 no predictive ML; AF-12 no auto-firmware-update; AF-13 no cross-box coordination.

### Promote into v2.0 scope (from FEATURES §5)

| # | Feature | Why now |
|---|---|---|
| M-1 | Webhook delivery retry (3 attempts, exp backoff) | Table stakes for NOC-grade alerting |
| M-2 | Webhook payload deduplication / coalescing (60 s default) | Without it alert fatigue kills the webhook in week 1 |
| M-4 | `X-Spark-Timestamp` header | Replay-protection partner to HMAC §4.3 |
| M-5 | `spark_modem_state_duration_seconds{modem,state}` histogram | Lets NOC compute MTTR (M2) directly from Prom |
| M-6 | Daemon-restart event marker with reason enum | Today: only daemon_started/stopped, no "why" |
| M-9 | `spark-modem ctl history --modem=X --since=1h` | First-class subcommand |
| M-10 | Maintenance mode (`ctl maintenance on --duration=2h`, max 8h, auto-expiry) | Without `--duration` / auto-expiry it becomes a CRITICAL operational pitfall |
| M-15 | `action_failed` event | Failure should optionally accelerate ladder |
| M-17 | `cycle.actions_executed` and `cycle.transitions` in status.json | "Boring vs busy" dashboards |
| M-21 | CLI advisory lock during state mutations | Two operators running `ctl reset-state` simultaneously must serialize |

### Defer to v2.1

M-3 webhook batching; M-14 schema export; M-23 identity-map portability; M-24 simulate-issue; HTTP API on UDS (Q1); 5G NR-aware policy; multi-vendor modem support.

---

## 4. Architecture decisions and patterns

The docs/ 11-module decomposition is correct; **do not split or merge**. Three prescriptive pushbacks before Phase 0:

### 4.1 Three prescriptive changes

| # | Change | Confidence |
|---|---|---|
| 1 | **`asyncio.TaskGroup` + per-task `asyncio.timeout`**, not `gather` + `wait_for`. Each per-modem probe gets its own 8s budget. | HIGH |
| 2 | **Per-modem `asyncio.Lock` + one globals lock**, not single state-store lock. `dict[str, asyncio.Lock]` lazily populated; ~10 LOC; single-key APIs only. | MEDIUM |
| 3 | **State files keyed by `usb_path`**: `state/by-usb/2-3.1.1.json`. Inventory cross-checks (file usb_path) ↔ (sysfs) ↔ (current cdc-wdm) on startup; mismatch is an error. | HIGH |

### 4.2 Library bridging recipes (filling docs/ gaps)

- **`pyudev`**: `Monitor.from_netlink()` + `loop.add_reader(monitor.fileno())`. **No `MonitorObserver`** (PITFALLS §7.1: thread crashes silently).
- **`pyroute2`**: `AsyncIPRoute` async context manager + `await ipr.bind()` + `async for msg in ipr.get()`. Not NDB, not sync IPRoute.
- **`asyncinotify`**: `with Inotify() as ino` + outer reopen-on-rotate loop (MOVE_SELF / DELETE_SELF). Plus `os.stat().st_size` truncation check for `copytruncate` (PITFALLS §8.1). Watch the **directory** for `IN_CREATE` if file absent at startup.
- **`/dev/kmsg`**: `O_RDONLY|O_NONBLOCK` + `lseek(SEEK_END)` + `add_reader`. EPIPE-tolerant. ~30 LOC.
- **Prom over UDS**: `make_wsgi_app()` + custom `UnixStreamServer`+`WSGIServer` subclass; run in `asyncio.to_thread`. Phase 0 spike for aarch64+wsgiref. MEDIUM-HIGH.
- **qmicli subprocess**: `create_subprocess_exec` + `proc.communicate(timeout=...)` + two-stage shutdown (graceful, then SIGKILL drain, then re-communicate). `start_new_session=True` (kill the process group, not bare PID — cpython#127049). `limit=1024*1024` for chatty 5G (§5.4).
- **`sd_notify`**: emit `READY=1` after first full cycle; `STATUS=` keepalive each cycle; optional `WatchdogSec=90s`. Send from main daemon PID only.
- **Signal handling**: `loop.add_signal_handler(SIGTERM, ...)` → `shutdown_event`. Never `signal.signal()` from asyncio.

### 4.3 Build order (validated, ARCHITECTURE §3.3)

```
A — plumbing:        clock → subproc → wire/ → config → state_store → event_logger
B — minimal cycle:   qmi → observer (sysfs only) → policy → cheap actions → cycle driver → cli
C — status+metrics:  status.json writer → Prom UDS → webhook poster
D — event sources:   zao_log → inventory (pyudev) → observer (rtnetlink) → dmesg
E — lifecycle:       sd_notify → SIGHUP reload → SIGTERM drain → PID-lock + preflight
F — destructive:     soft_reset, modem_reset, usb_reset → driver_reset
```

A–C pure-Python, laptop-testable. D needs Linux. E–F need Jetson for full validation.

### 4.4 Anti-pattern catalogue (top 15 expected Phase 0 temptations)

`subprocess.run` sync; `gather(return_exceptions=True)` for probes; `MonitorObserver`; cdc-wdmN-keyed state; single state-store lock; `signal.signal` from asyncio; subprocess/httpx in policy; UDS RPC for `ctl status`; `urllib.request` for webhooks; missing directory `fsync`; blocking read on `/dev/kmsg`; best-effort event-log swallowing exceptions; hot-reload of event-source paths; `run_in_executor` to "speed up" qmicli; `if/elif` instead of `match` on `ModemState`.

### 4.5 Phase 0 architecture spikes

Prom-over-UDS aarch64; .deb integration on aarch64; `AsyncIPRoute` API maturity; WatchdogSec cadence; `Type=notify` (NOT `notify-reload`, requires systemd 253+; Ubuntu 20.04 ships 245).

### 4.6 Test-seam protocols to add

`WebhookPoster`, `MetricRegistry`, `PIDLock`, `SignalHandler` (in addition to ARCH §12 list). Phase 0 lint check: `grep -r 'create_subprocess_exec' src/` matches zero lines outside `subproc/`.

---

## 5. Top pitfalls to design against

### 5.1 Top-15 highest-stakes pitfalls

| # | Pitfall | Origin | P/S | Prevention | Phase |
|---|---|---|---|---|---|
| §3.1 | cdc-wdmN renumbering breaks state-file/identity match | v1-carryover | med/high | Key by `usb_path`; startup migration; cross-check on load | **Phase 0 SCHEMA** |
| §3.2 / §16.1 | Concurrent writers: daemon vs `ctl reset-state` lost-update | new-in-v2 | med/high | `flock` on `/run/.../state.lock`; per-modem `flock` on `/run/.../modem-{device}.lock`; CLI acquires same | Phase 0 design (FR-61.1) |
| §1.1 | qmi-proxy crash leaves stale CIDs | v1-carryover | med/high | Detect `proxy_died` in stderr; short-circuit to `driver_reset`; HIL `pkill -9 qmi-proxy` mid-cycle | Phase 0 fixture+HIL |
| §1.2 | qmicli output drift across libqmi 1.30→1.32+ | domain | med/high | Pin `expected_libqmi_version`; per-version fixtures; `extra=ignore`; missing field → typed `MissingField`; `LC_ALL=C` (§1.3 locale) | Phase 0 fixtures |
| §2.1 | InfraCtrl.script returns 0 while not applying | domain | med/high | Every InfraCtrl invocation has explicit post-action verify; `result=accepted` vs `result=verified` metrics | Phase 0 HIL |
| §2.3 | qmi-proxy ownership transition on Zao restart | domain | med/high | Subscribe to `zao-infra-ctrl.service` D-Bus state changes; suspend QMI probes for `zao_restart_grace_seconds`; `qmi_proxy_uptime_seconds` gauge | Phase 0 HIL; closes Q2 |
| §5.1 | `Process.communicate()` cancellation loses stdout (cpython#139373) | domain | med/high | Use `asyncio.timeout()`, not `wait_for` around `communicate`; 100 random-timing cancellation tests | Phase 0 unit |
| §6.1 | rtnetlink ENOBUFS during event storms | domain | med/high | Tight read loop; `SO_RCVBUF=4MiB`; on ENOBUFS close+reopen and force inventory refresh | Phase 0 unit + HIL stress |
| §7.1 | `MonitorObserver` thread crashes silently (pyudev #194/#363/#402) | domain | med/high | Use `Monitor` + `add_reader(monitor.fileno())`; no thread; heartbeat metric tripwire | Phase 0 design |
| §8.1 | logrotate `copytruncate` breaks inotify watch invisibly | domain | high/high | `os.stat().st_size` truncation check; opportunistic inode check; coordinate field eng to switch Zao to `create` mode | Phase 0 unit + bench cron |
| §9.2 | Daemon restart silently resets `_healthy_streak` (re-introduces v1's permanent-Exhausted) | new-in-v2 | high/high | Streak persisted in `state/<usb_path>.json`; verify load-on-startup; replay test with daemon restart mid-streak | **Phase 0 unit + replay** |
| §9.1 | `_healthy_streak` persistence vs decay race (crash mid-cycle) | new-in-v2 | med/high | Streak update + decay + counter reset + state-write are ONE atomic op; pin ordering in RECOVERY §8 | Phase 0 unit + replay |
| §10.1 | DNS resolution blocking the event loop on broken/slow LTE-tunneled DNS | domain | med/high | Webhook on separate fire-and-forget task; explicit httpx timeouts; pre-resolve URL DNS at config-load, cache 60s | Phase 0 design + DNS-failure unit |
| §13.1 | Cardinality explosion via `state` one-hot label | new-in-v2 | high/high | `prometheus_client.Enum` or integer-encoded `state_value{modem}`; document per-box cardinality ceiling | **Phase 0 metrics redesign** |
| §15.1 | Phase 1 dry-run agreement biased toward healthy cycles | domain | high/high | Compare tool weights fault cycles separately; gate Phase 2 on **fault-cycle agreement ≥95%** (not aggregate); inject synthetic faults daily | Phase 0 compare-tool design |

### 5.2 Three "new in v2" pitfall classes

| Class | Source | Phase 0 design item |
|---|---|---|
| Cardinality explosion via `state` one-hot label | §13.1 / §9.4 | Replace gauge with `Enum` or integer encoding |
| `_healthy_streak` non-persistence resets decay across restarts | §9.2 | Verify SCHEMA §3 streak load-on-startup; replay test with mid-streak restart |
| Concurrent CLI + daemon state mutations | §3.2 / §16.1; FEATURES M-21 | Per-modem `flock` + state-store `flock` (separate from PID lock); CLI acquires both |

### 5.3 Phase exposure summary

- **Phase 0**: 45 cataloged pitfalls have Phase 0 design / unit / fixture / HIL items. Smoke test "real .deb runs on real Jetson" is the gate.
- **Phase 1** (bench shadow): qmicli parser drift, Zao restart races, LoadCredential interaction. New exit gate: **fault-cycle agreement ≥95%**.
- **Phase 2** (field shadow): locale, Zao SDK <2.1.0, EM7421 firmware variation. Exit gate: per-box firmware/SDK inventory in known set.
- **Phase 3** (one box live): downgrade schema mismatch, identity drift, apt downgrade. Exit gate: rollback-to-v1 in <10 minutes verified.
- **Phase 4** (canary): cardinality at 10% scale, dry-run bias, Tegra USB hub PSU droop. Exit gate: Prom WAL compaction within budget at fleet ingest.
- **Phase 5** (rollout): carrier-table SHA convergence, certifi rotation policy.

---

## 6. Cross-cutting recommendations (span ≥2 research files)

| Recommendation | Touches | Why coordinated |
|---|---|---|
| State-machine refactor (5+2 flags) | FEATURES §4.1 + ARCHITECTURE Q14 + SCHEMA + status.json + webhook payload | Ripples through wire format, status output, external integrations. Must land before any module past `wire/`. **ADR-0008.** |
| State files keyed by `usb_path` | ARCHITECTURE Q14 + PITFALLS §3.1 + SCHEMA §3 + ARCH §6, §7 | Consistent with identity.json's existing usb_path keying |
| Webhook design | FEATURES §4.3 / M-1..M-4 + ARCHITECTURE §8 + PITFALLS §10.1..10.5 | HMAC v2.0 + DNS-loop-blocking defense + retry/dedup queue all converge on `WebhookPoster` protocol |
| State-store concurrency | ARCHITECTURE Q3 + PITFALLS §3.2 + FEATURES M-21 | Three layers: in-process per-modem `asyncio.Lock`; cross-process `flock` on state.lock; per-modem `flock` on action lock |
| `_healthy_streak` durability | PITFALLS §9.1+§9.2 + ADR-0006 + RECOVERY §8 | Persist on every cycle; load on startup; one atomic write; replay tests include daemon-restart-mid-streak |
| Cardinality / metric design | PITFALLS §13.1 + NFR-21 + FEATURES M-5, M-8, M-11, M-17 | Re-design metric surface in Phase 0 *before* `prometheus_client` code |
| Maintenance mode (M-10) | FEATURES M-10 + PITFALLS §16.2 | M-10 desirable; without `--duration` enforcement and auto-expiry it becomes a CRITICAL operational pitfall |
| Carrier table | FEATURES §4.6 + PITFALLS §11.2 (YAML "Norway problem") + FEATURES M-11 | Fixture-driven validation with hostile inputs; `mnc: str` regex `r"^\d{2,3}$"` |
| qmi-proxy ownership | FEATURES M-20 + PITFALLS §1.5/§2.3 + PRD Q2 | All converge: "assume Zao owns; refuse to start qmicli direct mode" |
| EM7421 hardware quirks | PITFALLS §1.6 + ADR-0001 + FR-1 | Inventory matches Sierra-VID `1199:*` (any PID); verify `operating_mode == "online"` and `raw_ip == "Y"` after every reset; persist `(usb_path → first_seen_apn)` for NV-wipe drift detection |
| Tegra USB hub PSU droop | PITFALLS §17.2 + RUNBOOK §7 | Daemon-side mitigation: stagger first-cycle startup actions across modems with 5s spacing |

---

## 7. Conflicts / contradictions across research files

**No contradictions detected.** The four research files agree on every cross-referenced point:

- State machine: FEATURES §4.1 says reduce to 5+2; ARCHITECTURE never asserts the 7-state shape; PITFALLS §9.5 implicitly endorses orthogonal-flag treatment of `rf_blocked`.
- State file keying: ARCHITECTURE Q14 and PITFALLS §3.1 independently arrived at the same prescription.
- TaskGroup over gather: ARCHITECTURE Q2 + anti-pattern catalogue + STACK's pin of Python 3.12 align.
- HMAC promotion: FEATURES §4.3 promotes; STACK silent (stdlib `hmac` + httpx); PITFALLS §10.4 mentions header-injection only as defense-in-depth — non-conflicting.
- qmi-proxy ownership: FEATURES M-20, PITFALLS §1.5/§2.3, ARCHITECTURE Q8 all converge.
- Per-modem locks: ARCHITECTURE Q3 (in-process) and PITFALLS §3.2/§16.1 (cross-process) describe orthogonal layers — both needed, no conflict.
- Python version: STACK closes Q8 conclusively.

The only place files differ in **emphasis** is on confidence levels: STACK HIGH for 3.12; ARCHITECTURE MEDIUM-HIGH for Prom-on-UDS (needs Phase 0 spike); PITFALLS calls Prom-cardinality CRITICAL while ARCHITECTURE doesn't flag it (PITFALLS is the only file that reviewed metric surface).

---

## 8. Open questions to close before Phase 0

| Rank | Question | Recommended answer | Confidence | Source |
|---|---|---|---|---|
| 1 | **PROJECT.md Q8** — Jetson Python | Bundle CPython 3.12 in .deb venv via `python-build-standalone` | **HIGH (RESOLVED)** | STACK |
| 2 | **PRD Q5** — HMAC in v2.0 or v2.1 | **v2.0** (re-classify) | HIGH | FEATURES §4.3 |
| 3 | **PRD Q2** — daemon vs Zao owns qmi-proxy | Assume Zao owns; refuse direct mode if proxy unavailable | HIGH | FEATURES M-20, PITFALLS §1.5/§2.3, ARCH Q8 |
| 4 | **NEW** — 7 states or 5+2 flags? | 5+2 flags; ADR-0008 | MEDIUM-HIGH | FEATURES §4.1 |
| 5 | **NEW** — state files keyed by cdc-wdmN or usb_path? | `usb_path`; `state/by-usb/<usb_path>.json` | HIGH | ARCH Q14, PITFALLS §3.1 |
| 6 | **NEW** — `state` as one-hot Prom label? | No — use `Enum` or integer-encoded `state_value{modem}` | HIGH | PITFALLS §13.1 |
| 7 | **PRD Q6** — config-change communication | SIGHUP transactional reload for data; restart-only for topology | HIGH | ARCH Q11; PITFALLS §11.4 |
| 8 | **PRD Q7** — carrier-table ownership | Bundle US/UK/DE day-one; product owns the table; eng ships releases | MEDIUM | FEATURES §4.6 |
| 9 | **NEW** — non-IL carriers in v2.0? | Yes — minimal US/UK/DE with `unverified: true`; ~30 lines YAML | HIGH | FEATURES §4.6 |
| 10 | **NEW** — webhook dedup window default | 60 s per `(modem, transition)`; per-transition tunable in v2.1 | MEDIUM | FEATURES M-2, §4.3 |
| 11 | **PRD Q3** — minimum Zao SDK | 2.1.0; add Phase 0 fleet sweep | HIGH | docs + PITFALLS §2.5 |
| 12 | **PRD Q4** — feature parity with v1 `--watch` | Replace with `journalctl -fu \| jq` + Prometheus + `ctl history` (M-9) | MEDIUM | FEATURES M-9 |
| 13 | **PRD Q1** — HTTP API on UDS in v2.0 | No, defer to v2.1; explicitly document daemon never accepts inbound IPC | HIGH | FEATURES §4.4, ARCH Q17 |
| 14 | **NEW** — schema-downgrade behavior | Non-destructive: keep file, shadow as `.from-v<N>.json`, fresh defaults, log `schema_downgrade_pending`; provide `ctl migrate-state` and `ctl reset-state --all` | HIGH | PITFALLS §3.4, ARCH Q15 |
| 15 | **NEW** — ADR-0006 atomic-cycle ordering | Streak-update + decay-check + counter-reset + state-write are one atomic unit; pin ordering in RECOVERY §8 | HIGH | PITFALLS §9.1, §9.2 |

Items 4, 5, 6, 9, 10, 14, 15 are **new questions surfaced by this research** (not in PRD §10). Items 1, 2, 3, 11, 12 close existing PRD/PROJECT open questions.

---

## 9. Roadmap implications

### 9.1 Suggested phase boundaries

The migration phase numbering (0..6) is delivery-flavored (build → bench shadow → field shadow → field live → canary → rollout → decommission). The build-out within Phase 0 fits the 5-stage A..F structure from §4.3. Recommend the roadmap use the migration-phase numbering at the top level and the A..F build-order as the Phase 0 sub-plan.

### 9.2 Phase 0 spike list (must-do before any production code)

1. `.deb` builds and installs on Jetson Orin NX (STACK MEDIUM). Smoke test: `import` all 9 runtime libs.
2. Prom-over-UDS aarch64 spike (ARCH Q9 MEDIUM-HIGH). `curl --unix-socket` returns 200 with valid Prom text.
3. systemd `Type=notify` on Ubuntu 20.04 / systemd 245 (PITFALLS §4.1, §4.3). 50-boot test: `systemctl status` Active within 60 s every time. `LoadCredential=` works without `PrivateMounts=`.
4. Per-modem state-file keying spike (ARCH Q14 / PITFALLS §3.1). End-to-end: random USB renumbering survives.
5. qmi-proxy crash recovery HIL (PITFALLS §1.1). `pkill -9 qmi-proxy` mid-cycle → daemon recovers with one `driver_reset`, no thrash.
6. Compare-tool fault-weighted agreement (PITFALLS §15.1). Phase 1's exit gate.

### 9.3 Phase 0 ADR amendments + new ADRs

**Amend existing:**

| ADR | Amendment |
|---|---|
| ADR-0001 (Python rewrite) | Add: "We bundle CPython 3.12 via `astral-sh/python-build-standalone`. Closes Q8." |
| ADR-0003 (Zao log authoritative) | Add: "Parser only consumes `RASCOW_STAT`; other lines accepted-but-ignored with counter; growing parsed surface is a schema-version bump." |
| ADR-0004 (Typed wire formats) | Add: "Schema downgrade is non-destructive — shadow as `.from-v<N>.json`, log `schema_downgrade_pending`; reset only on explicit `ctl reset-state`." |
| ADR-0005 (state machine) | **Amend significantly** — change top-level state count from 7 to 5; add orthogonal flags `present` and `rf_blocked`; rewrite worked example 10.2. Or supersede with ADR-0008. |
| ADR-0006 (counter decay) | Add: "Streak update + decay + counter reset + state-write are ONE atomic write per cycle; streak persists across daemon restarts; replay test must include mid-streak restart." |

**New ADRs:**

| ADR | Topic | Source |
|---|---|---|
| ADR-0008 | Per-modem state machine: 5 top-level + 2 orthogonal flags (supersedes ADR-0005's 7-state) | FEATURES §4.1 |
| ADR-0009 | State files keyed by `usb_path` | ARCH Q14, PITFALLS §3.1 |
| ADR-0010 | Packaging: `python-build-standalone` + `uv` + custom debhelper rule | STACK |
| ADR-0011 | Webhook subsystem: HMAC v2.0 + retry/dedup queue + pre-resolved DNS | FEATURES §4.3, M-1..M-4; PITFALLS §10.1 |
| ADR-0012 | Concurrency: per-modem `asyncio.Lock` + globals lock; per-modem `flock`; state-store `flock` separate from PID lock | ARCH Q3, PITFALLS §3.2/§16.1, FEATURES M-21 |
| ADR-0013 | Metric surface: replace `state` one-hot label with `Enum` or integer encoding | PITFALLS §13.1/§9.4 |

### 9.4 Phase-by-phase risk exposure

| Phase | Highest risks newly exposed | Suggested exit gate |
|---|---|---|
| 0 (build/HIL) | Packaging risks (§18.x); cardinality design (§13.1); state-machine refactor; concurrency design; qmi-proxy HIL | Real .deb runs on real Jetson and passes 6 spikes |
| 1 (bench shadow) | Parser drift (§1.2); LoadCredential (§4.3); Zao restart races (§2.4) | **Fault-cycle agreement ≥95%** (not aggregate ≥99%); synthetic faults daily |
| 2 (field shadow) | Locale (§1.3); EM7421 firmware variation (§17.1); Zao SDK <2.1.0 (§2.5) | All field-cohort firmware/SDK in known set with captured fixtures |
| 3 (one box live) | Schema downgrade (§3.4); identity drift (§15.3); apt downgrade (§15.4); 14-day forensics (§16.4) | Rollback-to-v1 in <10 minutes verified end-to-end |
| 4 (canary) | Cardinality (§13.1); dry-run bias (§15.1); FW variation; Tegra USB hub PSU droop (§17.2) | Prom WAL compaction within budget at fleet ingest |
| 5 (rollout) | Carrier-table SHA convergence (§15.5); certifi rotation (§18.5) | Carrier-table SHA convergence ≤1h after rollout |

### 9.5 Research flags

- **Phase 0** likely needs deeper research on: (a) python-build-standalone integration with debhelper on aarch64 (no fully-worked public example), (b) Prom-over-UDS WSGIServer subclass on aarch64+glibc 2.31, (c) systemd 245 `LoadCredential=` + `ProtectSystem=` matrix on Ubuntu 20.04. Spike day 1.
- **Phase 1** likely needs deeper research on v1→v2 replay-harness format and v1's qmicli output byte-stability across libqmi point releases.
- **Phase 4** likely needs deeper research on real production cycle-latency distributions (validates the per-modem-lock recommendation in ARCH Q3).
- **Standard patterns (skip extra research):** Phases 2, 3, 5 — standard fleet-rollout discipline; MIGRATION.md is sufficient once Phase 0/1 land.

---

## 10. Source files

| File | Path | Commit | Bytes |
|---|---|---|---|
| STACK.md | `.planning/research/STACK.md` | `90cb0a0` | 30,981 |
| FEATURES.md | `.planning/research/FEATURES.md` | `9555e29` | 22,781 |
| ARCHITECTURE.md | `.planning/research/ARCHITECTURE.md` | `56d1197` | 62,668 |
| PITFALLS.md | `.planning/research/PITFALLS.md` | `e8acc29` | 95,813 |

Plus existing context: `.planning/PROJECT.md` and `docs/{PRD, ARCHITECTURE, RECOVERY_SPEC, SCHEMA, RUNBOOK, MIGRATION, TEST_STRATEGY, GLOSSARY}.md` and `docs/adr/0001..0007.md`.

# ARCHITECTURE research — spark-modem-watchdog v2

**Research mode:** Project Research (Architecture dimension)
**Confidence:** HIGH for asyncio patterns and library bridging (verified against current Python 3.12 docs, library source, and changelogs); MEDIUM for the per-modem-vs-single-lock recommendation (a judgement call, both work); MEDIUM-HIGH for the prometheus Unix socket recipe (proven pattern, needs Phase 0 spike); HIGH for shutdown / sd_notify / signal-handling sequence.

---

## 1. Bottom line up front

The docs/ proposal is **architecturally correct in its bones and broadly aligned with 2026 best practice for asyncio Linux daemons.** The 11-module decomposition is honest, the protocol-typed seams enable real testing, and the cycle-as-pure-function discipline is the right invariant. Three things in the proposal need attention before Phase 0:

1. **Adopt `TaskGroup` + `asyncio.timeout`, not `gather` + per-call `wait_for`.** Python 3.12 is the target; the modern structured-concurrency primitives are strictly better than `gather` for our cancellation-on-error and per-task-deadline semantics. *Mostly a code-style upgrade, not an architectural change* — but worth pinning before the team reaches for `gather` out of muscle memory.
2. **Bridge `pyudev` and `pyroute2` into asyncio explicitly via the loop's `add_reader`.** The docs say "background tasks pushing onto an asyncio.Queue" but doesn't pin *how*. The cleanest 2026 way for both libraries is the same: take the underlying fd, register `add_reader`, parse on the event-loop thread. Avoid the thread bridge for pyudev (`MonitorObserver`) — its asyncio.Queue.put_nowait-from-a-thread is a footgun if you forget `call_soon_threadsafe`. (For pyroute2, use `AsyncIPRoute` — it is asyncio-native as of the 0.9.x line.) **Confidence: HIGH.**
3. **Replace the single state-store `asyncio.Lock` with per-modem locks plus a `globals` lock.** A slow disk write to one `cdc-wdmN.json` MUST NOT serialize the rest of the cycle. Cost is ~10 lines of code; benefit is the cycle no longer falls off the NFR-1 10-second budget when one modem's state-write blocks on `fsync`. **Confidence: MEDIUM** — both designs work; this is a small win that is also a small cost.

Beyond those three, the proposal is sound. Specific pushbacks per question are below.

---

## 2. Comparable asyncio-Linux daemons examined

| Daemon | Language | Pattern relevant to us |
|---|---|---|
| **systemd-resolved** (C) | C, structured around `sd-event` | The "event loop with fd-readers + timer events" topology is exactly what we're building; their dispatch order (events first, then timers) is what asyncio does for free. **Lesson:** use the loop's primitives rather than building a separate dispatcher. |
| **cockpit-bridge** (Python, `cockpit-project/cockpit/src/cockpit/`) | Python asyncio + python-sdbus (formerly dbus-next) | Production asyncio Python daemon under systemd. They use `asyncio.run()` with a top-level coroutine that owns shutdown; signal handlers set a future the top-level awaits. **Lesson:** `asyncio.run()` is fine *if* the top-level coroutine has explicit shutdown drain logic. This is what we want. |
| **glances** (Python) | asyncio for some agents, threads for stats collection | Long-running Python daemon with many subscribers and one publisher, plus an http exporter. Their pattern is a single event loop in main thread with stats collection sometimes in `to_thread`. **Lesson:** when a library is fundamentally synchronous (psutil), `asyncio.to_thread` for the call is fine — but avoid inventing a thread pool. |
| **borgbackup** (Python, sync) | Atomic-write patterns, JSON state files, multi-process locking | Their `lock.py` module + `safe_write` (write tmp, fsync, rename, fsync dir) is the canonical Python recipe. **Lesson:** our `state_store.atomic_write` MUST do the dance below — anything less is data-loss-on-power-cut. |
| **ModemManager** (C + DBus) | DBus FSM per modem | Per-modem state machine with explicit transitions and a "no concurrent operations on the same modem" invariant. **Lesson:** validates ADR-0005's "explicit per-modem state machine" stance. Their FSM is much bigger than ours (~13 states); ours can stay smaller because Zao owns the data plane. |
| **frr (zebra/bgpd/ospfd)** (C, multi-process, libfrr event loop) | Multi-process, IPC over Unix sockets, signal-driven reload | They split per-protocol daemons because each protocol's failure should not crash routing. **Lesson:** *we are not multi-process and that is correct* — our blast radius is one box, our "protocols" share state, and a crash means the whole watchdog restarts via systemd. The frr split makes sense for them, not us. |
| **Python asyncio docs `subprocess` examples** | Stdlib | Show the canonical `create_subprocess_exec` + `proc.wait()` + `proc.communicate()` pattern. **Lesson:** read the Python 3.12 changelog: `ThreadedChildWatcher` is the default, no event-loop policy fiddling needed. The "FD leak under default loop" footnote in docs/ §15 is a 3.10-and-earlier concern; on 3.12 it's a non-issue if you `await proc.wait()` and don't dangle Process objects. |

---

## 3. Recommended component decomposition (validation of docs/ §4)

The docs/ 11-module list is correct. I would not split or merge any of them. Two notes:

### 3.1 What the existing modules own

The docs/ table (§4.1) gets responsibilities right. Reproduced for traceability and annotated with concurrency/lifecycle notes:

| Module | Concurrency model | Owns the lifecycle of |
|---|---|---|
| `inventory` | Synchronous on the main loop; reads sysfs at most once per cycle. udev events arrive on a queue from the udev background task. | The `Modem` records (line, cdc-wdm, usb_path, ns, iface). |
| `observer` | Per-modem probes via `TaskGroup` + `asyncio.timeout`. **No state mutation.** | One `Diag` per cycle; nothing else. |
| `policy` | Pure function. Synchronous. **Cannot await.** | Nothing. Returns `PlannedAction[]`. |
| `actions` | Each action is a coroutine; runs sequentially after policy decides. One per modem per cycle. | Subprocess invocation + `ActionResult`. |
| `state_store` | `asyncio.Lock` per key (per modem + per global). | Disk JSON files; in-memory cache of last loaded state. |
| `event_logger` | Single writer task with an `asyncio.Queue`; drains queue and writes batched to JSONL. | `events.jsonl`. Owns rotation handover (logrotate sends SIGHUP — we re-open). |
| `status_reporter` | Two sub-components: status.json writer (atomic write per cycle) + Prom exporter (background server task) + webhook poster (one task per webhook, fire-and-forget with timeout). | `status.json`, the metrics socket, webhook outbound calls. |
| `config` | Single read on start; SIGHUP triggers reload-cycle event. | `Config` dataclass; the validation pipeline. |
| `clock` | Stateless wrappers. | Nothing. |
| `subproc` | Stateless wrapper. | One Process + its stdout/stderr per call; closes them in `finally`. |
| `qmi` | Calls `subproc.run`; parses stdout. Stateless. | Nothing persistent. |
| `zao_log` | Background task with `asyncinotify` + a re-open-on-rotate loop. Publishes the latest snapshot via a `latest()` accessor (inproc). | The open file handle to the Zao log; the parsed `RASCOW_STAT` snapshot. |
| `cli` | `asyncio.run(main())` per subcommand; daemon entry is a separate `asyncio.run()`. | Argv parsing; exit codes. |

### 3.2 What crosses each boundary

Strict typed dataclasses only. No raw dicts, no `Any`, no shell-string command construction.

```
inventory ──── Modem records ────▶ observer
observer ──── Diag (frozen) ────▶ policy
policy ──── PlannedAction[] ────▶ actions, status_reporter, event_logger
actions ──── ActionResult ────▶ state_store, event_logger
state_store ──── ModemState ────▶ policy (next cycle), status_reporter
zao_log ──── ZaoSnapshot (via .latest()) ────▶ observer
config ──── Config ────▶ everyone (read-only)
clock ──── (float | str) ────▶ everyone
qmi ──── typed result | QmiError ────▶ observer
subproc ──── Completed(rc, stdout, stderr) ────▶ qmi (only)
```

The arrow direction matters: **policy never reaches into actions** (policy plans; the cycle driver calls actions). **actions never write status.json** (actions emit `ActionResult`; status_reporter aggregates). **event_logger is fire-and-forget** (cycle does not await event log writes; the queue absorbs them).

### 3.3 Suggested build order with dependencies

```
Phase 0 — Plumbing that everything needs
1. clock                        (nothing depends on anything)
2. subproc                      (uses clock for timeouts)
3. wire/                        (pydantic models for Diag, ModemState, etc.)
4. config                       (uses wire/; loads + validates YAML)
5. state_store                  (uses wire/, clock; atomic write recipe)
6. event_logger                 (uses wire/, clock; backed by an asyncio.Queue)

Phase 1 — Single-modem, polling-only minimal viable cycle
7. qmi                          (uses subproc, wire/)
8. observer (no events, no Zao yet — sysfs only)
9. policy                       (consumes Diag, ModemState, Config, Clock)
10. actions (set_apn, fix_raw_ip only — the cheap ones)
11. cycle driver                (the §4.2 hot-loop sequence)
12. cli                         (diag + recovery subcommands; no daemon yet)

Phase 2 — Status + metrics
13. status_reporter (status.json only)
14. status_reporter (Prom exporter on Unix socket)
15. status_reporter (webhook poster)

Phase 3 — Event sources
16. zao_log (asyncinotify + rotation handling)
17. inventory (pyudev with add_reader bridge)
18. observer (rtnetlink with pyroute2 AsyncIPRoute)
19. dmesg reader (/dev/kmsg with add_reader bridge)

Phase 4 — Lifecycle hardening
20. sd_notify integration (Type=notify ready/reloading)
21. SIGHUP reload semantics
22. SIGTERM graceful drain
23. PID-file lock + startup preflight (FR-60)

Phase 5 — Destructive actions + driver_reset
24. actions (soft_reset, modem_reset, usb_reset)
25. actions (driver_reset)
```

Phases 0–2 are pure-Python, fully testable without hardware. Phase 3 needs Linux (event sources). Phases 4–5 need a target box for full validation but the *logic* is testable on a laptop.

---

## 4. The 17 questions, answered

> Format: **Stance | Rationale | Confidence | Implementation pointer**

### Q1. Single asyncio loop / single process / single thread — sufficient?

**Stance: YES, with exactly one minor exception.** Confidence: HIGH.

The policy-engine purity discipline is sufficient for correctness. Adding threads adds GIL contention, signal-handler races, and `asyncio.run_in_executor`-style hand-offs that we'd then have to test. We do not need them.

**The one exception:** if any single `qmicli` *parsing* step is CPU-heavy enough to register on a profiler (parsing thousands of lines), wrap it in `asyncio.to_thread`. As of writing, this is not the case (qmicli output for one probe is <50 lines), so we do not need this. Phase 0's profiler run validates this assumption.

**Anti-pattern to avoid:** "Let me put the qmicli subprocess on a thread pool to be safe." NO. `asyncio.create_subprocess_exec` is *already* non-blocking by virtue of being implemented over `add_reader` on the child's pipes. Wrapping it in `to_thread` is wasteful and breaks cancellation semantics.

### Q2. Per-task timeout pattern in 2026 — what's the right primitive?

**Stance: `asyncio.TaskGroup` + `asyncio.timeout` (per task).** Confidence: HIGH.

Python 3.12 is our target (per STACK.md). `TaskGroup` and `asyncio.timeout` are both 3.11+. They are strictly better than the old `gather` + `wait_for` pair:

- `wait_for` is *not* deprecated in 3.12, but the 3.11 release notes flagged it as "consider using `asyncio.timeout()`" because `wait_for` has a known subtle cancellation race in some chaining scenarios.
- `gather(return_exceptions=True)` masks cancellation; if one probe times out, the other probes keep running until their timeouts. With `TaskGroup`, the *parent* timing out cancels the siblings — which is *not* what we want here. So we want **per-task `timeout`**, not parent-level.

**Recommended pattern (per-modem probes, observer):**

```python
async def probe_modem(modem: Modem, qmi: QmiClient, clock: Clock,
                      timeout_s: float = 8.0) -> ModemDiag:
    try:
        async with asyncio.timeout(timeout_s):
            return await _probe_modem_inner(modem, qmi, clock)
    except TimeoutError:
        return ModemDiag.timed_out(modem.device, clock.now_iso())
    except Exception as e:
        # NFR-11: never crash the daemon on an observer error.
        return ModemDiag.errored(modem.device, e, clock.now_iso())

async def observe_all(modems: list[Modem], qmi: QmiClient,
                       clock: Clock) -> list[ModemDiag]:
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(probe_modem(m, qmi, clock)) for m in modems]
    return [t.result() for t in tasks]
```

Two key properties:
- Each per-modem probe has its **own** 8 s budget; one slow modem does not slow another.
- The TaskGroup waits for all tasks to finish (by success, timeout, or per-task error). No wedged probe wedges the cycle. NFR-11 satisfied.

**Anti-pattern:** `asyncio.gather(*coros, return_exceptions=True)`. It works but exception handling is by-hand and the absence of structured cancellation has bitten dozens of asyncio codebases. Use TaskGroup.

### Q3. Single `asyncio.Lock` for state-store commits — fine, or per-modem?

**Stance: PER-MODEM locks plus a single `globals` lock.** Confidence: MEDIUM.

The single-lock design is the safer default and is documented (ARCH §4.3). It guarantees no two modem-state mutations interleave, which simplifies reasoning. But it has a real cost: a slow `fsync` on `cdc-wdm0.json` blocks any other modem's state commit.

**The tradeoff:**
- **Single lock** (current): simpler. Cycle serializes through one critical section. Worst case: an `fsync` stall on one file blocks the whole cycle. Cost is a few hundred ms on a slow eMMC; not catastrophic.
- **Per-modem lock + globals lock** (recommended): each `cdc-wdmN.json` has its own lock. `globals.json` (driver_reset marker etc.) has a separate lock. Cycle parallelizes per-modem state commits. Worst case: two state-writes happening at once on different files — fine, kernel handles disk I/O serialization.

**Why per-modem wins:** the cycle algorithm in §4.2 already parallelizes per-modem *probes* (step 3) and per-modem *actions* (step 7). State commits (step 8) being serial is asymmetric. With per-modem locks, the *whole* cycle is per-modem-parallel except for the policy decision (step 6, pure function, fast) and the global writes (status.json, events.jsonl).

**Implementation:** a `dict[str, asyncio.Lock]` in `state_store`, lazily populated. `state_store.commit(device, new_state)` acquires `_locks[device]`; `state_store.commit_globals(g)` acquires `_globals_lock`. ~10 LOC.

**Caveat (why MEDIUM confidence):** if you mess up and a single piece of code modifies *two* modems' state in one critical section, lock-ordering bugs are a thing. Easy avoidance: `state_store` exposes only single-key APIs (`commit_modem(device, ...)`, `commit_globals(...)`), never a multi-modem commit.

### Q4. `pyudev` integration with asyncio — cleanest 2026 way?

**Stance: `pyudev.Monitor` + `loop.add_reader` on `monitor.fileno()`. Do NOT use `MonitorObserver`.** Confidence: HIGH.

`pyudev` issue [#450](https://github.com/pyudev/pyudev/issues/450) requested native asyncio support; as of 0.24.4 (Oct 2025) it has not landed. The library exposes `Monitor.fileno()` precisely for this purpose. Our integration:

```python
def start_udev(loop: asyncio.AbstractEventLoop, q: asyncio.Queue[UdevEvent]) -> Monitor:
    ctx = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(ctx)
    monitor.filter_by(subsystem='usb', device_type='usb_device')
    monitor.start()  # arms the netlink socket; non-blocking
    fd = monitor.fileno()

    def on_readable() -> None:
        # Drain all available events; the monitor returns None when fd has nothing.
        while True:
            dev = monitor.poll(timeout=0)
            if dev is None:
                break
            q.put_nowait(UdevEvent.from_pyudev(dev))

    loop.add_reader(fd, on_readable)
    return monitor  # caller owns shutdown: loop.remove_reader(fd); monitor = None
```

**Why not `MonitorObserver`:** it spawns a thread, and the thread's callback runs in *thread context*. To safely push to an `asyncio.Queue` from there, you need `loop.call_soon_threadsafe(q.put_nowait, ev)`. It works but it is one easy mistake away from a deadlock and is more complex than the add_reader version.

**Why not `aiopyudev` or similar:** there is no maintained asyncio-pyudev wrapper as of May 2026. The `add_reader` bridge is the supported pattern and is what `aiopyudev`-equivalents end up doing internally.

**Lifecycle:** the Monitor file descriptor is owned by `inventory`'s startup. Shutdown sequence: `loop.remove_reader(fd)` → release the Monitor reference → garbage collection closes the fd. Add this to the `asyncio.Event`-based shutdown drain.

### Q5. `pyroute2` — IPRoute / NDB / IPDB — which API in 2026?

**Stance: `pyroute2.AsyncIPRoute`.** Confidence: HIGH.

- **IPDB:** deprecated; do not touch.
- **NDB:** the current high-level API for *managing* network state. We do not manage; we only *observe*. NDB is over-engineered for our use case — it maintains an in-memory + SQLite database mirroring the kernel's network state. We don't need that.
- **IPRoute (sync):** works, but its event subscription is by-hand polling.
- **AsyncIPRoute (async, 0.9.x line):** designed for asyncio, exposes link events via `async for msg in ipr.get()` after `bind()`. This is the right one.

**Recommended pattern (rtnetlink link-state listener):**

```python
async def watch_links(q: asyncio.Queue[LinkEvent]) -> None:
    async with pyroute2.AsyncIPRoute() as ipr:
        await ipr.bind()  # subscribe to RTMGRP_LINK
        async for msg in ipr.get():
            ev = LinkEvent.from_netlink(msg)
            if ev is None:
                continue
            await q.put(ev)
```

The `async with` ensures the netlink socket closes cleanly on shutdown.

**Caveat:** pyroute2's API surface is larger than we need; we only consume `RTM_NEWLINK`/`RTM_DELLINK` for the wwan ifaces. Filter aggressively in `LinkEvent.from_netlink`; ignore the rest.

### Q6. inotify on Zao log — `asyncinotify` vs `pyinotify` vs `aionotify`?

**Stance: `asyncinotify >=4.0.10,<5`.** Confidence: HIGH (matches STACK.md).

- **pyinotify:** legacy, last meaningful release 2015; no asyncio integration, sync-only with manual select() loops. NO.
- **aionotify:** thin asyncio wrapper, but maintenance has been spotty (last release 2023, intermittent activity). NO.
- **asyncinotify:** active maintenance (latest 4.x in 2025), asyncio-native (`async for ev in inotify`), pure-Python ctypes wrapper around the inotify syscalls. YES.

**Rotation handling.** The Zao log rotates via logrotate. asyncinotify does NOT auto-update `Watch.path` on `IN_MOVE_SELF` (per its docs — quoted in our research findings above). The pattern we want:

```python
async def tail_zao_log(path: Path, parser: ZaoParser, q: asyncio.Queue[Snapshot]) -> None:
    while True:  # outer loop: re-open on rotation
        try:
            with Inotify() as ino:
                ino.add_watch(path, Mask.MODIFY | Mask.MOVE_SELF | Mask.DELETE_SELF | Mask.CLOSE_WRITE)
                with path.open("rb") as f:
                    f.seek(0, os.SEEK_END)  # tail; v1 startup-mode reads the tail only
                    async for event in ino:
                        if event.mask & (Mask.MOVE_SELF | Mask.DELETE_SELF):
                            break  # rotation; exit inner, fall through to outer reopen
                        if event.mask & Mask.MODIFY:
                            chunk = f.read()
                            for snap in parser.feed(chunk):
                                await q.put(snap)
        except FileNotFoundError:
            await asyncio.sleep(1.0)  # logrotate hasn't created the new file yet
        except Exception as e:
            log.exception("zao_log_tail crashed; restarting in 1s", exc_info=e)
            await asyncio.sleep(1.0)
```

Notes:
- `IN_MOVE_SELF` fires when `logrotate` renames `zao-remote-endpoint.log → zao-remote-endpoint.log.1`. The next file `logrotate` creates is a new inode; we re-watch the path.
- Hold the `asyncinotify.Inotify()` context manager — its `__exit__` closes the inotify fd. No fd leaks across reopens.
- `f.seek(0, os.SEEK_END)` is the *initial* tail behavior; on reopen, you start from offset 0 of the new file (not END) since you missed the lines between rotation and reopen. (The first lines after a rotation will include the most recent `RASCOW_STAT`.)

### Q7. `/dev/kmsg` reader — cleanest pattern?

**Stance: open with `O_NONBLOCK`, register `loop.add_reader`, parse partial lines.** Confidence: HIGH.

`/dev/kmsg` is a kernel-printk interface. Each `read()` returns one full message (the kernel guarantees this; you do NOT need partial-line buffering at the message level — the kernel splits on newline-terminated records before the userspace read returns). However, the *first* message after open is the message at the current head; subsequent reads return as new messages arrive.

**Pattern:**

```python
def start_kmsg(loop: asyncio.AbstractEventLoop, q: asyncio.Queue[KmsgEvent]) -> int:
    fd = os.open("/dev/kmsg", os.O_RDONLY | os.O_NONBLOCK)
    # Optional: seek to end so we don't replay the boot log on every daemon start.
    # SEEK_DATA on /dev/kmsg jumps to the head; SEEK_END jumps to the tail.
    os.lseek(fd, 0, os.SEEK_END)

    def on_readable() -> None:
        while True:
            try:
                buf = os.read(fd, 8192)
            except BlockingIOError:
                return
            except OSError as e:
                if e.errno == errno.EPIPE:
                    # Ring buffer overrun; we lost some messages. Continue.
                    continue
                raise
            ev = KmsgEvent.parse(buf)  # one record per read; no partial-line worry
            if ev:
                q.put_nowait(ev)

    loop.add_reader(fd, on_readable)
    return fd
```

The kernel's `/dev/kmsg` has one quirk: when reads can't keep up with the print rate, you get `EPIPE` and the kernel skips you ahead. Catch and continue; it just means we missed a message. We don't care for steady-state operation (overcurrent / enum errors are infrequent); we *do* care to not crash the cycle on it.

**Why not `dmesg --follow` as a subprocess:** spawning a subprocess for an event source is wasteful and adds a hard dependency on `dmesg` (which v1 has). Reading the device file directly is one less moving piece.

### Q8. `qmicli` subprocess — pitfalls under asyncio?

**Stance: `asyncio.create_subprocess_exec` with explicit timeout, `proc.wait()`, and `close_fds=True` (default in 3.x). On 3.12 the ChildWatcher concerns are moot.** Confidence: HIGH.

Three pitfalls to call out, all addressed:

1. **SIGCHLD races (historical 3.10 and earlier).** Python ≤3.9 default ChildWatcher was `SafeChildWatcher`, which had known races on busy systems. Python 3.10 changed default to `ThreadedChildWatcher`. Python 3.12 keeps `ThreadedChildWatcher`. On 3.12 (our target), nothing to do. Don't fiddle with `set_event_loop_policy` or `set_child_watcher`.
2. **Stdout/stderr buffering deadlocks.** If `qmicli` writes more than the OS pipe buffer (~64KiB) without us reading, it blocks. Use `proc.communicate(timeout=...)` (which reads both pipes concurrently), NOT separate `proc.stdout.read()` / `proc.stderr.read()` (deadlock risk if you read one pipe while the other fills).
3. **FD leaks (the docs/ §15 Q4 worry).** `close_fds=True` is the default in `asyncio.subprocess` in Python 3.x; this means file descriptors from the parent process are not inherited. `lsof` self-check as a tripwire (docs/ §15) is a good defense in depth but not strictly necessary. Keep it as a low-cost periodic metric (`spark_modem_open_fds`).

**Recommended subproc wrapper:**

```python
async def run(argv: list[str], *, timeout: float, stdin: bytes | None = None) -> Completed:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE if stdin else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        # close_fds=True is the default; explicit for clarity
    )
    try:
        async with asyncio.timeout(timeout):
            stdout, stderr = await proc.communicate(input=stdin)
    except TimeoutError:
        proc.kill()
        # Drain to release the pipes; then wait (this is fast since SIGKILL is sync at the kernel level)
        try:
            async with asyncio.timeout(2.0):
                stdout, stderr = await proc.communicate()
        except TimeoutError:
            stdout, stderr = b"", b""
        return Completed(rc=-9, stdout=stdout, stderr=stderr, timed_out=True)
    return Completed(rc=proc.returncode, stdout=stdout, stderr=stderr, timed_out=False)
```

The two-stage timeout (graceful via `communicate`, then SIGKILL drain) handles the case where `qmicli` is wedged AND its stdout buffer is full — without it, `proc.kill()` succeeds but the pipes remain open if no one drains them, leaking fds.

**Anti-pattern:** sending SIGTERM to qmicli first. qmicli has no special signal handler and SIGTERM may or may not interrupt its libqmi blocking call. SIGKILL is correct here; the call is idempotent (FR-27 says actions are idempotent), so re-running on next cycle is fine.

### Q9. `prometheus_client` over Unix socket — what's the right adapter?

**Stance: `prometheus_client.make_wsgi_app()` + a custom `wsgiref.simple_server.WSGIServer` subclass that binds an `AF_UNIX` socket. Run in `asyncio.to_thread` because wsgiref is sync-only.** Confidence: MEDIUM-HIGH.

`prometheus_client` provides `make_wsgi_app()` which returns a WSGI app. The library also provides `start_wsgi_server()`, but that creates an `AF_INET` server (TCP). For Unix-socket binding, we need ~30 lines of wrapper.

**Recommended pattern:**

```python
import socket
from socketserver import UnixStreamServer
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler
from prometheus_client import make_wsgi_app

class UnixWSGIServer(UnixStreamServer, WSGIServer):
    address_family = socket.AF_UNIX

    def server_bind(self) -> None:
        # Avoid setsockopt(SOL_SOCKET, SO_REUSEADDR) — Unix sockets don't need it
        # and on some kernels it errors. UnixStreamServer.server_bind handles unlink.
        UnixStreamServer.server_bind(self)
        self.setup_environ()  # wsgiref expects this; SERVER_NAME is bogus on UDS

def start_metrics_server(socket_path: Path) -> UnixWSGIServer:
    socket_path.unlink(missing_ok=True)
    server = UnixWSGIServer(str(socket_path), WSGIRequestHandler)
    server.set_app(make_wsgi_app())
    socket_path.chmod(0o660)  # nginx group can read; root owns
    return server

# In daemon main:
metrics_server = start_metrics_server(Path("/run/spark-modem-watchdog/metrics.sock"))
metrics_task = asyncio.create_task(asyncio.to_thread(metrics_server.serve_forever))
# On shutdown: metrics_server.shutdown(); metrics_task is cancelled.
```

**Why this and not `aiohttp` / `starlette` / `prometheus-async`:**
- `aiohttp` works (it has `web.UnixSite`), but pulls a full HTTP framework for one endpoint. Overkill.
- `starlette` even more so.
- `prometheus-async` is for instrumenting async code; we already use `prometheus_client`'s metric primitives. The exporter side is what we need; that's `make_wsgi_app`.

**Why `to_thread` and not the asyncio-native serve:** `wsgiref` is synchronous. Running it in a single dedicated thread (the same thread for the lifetime of the daemon) is fine — Prom scrapes are sub-100-millisecond and infrequent. We don't need full asyncio integration. `to_thread` keeps the main loop unblocked.

**Caveat (why not HIGH):** the exact wsgiref subclass might need tweaking on aarch64 + glibc to handle EAGAIN / SIGPIPE on the Unix socket cleanly. Phase 0 spike: 1 day to validate end-to-end, including a `curl --unix-socket` smoke test.

### Q10. `sd_notify` integration — when to emit `READY=1`?

**Stance: emit `READY=1` after `(inventory loaded) AND (zao_log subscribed AND first snapshot received OR 30 s elapsed) AND (event sources started) AND (first cycle completed)`.** Confidence: HIGH.

`Type=notify` semantics: until you send `READY=1`, systemd holds `systemctl start` blocked. Other units' `After=` ordering depends on this. NFR-13 demands ≤60 s.

**Lifecycle script:**

```python
async def main() -> None:
    notifier = sdnotify.SystemdNotifier()  # tolerates missing $NOTIFY_SOCKET (non-systemd dev)

    cfg = load_config()                                      # 0.0 s
    state = state_store.open(cfg.state_dir)                  # ~0.1 s
    event_logger.start(cfg.events_path)                      # ~0.0 s
    pre_check_external_tools()                               # FR-60: 0.1 s
    inventory_initial = await inventory.bootstrap()          # ~0.5 s, sysfs scan

    # Start event sources in parallel; bail if they all fail.
    udev_task = inventory.start_udev_listener()
    rtnetlink_task = observer.start_rtnetlink_listener()
    kmsg_task = observer.start_kmsg_listener()
    zao_task, zao_first_snapshot_evt = zao_log.start_tailer(cfg.zao.log_path)

    # Wait for the Zao first snapshot OR a 30s timeout (we will operate even
    # without Zao; FR-12 fall-back is direct probing).
    try:
        async with asyncio.timeout(30.0):
            await zao_first_snapshot_evt.wait()
    except TimeoutError:
        log.warning("zao_log first snapshot did not arrive in 30s; operating in fallback")

    # Run one full cycle to prove the pipeline.
    await run_one_cycle(...)
    write_status_json(...)

    # NOW we are READY. Total time ~5–35 s depending on Zao. Within NFR-13's 60 s.
    notifier.notify("READY=1")
    notifier.notify("STATUS=watching 4 modems, 4 active, 0 degraded")

    # Hot loop.
    await main_cycle_loop(...)
```

**SIGHUP reload (Q11 references):**
```python
# When SIGHUP arrives:
notifier.notify("RELOADING=1\nMONOTONIC_USEC={}".format(int(time.monotonic() * 1e6)))
new_cfg = load_config()
config.swap(new_cfg)
notifier.notify("READY=1")
```

`MONOTONIC_USEC=` is recommended by systemd ≥253 for `Type=notify-reload` semantics. We can set Type to `notify-reload` if we want systemd to handle the SIGHUP-vs-ExecReload dispatch; for v2.0 the simpler `notify` + manual SIGHUP handler is fine.

**Watchdog ping:** if we add `WatchdogSec=` to the unit (recommended for the daemon), we periodically `notifier.notify("WATCHDOG=1")` from the main loop — say every cycle. Suggest 90 s WatchdogSec (= 3× cycle interval); systemd kills us if 90 s pass with no ping. This is real safety against a stuck cycle.

**Status string:** keep `notifier.notify("STATUS=...")` updated each cycle so `systemctl status` shows live aggregate state.

### Q11. Hot-reload on SIGHUP — what's reload-safe vs restart-only?

**Stance: docs §10 is right.** Confidence: HIGH.

Reload-safe (changes apply without reconnecting subscriptions):
- Thresholds (`min_rsrp_dbm`, `min_rsrq_db`, `min_snr_db`, `signal_sufficient` boundaries)
- Backoff durations (`backoff_seconds`, `ladder_min_interval`, `global_driver_reset_backoff_seconds`)
- Webhook URL, transitions list, HMAC secret reload
- Carrier table (`il.yaml`)
- Logging level
- Counter ladder ceilings (`MAX_SOFT`, `MAX_MODEM`, `MAX_USB`, `decay_after_healthy_cycles`)

Restart-only (require process restart):
- `cycle.interval_seconds` (the polling deadline; trivial to support reload, but rarely worth the test surface)
- Event source choices (paths, whether to subscribe to rtnetlink, kmsg, etc.)
- Path locations (`events_path`, `state_dir`, `metrics.sock` path)
- `expected_modems` count
- Schema version

**Why this split:** the reloadable items are pure data consumed by policy / status_reporter, no subscription rewiring. The restart-only items would require tearing down the udev/rtnetlink/inotify/kmsg subscriptions and re-establishing them — which is *possible* but doubles the test matrix for a feature that operators rarely use mid-run.

**Implementation:** `config.swap(new_cfg)` does a single atomic pointer swap; readers of `cfg` see the new value on their next cycle (one read). No locking needed because the policy engine is pure (each cycle re-reads cfg). Restart-only items are detected at swap time; if any changed, log a warning telling the operator to `systemctl restart spark-modem-watchdog` to apply.

**Anti-pattern:** allowing `interval_seconds` to be reloaded but not the event-source paths. Asymmetry is confusing; prefer the clear split (data items reload; topology items restart).

### Q12. Graceful SIGTERM within 5 s — the right shutdown sequence?

**Stance: `loop.add_signal_handler(SIGTERM, ...)` sets a `shutdown_event`; the cycle loop awaits both `shutdown_event` and the work queue; on shutdown, drain the current cycle, close stores, flush event log, close metrics socket, exit.** Confidence: HIGH.

NFR-13 / FR-53 says 5 s. Our hot loop has known max sub-cycle costs (per-modem probe = 8 s ceiling, but we abort on signal). The pattern:

```python
shutdown_event = asyncio.Event()

def _on_signal(signame: str) -> None:
    log.info("received %s; initiating graceful shutdown", signame)
    shutdown_event.set()

async def main() -> None:
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, _on_signal, "SIGTERM")
    loop.add_signal_handler(signal.SIGINT, _on_signal, "SIGINT")
    loop.add_signal_handler(signal.SIGHUP, _on_sighup_reload)

    async with asyncio.TaskGroup() as tg:
        cycle_task = tg.create_task(cycle_loop(shutdown_event))
        # Event source tasks; they all check shutdown_event in their loops
        ...

    # TaskGroup exits when all tasks return. Here every task is shutdown-aware.
    await shutdown_drain(state_store, event_logger, metrics_server)
    notifier.notify("STOPPING=1")

async def cycle_loop(shutdown_event: asyncio.Event) -> None:
    while not shutdown_event.is_set():
        # Wait for any of: queue event, polling deadline, shutdown
        try:
            async with asyncio.timeout(cfg.cycle_interval_seconds):
                event = await wait_any(event_queue.get(), shutdown_event.wait())
        except TimeoutError:
            event = None  # polling tick

        if shutdown_event.is_set():
            return

        # Skip cycle on shutdown; let the in-flight tasks finish naturally.
        await run_one_cycle(...)

async def shutdown_drain(state_store, event_logger, metrics_server) -> None:
    # Order matters: stop accepting new work; drain the buffers; close fds.
    metrics_server.shutdown()                 # stops the WSGI server thread
    await event_logger.drain_and_close()      # flush queue → fsync → close
    await state_store.flush_all()             # any pending state writes
```

**Two known gotchas, both handled:**

1. **`asyncio.subprocess` and signals:** if a SIGTERM arrives mid-`qmicli`, the in-flight subprocess holds open pipes that `proc.wait()` is awaiting. Our `subproc.run` already wraps in `asyncio.timeout`; on shutdown, those subprocesses will hit their per-call timeout and get killed. `proc.kill()` is signal-safe.

2. **Signal handler can fire on a non-main thread:** `loop.add_signal_handler` *only* works on the main thread (asyncio raises if not). We MUST ensure the daemon `asyncio.run` is on the main thread. This is the default unless someone wraps the daemon entry in a thread (which we won't).

**Anti-pattern:** `signal.signal(SIGTERM, handler)` directly. The C-level signal handler can fire while asyncio is mid-step and you cannot safely call any asyncio function from it. `loop.add_signal_handler` schedules the callback safely.

**Five-second budget:** the drain consists of ~3 file fsyncs + closing event-source fds. ~50 ms total. The 5 s ceiling is for *cycle* drain (one cycle in flight). If a per-modem probe is timing out at the 8 s ceiling and SIGTERM arrives, we exceed 5 s. **Mitigation:** the cycle's own per-task timeout is 8 s; on SIGTERM we cancel the TaskGroup early (cycle_task.cancel()), which propagates to the per-modem probe TaskGroup, which propagates to the subprocess `proc.kill()` path. End-to-end shutdown cap is ~2 s in the worst case.

### Q13. Crash safety mid-action — durable in-flight marker?

**Stance: NO durable marker needed; the docs §9 "next cycle observes" approach is sufficient.** Confidence: HIGH.

The argument:

- All recovery actions are *idempotent* (FR-27). Running `soft_reset` twice has the same net effect as once.
- All persistent writes are atomic (FR-62). On crash, on-disk state is either pre-action or post-action, never partial.
- Counters bump *after* `action_executed` returns (RECOVERY §9). On crash mid-action, the counter is still pre-action, so the next cycle re-tries — which is correct because the action may not have completed.
- The `action_planned` event in `events.jsonl` is for forensics, not for replay. The event log is append-only; if the daemon crashed mid-write, at most the last line is partial (logrotate / our reader tolerate this).

**Where this argument is slightly wrong:** non-idempotent side-effects in the *kernel* (e.g. `usb_reset`'s effect on the modem's internal session state). The kernel might be in the middle of resetting when we crash; on restart, the device might be re-enumerating. Our cycle handles this *because* the next cycle observes the actual state (via `qmicli`) and decides — no replay-from-log needed.

**Anti-pattern:** writing an "in-flight action" marker before execution and clearing on success. Sounds robust but introduces a *new* failure mode: what if we crash *after* writing the marker but before starting the action? Now on restart we have a marker for an action we didn't run. The state machine needs special-case handling for "marker present but no observable action effect" → roll back? retry? It's a tarpit. The "crash → next cycle observes" model has none of this complexity.

**Caveat:** if a future action becomes non-idempotent (e.g. one that writes a unique ID to the modem and refuses on repeat), revisit this. None of our v2.0 actions are non-idempotent.

### Q14. Per-modem state file granularity — cdc-wdmN renumbering footgun?

**Stance: REAL footgun in the docs/ proposal as written. FIX: per-modem state files key by `usb_path`, not `cdc-wdmN`.** Confidence: HIGH.

Docs §7.1 says "One JSON file per cdc-wdm device, under `state/`." Filenames `cdc-wdm0.json` ... `cdc-wdm3.json`.

The problem: cdc-wdm minor numbers are assigned by the kernel in order of enumeration. If a modem disconnects (or kernel re-enumerates the bus), modem at usb_path `2-3.1.2` might come back as `cdc-wdm5` instead of `cdc-wdm1`. Now we have an orphan `cdc-wdm1.json` with stale state and a fresh-bootstrap on `cdc-wdm5.json`.

The docs/ §7.2 already acknowledges this for the *identity map* ("identity.json keyed by USB sysfs path... Survives cdc-wdm renumbering"). The same logic applies to per-modem state files.

**Recommended:**

```
state/
├─ by-usb/
│  ├─ 2-3.1.1.json    ← keyed by stable usb_path
│  ├─ 2-3.1.2.json
│  ├─ 2-3.1.3.json
│  └─ 2-3.1.4.json
└─ by-device-symlink/   (optional; for human inspection)
   ├─ cdc-wdm0.json -> ../by-usb/2-3.1.1.json
   ...
```

The state file payload still records `device: "cdc-wdm0"` for the current cycle (because policy uses cdc-wdmN for issue attribution and event log entries), but the *file's name* is the stable usb_path.

**Migration:** a fresh v2 box has empty state directories — no migration needed. Phase 0 boxes do not have legacy state files. Phase 5 cutover: any v1 state is discarded ("v2 starts fresh per box" — PROJECT.md "Out of Scope" clause is explicit).

**Anti-pattern fixed:** if you ever see code `Path(f"state/{modem.device}.json")`, that's the bug. Use `Path(f"state/by-usb/{modem.usb_path}.json")`.

### Q15. Schema evolution — daemon refuses future versions; what about older?

**Stance: build `wire/migrate.py` from day one with `migrate_v0_to_v1` (a no-op) and `migrate_unknown -> refuse`. Add `spark-modem ctl reset-state` as the recovery hatch.** Confidence: HIGH.

The docs/ + ADR-0004 say:
- Refuse future schema versions: log error, exit 3.
- Older versions: "explicit migration code or a tool-driven reset."

Tool-driven reset alone is *not enough*. Reasons:
1. Fleet has 100s of boxes. Telling field engineers "ssh in and run `ctl reset-state` after every upgrade" is expensive operationally.
2. Reset loses *operational state* (recovery counters, healthy_streak). Fresh start is fine on day-1 but bad if a long-running incident is mid-recovery during an upgrade.
3. We will need the migration framework eventually (any non-trivial schema change). Building it on demand under fire is worse than building it ergonomically up front.

**Recommended:**

```python
# src/spark_modem_watchdog/wire/migrate.py

def migrate(payload: dict, target_version: int) -> dict | None:
    """
    Migrate `payload` to `target_version`. Returns None if no migration path exists
    (caller should refuse / reset).
    """
    src = payload.get("schema_version")
    if src is None:
        return None  # malformed
    if src == target_version:
        return payload
    if src > target_version:
        return None  # never downgrade silently
    # Forward chain: apply v_i -> v_{i+1} ... -> v_target
    current = payload
    for v in range(src, target_version):
        migrator = _MIGRATORS.get(v)
        if migrator is None:
            return None
        current = migrator(current)
    return current

_MIGRATORS: dict[int, Callable[[dict], dict]] = {
    # 0: lambda p: p,  # placeholder for future v1 -> v2 migration
}
```

In v2.0, `_MIGRATORS` is empty and `target_version` is 1 — the migrate path is exercised only if we encounter a v0 file (we won't; v0 didn't exist). This costs 30 lines of code, sets the architectural pattern, and means v2.1's first schema bump is a one-line `_MIGRATORS[1] = migrate_v1_to_v2` addition.

**Plus the reset hatch.** `spark-modem ctl reset-state [--device=cdc-wdmN | --all]` exists per ARCH §13. Keep it. It's the escape valve when migration explicitly cannot.

### Q16. Test seam quality — does IO leak past protocol boundaries?

**Stance: the proposed seams are clean. ONE leak risk to lock down: ensure `qmi.QmiClient` only invokes `subproc.SubprocessRunner`, never `subprocess` directly.** Confidence: HIGH.

The §12 protocol list:

| Protocol | Real impl | Test impl | Leak risk |
|---|---|---|---|
| `QmiClient` | `qmi.RealQmiClient` | `qmi.FixtureQmiClient` (loads from `--qmi-fixture-dir`) | LOW if it goes through `SubprocessRunner` |
| `SubprocessRunner` | `subproc.RealRunner` | `subproc.FakeRunner` (records calls) | LOW |
| `Clock` | `clock.RealClock` | `clock.ManualClock` | None |
| `ZaoLogTailer` | `zao_log.RealTailer` | `zao_log.FixtureTailer` | None |
| `StateStore` | `state_store.JsonStore` | `state_store.MemoryStore` | None |
| `FileWriter` | `state_store.AtomicFileWriter` | `state_store.MemoryFileWriter` | None |

**The one risk:** `qmi.RealQmiClient.get_signal()` is tempted to do `await asyncio.create_subprocess_exec("qmicli", ...)` directly because it's right there. This bypasses `SubprocessRunner` and breaks the `--qmi-fixture-dir` replay path (because the fixture client fakes at the QMI layer, not the subprocess layer).

**Discipline:** `qmi.RealQmiClient.__init__` takes a `SubprocessRunner` and never imports `asyncio.subprocess`. Phase 0 lint check: `grep -r 'create_subprocess_exec' src/qmi/` should match zero lines (the only file allowed to call it is `subproc/`).

**Beyond the listed protocols:** add `WebhookPoster` (so tests can assert webhook payloads), `MetricRegistry` (so tests can assert metric increments). Both are tiny — 1 method each. Recommend adding them in Phase 0.

```python
class WebhookPoster(Protocol):
    async def post(self, url: str, payload: dict, *, timeout: float) -> WebhookResult: ...

class MetricRegistry(Protocol):
    def counter(self, name: str, labels: dict[str, str]) -> Counter: ...
    def gauge(self, name: str, labels: dict[str, str]) -> Gauge: ...
    def histogram(self, name: str, labels: dict[str, str]) -> Histogram: ...
```

The real `MetricRegistry` wraps `prometheus_client`; the fake records events for tests.

**`PIDLock` and `SignalHandler`:** also worth their own protocols, even if trivial. Tests should be able to assert "on SIGTERM, daemon shuts down within 5 s" without actually sending SIGTERM to the test runner.

### Q17. CLI vs daemon shared code — how structured?

**Stance: layered (CLI imports core); NO RPC to a running daemon for the diag/recovery/provision/reset paths in v2.0. Status command is the only one with daemon-IPC ambiguity, and it should read `/var/lib/.../status.json`, not RPC.** Confidence: HIGH.

The docs/ §13 CLI surface lists `diag`, `recovery`, `provision`, `reset`, `status`, `ctl <several>`. These have different needs:

| Command | Needs running daemon? | Mechanism |
|---|---|---|
| `diag [--qmi-fixture-dir]` | NO | Imports `observer`, runs one-shot. |
| `recovery [--diag-fixture]` | NO | Imports `policy`, runs pure-function. |
| `provision` | NO | Imports `actions.set_apn`, runs one-shot. |
| `reset <line> {--soft|--modem|--usb}` | NO | Imports `actions.modem_reset` etc. |
| `status` | NO | Reads `/var/lib/.../status.json`. (Daemon writes; CLI reads.) |
| `ctl reset-state` | NO | Reads/writes state files directly with PID-lock check. |
| `ctl support-bundle` | NO | Reads files; runs `journalctl` / `dmesg`. |
| `ctl install` / `uninstall` / `edit-config` / `version` | NO | systemd / file ops. |

**No command in v2.0 needs RPC to a running daemon.** This is a strong simplification: no Unix-socket protocol, no JSON-RPC layer, no schema for the wire calls. Open question Q1 ("HTTP API on Unix socket?") in the PRD is correctly deferred to v2.1.

**Layered structure:**

```
src/spark_modem_watchdog/
├─ wire/             # pydantic models — leaf, no other src/ deps
├─ clock/            # leaf
├─ subproc/          # leaf
├─ qmi/              # depends: subproc, wire, clock
├─ zao_log/          # depends: wire, clock
├─ state_store/      # depends: wire, clock
├─ event_logger/     # depends: wire, clock
├─ inventory/        # depends: subproc, wire, clock
├─ observer/         # depends: qmi, zao_log, inventory, wire, clock
├─ policy/           # depends: wire, clock — pure
├─ actions/          # depends: subproc, qmi, wire, clock, state_store
├─ status_reporter/  # depends: wire, clock, state_store
├─ config/           # depends: wire
├─ cli/              # depends: ALL the above
└─ daemon/           # depends: ALL the above
```

`cli/` imports the same modules as `daemon/`. There is no code duplication. The two entry points differ in:

- `daemon/`: builds the cycle loop, owns event sources, owns the cycle timer.
- `cli/`: builds *one-shot* invocations of subsets (e.g. `cli/diag.py` runs observer once and prints).

**Coordination:** `ctl reset-state` and `ctl support-bundle` while the daemon runs need to *read* the state files without conflicting with the daemon's writes. The atomic-write contract (FR-62) handles this: readers see a consistent file at all times. The PID-lock (FR-61) is for the *daemon* to be singleton; CLI commands can hold a separate read-only lock pattern (or just open and read; atomic writes are race-free for readers).

**Anti-pattern:** building a Unix-socket RPC layer "in case we need it." We don't. v2.1 can add one if Q1 lands "yes"; v2.0 ships without it.

---

## 5. Comparison table: docs/ proposal vs this research

| Question | docs/ approach | This research's recommendation | Delta |
|---|---|---|---|
| Q1 Single-thread asyncio | Single-thread asyncio | Single-thread asyncio | Same; HIGH agreement. |
| Q2 Per-task timeout | Implied `asyncio.gather` + per-task timeout (ARCH §4.3 and NFR-4) | `asyncio.TaskGroup` + per-task `asyncio.timeout` | **Modernize the primitive.** Mostly cosmetic; better cancellation semantics. |
| Q3 State-store lock | "single asyncio.Lock guards state-store commits" | Per-modem locks + 1 globals lock | **Pushback: change.** Avoids worst-case fsync stall on the cycle. |
| Q4 pyudev | "pyudev" (ARCH §8) | `pyudev.Monitor.fileno()` + `loop.add_reader` | **Specify integration.** docs is silent on the bridge mechanism. |
| Q5 pyroute2 | "pyroute2" (ARCH §8) | `AsyncIPRoute` (the asyncio-native API) | **Specify the API.** docs is silent on which submodule. |
| Q6 inotify | "inotify" generic (ARCH §8) | `asyncinotify` + outer reopen-on-rotate loop | **Specify library + rotation pattern.** STACK already chose `asyncinotify`. |
| Q7 /dev/kmsg | "kmsg via /dev/kmsg reader" (ARCH §8) | Open `O_NONBLOCK` + `add_reader` + EPIPE-tolerant | **Specify pattern.** No library; ~30 LOC. |
| Q8 qmicli subprocess | `asyncio.subprocess` (ARCH §4.3); `close_fds=True` (§15 Q4) | Same + `proc.communicate(timeout=...)`; two-stage timeout (graceful then SIGKILL drain) | **Add the kill-and-drain detail.** §15 Q4's lsof tripwire is good defense-in-depth. |
| Q9 Prom over UDS | "prometheus_client over Unix socket" (§5, §11.2) | `make_wsgi_app()` + `UnixStreamServer` subclass; run in `asyncio.to_thread` | **Specify recipe.** docs is silent on the adapter. |
| Q10 sd_notify | "Type=notify" (FR-53) + 60s NFR-13 | `sdnotify` lib; emit READY=1 after first cycle; STATUS= keepalive; optional WatchdogSec= | **Specify timing.** docs picks the contract; we pick when. |
| Q11 SIGHUP reload | "SIGHUP reloads (1)–(5)" (§10) | Same: data items reload, topology items restart-only | Same. Already correct. |
| Q12 SIGTERM shutdown | "graceful SIGTERM within 5s" (FR-53) | `loop.add_signal_handler` → `shutdown_event` → drain cycle → close stores | **Specify sequence.** docs is silent on the in-flight subprocess concern. |
| Q13 Crash mid-action | "next cycle observes" (RECOVERY §9) | Same: idempotent + atomic + counter-after-execute is sufficient | Same. **Pushback considered and rejected** (no marker needed). |
| Q14 State file naming | "One JSON file per cdc-wdm device" (§7.1) | Per-`usb_path` keyed file; cdc-wdmN is a label, not a key | **Pushback: change.** docs has a real footgun on USB renumbering. |
| Q15 Schema evolution | "explicit migration code or tool-driven reset" (§10, ADR-0004) | Build `wire/migrate.py` from day one (empty registry); keep reset hatch | **Add the framework upfront.** Tool-driven-only is too brittle for fleet ops. |
| Q16 Test seams | Protocols listed in §12 | Same + add `WebhookPoster`, `MetricRegistry`, `PIDLock`, `SignalHandler` | **Add 4 protocols.** Otherwise their consumers are untestable. |
| Q17 CLI vs daemon | Single binary, subcommands (§13); silent on shared-code structure | Layered: CLI imports core; no RPC in v2.0 | **Specify layering.** No daemon RPC. Q1 (PRD §10) correctly deferred. |

---

## 6. "If you do X, you'll regret it" — architectural anti-patterns

These are the patterns I expect Phase 0/1 to be tempted by, listed in order of severity.

1. **`subprocess.run` (sync) anywhere in the daemon.** Blocks the event loop. STACK calls this out; reiterating because Phase 0 will be tempted to "shim it for now and clean up later." Don't. Cost is 5 minutes; debt is a week.
2. **`asyncio.gather(*coros, return_exceptions=True)` for per-modem probes.** Works but exception handling is by-hand. Use `TaskGroup`. The diff is ~3 lines.
3. **`MonitorObserver` (pyudev's thread-based observer).** Calling `loop.call_soon_threadsafe` from its callback works but is the kind of code that breaks in mysterious ways under shutdown. Use `add_reader` on `monitor.fileno()`.
4. **Per-modem state files keyed by `cdc-wdmN`.** USB renumbering will silently corrupt your state. Key by `usb_path`.
5. **Single `asyncio.Lock` for all state commits.** Not catastrophic, but a slow fsync on one modem stalls the others. Fine-grained locks are 10 lines.
6. **`signal.signal(SIGTERM, handler)` instead of `loop.add_signal_handler`.** The C-level handler can fire on any thread / mid-step; you can't safely call asyncio APIs from it.
7. **Putting `subprocess.run` or `httpx.post` directly in policy/.** Policy is pure. ADR-0004 + RECOVERY_SPEC §0 say so. Anything that breaks this breaks every replay test.
8. **Building a Unix-socket RPC for `ctl status`.** Add complexity for nothing — `status.json` is atomically written every cycle and is exactly what `status` should print. Save the socket idea for v2.1 if Q1 lands "yes".
9. **`urllib.request.urlopen` for webhooks.** Synchronous; no timeout by default. Use `httpx.AsyncClient` (per STACK).
10. **Forgetting `fsync` on the directory after `os.replace`.** On a power cut, the rename can be lost even though the file content is durable. The atomic-write recipe must include directory fsync.
11. **Reading `/dev/kmsg` with `open(...).readlines()`.** Blocking read on a kernel device — depending on kernel version, this can return gibberish or block forever. Use `O_NONBLOCK` + `add_reader`.
12. **A "best-effort" event log writer that catches exceptions and continues.** Hides bugs. Wrong write → log to journal at WARNING level → fall through. Don't silently swallow.
13. **Hot-reloading event-source paths.** Means tearing down and re-establishing pyudev/asyncinotify subscriptions. Possible, but doubles the test matrix. Restart-only is correct.
14. **`asyncio.run_in_executor` to "speed up" qmicli.** It's already non-blocking. Wrapping it in a thread pool *adds* overhead, doesn't remove it.
15. **State-machine arms with `if/elif` instead of `match` on `ModemState`.** `match` + mypy --strict catches missing cases. This is exactly the test ADR-0005's "exhaustive match statements" promises.

---

## 7. Confidence summary per recommendation

| Recommendation | Confidence | Why |
|---|---|---|
| Use `TaskGroup` + `asyncio.timeout` not `gather`+`wait_for` | HIGH | Python 3.12 docs explicitly recommend; structured concurrency is the modern API. |
| `pyudev` via `add_reader(monitor.fileno())` | HIGH | This is the documented integration mechanism; pyudev issue #450 confirms no native asyncio yet. |
| `pyroute2.AsyncIPRoute` for rtnetlink | HIGH | 0.9.x is the asyncio API; the sync IPRoute is built over it. |
| `asyncinotify` with outer reopen-on-rotate loop | HIGH | asyncinotify docs explicitly say MOVE_SELF doesn't update the watch path; reopen pattern is canonical. |
| `/dev/kmsg` via `O_NONBLOCK` + `add_reader` | HIGH | Kernel guarantee: one read = one record. EPIPE on overrun is the documented behavior. |
| `asyncio.subprocess` with two-stage timeout (graceful then SIGKILL) | HIGH | `proc.communicate(timeout=...)` is the canonical pattern; SIGKILL drain handles the wedged-with-full-stdout corner. |
| Prom over UDS via `make_wsgi_app` + `UnixStreamServer` subclass + `to_thread` | MEDIUM-HIGH | Pattern is sound; needs Phase 0 spike to confirm aarch64+wsgiref interaction. |
| `sd_notify` after first full cycle (~5–35s, within NFR-13's 60s) | HIGH | Standard systemd Type=notify pattern; matches sd_notify(3) man page. |
| Per-modem `asyncio.Lock` instead of single state-store lock | MEDIUM | Both work; per-modem is a small win at small cost. Reasonable to defer to "if cycle latency starts pinching, refactor." |
| State files keyed by `usb_path` not `cdc-wdmN` | HIGH | Real footgun on USB renumbering; identity.json already does this for the same reason. |
| `wire/migrate.py` from day one | HIGH | Building under pressure during a fleet migration is worse than prebuilding. |
| Add `WebhookPoster` and `MetricRegistry` protocols | HIGH | Otherwise their consumers cannot be unit-tested without network/Prom registry. |
| CLI imports core; no RPC layer in v2.0 | HIGH | Q1 is correctly deferred; status.json + atomic writes give "view current state" without RPC. |
| `loop.add_signal_handler` not raw `signal.signal` | HIGH | `signal.signal` from asyncio is officially unsafe; documented in Python signal module docs. |
| Idempotent action + atomic write + counter-after-execute → no in-flight marker | HIGH | The argument from idempotency is airtight given FR-27 + FR-62 + RECOVERY §9. |

---

## 8. What I am uncertain about (gaps for Phase 0 to resolve)

- **Prom-on-UDS aarch64 spike:** the wsgiref Unix-socket subclass works on x86 Linux; I have no reason to expect aarch64 / glibc 2.31 to differ, but a 1-day spike in Phase 0 with `curl --unix-socket /run/spark-modem-watchdog/metrics.sock http://x/metrics` ends the speculation.
- **WatchdogSec= cadence:** suggested 90 s (3× 30 s cycle). If field engineers want a tighter SLO, drop to 60 s. Trade-off: tighter watchdog = more sensitive to GC pauses + heavy logging. Decide post-Phase 1 latency profiling.
- **Type=notify vs Type=notify-reload:** systemd 253+ supports `notify-reload`. JetPack 5.1.5 / R35.6.4 / Ubuntu 20.04 ships systemd 245. We must use `Type=notify` + manual SIGHUP handler, NOT `Type=notify-reload`. Confirmed; if/when boxes upgrade past systemd 253, revisit.
- **`AsyncIPRoute` API stability:** the 0.9.x line is current; we're picking it. The 0.9.x `bind()` + `async for` pattern is documented but the wider community has fewer worked examples than IPRoute (sync). If the API changes between 0.9 and 1.0, we have one library upgrade to absorb.
- **Single-process vs per-modem-process supervisor:** I considered (briefly) whether to run one watchdog process per modem and a thin coordinator. Rejected because: shared state (driver_reset gate, global metrics) makes IPC the bulk of the code; failure-isolation is achievable with `try/except` + cycle-skip; systemd `Restart=on-failure` is our safety net. But this is the kind of decision that only feels right after we've shipped one and seen what wakes us up. Worth revisiting at the M6 milestone (zero unhandled-exception restarts in 30 days).

---

## 9. Implications for roadmap

The 25-step build order in §3.3 maps cleanly onto migration phases:

- **Migration Phase 0 (bench):** build steps 1–25. Single bench Jetson; 4 modems.
- **Migration Phase 1 (bench dry-run):** all 25 + the v1-side-by-side replay harness (uses `--qmi-fixture-dir` and `--diag-fixture` from FR-51/FR-52).
- **Migration Phase 2 (field box dry-run):** prove sd_notify + watchdog ping work in a real systemd environment (no laptop emulation can fully cover this).
- **Migration Phase 3+ (active):** the architecture is locked. Only configuration changes here.

Phase-specific architectural research flags:

- **Phase 0** likely needs deeper research on: the Prom-on-UDS recipe; the `python-build-standalone` packaging integration (per STACK.md MEDIUM confidence). Spike both day 1.
- **Phase 1** likely needs deeper research on: the v1 replay harness format; whether v1's `qmicli` output captures are byte-stable enough for our parser fixtures.
- **Phase 4 (10% canary)** likely needs deeper research on: real production cycle-latency distributions; whether NFR-1's 10s is hit (and whether the per-modem state lock recommendation in Q3 was actually needed).

---

## 10. Sources

**Primary (HIGH confidence):**
- [Python 3.14 asyncio-task documentation](https://docs.python.org/3/library/asyncio-task.html) — TaskGroup + timeout primitives.
- [Python 3.14 asyncio-eventloop documentation](https://docs.python.org/3/library/asyncio-eventloop.html) — `add_signal_handler`, `add_reader` semantics.
- [Python 3.12 asyncio-subprocess documentation](https://docs.python.org/3.12/library/asyncio-subprocess.html) — ChildWatcher, default ThreadedChildWatcher.
- [pyudev 0.24.4 monitor module](https://pyudev.readthedocs.io/en/latest/api/pyudev.html) — Monitor.fileno() integration.
- [pyudev issue #450: Add asyncio support?](https://github.com/pyudev/pyudev/issues/450) — confirms no native asyncio API as of writing.
- [pyroute2 0.9.3 docs: AsyncIPRoute](https://docs.pyroute2.org/iproute_intro.html) — async netlink API.
- [pyroute2 0.9.3 docs: NDB intro](https://docs.pyroute2.org/ndb.html) — confirms NDB is for management not observation.
- [asyncinotify 4.4.0 documentation](https://asyncinotify.readthedocs.io/en/latest/asyncinotify.html) — MOVE_SELF caveat documented.
- [sd_notify(3) Linux manual page](https://man7.org/linux/man-pages/man3/sd_notify.3.html) — READY/RELOADING/STOPPING/WATCHDOG protocol.
- [systemd PR #25916: Type=notify-reload](https://github.com/systemd/systemd/pull/25916) — version availability of notify-reload.
- [prometheus/client_python exposition.py](https://github.com/prometheus/client_python/blob/master/prometheus_client/exposition.py) — `make_wsgi_app` source.

**Secondary (MEDIUM confidence):**
- [hynek's "Waiting in asyncio"](https://hynek.me/articles/waiting-in-asyncio/) — practical TaskGroup vs gather comparison.
- [roguelynn's "Graceful Shutdowns with asyncio"](https://roguelynn.com/words/asyncio-graceful-shutdowns/) — signal-handler shutdown patterns.
- [cockpit-project HACKING](https://github.com/cockpit-project/cockpit/blob/main/HACKING.md) — comparable production asyncio Python daemon.
- [Reliable file updates with Python (gocept blog)](https://blog.gocept.com/2013/07/15/reliable-file-updates-with-python/) — atomic write recipe with directory fsync.

**Tertiary (directional only):**
- [maliubiao/python_kmsg](https://github.com/maliubiao/python_kmsg) — example Python `/dev/kmsg` reader; confirms one-record-per-read kernel guarantee.
- [Cziegler "Signal handling with async multiprocesses"](https://medium.com/@cziegler_99189/gracefully-shutting-down-async-multiprocesses-in-python-2223be384510) — multiprocess pattern (we don't use, but cross-checks the single-process pattern by contrast).

---

*Architecture research for: spark-modem-watchdog v2 (single-process root daemon, asyncio, aarch64 Linux)*
*Researched: 2026-05-05*

# Stack Research — spark-modem-watchdog v2

**Domain:** Long-running root-privileged single-process asyncio daemon on aarch64 Linux (NVIDIA Jetson Orin NX, Ubuntu 20.04 / L4T R35.6.4, kernel 5.10-tegra)
**Researched:** 2026-05-05
**Overall confidence:** HIGH for library versions, HIGH for Python-version recommendation, MEDIUM for packaging tool choice (the field has shifted under us).

This document is **opinionated**. Where the docs/ proposal stands up against current reality, we say so and pin versions. Where it does not, we say what to change and why.

---

## Executive recommendation (TL;DR)

1. **Bundle CPython 3.12.x in the .deb venv via `astral-sh/python-build-standalone`** — do NOT use deadsnakes (focal is unsupported as of April 2025), do NOT compile from source on the build host, do NOT drop to Python 3.8. ADR-0001's "ship the runtime we tested with" stance is correct; the implementation tactic just changed.
2. **Pin pydantic to `>=2.13,<3` and target Python 3.12.** pydantic dropped 3.8 support in v2.11 (March 2025). Target the most recent CPython that python-build-standalone publishes prebuilt and that pydantic-core wheels exist for — **3.12** today, not 3.13 (free-threaded transition risk) and not 3.11 (no longer the latest stable).
3. **Replace `dh-virtualenv` with a hand-rolled `debhelper` rule that drops `python-build-standalone` + a `uv`-installed venv into `/opt/spark-modem-watchdog/`.** dh-virtualenv assumes a system Python you can re-use; we are deliberately NOT re-using one. Rolling our own is ~80 lines of shell and removes a moribund dependency.
4. **Add `httpx` for webhooks** (not stdlib `urllib.request`, not `requests`, not `aiohttp`). The docs/ tech-stack table is silent on webhooks; this is a gap.
5. **Adopt `mypy --strict` as the gate, but run `pyright` in editor.** The docs/ proposal says mypy; keep it. mypy's stricter inference around `Any` propagation matches our policy-engine purity goal better than pyright's friendlier-but-looser defaults.
6. **Drop `black`; use `ruff format` only.** The docs/ proposal already hedges with "configured-as-ruff-format" — make it explicit.

Confidence on each above: 1=HIGH, 2=HIGH, 3=MEDIUM, 4=HIGH, 5=MEDIUM, 6=HIGH.

---

## Python 3.8.10 vs 3.11+ resolution

**Recommendation: bundle CPython 3.12.x in the .deb venv. Confidence: HIGH.**

### Why this is the only good answer

The PRD and ADR-0001 already say "we ship the runtime we tested with" and call out a venv at `/opt/spark-modem-watchdog/lib/python3.11/...`. The only open question was *how* to source that interpreter. Three options were on the table; only one survives 2026-reality.

| Option | Verdict | Reason |
|--------|---------|--------|
| **A. Bundle 3.11+ in the venv** | **CHOSEN** | Honors ADR-0001's intent. `python-build-standalone` solves the supply problem. |
| B. Drop to Python 3.8 code | REJECTED | pydantic v2.11 dropped 3.8 (March 2025); pydantic v2.13 (latest) requires ≥3.9. We'd be pinned to a 14-month-old pydantic and would lose match statements, TaskGroup, tomllib, parameterized typing.Self, and `from __future__ import annotations` deferred eval cleanly. Cost benefit: terrible. |
| C. Upgrade Jetson system Python via deadsnakes | REJECTED — deadsnakes does not support focal anymore | Ubuntu 20.04 standard support ended 31 May 2025; deadsnakes deletes packages on EOL (precedent: 18.04 in April 2023). Even on Ubuntu Pro ESM (which keeps the *3.8 package* alive through 2030–2032), deadsnakes itself does not publish 3.11+ for focal. |

### Sourcing the bundled interpreter

Use **`astral-sh/python-build-standalone`** (formerly `indygreg/python-build-standalone`; stewardship transferred to Astral on 2024-12-17 and the release cadence is now automated and reliable). This is the same project `uv` uses to install Python.

Concrete plan:

- Asset: `cpython-3.12.<patch>+<datetag>-aarch64-unknown-linux-gnu-install_only.tar.gz`
- Baseline glibc: **2.17**. Ubuntu 20.04 ships glibc 2.31. Comfortable margin (no risk of "not found" against tegra).
- Build host: any Linux x86_64 or arm64 with internet at *build* time. Constraint C20 (offline at install) is satisfied because the .deb bundles the interpreter.
- Why `gnu` and not `musl`: glibc is what the Jetson runs; staying on glibc keeps `ctypes`, `pyudev` (which dlopens libudev.so.1), and any C extensions consistent with the host.

### Why 3.12 specifically (not 3.11, not 3.13, not 3.14)

- **Not 3.11**: It's been the team's mental anchor, but it's already two minors behind 3.14. Migrating to 3.12 now (pre-Phase-0) is cheaper than migrating later.
- **3.12 (RECOMMENDED)**: PEP 695 type parameter syntax, per-interpreter GIL groundwork, real `tomllib`, sys.monitoring (cheap profiling), TaskGroup matured, BOLT-optimized binaries from python-build-standalone. Every wheel we depend on (pydantic-core 2.x, prometheus-client 0.25, pyudev 0.24, pyroute2 0.9.6) ships aarch64 wheels for 3.12.
- **Not 3.13**: free-threaded build complexity and slightly thinner wheel ecosystem on aarch64 (some C extensions still building). For a daemon where stability matters more than novelty, wait one cycle.
- **Not 3.14**: in beta/RC as of May 2026; not appropriate for a production rewrite.

### What in docs/ specifically would break under 3.8 (the rejected option)

For the record, since this was an open question (Q8), here is the survey of what 3.8-compat would cost:

| docs/ pattern | Min Python | Workaround on 3.8 |
|---------------|-----------|-------------------|
| `match` statements (RECOVERY_SPEC, policy engine) | 3.10 | Rewrite as `if/elif`. Verbose but works. |
| `asyncio.TaskGroup` (ARCH §4.3 — implied for per-modem `gather`) | 3.11 | The `taskgroup` PyPI backport works on 3.8–3.11. Acceptable but extra dep. |
| `asyncio.timeout` context manager | 3.11 | `async-timeout` library. Acceptable. |
| `tomllib` (potential pyproject.toml reads) | 3.11 | `tomli` library. Acceptable. |
| `typing.Self`, `Literal` discriminated unions on assignment | 3.11 / 3.10 | `typing_extensions`. Acceptable. |
| `from __future__ import annotations` quirks under pydantic v2 | n/a | pydantic v2 with deferred annotations works on 3.9+; on 3.8 you hit `ForwardRef._evaluate` signature mismatches in some chains. |
| `pydantic` v2.11+ | **≥3.9** | **No workaround. Pin to v2.10.x and never upgrade. Hard NO.** |
| `prometheus_client` 0.22+ | **≥3.9** | Pin to 0.21.x. Possible but pointless. |
| `pyudev` 0.24+ | **≥3.9** | Pin to 0.24.0 (the last 3.8-compatible one). Possible. |
| `pyroute2` latest | **≥3.9** | Pin to 0.7.x. Possible. |
| Parameterized generic builtins `list[int]` at *runtime* | 3.9 (via `__future__`) / 3.10 (no `__future__`) | Use `from __future__ import annotations` everywhere; pydantic v2 still works because it treats annotations as strings. |

The deal-breaker is the pydantic ceiling alone. Everything else has a workaround; pydantic v2.11+ does not. Locking to a year-old pydantic for the 5-year fleet life of v2 is the worst of both worlds.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **CPython** | **3.12.x** (latest patch at build time) | Language runtime | ADR-0001 dictates a typed-language rewrite; 3.12 is the lowest-cost target that all dependencies fully support. Sourced via `python-build-standalone` aarch64-gnu builds. |
| **asyncio** (stdlib) | n/a (3.12 stdlib) | Concurrency | Single-process IO-bound daemon. ARCH §4.3 already commits. No reason to add `trio`/`anyio`. |
| **pydantic** | `>=2.13,<3` | Wire-format types, config validation | ADR-0004 mandates typed contracts with closed enums + tagged unions + `schema_version` checks. v2.13 is current (April 2026). Cap at `<3` because v3 will likely change the model API. |
| **pydantic-core** | matched to pydantic 2.13 | Rust-backed validator | Comes transitively. Wheels exist for `aarch64-manylinux_2_17` (matches our glibc). No special action. |
| **PyYAML** | `>=6.0.2,<7` | Config loading | Stdlib-quality, ubiquitous; FR-54 layered config loads YAML. C-extension wheels for aarch64 exist. |
| **prometheus-client** | `>=0.25,<1` | Metrics over Unix socket | NFR-21 requires Prom scrape. Pure-python, supports `make_wsgi_app` over a UDS via custom server (we'll wrap with stdlib `socket` + `wsgiref` or `aiohttp.web`). |
| **pyudev** | `>=0.24.4,<1` | udev add/remove subscription | Pure-python ctypes binding to `libudev.so.1`; needs libudev ≥151 (Ubuntu 20.04 ships 245 — fine). FR-1, ARCH §8. |
| **pyroute2** | `>=0.9.6,<1` | rtnetlink link-state events | The rtnetlink event source for ARCH §8 "Link state change". Pure-Python, no compiler at install time. |
| **httpx** | `>=0.27,<1` | Webhook POST (FR-44) | Replaces the docs/ silence on this point. Has both sync and async clients with the same surface; supports HTTP/2; explicit timeouts; built-in retries via transports. Clean asyncio integration. |
| **systemd-python** OR **sdnotify** | systemd-python `>=235`; sdnotify `>=0.3.2` | `Type=notify` readiness | FR-53 says systemd `Type=notify`. `sdnotify` is the lighter, pure-Python option (just sends `READY=1` over `$NOTIFY_SOCKET`). Prefer it; `systemd-python` pulls a system C library and is overkill. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **inotify_simple** | `>=1.3.5,<2` | inotify on Zao log + kmsg reader's rotation handling | ARCH §8 inotify-on-Zao-log; ADR-0002 event sources. Tiny ctypes wrapper, no deps. Alternative: `asyncinotify` (asyncio-native) — equivalent quality, choose based on whether you want sync-thread or asyncio-task event consumption. **Pick `asyncinotify` (`>=4.0.10,<5`) since the rest of the daemon is asyncio.** |
| **asyncinotify** | `>=4.0.10,<5` | asyncio inotify | See above. Replaces `inotify_simple` in our case. |
| **dbus-next** OR **jeepney** | dbus-next `>=0.2.3`; jeepney `>=0.9.0` | systemd unit-state watching (deferred / optional, ARCH §8) | Only needed if Q4/Q6 land on "watch zao-infra-ctrl.service via dbus". Recommend **`jeepney` >=0.9.0** — purer asyncio integration, more recent active development, used by `secretstorage` and `keyring` in Debian. dbus-next still works but its release cadence has slowed. *Defer: not v2.0-required.* |
| **psutil** | `>=5.9,<7` | Process self-stats (RSS for the NFR-3 budget tripwire) | NFR-3 says ≤80 MiB; the daemon should self-report and trip if it crosses. psutil is the canonical aarch64-supported stdlib-quality wrapper. |
| **tomli** | n/a — use stdlib `tomllib` (Python 3.11+) | TOML reads (pyproject.toml only, not config) | We're on 3.12, so no dep. Listed only to confirm it's NOT needed. |
| **typing-extensions** | `>=4.12` | Forward-compatible typing helpers | Even on 3.12, pydantic transitively requires it. Don't pin yourself; let pydantic pull the right minor. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| **ruff** | Lint + format | Replaces flake8 + black + isort + pyupgrade. Configure `format` profile = black-equivalent. Pin `>=0.6,<1`. |
| **mypy** (`--strict`) | Type check (CI gate) | NFR-40. Pin `>=1.13,<2`. mypy's stricter `Any` propagation rules suit a policy-engine that must be pure. |
| **pyright** (developer-only, optional) | Editor/IDE feedback | Faster incremental check during development. **Not** the CI gate (would create dual-source-of-truth fights). Not required to be installed. |
| **pytest** | Test runner | Pin `>=8.3,<9`. |
| **pytest-asyncio** | asyncio test support | Pin `>=0.24,<1`. Use `mode = "auto"` in pyproject. |
| **hypothesis** | Property tests (per TEST_STRATEGY §5) | Pin `>=6.110,<7`. |
| **pytest-cov** | Coverage | Pin `>=5,<7`. |
| **uv** | Package install during build | Astral's installer; ~10× faster than pip; consistent lockfile. Used at build time only, not at runtime on the box. Pin `>=0.5,<1`. |
| **debhelper** + custom rules | .deb assembly | See "Packaging" section. |
| **lintian** | Debian policy lint (TEST_STRATEGY §6) | System tool; install on CI host. |

### Tools and libraries we are explicitly REPLACING vs the docs/ proposal

| docs/ proposal | Replace with | Why |
|----------------|-------------|-----|
| `black` (alongside ruff) | `ruff format` only | The docs/ table already says "configured-as-ruff-format". Drop black entirely. One tool, one config. |
| Implicit `requests` for webhooks | `httpx` | docs/ doesn't actually pick a webhook lib, but `requests` is the obvious default. `requests` is sync-only; calling it from the asyncio loop blocks. `httpx` has a real async client. |
| `dh-virtualenv` (implied by §14 "venv at /opt/spark-modem-watchdog/") | Custom debhelper rule using `python-build-standalone` + `uv pip install` | dh-virtualenv assumes a system Python interpreter; we are deliberately not using one. Last dh-virtualenv release is 1.2.2 (mid-2022), 1.2.4 in 2024 in some forks; cadence has slowed. Rolling our own is ~50 lines of `debian/rules` and removes a fragile dependency on someone else's Python-build assumptions. |
| `pip` (implicit) for installing into venv | `uv pip install --no-deps -r requirements.lock` | Faster, deterministic, lockfile-driven. Keeps build reproducible. |
| `subprocess` (sync) anywhere | `asyncio.subprocess` everywhere | docs/ already says this; calling it out for emphasis since Phase 0 will be tempted to shim it. |

---

## Packaging recipe (the .deb)

> The docs/ proposal calls for "a Debian `.deb` containing a venv under `/opt/spark-modem-watchdog/`" but does not specify the toolchain. Phase 0 will commit to one. Here is the recipe.

**Layout produced** (matches ARCH §6 verbatim):

```
/opt/spark-modem-watchdog/
├─ python/                              ← unpacked python-build-standalone
│  ├─ bin/python3.12
│  ├─ lib/python3.12/...
│  └─ ...
├─ venv/                                ← venv created with /opt/.../python/bin/python3.12 -m venv
│  └─ lib/python3.12/site-packages/...
├─ bin/spark-modem                      ← shim: exec /opt/.../venv/bin/spark-modem "$@"
├─ libexec/spark-modem-watchdog         ← shim: exec /opt/.../venv/bin/spark-modem-watchdog "$@"
└─ share/{default-config.yaml, carriers/il.yaml, systemd/, logrotate/}
```

**Build steps (`debian/rules`):**

1. Download `cpython-3.12.x+YYYYMMDD-aarch64-unknown-linux-gnu-install_only.tar.gz` (pinned by SHA256 in `debian/python.sha256`). Unpack to `debian/spark-modem-watchdog/opt/spark-modem-watchdog/python/`.
2. `/opt/.../python/bin/python3.12 -m venv /opt/.../venv` (called against the destdir).
3. `uv pip install --python /opt/.../venv/bin/python --no-deps -r requirements.lock` (the project itself + frozen deps).
4. `python -m compileall` for faster cold-start (helps NFR-13).
5. Strip __pycache__ duplicates if size matters (it shouldn't — tegra has plenty).
6. Generate the two `bin/` shim scripts.
7. Install systemd unit, default config, logrotate snippet, post-install hook (creates `/var/lib/...`, `/var/log/...`, `/run/...` with FR-61-mandated modes).

**Estimated .deb size**: ~30–35 MiB (python-build-standalone install_only is ~25 MiB unpacked + pydantic-core wheel ~3 MiB + everything else ~3 MiB). Acceptable for a fleet that already ships JetPack images of multi-GiB.

**Security update story**: the bundled interpreter does NOT receive Ubuntu security updates. We accept this and own it: we rebuild the .deb when a CPython security release lands (release cadence: 4–6× per year on stable branches). This is the same model uv users have lived with for 18 months. The alternative (system Python on focal) leaves us on Python 3.8 PSF-EOL for free.

**Why not dh-virtualenv**:

- It assumes you start from `/usr/bin/python3` and creates a venv. We don't have a 3.12 system python.
- Workaround would be: install python-build-standalone *into* the build host, point dh-virtualenv at it, hope it does the right thing with the rpath shenanigans. This is more fragile than just doing the dance ourselves.
- dh-virtualenv last release on the canonical Spotify repo is 1.2.2 (2022). It still works, but the maintenance pulse is shallow.

**Why not pex / shiv / pyinstaller**:

- pex/shiv produce a single zip archive with a __main__. They want the *system* python at runtime. We don't have one.
- pyinstaller produces a fat binary with bundled CPython, but its bundling is more brittle than a plain venv (relative imports, ctypes path discovery for libudev, etc.). For a daemon with native deps and ctypes lookups (pyudev), a plain venv is more debuggable.

**Why not uv standalone (`uv tool install`)**:

- `uv tool` is great for user-level developer tools. It's not a fleet-deployment story. We need a `.deb` for `apt install` and unattended provisioning. uv is a *build-time* tool here.

Confidence on the full packaging recipe: **MEDIUM**. The pieces are all proven; the integration is bespoke. Phase 0 should produce a working `.deb` end-to-end before anything else.

---

## Comparison with docs/ proposal

| Concern | docs/ proposal (ARCH §5, ADR-0001, ADR-0004) | This research's recommendation | Delta |
|---------|----------------------------------------------|-------------------------------|-------|
| Language | Python 3.11+ | **Python 3.12.x** (specific) | Move target one minor up. 3.11 is fine technically but 3.12 has matured wheels and is what we'd pick today. |
| Async runtime | `asyncio` (stdlib) | `asyncio` (stdlib) | Same. |
| Wire types | `pydantic` v2 | `pydantic >=2.13,<3` | Same library, version pinned to range. |
| Config | `PyYAML`, layered with env + flags | `PyYAML >=6.0.2,<7`, layered with env + flags | Same; pinned. |
| Subprocess | stdlib `asyncio.subprocess` | stdlib `asyncio.subprocess` | Same. |
| QMI parsing | In-house wrapper over `qmicli` text | In-house wrapper over `qmicli` text | Same. **Note**: libqmi 1.30.4 in focal-updates is the maintained version we wrap. |
| Logging | stdlib `logging` + JSON formatter | stdlib `logging` + JSON formatter | Same. Suggest `python-json-logger` (`>=3.1`) or hand-rolled (~30 lines). Either is fine; hand-rolled keeps deps minimal. |
| Metrics | `prometheus_client` over Unix socket | `prometheus_client >=0.25,<1` over Unix socket | Same; pinned. |
| Webhook HTTP | (not specified) | `httpx >=0.27,<1` | **Gap filled**: docs is silent. Pick httpx, async client, explicit timeout, retry transport. |
| systemd notify | `Type=notify` (FR-53) | `sdnotify >=0.3.2` (pure-Python) | **Gap filled**: docs picks the *contract* but not the library. sdnotify keeps deps light. |
| Tests | `pytest`, `pytest-asyncio` | `pytest >=8.3,<9`, `pytest-asyncio >=0.24,<1`, `hypothesis >=6.110,<7` | Same + pinned + hypothesis explicitly listed (TEST_STRATEGY mentions it but tech-stack table doesn't). |
| Lint/format | `ruff`, `black` ("configured-as-ruff-format") | `ruff >=0.6,<1` only; **drop black** | Simplification. The hedge in docs is unnecessary; ruff format is stable. |
| Type-check | `mypy --strict` | `mypy >=1.13,<2 --strict` | Same; pinned. pyright optional in editor; not in CI. |
| Packaging | "Debian `.deb` with venv at `/opt/spark-modem-watchdog/`" | python-build-standalone + uv + custom debhelper rule | **Method specified**. The docs/ goal is correct; the implementation tactic is novel and worth a short ADR. |
| Init | systemd `Type=notify` | systemd `Type=notify` + `Restart=on-failure` + `LoadCredential=` (NFR-34) | Same. |
| udev events | `pyudev` (ARCH §8) | `pyudev >=0.24.4,<1` | Same; pinned. |
| rtnetlink | `pyroute2` (ARCH §8) | `pyroute2 >=0.9.6,<1` | Same; pinned. |
| inotify | (not specified by name) | `asyncinotify >=4.0.10,<5` | **Gap filled**. asyncinotify > inotify_simple for an asyncio daemon. |
| dbus (optional) | "`dbus` if available, else polled" (ARCH §8) | **Defer**. If implemented later, prefer `jeepney >=0.9.0`. | Deferred to v2.1; not on critical path. |
| /dev/kmsg | (custom reader implied, ARCH §8) | Custom reader; no library needed | Confirmed. `/dev/kmsg` is a 60-line custom reader; no library buys us anything. |
| psutil | (not specified) | `psutil >=5.9,<7` for self-RSS tripwire (NFR-3) | **Gap filled**. Optional but valuable. |

---

## Installation (developer setup)

```bash
# One-time on dev laptop
curl -LsSf https://astral.sh/uv/install.sh | sh         # uv (fast pip)
uv python install 3.12                                   # ← same artifact that production gets

# Project bootstrap
cd spark-modem-watchdog
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e '.[dev]'
```

`pyproject.toml` deps (canonical pin set, edit in lockstep):

```toml
[project]
name = "spark-modem-watchdog"
requires-python = ">=3.12,<3.13"
dependencies = [
    "pydantic>=2.13,<3",
    "PyYAML>=6.0.2,<7",
    "prometheus-client>=0.25,<1",
    "pyudev>=0.24.4,<1",
    "pyroute2>=0.9.6,<1",
    "asyncinotify>=4.0.10,<5",
    "httpx>=0.27,<1",
    "sdnotify>=0.3.2,<1",
    "psutil>=5.9,<7",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3,<9",
    "pytest-asyncio>=0.24,<1",
    "pytest-cov>=5,<7",
    "hypothesis>=6.110,<7",
    "mypy>=1.13,<2",
    "ruff>=0.6,<1",
]
```

`requirements.lock` (frozen for the .deb) generated via `uv pip compile pyproject.toml -o requirements.lock` against a python-build-standalone 3.12 interpreter on the build host.

---

## What NOT to use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Python 3.8 system interpreter on Jetson | PSF-EOL October 2024; pydantic dropped support v2.11 (March 2025); locks us out of every modern wheel-cycle improvement | Bundle CPython 3.12 via python-build-standalone in the .deb |
| deadsnakes PPA on Ubuntu 20.04 | Focal is unsupported by deadsnakes since April 2025 (after Ubuntu standard support ended) | python-build-standalone |
| Compile CPython from source on the Jetson | Build toolchain on a production box is a bad smell; build slow on Orin NX; reproducibility hard | python-build-standalone (pre-built, deterministic) |
| `requests` library for webhooks | Sync-only; calling from asyncio loop blocks the cycle (kills NFR-1's 10s budget under any network hiccup) | `httpx` async client |
| `aiohttp` for client-only webhook usage | Brings a server framework we don't need; bigger surface area | `httpx` |
| `subprocess.run` (sync) anywhere in the daemon | Blocks the asyncio loop. Even for "fast" calls like `ip netns exec`, a hung qmicli process can stall everything. | `asyncio.subprocess` exclusively (already in ARCH §4.3) |
| `urllib.request` for webhooks | Synchronous, no timeout-by-default, no retries, no HTTPS verification niceties | `httpx` |
| `black` alongside `ruff` | Two formatters fighting; needless dep | `ruff format` only |
| `pip-tools` / Poetry / Hatch / PDM for build | All work, but `uv` is faster and Astral-stable; aligns with the python-build-standalone choice | `uv` |
| Threads for QMI parallelism | NFR-4 says parallel; ARCH §4.3 says asyncio.gather. Threads add GIL+lock complexity. | `asyncio.gather` with per-task timeout |
| Generic `python-dbus` (the dbus-python C-extension) | Pulls glib; awkward in asyncio; legacy | `jeepney` if/when needed |
| `pkg_resources` for runtime introspection | Deprecated, slow at startup | `importlib.metadata` (stdlib) |
| Typed-dict-only state shapes (instead of pydantic models) | TypedDict gives no runtime validation; ADR-0004 mandates strict | pydantic v2 BaseModel |
| `dataclasses` for wire formats | No validation, no enum coercion; ADR-0004 explicitly chose pydantic | pydantic v2 BaseModel; dataclasses fine for purely-internal lightweight records |

---

## Stack patterns by variant

**If the decision flips to "drop to Python 3.8 system interpreter"** (NOT recommended):
- Pin `pydantic==2.10.6` (last 3.8-compatible release).
- Add `taskgroup`, `async-timeout`, `tomli`, `typing_extensions` deps.
- Rewrite all `match` statements as if/elif (RECOVERY_SPEC.md decision tables).
- Accept frozen dependency tree for the 5-year fleet life.
- Document this as an ADR superseding ADR-0001's "we ship the runtime we tested with".

**If the team revisits ADR-0001 and goes Go/Rust** (deferred per ADR-0001 "revisit when"):
- Out of scope for this milestone. Phase 6 of migration (decommission) is the natural revisit point.

**If wheel resolution ever fails on aarch64** for some new dep:
- First check piwheels (Raspberry Pi wheel repo; some aarch64 wheels there too).
- Then `uv pip install --no-binary <pkg>` and accept the build cost in the .deb pipeline (`build-essential` on the build host).
- Only as last resort: vendor the C extension into the .deb's site-packages.

---

## Version compatibility

| Package A | Compatible with | Notes |
|-----------|-----------------|-------|
| pydantic 2.13.x | pydantic-core matched (auto) | Don't pin pydantic-core directly; let pydantic resolve. |
| pydantic 2.13.x | Python 3.12 | Fully supported; aarch64-manylinux_2_17 wheels. |
| pyudev 0.24.4 | libudev ≥ 151 | Ubuntu 20.04 has libudev 245. Comfortable. |
| pyroute2 0.9.6 | Python 3.12 | OK. ≥0.9.5 supports 3.12 fully. |
| prometheus-client 0.25.0 | Python ≥3.9 | OK on 3.12. |
| asyncinotify 4.x | Python ≥3.10 | OK on 3.12; needs `asyncio.timeout` semantics. |
| httpx 0.27 | h11/h2/anyio (auto) | Pure-Python deps, no aarch64 issues. |
| python-build-standalone 3.12 (gnu) | glibc ≥ 2.17 | Ubuntu 20.04 has glibc 2.31. ≥1.5 minor versions of headroom. |
| sdnotify 0.3.2 | Python ≥3.6 | Trivial dep. |
| psutil 7.x | Python ≥3.6, aarch64 | Wheels exist. Don't compile. |

No known mutual-incompatibilities in this set.

---

## Specific requirement traceability

Each library choice above tied to a specific requirement, ADR, or constraint:

- **CPython 3.12 bundled**: ADR-0001 ("we ship the runtime we tested with"); FR-60 ("python3 ≥3.11"); C14 ("Python ≥ 3.11 available").
- **pydantic v2.13**: ADR-0004 (typed wire formats); FR-13, FR-32, FR-63, NFR-43 (validation, schema versioning).
- **PyYAML**: FR-54 (layered config); FR-33 (config-only carrier table edits).
- **prometheus-client**: NFR-21 (specific metric set); FR-42 (Unix socket scrape).
- **pyudev**: FR-1 (USB add/remove); ARCH §8.
- **pyroute2**: ARCH §8 (rtnetlink link-state); ADR-0002 (event-driven).
- **asyncinotify**: ARCH §8 (Zao-log inotify, kmsg rotation); ADR-0002.
- **httpx**: FR-44 (webhook POST); NFR-33 (HTTPS-only by default).
- **sdnotify**: FR-53 (`Type=notify`); NFR-13 (steady-state within 60s).
- **psutil**: NFR-3 (RSS ≤ 80 MiB tripwire).
- **mypy --strict + ruff**: NFR-40 (CI gates).
- **pytest + pytest-asyncio + hypothesis**: NFR-41 (hardware-free tests); TEST_STRATEGY §1, §5.

---

## Confidence per recommendation

| Recommendation | Confidence | Why |
|---------------|-----------|-----|
| Bundle CPython 3.12 via python-build-standalone | HIGH | All facts verified against PyPI, astral-sh release page, pydantic changelog, deadsnakes Launchpad page. Only sensible answer given the constraint matrix. |
| pydantic v2.13 | HIGH | PyPI confirmed; changelog confirmed Python 3.8 dropped at 2.11. |
| prometheus-client 0.25 | HIGH | PyPI confirmed; matches docs/ proposal. |
| pyudev 0.24.4 | HIGH | PyPI confirmed; libudev compat documented. |
| pyroute2 0.9.6 | HIGH | PyPI confirmed; Python ≥3.9 documented. |
| asyncinotify (over inotify_simple) | MEDIUM | Both work; preference is stylistic (asyncio-native). |
| httpx for webhooks | HIGH | Industry consensus for asyncio HTTP client; sync/async unified API. |
| Drop dh-virtualenv, roll our own debhelper rule | MEDIUM | The decision is sound; the recipe needs proving end-to-end in Phase 0. dh-virtualenv could still be made to work, but the integration with python-build-standalone is non-obvious. |
| uv as build-time installer | HIGH | Stable, fast, Astral-maintained, lockfile-clean. |
| sdnotify over systemd-python | MEDIUM | Both work; sdnotify is lighter and dep-free. |
| jeepney over dbus-next (if dbus is added later) | LOW | Both are viable; jeepney's recent activity edges it. **Deferred** to v2.1 anyway, so this can be re-decided then. |
| Drop black, use ruff format only | HIGH | Industry consensus 2025+; docs/ already hedges. |
| mypy in CI, pyright in editor | MEDIUM | Both are credible; mypy's stricter `Any` propagation matches our policy-engine purity story; pyright's speed helps day-to-day editing. Splitting is a known and accepted pattern. |

---

## Sources

**Primary (HIGH confidence)**:
- [pydantic on PyPI](https://pypi.org/project/pydantic/) — v2.13.3 latest, requires Python ≥3.9, fetched 2026-05-05.
- [pydantic v2.11 release](https://pydantic.dev/articles/pydantic-v2-11-release) — Python 3.8 drop confirmation.
- [prometheus-client on PyPI](https://pypi.org/project/prometheus-client/) — v0.25.0 latest, requires Python ≥3.9.
- [pyudev on PyPI](https://pypi.org/project/pyudev/) — v0.24.4 (Oct 2025), Python ≥3.9, libudev ≥151.
- [pyroute2 on PyPI](https://pypi.org/project/pyroute2/) — v0.9.6 (April 2026), Python ≥3.9 with 3.12+ support.
- [astral-sh/python-build-standalone](https://github.com/astral-sh/python-build-standalone) — stewardship since Dec 2024; aarch64-unknown-linux-gnu builds for 3.10–3.14; glibc 2.17 baseline.
- [python-build-standalone running.rst](https://github.com/astral-sh/python-build-standalone/blob/main/docs/running.rst) — glibc 2.17 minimum confirmed.
- [deadsnakes PPA](https://launchpad.net/~deadsnakes/+archive/ubuntu/ppa) — focal removed after EOL April 2025.
- [Ubuntu 20.04 LTS End of Standard Support](https://ubuntu.com/blog/ubuntu-20-04-lts-end-of-life-standard-support-is-coming-to-an-end-heres-how-to-prepare) — 31 May 2025 EOL.
- [Astral uv blog — python-build-standalone home](https://astral.sh/blog/python-build-standalone) — stewardship transfer Dec 2024.

**Secondary (MEDIUM confidence)**:
- [HTTPX vs Requests vs AIOHTTP guide 2026](https://decodo.com/blog/httpx-vs-requests-vs-aiohttp) — async support comparison.
- [pyright vs mypy 2026 comparison](https://www.danilchenko.dev/posts/ty-vs-mypy-vs-pyright/) — strictness defaults; speed.
- [Spotify dh-virtualenv repo](https://github.com/spotify/dh-virtualenv) — maintenance pulse signal.
- [taskgroup PyPI](https://pypi.org/project/taskgroup/) — 3.8 backport availability for `asyncio.TaskGroup`.
- [Ubuntu Pro / ESM extended support](https://ubuntu.com/security/esm) — focal package security through 2030/2032.

**Tertiary (LOW confidence — directional)**:
- [dbus-next PyPI](https://pypi.org/project/dbus-next/) and [Jeepney 0.9.0](https://jeepney.readthedocs.io/) — both work; activity pulses fluctuate.
- libqmi changelog on Launchpad — 1.30.4 in focal-updates confirmed; deeper version analysis deferred until needed.

---

*Stack research for: spark-modem-watchdog v2 (single-process root daemon, asyncio, aarch64 Linux)*
*Researched: 2026-05-05*

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