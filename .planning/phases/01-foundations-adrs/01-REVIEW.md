---
phase: 01-foundations-adrs
reviewed: 2026-05-06T00:00:00Z
depth: standard
files_reviewed: 38
files_reviewed_list:
  - src/spark_modem/__init__.py
  - src/spark_modem/clock/__init__.py
  - src/spark_modem/clock/clock.py
  - src/spark_modem/config/__init__.py
  - src/spark_modem/config/reload_marker.py
  - src/spark_modem/config/settings.py
  - src/spark_modem/config/yaml_merge.py
  - src/spark_modem/event_logger/__init__.py
  - src/spark_modem/event_logger/writer.py
  - src/spark_modem/state_store/__init__.py
  - src/spark_modem/state_store/atomic.py
  - src/spark_modem/state_store/errors.py
  - src/spark_modem/state_store/inventory.py
  - src/spark_modem/state_store/locks.py
  - src/spark_modem/state_store/paths.py
  - src/spark_modem/state_store/store.py
  - src/spark_modem/subproc/__init__.py
  - src/spark_modem/subproc/errors.py
  - src/spark_modem/subproc/result.py
  - src/spark_modem/subproc/runner.py
  - src/spark_modem/wire/__init__.py
  - src/spark_modem/wire/_base.py
  - src/spark_modem/wire/carriers.py
  - src/spark_modem/wire/diag.py
  - src/spark_modem/wire/enums.py
  - src/spark_modem/wire/events.py
  - src/spark_modem/wire/globals.py
  - src/spark_modem/wire/identity.py
  - src/spark_modem/wire/state.py
  - src/spark_modem/wire/versioning.py
  - src/spark_modem/wire/webhook.py
  - debian/rules
  - debian/spark-modem-watchdog.postinst
  - debian/spark-modem-watchdog.postrm
  - debian/spark-modem-watchdog.service
  - scripts/build_deb.sh
  - scripts/lint_no_subprocess.sh
  - scripts/postinst_smoke_test.sh
findings:
  critical: 2
  warning: 11
  info: 9
  total: 22
status: issues_found
---

# Phase 1: Code Review Report

**Reviewed:** 2026-05-06
**Depth:** standard
**Files Reviewed:** 38
**Status:** issues_found

## Summary

Phase 1 establishes the foundations of `spark-modem-watchdog` v2 — wire types,
clock, subproc runner, config, state store, event logger, and the `.deb`
packaging pipeline. The overall design quality is **high**: invariants from
CLAUDE.md and the ADR set are tracked carefully (ADR-0007 monotonic clock,
ADR-0009 usb_path keying, ADR-0012 3-layer locking, SP-03 spawn discipline,
NFR-43 non-destructive schema downgrade). Pydantic v2 wire types are
correctly frozen with `extra='forbid'`, the subprocess runner is the sole
spawn site (lint-enforced), and atomic writes follow the temp-fsync-rename-
dirfsync recipe.

Two **critical** findings stand out:

1. **CR-001** — The systemd unit runs as `User=root` with `NoNewPrivileges=false`,
   which is overly broad for a daemon that only writes to a single state tree.
   It contradicts the documented `LoadCredential=` discipline (which exists
   precisely to keep the HMAC secret off-process) and breaks Phase 1 SC #1
   defense-in-depth (the unit has no `CapabilityBoundingSet`, no
   `ProtectKernelTunables`, no `RestrictAddressFamilies`, no
   `SystemCallFilter`).
2. **CR-002** — `state_store/store.py:234` and `store.py:323` use
   `target.rename(shadow)` for the schema-downgrade rename instead of
   `os.replace`. On POSIX `Path.rename` raises if the destination already
   exists; if a previous downgrade left a stale `.from-v0.json` shadow (e.g.
   from a crashed earlier downgrade attempt), the rename will raise mid-load
   and the daemon will refuse to start without operator action — and worse,
   the original file will still be on disk in its old-version shape, so a
   retry will hit the same path. There is also no directory `fsync` after
   the rename, which violates the same atomicity discipline `atomic.py`
   enforces for forward writes.

The warning set is dominated by:

- Lock-handle leakage when an exception is raised inside `_enter_flock_for_async`
  after a successful `flock` but before the handle is returned (locks.py).
- Several catch-broad-OSError-then-raise-UsbPathMismatch sites in
  `store.load_modem_state` that conflate "file unreadable due to disk error"
  with "file's usb_path doesn't match sysfs" — operator triage will be
  misled (S-02 says daemon refuses to start, but it should refuse for the
  *correct* reason).
