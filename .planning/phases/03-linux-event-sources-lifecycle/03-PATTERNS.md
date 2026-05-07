# Phase 3: Linux Event Sources & Lifecycle - Pattern Map

**Mapped:** 2026-05-07
**Files analyzed:** 25 production + 14 modified + 30+ test files
**Analogs found:** 39 / 39

## File Classification

### Production code (new)

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `src/spark_modem/inventory/udev.py` | inventory impl (Protocol satisfier) | event-driven → on-demand sysfs scan | `src/spark_modem/inventory/sysfs.py` | exact (same Protocol; swap polling for event-pushed wake) |
| `src/spark_modem/inventory/netns.py` | utility (sysfs walk helper) | request-response (file-I/O) | `src/spark_modem/inventory/sysfs.py` `_find_cdc_wdm` / `_find_wwan_iface` | role-match (sysfs accessor co-located with inventory) |
| `src/spark_modem/event_sources/__init__.py` | package marker | n/a | `src/spark_modem/observer/__init__.py` | role-match |
| `src/spark_modem/event_sources/supervisor.py` | supervisor wrapper + WakeSignal enum | event-driven (TaskGroup child supervision) | `src/spark_modem/observer/orchestrator.py` (TaskGroup + per-task isolation) + `src/spark_modem/wire/enums.py` (StrEnum closed values) | role-match (TaskGroup pattern + closed enum) |
| `src/spark_modem/event_sources/udev_producer.py` | event-source producer | streaming (kernel netlink → wake signal) | `src/spark_modem/observer/orchestrator.py` (asyncio task with try/finally cleanup) | role-match (long-lived async task with own exception isolation) |
| `src/spark_modem/event_sources/rtnetlink_producer.py` | event-source producer | streaming (rtnetlink async iter → wake signal) | `src/spark_modem/observer/orchestrator.py` | role-match |
| `src/spark_modem/event_sources/kmsg_producer.py` | event-source producer | streaming (`/dev/kmsg` add_reader → wake + Issue) | `src/spark_modem/observer/orchestrator.py` + `src/spark_modem/zao_log/parser.py` (regex+parse) | role-match |
| `src/spark_modem/event_sources/asyncinotify_producer.py` | event-source producer | streaming (inotify async iter → reopen dispatch) | `src/spark_modem/observer/orchestrator.py` | role-match |
| `src/spark_modem/kmsg/__init__.py` | package marker | n/a | `src/spark_modem/zao_log/__init__.py` | role-match |
| `src/spark_modem/kmsg/classifier.py` | utility (regex → enum classifier) | transform (line → IssueDetail) | `src/spark_modem/zao_log/parser.py` (regex match → typed snapshot) | role-match |
| `src/spark_modem/kmsg/dedup.py` | utility (sliding-window dedup) | transform (event → emit-or-suppress) | `src/spark_modem/webhook/dedup.py` `DedupTable` | exact (same call shape: `is_deduped`, `consume_count`, monotonic-clock-injected) |
| `src/spark_modem/zao_log/inotify_tailer.py` | tailer impl (Protocol satisfier) | streaming (inotify → snapshot) | `src/spark_modem/zao_log/parser.py` (`ZaoLogParser`) | exact (same `ZaoLogTailer` Protocol surface) |
| `src/spark_modem/daemon/lifecycle.py` | lifecycle service (sd_notify wrapper, signals, marker, PID lock) | request-response (init), event-driven (signal handlers) | `src/spark_modem/state_store/locks.py` (flock primitive) + `src/spark_modem/state_store/atomic.py` (atomic marker write) | role-match |
| `src/spark_modem/daemon/sighup.py` | reload coordinator | event-driven (SIGHUP → transactional swap) | `src/spark_modem/config/reload_marker.py` + `src/spark_modem/config/settings.py` | role-match |
| `src/spark_modem/daemon/sigterm.py` | shutdown coordinator (8-step choreography) | event-driven (SIGTERM → ordered teardown) | `src/spark_modem/webhook/poster.py` `drain()` + `src/spark_modem/daemon/cycle_driver.py` step ordering | role-match |
| `src/spark_modem/daemon/preflight.py` | preflight gate (PATH check + Settings validate) | request-response (one-shot at startup) | `src/spark_modem/state_store/inventory.py` cross-check + `src/spark_modem/subproc/runner.py` | role-match |
| `src/spark_modem/event_logger/inotify_reopener.py` | dispatcher (inotify → writer.reopen()) | event-driven (inotify event → method call) | `src/spark_modem/observer/orchestrator.py` | role-match |

### Production code (modified)

| Modified File | Role | Change Type | Closest Analog Section |
|---------------|------|-------------|------------------------|
| `src/spark_modem/inventory/sysfs.py` | inventory impl | extension (call `derive_ns()`) | self (lines 73-83 — descriptor construction) |
| `src/spark_modem/inventory/descriptor.py` | wire model | field semantic change (ns populated, not None) | self (line 21 — already typed `str \| None`) |
| `src/spark_modem/wire/enums.py` | closed enums | append (5+1 new IssueDetail values) | self (lines 23-67 — existing IssueDetail variants) |
| `src/spark_modem/qmi/wrapper.py` | qmicli wrapper | extension (auto-prepend `ip netns exec`) | self (lines 128-160 — argv construction sites) |
| `src/spark_modem/event_logger/writer.py` | log writer | extension (`reopen()`, deque buffer) | self (lines 81-107 — fd lifecycle + append) |
| `src/spark_modem/daemon/main.py` | daemon entry | rewrite (single-cycle → event loop with TaskGroup) | self + `src/spark_modem/observer/orchestrator.py` (TaskGroup wrapping) |

### Test seams (new)

