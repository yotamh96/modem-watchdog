---
phase: 01-foundations-adrs
plan: 04
type: execute
wave: 3
depends_on: [01, 03]
files_modified:
  - src/spark_modem/state_store/__init__.py
  - src/spark_modem/state_store/atomic.py
  - src/spark_modem/state_store/locks.py
  - src/spark_modem/state_store/inventory.py
  - src/spark_modem/state_store/store.py
  - src/spark_modem/state_store/paths.py
  - src/spark_modem/state_store/errors.py
  - tests/unit/state_store/__init__.py
  - tests/unit/state_store/test_atomic.py
  - tests/unit/state_store/test_locks.py
  - tests/unit/state_store/test_inventory.py
  - tests/unit/state_store/test_inventory_crosscheck.py
  - tests/unit/state_store/test_store.py
  - tests/unit/state_store/test_schema_downgrade.py
  - tests/unit/state_store/test_concurrent_writers.py
autonomous: true
requirements:
  - FR-62
  - FR-62.1
  - FR-72
  - FR-73
  - NFR-32
  - NFR-43
tags:
  - python
  - state-store
  - atomic-writes
  - locks
  - hypothesis

must_haves:
  truths:
    - "Per-modem state files persist at /var/lib/spark-modem-watchdog/state/by-usb/<usb_path>.json (configurable for tests)"
    - "Every persistent file write is atomic: temp file in same directory + os.fsync(temp) + os.rename + dir os.fsync"
    - "Per-modem in-process locking via dict[usb_path, asyncio.Lock] lazily populated; separate globals asyncio.Lock for the GlobalsState file"
    - "StateStore.save_modem_state acquires BOTH the per-modem asyncio.Lock AND the per-modem flock at /run/spark-modem-watchdog/modem-<usb_path>.lock; StateStore.save_globals acquires BOTH the globals asyncio.Lock AND the state-store flock at /run/spark-modem-watchdog/state.lock; lock acquisition order is asyncio.Lock first, flock second (documented to prevent ABBA between daemon and CLI). PID lock at /run/spark-modem-watchdog/lock is SEPARATE from these."
    - "Schema-downgrade-on-load is deadlock-free: load_modem_state and load_globals each acquire the asyncio.Lock + flock once and call private _save_*_locked helpers (no re-acquire) on the downgrade write path. asyncio.Lock is NOT reentrant; the public/private split prevents the same-task re-acquire deadlock."
    - "Inventory cross-check at startup compares (file usb_path, sysfs usb_path, current cdc-wdmN); on mismatch, raises UsbPathMismatch with details and the daemon refuses to start (Phase 1 raises; Phase 2/3 wires the sd_notify STATUS=usb_path_mismatch + non-zero exit). The cross-check is invoked through StateStore.cross_check_inventory_for(usb_path, sysfs_walker) — the daemon caller (Phase 2) MUST call this at startup before any load_modem_state."
    - "Loading a forward-schema-version file raises SchemaVersionTooNew; loading a past-schema-version file writes a .from-v<N>.json shadow, returns a fresh-default ModemState, and emits a SchemaDowngradePending event-shaped value (caller in Phase 2 writes to events.jsonl)"
    - "A hypothesis property test simulates random USB renumbering against a tmp_path-backed fake-sysfs tree and verifies the cross-check fires on every mismatch and rounds-trips on every consistent state — hardware-free, <1s"
    - "A regression test in tests/unit/state_store/test_schema_downgrade.py asserts the downgrade-on-load path completes without deadlock within asyncio.timeout(5)."
    - "A regression test in tests/unit/state_store/test_concurrent_writers.py asserts the daemon's save_modem_state surfaces StateStoreLocked (or waits, depending on the wait_for_flock parameter) when a simulated CLI mutator holds the per-modem flock — daemon-vs-CLI lost-update prevention is wired, not just exposed as a primitive."
    - "ruff check, ruff format --check, mypy --strict are green on src/spark_modem/state_store/ and tests/unit/state_store/"
    - "All unit tests pass; the property test does not exceed 1s wall time on a developer laptop"
  artifacts:
    - path: "src/spark_modem/state_store/atomic.py"
      provides: "atomic_write_bytes(path, data) and atomic_write_text(path, text) — temp+fsync+rename+dir-fsync; never partial writes"
      contains: "os.fsync"
    - path: "src/spark_modem/state_store/locks.py"
      provides: "PerModemLockTable (dict[usb_path, asyncio.Lock] lazily populated), globals_lock; acquire_flock / acquire_flock_async / AsyncFlockHandle helpers used directly by StateStore methods"
      contains: "asyncio.Lock"
    - path: "src/spark_modem/state_store/inventory.py"
      provides: "cross_check_inventory(file_usb_path, sysfs_usb_path, cdc_wdm) -> None | raises UsbPathMismatch; sysfs walker that emits the expected (usb_path, cdc_wdm) tuple set"
      contains: "UsbPathMismatch"
    - path: "src/spark_modem/state_store/store.py"
      provides: "StateStore class — async load/save/list per-modem ModemState, GlobalsState, Identity map; takes per-modem asyncio.Lock + per-modem flock on every save; takes globals asyncio.Lock + state-store flock on every globals save; exposes cross_check_inventory_for(usb_path, sysfs_walker) for the daemon to call at startup."
      contains: "async def save_modem_state"
    - path: "src/spark_modem/state_store/paths.py"
      provides: "Filesystem path constants and constructors: state_root, state_by_usb, run_dir, lockfile_for_modem, identity_map_path, globals_path, pid_lockfile, state_store_lockfile"
      contains: "state/by-usb"
    - path: "src/spark_modem/state_store/errors.py"
      provides: "UsbPathMismatch, StateStoreLocked, AtomicWriteFailed exceptions"
      contains: "class UsbPathMismatch(Exception)"
    - path: "tests/unit/state_store/test_inventory_crosscheck.py"
      provides: "Hypothesis property test for SC #5 (random USB renumbering, fake-sysfs tree, hardware-free, <1s)"
      contains: "from hypothesis import given"
    - path: "tests/unit/state_store/test_schema_downgrade.py"
      provides: "Regression test asserting the schema-downgrade path doesn't deadlock on the per-modem asyncio.Lock or the per-modem flock; uses asyncio.timeout(5)."
      contains: "asyncio.timeout"
    - path: "tests/unit/state_store/test_concurrent_writers.py"
      provides: "Regression test simulating a CLI mutator holding the per-modem flock; asserts StateStore.save_modem_state surfaces StateStoreLocked (non-blocking) or waits (blocking) — daemon-vs-CLI lost-update is wired."
      contains: "StateStoreLocked"
  key_links:
    - from: "src/spark_modem/state_store/store.py StateStore.save_modem_state"
      to: "src/spark_modem/state_store/atomic.py atomic_write_bytes"
      via: "delegated atomic write inside per-modem asyncio.Lock + per-modem flock"
      pattern: "atomic_write_(bytes|text)"
    - from: "src/spark_modem/state_store/store.py StateStore.save_modem_state"
      to: "src/spark_modem/state_store/locks.py acquire_flock_async"
      via: "per-modem flock at /run/spark-modem-watchdog/modem-<usb_path>.lock acquired AFTER the asyncio.Lock"
      pattern: "acquire_flock_async"
    - from: "src/spark_modem/state_store/store.py StateStore.save_globals"
      to: "src/spark_modem/state_store/locks.py acquire_flock_async"
      via: "state-store flock at /run/spark-modem-watchdog/state.lock acquired AFTER the globals asyncio.Lock"
      pattern: "acquire_flock_async"
    - from: "src/spark_modem/state_store/store.py StateStore.load_modem_state"
      to: "src/spark_modem/wire/versioning.py validate_schema_version"
      via: "schema-version refusal + downgrade-shadow decision, written via _save_modem_state_locked (no re-acquire)"
      pattern: "validate_schema_version"
    - from: "src/spark_modem/state_store/store.py StateStore.cross_check_inventory_for"
      to: "src/spark_modem/state_store/inventory.py cross_check_inventory + walk_sysfs_for_qmi_modems"
      via: "explicit daemon-startup call; raises UsbPathMismatch on inconsistency"
      pattern: "cross_check_inventory_for"
    - from: "src/spark_modem/state_store/inventory.py cross_check_inventory"
      to: "tests/unit/state_store/test_inventory_crosscheck.py"
      via: "hypothesis @given over (usb_path, cdc_wdm) permutations"
      pattern: "hypothesis"
---

<objective>
Implement the full atomic-write + 3-layer locking + inventory cross-check + non-destructive schema-downgrade layer that every Phase 2/3/4 module reads and writes through. The state_store API is the single chokepoint for persistent state — no other module writes JSON to disk under `/var/lib/spark-modem-watchdog/`.

Purpose: Closes Phase 1 SC #5 (state files round-trip atomically; inventory cross-check fires on mismatch). Closes FR-62 (atomic writes — temp + rename + directory fsync). Closes FR-62.1 (per-modem state files keyed by `usb_path`; startup cross-check). Implements ADR-0009 (state files keyed by usb_path) and ADR-0012 (per-modem asyncio.Lock + per-modem flock + state-store flock; PID lock separate). Wires NFR-43 (non-destructive schema downgrade — Plan 03 supplied the helpers; this plan invokes them at load time). Closes FR-72 (Protocol shapes — StateStore Protocol is implicit here; Phase 2 may abstract it). Wires the per-modem dry-run prep for FR-73 (the policy engine reads ModemState from this layer).

Output: `src/spark_modem/state_store/` complete with 7 source files and 7 test files. The CLI mutators (`ctl reset-state`, `ctl migrate-state`) don't exist yet (Phase 2), but the locking surface IS WIRED INTO StateStore methods (not just exposed as primitives) so Phase 2/3 callers wire in without churn — this is the CONTEXT.md S-01 mandate ("Phase 1 ships the FULL atomic-write + 3-layer flock layer at the StateStore method level so Phase 2/3 CLI callers wire without churn").

