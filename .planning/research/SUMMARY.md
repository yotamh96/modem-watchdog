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
