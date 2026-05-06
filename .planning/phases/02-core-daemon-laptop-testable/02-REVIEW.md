---
phase: 02-core-daemon-laptop-testable
reviewed: 2026-05-06T00:00:00Z
depth: standard
files_reviewed: 53
files_reviewed_list:
  - src/spark_modem/actions/context.py
  - src/spark_modem/actions/dispatcher.py
  - src/spark_modem/actions/fix_autosuspend.py
  - src/spark_modem/actions/fix_raw_ip.py
  - src/spark_modem/actions/result.py
  - src/spark_modem/actions/set_apn.py
  - src/spark_modem/actions/set_operating_mode.py
  - src/spark_modem/actions/sim_power_on.py
  - src/spark_modem/actions/soft_reset.py
  - src/spark_modem/actions/verify.py
  - src/spark_modem/cli/clients.py
  - src/spark_modem/cli/ctl/history.py
  - src/spark_modem/cli/ctl/maintenance.py
  - src/spark_modem/cli/ctl/support_bundle.py
  - src/spark_modem/cli/diag.py
  - src/spark_modem/cli/explain.py
  - src/spark_modem/cli/main.py
  - src/spark_modem/cli/provision.py
  - src/spark_modem/cli/recovery.py
  - src/spark_modem/cli/redact.py
  - src/spark_modem/cli/reset.py
  - src/spark_modem/cli/status.py
  - src/spark_modem/daemon/cycle_driver.py
  - src/spark_modem/daemon/cycle_scheduler.py
  - src/spark_modem/daemon/main.py
  - src/spark_modem/daemon/rss_tripwire.py
  - src/spark_modem/inventory/descriptor.py
  - src/spark_modem/inventory/protocol.py
  - src/spark_modem/inventory/sysfs.py
  - src/spark_modem/observer/diag_builder.py
  - src/spark_modem/observer/issue_extractor.py
  - src/spark_modem/observer/orchestrator.py
  - src/spark_modem/policy/context.py
  - src/spark_modem/policy/decision_table.py
  - src/spark_modem/policy/engine.py
  - src/spark_modem/policy/gates.py
  - src/spark_modem/policy/result.py
  - src/spark_modem/policy/transitions.py
  - src/spark_modem/qmi/errors.py
  - src/spark_modem/qmi/parsers/_header.py
  - src/spark_modem/qmi/parsers/get_current_settings.py
  - src/spark_modem/qmi/parsers/get_data_session.py
  - src/spark_modem/qmi/parsers/get_operating_mode.py
  - src/spark_modem/qmi/parsers/get_profile_settings.py
  - src/spark_modem/qmi/parsers/get_serving_system.py
  - src/spark_modem/qmi/parsers/get_signal.py
  - src/spark_modem/qmi/parsers/get_sim_state.py
  - src/spark_modem/qmi/wrapper.py
  - src/spark_modem/status_reporter/metrics_registry.py
  - src/spark_modem/status_reporter/prom.py
  - src/spark_modem/status_reporter/status.py
  - src/spark_modem/webhook/dedup.py
  - src/spark_modem/webhook/dns.py
  - src/spark_modem/webhook/poster.py
  - src/spark_modem/webhook/sign.py
  - src/spark_modem/wire/maintenance.py
  - src/spark_modem/wire/status.py
  - src/spark_modem/zao_log/parser.py
  - src/spark_modem/zao_log/protocol.py
  - src/spark_modem/zao_log/snapshot.py
  - tools/check_spec.py
  - tools/gen_replay_fixtures.py
findings:
  critical: 1
  warning: 8
  info: 9
  total: 18
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-05-06T00:00:00Z
**Depth:** standard
**Files Reviewed:** 53
**Status:** issues_found

## Summary

Phase 2 ships the core daemon pipeline (observer, pure policy, cheap actions, status/Prometheus, HMAC webhook, and the spark-modem CLI) with strong project-invariant discipline overall. The critical CLAUDE.md invariants (policy purity, `usb_path` keying, monotonic durations, integer-encoded `modem_state_value`, raw-bytes HMAC over the envelope, `match` on `ModemState`, list-form argv) are respected throughout — and several files (`policy/engine.py`, `webhook/sign.py`, `qmi/wrapper.py`, `metrics_registry.py`) document the invariants in-source.

