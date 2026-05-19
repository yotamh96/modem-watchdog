# spark-modem-watchdog v2 — Architecture Decision Records

This directory holds the ADR set for v2. Each ADR documents one
architecturally-significant decision: why we made it, what falls out,
and the conditions under which we'd revisit. ADRs are append-only
history: amendments are sections appended to the original; supersession
leaves the original in place with a status change.

## Status overview

| ADR | Title | Status | Closes |
|-----|-------|--------|--------|
| [ADR-0001](0001-language-python.md) | Language: Python 3.11+ | Accepted (Amended 2026-05-06) | Q8 partially (with ADR-0010) |
| [ADR-0002](0002-event-driven-core.md) | Event-driven core | Accepted | — |
| [ADR-0003](0003-zao-authority.md) | Zao log is authoritative for line health | Accepted (Amended 2026-05-06) | Q3 |
| [ADR-0004](0004-typed-contract.md) | Strict typed JSON contract | Accepted (Amended 2026-05-06) | — |
| [ADR-0005](0005-explicit-state-machine.md) | Explicit per-modem state machine | **Superseded by ADR-0008** (2026-05-06) | — |
| [ADR-0006](0006-counter-decay.md) | Recovery counters decay on healthy cycles | Accepted (Amended 2026-05-06) | — |
| [ADR-0007](0007-monotonic-clock.md) | Monotonic clock for backoff arithmetic | Accepted | — |
| [ADR-0008](0008-state-machine-5-plus-2.md) | Per-modem state machine: 5 + 2 flags | Accepted (Supersedes ADR-0005) | — |
| [ADR-0009](0009-state-files-keyed-by-usb-path.md) | State files keyed by usb_path | Accepted | — |
| [ADR-0010](0010-packaging-python-build-standalone.md) | Packaging via python-build-standalone | Accepted | Q8 (with ADR-0001 amendment); Q6/Q7 ops notes |
| [ADR-0011](0011-webhook-subsystem.md) | Webhook subsystem (HMAC v2.0) | Accepted | Q5; Q1, Q2, Q4 (notes) |
| [ADR-0012](0012-concurrency-locks.md) | 3-layer locking model | Accepted | — |
| [ADR-0013](0013-metric-surface.md) | Integer-encoded modem_state_value | Accepted | — |
| [ADR-0014](0014-v1-retired-pivot.md) | v1-Retired Scope Pivot | Accepted | — |

## Mapping: PROJECT.md open questions to ADRs

All eight PROJECT.md open questions Q1-Q8 are closed in writing as of
Phase 1 (2026-05-06):

| Q | Topic | Closing ADR |
|---|-------|-------------|
| Q1 | HTTP API on Unix socket vs CLI-only ctl | ADR-0011 §"Q1 closure" — CLI-only for v2.0; deferred to v2.1 |
| Q2 | qmi-proxy ownership | ADR-0011 §"Q2 closure" + ADR-0003 amendment — Zao owns |
| Q3 | Minimum-supported Zao SDK version | ADR-0003 amendment — 2.1.0+ |
| Q4 | Feature parity with v1 `--watch` mode | ADR-0011 §"Q4 closure" — replaced with journalctl + Prometheus + `ctl history` |
| Q5 | HMAC v2.0 vs v2.1 | ADR-0011 — promoted to v2.0 |
| Q6 | Config-change communication | ADR-0010 §"Q6 ops note" — SIGHUP for data; restart for topology (markers in Settings; Phase 3 listener) |
| Q7 | Carrier-table ownership | ADR-0010 §"Q7 ops note" — product owns table; eng ships releases; ops adds via conf.d/ overlay |
| Q8 | Jetson Python | ADR-0001 amendment + ADR-0010 — bundle CPython 3.12 via python-build-standalone |

## Conventions

- **One file per decision.** `ADR-NNNN-short-kebab-title.md`.
- **Format.** Status block as a 4-row table; Context / Decision /
  Consequences / Risks and mitigations / Revisit when. See ADR-0001
  for the canonical template.
- **Amendments** are append-only `## Amendment YYYY-MM-DD` sections
  appended to the original file, with their own dated row in the status
  block (`| Amended | YYYY-MM-DD |`).
- **Supersession** is loud: the superseded ADR's status changes to
  `Superseded by ADR-NNNN`; the new ADR carries `Supersedes: ADR-NNNN`
  in its status block. The superseded ADR keeps its content (history)
  and gains a `## Superseded YYYY-MM-DD — see ADR-NNNN` pointer.
- **Numbering** is monotonically increasing; never reuse numbers.

## Reading order for a new contributor

1. **ADR-0001** (language choice) + **ADR-0010** (packaging) — what
   runtime lives on the box and how it is packaged.
2. **ADR-0002** (event-driven core) + **ADR-0003** (Zao authority) —
   how the daemon observes the world without racing Zao.
3. **ADR-0004** (typed contract) + **ADR-0008** (state machine) — the
   wire boundary (pydantic v2) and the per-modem state shape (5+2).
4. **ADR-0006** (counter decay) + **ADR-0007** (monotonic clock) —
   recovery semantics: how escalation ladders reset and how backoff
   is computed safely.
5. **ADR-0009** (state files keyed by usb_path) + **ADR-0012** (locks)
   — the persistence layer: where state lives on disk and how concurrent
   writers are serialized.
6. **ADR-0011** (webhook) + **ADR-0013** (metrics) — the observability
   surface: outbound alerts and Prometheus gauges.
