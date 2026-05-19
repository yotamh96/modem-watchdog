# T06: 02-core-daemon-laptop-testable 06

**Slice:** S02 — **Milestone:** M001

## Description

Plan 02-06 lands the cheap action set the policy engine in plan 02-05
selects from. Six action modules (one file per action) plus a shared
dispatcher and result types.

The dispatcher is the SINGLE entry point used by:
- The cycle driver (plan 02-10) for `execute_and_verify(plan.kind, plan.who, ctx)`.
- The CLI (plan 02-09) for `spark-modem reset --action=<name> --modem=...`.

Phase 2 cheap actions (per CLAUDE.md "Critical invariants" + RECOVERY_SPEC §2):
1. `set_apn` — reads carrier table by (MCC, MNC), writes profile-1 if APN
   differs (FR-31), then reads back to verify (FR-32). Idempotent.
2. `fix_raw_ip` — sets `--wds-set-ip-family=4` when raw_ip is "N".
3. `sim_power_on` — `--uim-sim-power-on=1`.
4. `soft_reset` — single qmicli reset; verify is deferred (effect observed
   next cycle, not inline).
5. `set_operating_mode` — DMS set/get operating mode (used to push out of
   `low_power` / `offline`; idempotent — FR-31-style read-then-write).
6. `fix_autosuspend` — writes "on" to the USB device's `power/control`
   sysfs file (this is the only action that doesn't go through qmicli;
   it goes through `subproc.run` for `tee` so SP-04 lint stays clean —
   alternative: use `Path.write_text` since it's a regular file write,
   not a subprocess).

Destructive actions (modem_reset / usb_reset / driver_reset) are NOT
registered here — they land in Phase 4. The dispatcher registry shape
guarantees Phase 4 is a pure data-add.

Output: `actions/` package + per-action tests using FakeRunner +
dry-run gate tests + carrier-table lookup tests.

## Must-Haves

- [ ] "actions/dispatcher.execute_and_verify(kind, who, ctx) is the SINGLE entry point for both CLI and cycle driver."
- [ ] "Each action file (set_apn.py, fix_raw_ip.py, sim_power_on.py, soft_reset.py, set_operating_mode.py, fix_autosuspend.py) exposes execute(modem, ctx) and verify(modem, ctx)."
- [ ] "Phase 4 destructive actions (modem_reset, usb_reset, driver_reset) register into the same _REGISTRY without dispatcher code changes."
- [ ] "FR-31: set_apn skips writing if observed APN already matches desired (read-then-write)."
- [ ] "FR-32: post-write verify reads the field back and returns VerifyResult.ok or VerifyResult.failed."
- [ ] "Soft-reset.verify() returns VerifyResult.deferred() — its effect is observed next cycle, not inline."
- [ ] "FR-28: --dry-run gate is at action-execution time; ActionResult carries dry_run=True with no side effects."
- [ ] "FR-28.1: per-modem dry-run accepts bool | list[str] from config; gate at the dispatcher consults the list of usb_paths."
- [ ] "Carrier-table lookup (FR-30) consults the YAML-backed wire/carriers.py CarrierTable; new MCC/MNC adds = YAML edit + reload (FR-33 / NFR-42)."

## Files

- `src/spark_modem/actions/__init__.py`
- `src/spark_modem/actions/result.py`
- `src/spark_modem/actions/context.py`
- `src/spark_modem/actions/dispatcher.py`
- `src/spark_modem/actions/verify.py`
- `src/spark_modem/actions/set_apn.py`
- `src/spark_modem/actions/fix_raw_ip.py`
- `src/spark_modem/actions/sim_power_on.py`
- `src/spark_modem/actions/soft_reset.py`
- `src/spark_modem/actions/set_operating_mode.py`
- `src/spark_modem/actions/fix_autosuspend.py`
- `src/spark_modem/wire/carriers.py`
- `tests/unit/actions/__init__.py`
- `tests/unit/actions/test_dispatcher.py`
- `tests/unit/actions/test_set_apn.py`
- `tests/unit/actions/test_fix_raw_ip.py`
- `tests/unit/actions/test_sim_power_on.py`
- `tests/unit/actions/test_soft_reset.py`
- `tests/unit/actions/test_set_operating_mode.py`
- `tests/unit/actions/test_fix_autosuspend.py`
- `tests/unit/actions/test_dry_run.py`
- `tests/unit/actions/test_verify.py`
