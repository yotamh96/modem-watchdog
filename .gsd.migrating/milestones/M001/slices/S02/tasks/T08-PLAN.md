# T08: 02-core-daemon-laptop-testable 08

**Slice:** S02 — **Milestone:** M001

## Description

Plan 02-08 lands the webhook subsystem: HMAC-signed POSTs to a configured
URL on Healthy→Degraded and Recovering→Exhausted transitions, plus
DaemonRestart and ActionFailed variants.

The poster runs in a SEPARATE asyncio task so the cycle never blocks on
webhook I/O (FR-44.8). DNS is pre-resolved at config-load + refreshed every
60s with a 600s "go-stale" fallback before marking webhooks `skipped_no_dns`.
TLS uses the Host-header trick: URL string contains the cached IP, but the
`Host:` header carries the original hostname so TLS SNI verifies correctly.

Output: `webhook/` package + parametrized tests using `pytest-httpx` (or a
small custom transport mock if pytest-httpx is not in the dev deps) +
property tests for the dedup table + a Linux/Windows-portable DNS test
that exercises `loop.getaddrinfo` against a known-static name (`localhost`).

## Must-Haves

- [ ] "WebhookPoster signs raw body bytes (not the parsed dict): hmac.new(secret, body, sha256).hexdigest() — FR-44.1 carry-forward."
- [ ] "Every POST carries X-Spark-Signature: sha256=<hex> AND X-Spark-Timestamp: <unix> headers — FR-44.2 carry-forward."
- [ ] "DNS pre-resolved at config-load + 60s refresh + 600s stale-window before falling back to skipped_no_dns (W-02)."
- [ ] "httpx Host-header trick: URL uses cached IP, Host header carries original hostname so TLS SNI is server-correct."
- [ ] "In-memory bounded asyncio.Queue (default 100); 3 attempts with backoff [1s, 4s, 16s]; exhaustion → webhook_dropped event + counter (W-01, FR-44.3)."
- [ ] "Per-(modem, transition) dedup window 60s default (config.webhook_dedup_seconds); coalesced webhook carries dedup_count > 0 (FR-44.4)."
- [ ] "DaemonRestart payload variant emitted on restart with reason enum (FR-44.5); ActionFailedWebhook variant for failed actions (FR-44.6)."
- [ ] "Pre-exit best-effort drain bounded at 3s (W-01); items not delivered are written as webhook_dropped events (post-mortem reconstructable)."
- [ ] "Webhook task NEVER blocks the cycle: separate asyncio task with explicit httpx timeouts + non-blocking DNS resolve via loop.getaddrinfo in default executor (FR-44.8)."

## Files

- `src/spark_modem/webhook/__init__.py`
- `src/spark_modem/webhook/dns.py`
- `src/spark_modem/webhook/sign.py`
- `src/spark_modem/webhook/dedup.py`
- `src/spark_modem/webhook/poster.py`
- `src/spark_modem/wire/events.py`
- `tests/unit/webhook/__init__.py`
- `tests/unit/webhook/test_dns.py`
- `tests/unit/webhook/test_sign.py`
- `tests/unit/webhook/test_dedup.py`
- `tests/unit/webhook/test_poster.py`
- `tests/unit/webhook/test_drain.py`
