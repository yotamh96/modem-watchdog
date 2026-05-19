# Phase 5: Bench & Field Shadow — Research

**Researched:** 2026-05-11
**Domain:** Delivery / shadow-validation. v2 live soak (v1 retired across the fleet) + fleet-fixture capture + replay-harness gate + SIGNOFF.
**Confidence:** HIGH on existing-code wiring (all surfaces audited in this session); MEDIUM on policy choices the user marked Claude's Discretion (index shape, query mechanism, SIGNOFF template); HIGH on the v1-retired pivot semantics (locked by CONTEXT.md).

---

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Scope pivot (overrides ROADMAP / MIGRATION):** v1 is retired across the entire fleet. The shadow-alongside-v1 framing in MIGRATION.md Phases 1–2 is **dead**. `tools/compare_v1_v2.py` is **NOT** built. v2 runs at canonical paths from day 1. No `99-shadow.yaml`, no `spark-modem-watchdog-v2.service`, no `-v2`-suffixed state/log/run dirs.

**Replay harness (R-*):**
- R-01: Day-1 fresh trace pull from real-fleet v1 logs at Phase 5 kickoff. Engineer archives `/var/log/spark-modem-watchdog/` from each (decommissioned) v1 box, runs `tools/pull_replay_traces.py` locally for sha256[:8] redaction, opens one PR with the LFS payload updating `tests/fixtures/replay/v1-30d/`.
- R-02: Replay-harness gate (`tests/replay/test_v1_agreement.py` + R-03 hard-fail) runs **once, manually, at Phase 5 exit** — not on every commit, not nightly. Eng triggers before committing SIGNOFF.md.
- R-03: Gate bar stays at **≥0.95** (no change to `tests/replay/conftest.py`; no two-tier slicing).
- R-04: Quarterly trace refresh begins with the day-1 pull; subsequent cadence is Phase 6/7 concern.

**Soak windows (S-*):**
- S-01: "Clean soak" = all three over bench week + field two weeks:
  1. Zero daemon crashes / OOM / unhandled-exception restarts (M6).
  2. Zero "action planned on a Zao-active line" (ADR-0003).
  3. Zero unexplained `exhausted` state transitions (M4 / ADR-0006).
- S-01.1: M5 P99 ≤10s and NFR-3 RSS ≤80 MiB are **informational only**, not blockers.
- S-02: **1 week bench + 2 weeks field, sequential.** Field can't start until bench week clean.
- S-03: Bench→field handoff = same 3 gates over bench week.
- S-04: Phase 6 entry signoff = `SIGNOFF.md` checklist + replay-harness JSON committed alongside.

**Fault injection (F-*):**
- F-01: **No synthetic injection on field box.** Field rides natural faults only.
- F-02: Bench-week injection rides existing Plan 04-07 HIL nightly cron unchanged.
- F-03: **No natural-fault minimum** on field; 14-day soak does not require any minimum recovery events.
- F-04: **1 minor violation per week budget** of any S-01 gate; 2nd violation same week resets the soak clock.

**Fleet fixture capture (X-*):**
- X-01: New CLI verb `spark-modem ctl capture-fleet-fixture --out=<dir>`.
- X-02: Fixture contains `triple.json` + `qmi/<modem_usb_path>/<verb>.txt` (raw stdout of 6–8 qmicli verbs, PII scrubbed) + `zao-log-sample.txt` (last 50 RASCOW_STAT lines).
- X-03: **Daemon preflight refuses to start on unknown (firmware, SDK, libqmi) triple.** Index baked into `.deb` under `/etc/spark-modem-watchdog/known-fleet/`. New behavior added to preflight in Phase 5.
- X-04: Engineer runs capture on each fleet box during physical-access window for Phase 6 prep; per-box PRs batched into one Phase-6-prerequisite PR.

### Claude's Discretion