- `Path.rename` (not `os.replace`) used for shadow-rename in two places.
- A circular-import / import-order issue between `event_logger` (imports
  every concrete event type from `wire.events`) and the public surface in
  `wire/__init__.py`.
- The `EventAdapter.dump_json` that `event_logger/writer.py` calls is
  documented as bytes but `pydantic.TypeAdapter` exposes `dump_json` only on
  Pydantic v2, and `dump_json` does NOT take an event instance directly — it
  takes `(value)`; the call in writer.py:93 reads correctly but the
  TypeAdapter's `validate_*` discriminator implies `dump_json` must
  serialize through the discriminated wrapper. Worth a unit test.
- The systemd unit's placeholder `ExecStart=` exits 0 immediately after
  `notify(READY=1)`. With `Restart=on-failure`, this is fine, but the unit
  will rapid-cycle if anyone changes Restart= without realizing.
- `validate_argv` accepts an empty *string element* `argv[0] == ""` that
  passes the `isinstance(str)` check; spawn will fail with a confusing
  ENOENT.

A handful of info-level items: documentation drift between code comments
("all 9 libs"; the postinst_smoke_test.sh imports 10), TODO-flavored
forward-compat hooks, an unused parameter, and a few opportunities to
tighten validators.

---

## Critical Issues

### CR-001: systemd unit runs as root with NoNewPrivileges=false and no syscall/capability hardening

**File:** `debian/spark-modem-watchdog.service:24-30`
**Issue:** The unit declares `User=root`, `Group=root`, and
`NoNewPrivileges=false` while bundling a Python interpreter that imports
`pydantic`, `pyudev`, `pyroute2`, `httpx`, etc. The `ProtectSystem=strict`
+ `ProtectHome=true` + `PrivateTmp=true` set is good, but it leaves out:

- `NoNewPrivileges=true` (currently *false* — actively disabled)
- `CapabilityBoundingSet=` (no bounding set; root has CAP_SYS_*\* full)
- `RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK` (the daemon
  needs only these — netlink for pyroute2, UNIX for Prom UDS, INET for
  webhook)
- `RestrictNamespaces=true`
- `RestrictRealtime=true`
- `LockPersonality=true`
- `MemoryDenyWriteExecute=true`
- `SystemCallFilter=@system-service` (or similar)
- `ProtectKernelTunables=true`, `ProtectKernelModules=true`,
  `ProtectKernelLogs=true`
- `ProtectControlGroups=true`
- `RuntimeDirectory=spark-modem-watchdog` (creates `/run/spark-modem-watchdog`
  with the right ownership automatically)

The daemon does need raw root for `usb_reset` / `driver_reset` (Phase 4),
but Phase 1 has no destructive actions; the unit should be locked down now
and selectively relaxed when those actions land.

The HMAC `LoadCredential=` design (ADR-0011) loses much of its value if the
daemon process can read arbitrary files anyway because it runs as root with
no `CapabilityBoundingSet`. The design intent is "secret is in
`$CREDENTIALS_DIRECTORY` and nowhere else" — that requires the process to
*not* be able to read `/etc/spark-modem-watchdog/hmac-secret` directly.

**Fix:**
```ini
[Service]
Type=notify
NotifyAccess=main

# Phase 1: hardened baseline. Phase 4 will need to relax some of these
# when destructive actions (usb_reset, driver_reset) land.
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
RestrictNamespaces=true
RestrictRealtime=true
LockPersonality=true
MemoryDenyWriteExecute=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK
RestrictSUIDSGID=true
ProtectClock=true
ProtectHostname=true
SystemCallFilter=@system-service
SystemCallErrorNumber=EPERM

# Capabilities the daemon actually uses today (Phase 1 needs none — placeholder
# ExecStart just notifies READY=1). Phase 2 adds CAP_NET_ADMIN for pyroute2;
# Phase 4 adds CAP_SYS_ADMIN for usb_reset.
CapabilityBoundingSet=
AmbientCapabilities=

# Use systemd to manage runtime + state + log directories (auto-created with
# the right ownership, auto-cleaned on stop where appropriate).
RuntimeDirectory=spark-modem-watchdog
RuntimeDirectoryMode=0750
StateDirectory=spark-modem-watchdog
StateDirectoryMode=0750
LogsDirectory=spark-modem-watchdog
LogsDirectoryMode=0750
ConfigurationDirectory=spark-modem-watchdog

ReadWritePaths=/var/lib/spark-modem-watchdog /var/log/spark-modem-watchdog /run/spark-modem-watchdog

User=spark-modem-watchdog
Group=spark-modem-watchdog
```

