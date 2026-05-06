# ADR-0002 — Event-driven core with polling fallback

| Field        | Value          |
| ------------ | -------------- |
| Status       | Accepted       |
| Date         | 2026-05-05     |
| Deciders     | Eng team       |

## Context

v1 polls every 120 seconds. Costs:

- A modem failure observed at T+0 might not be acted on until T+120.
- Probing N modems sequentially is wasted parallelism.
- The probes themselves are the dominant load on the QMI channel —
  they cause the very races they then have to retry.
- The kernel and Zao both already emit signals about the things we
  care about; ignoring them is silly.

## Options considered

### A. Pure polling, faster (chosen for fallback only)

- Pros: simple; no event-source library deps.
- Cons: still wasteful; still slow to react; still QMI-noisy.

### B. Pure event-driven, no fallback

- Pros: minimal QMI noise; instant reaction.
- Cons: not all things we care about have events (e.g. signal
  quality drift). And event sources can fail (Zao log might not be
  rotating; udev might lose events under load). A pure event-driven
  daemon hangs when the events stop.

### C. Event-driven core with polling fallback (chosen)

- Pros: react fast when events fire; still tick at a wall-clock
  deadline so signal drift and missed events get caught.
- Cons: two execution paths to test. We mitigate via fixture-driven
  testing where the same cycle function is invoked from both paths.

## Decision

**Event-driven core with a 30 s polling fallback.** The cycle
function runs whenever any of:

- A `udev` USB add/remove event arrives.
- An `rtnetlink` link-state change fires.
- The Zao log gets an `IN_MODIFY` (parsed; if the new content
  contains a `RASCOW_STAT` change, we cycle).
- A polling deadline expires (default 30 s; configurable).
- A SIGHUP arrives (config reload + cycle).

After a cycle, the deadline timer resets.

Event sources are background `asyncio` tasks pushing onto an
`asyncio.Queue`. The main loop awaits the queue with a timeout
equal to the polling deadline.

## Consequences

- Polling cadence drops from v1's 120 s to v2's 30 s wall-clock,
  but the *typical* reaction time is sub-second (when an event
  fires).
- We must test both paths. The cycle function is a pure function of
  inputs; both paths converge on it.
- We must handle event-source failures gracefully:
  - inotify on the Zao log re-opens on `IN_MOVE_SELF` /
    `IN_DELETE_SELF`.
  - udev re-subscribes on `OSError`.
  - rtnetlink uses `pyroute2`'s reconnect logic.
- `qmi_zao_log_age_seconds` is a metric; if it grows unbounded, NOC
  pages.

## Risks and mitigations

| Risk                                       | Mitigation                                          |
| ------------------------------------------ | --------------------------------------------------- |
| Event flood causes cycle starvation        | Coalesce: if events arrive while a cycle is running, run exactly one more cycle when current cycle finishes. |
| Event source dies silently                 | Each source has a heartbeat; failure to update its `last_seen` for > 5 min logs an error and the source restarts. |
| Polling fallback is too aggressive in a busy cycle | Cycle duration histogram is metric'd; alert if P99 > 30 s for ≥ 5 min. |

## Revisit when

- We see the daemon over-cycling under event storms.
- We add a new event source (e.g. ModemManager D-Bus).