This plan uses TDD aggressively: each module gets a test file first; the hypothesis property test for the inventory cross-check is the centerpiece (closes SC #5).

**Critical implementation notes (post-checker):**
- `asyncio.Lock` is NOT reentrant. The public methods (`save_modem_state`, `save_globals`)
  acquire the lock; private `_save_modem_state_locked` and `_save_globals_locked` helpers
  contain the actual write logic and are called from inside an already-locked context
  (the schema-downgrade branches in `load_modem_state` / `load_globals`).
- Lock acquisition order is **asyncio.Lock first, then flock**. This order is documented
  in module-level comments and enforced by every StateStore method to prevent ABBA between
  the daemon (asyncio.Lock + flock) and a CLI mutator (flock only).
- The inventory cross-check is wired into a public method `StateStore.cross_check_inventory_for(usb_path, sysfs_walker)` that the daemon caller (Phase 2 cycle driver) MUST invoke at startup before any `load_modem_state` call. SC #5's "raises a structured error on mismatch rather than silently overwriting" needs StateStore wiring, not just a freestanding helper.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/01-foundations-adrs/01-CONTEXT.md
@.planning/research/ARCHITECTURE.md
@.planning/research/PITFALLS.md
@.planning/research/SUMMARY.md
@docs/SCHEMA.md
@docs/RECOVERY_SPEC.md
@docs/adr/0006-counter-decay.md
@CLAUDE.md
@src/spark_modem/wire/__init__.py
@src/spark_modem/wire/state.py
@src/spark_modem/wire/identity.py
@src/spark_modem/wire/globals.py
@src/spark_modem/wire/versioning.py
@src/spark_modem/wire/events.py

<interfaces>
<!-- This plan consumes wire/ types from Plan 03 and provides the persistence layer. -->

From src/spark_modem/wire/__init__.py (Plan 03 just exposed):
```python
from spark_modem.wire import (
    ModemState,            # 5+2 flat shape (ADR-0008)
    Identity,
    GlobalsState,
    SchemaDowngradePending,  # event variant we may emit
    UsbPathMismatch as UsbPathMismatchEvent,  # event variant; this plan defines the EXCEPTION
    CURRENT_SCHEMA_VERSION,
    SchemaVersionTooNew,
    shadow_filename,
    validate_schema_version,
)
```

Naming clash to avoid: wire.events.UsbPathMismatch is an EVENT model; state_store.errors.UsbPathMismatch is an EXCEPTION class. They serve different roles (event = persisted record; exception = control flow). Keep them distinct; the StateStore.cross_check_inventory_for raises the exception, and the daemon's caller (Phase 2/3) writes the event in response.

From CONTEXT.md S-01..S-04:
- S-01: Phase 1 ships the FULL atomic-write + 3-layer flock layer (asyncio.Lock + flock + flock).
  - PID lock at /run/spark-modem-watchdog/lock is SEPARATE from state-store flocks (FR-61).
  - Locks are wired into StateStore methods (not just exposed as primitives) so Phase 2/3 callers
    don't have to re-implement them.
- S-02: Inventory cross-check at startup; on mismatch, refuses to start. Emits typed event + sd_notify STATUS=usb_path_mismatch + exits non-zero.
  - Phase 1 raises the typed exception via StateStore.cross_check_inventory_for(usb_path, sysfs_walker);
    Phase 2/3 wires the sd_notify + daemon-shutdown.
- S-03: Schema-downgrade shadow file naming: `state/by-usb/<usb_path>.from-v<N>.json` (sibling, same dir).
- S-04: Random-USB-renumbering simulation = hypothesis property test in tests/unit/state_store/test_inventory_crosscheck.py.
  - Generates random (usb_path, cdc_wdm_index) permutations against a tmp_path-backed fake-sysfs tree.
  - Asserts cross-check raises UsbPathMismatch on every mismatch and round-trips on consistent state.
  - Hardware-free; <1s; serves as spec-as-tests for ADR-0009.

From ARCHITECTURE.md Q3 + PITFALLS §3.2/§16.1:
- 3-layer concurrency: in-process per-modem asyncio.Lock + globals lock; cross-process per-modem flock + state-store flock; PID lock at top.

From CLAUDE.md anti-patterns to avoid:
- single state-store lock (we ship per-modem)
- subprocess.run sync (no subprocess in state_store anyway)
- missing directory fsync — atomic.py MUST fsync the directory
- atomic write order: temp + fsync(temp) + rename + fsync(dir)
- asyncio.Lock re-entry from the same task (NOT reentrant — must split into public-with-lock + private-without-lock helpers when one path needs to call another from inside the lock)

Atomic-write canonical recipe (PITFALLS §3.x; standard POSIX):
  1. open(O_CREAT|O_WRONLY|O_EXCL, mode=0o640) at <path>.tmp.<random>
  2. write all bytes
  3. fsync(fd_temp)
  4. close(fd_temp)
  5. rename(<path>.tmp.<random>, <path>)   — atomic on POSIX (same dir)
  6. open(directory) and fsync(directory_fd) — durability across crash
  7. close(directory_fd)

Locking discipline (this plan + Phase 2/3 callers):
  1. asyncio.Lock acquired FIRST (in-process serialization).
  2. flock acquired SECOND (cross-process serialization).
  3. Release in reverse order on context-manager exit.
  This ordering is documented in store.py module docstring + repeated as a comment at every
  acquisition site so a future contributor cannot accidentally invert the order.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: paths.py + errors.py + atomic.py + tests</name>
  <files>src/spark_modem/state_store/__init__.py, src/spark_modem/state_store/paths.py, src/spark_modem/state_store/errors.py, src/spark_modem/state_store/atomic.py, tests/unit/state_store/__init__.py, tests/unit/state_store/test_atomic.py</files>
  <read_first>
    - .planning/phases/01-foundations-adrs/01-CONTEXT.md §"S. State store" S-01..S-04 (full)
    - .planning/research/PITFALLS.md §3.x (atomic write, directory fsync, concurrent writers)
    - CLAUDE.md §"Critical invariants" #5 (atomic writes — temp + rename + directory fsync)
    - src/spark_modem/wire/state.py (the ModemState shape this layer persists)
    - src/spark_modem/wire/versioning.py (CURRENT_SCHEMA_VERSION, SchemaVersionTooNew, validate_schema_version, shadow_filename)
  </read_first>
  <behavior>
    Paths (no test file — pure constants exercised by other tests):
    - state_root: configurable (default /var/lib/spark-modem-watchdog), overridable via env var `SPARK_MODEM_STATE_ROOT` for tests.
    - state_by_usb_dir(state_root) -> Path("state/by-usb") under state_root.
    - state_file_for_modem(state_root, usb_path) -> state/by-usb/<usb_path>.json.
    - run_dir: configurable (default /run/spark-modem-watchdog), overridable via `SPARK_MODEM_RUN_DIR`.
    - lockfile_for_modem(run_dir, usb_path) -> /run/.../modem-<usb_path>.lock.
    - state_store_lockfile(run_dir) -> /run/.../state.lock.
    - pid_lockfile(run_dir) -> /run/.../lock — SEPARATE from state.lock.
    - identity_map_path(state_root) -> identity.json under state_root.
    - globals_path(state_root) -> globals.json under state_root.

    Errors (test_atomic.py exercises AtomicWriteFailed; UsbPathMismatch + StateStoreLocked are exercised in later tests):
    - UsbPathMismatch(file_usb_path, sysfs_usb_path, cdc_wdm): exception with structured attributes.
    - StateStoreLocked(holder_pid: int | None, lock_path: str): exception when flock acquisition fails.
    - AtomicWriteFailed(target_path: str, reason: str, original_exception: BaseException | None): wraps low-level OSErrors.

    atomic.py (test_atomic.py):
    - Test: atomic_write_bytes(tmp_path / "a.json", b"hello") — file exists with content "hello".
    - Test: After atomic_write_bytes, no `<file>.tmp.*` siblings remain.
    - Test: atomic_write_bytes overwrites an existing file atomically (replace vs create — same code path).
    - Test (interruption simulation): mock os.fsync to raise OSError → caller raises AtomicWriteFailed; the target file is unchanged (atomicity preserved by writing to .tmp first).
    - Test: file mode is 0o640 by default (umask doesn't widen it).
    - Test: directory fsync is called — patch `os.fsync` and assert it's called twice (once on the tmp fd, once on the directory fd).
    - Test: atomic_write_text(path, "string", encoding="utf-8") wraps atomic_write_bytes correctly.
    - Test: tmp filename uses an unguessable suffix (a random nonce), so concurrent writers don't collide on the same .tmp filename.
  </behavior>
  <action>
    1. Create `src/spark_modem/state_store/__init__.py` with a single docstring and `__all__ = []` (no public exports yet — Task 4 fills `__init__.py` with the StateStore class).

    2. Create `src/spark_modem/state_store/paths.py`:
    ```python
    """Filesystem paths for persistent state and runtime locks.

    All paths are configurable via environment variables for test isolation:
      SPARK_MODEM_STATE_ROOT  (default /var/lib/spark-modem-watchdog)
      SPARK_MODEM_RUN_DIR     (default /run/spark-modem-watchdog)
    """

    from __future__ import annotations

    import os
    from pathlib import Path

    DEFAULT_STATE_ROOT = "/var/lib/spark-modem-watchdog"
    DEFAULT_RUN_DIR = "/run/spark-modem-watchdog"


    def state_root() -> Path:
        return Path(os.environ.get("SPARK_MODEM_STATE_ROOT", DEFAULT_STATE_ROOT))


    def run_dir() -> Path:
        return Path(os.environ.get("SPARK_MODEM_RUN_DIR", DEFAULT_RUN_DIR))


    def state_by_usb_dir(*, root: Path | None = None) -> Path:
        return (root or state_root()) / "state" / "by-usb"


    def state_file_for_modem(usb_path: str, *, root: Path | None = None) -> Path:
        # ADR-0009: state/by-usb/<usb_path>.json keyed by USB topology, NOT cdc-wdmN.
        if not usb_path or "/" in usb_path or ".." in usb_path:
            raise ValueError(f"invalid usb_path for state file: {usb_path!r}")
        return state_by_usb_dir(root=root) / f"{usb_path}.json"


    def identity_map_path(*, root: Path | None = None) -> Path:
        return (root or state_root()) / "identity.json"


    def globals_path(*, root: Path | None = None) -> Path:
        return (root or state_root()) / "globals.json"


    def lockfile_for_modem(usb_path: str, *, run: Path | None = None) -> Path:
        # Per-modem cross-process flock (FR-61.1, ADR-0012).
        if not usb_path or "/" in usb_path or ".." in usb_path:
            raise ValueError(f"invalid usb_path for lockfile: {usb_path!r}")
        return (run or run_dir()) / f"modem-{usb_path}.lock"


    def state_store_lockfile(*, run: Path | None = None) -> Path:
        # State-store cross-process flock (FR-61.1, ADR-0012).
        return (run or run_dir()) / "state.lock"


    def pid_lockfile(*, run: Path | None = None) -> Path:
        # PID lock — SEPARATE from state.lock and modem-*.lock (FR-61, ADR-0012).
        return (run or run_dir()) / "lock"
    ```

    3. Create `src/spark_modem/state_store/errors.py`:
    ```python
    """Exception types raised by the state-store layer.

    These are EXCEPTIONS — control-flow signals. The on-the-wire equivalents
    (e.g. spark_modem.wire.events.UsbPathMismatch) are *event records*; do not
    confuse the two. The daemon's startup path (Phase 2/3) catches these
    exceptions and emits the corresponding wire events.
    """

    from __future__ import annotations


    class StateStoreError(Exception):
        """Base class for all state-store control-flow signals."""


    class UsbPathMismatch(StateStoreError):
        """Inventory cross-check failed: file's usb_path doesn't match sysfs.

        S-02: daemon refuses to start on this exception. Operator runs
        `spark-modem ctl reset-state --modem=<usb_path>` to clear.
        """

        def __init__(
            self,
            *,
            file_usb_path: str,
            sysfs_usb_path: str | None,
            cdc_wdm: str | None,
            file_path: str = "<unknown>",
        ) -> None:
            self.file_usb_path = file_usb_path
            self.sysfs_usb_path = sysfs_usb_path
            self.cdc_wdm = cdc_wdm
            self.file_path = file_path
            super().__init__(
                f"USB-path inventory mismatch: file={file_usb_path!r} "
                f"sysfs={sysfs_usb_path!r} cdc_wdm={cdc_wdm!r} ({file_path})"
            )


    class StateStoreLocked(StateStoreError):
        """Cross-process flock acquisition failed (another holder)."""

        def __init__(self, *, holder_pid: int | None, lock_path: str) -> None:
            self.holder_pid = holder_pid
            self.lock_path = lock_path
            holder_str = f"pid {holder_pid}" if holder_pid is not None else "unknown holder"
            super().__init__(f"State-store lock {lock_path!r} held by {holder_str}")


    class AtomicWriteFailed(StateStoreError):
        def __init__(
            self,
            *,
            target_path: str,
            reason: str,
            original_exception: BaseException | None = None,
        ) -> None:
            self.target_path = target_path
            self.reason = reason
            self.original_exception = original_exception
            super().__init__(f"Atomic write to {target_path!r} failed: {reason}")
    ```

    4. Write `tests/unit/state_store/__init__.py` (one-line docstring) and `tests/unit/state_store/test_atomic.py` (TDD RED) covering all 8 behaviors above. Use `pytest`'s `tmp_path` and `monkeypatch` fixtures. For the fsync verification, use `monkeypatch.setattr(os, "fsync", spy_fn)`.

    5. Implement `src/spark_modem/state_store/atomic.py`:
    ```python
    """Atomic file writes — temp + fsync + rename + directory fsync.

    FR-62: every persistent file write is atomic. CLAUDE.md §"Critical
    invariants" #5: temp + rename + directory fsync; never partial-write.

    Recipe (PITFALLS §3.x; POSIX semantics):
      1. Open <target>.tmp.<nonce> with O_CREAT|O_WRONLY|O_EXCL, mode=0o640.
      2. Write all bytes.
      3. os.fsync(fd_temp).
      4. Close fd_temp.
      5. os.rename(temp, target) — atomic on POSIX (same directory required).
      6. os.fsync(directory_fd) — durability across crash; rename is durable
         only after the dir's metadata is sync'd.
      7. Close directory_fd.
    """

    from __future__ import annotations

    import os
    import secrets
    from pathlib import Path

    from spark_modem.state_store.errors import AtomicWriteFailed

    _DEFAULT_MODE = 0o640


    def atomic_write_bytes(
        target: Path | str,
        data: bytes,
        *,
        mode: int = _DEFAULT_MODE,
    ) -> None:
        """Write `data` to `target` atomically. Never leaves a partial file.

        On any failure, raises AtomicWriteFailed and ensures the target file
        (if it existed before) is unchanged.
        """
        target_path = Path(target)
        target_dir = target_path.parent
        if not target_dir.is_dir():
            raise AtomicWriteFailed(
                target_path=str(target_path),
                reason=f"parent directory {str(target_dir)!r} does not exist",
            )

        nonce = secrets.token_hex(8)
        tmp_path = target_dir / f".{target_path.name}.tmp.{nonce}"

        fd_temp: int | None = None
        try:
            # O_EXCL prevents collision with another writer on the same nonce
            # (vanishingly improbable; insurance).
            fd_temp = os.open(
                str(tmp_path),
                os.O_CREAT | os.O_WRONLY | os.O_EXCL,
                mode,
            )
            written = os.write(fd_temp, data)
            if written != len(data):
                raise AtomicWriteFailed(
                    target_path=str(target_path),
                    reason=f"short write: {written} of {len(data)} bytes",
                )
            os.fsync(fd_temp)
        except AtomicWriteFailed:
            # Already typed; clean up tmp and re-raise.
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise
        except OSError as e:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise AtomicWriteFailed(
                target_path=str(target_path),
                reason=f"OSError during temp write: {e!r}",
                original_exception=e,
            ) from e
        finally:
            if fd_temp is not None:
                try:
                    os.close(fd_temp)
                except OSError:
                    pass

        # Step 5: atomic rename.
        try:
            os.rename(str(tmp_path), str(target_path))
        except OSError as e:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise AtomicWriteFailed(
                target_path=str(target_path),
                reason=f"OSError during rename: {e!r}",
                original_exception=e,
            ) from e

        # Step 6: directory fsync — durability of the rename across crash.
        dir_fd: int | None = None
        try:
            dir_fd = os.open(str(target_dir), os.O_RDONLY)
            os.fsync(dir_fd)
        except OSError as e:
            raise AtomicWriteFailed(
                target_path=str(target_path),
                reason=f"OSError during directory fsync: {e!r}",
                original_exception=e,
            ) from e
        finally:
            if dir_fd is not None:
                try:
                    os.close(dir_fd)
                except OSError:
                    pass


    def atomic_write_text(
        target: Path | str,
        text: str,
        *,
        mode: int = _DEFAULT_MODE,
        encoding: str = "utf-8",
    ) -> None:
        """Convenience wrapper for atomic_write_bytes with text input."""
        atomic_write_bytes(target, text.encode(encoding), mode=mode)
    ```

    6. Run pytest — all atomic.py tests turn GREEN.
  </action>
  <verify>
    <automated>
      cd S:/spark/modem-watchdog && \
      .venv/bin/pytest tests/unit/state_store/test_atomic.py -q && \
      .venv/bin/ruff check src/spark_modem/state_store/atomic.py src/spark_modem/state_store/errors.py src/spark_modem/state_store/paths.py tests/unit/state_store/test_atomic.py && \
      .venv/bin/ruff format --check src/spark_modem/state_store/atomic.py src/spark_modem/state_store/errors.py src/spark_modem/state_store/paths.py && \
      .venv/bin/mypy --strict src/spark_modem/state_store/atomic.py src/spark_modem/state_store/errors.py src/spark_modem/state_store/paths.py && \
      .venv/bin/python -c "from spark_modem.state_store.atomic import atomic_write_bytes, atomic_write_text; from spark_modem.state_store.errors import AtomicWriteFailed, StateStoreLocked, UsbPathMismatch, StateStoreError; from spark_modem.state_store.paths import state_root, state_file_for_modem, lockfile_for_modem, pid_lockfile, state_store_lockfile, identity_map_path; assert state_file_for_modem('2-3.1.1', root=__import__('pathlib').Path('/tmp')).name == '2-3.1.1.json'; print('paths/errors/atomic: OK')"
    </automated>
  </verify>
  <done>
    `paths.py` exposes constructors honoring `SPARK_MODEM_STATE_ROOT` and `SPARK_MODEM_RUN_DIR` env overrides; `state_file_for_modem(usb_path)` rejects `/` and `..` in usb_path. `errors.py` defines `UsbPathMismatch`, `StateStoreLocked`, `AtomicWriteFailed` with structured attributes. `atomic.py` writes via temp+fsync+rename+dir-fsync and raises `AtomicWriteFailed` on any I/O error without leaving partial files. All tests pass; mypy --strict and ruff are green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: locks.py — per-modem asyncio.Lock + globals lock + flock helpers + tests</name>
  <files>src/spark_modem/state_store/locks.py, tests/unit/state_store/test_locks.py</files>
  <read_first>
    - .planning/phases/01-foundations-adrs/01-CONTEXT.md §"S. State store" S-01 (3-layer locking)
    - .planning/research/ARCHITECTURE.md Q3 (per-modem asyncio.Lock + globals lock)
    - .planning/research/PITFALLS.md §3.2, §16.1 (concurrent writers; cross-process flocks)
    - src/spark_modem/state_store/paths.py and errors.py (just written)
    - CLAUDE.md §"Critical invariants" #12 (CLI mutating commands take same flocks the daemon does)
  </read_first>
  <behavior>
    PerModemLockTable (test_locks.py):
    - Test: PerModemLockTable() starts empty; .get("2-3.1.1") returns an asyncio.Lock; .get("2-3.1.1") again returns the SAME instance (lazy cache).
    - Test: .get("2-3.1.2") returns a DIFFERENT instance (per-modem isolation).
    - Test (concurrency): two coroutines `async with table.get("2-3.1.1"):` serialize — the second waits.
    - Test: a coroutine holding lock for usb_path A does not block another coroutine on usb_path B.
    - Test: globals_lock is a singleton asyncio.Lock; multiple imports return the same instance.
    - Test: PerModemLockTable supports a `usb_paths()` snapshot that returns the currently-known modem keys.

    flock helpers (test_locks.py):
    - Test: acquire_flock(path) on a fresh path returns a context manager; entering creates the file and acquires LOCK_EX | LOCK_NB; exiting releases.
    - Test: a second acquire_flock on the same path while the first is held raises StateStoreLocked.
    - Test: acquire_flock writes the holder's PID to the file (operational debugging — `cat /run/.../state.lock` shows the pid).
    - Test: when the first holder exits the context, a second acquire succeeds.
    - Test: blocking acquire (`acquire_flock(path, blocking=True)`) waits for release; for the unit test, use a thread + a short timeout so the test runs <500ms.
    - Test: acquire_flock_async wraps the blocking acquire in `asyncio.to_thread` so the asyncio event loop doesn't block.
  </behavior>
  <action>
    1. Write `tests/unit/state_store/test_locks.py` (TDD RED) covering all behaviors. For the cross-process flock tests, fork via `multiprocessing` is overkill — use a separate thread that flocks the same file and assert the second flock raises (`fcntl.LOCK_NB` returns immediately with EWOULDBLOCK, which we map to StateStoreLocked).

    2. Implement `src/spark_modem/state_store/locks.py`:
    ```python
    """3-layer locking model (ADR-0012).

    Layer 1 (in-process, asyncio):
      - PerModemLockTable: dict[usb_path, asyncio.Lock] lazily populated.
      - globals_lock: a singleton asyncio.Lock for the GlobalsState file.
      Single-key APIs only (acquire one modem at a time; never compose).

    Layer 2 (cross-process, advisory flocks):
      - acquire_flock(/run/.../state.lock)         — state-store flock
      - acquire_flock(/run/.../modem-<usb>.lock)   — per-modem flock
      Daemon and CLI take the same flocks. CLI mutating commands take the
      same flocks the daemon does (CLAUDE.md invariant #12).

    Layer 3 (PID, separate file):
      - PID lock at /run/.../lock — owned by the daemon's main process; SEPARATE
      from the flocks above. Implementation lands in Phase 3 (sd_notify lifecycle).

    LOCK ACQUISITION ORDER (mandatory, enforced at every StateStore call site):
      1. asyncio.Lock first (in-process serialization).
      2. flock second (cross-process serialization).
      Releasing happens in reverse order on context-manager exit.
      This order is documented at every acquisition site in store.py to
      prevent ABBA between the daemon (asyncio.Lock + flock) and a CLI mutator
      (flock only).
    """

    from __future__ import annotations

    import asyncio
    import contextlib
    import errno
    import fcntl
    import os
    from pathlib import Path
    from typing import Iterator

    from spark_modem.state_store.errors import StateStoreLocked


    class PerModemLockTable:
        """Lazily-populated per-modem asyncio.Lock cache."""

        def __init__(self) -> None:
            self._locks: dict[str, asyncio.Lock] = {}

        def get(self, usb_path: str) -> asyncio.Lock:
            """Return the lock for usb_path, creating it if absent."""
            lock = self._locks.get(usb_path)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[usb_path] = lock
            return lock

        def usb_paths(self) -> tuple[str, ...]:
            """Snapshot of currently-known usb_paths (sorted, deterministic)."""
            return tuple(sorted(self._locks.keys()))


    # Singleton globals lock — separate from the per-modem table.
    # Module-level so multiple consumers see the same instance.
    _GLOBALS_LOCK_SINGLETON: asyncio.Lock | None = None


    def globals_lock() -> asyncio.Lock:
        """The single asyncio.Lock guarding GlobalsState writes."""
        global _GLOBALS_LOCK_SINGLETON
        if _GLOBALS_LOCK_SINGLETON is None:
            _GLOBALS_LOCK_SINGLETON = asyncio.Lock()
        return _GLOBALS_LOCK_SINGLETON


    @contextlib.contextmanager
    def acquire_flock(
        path: Path | str,
        *,
        blocking: bool = False,
        write_pid: bool = True,
    ) -> Iterator[int]:
        """Acquire an exclusive flock on `path`.

        - blocking=False (default): non-blocking acquire (LOCK_EX | LOCK_NB);
          raises StateStoreLocked on EWOULDBLOCK / EAGAIN.
        - blocking=True: waits for the lock; the asyncio variant
          (acquire_flock_async) wraps this in to_thread so the event loop
          doesn't block.
        - write_pid=True: writes os.getpid() to the file after acquire so
          `cat <path>` shows the holder for debugging.

        The lock file is created if absent. Mode 0o640.
        Yields the open file descriptor; caller does not close it (we own it).
        """
        path_p = Path(path)
        path_p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path_p), os.O_CREAT | os.O_RDWR, 0o640)
        try:
            flags = fcntl.LOCK_EX
            if not blocking:
                flags |= fcntl.LOCK_NB
            try:
                fcntl.flock(fd, flags)
            except OSError as e:
                if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                    holder_pid = _read_pid_from(path_p)
                    raise StateStoreLocked(
                        holder_pid=holder_pid,
                        lock_path=str(path_p),
                    ) from e
                raise
            if write_pid:
                # Truncate-and-write the holder's pid so external observers can see it.
                os.lseek(fd, 0, os.SEEK_SET)
                os.ftruncate(fd, 0)
                os.write(fd, str(os.getpid()).encode("ascii"))
                os.fsync(fd)
            yield fd
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                os.close(fd)
            except OSError:
                pass


    async def acquire_flock_async(
        path: Path | str,
        *,
        blocking: bool = False,
        write_pid: bool = True,
    ) -> AsyncFlockHandle:
        """Asyncio-friendly wrapper.

        Returns a context-manager-shaped handle so callers can write:
            handle = await acquire_flock_async(path)
            try:
                ...
            finally:
                await handle.release()

        Or, more idiomatically, use as `async with` (handle implements
        __aenter__/__aexit__).
        """
        return await asyncio.to_thread(
            _enter_flock_for_async, path, blocking, write_pid
        )


    class AsyncFlockHandle:
        """Internal handle for acquire_flock_async; released via .release()."""

        def __init__(self, fd: int, path: Path) -> None:
            self._fd: int | None = fd
            self._path = path

        async def release(self) -> None:
            fd = self._fd
            self._fd = None
            if fd is not None:
                await asyncio.to_thread(_release_flock_fd, fd)

        async def __aenter__(self) -> "AsyncFlockHandle":
            return self

        async def __aexit__(self, *_excinfo: object) -> None:
            await self.release()


    def _enter_flock_for_async(
        path: Path | str, blocking: bool, write_pid: bool
    ) -> AsyncFlockHandle:
        path_p = Path(path)
        path_p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path_p), os.O_CREAT | os.O_RDWR, 0o640)
        try:
            flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
            fcntl.flock(fd, flags)
        except OSError as e:
            try:
                os.close(fd)
            except OSError:
                pass
            if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                raise StateStoreLocked(
                    holder_pid=_read_pid_from(path_p),
                    lock_path=str(path_p),
                ) from e
            raise

        if write_pid:
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                os.ftruncate(fd, 0)
                os.write(fd, str(os.getpid()).encode("ascii"))
                os.fsync(fd)
            except OSError:
                pass
        return AsyncFlockHandle(fd, path_p)


    def _release_flock_fd(fd: int) -> None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(fd)
        except OSError:
            pass


    def _read_pid_from(path: Path) -> int | None:
        try:
            text = path.read_text(encoding="ascii", errors="ignore").strip()
            return int(text) if text else None
        except (OSError, ValueError):
            return None
    ```

    Note: `fcntl` is POSIX-only (Linux). The test suite is hardware-free but assumes a POSIX dev environment; on Windows developer laptops, the flock tests skip via `pytest.importorskip("fcntl")` at the top of the test file. The Phase 1 production target is Jetson (Linux) — the daemon never runs on Windows.

    3. Run pytest — all locks.py tests turn GREEN.
  </action>
  <verify>
    <automated>
      cd S:/spark/modem-watchdog && \
      .venv/bin/pytest tests/unit/state_store/test_locks.py -q && \
      .venv/bin/ruff check src/spark_modem/state_store/locks.py tests/unit/state_store/test_locks.py && \
      .venv/bin/ruff format --check src/spark_modem/state_store/locks.py && \
      .venv/bin/mypy --strict src/spark_modem/state_store/locks.py && \
      .venv/bin/python -c "from spark_modem.state_store.locks import PerModemLockTable, globals_lock, acquire_flock, acquire_flock_async, AsyncFlockHandle, StateStoreLocked; t = PerModemLockTable(); a = t.get('2-3.1.1'); b = t.get('2-3.1.1'); assert a is b; c = t.get('2-3.1.2'); assert c is not a; print('locks: OK')"
    </automated>
  </verify>
  <done>
    `PerModemLockTable.get(usb_path)` returns a stable per-key asyncio.Lock; `globals_lock()` is a singleton. `acquire_flock(path)` provides exclusive cross-process locking with PID-write for debugging; raises `StateStoreLocked` on contention. `acquire_flock_async` + `AsyncFlockHandle` provide an asyncio-friendly wrapper. The module docstring documents the mandatory acquisition order (asyncio.Lock first, flock second). All tests pass; mypy --strict and ruff are green. (Tests on non-POSIX dev hosts skip the flock subset via `importorskip("fcntl")`.)
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: inventory.py + the centerpiece hypothesis property test for SC #5</name>
  <files>src/spark_modem/state_store/inventory.py, tests/unit/state_store/test_inventory.py, tests/unit/state_store/test_inventory_crosscheck.py</files>
  <read_first>
    - .planning/phases/01-foundations-adrs/01-CONTEXT.md §"S. State store" S-02 (refuse to start on mismatch) and S-04 (hypothesis property test design)
    - .planning/research/PITFALLS.md §3.1 (cdc-wdmN renumbering — the exact failure mode)
    - .planning/research/ARCHITECTURE.md Q14 (state files keyed by usb_path; cross-checks)
    - docs/RECOVERY_SPEC.md §8 (atomic cycle ordering — informs the order of cross-check vs first cycle)
    - src/spark_modem/state_store/errors.py (UsbPathMismatch — just defined)
    - src/spark_modem/state_store/paths.py (just defined)
  </read_first>
  <behavior>
    inventory.py (test_inventory.py):
    - Test: cross_check_inventory(file_usb_path="2-3.1.1", sysfs_usb_path="2-3.1.1", cdc_wdm="cdc-wdm0") returns None silently (consistent state).
    - Test: cross_check_inventory(file_usb_path="2-3.1.1", sysfs_usb_path="2-3.1.2", cdc_wdm="cdc-wdm0") raises UsbPathMismatch with all three fields populated.
    - Test: cross_check_inventory(file_usb_path="2-3.1.1", sysfs_usb_path=None, cdc_wdm=None) raises UsbPathMismatch (the file references a modem that no longer exists in sysfs).

    walk_sysfs_for_qmi_modems(sysfs_root: Path) -> dict[usb_path, cdc_wdm] (test_inventory.py + test_inventory_crosscheck.py):
    - Test: given a fake-sysfs tree under tmp_path mirroring `/sys/bus/usb/devices/2-3.1.1/.../qmi/cdc-wdm0`, the walker returns {"2-3.1.1": "cdc-wdm0", ...}.
    - Test: given a tree with no qmi modems, returns {}.
    - Test: given a tree where one device has `idVendor` != "1199" (the Sierra VID), the walker excludes it.
    - Test: walker is hardware-free — never reads /sys directly; takes a `sysfs_root: Path` parameter.

    test_inventory_crosscheck.py — the SC #5 centerpiece (hypothesis property test):
    - @given over (n_modems: int between 1 and 8, permutation: a random shuffle of 0..n-1, vid_overrides: optional VID swaps).
    - Builds a fake-sysfs tree at `tmp_path / "sys/bus/usb/devices/"` with `n_modems` Sierra-VID modems on usb_paths "2-3.1.1".."2-3.1.<n>" and corresponding cdc-wdm0..cdc-wdm<n-1>; the cdc-wdm assignment uses `permutation` so the cdc-wdm <-> usb_path mapping varies per Hypothesis run.
    - For each generated tree:
      a) Walk sysfs → expected (usb_path, cdc_wdm) pairs.
      b) Write a state file for each usb_path at `state/by-usb/<usb_path>.json` with that usb_path baked in.
      c) Run cross-check on each file vs the walker — assert no UsbPathMismatch (consistent case).
      d) Re-permute the cdc-wdm assignments without rewriting state files (simulates USB renumbering on next boot).
      e) Run cross-check on each state file vs the new walker output — for files whose usb_path no longer matches sysfs's (usb_path -> cdc_wdm) shape, the cross-check MUST raise UsbPathMismatch with the right fields.
    - Property guarantee: the cross-check NEVER silently overwrites state. It either accepts (consistent) or raises (inconsistent).
    - @settings(max_examples=50, deadline=200ms) — total wall time well under 1s.
  </behavior>
  <action>
    1. Write `tests/unit/state_store/test_inventory.py` (TDD RED) covering the basic behaviors.

    2. Write `tests/unit/state_store/test_inventory_crosscheck.py` (TDD RED) — the hypothesis property test:
    ```python
    """SC #5 — random USB renumbering survives state-store cross-check.

    Property: cross_check_inventory NEVER silently overwrites state. Either
    accepts (consistent) or raises UsbPathMismatch (inconsistent).

    Hardware-free: builds a fake-sysfs tree under tmp_path. Hypothesis
    generates random (n_modems, cdc_wdm permutation) cases.

    Closes Phase 1 SC #5 (ROADMAP §"Phase 1: Foundations & ADRs").
    Reference: ADR-0009 (state files keyed by usb_path), CONTEXT.md S-02/S-04.
    """

    from __future__ import annotations

    import json
    from pathlib import Path

    import pytest
    from hypothesis import HealthCheck, given, settings, strategies as st

    from spark_modem.state_store.errors import UsbPathMismatch
    from spark_modem.state_store.inventory import (
        cross_check_inventory,
        walk_sysfs_for_qmi_modems,
    )


    SIERRA_VID = "1199"
    SIERRA_PID_DEFAULT = "9091"


    @st.composite
    def fake_sysfs_inventory(draw: st.DrawFn) -> tuple[int, list[int]]:
        n = draw(st.integers(min_value=1, max_value=8))
        permutation = draw(st.permutations(list(range(n))))
        return n, permutation


    def _build_sysfs_tree(
        sysfs_root: Path, *, n_modems: int, permutation: list[int]
    ) -> dict[str, str]:
        usb_paths = [f"2-3.1.{i + 1}" for i in range(n_modems)]
        cdc_wdms = [f"cdc-wdm{idx}" for idx in permutation]
        for up, cw in zip(usb_paths, cdc_wdms, strict=True):
            dev_dir = sysfs_root / "bus" / "usb" / "devices" / up
            qmi_dir = dev_dir / "qmi" / cw
            qmi_dir.mkdir(parents=True, exist_ok=True)
            (dev_dir / "idVendor").write_text(SIERRA_VID)
            (dev_dir / "idProduct").write_text(SIERRA_PID_DEFAULT)
        return dict(zip(usb_paths, cdc_wdms, strict=True))


    @settings(max_examples=50, deadline=200, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(case=fake_sysfs_inventory())
    def test_inventory_crosscheck_consistent_state_passes(
        case: tuple[int, list[int]], tmp_path: Path
    ) -> None:
        n, perm = case
        sysfs_root = tmp_path / "sys"
        mapping = _build_sysfs_tree(sysfs_root, n_modems=n, permutation=perm)
        inventory = walk_sysfs_for_qmi_modems(sysfs_root)
        assert inventory == mapping

        # All consistent — no UsbPathMismatch raised.
        for usb_path, cdc_wdm in mapping.items():
            cross_check_inventory(
                file_usb_path=usb_path,
                sysfs_usb_path=usb_path,
                cdc_wdm=cdc_wdm,
            )


    @settings(max_examples=30, deadline=200)
    @given(
        case=fake_sysfs_inventory(),
        renumber=st.integers(min_value=0, max_value=10_000),
    )
    def test_inventory_crosscheck_renumbering_raises(
        case: tuple[int, list[int]],
        renumber: int,
        tmp_path: Path,
    ) -> None:
        """Simulate USB renumbering: cdc-wdm assignment shuffles between boots.

        For each modem whose cdc-wdm changed, cross-check against the OLD cdc-wdm
        that was baked into the file MUST raise UsbPathMismatch.
        """
        n, perm = case
        sysfs_root_v1 = tmp_path / "sys_boot1"
        mapping_v1 = _build_sysfs_tree(sysfs_root_v1, n_modems=n, permutation=perm)

        # Shuffle the permutation deterministically with `renumber` as a seed-equiv;
        # to keep the test cheap we rotate by `renumber % n`.
        if n == 1:
            pytest.skip("Renumbering with n==1 has no permutation effect.")
        rotated = perm[renumber % n :] + perm[: renumber % n]
        if rotated == perm:
            pytest.skip("Rotation collided with identity permutation.")

        sysfs_root_v2 = tmp_path / "sys_boot2"
        mapping_v2 = _build_sysfs_tree(sysfs_root_v2, n_modems=n, permutation=rotated)
        inventory_v2 = walk_sysfs_for_qmi_modems(sysfs_root_v2)
        assert inventory_v2 == mapping_v2

        # For every modem whose cdc-wdm changed, the cross-check MUST raise.
        for usb_path, old_cdc in mapping_v1.items():
            new_cdc = mapping_v2[usb_path]
            if old_cdc == new_cdc:
                continue
            with pytest.raises(UsbPathMismatch) as excinfo:
                cross_check_inventory(
                    file_usb_path=usb_path,
                    sysfs_usb_path=usb_path,
                    cdc_wdm=old_cdc,
                    expected_cdc_wdm=new_cdc,
                )
            assert excinfo.value.file_usb_path == usb_path
            assert excinfo.value.cdc_wdm == old_cdc
    ```

    3. Implement `src/spark_modem/state_store/inventory.py`:
    ```python
    """Sysfs inventory walker + cross-check helper.

    ADR-0009: state files are keyed by usb_path. cdc-wdmN can renumber
    across boots (PITFALLS §3.1) — the walker resolves the current
    (usb_path -> cdc_wdm) mapping from /sys/bus/usb/devices/. The
    cross-check refuses to load a state file whose usb_path doesn't
    match what sysfs reports.

    S-02: on mismatch, the daemon refuses to start. Phase 1 raises
    UsbPathMismatch via StateStore.cross_check_inventory_for(); Phase 2/3
    wires the sd_notify STATUS=usb_path_mismatch + non-zero exit.
    """

    from __future__ import annotations

    from pathlib import Path

    from spark_modem.state_store.errors import UsbPathMismatch

    SIERRA_VID = "1199"
    """Sierra Wireless USB Vendor ID. The walker matches on this; PID varies
    across firmware revisions (PITFALLS §1.6 — match VID, not VID:PID)."""


    def walk_sysfs_for_qmi_modems(sysfs_root: Path) -> dict[str, str]:
        """Walk /sys/bus/usb/devices/ and return {usb_path: cdc_wdm}.

        Hardware-free when sysfs_root is a tmp_path; production callers pass
        Path('/sys'). Only Sierra-VID devices with a qmi/cdc-wdmN child are
        included.
        """
        result: dict[str, str] = {}
        usb_devices_dir = sysfs_root / "bus" / "usb" / "devices"
        if not usb_devices_dir.is_dir():
            return result

        for dev_dir in usb_devices_dir.iterdir():
            if not dev_dir.is_dir():
                continue
            id_vendor_file = dev_dir / "idVendor"
            if not id_vendor_file.is_file():
                continue
            try:
                vid = id_vendor_file.read_text().strip()
            except OSError:
                continue
            if vid != SIERRA_VID:
                continue
            qmi_dir = dev_dir / "qmi"
            if not qmi_dir.is_dir():
                continue
            for cdc in qmi_dir.iterdir():
                if cdc.is_dir() and cdc.name.startswith("cdc-wdm"):
                    result[dev_dir.name] = cdc.name
                    break
        return result


    def cross_check_inventory(
        *,
        file_usb_path: str,
        sysfs_usb_path: str | None,
        cdc_wdm: str | None,
        expected_cdc_wdm: str | None = None,
        file_path: str = "<unknown>",
    ) -> None:
        """Compare a persisted state file's identity against current sysfs.

        Raises UsbPathMismatch when:
          - sysfs_usb_path is None (the file references a modem that vanished),
          - file_usb_path != sysfs_usb_path,
          - expected_cdc_wdm is provided AND cdc_wdm != expected_cdc_wdm
            (the cdc-wdm renumbered between boot 1 and boot 2 — the file's
            recorded cdc-wdm is stale).

        Returns None silently on consistency.
        """
        if sysfs_usb_path is None:
            raise UsbPathMismatch(
                file_usb_path=file_usb_path,
                sysfs_usb_path=None,
                cdc_wdm=cdc_wdm,
                file_path=file_path,
            )
        if file_usb_path != sysfs_usb_path:
            raise UsbPathMismatch(
                file_usb_path=file_usb_path,
                sysfs_usb_path=sysfs_usb_path,
                cdc_wdm=cdc_wdm,
                file_path=file_path,
            )
        if expected_cdc_wdm is not None and cdc_wdm != expected_cdc_wdm:
            raise UsbPathMismatch(
                file_usb_path=file_usb_path,
                sysfs_usb_path=sysfs_usb_path,
                cdc_wdm=cdc_wdm,
                file_path=file_path,
            )
    ```

    4. Run pytest. The hypothesis property test must complete in well under 1s (CONTEXT.md S-04).
  </action>
  <verify>
    <automated>
      cd S:/spark/modem-watchdog && \
      .venv/bin/pytest tests/unit/state_store/test_inventory.py tests/unit/state_store/test_inventory_crosscheck.py -q --tb=short && \
      .venv/bin/ruff check src/spark_modem/state_store/inventory.py tests/unit/state_store/test_inventory.py tests/unit/state_store/test_inventory_crosscheck.py && \
      .venv/bin/ruff format --check src/spark_modem/state_store/inventory.py && \
      .venv/bin/mypy --strict src/spark_modem/state_store/inventory.py && \
      .venv/bin/python -c "from spark_modem.state_store.inventory import walk_sysfs_for_qmi_modems, cross_check_inventory, SIERRA_VID; from spark_modem.state_store.errors import UsbPathMismatch; assert SIERRA_VID == '1199'; print('inventory: OK')" && \
      time .venv/bin/pytest tests/unit/state_store/test_inventory_crosscheck.py -q --no-header
    </automated>
  </verify>
  <done>
    `walk_sysfs_for_qmi_modems(sysfs_root)` parses a fake-sysfs tree and returns `{usb_path: cdc_wdm}` for Sierra-VID modems. `cross_check_inventory(...)` raises `UsbPathMismatch` on (vanished modem | usb_path mismatch | stale cdc-wdm) and returns silently on consistency. The hypothesis property test exercises 50+ random (n_modems, permutation) cases against a tmp_path fake-sysfs tree, asserting the property "never silently overwrites state". Property test completes in <1s. Closes Phase 1 SC #5's pure-function half; the StateStore wiring (Task 4) closes the rest.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 4: store.py — StateStore wiring with deadlock-safe schema-downgrade + flock-on-save + inventory cross-check</name>
  <files>src/spark_modem/state_store/store.py, src/spark_modem/state_store/__init__.py, tests/unit/state_store/test_store.py, tests/unit/state_store/test_schema_downgrade.py, tests/unit/state_store/test_concurrent_writers.py</files>
  <read_first>
    - src/spark_modem/state_store/atomic.py, errors.py, locks.py, paths.py, inventory.py (just written)
    - src/spark_modem/wire/state.py, identity.py, globals.py, versioning.py (Plan 03)
    - .planning/phases/01-foundations-adrs/01-CONTEXT.md §"S. State store" S-01..S-04 (locking + downgrade behavior)
    - docs/SCHEMA.md §10 versioning policy
    - CLAUDE.md §"Critical invariants" #12 (CLI mutating commands take same flocks the daemon does)
  </read_first>
  <behavior>
    StateStore (test_store.py):
    - Test: StateStore(state_root=tmp_path/'state', run_dir=tmp_path/'run') initializes — both directories created, no exceptions.
    - Test: `await store.save_modem_state(usb_path, state)` writes to state_root/state/by-usb/<usb_path>.json atomically; subsequent `await store.load_modem_state(usb_path)` returns an equal ModemState.
    - Test: `await store.list_modem_state_usb_paths()` returns the sorted list of usb_paths with state files on disk.
    - Test: concurrent `save_modem_state` calls for the SAME usb_path serialize via the per-modem asyncio.Lock — last writer wins; no torn writes (atomicity guarantees this).
    - Test: concurrent `save_modem_state` calls for DIFFERENT usb_paths run in parallel (per-modem isolation).
    - Test: `await store.save_modem_state(usb_path, state)` acquires the per-modem flock at /run/.../modem-<usb_path>.lock — verify the file exists after the call AND was held during the call (use a separate thread holding the flock to surface the wait/raise behavior; covered in test_concurrent_writers.py).
    - Test: `await store.save_globals(g)` and `await store.load_globals()` round-trip; the state-store flock at /run/.../state.lock is acquired during save (verify file exists; concurrent-writer test covers contention).
    - Test: `await store.save_identity_map(map)` and `await store.load_identity_map()` round-trip; same state-store flock.
    - Test: `await store.cross_check_inventory_for(usb_path, sysfs_walker_callable)` invokes the walker, calls cross_check_inventory, and re-raises UsbPathMismatch on mismatch. Returns None on consistency.

    Schema downgrade (test_schema_downgrade.py) — DEADLOCK-FREE REGRESSION TEST:
    - Test: write a ModemState file with `schema_version=0` (a hypothetical v0 — the test fakes it via raw JSON since pydantic enforces ge=1; use `path.write_text('{"schema_version": 0, ...}')` directly).
    - Test: `async with asyncio.timeout(5): result = await store.load_modem_state(usb_path)` for that file:
      a) Detects schema_version=0 < CURRENT_SCHEMA_VERSION=1 → downgrade.
      b) Renames the file to `<usb_path>.from-v0.json` (shadow_filename helper).
      c) Writes a fresh-default ModemState at v1 via `_save_modem_state_locked` (NO re-acquire of the per-modem asyncio.Lock or flock — the calling load_modem_state already holds them).
      d) Returns a SchemaDowngradePending event-shaped object that the caller (daemon Phase 2) writes to events.jsonl.
      e) The whole call completes within asyncio.timeout(5) — proves no self-deadlock on the per-modem asyncio.Lock or per-modem flock.
    - Test: write a GlobalsState file with `schema_version=0` → `await store.load_globals()` performs the same deadlock-free downgrade via `_save_globals_locked`.
    - Test: write a ModemState file with `schema_version=99` (forward) — load raises SchemaVersionTooNew. The file is NOT renamed; the daemon caller is expected to refuse to start.
    - Test: write a ModemState file with `schema_version=1` (current) — loads cleanly, no shadow.

    Concurrent writers (test_concurrent_writers.py) — WARN-3 REGRESSION TEST:
    - Test: a separate thread acquires the per-modem flock at /run/.../modem-2-3.1.1.lock (via `acquire_flock` blocking=False); while held, `await store.save_modem_state("2-3.1.1", state, wait_for_flock=False)` raises StateStoreLocked.
    - Test: same setup but `wait_for_flock=True` — save_modem_state waits; release the simulated holder after 100ms; assert save completes within 1s and writes the state.
    - Test: same pattern for save_globals against /run/.../state.lock.
    - Asserts: lost-update prevention works; the daemon and a CLI mutator (Phase 2) cannot write the same file simultaneously.

    Inventory cross-check wiring (test_store.py):
    - Test: `cross_check_inventory_for(usb_path, sysfs_walker)` where the walker returns `{usb_path: cdc_wdm}` (consistent) → returns None.
    - Test: walker returns `{}` (modem vanished) → raises UsbPathMismatch.
    - Test: walker returns a different usb_path mapping → raises UsbPathMismatch.

    StateStore signature for the downgrade-aware load:
    ```python
    @dataclass(frozen=True)
    class LoadResult:
        state: ModemState
        downgrade_event: SchemaDowngradePending | None  # non-None when shadow was written

    async def load_modem_state(
        self,
        usb_path: str,
        *,
        expected_cdc_wdm: str | None = None,
    ) -> LoadResult:
        ...

    async def cross_check_inventory_for(
        self,
        usb_path: str,
        sysfs_walker: Callable[[], dict[str, str]],
        *,
        expected_cdc_wdm: str | None = None,
    ) -> None:
        ...
    ```

    Caller pattern (Phase 2 cycle driver, MUST be invoked at startup before any load_modem_state):
    ```python
    walker = lambda: walk_sysfs_for_qmi_modems(Path("/sys"))
    for usb_path in await store.list_modem_state_usb_paths():
        await store.cross_check_inventory_for(usb_path, walker)
    # ... only after all cross-checks pass, proceed to load and run cycles ...
    ```
  </behavior>
  <action>
    1. Update `src/spark_modem/state_store/__init__.py` to publicly re-export the StateStore class and the LoadResult dataclass (will be imported by Phase 2 modules).

    2. Write `tests/unit/state_store/test_store.py`, `tests/unit/state_store/test_schema_downgrade.py`, and `tests/unit/state_store/test_concurrent_writers.py` (TDD RED).
       - `test_schema_downgrade.py` MUST wrap the downgrade-load call in `async with asyncio.timeout(5):` to fail fast on regression.
       - `test_concurrent_writers.py` uses `threading.Thread` to hold the flock from a non-asyncio context (the simulated CLI mutator), then calls `await store.save_modem_state(...)` from the asyncio side and asserts StateStoreLocked is raised (non-blocking) or the save completes after release (blocking).
       - For concurrent same-key save tests, fire two `save_modem_state` coroutines via `asyncio.gather(...)` and assert they serialize on the per-modem asyncio.Lock (use a probe that `await asyncio.sleep(0)` mid-save to surface non-serialization).

    3. Implement `src/spark_modem/state_store/store.py`:
    ```python
    """StateStore — the single chokepoint for persistent state.

    Composes:
      - atomic.atomic_write_bytes / atomic_write_text (FR-62)
      - locks.PerModemLockTable + globals_lock (in-process serialization)
      - locks.acquire_flock_async (cross-process serialization; daemon-vs-CLI lost-update prevention)
      - inventory.cross_check_inventory + walk_sysfs_for_qmi_modems (S-02 startup check; ADR-0009)
      - versioning.validate_schema_version + shadow_filename (NFR-43; non-destructive downgrade)

    LOCK ACQUISITION ORDER (mandatory at every call site):
      1. asyncio.Lock first (in-process serialization).
      2. flock second (cross-process serialization).
      Releases happen in reverse order on context-manager exit.
      This prevents ABBA between the daemon (asyncio.Lock + flock) and a CLI
      mutator (flock only).

    DEADLOCK-SAFE PUBLIC/PRIVATE SPLIT:
      Public methods (save_modem_state, save_globals) acquire the asyncio.Lock + flock.
      Private methods (_save_modem_state_locked, _save_globals_locked) contain the
      actual write logic and assume both locks are already held by the caller.
      The schema-downgrade branches in load_modem_state / load_globals call the
      private methods because they're already inside the per-modem (or globals)
      asyncio.Lock + flock context. asyncio.Lock is NOT reentrant — re-acquiring
      it from the same task deadlocks; the public/private split makes that
      structurally impossible.
    """

    from __future__ import annotations

    import json
    from collections.abc import Callable
    from dataclasses import dataclass
    from datetime import datetime, timezone
    from pathlib import Path

    from spark_modem.state_store.atomic import atomic_write_bytes
    from spark_modem.state_store.errors import UsbPathMismatch
    from spark_modem.state_store.inventory import cross_check_inventory
    from spark_modem.state_store.locks import (
        PerModemLockTable,
        acquire_flock_async,
        globals_lock,
    )
    from spark_modem.state_store.paths import (
        globals_path,
        identity_map_path,
        lockfile_for_modem,
        run_dir,
        state_by_usb_dir,
        state_file_for_modem,
        state_root,
        state_store_lockfile,
    )
    from spark_modem.wire.enums import DowngradeReason
    from spark_modem.wire.events import SchemaDowngradePending
    from spark_modem.wire.globals import GlobalsState
    from spark_modem.wire.identity import Identity
    from spark_modem.wire.state import ModemState
    from spark_modem.wire.versioning import (
        CURRENT_SCHEMA_VERSION,
        SchemaVersionTooNew,
        shadow_filename,
        validate_schema_version,
    )


    @dataclass(frozen=True)
    class LoadResult:
        """Result of a load that may have triggered a non-destructive downgrade."""

        state: ModemState
        downgrade_event: SchemaDowngradePending | None = None


    @dataclass(frozen=True)
    class GlobalsLoadResult:
        state: GlobalsState
        downgrade_event: SchemaDowngradePending | None = None


    class StateStore:
        """Atomic + locked persistence for ModemState / GlobalsState / Identity map."""

        def __init__(
            self,
            *,
            state_root_override: Path | None = None,
            run_dir_override: Path | None = None,
        ) -> None:
            self._state_root = state_root_override or state_root()
            self._run_dir = run_dir_override or run_dir()
            self._state_root.mkdir(parents=True, exist_ok=True)
            (self._state_root / "state" / "by-usb").mkdir(parents=True, exist_ok=True)
            self._run_dir.mkdir(parents=True, exist_ok=True)
            self._modem_locks = PerModemLockTable()

        # ------------------------------------------------------------------
        # per-modem state — public (acquires locks) / private (assumes locks)
        # ------------------------------------------------------------------

        async def save_modem_state(
            self,
            usb_path: str,
            state: ModemState,
            *,
            wait_for_flock: bool = True,
        ) -> None:
            """Atomic save with per-modem asyncio.Lock + per-modem flock.

            Lock order (MANDATORY): asyncio.Lock first, flock second.
            Raises StateStoreLocked when wait_for_flock=False and a CLI mutator
            holds the per-modem flock.
            """
            # Layer 1: per-modem asyncio.Lock (in-process).
            async with self._modem_locks.get(usb_path):
                # Layer 2: per-modem flock (cross-process; daemon-vs-CLI).
                lock_path = lockfile_for_modem(usb_path, run=self._run_dir)
                async with await acquire_flock_async(
                    lock_path, blocking=wait_for_flock
                ):
                    await self._save_modem_state_locked(usb_path, state)

        async def _save_modem_state_locked(
            self, usb_path: str, state: ModemState
        ) -> None:
            """Actual write — assumes per-modem asyncio.Lock + flock are held.

            Called from save_modem_state (which acquires both) AND from
            load_modem_state's schema-downgrade branch (which already holds
            both). asyncio.Lock is NOT reentrant; the public/private split
            prevents same-task re-acquire deadlock.
            """
            target = state_file_for_modem(usb_path, root=self._state_root)
            payload = state.model_dump_json(by_alias=True).encode("utf-8")
            atomic_write_bytes(target, payload)

        async def load_modem_state(
            self,
            usb_path: str,
            *,
            expected_cdc_wdm: str | None = None,
        ) -> LoadResult:
            """Load a ModemState; performs schema-version + (optional) cdc-wdm check.

            Behavior:
              - file at CURRENT_SCHEMA_VERSION → returns LoadResult(state, None).
              - file at lower version → renames file to .from-v<N>.json (shadow),
                writes a fresh-default ModemState at the current version via the
                PRIVATE _save_modem_state_locked helper (no re-acquire — we already
                hold the per-modem asyncio.Lock + flock), returns
                LoadResult(fresh_state, downgrade_event). Caller writes the event
                to events.jsonl.
              - file at higher version → raises SchemaVersionTooNew. Caller is
                expected to refuse to start (NFR-43).

            Inventory cross-check (file usb_path vs sysfs) is the daemon caller's
            job via cross_check_inventory_for(); this method assumes the cross-check
            has already passed.
            """
            target = state_file_for_modem(usb_path, root=self._state_root)
            lock_path = lockfile_for_modem(usb_path, run=self._run_dir)

            # Layer 1 + Layer 2: same order as save (asyncio.Lock first, flock second).
            async with self._modem_locks.get(usb_path):
                async with await acquire_flock_async(lock_path, blocking=True):
                    if not target.exists():
                        # Fresh modem: return a default Unknown state, no downgrade.
                        return LoadResult(
                            state=_fresh_modem_state(usb_path),
                            downgrade_event=None,
                        )

                    try:
                        raw_bytes = target.read_bytes()
                    except OSError as e:
                        raise UsbPathMismatch(
                            file_usb_path=usb_path,
                            sysfs_usb_path=None,
                            cdc_wdm=None,
                            file_path=str(target),
                        ) from e

                    try:
                        raw = json.loads(raw_bytes.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError) as e:
                        raise UsbPathMismatch(
                            file_usb_path=usb_path,
                            sysfs_usb_path=usb_path,
                            cdc_wdm=None,
                            file_path=str(target),
                        ) from e

                    file_version = int(raw.get("schema_version", 0))
                    decision = validate_schema_version(
                        file_version=file_version, where=str(target)
                    )
                    if decision == "downgrade":
                        shadow = shadow_filename(target, from_version=file_version)
                        target.rename(shadow)
                        fresh = _fresh_modem_state(usb_path)
                        # PRIVATE helper — locks already held by this method.
                        await self._save_modem_state_locked(usb_path, fresh)
                        event = SchemaDowngradePending(
                            ts_iso=_now_iso(),
                            file_path=str(target),
                            from_version=file_version,
                            to_version=CURRENT_SCHEMA_VERSION,
                            shadow_path=str(shadow),
                            reason=DowngradeReason.FILE_TOO_OLD,
                        )
                        return LoadResult(state=fresh, downgrade_event=event)

                    state = ModemState.model_validate(raw)
                    _ = expected_cdc_wdm  # forward-compat hook
                    return LoadResult(state=state, downgrade_event=None)

        async def list_modem_state_usb_paths(self) -> tuple[str, ...]:
            d = state_by_usb_dir(root=self._state_root)
            if not d.is_dir():
                return ()
            paths = []
            for f in d.iterdir():
                if f.is_file() and f.suffix == ".json" and ".from-v" not in f.name:
                    paths.append(f.stem)
            return tuple(sorted(paths))

        # ------------------------------------------------------------------
        # globals — public (acquires locks) / private (assumes locks)
        # ------------------------------------------------------------------

        async def save_globals(
            self,
            state: GlobalsState,
            *,
            wait_for_flock: bool = True,
        ) -> None:
            # Layer 1: globals asyncio.Lock first, then Layer 2: state-store flock.
            async with globals_lock():
                lock_path = state_store_lockfile(run=self._run_dir)
                async with await acquire_flock_async(
                    lock_path, blocking=wait_for_flock
                ):
                    await self._save_globals_locked(state)

        async def _save_globals_locked(self, state: GlobalsState) -> None:
            """Actual globals write — assumes globals_lock + state-store flock held.

            Called from save_globals AND from load_globals's downgrade branch.
            """
            target = globals_path(root=self._state_root)
            payload = state.model_dump_json(by_alias=True).encode("utf-8")
            atomic_write_bytes(target, payload)

        async def load_globals(self) -> GlobalsLoadResult:
            target = globals_path(root=self._state_root)
            lock_path = state_store_lockfile(run=self._run_dir)
            async with globals_lock():
                async with await acquire_flock_async(lock_path, blocking=True):
                    if not target.exists():
                        return GlobalsLoadResult(
                            state=GlobalsState(), downgrade_event=None
                        )
                    raw = json.loads(target.read_bytes().decode("utf-8"))
                    file_version = int(raw.get("schema_version", 0))
                    decision = validate_schema_version(
                        file_version=file_version, where=str(target)
                    )
                    if decision == "downgrade":
                        shadow = shadow_filename(target, from_version=file_version)
                        target.rename(shadow)
                        fresh = GlobalsState()
                        # PRIVATE helper — locks already held.
                        await self._save_globals_locked(fresh)
                        event = SchemaDowngradePending(
                            ts_iso=_now_iso(),
                            file_path=str(target),
                            from_version=file_version,
                            to_version=CURRENT_SCHEMA_VERSION,
                            shadow_path=str(shadow),
                            reason=DowngradeReason.FILE_TOO_OLD,
                        )
                        return GlobalsLoadResult(state=fresh, downgrade_event=event)
                    return GlobalsLoadResult(
                        state=GlobalsState.model_validate(raw),
                        downgrade_event=None,
                    )

        # ------------------------------------------------------------------
        # identity map — uses the same state-store flock as globals
        # ------------------------------------------------------------------

        async def save_identity_map(
            self,
            identities: dict[str, Identity],
            *,
            wait_for_flock: bool = True,
        ) -> None:
            async with globals_lock():
                lock_path = state_store_lockfile(run=self._run_dir)
                async with await acquire_flock_async(
                    lock_path, blocking=wait_for_flock
                ):
                    target = identity_map_path(root=self._state_root)
                    envelope = {
                        "schema_version": CURRENT_SCHEMA_VERSION,
                        "by_usb_path": {
                            k: v.model_dump(by_alias=True)
                            for k, v in identities.items()
                        },
                    }
                    payload = json.dumps(envelope, sort_keys=True).encode("utf-8")
                    atomic_write_bytes(target, payload)

        async def load_identity_map(self) -> dict[str, Identity]:
            async with globals_lock():
                lock_path = state_store_lockfile(run=self._run_dir)
                async with await acquire_flock_async(lock_path, blocking=True):
                    target = identity_map_path(root=self._state_root)
                    if not target.exists():
                        return {}
                    raw = json.loads(target.read_bytes().decode("utf-8"))
                    file_version = int(raw.get("schema_version", 0))
                    _ = validate_schema_version(
                        file_version=file_version, where=str(target)
                    )
                    by_usb = raw.get("by_usb_path", {}) or {}
                    return {k: Identity.model_validate(v) for k, v in by_usb.items()}

        # ------------------------------------------------------------------
        # inventory cross-check — wired (WARN-1 fix)
        # ------------------------------------------------------------------

        async def cross_check_inventory_for(
            self,
            usb_path: str,
            sysfs_walker: Callable[[], dict[str, str]],
            *,
            expected_cdc_wdm: str | None = None,
        ) -> None:
            """Daemon-startup inventory cross-check for a single state-file usb_path.

            Phase 2 cycle driver MUST call this for every usb_path returned by
            `list_modem_state_usb_paths()` BEFORE any `load_modem_state` call.
            On UsbPathMismatch, the daemon refuses to start (S-02).

            Plan 03's ModemState shape does not yet carry cdc_wdm; option (a)
            (extending ModemState with `last_seen_cdc_wdm`) is rejected because
            Plan 03 is locked. Option (b) (this method) lets the caller supply
            `expected_cdc_wdm` from the identity layer or omit it. When omitted,
            the cross-check verifies usb_path presence in sysfs only.
            """
            sysfs_inventory = sysfs_walker()
            sysfs_usb_path = usb_path if usb_path in sysfs_inventory else None
            cdc_wdm = sysfs_inventory.get(usb_path)
            cross_check_inventory(
                file_usb_path=usb_path,
                sysfs_usb_path=sysfs_usb_path,
                cdc_wdm=cdc_wdm,
                expected_cdc_wdm=expected_cdc_wdm,
                file_path=str(state_file_for_modem(usb_path, root=self._state_root)),
            )


    def _fresh_modem_state(usb_path: str) -> ModemState:
        """Default state for a freshly-discovered modem (pre-first-cycle)."""
        _ = usb_path  # usb_path not stored in ModemState (Plan 03 W-04 shape); the file's name carries it.
        return ModemState(
            state="unknown",
            present=True,
            rf_blocked=False,
            recovering_level=None,
            healthy_streak=0,
            counters={},
            last_action_monotonic=None,
            last_state_transition_iso=_now_iso(),
        )


    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
    ```

    4. Update `src/spark_modem/state_store/__init__.py`:
    ```python
    """StateStore — atomic, locked, schema-versioned persistence."""

    from spark_modem.state_store.errors import (
        AtomicWriteFailed,
        StateStoreError,
        StateStoreLocked,
        UsbPathMismatch,
    )
    from spark_modem.state_store.inventory import (
        cross_check_inventory,
        walk_sysfs_for_qmi_modems,
    )
    from spark_modem.state_store.locks import (
        AsyncFlockHandle,
        PerModemLockTable,
        acquire_flock,
        acquire_flock_async,
        globals_lock,
    )
    from spark_modem.state_store.store import (
        GlobalsLoadResult,
        LoadResult,
        StateStore,
    )

    __all__ = [
        # Errors
        "AtomicWriteFailed", "StateStoreError", "StateStoreLocked", "UsbPathMismatch",
        # Inventory
        "cross_check_inventory", "walk_sysfs_for_qmi_modems",
        # Locks
        "AsyncFlockHandle", "PerModemLockTable", "acquire_flock", "acquire_flock_async", "globals_lock",
        # Store
        "GlobalsLoadResult", "LoadResult", "StateStore",
    ]
    ```

    5. Run pytest — all state_store tests pass. The schema-downgrade test MUST complete within asyncio.timeout(5); the concurrent-writers test MUST surface StateStoreLocked when the flock is held by a separate thread. Run mypy --strict and ruff over the entire `src/spark_modem/state_store/` and `tests/unit/state_store/` trees.

    6. **Carry-forward note for Phase 2 cycle driver:** The Phase 2 daemon-startup path
    MUST iterate `await store.list_modem_state_usb_paths()` and call
    `await store.cross_check_inventory_for(usb_path, walker)` for each before any
    `load_modem_state` call. On UsbPathMismatch, sd_notify STATUS=usb_path_mismatch and
    exit non-zero (S-02). This requirement is documented in this plan's must_haves and
    threaded into the SUMMARY for the Phase 2 planner.
  </action>
  <verify>
    <automated>
      cd S:/spark/modem-watchdog && \
      .venv/bin/pytest tests/unit/state_store/ -q && \
      .venv/bin/pytest tests/unit/state_store/test_schema_downgrade.py -q --tb=short && \
      .venv/bin/pytest tests/unit/state_store/test_concurrent_writers.py -q --tb=short && \
      .venv/bin/ruff check src/spark_modem/state_store/ tests/unit/state_store/ && \
      .venv/bin/ruff format --check src/spark_modem/state_store/ tests/unit/state_store/ && \
      .venv/bin/mypy --strict src/spark_modem/state_store/ && \
      bash scripts/lint_no_subprocess.sh && \
      .venv/bin/python -c "from spark_modem.state_store import StateStore, LoadResult, GlobalsLoadResult, UsbPathMismatch, StateStoreLocked, AtomicWriteFailed, cross_check_inventory, walk_sysfs_for_qmi_modems, PerModemLockTable, globals_lock, acquire_flock, acquire_flock_async; print('state_store public surface OK'); s = StateStore.__init__.__doc__ or ''; print('StateStore.cross_check_inventory_for is wired:', hasattr(StateStore, 'cross_check_inventory_for'))"
    </automated>
  </verify>
  <done>
    `StateStore` provides `save_modem_state`, `load_modem_state` (with schema-version + deadlock-safe downgrade-shadow handling), `list_modem_state_usb_paths`, `save_globals` / `load_globals`, `save_identity_map` / `load_identity_map`, AND `cross_check_inventory_for(usb_path, sysfs_walker)`. Save methods acquire the per-modem (or globals) `asyncio.Lock` AND the corresponding flock at /run/.../modem-<usb_path>.lock or /run/.../state.lock — order is asyncio.Lock first, flock second. The schema-downgrade branches in load_* call `_save_*_locked` private helpers (no re-acquire) — regression test in test_schema_downgrade.py asserts no deadlock within `asyncio.timeout(5)`. The concurrent-writers regression test in test_concurrent_writers.py asserts daemon-vs-CLI lost-update prevention works. `cross_check_inventory_for` wires the SC #5 cross-check into the StateStore method surface; the Phase 2 carry-forward note documents the daemon-startup requirement. `__init__.py` exports the full public surface. All tests pass; mypy --strict and ruff are green; SP-04 lint gate passes.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Disk → in-memory | Persisted state files are deserialized via pydantic in store.py; corruption surfaces as ValidationError or UsbPathMismatch. |