(Run as the `spark-modem-watchdog` system user that postinst already
creates, then add capabilities back as needed in Phase 2/4. The placeholder
ExecStart works fine as a non-root user.)

---

### CR-002: schema-downgrade rename uses Path.rename (clobber-unsafe) and skips directory fsync

**File:** `src/spark_modem/state_store/store.py:234, 323`
**Issue:** Both downgrade branches do:

```python
shadow = shadow_filename(target, from_version=file_version)
target.rename(shadow)
```

Two distinct problems:

1. **Clobber semantics.** On POSIX, `Path.rename` is implemented via
   `os.rename`, which under POSIX semantics is *defined* to atomically
   replace the destination — so on Linux this is fine. **However**, the
   docstring of `Path.rename` and the behavior on Windows differ
   (`os.rename` raises `FileExistsError` if the destination exists on
   Windows). The atomic-write module deliberately uses `os.replace` to
   normalize this. The downgrade path should follow the same discipline.
   Even on POSIX, if a stale `.from-v0.json` shadow already exists (e.g.
   from a previous crashed downgrade), it will be silently overwritten
   without any audit trail — a forensic loss.
2. **No directory fsync after rename.** The atomicity discipline in
   `atomic.atomic_write_bytes` includes step 6 (`_fsync_directory`) so the
   rename is durable across crash. The downgrade path renames the live
   state file to a shadow but skips this step; if the box loses power
   between rename and the subsequent `_save_modem_state_locked` write
   (which *does* dirfsync), the state directory's metadata may not have
   been flushed and the rename can be lost on remount. Result: on next
   boot, the file is back at its old location with the old version, and
   the operator's audit trail (the `schema_downgrade_pending` event)
   refers to a shadow file that doesn't exist.

**Fix:**
```python
import os

# (in load_modem_state)
shadow = shadow_filename(target, from_version=file_version)
# os.replace: atomically clobber any existing shadow (forensic loss is
# acceptable for stale shadows from crashed earlier downgrades; the audit
# is in the schema_downgrade_pending event, not in the shadow's mtime).
os.replace(target, shadow)
# Persist the rename across crash before writing the fresh default.
# (Reuse atomic._fsync_directory or extract a public helper.)
_fsync_directory(target.parent, target)

fresh = _fresh_modem_state(usb_path)
await self._save_modem_state_locked(usb_path, fresh)
```

Same fix in `load_globals`. Consider extracting `_fsync_directory` to a
public helper in `atomic.py` (`fsync_directory(path: Path) -> None`) so
both modules share the same implementation and its Windows-no-op semantics.

---

## Warnings

### WR-001: AsyncFlockHandle is leaked if the constructor's caller is cancelled before await returns

**File:** `src/spark_modem/state_store/locks.py:250-271, 164-205`
**Issue:** `acquire_flock_async` is

```python
async def acquire_flock_async(...) -> AsyncFlockHandle:
    return await asyncio.to_thread(_enter_flock_for_async, ...)
```

If the caller is cancelled *between* `_enter_flock_for_async` returning a
locked handle (worker thread already finished) and the awaiting coroutine
resuming, asyncio will deliver `CancelledError` and the returned
`AsyncFlockHandle` is dropped on the floor — its `_fd` remains open and
flocked. There is no `__del__` to release the fd.

Worse, the call sites use the
`async with await acquire_flock_async(...)` pattern, which has the same
race in two places: the `await` resolves the awaitable, then control
transfers to `__aenter__`. If cancellation arrives at this exact point,
the handle has no owner.

This is the well-known asyncio cancellation-leak pattern. The standard
fix is to wrap the acquire in a context manager that owns the fd from
syscall to release.

**Fix:**
```python
@contextlib.asynccontextmanager
async def acquire_flock_async(
    path: Path | str,
    *,
    blocking: bool = False,
    write_pid: bool = True,
) -> AsyncIterator[AsyncFlockHandle]:
    handle = await asyncio.to_thread(_enter_flock_for_async, path, blocking, write_pid)
    try:
        yield handle
    finally:
        await handle.release()
```

Then call sites become `async with acquire_flock_async(...) as handle:`
(no `await` outside the `async with`). This eliminates the cancellation
window. Also add an `atexit`-style backstop: track open handles in a
weakset and warn at shutdown if any are still held.

---

### WR-002: load_modem_state conflates "OSError reading file" and "JSON decode error" with UsbPathMismatch

