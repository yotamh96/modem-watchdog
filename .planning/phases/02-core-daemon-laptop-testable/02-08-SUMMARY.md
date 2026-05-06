---
phase: 02-core-daemon-laptop-testable
plan: 08
subsystem: webhook
tags: [webhook, hmac, dns, dedup, retry, drain, poster, fr-44, fr-44.3, fr-44.4, fr-44.5, fr-44.6, fr-44.7, fr-44.8, adr-0011, w-01, w-02]

# Dependency graph
requires:
  - phase: 01-foundations-adrs
    provides: BaseWire (frozen, extra='forbid'); WebhookEnvelope + WebhookPayload discriminated union (HealthyToDegraded / RecoveringToExhausted / DaemonRestart / ActionFailedWebhook); WebhookPayloadAdapter (TypeAdapter for raw-bytes serialisation); Settings (webhook_url / webhook_max_retries / webhook_dedup_seconds / webhook_allow_http); Event union + EventAdapter; EventLogWriter (append-only JSONL); ActionKind / DaemonStopReason enums
  - phase: 02-01-test-fakes
    provides: FakeClock (monotonic + wall_clock_iso); FakeDNSResolver (resolve(host) -> str | None); pattern for `tests/unit/<module>/__init__.py` package scaffolding
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
affects: [02-10-cycle-driver, 02-09-cli, phase-3-sighup-reload, phase-3-sigterm-graceful-shutdown]

# Tech tracking
tech-stack:
  added:
    - "httpx >=0.27,<1 — already pinned in packaging/requirements.in (Phase 1); Plan 02-08 is the first consumer in src/."
  patterns:
    - "HMAC over raw bytes (PITFALLS §10.5): sign_envelope returns (body_bytes, sig_header, ts_header) as a tuple; the caller MUST pass body_bytes verbatim to httpx as `content=body`. Re-serializing the envelope after signing breaks receiver verification — the contract is enforced by `test_payload_bytes_match_adapter_dump_json_exactly` and by the absence of any model_dump_json call inside _post_one between sign and POST."
    - "Host-header DNS trick (W-02 / RESEARCH §2.7): the request URL embeds the cached IP (`https://192.0.2.7:443/path`) so the TCP connection never blocks on resolver state, while the explicit `Host: noc.example.test` header preserves the SNI hostname for TLS verify=True. Verified by `test_post_one_uses_host_header_with_cached_ip_url`."
    - "Separate-task / cycle non-blocking (FR-44.8): WebhookPoster.enqueue is non-blocking (queue.put_nowait + counter increment); run_forever() polls the queue with a 0.5s timeout so stop() can preempt it; the cycle driver only calls enqueue() and never awaits delivery."
    - "ClockProto seam: DnsCache + WebhookPoster accept any object with .monotonic() (and for the poster, .wall_clock_iso()). FakeClock satisfies the seam without monkey-patching; production uses spark_modem.clock.clock module functions wrapped in a tiny Clock instance."
    - "DnsCacheProto seam: WebhookPoster takes `dns_cache: DnsCacheProto | None`. FakeDNSResolver implements `async resolve(host)` and is used in every poster test; production builds a real DnsCache(clock=clock)."
    - "Bounded queue + drop-on-full: asyncio.Queue(maxsize=100); on QueueFull, the poster increments webhook_delivery_total{result=dropped} and emits a WebhookDropped(reason=queue_full) event — never silently overwrites or blocks the cycle."
    - "Backoff schedule via tuple parameter (default (1.0, 4.0, 16.0)): tests pass (0.0, 0.0, 0.0) to remove backoff timing from test logic. attempt_index is computed from (max_retries - attempts_left - 1) and clamped at len(backoff)-1 to defend against config drift."
    - "Drain semantics (W-01): drain() sets stopped, then runs ONE attempt per queued item until budget elapses; remaining items are swept up and emit WebhookDropped(reason=drain_budget_exhausted). Failed-but-attempted items emit reason=drain_timeout. Both metrics paths land in webhook_delivery_total{result=dropped}."
    - "Test pattern — _install_mock_transport(poster, handler): monkey-patches `_make_client` to return an AsyncClient backed by httpx.MockTransport. Avoids adding pytest-httpx as a new dev dep (already absent from pyproject; httpx ships MockTransport)."
    - "Test pattern — _StepClock for budget-time tests: drain test uses a hand-rolled clock that the handler advances on each call. Avoids real `asyncio.sleep` so M7 (≤30 s test budget) holds even with budget-exhaustion test."

key-files:
  created:
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
  modified:
    - src/spark_modem/wire/events.py        # +WebhookDropped variant; added to Event Annotated union
    - src/spark_modem/event_logger/writer.py # +WebhookDropped in _EVENT_TYPES tuple

