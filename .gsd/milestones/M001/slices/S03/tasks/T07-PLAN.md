# T07: 03-linux-event-sources-lifecycle 07

**Slice:** S03 — **Milestone:** M001

## Description

Wave 3b — cycle_driver SIM-swap detection + StateStore atomic streak/counters
reset. Depends on Plan 03-06's SimSwapped wire variant.

Specifically:

  1. Add `StateStore.reset_modem_streak_and_counters(usb_path: str)` public
     method that takes the per-modem asyncio.Lock + flock and resets
     `_healthy_streak` + all escalation counters in ONE atomic write per
     RECOVERY_SPEC §8 ordering. (Issue #9.)
  2. Insert SIM-swap detection into `daemon/cycle_driver.py` per-cycle
     pipeline: load identity map, compare against current observation,
     persist updated map, call `reset_modem_streak_and_counters` for each
     swapped usb_path, emit SimSwapped event with sha256[:8]-redacted ICCIDs.
  3. Two unit tests: one for the StateStore method (atomic ordering), one
     for the cycle-driver integration (E-04 / FR-4 latency = one cycle;
     SimSwapped event emitted via event_logger.append, NOT logger.info).

This plan was carved out of the original Plan 03-06 to keep that plan
focused on lifecycle modules + main.py rewrite. SIM-swap detection is its
own concern (state-store extension + cycle-driver integration); splitting
keeps each plan within context budget.

Output: 1 modified state-store module + 1 modified daemon module + 2 new
test files.

## Must-Haves

- [ ] "Cycle driver compares per-modem identity each cycle; ICCID change at the same usb_path triggers atomic reset (E-04 / FR-4)."
- [ ] "StateStore.reset_modem_streak_and_counters resets _healthy_streak + escalation counters in ONE atomic write per RECOVERY_SPEC §8 ordering (Issue #9)."
- [ ] "SIM-swap reset takes per-modem asyncio.Lock + flock; daemon and a concurrent ctl mutator never produce a lost update (FR-61.1)."
- [ ] "Cycle driver emits SimSwapped event variant (NOT logger.info) — Plan 03-06 wire variant is the emission target (Issue #8)."
- [ ] "ICCID values are sha256[:8]-redacted in the SimSwapped event payload — daemon never logs raw ICCIDs."

## Files

- `src/spark_modem/daemon/cycle_driver.py`
- `src/spark_modem/state_store/store.py`
- `tests/unit/daemon/test_sim_swap_detection.py`
- `tests/unit/state_store/test_reset_modem_streak_and_counters.py`