| New Test File | Role | Data Flow | Closest Analog | Match Quality |
|---------------|------|-----------|----------------|---------------|
| `tests/fakes/udev.py` | test fake (event injector) | event-driven (test pushes events) | `tests/fakes/zao_log.py` (FixtureZaoTailer) + `tests/fakes/runner.py` (FakeRunner records calls) | role-match |
| `tests/fakes/rtnetlink.py` | test fake | event-driven | `tests/fakes/runner.py` | role-match |
| `tests/fakes/asyncinotify.py` | test fake | event-driven | `tests/fakes/runner.py` | role-match |
| `tests/fakes/kmsg.py` | test fake (canned dmesg lines) | streaming | `tests/fakes/runner.py` | role-match |
| `tests/fakes/sdnotify.py` | test fake (records notify calls) | request-response | `tests/fakes/runner.py` (records calls list) + `tests/fakes/webhook.py` (sent list) | exact (call-recording fake) |
| `tests/fakes/pidlock.py` | test fake (asyncio.Lock fallback) | request-response | `tests/fakes/dns.py` (one-shot fail flag) | role-match |
| `tests/unit/event_sources/test_supervisor.py` | unit test | structured concurrency | `tests/unit/observer/test_orchestrator.py` | role-match |
| `tests/unit/event_sources/test_udev_producer.py` | unit test | event injection | `tests/unit/zao_log/test_parser.py` | role-match |
| `tests/unit/event_sources/test_rtnetlink_producer.py` | unit test | event injection | `tests/unit/zao_log/test_parser.py` | role-match |
| `tests/unit/event_sources/test_kmsg_producer.py` | unit test | event injection | `tests/unit/zao_log/test_parser.py` | role-match |
| `tests/unit/event_sources/test_asyncinotify_producer.py` | unit test | event injection | `tests/unit/zao_log/test_parser.py` | role-match |
| `tests/unit/kmsg/test_classifier.py` | unit test (table-driven regex) | transform | `tests/unit/zao_log/test_parser.py` (fixture-driven) | role-match |
| `tests/unit/kmsg/test_dedup.py` | unit test (windowed dedup) | transform | `tests/unit/webhook/test_dedup.py` | exact |
| `tests/unit/daemon/test_lifecycle_sd_notify.py` | unit test | sd_notify wrapper | `tests/unit/daemon/test_cycle_scheduler.py` | role-match |
| `tests/unit/daemon/test_sigterm_choreography.py` | unit test (8-step ordering) | event sequence | `tests/unit/webhook/` poster tests | role-match |
| `tests/unit/daemon/test_sighup_swap.py` | unit test (transactional swap) | request-response | `tests/unit/config/test_settings.py` + `test_reload_marker.py` | role-match |
| `tests/unit/daemon/test_clean_shutdown_marker.py` | unit test (atomic JSON marker IO) | file-I/O | `tests/unit/state_store/test_atomic.py` | role-match |
| `tests/unit/daemon/test_pid_lock.py` | unit test (POSIX-only flock) | cross-process file lock | `tests/unit/state_store/test_locks.py` | exact |
| `tests/unit/daemon/test_sim_swap_detection.py` | unit test (cycle-driver ICCID compare) | request-response | `tests/unit/daemon/test_cycle_driver.py` (full pipeline) | role-match |
| `tests/unit/inventory/test_udev_inventory.py` | unit test | event-driven scan | `tests/unit/inventory/test_sysfs.py` | exact (same Protocol; analogous fixture-tree pattern) |
| `tests/unit/inventory/test_netns_derivation.py` | unit test | sysfs link read | `tests/unit/inventory/test_sysfs.py` (`_materialise_sierra_modem`) | role-match |
| `tests/unit/zao_log/test_inotify_tailer_dual_mode.py` | unit test (logrotate scenarios) | streaming | `tests/unit/zao_log/test_parser.py` | role-match |
| `tests/unit/event_logger/test_writer_reopen.py` | unit test (reopen + buffer) | file-I/O | `tests/unit/event_logger/test_writer.py` (existing) | role-match |
| `tests/integration/test_lifecycle.py` | integration (Linux runner) | event-driven end-to-end | `tests/unit/daemon/test_cycle_driver.py` (end-to-end shape) | role-match |
| `tests/integration/test_logrotate_create.py` | integration | streaming + filesystem | `tests/unit/zao_log/test_parser.py` (fixture-driven) | role-match |
| `tests/integration/test_unit_file_audit.py` | integration (parse `.service`) | text parsing | `tests/integration/test_default_carrier_table.py` | role-match |

### Other (new / modified)

| File | Role | Closest Analog |
|------|------|----------------|
| `debian/spark-modem-watchdog.service` (modified) | systemd unit | self (Phase 1 baseline; lines 21-71) |
| `debian/spark-modem-watchdog.logrotate` (new) | logrotate snippet | n/a — first one in repo; pattern from RESEARCH.md R-02 |

---

## Pattern Assignments

### `src/spark_modem/inventory/udev.py` (inventory, event-driven)

**Analog:** `src/spark_modem/inventory/sysfs.py`

**Imports + module docstring** (sysfs.py lines 1-13):
```python
"""SysfsInventory - Phase 2 implementation of InventorySource via sysfs walk.

Reads /sys/bus/usb/devices/ for VID:PID 1199:9091 (Sierra EM7421) entries.
Phase 3 swaps in a UdevInventory backed by pyudev.Monitor; observer/
does not change.
"""
from __future__ import annotations
from pathlib import Path
from typing import Final
from spark_modem.inventory.descriptor import ModemDescriptor

_SIERRA_VID: Final[str] = "1199"
_EM7421_PID: Final[str] = "9091"
```

**Class skeleton + `scan()` shape** (sysfs.py lines 23-83):
```python
class SysfsInventory:
    def __init__(self, *, sysfs_root_override: Path | None = None) -> None:
        self._sysfs_root = sysfs_root_override or Path("/sys")

    async def scan(self) -> list[ModemDescriptor]:
        # ... walk sysfs, build descriptors ...
        descriptors.append(
            ModemDescriptor(
                line=line, cdc_wdm=cdc_wdm, usb_path=usb_path,
                ns=None, iface=iface,
            )
        )
        return descriptors
```

**Pattern to copy:** UdevInventory keeps the `scan() -> list[ModemDescriptor]` Protocol surface from `inventory/protocol.py`; the producer pushes wake signals while `scan()` does the same on-demand sysfs walk (E-02: state derives from re-observation). UdevInventory may delegate the actual walk to a shared internal helper that `SysfsInventory.scan` also uses.

---

### `src/spark_modem/inventory/netns.py` (utility, file-I/O)

**Analog:** `src/spark_modem/inventory/sysfs.py` (helper methods at lines 108-127)

**Helper-method pattern** (lines 108-127):
```python
@staticmethod
def _find_cdc_wdm(resolved: Path) -> str | None:
    """Search children for a cdc-wdmN node and return the basename."""
    for misc in resolved.rglob("usbmisc/cdc-wdm*"):
        if misc.is_dir() or misc.is_symlink():
            return misc.name
    return None

@staticmethod
def _find_wwan_iface(resolved: Path) -> str | None:
    """Search children for a wwanN net interface and return its basename."""
    for net in resolved.rglob("net/wwan*"):
        if net.is_dir() or net.is_symlink():
            return net.name
    return None
```

**Pattern to copy:** netns.py exposes `derive_ns(usb_dev_path: Path) -> str | None` as a module-level pure function (mirrors the staticmethod shape: same nullable return, same skip-on-missing semantics). Called from `SysfsInventory.scan()` at descriptor-construction time; ns name read from cdc-wdm parent's sysfs link or `/var/run/netns/` walk (planner picks the most-stable read).

---

### `src/spark_modem/event_sources/supervisor.py` (supervisor + closed enum)

**Analog 1 (TaskGroup + per-child isolation):** `src/spark_modem/observer/orchestrator.py`

