# ADR-0012 — 3-layer locking model: per-modem asyncio.Lock + flocks + PID lock

| Field        | Value          |
| ------------ | -------------- |
| Status       | Accepted       |
| Date         | 2026-05-06     |
| Deciders     | Eng team       |

## Context

Three independent failure modes converge on the same design question
("who may write to a modem's state file at any given time?"):

**In-process concurrency** (`.planning/research/ARCHITECTURE.md` Q3):
The cycle driver and the SIGHUP reload listener both write state for
modems. In asyncio, two coroutines can interleave at any `await`
point. Without serialization, a cycle coroutine writing modem A's
state and a reload coroutine updating the globals file can interleave
and produce a torn write.

**Cross-process concurrency** (`.planning/research/PITFALLS.md`
§3.2/§16.1; FEATURES M-21): The daemon and `spark-modem ctl reset-state`
are two separate processes that may run concurrently on the same box.
Both mutate the same state files under `/var/lib/spark-modem-watchdog/`.
Without cross-process coordination, they can produce a lost update or
a corrupted file.

**PID exclusivity** (FR-61): only one daemon process may run per box.
If `systemctl start` races with a leftover daemon from a previous
invocation, two daemons writing to the same state files simultaneously
is a data corruption scenario.

These three problems are distinct: in-process contention needs asyncio
primitives (no thread blocking); cross-process contention needs OS-
level advisory locks; PID exclusivity needs a separate lock file that
CLI tools do NOT take (so that `ctl reset-state` can run while the
daemon holds its PID lock).

## Decision

A **3-layer locking model**:

### Layer 1: In-process (asyncio.Lock)

**Per-modem lock**: one `asyncio.Lock` per `usb_path`, lazily
populated in a `dict[str, asyncio.Lock]` (`PerModemLockTable`).
~10 LOC. Acquired for the duration of any coroutine that reads or
writes a specific modem's state file.

**Globals lock**: one `asyncio.Lock` for `globals.json` and
`identity.json`. Acquired separately from per-modem locks.

**Single-key API**: the locking API exposes only per-modem locks
and the globals lock. It never acquires multiple per-modem locks
simultaneously. Rationale: composing two per-modem locks creates a
deadlock risk (lock ordering must be consistent). Since the current
design has no operation that needs two modems' locks simultaneously,
the single-key API rule prevents the hazard at design time rather
than relying on discipline.

If a future operation requires locking two modems simultaneously, the
rule is: acquire locks in sorted `usb_path` order (lexicographic).
This rule is documented in the locking module's docstring; violating
it is a bug.

### Layer 2: Cross-process (advisory fcntl flocks)

**Per-modem flock**: advisory exclusive lock at
`/run/spark-modem-watchdog/modem-<usb_path>.lock`.

**State-store flock**: advisory exclusive lock at
`/run/spark-modem-watchdog/state.lock`.

Both the daemon and CLI mutating commands (`ctl reset-state`,
`ctl migrate-state`) acquire the relevant flock(s) before reading
or writing state files. CLAUDE.md invariant #12: CLI mutating commands
take the same flocks the daemon does. FR-61.1.

Lock files have mode `0o640` with the holder's PID written in plain
ASCII (e.g. `1234\n`). This makes the holder visible:
`cat /run/spark-modem-watchdog/state.lock` tells an operator which
PID holds the lock.

Flock semantics: `fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)`.
If the lock is held by another process, the caller retries with a
bounded timeout (default 5 s for the daemon; 30 s for CLI commands
to allow for long-running daemon cycles).

The async wrapper `acquire_flock_async` uses
`asyncio.get_event_loop().run_in_executor(None, ...)` to avoid
blocking the event loop during the retry poll. Maximum flock acquire
time is bounded by the timeout parameter.

### Layer 3: PID lock (separate file)

**PID lock**: `/run/spark-modem-watchdog/lock`. Acquired exclusively
by the daemon's main process on startup; released on exit. SEPARATE
from the Layer 2 flocks.

The PID lock file is separate so that CLI mutating commands can take
the Layer 2 state-store and per-modem flocks WITHOUT conflicting with
the daemon's PID exclusivity. A `ctl reset-state` run while the
daemon is running:
1. Acquires the state-store flock (Layer 2) — may wait ≤30 s.
2. Acquires the per-modem flock for the target modem (Layer 2).
3. Reads and writes the state file.
4. Releases both Layer 2 flocks.