That said, the review surfaced one Critical issue and several Warnings worth addressing before the phase closes:

1. **CR-01 — Webhook timestamp/replay-protection bug**: `webhook/poster.py:241` builds the HMAC `X-Spark-Timestamp` header from `int(self._clock.monotonic())`. Monotonic time is process-relative; the receiver expects a Unix wall-clock for replay protection (ADR-0011 / FR-44.2). Receivers comparing `now_unix - X-Spark-Timestamp` against a window will reject every legitimate request.
2. **WR-01 — Exhausted state machine arm cannot recover**: `policy/transitions.py:103-105` keeps a modem in `exhausted` even when issues have cleared, regardless of `_healthy_streak` decay (which the engine resets to 0 on non-healthy states). Once exhausted, a modem cannot return to healthy via the transitions function alone.
3. **WR-02 — Webhook backoff/timestamp uses monotonic for `ts_unix`** in the same site as CR-01; even after fixing the wire-format header, the in-memory monotonic-as-unix conflation is a category error worth tightening.
4. Other warnings cover: lexicographic ISO comparison in `cli/ctl/maintenance.py` and `cli/ctl/history.py` (works in UTC but brittle if a non-UTC string ever sneaks through), webhook drain handing items off without backoff/respecting `next_retry_monotonic`, `re.MULTILINE` referenced in a comment but not actually applied in `parsers/get_signal.py`, observer not surfacing `apn_mismatch` (consistent with the design but the comment in `engine.py` claims it lives in `policy/decision_table.py` where in fact no such logic exists), CLI sync file reads without ASYNC240 guards in a few places, sysfs `_line_from_usb_path` silently degrading malformed input to `1` rather than skipping the modem.

Info items cover smaller hygiene: docstring/code drift, missing `Disconnected` in the state-aggregation in status.json (a `match` would be safer than the if/elif chain), some optional logging on dropped webhook envelopes, and a few places that could use the integer encoding helper rather than open-coded fallback.

The Phase 2 deliverable is sound, but **CR-01 must be fixed before Phase 3 wires the production webhook receiver** (otherwise every authentic post is rejected as expired).

## Critical Issues

### CR-01: Webhook `X-Spark-Timestamp` header uses `time.monotonic()` instead of Unix wall-clock

**File:** `src/spark_modem/webhook/poster.py:241`
**Issue:** `ts_unix = int(self._clock.monotonic())` builds the replay-protection timestamp from a monotonic clock. Per ADR-0011 / FR-44.2 / `webhook/sign.py:36-38` docstring, `X-Spark-Timestamp` is the Unix wall-clock seconds and the receiver compares it against `time.time()` to enforce a replay window (typically ±5 minutes). Monotonic time on a Linux process can be hundreds of seconds (since boot) up to days/weeks; under no circumstance does it match wall-clock seconds. Every authentic POST will be rejected by a strict receiver as either far in the past or far in the future. CLAUDE.md invariant #4 explicitly says "`time.monotonic()` for durations and backoffs; `time.time()` only for ISO-8601 stamps" — Unix-seconds in a wire-format header is a wall-clock stamp, not a duration.

The `ClockProto` defined on lines 50-54 of the same file does not expose a `unix_seconds()` accessor today; either add one or compute the wall-clock seconds inline (the cycle driver already uses `wall_clock_iso()` in adjacent code, so adding a wall-time integer accessor is consistent).

**Fix:**
```python
# In ClockProto on poster.py and on cli/clients._CliClock:
class ClockProto(Protocol):
    def monotonic(self) -> float: ...
    def wall_clock_iso(self) -> str: ...
    def unix_seconds(self) -> int: ...   # NEW

# _CliClock implementation:
import time as _time
class _CliClock:
    def monotonic(self) -> float: return _time.monotonic()
    def wall_clock_iso(self) -> str: return datetime.now(UTC).isoformat()
    def unix_seconds(self) -> int: return int(_time.time())   # NEW

# poster.py:241:
ts_unix = self._clock.unix_seconds()
```

Tests should assert that `X-Spark-Timestamp` is within `±60s` of `int(time.time())` at sign time, and verify_signature-style replay tests should drive the cutoff via the receiver. Until this is fixed, every signed webhook is dead-on-arrival to a receiver that enforces the replay window.

