---
estimated_steps: 11
estimated_files: 1
skills_used: []
---

# T02: MIGRATION.md rewrite for v1-retired reality

**Why:** The current MIGRATION.md references dead artifacts (99-shadow.yaml, compare_v1_v2.py, -v2 paths, v1 .deb rollback) and dead phases (Phase 1 shadow-alongside, Phase 2 field-shadow). Operators will follow stale procedures if this isn't fixed. This is the P0 deliverable.

**Do:**
1. Rewrite Phase 1 (§3) — replace shadow-alongside framing with: v2 deployed live on bench Jetson for 1-week soak. Remove all references to `-v2` service, `99-shadow.yaml`, `tools/compare_v1_v2.py`.
2. Rewrite Phase 2 (§4) — replace field-shadow framing with: v2 deployed live on field box for 2-week soak.
3. Simplify Phase 3 (§5) — remove unmask/remask dance, -v2 path migration, 99-shadow.yaml removal. Cutover is: `apt install` the .deb, `systemctl enable --now`, verify Healthy within 60s.
4. Fix Phase 4 (§6) — update metric names from `modem_state{state="exhausted"}` to `modem_state_value` integer-encoded per ADR-0013. Reference `docs/FLEET_GATES.md` for concrete PromQL.
5. Fix Phase 6 (§8) — remove `apt purge spark-modem-watchdog-v1` reference.
6. Fix rollback (§5) — replace v1 .deb rollback with v2-previous version rollback per ADR-0014. State: rollback = `apt install spark-modem-watchdog=<previous-version>`.
7. Update intro paragraph — remove "v1 currently keeps a real fleet online" framing; add v1-retired context referencing ADR-0014.
8. Update Status field to reflect current state. Update Last-updated date.

**Done-when:** `grep -cE '99-shadow|compare_v1_v2|watchdog-v2\.service|-v2/' docs/MIGRATION.md` returns 0. All phase procedures reflect v1-retired reality. ADR-0014 is referenced.

## Inputs

- `docs/MIGRATION.md`
- `docs/adr/0014-v1-retired-pivot.md`
- `docs/FLEET_GATES.md`
- `src/spark_modem/status_reporter/metrics_registry.py`

## Expected Output

- `docs/MIGRATION.md`

## Verification

Select-String -Pattern '99-shadow|compare_v1_v2|watchdog-v2\.service|-v2/' docs/MIGRATION.md -Quiet; if ($?) { Write-Error 'Stale refs found'; exit 1 } else { Write-Output 'No stale refs' }; Select-String -Pattern 'ADR-0014' docs/MIGRATION.md -Quiet
