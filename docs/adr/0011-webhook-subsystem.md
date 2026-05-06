# ADR-0011 — Webhook subsystem: HMAC-SHA256 v2.0 + retry/dedup + pre-resolved DNS

| Field        | Value          |
| ------------ | -------------- |
| Status       | Accepted       |
| Date         | 2026-05-06     |
| Deciders     | Eng team       |
| Closes       | Q5 (HMAC v2.0); Q1, Q2, Q4 (notes) |

## Context

The PRD (§ Q5) originally deferred HMAC-SHA256 webhook payload signing
to v2.1, treating it as a "nice to have." Research
(`.planning/research/FEATURES.md` §4.3) reversed this:

- Receivers increasingly require signatures to accept webhook payloads;
  unsigned webhooks are rejected by modern security postures.
- The cost is ~30 LOC + one config field (`webhook_hmac_secret` loaded
  from systemd `LoadCredential=`). The incremental effort is negligible.
- Signed-by-default is strictly more compatible with future receivers
  than unsigned; there is no benefit to deferring.

A second concern (`.planning/research/PITFALLS.md` §10.1) is DNS
resolution. The webhook delivery path runs in the same event loop as
the cycle driver. If the webhook URL's hostname resolves slowly or
fails (a real risk on LTE-tunneled or degraded-uplink deployments),
DNS resolution can block the event loop for the system-configured
resolver timeout (typically 5 s). This is unacceptable when P99 cycle
duration must be ≤10 s (NFR-1).

The webhook subsystem is a single concern with ~7 independent
prescriptions converging. Documenting them together in one ADR makes
the design intent legible.

**Closes Q5** (PROJECT.md: HMAC v2.0 vs v2.1): HMAC is promoted to
v2.0.

Also closes (as notes):
- **Q1** (HTTP API on Unix socket vs CLI-only): CLI-only for v2.0.
- **Q2** (qmi-proxy ownership): Zao owns; noted in this ADR.
- **Q4** (v1 `--watch` mode parity): replaced; noted in this ADR.

## Decision

The v2.0 webhook subsystem implements the following nine features:

### 1. HMAC-SHA256 signing (FR-44.1)

Header: `X-Spark-Signature: sha256=<hex>`.

Signed over the **raw body bytes** — not the JSON-decoded structure.
This avoids whitespace ambiguity on the receiver (a receiver that
re-serializes the decoded JSON may produce a different byte sequence).
The receiver verifies by computing `HMAC-SHA256(secret, body_bytes)`
and comparing the hex to the header value (constant-time compare).

The HMAC secret is loaded via systemd `LoadCredential=webhook_hmac_secret`
(NFR-34). It is never on disk as a plaintext file; never in environment
variables in the systemd unit file; never in the `.deb` package.
If the credential is not present at startup, the daemon starts but
webhook delivery is disabled (log warning on first attempted delivery).

### 2. Replay-protection timestamp (FR-44.2; M-4)

Header: `X-Spark-Timestamp: <unix_seconds>`.

Every request carries the current Unix timestamp. Receivers reject
requests older than ±5 minutes (the recommended window; operators may
tighten). This prevents replay of a captured signed request.

### 3. Retry queue with bounded budget (FR-44.3; M-1)

3 delivery attempts per payload with exponential backoff:
attempt 1 immediately, attempt 2 after 5 s, attempt 3 after 25 s.
After the third failure, the payload is dropped and a
`webhook_delivery_failed` event is emitted (count + last error).

The in-memory queue depth is bounded at 100 payloads. If the queue
fills (e.g. the receiver is down for an extended period), new payloads
are dropped with a `webhook_queue_overflow` event.

### 4. Per-(modem, transition) dedup (FR-44.4; M-2)

Default 60 s coalescing window. If the same `(usb_path, prior_state,
new_state)` transition fires multiple times within 60 s (e.g. a
flapping modem), a single payload is emitted for the window with
`dedup_count: int` indicating how many transitions were coalesced.

The dedup window starts on the FIRST occurrence; the LAST occurrence's
timestamp is reported. `dedup_count=1` means no deduplication occurred
(a single transition in the window).

### 5. Daemon-restart event (FR-44.5; M-6)

On SIGTERM (graceful shutdown), the daemon emits a
`daemon_stopping` webhook event with `reason: Literal['sigterm',
'crash', 'config_invalid', 'oom', 'kill']`. Best-effort: the
pre-exit send has a 2 s deadline. SIGKILL cannot be caught; no event.

### 6. action_failed variant (FR-44.6; M-15)

When a recovery action fails (non-zero exit, timeout, or qmicli
error), the daemon emits an `action_failed` webhook event with:
- `usb_path`
- `action: ActionKind`
- `failure_reason: str` (structured; not a raw stderr dump)
- `recovering_level: int | None`

### 7. Pre-exit best-effort send (FR-44.7; M-25)

On `SchemaVersionTooNew` refusal (daemon exits non-zero because a
state file has a schema version newer than the daemon supports), the
daemon emits a `schema_too_new` webhook event before exiting. Best-
effort; 2 s deadline. This gives the NOC visibility into a failed
upgrade rollback.

### 8. Pre-resolved cached DNS (FR-44.8; PITFALLS §10.1)

At config-load time, the daemon resolves the webhook URL's hostname
via `asyncio.get_event_loop().getaddrinfo()` (which delegates to the
system resolver without blocking the event loop). The result is cached
for 60 s. Webhook delivery uses the cached IP address directly via
`httpx` with `http2=False` and explicit `timeout=httpx.Timeout(10.0)`.

A cache miss (60 s elapsed or first call) triggers a background
re-resolve. The previous cached address is used for any delivery
that arrives during the re-resolve window.