It does NOT acquire the PID lock. The PID lock is only for
"one daemon at a time" exclusivity; it is not a general write guard.

### Lock acquisition order (invariant)

To prevent deadlock, all code that acquires multiple locks follows
this order:

1. Globals asyncio.Lock (if needed) — OR — per-modem asyncio.Lock(s)
   in sorted `usb_path` order.
2. State-store flock (Layer 2).
3. Per-modem flock (Layer 2) in sorted `usb_path` order.

PID lock (Layer 3) is acquired once at startup and never released
mid-flight; it does not participate in the ordering.

## Consequences

- **Per-modem isolation**: a slow fsync on modem A's file does not
  block writes on modem B. Each modem has its own asyncio.Lock and
  its own flock file.

- **CLI mutators and daemon are race-free** on the same state file.
  Both acquire the Layer 2 flock before writing; one waits.

- **PID lock is a separate file**: `ctl reset-state` does not need
  to be PID-exclusive; it only needs the per-modem and state-store
  flocks.

- **Stale flock files after crash**: `fcntl.flock` is advisory and
  kernel-released on process death. The lock file itself persists on
  disk after a crash but the lock is immediately available to the
  next acquirer. The stale PID in the file is stale data; a new holder
  overwrites it on acquisition.

- **Lock files are on tmpfs** (`/run/` is tmpfs on modern Linux).
  Lock files do not persist across reboots. This is intentional: a
  lock file held across a reboot would block the daemon at startup.

- **Phase 1 ships the full locking layer** even though CLI mutators
  don't land until Phase 2/3. The interface is locked in Phase 1 so
  Phase 2/3 wire callers without interface churn (CONTEXT.md S-01).

## Risks and mitigations

| Risk | Mitigation |
| ---- | ---------- |
| Lock-ordering hazard if a cycle ever needs to lock two modems atomically | Single-key API forbids it by design. If ever needed, lock by sorted `usb_path` order (documented in `locks.py` docstring). mypy + code review catch violations. |
| Stale flock after crash (lock file exists, process is dead) | `fcntl.flock` is kernel-released on process death. The file persists but the lock is free. New acquirer opens the file and acquires immediately. |
| `flock` on NFS | `/run/spark-modem-watchdog/` is tmpfs; NFS is not applicable. If the run dir ever moves to a network filesystem, this invariant must be re-validated (the answer is likely "don't"). |
| asyncio.Lock held across an await that itself blocks | The asyncio.Lock is held for the duration of the state-read + state-write sequence. No slow I/O is performed while holding the asyncio.Lock WITHOUT also holding the flock. The flock acquisition is the slow I/O; it is done first, then the asyncio.Lock is acquired. This ordering ensures the event loop is not blocked while waiting for the flock. |
| Per-modem flock timeout causes the cycle to miss a deadline | Default 5 s timeout for the daemon's flock acquire. The cycle's P99 deadline is 10 s. A 5 s flock wait is the worst-case contribution from locking; acceptable given that the flock is only contended when a CLI mutator runs during a cycle. |

## Implementation reference

- `src/spark_modem/state_store/locks.py` — `PerModemLockTable`,
  `globals_lock`, `acquire_flock`, `acquire_flock_async` (Plan 04).
- `src/spark_modem/state_store/store.py` — acquires asyncio.Lock +
  flock before every state read/write (Plan 04).
- Phase 3 — PID lock implementation wired into the daemon's
  startup/shutdown lifecycle (alongside `sd_notify`).
- Phase 2 — `ctl reset-state` and `ctl migrate-state` acquire Layer 2
  flocks (CLI commands).

## Revisit when

- Cycle profile shows per-modem lock contention is meaningful.
  Current measurement: zero contention (the lock is for safety,
  not performance). If contention appears, investigate whether a CLI
  command is holding a flock longer than expected.
- A future operation needs to atomically update two modems'
  state simultaneously. Then the single-key rule must be relaxed,
  the sorted-lock-order rule must be enforced, and a lock ordering
  test must be added to the test suite.
- The run directory moves off tmpfs (e.g. to a persistent volume for
  debugging purposes). Then the "flock on NFS" risk must be evaluated
  and lock files must be explicitly placed on a local filesystem.
