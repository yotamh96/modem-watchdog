# Phase 1: Foundations & ADRs - Context

**Gathered:** 2026-05-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 1 locks the wire formats, packaging story, ADR set, and plumbing
skeleton so that no Phase 2 module is ever built against a wire type that
needs to change.

By exit:

1. arm64 `.deb` containing CPython 3.12 + all 9 pinned runtime libraries
   (`pydantic`, `PyYAML`, `prometheus-client`, `pyudev`, `pyroute2`,
   `asyncinotify`, `httpx`, `sdnotify`, `psutil`) installs cleanly on a
   fresh Jetson Orin NX (JetPack 5.1.5 / Ubuntu 20.04) and all 9 imports
   succeed under `/opt/spark-modem-watchdog/python/bin/python3.12`.
2. All eight PROJECT.md open questions Q1-Q8 are closed in writing: six
   new ADRs (0008 state-machine, 0009 usb_path keying, 0010 packaging,
   0011 webhook subsystem, 0012 concurrency, 0013 metric surface) merged;
   ADRs 0001/0003/0004/0005/0006 carry the research-derived amendments.
3. The default carrier table at
   `/etc/spark-modem-watchdog/conf.d/00-carriers.yaml` covers IL (425/01,
   02, 03), US (310/410, 311/480, 312/530), UK (234/10, 234/15, 234/30),
   DE (262/01, 262/02, 262/03) marked `unverified: true`; YAML parses
   against pydantic validators with hostile-input fixtures (Norway problem,
   leading-zero MNCs, `mnc: str` regex `^\d{2,3}$`).
4. `mypy --strict`, `ruff check`, `ruff format --check` are green on
   `clock/`, `subproc/`, `wire/`, `config/`, `state_store/`,
   `event_logger/`; `wire/` defines all closed enums, tagged-union `who`
   types, and `Diag`/`PlannedAction`/`StateTransition` pydantic models
   with `schema_version: int` enforcement and non-destructive downgrade
   (`*.from-v<N>.json` shadow + `schema_downgrade_pending` log line);
   `grep -r 'subprocess.run\|os.system' src/` outside `subproc/` returns
   zero matches.
5. State files round-trip on disk under `state/by-usb/<usb_path>.json`
   with atomic temp+rename+directory-fsync semantics; the unit-test spike
   harness simulates random USB renumbering and the inventory
   cross-check (file `usb_path` ↔ sysfs ↔ current `cdc-wdmN`) raises a
   structured error rather than silently overwriting.

**Carried forward from project init (locked decisions, do not re-discuss):**

- Bundle CPython 3.12 via `astral-sh/python-build-standalone` (closes Q8)
- 5 top-level states + 2 orthogonal flags (ADR-0008 supersedes ADR-0005)
- State files keyed by `usb_path` (ADR-0009)
- HMAC-SHA256 v2.0 webhook signing + `X-Spark-Timestamp` (closes Q5; ADR-0011)
- Per-modem `asyncio.Lock` + globals lock + `flock`s separate from PID
  lock (ADR-0012)
- Integer-encoded `modem_state_value{modem}` (no one-hot `state` label;
  ADR-0013)

</domain>

<decisions>
## Implementation Decisions

### W. Wire types module (`wire/`)

- **W-01:** Per-domain file split — `wire/diag.py`, `wire/state.py`,
  `wire/events.py`, `wire/webhook.py`, `wire/identity.py`,
  `wire/globals.py`, `wire/carriers.py`. `wire/__init__.py` re-exports
  the public surface. Each file mirrors a numbered section of
  `docs/SCHEMA.md` (§2 Diag, §3 ModemState, §4 status.json, §5
  events.jsonl, §6 identity, §7 globals, §8 carrier table, §9 webhook).
- **W-02:** Every wire `BaseModel` inherits a base with
  `model_config = ConfigDict(frozen=True, extra='forbid', populate_by_name=True)`.
  - **Boundary split:** This is the *wire* boundary (persisted state,
    events, status, webhook payloads). The qmicli output parser in
    `subproc/`-adjacent code (`qmi/parsers/`, Phase 2) uses
    `extra='ignore'` per PITFALLS §1.2 to absorb libqmi 1.30→1.32+ output
    drift; missing-but-required fields surface as a typed `MissingField`
    error rather than a parse exception. The `extra='forbid'` discipline
    ends at the parser; everything downstream of the parser is on the
    strict wire.