### 9. Separate delivery task (FR-44.8)

Webhook delivery runs in a separate `asyncio.Task` spawned by the
cycle driver. The cycle driver never awaits delivery; it enqueues the
payload into the bounded queue and continues. Delivery timeout is
never on the critical path of a cycle.

`httpx.AsyncClient` with explicit timeouts; `urllib.request` is
forbidden (CLAUDE.md anti-pattern; synchronous; blocks the event loop).

## Wire shape (Phase 1)

Phase 1 (this plan) ships the wire shapes:
- `spark_modem.wire.webhook.WebhookEnvelope` — outer signed envelope
  with `X-Spark-Signature`, `X-Spark-Timestamp`, payload bytes.
- `spark_modem.wire.webhook.WebhookPayload` — discriminated union of
  all event variants (`state_transition`, `action_failed`,
  `daemon_stopping`, `schema_too_new`).
- `spark_modem.wire.webhook.WebhookEventKind` — enum of all variants.

Phase 2 ships the `WebhookPoster` Protocol + concrete implementation.

## Q-closures documented here

**Q1 closure** — HTTP API on Unix socket vs CLI-only ctl:
**CLI-only for v2.0; deferred to v2.1.** The daemon accepts no inbound
IPC in v2.0 (CLAUDE.md invariant #11). This preserves the minimal-
attack-surface principle and is sufficient for all v2.0 operational
use cases. v2.1 may add an HTTP API over a Unix socket if field
experience shows a need (CTL-01, CTL-02 in REQUIREMENTS.md deferred
section).

**Q2 closure** — Daemon owns `qmi-proxy` or assumes Zao does:
**Zao owns; the daemon assumes `qmi-proxy` is running.** The daemon
refuses to start if `qmicli` fails a connectivity check at startup
(FR-74). It does NOT start or stop `qmi-proxy`. A `qmi_proxy_down`
webhook event is emitted when `qmicli` fails with a proxy error, giving
the NOC visibility without the daemon trying to manage Zao's component.
Full rationale in ADR-0003 amendment.

**Q4 closure** — Feature parity with v1 `--watch` mode:
**Replace with `journalctl -fu spark-modem-watchdog` + Prometheus +
`spark-modem ctl history` (M-9).** The v1 `--watch` mode polled
`status.json` and printed diffs to stdout. v2 provides richer
alternatives: structured `events.jsonl` (replayable), Prometheus
scrape endpoint, and `ctl history` (planned Phase 2). No separate
ADR required; the deferral is operational.

## Consequences

- HMAC adds ~30 LOC + a `webhook_hmac_secret` LoadCredential config.
  Receivers that do not verify the signature are unaffected.

- Webhook URL must be `https://` unless `webhook_allow_http=true`
  (NFR-33). The Settings field validator (Plan 06) enforces this at
  config-load time; the daemon refuses to start with an `http://` URL
  unless the override is explicitly set.

- The dedup window is per-(modem, transition) in-memory. A daemon
  restart resets all dedup windows. Coalesced events from before the
  restart are not re-emitted.

- The bounded queue (100 payloads) drops oldest payloads when full.
  The `webhook_queue_overflow` metric (ADR-0013) tracks drops.

## Risks and mitigations

| Risk | Mitigation |
| ---- | ---------- |
| HMAC secret rotation | Operator updates the `LoadCredential=` source file and sends SIGHUP. Phase 3 wires the SIGHUP reload to re-read credentials. Until Phase 3, a daemon restart is required. |
| DNS cache stale during a long-running DNS migration | 60 s TTL is short enough that a DNS cutover is visible within two cache cycles. Restart clears the cache immediately. |
| Receiver clock skew on `X-Spark-Timestamp` | ±5 min window is loose enough for any realistic NTP-synced deployment. Document for receivers: boxes may have ≤60 s NTP drift. |
| Dedup window misuse: a flapping modem's legitimate distinct transitions are coalesced | `dedup_count: int` on the emitted payload exposes the count. The NOC alert threshold should be set on `dedup_count > 1` as a secondary signal. |
| httpx connection pool exhausted under sustained delivery failure | The retry budget (3 attempts) bounds the in-flight connections per payload; the bounded queue bounds total enqueued payloads. Worst case: 3 × 100 = 300 attempts, all within the delivery task, not the cycle. |

## Implementation reference

- `src/spark_modem/wire/webhook.py` — wire shapes (`WebhookEnvelope`,
  `WebhookPayload`, `WebhookEventKind`) — Plan 03, Wave 4.
- `src/spark_modem/config/settings.py` — `webhook_url`,
  `webhook_hmac_secret`, `webhook_allow_http`, `webhook_dedup_window_s`
  fields — Plan 06.
- Phase 2 — `WebhookPoster` Protocol + concrete `HttpxWebhookPoster`
  implementation + retry queue + DNS cache.
- Phase 3 — SIGHUP reload wiring for `webhook_hmac_secret`.

## Revisit when

- Receivers need batching (WHK-01 in REQUIREMENTS.md deferred section).
  Batching is a v2.1 feature; it does not change the signing or retry
  model.
- Receivers want a different signature algorithm (e.g. Ed25519 over
  HMAC-SHA256). The `X-Spark-Signature` header format can accommodate
  a prefix change (`ed25519=<hex>` vs `sha256=<hex>`).
- A fleet-API endpoint replaces per-box webhooks. This ADR covers the
  per-box outbound push; a pull-based fleet API is a separate ADR.
- The ±5 min replay window causes operational problems (e.g. a box
  with severe NTP drift consistently fails the receiver's replay
  check). Then widen the window or add a per-box NTP health check.
