# spark-modem-watchdog v2 — design docs

Seed documents for the rewrite of the Sierra EM7421 multi-modem
diagnostic, recovery, and provisioning toolchain.

The v1 system (the scripts in the parent directory) works in production
but has limits we want to break out of in v2. These documents are the
single source of truth for *what* v2 is, *why* it is that way, and
*how* it is built and operated.

## Reading order

If you have one hour, read these in order:

1. **[PRD.md](PRD.md)** — Why we're building it, what it must do,
   what success looks like, what's out of scope.
2. **[ARCHITECTURE.md](ARCHITECTURE.md)** — Components, data flow,
   tech stack, deployment model. The "how it fits together."
3. **[RECOVERY_SPEC.md](RECOVERY_SPEC.md)** — The single most important
   spec: the per-modem recovery state machine, gates, and decision tables.
4. **[SCHEMA.md](SCHEMA.md)** — The wire formats: diag output, status
   snapshot, event log, recovery state file.

If you have another hour:

5. **[RUNBOOK.md](RUNBOOK.md)** — Install, day-2 operations, on-call.
6. **[TEST_STRATEGY.md](TEST_STRATEGY.md)** — Fixtures, fakes, CI gates.
7. **[MIGRATION.md](MIGRATION.md)** — How we cut over from v1.
8. **[GLOSSARY.md](GLOSSARY.md)** — Domain terms, acronym expansions.

## Architecture decision records

Decisions that close off design alternatives. Read these when something
in the architecture surprises you — the rationale is in the ADRs.

- [ADR-0001 — Language: Python 3.11+](adr/0001-language-python.md)
- [ADR-0002 — Event-driven core with polling fallback](adr/0002-event-driven-core.md)
- [ADR-0003 — Zao log is authoritative for line health](adr/0003-zao-authority.md)
- [ADR-0004 — Strict typed JSON contract between components](adr/0004-typed-contract.md)
- [ADR-0005 — Explicit per-modem state machine](adr/0005-explicit-state-machine.md)
- [ADR-0006 — Recovery counters decay on healthy cycles](adr/0006-counter-decay.md)
- [ADR-0007 — Use CLOCK_MONOTONIC for all backoff arithmetic](adr/0007-monotonic-clock.md)

## What v1 looked like

The previous toolchain is a set of bash scripts (`diag.sh`, `recovery.sh`,
`auto_profile.sh`, `zao_reset_line.sh`, `spark-modem-watchdog.sh`) plus
a systemd unit. Its strengths and weaknesses are catalogued at the
top of [PRD.md § Background](PRD.md#background) and in
[ARCHITECTURE.md § What we are taking from v1](ARCHITECTURE.md#what-we-are-taking-from-v1).
We keep the architectural insights; we replace almost all of the
implementation.

## Document conventions

- **MUST / SHOULD / MAY** follow RFC 2119.
- Requirement IDs (`FR-1`, `NFR-3`, etc.) are stable. Do not renumber
  on edit; mark obsolete requirements `[withdrawn]` and add new ones
  at the end.
- All time durations are in seconds unless suffixed (`120s`, `5min`,
  `1h`).
- All sizes are in IEC binary units (`MiB`, `GiB`).
- Code paths are written `module/file.py:line` so they survive moves.
- Status badges at the top of each doc: **Draft** / **Reviewed** /
  **Frozen**. The first commit lands as Draft.

## Out of scope for these documents

- Vendor selection (we have hardware: Jetson Orin NX + Sierra EM7421).
- The Zao bonding stack itself (a third-party black box; we integrate
  with it but do not modify it).
- The cloud-side ingestion of telemetry (covered by a separate doc
  outside this repo).
