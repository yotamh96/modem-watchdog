---
phase: 01-foundations-adrs
plan: 07
type: execute
wave: 1
depends_on: []
files_modified:
  - docs/adr/0001-language-python.md
  - docs/adr/0003-zao-authority.md
  - docs/adr/0004-typed-contract.md
  - docs/adr/0005-explicit-state-machine.md
  - docs/adr/0006-counter-decay.md
  - docs/adr/0008-state-machine-5-plus-2.md
  - docs/adr/0009-state-files-keyed-by-usb-path.md
  - docs/adr/0010-packaging-python-build-standalone.md
  - docs/adr/0011-webhook-subsystem.md
  - docs/adr/0012-concurrency-locks.md
  - docs/adr/0013-metric-surface.md
  - docs/adr/README.md
autonomous: true
requirements: []
tags:
  - docs
  - adr

must_haves:
  truths:
    - "All eight PROJECT.md open questions Q1-Q8 are closed in writing in the ADR set"
    - "Six new ADRs (0008..0013) exist with Status: Accepted and the dates are 2026-05-06 (Phase 1)"
    - "Five existing ADRs (0001, 0003, 0004, 0005, 0006) carry research-derived amendments — each amendment has a clearly-marked '## Amendment YYYY-MM-DD' section appended to the original ADR"
    - "ADR-0005 has Status: Superseded by ADR-0008; ADR-0008 carries Supersedes: ADR-0005"
    - "Every new ADR cross-references the source(s) it derives from in .planning/research/ and the requirement IDs (FR-/NFR-) it closes"
    - "docs/adr/README.md exists with a status table listing all 13 ADRs (0001-0013), their status, and a 1-line summary"
  artifacts:
    - path: "docs/adr/0001-language-python.md"
      provides: "ADR-0001 amended: bundle CPython 3.12 via python-build-standalone (closes Q8)"
      contains: "## Amendment 2026-05-06"
    - path: "docs/adr/0003-zao-authority.md"
      provides: "ADR-0003 amended: parser surface bound to RASCOW_STAT only"
      contains: "## Amendment 2026-05-06"
    - path: "docs/adr/0004-typed-contract.md"
      provides: "ADR-0004 amended: schema downgrade non-destructive"
      contains: "## Amendment 2026-05-06"
    - path: "docs/adr/0005-explicit-state-machine.md"
      provides: "ADR-0005 marked Superseded by ADR-0008"
      contains: "Status: Superseded by ADR-0008"
    - path: "docs/adr/0006-counter-decay.md"
      provides: "ADR-0006 amended: streak persistence + atomic single-write per cycle"
      contains: "## Amendment 2026-05-06"
    - path: "docs/adr/0008-state-machine-5-plus-2.md"
      provides: "ADR-0008 (new): 5 top-level + 2 orthogonal flags state machine; supersedes ADR-0005"
      contains: "Supersedes: ADR-0005"
    - path: "docs/adr/0009-state-files-keyed-by-usb-path.md"
      provides: "ADR-0009 (new): state files keyed by usb_path with startup cross-check"
      contains: "state/by-usb"
    - path: "docs/adr/0010-packaging-python-build-standalone.md"
      provides: "ADR-0010 (new): packaging via PBS + uv + custom debhelper rule (closes Q8)"
      contains: "python-build-standalone"
    - path: "docs/adr/0011-webhook-subsystem.md"
      provides: "ADR-0011 (new): HMAC-SHA256 v2.0 + retry/dedup queue + pre-resolved DNS (closes Q5)"
      contains: "HMAC"
    - path: "docs/adr/0012-concurrency-locks.md"
      provides: "ADR-0012 (new): per-modem asyncio.Lock + globals lock + per-modem flock + state-store flock; PID lock separate"
      contains: "per-modem"
    - path: "docs/adr/0013-metric-surface.md"
      provides: "ADR-0013 (new): integer-encoded modem_state_value{modem} replaces one-hot state label"
      contains: "modem_state_value"
    - path: "docs/adr/README.md"
      provides: "Status table for all 13 ADRs"
      contains: "ADR-0001"
  key_links:
    - from: "docs/adr/0008-state-machine-5-plus-2.md Supersedes"
      to: "docs/adr/0005-explicit-state-machine.md"
      via: "Supersedes header + reciprocal Status: Superseded by"
      pattern: "Supersedes: ADR-0005|Superseded by ADR-0008"
    - from: "docs/adr/0009-state-files-keyed-by-usb-path.md"
      to: "src/spark_modem/state_store/inventory.py"
      via: "implementation reference (Plan 04)"
      pattern: "state/by-usb"
    - from: "docs/adr/0010-packaging-python-build-standalone.md"
      to: "debian/rules and packaging/requirements.lock"
      via: "implementation reference (Plan 02)"
      pattern: "debian/rules"
    - from: "docs/adr/0013-metric-surface.md"
      to: "src/spark_modem/wire/state.py state_to_int"
      via: "implementation reference (Plan 03)"
      pattern: "state_to_int|modem_state_value"
---

<objective>
Land the ADR set that closes all eight PROJECT.md open questions Q1–Q8 in writing. Six new ADRs (0008–0013) document decisions the research SUMMARY raised and Plans 02–06 implemented; five existing ADRs (0001, 0003, 0004, 0005, 0006) get formal amendments capturing the research-derived deltas. ADR-0005 is marked superseded by ADR-0008 (the 5+2 state shape replaces the 7-state shape).

Purpose: Closes Phase 1 SC #2 (all eight PROJECT.md open questions Q1-Q8 are closed in writing; six new ADRs merged; ADRs 0001/0003/0004/0005/0006 carry the research-derived amendments). This plan ships ZERO code — every implementation already lands in Plans 02–06; this plan provides the *decision record* so a reader six months later can answer "why does the daemon bundle Python via PBS?" or "why is `state` not a one-hot Prom label?" without re-reading the research.

Output: 11 markdown files in `docs/adr/` (5 amended + 6 new) plus a `docs/adr/README.md` index. Total: ~2000-2500 lines of documentation. Style matches existing ADR-0001..0007 (the four-column status block, Context / Decision / Consequences / Risks / Revisit).

This plan is parallelizable with Plan 01 (both Wave 1; both touch disjoint files — `docs/adr/` vs repo scaffolding). It does NOT depend on any code: the implementation that backs each ADR lands in Plans 02–06, but the ADR text describes the *decision*, not the code. ADRs document why; Plans 02–06 document how.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/01-foundations-adrs/01-CONTEXT.md
@.planning/research/SUMMARY.md
@.planning/research/STACK.md
@.planning/research/ARCHITECTURE.md
@.planning/research/PITFALLS.md
@.planning/research/FEATURES.md
@docs/adr/0001-language-python.md
@docs/adr/0002-event-driven-core.md
@docs/adr/0003-zao-authority.md
@docs/adr/0004-typed-contract.md
@docs/adr/0005-explicit-state-machine.md
@docs/adr/0006-counter-decay.md
@docs/adr/0007-monotonic-clock.md
@CLAUDE.md

<interfaces>
<!-- This plan ships ONLY .md docs. The pre-existing ADR template format: -->

