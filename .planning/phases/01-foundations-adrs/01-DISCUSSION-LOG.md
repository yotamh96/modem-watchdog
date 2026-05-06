# Phase 1: Foundations & ADRs - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in `01-CONTEXT.md` — this log preserves the alternatives considered.

**Date:** 2026-05-06
**Phase:** 01-foundations-adrs
**Areas discussed:** wire/ layout & schema_version, .deb build & CI strategy, state_store/ atomic-write contract, subproc/ wrapper shape

---

## wire/ layout & schema_version

### Q1 — wire/ module organization

| Option | Description | Selected |
|--------|-------------|----------|
| Per-domain files (recommended) | `wire/diag.py`, `wire/state.py`, `wire/events.py`, `wire/webhook.py`, `wire/identity.py`, `wire/globals.py`, `wire/carriers.py`. Mirrors SCHEMA.md §2-9 sections. | ✓ |
| Per-purpose grouping | `wire/types.py` (enums + shared primitives), `wire/models.py` (all BaseModels), `wire/unions.py` (Who tagged union). | |
| Single `wire/__init__.py` | Everything in one ~600-LOC file. Simplest grep, biggest git churn. | |

**User's choice:** Per-domain files (recommended)

### Q2 — pydantic v2 ConfigDict defaults

| Option | Description | Selected |
|--------|-------------|----------|
| `frozen=True, extra='forbid', populate_by_name=True` (recommended) | Immutable + strict shape + alias-friendly. Matches NFR-32 literally. | ✓ |
| `frozen=True, extra='ignore'` | PITFALLS §1.2 recommends ignore at the qmicli boundary specifically. Requires a split. | |
| `frozen=False, extra='forbid'` | Mutable + strict. Loses immutability guarantee for asyncio sharing. | |

**User's choice:** `frozen=True, extra='forbid', populate_by_name=True`
**Notes:** Boundary split — qmicli parser in `subproc/`-adjacent code uses `extra='ignore'` per PITFALLS §1.2; the strict wire is the persisted/transmitted boundary.

### Q3 — discriminated union representation

| Option | Description | Selected |
|--------|-------------|----------|
| `Annotated[Union[...], Field(discriminator='kind')]` (recommended) | Pydantic v2 idiom; mypy-friendly; one error per variant on bad input. | ✓ |
| `RootModel` with validator | More code; useful only if discriminator needs computation. | |
| `TypeAdapter` at parse sites | Less type-safety for downstream consumers. | |

**User's choice:** `Annotated[Union[...], Field(discriminator='kind')]`

### Q4 — ModemState 5+2 shape (per ADR-0008)

| Option | Description | Selected |
|--------|-------------|----------|
| Flat top-level fields (recommended) | `state: Literal[...]`, `recovering_level: int \| None`, `present: bool`, `rf_blocked: bool` as siblings. Matches SCHEMA §3. | ✓ |
| Nested `Flags` submodel | Cleaner if flags grow beyond 2; extra indirection on every read. | |
| Sealed StateMachine ADT-style | Most type-safe; requires `match` everywhere policy reads state. | |

**User's choice:** Flat top-level fields

---

## .deb build & CI strategy

### Q1 — build host

| Option | Description | Selected |
|--------|-------------|----------|
| Self-hosted aarch64 runner (recommended) | Native build on real arm64 Linux (ideally a dev Jetson). Closest to production. | ✓ |
| GitHub-hosted ubuntu-24.04-arm | Native arm64 GHA runner. No infra to own; glibc 2.39 vs Jetson's 2.31 (PBS 2.17 baseline absorbs). | |
| QEMU emulation on amd64 runner | ~5× slower; occasional syscall divergence. | |
| Cross-build chroot (debcrossgen) | Brittle for native-extension wheels in a venv we won't run on the host. | |

**User's choice:** Self-hosted aarch64 runner

### Q2 — `python-build-standalone` source

