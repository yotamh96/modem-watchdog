# Phase 2: Core Daemon (laptop-testable) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or
> execution agents. Decisions are captured in `02-CONTEXT.md` — this log
> preserves the alternatives considered.

**Date:** 2026-05-06
**Phase:** 02-core-daemon-laptop-testable
**Areas discussed:** Replay harness & v1 agreement gate; CLI surface &
operability; Phase 2 module decomposition & build-order; Webhook +
observability emission semantics

---

## Replay harness & v1 agreement gate

### Q1 — Where do the ≥1000 v1 cycles come from?

| Option | Description | Selected |
|--------|-------------|----------|
| Synthesize from RECOVERY_SPEC + fault catalogue (Recommended) | Generate from RECOVERY_SPEC §4 + 15 PITFALLS scenarios + randomized fault generator. Hardware-free, deterministic, ships in tests/fixtures/replay/. | ✓ |
| Capture from production v1 boxes (one-shot tool) | Write a v1-side logger now; deploy to one or two field boxes for a week. Real v1 behavior; touches v1. | |
| Hybrid — synthesized for breadth + production capture for fidelity | Phase 2 SC #1 passes on synthesized; Phase 5 widens to real. | |
| v1 log post-processor | Parse whatever v1's bash leaves on disk and reconstruct (Diag, action) pairs. Lossy. | |

**User's choice:** Synthesize from RECOVERY_SPEC + fault catalogue.
**Notes:** Live-fleet capture is deferred to Phase 5 bench/field shadow.

### Q2 — How should "equal-or-safer" be encoded?

| Option | Description | Selected |
|--------|-------------|----------|
| Partial order on action cost + skip-as-safest (Recommended) | `no_action ≺ set_apn ≺ fix_raw_ip ≺ sim_power_on ≺ soft_reset ≺ modem_reset ≺ usb_reset ≺ driver_reset`. Per-cycle classification: agree / safer / less-safe / different-issue / both-skip. | ✓ |
| Strict equality + hand-curated allow-list of safer-substitutions | tests/fixtures/replay/safer_substitutions.yaml with explicit rows. | |
| Action-category equality (config/sim/datapath/registration/qmi) | Compare only the category, not the specific action. | |

**User's choice:** Partial order + skip-as-safest.

### Q3 — How does the compare tool run, and what does it output?

| Option | Description | Selected |
|--------|-------------|----------|
| pytest gate + JSON summary artifact (Recommended) | tests/replay/test_v1_agreement.py is the CI gate; emits artifacts/replay-summary.json. | ✓ |
| Standalone CLI: `spark-modem replay --diag-fixture-dir=...` | First-class subcommand. | |
| Hourly compare report (HTML) | docs/reports/replay-YYYY-MM-DD.html with per-scenario tables. | |

**User's choice:** pytest gate + JSON summary artifact.
**Notes:** Hourly HTML report is the Phase 5 tool (`tools/compare_v1_v2.py`),
not Phase 2.

### Q4 — How are the ≥1000 fixture cycles laid out on disk?

| Option | Description | Selected |
|--------|-------------|----------|
| One JSON file per cycle, grouped by scenario directory (Recommended) | tests/fixtures/replay/<scenario>/<NNN>.json. Mirrors tests/fixtures/diag/ layout. | ✓ |
| Single JSONL stream per scenario | tests/fixtures/replay/<scenario>.jsonl. | |
| Pytest parametrize from a YAML manifest | tests/fixtures/replay/manifest.yaml; cycles built in-memory. | |

**User's choice:** One JSON file per cycle.

---

## CLI surface & operability

### Q1 — When `ctl maintenance on --duration=2h` is active, what gets paused?

| Option | Description | Selected |
|--------|-------------|----------|
| Destructive actions only — cheap actions still run (Recommended) | Only modem_reset/usb_reset/driver_reset are gated. | ✓ |
| All actions (cheap + destructive) — daemon observes only | Full action pause; observation/status/metrics/webhooks continue. | |
| Full freeze — cycles paused entirely | Equivalent to systemctl stop. | |

