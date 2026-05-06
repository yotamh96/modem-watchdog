# Test strategy — spark-modem-watchdog v2

| Field         | Value                  |
| ------------- | ---------------------- |
| Status        | Draft                  |
| Owner         | TBD (modem platform)   |
| Last updated  | 2026-05-05             |

The v1 toolchain has zero automated tests. v2 makes tests a hard
gate from commit zero. This document describes how, what, and where.

---

## 1. Goals

- **Confidence to refactor.** Anyone should be able to restructure
  the policy engine and know within 30 s whether they broke a
  decision.
- **Hardware-free dev loop.** A laptop with `pytest` MUST be able
  to validate every piece of logic without a Jetson or modems.
- **Spec-as-tests for [RECOVERY_SPEC.md](RECOVERY_SPEC.md).** Every
  decision-table row, every gate, every state transition is a
  fixture; the test asserts the policy engine matches the spec.
- **CI gates that catch regressions before review.** No PR merges
  without lint + typecheck + tests green.

## 2. Test layers

### Layer 1 — Unit tests (the bulk)

Pure-Python tests of individual modules. No subprocess, no I/O.

Targets:

- `policy/` — every decision-table row in `RECOVERY_SPEC.md`.
- `wire/` — round-trip serialization / validation of every schema.
- `qmi/parsers.py` — qmicli text → typed records, against fixtures.
- `zao_log/parser.py` — Zao log lines → `ZaoSnapshot`.
- `state_store/` — atomic write semantics (using `tmp_path`).
- `config/` — layered loading + validation.
- `clock/` — monotonic vs wall semantics.

Speed budget: 5 s wall-clock for the full suite.

### Layer 2 — Integration tests (logic-level)

Tests that exercise multiple modules end-to-end with fakes for
every external IO.

Examples:

- "Given this `Diag` JSON fixture and this `ModemState`, the daemon
  cycle produces these `PlannedAction[]` and these state file
  diffs."
- "When a `udev_remove` event arrives, the inventory marks the
  modem as `disconnected` and no actions are planned for it."
- "When the Zao log has not been touched in 5 minutes, all four
  modems revert to direct-probe mode and the daemon emits a
  `zao_log_stale` issue."

Speed budget: 20 s.

### Layer 3 — Subprocess-shim tests

Tests that exercise the daemon as a single Python process, but with
a **fake `qmicli` shim** on `PATH` instead of the real binary. The
shim reads canned responses from `tests/fixtures/qmicli/<intent>.txt`.

Targets:

- The daemon's main loop with all real modules wired except for the
  fake `qmicli`, fake `ip netns`, and fake `inotify` event source.
- Configuration loading on a real file tree.
- `spark-modem` CLI subcommand exit codes.

Speed budget: 60 s.

### Layer 4 — Hardware-in-loop (HIL) tests

Run on a real Jetson with real modems before tagging a release.
**Not** part of every-PR CI.

Procedure (semi-automated under `tests/hil/`):

- Install the candidate `.deb`.
- Wait for one Healthy cycle.
- Inject faults via `qmicli` directly: take a SIM down, force a
  modem reset, trip raw_ip off.
- Assert the daemon recovers within the spec'd MTTRs.
- Tear down; capture support bundle on failure.

Run weekly on a HIL fixture in the lab plus before each release.

## 3. Fixture library

```
tests/fixtures/
├─ qmicli/
│  ├─ get_signal/
│  │  ├─ lte_strong.txt
│  │  ├─ lte_weak.txt
│  │  ├─ nr5g_normal.txt
│  │  ├─ no_serving_cell.txt
│  │  └─ timeout.txt              ← shim mode that exits with timeout error
│  ├─ get_card_status/
│  │  ├─ present_ready.txt
│  │  ├─ present_detected.txt
│  │  ├─ power_down.txt
│  │  └─ absent.txt
│  ├─ get_serving_system/
│  │  ├─ registered.txt
│  │  ├─ not_registered_searching.txt
│  │  └─ denied.txt
│  ├─ get_home_network/
│  ├─ get_profile_list/
│  └─ get_packet_service_status/
├─ zao_log/
│  ├─ all_active.log
│  ├─ line1_inactive.log
│  ├─ all_inactive.log
│  └─ rascow_format_changed.log    ← regression for ADR-0003 fallback
├─ diag/
│  ├─ all_healthy.json
│  ├─ apn_empty_one.json
│  ├─ rf_blocked.json
│  ├─ qmi_hung_three.json
│  ├─ session_disconnected.json
│  └─ ladder_exhausted.json
├─ state/
│  ├─ fresh.json
│  ├─ recovering_soft.json
│  ├─ recovering_modem.json
│  └─ exhausted.json
└─ config/
   ├─ minimal.yaml
   ├─ tight_thresholds.yaml
   └─ broken.yaml
```

