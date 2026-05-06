# ADR-0007 — Use CLOCK_MONOTONIC for all backoff arithmetic

| Field        | Value          |
| ------------ | -------------- |
| Status       | Accepted       |
| Date         | 2026-05-05     |
| Deciders     | Eng team       |

## Context

In v1, all backoff math uses `date +%s` (wall clock):

```bash
last_t="${STATE_THIS[last_action_time]:-0}"
local now=$(date +%s)
local age=$((now - last_t))
[ "$age" -lt "$BACKOFF_SECONDS" ]
```

If NTP steps the wall clock backward (which happens on a Jetson
during boot or after a long offline period), `last_action_time`
becomes "in the future." The age computation goes negative and
backoff effectively never expires. The README acknowledges this:

> If `last_action_time` updates every cycle, backoff isn't sticking — likely a clock issue. Verify: `date`, `timedatectl status`.

This is exactly the kind of thing we should not require operators
to diagnose.

## Decision

**All backoff and elapsed-time arithmetic uses `time.monotonic()`,
not `time.time()`.** The wall clock is used **only** for ISO-8601
timestamps on log lines and event records.

Mechanism:

- The `Clock` protocol exposes `now_monotonic() -> float` and
  `now_iso() -> str`.
- The `StateStore` persists action timestamps as monotonic seconds
  with the daemon's `monotonic_epoch_iso` (the wall-clock ISO at
  which monotonic=0 effectively was). On daemon restart, the new
  daemon writes a fresh `monotonic_epoch_iso` and converts old
  monotonic timestamps to **wall-relative** "happened N seconds
  ago" form by subtracting from the previous epoch's wall stamp.
  Then it persists the converted "wall ago" plus the new monotonic
  timestamp. (See `state/clock_translation.py`.)
- For human consumption (status.json, events.jsonl) every persisted
  monotonic value is paired with a wall-clock ISO so an operator
  reading the file by hand sees a meaningful timestamp.

## Consequences

- Backoff is robust to NTP steps and suspend-resume.
- State files become slightly busier: each timestamp has both
  `_monotonic` (float) and `_iso` (string) variants.
- Daemon restart is non-trivial for elapsed-time semantics: a
  process that was 100 s into a 300 s backoff and then died for
  10 s before restarting, should resume backoff. The translation
  on startup preserves this within `wall_clock_drift_tolerance`
  seconds; we default to 60 s. Beyond that we assume the wall clock
  drifted significantly (e.g. NTP step) and we treat any
  pre-restart monotonic as "expired" — the conservative choice
  (re-allows the action sooner).

## Why not just record action times in wall clock and compare wall

It works under steady NTP, but our threat model includes:
- Boxes deployed without internet at install time, so first NTP step
  is hours later.
- Boxes that lose NTP for a day and come back.
- Boxes whose RTC drifts by minutes.

Wall-clock backoff is brittle to all of these. Monotonic is not.

## Risks and mitigations

| Risk                                                  | Mitigation                                                |
| ----------------------------------------------------- | --------------------------------------------------------- |
| Daemon restart loses backoff state                    | State file pairs monotonic with ISO so we can re-anchor. Drift tolerance avoids treating an old state as eternal.|
| Operator reading a state file is confused by `_monotonic` | The paired `_iso` field tells them when, in human terms.   |
| Tests need a fake monotonic clock                     | The `Clock` protocol is mocked in every test. |

## Revisit when

- The `wall_clock_drift_tolerance` heuristic produces wrong answers
  in real boxes. Then we either tune it or store a richer record
  (e.g. boot ID).
