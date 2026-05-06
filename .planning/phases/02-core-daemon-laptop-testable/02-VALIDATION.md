---
phase: 2
slug: core-daemon-laptop-testable
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-06
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `02-RESEARCH.md` §6 "Validation Architecture" — every plan task
> below has an `<automated>` verify block (no MISSING references); plan
> 02-01 is the Wave 0 scaffolding that produces every fake/fixture every
> downstream task imports.

---

## Test Infrastructure

| Property              | Value                                                              |
|-----------------------|--------------------------------------------------------------------|
| **Framework**         | pytest 7.x + pytest-asyncio (`mode=auto`)                          |
| **Config file**       | `pyproject.toml` (`[tool.pytest.ini_options]`)                     |
| **Quick run command** | `python -m pytest -q -x`                                           |
| **Full suite command**| `python -m pytest -q`                                              |
| **Estimated runtime** | ~30 seconds (M7 budget; replay harness contributes ~5s of that)    |

Supporting gates that run alongside pytest:

- `python -m mypy --strict src/spark_modem/ tests/`
- `python -m ruff check src/spark_modem/ tests/`
- `python -m ruff format --check src/spark_modem/ tests/`
- `bash scripts/lint_no_subprocess.sh` (SP-04 — no `subprocess` outside `subproc/`)
- `python tools/check_spec.py` (RECOVERY_SPEC §4 coverage gate, plan 02-05)

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest -q -x`
- **After every plan wave:** Run `python -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds (M7 budget)

---

## Per-Task Verification Map

> Task ID format: `<phase>-<plan>-<task>` → `02-NN-MM`. Each row's automated
> command is the highest-signal command from the corresponding `<verify>
> <automated>` block in the plan file (long composite commands are abbreviated
> when a tighter pytest invocation already covers the change). All test files
> are created under `tests/unit/<area>/` (or `tests/replay/` for plan 02-10
> task 2) and exist on disk after the listed Wave-0 plan ships — Wave 0 is
> plan **02-01**, so every task starting wave ≥2 has its test file already on
> disk by construction (Wave-0 produces the FAKES; the test file itself is
> created by the same task that creates the production code).