- **W-03:** Discriminated unions are written as
  `Annotated[Union[VariantA, VariantB, ...], Field(discriminator='kind')]`.
  Applies to `Who = WhoModem | WhoHost` (SCHEMA §2 Issue tagged union)
  and to any future event-payload union (SCHEMA §5).
- **W-04:** `ModemState` carries 5+2 as flat top-level fields:
  - `state: Literal['unknown', 'healthy', 'degraded', 'recovering', 'exhausted']`
  - `recovering_level: int | None`  (None unless `state == 'recovering'`)
  - `present: bool`
  - `rf_blocked: bool`
  Status output (`status.json`) composes them in the standard SCHEMA §4
  shape; the policy engine matches on `state` and reads the orthogonal
  flags directly.

### B. `.deb` build & CI

- **B-01:** Native arm64 build on a **self-hosted aarch64 GitHub Actions
  runner** (a real arm64 Linux box; ideally a dev Jetson Orin NX so the
  build host matches production glibc 2.31). No QEMU emulation in the
  primary CI path. (QEMU emulation is acceptable as a backup runner for
  draft PRs from contributors who can't reach the self-hosted runner;
  not gating.)
- **B-02:** `python-build-standalone` tarball is **fetched at build time**
  by `debian/rules` from the `astral-sh/python-build-standalone` GitHub
  release (`cpython-3.12.<patch>+<datetag>-aarch64-unknown-linux-gnu-install_only.tar.gz`).
  SHA256 is pinned in `debian/python.sha256` and verified before unpack.
  Repo stays small; offline-rebuild is not a Phase 1 requirement.
- **B-03:** "All 9 libs import" smoke test is wired in **two places**:
  - `debian/postinst` runs the import check after package install; a
    failed import fails `apt install` (non-zero exit). This is the
    Phase 1 SC #1 acceptance gate.
  - The systemd unit's `ExecStartPre=` re-runs the same check at every
    daemon start (FR-60). A glibc/library breakage on a running box
    surfaces as `systemctl status` failed, not a silent crash mid-cycle.
- **B-04:** `.deb` versioning + reproducibility:
  - **Releases:** semver `2.0.0-1` (Debian-style upstream-debian split).
  - **Dev builds:** `2.0.0-0.git<short-sha>-1` so dev `.deb`s are visibly
    distinct from releases.
  - **Reproducibility:** `SOURCE_DATE_EPOCH=$(git log -1 --format=%ct)`
    exported in `debian/rules`; `python -m compileall` runs in-build for
    NFR-13 warm-cache; `requirements.lock` (output of `uv pip compile`)
    is committed; `uv pip install --frozen` enforced in `debian/rules`.

### S. State store (`state_store/`)

- **S-01:** Phase 1 ships the **full atomic-write + flock layer** for the
  per-modem state files at `state/by-usb/<usb_path>.json`. The 3-layer
  locking model from ADR-0012 lands now even though CLI mutators don't
  exist until Phase 2/3:
  - In-process: per-modem `asyncio.Lock` + a separate globals
    `asyncio.Lock` (FR-71).
  - Cross-process: per-modem `flock` at
    `/run/spark-modem-watchdog/modem-{usb_path}.lock` and a state-store
    `flock` at `/run/spark-modem-watchdog/state.lock` (FR-61.1).
  - PID lock at `/run/spark-modem-watchdog/lock` is **separate** from the
    state-store flocks (FR-61). Locking the API surface in Phase 1 means
    Phase 3 wires real callers without any interface churn.
- **S-02:** Inventory cross-check at startup (`file usb_path` ↔ sysfs
  topology ↔ current `cdc-wdmN` mapping). On mismatch, the daemon
  **refuses to start**:
  - Emits a typed event: `{module: 'inventory', error:
    'usb_path_mismatch', details: {file_usb_path, sysfs_usb_path, cdc_wdm}}`
  - Sends `STATUS=usb_path_mismatch` via `sd_notify` so `systemctl
    status` surfaces the cause.
  - Exits non-zero. Recovery: operator runs `spark-modem ctl
    reset-state --modem=<usb_path>` (or `--all`) to clear the offending
    file. (The `ctl reset-state` subcommand itself lands in Phase 2; in
    Phase 1 the operator deletes the file by hand.)
