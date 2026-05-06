"""Exception types raised by the state-store layer.

These are EXCEPTIONS — control-flow signals. The on-the-wire equivalents
(e.g. spark_modem.wire.events.UsbPathMismatch) are *event records*; do not
confuse the two. The daemon's startup path (Phase 2/3) catches these
exceptions and emits the corresponding wire events.

Naming clarification:
  state_store.errors.UsbPathMismatch  = Exception (raises from cross-check)
  wire.events.UsbPathMismatch         = Pydantic BaseModel (persisted event record)

N818: ruff wants "Error" suffix on exception names. These names are mandated by
the plan's must_haves (UsbPathMismatch, StateStoreLocked, AtomicWriteFailed).
"""

from __future__ import annotations


class StateStoreError(Exception):
    """Base class for all state-store control-flow signals."""


class UsbPathMismatch(StateStoreError):  # noqa: N818
    """Inventory cross-check failed: file's usb_path doesn't match sysfs.

    S-02: daemon refuses to start on this exception. Operator runs
    ``spark-modem ctl reset-state --modem=<usb_path>`` to clear.

    ADR-0009: cross-check is mandatory at daemon startup before any
    load_modem_state call.
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


class StateStoreLocked(StateStoreError):  # noqa: N818
    """Cross-process flock acquisition failed because another holder owns it.

    T-04-06: save_modem_state / save_globals accept ``wait_for_flock`` —
    CLI callers may opt out and catch this exception immediately rather than
    blocking the terminal.
    """

    def __init__(self, *, holder_pid: int | None, lock_path: str) -> None:
        self.holder_pid = holder_pid
        self.lock_path = lock_path
        holder_str = f"pid {holder_pid}" if holder_pid is not None else "unknown holder"
        super().__init__(f"State-store lock {lock_path!r} held by {holder_str}")


class StateFileCorrupt(StateStoreError):  # noqa: N818
    """JSON parse failure on a persisted state file.

    Distinct from UsbPathMismatch (inventory mismatch) and StateFileIOError
    (OS-level read failure). Operator runbook step: inspect the file, then
    run ``spark-modem ctl reset-state --modem=<usb_path>`` to clear.
    """

    def __init__(
        self,
        *,
        file_path: str,
        reason: str,
        original_exception: BaseException | None = None,
    ) -> None:
        self.file_path = file_path
        self.reason = reason
        self.original_exception = original_exception
        super().__init__(f"State file corrupt: {file_path!r}: {reason}")


class StateFileIOError(StateStoreError):  # noqa: N818
    """OS-level I/O error reading or writing a state file.

    Distinct from UsbPathMismatch (inventory mismatch) and StateFileCorrupt
    (bad JSON). Causes include EIO (storage failure), EACCES (permissions),
    ENOSPC. Operator runbook step: investigate hardware / permissions before
    clearing state.
    """

    def __init__(
        self,
        *,
        file_path: str,
        reason: str,
        original_exception: BaseException | None = None,
    ) -> None:
        self.file_path = file_path
        self.reason = reason
        self.original_exception = original_exception
        super().__init__(f"State file I/O error: {file_path!r}: {reason}")


class AtomicWriteFailed(StateStoreError):  # noqa: N818
    """An atomic file write could not be completed.

    The target file is guaranteed to be unchanged (or not created) because the
    write happened to a temp file first; the replace never happened.
    """

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