## Warnings

### WR-01: `exhausted` state has no escape path in `transitions.py`

**File:** `src/spark_modem/policy/transitions.py:103-105`
**Issue:** The `match` arm for `exhausted` returns `_stay_or_update(prior, "exhausted", ...)` unconditionally — i.e. the only way out is via the engine's healthy-streak decay (`engine.py:122-124`). But `engine.run_cycle` line 117 sets `new_streak = (prior.healthy_streak + 1) if new_state.state == "healthy" else 0`. Since the transitions function never returns `healthy` from an `exhausted` prior (it always re-emits `exhausted`), the streak never increments, decay never fires, and the modem is permanently stuck. RECOVERY_SPEC §3.2 / ADR-0008 expect exhausted -> healthy when issues clear AND signal is good (the same conditions other arms check at line 70 `if not snap.issues and not rf_blocked: return _to_healthy(...)`).

This is also flagged by Success Metric M4 ("Zero `Exhausted` states caused by counter accumulation") — once stuck, the modem never recovers without human intervention.

**Fix:**
```python
case "exhausted":
    # RECOVERY_SPEC §3.2: exhausted -> healthy when issues clear AND signal good.
    # The early-return at line 70 already handles the no-issues + signal-good case
    # but ONLY when prior.state matches an arm above; exhausted falls through.
    if not snap.issues and not rf_blocked:
        return _to_healthy(prior, present, rf_blocked)
    return _stay_or_update(prior, "exhausted", present, rf_blocked)
```

Also: the early-return on line 70 already covers this, but only because it executes before the `match`. Verify the desired semantics — if the early-return is the canonical exit, this is moot for exhausted; but the early-return at line 70 reads `if not snap.issues and not rf_blocked` which IS reached for exhausted, so the bug may be benign. Audit + add an explicit test (`test_transitions_exhausted_to_healthy_on_clear`) to lock the behaviour either way; the current code's correctness depends on subtle ordering between early-return and `match`.

### WR-02: Lexicographic ISO-8601 comparison is fragile across timezones

**File:** `src/spark_modem/cli/ctl/maintenance.py:130-133`, `src/spark_modem/cli/ctl/history.py:142`
**Issue:** Both sites compare ISO timestamps with `<` / `>=`. This works only when both strings are in the same canonical form (UTC `+00:00` or `Z`). The codebase generates UTC strings via `datetime.now(UTC).isoformat()` everywhere I checked, so this is correct today — but a hand-edited globals.json or a future writer that emits a different timezone offset (e.g. `+02:00`) will produce ordering bugs. `2026-05-06T01:00:00+00:00` lexicographically sorts AFTER `2026-05-06T02:00:00+02:00` even though the latter represents the same instant.

**Fix:** Parse both sides through `datetime.fromisoformat` and compare as `datetime` objects (or normalise to UTC seconds first):
```python
# maintenance.py:130-133:
expires_dt = datetime.fromisoformat(m.expires_iso)
now_dt = datetime.now(UTC)
expired = (now_mono >= m.expires_monotonic) or (now_dt >= expires_dt)
```
Same fix for `history.py:142`. Cheap and removes the latent class of bug.

### WR-03: `WebhookPoster.drain` ignores `next_retry_monotonic`

**File:** `src/spark_modem/webhook/poster.py:283-298`
**Issue:** During shutdown the drain loop pops items with `get_nowait()` and calls `_post_one` directly, bypassing the per-item `next_retry_monotonic` field that the retry path sets on requeue. If an item was requeued at attempt 2 with a 16-second backoff and the daemon receives SIGTERM 1 second later, the drain will hit the receiver immediately — potentially within the receiver's anti-spam window from the failed first attempt. Lower priority than CR-01 but still worth tightening; the docstring on line 273-279 promises "ONE attempt per queued item within budget" which is satisfied, but doesn't address whether to honour the backoff.

**Fix:** Either explicitly document "drain ignores backoff" in the docstring (acceptable per W-01) or add a `now < item.next_retry_monotonic` skip path:
```python
while not self._queue.empty() and self._clock.monotonic() < deadline:
    item = self._queue.get_nowait()
    if self._clock.monotonic() < item.next_retry_monotonic:
        # Skip; let it expire as drain_budget_exhausted on the second loop.
        await self._queue.put(item)
        continue
    ...
```
The current code is observable as "drain attempts everything immediately" — confirm that's the intended W-01 behaviour and document it; otherwise add the backoff check.

