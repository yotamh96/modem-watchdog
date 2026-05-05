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
