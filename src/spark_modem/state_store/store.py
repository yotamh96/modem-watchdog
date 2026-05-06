"""StateStore — the single chokepoint for persistent state.

Composes:
  - atomic.atomic_write_bytes (FR-62: temp + fsync + rename + dir-fsync)
  - locks.PerModemLockTable + globals_lock (in-process serialization)
  - locks.acquire_flock_async (cross-process serialization; daemon-vs-CLI
    lost-update prevention wired at the method level, not just exposed)
  - inventory.cross_check_inventory (S-02 startup check; ADR-0009)
  - versioning.validate_schema_version + shadow_filename (NFR-43;
    non-destructive schema downgrade)

LOCK ACQUISITION ORDER (mandatory at every call site):
  1. asyncio.Lock first (in-process serialization).
  2. flock second  (cross-process serialization).
  Releases happen in reverse order on context-manager exit.
  This prevents ABBA between the daemon (asyncio.Lock + flock) and a CLI
  mutator (flock only).

DEADLOCK-SAFE PUBLIC/PRIVATE SPLIT:
  Public methods (save_modem_state, save_globals) acquire the asyncio.Lock
  + flock. Private methods (_save_modem_state_locked, _save_globals_locked)
  contain the actual write logic and assume both locks are already held by
  the caller.

  The schema-downgrade branches in load_modem_state / load_globals call the
  private methods because they are already inside the per-modem (or globals)
  asyncio.Lock + flock context.  asyncio.Lock is NOT reentrant — re-acquiring
  it from the same task deadlocks; the public/private split makes that
  structurally impossible.

Phase 2 carry-forward:
  The daemon-startup path MUST iterate list_modem_state_usb_paths() and call
  cross_check_inventory_for(usb_path, walker) for each usb_path BEFORE any
  load_modem_state call. On UsbPathMismatch, sd_notify STATUS=usb_path_mismatch
  and exit non-zero (S-02).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
    shadow_filename,
    validate_schema_version,
)


@dataclass(frozen=True)
class LoadResult:
    """Result of load_modem_state; may carry a downgrade event."""

    state: ModemState
    downgrade_event: SchemaDowngradePending | None = field(default=None)


@dataclass(frozen=True)
class GlobalsLoadResult:
    """Result of load_globals; may carry a downgrade event."""

    state: GlobalsState
    downgrade_event: SchemaDowngradePending | None = field(default=None)


class StateStore:
    """Atomic + locked persistence for ModemState / GlobalsState / Identity map.

    All persistent file writes go through this class. No other module in the
    daemon writes JSON to /var/lib/spark-modem-watchdog/.

    Instantiation:
        store = StateStore()  # production — uses env-var-configured paths
        store = StateStore(
            state_root_override=Path('/tmp/test-state'),
            run_dir_override=Path('/tmp/test-run'),
        )  # test isolation
    """

    def __init__(
        self,
        *,
        state_root_override: Path | None = None,
        run_dir_override: Path | None = None,
    ) -> None:
        self._state_root = state_root_override or state_root()
        self._run_dir = run_dir_override or run_dir()
        # Ensure directories exist at startup.
        self._state_root.mkdir(parents=True, exist_ok=True)
        state_by_usb_dir(root=self._state_root).mkdir(parents=True, exist_ok=True)
        self._run_dir.mkdir(parents=True, exist_ok=True)
        # Layer 1: in-process per-modem asyncio.Lock table.
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

        Lock order (MANDATORY — see module docstring):
          1. asyncio.Lock first (in-process).
          2. flock second (cross-process).

        Args:
            wait_for_flock: If False, raises StateStoreLocked immediately
                when a CLI mutator holds the per-modem flock. If True
                (default), blocks until the lock is released.
        """
        # Layer 1: per-modem asyncio.Lock (in-process serialization).
        async with self._modem_locks.get(usb_path):
            # Layer 2: per-modem flock (cross-process; daemon-vs-CLI guard).
            # Lock acquisition order: asyncio.Lock acquired above, flock here.
            lock_path = lockfile_for_modem(usb_path, run=self._run_dir)
            async with await acquire_flock_async(lock_path, blocking=wait_for_flock):
                await self._save_modem_state_locked(usb_path, state)

    async def _save_modem_state_locked(
        self,
        usb_path: str,
        state: ModemState,
    ) -> None:
        """Actual write — caller MUST hold the per-modem asyncio.Lock + flock.

        Called from save_modem_state (which acquires both) AND from
        load_modem_state's schema-downgrade branch (which already holds
        both from the outer load context).

        asyncio.Lock is NOT reentrant. Never call from outside an
        already-locked context — it will deadlock.
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
        """Load a ModemState; handles schema-version check and non-destructive downgrade.

        Behavior by schema_version in the file:
          - CURRENT  → returns LoadResult(state, None)
          - TOO_OLD  → renames file to .from-v<N>.json (shadow), writes fresh
                       default via _save_modem_state_locked (no re-acquire —
                       asyncio.Lock + flock already held), returns
                       LoadResult(fresh_state, downgrade_event)
          - TOO_NEW  → raises SchemaVersionTooNew; file unchanged

        Missing file: returns a fresh-default ModemState (unknown state).

        Inventory cross-check (usb_path vs sysfs) is the daemon caller's
        responsibility via cross_check_inventory_for(); this method assumes
        that check has already passed.

        expected_cdc_wdm is a forward-compat hook for the Phase 2 identity
        layer; currently not used in the load path.
        """
        target = state_file_for_modem(usb_path, root=self._state_root)
        lock_path = lockfile_for_modem(usb_path, run=self._run_dir)

        # Layer 1 + Layer 2: same acquisition order as save.
        # SIM117: cannot merge — inner arm uses `await` which is not valid
        # in a multi-context `async with A, await B():` statement.
        async with self._modem_locks.get(usb_path):  # noqa: SIM117
            # Lock acquisition order: asyncio.Lock acquired above, flock here.
            async with await acquire_flock_async(lock_path, blocking=True):
                if not target.exists():
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
                    raw: dict[str, object] = json.loads(raw_bytes.decode("utf-8"))
                except (ValueError, UnicodeDecodeError) as e:
                    raise UsbPathMismatch(
                        file_usb_path=usb_path,
                        sysfs_usb_path=usb_path,
                        cdc_wdm=None,
                        file_path=str(target),
                    ) from e

                file_version = _schema_version_of(raw)
                decision = validate_schema_version(file_version=file_version, where=str(target))

                if decision == "downgrade":
                    shadow = shadow_filename(target, from_version=file_version)
                    target.rename(shadow)
                    fresh = _fresh_modem_state(usb_path)
                    # PRIVATE helper — per-modem asyncio.Lock + flock already held.
                    # Do NOT call self.save_modem_state here (asyncio.Lock is not
                    # reentrant; re-acquiring from the same task deadlocks).
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

                # "current" — parse with pydantic.
                state = ModemState.model_validate(raw)
                _ = expected_cdc_wdm  # forward-compat hook (Phase 2 identity layer)
                return LoadResult(state=state, downgrade_event=None)

    async def list_modem_state_usb_paths(self) -> tuple[str, ...]:
        """Return sorted usb_paths with active (non-shadow) state files on disk."""
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
        """Atomic save with globals asyncio.Lock + state-store flock.

        Lock order (MANDATORY):
          1. globals asyncio.Lock first (in-process).
          2. state-store flock second (cross-process).
        """
        # Layer 1: globals asyncio.Lock (in-process).
        async with globals_lock():
            # Layer 2: state-store flock (cross-process; daemon-vs-CLI guard).
            # Lock acquisition order: asyncio.Lock acquired above, flock here.
            lock_path = state_store_lockfile(run=self._run_dir)
            async with await acquire_flock_async(lock_path, blocking=wait_for_flock):
                await self._save_globals_locked(state)

    async def _save_globals_locked(self, state: GlobalsState) -> None:
        """Actual globals write — caller MUST hold globals asyncio.Lock + state-store flock.

        Called from save_globals AND from load_globals's schema-downgrade branch.
        asyncio.Lock is NOT reentrant; never call from outside an already-locked context.
        """
        target = globals_path(root=self._state_root)
        payload = state.model_dump_json(by_alias=True).encode("utf-8")
        atomic_write_bytes(target, payload)

    async def load_globals(self) -> GlobalsLoadResult:
        """Load GlobalsState; handles schema downgrade non-destructively.

        Missing file: returns fresh-default GlobalsState.
        Downgrade: renames to .from-v<N>.json, writes fresh default via
        _save_globals_locked (no re-acquire — locks already held).
        """
        target = globals_path(root=self._state_root)
        lock_path = state_store_lockfile(run=self._run_dir)

        # SIM117: cannot merge — inner arm uses `await` which is not valid
        # in a multi-context `async with A, await B():` statement.
        async with globals_lock():  # noqa: SIM117
            # Lock acquisition order: asyncio.Lock acquired above, flock here.
            async with await acquire_flock_async(lock_path, blocking=True):
                if not target.exists():
                    return GlobalsLoadResult(state=GlobalsState(), downgrade_event=None)

                raw: dict[str, object] = json.loads(target.read_bytes().decode("utf-8"))
                file_version = _schema_version_of(raw)
                decision = validate_schema_version(file_version=file_version, where=str(target))
                if decision == "downgrade":
                    shadow = shadow_filename(target, from_version=file_version)
                    target.rename(shadow)
                    fresh = GlobalsState()
                    # PRIVATE helper — globals asyncio.Lock + state-store flock already held.
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
    # identity map — shares the state-store flock with globals
    # ------------------------------------------------------------------

    async def save_identity_map(
        self,
        identities: dict[str, Identity],
        *,
        wait_for_flock: bool = True,
    ) -> None:
        """Atomic save of the identity map with globals asyncio.Lock + state-store flock."""
        async with globals_lock():
            # Lock acquisition order: asyncio.Lock acquired above, flock here.
            lock_path = state_store_lockfile(run=self._run_dir)
            async with await acquire_flock_async(lock_path, blocking=wait_for_flock):
                target = identity_map_path(root=self._state_root)
                envelope = {
                    "schema_version": CURRENT_SCHEMA_VERSION,
                    "by_usb_path": {k: v.model_dump(by_alias=True) for k, v in identities.items()},
                }
                payload = json.dumps(envelope, sort_keys=True).encode("utf-8")
                atomic_write_bytes(target, payload)

    async def load_identity_map(self) -> dict[str, Identity]:
        """Load the identity map; raises SchemaVersionTooNew on forward version.

        Missing file: returns {}.
        """
        async with globals_lock():
            # Lock acquisition order: asyncio.Lock acquired above, flock here.
            lock_path = state_store_lockfile(run=self._run_dir)
            async with await acquire_flock_async(lock_path, blocking=True):
                target = identity_map_path(root=self._state_root)
                if not target.exists():
                    return {}
                raw: dict[str, object] = json.loads(target.read_bytes().decode("utf-8"))
                file_version = _schema_version_of(raw)
                validate_schema_version(file_version=file_version, where=str(target))
                by_usb_raw = raw.get("by_usb_path")
                by_usb: dict[str, object] = by_usb_raw if isinstance(by_usb_raw, dict) else {}
                return {k: Identity.model_validate(v) for k, v in by_usb.items()}

    # ------------------------------------------------------------------
    # inventory cross-check — wired at the method level (WARN-1 fix)
    # ------------------------------------------------------------------

    async def cross_check_inventory_for(
        self,
        usb_path: str,
        sysfs_walker: Callable[[], dict[str, str]],
        *,
        expected_cdc_wdm: str | None = None,
    ) -> None:
        """Daemon-startup inventory cross-check for a single state-file usb_path.

        The Phase 2 cycle driver MUST call this for every usb_path returned by
        list_modem_state_usb_paths() BEFORE any load_modem_state call. On
        UsbPathMismatch, the daemon refuses to start (S-02).

        Caller pattern:
            walker = lambda: walk_sysfs_for_qmi_modems(Path("/sys"))
            for usb_path in await store.list_modem_state_usb_paths():
                await store.cross_check_inventory_for(usb_path, walker)
            # Only after all cross-checks pass, proceed to load + run cycles.

        expected_cdc_wdm: optional hook for Phase 2 identity layer; when
        omitted, verifies usb_path presence in sysfs only.
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