**Per-task exception isolation pattern** (orchestrator.py lines 63-91):
```python
async def _probe_one(modem, qmi_factory, zao, clock, timeout_s) -> ModemSnapshot:
    """Per-modem probe with own try/except - never propagates to TaskGroup."""
    try:
        async with asyncio.timeout(timeout_s):
            return await probe_modem_to_snapshot(modem, qmi_factory(modem), clock)
    except TimeoutError:
        logger.warning("probe timed out for %s", modem.usb_path)
        return _timed_out_snapshot(modem)
    except Exception:  # NFR-11: never crash the cycle - errors are data
        logger.exception("probe failed for %s", modem.usb_path)
        return _errored_snapshot(modem)
```

**Analog 2 (closed StrEnum):** `src/spark_modem/wire/enums.py`

**Closed-enum pattern** (enums.py lines 145-153):
```python
class DaemonStopReason(StrEnum):
    """Reason enum on daemon_stopped events / DaemonRestart webhooks (M-6)."""
    SIGTERM = "sigterm"
    CRASH = "crash"
    CONFIG_INVALID = "config_invalid"
    OOM = "oom"
    KILL = "kill"
```

**Pattern to copy:** `class WakeSignal(StrEnum): UDEV; RTNETLINK; ZAO_LOG; EVENTS_LOG_ROTATED; KMSG`. `restart_on_crash(name, factory, *, sleeper, event_logger, backoffs=...)` wraps each producer; catches `Exception` only (passes through `CancelledError`); emits `event_source_crashed{source=name}`; sleeps via injected `Sleeper` Protocol (PITFALLS §14.1) so FakeClock-driven tests don't hang; resets attempt counter after >5 min uptime success. RESEARCH.md Pattern 1 lines 339-368 give the exact body.

---

### `src/spark_modem/event_sources/udev_producer.py` (producer, streaming)

**Analog:** `src/spark_modem/observer/orchestrator.py` (long-lived task with `try/finally`)

**Imports + Protocol pattern** (orchestrator.py lines 11-37):
```python
from __future__ import annotations
import asyncio
import logging
from collections.abc import Callable
from typing import Final, Protocol
from spark_modem.inventory.descriptor import ModemDescriptor
# ...

logger = logging.getLogger(__name__)
DEFAULT_PROBE_TIMEOUT_S: Final[float] = 8.0

class ClockProto(Protocol):
    """Subset of the Clock surface used by the orchestrator (test-shimmable)."""
    def monotonic(self) -> float: ...
    def wall_clock_iso(self) -> str: ...
```

**Pattern to copy:** Co-located `_EventQueueProto` (`def put_nowait(self, item: object) -> None: ...`); RESEARCH.md Pattern 2 lines 1140-1184 give the body shape (`pyudev.Monitor.from_netlink` + `set_receive_buffer_size(4 MiB)` + `loop.add_reader(monitor.fileno(), on_readable)` + drain loop in callback + `await asyncio.Future()` to sleep until cancelled + `loop.remove_reader(fd)` in `finally`). NEVER `MonitorObserver` (PITFALLS §7.1).

---

### `src/spark_modem/event_sources/rtnetlink_producer.py` (producer, streaming)

**Analog:** `src/spark_modem/observer/orchestrator.py` (async context manager + `try/finally`)

**Pattern to copy:** Tight read loop only — body is `event_queue.put_nowait(WakeSignal.RTNETLINK)`. NO parsing, NO state, NO logging. RESEARCH.md Pattern 3 lines 1196-1213:
```python
async with AsyncIPRoute() as ipr:
    ipr.asyncore.socket.setsockopt(
        socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024
    )
    await ipr.bind(groups=rtnl.RTMGRP_LINK)
    async for _msg in ipr.get():
        event_queue.put_nowait(WakeSignal.RTNETLINK)
```

ENOBUFS escapes the producer task; `restart_on_crash` wrapper restarts factory (PITFALLS §6.1). NEVER sync `IPRoute` (anti-pattern).

---

### `src/spark_modem/event_sources/kmsg_producer.py` (producer, streaming)

**Analog 1 (event source structure):** `src/spark_modem/observer/orchestrator.py`

**Analog 2 (regex parsing):** `src/spark_modem/zao_log/parser.py` lines 28-33:
```python
_RASCOW_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z))"
    r".*RASCOW_STAT.*\bline=(?P<line>\d+)\b.*\bstatus=(?P<status>\w+)\b"
)
```

**Pattern to copy:** RESEARCH.md Pattern 5 lines 1248-1297 give the exact body — `os.open(KMSG_DEV, os.O_RDONLY | os.O_NONBLOCK)` + `os.lseek(fd, 0, os.SEEK_END)` to skip historical buffer; `loop.add_reader(fd, on_readable)`; on_readable does a non-blocking `os.read(fd, 8192)` loop until `BlockingIOError` (drained); parses `<priority>,<sequence>,<timestamp>,<flags>;<message>` header; tracks last_seq for gap detection; calls `classifier(line)` then `dedup.should_emit(detail)` then emits Issue + wake signal; `loop.remove_reader(fd)` + `os.close(fd)` in finally.

---

### `src/spark_modem/event_sources/asyncinotify_producer.py` (producer, streaming)

**Analog:** `src/spark_modem/observer/orchestrator.py` + `src/spark_modem/zao_log/parser.py`

**Pattern to copy:** RESEARCH.md Pattern 4 lines 411-475. Single producer task watches BOTH `/var/log/spark-modem-watchdog/` (events.jsonl rotate → `EventLogWriter.reopen()`) AND `/var/log/zao/` (Zao log rotate → `ZaoLogInotifyTailer.reopen()`); two `add_watch` return values dispatched on `event.watch`. Mask: `Mask.MODIFY | Mask.MOVE_SELF | Mask.DELETE_SELF | Mask.CLOSE_WRITE` on file + `Mask.CREATE | Mask.MOVED_TO` on parent dir (PITFALLS §8.1, §8.2). On MODIFY: compare `os.fstat(fd).st_size` vs `last_offset` (copytruncate), opportunistic inode compare (R-04). Coalesce — drain all pending events before reacting.

---

### `src/spark_modem/kmsg/classifier.py` (utility, transform)

**Analog:** `src/spark_modem/zao_log/parser.py` (lines 28-105 — regex-driven typed-output parser)

**Regex catalog pattern** (parser.py lines 28-33 — see kmsg_producer above)

**Module-level decode discipline** (parser.py lines 80-82):
```python
# ascii decode with errors="replace" tolerates malformed lines without
# raising (T-02-03-01).
text = raw.decode("ascii", errors="replace")
```