**File:** `src/spark_modem/state_store/store.py:209-227`
**Issue:** The load path catches `OSError` from `read_bytes()` and
`ValueError | UnicodeDecodeError` from `json.loads` and re-raises them as
`UsbPathMismatch`. This is semantically wrong:

- An I/O error reading the file (EIO, permission, ENOSPC during read) has
  nothing to do with usb_path inconsistency — the operator runs `ctl
  reset-state --modem=<usb_path>` (per S-02) and either gets the same EIO
  or now-loses-the-state-because-the-OSError-was-actually-storage-related.
- A JSON parse error means the file is corrupt — that is a data integrity
  problem, not an inventory problem.

S-02 says the daemon refuses to start on usb_path_mismatch, with sd_notify
STATUS=usb_path_mismatch. If the underlying cause is "disk full" or
"corrupt JSON," operators chasing the wrong runbook step will conclude
the modem renumbered when it didn't.

**Fix:** Define separate error types and a separate event variant:

```python
# state_store/errors.py
class StateFileCorrupt(StateStoreError):  # noqa: N818
    """JSON parse failure on a persisted state file."""
    def __init__(self, *, file_path: str, reason: str,
                 original_exception: BaseException | None = None) -> None:
        ...

class StateFileIOError(StateStoreError):  # noqa: N818
    """OS-level I/O error reading or writing a state file."""
    ...
```

Then in `load_modem_state`:
```python
try:
    raw_bytes = target.read_bytes()
except OSError as e:
    raise StateFileIOError(...) from e
try:
    raw = json.loads(raw_bytes.decode("utf-8"))
except (ValueError, UnicodeDecodeError) as e:
    raise StateFileCorrupt(file_path=str(target), reason=str(e),
                           original_exception=e) from e
```

Add corresponding wire-event variants (or accept the reuse and tag the
event with a `cause: str` field). Daemon startup classifies the exception
type to decide which `sd_notify STATUS=` message to emit. This is the
diagnostic foundation S-02 promised.

---

### WR-003: Validators allow argv[0] = "" through (empty-string element)

