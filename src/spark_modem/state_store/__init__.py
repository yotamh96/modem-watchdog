"""StateStore — atomic, locked, schema-versioned persistence.

Public surface for Phase 2/3/4 consumers:

    from spark_modem.state_store import StateStore, LoadResult, UsbPathMismatch
"""

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
    "AsyncFlockHandle",
    "AtomicWriteFailed",
    "GlobalsLoadResult",
    "LoadResult",
    "PerModemLockTable",
    "StateStore",
    "StateStoreError",
    "StateStoreLocked",
    "UsbPathMismatch",
    "acquire_flock",
    "acquire_flock_async",
    "cross_check_inventory",
    "globals_lock",
    "walk_sysfs_for_qmi_modems",
]
