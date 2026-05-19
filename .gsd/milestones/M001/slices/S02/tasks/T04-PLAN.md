# T04: 02-core-daemon-laptop-testable 04

**Slice:** S02 — **Milestone:** M001

## Description

Plan 02-04 lands the observer subsystem and its supporting inventory:
the `InventorySource` Protocol + `SysfsInventory` impl, and the
`asyncio.TaskGroup`-based probe orchestrator that produces one `Diag` per cycle.

This is the "fan-out" half of the cycle (the policy engine is the "decide"
half — plan 02-05). The orchestrator obeys two CLAUDE.md invariants:
- Every per-modem probe runs under `asyncio.timeout(8s)` inside a TaskGroup
  (FR-70, NFR-4).
- Every per-modem probe catches its own exceptions; the TaskGroup never sees
  an exception escape, so one slow modem never cancels its three siblings
  (NFR-11).

Output: `inventory/` package + `observer/` package + parametrized tests
(parallel-probe correctness, single-probe timeout, single-probe exception,
Zao-active-skip behavior) + sysfs fixture tree for SysfsInventory.

## Must-Haves

- [ ] "InventorySource Protocol exposes async scan() -> list[ModemDescriptor]; FixtureInventory + SysfsInventory both satisfy it."
- [ ] "ModemDescriptor carries (line, cdc_wdm, usb_path, ns, iface) per FR-2."
- [ ] "Observer.observe_all uses asyncio.TaskGroup with per-task asyncio.timeout(8s); one slow probe never cancels siblings."
- [ ] "Each per-modem probe catches all exceptions internally — TaskGroup never sees an exception escape (NFR-11 protected)."
- [ ] "Zao-active modems return ModemSnapshot.zao_active(...) with zero issues (FR-10 enforced before any qmicli call)."
- [ ] "Builder produces a single Diag(BaseWire) per cycle from observer output (FR-13)."
- [ ] "Issue extractor surfaces all RECOVERY_SPEC §4 detected issues from ModemSnapshot fields."

## Files

- `src/spark_modem/inventory/__init__.py`
- `src/spark_modem/inventory/protocol.py`
- `src/spark_modem/inventory/descriptor.py`
- `src/spark_modem/inventory/sysfs.py`
- `src/spark_modem/observer/__init__.py`
- `src/spark_modem/observer/orchestrator.py`
- `src/spark_modem/observer/diag_builder.py`
- `src/spark_modem/observer/issue_extractor.py`
- `tests/unit/inventory/__init__.py`
- `tests/unit/inventory/test_sysfs.py`
- `tests/unit/observer/__init__.py`
- `tests/unit/observer/test_orchestrator.py`
- `tests/unit/observer/test_diag_builder.py`
- `tests/fakes/inventory.py`
- `tests/fixtures/inventory/four_modems_one_zao_active.json`
- `tests/fixtures/inventory/two_modems.json`
- `tests/fixtures/sysfs/four_modems/sys/bus/usb/devices/.gitkeep`