# ------------------------------------------------------------------
# Private module-level helpers
# ------------------------------------------------------------------


def _schema_version_of(raw: dict[str, object]) -> int:
    """Extract schema_version from a raw JSON dict; returns 0 if missing/non-int."""
    sv = raw.get("schema_version", 0)
    if isinstance(sv, int):
        return sv
    if isinstance(sv, str):
        try:
            return int(sv)
        except ValueError:
            return 0
    return 0


def _fresh_modem_state(usb_path: str) -> ModemState:
    """Default state for a freshly-discovered (or downgraded) modem."""
    # usb_path is not stored in ModemState (ADR-0009: the file's name carries
    # the usb_path). It is accepted here to document intent for the caller.
    _ = usb_path
    # Use model_validate with the alias key (_healthy_streak) because mypy
    # without the pydantic plugin cannot verify the populate_by_name alias
    # mapping and raises a call-arg error on `healthy_streak=0`.
    return ModemState.model_validate(
        {
            "state": "unknown",
            "present": True,
            "rf_blocked": False,
            "recovering_level": None,
            "_healthy_streak": 0,
            "counters": {},
            "last_action_monotonic": None,
            "last_state_transition_iso": _now_iso(),
        }
    )


def _now_iso() -> str:
    """Current UTC time as ISO-8601 string (wall-clock; ADR-0007)."""
    return datetime.now(UTC).isoformat()