Existing ADR shape (e.g. ADR-0001):
```
# ADR-NNNN — Short title

| Field        | Value          |
| ------------ | -------------- |
| Status       | Accepted | Proposed | Superseded by ADR-XXXX |
| Date         | YYYY-MM-DD     |
| Deciders     | Eng team       |
| Supersedes   | (optional)     |

## Context
... why this decision is being made

## Decision
... what we're doing

## Consequences
... what falls out

## Risks and mitigations
... table

## Revisit when
... the trigger conditions to re-open the decision
```

Six new ADRs (matrix from CONTEXT.md):
| ADR | Topic | Source |
|-----|-------|--------|
| 0008 | 5 top-level + 2 orthogonal flags | FEATURES §4.1 |
| 0009 | State files keyed by usb_path | ARCH Q14, PITFALLS §3.1 |
| 0010 | Packaging via PBS + uv + custom debhelper | STACK §"Packaging recipe" |
| 0011 | Webhook subsystem (HMAC v2.0 + retry/dedup + pre-resolved DNS) | FEATURES §4.3, M-1..M-4; PITFALLS §10.1 |
| 0012 | Concurrency locks (per-modem asyncio.Lock + globals lock; per-modem flock + state-store flock; PID lock separate) | ARCH Q3, PITFALLS §3.2/§16.1, FEATURES M-21 |
| 0013 | Metric surface (integer-encoded modem_state_value{modem}) | PITFALLS §13.1/§9.4 |

Five amendments (matrix from CONTEXT.md):
| ADR | Amendment |
|-----|-----------|
| 0001 | Bundle CPython 3.12 via python-build-standalone. Closes Q8. |
| 0003 | Parser surface bound to RASCOW_STAT; other lines accepted-but-ignored with counter; growing parsed surface is a schema-version bump. |
| 0004 | Schema downgrade is non-destructive — shadow as .from-v<N>.json, log schema_downgrade_pending; reset only on explicit ctl reset-state. |
| 0005 | Status: Superseded by ADR-0008 |
| 0006 | Streak update + decay + counter reset + state-write are ONE atomic write per cycle; streak persists across daemon restarts; replay test must include mid-streak restart. |

Mapping from open questions (PROJECT.md Q1–Q8) to closing ADRs:

| Q | Topic | ADR closing it |
|---|-------|----------------|
| Q1 | HTTP API on Unix socket vs CLI-only ctl | ADR-0011 (CLI-only for v2.0; deferred to v2.1) — addressed in §"Decision" |
| Q2 | Daemon owns qmi-proxy or assumes Zao does | ADR-0011 + ADR-0010 (Zao owns; daemon refuses to start in qmicli-direct mode if proxy unavailable) — actually: this is partly Plan 11 / Phase 2; in Phase 1 we lock the *contract* via ADR-0011 §"Out of scope" + ADR-0003 amendment. Document explicitly. |
| Q3 | Minimum-supported Zao SDK version | ADR-0003 amendment (2.1.0 confirmed) |
| Q4 | Feature parity with v1 --watch mode | Closed in ROADMAP/REQUIREMENTS as "replace with journalctl + Prometheus + ctl history (M-9)"; ADR-0011 §"Out of scope" notes the deferral. We don't need a separate ADR for Q4. Document in ADR-0011's Out-of-scope section. |
| Q5 | HMAC in v2.0 or v2.1 | ADR-0011 (v2.0; promoted from v2.1) |
| Q6 | Config-change communication | Implicitly addressed in Plan 06 Settings reload markers; mention in ADR-0010 §"Consequences" so the trail exists. |
| Q7 | Carrier-table ownership | ADR-0011 §"Operational ownership" — actually best fit: not an ADR-0011 topic. Document in PROJECT.md Key Decisions table; Q7 is product-org, not engineering. Out-of-scope for code ADRs; ADR-0010 mentions the day-one shipped table. |
| Q8 | Jetson Python | ADR-0001 amendment + ADR-0010 (closes; bundle CPython 3.12 via PBS) |