**Pattern to copy:** RESEARCH.md lines 547-555:
```python
KMSG_PATTERNS: list[tuple[re.Pattern[str], IssueDetail]] = [
    (re.compile(r"USB \S+: device not accepting address"),  IssueDetail.usb_enum_failure),
    (re.compile(r"over-current.*on port"),                    IssueDetail.usb_overcurrent),
    (re.compile(r"thermal.*throttl(ing|ed)"),                 IssueDetail.thermal_throttle),
    (re.compile(r"qmi_wwan.*probe.*fail(ed)?"),               IssueDetail.qmi_wwan_probe_fail),
    (re.compile(r"tegra-xusb.*power.*loss"),                  IssueDetail.tegra_hub_psu_droop),
]
```

`def classify(line: str) -> IssueDetail`: scans patterns in order, returns first match or `IssueDetail.UNKNOWN` (E-03). Closed-enum return — never free-form string.

---

### `src/spark_modem/kmsg/dedup.py` (utility, transform)

**Analog:** `src/spark_modem/webhook/dedup.py` `DedupTable` (lines 19-55)

**Full class shape** (dedup.py lines 19-55):
```python
class DedupTable:
    """Per-(modem, kind) cooldown table with suppressed-count accumulation."""

    def __init__(self, *, window_seconds: float = 60.0) -> None:
        self._window = window_seconds
        self._expires_at: dict[tuple[str, str], float] = {}
        self._suppressed: dict[tuple[str, str], int] = {}

    def is_deduped(self, modem: str, kind: str, *, now_monotonic: float) -> bool:
        key = (modem, kind)
        expires = self._expires_at.get(key, 0.0)
        if now_monotonic < expires:
            self._suppressed[key] = self._suppressed.get(key, 0) + 1
            return True
        self._expires_at[key] = now_monotonic + self._window
        return False

    def consume_dedup_count(self, modem: str, kind: str) -> int:
        key = (modem, kind)
        return self._suppressed.pop(key, 0)
```

