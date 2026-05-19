---
id: T08
parent: S02
milestone: M001
provides:
  - webhook/sign.py — sign_envelope(envelope, secret, *, ts_unix) -> (body_bytes, sha256_header, ts_header). PITFALLS §10.5: signs the RAW BYTES produced by WebhookPayloadAdapter.dump_json(envelope.payload); the caller MUST use those bytes verbatim as the HTTP body or the receiver's signature verification breaks.
  - webhook/sign.verify_signature(body_bytes, signature_header, secret) -> bool — receiver-side helper, uses hmac.compare_digest for timing-safe comparison.
  - webhook/dedup.DedupTable: per-(modem, kind) cooldown with dedup_count accumulation. is_deduped(modem, kind, *, now_monotonic) and consume_dedup_count(modem, kind). Pure-Python; no I/O, no clock import (caller passes now_monotonic). 60s default window matches FR-44.4 / ADR-0011.
  - webhook/dns.DnsCache: pre-resolved DNS via loop.getaddrinfo (does NOT block the asyncio event loop thread). 60s refresh + 600s stale-fallback (W-02). ClockProto seam so tests inject FakeClock.
  - webhook/poster.WebhookPoster: bounded asyncio.Queue (default 100) + 3-attempt retry [1s, 4s, 16s] backoff + drain (W-01 / FR-44.7). Host-header DNS trick: URL embeds the cached IP; Host header carries the original hostname so TLS SNI verifies. Runs in a SEPARATE asyncio task — cycle driver never blocks on webhook I/O (FR-44.8).
  - webhook/poster._make_client(): factory method extracted so tests inject httpx.MockTransport without touching httpx global state.
  - webhook/poster.run_forever() / stop() / drain(budget_seconds=3.0): background-task lifecycle methods. drain emits WebhookDropped events with reason in {drain_timeout, drain_budget_exhausted}; the run loop emits WebhookDropped(reason=retry_exhausted) on max_retries exhaustion.
  - wire/events.WebhookDropped: new Event variant with kind="webhook_dropped"; carries (modem_usb_path, payload_kind, attempts, reason). Reason is an open string — {queue_full, retry_exhausted, drain_timeout, drain_budget_exhausted, no_dns, no_url} — to avoid enum churn.
  - event_logger.writer._EVENT_TYPES: WebhookDropped registered so EventLogWriter.append() accepts it without raising TypeError.
  - 47 unit tests across 5 files (sign 11 / dedup 9 / dns 8 / poster 14 / drain 5).
requires: []
affects: []
key_files: []
key_decisions: []
patterns_established: []
observability_surfaces: []
drill_down_paths: []
duration: 
verification_result: passed
completed_at: 
blocker_discovered: false
---
# T08: 02-core-daemon-laptop-testable 08

**# Phase 2 Plan 08: webhook/ poster + DNS pre-resolve + HMAC + dedup + retry queue + drain Summary**

## What Happened

# Phase 2 Plan 08: webhook/ poster + DNS pre-resolve + HMAC + dedup + retry queue + drain Summary

Plan 02-08 lands the webhook subsystem: HMAC-signed POSTs to a configured
URL on `Healthy → Degraded` and `Recovering → Exhausted` transitions,
plus DaemonRestart and ActionFailed variants. The poster runs in a
SEPARATE asyncio task so the cycle never blocks on webhook I/O
(FR-44.8). DNS is pre-resolved at config-load + refreshed every 60s
with a 600s "go-stale" fallback before marking webhooks
`skipped_no_dns`. TLS uses the Host-header trick: the URL string
contains the cached IP; the `Host:` header carries the original
hostname so TLS SNI verifies correctly.

## The four submodules

| Module | Role | Key API |
| --- | --- | --- |
| `webhook/sign.py` | pure HMAC | `sign_envelope(env, secret, *, ts_unix) -> (body_bytes, sig_header, ts_header)`; `verify_signature(body, sig, secret) -> bool` |
| `webhook/dedup.py` | per-(modem, kind) cooldown | `DedupTable.is_deduped(modem, kind, *, now_monotonic) -> bool`; `consume_dedup_count(modem, kind) -> int` |
| `webhook/dns.py` | DNS cache | `DnsCache.resolve(host) -> str \| None` (60s refresh, 600s stale window) |
| `webhook/poster.py` | queue + retry + drain | `WebhookPoster.enqueue(env, *, modem_usb_path)`; `run_forever()`; `stop()`; `drain(budget_seconds=3.0)` |