- **S-03:** Schema-downgrade shadow file naming: the old-version file is
  preserved verbatim as `state/by-usb/<usb_path>.from-v<N>.json` (sibling
  in the same directory), the daemon writes a fresh-default
  `state/by-usb/<usb_path>.json` at its own version, and emits a
  structured `schema_downgrade_pending` log line + event. No automatic
  re-merge; explicit `ctl migrate-state` (Phase 2) or `ctl reset-state
  --all` is the user-facing recovery path.
- **S-04:** Random-USB-renumbering simulation for Phase 1 SC #5 is a
  **hypothesis property test** in `tests/unit/state_store/test_inventory_crosscheck.py`:
  - Generates random `(usb_path, cdc_wdm_index)` permutations against a
    `tmp_path`-backed fake-sysfs tree (just files mirroring the real
    sysfs layout under `/sys/bus/usb/devices/`).
  - Asserts the inventory cross-check raises the typed
    `UsbPathMismatch` error on every mismatch and round-trips cleanly
    when consistent.
  - Hardware-free; runs in <1 s; serves as spec-as-tests for ADR-0009.

### SP. Subprocess wrapper (`subproc/`)

- **SP-01:** **One** generic async runner in `subproc/runner.py`:

      async def run(
          argv: list[str],
          *,
          timeout: float,
          stdin: bytes | None = None,
          env: dict[str, str] | None = None,
      ) -> CompletedProcess

  Per-tool *parsing* (qmicli, ip, InfraCtrl, journalctl) lives in domain
  modules — `qmi/parsers/`, `observer/zao/`, etc. — not in `subproc/`.
  `subproc/` owns spawn discipline; domain modules own argv composition
  and output parsing.
