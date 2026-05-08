---
phase: 03-linux-event-sources-lifecycle
reviewed: 2026-05-08T00:00:00Z
depth: standard
files_reviewed: 51
files_reviewed_list:
  - debian/spark-modem-watchdog.logrotate
  - debian/spark-modem-watchdog.service
  - pyproject.toml
  - src/spark_modem/cli/diag.py
  - src/spark_modem/daemon/cycle_driver.py
  - src/spark_modem/daemon/lifecycle.py
  - src/spark_modem/daemon/main.py
  - src/spark_modem/daemon/preflight.py
  - src/spark_modem/daemon/sighup.py
  - src/spark_modem/daemon/sigterm.py
  - src/spark_modem/event_logger/inotify_reopener.py
  - src/spark_modem/event_logger/writer.py
  - src/spark_modem/event_sources/__init__.py
  - src/spark_modem/event_sources/asyncinotify_producer.py
  - src/spark_modem/event_sources/kmsg_producer.py
  - src/spark_modem/event_sources/rtnetlink_producer.py
  - src/spark_modem/event_sources/supervisor.py
  - src/spark_modem/event_sources/udev_producer.py
  - src/spark_modem/inventory/netns.py
  - src/spark_modem/inventory/sysfs.py
  - src/spark_modem/inventory/udev.py
  - src/spark_modem/kmsg/__init__.py
  - src/spark_modem/kmsg/classifier.py
  - src/spark_modem/kmsg/dedup.py
  - src/spark_modem/observer/issue_extractor.py
  - src/spark_modem/qmi/wrapper.py
  - src/spark_modem/state_store/store.py
  - src/spark_modem/wire/diag.py
  - src/spark_modem/wire/enums.py
  - src/spark_modem/wire/events.py
  - src/spark_modem/zao_log/inotify_tailer.py
  - tests/fakes/__init__.py
  - tests/fakes/asyncinotify.py
  - tests/fakes/kmsg.py
  - tests/fakes/pidlock.py
  - tests/fakes/rtnetlink.py
  - tests/fakes/sdnotify.py
  - tests/fakes/sleeper.py
  - tests/fakes/udev.py
  - tests/integration/conftest.py
  - tests/integration/test_lifecycle.py
  - tests/integration/test_logrotate_create.py
  - tests/integration/test_unit_file_audit.py
  - tests/unit/daemon/test_clean_shutdown_marker.py
  - tests/unit/daemon/test_lifecycle_sd_notify.py
  - tests/unit/daemon/test_pid_lock.py
  - tests/unit/daemon/test_preflight.py
  - tests/unit/daemon/test_sighup_swap.py
  - tests/unit/daemon/test_sigterm_choreography.py
  - tests/unit/daemon/test_sim_swap_detection.py
  - tests/unit/event_logger/test_writer_reopen.py
  - tests/unit/event_sources/test_asyncinotify_producer.py
  - tests/unit/event_sources/test_kmsg_producer.py
  - tests/unit/event_sources/test_rtnetlink_producer.py
  - tests/unit/event_sources/test_supervisor.py
  - tests/unit/event_sources/test_udev_producer.py
  - tests/unit/inventory/test_netns_derivation.py
  - tests/unit/inventory/test_udev_inventory.py
  - tests/unit/kmsg/test_classifier.py
  - tests/unit/kmsg/test_dedup.py
  - tests/unit/qmi/test_wrapper_netns.py
  - tests/unit/state_store/test_reset_modem_streak_and_counters.py
  - tests/unit/wire/test_enums_phase3.py
  - tests/unit/wire/test_events.py
  - tests/unit/zao_log/test_inotify_tailer_dual_mode.py
findings:
  critical: 0
  warning: 5
  info: 7
  total: 12
status: has-findings
---

# Phase 03: Code Review Report

**Reviewed:** 2026-05-08
**Depth:** standard
**Files Reviewed:** 51
**Status:** has-findings

## Summary