### WR-04: `re.MULTILINE` documented but not used in get_signal.py

**File:** `src/spark_modem/qmi/parsers/get_signal.py:40-45`
**Issue:** The comment on line 40-41 says "Anchor each capture on a single line; `re.MULTILINE` lets `^` match the start of a line so an LTE block doesn't bleed RSSI from a stale NR5G block." The patterns themselves (lines 42-45) do NOT use `^` anchors, do NOT pass `re.MULTILINE`, and `re.search` on a multi-band response will happily match the first occurrence of `RSSI: '-65 dBm'` regardless of which band-block it sits in. The defensive intent in the comment is not implemented.

For libqmi 1.32+ NR5G+LTE outputs (mentioned in the module docstring lines 12-14), this means an NR5G RSSI may be reported as the LTE RSSI. EM7421 is LTE-only, so this is unlikely to fire in production, but the comment claims correctness that the code does not provide.

**Fix:** Either implement the documented behaviour:
```python
_RE_RSSI: Final[re.Pattern[str]] = re.compile(r"^\s+RSSI:\s*'(-?\d+)\s*dBm'", re.MULTILINE)
_RE_RSRP: Final[re.Pattern[str]] = re.compile(r"^\s+RSRP:\s*'(-?\d+)\s*dBm'", re.MULTILINE)
# ...
```
combined with prefix-band-section detection, or remove/rewrite the comment to honestly describe the current "first-match-wins" behaviour. Add a fixture for an NR5G+LTE response to lock whichever decision you make.

### WR-05: `SysfsInventory._line_from_usb_path` silently degrades malformed input to line=1

**File:** `src/spark_modem/inventory/sysfs.py:79-93`
**Issue:** When `usb_path` does not end in a numeric component (e.g. a non-Sierra device that somehow matched VID/PID) or the trailing component is out of range, `_line_from_usb_path` returns `_LINE_MIN` (=1). This means two real modems can resolve to the same `line=1` if their `usb_path` tails are unparseable, potentially conflating two different USB devices in policy/Zao keying.

The descriptor IS keyed by `usb_path` per ADR-0009, so policy state stays correct; but the Zao FR-10 gate uses `line` as the key (`zao.is_line_active(modem.line)`) — and silently mapping multiple modems to the same Zao line is a correctness bug for the gate.

**Fix:** Return `None` and have `scan()` skip the descriptor:
```python
@staticmethod
def _line_from_usb_path(usb_path: str) -> int | None:
    tail = usb_path.rsplit(".", 1)[-1]
    try:
        value = int(tail)
    except ValueError:
        return None
    return value if _LINE_MIN <= value <= _LINE_MAX else None
```
Then in `scan()`, skip when `line is None`. A non-Sierra device that happens to share VID/PID is safer dropped than mis-keyed.

### WR-06: Observer surfaces `connection_status='disconnected'` even when value is missing

**File:** `src/spark_modem/observer/issue_extractor.py:270-277`
**Issue:** The check on line 270 reads `if isinstance(data, GetDataSessionResult) and data.connection_status == "disconnected":`. `parse_get_data_session` returns `QmiError(UNEXPECTED_OUTPUT)` when the line is missing entirely, so `isinstance(data, GetDataSessionResult)` would be False — that path is fine. BUT the parser also normalises with `.strip().lower()` on line 43, and any value other than `"disconnected"` (e.g. `"connected"`, `"limited"`, `"flow-controlled"`) silently passes through without surfacing a SESSION_DISCONNECTED issue. This is correct for the literal "disconnected" case but obscures whether the observer should also flag intermediate states (libqmi has emitted `"limited"` since 1.30).

This is more of a coverage gap than a bug — file an Info item, but Phase 2 should explicitly enumerate the "issue-equivalent" states OR document that only literal `"disconnected"` triggers.

**Fix:** Either expand the trigger set or pin the "disconnected only" behaviour in a fixture-test comment; ADD a parametrised test for `"limited"` so future libqmi changes don't drift silently.

### WR-07: `cli/recovery.py` synchronous file read in async context flagged with `# noqa: ASYNC240`