**User's choice:** Destructive actions only.

### Q2 — Where is the active maintenance window stored, and what enforces auto-expiry?

| Option | Description | Selected |
|--------|-------------|----------|
| globals.json field with monotonic + wall expiry (Recommended) | Dual-clock; 8h max enforced at CLI; daemon restart preserves window. | ✓ |
| Marker file + separate flock | /run/spark-modem-watchdog/maintenance.lock with JSON body. | |
| In-memory only — expires on daemon restart | Simpler; risky during NOC work. | |

**User's choice:** globals.json + monotonic + wall expiry.

### Q3 — Where does `ctl history --modem=cdc-wdm0 --since=1h` read from?

| Option | Description | Selected |
|--------|-------------|----------|
| events.jsonl tail-read with structured filter (Recommended) | Single source of truth; reads current + rotated siblings. | ✓ |
| Separate transitions.jsonl alongside events.jsonl | Faster queries; doubles writer surface. | |
| Derive from state-store action history ring buffer | Bounded; couples ctl history to state-store schema. | |

**User's choice:** events.jsonl tail-read.

### Q4 — What does `ctl support-bundle` produce, and what's the redaction policy?

| Option | Description | Selected |
|--------|-------------|----------|
| Tarball with redacted PII; secrets never copied (Recommended) | ICCID/IMSI hashed; HMAC secret never copied; webhook URL host-only. Mode 0640 root:adm. | ✓ |
| Tarball with full PII, locked to root only | Same contents, no redaction; mode 0600 root:root. | |
| Keep it minimal — just events + status + state, no journal/dmesg | Smaller bundle. | |

**User's choice:** Redacted tarball.

---

## Phase 2 module decomposition & build-order

### Q1 — What does Phase 2 use to know what modems exist?

| Option | Description | Selected |
|--------|-------------|----------|
| Sysfs one-shot scan + fixture override behind a Protocol (Recommended) | InventorySource Protocol; SysfsInventory for production, FixtureInventory for tests. Phase 3 swaps in UdevInventory behind the same Protocol. | ✓ |
| Fixture-only — no real sysfs in Phase 2 | Pushes ARCH §6 decisions into Phase 3. | |
| Real sysfs only — no fixture override | Forces test monkey-patching. | |

**User's choice:** Sysfs + fixture behind Protocol.

### Q2 — How does the cycle wake up in Phase 2?

| Option | Description | Selected |
|--------|-------------|----------|
| Pure 30 s monotonic polling timer + event-queue stub (Recommended) | `await asyncio.wait({sleep_until(...), event_queue.get()}, FIRST_COMPLETED)`. Phase 2 ships only the sleep arm; Phase 3 wires producers. | ✓ |
| Pure 30 s timer, no event queue at all | Phase 3 retrofits the queue; ripples through tests. | |
| Configurable cadence with --cycle-period flag | 30s default, replay runs at 0s. Adds a config knob. | |

**User's choice:** 30s timer + event-queue stub.

### Q3 — How fine should we slice Phase 2 plans?

| Option | Description | Selected |
|--------|-------------|----------|
| 8–10 plans aligned to module boundaries (Recommended) | One plan per major module so each PR is reviewable on its own. | ✓ |
| 5–6 chunkier plans by build-layer | Faster waves; each plan touches more files. | |
| 12+ tightly-scoped plans | Smaller blast radius; more sequencing ceremony. | |

**User's choice:** 8–10 plans by module boundary.

### Q4 — How should the cheap-actions module be structured?

| Option | Description | Selected |
|--------|-------------|----------|
| One file per action under actions/, with a shared dispatcher (Recommended) | actions/{set_apn.py, ...}, each `async def execute(...) -> ActionResult`. Dispatcher in __init__.py. Per-action CLI runnability per FR-25. | ✓ |
| Grouped by category in actions/{config,sim,datapath,registration,qmi}.py | Mirrors policy categories. | |
| Single actions.py with all functions | Smallest footprint; loses test isolation. | |

**User's choice:** One file per action + dispatcher.

