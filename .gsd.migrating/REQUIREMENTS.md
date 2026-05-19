# Requirements

## Active

## Validated

### R001 — System classifies each modem with state-machine v2 (post-research refactor): top-level `unknown` / `healthy` / `degraded` / `recovering(level)` / `exhausted` plus orthogonal flags `present` and `rf_blocked` (supersedes PRD FR-12

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: none yet

Legacy ID: FR-12

System classifies each modem with state-machine v2 (post-research refactor): top-level `unknown` / `healthy` / `degraded` / `recovering(level)` / `exhausted` plus orthogonal flags `present` and `rf_blocked` (supersedes PRD FR-12

### R002 — Webhook POST on `Healthy → Degraded` and `Recovering → Exhausted` transitions, with typed payload

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: none yet

Legacy ID: FR-44

Webhook POST on `Healthy → Degraded` and `Recovering → Exhausted` transitions, with typed payload

### R003 — Webhook delivery retry with bounded queue (3 attempts, exponential backoff) before drop (M-1)

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: none yet

Legacy ID: FR-44.3

Webhook delivery retry with bounded queue (3 attempts, exponential backoff) before drop (M-1)

### R004 — Webhook payload deduplication / coalescing per `(modem, transition)` with default 60 s cooldown; `dedup_count` field on next emission (M-2)

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: none yet

Legacy ID: FR-44.4

Webhook payload deduplication / coalescing per `(modem, transition)` with default 60 s cooldown; `dedup_count` field on next emission (M-2)

### R005 — Daemon-restart event with reason enum (`sigterm` / `crash` / `config_invalid` / `oom` / `kill`) (M-6)

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: none yet

Legacy ID: FR-44.5

Daemon-restart event with reason enum (`sigterm` / `crash` / `config_invalid` / `oom` / `kill`) (M-6)

### R006 — `action_failed` event variant with structured failure reason (M-15)

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: none yet

Legacy ID: FR-44.6

`action_failed` event variant with structured failure reason (M-15)

### R007 — Pre-exit best-effort webhook on schema-version refusal (M-25)

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: none yet

Legacy ID: FR-44.7

Pre-exit best-effort webhook on schema-version refusal (M-25)

### R008 — Webhook delivery runs in a separate task with explicit httpx timeouts; URL DNS pre-resolved at config-load and cached 60 s; never blocks the cycle (PITFALLS §10.1)

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: none yet

Legacy ID: FR-44.8

Webhook delivery runs in a separate task with explicit httpx timeouts; URL DNS pre-resolved at config-load and cached 60 s; never blocks the cycle (PITFALLS §10.1)

### R009 — Single `spark-modem` CLI with subcommands `diag`, `recovery`, `provision`, `reset`, `status`, `ctl`

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: none yet

Legacy ID: FR-50

Single `spark-modem` CLI with subcommands `diag`, `recovery`, `provision`, `reset`, `status`, `ctl`

### R010 — `spark-modem ctl history --modem=cdc-wdmN --since=DURATION` first-class subcommand for per-modem timeline (M-9)

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: none yet

Legacy ID: FR-50.1

`spark-modem ctl history --modem=cdc-wdmN --since=DURATION` first-class subcommand for per-modem timeline (M-9)

### R011 — `spark-modem ctl maintenance on --duration=DURATION` (max 8 h, mandatory `--duration`, auto-expiry); suppresses webhooks while observing continues (M-10; PITFALLS §16.2)

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: none yet

Legacy ID: FR-50.2

`spark-modem ctl maintenance on --duration=DURATION` (max 8 h, mandatory `--duration`, auto-expiry); suppresses webhooks while observing continues (M-10; PITFALLS §16.2)

### R012 — `--explain` flag on `diag` surfaces decision rationale (PRD UC3, RUNBOOK reference)

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: none yet

Legacy ID: FR-50.3

`--explain` flag on `diag` surfaces decision rationale (PRD UC3, RUNBOOK reference)

### R013 — CLI accepts `--qmi-fixture-dir=PATH` to read recorded `qmicli` output instead of executing

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: none yet

Legacy ID: FR-51

CLI accepts `--qmi-fixture-dir=PATH` to read recorded `qmicli` output instead of executing

### R014 — CLI accepts `--diag-fixture=PATH` for `recovery` to replay a captured snapshot

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: none yet

Legacy ID: FR-52

CLI accepts `--diag-fixture=PATH` for `recovery` to replay a captured snapshot

## Deferred

## Out of Scope