**File:** `src/spark_modem/cli/recovery.py:52`
**Issue:** `Diag.model_validate_json(diag_path.read_bytes())  # noqa: ASYNC240` reads the diag fixture synchronously from inside an async function. The `noqa` is justified by the comment "CLI is short-lived; sync read is intentional and bounded" — fine for CLI mode. However, `cli/ctl/support_bundle.py` does the same pattern (`f.read_bytes()` on lines 120, 144, 157) inside an `async def` without the `noqa`, and `cli/ctl/history.py` opens files in async context too (lines 71, 74). The lint suppression is inconsistent: either suppress everywhere or hoist sync I/O into a helper.

**Fix:** Either:
- Add `# noqa: ASYNC240` to the support_bundle and history sync reads (matches the pattern in recovery.py), or
- Pull the sync I/O out into a sync helper function (matches the pattern in `daemon/main.py:_ensure_dirs`).

The second is cleaner and consistent with the existing daemon/main.py pattern.

### WR-08: `cli/diag.py` default inventory path is relative to CWD

**File:** `src/spark_modem/cli/diag.py:28` (and `daemon/main.py:74`)
**Issue:** `_DEFAULT_INVENTORY = Path("tests/fixtures/inventory/four_modems.json")` is a relative path. If the operator runs `spark-modem diag --qmi-fixture-dir=...` from any directory other than the repo root, the inventory file will not be found and the descriptor scan returns no modems — the diag CLI silently outputs `"per_modem": {}` rather than producing a useful error. Same concern in `daemon/main.py:74`.

**Fix:**
```python
# Anchor to the package, not CWD:
_DEFAULT_INVENTORY = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "tests" / "fixtures" / "inventory" / "four_modems.json"
)
```
OR fail fast when the file is absent:
```python
if not inventory_path.is_file():
    print(f"diag: inventory file not found: {inventory_path}", file=sys.stderr)
    return 2
```
Combine both for the cleanest behaviour.

## Info

### IN-01: `cycle_driver._write_status_report` uses `if/elif` chain on state name

**File:** `src/spark_modem/daemon/cycle_driver.py:462-472`
**Issue:** The `state_name == "healthy" / "degraded" / ...` chain conflicts with CLAUDE.md anti-pattern #9: "if/elif instead of `match` on `ModemState`". Although `state_name` here is a literal string, the underlying `ModemState.state` is a closed `Literal`, and `match` would let mypy --strict catch a missing arm if the StateLiteral grows.
**Fix:** Replace with `match state_name: case "healthy": healthy += 1; ...` — same pattern as `policy/transitions.py:74`. Also the `else: unknown += 1` arm masks any drift; an explicit `case _: unknown += 1` documents the intent.

### IN-02: Status report aggregation drops `Disconnected` count

**File:** `src/spark_modem/daemon/cycle_driver.py:442-485`
**Issue:** `StatusModemSummary` (wire/status.py:35-45) has a `disconnected` counter (line 44), but the `_write_status_report` aggregator on cycle_driver.py:442 never sets it — the count is always 0 even when modems are present=False. Phase 3 will introduce udev-driven `present=False` transitions; updating now keeps the wire shape honest.
**Fix:** Add a `disconnected = sum(1 for m in modems if not states.get(m.usb_path, prior).present)` accumulator and pass it into `StatusModemSummary(disconnected=disconnected, ...)`.

### IN-03: `_event_modem_id` could be a method on the Event union

**File:** `src/spark_modem/cli/ctl/history.py:104-119`
**Issue:** The `hasattr` chain on lines 110-118 would be cleaner as an `event.modem_identity()` accessor on each Event subclass, returning `usb_path` / `modem_usb_path` / `file_usb_path` consistently. The current code grows fragile if a new Event variant uses yet another field name.
**Fix:** Either add a `modem_identity()` abstract method to the Event base, or `match` on the discriminated union to make the field-name mapping explicit.

### IN-04: `redact.py` 8-char hash space is small for fleet-wide ICCID space