Capturing a fixture from real hardware:

```bash
# On a Jetson with the modem in the desired state:
sudo qmicli -d /dev/cdc-wdm0 --nas-get-signal-info \
    > tests/fixtures/qmicli/get_signal/<scenario>.txt

# Or capture a full Diag snapshot:
sudo spark-modem diag --json > tests/fixtures/diag/<scenario>.json
```

PRs that change observed shapes MUST re-capture relevant fixtures
on real hardware (HIL job auto-captures and uploads as artifacts).

## 4. Spec-as-tests

`tests/test_recovery_spec.py` walks `RECOVERY_SPEC.md` row by row
and asserts the policy engine matches. The spec table is parsed
directly from the markdown (one source of truth, not duplicated):

```python
@pytest.mark.parametrize("row", parse_decision_table(SPEC_PATH))
def test_decision_table_row(row, fake_clock, fake_store):
    diag = make_diag_for_row(row)
    state = fake_store.load_modem(row.device) or initial_state(row.device)
    plans = run_cycle(diag, fake_store, default_config(), fake_clock).plans
    assert plans == row.expected_plans
```

This means edits to the markdown table automatically become test
coverage.

## 5. Property-based tests

Three property classes use `hypothesis`:

1. **Idempotency**: applying any planned action and then re-running
   the policy on the same Diag produces the same plan or `skip:backoff`.
2. **No-action-on-Healthy**: any Diag where every modem is Healthy
   (no issues, signal sufficient) produces zero `PlannedAction`s.
3. **Counter monotonicity**: counters never go negative; never grow
   past `MAX_*+1` before triggering `Exhausted`.

## 6. CI pipeline

Per PR:

| Stage             | Tool                       | Pass criterion                                     |
| ----------------- | -------------------------- | -------------------------------------------------- |
| Lint              | `ruff check`               | Zero violations.                                   |
| Format            | `ruff format --check`      | Zero diffs.                                        |
| Type check        | `mypy --strict src/`       | Zero errors.                                       |
| Unit + integration| `pytest tests/`            | 100 % pass; coverage ≥ 85 % on `policy/` and `wire/`. |
| Schema doc check  | custom: `tools/check_schemas.py` | Doc samples in `SCHEMA.md` round-trip through the pydantic models. |
| Spec doc check    | custom: `tools/check_spec.py` | Every row of `RECOVERY_SPEC.md § 4` is referenced by at least one test. |
| Build `.deb`      | `dpkg-buildpackage`        | Builds; lintian clean.                             |

On tag push:

| Stage             | Action                                                              |
| ----------------- | ------------------------------------------------------------------- |
| HIL              | Trigger nightly HIL job. Block release on failure.                  |
| Publish           | Upload `.deb` to internal apt repo; cut GitHub release with notes.  |

## 7. Running locally

```bash
# Setup
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

# Fast loop (unit + integration, ~25 s)
pytest -q

# Single layer
pytest tests/unit/
pytest tests/integration/
pytest tests/subprocess/

# With coverage
pytest --cov=spark_modem_watchdog --cov-report=term-missing

# Property-based, more iterations
pytest tests/properties/ --hypothesis-show-statistics

# Lint + types
ruff check .
ruff format --check .
mypy --strict src/
```

## 8. Conventions

- One assertion per test by default; use sub-tests for groups.
- Fixtures live in `conftest.py` per layer; no cross-layer fixture
  imports.
- Time is mocked with a `FakeClock` (asyncio-compatible). Tests
  never call `time.monotonic` or `time.time` directly.
- Subprocess is mocked with a `FakeSubprocessRunner` that maps
  argv → canned `Completed` records loaded from fixtures.
- Filesystem writes use `tmp_path`. No global state.
- Test names are sentences:
  `test_policy_chooses_soft_reset_when_registration_searching_first_time`.

## 9. What we deliberately do NOT test

- Real `qmicli` parsing across libqmi versions (we pin one).
- Real systemd interaction (covered by HIL).
- Real udev/rtnetlink events at the kernel level (covered by HIL).
- The Zao stack itself.

These are HIL territory. Adding them to PR-time CI would make the
fast loop slow without protecting against the failures most likely
to land in code.