**File:** `src/spark_modem/subproc/runner.py:48-66`
**Issue:** `_validate_argv` checks `not isinstance(a, str)` for each
element but accepts the empty string. Spawning with `argv=[""]` calls
`asyncio.create_subprocess_exec(*[""])` and produces a confusing
`FileNotFoundError: [Errno 2] No such file or directory: ''` that doesn't
make clear the empty-string element is the problem. Also: a list with a
NUL byte inside the executable name will fail with a less-clear OSError
(POSIX execve doesn't accept embedded NUL).

**Fix:**
```python
for i, a in enumerate(argv):
    if not isinstance(a, str):
        raise TypeError(...)
    if "\x00" in a:
        raise ValueError(f"argv[{i}] contains NUL byte; rejected before spawn")
if not argv[0]:
    raise ValueError("argv[0] (the executable) must be non-empty")
```

---

### WR-004: _two_stage_shutdown silently swallows BrokenPipeError but never times out the second communicate()

**File:** `src/spark_modem/subproc/runner.py:207-211`
**Issue:** After SIGKILL, the second `proc.communicate()` is called
without a timeout. In the rare case where the kernel hasn't yet reaped
the process group (zombie) and the parent fd is somehow stuck, this
hangs forever. The whole point of two-stage shutdown is to bound how
long a misbehaving subprocess can pin the daemon — but the recovery
drain has no upper bound.

**Fix:**
```python
try:
    async with asyncio.timeout(_SIGKILL_DRAIN_SECONDS):  # e.g. 3.0s
        drained_out, drained_err = await proc.communicate()
except (BrokenPipeError, ConnectionResetError, TimeoutError):
    drained_out, drained_err = b"", b""
```

This guarantees `run()` returns within `timeout_s + 2 + 3` seconds in the
worst case. M5 (P99 cycle ≤10s) depends on this bound being hard.

---

### WR-005: yaml_merge.load_yaml_layer silently drops invalid YAML files (FR-63 says "logged error, not crash")

**File:** `src/spark_modem/config/yaml_merge.py:45-53`
**Issue:** When a file under `conf.d/` raises `OSError` or `yaml.YAMLError`,
the merger silently `continue`s. The comment correctly identifies this
needs Phase 3 wiring (the daemon-boot path emits `config_invalid`
events) but in Phase 1, an operator who misconfigures a YAML file gets a
*silent no-op* — the rest of the carrier table loads, the bad file is
ignored, and there is no log message at all.

This violates FR-63 ("logged error, not crash"). Even without the
event_logger circular-import problem, a `print(..., file=sys.stderr)` or
a `logging.warning(...)` would make the failure visible.

**Fix:** At minimum log to stderr in Phase 1:

```python
import sys
...
except (OSError, yaml.YAMLError) as e:
    print(
        f"WARNING: spark_modem.config: failed to parse {f}: "
        f"{type(e).__name__}: {e}",
        file=sys.stderr,
    )
    continue
```

Better: use the stdlib `logging` module with a named logger
(`logging.getLogger(__name__)`); the daemon-boot path in Phase 3 can
attach a structured-event handler that turns those warnings into
`config_invalid` events.

---

### WR-006: walk_sysfs_for_qmi_modems uses .read_text() without explicit encoding and silently skips on OSError

**File:** `src/spark_modem/state_store/inventory.py:50-58`
**Issue:** `id_vendor_file.read_text().strip()` uses the default
encoding (locale-dependent). On a Jetson with a misconfigured locale this
*could* (very rarely) raise UnicodeDecodeError, which is not caught here
— the loop catches only `OSError`. The body of `idVendor` is ASCII
(`1199\n`) so this is a low-likelihood bug, but the discipline elsewhere
(state_store/store.py, atomic.py, event_logger) is to set
`encoding="utf-8"` explicitly.

Also: silently skipping on OSError when reading sysfs masks legitimate
USB-permissions issues. If `id_vendor_file.is_file()` is True but read
returns EACCES, the daemon will silently treat the modem as
"not-Sierra-Wireless" and refuse to enroll it — operators chasing
"modem invisible" will not see anything in the logs.

**Fix:**
```python
try:
    vid = id_vendor_file.read_text(encoding="ascii").strip()
except (OSError, UnicodeDecodeError) as e:
    # Surface a structured warning so the operator can investigate
    # permissions / hardware failure on a specific bus path.
    logger.warning(
        "spark_modem.inventory: skipping %s: %s: %s",
        dev_dir.name, type(e).__name__, e,
    )
    continue
```

(Logger plumbing per WR-005.)

---

### WR-007: Settings.webhook_url validator allows trivial-bypass URLs (e.g. `http://`, `https://`)

**File:** `src/spark_modem/config/settings.py:130-138`
**Issue:** The validator only checks the scheme prefix:
```python
if not (v.startswith("http://") or v.startswith("https://")):
    raise ValueError(...)
```

This accepts:
- `http://` (no host)
- `https://` (no host)
- `http://[invalid bracket`
- `https:// space in url`
- `https://localhost/` (allowed by NFR-33? unclear)

`urllib.parse.urlsplit` would catch malformed URLs and verify a non-empty
host. Rejecting at config-load time is much better than crashing at
first webhook send.

**Fix:**
```python
from urllib.parse import urlsplit
...
@field_validator("webhook_url")
@classmethod
def _validate_webhook_url(cls, v: str | None) -> str | None:
    if v is None:
        return None
    parts = urlsplit(v)
    if parts.scheme not in ("http", "https"):
        raise ValueError("webhook_url must use http or https scheme")
    if not parts.netloc:
        raise ValueError("webhook_url must include a host")
    if not parts.hostname:
        raise ValueError("webhook_url has empty hostname")
    return v
```

Consider also rejecting `localhost`, `127.0.0.0/8`, `[::1]`, and
internal IPs unless an explicit `webhook_allow_local: bool = False` is
set — webhook-to-localhost is a typical ops mistake.

---

### WR-008: EventLogWriter.__init__ creates parent dir but never fsyncs it after creation

**File:** `src/spark_modem/event_logger/writer.py:72-79`
**Issue:** `self._path.parent.mkdir(parents=True, exist_ok=True)` is
followed immediately by `os.open(...)`. If the parent directory was
freshly created (i.e. no other on-disk operation has fsynced its parent
yet), a power loss between mkdir and the first append will lose the
events.jsonl file. Subsequent boots will see no events for the period
between writer-init and the first append.

This is the same dir-fsync discipline the atomic-write module enforces
(step 6 of the recipe). The event log is FR-43 / FR-43.1 — a structured
audit trail that must survive crash.

**Fix:** Either fsync the parent dir after mkdir:

```python
def __init__(self, path: Path | str) -> None:
    self._path = Path(path)
    parent = self._path.parent
    new_parent = not parent.exists()
    parent.mkdir(parents=True, exist_ok=True)
    self._fd: int | None = os.open(
        str(self._path),
        os.O_WRONLY | os.O_CREAT | os.O_APPEND,
        _MODE,
    )
    if new_parent and hasattr(os, "O_DIRECTORY"):
        from spark_modem.state_store.atomic import _fsync_directory
        _fsync_directory(parent, self._path)
```

Or — simpler — defer event-log directory creation to the postinst /
systemd `LogsDirectory=` machinery (CR-001 fix). The daemon then can
require the directory to exist at startup and refuse to start otherwise,
removing the runtime mkdir entirely.

---

### WR-009: AsyncFlockHandle.release() sets self._fd = None before the worker thread call returns

**File:** `src/spark_modem/state_store/locks.py:232-241`
**Issue:**
```python
async def release(self) -> None:
    fd = self._fd
    self._fd = None        # cleared BEFORE the to_thread call returns
    if fd is not None:
        await asyncio.to_thread(_release_flock_fd, fd)
```

If `release()` is called concurrently from two coroutines (defensive
pattern; e.g. an `__aexit__` racing with an explicit `release()`), both
read non-None `_fd`, both set it to None, both call
`_release_flock_fd(fd)` — the second call hits `os.close(fd)` on an
already-closed fd, which on Linux can race against fd-recycling and
close someone else's file. asyncio.Lock or a sentinel boolean would
prevent this.

In the current code this race is unreachable because `acquire_flock_async`
returns a fresh handle each call, and `__aexit__` is called exactly once,
but the `release()` method is also part of the public API (docstring says
"Or own the lifetime explicitly"). Defensive coding cost is one bool.

**Fix:**
```python
async def release(self) -> None:
    fd = self._fd
    if fd is None:
        return  # already released
    self._fd = None
    await asyncio.to_thread(_release_flock_fd, fd)
```

And consider an `_released` flag to make a double release explicitly a
no-op rather than relying on `_fd is None`.

---

### WR-010: postinst runs smoke test BEFORE creating the system user, leaving smoke-test failures in a "user not yet created" state

**File:** `debian/spark-modem-watchdog.postinst:6-29`
**Issue:** The order is:

1. Run smoke test (line 7-12).
2. If smoke test fails → `exit 1`.
3. Otherwise → create user, create dirs, mask ModemManager.

If the smoke test fails on first install, no user, no directories, no
ModemManager-mask state are set up. On `apt install` retry, the postinst
re-runs and the smoke test will fail again (the bug is environmental,
not transient) — never reaching the user-create. Operators end up in a
partial-install state.

`dpkg --configure -a` semantics: a failed postinst leaves the package in
"half-configured" status. The package can't be fully purged without
hand-editing dpkg's status file.

**Fix:** Run user creation, dir creation, and ModemManager mask FIRST,
then run the smoke test last. The smoke test failure is the right
gate — it just shouldn't leave the install in a half-configured state if
the failure is reproducible:

```bash
case "$1" in
  configure)
    # Set up user, dirs, mask ModemManager FIRST so a smoke-test failure
    # leaves the system in a "configured-but-broken" state that's easier
    # to diagnose than "half-configured".
    if ! id -u spark-modem-watchdog >/dev/null 2>&1; then
      adduser --system --group --no-create-home ...
    fi
    install -d -m 0750 -o spark-modem-watchdog -g spark-modem-watchdog ...
    if command -v systemctl >/dev/null 2>&1 && [[ -d /run/systemd/system ]]; then
      systemctl mask ModemManager.service >/dev/null 2>&1 || true
      systemctl --system daemon-reload >/dev/null || true
    fi

    # B-03 belt-and-suspenders A: smoke test last; failure means the bundled
    # Python or runtime libs are broken — refuse to complete install.
    if ! /opt/spark-modem-watchdog/libexec/postinst_smoke_test.sh; then
      echo "ERROR: spark-modem-watchdog postinst smoke test failed." >&2
      exit 1
    fi
    ;;
```

---

### WR-011: scripts/build_deb.sh's sed-based version rewrite is fragile and not reverted on success

**File:** `scripts/build_deb.sh:28-30`
**Issue:**

```bash
sed -i "1s/spark-modem-watchdog (2\.0\.0-1)/spark-modem-watchdog ($DEV_VERSION)/" debian/changelog
```

Two problems:

1. The sed-rewrite is destructive and not undone after the build. A dev
   build leaves `debian/changelog` modified in the working tree. The
   next dev build rewrites the *already-rewritten* line and the regex
   no longer matches `spark-modem-watchdog (2.0.0-1)` — silently no-op,
   producing a `.deb` with the *previous* dev tag.
2. The regex assumes the committed top-level version is exactly
   `2.0.0-1`. If the committed changelog ever gets a hotfix bump to
   `2.0.1-1`, this sed silently does nothing, the dev build ships with
   the hotfix version, and operators can't tell dev from release.

**Fix:** Use `git stash` + `git checkout` to revert, OR use a build dir:

```bash
# Build in a copy so the working tree is never touched.
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT
git archive HEAD | tar -C "$BUILD_DIR" -xf -
cd "$BUILD_DIR"
# now do the dch / sed rewrite + dpkg-buildpackage in the temp dir
```

Or commit to using `dch --force-bad-version` always (don't sed), and
fail loudly if `dch` is missing rather than fall back to a fragile sed.

---

## Info

### IN-001: Documentation drift: 9 vs 10 runtime libraries

**File:** `.planning/phases/01-foundations-adrs/01-CONTEXT.md` (item 1),
multiple sources reference "all 9 runtime libs"; `scripts/postinst_smoke_test.sh:17-28` imports 10 (`pydantic`, `pydantic_settings`, `yaml`, `prometheus_client`, `pyudev`, `pyroute2`, `asyncinotify`, `httpx`, `sdnotify`, `psutil`).
**Issue:** The CONTEXT.md and the SUMMARY.md both say "9 pinned runtime
libraries"; `pydantic_settings` was added (config/settings.py imports
from it) and the smoke test correctly expanded to 10. Comments in
`debian/rules` (line 51) say "all 10 runtime libs" but file-level
docstrings elsewhere still say 9.
**Fix:** Update `.planning/phases/01-foundations-adrs/01-CONTEXT.md`
boundary item 1 to "all 10 pinned runtime libraries" and search-and-
replace any remaining "9 libs" / "9 runtime libs" mentions.

---

### IN-002: Unused parameter `expected_cdc_wdm` documented as forward-compat hook

**File:** `src/spark_modem/state_store/store.py:172, 252`
**Issue:** `load_modem_state` accepts `expected_cdc_wdm` and
immediately discards it: `_ = expected_cdc_wdm`. Forward-compat hooks
that aren't actually wired into the call chain tend to bit-rot: when
Phase 2 lands, the new code may add behavior at a different layer and
the param sits unused forever.
**Fix:** Either wire it now (pass to `cross_check_inventory_for` and
remove the second arg there too — it's a partial duplicate), or remove
it entirely until Phase 2 needs it. YAGNI.

---

### IN-003: _now_iso() duplicated across modules

**File:** `src/spark_modem/state_store/store.py:462-464` and
`src/spark_modem/clock/clock.py:32-39` both define a now-as-ISO function.
**Issue:** Two implementations of "datetime.now(UTC).isoformat()" with
slightly different signatures (clock.wall_clock_iso accepts an explicit
tz; state_store._now_iso doesn't). The state_store version doesn't go
through the clock module — which the clock module's docstring
specifically forbids ("Never call time.monotonic() or time.time()
directly outside this module"). Same principle applies to wall-clock
ISO; the indirection lets policy/ accept a Clock Protocol stub for tests.
**Fix:** Replace `_now_iso()` in store.py with `wall_clock_iso()` from
the clock module; delete the duplicate.

---

### IN-004: Path.with_suffix on multi-suffix file produces wrong shadow name

**File:** `src/spark_modem/wire/versioning.py:64-73`
**Issue:** `shadow_filename(Path("foo.from-v0.json"), from_version=1)`
returns `Path("foo.from-v0.from-v1.json")` because `Path.with_suffix`
only replaces the last suffix. This is correct for `2-3.1.1.json` but
not for the (impossible-but-defensible) case of double-shadowed files.
The current state-store load path never hits this because it only loads
unshadowed files (the `.from-v` substring filter in
`list_modem_state_usb_paths` excludes them).
**Fix:** Add a unit test that `shadow_filename(p, from_version=N)` is
idempotent for `p` already containing `.from-vM.`, and either accept
chained shadows (current behavior) or assert no `.from-v` substring on
input. Document in the docstring that input is assumed unshadowed.

---

### IN-005: Settings does not pass model_config in inheritance chain to BaseSettings

**File:** `src/spark_modem/config/settings.py:31-36`
**Issue:** `model_config = SettingsConfigDict(env_prefix=...)` overrides
the BaseSettings default but does NOT carry forward populate_by_name=True
or extra='forbid' from the BaseWire class — Settings doesn't inherit
from BaseWire (it can't; it's a BaseSettings). The frozen=True field is
on Settings only. This is structurally correct (BaseWire is the wire
boundary; BaseSettings is the env+flag boundary), but the codebase's
discipline of "every wire model frozen" doesn't mention that Settings
follows the same rule.
**Fix:** Just a comment update; no code change required. Add a one-line
comment near `model_config` saying "Settings is the env+flag boundary;
not a wire type, but follows the same frozen+forbid discipline."

---

### IN-006: Lint script doesn't catch `import subprocess`

**File:** `scripts/lint_no_subprocess.sh:8`
**Issue:** The pattern catches usage (`subprocess.run`, etc.) but a file
that does `import subprocess` and never uses it would slip through. More
realistically, a developer might `from subprocess import Popen` (in
which case the lint catches `Popen` only if used unqualified — actually
the regex wouldn't match a bare `Popen` call). The current regex says
`subprocess\.(run|Popen|...)` which requires the `subprocess.` prefix.
**Fix:** Add a stricter pattern to also match a from-imports:
```bash
PATTERN='create_subprocess_exec|create_subprocess_shell|subprocess\.(run|Popen|call|check_call|check_output)|os\.system|^import subprocess|^from subprocess import'
```
Or, simpler: lint that `import subprocess` is in only `subproc/runner.py`. Currently it's not even imported there (the runner uses asyncio.subprocess), so banning the synchronous import everywhere except `subproc/` is enforceable.

---

### IN-007: Postrm `deluser --system` race against systemctl operations

**File:** `debian/spark-modem-watchdog.postrm:24-27`
**Issue:** On purge, postrm unmasks ModemManager, removes
`/opt/spark-modem-watchdog`, removes `/var/lib/...` and `/var/log/...`,
THEN runs `deluser --system spark-modem-watchdog`. If the daemon is
still running (e.g. a stop in progress), removing the venv and state
dirs while the process is alive can produce confusing logs and may even
cause the service to crash on a different path. Postrm runs after
`prerm stop` in a typical Debian sequence, but on `disappear` /
`failed-upgrade` cases, the order is less guaranteed.
**Fix:** Add an explicit `systemctl stop spark-modem-watchdog` before
the rm operations, with `|| true` so a not-running service doesn't
fail purge:
```bash
purge)
    if command -v systemctl >/dev/null 2>&1 && [[ -d /run/systemd/system ]]; then
      systemctl stop spark-modem-watchdog.service >/dev/null 2>&1 || true
      systemctl disable spark-modem-watchdog.service >/dev/null 2>&1 || true
      systemctl unmask ModemManager.service >/dev/null 2>&1 || true
      systemctl --system daemon-reload >/dev/null || true
    fi
    rm -rf /opt/spark-modem-watchdog || true
    ...
```

---

### IN-008: ModemState validator names use leading underscore but pydantic decorator expects public method conceptually

**File:** `src/spark_modem/wire/state.py:65-84`
**Issue:** `_check_recovering_level` and `_check_counters_nonneg` are
prefixed with an underscore, signalling "private" — but `model_validator`
turns them into part of the validation surface and they appear in error
messages. Convention in pydantic v2 codebases is to use a non-underscore
name (the decorator handles non-public-API) so the error path is more
readable:
```
ValidationError: ... [type=value_error, ...]
  validation by check_recovering_level
```
versus
```
  validation by _check_recovering_level
```

Minor stylistic nit. Both work.
**Fix:** Rename to `check_recovering_level` and `check_counters_nonneg`,
or add a `# noqa` comment if ruff complains.

---

### IN-009: Carrier table schema has no top-level `country: str` validator for ISO-3166 alpha-2 set

**File:** `src/spark_modem/wire/carriers.py:21`
**Issue:** `country: StrictStr = Field(pattern=r"^[A-Z]{2}$")` — accepts
any two uppercase letters including `XX`, `ZZ`, `QQ`. The carrier table
fixtures explicitly cover IL/US/UK/DE; rejecting nonsensical ISO codes
at config-load is a small win.
**Fix:** Maintain a static set of accepted alpha-2 codes (or use the
`pycountry` library — but adding a dependency for one validator is
overkill). A simple `@field_validator` against a frozen set covers
edge cases:
```python
_ISO_3166_ALPHA2 = frozenset({"IL", "US", "UK", "GB", "DE", ...})

@field_validator("country")
@classmethod
def _validate_country(cls, v: str) -> str:
    if v not in _ISO_3166_ALPHA2:
        raise ValueError(f"unknown country code: {v}")
    return v
```
Alternative: leave as-is and rely on operator review at carrier-table
edit time. Phase 1 carrier table is a static config file maintained by
product (per PRD Q7), so this is low-risk.

---

_Reviewed: 2026-05-06_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
