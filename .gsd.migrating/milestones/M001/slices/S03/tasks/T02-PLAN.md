# T02: Plan 02

**Slice:** S03 — **Milestone:** M001

## Description

Wave 2 — pyudev producer + UdevInventory swap + netns end-to-end.
Specifically:

  1. `src/spark_modem/event_sources/udev_producer.py` — `run_udev_producer`
     coroutine using `pyudev.Monitor.from_netlink(Context())` +
     `loop.add_reader(monitor.fileno(), on_readable)` (PITFALLS §7.1
     PRESCRIPTIVE — never `MonitorObserver`). Body: `event_queue.put_nowait(
     WakeSignal.UDEV)` only. NO sysfs reads, NO parsing, NO state
     (E-02).
  2. `src/spark_modem/inventory/udev.py` — `UdevInventory` satisfies the
     existing `InventorySource` Protocol. Internally delegates the sysfs
     walk to `SysfsInventory` (composition; the walk shape is shared).
  3. `src/spark_modem/inventory/netns.py` — `derive_ns(usb_dev_path:
     Path) -> str | None`. Pure function (per PATTERNS.md analog: same
     staticmethod shape as `_find_cdc_wdm` / `_find_wwan_iface`). The
     derivation source is Open Question 4 in RESEARCH.md — pick option
     (a) sysfs `/proc/.../ns/net` of the cdc-wdm worker AND fall back
     to None on file-absent (single-namespace bench is the Phase 3
     reality; production fleet decides later).
  4. `src/spark_modem/inventory/sysfs.py` — replace the literal `ns=None`
     at line 79 with `ns=derive_ns(resolved)`. Single-line edit per
     PATTERNS.md "MODIFIED: inventory/sysfs.py" guidance.
  5. `src/spark_modem/qmi/wrapper.py` — extend `QmiWrapper.__init__`
     with optional `ns: str | None = None`; add a private `_argv(self,
     qmicli_args: list[str]) -> list[str]` helper that prepends `["ip",
     "netns", "exec", self._ns]` when `self._ns is not None`; rewrite
     every existing method's argv-construction call site to route
     through `self._argv([...])`. NEVER `setns()` from asyncio (PITFALLS
     §6.2 — the `ip netns exec` subprocess does its own setns in a
     forked child).
  6. Test seams: `tests/fakes/udev.py` (FakeUdevMonitor), unit tests
     for the producer + UdevInventory + derive_ns + QmiWrapper netns
     prepend.

Purpose: Plans 03-03/04/05 each ship one producer; this plan ships the
udev producer and the netns end-to-end because netns derivation is
inventory-resident (E-05) and qmicli netns-aware invocation is the
direct consumer. Splitting them across two plans would cross a clean
seam unnecessarily.

Output: 5 new production files + 2 modified production files + 4 new
test files.
