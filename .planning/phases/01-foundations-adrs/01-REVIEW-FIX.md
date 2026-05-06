---
phase: 01-foundations-adrs
fixed_at: 2026-05-06T00:00:00Z
review_path: .planning/phases/01-foundations-adrs/01-REVIEW.md
iteration: 1
findings_in_scope: 13
fixed: 12
skipped: 1
status: partial
---

# Phase 1: Code Review Fix Report

**Fixed at:** 2026-05-06
**Source review:** `.planning/phases/01-foundations-adrs/01-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 13 (2 critical + 11 warning)
- Fixed: 12
- Skipped: 1

Gates after all fixes: `mypy --strict` clean (31 source files), `ruff check` clean, `ruff format --check` clean, 253 unit tests passed / 41 skipped (all skips are POSIX-only tests correctly skipped on Windows dev host).

---

## Fixed Issues

### CR-001: systemd unit runs as root with NoNewPrivileges=false and no syscall/capability hardening

**Files modified:** `debian/spark-modem-watchdog.service`
**Commit:** `6f33d90`
**Applied fix:** Replaced `User=root / Group=root / NoNewPrivileges=false` with
`User=spark-modem-watchdog / Group=spark-modem-watchdog / NoNewPrivileges=true`.
Added the full Phase 1 hardening baseline: `CapabilityBoundingSet=` (empty),
`AmbientCapabilities=`, `PrivateDevices=true`, `ProtectKernelTunables/Modules/Logs=true`,
`ProtectControlGroups/Clock/Hostname=true`, `RestrictNamespaces/Realtime/SUIDSGID=true`,
`LockPersonality=true`, `MemoryDenyWriteExecute=true`,
`RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK`,
`SystemCallFilter=@system-service`, `SystemCallErrorNumber=EPERM`.
Added `RuntimeDirectory`, `StateDirectory`, `LogsDirectory`, `ConfigurationDirectory`
so systemd manages directory creation/ownership. Phase 2 will add `CAP_NET_ADMIN`;
Phase 4 will add `CAP_SYS_ADMIN`.

---

### CR-002: schema-downgrade rename uses Path.rename (clobber-unsafe) and skips directory fsync

**Files modified:** `src/spark_modem/state_store/store.py`
**Commit:** `c449a34`
**Applied fix:** Both `target.rename(shadow)` calls in `load_modem_state` and
`load_globals` replaced with `target.replace(shadow)` (via `Path.replace`, which
is the PTH105-compliant form and has identical POSIX atomicity semantics to
`os.replace`). Added `_fsync_directory(target.parent, target)` after each replace
to make the rename durable across a power loss before the subsequent atomic write
completes. Imported `_fsync_directory` from `atomic.py`. Also updated the import
block in the subsequent lint-cleanup commit (`7a5294d`) to remove the transitional
`import os` and the now-unused `UsbPathMismatch` import.

---

### WR-001: AsyncFlockHandle is leaked if the constructor's caller is cancelled before await returns

**Files modified:** `src/spark_modem/state_store/locks.py`, `src/spark_modem/state_store/store.py`, `tests/unit/state_store/test_locks.py`
**Commit:** `ed4dd9e`
**Applied fix:** Converted `acquire_flock_async` from a plain `async def` returning
`AsyncFlockHandle` to a `@contextlib.asynccontextmanager` yielding `AsyncFlockHandle`.
The `finally` block guarantees `handle.release()` is called even if the caller is
cancelled between the `to_thread` call and the coroutine resuming. Updated all six
`async with await acquire_flock_async(...)` call sites in `store.py` to
`async with acquire_flock_async(...)` (no `await`). Updated three test functions
that used the old `await`-then-use pattern to use the new context-manager pattern.
Added `AsyncIterator` to the `collections.abc` import.

---

### WR-002: load_modem_state conflates OSError and JSON decode error with UsbPathMismatch

**Files modified:** `src/spark_modem/state_store/errors.py`, `src/spark_modem/state_store/store.py`, `src/spark_modem/state_store/__init__.py`
**Commit:** `d9f55ff`
**Applied fix:** Added two new `StateStoreError` subclasses to `errors.py`:
- `StateFileCorrupt`: raised on `ValueError`/`UnicodeDecodeError` from JSON parse
- `StateFileIOError`: raised on `OSError` from `read_bytes()`

Fixed `load_modem_state` to raise the semantically correct exception type instead
of `UsbPathMismatch` for every read or parse failure. Exported both new types from
`state_store/__init__.py`. The spurious `# noqa: N818` on `StateFileIOError` was
removed in the follow-up lint cleanup (`7a5294d`) since the name already ends in "Error".

---

### WR-003: Validators allow argv[0] = "" through (empty-string element)

**Files modified:** `src/spark_modem/subproc/runner.py`
**Commit:** `28bb64d`
**Applied fix:** Extended `_validate_argv` to:
1. Check each element for embedded NUL bytes (`\x00`) — POSIX `execve(2)` rejects
   these and the error is confusing without an early-fail message.