| Sysfs → walker | walk_sysfs_for_qmi_modems reads /sys/bus/usb/devices/; sysfs is kernel-controlled (root-only writable on Jetson), but the walker takes a configurable root for tests. |
| Concurrent writers (daemon vs CLI) | Daemon + ctl reset-state mutate the same file; the 3-layer lock model (asyncio.Lock + per-modem flock + state-store flock) WIRED INTO StateStore methods prevents lost-update at the API surface — not just exposed as primitives. |
| Forward-version files | NFR-43: refuse rather than silently truncate. |
| Same-task re-entry on asyncio.Lock | asyncio.Lock is NOT reentrant; the schema-downgrade-on-load path used to call save_modem_state from inside the per-modem lock, deadlocking. Public/private split prevents this structurally. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-04-01 | T (Tampering) | state file content | mitigate | atomic.py temp+fsync+rename+dir-fsync prevents partial writes; pydantic ValidationError on hand-tampered JSON; SchemaVersionTooNew on forward-version files. |
| T-04-02 | T | concurrent CLI + daemon writers | mitigate | StateStore.save_modem_state acquires per-modem asyncio.Lock + per-modem flock; StateStore.save_globals acquires globals asyncio.Lock + state-store flock. CLI mutators (Phase 2) MUST take the same flocks the daemon does (CLAUDE.md invariant #12) — they will use the same StateStore methods. The locks are wired at the method level, not just exposed as primitives, so callers cannot accidentally skip them. |
| T-04-03 | E (Elevation) | path-traversal via crafted usb_path | mitigate | paths.py rejects "/" and ".." in usb_path; pydantic Identity.usb_path regex `^\d+(-\d+(\.\d+)*)?$` enforces safe shape upstream. |
| T-04-04 | T | symlink races on /var/lib/spark-modem-watchdog/state/by-usb/ | accept | Daemon runs as root (NFR-30); the directory is root-owned 0o700 (Phase 1 doesn't set the mode explicitly — Phase 3 wires it via debian/postinst chmod or systemd ReadWritePaths). NFR-30 limits attack surface. |
| T-04-05 | I (Information disclosure) | identity.json (ICCID/IMSI) | mitigate | atomic.py default mode 0o640 (root-readable); /var/lib/spark-modem-watchdog parent dir is 0o750 by debhelper convention. |
| T-04-06 | D (DoS) | a stuck flock holder | mitigate | save_modem_state and save_globals accept `wait_for_flock` parameter; default `True` means the daemon waits, but ctl-side callers can opt out and surface StateStoreLocked immediately. |
| T-04-07 | T | inventory mismatch silently overwriting state | mitigate | cross_check_inventory raises UsbPathMismatch (S-02); never silently overwrites. The hypothesis property test in tests/unit/state_store/test_inventory_crosscheck.py is regression-proof for the pure-function half; the StateStore.cross_check_inventory_for wiring + WARN-1 regression test are regression-proof for the wired half. The Phase 2 cycle driver carry-forward note documents the daemon-startup requirement. |
| T-04-08 | T | schema-version mismatch silently truncating data | mitigate | NFR-43: forward versions raise SchemaVersionTooNew; backward versions write a `.from-v<N>.json` shadow rather than overwrite. The shadow file is preserved verbatim until operator runs `ctl migrate-state` (Phase 2). |
| T-04-09 | D (DoS) | self-deadlock on schema-downgrade-on-load | mitigate | asyncio.Lock is NOT reentrant. The public/private split (`save_modem_state` / `_save_modem_state_locked`, `save_globals` / `_save_globals_locked`) makes same-task re-acquire structurally impossible. test_schema_downgrade.py's `asyncio.timeout(5)` regression test fails fast on any future regression. |
</threat_model>

<verification>
End-to-end check after all four tasks complete:

1. `pytest tests/unit/state_store/ -q` — all tests pass; total runtime <2s on developer laptop.
2. `pytest tests/unit/state_store/test_inventory_crosscheck.py -q --no-header` reports the hypothesis property test passing in <1s (CONTEXT.md S-04).
3. `pytest tests/unit/state_store/test_schema_downgrade.py -q` — schema-downgrade-on-load completes within `asyncio.timeout(5)` for both ModemState and GlobalsState paths (BLK-4 regression).
4. `pytest tests/unit/state_store/test_concurrent_writers.py -q` — simulated CLI mutator holding the per-modem flock causes `save_modem_state(wait_for_flock=False)` to raise StateStoreLocked; `wait_for_flock=True` waits then completes (WARN-3 regression).
5. `mypy --strict src/spark_modem/state_store/` — zero errors.
6. `ruff check src/spark_modem/state_store/ tests/unit/state_store/` and `ruff format --check ...` — clean.
7. `bash scripts/lint_no_subprocess.sh` — passes (no subprocess in state_store).
8. End-to-end smoke: `python -c "import asyncio; from pathlib import Path; from spark_modem.state_store import StateStore; from spark_modem.wire import ModemState; ...` — save then load round-trips a ModemState; the file at state/by-usb/2-3.1.1.json is valid JSON with schema_version=1; the per-modem lockfile at /run/.../modem-2-3.1.1.lock exists.
9. Forward-version refusal: write a state file with `{"schema_version": 99}` directly → load raises SchemaVersionTooNew.
10. Backward-version shadow: write a state file with `{"schema_version": 0, ...}` → load renames to `.from-v0.json`, writes fresh default via _save_modem_state_locked (no deadlock), returns SchemaDowngradePending event.
11. cross_check_inventory_for wiring: `await store.cross_check_inventory_for("2-3.1.1", lambda: {})` → raises UsbPathMismatch (modem vanished); `lambda: {"2-3.1.1": "cdc-wdm0"}` → returns None.
</verification>

<success_criteria>
- Closes Phase 1 SC #5: state files round-trip on disk under `state/by-usb/<usb_path>.json` with atomic temp+rename+directory-fsync semantics; the hypothesis-driven inventory cross-check (test_inventory_crosscheck.py) raises UsbPathMismatch on every mismatch and round-trips on every consistent state. The cross-check is wired into StateStore.cross_check_inventory_for(), not just exposed as a freestanding helper — the daemon caller (Phase 2) MUST invoke it at startup. Hardware-free; <1s runtime for the property test.
- FR-62: every persistent file write is atomic (temp + rename + directory fsync). atomic.py implements; StateStore consumes via _save_modem_state_locked / _save_globals_locked.
- FR-62.1: state files keyed by `usb_path`; startup cross-check via `StateStore.cross_check_inventory_for`. ADR-0009 surface implemented.
- ADR-0012: 3-layer locking model wired at the StateStore method level, not just exposed as primitives. Every save_* method acquires asyncio.Lock + flock in the documented order; save_modem_state takes the per-modem flock, save_globals + save_identity_map take the state-store flock. PID lock at /run/.../lock is separate (Phase 3 owns it via sd_notify lifecycle).
- NFR-43: schema-version refusal of forward versions (SchemaVersionTooNew) + non-destructive downgrade (.from-v<N>.json shadow) — wired through StateStore.load_* with the deadlock-safe public/private helper split. test_schema_downgrade.py is the regression test for the public/private split.
- The CLI mutating commands (`ctl reset-state`, `ctl migrate-state`) don't exist yet (Phase 2); when they do, they wire into the existing `StateStore.save_*` API and inherit the asyncio.Lock + flock + atomic-write surface for free — CONTEXT.md S-01 mandate (FULL atomic-write + 3-layer flock layer at the StateStore method level so Phase 2/3 CLI callers wire without churn). test_concurrent_writers.py is the regression test for daemon-vs-CLI lost-update.
- Phase 2 carry-forward: the cycle driver MUST call `await store.cross_check_inventory_for(usb_path, walker)` for every usb_path returned by `list_modem_state_usb_paths()` BEFORE any `load_modem_state` call. On UsbPathMismatch, sd_notify STATUS=usb_path_mismatch and exit non-zero. Documented in this plan's must_haves and SUMMARY.
</success_criteria>

<output>
After completion, create `.planning/phases/01-foundations-adrs/01-04-SUMMARY.md` covering: full state_store public surface (save_*, load_*, list_*, cross_check_inventory_for), the 3-layer lock model in concrete terms (asyncio.Lock + flock + flock + separate PID lock) with the mandatory acquisition order (asyncio.Lock first, flock second), the public/private helper split that prevents the asyncio.Lock re-entry deadlock on schema-downgrade-on-load (BLK-4 fix), the daemon-vs-CLI lost-update regression test (test_concurrent_writers.py — WARN-3 fix), the inventory cross-check wiring (StateStore.cross_check_inventory_for — WARN-1 fix), the inventory-cross-check property test result (max_examples + wall time), the schema-downgrade behavior (shadow naming, SchemaDowngradePending event emitted by load), and the explicit Phase 2 carry-forward requirement (cycle driver MUST call cross_check_inventory_for at startup before load_modem_state). Reference Plan 07 (ADR-0009 + ADR-0012 documentation), which captures these implementation choices as decision records.
</output>
</content>
</invoke>