**File:** `src/spark_modem/cli/redact.py:5-7,27-28`
**Issue:** The docstring on lines 5-7 acknowledges this: "~32 bits of distinct hash space — sufficient to cross-reference within a single bundle but not enough to enable a brute-force lookup table." That's correct for a single bundle, BUT across the fleet (say 200 boxes × 4 modems = 800 ICCIDs) the birthday probability of a collision is non-trivial (~1 in 5,000 per bundle pair). For cross-bundle correlation that may matter.
**Fix:** No change needed for v1 — Phase 2 redaction is single-bundle correlation only. File a v2 follow-up to widen to 12-16 chars if cross-bundle correlation becomes a NOC need.

### IN-05: `_find_cdc_wdm` returns first match without sorting

**File:** `src/spark_modem/inventory/sysfs.py:96-106`
**Issue:** `Path.rglob` does not guarantee a stable iteration order, so if an EM7421 entry produces multiple `usbmisc/cdc-wdm*` matches (rare but possible during enumeration races), the chosen `cdc_wdm` could vary across cycles. ADR-0009 says state is keyed by `usb_path` so this doesn't corrupt persistence, but the cycle-to-cycle variance in `cdc_wdm` would surface in events.jsonl.
**Fix:** `for misc in sorted(resolved.rglob("usbmisc/cdc-wdm*")):` — pick the lexicographically smallest match deterministically.

### IN-06: `WebhookPoster._make_client` rebuilds AsyncClient per attempt

**File:** `src/spark_modem/webhook/poster.py:210-220, 254-260`
**Issue:** A new `httpx.AsyncClient` is created and torn down per `_post_one` call. This rebuilds the connection pool every time and prevents HTTP/2 connection reuse. Phase 2 cycle cadence is 30s so the cost is bounded, but a long-lived client (built in `__init__`) would be cheaper and would let the connection pool absorb retries.
**Fix:** Build `self._client` in `__init__`, `await self._client.aclose()` in `drain()`. Adds an `__aenter__`/`__aexit__` requirement on the poster (or just construct and close in `run_forever`). v1 acceptable as-is; flag as a future optimisation since CLAUDE.md explicitly says performance is OOS for v1.

### IN-07: `sign_envelope` verifies-no-replay-window

**File:** `src/spark_modem/webhook/sign.py:45-64`
**Issue:** `verify_signature` on the receiver side does NOT check the timestamp (it only verifies the HMAC). Replay protection requires the receiver to also assert `abs(now - X-Spark-Timestamp) < window_seconds`. The function is documented as "receiver-side helper, included so the same code path is exercised by the test suite," and the docstring doesn't promise replay protection — but the lack of a timestamp check makes the test asymmetric with what a real receiver MUST do.
**Fix:** Either add a `verify_signature_with_timestamp(body, sig_header, ts_header, secret, *, window_seconds, now_unix)` companion or document loudly that callers MUST verify the timestamp themselves. Phase 3's receiver wiring can pick one.

### IN-08: `cli/clients.py` `_NoZaoTailer.snapshot` allocates per-call

**File:** `src/spark_modem/cli/clients.py:84-85`
**Issue:** Returns `ZaoSnapshot.unknown(reason="cli-mode")` on each call. For a CLI single-cycle invocation this is fine (one allocation per modem), but if the CLI ever invokes the cycle-driver loop, per-modem allocation in a hot path adds up. Since `ZaoSnapshot` is a frozen pydantic model, hoisting to a class-level constant is safe.
**Fix:**
```python
_UNKNOWN_SNAPSHOT: ClassVar[ZaoSnapshot] = ZaoSnapshot.unknown(reason="cli-mode")
def snapshot(self) -> ZaoSnapshot:
    return self._UNKNOWN_SNAPSHOT
```

### IN-09: `gen_replay_fixtures.py` `random.seed` set but `random` never used

**File:** `tools/gen_replay_fixtures.py:214`
**Issue:** `random.seed(args.seed)` is called on line 214, but the module never calls any `random.*` function — fixture generation is fully deterministic from the scenario list. The seed is dead state. The docstring (lines 25-27) says "Determinism: the generator seeds `random.seed(args.seed)` once. Same seed + same count produces byte-identical fixture files (T-02-10-04)." — which is technically true (because nothing random happens) but misleading.
**Fix:** Either remove the `random.seed` call and the `--seed` arg + docstring claim, or actually use `random` to introduce deterministic-but-varied jitter in the fixtures (timestamps, signal values) which would catch a class of policy-engine bugs the current fixed values miss.

---

_Reviewed: 2026-05-06T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