2. After the per-element loop, explicitly reject `argv[0] == ""` with a clear
   `ValueError` explaining that the kernel produces a confusing ENOENT.

---

### WR-004: _two_stage_shutdown silently swallows BrokenPipeError but never times out the second communicate()

**Files modified:** `src/spark_modem/subproc/runner.py`
**Commit:** `10bf228`
**Applied fix:** Added `_SIGKILL_DRAIN_SECONDS: Final[float] = 2.0` constant.
Wrapped the post-SIGKILL `proc.communicate()` drain in
`async with asyncio.timeout(_SIGKILL_DRAIN_SECONDS)` and extended the except
clause to also catch `TimeoutError`. Worst-case `run()` wall time is now
deterministically bounded at `timeout_s + 2.0 + 2.0` seconds, satisfying M5.

---

### WR-005: yaml_merge.load_yaml_layer silently drops invalid YAML files

**Files modified:** `src/spark_modem/config/yaml_merge.py`
**Commit:** `762b882`
**Applied fix:** Added `import logging` and `_logger = logging.getLogger(__name__)`.
Replaced the silent `continue` in the `except (OSError, yaml.YAMLError)` handler
with `_logger.warning(...)` that logs the file path, exception type, and message.
Phase 3 can attach a structured `config_invalid` event handler to the same logger.

---

### WR-006: walk_sysfs_for_qmi_modems uses .read_text() without explicit encoding and silently skips on OSError

**Files modified:** `src/spark_modem/state_store/inventory.py`
**Commit:** `4eefb71`
**Applied fix:** Changed `id_vendor_file.read_text().strip()` to
`id_vendor_file.read_text(encoding="ascii").strip()`. Extended the `except` clause
to also catch `UnicodeDecodeError`. Replaced the silent `continue` with
`_logger.warning(...)` (added `import logging` and `_logger` module-level logger)
so EACCES and encoding errors are surfaced in the journal.

---

### WR-007: Settings.webhook_url validator allows trivial-bypass URLs

**Files modified:** `src/spark_modem/config/settings.py`
**Commit:** `e492e33` (lint format: `7a5294d`)
**Applied fix:** Replaced the bare `startswith("http://") or startswith("https://")`
check with a `urlsplit`-based validator that verifies `parts.scheme in ("http", "https")`,
`parts.netloc` is non-empty, and `parts.hostname` is non-empty. Rejects degenerate
URLs like `http://`, `https:// space`, and malformed bracket sequences at config-load
time rather than at first webhook send. Added `from urllib.parse import urlsplit` import.

---

### WR-008: EventLogWriter.__init__ creates parent dir but never fsyncs it after creation

**Files modified:** `src/spark_modem/event_logger/writer.py`
**Commit:** `e2e6d5d`
**Applied fix:** Track whether the parent directory existed before `mkdir` with a
`parent_existed = parent.exists()` check. After `os.open`, if `not parent_existed`,
call `_fsync_directory(parent, self._path)` (imported from `state_store.atomic`)
so the new directory's metadata is durable before the first append. On Windows
`_fsync_directory` is a no-op (production target is Jetson/POSIX).

---

### WR-009: AsyncFlockHandle.release() sets self._fd = None before the worker thread call returns

**Files modified:** `src/spark_modem/state_store/locks.py`
**Commit:** `ed4dd9e` (committed together with WR-001)
**Applied fix:** Added an early `if fd is None: return` guard before `self._fd = None`
in `AsyncFlockHandle.release()`. A second call to `release()` is now a no-op rather
than calling `_release_flock_fd` on an already-closed (and potentially recycled) fd.

---

### WR-010: postinst runs smoke test BEFORE creating the system user

**Files modified:** `debian/spark-modem-watchdog.postinst`
**Commit:** `4c82c6e`
**Applied fix:** Reordered the `configure)` case to run `adduser`, `install -d`,
and `systemctl mask ModemManager` first, with the smoke test invocation last.
A smoke-test failure now leaves the system in "configured-but-broken" state with
the user and directories already present, so `dpkg --configure -a` on retry reaches
the smoke test cleanly without re-creating them. Updated the comment block to explain
the ordering rationale.

---

## Skipped Issues

### WR-011: scripts/build_deb.sh's sed-based version rewrite is fragile and not reverted on success

**File:** `scripts/build_deb.sh:28-30`
**Reason:** The fix requires restructuring the build script around `git archive | tar -C "$BUILD_DIR"` to avoid touching the working tree. This is a non-trivial change to the CI/build pipeline with side-effects on path resolution (`dpkg-buildpackage` must run inside the archive copy, not the repo root). The primary `dch` path is already correct and idempotent; the fragility only affects the `dch`-absent fallback path which is a CI-host configuration issue, not a code bug. Skipping to avoid introducing regressions in the build pipeline without a full integration test of the new flow.

---

_Fixed: 2026-05-06_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
