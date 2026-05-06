---
phase: 01-foundations-adrs
verified: 2026-05-06T00:00:00Z
status: human_needed
score: 4/5 must-haves verified
overrides_applied: 0
gaps:
  - truth: "arm64 .deb builds in CI from requirements.lock and all 10 libs import cleanly on a real Jetson Orin NX"
    status: partial
    reason: "All build artifacts exist and are well-formed; postinst smoke test imports all 10 libs correctly. However, actual install on a real Jetson Orin NX with JetPack 5.1.5 / Ubuntu 20.04 / aarch64 hardware cannot be verified on this Windows host. Additionally, two code-review findings affect this SC: (WR-010) postinst runs smoke test BEFORE creating the system user — if the smoke test fails, the package is left in an unrecoverable half-configured state; (CR-001) systemd unit runs as root with NoNewPrivileges=false and no CapabilityBoundingSet, which undermines the LoadCredential= design intent."
    artifacts:
      - path: "debian/spark-modem-watchdog.postinst"
        issue: "WR-010: smoke test executes before adduser/install-d steps (lines 7-12 vs 20+). A failing smoke test leaves no system user, no directories, and ModemManager not masked — partial install state that dpkg cannot cleanly recover from."
      - path: "debian/spark-modem-watchdog.service"
        issue: "CR-001: User=root, NoNewPrivileges=false, no CapabilityBoundingSet. Runs as root with the bundled Python importing pyroute2/pyudev/httpx — broader than needed and undermines LoadCredential= isolation intent for Phase 1."
    missing:
      - "Move adduser/install-d/ModemManager mask BEFORE smoke test in postinst (WR-010 fix)"
      - "Add systemd hardening: NoNewPrivileges=true, CapabilityBoundingSet=, RuntimeDirectory=spark-modem-watchdog, RestrictAddressFamilies=, SystemCallFilter=@system-service, ProtectKernelTunables=true (CR-001 fix)"
      - "Live Jetson hardware test: arm64 .deb install with postinst smoke test passing end-to-end"
human_verification:
  - test: "Install the .deb on a fresh Jetson Orin NX (JetPack 5.1.5 / Ubuntu 20.04 / aarch64) and verify all 10 runtime libs import under /opt/spark-modem-watchdog/python/bin/python3.12"
    expected: "apt install succeeds, postinst smoke test prints 'OK: all 10 runtime libs import', systemctl start spark-modem-watchdog reports active (running) after ExecStartPre= smoke test passes, no errors in journalctl -u spark-modem-watchdog"
    why_human: "Requires aarch64 Linux hardware; cannot be verified on Windows host. The CI pipeline builds for arm64 on a self-hosted runner, but actual on-device install and runtime behavior requires the Jetson target."
  - test: "Verify .deb size is ≤ 40 MiB (NFR-51) after a real dpkg-buildpackage run on the arm64 CI runner"
    expected: "stat -c %s *.deb produces a value ≤ 41,943,040 bytes; the CI workflow's size check exits 0"
    why_human: "The .deb is built at CI time on the aarch64 self-hosted runner. The repo ships build instructions, not a pre-built .deb. Size can only be measured after a real build."
  - test: "Verify systemctl reload and SIGHUP transactional config reload wiring (FR-54) on the Jetson"
    expected: "Data-only fields (carrier table, thresholds) update transactionally; topology-affecting fields emit 'restart required' log and are not applied (Phase 3 full behavior deferred, but config parsing must work)"
    why_human: "Config reload behavior requires a running daemon and a real systemd signal delivery; the placeholder ExecStart= exits immediately so this cannot be verified until Phase 2."
---

# Phase 1: Foundations & ADRs Verification Report

**Phase Goal:** Lock the wire formats, packaging story, ADR set, and plumbing skeleton so that no
Phase 2 module is ever built against a wire type that needs to change. By exit, a `.deb` containing
CPython 3.12 and all 10 runtime libs installs cleanly on a real Jetson, every open question from
PROJECT.md is closed by an ADR or explicit deferral, and the `wire/`, `config/`, `clock/`,
`subproc/`, `state_store/`, `event_logger/` modules exist with mypy --strict and ruff green in CI.

