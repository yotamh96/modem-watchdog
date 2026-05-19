# S12: V1 Decommission & Archive — UAT

**Milestone:** M001
**Written:** 2026-05-19T12:32:15.863Z

# UAT: S12 — V1 Decommission & Archive

**UAT Type:** Documentation correctness — verified by file-existence tests, content grep checks, and automated validation suite.

## Preconditions

- S11 (Cutover & Fleet Rollout) completed: MIGRATION.md rewritten, stale-doc cleanup done.
- Repository checked out at the M001 worktree.
- Python venv with pytest, mypy, ruff available.

## Steps

1. **Verify archive pointer exists and is correct**
   - Open `archive/v1/README.md`.
   - Confirm it lists the five v1 scripts (`diag.sh`, `recovery.sh`, `auto_profile.sh`, `zao_reset_line.sh`, `spark-modem-watchdog.sh`).
   - Confirm it references ADR-0014 and the retirement date (2026-05-11).
   - Confirm it states v1 scripts were never in this repo and points to the v1-legacy branch.
   - **Expected:** All items present; document is a pointer, not a container.

2. **Verify purge checklist is operator-ready**
   - Open `docs/V1_PURGE_CHECKLIST.md`.
   - Confirm five verification areas: scripts removal, cron cleanup, systemd cleanup, state file cleanup, v2 health confirmation.
   - Confirm sign-off block exists for operator audit trail.
   - **Expected:** Checklist is actionable per-box with clear pass/fail criteria.

3. **Verify postmortem template has required structure**
   - Open `docs/MIGRATION_POSTMORTEM_TEMPLATE.md`.
   - Confirm sections: timeline, incident log, lessons learned, before/after metrics, sign-off.
   - Confirm MTTR rows broken out by fault type (SIM, registration, QMI-hung).
   - Confirm `{{PLACEHOLDER}}` syntax used throughout.
   - **Expected:** Template matches PRD M1-M5 metrics and MIGRATION.md Phase 5 requirements.

4. **Verify ADR README includes ADR-0014**
   - Open `docs/adr/README.md`.
   - Confirm ADR-0014 appears in the status table.
   - **Expected:** Entry present with title, status, and date.

5. **Verify docs README is updated**
   - Open `docs/README.md`.
   - Confirm ADRs 0008-0014 are listed (previously stopped at 0007).
   - Confirm v1 references use past-tense retired language, not active-state claims.
   - Confirm pointer to `archive/v1/README.md` exists.
   - **Expected:** No stale v1-as-active language remains.

6. **Run automated validation suite**
   - Execute: `pytest tests/unit/test_v1_decommission.py -v`
   - **Expected:** 7/7 tests pass.

7. **Run full regression suite**
   - Execute: `pytest tests/unit/ -q`
   - **Expected:** All existing tests pass (1008+), no new failures.

## Edge Cases

- **False positives in stale-reference sweep:** Historical/architectural mentions of v1 (e.g., "v1 was replaced by v2") are intentionally kept. Only active-state claims ("v1 handles...") should be flagged. The test suite's regex patterns distinguish these.
- **Template placeholders:** `{{PLACEHOLDER}}` syntax must remain literal — operators fill these in post-migration, not the build system.

## Not Proven By This UAT

- Operator actually executes the purge checklist on a live Jetson box (field validation).
- Postmortem template is filled in with real migration metrics (happens post-rollout).
- ADR-0014 document itself exists in `docs/adr/` (that was an S11 deliverable, not S12).
- v1 scripts are actually removed from fleet devices (operational, not repo-level).
