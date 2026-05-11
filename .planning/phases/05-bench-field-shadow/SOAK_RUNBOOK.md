# Phase 5 Soak Runbook — Bench & Field Shadow

| Field         | Value                                                 |
| ------------- | ----------------------------------------------------- |
| Status        | Active (Phase 5)                                      |
| Owner         | On-site engineer (single human in the Phase 5 loop)   |
| Audience      | On-site engineer + reviewer                           |
| Scope         | Bench Jetson 1-week soak + field box 2-week soak      |
| Last updated  | 2026-05-11                                            |

> **Scope context:** v1 is retired across the fleet (CONTEXT.md scope_pivot
> 2026-05-11). v2 runs at canonical paths from day 1; there is no
> v1-vs-v2 compare tool, no shadow-mode YAML drop-in, no `-v2`-suffixed
> service or paths, and no synthetic fault injection on the field box (F-01).
> See `05-CONTEXT.md` § scope_pivot for the retired-artifact list.

---

## 1. Soak windows

Sequential (S-02):
1. **Bench Jetson — 1 week** (`bench-jetson-<id>`). Bench-week fault
   injection rides the existing Plan 04-07 HIL nightly cron unchanged (F-02).
2. **Bench → Field handoff gate (S-03)** — same 3 gates as Phase 5 exit,
   measured over bench week alone. Cannot proceed until clean.
3. **Field box — 2 weeks** (`box-<region>-<n>`). Natural faults only (F-01);
   no synthetic injection.

F-04 budget: 1 minor violation per week of any single S-01 gate is permitted.
Disposition each violation in SIGNOFF.md regardless of severity. 2nd
violation in the same week of the same gate resets the soak clock for that
window.

---

## 2. Daily operator checks

Run these every day during both soak windows. Anything anomalous gets
logged in SIGNOFF.md F-04 Violations log immediately (capture the evidence
even if you later decide it was not a violation).

### 2.1 Daemon health (M6 / S-01 #1)

```bash
# Failed-unit + crash events over the last 24h
journalctl --unit spark-modem-watchdog.service --since "24 hours ago" \
  | grep -E '(error|Main process exited|systemd\[1\]: spark-modem-watchdog)' || echo "no errors"

# Confirm process is up and accumulating uptime
systemctl status spark-modem-watchdog.service --no-pager | head -10
```

A failed unit OR a `daemon_started` event with `reason=CRASH` in
`events.jsonl` is an S-01 #1 violation. Capture the journal slice.

### 2.2 Cycle health (M5 — informational, NOT blocking)

```bash
# Latest cycle duration via status.json
sudo cat /var/lib/spark-modem-watchdog/status.json | jq '.cycle.last_duration_seconds'

# Prometheus UDS scrape (cardinality-safe integer metric per ADR-0013):
sudo curl --unix-socket /run/spark-modem-watchdog/metrics.sock \
  http://localhost/metrics \
  | grep -E '^(cycle_duration_seconds|modem_state_value\{|daemon_self_health)'
```

> **DO NOT** use the legacy one-hot label form where a `state` label
> dimension was put on the modem-state metric (the shape ADR-0013 rejected).
> Always use the integer-encoded form above: `modem_state_value{modem="2-3.1.1"}`
> returns an integer in {0=unknown, 1=healthy, 2=degraded, 3=recovering,
> 4=exhausted}. The legacy one-hot label form is the cardinality-explosion
> anti-pattern.

### 2.3 State scan (M4 / S-01 #3 incremental)

```bash
sudo cat /var/lib/spark-modem-watchdog/state/by-usb/*.json \
  | jq -c 'select(.state=="exhausted") | {usb_path, state, recovering_level, _healthy_streak}'
```

Any modem in `state=exhausted` warrants investigation. Cross-check against
`events.jsonl` for the most recent `state_transition` to that modem to
classify EXPLAINED vs UNEXPLAINED (the audit tool does this at soak exit).

### 2.4 Action history (S-01 #2 + #3 incremental)

```bash
# All ActionPlanned events in the last 24h
sudo spark-modem ctl history --since=24h \
  | jq -c 'select(.kind=="action_planned") | {ts_iso, who: .who.usb_path, action, category}'
```

For each ActionPlanned event, sanity-check against the Zao log to confirm
the line was inactive at the cycle. Full audit runs at soak exit via
`tools/audit_soak_zao.py`.

### 2.5 RSS tripwire (NFR-3 — informational)

```bash
sudo curl --unix-socket /run/spark-modem-watchdog/metrics.sock \
  http://localhost/metrics | grep -E '^daemon_self_health\{kind="rss"\}'
```

RSS budget is 80 MiB; tripwire at 200 MiB. If the daemon trips, it logs a
WARN line and an event; the daemon does NOT restart on this alone.

---

## 3. F-04 violation disposition workflow

When a daily check surfaces an anomaly:

1. **Capture evidence immediately.** Save the journalctl slice, the
   status.json snapshot, and the most recent `state/by-usb/*.json` and
   Zao log tail.
2. **Classify within 24h:**
   - Customer-visible outage? → NOT minor; soak clock resets for this gate.
   - Root cause attributable? → if not within 24h, NOT minor; clock resets.
   - Fixable in <4h of engineering work? → if not, NOT minor; clock resets.
3. **Open issue + fix PR** if minor (CONTEXT.md F-04 "dispositioned"
   definition). Record both links in SIGNOFF.md.
4. **Record in SIGNOFF.md F-04 Violations log** REGARDLESS of disposition.
   Every violation is auditable.
5. **2nd violation of same gate in same week → soak clock resets** for that
   window. Field deploy can only start after a fresh clean bench week.

---