**Pattern to copy:** Identical shape, swap key from `(modem, kind)` to `(detail,)`, default `window_seconds=30.0`. Caller passes `now_monotonic` — module is pure-Python (no clock import). Field assertion: monotonic time only (CLAUDE.md invariant #4).

---

### `src/spark_modem/zao_log/inotify_tailer.py` (tailer impl, streaming)

**Analog:** `src/spark_modem/zao_log/parser.py` (`ZaoLogParser`)

**Class signature + Protocol satisfaction** (parser.py lines 36-67):
```python
class ZaoLogParser:
    """Reads the entire Zao log on demand and returns the latest block.

    Satisfies `spark_modem.zao_log.protocol.ZaoLogTailer`. Phase 2 file-read
    fallback; Phase 3 swaps in an inotify-backed tailer behind the same
    Protocol surface.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def is_line_active(self, line_idx: int) -> bool:
        """FR-10 gate: True iff Zao is currently bonding `line_idx`."""
        return self.snapshot().is_line_active(line_idx)

    def snapshot(self) -> ZaoSnapshot:
        # ... read & parse ...
```

**Pattern to copy:** Same `is_line_active(line_idx) -> bool` + `snapshot() -> ZaoSnapshot` Protocol surface (`zao_log/protocol.py`). Internally: incremental tail (last_offset + last_inode tracked across reads); on MODIFY append to internal buffer + re-parse latest block; on copytruncate reset offset; on rotate reopen via parent-dir watch (R-04). The existing `_RASCOW_RE` regex (parser.py line 30) is reused; the `_parse_bytes` block-walking logic (parser.py lines 70-111) is the same — only the "where does `raw` come from" changes.

---

### `src/spark_modem/daemon/lifecycle.py` (lifecycle service)

**Analog 1 (PID lock — flock primitive):** `src/spark_modem/state_store/locks.py` lines 108-161

**flock acquisition shape** (locks.py lines 108-161):
```python
@contextlib.contextmanager
def acquire_flock(
    path: Path | str,
    *,
    blocking: bool = False,
    write_pid: bool = True,
) -> Iterator[int]:
    """Acquire an exclusive flock on ``path`` (POSIX only).

    Raises:
        StateStoreLocked: when blocking=False and the lock is held by another.
    """
    if not _FCNTL_AVAILABLE:
        raise ImportError("fcntl is not available on this platform (POSIX only)")
    path_p = Path(path)
    path_p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path_p), os.O_CREAT | os.O_RDWR, 0o640)
    try:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(fd, flags)
        except OSError as e:
            if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                holder_pid = _read_pid_from(path_p)
                raise StateStoreLocked(
                    holder_pid=holder_pid, lock_path=str(path_p),
                ) from e
            raise
        if write_pid:
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.write(fd, str(os.getpid()).encode("ascii"))
            os.fsync(fd)
        yield fd
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        with contextlib.suppress(OSError):
            os.close(fd)
```

**Pattern to copy:** Re-use `acquire_flock` verbatim against a third lock path (`/run/spark-modem-watchdog/lock`); wrap with `PidLockHeldError` (mirrors `StateStoreLocked`). Kernel auto-releases on death; explicit unlock on graceful shutdown. ADR-0012: PID lock is SEPARATE file from `state.lock` and `modem-*.lock`.

**Analog 2 (clean-shutdown marker — atomic JSON write):** `src/spark_modem/state_store/atomic.py` lines 109-156

**Atomic-write pattern** (atomic.py lines 109-156):
```python
def atomic_write_bytes(target: Path | str, data: bytes, *, mode: int = _DEFAULT_MODE) -> None:
    """Write ``data`` to ``target`` atomically. Never leaves a partial file.

    On any failure, raises :class:`AtomicWriteFailed` and ensures the target
    file (if it existed before) is unchanged.
    """
    target_path = Path(target)
    target_dir = target_path.parent
    # ... temp file write + fsync + replace + dir fsync ...
```

**Pattern to copy:** `lifecycle.write_clean_shutdown_marker(path, body: dict)` calls `atomic_write_bytes(path, json.dumps(body).encode("utf-8"))`. CLAUDE.md invariant #5 — never partial-write a marker.

**Analog 3 (sd_notify wrapper):** RESEARCH.md Pattern 6 lines 569-599 (no in-repo analog yet — sdnotify is a Phase 3 first).

`SdNotifyLifecycle` class with `ready(msg)` / `status(msg)` / `watchdog_kick()` / `stopping(msg)` instance methods; constructor checks `bool(os.environ.get("NOTIFY_SOCKET"))` so dev hosts no-op silently. PITFALLS §4.1: send only from main daemon PID.

**Analog 4 (signal handler installation):** RESEARCH.md Pattern 7 lines 640-666:
```python
loop = asyncio.get_running_loop()
sigterm_event = asyncio.Event()
sighup_event = asyncio.Event()
loop.add_signal_handler(signal.SIGTERM, sigterm_event.set)
loop.add_signal_handler(signal.SIGHUP,  sighup_event.set)
# ... spawn TaskGroup with sigterm_watcher / sighup_watcher children ...
loop.remove_signal_handler(signal.SIGTERM)
loop.remove_signal_handler(signal.SIGHUP)
```

NEVER `signal.signal()` from asyncio (CLAUDE.md anti-pattern catalogue).

---

### `src/spark_modem/daemon/sighup.py` (reload coordinator)

**Analog 1 (Settings + reload markers):** `src/spark_modem/config/reload_marker.py` lines 30-45

**Reload-classification pattern** (reload_marker.py lines 30-45):
```python
def restart_required_fields(model_cls: type[BaseModel]) -> frozenset[str]:
    """Return the set of field names tagged with RELOAD_RESTART on model_cls."""
    out: set[str] = set()
    for name, info in model_cls.model_fields.items():
        if reload_class(info) == "restart":
            out.add(name)
    return frozenset(out)

def data_reloadable_fields(model_cls: type[BaseModel]) -> frozenset[str]:
    """Return the set of field names tagged with RELOAD_DATA on model_cls."""
    out: set[str] = set()
    for name, info in model_cls.model_fields.items():
        if reload_class(info) == "data":
            out.add(name)
    return frozenset(out)
```

**Settings frozen pattern** (settings.py lines 32-37):
```python
model_config = SettingsConfigDict(
    env_prefix="SPARK_MODEM_",
    env_nested_delimiter="__",
    extra="forbid",
    frozen=True,  # Once loaded, immutable; SIGHUP constructs a new instance.
)
```

**Analog 2 (DnsCache re-resolve):** `src/spark_modem/webhook/dns.py` `DnsCache.resolve()` lines 53-82.

**Pattern to copy:** RESEARCH.md Pattern 10 lines 845-878 — `SighupSwapper.try_apply_reload()`: build new Settings from env+YAML, diff against current; intersect diff with `restart_required_fields(Settings)`; if non-empty emit `restart_required` event, keep old Settings, return; else atomic-swap reference (cycle driver reads `self._settings` once per cycle so the swap is naturally cycle-boundary atomic), trigger `await dns_cache.resolve(new_host)`, recompute carrier-table sha256, re-read on diff, emit `config_reloaded`. The cycle driver's `_settings` field at `daemon/cycle_driver.py:152` is the read site Phase 3 swaps.

---

### `src/spark_modem/daemon/sigterm.py` (shutdown coordinator)

**Analog 1 (drain pattern):** `src/spark_modem/webhook/poster.py` `drain()` lines 284-334

**Bounded-budget drain pattern** (poster.py lines 304-334):
```python
self._stopped.set()
deadline = self._clock.monotonic() + budget_seconds
while not self._queue.empty() and self._clock.monotonic() < deadline:
    item = self._queue.get_nowait()
    success = await self._post_one(item.envelope, item.modem_usb_path)
    if success:
        self._metrics.record_webhook_delivery("sent")
    else:
        # ... emit WebhookDropped(reason="drain_timeout") ...
# Anything remaining when the budget expired:
while not self._queue.empty():
    # ... emit WebhookDropped(reason="drain_budget_exhausted") ...
```

**Analog 2 (ordered cleanup, isolated steps):** `src/spark_modem/daemon/cycle_driver.py` lines 162-263 (numbered-step pattern with try/except per step + `NFR-11` comments)

**Pattern to copy:** RESEARCH.md Pattern 9 lines 759-828 — `SigtermChoreography.execute(deadline_seconds=5.0)`: 8 steps, strict order, each with bounded budget. Uses `await self.cycle_driver_task` after `cancel()` (lets `subproc/runner`'s two-stage shutdown drain in-flight qmicli per PITFALLS §5.3); chains into `webhook_poster.drain(budget=remaining)`; final `state_store.save_modem_state` flush; emits `DaemonStopped(reason=SIGTERM, uptime_seconds=...)` (wire shape from `wire/events.py:84-89`); calls `webhook_poster.stop()`; closes UDS metrics socket + `os.unlink(metrics_socket_path)` (PITFALLS §13.3); `atomic_write_bytes` clean-shutdown marker.

---

### `src/spark_modem/daemon/preflight.py` (preflight gate)

**Analog 1 (Settings build + validate):** `src/spark_modem/cli/clients.py` `build_default_settings()` (laptop entry)

**Analog 2 (subprocess for PATH check):** `src/spark_modem/subproc/runner.py` `run()` lines 108-196

**Subprocess invocation pattern** (runner.py lines 108-160):
```python
async def run(
    argv: list[str], *, timeout_s: float,
    stdin: bytes | None = None, env: dict[str, str] | None = None,
) -> CompletedProcess:
    """Run argv as a subprocess and return a CompletedProcess.

    Raises:
      - argv not a list  -> TypeError
      - argv is empty    -> ValueError
      - binary not on PATH -> FileNotFoundError (un-wrapped; standard idiom)
    """
    argv_list = _validate_argv(argv)
    # ...
    try:
        proc = await asyncio.create_subprocess_exec(...)
    except FileNotFoundError:
        raise  # Standard idiom: caller catches FileNotFoundError to detect 'binary missing'.
```

**Pattern to copy:** Preflight runs `await subproc.run(["qmicli", "--version"], timeout_s=2.0)` and `["ip", "--version"]`; catches `FileNotFoundError` → emit `last-config-error` (atomic_write_bytes) + exit non-zero. ALL subprocess calls go through `subproc.run` (SP-04 lint). Settings build via the existing `from_yaml_layer` path; validation failure (pydantic ValidationError) writes `/run/.../last-config-error` and exits non-zero (FR-60 + L-04).

---

### `src/spark_modem/event_logger/inotify_reopener.py` (dispatcher)

**Analog:** Co-located in `src/spark_modem/event_sources/asyncinotify_producer.py` (single producer; this module is the consumer-side dispatch helper)

**Pattern to copy:** `class EventLogReopener` with `async def on_rotate(self) -> None`: calls `EventLogWriter.reopen()`. The asyncinotify producer dispatches by inspecting `event.watch` and calls the appropriate consumer's `on_rotate()`. R-01: same producer, two consumers (this one + ZaoLogInotifyTailer).

---

### MODIFIED: `src/spark_modem/inventory/sysfs.py` (extension only)

**Self-reference (lines 73-83):** descriptor-construction site is the natural `derive_ns()` call site:
```python
descriptors.append(
    ModemDescriptor(
        line=line,
        cdc_wdm=cdc_wdm,
        usb_path=usb_path,
        ns=None,  # Phase 3 derives from netns ← REPLACE WITH derive_ns(resolved)
        iface=iface,
    )
)
```

**Pattern to copy:** Phase 3 inserts `from spark_modem.inventory.netns import derive_ns` and replaces `ns=None` with `ns=derive_ns(resolved)`. No other change — sysfs walk shape is preserved (E-05: inventory is the only sysfs walker).

---

### MODIFIED: `src/spark_modem/qmi/wrapper.py` (extension — argv prepend)

**Self-reference (every method body, e.g. lines 128-137):**
```python
async def nas_get_signal_info(self) -> CompletedProcess:
    return await self._runner.run(
        [
            "qmicli",
            "--device-open-proxy",
            f"--device={self._device}",
            "--nas-get-signal-info",
        ],
        timeout_s=_DEFAULT_TIMEOUT_S,
    )
```

**Pattern to copy:** Phase 3 adds `descriptor: ModemDescriptor | None = None` to `__init__` (or just `ns: str | None`); a single private helper `_argv(self, qmicli_args: list[str]) -> list[str]` prepends `["ip", "netns", "exec", self._ns]` when `self._ns is not None` and returns the full argv. Every existing query/state-changing method calls `self._argv([...])` instead of inlining. PITFALLS §6.2: NEVER `setns()` from asyncio loop — `ip netns exec` forks a child that does its own setns.

---

### MODIFIED: `src/spark_modem/wire/enums.py` (append values)

**Self-reference (existing IssueDetail block, lines 23-67):**
```python
class IssueDetail(StrEnum):
    """Specific diagnosable issues. See docs/RECOVERY_SPEC.md §4 decision table."""
    # Config
    APN_MISMATCH = "apn_mismatch"
    # ... existing variants ...
    # Enumeration / power
    ENUMERATION_MISSING = "enumeration_missing"
    ENUMERATION_ADDRESS_FAIL = "enumeration_address_fail"
    ENUMERATION_OVERCURRENT = "enumeration_overcurrent"
```

**Pattern to copy:** Append a new "Host (kmsg)" section with the 5+1 E-03 values:
```python
    # Host (kmsg classifier — Phase 3 / E-03)
    USB_OVERCURRENT = "usb_overcurrent"
    USB_ENUM_FAILURE = "usb_enum_failure"
    THERMAL_THROTTLE = "thermal_throttle"
    QMI_WWAN_PROBE_FAIL = "qmi_wwan_probe_fail"
    TEGRA_HUB_PSU_DROOP = "tegra_hub_psu_droop"
    UNKNOWN = "unknown"  # if not already present
```

Note: `USB_OVERCURRENT` differs from existing `ENUMERATION_OVERCURRENT`; closed-enum discipline (W-04 anti-pattern: free-form detail) — never collapse into one value.

---

### MODIFIED: `src/spark_modem/event_logger/writer.py` (extension)

**Self-reference (lines 75-120 — fd lifecycle):**
```python
def __init__(self, path: Path | str) -> None:
    self._path = Path(path)
    # ...
    self._fd: int | None = os.open(
        str(self._path),
        os.O_WRONLY | os.O_CREAT | os.O_APPEND,
        _MODE,
    )

def append(self, event: Event) -> None:
    fd = self._fd
    if fd is None:
        raise EventLogClosedError(f"writer for {self._path!s} is closed")
    # ...
    os.write(fd, line + b"\n")

def close(self) -> None:
    fd = self._fd
    self._fd = None
    if fd is not None:
        with contextlib.suppress(OSError):
            os.close(fd)
```

**Pattern to copy:** Phase 3 adds:
- `self._reopen_buffer: deque[bytes] = deque(maxlen=1000)` in `__init__`
- `self._reopening: bool = False`
- `def reopen(self) -> None`: set `_reopening=True`; close old fd; `os.open(self._path, O_WRONLY|O_CREAT|O_APPEND, _MODE)`; flush `_reopen_buffer` to new fd in order; clear buffer; clear `_reopening`
- `append()` checks `self._reopening`: if True, append serialized line to `_reopen_buffer` (drop on overflow + bump `events_dropped_total{reason="reopen_overflow"}`); else `os.write(fd, ...)` as before

R-03: window is microseconds in happy path (single coroutine, no awaits between detect and reopen).

---

### MODIFIED: `src/spark_modem/daemon/main.py` (rewrite)

**Self-reference (Phase 2 wiring shape, lines 59-140):** The Phase 2 wiring (`Settings → state_root → store → event_logger → metrics → inventory → zao → carriers → scheduler → webhook_poster → cycle_driver → run_one_cycle`) is the unchanged spine; Phase 3 wraps it in:

1. argparse (replaces line 66 `del argv`)
2. preflight (`daemon/preflight.py`)
3. clean-shutdown marker classify (`lifecycle.classify_prior_run`)
4. PID lock (`lifecycle.acquire_pid_lock`)
5. `loop.add_signal_handler(SIGTERM, sigterm_event.set)` (RESEARCH.md Pattern 7)
6. swap `_NoZaoTailer` / `_InventoryFromFile` → `ZaoLogInotifyTailer` / `UdevInventory`
7. wrap cycle in `async with asyncio.TaskGroup() as tg:` with 5 producer children + cycle driver child + sigterm/sighup watcher children
8. send `READY=1` AFTER first cycle completes (PITFALLS §4.1)
9. STATUS / WATCHDOG kicks at cycle-END (L-01)

The Phase 2 `boot_envelope` emission (lines 110-117) is preserved; reason field updates from CRASH to whatever `classify_prior_run` returned.

---

### TEST FAKES

#### `tests/fakes/sdnotify.py` (call-recording fake)

**Analog:** `tests/fakes/runner.py` (FakeRunner) and `tests/fakes/webhook.py` (FakeWebhookPoster — sent list)

**Recorded-calls pattern** (runner.py lines 26-62):
```python
class FakeRunner:
    def __init__(self) -> None:
        self._responses: dict[tuple[str, ...], CompletedProcess] = {}
        self._calls: list[list[str]] = []

    @property
    def calls(self) -> list[list[str]]:
        return [list(c) for c in self._calls]

    async def run(self, argv: list[str], *, timeout_s: float, ...) -> CompletedProcess:
        del timeout_s, stdin, env
        self._calls.append(list(argv))
        # ...
```

**Pattern to copy:** `FakeSdNotify` records `ready_calls: list[str]`, `status_calls: list[str]`, `watchdog_calls: list[None]`, `stopping_calls: list[str]`. Identical shape to `FakeWebhookPoster.sent`. Tests assert call-order + count.

#### `tests/fakes/udev.py` / `tests/fakes/rtnetlink.py` / `tests/fakes/asyncinotify.py` / `tests/fakes/kmsg.py` (event injectors)

**Analog:** `tests/fakes/zao_log.py` (FixtureZaoTailer with state-mutating helper)

**State-mutating helper pattern** (zao_log.py lines 28-52):
```python
class FixtureZaoTailer:
    def __init__(self, *, active_lines: set[int] | None = None) -> None:
        self._active_lines: set[int] = set(active_lines) if active_lines else set()

    def is_line_active(self, line_idx: int) -> bool:
        return line_idx in self._active_lines

    def snapshot(self) -> ZaoSnapshot:
        return ZaoSnapshot(
            active_lines=frozenset(self._active_lines),
            last_block_iso=None, log_age_seconds=None, unknown_reason=None,
        )

    def set_active(self, lines: set[int]) -> None:
        """Replace the active-line set with `lines` (defensive copy)."""
        self._active_lines = set(lines)
```

**Pattern to copy:** Each fake exposes the production Protocol AND a test-only mutator (`fake.inject_event(...)` / `fake.set_pending(...)`). Production code never sees the mutator (the Protocol surface omits it).

#### `tests/fakes/pidlock.py` (asyncio.Lock fallback for Windows)

**Analog:** `tests/fakes/dns.py` (one-shot fail flag) + `src/spark_modem/state_store/locks.py` `AsyncFlockHandle(fd=-1)` Windows sentinel (lines 178-180)

**Windows-fallback sentinel pattern** (locks.py lines 178-180):
```python
if not _FCNTL_AVAILABLE:
    # No-op on Windows; sentinel fd=-1 skipped by _release_flock_fd.
    return AsyncFlockHandle(-1, Path(path))
```

**Pattern to copy:** `FakePIDLock` wraps an `asyncio.Lock`; `acquire()` raises `PidLockHeldError` if already locked (matches non-blocking real flock semantics). Lets non-POSIX dev hosts run lifecycle tests minus the PID-lock layer.

---

### NEW: `tests/integration/test_lifecycle.py` (Linux-only end-to-end)

**Analog:** `tests/unit/daemon/test_cycle_driver.py` + `tests/integration/test_default_carrier_table.py`

**Skip-on-Windows pattern (locks.py + tests/unit/inventory/test_sysfs.py lines 25-28):**
```python
_SKIP_WIN_SYSFS = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Symlink-and-permission-heavy sysfs simulation; production target is Linux",
)
```

**Pattern to copy:** All Phase 3 integration tests carry `pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Linux-only event sources")`. RESEARCH.md proposes `pytest -m "linux_only"` as the selector — planner picks marker name. End-to-end shape: spawn daemon main() with TaskGroup; inject SIGTERM via fake sdnotify or asyncio.Event; assert 5 s SLA + clean-shutdown marker contents.

---

### NEW: `debian/spark-modem-watchdog.logrotate` (logrotate snippet)

**Analog:** None in repo — first logrotate snippet.

**Pattern to copy:** RESEARCH.md R-02 (CONTEXT.md decision) — verbatim contents:
```
/var/log/spark-modem-watchdog/events.jsonl {
    daily
    rotate 7
    size 100M
    compress
    delaycompress
    missingok
    notifempty
    sharedscripts
    create 0640 root adm
    postrotate
        # Empty: writer detects rotation via asyncinotify producer (R-01)
    endscript
}
```

`create 0640 root adm` is FR-43 / PITFALLS §12.2 (logrotate-user read perms); `daily` + `rotate 7` is FR-43; `size 100M` is FR-43.

---

### MODIFIED: `debian/spark-modem-watchdog.service` (Phase 3 hardening)

**Self-reference (current Phase 1 baseline at lines 21-71)** — Phase 3 edits per U-01..U-05.

**Pattern to copy:** RESEARCH.md U-01..U-05 (CONTEXT.md decisions). Specifically:
- Line 22 `Restart=on-failure` ✓ (already correct; keep)
- Line 23 `RestartSec=5s` → `RestartSec=10`
- Add `StartLimitIntervalSec=300`, `StartLimitBurst=20`, `TimeoutStopSec=10s`, `KillMode=mixed`, `WatchdogSec=90s`
- Line 52 `CapabilityBoundingSet=` → `CAP_NET_ADMIN CAP_SYS_ADMIN CAP_SYS_MODULE CAP_DAC_READ_SEARCH` (preallocated for Phase 4)
- Line 39 `RestrictNamespaces=true` → `RestrictNamespaces=net mnt` (allow netns + mnt for `ip netns exec`)
- Line 56-57 add `RuntimeDirectoryPreserve=yes` (load-bearing per PITFALLS §4.4)
- Line 29 REMOVE `PrivateTmp=true` AND verify NO `PrivateMounts=` (incompat with LoadCredential on systemd 245 per PITFALLS §4.3)
- Line 12 ExecStartPre extend with second `ExecStartPre=spark-modem ctl config-check` (U-05)

---

## Shared Patterns

### Pattern A: Protocol-typed dependencies (test-shimmable)

**Source:** `src/spark_modem/daemon/cycle_driver.py` lines 64-122 (multiple co-located Protocols)

**Apply to:** All new producer modules (`event_sources/*.py`), `daemon/lifecycle.py`, `daemon/sigterm.py`, `daemon/sighup.py`

```python
class ClockProto(Protocol):
    """Monotonic + wall-clock surface (ADR-0007)."""
    def monotonic(self) -> float: ...
    def wall_clock_iso(self) -> str: ...

class _EventQueueProto(Protocol):
    def put_nowait(self, item: object) -> None: ...

class EventLogWriterProto(Protocol):
    """Append-only events.jsonl writer surface."""
    def append(self, event: Event) -> None: ...
```

Co-located Protocol classes (one file = one production impl + N small Protocols for its deps). Tests inject FakeClock / FakeRunner / FakeSdNotify without module-level monkeypatch.

---

### Pattern B: NFR-11 isolation (errors are data; never crash the cycle)

**Source:** `src/spark_modem/observer/orchestrator.py` lines 81-91

```python
try:
    async with asyncio.timeout(timeout_s):
        return await probe_modem_to_snapshot(modem, qmi_factory(modem), clock)
except TimeoutError:
    logger.warning("probe timed out for %s", modem.usb_path)
    return _timed_out_snapshot(modem)
except Exception:  # NFR-11: never crash the cycle - errors are data
    logger.exception("probe failed for %s", modem.usb_path)
    return _errored_snapshot(modem)
```

**Apply to:** All event-source producers' inner-loop bodies + cycle driver step boundaries + lifecycle marker IO. Catch `Exception` (not `BaseException`); log via `logger.exception` (preserves stack); return a typed sentinel (timed_out / errored snapshot). The `restart_on_crash` wrapper does the same at the producer-task level.

---

### Pattern C: Platform-conditional fcntl (POSIX-only flock; Windows no-op sentinel)

**Source:** `src/spark_modem/state_store/locks.py` lines 42-50, 178-180, 213-214

```python
if sys.platform != "win32":
    import fcntl
    _FCNTL_AVAILABLE = True
else:
    _FCNTL_AVAILABLE = False

def _enter_flock_for_async(...) -> AsyncFlockHandle:
    if not _FCNTL_AVAILABLE:
        return AsyncFlockHandle(-1, Path(path))  # no-op sentinel
    # ... real flock body ...
```

**Apply to:** `daemon/lifecycle.py` PID lock, `daemon/preflight.py` if it touches lock files, all integration tests. Production target is Linux/aarch64; Windows dev-host accommodation is the no-op sentinel.

---

### Pattern D: Pydantic v2 closed enums + frozen models (W-02 wire boundary)

**Source:** `src/spark_modem/wire/enums.py` (StrEnum subclasses) + `src/spark_modem/config/settings.py` lines 32-37 (`frozen=True`) + `src/spark_modem/wire/_base.py` (BaseWire frozen model base)

**Apply to:** All new wire types Phase 3 introduces (none expected; only enum extensions). `WakeSignal(StrEnum)` follows the closed-enum discipline. `IssueDetail` extension follows the same StrEnum shape.

---

### Pattern E: Atomic file write + directory fsync (FR-62; CLAUDE.md invariant #5)

**Source:** `src/spark_modem/state_store/atomic.py` `atomic_write_bytes` (lines 109-156)

**Apply to:** Clean-shutdown marker write (`daemon/lifecycle.py`), `last-config-error` write (`daemon/preflight.py`). Never partial-write a marker; temp + fsync + replace + dir fsync. Already exposed at module level — do not re-implement.

---

### Pattern F: Skip-on-Windows pytest mark for POSIX-only paths

**Source:** `tests/unit/inventory/test_sysfs.py` lines 25-28; `tests/unit/state_store/test_concurrent_writers.py` lines 43-46

```python
import sys, platform, pytest
IS_POSIX = platform.system() != "Windows"
pytestmark = pytest.mark.skipif(not IS_POSIX, reason="flock is POSIX-only")
# OR:
_SKIP_WIN = pytest.mark.skipif(sys.platform == "win32", reason="...")
```

**Apply to:** All Phase 3 tests touching `pyudev`, `pyroute2`, `asyncinotify`, `/dev/kmsg`, `sd_notify`, real `flock`. Daemon never runs on Windows; tests use either FakeUdevMonitor / FakeKmsgReader on Windows or skip entirely.

---

### Pattern G: Lock acquisition order (asyncio.Lock then flock; ADR-0012)

**Source:** `src/spark_modem/state_store/store.py` lines 12-30, 354-371 (save_identity_map shape)

```python
async def save_identity_map(
    self, identities: dict[str, Identity], *, wait_for_flock: bool = True,
) -> None:
    """Atomic save with globals asyncio.Lock + state-store flock."""
    async with globals_lock():
        # Lock acquisition order: asyncio.Lock acquired above, flock here.
        lock_path = state_store_lockfile(run=self._run_dir)
        async with acquire_flock_async(lock_path, blocking=wait_for_flock):
            target = identity_map_path(root=self._state_root)
            envelope = {...}
            payload = json.dumps(envelope, sort_keys=True).encode("utf-8")
            atomic_write_bytes(target, payload)
```

**Apply to:** Any Phase 3 site that mutates state during SIM-swap detection. E-04 atomicity (identity update + streak reset + counter reset in one write) preserves this acquisition order — the existing `save_identity_map` is the call.

---

### Pattern H: Sleeper Protocol injection for FakeClock-driven tests

**Source:** PITFALLS §14.1 + RESEARCH.md Pitfall 14 (`tests/fakes/sleeper.py` referenced as Phase 2 infrastructure though file may not yet exist — verify or create)

**Apply to:** `event_sources/supervisor.py` `restart_on_crash` (its `await asyncio.sleep(delay)` becomes `await sleeper.sleep(delay)`). Production wires real `asyncio.sleep`; tests wire a fake that advances FakeClock and yields control.

---

## No Analog Found

All 39 new files have a strong Phase 1/2 analog. Edge cases:

| File | Why mostly-novel | Mitigation |
|------|------------------|------------|
| `daemon/lifecycle.py` (sd_notify wrapper portion) | sdnotify integration is Phase 3 first | RESEARCH.md Pattern 6 lines 569-599 (verified Context7 retrieval); pure-Python sdnotify lib is ~30 LOC |
| `event_sources/supervisor.py` (`restart_on_crash`) | Bounded-backoff supervisor not used elsewhere | RESEARCH.md Pattern 1 lines 339-368 + PITFALLS §6.1, §7.1, §8.1 + Pitfall 15 (attempt-counter reset on long uptime) |
| `event_sources/asyncinotify_producer.py` (dual-mode logrotate) | First inotify usage in repo | RESEARCH.md Pattern 4 lines 411-475; PITFALLS §8.1 prescriptive |
| `debian/spark-modem-watchdog.logrotate` | First logrotate snippet | RESEARCH.md R-02 verbatim; FR-43 + PITFALLS §12.2 |

For all four, RESEARCH.md provides the concrete recipe; the planner should reference RESEARCH.md line numbers in each plan's `read_first` block.

---

## Metadata

**Analog search scope:** `src/spark_modem/{daemon,inventory,zao_log,event_logger,webhook,state_store,subproc,observer,qmi,wire,config,status_reporter,cli}/` + `tests/{fakes,unit,integration}/`

**Files scanned:** 30+ production modules, 30+ test modules, debian/ unit file
**Pattern extraction date:** 2026-05-07
**Key Phase 1/2 surfaces re-used by Phase 3:**
- `state_store/locks.py:108-161` (acquire_flock — PID lock just adds third file path)
- `state_store/atomic.py:109-156` (atomic_write_bytes — clean-shutdown marker + last-config-error)
- `state_store/store.py:354-371` (save_identity_map — E-04 SIM-swap reset uses unchanged)
- `webhook/poster.py:284-334` (drain — SIGTERM step 3 just calls)
- `webhook/dns.py:53-82` (DnsCache.resolve — SIGHUP triggers force-refresh)
- `config/reload_marker.py:30-45` + `config/settings.py:32-37` (reload classification ready)
- `inventory/protocol.py` + `inventory/descriptor.py` (Phase 2 Protocol unchanged; descriptor.ns field already typed)
- `zao_log/protocol.py` (Phase 2 Protocol unchanged; ZaoLogInotifyTailer slots in)
- `daemon/cycle_driver.py:152` (self._settings read site → SIGHUP swap target)
- `daemon/cycle_scheduler.py` (event_queue arm plumbed as no-op stub in Phase 2)
- `wire/enums.py:145-153` (DaemonStopReason ready for `reason=SIGTERM` emission)
- `wire/events.py:84-89` (DaemonStopped event ready)
- `wire/identity.py` (Identity model + ICCID/IMSI fields ready)
- `observer/orchestrator.py:39-91` (TaskGroup + per-task isolation pattern; supervisor.py mirrors)
- `subproc/runner.py:108-196` (qmicli + ip netns exec invocations route through)
- `event_logger/writer.py:75-132` (extension target — reopen + buffer)