Phase 3 (Linux event sources + daemon lifecycle) is well-executed against the
13 critical CLAUDE.md invariants. The core architectural shape is correct:
producers run inside `restart_on_crash` with the documented backoff envelope;
udev uses `loop.add_reader(monitor.fileno())` (NOT `MonitorObserver`); rtnetlink
uses `pyroute2.AsyncIPRoute`; asyncinotify handles dual-mode logrotate;
`/dev/kmsg` is opened `O_NONBLOCK` and drained until `BlockingIOError`; sd_notify
goes through `sdnotify` (not `systemd-python`); SIGTERM is choreographed in
the L-02 8-step order; PID lock acquired via the same `flock` primitives the
state-store uses; per-modem state is `usb_path`-keyed (ADR-0009) and written
atomically (temp + rename + dir fsync).

No CRITICAL findings. Five WARNINGs and seven INFOs are listed below — all
are quality / minor-correctness items, not invariant violations or security
holes. The most load-bearing item is **WR-01** (`if/elif` on `state_name`
in `cycle_driver._write_status_report`), which violates the explicit
CLAUDE.md anti-pattern "`if/elif` instead of `match` on `ModemState`".

The `policy/` purity check passes: the package's docstrings explicitly forbid
subprocess/I/O imports and a quick grep confirms no `subprocess`, `httpx`,
`os.environ`, or file-read calls live under `policy/`. The single
`create_subprocess_exec` call in the codebase is correctly confined to
`subproc/runner.py`.

## Warnings

### WR-01: `if/elif` on `state_name` violates CLAUDE.md anti-pattern

**File:** `src/spark_modem/daemon/cycle_driver.py:572-581`
**Issue:** The status-summary aggregation walks each state with an
`if/elif/elif/elif/else` ladder on `state_name`. CLAUDE.md anti-pattern
catalogue explicitly lists "`if/elif` instead of `match` on `ModemState`"
as forbidden because mypy's exhaustiveness check on `match` is what catches
a dropped state when a new top-level state is introduced. The current
ladder silently falls into the `else` (`unknown`) branch on any new state.

`state_name: StateLiteral = Literal["unknown", "healthy", "degraded",
"recovering", "exhausted"]` (per `wire/state.py:19`) is exactly the kind of
closed-Literal type `match` was added to Python for.

**Fix:**
```python
match state_name:
    case "healthy":
        healthy += 1
    case "degraded":
        degraded += 1
    case "recovering":
        recovering += 1
    case "exhausted":
        exhausted += 1
    case "unknown":
        unknown += 1
```
With `mypy --strict` and `warn_unreachable = true` (already on per
`pyproject.toml:53`), adding a new state to `StateLiteral` will fail the
type-check until this match is updated.

### WR-02: `contextlib.suppress(asyncio.CancelledError, Exception)` in SIGTERM choreography swallows outer cancel

**File:** `src/spark_modem/daemon/sigterm.py:131-132`, `:142-143`
**Issue:** Steps 1 and 2 await the cancelled cycle/producer tasks inside
`with contextlib.suppress(asyncio.CancelledError, Exception):`. Suppressing
`Exception` here is intentional (per-step isolation, NFR-11), but suppressing
`asyncio.CancelledError` at this scope means a `CancelledError` raised
**against the choreography itself** (e.g. parent TaskGroup cancel during
shutdown) is silently swallowed by the very `await` that's supposed to be
the cancellation point. The outer `except Exception` arm is then dead code
(suppress already ate it).

The choreography is documented as "the LAST coroutine the daemon runs
before exit," so in practice this is unlikely to bite, but the code
shape misrepresents the cancellation model.

**Fix:** Suppress only the awaited task's `CancelledError`, not the
choreography's:
```python
try:
    self._cycle_driver_task.cancel()
    try:
        await self._cycle_driver_task
    except asyncio.CancelledError:
        # The task we just cancelled raised it — expected; swallow.
        pass
except asyncio.CancelledError:
    raise  # outer cancel — propagate
except Exception:
    logger.exception("sigterm step 1 (cancel cycle driver) failed")
```
Same shape for Step 2's per-task await.

### WR-03: `_laptop_main` leaks `EventLogWriter` fd

**File:** `src/spark_modem/daemon/main.py:124,164-167`
**Issue:** `_laptop_main` constructs `event_logger = EventLogWriter(settings.events_log_path)`
but never enters the writer's context manager (`with EventLogWriter(...) as`)
nor calls `.close()`. The writer holds an open fd; on a fast cycle the fd
leaks until process exit. In production the laptop path runs once and exits
so this is bounded, but tests that import `_laptop_main` repeatedly will
accumulate open fds.