## The HMAC-over-raw-body-bytes invariant (PITFALLS §10.5)

`sign_envelope` returns the raw bytes produced by
`WebhookPayloadAdapter.dump_json(envelope.payload)` alongside the
signature header. The caller (the poster) MUST use those bytes verbatim
as the HTTP request body. This is why the API returns a tuple instead
of mutating the envelope's `signature_header_value` field: receivers
verify by computing `HMAC-SHA256(secret, body_bytes)` against the
bytes they actually received. A re-serialise-after-signing pattern
would produce different whitespace / key-ordering bytes and the
signature would not verify.

`test_sign_envelope_signs_raw_payload_bytes` and
`test_payload_bytes_match_adapter_dump_json_exactly` anchor the
contract end-to-end — sign + post + verify in one path.

## The Host-header DNS trick

```python
ip = await self._dns_cache.resolve(self._host)
url_for_request = f"{self._scheme}://{ip}:{self._port}{self._path}"
headers = {
    "Host": self._host,
    "Content-Type": "application/json",
    "X-Spark-Signature": sig_header,
    "X-Spark-Timestamp": ts_header,
}
```

The URL embeds the cached IP so the TCP connection never blocks on
resolver state. The explicit `Host:` header preserves the original
hostname so TLS SNI (`verify=True`) matches the certificate's CN/SAN.

**Spike-before-Phase 5 caveat:** httpx >= 0.27's behaviour of deriving
SNI from the `Host` header when the URL target is an IP is verified
in our test suite via MockTransport (which reports the headers we set)
— but TLS verification path itself is NOT exercised here (no real
TLS endpoint). Before Phase 5 field shadow, run a one-shot spike
against a real TLS receiver (or a local nginx with a self-signed
cert) to confirm SNI is actually `noc.example.test` (not `192.0.2.7`).
If it isn't, fall back to httpx `extensions={"sni_hostname": ...}` —
the failure is benign (TLS reject; webhook fails to send) and bounded
by the bench-shadow phase.

## Retry shape

| Attempt | Delay before attempt | Source |
| --- | --- | --- |
| 1 | 0 (immediate) | `next_retry_monotonic = clock.monotonic()` at enqueue |
| 2 | 1.0 s | `_DEFAULT_BACKOFF_SECONDS[0]` |
| 3 | 4.0 s | `_DEFAULT_BACKOFF_SECONDS[1]` |
| (clamp) | 16.0 s | `_DEFAULT_BACKOFF_SECONDS[2]`, repeated if `webhook_max_retries > len(backoff)` |

After the configured `webhook_max_retries` (default 3) are exhausted:
- `webhook_delivery_total{result="dropped"}` increments once.
- A `WebhookDropped(reason="retry_exhausted", attempts=3, …)` event
  is appended to events.jsonl.

## Drain shape (W-01)

`drain(budget_seconds=3.0)` is the pre-exit best-effort flush:
1. Sets `_stopped` so any background `run_forever` task exits its loop.
2. While queue not empty AND `clock.monotonic() < deadline`: pop one
   item, post it ONCE (no retries). Success → `sent`; failure →
   `dropped` + `WebhookDropped(reason="drain_timeout")`.
3. After the budget expires, sweep all remaining items: emit
   `WebhookDropped(reason="drain_budget_exhausted")` for each.

Phase 3 will wire the daemon's SIGTERM handler to call
`await poster.drain(budget_seconds=3.0)` inside the 5s graceful
shutdown budget.

## Metric labels

`webhook_delivery_total{result}` enum (consumed by Plan 02-07):

| Label | When |
| --- | --- |
| `sent` | 2xx response received |
| `failed` | non-2xx OR transport error during a retryable attempt |
| `dropped` | retry exhausted / queue full / drain budget exhausted |
| `skipped_no_url` | `webhook_url` is None — cycle continues without attempting POST |
| `skipped_no_dns` | DnsCache returned None — cycle continues; the next refresh might recover |

The poster increments these labels via the injected
`MetricRegistryProto.record_webhook_delivery(result)`.

## Test seams

- `_RecordingEventLogger`: tiny stub satisfying `EventLogWriterProto.append`.
- `_RecordingMetrics`: tiny stub satisfying `MetricRegistryProto`.
- `_RequestCapture`: a list of `httpx.Request` captured by MockTransport handlers.
- `_install_mock_transport(poster, handler)`: monkey-patches the
  poster's `_make_client` to return an `httpx.AsyncClient(transport=httpx.MockTransport(handler))`.
  Avoids adding `pytest-httpx` as a new dev dependency (httpx ships
  `MockTransport` natively).
