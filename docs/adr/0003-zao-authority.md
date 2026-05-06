# ADR-0003 — Zao log is authoritative for line health

| Field        | Value          |
| ------------ | -------------- |
| Status       | Accepted       |
| Date         | 2026-05-05     |
| Deciders     | Eng team       |
| Inherits     | v1's behaviour, formalised. |

## Context

In production, Zao owns the modems' QMI control channel. If we probe
a modem while Zao is using it, we either race Zao for exclusive
ownership (and lose), or we go through `qmi-proxy` and still produce
a noisier-than-necessary load.

v1 already learned this and added a "Zao-first" rule: parse Zao's
`RASCOW_STAT` log lines; if Zao reports a line as `active=1`, skip
all QMI probes for that line and trust Zao that it is bonding fine.

## Decision

We keep this rule and elevate it. **Zao's log is the authoritative
source of truth for "is line N bonding right now?"** The observer's
QMI probes only run for lines Zao reports as inactive.

When Zao reports a line as active and the daemon has nothing else to
say about it, the line is in `Healthy` state. All probe fields in
`Diag` are `null`.

## Consequences

- The daemon must successfully tail and parse the Zao log to do its
  job. Failure modes:
  - **Log file missing** → daemon emits `zao/zao_log_stale`, falls
    back to direct probing for all lines (degraded mode).
  - **Log format changed** (RASCOW_STAT not found in newest entries)
    → log warning; alert; same fallback.
- The Zao log path is configurable, but the format we parse is not
  generalised — we know the EM7421 + Zao 2.1.0 format. A Zao SDK
  upgrade requires re-validation (TEST_STRATEGY § 4 fixture set).
- `signal.sufficient` and other RF-quality fields are `null` for
  active lines. Recovery's RF gate handles `null` as "proceed
  normally" (RECOVERY_SPEC § 6.1) so this does not over-gate.
- The rule does not extend to "is the line healthy?" — Zao reports
  `active`, which is its operational view; a line can be `active`
  with bad RF (Zao tolerates marginal links). For our purposes,
  `active` is sufficient: Zao itself is the entity that would suffer
  if the line were bad, and Zao's control loop will mark it
  inactive when it fails. We trust that loop.

## Why we don't replace this with a Zao API

There isn't one we can rely on as authoritative. Zao has internal
control structures, but:

- They are not part of Zao's public/stable surface.
- The log line is the existing public artefact; relying on it
  matches Zao's own debugging story.
- A future Zao change to expose this state more cleanly is welcomed;
  the daemon's `zao_log` module can grow a second backend.

## Risks and mitigations

| Risk                                                     | Mitigation                                                         |
| -------------------------------------------------------- | ------------------------------------------------------------------ |
| Zao log format changes and we don't notice               | `zao_log` parser fails closed: zero `RASCOW_STAT` matches in the last 10 minutes triggers `zao_log_stale` and a fallback. CI has fixtures for known good and known bad formats. |
| Zao stops writing the log for some other reason          | Same: `zao_log_stale` triggers fallback. The daemon does not silently start probing active lines. |
| Race: Zao log says active, but Zao is mid-fail and the modem is stuck | Acceptable. Zao's control loop rapidly transitions inactive on real failure. The watchdog notices a few cycles later. The cost is minutes, not hours. |

## Revisit when

- Zao SDK exposes a stable D-Bus or shared-memory state interface.
- We need finer granularity than "active / not active" (e.g. per-
  bearer or per-PDP context).
