# Phase 2: Core Daemon (laptop-testable) — Pattern Map

**Mapped:** 2026-05-06
**Files analyzed:** 28 (14 production + 14 test seam / fixture paths)
**Analogs found:** 26 / 28 (2 have no prior analog in Phase 1)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/spark_modem/qmi/wrapper.py` | service | request-response | `src/spark_modem/subproc/runner.py` | role-match |
| `src/spark_modem/qmi/parsers/<intent>.py` | utility/transform | transform | `src/spark_modem/wire/_base.py` + `wire/state.py` | partial |
| `src/spark_modem/zao_log/parser.py` | utility/transform | file-I/O | `src/spark_modem/event_logger/writer.py` | partial |
| `src/spark_modem/inventory/protocol.py` | protocol/interface | — | `src/spark_modem/subproc/runner.py` (Runner Protocol) | role-match |
| `src/spark_modem/inventory/sysfs.py` | service | file-I/O | `src/spark_modem/state_store/store.py` | partial |
| `src/spark_modem/observer/` | orchestrator | event-driven/batch | `src/spark_modem/state_store/store.py` (TaskGroup shape) | partial |
| `src/spark_modem/policy/transitions.py` | utility | transform | `src/spark_modem/wire/state.py` | partial |
| `src/spark_modem/policy/decision_table.py` | utility | transform | `src/spark_modem/wire/enums.py` | partial |
| `src/spark_modem/policy/gates.py` | utility | transform | `src/spark_modem/wire/state.py` | partial |
| `src/spark_modem/policy/engine.py` | service | transform | `src/spark_modem/wire/diag.py` | partial |
| `src/spark_modem/actions/<action>.py` | service | request-response | `src/spark_modem/subproc/runner.py` | role-match |
| `src/spark_modem/actions/dispatcher.py` | service | request-response | `src/spark_modem/state_store/store.py` | partial |
| `src/spark_modem/actions/verify.py` | utility | request-response | `src/spark_modem/subproc/result.py` | partial |
| `src/spark_modem/status_reporter/status.py` | service | file-I/O | `src/spark_modem/state_store/atomic.py` | exact |
| `src/spark_modem/status_reporter/prom.py` | service | request-response | — | no analog |
| `src/spark_modem/webhook/poster.py` | service | event-driven | `src/spark_modem/wire/webhook.py` | partial |
| `src/spark_modem/webhook/dns.py` | utility | request-response | `src/spark_modem/clock/clock.py` (monotonic cache) | partial |
| `src/spark_modem/cli/` | controller | request-response | `src/spark_modem/config/settings.py` | partial |
| `src/spark_modem/daemon/main.py` | orchestrator | event-driven | `src/spark_modem/state_store/store.py` | partial |
| `tests/fakes/runner.py` | test-fake | — | `tests/unit/subproc/test_runner_data_errors.py` | role-match |
| `tests/fakes/clock.py` | test-fake | — | `src/spark_modem/clock/clock.py` | exact |
| `tests/fakes/webhook.py` | test-fake | — | `src/spark_modem/wire/webhook.py` | role-match |
| `tests/fakes/inventory.py` | test-fake | — | `src/spark_modem/state_store/store.py` | role-match |
| `tests/fakes/dns.py` | test-fake | — | `src/spark_modem/clock/clock.py` | partial |
| `tests/fixtures/qmicli/<intent>/<libqmi-version>/*.txt` | fixture | — | `tests/fixtures/wire/` pattern | exact |
| `tests/fixtures/zao_log/*.log` | fixture | — | text fixture pattern | no analog |
| `tests/fixtures/inventory/<scenario>.json` | fixture | — | pydantic model_dump_json pattern | partial |
| `tests/replay/test_v1_agreement.py` | test | batch | `tests/unit/state_store/test_store.py` | role-match |

---

## Pattern Assignments

### `src/spark_modem/qmi/wrapper.py` (service, request-response)

**Analog:** `src/spark_modem/subproc/runner.py`

**Imports pattern** (`runner.py` lines 1–31):
```python
from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
import time
from typing import Final

from spark_modem.subproc.errors import SubprocSpawnError
from spark_modem.subproc.result import CompletedProcess
```

**Core pattern — `_in_critical_section` flag + `--device-open-proxy` always** (RESEARCH.md §2.1):
```python
class QmiWrapper:
    def __init__(self, runner: SubprocRunner, device: str) -> None:
        self._runner = runner
        self._device = device
        self._in_critical_section: bool = False

    async def set_operating_mode(self, mode: str) -> CompletedProcess:
        self._in_critical_section = True
        try:
            return await self._runner.run(
                ["qmicli", "--device-open-proxy",
                 f"--device={self._device}",
                 f"--dms-set-operating-mode={mode}"],
                timeout_s=15.0,
            )
        finally:
            self._in_critical_section = False
```

**`--device-open-proxy` enforcement:** every qmicli invocation must unconditionally include `--device-open-proxy`. Map `couldn't open the QMI device: proxy unavailable` in stdout/stderr to `QmiError(reason="proxy_unavailable")`. Never call qmicli in direct mode.

**All errors are data pattern** (`runner.py` lines 108–196): `run()` returns `CompletedProcess` for every outcome including non-zero exit and timeout. Only `FileNotFoundError` and `SubprocSpawnError` propagate. `QmiWrapper` follows the same contract — callers inspect `CompletedProcess.succeeded` and `CompletedProcess.timed_out`.

**Two-stage shutdown pattern** (`runner.py` lines 167–172):
```python
try:
    async with asyncio.timeout(timeout_s):
        stdout, stderr = await proc.communicate(input=stdin)
except TimeoutError:
    timed_out = True
    stdout, stderr = await _two_stage_shutdown(proc)
```

**Windows guard pattern** (`runner.py` lines 245–260):
```python
if sys.platform != "win32":
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(os.getpgid(proc.pid), sig)
else:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        proc.send_signal(sig)
```

---

### `src/spark_modem/qmi/parsers/<intent>.py` (utility, transform)

**Analog:** `src/spark_modem/wire/_base.py` + `src/spark_modem/wire/state.py`

**Pydantic boundary split — parsers use `extra='ignore'`** (`_base.py` lines 14–22 shows the wire boundary; parsers invert it):
```python
# Wire models (forbid unknown fields):
class BaseWire(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        populate_by_name=True,
    )

# Parser models (absorb new libqmi fields silently):
class GetSignalResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rsrp_dbm: int | None = None
    rsrq_db: float | None = None
    snr_db: float | None = None
    # Fields absent in libqmi 1.30 default to None.
    # Fields added in future libqmi point releases are absorbed by extra='ignore'.
```

**`model_validator` pattern** (`wire/state.py` lines 65–83):
```python
@model_validator(mode="after")
def _check_recovering_level(self) -> ModemState:
    if self.state == "recovering":
        if self.recovering_level is None:
            raise ValueError("recovering_level is required when state == 'recovering'")
    elif self.recovering_level is not None:
        raise ValueError(...)
    return self
```

**Fixture-keyed per-version layout:** fixture files live at `tests/fixtures/qmicli/<intent>/<libqmi-version>/<scenario>.txt` (e.g. `get_signal/1.30/lte_strong.txt`). First line of each file is a comment `# libqmi_version: 1.30`. Parser is version-agnostic — `extra='ignore'` absorbs version drift. Test parametrizer reads the header to label runs.

**`MissingField` sentinel:** if a required field is structurally absent (not just `None`), the parser returns `QmiError(reason="missing_field", field="<name>")` rather than `None`. Never silently produce `None` for a field the policy engine depends on.

---

### `src/spark_modem/zao_log/parser.py` (utility, file-I/O)

**Analog:** `src/spark_modem/event_logger/writer.py`

**File-open pattern** (`writer.py` lines 73–90):
```python
def __init__(self, path: Path | str) -> None:
    self._path = Path(path)
    parent = self._path.parent
    parent_existed = parent.exists()
    parent.mkdir(parents=True, exist_ok=True)
    self._fd: int | None = os.open(
        str(self._path),
        os.O_WRONLY | os.O_CREAT | os.O_APPEND,
        _MODE,
    )
```

**Parser structure** (RESEARCH.md §2.2 sketch):
```python
class ZaoLogParser:
    def parse_file(self, path: Path) -> ZaoSnapshot:
        """Read the log file and return the last RASCOW_STAT snapshot."""
        with path.open("r", encoding="ascii", errors="replace") as fh:
            lines = fh.readlines()
        # Walk backwards to find the most recent RASCOW_STAT block
        ...
```

**Protocol seam for Phase 3:** wrap `ZaoLogParser` behind a `ZaoLogTailer` Protocol so Phase 3 can swap in an inotify-backed impl. The Phase 2 impl calls `parse_file()` on each cycle; Phase 3 accumulates lines via inotify. The observer calls `zao.is_line_active(line_idx)` — same surface for both.

**`ZaoSnapshot.is_line_active(line_idx: int) -> bool`** is the method observer calls (FR-10). It determines whether a modem line is being actively bonded by Zao, which gates all QMI probing.

---

### `src/spark_modem/inventory/protocol.py` (protocol, —)

**Analog:** `src/spark_modem/subproc/runner.py` (the `SubprocRunner` Protocol pattern)

**Protocol definition pattern** — co-locate with the implementation module (Claude's Discretion):
```python
# inventory/protocol.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class InventorySource(Protocol):
    async def scan(self) -> list[ModemDescriptor]:
        """Return the current list of attached modems."""
        ...
```

Where `ModemDescriptor` carries `(line, cdc_wdm, usb_path, ns, iface)` — the five fields from FR-2.

**`runtime_checkable`** allows `isinstance(obj, InventorySource)` in tests. Same pattern as Python `typing.Protocol` best practices.

---

### `src/spark_modem/inventory/sysfs.py` (service, file-I/O)

**Analog:** `src/spark_modem/state_store/store.py` (directory-walk + path helpers pattern)

**Directory walk pattern** (`store.py` lines 260–269 for sysfs analog):
```python
async def list_modem_state_usb_paths(self) -> tuple[str, ...]:
    d = state_by_usb_dir(root=self._state_root)
    if not d.is_dir():
        return ()
    paths = []
    for f in d.iterdir():
        if f.is_file() and f.suffix == ".json" and ".from-v" not in f.name:
            paths.append(f.stem)
    return tuple(sorted(paths))
```

**SysfsInventory pattern:** walk `/sys/bus/usb/devices/` for VID:PID `1199:9091`; derive `(line, cdc_wdm, usb_path, ns, iface)` per modem. Called once per cycle (cheap; sysfs is local kernel memory). Returns `list[ModemDescriptor]` matching `InventorySource` Protocol.

**Constructor override pattern** (`store.py` lines 109–123):
```python
def __init__(
    self,
    *,
    state_root_override: Path | None = None,
    run_dir_override: Path | None = None,
) -> None:
    self._state_root = state_root_override or state_root()
    self._run_dir = run_dir_override or run_dir()
```

Apply the same `sysfs_root_override: Path | None = None` pattern to `SysfsInventory` so tests can point at a temporary sysfs tree without production path dependencies.

---

### `src/spark_modem/observer/` (orchestrator, event-driven/batch)

**Analog:** `src/spark_modem/state_store/store.py` (lock acquisition) + RESEARCH.md §2.3 sketch

**TaskGroup + per-task `asyncio.timeout` pattern** (RESEARCH.md §2.3 — mandatory shape):
```python
# observer/orchestrator.py
async def _probe_one(
    modem: Modem,
    qmi: QmiWrapper,
    zao: ZaoLogTailer,
    clock: Clock,
    timeout_s: float = 8.0,
) -> ModemSnapshot:
    try:
        async with asyncio.timeout(timeout_s):
            return await _probe_inner(modem, qmi, zao, clock)
    except TimeoutError:
        return ModemSnapshot.timed_out(modem.usb_path, modem.cdc_wdm, clock.now_iso())
    except Exception as exc:   # NFR-11: never crash the cycle
        logger.exception("probe failed for %s", modem.usb_path, exc_info=exc)
        return ModemSnapshot.errored(modem.usb_path, modem.cdc_wdm, clock.now_iso())

async def observe_all(
    modems: list[Modem],
    qmi: QmiWrapper,
    zao: ZaoLogTailer,
    clock: Clock,
) -> list[ModemSnapshot]:
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(_probe_one(m, qmi, zao, clock)) for m in modems]
    return [t.result() for t in tasks]
```

**Critical:** each `_probe_one` catches ALL exceptions internally. A bare `TaskGroup` wrapping the whole observer is wrong — one probe failure would cancel all sibling tasks. Per-task catch is the correctness requirement.

**Zao-active gate** (FR-10): before calling qmicli, check `zao.is_line_active(modem.line_idx)`. If active, return `ModemSnapshot.zao_active(...)` with zero issues — never QMI-probe a Zao-active line.

**Async lock pattern** (`store.py` lines 147–152 — per-modem asyncio.Lock before sysfs probe):
```python
async with self._modem_locks.get(usb_path):
    async with acquire_flock_async(lock_path, blocking=wait_for_flock):
        await self._save_modem_state_locked(usb_path, state)
```

---

### `src/spark_modem/policy/` (service, transform — pure function)

**Analog:** `src/spark_modem/wire/state.py` + `src/spark_modem/wire/diag.py`

**Purity invariant (CLAUDE.md §1):** The entire `policy/` package must not import `asyncio.subprocess`, `os`, `httpx`, or `subprocess`. Any import of these from within `policy/` is a build failure (`scripts/lint_no_subprocess.sh`).

**`match` statement requirement** (CLAUDE.md anti-patterns — "if/elif instead of match on ModemState is forbidden"):
```python
# policy/transitions.py
def transition(prior: ModemState, snap: ModemSnapshot, ctx: Context) -> ModemState:
    match prior.state:
        case "unknown":
            ...
        case "healthy":
            ...
        case "degraded":
            ...
        case "recovering":
            ...
        case "exhausted":
            ...
```

**Counter decay ordering** (RESEARCH.md §2.4 — ADR-0006, RECOVERY_SPEC §8):
```
1. transition(prior, snap) → new_state
2. if new_state == Healthy: increment _healthy_streak; else: reset to 0
3. if _healthy_streak >= K: decay all counters; reset _healthy_streak to 0
4. action_selection(new_state, snap, ctx)
5. if action selected and not skip: bump action counter
6. atomic_state_write(new_state, counters, _healthy_streak)   ← single fsync
```

Steps 1–5 are in-memory. Step 6 calls `state_store.save_modem_state()`. A crash between 5 and 6 is safe: actions are idempotent; next cycle re-reads pre-action state.

**`model_validator` pattern for state constraints** (`wire/state.py` lines 65–83):
```python
@model_validator(mode="after")
def _check_recovering_level(self) -> ModemState:
    if self.state == "recovering":
        if self.recovering_level is None:
            raise ValueError("recovering_level is required when state == 'recovering'")
    ...
    return self
```

Apply same cross-field validation for any policy result types.

**Field pattern** (`wire/state.py` lines 36–63):
```python
healthy_streak: int = Field(default=0, ge=0, alias="_healthy_streak")
counters: dict[ActionKind, int] = Field(default_factory=dict)
last_action_monotonic: float | None = None
```

---

### `src/spark_modem/actions/<action>.py` + `actions/dispatcher.py` + `actions/verify.py` (service, request-response)

**Analog:** `src/spark_modem/subproc/runner.py` (subprocess invocation) + `src/spark_modem/state_store/store.py` (public/private split)

**Per-action interface** (RESEARCH.md §2.5 — M-04):
```python
# actions/set_apn.py
async def execute(modem: Modem, ctx: ActionContext) -> ActionResult: ...
async def verify(modem: Modem, ctx: ActionContext) -> VerifyResult: ...
```

**Dispatcher registry pattern** (RESEARCH.md §2.5):
```python
# actions/dispatcher.py
_REGISTRY: dict[ActionKind, tuple[ExecuteFn, VerifyFn]] = {
    ActionKind.set_apn: (set_apn.execute, set_apn.verify),
    ActionKind.fix_raw_ip: (fix_raw_ip.execute, fix_raw_ip.verify),
    ...
}

async def execute_and_verify(
    kind: ActionKind,
    modem: Modem,
    ctx: ActionContext,
) -> ActionResult:
    fn_exec, fn_verify = _REGISTRY[kind]
    result = await fn_exec(modem, ctx)
    if result.succeeded:
        verify_result = await fn_verify(modem, ctx)
        return result.with_verify(verify_result)
    return result
```

Phase 4 destructive actions are registered by adding entries to `_REGISTRY` — no dispatcher code changes.

**`_in_critical_section` flag** (`runner.py` lines 167–175 + RESEARCH.md §2.1): state-changing QMI calls (`set_apn`, `sim_power_on`, `soft_reset`) set `qmi_wrapper._in_critical_section = True` before calling `runner.run()`, clear in `finally`. Phase 2 tests assert the flag is set correctly; Phase 3 SIGTERM handler reads it.

**`subproc.run()` invocation pattern** (`runner.py` lines 108–145) — every action calls through `qmi/wrapper.py` → `subproc.run()`:
```python
return await self._runner.run(
    ["qmicli", "--device-open-proxy",
     f"--device={self._device}",
     "--wds-set-ip-family=4"],
    timeout_s=10.0,
)
```

**All errors are data in `verify()`:** `verify()` returns `VerifyResult.deferred()` for `soft_reset` (next-cycle observation). For inline verifications (`set_apn`, `fix_raw_ip`), re-read the specific field via QMI and return `VerifyResult.ok` or `VerifyResult.failed`. The `ActionResult` carries `verify_result` so `actions_total{result=verified_ok|verify_failed|no_verify}` label is populated.

---

### `src/spark_modem/status_reporter/status.py` (service, file-I/O)

**Analog:** `src/spark_modem/state_store/atomic.py`

**`atomic_write_bytes` pattern** (`atomic.py` lines 109–156 — the canonical pattern):
```python
def atomic_write_bytes(
    target: Path | str,
    data: bytes,
    *,
    mode: int = _DEFAULT_MODE,
) -> None:
    target_path = Path(target)
    target_dir = target_path.parent
    nonce = secrets.token_hex(8)
    tmp_path = target_dir / f".{target_path.name}.tmp.{nonce}"

    write_error = _write_and_fsync_temp(tmp_path, data, mode, target_path)
    if write_error is not None:
        with contextlib.suppress(OSError):
            tmp_path.unlink()
        raise write_error

    tmp_path.replace(target_path)
    _fsync_directory(target_dir, target_path)
```

**`status_reporter/status.py` wraps `atomic_write_bytes`** — it does NOT re-implement atomic write. Calls `atomic_write_bytes(status_path, status.model_dump_json().encode("utf-8"))`. The `StatusReport` pydantic model uses `BaseWire` (frozen, extra='forbid') and includes `cycle_index`, `last_modified` (ISO-8601 wall), `carrier_table_sha256`, per-modem state as integer (ADR-0013).

**Atomic write calling pattern** (`store.py` lines 168–170):
```python
target = state_file_for_modem(usb_path, root=self._state_root)
payload = state.model_dump_json(by_alias=True).encode("utf-8")
atomic_write_bytes(target, payload)
```

**`_fsync_directory` Windows guard** (`atomic.py` lines 82–106):
```python
def _fsync_directory(target_dir: Path, target_path: Path) -> None:
    if not hasattr(os, "O_DIRECTORY"):
        return  # Windows: skip
    ...
```

Status writer must use the same guard.

---

### `src/spark_modem/status_reporter/prom.py` (service, request-response)

**No Phase 1 analog.** The Prometheus UDS bridge pattern is defined in RESEARCH.md §2.6.

**Implementation sketch** (RESEARCH.md §2.6 — copy verbatim):
```python
import socket
from socketserver import UnixStreamServer
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler
from prometheus_client import make_wsgi_app
from pathlib import Path

class _UnixWSGIServer(UnixStreamServer, WSGIServer):
    address_family = socket.AF_UNIX

    def server_bind(self) -> None:
        # Do NOT call setsockopt(SO_REUSEADDR) — UDS sockets don't need it
        # and some kernels return ENOPROTOOPT.
        UnixStreamServer.server_bind(self)
        self.setup_environ()

def start_metrics_server(socket_path: Path) -> _UnixWSGIServer:
    socket_path.unlink(missing_ok=True)  # clean stale socket on restart
    server = _UnixWSGIServer(str(socket_path), WSGIRequestHandler)
    server.set_app(make_wsgi_app())
    socket_path.chmod(0o660)
    return server

# In daemon startup:
metrics_task = asyncio.create_task(
    asyncio.to_thread(metrics_server.serve_forever)
)
```

**Metric names** (ADR-0013 + RESEARCH.md §2.6 — integer-encoded, NOT one-hot):
```python
modem_state_value    = Gauge("modem_state_value", "...", ["modem"])
modem_recovering_level = Gauge("modem_recovering_level", "...", ["modem"])
modem_present        = Gauge("modem_present", "...", ["modem"])
modem_rf_blocked     = Gauge("modem_rf_blocked", "...", ["modem"])
cycle_duration_seconds = Histogram("cycle_duration_seconds", "...",
    buckets=[0.5, 1, 2, 4, 8, 16, 32])
cycle_drift_seconds  = Gauge("cycle_drift_seconds", "...")
actions_total        = Counter("actions_total", "...", ["kind", "modem", "result"])
state_duration_seconds = Histogram("state_duration_seconds", "...", ["modem", "state"],
    buckets=[1, 5, 15, 60, 300, 1800, 7200, 86400])
webhook_delivery_total = Counter("webhook_delivery_total", "...", ["result"])
```

---

### `src/spark_modem/webhook/poster.py` (service, event-driven)

**Analog:** `src/spark_modem/wire/webhook.py` (payload types) + RESEARCH.md §2.7

**HMAC signing pattern** (RESEARCH.md §2.7 — over raw body bytes):
```python
body: bytes = envelope.model_dump_json().encode("utf-8")
ts = str(int(time_module.time()))
sig = hmac.new(secret, body, hashlib.sha256).hexdigest()
# Sign over `body` (raw bytes). Do NOT re-serialize after signing.
```

**Host-header DNS trick** (RESEARCH.md §2.7 — W-02):
```python
url = f"https://{cached_ip}{original_path}"
async with httpx.AsyncClient(
    transport=httpx.AsyncHTTPTransport(retries=0),
    verify=True,
    timeout=httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=10.0),
) as client:
    return await client.post(
        url,
        content=body,
        headers={
            "Host": original_host,
            "X-Spark-Signature": f"sha256={sig}",
            "X-Spark-Timestamp": ts,
        },
    )
```

**Dedup table pattern** (RESEARCH.md §2.7):
```python
_dedup_table: dict[tuple[str, str], float] = {}  # (usb_path, kind) → expires_at

def is_deduped(usb_path: str, kind: str, now: float, window_s: float = 60.0) -> bool:
    key = (usb_path, kind)
    if key in _dedup_table and now < _dedup_table[key]:
        return True
    _dedup_table[key] = now + window_s
    return False
```

**Retry queue shape** (W-01): bounded `asyncio.Queue(100)`. Item: `(envelope, attempts_left, next_retry_monotonic)`. Backoff: `[1s, 4s, 16s]`. On exhaustion: increment `webhook_delivery_total{result="dropped"}`, write `webhook_dropped` event via `EventLogWriter`.

**`WebhookEnvelope` type** (`wire/webhook.py` lines 76–87 — the thing that's posted):
```python
class WebhookEnvelope(BaseWire):
    payload: WebhookPayload
    signature_header_value: str = ""
    timestamp_header_value: str = ""
```

Poster fills `signature_header_value` and `timestamp_header_value` before posting.

---

### `src/spark_modem/webhook/dns.py` (utility, request-response)

**Analog:** `src/spark_modem/clock/clock.py` (monotonic-based cache pattern)

**Monotonic cache pattern** (`clock.py` lines 14–29):
```python
def monotonic() -> float:
    return time.monotonic()

def elapsed_since(t0_monotonic: float) -> float:
    return max(0.0, monotonic() - t0_monotonic)
```

**DNS cache class** (RESEARCH.md §2.7 — W-02):
```python
class DnsCache:
    def __init__(self) -> None:
        self._ip: str | None = None
        self._expires_at: float = 0.0      # monotonic
        self._stale_until: float = 0.0     # monotonic; beyond → skipped_no_dns
        self._refresh_interval: float = 60.0
        self._stale_max: float = 600.0     # W-02

    async def resolve(self, host: str, loop: asyncio.AbstractEventLoop) -> str | None:
        now = time.monotonic()
        if self._ip and now < self._expires_at:
            return self._ip
        try:
            infos = await loop.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            self._ip = infos[0][4][0]
            self._expires_at = now + self._refresh_interval
            self._stale_until = now + self._stale_max
            return self._ip
        except OSError:
            if self._ip and now < self._stale_until:
                return self._ip   # stale-but-OK
            return None           # no_dns
```

**`loop.getaddrinfo` semantics:** runs in the default `ThreadPoolExecutor`, not on the event loop thread. The `await` suspends the calling coroutine without blocking the loop. This is the correct non-blocking DNS pattern.

---

### `src/spark_modem/cli/` (controller, request-response)

**Analog:** `src/spark_modem/config/settings.py`

**pydantic-settings import pattern** (`settings.py` lines 1–27):
```python
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
```

**`@classmethod` factory pattern** (`settings.py` lines 161–169):
```python
@classmethod
def from_yaml_layer(cls, yaml_dict: dict[str, Any]) -> Settings:
    return cls(**yaml_dict)
```

**`--explain` output format** (Claude's Discretion — human-readable text default, `--json` structured):
```
modem 2-3.1.1 [cdc-wdm0]: degraded
  issue: registration/not_registered_searching (priority 4)
  gates: signal=pass, backoff=pass, ladder=pass
  action: soft_reset (counter=1/3)

modem 2-3.1.2 [cdc-wdm1]: healthy, no action
```

With `--json`, emit a machine-readable JSON object alongside.

**`ctl maintenance on` dual-clock pattern** (RESEARCH.md §2.8 — C-02):
```python
now_mono = time.monotonic()
expires_mono = now_mono + duration_seconds
expires_iso = (datetime.now(UTC) + timedelta(seconds=duration_seconds)).isoformat()
# Expiry check per cycle:
expired = (now_mono >= expires_mono) or (datetime.now(UTC).isoformat() >= expires_iso)
```

**Maintenance flock pattern** (Claude's Discretion — no new lock surface): `ctl maintenance on/off` acquires the existing state-store flock (`acquire_flock(state_store_lockfile(run=run_dir))`) before reading+updating `globals.json`. Same lock as `store.save_globals()`.

**ICCID/IMSI redaction** (RESEARCH.md §2.8 — C-04):
```python
import hashlib
def redact_pii(value: str) -> str:
    digest = hashlib.sha256(value.encode()).hexdigest()[:8]
    return f"<redacted:{digest}>"
```

---

### `src/spark_modem/daemon/main.py` (orchestrator, event-driven)

**Analog:** `src/spark_modem/state_store/store.py` (async context, lock lifecycle)

**Cycle wake pattern** (RESEARCH.md §2.9 — M-02):
```python
async def _cycle_loop(
    scheduler: CycleScheduler,
    event_queue: asyncio.Queue[CycleEvent],
    shutdown: asyncio.Event,
) -> None:
    while not shutdown.is_set():
        expected_next = scheduler.next_deadline()
        sleep_coro = asyncio.sleep(max(0.0, expected_next - time.monotonic()))
        queue_coro = event_queue.get()

        done, pending = await asyncio.wait(
            {asyncio.ensure_future(sleep_coro),
             asyncio.ensure_future(queue_coro)},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass

        drift = time.monotonic() - expected_next
        cycle_drift_seconds.set(max(0.0, drift))
        scheduler.advance()
        await _run_one_cycle(...)
```

**NFR-11 — policy exception must not crash the cycle** (RESEARCH.md §2.9):
```python
async def _run_one_cycle(ctx: CycleContext) -> None:
    try:
        snapshots = await observer.observe_all(...)
        diag = builder.build_diag(snapshots)
        try:
            plans = policy.engine.run_cycle(diag, ctx.store, ctx.config, ctx.clock)
        except Exception as exc:
            event_logger.emit(PolicyError(exc=repr(exc)))
            plans = []   # skip actions this cycle; continue
        for plan in plans:
            if not plan.is_skip():
                await actions.dispatcher.execute_and_verify(plan.kind, plan.who, ctx)
    except Exception as exc:
        event_logger.emit(CycleCrashed(exc=repr(exc)))
```

**StateStore constructor pattern** (`store.py` lines 109–123 — override for test isolation):
```python
def __init__(
    self,
    *,
    state_root_override: Path | None = None,
    run_dir_override: Path | None = None,
) -> None:
    self._state_root = state_root_override or state_root()
```

**Cross-check pattern** (`store.py` lines 260–269): daemon startup must call `cross_check_inventory_for(usb_path, walker)` for every usb_path in `list_modem_state_usb_paths()` before any `load_modem_state()` call. On `UsbPathMismatch`, refuse to start.

---

## Test Seam Pattern Assignments

### `tests/fakes/runner.py` — `FakeRunner` (test-fake)

**Analog:** `tests/unit/subproc/test_runner_data_errors.py` (what callers expect from `run()`)

**Interface the fake must satisfy** (`runner.py` lines 108–145 — same call surface):
```python
# tests/fakes/runner.py
class FakeRunner:
    """Maps argv lists to canned CompletedProcess results for tests.

    Usage:
        runner = FakeRunner()
        runner.register(["qmicli", "--device-open-proxy", ...], CompletedProcess(...))
        wrapper = QmiWrapper(runner=runner, device="/dev/cdc-wdm0")
    """

    def __init__(self) -> None:
        self._responses: dict[tuple[str, ...], CompletedProcess] = {}
        self._calls: list[list[str]] = []

    def register(self, argv: list[str], result: CompletedProcess) -> None:
        self._responses[tuple(argv)] = result

    async def run(
        self,
        argv: list[str],
        *,
        timeout_s: float,
        stdin: bytes | None = None,
        env: dict[str, str] | None = None,
    ) -> CompletedProcess:
        self._calls.append(argv)
        key = tuple(argv)
        if key not in self._responses:
            raise KeyError(f"FakeRunner: no canned response for {argv!r}")
        return self._responses[key]
```

**`CompletedProcess.make()` pattern** (`subproc/result.py` — use same factory for canned results in tests):
```python
from spark_modem.subproc.result import CompletedProcess

canned = CompletedProcess.make(
    argv=["qmicli", "--device-open-proxy", "--device=/dev/cdc-wdm0", ...],
    exit_code=0,
    stdout=fixture_bytes,
    stderr=b"",
    duration_monotonic=0.01,
    timed_out=False,
    kill_signal=None,
)
```

---

### `tests/fakes/clock.py` — `FakeClock` (test-fake)

**Analog:** `src/spark_modem/clock/clock.py`

**Clock module interface** (`clock.py` lines 14–39 — the surface to fake):
```python
def monotonic() -> float: ...
def elapsed_since(t0_monotonic: float) -> float: ...
def wall_clock_iso(*, tz: tzinfo | None = None) -> str: ...
```

**FakeClock pattern** (RESEARCH.md references `FakeClock` as existing project convention from TEST_STRATEGY.md §8):
```python
class FakeClock:
    """Deterministic, asyncio-compatible clock for tests.

    Call advance(seconds) to move time forward without wall-clock delay.
    """
    def __init__(self, start: float = 0.0) -> None:
        self._monotonic = start
        self._wall_iso = "2026-01-01T00:00:00+00:00"

    def monotonic(self) -> float:
        return self._monotonic

    def elapsed_since(self, t0: float) -> float:
        return max(0.0, self._monotonic - t0)

    def wall_clock_iso(self) -> str:
        return self._wall_iso

    def advance(self, seconds: float) -> None:
        self._monotonic += seconds
```

---

### `tests/fakes/webhook.py` — `FakeWebhookPoster` (test-fake)

**Analog:** `src/spark_modem/wire/webhook.py` (payload types) + `src/spark_modem/event_logger/writer.py` (append-and-record pattern)

**Interface to satisfy:**
```python
class FakeWebhookPoster:
    """Records envelopes sent by the poster for test assertions.

    Implements the WebhookPoster Protocol (co-located in webhook/poster.py).
    """

    def __init__(self) -> None:
        self.sent: list[WebhookEnvelope] = []
        self.dropped: list[WebhookEnvelope] = []

    async def enqueue(self, envelope: WebhookEnvelope) -> None:
        self.sent.append(envelope)

    async def drain(self, budget_seconds: float = 3.0) -> None:
        pass  # no-op in tests; all items already "sent" on enqueue
```

---

### `tests/fakes/inventory.py` — `FixtureInventory` (test-fake)

**Analog:** `src/spark_modem/state_store/store.py` (constructor override for test isolation)

**Interface to satisfy** (implements `InventorySource` Protocol):
```python
class FixtureInventory:
    """Reads inventory snapshots from tests/fixtures/inventory/<scenario>.json.

    Usage:
        inventory = FixtureInventory(Path("tests/fixtures/inventory/four_modems.json"))
        modems = await inventory.scan()
    """

    def __init__(self, fixture_path: Path) -> None:
        self._path = fixture_path

    async def scan(self) -> list[ModemDescriptor]:
        raw = json.loads(self._path.read_bytes())
        return [ModemDescriptor.model_validate(m) for m in raw["modems"]]
```

Fixture JSON shape: `{"modems": [{"line": 0, "cdc_wdm": "cdc-wdm0", "usb_path": "2-3.1.1", ...}]}`.

**pydantic model_validate** (`store.py` lines 256–258 — same pattern):
```python
state = ModemState.model_validate(raw)
```

---

### `tests/fakes/dns.py` — `FakeDNSResolver` (test-fake)

**Interface to satisfy** (implements `DnsCache.resolve()` surface):
```python
class FakeDNSResolver:
    """Returns canned IPs for test assertions; never makes real network calls."""

    def __init__(self, canned_ip: str = "192.0.2.1") -> None:
        self._ip = canned_ip
        self._fail_next: bool = False

    async def resolve(self, host: str, loop: object = None) -> str | None:
        if self._fail_next:
            self._fail_next = False
            return None
        return self._ip

    def set_fail_next(self) -> None:
        self._fail_next = True
```

---

### `tests/replay/test_v1_agreement.py` (test, batch)

**Analog:** `tests/unit/state_store/test_store.py` (pytest parametrize + tmp_path isolation)

**Fixture layout pattern** (`test_store.py` lines 61–65):
```python
def _make_store(tmp_path: Path) -> StateStore:
    return StateStore(
        state_root_override=tmp_path / "state",
        run_dir_override=tmp_path / "run",
    )
```

**Test structure** (RESEARCH.md §2.10):
```python
# tests/replay/test_v1_agreement.py
FIXTURE_DIR = Path("tests/fixtures/replay")

def _load_fixtures() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(FIXTURE_DIR.rglob("*.json"))]

@pytest.mark.parametrize("fixture", _load_fixtures(), ids=lambda f: f["scenario"])
async def test_v1_agreement(fixture: dict) -> None:
    diag = Diag.model_validate(fixture["diag"])
    prior = ModemState.model_validate(fixture["prior_state"])
    expected = fixture["expected_v1_actions"]
    is_fault = fixture["fault_cycle"]

    plans = policy.engine.run_cycle(diag, ...)
    classification = classify(plans, expected, fixture.get("v1_succeeded"))
    # "safer" counts as agreement; "less-safe" fails the cycle
    if is_fault:
        assert classification in ("agree", "safer", "both-skip")
```

**Aggregate gate** (R-03):
```python
def test_fault_cycle_agreement_rate(fixture_results: list[str]) -> None:
    fault_cycles = [r for r in fixture_results if r["fault_cycle"]]
    agreements = [r for r in fault_cycles if r["classification"] in ("agree", "safer", "both-skip")]
    rate = len(agreements) / len(fault_cycles) if fault_cycles else 1.0
    assert rate >= 0.95, f"Fault-cycle agreement {rate:.1%} < 95% ({len(agreements)}/{len(fault_cycles)})"
```

**`pytest.mark.skipif` pattern** (`test_runner_data_errors.py` lines 17–21):
```python
_SKIP_WIN = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Requires POSIX binaries; production target is Jetson",
)
```

Apply `skipif(win32)` to any replay test that calls into POSIX-only paths (flock, sysfs).

---

## Shared Patterns

### Atomic File Write
**Source:** `src/spark_modem/state_store/atomic.py` lines 109–156
**Apply to:** `status_reporter/status.py`, any other file that writes JSON to disk
```python
from spark_modem.state_store.atomic import atomic_write_bytes
# ...
payload = model.model_dump_json(by_alias=True).encode("utf-8")
atomic_write_bytes(target_path, payload)
```
Never re-implement temp+rename+fsync. Always call `atomic_write_bytes`.

### Pydantic Wire Boundary (extra='forbid')
**Source:** `src/spark_modem/wire/_base.py` lines 14–22
**Apply to:** `StatusReport`, `ZaoSnapshot`, `ModemDescriptor`, `ActionResult`, all new wire shapes
```python
class BaseWire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)
```

### Parser Boundary (extra='ignore')
**Source:** RESEARCH.md §2.1 + `wire/_base.py` (contrast)
**Apply to:** all `qmi/parsers/<intent>.py` models
```python
class GetSignalResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
```

### Monotonic Clock for Durations / Backoffs
**Source:** `src/spark_modem/clock/clock.py` lines 14–29
**Apply to:** `webhook/dns.py`, `policy/gates.py`, `daemon/main.py`, any backoff logic
```python
from spark_modem.clock.clock import monotonic, elapsed_since
# Never time.time() for durations. Only time.time() for ISO-8601 stamps.
```

### `asyncio.Lock` + `flock` Lock-Acquisition Order
**Source:** `src/spark_modem/state_store/store.py` lines 128–152 + `state_store/locks.py` lines 256–288
**Apply to:** `observer/`, `cli/` mutating commands, `daemon/main.py`
```python
# Order: asyncio.Lock FIRST, flock SECOND. Always.
async with self._modem_locks.get(usb_path):
    async with acquire_flock_async(lock_path, blocking=wait_for_flock):
        await self._save_modem_state_locked(usb_path, state)
```

### `model_dump_json` / `model_validate_json` Everywhere
**Source:** `src/spark_modem/state_store/store.py` lines 169 + 256
**Apply to:** all JSON serialization in Phase 2 code
```python
payload = state.model_dump_json(by_alias=True).encode("utf-8")
state = ModemState.model_validate(raw)
```
Never `json.loads` into untyped dicts in production code. All deserialization goes through pydantic.

### Windows Guard Pattern (POSIX-only features)
**Source:** `src/spark_modem/subproc/runner.py` lines 245–260 + `state_store/locks.py` lines 45–51
**Apply to:** `status_reporter/prom.py` (UDS socket), any `os.O_DIRECTORY` / `os.killpg` usage
```python
if sys.platform != "win32":
    # POSIX path
else:
    # Windows dev-host fallback or skip
```

### `from __future__ import annotations`
**Source:** Every Phase 1 source file (line 1)
**Apply to:** Every new `.py` file in Phase 2
Required for forward-reference annotations under `mypy --strict`.

### Event Log Append
**Source:** `src/spark_modem/event_logger/writer.py` lines 92–105
**Apply to:** `actions/dispatcher.py` (ActionPlanned, ActionExecuted), `daemon/main.py` (cycle events), `webhook/poster.py` (webhook_dropped, webhook_pending)
```python
from spark_modem.event_logger.writer import EventLogWriter
# writer is passed via context; do not construct per-call
writer.append(ActionExecuted(ts_iso=clock.wall_clock_iso(), ...))
```

### `conftest.py` directory markers
**Source:** `tests/conftest.py` lines 1–28
**Apply to:** New test files in `tests/unit/`, `tests/replay/`
Tests are auto-marked by directory location. Do not add `@pytest.mark.unit` by hand.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `src/spark_modem/status_reporter/prom.py` | service | request-response | No Prometheus UDS bridge exists in Phase 1; pattern comes from RESEARCH.md §2.6 |
| `tests/fixtures/zao_log/*.log` | fixture | — | No log-file fixtures exist yet; format is plain-text Zao log lines containing `RASCOW_STAT` blocks |

---

## Metadata

**Analog search scope:** `src/spark_modem/` (31 files across 7 packages), `tests/unit/` (38 test files), `tests/conftest.py`
**Files scanned (Read tool):** `subproc/runner.py`, `state_store/store.py`, `state_store/atomic.py`, `state_store/locks.py`, `wire/_base.py`, `wire/state.py`, `wire/diag.py`, `wire/webhook.py`, `wire/events.py`, `clock/clock.py`, `event_logger/writer.py`, `config/settings.py`, `tests/conftest.py`, `tests/unit/subproc/test_runner_data_errors.py`, `tests/unit/state_store/test_store.py`
**Pattern extraction date:** 2026-05-06