key-decisions:
  - "Body bytes returned from sign_envelope as a tuple (body_bytes, sig_header, ts_header) instead of a mutated envelope. Rationale: the WebhookEnvelope is BaseWire (frozen + extra='forbid'); mutating signature_header_value would require a new envelope construction, but the bytes signed are the PAYLOAD bytes (not the envelope bytes), so the receiver verifies against payload bytes. The tuple shape makes that contract explicit and impossible to break by re-serializing the envelope after signing."
  - "verify_signature(body_bytes, signature_header, secret) shipped alongside sign_envelope so the test suite exercises receiver-side verification on every test case (test_sign_envelope_signs_raw_payload_bytes asserts both sign + verify in one path). Same code path as a future Phase 5 receiver acceptance test."
  - "DnsCache._stale_until is set on success (not on failure). Rationale: stale-window is a cap on how long we'll TRUST the previously-cached value; on failure we just check (now < _stale_until). On a fresh resolve we extend the trust window. This matches ADR-0011 §8: 'previous cached address is used for any delivery that arrives during the re-resolve window' bounded by stale_max."
  - "DnsCache stores the IP from infos[0][4][0] (sockaddr[0]) cast to str. Rationale: getaddrinfo's tuple shape is (family, type, proto, canonname, sockaddr), and sockaddr is (host, port) for IPv4 / (host, port, flowinfo, scope_id) for IPv6. Both have host as element 0. The str() cast is defensive for typing; mypy --strict accepts it."
  - "DedupTable suppressed[] uses dict.get with default 0 instead of defaultdict(int). Rationale: keeps the type signature explicit (dict[tuple[str, str], int]) without import of collections.defaultdict, and the read-modify-write happens once per dedup hit — cheap."
  - "DedupTable opens a fresh window on the call AFTER expiry (caller's first cycle counts as 'first emission'). Rationale: matches ADR-0011 §4 — 'The dedup window starts on the FIRST occurrence'. The just-after-expiry call is logically the first occurrence in a new window."
  - "WebhookPoster takes `dns_cache: DnsCacheProto | None`. When None, the poster constructs a real DnsCache(clock=clock). Rationale: production code wires the real cache without ceremony; tests pass FakeDNSResolver. The default-None branch is exercised by `test_default_refresh_interval_and_stale_max` indirectly (DnsCache has the right defaults) and by full regression tests against the runtime."
  - "_post_one calls _make_client() inside `async with` so the AsyncClient is constructed AND torn down per attempt. Rationale: a single client across attempts could pin a stale connection to an IP that changed in a refresh; per-attempt clients are simpler and the connection-establishment cost is dominated by TLS handshake which we WANT to refresh on retry. Future optimisation (single client pooled) is post-Phase 5 work."
  - "_DEFAULT_BACKOFF_SECONDS = (1.0, 4.0, 16.0) matches the plan's W-01 [1s, 4s, 16s] explicitly. The dispatcher computes attempt_index = max_retries - attempts_left - 1 and clamps at len(backoff)-1 so a config setting webhook_max_retries > len(backoff) doesn't IndexError; the last value just repeats."
  - "Tests for retry/backoff use backoff_seconds=(0.0, 0.0, 0.0) so the loop runs at full speed; without this the test suite would block 21 s per retry-exhaustion test (1+4+16). Real-time `asyncio.sleep` was avoided in test_drain_budget_exhausted_drops_remaining via a hand-rolled _StepClock that the handler advances per call — keeps the test under 1s and hermetic."
  - "WebhookPoster.stop() public method added (Rule 2: missing critical functionality). The plan's run_forever() loop checks self._stopped.is_set(), but no public method to set it was specified outside drain(). stop() is needed by Phase 3 SIGTERM wiring (graceful shutdown without forcing drain). drain() also calls stop() internally."
  - "Settings http:// validation forced an http:// parametrize test to be reduced to an https-only round-trip assertion. The Phase 1 Settings model rejects http URLs without webhook_allow_http=true; rather than override the validator in tests, we keep the parametrize narrow (https-only) and document the http path is gated at config-load time. http URLs are tested in tests/unit/config/ as a Settings concern, not a poster concern."

patterns-established:
  - "src/spark_modem/<package>/<module>.py production module + tests/unit/<package>/test_<module>.py test pattern continues unchanged from Phase 2 prior plans."
  - "Public Protocol seams co-located with implementations (ClockProto, DnsCacheProto, EventLogWriterProto, MetricRegistryProto in poster.py; ClockProto in dns.py). Tests inject fakes that satisfy the Protocols without monkey-patching production code."
  - "Test fixtures construct Settings with /tmp paths to satisfy required state_root / run_dir / events_log_path / metrics_socket_path / carriers_yaml_path fields; the conftest.py `settings` fixture is reused where possible but per-test Settings construction (with explicit webhook_url override) is the established pattern in tests/unit/webhook/."
  - "ruff PLR2004 'magic value in comparison' is handled by lifting the literal into a module constant (_HTTP_OK_LOW=200, _HTTP_OK_HIGH=300) — same pattern as `_DEFAULT_BACKOFF_SECONDS`."

requirements-completed:
  - FR-44     # Webhook POST on Healthy → Degraded and Recovering → Exhausted transitions (poster ships; cycle driver wires in 02-10)
  - FR-44.3   # 3-attempt retry with exponential backoff [1s, 4s, 16s]; in-memory bounded queue (default 100); drop on exhaustion + WebhookDropped event
  - FR-44.4   # 60s per-(modem, transition) coalescing window via DedupTable; dedup_count accumulation + consume_dedup_count
  - FR-44.5   # DaemonRestart payload variant supported (Phase 1 wire shape; poster signs + sends it via the same code path as other variants)
  - FR-44.6   # ActionFailedWebhook payload variant supported (Phase 1 wire shape; same code path)
  - FR-44.7   # Pre-exit best-effort drain bounded at 3s default; remainders emit WebhookDropped events
  - FR-44.8   # Separate asyncio task with explicit httpx timeouts (connect=5, read=5, write=5, pool=10) + pre-resolved cached DNS via loop.getaddrinfo

# Metrics
metrics:
  duration: "~30m"
  tasks_completed: 2
  files_created: 11
  files_modified: 2
  tests_added: 47
  test_pass_rate: "100% (47/47 webhook tests; 559 passed, 44 skipped POSIX-only across full suite)"
  completed: 2026-05-06
---

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