**Verified:** 2026-05-06
**Status:** human_needed (4/5 SCs verified; SC#1 requires Jetson hardware + has two code-review items)
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC#1 | arm64 .deb builds in CI from requirements.lock; all 10 libs import on a real Jetson | PARTIAL | Build artifacts verified (debian/*, requirements.lock, 10-lib smoke test script). Hardware install unverifiable on Windows host. WR-010 (postinst ordering) + CR-001 (unit hardening) unresolved. |
| SC#2 | All Q1-Q8 closed by ADRs (0001/0003/0004/0005/0006 amended + 0008..0013 new) | VERIFIED | 14 ADR files exist; all 5 amendments confirmed present; ADR-0005 marked Superseded by ADR-0008; docs/adr/README.md maps all Q1-Q8 to closing ADRs. |
| SC#3 | Day-one carrier YAML covers IL/US/GB/DE with hostile-input fixtures + Norway-problem coverage | VERIFIED | debian/conf.d/00-carriers.yaml: 12 entries (IL×3, US×3, GB×3, DE×3); 8 hostile fixture files; 12 carrier wire tests pass; 8 integration tests pass (including Norway problem, leading-zero MNC, MNC-as-int rejection). |
| SC#4 | mypy --strict + ruff green on 6 plumbing modules; SP-04 lint gate (no subprocess outside subproc/) | VERIFIED | mypy: "Success: no issues found in 30 source files"; ruff check: "All checks passed"; ruff format --check: "30 files already formatted"; bash scripts/lint_no_subprocess.sh → exit 0. |
| SC#5 | State files round-trip under state/by-usb/<usb_path>.json with atomic write + inventory cross-check | VERIFIED | paths.py uses state/by-usb/<usb_path>.json (ADR-0009 keying); atomic.py has temp+fsync+rename+dirfsync recipe; hypothesis crosscheck test passes (UsbPathMismatch raised on mismatch); 61 state_store tests pass (17 skipped — flock/POSIX-only, correct on Windows). |

**Score:** 4/5 truths verified (SC#1 partial — Jetson hardware + code-review items)

---

### Required Artifacts

#### SC#1 — Packaging Pipeline

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `debian/control` | Architecture: arm64, Depends on libqmi-utils/iproute2/systemd | VERIFIED | Architecture: arm64; Depends declared correctly |
| `debian/rules` | PBS download + SHA256 verify + uv frozen install + compileall + SOURCE_DATE_EPOCH | VERIFIED | Full 5-step recipe implemented; sha256sum -c before unpack; uv pip install --no-deps --frozen; compileall under SOURCE_DATE_EPOCH |
| `debian/python.sha256` | SHA256 of cpython-3.12.x+<datetag>-aarch64 tarball | VERIFIED | cpython-3.12.13+20260504-aarch64-unknown-linux-gnu-install_only.tar.gz with hash |
| `scripts/postinst_smoke_test.sh` | Imports all 10 libs under bundled python3.12 | VERIFIED | Imports: pydantic, pydantic_settings, yaml, prometheus_client, pyudev, pyroute2, asyncinotify, httpx, sdnotify, psutil |
| `debian/spark-modem-watchdog.postinst` | Smoke test + user creation + dir creation + ModemManager mask | STUB | Smoke test runs BEFORE adduser/install-d (WR-010 — partial install state on failure) |
| `debian/spark-modem-watchdog.service` | Type=notify + ExecStartPre= smoke test + LoadCredential= | PARTIAL | Type=notify + ExecStartPre= + LoadCredential= present; User=root + NoNewPrivileges=false (CR-001 — hardening missing) |
| `.github/workflows/build-deb.yml` | Triggers on push/PR; runs on self-hosted ARM64; size ≤ 40 MiB gate | VERIFIED | Triggers on push/PR/workflow_dispatch; runs-on: [self-hosted, linux, ARM64]; dpkg-deb -I + size check (test "$SIZE_MIB" -le 40) |
| `packaging/requirements.lock` | uv pip compile output with --generate-hashes for 10 libs | VERIFIED | 243 SHA256 hashes; 20 packages (10 direct + 10 transitive); --python-version 3.12 --python-platform linux |

#### SC#2 — ADR Set

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `docs/adr/0001-language-python.md` | Amended: CPython 3.12 via PBS; closes Q8 | VERIFIED | "## Amendment 2026-05-06" section + python-build-standalone content present |
| `docs/adr/0003-zao-authority.md` | Amended: parser surface bound to RASCOW_STAT; closes Q3 | VERIFIED | "## Amendment 2026-05-06" + RASCOW_STAT + Zao SDK 2.1.0 present |
| `docs/adr/0004-typed-contract.md` | Amended: schema downgrade non-destructive (shadow + pending event) | VERIFIED | "## Amendment 2026-05-06" + from-v<N>.json + schema_downgrade_pending present |
| `docs/adr/0005-explicit-state-machine.md` | Status: Superseded by ADR-0008 | VERIFIED | "Superseded by ADR-0008" in status block + "## Superseded 2026-05-06" section |
| `docs/adr/0006-counter-decay.md` | Amended: streak persistence + atomic single-write per cycle | VERIFIED | "## Amendment 2026-05-06" + "ONE atomic write per cycle" content |
| `docs/adr/0008-state-machine-5-plus-2.md` | New; Status: Accepted; Supersedes: ADR-0005 | VERIFIED | File exists; references ADR-0005 supersession |
| `docs/adr/0009-state-files-keyed-by-usb-path.md` | New; state/by-usb pattern; usb_path cross-check | VERIFIED | File exists; "state/by-usb" content present |
| `docs/adr/0010-packaging-python-build-standalone.md` | New; closes Q8; PBS + uv + custom debhelper | VERIFIED | File exists; python-build-standalone + Q8 reference |
| `docs/adr/0011-webhook-subsystem.md` | New; HMAC-SHA256 v2.0; closes Q5; Q1/Q2/Q4 notes | VERIFIED | File exists; HMAC + X-Spark-Signature/Timestamp + Q5 present |
| `docs/adr/0012-concurrency-locks.md` | New; per-modem asyncio.Lock + flock; PID lock separate | VERIFIED | File exists; per-modem lock + flock content |
| `docs/adr/0013-metric-surface.md` | New; integer-encoded modem_state_value{modem} | VERIFIED | File exists; modem_state_value + state_to_int present |
| `docs/adr/README.md` | Status table for all 13 ADRs + Q1-Q8 mapping | VERIFIED | 14 ADR files in docs/adr/ (including README.md); all Q1-Q8 mapped |

#### SC#3 — Carrier Table

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `debian/conf.d/00-carriers.yaml` | IL/US/GB/DE; IL unverified=false; US/GB/DE unverified=true | VERIFIED | 12 entries: IL×3 (unverified=false), US×3, GB×3, DE×3 (all unverified=true); uses GB not UK (correct ISO) |
| `tests/fixtures/wire/carriers/hostile_norway_problem.yaml` | YAML 1.1 NO boolean problem fixture | VERIFIED | File exists; tests confirm NO is rejected when not quoted |
| `tests/fixtures/wire/carriers/hostile_*.yaml` | Leading-zero MNC, MNC-as-int, missing-apn, extra-field, mixed-case-country | VERIFIED | 7 hostile fixtures; 12 carrier tests pass; 8 integration tests pass |

#### SC#4 — Six Plumbing Modules + Lint Gates

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/spark_modem/wire/` | BaseWire, ModemState 5+2, Diag, PlannedAction, StateTransition, enums, versioning | VERIFIED | 10 files; exports 41 public names; mypy/ruff green |
| `src/spark_modem/clock/` | monotonic(), wall_clock_iso(), ADR-0007 compliance | VERIFIED | clock.py; never calls time.time() for durations |
| `src/spark_modem/subproc/` | run() with SP-03 invariants: list-argv, LC_ALL=C, start_new_session, two-stage SIGTERM→SIGKILL | VERIFIED | runner.py, result.py, errors.py; CompletedProcess errors-as-data |
| `src/spark_modem/config/` | Settings with env+flag+YAML layering; reload markers; CarrierTable loading | VERIFIED | settings.py, yaml_merge.py, reload_marker.py |
| `src/spark_modem/state_store/` | atomic.py, locks.py, paths.py, inventory.py, store.py, errors.py | VERIFIED | 6 files; state/by-usb keying; 3-layer locking scaffolded |
| `src/spark_modem/event_logger/` | writer.py with O_APPEND atomic JSON Lines | VERIFIED | writer.py; os.write of single byte-sequence |
| `scripts/lint_no_subprocess.sh` | SP-04 gate: no subprocess outside subproc/ | VERIFIED | Exit 0 on clean tree; catches create_subprocess_exec, subprocess.run, os.system |
| `.github/workflows/ci.yml` | self-hosted ARM64; ruff + mypy + SP-04 + pytest in CI | VERIFIED | runs-on: [self-hosted, linux, ARM64]; lint-and-types + tests jobs |

#### SC#5 — State Store Atomic Write + Inventory Cross-Check

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/spark_modem/state_store/paths.py` | state/by-usb/<usb_path>.json layout | VERIFIED | state_by_usb_dir() + state_file_for_modem(); ADR-0009 explicitly cited in docstrings |
| `src/spark_modem/state_store/atomic.py` | temp + os.fsync + os.replace + dir fsync | VERIFIED | 6-step recipe: write → fsync → close → os.replace → _fsync_directory |
| `src/spark_modem/state_store/store.py` | atomic save + schema downgrade shadow | PARTIAL | Atomic save wired; schema downgrade uses target.rename(shadow) not os.replace (CR-002) + no dirfsync after rename (CR-002); UsbPathMismatch also conflates I/O errors (WR-002) |
| `src/spark_modem/state_store/inventory.py` | cross_check_inventory; walk_sysfs_for_qmi_modems | VERIFIED | cross_check_inventory raises UsbPathMismatch on mismatch; 61 tests pass |
| `tests/unit/state_store/test_inventory_crosscheck.py` | Hypothesis property test for random USB renumbering | VERIFIED | @given + @settings; UsbPathMismatch raised on every mismatch; round-trips on consistent state |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `docs/adr/0008-state-machine-5-plus-2.md` (Supersedes) | `docs/adr/0005-explicit-state-machine.md` (Status: Superseded) | Reciprocal status markers | WIRED | ADR-0008 references ADR-0005; ADR-0005 has Superseded status |
| `docs/adr/0009-state-files-keyed-by-usb-path.md` | `src/spark_modem/state_store/paths.py` | state/by-usb/ path layout | WIRED | paths.py docstring cites ADR-0009 explicitly |
| `docs/adr/0010-packaging-python-build-standalone.md` | `debian/rules` + `packaging/requirements.lock` | PBS build recipe | WIRED | debian/rules implements the 5-step recipe from ADR-0010 |
| `docs/adr/0013-metric-surface.md` | `src/spark_modem/wire/state.py state_to_int` | integer encoding 0-4 | WIRED | state_to_int() implements ADR-0013's canonical mapping; exported in wire/__init__.py |
| `scripts/postinst_smoke_test.sh` | `debian/spark-modem-watchdog.postinst` + `debian/spark-modem-watchdog.service` | ExecStartPre= + postinst configure | WIRED | Both call the smoke script (B-03 belt-and-suspenders) |
| `packaging/requirements.lock` | `debian/rules` (uv pip install --frozen -r) | uv frozen install in build | WIRED | debian/rules line: `uv pip install --no-deps --frozen -r packaging/requirements.lock` |

### Data-Flow Trace (Level 4)

Not applicable for Phase 1 — no components render dynamic data from a live source. All modules are
plumbing (wire types, config, clock, subprocess runner, state store, event logger) with no data
pipeline rendering. Data-flow verification is deferred to Phase 2 (daemon cycle + metrics endpoint).

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| mypy --strict on 6 plumbing modules | `.venv/Scripts/mypy.exe --strict src/spark_modem/{wire,clock,subproc,config,state_store,event_logger}` | "Success: no issues found in 30 source files" | PASS |
| ruff check on 6 plumbing modules | `.venv/Scripts/ruff.exe check src/spark_modem/{wire,...}` | "All checks passed!" | PASS |
| ruff format --check | `.venv/Scripts/ruff.exe format --check ...` | "30 files already formatted" | PASS |
| SP-04 lint gate | `bash scripts/lint_no_subprocess.sh` | Exit 0 | PASS |
| All unit + integration tests | `python -m pytest tests/unit/ tests/integration/ -q` | 261 passed, 41 skipped in 5.89s | PASS |
| Carrier wire tests (12 tests) | `pytest tests/unit/wire/test_carriers.py` | 12 passed | PASS |
| Carrier integration tests (8 tests) | `pytest tests/integration/test_default_carrier_table.py` | 8 passed | PASS |
| Hypothesis inventory crosscheck | `pytest tests/unit/state_store/test_inventory_crosscheck.py` | 1 passed, 1 skipped (n==1 has no permutation effect) | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| FR-30.1 | 01-06 | Day-one carrier coverage IL/US/UK/DE | SATISFIED | debian/conf.d/00-carriers.yaml: 12 entries across 4 countries; integration tests pass |
| FR-33.1 | 01-03 | Carrier-table hostile-input validation | SATISFIED | 7 hostile fixtures; 12 wire tests + 8 integration tests pass; Norway-problem fixture confirmed |
| FR-44.1 | 01-03/01-11 | HMAC-SHA256 signing wire shapes + ADR | SATISFIED | wire/webhook.py has WebhookPayload/WebhookEnvelope; ADR-0011 documents decision; Phase 2 implements WebhookPoster |
| FR-44.2 | 01-03/01-11 | X-Spark-Timestamp replay protection | SATISFIED | wire/webhook.py WebhookEnvelope has timestamp field; ADR-0011 specifies it |
| FR-54 | 01-06 | Layered config: flags > env > YAML > defaults; SIGHUP reload markers | SATISFIED | config/settings.py + yaml_merge.py + reload_marker.py; SIGHUP listener deferred to Phase 3 |
| FR-60 | 01-02 | Refuse to start if bundled python/qmicli absent; smoke test | SATISFIED | ExecStartPre= smoke test + postinst smoke test (B-03 dual gate) |
| FR-62 | 01-04 | Atomic file writes (temp+rename+dirfsync) | SATISFIED | state_store/atomic.py implements 6-step recipe |
| FR-62.1 | 01-04 | State files keyed by usb_path; startup cross-check raises error on mismatch | SATISFIED | paths.py + inventory.py; UsbPathMismatch raised on mismatch; hypothesis test passes |
| FR-63 | 01-06 | Validate external input; logged error not crash | PARTIAL | Wire types validate external input (pydantic extra=forbid); yaml_merge.py silently drops invalid YAML files without logging (WR-005 — no log output on bad YAML in Phase 1) |
| FR-64 | 01-05 | Never exec a string from external data; list-form argv only | SATISFIED | subproc/runner.py _validate_argv enforces list[str]; SP-04 lint gate enforces boundary |
| FR-72 | 01-03 | External-IO seams behind Protocol types | PARTIAL | Wire DATA types (Diag, PlannedAction, ModemState) define seam shapes. Formal typing.Protocol CLASS declarations (QmiClient, ZaoLogTailer, WebhookPoster, MetricRegistry, PIDLock, SignalHandler) not yet defined — the module implementations exist (runner.py, clock.py, store.py, writer.py) but no Protocol interfaces declared. Phase 1 plan's must_haves did not require Protocol classes; treated as deferred to Phase 2 when policy/ module needs them. |
| FR-73 | 01-03 | Policy engine is a pure function | PARTIAL | Wire types define the function signature (Diag → PlannedAction[]). No policy/ module exists yet — implementation is Phase 2. Phase 1 establishes the input/output wire types; the invariant is enforced at the type level by the wire shapes. |
| NFR-31 | 01-05 | All subprocess calls list-form argv | SATISFIED | runner.py _validate_argv raises TypeError on non-list; SP-04 gate enforces boundary |
| NFR-32 | 01-03/01-05 | External text inputs parsed by validators | SATISFIED | Pydantic models with extra=forbid; StrictStr + pattern validation in carriers |
| NFR-33 | 01-06 | Webhook URLs https:// only by default | SATISFIED | settings.py webhook_url validator checks scheme prefix (WR-007 notes it could be stronger with urlsplit but core requirement is met) |
| NFR-34 | 01-02 | HMAC secret via LoadCredential=; never on disk | SATISFIED | debian/spark-modem-watchdog.service has LoadCredential=spark-modem-watchdog.hmac-secret |
| NFR-40 | 01-01 | mypy --strict, ruff check, ruff format --check in CI | SATISFIED | mypy: 0 issues; ruff: all passed; CI workflow wired |
| NFR-41 | 01-01 | Unit tests hardware-free | SATISFIED | 261 passed, 41 skipped (POSIX-only skips are correct; all tests run on Windows dev host) |
| NFR-43 | 01-03/01-04 | Schema-version refusal of future versions | SATISFIED | versioning.py raises SchemaVersionTooNew; test_schema_downgrade.py passes |
| NFR-50 | 01-02 | .deb distributes arm64 venv at /opt/spark-modem-watchdog/python/ | SATISFIED | debian/control Architecture: arm64; debian/rules installs to /opt/...python/ |
| NFR-51 | 01-02 | .deb size ≤ 40 MiB | NEEDS HUMAN | CI workflow has size gate (test "$SIZE_MIB" -le 40) but requires actual aarch64 build to measure |
| NFR-52 | 01-01 | requirements.lock from uv pip compile; committed for reproducibility | SATISFIED | packaging/requirements.lock: 243 hashes; committed to repo |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `debian/spark-modem-watchdog.postinst` | 7-12 | Smoke test runs BEFORE system user creation (WR-010) | Warning | On smoke-test failure, package is left half-configured (no user, no dirs, ModemManager not masked); dpkg status file may need hand-editing to recover |
| `debian/spark-modem-watchdog.service` | 24,26 | User=root + NoNewPrivileges=false + no CapabilityBoundingSet (CR-001) | Warning | Daemon runs with full root capabilities; LoadCredential= design intent undermined; Phase 4 will need capabilities anyway but Phase 1 hardening should be added now |
| `src/spark_modem/state_store/store.py` | 234, 323 | target.rename(shadow) not os.replace; no dirfsync after rename (CR-002) | Warning | On POSIX, rename is atomic but clobber semantics differ from os.replace on Windows; missing dirfsync after the downgrade rename means a power loss between rename and subsequent write can cause the rename to be lost (state file reappears at original location on remount) |
| `src/spark_modem/state_store/store.py` | 209-227 | OSError + ValueError caught and re-raised as UsbPathMismatch (WR-002) | Warning | Disk I/O errors and corrupt JSON are misclassified as inventory mismatches; operator receives wrong sd_notify STATUS= and follows wrong runbook |
| `src/spark_modem/config/yaml_merge.py` | 45-53 | Invalid YAML silently dropped with no log output (WR-005) | Warning | Violates FR-63 ("logged error, not crash"); operator misconfiguration is invisible in Phase 1 |
| `src/spark_modem/state_store/locks.py` | 250-271 | AsyncFlockHandle leaked if coroutine cancelled between to_thread return and caller resume (WR-001) | Warning | fd remains open and flocked; no __del__ to release; relevant when Phase 2 wires actual callers |
| `src/spark_modem/subproc/runner.py` | 207-211 | Second proc.communicate() after SIGKILL has no timeout (WR-004) | Warning | Can hang indefinitely if process group is stuck; relevant to M5 (P99 cycle ≤ 10 s) |
| `src/spark_modem/subproc/runner.py` | 48-66 | Empty string argv[0] passes _validate_argv (WR-003) | Info | Produces confusing ENOENT on spawn |
| `src/spark_modem/state_store/inventory.py` | 50-58 | read_text() without encoding="ascii" + silent EACCES skip (WR-006) | Info | Low-likelihood UnicodeDecodeError on misconfigured locale; EACCES silently hides permission issues |
| `src/spark_modem/state_store/store.py` | 462-464 | _now_iso() duplicates wall_clock_iso() from clock module (IN-003) | Info | Violates "never call time.time() directly outside clock module" discipline |

### Human Verification Required

#### 1. Jetson Hardware Install Test (SC#1 gate)

**Test:** Install the built arm64 .deb on a fresh Jetson Orin NX (JetPack 5.1.5 / Ubuntu 20.04 / aarch64):
```bash
apt install ./spark-modem-watchdog_2.0.0-*_arm64.deb
systemctl start spark-modem-watchdog.service
journalctl -u spark-modem-watchdog --no-pager -n 30
/opt/spark-modem-watchdog/python/bin/python3.12 -c "import pydantic,pydantic_settings,yaml,prometheus_client,pyudev,pyroute2,asyncinotify,httpx,sdnotify,psutil; print('all 10 libs OK')"
```
**Expected:** apt install exits 0; postinst smoke test prints "OK: all 10 runtime libs import under /opt/spark-modem-watchdog/python/bin/python3.12"; `systemctl status spark-modem-watchdog` shows active (ExecStartPre= smoke test passes before the placeholder ExecStart=); no errors in journal.

**Why human:** Requires aarch64 Linux hardware with JetPack 5.1.5. The CI workflow builds and smoke-installs in an ubuntu:20.04 arm64 Docker container on the self-hosted runner, but actual on-device validation (correct glibc version, correct sysfs layout, correct kernel, ModemManager masking working) requires the real Jetson target.

#### 2. .deb Size Verification (NFR-51)

**Test:** After a real dpkg-buildpackage run on the aarch64 CI runner, check the .deb size:
```bash
DEB=$(ls dist/spark-modem-watchdog_*_arm64.deb | head -n1)
stat -c %s "$DEB" | awk '{printf "%s bytes = %.1f MiB\n", $1, $1/1048576}'
```
**Expected:** Size ≤ 41,943,040 bytes (≤ 40 MiB). CI workflow already has this gate; manual verification confirms the gate fires correctly.

**Why human:** The repo ships build instructions, not a pre-built .deb. Cannot measure size without running the build on aarch64.

---

### Gaps Summary

The phase comes very close to full goal achievement. The two outstanding items are:

**Item 1 — Postinst ordering (WR-010):** The smoke test fires before the system user is created. If the bundled Python or any of the 10 libs is broken on a specific Jetson configuration, the install fails partway through, leaving no system user, no state directories, and ModemManager not masked — a state that dpkg cannot cleanly recover from on retry. Fix: move adduser/install-d/ModemManager mask above the smoke test call.

**Item 2 — systemd unit hardening (CR-001):** The unit runs as root with NoNewPrivileges=false and no CapabilityBoundingSet. This is broader than needed for Phase 1 (the placeholder ExecStart= just calls sdnotify) and undermines the LoadCredential= design intent for the HMAC secret. Fix: add NoNewPrivileges=true, CapabilityBoundingSet= (empty for Phase 1; Phase 4 adds CAP_SYS_ADMIN for usb_reset), RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6 AF_NETLINK, RuntimeDirectory=spark-modem-watchdog.

Both items are in the packaging layer (debian/), not in the plumbing modules. All 6 Python modules are clean (mypy/ruff green, tests pass). All 13 ADRs are present and correct. The carrier table and hostile fixtures are correct. The state store is correct apart from the schema-downgrade rename discipline (CR-002, WR-002 — warnings, not blockers for SC#5 which primarily tests round-trip and cross-check behavior).

FR-72 (Protocol types) and FR-73 (policy engine pure function) are listed as Phase 1 requirements, but their plan's must_haves do not require Protocol class declarations or a policy/ module — the wire types that define the seam shapes are the Phase 1 deliverable. The actual Protocol interfaces and policy engine implementation are Phase 2 work. This is consistent with how the team scoped the plans.

**Recommendation:** The two packaging items (WR-010 + CR-001) and the schema-downgrade dirfsync (CR-002) should be fixed before Phase 2 work begins, as they affect the Jetson install correctness. The other warnings (WR-002..WR-011) are real but Phase-2-impactful rather than Phase-1-blocking.

---

_Verified: 2026-05-06_
_Verifier: Claude (gsd-verifier)_