- **SP-02:** Failure model is **"all errors are data"**: `run()` returns
  a `CompletedProcess(argv, exit_code, stdout, stderr,
  duration_monotonic, timed_out: bool)` for any terminating outcome —
  including non-zero exit, timeout, and stderr-detected `proxy_died`.
  Caller decides whether non-zero is fatal (qmicli often exits 1 on
  "no SIM yet"; that's data, not an exception).
  - Exceptions are reserved for genuinely-broken-runtime conditions:
    binary not on PATH (raises `FileNotFoundError`), `OSError` on spawn,
    or invalid argv type (raises `TypeError`).
  - Pairs cleanly with the pure-function policy engine (FR-73): the
    policy never raises on subprocess failure; it returns a
    `PlannedAction` based on what it observed.
- **SP-03:** Spawn invariants are **all four always-on**, no per-call
  opt-out:
  - **list-form argv only** — `run()` accepts `list[str]` (TypeError
    otherwise). Closes FR-64 / NFR-31.
  - **Locale baseline** — `LC_ALL=C`, `LANG=C` in the spawned env unless
    the caller's `env=` explicitly overrides (rare; would need a domain
    justification). Closes PITFALLS §1.3.
  - **`start_new_session=True`** — kill the process group on SIGKILL
    drain, not the bare PID (cpython#127049). Closes PITFALLS §5.1.
  - **Two-stage shutdown on timeout** — SIGTERM → wait 2 s → SIGKILL →
    `proc.communicate()` drain to recover whatever stdout/stderr the
    child managed to emit before death. `timed_out: bool` is set on the
    returned `CompletedProcess`. Uses `asyncio.timeout()`, not
    `wait_for` around `communicate` (cpython#139373; STACK §4.2).
- **SP-04:** Lint gate enforcing "no `create_subprocess_exec` outside
  `src/spark_modem/subproc/`" lives in `scripts/lint_no_subprocess.sh`:

      grep -rE 'create_subprocess_exec|subprocess\.(run|Popen|call|check_(call|output))|os\.system' \
          src/ \
          --include='*.py' \
          | grep -v '^src/spark_modem/subproc/' \
          && exit 1 || exit 0

  Wired as both a `pre-commit` hook and a CI step. Catches `os.system`,
  `subprocess.run/Popen/call`, `subprocess.check_call/check_output`, and
  the async variant. Cheap, deterministic, no AST tooling.

### Claude's Discretion

The user accepted the recommended option in every question, signalling
alignment with the research recommendations. The following surfaces are
explicitly delegated to Claude during planning — pick a reasonable
default and proceed:

- **ADR landing PR strategy.** Whether the six new ADRs (0008-0013) and
  five amendments (0001/0003/0004/0005/0006) land in one PR, in waves
  (e.g. all amendments first, then new ADRs in dependency order), or
  one-ADR-per-commit. Recommended: one umbrella PR titled "Phase 1: ADR
  set" with one commit per ADR, so review is per-decision but merge is
  atomic. ADR-0005 should be marked `Status: Superseded by ADR-0008`
  with a header `Supersedes: ADR-0005` on ADR-0008 (clean break, history
  preserved).
- **Repository layout.** `src/spark_modem/` package root with submodules
  matching the 11-module decomposition in `docs/ARCHITECTURE.md` (`wire`,
  `clock`, `subproc`, `config`, `state_store`, `event_logger`, plus
  Phase-2+ `qmi`, `observer`, `policy`, `actions`, `cycle`, `cli`).
  Tests in `tests/{unit,integration,hil}/` mirroring the package
  structure.
- **`requirements.lock` location.** `packaging/requirements.lock` (next
  to `debian/`) so it's grouped with build artifacts; symlink or
  `pyproject.toml` reference if the dev workflow needs it at the root.
- **Carrier-table YAML schema shape.** Flat list of records is fine
  (`carriers: - {country, mcc, mnc, apn, carrier_name, unverified}`).
  Hostile-input fixtures cover at minimum: leading-zero MCC/MNC, the
  "Norway problem" (`NO` parsing as boolean), MNC as int, MNC out-of-
  range, missing required fields, extra fields, mixed-case country
  codes. Add hypothesis property tests if the inventory grows.
- **`event_logger/` writer shape.** Sync append-with-flush is fine for
  Phase 1 (no event volume yet); async queue can land in Phase 2 if
  cycle-duration measurements show append latency matters. Single
  writer, `O_APPEND`-safe newline-terminated JSON Lines, atomic via
  `os.write` of a single byte-sequence.
- **`config/` layering implementation.** Pydantic v2 `BaseSettings` for
  env+flag layer composed with a hand-written YAML merger for the
  `/etc/spark-modem-watchdog/conf.d/*.yaml` precedence; "topology-
  affecting" fields are tagged via a `Field(json_schema_extra={"reload":
  "restart"})` annotation that the SIGHUP reload (Phase 3) reads.
- **Closed-enum representation.** Python `enum.StrEnum` (3.11+, fine on
  3.12) so JSON serialization is automatic and mypy treats variants as
  literals.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor) MUST read these
before planning or implementing Phase 1.** Every entry is a full
relative path so the file can be read directly.

### Phase boundary & requirements

- `.planning/ROADMAP.md` §"Phase 1: Foundations & ADRs" — goal,
  requirements list, 5 success criteria.
- `.planning/REQUIREMENTS.md` §Traceability — the 12 FR + 10 NFR
  Phase-1-mapped entries (FR-30.1, FR-33.1, FR-44.1, FR-44.2, FR-54,
  FR-60, FR-62, FR-62.1, FR-63, FR-64, FR-72, FR-73, NFR-31, NFR-32,
  NFR-33, NFR-34, NFR-40, NFR-41, NFR-43, NFR-50, NFR-51, NFR-52).
- `.planning/PROJECT.md` §"Open questions" Q1-Q8 — every one of the
  eight must be closed in writing during Phase 1, by ADR or explicit
  deferral. §"Key Decisions" table tracks the outcomes.
- `CLAUDE.md` §"Critical invariants" + §"Anti-patterns" — non-negotiable
  rules that constrain Phase 1 module shape.

### Project research (deltas vs. docs/)

- `.planning/research/SUMMARY.md` — TL;DR + 9 sections; the *deltas*
  between `docs/` and current best practice. Most important single file.
- `.planning/research/STACK.md` — pinned library set, packaging recipe,
  Python 3.12 selection rationale (closes Q8).
- `.planning/research/ARCHITECTURE.md` — Q3 per-modem locks, Q9
  Prom-over-UDS, Q14 usb_path keying, Q15 schema downgrade, build order
  A..F.
- `.planning/research/PITFALLS.md` — top-15 highest-stakes pitfalls;
  §1.2 qmicli output drift / `extra='ignore'` rule; §3.1/§3.2
  state-store concurrency; §5.1 cancellation lost stdout; §9.1/§9.2
  streak persistence; §13.1 cardinality explosion.
- `.planning/research/FEATURES.md` §4.1 (5+2 state machine), §4.3 (HMAC
  v2.0), §4.5 (per-modem dry-run), §4.6 (US/UK/DE day-one).

### Wire format & schema (W-01..W-04)

- `docs/SCHEMA.md` — every persisted shape's authoritative definition
  (§2 Diag, §3 ModemState, §4 status.json, §5 events.jsonl, §6
  identity.json, §7 globals.json, §8 carrier table YAML, §9 webhook
  payload, §10 versioning policy). NB: §3 must be amended for ADR-0008's
  5+2 shape during Phase 1 ADR work.
- `docs/adr/0004-typed-contract.md` — typed wire formats; will be
  amended in Phase 1 with non-destructive downgrade clause.
- `docs/adr/0005-explicit-state-machine.md` — to be **superseded by
  ADR-0008** (5 top-level + 2 orthogonal flags); set
  `Status: Superseded by ADR-0008`.

### Packaging & CI (B-01..B-04)

- `docs/adr/0001-language-python.md` — to be amended: "Bundle CPython
  3.12 via `astral-sh/python-build-standalone`. Closes Q8."
- New ADR-0010 (packaging) — drafted in Phase 1, references
  `python-build-standalone` + `uv` + custom debhelper rule.
- `.planning/research/STACK.md` §"Packaging recipe" — the exact 5-step
  debhelper sequence (download tarball → unpack → venv → uv install →
  compileall → shims).
- `.planning/research/PITFALLS.md` §18.x packaging risks (venv path
  relocation §18.3; certifi rotation §18.5).

### State store & atomic-write (S-01..S-04)

- `docs/SCHEMA.md` §3 ModemState + §10 versioning policy.
- `docs/adr/0006-counter-decay.md` — to be amended in Phase 1: "Streak
  update + decay + counter reset + state-write are ONE atomic write per
  cycle; streak persists across daemon restarts."
- New ADR-0009 (state files keyed by `usb_path`) — to be drafted in
  Phase 1.
- New ADR-0012 (concurrency: per-modem asyncio.Lock + flocks) — to be
  drafted in Phase 1.
- `docs/RECOVERY_SPEC.md` §8 (atomic cycle ordering).
- `.planning/research/PITFALLS.md` §3.1 (cdc-wdmN renumbering), §3.2 +
  §16.1 (concurrent writers), §3.4 (schema downgrade).

### Subprocess wrapper (SP-01..SP-04)

- `.planning/research/STACK.md` §4.2 "qmicli subprocess" recipe —
  `create_subprocess_exec`, `start_new_session=True`,
  `proc.communicate(timeout=...)`, two-stage shutdown.
- `.planning/research/PITFALLS.md` §1.3 (locale `LC_ALL=C`), §5.1
  (cpython#139373 cancellation lost stdout).
- `docs/PRD.md` FR-64 / NFR-31 — list-form argv hard rule.
- `docs/ARCHITECTURE.md` §5 — qmicli is the contract, never replaced.

### Webhook subsystem (groundwork in Phase 1; full impl in Phase 2)

- New ADR-0011 (webhook subsystem) — drafted in Phase 1; HMAC v2.0
  implementation is Phase 2.
- `.planning/research/FEATURES.md` §4.3 (HMAC v2.0 cost/benefit).
- `.planning/research/PITFALLS.md` §10.1 (DNS blocking the loop).
- `docs/PRD.md` Q5 — re-classify "v2.1" → "v2.0".

### Metric surface (groundwork in Phase 1; full impl in Phase 2)

- New ADR-0013 (metric surface) — drafted in Phase 1.
- `.planning/research/PITFALLS.md` §13.1 (cardinality explosion).
- `docs/PRD.md` NFR-21 — to be amended: integer-encoded
  `modem_state_value{modem}` replaces one-hot `modem_state{modem,state}`.

### Migration / rollout context

- `docs/MIGRATION.md` §0 — Phase 1 corresponds to MIGRATION Phase 0
  (build + HIL).
- `docs/RUNBOOK.md` — operator-facing context that constrains Phase 1
  CLI surface design.
- `docs/TEST_STRATEGY.md` — Phase 1 test layout (unit / integration /
  HIL split) and the spec-as-tests philosophy.

### ADRs to AMEND in Phase 1

| ADR | Amendment |
|---|---|
| `docs/adr/0001-language-python.md` | "Bundle CPython 3.12 via `astral-sh/python-build-standalone`. Closes Q8." |
| `docs/adr/0003-zao-authority.md` | "Parser only consumes `RASCOW_STAT`; other lines accepted-but-ignored with counter; growing parsed surface is a schema-version bump." |
| `docs/adr/0004-typed-contract.md` | "Schema downgrade is non-destructive — shadow as `.from-v<N>.json`, log `schema_downgrade_pending`; reset only on explicit `ctl reset-state`." |
| `docs/adr/0005-explicit-state-machine.md` | Set `Status: Superseded by ADR-0008` (5+2 supersedes 7-state). |
| `docs/adr/0006-counter-decay.md` | "Streak update + decay + counter reset + state-write are ONE atomic write per cycle; streak persists across daemon restarts; replay test must include mid-streak restart." |

### ADRs to AUTHOR in Phase 1

| ADR | Topic |
|---|---|
| `docs/adr/0008-state-machine-5-plus-2.md` | 5 top-level states + 2 orthogonal flags; supersedes 0005 |
| `docs/adr/0009-state-files-keyed-by-usb-path.md` | `state/by-usb/<usb_path>.json`; cross-check on startup |
| `docs/adr/0010-packaging-python-build-standalone.md` | `.deb` build via PBS + uv + custom debhelper rule |
| `docs/adr/0011-webhook-subsystem.md` | HMAC v2.0 + retry/dedup queue + pre-resolved DNS |
| `docs/adr/0012-concurrency-locks.md` | per-modem asyncio.Lock + globals lock; per-modem flock + state-store flock; PID lock separate |
| `docs/adr/0013-metric-surface.md` | integer-encoded `modem_state_value{modem}`; cardinality-bounded label set |

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

**There is no `src/` tree yet.** Phase 1 is greenfield: it creates the
initial Python source layout. Existing assets are docs and research
only:

- `docs/` — 9 markdown specs + 7 ADRs that v2 must implement.
- `.planning/research/` — 4 deep research files + SUMMARY.
- `CLAUDE.md` — pre-distilled invariants and anti-patterns.

### Established Patterns

**No code patterns yet.** Phase 1 establishes the patterns:

- `mypy --strict` + `ruff check` + `ruff format --check` green from day
  one (NFR-40).
- `pytest` + `pytest-asyncio` (`mode=auto`) + `hypothesis` for tests.
- `asyncio` everywhere; **no** `subprocess.run` sync, **no** `gather +
  wait_for`, **no** `MonitorObserver` (CLAUDE.md anti-patterns).
- All wire JSON via pydantic v2 `model_dump_json` / `model_validate_json`
  (no `json.loads` of untyped dicts in production code).

### Integration Points

- `/etc/spark-modem-watchdog/conf.d/*.yaml` — configuration root;
  layered with env vars + CLI flags (FR-54).
- `/var/lib/spark-modem-watchdog/state/by-usb/<usb_path>.json` — per-
  modem state files (FR-62.1).
- `/run/spark-modem-watchdog/{lock, state.lock, modem-{usb_path}.lock,
  metrics.sock}` — runtime files.
- `/var/log/spark-modem-watchdog/events.jsonl` — structured event log
  (FR-40), groundwork in Phase 1 `event_logger/`.
- `/opt/spark-modem-watchdog/python/bin/python3.12` — bundled
  interpreter; the `.deb`'s shim entry points dispatch through it.

### Lint / quality gates established in Phase 1

- `mypy --strict` on the six modules (`clock`, `subproc`, `wire`,
  `config`, `state_store`, `event_logger`).
- `ruff check` + `ruff format --check`.
- `scripts/lint_no_subprocess.sh` (SP-04) — fails CI on
  `create_subprocess_exec`/`subprocess.run`/etc. outside `subproc/`.
- Pre-commit hook installs all three.

</code_context>

<specifics>
## Specific Ideas

The user accepted the recommended option in every question across all
four areas — alignment with the research SUMMARY's prescriptions is
total. Concrete specifics worth pinning for downstream:

- **Boundary discipline at `wire/`.** The `extra='forbid'` rule applies
  to the persisted/transmitted wire boundary (state files, status.json,
  events.jsonl, webhook payload). The qmicli parser explicitly relaxes
  to `extra='ignore'` to absorb libqmi 1.30→1.32+ output drift —
  PITFALLS §1.2 calls this out specifically. The split is *between*
  `subproc/` (which does I/O) and the parsers that produce `Diag`
  fields.
- **"All errors are data" subprocess model.** `subproc/runner.run()`
  never raises on non-zero exit or timeout — it returns a
  `CompletedProcess` with `timed_out: bool`. Exceptions only on
  genuinely-broken-runtime conditions. This pairs with FR-73's pure-
  function policy engine: the policy never `try/except`s subprocess
  outcomes; it inspects the data.
- **Belt-and-suspenders smoke test.** Phase 1 SC #1 is wired in two
  places: `debian/postinst` (fail-the-install) AND systemd
  `ExecStartPre=` (fail-the-start). Either failure is independently
  diagnostic.
- **Daemon-refuses-to-start on inventory mismatch.** Not "log warning
  and continue" — exit non-zero with a typed event. Recovery requires
  operator intervention via `ctl reset-state`. Strong default;
  intentional friction.
- **Phase 1 locks the API even though callers don't exist yet.** The
  full 3-layer locking (asyncio.Lock + flock + flock) ships now even
  though `ctl reset-state` and the daemon's full cycle don't land until
  Phase 2/3. Locking the interface in Phase 1 means later phases wire
  callers without interface churn.

</specifics>

<deferred>
## Deferred Ideas

Items mentioned during discussion or surfaced during analysis that
belong outside Phase 1 scope. None lost.

### Phase 2 (Core Daemon)

- Full `wire/Diag` parser (qmicli output → typed Diag) with
  `extra='ignore'` boundary in `qmi/parsers/`.
- `WebhookPoster` Protocol implementation: HMAC-SHA256 signing,
  `X-Spark-Timestamp` header, retry queue (3 attempts + exp backoff),
  60 s `(modem, transition)` dedup, pre-resolved cached DNS, separate
  task with explicit httpx timeouts (FR-44.1..FR-44.8).
- `MetricRegistry` Protocol implementation: integer-encoded
  `modem_state_value{modem}`, `state_duration_seconds{modem,state}`
  histogram, `cycle_drift_seconds`, `webhook_delivery_total{result}`.
- `spark-modem ctl` subcommands: `reset-state`, `migrate-state`,
  `history`, `maintenance`, `support-bundle`, `preflight`. The state-
  store API ships in Phase 1 with locks ready for them.
- Replay harness for the policy engine (≥1000 v1 cycles agreement).
- The `_healthy_streak` persistence + atomic single-write per cycle
  (FR-26.1, FR-26.2; ADR-0006 amendment lands in Phase 1, *enforcement*
  in Phase 2).

### Phase 3 (Linux Event Sources & Lifecycle)

- `pyudev.Monitor.from_netlink()` + `loop.add_reader(monitor.fileno())`
  for USB add/remove (FR-1, NFR-13).
- `pyroute2.AsyncIPRoute` for rtnetlink link-state.
- `asyncinotify` Zao-log + `events.jsonl` rotation watcher (FR-43.1).
- `/dev/kmsg` non-blocking reader for dmesg (FR-14).
- `sd_notify` `READY=1` + `STATUS=` + optional `WatchdogSec=90s` (FR-75).
- `loop.add_signal_handler` SIGTERM (graceful shutdown ≤5 s) + SIGHUP
  (transactional config reload) (FR-53, FR-54-runtime).
- PID-lock and the *real callers* of the per-modem flock + state-store
  flock that Phase 1 sets up.

### Phase 4 (Destructive Actions & HIL)

- All four destructive recovery actions (`soft_reset`, `modem_reset`,
  `usb_reset`, `driver_reset`) and their signal-quality / driver-reset
  gates (FR-23, FR-24, FR-27).

### v2.1 (already deferred in REQUIREMENTS.md)

- HTTP API on Unix socket (CTL-01, CTL-02; closes Q1 + Q4 in v2.1).
- Webhook batching (WHK-01).
- `ctl identity export/import` for RMA box swap (CARR-01).
- `ctl schema events` JSON-Schema export (SCH-01).
- `ctl simulate-issue` (SIM-01).
- 5G NR-aware policy (NR-01).

### Tactical / Claude-discretion (not full features)

- ADR landing PR composition (one umbrella PR, one commit per ADR is
  recommended).
- Repository layout details (`src/spark_modem/...`).
- `requirements.lock` location (`packaging/requirements.lock`).
- `event_logger/` writer shape (sync vs async; queued vs direct).
- `config/` layering implementation choice.
- Test layout details (`tests/{unit,integration,hil}/`).

</deferred>

---

*Phase: 01-foundations-adrs*
*Context gathered: 2026-05-06*