- Exact list of qmicli verbs in X-02 (6–8 range).
- Shape of known-set index baked into `.deb` (X-03).
- Mechanism for engineer to query triple without the daemon (X-03 chicken-and-egg).
- SIGNOFF.md template structure.
- "Minor violation" / "dispositioned" definitions (F-04).
- "Act on Zao-active line" post-hoc query mechanism (S-01 #2).
- "Unexplained Exhausted" detection mechanism (S-01 #3).
- "Run-once at Phase 5 exit" R-02 mechanism (pytest invocation vs. runbook step).

### Deferred Ideas (OUT OF SCOPE)

- Doc-rewrite housekeeping (ROADMAP SC#1/#2/#3 rewording, MIGRATION Phases 1–2 reframe, PROJECT.md / CLAUDE.md "v1 keeps fleet online" line edits, PROJECT.md migration checkboxes). Phase 7 or dedicated doc-fixup phase.
- ADR-0014 candidate ("v1 retired pre-Phase-5"). Not Phase 5 scope unless user asks.
- `tools/compare_v1_v2.py` (explicitly NOT built).
- Shadow `.deb` packaging story (NOT built).
- Field-box synthetic fault injection (NOT built).
- Real-fleet 1199:9051 bootloader rate measurement (v2.1 candidate; informational only during 14-day soak).
- D-Bus subscription to zao-infra-ctrl.service (v2.1).
- Per-MCC signal-gate override (v2.1).
- `ctl simulate-issue` (v2.1, deferred again).
- Phase 5 replay-harness as Phase 6/7 commit-CI gate.

---

## Phase Requirements

Phase 5 is a delivery phase with **no v1 REQ-IDs in ROADMAP** (ROADMAP.md line 350–352 explicitly: "no v1 REQ-IDs — this is a delivery / shadow-validation phase"). The de-facto requirements are the M-metrics from `.planning/PROJECT.md` § 8 plus the locked R-/S-/F-/X- decisions in CONTEXT.md. The S-01 gates are the **hard exit criteria**.

| ID | Description | Research Support |
|----|-------------|------------------|
| M4 | Zero `Exhausted` states caused by counter accumulation | ADR-0006 amendment locks the atomic streak+decay+counter-reset+state-write ordering. S-01 #3 detection replays `policy.transitions` + `policy.gates` against soak `events.jsonl` to confirm every `exhausted` transition is attributable. |
| M6 | Zero OOM / unhandled-exception daemon restarts in 30 days | S-01 #1. Detected by `journalctl --unit spark-modem-watchdog.service --since "<soak_start>"` for failed-unit log lines + counting `DaemonRestart` events with `reason=CRASH` in `events.jsonl`. |
| ADR-0003 | Never QMI-probe a Zao-active line | S-01 #2 detection joins `events.jsonl` `ActionPlanned` events with `ZaoSnapshot` history; zero violations is the bar. |
| S-04 (CONTEXT) | SIGNOFF.md + replay-harness JSON committed as Phase 6 prerequisite | Plan 04-07 already wired the pytest harness with `pytest_sessionfinish` writing `artifacts/replay-summary.json`; Phase 5 produces a committed copy alongside SIGNOFF.md. |
| X-03 (CONTEXT) | Daemon refuses to start on unknown (firmware, SDK, libqmi) triple | New `preflight_check_known_fleet_triple` slots into `daemon/main.py` between existing `preflight_check()` and `acquire_pid_lock()`. |
| X-01 + X-02 (CONTEXT) | `spark-modem ctl capture-fleet-fixture --out=<dir>` produces redacted per-box fixture | New verb under `cli/ctl/`; reuses `QmiWrapper`, `ZaoLogParser`, redaction helper. |

---

## Project Constraints (from CLAUDE.md)

The planner must honor every directive below; research recommendations below do not contradict any of these:

- **Subprocess discipline (CLAUDE.md §"Stack snapshot"):** list-form argv only; `asyncio.subprocess` only; one wrapper module (`subproc/`). `grep -r 'create_subprocess_exec' src/` outside `subproc/` must remain empty (verified at `src/spark_modem/subproc/runner.py:146` is the SOLE call site).
- **SP-04 lint scope:** `src/spark_modem/` only. `tools/` and `tests/` are exempt (verified at `tools/pull_replay_traces.py:18-21` and `tests/hil/fault_inject.py:22-27` docstrings). The new `capture-fleet-fixture` lands under `src/spark_modem/cli/ctl/` and therefore **MUST** route every qmicli invocation through `subproc.runner.run`, NOT direct `subprocess.run`.
- **Atomic file writes:** temp + rename + directory fsync via `state_store/atomic.py:atomic_write_bytes`. Required for any known-fleet index file written at capture time.
- **usb_path keying:** ADR-0009. Fleet fixture per-modem subdir uses `usb_path` (e.g. `qmi/2-3.1.1/dms_get_revision.txt`), never `cdc-wdmN`.
- **Zao RASCOW_STAT authoritative:** ADR-0003. The S-01 #2 detector verifies the daemon honored this in every cycle of the soak.
- **No inbound IPC in v2.0:** capture-fleet-fixture is invoked by the operator at a shell prompt; no socket/HTTP/DBus.
- **`match` not `if/elif` on `ModemState`:** if S-01 #3 detector touches state, `match modem_state.state:` is mandatory (`src/spark_modem/policy/transitions.py` is the pattern; `src/spark_modem/policy/engine.py:1-23` documents the cycle ordering).
- **Counter atomicity (ADR-0006 amendment):** streak update → decay check → counter reset → state-write is one atomic write per cycle. S-01 #3 detection must replay this exact ordering.
- **Integer-encoded `modem_state_value{modem}`:** ADR-0013. Soak-monitoring Prometheus queries read this metric directly.

---

## Summary

Phase 5 is **80% wiring existing assets, 20% net-new code**. The net-new pieces are: one CLI verb (`capture-fleet-fixture`), one preflight check (`preflight_check_known_fleet_triple`), a known-fleet index data file shipped via `.deb`, two post-hoc soak-audit tools (S-01 #2 and S-01 #3 detectors), a SIGNOFF.md template, and a soak runbook. Everything else (replay harness, LFS pull, HIL nightly, fixture-tree layout, redaction, atomic writes) already exists.

The **two highest-risk decisions** are:

1. **X-03 chicken-and-egg (Q2):** the daemon refuses to start on unknown triple, but the engineer must capture the triple on a daemon-less box. Recommended fix: `capture-fleet-fixture` is a standalone CLI subcommand that runs WITHOUT the daemon — it shells out to qmicli via the same `subproc.runner.run` the daemon uses, but in a CLI context, with no preflight participation. This avoids inventing a `--no-preflight` daemon flag (which would be a footgun in Phase 6) and avoids a redundant `ctl show-triple` companion verb.
2. **F-04 budget recording (process risk):** the user accepted 1 minor violation/week, but **every violation must be recorded regardless of disposition** so reviewers can audit the judgment. SIGNOFF.md must mandate this audit field. The recommended definitions land below.

**Primary recommendation:** Build the smallest possible delivery surface (4 code files net-new + 1 data file in `.deb` + 2 operator-facing markdowns). Plan task assignment should reflect that all soak monitoring and PR-authoring is on the on-site engineer; the daemon's behavior is locked.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Fleet-fixture capture (X-01/X-02) | CLI subcommand | qmicli subprocess via `subproc.runner` | Operator runs once per box; daemon not required. PII redaction at capture time via existing `redact_pii`. |
| Triple preflight (X-03) | Daemon preflight | systemd ExecStartPre (deferred) | Runs in-process before `acquire_pid_lock()` so `last-config-error` marker + sd_notify status work uniformly. ExecStartPre is an alternative considered but rejected — see Q4. |
| Known-fleet index (X-03 data) | `.deb` postinst-installed `/etc/spark-modem-watchdog/known-fleet/` | Build pipeline collects from `tests/fixtures/fleet/*/triple.json` | Read-only data; engineer never edits on the box. Atomic install via dpkg replaces semantics; daemon never mutates these files at runtime. |
| Day-1 v1-trace pull (R-01) | `tools/pull_replay_traces.py` | git-lfs CLI | Already built (Plan 04-06). Phase 5 just runs it. |
| Replay gate (R-02) | `pytest tests/replay/` | Pytest sessionfinish hook + LFS artifacts | Already built (Plan 02-10 + 04-07). Phase 5 invokes manually at exit. |
| Soak audit S-01 #2 ("act on Zao-active line") | `tools/audit_soak_zao.py` (new) | `event_logger` JSONL reader + `ZaoSnapshot` types | One-off Python script reading events.jsonl + Zao log. No daemon involvement. |
| Soak audit S-01 #3 ("unexplained Exhausted") | `tools/audit_soak_exhausted.py` (new) | Imports `policy.transitions` + `policy.gates` for replay | Pure-function policy modules are import-clean (no I/O at import; verified at `src/spark_modem/policy/engine.py:1-23`); tool replays decay logic against soak events. |
| SIGNOFF.md authoring | On-site engineer | RUNBOOK.md amendment + template | Operator-facing checklist; no code. |
| Soak runbook | `.planning/phases/05-bench-field-shadow/SOAK_RUNBOOK.md` (new) | Cross-references RUNBOOK.md | Operator-facing daily-checks doc; lifecycle-bound (Phase 5 only) so does NOT mutate `docs/RUNBOOK.md`. See Q9. |

---

## Q1 — X-03 known-set index shape

**Recommendation:** Directory of `<sha256-hex-of-triple>.json` files at `/etc/spark-modem-watchdog/known-fleet/` (one file per known box's triple).

Schema per file:
```json
{
  "schema_version": 1,
  "em7421_firmware": "SWI9X30C_02.38.00.00",
  "zao_sdk": "2.1.0",
  "libqmi": "1.30.6",
  "first_seen_box_id": "bench-jetson-01",
  "first_seen_iso": "2026-05-11T14:32:00Z",
  "_comment": "captured by spark-modem ctl capture-fleet-fixture; do not hand-edit"
}
```

Daemon preflight: hash the local triple (`sha256(f"{firmware}|{sdk}|{libqmi}").hexdigest()`), look for `/etc/spark-modem-watchdog/known-fleet/<hash>.json`. Existence check is the entire validation — file contents are informational metadata.

### Alternatives considered

| Option | Pro | Con | Verdict |
|--------|-----|-----|---------|
| **Directory of `<sha>.json` files** | Zero merge conflicts between concurrent X-04 capture PRs (each box adds exactly one file). O(1) lookup. Trivially auditable. Read-only at runtime. | One inode per known triple. Marginally more `.deb` install steps. | **Recommended.** |
| Single `index.json` with array | One file to read. | Every X-04 PR touches the same file → guaranteed merge conflict on the batched Phase-6-prereq PR with N boxes. Must be sorted+rewritten on every capture, fighting atomicity. | Rejected. |
| YAML at `/etc/.../known-fleet.yaml` | Human-readable. | YAML parser dependency on a hot path (preflight); pydantic+yaml load is ~50ms; preflight wants ms-class. PyYAML deserialization quirks. | Rejected. |
| Python module imported by daemon | Type-safe at parse. | Requires re-building the `.deb` for every captured triple; can't be hand-patched in the field. Couples data to code. | Rejected. |

**Atomic-write requirement:** the `.deb` postinst (or, more correctly, `debian/install` declarative copy via `dh_install`) drops these files at install time. dpkg-internal atomicity handles the replace; no daemon-side `atomic_write_bytes` is needed because the daemon never writes these files. Permissions: `0644 root:root` (read-only for daemon, daemon runs as root per `debian/spark-modem-watchdog.service:44`).

**`.deb` size impact:** trivial (~300 bytes per known triple × small fleet = single-digit KiB). Below noise floor of NFR-51's 40 MiB ceiling.

---

## Q2 — X-03 chicken-and-egg fix

**Recommendation:** **`capture-fleet-fixture` is a standalone CLI subcommand that does NOT participate in preflight at all** (no `--no-preflight` flag invented; no `ctl show-triple` companion verb invented). The capture runs in the CLI process; the daemon is not running; the daemon's preflight is irrelevant.

### Why this is safe

1. The daemon's preflight check is run by **the daemon's main process** (`src/spark_modem/daemon/main.py:170` `_production_main` → `await preflight_check()` at line 208). It is NOT a separate binary that the CLI inherits.
2. The CLI (`spark-modem` entry point) has its own argparse dispatch (`src/spark_modem/cli/main.py:183-188`) that invokes the subcommand directly — no preflight involvement, no PID lock, no sd_notify.
3. `capture-fleet-fixture` shells out to `qmicli` via `from spark_modem.subproc import runner as subproc_runner; await runner.run([...])`. This is the same import path the production `QmiWrapper` uses (verified at `src/spark_modem/qmi/wrapper.py:23-24`). SP-04 lint applies to every module under `src/spark_modem/` and is **satisfied** because every qmicli invocation goes through `subproc.runner.run`.
4. **The CLI is allowed to invoke `subproc.runner.run` directly.** SP-04 prohibits `create_subprocess_exec` and `subprocess.run` calls _outside_ `subproc/`, not _through_ the wrapper. Example precedent: `src/spark_modem/qmi/wrapper.py:23` imports the runner and uses it — same pattern, same module tier.

### Alternatives considered

| Option | Pro | Con | Verdict |
|--------|-----|-----|---------|
| **CLI bypasses preflight by design** | No new flag; cleanest mental model. Daemon and CLI are separate binaries. | Engineer must remember "you can run capture even on a box with no known-set entry." Mitigated by `RUNBOOK.md` + capture-time message. | **Recommended.** |
| `spark-modem-watchdog --no-preflight` daemon flag | Single binary. | Footgun: a Phase-6 operator hand-runs the daemon with `--no-preflight` to "fix" a broken install and now the X-03 gate silently doesn't fire. Adds a permanent surface to the daemon for a one-shot Phase 5 problem. | Rejected. |
| `spark-modem ctl show-triple` companion verb | Diagnostic value beyond capture. | Two near-identical code paths (compute triple → emit it). `capture-fleet-fixture --dry-run` could print the triple instead, achieving the same diagnostic surface with no new verb. | Rejected (subsume into capture). |

### Concrete entry point shape

```python
# src/spark_modem/cli/ctl/capture_fleet_fixture.py
async def run(args: argparse.Namespace) -> int:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Triple (firmware via qmicli, SDK via Zao log header or version probe,
    #    libqmi via `qmicli --version`).
    triple = await capture_triple()  # see Q3
    (out_dir / "triple.json").write_text(json.dumps(triple, indent=2) + "\n")

    # 2. Per-modem qmicli verbs (6-8 of them; see X-02 list lock at planning).
    qmi_dir = out_dir / "qmi"
    for descriptor in await scan_inventory():
        modem_dir = qmi_dir / descriptor.usb_path  # ADR-0009 usb_path keying
        modem_dir.mkdir(parents=True, exist_ok=True)
        for verb_name, verb_args in QMICLI_CAPTURE_VERBS:
            cp = await subproc_runner.run(
                ["qmicli", "--device-open-proxy",
                 f"--device=/dev/{descriptor.cdc_wdm}", *verb_args],
                timeout_s=8.0,
            )
            redacted = redact_pii_from_raw_qmicli(cp.stdout)
            (modem_dir / f"{verb_name}.txt").write_bytes(redacted)

    # 3. Last 50 RASCOW_STAT lines (see Q5 for zao_log API extension).
    (out_dir / "zao-log-sample.txt").write_bytes(read_last_n_rascow_lines(50))

    return 0
```

`QMICLI_CAPTURE_VERBS` is the locked X-02 list (see Q7 for the recommended 7-verb set).

---

## Q3 — libqmi version detection

**Recommendation:** Use `qmicli --version` stdout parsing via `subproc.runner.run`. This is **already done in production preflight** at `src/spark_modem/daemon/preflight.py:37-40`:

```python
_PREFLIGHT_BINARIES: tuple[tuple[str, list[str]], ...] = (
    ("qmicli", ["--version"]),
    ("ip", ["--version"]),
)
```

The preflight already verifies qmicli is on PATH by calling `qmicli --version`; it discards stdout today. Phase 5 needs to also **parse** that stdout to extract the libqmi version string.

### Implementation

Add a small helper in `src/spark_modem/qmi/version.py` (new module, two functions):

```python
# src/spark_modem/qmi/version.py
import re
from spark_modem.subproc import runner as subproc_runner

_LIBQMI_VERSION_RE = re.compile(r"libqmi-glib\s+(\d+\.\d+\.\d+)", re.IGNORECASE)


async def detect_libqmi_version(*, timeout_s: float = 2.0) -> str:
    """Returns the libqmi-glib version string (e.g. '1.30.6').

    Raises QmiVersionDetectionFailed when qmicli --version stdout can't
    be parsed or the call fails. Caller (preflight) maps this to
    PreflightFailed via the same shape as preflight_check().
    """
    cp = await subproc_runner.run(["qmicli", "--version"], timeout_s=timeout_s)
    if cp.exit_code != 0:
        raise QmiVersionDetectionFailed(stderr=cp.stderr[:512])
    m = _LIBQMI_VERSION_RE.search(cp.stdout.decode("utf-8", errors="replace"))
    if m is None:
        raise QmiVersionDetectionFailed(stdout=cp.stdout[:512])
    return m.group(1)


async def detect_em7421_firmware(*, device: str) -> str:
    """Returns the EM7421 firmware string via qmicli --dms-get-revision.

    Caller (capture-fleet-fixture and the new preflight) handles errors.
    """
    cp = await subproc_runner.run(
        ["qmicli", "--device-open-proxy", f"--device={device}",
         "--dms-get-revision"],
        timeout_s=8.0,
    )
    # parse "Revision: 'SWI9X30C_02.38.00.00'" or equivalent;
    # use ConfigDict(extra='ignore', frozen=True) shape per Plan 02-02
```

### Why this over `dpkg-query -W libqmi-glib5`

| Option | Pro | Con | Verdict |
|--------|-----|-----|---------|
| **`qmicli --version` stdout parse** | Same source the daemon already calls. No new subprocess. Works on any installation method (apt, source build, container). | Need regex (low risk; libqmi has shipped this format for years). | **Recommended.** |
| `dpkg-query -W libqmi-glib5` | Authoritative on apt-installed boxes. | Doesn't work if libqmi was built from source. Adds a second binary dependency. | Rejected. |
| Python module-import probe (`from gi.repository import Qmi`) | Type-safe. | The daemon does not depend on `python3-gi` / introspection bindings; pulling them in just for version detection is a major dep cost. | Rejected. |

### EM7421 firmware via `dms-get-revision`

**This verb is NOT in the current `QmiWrapper`** (verified at `src/spark_modem/qmi/wrapper.py`: methods are `nas_get_signal_info`, `nas_get_serving_system`, `uim_get_card_status`, `wds_get_packet_service_status`, `wds_get_profile_settings`, `wds_get_current_settings`, `dms_get_operating_mode`, `dms_set_operating_mode`, `uim_sim_power_on`, `wds_modify_profile`, `wds_set_ip_family`). Phase 5 must **add** `dms_get_revision` to the wrapper to satisfy X-02 (the triple needs firmware).

**Recommended placement:** new method on `QmiWrapper` following the existing pattern (see `wrapper.py:223-234` for `dms_get_operating_mode` as the analog). Plus a small parser at `src/spark_modem/qmi/parsers/get_revision.py` following the per-libqmi-version fixture tree pattern (Plan 02-02; `tests/fixtures/qmicli/<intent>/<version>/<scenario>.txt`).

### Zao SDK version

The Zao SDK version is **not directly probable**. Two options:

| Option | Source | Verdict |
|--------|--------|---------|
| Parse Zao log header / SDK-banner line | `tail -n 1000 <zao_log_path>` and grep for `zao_remote_endpoint/<version>` or similar | Recommended — needs spike in planning to confirm Zao writes a version banner. |
| `dpkg-query -W soliton-zao-*` | Package metadata | Fallback. Needs dpkg-query subprocess which is currently unused; small new dep. |

**Recommendation:** plan a 30-min spike during Phase 5 planning (not research time — needs a real Zao log sample) to confirm the Zao log banner shape. If a banner exists, parse it; if not, fall back to `dpkg-query`. Either way, the call lands in `src/spark_modem/zao_log/version.py` (new module, ~30 LOC).

---

## Q4 — Daemon preflight slot for X-03

**Recommendation:** New preflight runs **inside the daemon** (not as a systemd `ExecStartPre=`), inserted in `_production_main()` between the existing `await preflight_check()` (line 208) and `acquire_pid_lock()` (line 223).

Concrete edit shape (illustrative — planner names the actual function):

```python
# src/spark_modem/daemon/main.py — between existing line 215 and 217

# Step 3.5: known-fleet triple preflight (X-03, Phase 5 addition).
if not args.skip_preflight:
    try:
        await preflight_check_known_fleet_triple()
    except UnknownFleetTriple as exc:
        try:
            write_last_config_error(run_dir=run_dir, message=str(exc))
        except Exception:
            logger.exception("failed to write last-config-error marker")
        logger.error("unknown fleet triple: %s", exc)
        return 78  # EX_CONFIG
```

### Why in-daemon, not ExecStartPre

| Option | Pro | Con | Verdict |
|--------|-----|-----|---------|
| **In-daemon preflight (proposed)** | Reuses `write_last_config_error` → boot classifier (`lifecycle.classify_prior_run`) reports `CONFIG_INVALID` via `DaemonRestart.reason` (L-04 path). Reuses `--skip-preflight` flag. sd_notify status reports the failure via existing `STATUS=<msg>`. journalctl error has consistent format with kernel/topology probes. Single test surface. | Slightly later in startup than ExecStartPre (sub-second difference). | **Recommended.** |
| systemd `ExecStartPre=spark-modem ctl check-fleet-triple` | Fails before main daemon process boots; clear separation. | Doesn't write `last-config-error` marker (the next-boot classifier path is broken for this failure class). New CLI subcommand needed. journalctl message comes from CLI not daemon. Triple-checks the same binary load. | Rejected. |

### journalctl shape on failure

The existing preflight failure shape (verified at `src/spark_modem/daemon/main.py:208-215`) is:
```
ERROR preflight failed: required binary 'qmicli' not on PATH (FR-60)
```

The X-03 failure should follow the same template:
```
ERROR unknown fleet triple: em7421_firmware=SWI9X30C_02.38.00.00, zao_sdk=2.1.0, libqmi=1.30.6 not in /etc/spark-modem-watchdog/known-fleet/. Run 'spark-modem ctl capture-fleet-fixture --out=/tmp/fixture' and commit the resulting triple.json to tests/fixtures/fleet/<box-id>/ before retrying.
```

### sd_notify on failure

The current path writes `last-config-error`, returns exit code 78, and **does not invoke `sd_notify`** (the daemon hasn't yet built `SdNotifyLifecycle()` at this point — verified at `main.py:225` which constructs sd after PID lock acquisition). Systemd interprets the non-zero exit as a failed start; the boot-classifier next boot reads `last-config-error` and emits `DaemonRestart{reason=CONFIG_INVALID}`. **No additional sd_notify wiring needed for X-03.**

### `--skip-preflight` honors the new check

The existing `--skip-preflight` flag (`main.py:101-104`) bypasses the kernel-binary preflight. **It should also bypass the triple preflight** so a developer can run `spark-modem-watchdog --laptop --skip-preflight` on a non-Jetson host. The new check sits inside the same `if not args.skip_preflight:` block.

---

## Q5 — S-01 #2 "no action on Zao-active line" post-hoc query

**Recommendation:** New `tools/audit_soak_zao.py` script. **NOT** a pytest test and **NOT** a `ctl audit-soak` subcommand.

Rationale:
- The audit runs **once per soak week** by the on-site engineer, not on every commit. Putting it in `tests/` puts it on the CI hot path with no value.
- The audit needs to read **both** `events.jsonl` (for `ActionPlanned` events) **and** the Zao log file at the cycle each action was planned. The Zao log file path is on the production box; a `ctl audit-soak` CLI subcommand could read it, but a one-off `tools/` script with the same reach is lower friction.
- The existing replay-test substrate (`tests/replay/test_v1_agreement.py`) is for **policy** replay, not **observability cross-join**. Wedging the audit in there breaks the test's bounded scope.

### Concrete shape

```python
# tools/audit_soak_zao.py
"""Audits a soak window for S-01 #2 violations:
   any ActionPlanned event whose modem's line was Zao-active at cycle time.

   Reads events.jsonl (+ rotated siblings) and the Zao log; outputs a
   JSON report and exits 0 (clean) or 1 (violations found).
"""

# Reuses src/spark_modem/cli/ctl/history.py:read_events_with_rotated_siblings
# (handles rotated + .gz siblings; verified at history.py:78-101).
# Reuses src/spark_modem/zao_log/parser.py:ZaoLogParser._parse_bytes
# (read the Zao log once into memory; for each ActionPlanned event,
# binary-search backward to the RASCOW_STAT block <= event.ts_iso).

# tools/ is SP-04-exempt (verified at scripts/lint_no_subprocess.sh:11);
# script can use stdlib subprocess if needed (e.g. journalctl), but for
# this query no subprocess is required.
```

### Substrate already exists

- Event reader: `src/spark_modem/cli/ctl/history.py:read_events_with_rotated_siblings` — handles rotated siblings + gzip transparently.
- Zao parser: `src/spark_modem/zao_log/parser.py:ZaoLogParser._parse_bytes` — given a byte range, returns the latest `ZaoSnapshot` with `active_lines: frozenset[int]`.
- The cross-join logic is ~30 LOC. The tool's output is `{violations: int, details: [...]}`.

### Alternatives considered

| Option | Pro | Con | Verdict |
|--------|-----|-----|---------|
| **`tools/audit_soak_zao.py` (new)** | Bounded scope; runs once at soak exit; SP-04 exempt; lowest friction. | New file. | **Recommended.** |
| `ctl audit-soak --since=<dur>` CLI subcommand | Discoverable via `spark-modem ctl --help`. | Adds a permanent subcommand for a Phase 5 one-shot. Couples daemon-version compat to audit tooling. | Rejected. |
| Reuse existing pytest test | No new file. | Audit semantics ≠ test semantics. Pytest fails the build on R-03 breach; we don't want soak-audit failures to break unrelated CI. | Rejected. |

---

## Q6 — S-01 #3 "unexplained Exhausted" detection

**Recommendation:** New `tools/audit_soak_exhausted.py` script that **imports `policy.transitions` and `policy.gates`** and replays the decay logic against the soak-window events.

### Policy module import-safety

Verified at `src/spark_modem/policy/transitions.py:1-19` and `src/spark_modem/policy/gates.py:1-20`: both are pure-function modules with no I/O at import time, no clock/subprocess/network. The package-level lint (`scripts/lint_no_subprocess.sh`) enforces this. **A `tools/` script can safely import them** and run policy functions against synthesized inputs.

Also verified: `src/spark_modem/policy/engine.py:1-23` documents the cycle ordering:
```
1. transition(prior, snap) -> new_state shape
2. healthy_streak: if state == "healthy" then prior + 1 else 0
3. decay-check: if streak >= K then counters = {} and streak = 0
```

The S-01 #3 detector replays this exact ordering against the soak-window events.

### Concrete shape

```python
# tools/audit_soak_exhausted.py
"""Audits a soak window for S-01 #3 violations:
   any state_transition event with new_state='exhausted' that is NOT
   attributable to a genuine non-recoverable hardware fault (M4 / ADR-0006).

   For each exhausted transition, reconstruct the per-modem cycle history
   from events.jsonl, replay the streak+decay logic from
   policy.transitions + policy.engine, and check whether decay should
   have reset counters before exhaust was reached. If yes → unexplained.

   Outputs JSON; exits 0 (clean) or 1 (violations).
"""
from spark_modem.policy.transitions import transition  # pure-fn, import-clean
from spark_modem.policy.gates import gate_exhausted   # pure-fn, import-clean
from spark_modem.policy.engine import _DECAY_K_DEFAULT  # K (default 10)
from spark_modem.wire.state import ModemState
# ...
```

### Definition of "unexplained"

Per CONTEXT.md S-01 #3: "every `exhausted` event must be explainable by genuine non-recoverable hardware, not by counter accumulation."

The detector's heuristic:
- Walk the modem's events backward from the `state_transition(new_state='exhausted')` event to the most recent **first non-healthy cycle**.
- If the modem had ≥K consecutive healthy cycles in that window and counters were NOT reset, → BUG (regression of ADR-0006 amendment; M4 violation).
- If the modem had <K consecutive healthy cycles in the window AND every action in the ladder was attempted → expected exhausted; classified `explained`.
- Edge case: hardware error (`enumeration_overcurrent`, `enumeration_address_fail`) immediately preceding exhausted → `explained`.

### Alternatives considered

Same options table as Q5. Same recommendation reasoning. **`tools/` script over CLI/test.**

---

## Q7 — F-04 "minor violation" / "dispositioned" definitions

**Recommendation (sanity-checked against SLO error-budget and incident-triage practice):**

**"Minor violation"** — a soak-gate breach that satisfies ALL of:
1. **No customer-visible outage** during the violation window. (For S-01 #1 daemon crash: daemon restart completed in <60s and no LTE-bonded uplink was down for the customer due to the crash itself. For S-01 #2 Zao-active action: the planned action did not execute because some other gate also rejected it OR the daemon detected the conflict and aborted. For S-01 #3 unexplained Exhausted: the modem recovered on the next genuine fault without operator intervention.)
2. **Attributable root cause** identified within 24h of detection. ("Cause unknown" is not minor.)
3. **Fixable in <4h of engineering work.** (e.g. config edit + RELOAD_DATA SIGHUP; not "needs new ADR" or "needs schema bump.")

**"Dispositioned"** — ALL of:
1. Root cause filed in repo issues (link in SIGNOFF.md).
2. Fix PR opened (not necessarily merged; PR existence demonstrates triage closure).
3. **Audit-trail entry committed to SIGNOFF.md** with: violation timestamp, gate violated, root cause summary, PR link.

The CONTEXT.md proposed definitions match these closely; the only refinement is the explicit "no customer-visible outage" gate on (1), which is the canonical SLO error-budget framing.

### Industry sanity check

This matches the patterns documented in Google's SRE Workbook (Ch. 16, "Canarying Releases") and Atlassian's incident-severity rubric: a "minor" violation is one where SLO impact is bounded AND a clear remediation path exists within a small budget. The F-04 budget shape ("1 minor/week, 2 resets the clock") is a standard error-budget burndown rule with a hard reset.

### Audit trail enforcement

CONTEXT.md's "the audit trail must record every violation regardless of disposition" is non-negotiable. SIGNOFF.md must include the violations table (see Q8 template). The planner should NOT add automated audit-trail tooling; the on-site engineer fills the table in markdown.

---

## Q8 — SIGNOFF.md template

**Recommendation:** Single markdown file at `.planning/phases/05-bench-field-shadow/SIGNOFF.md` with this structure:

```markdown
# Phase 5 Sign-off — Bench & Field Shadow

**Authored by:** <on-site engineer name>
**Bench Jetson box-id:** <box-id>
**Field box box-id:** <box-id>
**Bench soak start:** <ISO timestamp>
**Bench soak end:** <ISO timestamp>
**Field soak start:** <ISO timestamp>
**Field soak end:** <ISO timestamp>

## S-01 Exit Gates

| Gate | Bench week | Field 2 weeks | Notes |
|------|-----------|---------------|-------|
| #1 Zero daemon crashes (M6) | ✅ / ❌ | ✅ / ❌ | journalctl + DaemonRestart event count |
| #2 Zero action on Zao-active line (ADR-0003) | ✅ / ❌ | ✅ / ❌ | `tools/audit_soak_zao.py` output JSON attached |
| #3 Zero unexplained Exhausted (M4) | ✅ / ❌ | ✅ / ❌ | `tools/audit_soak_exhausted.py` output JSON attached |

## R-02 Replay-harness gate

- **Fault-cycle agreement rate:** XX.X%
- **Bar:** ≥95.0%
- **PASS / FAIL**
- **Artifact:** `artifacts/replay-summary-phase5-exit.json` (committed alongside this file)

## S-01.1 Informational metrics (NOT blocking)

| Metric | Bench week | Field 2 weeks | NFR target |
|--------|-----------|---------------|------------|
| Cycle P99 (M5) | X.X s | X.X s | ≤10 s |
| RSS (NFR-3) | X.X MiB | X.X MiB | ≤80 MiB |

## F-04 Violations log

> Every gate violation MUST be recorded, regardless of disposition.

| Date | Gate | Classification | Root cause | Disposition (issue + PR) | Customer outage? |
|------|------|---------------|------------|--------------------------|------------------|
| (empty if none) | | | | | |

## X-04 Fleet fixtures captured

- [ ] All N field boxes captured at `tests/fixtures/fleet/<box-id>/`
- [ ] Bench Jetson captured
- [ ] Batched Phase-6-prereq PR opened (link: ...)

## Free-text rationale (≤1000 words)

<engineer narrative: what they saw, why they're comfortable signing off, any concerns flagged for Phase 6>

## Phase 6 entry approval

- [ ] All S-01 gates green over both soak windows
- [ ] R-02 replay-harness ≥0.95
- [ ] All fleet boxes have triple in known-set index
- [ ] Violations log dispositioned per F-04

**Approved:** <signature / commit author>
**Date:** <YYYY-MM-DD>
```

### Industry sanity check

This is a standard "release readiness review" or "go/no-go checklist" template. Comparable shapes appear in:
- Google's SRE production-readiness-review (PRR) checklist (sections: SLOs, dependencies, monitoring, runbooks).
- AWS Well-Architected reliability pillar's launch-readiness review (sections: load test, failure mode, recovery, observability).

The Phase 5 version is purpose-fit for the 3 S-01 gates rather than a general PRR. The free-text rationale section is the load-bearing operator artifact — automated checks pass/fail; the engineer's narrative is what makes Phase 6 entry decisions defensible.

### Machine-readable separation

- **Machine-readable artifact:** `artifacts/replay-summary.json` (already produced by `tests/replay/conftest.py:90-93`; Plan 04-07 archives via GitHub upload-artifact). Phase 5 commits a renamed copy at `.planning/phases/05-bench-field-shadow/replay-summary-phase5-exit.json` so it survives Phase 6.
- **Free-text artifact:** the SIGNOFF.md body. No machine parsing needed; reviewer reads it.

---

## Q9 — Bench/field soak runbook

**Recommendation:** New file at `.planning/phases/05-bench-field-shadow/SOAK_RUNBOOK.md`, NOT a `docs/RUNBOOK.md` amendment.

### Why a phase-local runbook

- The Phase 5 soak runbook is **lifecycle-bound**: it describes operator actions during the bench-week-then-field-2-weeks window. After Phase 5 closes (Phase 6 starts), the runbook is historical.
- `docs/RUNBOOK.md` is the **steady-state operator doc** for daemon ops (verified by reading it: §1 install, §2 day-to-day, §3 common problems, §4 state surgery, §5 support bundle, §7 alerting playbook). Adding a Phase 5 soak section there pollutes the steady-state surface with a lifecycle artifact.
- CONTEXT.md "integration points" line 357 says "docs/RUNBOOK.md gets the new 'Phase 5 bench/field soak runbook' amendment + SIGNOFF.md template reference" — **but** the deferred-ideas section also flags doc-rewrite housekeeping as out-of-scope for Phase 5. **Recommendation: phase-local file plus a single cross-reference line in `docs/RUNBOOK.md`** ("Phase 5 soak procedure: see `.planning/phases/05-bench-field-shadow/SOAK_RUNBOOK.md`"). This is a 1-line edit, not a doc rewrite.

### Concrete daily-check shape

Daily operator commands (verified against existing surfaces):

```bash
# Daemon health (M6 gate #1)
journalctl --unit spark-modem-watchdog.service --since "24 hours ago" \
  | grep -E '(error|Main process exited|systemd\[1\]: spark-modem-watchdog)' || echo "no errors"

# Cycle health (M5 informational)
spark-modem status --json | jq '.cycle.last_duration_seconds'
# Prom UDS:
sudo curl --unix-socket /run/spark-modem-watchdog/metrics.sock http://localhost/metrics \
  | grep -E '^(cycle_duration_seconds|modem_state_value|daemon_self_health)'

# State scan (M4 gate #3 incremental check)
sudo cat /var/lib/spark-modem-watchdog/state/by-usb/*.json \
  | jq -c 'select(.state=="exhausted")'

# Action history (gate #2 + #3 audit)
sudo spark-modem ctl history --since=24h | jq -c 'select(.kind=="action_planned")'

# Zao-active vs action cross-check (gate #2 incremental)
# (Full audit at soak exit via tools/audit_soak_zao.py)
```

### Soak-exit procedure

```bash
# 1. Run S-01 audits
python tools/audit_soak_zao.py --events /var/log/spark-modem-watchdog/events.jsonl \
  --zao-log /var/log/zao-remote-endpoint.log \
  --since-iso 2026-05-11T00:00:00Z \
  --out artifacts/soak-zao-violations.json

python tools/audit_soak_exhausted.py --events /var/log/spark-modem-watchdog/events.jsonl \
  --since-iso 2026-05-11T00:00:00Z \
  --out artifacts/soak-exhausted-violations.json

# 2. Run replay harness (R-02)
pytest tests/replay/ -ra --tb=short

# 3. Commit replay-summary + SIGNOFF.md + audit JSONs in one PR
```

---

## Q10 — `.deb` postinst for known-fleet index

**Recommendation:** Use `debian/install` (declarative) rather than `debian/spark-modem-watchdog.postinst` (imperative).

### Concrete edit shape

```
# debian/install — add one line per file pattern
tests/fixtures/fleet/*/triple.json  /etc/spark-modem-watchdog/known-fleet/
```

But `debian/install` doesn't support rename-on-install (the source filename `triple.json` would clobber). Two options:

| Option | Pro | Con | Verdict |
|--------|-----|-----|---------|
| **`debian/rules` `override_dh_auto_install` adds explicit copy with renaming** | Each `<box-id>/triple.json` is copied to `<sha>.json` in the destdir; deterministic from a build script. | Touches `debian/rules` (large file). | **Recommended.** |
| Generate the index files at build time via `tools/build_fleet_index.py` invoked from `debian/rules` | Most flexible. | New tool. Slightly more moving parts. | Acceptable secondary. |
| ship `tests/fixtures/fleet/` directly under `/usr/share/spark-modem-watchdog/known-fleet/` (one subdir per box, contains `triple.json`) | No renaming needed; lookup just walks the directory. | Daemon at preflight walks a directory instead of doing O(1) sha lookup — slower but only at startup; acceptable. | Acceptable simplest. |

**Final recommendation:** **ship `tests/fixtures/fleet/` directly as `/etc/spark-modem-watchdog/known-fleet/<box-id>/triple.json`** (one subdir per box). The daemon preflight reads every `triple.json` at startup (small N — fleet size is single-digit double-digit), computes each triple's sha-equivalence, builds an in-memory set, and checks the local triple against it. This avoids the build-time renaming entirely.

`debian/install` edit:
```
tests/fixtures/fleet  /etc/spark-modem-watchdog/known-fleet/
```

This copies the whole directory tree, preserving the `<box-id>/triple.json` structure.

### Permissions and idempotency

- Files: `0644 root:root` (default `debian/install` mode is fine; daemon runs as root per `debian/spark-modem-watchdog.service:44`, so 0644 is read-fine).
- Atomic install on upgrade: **dpkg handles this** (it stages the upgrade in `/var/lib/dpkg/info/` and atomically replaces files via rename). The known-fleet directory is **owned by the package** (no daemon writes), so upgrade semantics are clean.
- The existing postinst (`debian/spark-modem-watchdog.postinst`) does **not** need modification — it currently masks ModemManager and creates state directories; the known-fleet files are installed via `dh_install` before postinst runs.

---

## Q11 — Validation Architecture (REQUIRED)

> See dedicated Validation Architecture section below.

---

## State of the Art

| Old approach | Current approach | When changed | Impact |
|--------------|------------------|--------------|--------|
| v2 dry-run alongside v1 (MIGRATION Phases 1–2 framing) | v2 live soak (v1 already retired across fleet) | 2026-05-11 (this discuss session) | Entire "shadow mode" code path dropped; ROADMAP SC#1/#2/#3 stale; no `99-shadow.yaml`. |
| Hourly `tools/compare_v1_v2.py` agreement report | Single replay-harness invocation at Phase 5 exit | 2026-05-11 (R-02 locked) | Compare tool not built; eng triggers `pytest tests/replay/` manually before SIGNOFF. |
| Daily synthetic injection on field box | No field injection; bench injection rides existing HIL nightly | 2026-05-11 (F-01 + F-02 locked) | Less fault-path coverage in real conditions; offset by replay-harness against 30-day v1 traces. |
| Zero-tolerance abort on any gate breach | 1-minor-violation-per-week budget per gate | 2026-05-11 (F-04 locked) | More resilient to one-off transients; demands rigorous violation accounting. |

---

## Runtime State Inventory

Phase 5 is a delivery phase that adds one CLI verb + one preflight check + one data shipment + two audit scripts + two markdown files. There is no rename/refactor; no migration of existing state. Below is the inventory for completeness:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — Phase 5 produces NEW data (per-box `triple.json` under `tests/fixtures/fleet/`); no existing data is renamed or migrated. | None. |
| Live service config | None — the systemd unit, postinst, logrotate snippet are unchanged. (1-line `ExecStartPre=` addition for X-03 is deferred per Q4 — handled in-daemon instead.) | None. |
| OS-registered state | None — no new systemd units, no Task Scheduler equivalents (Linux only). | None. |
| Secrets / env vars | None — HMAC secret unchanged; webhook URL unchanged; no new env vars in Phase 5. | None. |
| Build artifacts / installed packages | New `/etc/spark-modem-watchdog/known-fleet/<box-id>/triple.json` files shipped by `.deb` (verified: not present today; first appearance in Phase 5). | dpkg-internal install (no daemon-side migration). |

**Canonical question check:** *After every file in the repo is updated, what runtime systems still have the old string cached, stored, or registered?* — None. Phase 5 adds data, does not rename data.

---

## Environment Availability

| Dependency | Required by | Available on bench / field | Version | Fallback |
|------------|-------------|----------------------------|---------|----------|
| `qmicli` | X-02 fixture capture, X-03 triple detection | ✓ (preflight verifies; `daemon/preflight.py:38`) | libqmi >= 1.30 (Plan 02-02 fixtures cover 1.30 + 1.32) | None — preflight refuses to start without it. |
| `ip` | netns prepend (existing) | ✓ | iproute2 (any) | None. |
| `git-lfs` | R-01 day-1 trace pull | ✓ on dev laptop; not on Jetson | (any modern) | `tools/pull_replay_traces.py:60-75` fails clearly with install instructions. |
| Jetson Orin NX bench (4× EM7421) | F-02 HIL nightly | ✓ (self-hosted runner `[self-hosted, linux, ARM64, hil-bench]` per `.github/workflows/hil.yml:24`) | bench-only | None — Phase 5 fault-injection cadence depends on this. |
| Field box (1× Jetson, customer-active) | S-02 field 2-week soak | ✓ (pre-arranged by R-04 contact) | field-only | None — defines the field soak window. |
| `journalctl` | S-01 #1 detection (daemon crash counting) | ✓ (systemd standard) | (any) | None. |
| Prometheus scraper or `curl --unix-socket` | M5/NFR-3 informational monitoring | ✓ (curl bundled) | (any) | Direct prom-text reads suffice; no central Prom scraper required for Phase 5. |

**No missing dependencies block execution.**

---

## Validation Architecture

> nyquist_validation is enabled (`.planning/config.json:19` `"nyquist_validation": true`).

### Test framework

| Property | Value |
|----------|-------|
| Framework | `pytest >= 8.3` + `pytest-asyncio >= 0.24` (`mode=auto`) — pinned in `pyproject.toml`; verified across Phases 1–4. |
| Config file | `pyproject.toml` (no separate `pytest.ini`); pytest markers registered at `[tool.pytest.ini_options].markers`: `linux_only`, `hil`, `unit`, `integration`. |
| Quick run command | `pytest -q -x tests/unit/cli/test_capture_fleet_fixture.py tests/unit/daemon/test_preflight_triple.py` |
| Full suite command | `pytest tests/ -ra` (Phase 4 baseline: 1835 pass + 88 skip + 0 fail in 17.94s; M7 30s budget preserved). |

### Phase 5 requirements → test map

| Req | Behavior | Test type | Automated command | File exists? |
|-----|----------|-----------|-------------------|--------------|
| X-01 | `spark-modem ctl capture-fleet-fixture --out=<dir>` produces redacted per-box fixture | unit | `pytest tests/unit/cli/ctl/test_capture_fleet_fixture.py -x` | ❌ Wave 0 — new |
| X-02 | Captured fixture contains `triple.json` + per-modem `qmi/<usb_path>/<verb>.txt` + `zao-log-sample.txt` (no PII) | unit (round-trip) | `pytest tests/unit/cli/ctl/test_capture_fleet_fixture_shape.py -x` | ❌ Wave 0 — new |
| X-02 PII | ICCID/IMSI scrubbed in raw qmicli stdout at capture time | unit | `pytest tests/unit/cli/ctl/test_capture_pii_redaction.py -x` | ❌ Wave 0 — new |
| X-03 | Daemon refuses to start when local triple absent from `/etc/spark-modem-watchdog/known-fleet/` | unit | `pytest tests/unit/daemon/test_preflight_triple.py -x` | ❌ Wave 0 — new |
| X-03 happy path | Daemon starts when local triple matches a known-fleet entry | unit | `pytest tests/unit/daemon/test_preflight_triple.py::test_known_triple_passes -x` | ❌ Wave 0 — new |
| X-03 `--skip-preflight` | Honors existing flag | unit | `pytest tests/unit/daemon/test_preflight_triple.py::test_skip_preflight_bypasses_triple_check -x` | ❌ Wave 0 — new |
| X-03 libqmi-version parse | `detect_libqmi_version()` parses `qmicli --version` stdout (fixture-driven) | unit | `pytest tests/unit/qmi/test_version_detection.py -x` | ❌ Wave 0 — new |
| X-03 firmware parse | `QmiWrapper.dms_get_revision` + parser (per-libqmi-version fixture pattern) | unit | `pytest tests/unit/qmi/test_dms_get_revision.py -x` | ❌ Wave 0 — new |
| R-02 gate | `pytest tests/replay/` produces `artifacts/replay-summary.json` with fault-cycle agreement ≥0.95 | manual (Phase 5 exit, one-shot) | `pytest tests/replay/ -ra --tb=short` | ✅ exists |
| F-02 HIL bench-week injection | 12 HIL scenarios pass on nightly cron | manual (rides existing) | `.github/workflows/hil.yml` scheduled | ✅ exists |
| S-01 #2 audit tool | `tools/audit_soak_zao.py` outputs JSON; exit 0 clean, 1 on violations | unit | `pytest tests/unit/tools/test_audit_soak_zao.py -x` | ❌ Wave 0 — new |
| S-01 #3 audit tool | `tools/audit_soak_exhausted.py` replays decay logic against canned events; flags unexplained transitions | unit | `pytest tests/unit/tools/test_audit_soak_exhausted.py -x` | ❌ Wave 0 — new |
| `.deb` known-fleet install | Known-fleet directory ends up at `/etc/spark-modem-watchdog/known-fleet/<box-id>/triple.json` after `apt install` | integration (smoke) | piggyback on existing `scripts/postinst_smoke_test.sh` if extended | ⚠️ extend existing |

### Sampling rate

- **Per task commit:** `pytest -q -x tests/unit/<plan-scope>` (the unit-test subset for the plan being touched).
- **Per wave merge:** `pytest -m "unit or integration"` (full unit + integration suite, M7 ≤30s).
- **Phase gate:** Full suite green + `pytest tests/replay/` green at ≥0.95 + nightly HIL green for at least one cycle within the bench soak week.

### Wave 0 gaps

- [ ] `tests/unit/cli/ctl/test_capture_fleet_fixture.py` — covers X-01 happy path + error paths.
- [ ] `tests/unit/cli/ctl/test_capture_fleet_fixture_shape.py` — round-trip: capture → parse → confirm structure.
- [ ] `tests/unit/cli/ctl/test_capture_pii_redaction.py` — ICCID/IMSI scrubbed in raw qmicli stdout.
- [ ] `tests/unit/daemon/test_preflight_triple.py` — covers X-03 (refuse, pass, skip-flag).
- [ ] `tests/unit/qmi/test_version_detection.py` — `detect_libqmi_version()` against `qmicli --version` fixtures.
- [ ] `tests/unit/qmi/test_dms_get_revision.py` — `QmiWrapper.dms_get_revision` + parser (mirror Plan 02-02 shape).
- [ ] `tests/unit/tools/test_audit_soak_zao.py` — feeds canned events + Zao log → asserts violations.
- [ ] `tests/unit/tools/test_audit_soak_exhausted.py` — feeds canned events → asserts unexplained-vs-explained classification.
- [ ] `tests/fixtures/qmicli/get_revision/1.30/lte_strong.txt` (and 1.32) — per-libqmi-version fixture for new verb.
- [ ] `tests/fixtures/qmicli/version/1.30/standard.txt` (and 1.32) — qmicli `--version` stdout fixtures.
- [ ] **Shared fixture:** `tests/fixtures/fleet/_test/triple.json` (an example fixture; the production index is checked in via Phase 5 X-04 PRs).

### Coverage exclusions (deliberate, documented in plans)

- **Bench / field hardware verification of daemon preflight refusing-to-start:** rides existing HIL nightly (`.github/workflows/hil.yml`); no new HIL scenario file added. Phase 5 piggybacks on the existing infrastructure.
- **`tools/audit_*.py` invocation against real soak-window data:** the audit tools are exercised against canned fixtures in unit tests; their value against real soak data is verified during Phase 5 execution, not at Phase 4 / pre-execution time.

---

## Pitfalls / Landmines

**Anti-patterns from CLAUDE.md that the planner must avoid:**

| Pitfall | Where it can sneak in | Mitigation |
|---------|----------------------|------------|
| `subprocess.run` sync outside `tests/` / `tools/` | `capture-fleet-fixture` lands under `src/spark_modem/cli/ctl/`; SP-04 lint scope **applies**. Engineer might be tempted to `subprocess.run(['qmicli', ...])` directly for "it's a one-shot CLI not the daemon". | **Hard rule:** every qmicli invocation in capture goes through `from spark_modem.subproc import runner as subproc_runner; await runner.run(...)`. Lint will catch a violation. (Verified at `src/spark_modem/qmi/wrapper.py:23` — same pattern.) |
| `cdc-wdmN`-keyed fixture directories | X-02 specifies per-modem subdirs; CONTEXT.md says `qmi/<modem_usb_path>/<verb>.txt`. Engineer might use `cdc-wdm0` for "operator-friendly". | **Hard rule:** ADR-0009; `usb_path` (e.g. `2-3.1.1`) is the per-modem key. Test asserts directory names match `r"^\d+-\d+(\.\d+)+$"`. |
| Best-effort exception-swallowing | `audit_soak_*.py` scripts might be tempted to `try/except/pass` on a malformed `events.jsonl` line. | Follow `cli/ctl/history.py:95-101` pattern: skip corrupt lines silently (events.jsonl integrity is the writer's responsibility) but count them and surface the count in tool output. NOT silent total swallow. |
| Blocking read on `/dev/kmsg` | (Not Phase 5 specific; flagging only because CONTEXT.md doesn't touch kmsg, planner shouldn't add it.) | Phase 5 has zero new kmsg surface. |
| One-hot Prometheus `state` label | Phase 5 RUNBOOK has Prom query examples; engineer might write `modem_state{state="exhausted"}`. | ADR-0013: query `modem_state_value{modem="..."} == 4`. Document this in the soak runbook. |
| `if/elif` on `ModemState` in audit tools | S-01 #3 detector touches `ModemState`. | `match modem_state.state:` per CLAUDE.md and `transitions.py:1-19` precedent. |
| Re-implementing the redaction algorithm | Capture-time PII scrubbing might be hand-rolled. | Reuse `src/spark_modem/cli/redact.py:redact_pii` (sha256[:8] form) — same shape as Plan 02-09 ctl support-bundle and `tests/fixtures/replay/v1-30d/README.md` redaction contract. |
| Daemon writing to `/etc/spark-modem-watchdog/known-fleet/` | A bug could make the daemon mutate the index it's preflight-checking against. | Files are package-owned (dpkg-managed); daemon read-only. Lint or test could pin `grep -r 'known-fleet' src/spark_modem/` to find only **read** patterns. |
| Phase 5 SC#1/#2/#3 literal interpretation | ROADMAP.md still says "v2 in dry-run", "`spark-modem-watchdog-v2.service`", etc. Planner might literally implement these. | CONTEXT.md scope_pivot is canonical; SC#1/#2/#3 are dead. RESEARCH.md "Phase Requirements" section above is the de-facto requirements set. |
| Hot-reloading the known-fleet index without a daemon restart | If X-04 captures a new triple while the daemon is running on that box, daemon won't see the new entry. | NOT a Phase 5 problem because X-04 explicitly happens during physical-access window for Phase 6 prep, after the soak ends. Document in soak runbook: "capture and PR-merge happen with daemon stopped." |

**Off-roadmap policy violations to watch:**

- **`tools/compare_v1_v2.py`:** if any plan references this filename, it's stale. Phase 5 does NOT build this tool (CONTEXT.md scope_pivot line 14).
- **`99-shadow.yaml` / `-v2` paths:** these are dead. v2 runs at `/var/lib/spark-modem-watchdog/`, `/var/log/spark-modem-watchdog/`, `/run/spark-modem-watchdog/` from day 1.
- **Synthetic injection on field box:** F-01 explicitly prohibits. Any plan adding `tests/field/fault_inject.py` or scheduled cron on the field box is a CONTEXT.md violation.
- **`ctl config-check` is referenced by `debian/spark-modem-watchdog.service:17` but NOT implemented** (verified: no file matches `config-check` in `src/spark_modem/cli/`). Pre-existing gap from Plan 02-09 / Plan 03-08; **not Phase 5's problem** but planner should be aware that if SOAK_RUNBOOK.md tells the operator to run `spark-modem ctl config-check`, the command will fail. Either don't mention it, or flag the gap explicitly.

---

## What's already done (the surfaces Phase 5 WIRES, not builds)

| Surface | Path | What it gives Phase 5 |
|---------|------|----------------------|
| `subproc.runner.run` async wrapper | `src/spark_modem/subproc/runner.py:108-196` | SOLE subprocess entry point in `src/`; capture-fleet-fixture imports this. |
| `QmiWrapper` (11 methods) | `src/spark_modem/qmi/wrapper.py:100-342` | 7 of the 8 X-02 verbs are already there. **Only `dms_get_revision` is missing** (Phase 5 must add). |
| Per-libqmi-version fixture tree | `tests/fixtures/qmicli/<intent>/<version>/<scenario>.txt` (Plan 02-02; verified by `cli/clients.py:115-211` FixtureRunner) | X-02 fleet-fixture tree mirrors this exact shape under `tests/fixtures/fleet/<box-id>/qmi/<usb_path>/<verb>.txt`. |
| `ZaoLogParser` + `ZaoSnapshot` | `src/spark_modem/zao_log/parser.py:1-128`; `snapshot.py:15-57` | S-01 #2 audit reuses these directly. X-02 zao-log-sample.txt: a small helper extracts the last 50 RASCOW_STAT lines from the file the parser reads (~20 LOC new helper, or extend `_parse_bytes` with `max_block_count` param). |
| `ctl <verb>` argparse pattern | `src/spark_modem/cli/main.py:119-178` (ctl subparser); existing verbs at `src/spark_modem/cli/ctl/{history,maintenance,support_bundle}.py` | `capture-fleet-fixture` lands as another verb following the same shape: add `add_parser("capture-fleet-fixture")`, `set_defaults(func=ctl_capture.run)`, new module under `cli/ctl/`. |
| `cli/clients.py` fakes (`FixtureRunner`, `_InventoryFromFile`, `build_default_settings`) | `src/spark_modem/cli/clients.py:1-211` | Unit tests for the new verb reuse `FixtureRunner` to fake qmicli, `_InventoryFromFile` for fake modem descriptors. |
| `redact_pii(value: str) -> str` | `src/spark_modem/cli/redact.py:19-28` | Sha256[:8] redaction — same shape as Plan 02-09 + v1-30d README contract. Capture verbal-output redaction reuses this. |
| `read_events_with_rotated_siblings` | `src/spark_modem/cli/ctl/history.py:78-101` | Both audit tools (S-01 #2 + #3) reuse this — handles primary + .1 + .2.gz transparently. |
| Atomic write helpers | `src/spark_modem/state_store/atomic.py:109-166` | Not needed in Phase 5 if known-fleet files are .deb-managed (Q10 recommendation); reserve as fallback. |
| Preflight surface | `src/spark_modem/daemon/preflight.py:1-76` (`PreflightFailed`, `preflight_check`, `write_last_config_error`) + `main.py:206-215` (call site) | New `preflight_check_known_fleet_triple` slots in following this exact shape: same exception class hierarchy, same `write_last_config_error` marker, same exit code 78. |
| Boot classifier (`lifecycle.classify_prior_run`) | (referenced in `daemon/main.py:218`) | Reads `last-config-error` marker; emits `DaemonRestart{reason=CONFIG_INVALID}` on next boot. The new triple-failure path participates uniformly. |
| sd_notify lifecycle | `daemon/lifecycle.py` (`SdNotifyLifecycle`) | NOT invoked for X-03 failure path (daemon hasn't constructed it yet at preflight time). No new wiring needed. |
| `tools/pull_replay_traces.py` | `tools/pull_replay_traces.py:1-110` | R-01 day-1 pull. Phase 5 just runs it; tool is feature-complete. |
| Replay harness | `tests/replay/test_v1_agreement.py:1-160` + `tests/replay/conftest.py:1-101` | R-02 gate. `pytest_sessionfinish` writes `artifacts/replay-summary.json`; hard-fails at <0.95. Plan 04-07 already wires this in `.github/workflows/hil.yml:49-72`. |
| HIL fault-injection helpers | `tests/hil/fault_inject.py:1-148` | F-02 — bench-week injection rides nightly cron unchanged. |
| LFS trace bundle directory | `tests/fixtures/replay/v1-30d/{.gitkeep,.gitattributes,README.md}` | R-01's destination. README documents the redaction contract verbatim. |
| HIL workflow | `.github/workflows/hil.yml:1-99` | F-02 substrate. Scheduled `0 4 * * *` UTC, `cancel-in-progress: false`. No Phase 5 edit. |
| `debian/install` + `debian/rules` + `debian/postinst` | `debian/install` (verified: 4 lines today); `debian/rules:54-127`; `debian/spark-modem-watchdog.postinst:1-58` | X-03's known-fleet directory ships via 1-line addition to `debian/install`. No postinst change. |
| Per-modem state-file shape (ADR-0009 usb_path keying) | `src/spark_modem/state_store/store.py`, `state/by-usb/<usb_path>.json` | Fleet fixture per-modem subdirs use the same `usb_path` convention. Cross-link in test invariant. |
| Pure-function policy package (import-clean) | `src/spark_modem/policy/{transitions.py:1-19, gates.py:1-20, engine.py:1-23}` | S-01 #3 audit tool imports these safely; verified no I/O at import. |

---

## Assumptions Log

> Claims tagged `[ASSUMED]` below need user confirmation in planning before becoming locked decisions.

| # | Claim | Section | Risk if wrong |
|---|-------|---------|---------------|
| A1 | The Zao log file path is `/var/log/zao-remote-endpoint.log` (referenced in `docs/RUNBOOK.md:126`). The SOAK_RUNBOOK.md operator commands hardcode this. | Q9 daily checks | Wrong path → audit script fails. Risk: low (path is set in the YAML config; engineer adapts). |
| A2 | Zao writes a parseable version banner in its log (so SDK version can be extracted from the log itself). | Q3 SDK version | If false, fall back to `dpkg-query -W` (acceptable). Mitigated by Q3 "30-min spike in planning to confirm". |
| A3 | The fleet's box-id namespace is human-assigned (e.g. `bench-jetson-01`, `box-il-13`) and committed in the `tests/fixtures/fleet/<box-id>/` directory structure. | Q1 + Q10 index shape | If the project later wants programmatic IDs (hostname-derived), the `<box-id>` subdir naming may need to change. Cosmetic only; the daemon never reads `<box-id>` (it reads `triple.json` contents). |
| A4 | The `qmicli --version` output format includes `libqmi-glib <version>` (regex `libqmi-glib\s+\d+\.\d+\.\d+`). | Q3 libqmi detection | If libqmi changes its `--version` format in a future release, the parser breaks; same risk class as Plan 02-02 parser drift. Fixture-driven test catches drift. |
| A5 | `qmicli --dms-get-revision` is supported by the EM7421 firmware variants in the fleet and produces a parseable `Revision: '...'` line. | Q3 firmware detection | If wrong, X-02 fixture is incomplete; X-03 preflight has a hole. Mitigated by per-libqmi-version fixture coverage in Plan 02-02 style. |
| A6 | The on-site engineer is the sole human in the Phase 5 loop and authors SIGNOFF.md commits. CONTEXT.md "specifics" line 374 states this. | Q8 SIGNOFF template | If the engineer changes mid-Phase, the audit-trail responsibility transfers; SIGNOFF template accommodates by being a single committed file. |
| A7 | `.deb` install on the bench/field Jetson uses standard `apt install` (not a custom installer). Therefore dpkg-managed file installation semantics apply to the known-fleet directory. | Q10 known-fleet shipment | If the fleet uses a non-dpkg installer (e.g. ansible-managed file deployment), the atomic-replace guarantees differ. Verified against `debian/spark-modem-watchdog.postinst` which is dpkg-shaped, so standard. |
| A8 | The bench Jetson runner for `.github/workflows/hil.yml` (label `[self-hosted, linux, ARM64, hil-bench]`) is the SAME physical box as the Phase 5 bench-week soak Jetson. | F-02 (rides existing HIL nightly) | If they're different boxes, the F-02 fault-injection signal does not pertain to the bench-week soak gate. Verified against Plan 04-06/07 acceptance criteria which name the bench Jetson uniquely; high confidence the same. |
| A9 | The fleet size at Phase 6 cutover is small (single-digit to double-digit boxes), so the directory-of-files known-fleet index has acceptable startup cost (walk N files at preflight, O(N) where N ≤ 100). | Q1 index shape | If the fleet is large (>1000 boxes), single index.json or sha-lookup becomes preferable. PROJECT.md does not state fleet size explicitly. |

---

## Open Questions

1. **Q-A2 above:** does the Zao log write a version banner we can parse for `zao_sdk`?
   - What we know: the parser only looks at `RASCOW_STAT` lines (ADR-0003 amendment).
   - What's unclear: whether Zao writes a startup banner like `zao-remote-endpoint 2.1.0 starting`.
   - Recommendation: planning spike (~30 min) — sample real Zao log; if banner exists, regex-parse; else fall back to `dpkg-query -W soliton-zao-*`.

2. **Q-A3 above:** is `<box-id>` a programmatic ID (hostname-derived) or human-assigned?
   - Implications: same as A3 above.
   - Recommendation: human-assigned at first; engineer commits as `tests/fixtures/fleet/box-<hostname>/triple.json` or `tests/fixtures/fleet/<engineer-friendly-name>/triple.json` — cosmetic, daemon doesn't care.

3. **What happens if the bench-week soak fails the 1-violation budget at violation #2?** CONTEXT.md says "soak clock resets." Open: does the field-deploy timeline also reset, or just bench-week? Recommendation: field timeline waits until **fresh, clean bench-week** completes; this is the conservative reading. Pin in SIGNOFF.md template.

4. **Replay-harness one-shot at Phase 5 exit: is it run on the bench, the dev laptop, or in CI?** R-02 says "manual at Phase 5 exit"; doesn't say where. Recommendation: run on the dev laptop (the fixture set is local LFS; pytest has no hardware dep), commit `replay-summary-phase5-exit.json` from the laptop's `artifacts/`. Document in SOAK_RUNBOOK.md.

---

## Sources

### Primary (HIGH confidence — read in this session)

- `S:\spark\modem-watchdog\.planning\phases\05-bench-field-shadow\05-CONTEXT.md` (locked decisions for this phase)
- `S:\spark\modem-watchdog\.planning\STATE.md` (current phase state + plan-completion summaries)
- `S:\spark\modem-watchdog\.planning\ROADMAP.md` (phase scope; Phase 5 SC#1/#2/#3 read through pivot lens)
- `S:\spark\modem-watchdog\.planning\research\SUMMARY.md` (project research baseline)
- `S:\spark\modem-watchdog\.planning\research\PITFALLS.md` §15.1 (the ≥0.95 fault-cycle gate origin)
- `S:\spark\modem-watchdog\docs\MIGRATION.md` §3, §4, §10 (stale framing — read for context)
- `S:\spark\modem-watchdog\docs\RECOVERY_SPEC.md` §8 (cycle ordering)
- `S:\spark\modem-watchdog\docs\RUNBOOK.md` (operator doc — phase-5 amendment target evaluated)
- `S:\spark\modem-watchdog\docs\adr\0003-zao-authority.md` (S-01 #2 root)
- `S:\spark\modem-watchdog\docs\adr\0006-counter-decay.md` (S-01 #3 root)
- `S:\spark\modem-watchdog\docs\adr\0008-state-machine-5-plus-2.md` (exhausted state shape)
- `S:\spark\modem-watchdog\docs\adr\0013-metric-surface.md` (soak monitoring substrate)
- `S:\spark\modem-watchdog\src\spark_modem\cli\main.py` (argparse subparser pattern)
- `S:\spark\modem-watchdog\src\spark_modem\cli\ctl\support_bundle.py` (PII redaction pattern)
- `S:\spark\modem-watchdog\src\spark_modem\cli\ctl\history.py` (events.jsonl reader)
- `S:\spark\modem-watchdog\src\spark_modem\cli\clients.py` (FixtureRunner + fakes)
- `S:\spark\modem-watchdog\src\spark_modem\cli\redact.py` (sha256[:8] redaction)
- `S:\spark\modem-watchdog\src\spark_modem\qmi\wrapper.py` (11 qmicli methods — confirmed dms_get_revision IS NOT present)
- `S:\spark\modem-watchdog\src\spark_modem\zao_log\parser.py` (RASCOW_STAT parser)
- `S:\spark\modem-watchdog\src\spark_modem\zao_log\snapshot.py` (ZaoSnapshot shape)
- `S:\spark\modem-watchdog\src\spark_modem\daemon\main.py` (preflight call site, slot for X-03)
- `S:\spark\modem-watchdog\src\spark_modem\daemon\preflight.py` (PreflightFailed pattern)
- `S:\spark\modem-watchdog\src\spark_modem\subproc\runner.py` (SP-04 anchor module)
- `S:\spark\modem-watchdog\src\spark_modem\policy\engine.py` (cycle ordering — verified import-clean)
- `S:\spark\modem-watchdog\src\spark_modem\policy\transitions.py` (pure-fn; safe to import from tools/)
- `S:\spark\modem-watchdog\src\spark_modem\policy\gates.py` (pure-fn; safe to import from tools/)
- `S:\spark\modem-watchdog\src\spark_modem\state_store\atomic.py` (atomic_write_bytes shape)
- `S:\spark\modem-watchdog\src\spark_modem\state_store\locks.py` (3-layer locking)
- `S:\spark\modem-watchdog\tools\pull_replay_traces.py` (R-01 day-1 pull tool)
- `S:\spark\modem-watchdog\tests\replay\test_v1_agreement.py` (R-02 gate substrate)
- `S:\spark\modem-watchdog\tests\replay\conftest.py` (R-03 hard-fail at <0.95)
- `S:\spark\modem-watchdog\tests\fixtures\replay\v1-30d\README.md` (redaction contract)
- `S:\spark\modem-watchdog\tests\hil\fault_inject.py` (F-02 helpers)
- `S:\spark\modem-watchdog\.github\workflows\hil.yml` (F-02 nightly cron)
- `S:\spark\modem-watchdog\debian\spark-modem-watchdog.install` (X-03 known-fleet shipment target)
- `S:\spark\modem-watchdog\debian\spark-modem-watchdog.postinst` (no Phase 5 edit needed)
- `S:\spark\modem-watchdog\debian\spark-modem-watchdog.service` (ExecStartPre pattern; preflight slot consideration)

### Secondary (industry sanity-check inputs)

- Google SRE Workbook Ch. 16 "Canarying Releases" — error-budget framing for F-04 "minor violation" definition (Q7).
- AWS Well-Architected reliability pillar launch-readiness review — SIGNOFF.md structure precedent (Q8).
- Standard SLO triage rubric — Q7 "no customer-visible outage" sanity check.

### Tertiary (LOW confidence — flagged for validation in planning)

- Zao log version banner shape (A2): not verified in this research session.
- EM7421 firmware variants `qmicli --dms-get-revision` output (A5): not verified against real-fleet samples.

---

## Metadata

**Confidence breakdown:**
- Existing-code surfaces (what Phase 5 wires): **HIGH** — every path/line cited above was read in this session.
- Recommended decisions (Q1, Q2, Q4, Q5, Q6, Q9, Q10): **MEDIUM-HIGH** — backed by code precedent in this codebase.
- Definitions (Q7) + template (Q8): **MEDIUM** — backed by industry practice but project-specific wording is at planner discretion.
- Spike-required items (Q3 Zao SDK; A2/A5): **LOW** — need real-fleet samples not present in repo.
- Anti-pattern catalogue (Pitfalls section): **HIGH** — directly cites CLAUDE.md.

**Research date:** 2026-05-11
**Valid until:** 2026-06-10 (30 days; stable phase scope locked by CONTEXT.md).

---

## RESEARCH COMPLETE