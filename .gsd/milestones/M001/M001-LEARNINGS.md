---
phase: M001
phase_name: Migration
project: spark-modem-watchdog
generated: 2026-05-19T15:45:00Z
counts:
  decisions: 6
  lessons: 5
  patterns: 4
  surprises: 3
missing_artifacts:
  - S04-SUMMARY.md (scope absorbed into S02+S03; slice skipped)
---

# M001 Learnings

### Decisions

- **ADR-0014: v1-retired scope pivot** — Mid-milestone decision to treat v1 as fully retired across the fleet. Eliminated shadow-deployment phases from MIGRATION.md, removed need for v1 .deb packaging, and simplified S11/S12 scope significantly. Rollback defined as v2→v2-previous only.
  Source: S11-SUMMARY.md/Key Decisions

- **Version 2.0.1-1 over 2.0.0+hotfix.1** — Chose standard Debian versioning for the first hotfix release. The `+` separator in local versions causes handling quirks in apt on Ubuntu 20.04; `2.0.1-1` is universally supported by Debian/PEP-440.
  Source: S06-SUMMARY.md/Plan 06

- **HMAC secret fallback for systemd 245** — LoadCredential= was introduced in systemd 247 but the target L4T R35.6.4 ships systemd 245. Added code-side fallback (L-02) reading from `/etc/spark-modem-watchdog/hmac-secret` when `CREDENTIALS_DIRECTORY` is unset.
  Source: S06-SUMMARY.md/Plan 02

- **WakeSignal as closed StrEnum** — Closed the WakeSignal enum to prevent arbitrary payload injection via pydantic validation. Supervisor never touches signal.signal or subprocess directly.
  Source: S03-SUMMARY.md/Key Architectural Decisions

- **Replay harness with 1002 fixtures for v1 agreement gate** — Built ceiling-divide fixture generator across 7 fault scenarios + 50 healthy cycles to achieve ≥95% v1 agreement as Phase 2 EXIT GATE.
  Source: S02-SUMMARY.md/Key Decisions

- **PromQL gates use Prometheus builtins** — Gate 4 uses `process_start_time_seconds` (Prometheus builtin) rather than a custom metric; Gate 3 uses `actions_total` as proxy. Minimizes custom metric surface.
  Source: S11-SUMMARY.md/Key Decisions

### Lessons

- **Phase 1 smoke gate was insufficient** — The postinst smoke test only imported 10 runtime libs, never the daemon package itself. This meant broken imports in daemon/CLI code passed the gate. S06 expanded the gate to also import `spark_modem.daemon.main` and `spark_modem.cli.main`. Future phases must include this pattern.
  Source: S06-SUMMARY.md/Learnings

- **Protocol structural matching is stricter than expected** — mypy strict with Protocols requires exact type variance. Using `kind: object` in a Protocol doesn't match `kind: ActionKind` in the implementation. Must import and use the exact type.
  Source: S02-SUMMARY.md/Learnings

- **Default-parameter capture at definition time breaks monkeypatch** — Monkeypatching module constants has no effect on functions that captured the value as a default parameter at definition time. Must use wrapper approach instead.
  Source: S02-SUMMARY.md/Learnings

- **pytest-asyncio mode=auto eliminates per-test decorators** — Redundant `@pytest.mark.asyncio` decorators and module-level `pytestmark` assignments are unnecessary when mode=auto is configured. Removing them is a lint requirement (multiple slices hit this).
  Source: S03-SUMMARY.md/Deviations, S05-SUMMARY.md/Deviations

- **systemd 245 compatibility requires proactive verification** — Target platform ships systemd 245, not 247+. Features like LoadCredential= silently do nothing. CI must include `systemd-analyze verify` against the target systemd version, not the build host version.
  Source: S06-SUMMARY.md/Plan 05

### Patterns

- **Belt-and-suspenders smoke test** — Smoke-import gate in TWO places: postinst (catches broken .deb install) and ExecStartPre (catches runtime path issues). Neither alone is sufficient; both are cheap.
  Source: S01-SUMMARY.md/Key Decisions, S06-SUMMARY.md/Plan 05

- **Documentation-only slices verified via grep + pytest** — Template files use `{{PLACEHOLDER}}` syntax. Verification uses grep-based content checks (no stale references) plus a pytest validation suite that asserts structural properties of the documents.
  Source: S12-SUMMARY.md/Patterns Established

- **Archive pointer pattern for deprecated modules** — Instead of copying retired code into the repo, create a pointer document (`archive/v1/README.md`) recording: retirement date, ADR reference, and where to find the original if needed. Keeps repo clean while maintaining traceability.
  Source: S12-SUMMARY.md/Key Decisions

- **Unit-file audit tests catch drift** — Dedicated tests that cross-check `pyproject.toml [project.scripts]` against `debian/.install` against systemd `ExecStart*` paths. Catches the class of bug where one path is updated but the others aren't.
  Source: S06-SUMMARY.md/Plan 05

### Surprises

- **S04 scope fully absorbed into S02+S03** — The "Destructive Actions HIL" slice was planned as independent work but its scope was entirely delivered by S02 (ActionDispatcher registry, 48 action tests, 6 cheap actions) and S03 (HIL testing deferred to Phase 4 per exit gate). S04 ended up as a 0-task slice with no independent deliverables.
  Source: M001-VALIDATION.md/Verdict Rationale

- **Floor-divide vs ceiling-divide for fixture generation** — The replay harness generator used floor division, producing 995 fixtures instead of the required 1000+. A subtle off-by-one that only surfaced when counting the output. Fixed by switching to ceiling division (1002 fixtures).
  Source: S02-SUMMARY.md/Deviations

- **S11 stale-reference sweep was exhaustive** — S12's independent grep sweep for v1-as-active references found zero remaining instances, confirming S11's cleanup was thorough. Expected to find stragglers; found none.
  Source: S12-SUMMARY.md/Learnings