---

## Webhook + observability emission semantics

### Q1 — Where does the webhook retry queue live, and what survives a daemon restart?

| Option | Description | Selected |
|--------|-------------|----------|
| In-memory ring buffer + pre-exit best-effort flush (Recommended) | Bounded asyncio.Queue (100 items); 3 attempts with exp backoff (1s/4s/16s); 3 s pre-exit drain. Crash loses queue; events.jsonl `webhook_pending` enables post-mortem. | ✓ |
| Disk-backed durable queue (replay on startup) | Stronger durability; doubles writer surface; needs explicit `redelivery: true` flag. | |
| events.jsonl-derived replay on startup | Use events.jsonl webhook_pending markers as source of truth. | |

**User's choice:** In-memory ring buffer.

### Q2 — How is webhook URL DNS resolved?

| Option | Description | Selected |
|--------|-------------|----------|
| Pre-resolved at config-load + 60 s refresh + on resolve failure go-stale (Recommended) | `loop.getaddrinfo` cache + Host-header trick + 600 s stale ceiling + go-no_dns thereafter. | ✓ |
| Resolve per-request with explicit asyncio timeout | Each request resolves with 2 s timeout. PITFALLS §10.1 calls this risky on LTE-tunneled DNS. | |
| Pre-resolved at config-load only — no refresh | Resolve once at startup; webhook breaks silently if upstream IP rolls. | |

**User's choice:** Pre-resolve + 60s refresh + go-stale.

### Q3 — How often is status.json written to disk?

| Option | Description | Selected |
|--------|-------------|----------|
| Every cycle, atomic write (Recommended) | Predictable freshness; carries `last_modified` + `cycle_index`. | ✓ |
| On-change-only with periodic refresh every 30 s | Lower I/O; harder for NOC consumers. | |
| Every cycle, but write to status.json.next and rename only on change | Hybrid; complex. | |

**User's choice:** Every cycle, atomic.

### Q4 — How are state_duration_seconds buckets selected, and how is cycle_drift_seconds derived?

| Option | Description | Selected |
|--------|-------------|----------|
| Buckets [1, 5, 15, 60, 300, 1800, 7200, 86400]; drift = now_monotonic - expected_next_cycle_monotonic (Recommended) | MTTR-targeted bucket sizing; drift recorded at wake-up boundary. | ✓ |
| Use prometheus_client default buckets, drift as gauge of last cycle's wallclock duration | Default buckets are exponential 0.005..10 — wrong shape. | |
| Custom buckets, but defer cycle_drift to Phase 3 | Drift is most meaningful with real event sources. | |

**User's choice:** Custom MTTR buckets + drift at wake-up boundary.

---

## Claude's Discretion

The user accepted the recommended option in every question across all four
selected areas. The following implementation surfaces are explicitly
delegated to Claude during planning:

- `--explain` output: text default, `--json` flag for structured.
- Plan ordering / wave parallelization within the 8–10 plans.
- Test seam Protocol locations (co-located; fakes in `tests/fakes/`).
- qmicli per-libqmi fixture layout
  (`tests/fixtures/qmicli/<intent>/<libqmi-version>/<scenario>.txt`).
- `cycle_duration_seconds` buckets `[0.5, 1, 2, 4, 8, 16, 32]`.
- psutil RSS tripwire is event-only in Phase 2; sd_notify watchdog
  graceful-exit lands Phase 3.
- `maintenance.lock` reuses the existing state-store flock (no new lock
  surface).

## Deferred Ideas

- Capture-from-production v1 logger — defer to Phase 5 (widens the
  synthesized gate to real-fleet captures).
- `tools/compare_v1_v2.py` hourly HTML report — Phase 5 tool.
- Phase 3: pyudev/rtnetlink/inotify/dmesg, sd_notify, signal handlers,
  PID lock, flock callers.
- Phase 4: destructive actions + HIL lane.
- v2.1: HTTP API on UDS, webhook batching, ctl identity export/import,
  ctl schema events, ctl simulate-issue, 5G NR-aware policy.