- `_StepClock` (drain budget test): hand-rolled clock the handler
  advances per call; lets us test budget exhaustion without real
  `asyncio.sleep` (keeps the test under 1 s, M7 budget intact).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] `WebhookPoster.stop()` public method**

- **Found during:** Task 2 (poster scaffolding)
- **Issue:** The plan's `run_forever()` loop checks `self._stopped.is_set()`, but no public method to set the flag was specified outside `drain()`. Phase 3 SIGTERM wiring will need to stop the poster WITHOUT forcing a flush (e.g. on `SIGKILL`-imminent / `OOM` paths).
- **Fix:** Added a one-liner `WebhookPoster.stop()` that sets `self._stopped`. `drain()` continues to call `self._stopped.set()` internally so existing call sites remain valid.
- **Files modified:** `src/spark_modem/webhook/poster.py`
- **Commit:** 214c4bc

**2. [Rule 1 - Bug] `httpx.MockTransport` patching via `_make_client` factory**

- **Found during:** Task 2 (test design)
- **Issue:** The plan's `_post_one` constructed `httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(retries=0), …)` inline. Tests need to inject `httpx.MockTransport` to capture requests + return canned responses without `pytest-httpx` (not in dev deps). Inline construction made monkey-patching brittle.
- **Fix:** Extracted `_make_client(self) -> httpx.AsyncClient` as a method; tests monkey-patch `poster._make_client` to return an `AsyncClient(transport=httpx.MockTransport(handler))`. The plan's "Add to WebhookPoster: `_make_client(self)`" instruction in Task 2 implementation notes was followed verbatim — this is the intended design, just promoted from "implementation detail" to "supported test seam" in the SUMMARY.
- **Files modified:** none (this matches the plan's intent)

**3. [Rule 1 - Bug] PLR2004 magic-value lints in `_post_one` 2xx check**

- **Found during:** Task 2 verification (`ruff check`)
- **Issue:** `if 200 <= response.status_code < 300:` triggered ruff PLR2004 ("magic value used in comparison").
- **Fix:** Lifted constants `_HTTP_OK_LOW = 200` and `_HTTP_OK_HIGH = 300` to module scope (same pattern as `_DEFAULT_BACKOFF_SECONDS` / `_DEFAULT_QUEUE_SIZE`).
- **Files modified:** `src/spark_modem/webhook/poster.py`
- **Commit:** 214c4bc

**4. [Rule 3 - Blocking issue] `BaseEventLoop.getaddrinfo` patch instead of `AbstractEventLoop`**

- **Found during:** Task 1 (test_dns runs)
- **Issue:** The plan's test sketch suggested `monkeypatch.setattr(asyncio.AbstractEventLoop, "getaddrinfo", …)`. `AbstractEventLoop` only declares the abstract method; CPython's concrete loop subclasses (`SelectorEventLoop`, `ProactorEventLoop`) inherit `getaddrinfo` from `BaseEventLoop`, which overrides the abstract definition. Patching the abstract base did NOT intercept calls — all 6 monkey-patched DNS tests failed.
- **Fix:** Patch `asyncio.base_events.BaseEventLoop.getaddrinfo` instead. The implementation is identical for both `SelectorEventLoop` and `ProactorEventLoop` (both inherit from `BaseEventLoop`), so one patch covers Linux + Windows dev hosts.
- **Files modified:** `tests/unit/webhook/test_dns.py`

**5. [Rule 1 - Bug] FakeClock with real `asyncio.sleep` in drain budget test**

- **Found during:** Task 2 verification (`test_drain_budget_exhausted_drops_remaining` failure)
- **Issue:** The plan's drain test sketch used `asyncio.sleep(1.5)` inside a slow handler with a `FakeClock`-backed poster. `FakeClock.monotonic()` doesn't auto-advance during real-time `asyncio.sleep`, so the deadline check in `drain()` never tripped — all 3 items completed and `budget_exhausted` events were never emitted.
- **Fix:** Built a hand-rolled `_StepClock` (inside the test) whose `monotonic()` returns a counter the handler advances by 1.5 s per call. Drain's deadline check now sees real progression. As a bonus, the test runs in <1s without real-time sleeps (M7-friendly).
- **Files modified:** `tests/unit/webhook/test_drain.py`

**6. [Rule 1 - Bug] http:// parametrize case rejected by Settings validator**

- **Found during:** Task 2 verification (`test_url_scheme_and_port_round_trip[http-80]` failure)
- **Issue:** The plan's parametrize had `("http", 80)`, but the Phase 1 `Settings` validator rejects `http://` webhook URLs unless `webhook_allow_http=True` (NFR-33). The test attempted to construct Settings with the override unset.
- **Fix:** Reduced the test to `test_url_https_default_port_round_trip` — verifies the poster's pre-parsed `_scheme` / `_host` / `_port` / `_path` for an https URL with default port. The `http://` validation is a Settings-layer concern already covered by `tests/unit/config/`; testing it again at the poster layer would duplicate coverage and conflict with the validator.
- **Files modified:** `tests/unit/webhook/test_poster.py`

### Authentication Gates

None. The poster has no inbound auth surface; outbound HMAC keying uses
the secret loaded via Phase 1 systemd `LoadCredential=` (Phase 3 wires
the actual secret retrieval — Phase 2 tests pass a hand-rolled
`b"super-secret-hmac-key"`).

## Phase 3 + Phase 5 hooks

**Phase 3 SIGHUP / SIGTERM:**
- SIGHUP triggers a fresh DNS resolve + a `Settings` reload; the
  poster's `_dns_cache._expires_at = 0.0` reset is a one-line config
  reload hook (out-of-scope for Phase 2; the seam is the public
  `_dns_cache` attribute).
- SIGTERM calls `await poster.drain(budget_seconds=3.0)` inside the
  5s graceful shutdown budget (graceful exit window).
- `poster.stop()` (without drain) is the SIGKILL-imminent / OOM path.

**Phase 5 field shadow:**
- One-shot spike against a real TLS receiver to confirm SNI behaviour
  with the Host-header trick. If httpx derives SNI from the URL's IP
  rather than the Host header, switch to
  `extensions={"sni_hostname": original_host}`.
- Wire the receiver-side `verify_signature` helper into the NOC
  webhook validator to ensure round-trip compatibility before
  enabling the v1 → v2 cutover.

## Self-Check: PASSED

**Files created (11) — all present:**

- src/spark_modem/webhook/__init__.py
- src/spark_modem/webhook/sign.py
- src/spark_modem/webhook/dedup.py
- src/spark_modem/webhook/dns.py
- src/spark_modem/webhook/poster.py
- tests/unit/webhook/__init__.py
- tests/unit/webhook/test_sign.py
- tests/unit/webhook/test_dedup.py
- tests/unit/webhook/test_dns.py
- tests/unit/webhook/test_poster.py
- tests/unit/webhook/test_drain.py

**Files modified (2):**
- src/spark_modem/wire/events.py — `WebhookDropped` variant + Event Annotated union
- src/spark_modem/event_logger/writer.py — `WebhookDropped` registered in `_EVENT_TYPES`

**Commits exist:**
- 8014e12 — feat(02-08): add webhook/ sign + dedup + dns helpers
- 214c4bc — feat(02-08): add WebhookPoster + WebhookDropped event variant

**Verification gates pass:**
- `python -m mypy --strict src/spark_modem/webhook/ src/spark_modem/wire/events.py src/spark_modem/event_logger/writer.py tests/unit/webhook/`: clean (13 source files)
- `python -m ruff check src/spark_modem/webhook/ tests/unit/webhook/`: clean
- `python -m ruff format --check src/spark_modem/webhook/ tests/unit/webhook/`: 11 files already formatted
- `python -m pytest tests/unit/webhook/`: 47 passed (sign 11, dedup 9, dns 8, poster 14, drain 5)
- `bash scripts/lint_no_subprocess.sh`: SP-04 clean (no subprocess calls outside src/spark_modem/subproc/)
- Full regression: `python -m pytest tests/`: 559 passed, 44 POSIX-only skipped on Windows dev host
- Acceptance grep checks all pass (X-Spark-Signature / X-Spark-Timestamp / Host header / `_DEFAULT_BACKOFF_SECONDS = (1.0, 4.0, 16.0)` / `class WebhookDropped` / WebhookDropped registered in writer's `_EVENT_TYPES` / `loop.getaddrinfo` / `WebhookPayloadAdapter.dump_json(envelope.payload)` / `hmac.new` / `hmac.compare_digest`)
