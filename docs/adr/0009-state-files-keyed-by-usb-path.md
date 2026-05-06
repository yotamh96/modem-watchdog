# ADR-0009 — State files keyed by usb_path

| Field        | Value          |
| ------------ | -------------- |
| Status       | Accepted       |
| Date         | 2026-05-06     |
| Deciders     | Eng team       |

## Context

v1 keyed per-modem state files by `cdc-wdm` device index
(`cdc-wdm0`, `cdc-wdm1`, `cdc-wdm2`, `cdc-wdm3`). This is the
kernel's enumeration order at a given boot, not a stable identifier.

**The problem** (`.planning/research/PITFALLS.md` §3.1): the kernel's
`cdc-wdm` enumeration order varies across boots. When the USB hub
re-enumerates — after a suspend-resume cycle, a hub reset, or a
`usb_reset` action — the kernel may assign `cdc-wdm0` to the physical
modem that was previously `cdc-wdm2`. v1's state files then attach
to the wrong physical modem. Recovery counters, escalation history,
and ICCID identity cross-reference are silently corrupted.

**The root cause**: `cdc-wdmN` is a kernel enumeration artifact, not
a physical identity. It reflects the order in which the kernel
discovered devices on this boot, which depends on USB hub timing and
driver probe order. It is not stable.

**The fix** (`.planning/research/ARCHITECTURE.md` Q14): key state
files by `usb_path` — the sysfs path of the USB device
(e.g. `2-3.1.1`, `2-3.1.2`, `2-3.1.3`, `2-3.1.4`). The `usb_path`
reflects physical topology (port numbers on the USB hub chain), which
is stable across enumerations as long as the physical cabling does not
change.

## Decision

Per-modem state files persist at:

```
/var/lib/spark-modem-watchdog/state/by-usb/<usb_path>.json
```

Where `<usb_path>` is the sysfs USB path (e.g. `2-3.1.1`). The
`usb_path` regex is `^\d+(-\d+(\.\d+)*)?$`; the `paths.py` module
rejects any value containing `/` or `..`.

The identity map (`ICCID/IMSI ↔ modem`) is also keyed by `usb_path`.
The runtime `cdc-wdmN` device node is a lookup result, not a key.

### Startup inventory cross-check

On daemon startup, the inventory module:

1. Walks `/sys/bus/usb/devices/` to build the current
   `(usb_path → cdc_wdm_index)` mapping from sysfs.
2. For each persisted state file in `state/by-usb/`, reads the
   `usb_path` field from the file's identity header.
3. Cross-checks: the file's `usb_path` must match a live sysfs entry.

On **mismatch** (a state file's `usb_path` is not present in sysfs,
or the sysfs topology has changed since the file was written), the
daemon:

1. Emits a typed `UsbPathMismatch` event:
   `{module: 'inventory', error: 'usb_path_mismatch',
   details: {file_usb_path, sysfs_usb_path, cdc_wdm}}`.
2. Sends `STATUS=usb_path_mismatch` via `sd_notify` so
   `systemctl status` surfaces the cause immediately.
3. **Exits non-zero.** The daemon does NOT start in a degraded mode
   that could silently corrupt state for the wrong physical modem.

**Recovery**: the operator runs:
```
spark-modem ctl reset-state --modem=<usb_path>
```
or
```
spark-modem ctl reset-state --all
```
to clear the offending file(s). (The `ctl reset-state` subcommand
lands in Phase 2; until then, the operator deletes the file by hand.)

### Shadow files

When a state file is downgraded (ADR-0004 amendment), the old-version
file is preserved as `state/by-usb/<usb_path>.from-v<N>.json`. The
inventory walker excludes these files via the `.from-v*.json` suffix
check — they are not subject to the usb_path cross-check.

## Consequences

- **cdc-wdmN renumbering does not corrupt state.** After a USB
  re-enumeration, the daemon re-walks sysfs, rebuilds the
  `(usb_path → cdc_wdm)` map, and looks up the correct state file
  by `usb_path`. The state file has not moved.

- **Hot-plug of a modem mid-flight** is supported via udev events
  (Phase 3 wires `pyudev.Monitor`). A hot-plugged modem with a known
  ICCID at the same `usb_path` re-uses its existing state file. A
  modem at a new `usb_path` starts fresh.

- **SIM swap detection** (Phase 3 FR-4): the daemon compares the live
  ICCID (from qmicli) against the persisted `Identity.iccid` in the
  `usb_path`-keyed state file. A mismatch signals a SIM swap event.

- **`state/by-usb/` is the single source of truth.** The `cdc-wdmN`
  device node is a runtime detail discovered at startup and on each
  udev event; it is never persisted as a primary key.

- **The `*.from-v<N>.json` shadow files** are siblings in
  `state/by-usb/`; the inventory walker excludes them via filename
  suffix check. They are preserved for `ctl migrate-state` (Phase 2).

- **Atomic writes** (ADR-0012): all writes to `state/by-usb/*.json`
  use temp-file + rename + directory fsync. The `usb_path` in the file
  is written on creation and never changes; it is validated on read
  as a consistency check.

## Risks and mitigations

| Risk | Mitigation |
| ---- | ---------- |
| Two boxes with the same physical USB topology have colliding `usb_path` strings | The daemon runs per-box; state directories are not shared. No cross-box collision is possible. |
| Replacing a USB hub mid-flight changes `usb_path`s globally | This is a topology change, not a renumbering. The operator is expected to run `ctl reset-state --all` after hardware reconfiguration. The daemon will refuse to start with `UsbPathMismatch` on the next boot, making the problem immediately visible. |
| `usb_path` string containing `/` or `..` (path traversal) | `paths.py` validates `usb_path` against the regex `^\d+(-\d+(\.\d+)*)?$` before constructing any filesystem path. Validation happens at parse time, not at use time. |
| Inventory cross-check races with a concurrent udev event during startup | The inventory cross-check happens before the daemon installs the udev monitor. The sysfs walk and the check are synchronous during the startup sequence. A udev event arriving during startup is queued; the daemon processes it after the check completes. |
| State file for a modem that was physically removed still exists | On startup, the cross-check emits `UsbPathMismatch` and the daemon exits. The operator deletes the stale file. This is intentional: the daemon prefers loud failure over silent state mismatch. |

## Implementation reference

- `src/spark_modem/state_store/paths.py` — `usb_path` validation,
  state-file path construction (Plan 04).
- `src/spark_modem/state_store/inventory.py` — sysfs walk +
  `(usb_path → cdc_wdm)` map + startup cross-check (Plan 04).
- `tests/unit/state_store/test_inventory_crosscheck.py` — hypothesis
  property test for random USB renumbering permutations (Plan 04,
  Phase 1 SC #5).
- `src/spark_modem/wire/state.py` — `ModemState` shape includes
  `usb_path` in its identity header (Plan 03).

## Revisit when

- USB topology becomes itself unstable (e.g. the fleet rolls out a
  different USB hub model with a different port numbering scheme).
  Then `usb_path` strings change with hardware model, and we need a
  more stable identifier (e.g. ICCID-keyed state with a
  `usb_path → ICCID` runtime map).
- A Zao SDK upgrade exposes a stable per-modem identifier above the
  kernel (e.g. a Zao-assigned modem UUID). Then we can key on that
  instead of `usb_path`.
- The hardware target changes to a platform where sysfs `usb_path`
  is not stable (unlikely on Jetson Orin NX with a fixed USB hub).