Q4 and Q7 don't need their own new ADRs (one is a feature deferral, the other is product ownership). Document them in ADR-0011 (Q4) and ADR-0010 (Q7 ops note); the PROJECT.md Key Decisions table reflects the closure. The other 6 questions get explicit ADR coverage.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Amend the five existing ADRs (0001, 0003, 0004, 0005, 0006)</name>
  <files>docs/adr/0001-language-python.md, docs/adr/0003-zao-authority.md, docs/adr/0004-typed-contract.md, docs/adr/0005-explicit-state-machine.md, docs/adr/0006-counter-decay.md</files>
  <read_first>
    - docs/adr/0001-language-python.md (the original — read fully so the amendment slots cleanly)
    - docs/adr/0003-zao-authority.md (the original)
    - docs/adr/0004-typed-contract.md (the original)
    - docs/adr/0005-explicit-state-machine.md (the original — being superseded)
    - docs/adr/0006-counter-decay.md (the original)
    - .planning/research/SUMMARY.md §"9.3 Phase 0 ADR amendments" (the prescribed amendment text)
    - .planning/phases/01-foundations-adrs/01-CONTEXT.md §"ADRs to AMEND in Phase 1" (the canonical amendment list)
  </read_first>
  <action>
    For each of the five ADRs, **append** an `## Amendment 2026-05-06` section at the bottom of the existing file (before any "Revisit when" section if present, or at the very end if not — keep "Revisit when" last). Do NOT rewrite the original Context / Decision / Consequences sections; the amendment is additive history.

    Also update each amended ADR's status-block table:
      - ADR-0001: Status stays "Accepted"; add `Amended: 2026-05-06` row.
      - ADR-0003: Status stays "Accepted"; add `Amended: 2026-05-06` row.
      - ADR-0004: Status stays "Accepted"; add `Amended: 2026-05-06` row.
      - ADR-0005: change Status to `Superseded by ADR-0008`; add `Superseded: 2026-05-06` row.
      - ADR-0006: Status stays "Accepted"; add `Amended: 2026-05-06` row.

    **ADR-0001 amendment** — add at end of file (before "Revisit when"):
    ```markdown
    ## Amendment 2026-05-06

    **Closes PROJECT.md Q8** (Jetson Python). The original "Decision"
    section said "Python 3.11+, packaged as a Debian `.deb` containing a
    self-contained venv at /opt/spark-modem-watchdog/" but did not commit
    to a sourcing tactic. Research (`.planning/research/STACK.md` §2)
    closed the question: **bundle CPython 3.12 via
    `astral-sh/python-build-standalone`**.

    Rationale (full reasoning in `.planning/research/STACK.md`):

    - Jetson system Python is 3.8.10 (L4T R35.6.4 / Ubuntu 20.04). Pydantic
      v2.11+ requires Python ≥3.9; deadsnakes does not publish 3.11+ for
      Ubuntu 20.04 ("focal"). Patching the box's system Python is operationally
      hostile (Zao's runtime depends on it).
    - python-build-standalone publishes glibc-2.17-baselined CPython for
      `aarch64-unknown-linux-gnu`; Ubuntu 20.04 ships glibc 2.31 — comfortable
      margin. Tarball is ~30 MiB; `.deb` size ceiling 40 MiB (NFR-51) accommodates.
    - Python 3.13 deferred (free-threaded transition risk + thinner aarch64
      wheel ecosystem). 3.14 too new (beta).

    The full packaging recipe (PBS + `uv pip compile` for lockfile + custom
    debhelper rule replacing `dh-virtualenv`) is documented separately in
    **ADR-0010**.

    Status row: `Amended: 2026-05-06`.
    ```

    **ADR-0003 amendment** — add at end:
    ```markdown
    ## Amendment 2026-05-06

    **Closes PROJECT.md Q3** (minimum Zao SDK). Confirmed: Zao SDK 2.1.0+;
    pre-2.1.0 is unsupported (Zao log format `RASCOW_STAT` not stable).
    Phase 5 (Bench & Field Shadow) captures every box's `(EM7421 firmware,
    Zao SDK, libqmi)` triple as fixtures; any box outside the known set is
    upgraded before Phase 6 cutover.

    **Bound parser surface.** The Zao log tailer parses ONLY the
    `RASCOW_STAT` line; all other lines are accepted-but-ignored and
    counted via a `zao_log_unparsed_lines_total` metric. Growing the
    parsed surface (e.g. accepting a new Zao log line type) is a
    schema-version bump for the Zao log tailer subsystem. Rationale:
    Zao SDK changes are not on our control plane; pinning the parsed
    surface and surfacing every other line as opaque-but-counted means
    a Zao SDK upgrade that adds new log lines doesn't silently break us
    (and the metric tells us when we should consider expanding the parser).

    Source: `.planning/research/PITFALLS.md` §2.x (Zao SDK churn).

    Status row: `Amended: 2026-05-06`.
    ```

    **ADR-0004 amendment** — add at end:
    ```markdown
    ## Amendment 2026-05-06

    **Closes new question (CONTEXT.md S-03 / SUMMARY §8 item 14):
    schema-downgrade behavior.**

    The original "Decision" required "Lower versions require explicit
    migration code; without it, refuse." Research (`.planning/research/
    PITFALLS.md` §3.4) refined this:

    **Schema downgrade is non-destructive.** When the daemon boots and
    finds a state file with `schema_version < CURRENT_SCHEMA_VERSION`:

    1. Rename the old file to `<original>.from-v<N>.json` (a sibling in the
       same directory).
    2. Write a fresh-default state file at `CURRENT_SCHEMA_VERSION`.
    3. Emit a structured `schema_downgrade_pending` event (typed; see
       `spark_modem.wire.events.SchemaDowngradePending`).
    4. The shadow file is preserved verbatim until the operator runs
       `spark-modem ctl migrate-state` (Phase 2) or `ctl reset-state --all`.

    Forward versions (file's `schema_version > CURRENT_SCHEMA_VERSION`) still
    refuse: the daemon raises `SchemaVersionTooNew` and exits non-zero (the
    `apt downgrade` failure path is loud rather than data-destroying).

    Implementation reference: `src/spark_modem/wire/versioning.py`
    (Plan 03), `src/spark_modem/state_store/store.py` (Plan 04),
    `tests/unit/state_store/test_schema_downgrade.py` (Plan 04).

    Status row: `Amended: 2026-05-06`.
    ```

    **ADR-0005 update** — change status row to `Superseded by ADR-0008`, add `Superseded: 2026-05-06`, and append:
    ```markdown
    ## Superseded 2026-05-06 — see ADR-0008

    Research (`.planning/research/FEATURES.md` §4.1) found the 7-state
    shape redundant: `disconnected` is a guard rather than a state, and
    `rf_blocked` is partly orthogonal (cheap actions still run while it's
    set; worked example RECOVERY_SPEC.md §10.2 transitions
    `recovering(modem) → rf_blocked → recovering(usb)` show that
    `recovering` did not actually disappear when `rf_blocked` was set).

    **ADR-0008** replaces this with **5 top-level states + 2 orthogonal
    flags**:

    - states: `unknown` / `healthy` / `degraded` / `recovering(level)` / `exhausted`
    - flags: `present: bool`, `rf_blocked: bool`

    The functions `transition()` and `decide_action()` from this ADR
    survive in spirit; their signatures shift to consume the new shape.
    See ADR-0008 for the full new shape and `src/spark_modem/wire/state.py`
    (Plan 03) for the implementation. The original 7-state diagram in
    RECOVERY_SPEC.md §3 was updated in Phase 1 (the diagram now reflects
    5+2 — `RECOVERY_SPEC.md` is amended in the same PR as ADR-0008).
    ```

    **ADR-0006 amendment** — add at end:
    ```markdown
    ## Amendment 2026-05-06

    **Pinned cycle ordering + streak persistence (closes PITFALLS §9.1, §9.2).**

    Research surfaced two failure modes the original ADR did not address:

    1. **Daemon-restart silently resets `_healthy_streak`** (PITFALLS §9.2).
       The original "Decision" describes the mechanism but does not say the
       streak is durable. v1's regression risk: a streak that's lost on
       every daemon restart re-introduces the v1 permanent-Exhausted
       failure mode this ADR was written to fix.

    2. **`_healthy_streak` persistence vs decay race** (PITFALLS §9.1):
       a crash mid-cycle between "streak += 1" and "counters reset" leaves
       the on-disk file inconsistent.

    **Refined rule (atomic single-write per cycle):**

    Per cycle, the per-modem state-write pipeline is:

    ```
    streak update → decay check → counter reset (if streak == K) →
    state-write (one atomic temp+rename+dir-fsync)
    ```

    All four happen as ONE atomic write per cycle. `_healthy_streak` is
    persisted in the per-modem state file every cycle and reloaded on
    daemon start; mid-streak restart does NOT reset progress.

    Replay test contract (Phase 2): the policy-engine replay harness
    includes a daemon-restart-mid-streak case that proves K consecutive
    Healthy cycles correctly resume after restart and decay counters to
    zero on cycle K post-restart, not on cycle K post-most-recent-boot.

    Implementation reference: `src/spark_modem/wire/state.py`
    (`_healthy_streak` field with alias on ModemState, Plan 03);
    `src/spark_modem/state_store/store.py` (atomic save, Plan 04);
    Phase 2 cycle driver wires the actual streak increment/decay logic.

    See ADR-0009 (state files keyed by usb_path) and ADR-0012 (atomic
    write + locking) for the persistence and concurrency context.

    Status row: `Amended: 2026-05-06`.
    ```
  </action>
  <verify>
    <automated>
      cd S:/spark/modem-watchdog && \
      grep -q '## Amendment 2026-05-06' docs/adr/0001-language-python.md && \
      grep -q 'python-build-standalone' docs/adr/0001-language-python.md && \
      grep -q '## Amendment 2026-05-06' docs/adr/0003-zao-authority.md && \
      grep -q 'RASCOW_STAT' docs/adr/0003-zao-authority.md && \
      grep -q 'Zao SDK 2\.1\.0' docs/adr/0003-zao-authority.md && \
      grep -q '## Amendment 2026-05-06' docs/adr/0004-typed-contract.md && \
      grep -q 'from-v' docs/adr/0004-typed-contract.md && \
      grep -q 'schema_downgrade_pending' docs/adr/0004-typed-contract.md && \
      grep -q 'Superseded by ADR-0008' docs/adr/0005-explicit-state-machine.md && \
      grep -q '## Superseded 2026-05-06' docs/adr/0005-explicit-state-machine.md && \
      grep -q '## Amendment 2026-05-06' docs/adr/0006-counter-decay.md && \
      grep -q 'one atomic write per cycle\|ONE atomic write per cycle' docs/adr/0006-counter-decay.md && \
      grep -q 'streak persists across daemon restarts\|persisted .* every cycle' docs/adr/0006-counter-decay.md && \
      echo "Task 1 verification: all 5 amendments present"
    </automated>
  </verify>
  <done>
    All five existing ADRs carry the amendment section. ADR-0005 is marked Superseded by ADR-0008. Each amendment is dated 2026-05-06, references its research source, and notes the implementation plan (02–06). The original ADR text (Context / Decision / Consequences) is unchanged; amendments append cleanly.
  </done>