| Option | Description | Selected |
|--------|-------------|----------|
| Build-time download with SHA256 pin (recommended) | Curl release tarball; SHA256 in `debian/python.sha256`. Repo stays small. | ✓ |
| Vendored in-repo via Git LFS | Offline-buildable; LFS quota cost; contributor onboarding cost. | |
| Side-channel artifact storage | Splits the difference; adds a third-party dependency. | |

**User's choice:** Build-time download with SHA256 pin

### Q3 — smoke test wiring (Phase 1 SC #1)

| Option | Description | Selected |
|--------|-------------|----------|
| post-install dpkg hook + ExecStartPre (recommended) | `postinst` fails install on import error; `ExecStartPre=` re-runs at every start (FR-60). Belt-and-suspenders. | ✓ |
| Standalone CLI subcommand | `spark-modem ctl preflight` does the check; CI invokes post-install. Misses fail-the-install signal. | |
| CI-only smoke job | GHA installs and tests on a runner. Doesn't run on real installs in production. | |

**User's choice:** post-install dpkg hook + ExecStartPre

### Q4 — versioning + reproducibility

| Option | Description | Selected |
|--------|-------------|----------|
| Semver + git-describe + SOURCE_DATE_EPOCH (recommended) | `2.0.0-1` releases, `2.0.0-0.git<sha>-1` dev; deterministic timestamps; `requirements.lock` committed. | ✓ |
| Calver (YYYY.MM.PATCH) | Easier deploy-window reasoning; less common in Debian-land. | |
| Strict semver only | No git suffix; can't distinguish dev from release without inspecting build log. | |

**User's choice:** Semver + git-describe + SOURCE_DATE_EPOCH

---

## state_store/ atomic-write contract

### Q1 — Phase 1 scope vs deferral

| Option | Description | Selected |
|--------|-------------|----------|
| Full atomic-write + flock layer now (recommended) | 3-layer locking ships now (per-modem asyncio.Lock + per-modem flock + state-store flock); CLI mutators don't exist yet but tested via concurrent-pytest. | ✓ |
| Atomic-write only; flocks stub'd | Writer + asyncio.Lock now; flock is no-op stub; Phase 3 wires real flock. Risk: stub interface fossilizes. | |
| Atomic-write only; defer locks entirely | Just the file writer; no lock interface. Maximum Phase 3 churn. | |

**User's choice:** Full atomic-write + flock layer now

### Q2 — inventory cross-check failure behaviour

| Option | Description | Selected |
|--------|-------------|----------|
| Refuse to start with structured error (recommended) | Typed `inventory.usb_path_mismatch` event + `sd_notify STATUS=`; non-zero exit. Recovery via `ctl reset-state`. Matches Phase 1 SC #5. | ✓ |
| Quarantine + continue | Move conflicting file to `.conflict-<ts>.json`; start with fresh defaults; WARN log. | |
| Overwrite with current sysfs view | Anti-pattern — defeats ADR-0009 by losing streak/counter history on hub re-enumeration. | |

**User's choice:** Refuse to start with structured error

### Q3 — schema-downgrade shadow file naming

| Option | Description | Selected |
|--------|-------------|----------|
| Sibling: `<usb_path>.from-v<N>.json` (recommended) | Same directory; emits structured `schema_downgrade_pending` event; `ctl migrate-state` reads shadow when downgrade tooling lands. | ✓ |
| Separate dir: `state/quarantine/<ts>/<usb_path>.json` | Cleaner directory listing; no obvious cross-reference between predecessor and successor file. | |
| In-file marker only | `__downgraded_from: <N>` metadata + .from-v<N> with no timestamp. Single-file source of truth; loses original byte-for-byte. | |

**User's choice:** Sibling `<usb_path>.from-v<N>.json`

### Q4 — random-USB-renumbering simulation (Phase 1 SC #5)