**Fix:** Wrap the cycle in a `with` block:
```python
with EventLogWriter(settings.events_log_path) as event_logger:
    ...
    result = await driver.run_one_cycle(cycle_id=0)
    ...
```

### WR-04: `_laptop_main` uses `__import__(...)` for `DaemonStopReason`

**File:** `src/spark_modem/daemon/main.py:143-145`
**Issue:** The boot-envelope construction reaches for `DaemonStopReason`
via `__import__("spark_modem.wire.enums", fromlist=["DaemonStopReason"]).DaemonStopReason.CRASH`.
This bypasses `mypy --strict` (no static type-check on the dynamic import),
makes `ruff` flag the call as unusual, and obscures the dependency from
import-graph tools. There's no circular-import justification — `DaemonStopReason`
is already imported at module scope of `wire/enums.py` and used directly
in `daemon/sigterm.py` and `daemon/lifecycle.py`.

**Fix:** Add the import to the module-level import block:
```python
from spark_modem.wire.enums import DaemonStopReason
...
boot_envelope = WebhookEnvelope(
    payload=DaemonRestart(
        ts_iso=clock.wall_clock_iso(),
        reason=DaemonStopReason.CRASH,
        prior_run_uptime_seconds=0.0,
    ),
)
```

### WR-05: `EventLogWriter._fsync_directory` only fires on first-creation; not on directory pre-existence