| Task ID  | Plan | Wave | Requirement(s)                                  | Threat Ref           | Secure Behavior                                      | Test Type   | Automated Command                                                                                                       | File Exists | Status     |
|----------|------|------|-------------------------------------------------|----------------------|------------------------------------------------------|-------------|-------------------------------------------------------------------------------------------------------------------------|-------------|------------|
| 02-01-01 | 01   | 1    | — (Wave 0 scaffolding)                          | T-02-01-01..03       | Test fakes never reach production runtime            | unit + lint | `python -m pytest tests/unit/fakes/test_runner.py tests/unit/fakes/test_clock.py tests/unit/fakes/test_zao_log.py -q`   | ✅ W0       | ⬜ pending |
| 02-01-02 | 01   | 1    | — (Wave 0 scaffolding)                          | T-02-01-01..03       | Test fakes never reach production runtime            | unit + lint | `python -m pytest tests/unit/fakes/ -q`                                                                                 | ✅ W0       | ⬜ pending |
| 02-02-01 | 02   | 2    | FR-11, FR-74                                    | T-02-02-01..05       | --device-open-proxy always; classify proxy_died/timeout | unit + lint | `python -m pytest tests/unit/qmi/test_wrapper.py -q && bash scripts/lint_no_subprocess.sh`                              | ✅          | ⬜ pending |
| 02-02-02 | 02   | 2    | FR-11                                           | T-02-02-04           | Per-libqmi-version fixtures; extra='ignore' on parsers | unit + lint | `python -m pytest tests/unit/qmi/test_parsers.py -q && bash scripts/lint_no_subprocess.sh`                              | ✅          | ⬜ pending |
| 02-03-01 | 03   | 2    | FR-10                                           | T-02-03-01..04       | Unparseable Zao log → `unknown` (safe direction)     | lint + smoke| `python -m mypy --strict src/spark_modem/zao_log/ && python -c "from spark_modem.zao_log.protocol import ZaoLogTailer; from spark_modem.zao_log.snapshot import ZaoSnapshot; assert ZaoSnapshot.unknown(reason='x').is_line_active(1) is False"` | ✅          | ⬜ pending |
| 02-03-02 | 03   | 2    | FR-10                                           | T-02-03-01..04       | Parse failure → ZaoSnapshot.unknown (no crash)       | unit + lint | `python -m pytest tests/unit/zao_log/ -q && bash scripts/lint_no_subprocess.sh`                                         | ✅          | ⬜ pending |
| 02-04-01 | 04   | 3    | FR-2, FR-13, FR-70, FR-71                       | T-02-04-03           | sysfs path traversal contained; usb_path validated   | unit + lint | `python -m pytest tests/unit/inventory/ -q && bash scripts/lint_no_subprocess.sh`                                       | ✅          | ⬜ pending |
| 02-04-02 | 04   | 3    | NFR-4, NFR-10                                   | T-02-04-01,02,04,05  | TaskGroup + per-task asyncio.timeout; FR-10 gate     | unit + lint | `python -m pytest tests/unit/observer/ -q && bash scripts/lint_no_subprocess.sh`                                        | ✅          | ⬜ pending |
| 02-05-01 | 05   | 2    | FR-12, FR-25, FR-25.1, FR-26, FR-26.2           | T-02-05-01,02,03     | Pure function; mypy --strict exhaustive `match` arms | unit + lint | `python -m pytest tests/unit/policy/test_transitions.py tests/unit/policy/test_decision_table.py tests/unit/policy/test_gates.py tests/unit/policy/test_streak.py -q` | ✅          | ⬜ pending |
| 02-05-02 | 05   | 2    | FR-20..22, FR-26.1, NFR-11, NFR-20              | T-02-05-04,05        | Engine emits StateTransition records (no PII in reason) | unit + spec | `python -m pytest tests/unit/policy/test_engine.py tests/test_recovery_spec.py -q && python tools/check_spec.py`        | ✅          | ⬜ pending |
| 02-06-01 | 06   | 3    | FR-22, FR-28, FR-28.1, FR-30, FR-40             | T-02-06-04,05,06     | Dispatcher dry-run gate; ActionPlanned event emitted | unit + lint | `python -m pytest tests/unit/actions/test_dispatcher.py tests/unit/actions/test_dry_run.py tests/unit/actions/test_verify.py -q` | ✅          | ⬜ pending |
| 02-06-02 | 06   | 3    | FR-31, FR-32, FR-33, NFR-42                     | T-02-06-01,02,03     | Idempotent (read-then-write); typed boundary (no `_runner` access from actions/) | unit + lint | `python -m pytest tests/unit/actions/ -q && bash scripts/lint_no_subprocess.sh`                                         | ✅          | ⬜ pending |
| 02-07-01 | 07   | 4    | FR-41, FR-41.1, NFR-3, NFR-21, NFR-21.1         | T-02-07-04,06        | atomic_write_bytes for status.json; max_duration ≤ 8h | unit + lint | `python -m pytest tests/unit/status_reporter/test_status.py -q && bash scripts/lint_no_subprocess.sh`                   | ✅          | ⬜ pending |
| 02-07-02 | 07   | 4    | FR-42, NFR-5                                    | T-02-07-01,02,03,05  | Cardinality-safe metrics (state-as-value); UDS 0o660 | unit + lint | `python -m pytest tests/unit/status_reporter/test_metrics_registry.py -q && bash scripts/lint_no_subprocess.sh`         | ✅          | ⬜ pending |
| 02-08-01 | 08   | 3    | FR-44.3, FR-44.6                                | T-02-08-01,02,06     | HMAC-SHA256 signs raw bytes; cert validation via Host header | unit + lint | `python -m pytest tests/unit/webhook/test_sign.py tests/unit/webhook/test_dedup.py tests/unit/webhook/test_dns.py -q`   | ✅          | ⬜ pending |
| 02-08-02 | 08   | 3    | FR-44, FR-44.4, FR-44.5, FR-44.7, FR-44.8       | T-02-08-03,04,05,07,08 | Bounded retries; in-memory queue; replay-protection ts header | unit + lint | `python -m pytest tests/unit/webhook/ -q && bash scripts/lint_no_subprocess.sh`                                         | ✅          | ⬜ pending |
| 02-09-01 | 09   | 5    | FR-50, FR-50.3, FR-51, FR-52                    | (no new threats)     | Production code never imports `tests.fakes`; argparse rejects unknown flags | unit + lint | `python -m pytest tests/unit/cli/test_main.py tests/unit/cli/test_diag.py tests/unit/cli/test_recovery.py tests/unit/cli/test_provision.py tests/unit/cli/test_reset.py tests/unit/cli/test_status.py tests/unit/cli/test_explain.py -q` | ✅          | ⬜ pending |
| 02-09-02 | 09   | 5    | FR-50.1, FR-50.2, NFR-22, NFR-22.1              | T-02-09-01..07       | ICCID/IMSI redacted; HMAC secret excluded; webhook URL host-only; 8h cap | unit + lint | `python -m pytest tests/unit/cli/test_ctl_history.py tests/unit/cli/test_ctl_maintenance.py tests/unit/cli/test_ctl_support_bundle.py tests/unit/cli/test_redact.py -q` | ✅          | ⬜ pending |
| 02-10-01 | 10   | 6    | NFR-1, NFR-2                                    | T-02-10-01,02,05,06,07,08 | Policy exception isolated (NFR-11); SC #5 webhook envelopes enqueued; 200 MiB tripwire event-only | unit + lint | `python -m pytest tests/unit/daemon/ -q && bash scripts/lint_no_subprocess.sh`                                          | ✅          | ⬜ pending |
| 02-10-02 | 10   | 6    | FR-26.1, NFR-1                                  | T-02-10-03,04        | Replay fixtures deterministic (seeded); ≥95% v1 agreement (R-03) | replay + lint | `python -m tools.gen_replay_fixtures --count 1000 --out tests/fixtures/replay && python -m pytest tests/replay/ -q && test -f artifacts/replay-summary.json` | ✅          | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Plan **02-01** is the Wave 0 scaffolding plan. It produces every fake and
fixture-directory marker that downstream plans (02-02..02-10) import or
populate:

- [ ] `tests/fakes/__init__.py` — package marker
- [ ] `tests/fakes/runner.py` — `FakeRunner` (argv → CompletedProcess map)
- [ ] `tests/fakes/clock.py` — `FakeClock` (deterministic `monotonic` /
      `wall_clock_iso` / `advance`)
- [ ] `tests/fakes/webhook.py` — `FakeWebhookPoster` (`sent: list[WebhookEnvelope]` recorder)
- [ ] `tests/fakes/inventory.py` — `FixtureInventory` (loads ModemDescriptor JSON)
- [ ] `tests/fakes/dns.py` — `FakeDNSResolver` (canned IP + `set_fail_next()`)
- [ ] `tests/fakes/zao_log.py` — `FixtureZaoTailer` (canned active-line set)
- [ ] `tests/unit/fakes/__init__.py` + per-fake self-tests
      (`test_runner.py`, `test_clock.py`, `test_zao_log.py`,
      `test_webhook.py`, `test_inventory.py`, `test_dns.py`)
- [ ] `tests/conftest.py` — directory-based pytest auto-marker hook
- [ ] `tests/fixtures/qmicli/.gitkeep` — qmicli per-version fixture root
- [ ] `tests/fixtures/zao_log/.gitkeep` — Zao log fixture root
- [ ] `tests/fixtures/inventory/.gitkeep` — inventory fixture root (+ seed
      `four_modems.json`)
- [ ] `tests/fixtures/diag/.gitkeep` — Diag JSON fixture root
- [ ] `tests/fixtures/replay/.gitkeep` — replay-cycle JSON fixture root

After plan 02-01 ships, every test file referenced by plans 02-02..02-10
either already exists (under `tests/fakes/` or `tests/fixtures/`) or is
created by the same task that creates the production code it covers. No
task in waves 2..6 has a `MISSING — Wave 0 must create …` placeholder.

---

## Manual-Only Verifications

All phase behaviors have automated verification.

Phase 2 is hardware-free by design: every QMI call goes through
`FakeRunner` + canned per-libqmi-version fixtures, every Zao log read goes
through `FixtureZaoTailer`, every webhook delivery uses `FakeWebhookPoster`
or a `respx` httpx-mock harness, and every state-store mutation hits a
`tmp_path`-rooted directory tree. Hardware integration (Sierra EM7421,
Soliton Zao, USB hub topology) lands in Phase 5.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (Phase 2 has none)
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