| Option | Description | Selected |
|--------|-------------|----------|
| Hypothesis property test against fake sysfs (recommended) | `tmp_path`-backed fake-sysfs tree; hypothesis generates random `(usb_path, cdc_wdm)` permutations; serves as spec-as-tests for ADR-0009. Hardware-free; <1 s. | ✓ |
| Hand-coded scenario tests | Explicit pytest cases. More readable; less corner-case coverage; no hypothesis dependency. | |
| Both: hypothesis + golden scenarios | Property tests for invariants + 3-5 hand-written for readability. ~2× test code; strongest coverage. | |

**User's choice:** Hypothesis property test against fake sysfs

---

## subproc/ wrapper shape

### Q1 — generic wrapper or per-tool wrappers

| Option | Description | Selected |
|--------|-------------|----------|
| Generic `run()` + per-tool parsers (recommended) | One async `run(argv, *, timeout, stdin, env) -> CompletedProcess`; per-tool parsing in domain modules (`qmi/`, `observer/zao/`, etc.). | ✓ |
| Per-tool wrappers in subproc/ | `subproc/qmicli.py`, `subproc/ip.py`, `subproc/infractrl.py` each owns argv + parsing. Risks duplicating timeout/SIGTERM/LC_ALL plumbing. | |
| Both: generic `run()` + thin per-tool helpers | Per-tool helpers compose argv lists; everyone uses `run()`. Most code; cleanest call sites. | |

**User's choice:** Generic `run()` + per-tool parsers

### Q2 — failure return type

| Option | Description | Selected |
|--------|-------------|----------|
| Always returns `CompletedProcess`; caller inspects (recommended) | "All errors are data" — `CompletedProcess(argv, exit_code, stdout, stderr, duration_monotonic, timed_out)` for any terminating outcome. Exceptions only on broken-runtime. | ✓ |
| `Result/Err` discriminated union | `Ok[CompletedProcess] \| Err[SubprocFailure]`. Most type-safe; new dependency. | |
| Raise on non-zero / timeout; return on success | Pythonic; forces try/except even for benign non-zero exits (qmicli 1 on no-SIM). | |

**User's choice:** Always returns `CompletedProcess`; caller inspects

### Q3 — spawn invariants

| Option | Description | Selected |
|--------|-------------|----------|
| All four always-on (recommended) | list-form argv + LC_ALL=C/LANG=C + start_new_session=True + two-stage SIGTERM→2s→SIGKILL drain. No opt-out. | ✓ |
| All four with per-call escape hatches | Same defaults; caller can opt out per spawn. More flexible; risks regression. | |
| list-form argv only; rest opt-in | Smallest wrapper; wires up failure modes the docs already warn about. | |

**User's choice:** All four always-on

### Q4 — lint gate enforcement

| Option | Description | Selected |
|--------|-------------|----------|
| Pre-commit + CI grep (recommended) | `scripts/lint_no_subprocess.sh` greps for `create_subprocess_exec`/`subprocess.run|Popen|call|check_*`/`os.system` outside `src/spark_modem/subproc/`. | ✓ |
| Custom ruff rule (per-package allowlist) | `[tool.ruff.lint.per-file-ignores]` permits these calls only in `subproc/`. Cleaner output; small custom config. | |
| Both: pre-commit grep AND ruff rule | Defense in depth. ~10 lines extra config. | |

**User's choice:** Pre-commit + CI grep

---

## Claude's Discretion

The user accepted the recommended option in every question. Areas
explicitly delegated to Claude during planning (see `01-CONTEXT.md`
§Decisions § Claude's Discretion for the recommended defaults):

- ADR landing PR strategy (one umbrella PR vs waves vs one-per-commit)
- Repository layout (`src/spark_modem/...`)
- `requirements.lock` location
- Carrier-table YAML schema shape
- `event_logger/` writer shape (sync vs async; queue vs direct)
- `config/` layering implementation choice (BaseSettings vs custom merge)
- Closed-enum representation (StrEnum recommended)

## Deferred Ideas

See `01-CONTEXT.md` §Deferred Ideas for the full list (organized by
target phase: Phase 2, Phase 3, Phase 4, v2.1, and tactical Claude-
discretion items).