**File:** `src/spark_modem/event_logger/writer.py:87-98`
**Issue:** The writer fsyncs the parent directory **only if** `parent_existed`
was False. When the writer opens an existing directory (the production
case after the .deb's postinst creates `/var/log/spark-modem-watchdog/`),
the directory entry for the freshly-created `events.jsonl` file is **not**
fsynced. After a power loss between the `os.open(O_CREAT)` and the first
`os.write`, the directory entry could be lost on remount, breaking the
durability claim that "events.jsonl exists" (FR-43).

CLAUDE.md invariant #5 ("Atomic file writes — temp + rename + directory
fsync") is for state files which use `atomic_write_bytes` correctly; the
events.jsonl writer is intentionally `O_APPEND`-streaming (not a temp+rename
pattern), so the contract is weaker. But the dir-fsync-on-create path
should still fire to make the file-existence durable.

**Fix:** Always fsync the parent directory on writer construction; it's a
microsecond-cost on tmpfs/ext4 and removes the corner case:
```python
parent.mkdir(parents=True, exist_ok=True)
self._fd: int | None = os.open(...)
# Fsync the parent so the events.jsonl directory entry is durable.
_fsync_directory(parent, self._path)
```

## Info

### IN-01: `event_sources/asyncinotify_producer.py` — orphan `pass` statement in test

**File:** `tests/unit/event_sources/test_asyncinotify_producer.py:253`
**Issue:** `test_events_jsonl_create_invokes_reopener` contains an unreachable
`pass` statement followed by exploratory code that gets torn down without
any assertion. The body reads as scratch notes that survived a refactor.

**Fix:** Delete the test or rewrite it as a focused assertion. The
sibling test `test_events_jsonl_create_dispatches_with_captured_handle`
already covers the dispatch path correctly.

### IN-02: `daemon/main.py` — `_production_main` is a documented placeholder; some imports are kept-alive only

**File:** `src/spark_modem/daemon/main.py:275-278`
**Issue:** `_ = restart_on_crash`, `_ = signal`, `_ = UdevInventory`,
`_ = ZaoLogInotifyTailer` exist solely to keep imports live for Plan 03-09.
This is documented in the docstring and is intentional, but `ruff` `F401`
suppression via `_ = name` is unconventional. Plan 03-09 will replace this
shape with the real TaskGroup body.

**Fix:** Track in Plan 03-09's checklist (already documented). No code
change needed for Phase 3 acceptance.

### IN-03: `inventory/netns.py` — bench Jetson default branch returns from rglob loop

**File:** `src/spark_modem/inventory/netns.py:67-78`
**Issue:** `derive_ns` walks `usb_dev_path.rglob("net/wwan*")` and returns
**after the first iteration** unconditionally — either the inode-resolved
name or `None`. This is fine for the bench Jetson (one wwan iface per
modem), but `rglob` semantics could surface duplicates (e.g. a sysfs
symlink loop), and the function doesn't pin "first match wins" behavior
in a comment.

**Fix:** Add a one-line comment documenting the first-match contract, or
break out of the loop explicitly:
```python
for net in usb_dev_path.rglob("net/wwan*"):
    # First wwan iface wins — bench Jetson has exactly one per modem.
    ...
    return _resolve_netns_name(target, netns_root=root)
```

### IN-04: `KmsgDedup.consume_dedup_count` returns 0 for never-suppressed key — test pins this; documentation could be clearer

**File:** `src/spark_modem/kmsg/dedup.py:58-66`
**Issue:** The `consume_dedup_count` docstring says "Reset and return the
suppressed count for `detail`. Subsequent calls return 0 until the next
suppression occurs." This is correct, but it omits that calling consume on
a `detail` that has **never** been suppressed also returns 0 (no KeyError).
The test `test_consume_for_unknown_key_returns_zero` pins this behavior.

**Fix:** One-line docstring extension:
```
Reading a never-suppressed detail returns 0 (not KeyError).
```

### IN-05: `event_sources/kmsg_producer.py` — `sequence_gaps_total` is a local counter never surfaced

**File:** `src/spark_modem/event_sources/kmsg_producer.py:168-191`
**Issue:** The producer maintains `sequence_gaps_total` as a closure-local
counter inside `on_readable` and never exposes it. The comment says "local
self-health counter (Plan 03-06 wires Prom)" but the metrics integration
appears not to have landed in this phase. The counter increments on every
sequence gap but is invisible to anything outside `run_kmsg_producer`.

**Fix:** Either wire the Prom metric in Plan 03-06 follow-up, or remove
the counter as dead code. Track in Plan 03-06's checklist.

### IN-06: `cycle_driver.py` — `prior_globals` parameter shadows reload-friendly read

**File:** `src/spark_modem/daemon/cycle_driver.py:439-460`
**Issue:** `_persist_states_and_globals` accepts a `prior_globals: GlobalsState`
parameter and only writes new globals when `cycle_result.new_globals !=
prior_globals`. This avoids unnecessary writes but means a SIGHUP-driven
globals refresh that lands mid-cycle would be silently overwritten if the
policy engine returned `cycle_result.new_globals` equal to the pre-SIGHUP
globals snapshot. SIGHUP currently only swaps Settings (not globals), so
this is theoretical — but the diff-only write protocol should be commented
to make the design intent explicit.

**Fix:** Add a comment at the diff-only write:
```python
# Diff-only write avoids touching the file on no-op cycles. Globals
# are NOT reloaded via SIGHUP in v2.0; the maintenance window is the
# only mutator and it goes through the cycle driver, so the cached
# prior_globals reflects on-disk state.
if cycle_result.new_globals != prior_globals:
    await self._store.save_globals(cycle_result.new_globals)
```

### IN-07: `cycle_driver.py` — webhook logic uses `tr.from_state.startswith("recovering")`

**File:** `src/spark_modem/daemon/cycle_driver.py:503`
**Issue:** The `RecoveringToExhausted` envelope is emitted when
`tr.from_state.startswith("recovering")` and `tr.to_state == "exhausted"`.
`StateTransition.from_state: str` is intentionally a free-form `str`
(per `wire/events.py:69` comment: "Literal not used here so old/legacy
state names don't break replay"), so `startswith` accommodates both the
canonical "recovering" and any legacy `"recovering(2)"` shape. This is
correct but worth a sentence at the call site so a future reader doesn't
"fix" it to `==`.

**Fix:** One-line clarifying comment:
```python
# from_state may be "recovering" or legacy "recovering(<level>)" —
# replay-compat per wire/events.py StateTransition note. Use startswith
# rather than == so legacy shapes still emit the envelope.
elif tr.from_state.startswith("recovering") and tr.to_state == "exhausted":
```

---

_Reviewed: 2026-05-08_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