</task>

<task type="auto">
  <name>Task 2: Author the six new ADRs (0008..0013)</name>
  <files>docs/adr/0008-state-machine-5-plus-2.md, docs/adr/0009-state-files-keyed-by-usb-path.md, docs/adr/0010-packaging-python-build-standalone.md, docs/adr/0011-webhook-subsystem.md, docs/adr/0012-concurrency-locks.md, docs/adr/0013-metric-surface.md</files>
  <read_first>
    - docs/adr/0001-language-python.md (style template — Context / Decision / Consequences / Risks / Revisit)
    - docs/adr/0007-monotonic-clock.md (style template; closer in spirit to several of the new ADRs)
    - .planning/research/SUMMARY.md (TL;DR; §3 features; §4 architecture; §5 pitfalls)
    - .planning/research/STACK.md §"Packaging recipe" (5 steps; for ADR-0010)
    - .planning/research/FEATURES.md §4.1 (5+2 state shape, ADR-0008), §4.3 (HMAC v2.0, ADR-0011)
    - .planning/research/ARCHITECTURE.md Q3 (per-modem locks, ADR-0012), Q9 (Prom over UDS, supports ADR-0013), Q14 (state files keyed by usb_path, ADR-0009)
    - .planning/research/PITFALLS.md §3.1 (cdc-wdmN renumbering, ADR-0009), §3.2 + §16.1 (concurrent writers, ADR-0012), §10.1 (DNS blocking, ADR-0011), §13.1 (cardinality, ADR-0013)
    - .planning/phases/01-foundations-adrs/01-CONTEXT.md (CONTEXT.md decisions tying back to each ADR)
  </read_first>
  <action>
    Write each ADR following the established 7-section format. Each file is ~150-300 lines. The exact content for each:

    **`docs/adr/0008-state-machine-5-plus-2.md`** — 5 top-level + 2 orthogonal flags state machine:

    Status block: Status: Accepted; Date: 2026-05-06; Deciders: Eng team; Supersedes: ADR-0005.

    Sections:
    - **Context**: Reference ADR-0005's 7-state shape. Quote `.planning/research/FEATURES.md` §4.1: `disconnected` is a guard, not a state; `rf_blocked` is partly orthogonal (cheap actions still run while set). Worked example RECOVERY_SPEC.md §10.2 shows `recovering(modem) → rf_blocked → recovering(usb)` — `recovering` didn't disappear; the line was momentarily set on the orthogonal axis.
    - **Decision**: Define the 5+2 shape literally:
      - `state: Literal['unknown', 'healthy', 'degraded', 'recovering', 'exhausted']`
      - `recovering_level: int | None`  (None unless state == 'recovering')
      - `present: bool`  (orthogonal flag #1: is the modem on the USB bus right now?)
      - `rf_blocked: bool`  (orthogonal flag #2: is RF below the signal-quality gate?)
      Status output (`status.json`) composes them into a human-readable shape; the policy engine matches on `state` directly via `match` (CLAUDE.md anti-pattern: never `if/elif` on ModemState).
    - **Consequences**:
      - SCHEMA.md §3 was reshaped (the SCHEMA edit lands in this PR or a follow-up; ADR-0008 is the source of truth).
      - status.json composes the 5+2 into the v1-style shape for compatibility with the existing NOC dashboards (cycle-driver responsibility, Phase 2).
      - Webhook payloads carry `prior_state` / `new_state` as 5+2-shaped strings.
      - The `transition()` function from ADR-0005 still exists; its return type shifts to the new shape.
      - Cheap actions (set_apn, fix_raw_ip, sim_power_on, soft_reset) still run while `rf_blocked=True`; only `modem_reset` and `usb_reset` honor the gate.
    - **Risks and mitigations** (table):
      - Adding a 6th state slips into the codebase — match-statement exhaustiveness check forces the issue at compile time.
      - status.json composes the wrong human-readable shape — Phase 2 has spec-as-tests for status.json composition.
      - `rf_blocked` flag composition with `state=recovering` produces ambiguous policy decisions — explicit precedence: the orthogonal flag is informational; the policy engine reads `state` first.
    - **Why not 7 states** (link back to ADR-0005's superseded reasoning).
    - **Revisit when**: real fleet data shows a state we should split (e.g. `recovering(usb)` deserves its own top-level state), or rf_blocked needs to be promoted to a state.
    - **Implementation reference**: `src/spark_modem/wire/state.py` (Plan 03 W-04); `src/spark_modem/wire/state.py state_to_int` for the integer encoding consumed by ADR-0013.

    ---

    **`docs/adr/0009-state-files-keyed-by-usb-path.md`** — state files keyed by usb_path with startup cross-check:

    Status: Accepted; Date: 2026-05-06; Deciders: Eng team.

    Sections:
    - **Context**: PITFALLS §3.1: kernel cdc-wdm enumeration order varies across boots (USB hub re-enumeration, suspend-resume, hot-plug). v1 keyed state files by `cdc-wdm0..3`; on USB renumbering, the files attached to the wrong physical modem. ARCHITECTURE Q14 reached the same conclusion: `usb_path` (sysfs `2-3.1.1`) is stable across renumbering because it reflects topology, not enumeration order.
    - **Decision**: Per-modem state files persist at `/var/lib/spark-modem-watchdog/state/by-usb/<usb_path>.json`. Identity map (ICCID/IMSI ↔ modem) is the same — keyed by usb_path. On startup, the daemon walks `/sys/bus/usb/devices/` to discover the current `(usb_path → cdc_wdm)` map; for each persisted state file, it cross-checks the file's `usb_path` against sysfs. On mismatch, the daemon **refuses to start** with a typed `UsbPathMismatch` event + `sd_notify STATUS=usb_path_mismatch` + non-zero exit. Recovery: operator runs `spark-modem ctl reset-state --modem=<usb_path>` (or `--all`).
    - **Consequences**:
      - Hot-plug of a modem mid-flight is supported via udev events (Phase 3 wires `pyudev.Monitor`); a hot-plugged modem with a known ICCID re-uses its existing state file.
      - SIM swap (ICCID changes at the same usb_path) is detected by comparing the live ICCID against the persisted Identity (Phase 3 FR-4).
      - The `state/by-usb/` directory is the single source of truth; `cdc-wdmN` is a runtime detail.
      - `*.from-v<N>.json` shadow files are siblings in `state/by-usb/`; the inventory walker excludes them via filename suffix check.
    - **Risks and mitigations**:
      - Two boxes with the same physical USB topology have collidable usb_path strings — they're already isolated by box (the daemon runs per-box; no cross-box sharing).
      - Replacing a hub mid-flight changes usb_paths globally — this is a topology change, not a renumbering; the operator is expected to `ctl reset-state --all` after hardware reconfiguration.
      - usb_path strings can contain `/` if sysfs nests deeper — paths.py rejects `/` and `..` in usb_path; Identity.usb_path regex is `^\d+(-\d+(\.\d+)*)?$`.
    - **Implementation reference**: `src/spark_modem/state_store/paths.py` (Plan 04), `src/spark_modem/state_store/inventory.py` (Plan 04), `tests/unit/state_store/test_inventory_crosscheck.py` (Plan 04 — hypothesis property test for SC #5).
    - **Revisit when**: USB topology becomes itself unstable (e.g. fleet rolls out a different USB-hub model); OR a Zao SDK upgrade exposes a stable per-modem identifier above the kernel.

    ---

    **`docs/adr/0010-packaging-python-build-standalone.md`** — packaging via PBS + uv + custom debhelper:

    Status: Accepted; Date: 2026-05-06; Deciders: Eng team. Closes Q8 (with ADR-0001 amendment).

    Sections:
    - **Context**: ADR-0001 said "ship the runtime we tested with"; this ADR fills in the *how*. STACK.md §2 lays out the constraints: Jetson Python is 3.8.10 (frozen); pydantic v2 needs ≥3.9; deadsnakes doesn't ship 3.11+ for focal; `dh-virtualenv` assumes a system Python we deliberately won't reuse. The packaging path must be reproducible (NFR-43, NFR-52), self-contained (NFR-50; no apt deps on python3-*), and ≤40 MiB (NFR-51).
    - **Decision**: Use `astral-sh/python-build-standalone` to fetch a relocatable CPython 3.12.x tarball at build time; install runtime libs via `uv pip install --frozen --no-deps -r packaging/requirements.lock`; package via custom `debian/rules` (NOT `dh-virtualenv`). The recipe is the canonical 5-step sequence from STACK.md §"Packaging recipe":

    ```
    1. Download pinned PBS tarball; SHA256 in debian/python.sha256; verify before unpack.
    2. Unpack to debian/<pkg>/opt/spark-modem-watchdog/python/ (the FINAL install path).
    3. uv pip install --frozen --no-deps -r packaging/requirements.lock into the bundled python.
    4. python -m compileall under SOURCE_DATE_EPOCH (NFR-13 warm cache; NFR-43 reproducibility).
    5. Install systemd unit + default carrier-table YAML + libexec scripts; postinst smoke-tests all 9 (10 with pydantic-settings) imports under the bundled python.
    ```

    Versioning: `2.0.0-1` (release) and `2.0.0-0.git<short-sha>-1` (dev) are visibly distinct. `SOURCE_DATE_EPOCH` from the most-recent git commit ts.

    - **Consequences**:
      - .deb size: ~30-35 MiB (NFR-51 ceiling 40 MiB).
      - Security update story: rebuild the .deb on every CPython security release (4-6× per year on stable branches). Carrier-table edits are config-only and don't require a rebuild.
      - PITFALLS §18.3 (venv path relocation): the venv is installed AT the final `/opt/spark-modem-watchdog/python/` path during build; `compileall` runs under the destination layout so .pyc files don't bake builder paths. `debian/rules` asserts `python3.12 -c "assert sys.executable == '/opt/...'"` post-install.
      - PITFALLS §18.5 (certifi rotation): a stale .deb ships a stale certifi bundle, which eventually breaks TLS to webhook endpoints. Mitigation is operational (rebuild policy).
      - **Q6 ops note**: configuration precedence (CLI > env > YAML > defaults) is implemented in `src/spark_modem/config/Settings` (Plan 06). SIGHUP transactional reload for data-only fields lands in Phase 3; topology-affecting fields (state_root, run_dir, metrics_socket_path) are tagged `RELOAD_RESTART` so the SIGHUP reload refuses to apply them mid-flight.
      - **Q7 ops note**: the carrier-table is shipped at `debian/conf.d/00-carriers.yaml` (12 entries day-one; IL verified, US/UK/DE unverified). Ownership: product owns the table contents; engineering ships it via `.deb`. Ops adds new MCC/MNC entries via `/etc/spark-modem-watchdog/conf.d/*.yaml` overlay (FR-33) and a SIGHUP reload.
    - **Risks and mitigations**:
      - PBS upstream stops publishing 3.12 builds — pin a known-good release; pre-download to fleet artifact storage if the GitHub source ever becomes unavailable.
      - glibc compatibility regression — PBS's glibc 2.17 baseline is below Ubuntu 20.04's 2.31; the margin is generous. CI builds on aarch64 (Plan 02) catch this.
      - Build-time download flakes — `debian/rules` caches the PBS tarball locally; subsequent rebuilds reuse the cached tarball if the SHA matches. (`--cache-dir` semantics in CI runner.)
    - **Revisit when**: CPython 3.13's free-threaded story stabilizes and we want concurrent GIL-free execution; OR Sierra publishes a Linux ABI shift that requires a newer glibc; OR Jetpack ships a system Python ≥3.12 (then we revisit "do we still bundle?").
    - **Implementation reference**: `debian/rules`, `debian/python.sha256`, `debian/spark-modem-watchdog.postinst`, `scripts/postinst_smoke_test.sh`, `scripts/build_deb.sh`, `.github/workflows/build-deb.yml` — all from Plan 02. `packaging/requirements.in` and `packaging/requirements.lock` from Plan 01 (regenerated to add `pydantic-settings` in Plan 06).

    ---

    **`docs/adr/0011-webhook-subsystem.md`** — HMAC-SHA256 v2.0 + retry/dedup + pre-resolved DNS:

    Status: Accepted; Date: 2026-05-06; Deciders: Eng team. Closes Q5 (HMAC promoted from v2.1 to v2.0).

    Sections:
    - **Context**: PRD Q5 originally deferred HMAC to v2.1. Research (`.planning/research/FEATURES.md` §4.3) found receivers increasingly require signatures; the cost is ~30 LOC + one config field; signed-by-default is strictly more compatible than unsigned. Closely related: PITFALLS §10.1 — DNS resolution blocking the asyncio event loop on broken/slow LTE-tunneled DNS. The webhook subsystem is a single concern with ~7 prescriptions converging.
    - **Decision**: The v2.0 webhook subsystem implements:
      1. **HMAC-SHA256 signing** (FR-44.1). Header `X-Spark-Signature: sha256=<hex>` over the **raw body bytes** (not the JSON-decoded structure — avoids whitespace ambiguity on the receiver). Secret from systemd `LoadCredential=` (NFR-34); never on disk.
      2. **Replay-protection timestamp** (FR-44.2; M-4). Header `X-Spark-Timestamp: <unix>` on every request; receivers reject windows >5 min old.
      3. **Retry queue with bounded budget** (FR-44.3; M-1). 3 attempts with exponential backoff; drop after the third. Queue depth bounded.
      4. **Per-(modem, transition) dedup** (FR-44.4; M-2). Default 60s coalescing window; emits a single payload with `dedup_count: int` for the next-window emission.
      5. **Daemon-restart event** (FR-44.5; M-6). Reason enum (`sigterm` / `crash` / `config_invalid` / `oom` / `kill`).
      6. **action_failed variant** (FR-44.6; M-15). Failure reason as structured field.
      7. **Pre-exit best-effort send** (FR-44.7; M-25) on schema-version refusal.
      8. **Pre-resolved cached DNS** (FR-44.8; PITFALLS §10.1). At config-load time, resolve the webhook URL's hostname; cache 60s. Webhook delivery never blocks on DNS.
      9. **Separate task** for delivery (FR-44.8). Cycle never blocks on webhook I/O. httpx with explicit timeouts; no urllib.request.
    - **Consequences**:
      - HMAC adds ~30 LOC + a `webhook_hmac_secret` config (loaded via `LoadCredential=`).
      - Webhook URL must be `https://` unless `webhook_allow_http=true` (NFR-33; Settings field validator in Plan 06).
      - Phase 1 (this plan) ships the wire shapes (`spark_modem.wire.WebhookEnvelope`, `WebhookPayload` union, `WebhookEventKind` enum). Phase 2 ships the `WebhookPoster` Protocol + concrete implementation.
      - **Q1 closure**: HTTP API on Unix socket vs CLI-only ctl — **CLI-only for v2.0; deferred to v2.1.** Daemon never accepts inbound IPC in v2.0 (preserves the discipline; minimizes attack surface).
      - **Q2 closure**: daemon owns qmi-proxy or assumes Zao does — **Zao owns; daemon refuses to start in qmicli-direct mode if proxy is unavailable** (FR-74). The relevant ADR is partly ADR-0003; this ADR mentions Q2 because the webhook subsystem is observability for "qmi-proxy down" events.
      - **Q4 closure**: feature parity with v1 `--watch` mode — **replace with `journalctl -fu` + Prometheus + `ctl history` (M-9).** No ADR-specific mandate; documented as deferred-by-replacement.
    - **Risks and mitigations**:
      - HMAC secret rotation — operator updates `LoadCredential=` source and SIGHUPs the daemon (Phase 3 wires this).
      - DNS cache stale during long-running DNS migration — 60s TTL bounded; restart resolves.
      - Receiver clock skew on `X-Spark-Timestamp` — ±5 min window is loose enough; document for receivers.
      - Dedup window misuse: a flapping modem's transitions get coalesced silently — `dedup_count: int` field on the emitted payload surfaces the count.
    - **Revisit when**: receivers need batching (M-3 — webhook batching is deferred to v2.1); receivers want a different signature algorithm; or a fleet-API endpoint replaces webhook (separate from this ADR).
    - **Implementation reference**: `src/spark_modem/wire/webhook.py` (Plan 03 — wire shapes only); `src/spark_modem/config/settings.py webhook_*` fields (Plan 06); Phase 2 ships the WebhookPoster.

    ---

    **`docs/adr/0012-concurrency-locks.md`** — 3-layer locking model:

    Status: Accepted; Date: 2026-05-06; Deciders: Eng team.

    Sections:
    - **Context**: ARCH Q3 + PITFALLS §3.2/§16.1 + FEATURES M-21. Three independent failure modes converge on the same set of locks:
      - In-process: cycle driver and reload listener both write state for the same modem; without serialization the writes interleave (Q3).
      - Cross-process: daemon and `ctl reset-state` mutate the same files (PITFALLS §3.2/§16.1; M-21).
      - PID exclusivity: only one daemon process per box (FR-61).
    - **Decision**: The 3-layer locking model:

      **Layer 1 (in-process, asyncio):**
      - Per-modem `asyncio.Lock`, lazily populated as a `dict[usb_path, Lock]`. ~10 LOC.
      - Globals lock: a single `asyncio.Lock` for `globals.json` and `identity.json`.
      - Single-key APIs only: never compose locks (no "acquire usb_path A AND usb_path B"; deadlocks via lock ordering).

      **Layer 2 (cross-process, advisory flocks):**
      - Per-modem flock at `/run/spark-modem-watchdog/modem-<usb_path>.lock`.
      - State-store flock at `/run/spark-modem-watchdog/state.lock`.
      - CLI mutating commands take the same flocks the daemon does (CLAUDE.md invariant #12). FR-61.1.

      **Layer 3 (PID lock, separate file):**
      - PID lock at `/run/spark-modem-watchdog/lock`. Owned by the daemon's main process. SEPARATE from the flocks above so a CLI mutator can take state-store + per-modem flocks without conflicting with the daemon's PID exclusivity. FR-61.

    - **Consequences**:
      - Per-modem isolation: a slow fsync on modem A's file does not block writes on modem B.
      - CLI mutators and daemon are race-free on the same file.
      - PID lock is a separate file — `ctl reset-state` doesn't need to be PID-exclusive (it just needs the per-modem and state-store flocks).
      - Lock files have mode 0o640 with PID written in plain ASCII for `cat /run/.../state.lock`-debugability.
      - A stuck flock holder is operator-visible: the file's PID points to the holder process; the operator can `kill -TERM` it manually.
    - **Risks and mitigations**:
      - Lock-ordering hazard if a cycle ever needs to lock two modems atomically — single-key API forbids it; if it ever becomes necessary, lock by sorted usb_path order.
      - Stale lock files after crash — flock is advisory + kernel-released on process death; the file persists but the lock is freed.
      - flock on NFS: not supported (advisory locks on NFS are dragons). `/run/spark-modem-watchdog/` is tmpfs, not NFS — by definition local.
    - **Revisit when**: cycle profile shows the per-modem lock contention is meaningful (today's measurement: zero contention; the lock is for safety, not performance).
    - **Implementation reference**: `src/spark_modem/state_store/locks.py` (Plan 04 — `PerModemLockTable`, `globals_lock`, `acquire_flock`, `acquire_flock_async`). The PID lock implementation lands in Phase 3 (sd_notify lifecycle).

    ---

    **`docs/adr/0013-metric-surface.md`** — integer-encoded `modem_state_value{modem}`:

    Status: Accepted; Date: 2026-05-06; Deciders: Eng team.

    Sections:
    - **Context**: PITFALLS §13.1 / §9.4. PRD's NFR-21 originally specified `modem_state{modem,state}` as a one-hot label (state values become Prom labels). At 4 modems × N states × 7 days of WAL retention, label cardinality grows unboundedly under flapping (every transition adds a new time series). Prometheus WAL compaction cost scales with cardinality. At fleet scale this becomes a real problem.
    - **Decision**: Replace the one-hot `state` label with **integer-encoded `modem_state_value{modem}`**. Stable canonical mapping:
      ```
      0 = unknown
      1 = healthy
      2 = degraded
      3 = recovering
      4 = exhausted
      ```
      The integer mapping is **stable across releases**; never reuse a number for a different state. New states extend at the end. Implementation: `spark_modem.wire.state.state_to_int(ModemState) -> int` (Plan 03). The `recovering_level` orthogonal axis (1, 2, 3) is exposed as a separate metric `modem_recovering_level{modem}` (gauge; 0 when state != recovering). The orthogonal flags `present` and `rf_blocked` are separate gauges: `modem_present{modem}` and `modem_rf_blocked{modem}` (each 0/1).
    - **Consequences**:
      - Cardinality is bounded: `4 modems × 1 state series + 4 modems × 1 recovering_level series + 4 modems × 1 present series + 4 modems × 1 rf_blocked series = 16 series` (per box; same regardless of state churn).
      - NOC dashboards translate the integer back to a label via Prometheus's `label_replace` or via Grafana dashboard mapping. Slight cognitive overhead vs. a one-hot, but quickly memorized.
      - `state_duration_seconds{modem,state}` (M-5) histogram still uses a `state` label — it's a histogram with bounded buckets per modem-state; cardinality is bounded by (4 modems × 5 states × N buckets). Acceptable.
      - The cycle driver (Phase 2) wires `modem_state_value{modem}.set(state_to_int(modem_state))` after every transition.
    - **Risks and mitigations**:
      - Adding a new state without bumping the docs — this ADR plus inline comment in `state.py state_to_int` keep the convention alive; mypy + ruff catch typos.
      - NOC dashboard breaks when the integer mapping changes — the mapping is **stable**; never reuse numbers. New states extend the table.
      - `recovering_level` exposed as 0 when state != recovering can be misread as "level 0" — document explicitly: 0 means "not in recovering"; levels start at 1.
    - **Revisit when**: real fleet data shows cardinality is fine even with one-hot (e.g. boxes don't actually flap state often) — then we can revisit.
    - **Implementation reference**: `src/spark_modem/wire/state.py state_to_int` (Plan 03 — the canonical mapping); Phase 2 cycle driver wires the gauge `.set(...)`.
  </action>
  <verify>
    <automated>
      cd S:/spark/modem-watchdog && \
      for n in 0008 0009 0010 0011 0012 0013; do test -f docs/adr/${n}-*.md || { echo "missing: ADR-${n}"; exit 1; }; done && \
      grep -l 'Status.*Accepted' docs/adr/0008-*.md docs/adr/0009-*.md docs/adr/0010-*.md docs/adr/0011-*.md docs/adr/0012-*.md docs/adr/0013-*.md && \
      grep -q 'Supersedes: ADR-0005' docs/adr/0008-*.md && \
      grep -q 'state/by-usb' docs/adr/0009-*.md && \
      grep -q 'cdc-wdmN renumbering\|cdc-wdm.*renumbering\|usb_path.*sysfs' docs/adr/0009-*.md && \
      grep -q 'python-build-standalone' docs/adr/0010-*.md && \
      grep -q 'Closes Q8\|closes Q8' docs/adr/0010-*.md && \
      grep -q 'HMAC' docs/adr/0011-*.md && \
      grep -q 'X-Spark-Signature\|X-Spark-Timestamp' docs/adr/0011-*.md && \
      grep -q 'Closes Q5\|closes Q5' docs/adr/0011-*.md && \
      grep -q 'per-modem.*Lock\|per-modem.*lock' docs/adr/0012-*.md && \
      grep -q 'flock' docs/adr/0012-*.md && \
      grep -q 'modem_state_value' docs/adr/0013-*.md && \
      grep -q 'state_to_int\|integer-encoded\|integer encoded' docs/adr/0013-*.md && \
      echo "Task 2 verification: all 6 new ADRs present with required content"
    </automated>
  </verify>
  <done>
    Six new ADRs (0008..0013) exist, each with Status: Accepted and Date: 2026-05-06. ADR-0008 carries `Supersedes: ADR-0005`. ADR-0010 closes Q8 and ADR-0011 closes Q5 (referenced explicitly in the doc text). Each ADR cross-references its research source(s) and its implementation plan number (02–06).
  </done>
</task>

<task type="auto">
  <name>Task 3: docs/adr/README.md — index of all 13 ADRs</name>
  <files>docs/adr/README.md</files>
  <read_first>
    - All 13 ADRs (0001..0013) — verify titles for the index
    - .planning/PROJECT.md §"Open questions" + §"Key Decisions" (Q→ADR mapping)
  </read_first>
  <action>
    Create `docs/adr/README.md`:
    ```markdown
    # spark-modem-watchdog v2 — Architecture Decision Records

    This directory holds the ADR set for v2. Each ADR documents one
    architecturally-significant decision: why we made it, what falls out,
    and the conditions under which we'd revisit. ADRs are append-only
    history: amendments are sections appended to the original; supersession
    leaves the original in place with a status change.

    ## Status overview

    | ADR | Title | Status | Closes |
    |-----|-------|--------|--------|
    | [0001](0001-language-python.md) | Language: Python 3.11+ | Accepted (Amended 2026-05-06) | Q8 partially (with ADR-0010) |
    | [0002](0002-event-driven-core.md) | Event-driven core | Accepted | — |
    | [0003](0003-zao-authority.md) | Zao log is authoritative for line health | Accepted (Amended 2026-05-06) | Q3 |
    | [0004](0004-typed-contract.md) | Strict typed JSON contract | Accepted (Amended 2026-05-06) | — |
    | [0005](0005-explicit-state-machine.md) | Explicit per-modem state machine | **Superseded by ADR-0008** (2026-05-06) | — |
    | [0006](0006-counter-decay.md) | Recovery counters decay on healthy cycles | Accepted (Amended 2026-05-06) | — |
    | [0007](0007-monotonic-clock.md) | Monotonic clock for backoff arithmetic | Accepted | — |
    | [0008](0008-state-machine-5-plus-2.md) | Per-modem state machine: 5 + 2 flags | Accepted (Supersedes 0005) | — |
    | [0009](0009-state-files-keyed-by-usb-path.md) | State files keyed by usb_path | Accepted | — |
    | [0010](0010-packaging-python-build-standalone.md) | Packaging via python-build-standalone | Accepted | Q8 (with ADR-0001 amendment); Q6/Q7 ops notes |
    | [0011](0011-webhook-subsystem.md) | Webhook subsystem (HMAC v2.0) | Accepted | Q5; Q1, Q2, Q4 (notes) |
    | [0012](0012-concurrency-locks.md) | 3-layer locking model | Accepted | — |
    | [0013](0013-metric-surface.md) | Integer-encoded modem_state_value | Accepted | — |

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

    - **One file per decision.** ADR-NNNN-short-kebab-title.md.
    - **Format.** Status block as a 4-row table; Context / Decision /
      Consequences / Risks and mitigations / Revisit when. See ADR-0001
      for the canonical template.
    - **Amendments** are append-only `## Amendment YYYY-MM-DD` sections
      with their own dated row in the status block.
    - **Supersession** is loud: the superseded ADR's status changes to
      `Superseded by ADR-NNNN`; the new ADR carries `Supersedes: ADR-NNNN`
      in its status block. The superseded ADR keeps its content
      (history) and gains a `## Superseded YYYY-MM-DD — see ADR-NNNN`
      pointer.
    - **Numbering** is monotonically increasing; never reuse numbers.

    ## Reading order for a new contributor

    1. ADR-0001 (language choice) + ADR-0010 (packaging) — what runtime
       lives on the box.
    2. ADR-0002 (event-driven core) + ADR-0003 (Zao authority) — how the
       daemon observes the world.
    3. ADR-0004 (typed contract) + ADR-0008 (state machine) — the wire
       boundary and the state shape.
    4. ADR-0006 (counter decay) + ADR-0007 (monotonic clock) — recovery
       semantics.
    5. ADR-0009 (state files keyed by usb_path) + ADR-0012 (locks) — the
       persistence layer.
    6. ADR-0011 (webhook) + ADR-0013 (metrics) — the observability surface.
    ```
  </action>
  <verify>
    <automated>
      cd S:/spark/modem-watchdog && \
      test -f docs/adr/README.md && \
      for n in 0001 0002 0003 0004 0005 0006 0007 0008 0009 0010 0011 0012 0013; do grep -q "ADR-${n}\|adr-${n}\|${n}-" docs/adr/README.md || { echo "README missing entry: ADR-${n}"; exit 1; }; done && \
      grep -q 'Q8' docs/adr/README.md && \
      grep -q 'Q5' docs/adr/README.md && \
      grep -q 'Superseded by ADR-0008' docs/adr/README.md && \
      echo "Task 3 verification: README index covers all 13 ADRs and the Q1..Q8 mapping"
    </automated>
  </verify>
  <done>
    `docs/adr/README.md` exists with a status table for all 13 ADRs (0001..0013), a mapping from PROJECT.md Q1..Q8 to the closing ADRs, ADR conventions, and a reading order. The status table marks ADR-0005 as Superseded by ADR-0008.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Repo → contributors | ADRs are markdown read by humans (and assistants like Claude); no execution; no security-sensitive surface. |
| ADR text → implementation | An incorrect ADR claim drifts the implementation. Mitigation is the link from ADR to implementation plan (02–06) and a cross-reference in `docs/adr/README.md`. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-07-01 | T (Tampering) | docs/adr/* | accept | ADRs are markdown in git; tampering is review-detectable. No security-sensitive content lives in the ADRs (no secrets, no signing keys). |
| T-07-02 | I (Information disclosure) | ADR text | accept | ADRs reference implementation paths (e.g. `/run/spark-modem-watchdog/state.lock`) and design choices (e.g. HMAC-SHA256 over raw body bytes). All this information is intentionally public — the receiver of a webhook needs to know the signing protocol, and an operator needs to know where state files live. |
| T-07-03 | T | ADR drift from implementation | mitigate | Each ADR carries an "Implementation reference" pointer to the relevant plan (02–06) so readers can verify. The plans themselves quote ADR section IDs. |
</threat_model>

<verification>
End-to-end check after all three tasks complete:

1. All 13 ADRs exist:
```
test -f docs/adr/0001-language-python.md && \
test -f docs/adr/0002-event-driven-core.md && \
test -f docs/adr/0003-zao-authority.md && \
test -f docs/adr/0004-typed-contract.md && \
test -f docs/adr/0005-explicit-state-machine.md && \
test -f docs/adr/0006-counter-decay.md && \
test -f docs/adr/0007-monotonic-clock.md && \
test -f docs/adr/0008-state-machine-5-plus-2.md && \
test -f docs/adr/0009-state-files-keyed-by-usb-path.md && \
test -f docs/adr/0010-packaging-python-build-standalone.md && \
test -f docs/adr/0011-webhook-subsystem.md && \
test -f docs/adr/0012-concurrency-locks.md && \
test -f docs/adr/0013-metric-surface.md && \
test -f docs/adr/README.md
```

2. All five amendments present (Task 1's grep loop):
```
grep -l '## Amendment 2026-05-06' docs/adr/0001-*.md docs/adr/0003-*.md docs/adr/0004-*.md docs/adr/0006-*.md
grep -l 'Superseded by ADR-0008' docs/adr/0005-*.md
```

3. All six new ADRs have Status: Accepted:
```
for n in 0008 0009 0010 0011 0012 0013; do grep -q "Status\s*|\s*Accepted" docs/adr/${n}-*.md; done
```

4. Q1..Q8 closures referenced in `docs/adr/README.md`:
```
for q in Q1 Q2 Q3 Q4 Q5 Q6 Q7 Q8; do grep -q "$q" docs/adr/README.md; done
```

5. Cross-references intact: ADR-0008 carries `Supersedes: ADR-0005`; ADR-0005 carries `Superseded by ADR-0008`:
```
grep 'Supersedes: ADR-0005' docs/adr/0008-*.md
grep 'Superseded by ADR-0008' docs/adr/0005-*.md
```

6. Each new ADR cross-references its research source(s):
   - ADR-0008 references `.planning/research/FEATURES.md §4.1`
   - ADR-0009 references `.planning/research/PITFALLS.md §3.1` and `ARCHITECTURE.md Q14`
   - ADR-0010 references `.planning/research/STACK.md §"Packaging recipe"`
   - ADR-0011 references `.planning/research/FEATURES.md §4.3` and `PITFALLS.md §10.1`
   - ADR-0012 references `.planning/research/ARCHITECTURE.md Q3` and `PITFALLS.md §3.2/§16.1`
   - ADR-0013 references `.planning/research/PITFALLS.md §13.1`

7. Each new ADR cross-references its implementation plan number (02–06).
</verification>

<success_criteria>
- Closes Phase 1 SC #2: all eight PROJECT.md open questions Q1-Q8 are closed in writing; six new ADRs (0008..0013) are merged; ADRs 0001/0003/0004/0005/0006 carry the research-derived amendments.
- ADR-0005 is marked `Status: Superseded by ADR-0008`; ADR-0008 carries `Supersedes: ADR-0005` — the supersession is loud and reciprocal.
- `docs/adr/README.md` provides a status table for all 13 ADRs plus a mapping from Q1..Q8 to closing ADRs — a single-file orientation for new contributors.
- Each new ADR cross-references its research source (`.planning/research/SUMMARY.md` / FEATURES.md / ARCHITECTURE.md / STACK.md / PITFALLS.md) AND its implementation plan (02–06) — drift between ADR and code is reviewer-detectable.
- This plan ships ZERO code; all the implementation lives in Plans 02–06. The ADR set is parallel-able with Plan 01 because both are docs-only (Plan 01) or scaffolding-only (this plan); they touch disjoint files.
</success_criteria>

<output>
After completion, create `.planning/phases/01-foundations-adrs/01-07-SUMMARY.md` covering: the 13-ADR status table (mirroring `docs/adr/README.md`), the Q1..Q8 → ADR mapping, and a one-line for each amendment + each new ADR. Reference Plan 02 (ADR-0010 implementation), Plan 03 (ADR-0008 + ADR-0013 implementation surfaces), Plan 04 (ADR-0009 + ADR-0012 implementation), Plan 06 (Q6/Q7 ops notes wiring via Settings).
</output>