## 4. Soak-exit procedure

Run this checklist at the END of the field 2-week soak (or, if the bench
week is being evaluated for S-03, with `--since-iso` set to the bench-week
start).

### 4.1 Run S-01 #2 audit

```bash
python tools/audit_soak_zao.py \
  --events /var/log/spark-modem-watchdog/events.jsonl \
  --zao-log /var/log/zao-remote-endpoint.log \
  --since-iso <SOAK_START_ISO> \
  --out artifacts/soak-zao-violations.json

# Inspect:
cat artifacts/soak-zao-violations.json | jq '.violations'
```

Exit 0 = clean. Exit 1 = at least one violation; review `details[]`.

### 4.2 Run S-01 #3 audit

```bash
python tools/audit_soak_exhausted.py \
  --events /var/log/spark-modem-watchdog/events.jsonl \
  --since-iso <SOAK_START_ISO> \
  --out artifacts/soak-exhausted-violations.json

cat artifacts/soak-exhausted-violations.json \
  | jq '.violations, .audited_exhausted'
```

Exit 0 = clean. Exit 1 = at least one UNEXPLAINED transition.

### 4.3 Run R-02 replay-harness one-shot

Run on the dev laptop (local LFS bundle is sufficient; no hardware needed):

```bash
# Ensure latest v1-30d trace bundle is pulled
python tools/pull_replay_traces.py

# Run the harness; conftest.py R-03 hard-fails below 0.95
pytest tests/replay/test_v1_agreement.py -v --tb=short

# Locate the JSON summary produced by pytest_sessionfinish
ls -la artifacts/replay-summary.json

# Commit as the Phase 5 exit artifact
cp artifacts/replay-summary.json \
   .planning/phases/05-bench-field-shadow/replay-summary-phase5-exit.json
```

### 4.4 Fill in + commit SIGNOFF.md

```bash
# Edit:
$EDITOR .planning/phases/05-bench-field-shadow/SIGNOFF.md
# (fill engineer name, box-ids, soak windows, gates, R-02 rate, F-04 log)

# Commit alongside the replay-summary artifact + audit JSONs:
git add .planning/phases/05-bench-field-shadow/SIGNOFF.md \
        .planning/phases/05-bench-field-shadow/replay-summary-phase5-exit.json \
        artifacts/soak-zao-violations.json \
        artifacts/soak-exhausted-violations.json
git commit -m "phase-5: SIGNOFF.md + R-02 replay-harness exit artifacts"
```

### 4.5 Open Phase 6 entry PR

Phase 6 PR cannot merge until:
- All four "Phase 6 entry approval" boxes in SIGNOFF.md are checked.
- The X-04 batched fleet-fixture PR is merged FIRST (every fleet box has a
  triple.json under `tests/fixtures/fleet/<box-id>/` per CONTEXT.md X-04).
  Engineer triggers this on each box via `spark-modem ctl capture-fleet-fixture`
  (Plan 05-03) during the physical-access window for Phase 6 prep.

---

## 5. R-01 day-1 trace pull (kickoff procedure)

This runs ONCE, at Phase 5 kickoff, BEFORE the bench soak begins.

1. On-site engineer archives `/var/log/spark-modem-watchdog/` from every
   (decommissioned) v1 box. Tarball per box, preserving filenames.
2. On the dev laptop, run:

   ```bash
   python tools/pull_replay_traces.py \
     --input-archive <path-to-archive-bundle> \
     --output-dir tests/fixtures/replay/v1-30d/
   ```

   Tool applies sha256[:8] redaction to ICCID/IMSI/IP per
   `tests/fixtures/replay/v1-30d/README.md` contract.
3. Open a single LFS PR updating `tests/fixtures/replay/v1-30d/`. Commit
   message includes the day-1 refresh tag for future quarterly cadence
   (R-04).
4. Merge before bench soak begins; the replay-harness uses this bundle at
   Phase 5 exit (R-02).

---

## 6. Known gaps / antipatterns

These are pre-existing repo issues; the runbook flags them so operators
don't trip on them during Phase 5:

- **`spark-modem ctl config-check`** is referenced by
  `debian/spark-modem-watchdog.service:17` (ExecStartPre) but is NOT
  implemented in `src/spark_modem/cli/`. Operators should NOT run this
  command manually during soak — it will fail with "unknown subcommand".
  Fix is deferred per CONTEXT.md (not Phase 5's job).
- **Prom one-hot label** — never use a `state` label dimension on the
  modem-state metric (the legacy shape ADR-0013 rejected because it
  causes cardinality explosion across the {unknown, healthy, degraded,
  recovering, exhausted} value set). Always use the integer-encoded form
  `modem_state_value{modem="<usb_path>"}` returning an integer 0-4.

---

## 7. Cross-reference

- Steady-state operator doc (non-soak operations): `docs/RUNBOOK.md`
- Phase 5 entry signoff: `.planning/phases/05-bench-field-shadow/SIGNOFF.md`
- S-01 / F-04 / R-02 / X-04 locked decisions: `.planning/phases/05-bench-field-shadow/05-CONTEXT.md`
- X-03 daemon preflight (refuses-to-start-on-unknown-triple):
  `src/spark_modem/daemon/preflight_triple.py`
- Audit tools: `tools/audit_soak_zao.py`, `tools/audit_soak_exhausted.py`
- Replay harness: `tests/replay/test_v1_agreement.py`
- Fleet fixture capture CLI: `spark-modem ctl capture-fleet-fixture` (Plan 05-03)

---

*Phase 5: Bench & Field Shadow — soak runbook.*
*Authored by Plan 05-07. Lifecycle-bound; archive (NOT delete) after Phase 6.*
