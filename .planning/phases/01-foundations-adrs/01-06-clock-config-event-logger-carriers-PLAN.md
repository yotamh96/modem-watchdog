---
phase: 01-foundations-adrs
plan: 06
type: execute
wave: 3
depends_on: [01, 03]
files_modified:
  - src/spark_modem/clock/__init__.py
  - src/spark_modem/clock/clock.py
  - src/spark_modem/config/__init__.py
  - src/spark_modem/config/settings.py
  - src/spark_modem/config/yaml_merge.py
  - src/spark_modem/config/reload_marker.py
  - src/spark_modem/event_logger/__init__.py
  - src/spark_modem/event_logger/writer.py
  - debian/conf.d/00-carriers.yaml
  - tests/unit/clock/__init__.py
  - tests/unit/clock/test_clock.py
  - tests/unit/config/__init__.py
  - tests/unit/config/test_settings.py
  - tests/unit/config/test_yaml_merge.py
  - tests/unit/config/test_reload_marker.py
  - tests/unit/event_logger/__init__.py
  - tests/unit/event_logger/test_writer.py
  - tests/integration/test_default_carrier_table.py
autonomous: true
requirements:
  - FR-30.1
  - FR-33.1
  - FR-44.1
  - FR-44.2
  - FR-54
  - FR-72
  - FR-73
tags:
  - python
  - clock
  - config
  - yaml
  - event-logger
  - carrier-table

must_haves:
  truths:
    - "src/spark_modem/clock/clock.py exposes monotonic() (returns time.monotonic()) and wall_clock_iso() (returns ISO-8601 with timezone) — durations/backoffs use monotonic; ISO stamps use wall clock (ADR-0007)"
    - "src/spark_modem/config/ exposes Settings (pydantic v2 BaseSettings: env vars + CLI flags) and a YAML merger that composes /etc/spark-modem-watchdog/conf.d/*.yaml in lexical order with later files overriding earlier; layered precedence is CLI > env > YAML > defaults (FR-54)"
    - "Each Settings field carries a Field(json_schema_extra={'reload': 'restart'} | {'reload': 'data'}) marker; Phase 3 SIGHUP reload reads this to refuse topology-affecting changes mid-flight; Plan 06 ships only the marker convention + a helper that lists all 'restart' fields"
    - "src/spark_modem/event_logger/writer.py provides a sync EventLogWriter with append() that does ONE atomic os.write of a newline-terminated JSON line; single-writer-safe; survives via O_APPEND so even mid-write crashes leave the file at a valid line boundary"
    - "debian/conf.d/00-carriers.yaml exists with 12 entries: IL/425 (01,02,03 verified) + US/310,311,312 (410,480,530 unverified) + GB/234 (10,15,30 unverified) + DE/262 (01,02,03 unverified); validates via spark_modem.wire.CarrierTable; the integration test loads the file and asserts all 12 entries parse"
    - "Hostile-input fixtures from Plan 03 still pass against the carrier validators (regression cover)"
    - "Settings imports from `pydantic_settings` — the `pydantic-settings>=2.5,<3` dependency is already pinned in `packaging/requirements.in` by Plan 01 (wave 1) and is included in the lockfile by the time Plan 06 runs (wave 3)"
    - "ruff check, ruff format --check, mypy --strict are green on all four modules and the test files"
    - "Total unit-test wall time for this plan <2s"
  artifacts:
    - path: "src/spark_modem/clock/clock.py"
      provides: "monotonic() and wall_clock_iso() helpers (ADR-0007 surface)"
      contains: "time.monotonic"
    - path: "src/spark_modem/config/settings.py"
      provides: "Settings BaseSettings class (env+flag layer); reload-marker convention; helper restart_required_fields()"
      contains: "class Settings(BaseSettings)"
    - path: "src/spark_modem/config/yaml_merge.py"
      provides: "load_yaml_layer(conf_d_dir) → dict; deep_merge(base, override) → dict"
      contains: "def load_yaml_layer"
    - path: "src/spark_modem/config/reload_marker.py"
      provides: "Field marker helpers — RELOAD_DATA, RELOAD_RESTART; restart_required_fields(model) helper"
      contains: "RELOAD_RESTART"
    - path: "src/spark_modem/event_logger/writer.py"
      provides: "EventLogWriter — single-writer, sync, append-with-flush JSON Lines; O_APPEND-safe newline-terminated"
      contains: "O_APPEND"
    - path: "debian/conf.d/00-carriers.yaml"
      provides: "Default carrier table — IL/US/UK/DE day-one (FR-30.1)"
      contains: "country: IL"
  key_links:
    - from: "src/spark_modem/event_logger/writer.py"
      to: "src/spark_modem/wire/events.py"
      via: "EventLogWriter.append takes an Event union and serializes via TypeAdapter(Event).dump_json"
      pattern: "Event|EventAdapter"
    - from: "debian/conf.d/00-carriers.yaml"
      to: "src/spark_modem/wire/carriers.py CarrierTable"
      via: "tests/integration/test_default_carrier_table.py loads via yaml.safe_load + CarrierTable.model_validate"
      pattern: "CarrierTable\\.model_validate"
    - from: "src/spark_modem/clock/clock.py monotonic"
      to: "ADR-0007"
      via: "all durations + backoffs (Phase 2+) use this"
      pattern: "time\\.monotonic"
    - from: "src/spark_modem/config/settings.py reload-marker"
      to: "Phase 3 SIGHUP reload"
      via: "restart_required_fields() helper"
      pattern: "json_schema_extra.*reload"
    - from: "src/spark_modem/config/settings.py"
      to: "packaging/requirements.in (Plan 01)"
      via: "Settings imports pydantic_settings; the pin is upstreamed to Plan 01 so the lockfile carries it before Plan 06 runs"
      pattern: "from pydantic_settings import BaseSettings"
---

<objective>
Ship the four remaining Phase 1 plumbing modules (`clock/`, `config/`, `event_logger/`) and the default carrier table that validates against Plan 03's `CarrierTable`. These are thin module skeletons — the heavy lifting was front-loaded into Plans 03 and 04. The goal here is to land the API surface every Phase 2/3/4 module reads from, lock the conventions (`time.monotonic` for durations, `json_schema_extra={'reload': '...'}` for config field annotations, `O_APPEND` newline-terminated JSON Lines), and ship the day-one carrier YAML.

Purpose: Closes Phase 1 SC #3 (default carrier table covers Israel + minimal US/UK/DE with `unverified: true`; YAML parses against pydantic with hostile-input fixtures). Closes Phase 1 SC #4 partially (`mypy --strict` + `ruff check` green on `clock/`, `config/`, `event_logger/` — Plans 03/04/05 covered the rest). Closes FR-30.1 (day-one IL/US/UK/DE carriers), FR-33.1 (already covered by Plan 03's hostile-input fixtures; this plan re-runs them as a regression check against the actual default YAML). Closes FR-44.1 / FR-44.2 (HMAC v2.0 + X-Spark-Timestamp — wire shapes from Plan 03 are reused; this plan adds NO impl, only ships the carrier-table CONFIG that ADR-0011's Phase 2 work depends on indirectly via the operator-edited config layer). Closes FR-54 (configuration precedence: CLI > env > /etc/spark-modem-watchdog/conf.d/*.yaml > defaults; SIGHUP transactional reload — the marker is shipped here, the SIGHUP listener is Phase 3). Closes FR-72 (Protocol seams — `Clock`, `EventLogWriter` declared as concrete classes here; Phase 2 may add explicit `Protocol` shadows). Closes FR-73 (policy engine purity — `Clock` lives separately so `policy/` never imports `time` directly).

Output: 7 source files + 8 test files + 1 default-config YAML (the YAML data file only — the install line that ships it to `/etc/spark-modem-watchdog/conf.d/` lives in Plan 02 alongside the rest of `debian/spark-modem-watchdog.install`). Total <2s test wall time. The defaults shipped here are the ones a fresh Jetson sees on first boot of the v2.0 `.deb`.

**Scope notes (post-checker):**
- Plan 06 produces the `debian/conf.d/00-carriers.yaml` data file. Plan 02 (wave 4) owns
  `debian/spark-modem-watchdog.install` and is responsible for adding the install line that
  ships the YAML to `/etc/spark-modem-watchdog/conf.d/`. Plan 06 does NOT edit Plan 02's
  install file.
- The `pydantic-settings>=2.5,<3` dependency is upstreamed to Plan 01 (wave 1) — Plan 01 ships
  it in `packaging/requirements.in` and the regenerated `packaging/requirements.lock`, and
  Plan 02's `scripts/postinst_smoke_test.sh` includes `pydantic_settings` in its 10-import
  list. Plan 06 does NOT edit `packaging/requirements.in`, `packaging/requirements.lock`, or
  `scripts/postinst_smoke_test.sh`. By the time Plan 06 runs (wave 3), the dependency is
  already installed in the dev venv (Plan 01 wave 1 → Plan 03 wave 2 → Plan 06 wave 3).
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/01-foundations-adrs/01-CONTEXT.md
@.planning/research/SUMMARY.md
@.planning/research/PITFALLS.md
@.planning/research/FEATURES.md
@docs/SCHEMA.md
@docs/adr/0007-monotonic-clock.md
@CLAUDE.md
@src/spark_modem/wire/__init__.py
@src/spark_modem/wire/carriers.py
@src/spark_modem/wire/events.py
@packaging/requirements.in
@packaging/requirements.lock

<interfaces>
<!-- This plan creates four small modules + a YAML config. Plans 03 (wire) and 01 (CI + pinned libs) are dependencies. -->

From CONTEXT.md §"Claude's Discretion":
- event_logger/ writer shape: sync append-with-flush is fine for Phase 1 (no event volume yet);
  async queue can land in Phase 2 if cycle-duration measurements show append latency matters.
  Single writer; O_APPEND-safe newline-terminated JSON Lines; atomic via single os.write of a single byte sequence.
- config/ layering: pydantic v2 BaseSettings for env+flag layer composed with hand-written YAML
  merger for /etc/spark-modem-watchdog/conf.d/*.yaml; "topology-affecting" fields tagged via
  Field(json_schema_extra={"reload": "restart"}) annotation that the SIGHUP reload (Phase 3) reads.
- Closed-enum representation: enum.StrEnum (already done in Plan 03).

From CLAUDE.md §"Critical invariants" #4:
- All durations and backoffs use time.monotonic(). time.time() only for ISO-8601 stamps. ADR-0007.

From CONTEXT.md §"Specific Ideas":
- "Phase 1 locks the API even though callers don't exist yet." event_logger/, clock/, config/
  ship the API surface; Phase 2 wires real callers without churn.

From PITFALLS §11.2 (already locked at Plan 03 for the validator; here we ship the YAML):
- Norway problem (`country: NO` parses as bool False) — REJECTED by validator; not a problem
  for our default YAML because `country: GB` (not `country: NO`) is what we ship.
- Leading-zero MNCs require quoting: `mnc: "01"` (string), not `mnc: 01` (octal/int). The
  YAML must use quoted strings for MNCs.
- mnc as int is REJECTED; the YAML uses strings.

From .planning/research/FEATURES.md §4.6 (carrier table US/UK/DE day-one):
The exact 12-entry table:
  - IL: 425/01 Partner internetg (verified)
  - IL: 425/02 Cellcom internetg (verified)
  - IL: 425/03 Pelephone internetg (verified)
  - US: 310/410 AT&T (unverified, APN typically broadband or generic)
  - US: 311/480 Verizon (unverified, APN vzwinternet)
  - US: 312/530 Sprint/T-Mobile (unverified)
  - GB: 234/10 O2 (unverified, APN internet/m-bb.o2.co.uk)
  - GB: 234/15 Vodafone (unverified, APN internet)
  - GB: 234/30 EE (unverified, APN everywhere)
  - DE: 262/01 Telekom (unverified, APN internet.t-d1.de or internet)
  - DE: 262/02 Vodafone DE (unverified, APN web.vodafone.de or internet)
  - DE: 262/03 O2 DE (unverified, APN internet)

From CONTEXT.md §"Specific Ideas" + §"Claude's Discretion" carrier-table YAML schema shape:
- Flat list of records: `carriers: - {country, mcc, mnc, apn, carrier_name, unverified}`.
- Hostile-input fixtures cover at minimum: leading-zero MCC/MNC, Norway problem, MNC-as-int,
  MNC out-of-range, missing required fields, extra fields, mixed-case country codes.
  (Already shipped in Plan 03 tests/fixtures/wire/carriers/.)

From Plan 01 (wave 1, runs before this plan):
- `packaging/requirements.in` ships 10 pinned runtime libs INCLUDING `pydantic-settings>=2.5,<3`.
- `packaging/requirements.lock` carries the corresponding hash-pinned entry.
- The dev venv already has `pydantic_settings` importable when Plan 06 starts at wave 3.

From Plan 02 (wave 4, runs after this plan):
- `debian/spark-modem-watchdog.install` includes the line shipping `debian/conf.d/00-carriers.yaml`
  to `/etc/spark-modem-watchdog/conf.d/`. Plan 06 does NOT touch this file; the install wiring
  is Plan 02's responsibility.
- `scripts/postinst_smoke_test.sh` already imports `pydantic_settings` (1 of 10 libs) per the
  Plan 01 lib pin.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: clock/ + event_logger/ — thin modules with TDD</name>
  <files>src/spark_modem/clock/__init__.py, src/spark_modem/clock/clock.py, src/spark_modem/event_logger/__init__.py, src/spark_modem/event_logger/writer.py, tests/unit/clock/__init__.py, tests/unit/clock/test_clock.py, tests/unit/event_logger/__init__.py, tests/unit/event_logger/test_writer.py</files>
  <read_first>
    - .planning/phases/01-foundations-adrs/01-CONTEXT.md §"Claude's Discretion" event_logger/ writer shape (full)
    - docs/adr/0007-monotonic-clock.md (ADR-0007 — durations on monotonic, ISO on wall clock)
    - src/spark_modem/wire/events.py (Event discriminated union — what EventLogWriter serializes)
    - src/spark_modem/wire/__init__.py (Event, EventAdapter exports)
    - CLAUDE.md §"Critical invariants" #4 (monotonic for durations; ISO for stamps)
  </read_first>
  <behavior>
    Clock (test_clock.py):
    - Test: clock.monotonic() returns a float; two consecutive calls return non-decreasing values.
    - Test: clock.monotonic() is independent of wall-clock changes — patch `time.time` to a far-past value, monotonic() unaffected.
    - Test: clock.wall_clock_iso() returns an ISO-8601 string with timezone offset (matches `\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(Z|[+-]\d{2}:\d{2})`); UTC by default.
    - Test: clock.wall_clock_iso() can be parsed back with `datetime.fromisoformat`.
    - Test: clock.wall_clock_iso(tz=...) honors the timezone parameter.
    - Test: clock.elapsed_since(t0) returns a non-negative float (current monotonic minus t0).

    EventLogWriter (test_writer.py):
    - Test: EventLogWriter(path) creates the parent directory if absent; opens the file in O_APPEND mode (mode 0o640).
    - Test: writer.append(event) writes ONE line ending in `\n` to the file (use a DaemonStarted instance from wire.events).
    - Test: 100 sequential append() calls produce exactly 100 lines, each parseable as JSON via EventAdapter.validate_json — no torn writes.
    - Test: each line is the JSON serialization of the event; the `kind` discriminator is present on every line.
    - Test: writer.close() releases the file descriptor; subsequent append() raises a typed EventLogClosed exception (or re-opens — pick one; closed-and-reopen is simpler. Decision: closed file raises EventLogClosed; caller must construct a new writer for log rotation. This pairs with Phase 3's logrotate watcher (FR-43.1) which will close the writer on MOVE_SELF and create a new one on the next file.)
    - Test: writer is context-manager-shaped: `with EventLogWriter(path) as w: w.append(...)` — exit closes the fd.
    - Test: writer.append raises TypeError on input that isn't a known Event variant (use a non-pydantic dict).
    - Test (atomic-ish single write): patch os.write to record call counts; one append() produces exactly one os.write call. (Single-byte-sequence write is the "atomic via single os.write" property from CONTEXT.md.)
    - Test: writer.fileno() returns an int (lets Phase 3's inotify watcher hook the fd if needed).
  </behavior>
  <action>
    1. Write `tests/unit/clock/__init__.py`, `tests/unit/clock/test_clock.py`, `tests/unit/event_logger/__init__.py`, `tests/unit/event_logger/test_writer.py` — all TDD RED.

    2. Implement `src/spark_modem/clock/clock.py`:
    ```python
    """Clock helpers (ADR-0007).

    Durations and backoffs use monotonic(); ISO-8601 stamps use wall_clock_iso().
    Never call time.monotonic() or time.time() directly outside this module —
    the indirection lets policy/ (Phase 2) accept a Clock Protocol stub for tests.
    """

    from __future__ import annotations

    import time
    from datetime import datetime, timezone, tzinfo
    from typing import Final

    _DEFAULT_TZ: Final[tzinfo] = timezone.utc


    def monotonic() -> float:
        """time.monotonic() — for durations, backoffs, and rate limits.

        ADR-0007: NTP step on the Jetson can wedge wall-clock backoff; never
        use time.time() for arithmetic.
        """
        return time.monotonic()


    def elapsed_since(t0_monotonic: float) -> float:
        """Convenience: monotonic() - t0_monotonic, never negative.

        Returns 0.0 if t0 is in the future (clock skew shouldn't happen with
        monotonic; this is belt-and-suspenders).
        """
        return max(0.0, monotonic() - t0_monotonic)


    def wall_clock_iso(*, tz: tzinfo | None = None) -> str:
        """Wall-clock ISO-8601 stamp with timezone — for log lines and events.

        Uses datetime.now(tz). Default tz is UTC; ISO-8601 is the on-the-wire
        format for events.jsonl and webhook payloads. ISO stamps are
        operator-readable; durations are not — different concerns.
        """
        return datetime.now(tz or _DEFAULT_TZ).isoformat()
    ```

    3. Implement `src/spark_modem/clock/__init__.py`:
    ```python
    """clock — monotonic durations + ISO wall-clock stamps (ADR-0007)."""

    from spark_modem.clock.clock import elapsed_since, monotonic, wall_clock_iso

    __all__ = ["elapsed_since", "monotonic", "wall_clock_iso"]
    ```

    4. Implement `src/spark_modem/event_logger/writer.py`:
    ```python
    """EventLogWriter — single-writer sync JSON Lines append.

    Design (CONTEXT.md §"Claude's Discretion" — event_logger/ writer shape):
      - Sync append-with-flush; async queue deferred to Phase 2 if needed.
      - Single writer; O_APPEND so concurrent writers are kernel-serialized
        at line boundaries.
      - One os.write per append() of the full newline-terminated JSON bytes —
        on Linux, write(2) of <PIPE_BUF (4096) bytes is atomic. We don't enforce
        the size limit here; events are typically <500 bytes.
      - Caller serializes via spark_modem.wire.EventAdapter.dump_json.

    Phase 3 logrotate (FR-43.1) closes this writer on MOVE_SELF / DELETE_SELF
    inotify event and constructs a new one for the freshly-rotated file.
    """

    from __future__ import annotations

    import json
    import os
    from pathlib import Path
    from types import TracebackType
    from typing import Self

    from pydantic import TypeAdapter

    from spark_modem.wire.events import Event, EventAdapter

    _MODE = 0o640


    class EventLogClosed(RuntimeError):
        """Append attempted on a closed writer."""


    class EventLogWriter:
        """Single-writer JSON Lines append for events.jsonl.

        Use as a context manager:
            with EventLogWriter("/var/log/spark-modem-watchdog/events.jsonl") as w:
                w.append(event)

        Or own the lifetime explicitly: writer = EventLogWriter(path); ... ; writer.close().
        """

        def __init__(self, path: Path | str) -> None:
            self._path = Path(path)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._fd: int | None = os.open(
                str(self._path),
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                _MODE,
            )

        def append(self, event: Event) -> None:
            """Serialize and write one newline-terminated JSON line.

            Raises:
              EventLogClosed if the writer was closed.
              TypeError if `event` is not an Event-union member (the TypeAdapter
                surfaces a pydantic ValidationError, which we let propagate;
                tests/unit/event_logger/test_writer.py asserts TypeError-ish
                behavior on bogus dict inputs).
            """
            fd = self._fd
            if fd is None:
                raise EventLogClosed(f"writer for {self._path!s} is closed")
            line = EventAdapter.dump_json(event)  # bytes, no trailing newline
            os.write(fd, line + b"\n")

        def fileno(self) -> int:
            fd = self._fd
            if fd is None:
                raise EventLogClosed(f"writer for {self._path!s} is closed")
            return fd

        def close(self) -> None:
            fd = self._fd
            self._fd = None
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass

        # Context-manager protocol.
        def __enter__(self) -> Self:
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: TracebackType | None,
        ) -> None:
            self.close()
    ```

    5. Implement `src/spark_modem/event_logger/__init__.py`:
    ```python
    """event_logger — single-writer sync JSON Lines append for events.jsonl."""

    from spark_modem.event_logger.writer import EventLogClosed, EventLogWriter

    __all__ = ["EventLogClosed", "EventLogWriter"]
    ```

    6. Run pytest — clock + event_logger tests turn GREEN.
  </action>
  <verify>
    <automated>
      cd S:/spark/modem-watchdog && \
      .venv/bin/pytest tests/unit/clock/ tests/unit/event_logger/ -q && \
      .venv/bin/ruff check src/spark_modem/clock/ src/spark_modem/event_logger/ tests/unit/clock/ tests/unit/event_logger/ && \
      .venv/bin/ruff format --check src/spark_modem/clock/ src/spark_modem/event_logger/ && \
      .venv/bin/mypy --strict src/spark_modem/clock/ src/spark_modem/event_logger/ && \
      .venv/bin/python -c "from spark_modem.clock import monotonic, elapsed_since, wall_clock_iso; t0 = monotonic(); assert elapsed_since(t0) >= 0; iso = wall_clock_iso(); from datetime import datetime; datetime.fromisoformat(iso); print('clock: OK')" && \
      .venv/bin/python -c "import tempfile, pathlib; from spark_modem.event_logger import EventLogWriter; from spark_modem.wire.events import DaemonStarted; from spark_modem.clock import wall_clock_iso
      with tempfile.TemporaryDirectory() as d:
          p = pathlib.Path(d) / 'events.jsonl'
          with EventLogWriter(p) as w:
              w.append(DaemonStarted(ts_iso=wall_clock_iso(), version='2.0.0', bundled_python_version='3.12.7'))
          lines = p.read_bytes().splitlines()
          assert len(lines) == 1
          import json
          rec = json.loads(lines[0])
          assert rec['kind'] == 'daemon_started'
          assert rec['version'] == '2.0.0'
          print('event_logger: round-trip OK')"
    </automated>
  </verify>
  <done>
    `clock.monotonic`/`elapsed_since`/`wall_clock_iso` separate duration arithmetic from ISO-8601 stamps (ADR-0007). `EventLogWriter` opens with O_APPEND + 0o640, writes one os.write per append (newline-terminated JSON), and supports the context-manager protocol. All tests pass; mypy --strict and ruff are green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: config/ — Settings + YAML merger + reload-marker convention</name>
  <files>src/spark_modem/config/__init__.py, src/spark_modem/config/settings.py, src/spark_modem/config/yaml_merge.py, src/spark_modem/config/reload_marker.py, tests/unit/config/__init__.py, tests/unit/config/test_settings.py, tests/unit/config/test_yaml_merge.py, tests/unit/config/test_reload_marker.py</files>
  <read_first>
    - .planning/phases/01-foundations-adrs/01-CONTEXT.md §"Claude's Discretion" config/ layering implementation
    - .planning/research/SUMMARY.md §"8. Open questions" item 7 (Q6 — SIGHUP transactional reload for data; restart-only for topology)
    - docs/adr/0004-typed-contract.md (typed contract — Settings is the env+flag layer)
    - .planning/research/PITFALLS.md §11.4 (config-reload risks)
    - src/spark_modem/wire/__init__.py (re-uses pydantic ConfigDict patterns)
    - packaging/requirements.in (confirm `pydantic-settings>=2.5,<3` is pinned by Plan 01 — Plan 06 must NOT modify this file)
  </read_first>
  <behavior>
    yaml_merge.py (test_yaml_merge.py):
    - Test: deep_merge({"a": 1, "b": {"c": 2}}, {"b": {"c": 3}}) == {"a": 1, "b": {"c": 3}} (override wins on leaf).
    - Test: deep_merge({"a": [1, 2]}, {"a": [3]}) == {"a": [3]} (list replaces, NOT extends — predictable for ops).
    - Test: deep_merge({"a": 1}, {"a": {"b": 2}}) == {"a": {"b": 2}} (type change is allowed; later layer wins).
    - Test: load_yaml_layer(tmp_path) reads `*.yaml` files in lexical order, deep_merges them in order, returns the final dict.
    - Test: filename ordering — `00-base.yaml` then `99-overrides.yaml` produces a dict where 99-overrides wins.
    - Test: load_yaml_layer ignores non-yaml files (`README.md`, `.bak`).
    - Test: empty conf.d/ returns {}.
    - Test: a YAML file containing the Norway-problem syntax (`country: NO`) is loaded as `{"country": False}` BY YAML — the merger doesn't fix it; the carrier-table validator (Plan 03) catches it at the wire boundary.

    reload_marker.py (test_reload_marker.py):
    - Test: RELOAD_DATA == {"reload": "data"}; RELOAD_RESTART == {"reload": "restart"} — these are the json_schema_extra values used by Settings fields.
    - Test: restart_required_fields(model_cls) returns the set of field names whose Field has `json_schema_extra={"reload": "restart"}`. Phase 3's SIGHUP listener uses this to refuse topology-affecting changes.
    - Test: restart_required_fields ignores fields without the marker.
    - Test: a Settings subclass with mixed-marker fields produces the right partition.

    Settings (test_settings.py):
    - Test: Settings reads env vars prefixed `SPARK_MODEM_` (e.g. SPARK_MODEM_BACKOFF_SECONDS=600 maps to `backoff_seconds=600`).
    - Test: Settings field defaults are sensible: backoff_seconds=300 (FR-25), ladder_min_interval_seconds=90 (FR-25.1), healthy_streak_decay_k=10 (FR-26), webhook_url=None, webhook_allow_http=False (NFR-33), webhook_dedup_seconds=60 (M-2), maintenance_max_seconds=8*3600 (FR-50.2), state_root="/var/lib/spark-modem-watchdog", run_dir="/run/spark-modem-watchdog", events_log_path="/var/log/spark-modem-watchdog/events.jsonl", carriers_yaml_path="/etc/spark-modem-watchdog/conf.d/00-carriers.yaml".
    - Test: `state_root` field carries `RELOAD_RESTART` marker (changing where state lives requires daemon restart). `backoff_seconds` carries `RELOAD_DATA` (data-only).
    - Test: `restart_required_fields(Settings)` returns at least `{state_root, run_dir, events_log_path, metrics_socket_path}` (all topology-affecting).
    - Test: webhook_allow_http defaults to False (NFR-33); webhook_url validator rejects http://… unless allow_http=True (NFR-33). When webhook_url is None, no validation needed.
    - Test: Settings.from_yaml_layer(yaml_dict) overlays a yaml_merge.deep_merge result into the default-or-env Settings.
    - Test: `from pydantic_settings import BaseSettings` succeeds in the dev venv (proves Plan 01's pin is in effect).
  </behavior>
  <action>
    1. Write the four test files (TDD RED).

    2. Implement `src/spark_modem/config/yaml_merge.py`:
    ```python
    """YAML deep-merge for /etc/spark-modem-watchdog/conf.d/*.yaml.

    Files are merged in lexical filename order — `00-base.yaml` is loaded first,
    then `99-local.yaml` overlays it. Lists REPLACE (do not extend); leaf scalars
    are overridden by the latest layer.

    The carrier-table-validator (spark_modem.wire.CarrierTable) is what catches
    the YAML "Norway problem" (`country: NO` parses as bool); the merger here
    is YAML-shape-agnostic.
    """

    from __future__ import annotations

    from pathlib import Path
    from typing import Any

    import yaml


    def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        """Recursively merge `override` into `base`.

        - Both dict at the same path → recurse.
        - Otherwise → override wins (including type changes; including lists).
        Returns a new dict; inputs are not mutated.
        """
        out: dict[str, Any] = dict(base)
        for k, v in override.items():
            if k in out and isinstance(out[k], dict) and isinstance(v, dict):
                out[k] = deep_merge(out[k], v)
            else:
                out[k] = v
        return out


    def load_yaml_layer(conf_d_dir: Path | str) -> dict[str, Any]:
        """Read every *.yaml file under conf_d_dir in lexical order; deep-merge."""
        d = Path(conf_d_dir)
        if not d.is_dir():
            return {}
        result: dict[str, Any] = {}
        for f in sorted(d.iterdir()):
            if not f.is_file() or f.suffix not in (".yaml", ".yml"):
                continue
            try:
                content = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                # FR-63: invalid input is logged error, not crash. Plan 06 doesn't
                # have access to the event_logger from this module to avoid an
                # import cycle; we surface the error by skipping the file.
                # Phase 3 wires a structured "config_invalid" event via the daemon
                # boot path. For Phase 1, skipping is the right default.
                continue
            if isinstance(content, dict):
                result = deep_merge(result, content)
        return result
    ```

    3. Implement `src/spark_modem/config/reload_marker.py`:
    ```python
    """Field-level reload markers — annotate Settings fields with reload semantics.

    Phase 3's SIGHUP listener (FR-54) reads these to decide:
      RELOAD_DATA    → re-apply on SIGHUP without daemon restart.
      RELOAD_RESTART → log a structured 'restart_required' event and refuse
                       to apply mid-flight (changing state root or socket
                       paths is a topology change, not a config tweak).
    """

    from __future__ import annotations

    from typing import Any

    from pydantic import BaseModel
    from pydantic.fields import FieldInfo

    RELOAD_DATA: dict[str, Any] = {"reload": "data"}
    RELOAD_RESTART: dict[str, Any] = {"reload": "restart"}


    def reload_class(field_info: FieldInfo) -> str | None:
        extra = field_info.json_schema_extra
        if isinstance(extra, dict):
            value = extra.get("reload")
            if isinstance(value, str):
                return value
        return None


    def restart_required_fields(model_cls: type[BaseModel]) -> frozenset[str]:
        """Return the set of field names tagged with RELOAD_RESTART on model_cls."""
        out: set[str] = set()
        for name, info in model_cls.model_fields.items():
            if reload_class(info) == "restart":
                out.add(name)
        return frozenset(out)


    def data_reloadable_fields(model_cls: type[BaseModel]) -> frozenset[str]:
        """Return the set of field names tagged with RELOAD_DATA on model_cls."""
        out: set[str] = set()
        for name, info in model_cls.model_fields.items():
            if reload_class(info) == "data":
                out.add(name)
        return frozenset(out)
    ```

    4. Implement `src/spark_modem/config/settings.py`:
    ```python
    """Settings — env + flag layer (pydantic v2 BaseSettings).

    Layered precedence (FR-54): CLI flags > env vars > YAML conf.d/*.yaml > defaults.

    This module owns the env+flag layer. The YAML layer is read separately by
    yaml_merge.load_yaml_layer and overlaid via Settings.from_yaml_layer; the CLI
    flag layer lands in Phase 2 (the `spark-modem` argparse front-end calls
    Settings(**cli_overrides)).

    Fields are annotated with reload markers (RELOAD_DATA / RELOAD_RESTART) so
    Phase 3 SIGHUP can decide what to apply mid-flight.

    Imports `BaseSettings` from `pydantic_settings` — the `pydantic-settings>=2.5,<3`
    dependency is pinned in `packaging/requirements.in` by Plan 01 (wave 1) and is
    available in the dev venv by the time this plan executes (wave 3).
    """

    from __future__ import annotations

    from typing import Any

    from pydantic import Field, field_validator
    from pydantic_settings import BaseSettings, SettingsConfigDict

    from spark_modem.config.reload_marker import RELOAD_DATA, RELOAD_RESTART


    class Settings(BaseSettings):
        """Daemon-wide configuration. Read from env vars; overlay-able with YAML."""

        model_config = SettingsConfigDict(
            env_prefix="SPARK_MODEM_",
            env_nested_delimiter="__",
            extra="forbid",  # Reject unknown SPARK_MODEM_* env vars.
            frozen=True,     # Once loaded, immutable; SIGHUP constructs a new instance.
        )

        # --- Topology fields (RELOAD_RESTART) ---

        state_root: str = Field(
            default="/var/lib/spark-modem-watchdog",
            json_schema_extra=RELOAD_RESTART,
            description="Root dir for persistent state (per-modem files, identity, globals).",
        )
        run_dir: str = Field(
            default="/run/spark-modem-watchdog",
            json_schema_extra=RELOAD_RESTART,
            description="Runtime dir (locks, metrics socket).",
        )
        events_log_path: str = Field(
            default="/var/log/spark-modem-watchdog/events.jsonl",
            json_schema_extra=RELOAD_RESTART,
        )
        metrics_socket_path: str = Field(
            default="/run/spark-modem-watchdog/metrics.sock",
            json_schema_extra=RELOAD_RESTART,
        )
        carriers_yaml_path: str = Field(
            default="/etc/spark-modem-watchdog/conf.d/00-carriers.yaml",
            json_schema_extra=RELOAD_DATA,  # Carrier-table edit is hot-reloadable.
        )

        # --- Recovery / backoff (RELOAD_DATA) ---

        backoff_seconds: int = Field(
            default=300, ge=1,
            json_schema_extra=RELOAD_DATA,
            description="FR-25 same-action backoff (default 300s).",
        )
        ladder_min_interval_seconds: int = Field(
            default=90, ge=1,
            json_schema_extra=RELOAD_DATA,
            description="FR-25.1 cross-action ladder backoff (default 90s).",
        )
        healthy_streak_decay_k: int = Field(
            default=10, ge=1,
            json_schema_extra=RELOAD_DATA,
            description="ADR-0006 K consecutive Healthy cycles before counters decay.",
        )
        startup_delay_seconds: int = Field(
            default=15, ge=0,
            json_schema_extra=RELOAD_RESTART,
            description="NFR-13 first-cycle exemption window.",
        )

        # --- Webhook (RELOAD_DATA, except URL change is data-only too) ---

        webhook_url: str | None = Field(
            default=None,
            json_schema_extra=RELOAD_DATA,
        )
        webhook_allow_http: bool = Field(
            default=False,
            json_schema_extra=RELOAD_DATA,
            description="NFR-33: webhook URL must be https unless this is true.",
        )
        webhook_dedup_seconds: int = Field(
            default=60, ge=0,
            json_schema_extra=RELOAD_DATA,
            description="M-2: per-(modem, transition) coalescing window.",
        )
        webhook_max_retries: int = Field(
            default=3, ge=0,
            json_schema_extra=RELOAD_DATA,
        )

        # --- Maintenance / dry-run (RELOAD_DATA) ---

        maintenance_max_seconds: int = Field(
            default=8 * 3600, ge=1, le=24 * 3600,
            json_schema_extra=RELOAD_DATA,
            description="FR-50.2: max 8h hard cap on `ctl maintenance on --duration`.",
        )
        dry_run: bool = Field(
            default=False,
            json_schema_extra=RELOAD_DATA,
            description="FR-28: global dry-run toggle.",
        )

        # --- Validators ---

        @field_validator("webhook_url")
        @classmethod
        def _validate_webhook_url(cls, v: str | None) -> str | None:
            """NFR-33: https only unless webhook_allow_http=true.

            Note: pydantic v2 field_validators don't trivially see sibling-field
            values; for cross-field rules we'd need model_validator. Here we
            accept any non-None and let the model_validator below handle the
            scheme check.
            """
            if v is None:
                return None
            if not (v.startswith("http://") or v.startswith("https://")):
                raise ValueError("webhook_url must start with http:// or https://")
            return v

        @classmethod
        def from_yaml_layer(cls, yaml_dict: dict[str, Any]) -> "Settings":
            """Construct Settings with YAML-layer values; env+flags then override.

            Caller pattern:
                yaml_layer = load_yaml_layer('/etc/spark-modem-watchdog/conf.d/')
                settings = Settings.from_yaml_layer(yaml_layer)
                # Then CLI flags can override via Settings.model_copy(update={...}).
            """
            return cls(**yaml_dict)
    ```

    Note: `pydantic_settings` is imported here because Plan 01 (wave 1) shipped
    `pydantic-settings>=2.5,<3` in `packaging/requirements.in`, the regenerated
    `packaging/requirements.lock`, and the dev venv install. Plan 06 must NOT touch
    `packaging/requirements.in`, `packaging/requirements.lock`, or
    `scripts/postinst_smoke_test.sh` — those edits all live in Plans 01 and 02.

    5. Implement `src/spark_modem/config/__init__.py`:
    ```python
    """config — Settings + YAML merger + reload-marker convention."""

    from spark_modem.config.reload_marker import (
        RELOAD_DATA,
        RELOAD_RESTART,
        data_reloadable_fields,
        reload_class,
        restart_required_fields,
    )
    from spark_modem.config.settings import Settings
    from spark_modem.config.yaml_merge import deep_merge, load_yaml_layer

    __all__ = [
        "RELOAD_DATA",
        "RELOAD_RESTART",
        "Settings",
        "data_reloadable_fields",
        "deep_merge",
        "load_yaml_layer",
        "reload_class",
        "restart_required_fields",
    ]
    ```

    6. Run pytest — config tests turn GREEN.
  </action>
  <verify>
    <automated>
      cd S:/spark/modem-watchdog && \
      grep -q '^pydantic-settings>=2\.5,<3' packaging/requirements.in && \
      .venv/bin/python -c "import pydantic_settings; print('pydantic_settings importable:', pydantic_settings.__version__)" && \
      .venv/bin/pytest tests/unit/config/ -q && \
      .venv/bin/ruff check src/spark_modem/config/ tests/unit/config/ && \
      .venv/bin/ruff format --check src/spark_modem/config/ && \
      .venv/bin/mypy --strict src/spark_modem/config/ && \
      .venv/bin/python -c "from spark_modem.config import Settings, RELOAD_DATA, RELOAD_RESTART, restart_required_fields, deep_merge, load_yaml_layer; s = Settings(); assert s.backoff_seconds == 300; rf = restart_required_fields(Settings); assert 'state_root' in rf; assert 'backoff_seconds' not in rf; merged = deep_merge({'a': 1, 'b': {'c': 2}}, {'b': {'c': 3}}); assert merged == {'a': 1, 'b': {'c': 3}}; print('config: OK')"
    </automated>
  </verify>
  <done>
    `Settings` is a frozen pydantic-settings BaseSettings with env_prefix=SPARK_MODEM_, all topology-affecting fields tagged with RELOAD_RESTART, all data-only fields tagged with RELOAD_DATA. `restart_required_fields(Settings)` returns the right partition. `yaml_merge.deep_merge` and `load_yaml_layer` provide the YAML overlay. `pydantic_settings` is importable in the dev venv (Plan 01 owns the pin and lockfile entry; Plan 06 does NOT modify those files). All tests pass; mypy --strict and ruff are green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: debian/conf.d/00-carriers.yaml + integration test against CarrierTable</name>
  <files>debian/conf.d/00-carriers.yaml, tests/integration/test_default_carrier_table.py</files>
  <read_first>
    - src/spark_modem/wire/carriers.py (Plan 03 — the validator the YAML must satisfy)
    - tests/fixtures/wire/carriers/happy_minimal.yaml (Plan 03 — the reference shape)
    - .planning/research/FEATURES.md §4.6 (US/UK/DE day-one with `unverified: true`)
    - .planning/phases/01-foundations-adrs/01-CONTEXT.md §"Specific Ideas" (carrier-table YAML schema shape)
  </read_first>
  <behavior>
    test_default_carrier_table.py:
    - Test: `debian/conf.d/00-carriers.yaml` exists.
    - Test: yaml.safe_load on the file produces a dict with `schema_version: 1` and `carriers: list`.
    - Test: CarrierTable.model_validate(parsed_yaml) succeeds and produces exactly 12 entries.
    - Test: countries present: IL=3, US=3, GB=3, DE=3 (Total 12).
    - Test: all IL entries have unverified=False; all non-IL have unverified=True.
    - Test: every entry's mcc matches `^\d{3}$` and mnc matches `^\d{2,3}$`.
    - Test: APNs are non-empty and < 64 chars.
    - Test: re-running the existing Plan 03 hostile-input fixtures against CarrierTable still works (regression cover).
  </behavior>
  <action>
    1. Create `debian/conf.d/00-carriers.yaml` with the 12 day-one carriers. Use **string-quoted** MCCs and MNCs to avoid PITFALLS §11.2 leading-zero/octal traps:
    ```yaml
    # Default carrier table for spark-modem-watchdog v2.0.
    # Day-one coverage: IL (verified), plus US/UK/DE marked unverified.
    # Carrier additions are pure config; reload via SIGHUP (Phase 3).
    # Source: .planning/research/FEATURES.md §4.6.
    schema_version: 1
    carriers:
      # --- Israel (verified — production fleet) ---
      - country: IL
        mcc: "425"
        mnc: "01"
        apn: internetg
        carrier_name: Partner
        unverified: false
      - country: IL
        mcc: "425"
        mnc: "02"
        apn: internetg
        carrier_name: Cellcom
        unverified: false
      - country: IL
        mcc: "425"
        mnc: "03"
        apn: internetg
        carrier_name: Pelephone
        unverified: false

      # --- United States (unverified — APN guesses, validate before fleet rollout) ---
      - country: US
        mcc: "310"
        mnc: "410"
        apn: broadband
        carrier_name: AT&T
        unverified: true
      - country: US
        mcc: "311"
        mnc: "480"
        apn: vzwinternet
        carrier_name: Verizon
        unverified: true
      - country: US
        mcc: "312"
        mnc: "530"
        apn: fast.t-mobile.com
        carrier_name: SprintTMobile
        unverified: true

      # --- United Kingdom (unverified — ISO code is GB, not UK) ---
      - country: GB
        mcc: "234"
        mnc: "10"
        apn: m-bb.o2.co.uk
        carrier_name: O2
        unverified: true
      - country: GB
        mcc: "234"
        mnc: "15"
        apn: internet
        carrier_name: Vodafone
        unverified: true
      - country: GB
        mcc: "234"
        mnc: "30"
        apn: everywhere
        carrier_name: EE
        unverified: true

      # --- Germany (unverified) ---
      - country: DE
        mcc: "262"
        mnc: "01"
        apn: internet.t-d1.de
        carrier_name: Telekom
        unverified: true
      - country: DE
        mcc: "262"
        mnc: "02"
        apn: web.vodafone.de
        carrier_name: Vodafone-DE
        unverified: true
      - country: DE
        mcc: "262"
        mnc: "03"
        apn: internet
        carrier_name: O2-DE
        unverified: true
    ```

    2. Plan 06 does NOT edit `debian/spark-modem-watchdog.install`. Plan 02 (wave 4)
    owns that file and adds the install line:
    ```
    debian/conf.d/00-carriers.yaml /etc/spark-modem-watchdog/conf.d/
    ```
    By the time Plan 02 runs at wave 4, `debian/conf.d/00-carriers.yaml` already exists
    (Plan 06 wave 3). Plan 02's depends_on includes `[06]` so the wave ordering is enforced.
    The existing `debian/spark-modem-watchdog.dirs` (Plan 02) already creates
    `/etc/spark-modem-watchdog/conf.d`.

    3. Write `tests/integration/test_default_carrier_table.py`:
    ```python
    """Default carrier table validates and ships day-one IL/US/GB/DE coverage.

    Closes Phase 1 SC #3 — carrier table covers Israel + US/UK/DE marked
    unverified, parses against pydantic, hostile-input fixtures still reject.

    Source: .planning/research/FEATURES.md §4.6, ROADMAP §"Phase 1: Foundations & ADRs".
    """

    from __future__ import annotations

    from collections import Counter
    from pathlib import Path

    import pytest
    import yaml
    from pydantic import ValidationError

    from spark_modem.wire.carriers import CarrierTable

    REPO_ROOT = Path(__file__).resolve().parents[2]
    DEFAULT_YAML = REPO_ROOT / "debian" / "conf.d" / "00-carriers.yaml"


    def test_default_yaml_exists() -> None:
        assert DEFAULT_YAML.is_file(), DEFAULT_YAML


    def test_default_yaml_validates() -> None:
        data = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
        assert data is not None
        table = CarrierTable.model_validate(data)
        assert len(table.carriers) == 12

    def test_default_yaml_country_distribution() -> None:
        data = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
        table = CarrierTable.model_validate(data)
        countries = Counter(c.country for c in table.carriers)
        assert countries == {"IL": 3, "US": 3, "GB": 3, "DE": 3}, countries

    def test_default_yaml_il_verified_others_unverified() -> None:
        data = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
        table = CarrierTable.model_validate(data)
        for entry in table.carriers:
            if entry.country == "IL":
                assert entry.unverified is False, entry
            else:
                assert entry.unverified is True, entry

    def test_default_yaml_uses_quoted_mnc_strings_no_norway_problem() -> None:
        # Confirm we did not regress to bare unquoted country/mnc values
        # (PITFALLS §11.2). The whole-file text inspection is belt; the wire
        # validator (Plan 03) is suspenders.
        text = DEFAULT_YAML.read_text(encoding="utf-8")
        # Every mnc should appear as a quoted string, e.g. mnc: "01" — not mnc: 01.
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("mnc:"):
                # mnc: "<digits>"
                value = line[len("mnc:"):].strip()
                assert value.startswith('"') and value.endswith('"'), (
                    f"mnc line not quoted (Norway-problem hazard): {line!r}"
                )

    def test_hostile_fixtures_still_reject_after_default_table_change() -> None:
        # Regression cover: re-validate against Plan 03's hostile fixtures so
        # we don't accidentally widen the validator while shipping the default.
        fixtures = REPO_ROOT / "tests" / "fixtures" / "wire" / "carriers"
        for hostile in (
            "hostile_norway_problem.yaml",
            "hostile_leading_zero_mnc.yaml",  # this one is HAPPY (leading-zero quoted)
            "hostile_mnc_as_int.yaml",
            "hostile_mnc_too_long.yaml",
            "hostile_missing_apn.yaml",
            "hostile_extra_field.yaml",
            "hostile_mixed_case_country.yaml",
        ):
            p = fixtures / hostile
            if not p.exists():
                pytest.skip(f"fixture missing: {p} (Plan 03 not yet executed)")
                continue
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            if hostile == "hostile_leading_zero_mnc.yaml":
                # This is the HAPPY case (mnc: "01" is valid).
                CarrierTable.model_validate(data)
            else:
                with pytest.raises(ValidationError):
                    CarrierTable.model_validate(data)
    ```

    Note on `hostile_leading_zero_mnc.yaml`: in Plan 03's behavior table, this fixture is the HAPPY case ("the validator MUST accept leading-zero mnc when written as a quoted string `\"01\"`"). The integration test reflects that.
  </action>
  <verify>
    <automated>
      cd S:/spark/modem-watchdog && \
      test -f debian/conf.d/00-carriers.yaml && \
      grep -q 'country: IL' debian/conf.d/00-carriers.yaml && \
      grep -q 'country: GB' debian/conf.d/00-carriers.yaml && \
      grep -q 'country: DE' debian/conf.d/00-carriers.yaml && \
      grep -q 'country: US' debian/conf.d/00-carriers.yaml && \
      .venv/bin/pytest tests/integration/test_default_carrier_table.py -q && \
      .venv/bin/python -c "import yaml, pathlib; from spark_modem.wire.carriers import CarrierTable; data = yaml.safe_load(pathlib.Path('debian/conf.d/00-carriers.yaml').read_text(encoding='utf-8')); t = CarrierTable.model_validate(data); assert len(t.carriers) == 12; il = [c for c in t.carriers if c.country == 'IL']; assert all(not c.unverified for c in il); us = [c for c in t.carriers if c.country == 'US']; assert all(c.unverified for c in us); print('default carrier table: 12 entries, IL verified, US/GB/DE unverified — OK')"
    </automated>
  </verify>
  <done>
    `debian/conf.d/00-carriers.yaml` ships 12 day-one entries (IL=3 verified; US/GB/DE = 3 each, all unverified). The integration test validates the YAML via `CarrierTable.model_validate`, confirms the country distribution and verified/unverified split, and re-runs Plan 03's hostile-input fixtures as regression cover. All tests pass. Plan 06 does NOT edit `debian/spark-modem-watchdog.install`; that line lands in Plan 02.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Operator-edited YAML → daemon | conf.d/*.yaml is operator-writable; the YAML merger + CarrierTable validator is the gatekeeper. |
| Env vars → Settings | SPARK_MODEM_* env vars are the deployment knob. extra='forbid' rejects unknown keys (typos surface as boot failure rather than silent drift). |
| events.jsonl → external readers | The log file has mode 0o640 (NFR-30 — daemon as root); other processes need group access to read. NOC support-bundle (FR-50.3) reads it with explicit grant. |
| Wall-clock vs monotonic | Mixing the two is a known footgun — ADR-0007. The clock module makes the difference type-visible. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-06-01 | T (Tampering) | hand-edited YAML in conf.d/ | mitigate | yaml_merge.load_yaml_layer skips unparseable files (the daemon doesn't crash on bad YAML). The carrier-table validator (Plan 03 wire/carriers.py) raises ValidationError on hostile inputs (Norway problem, mnc-as-int, etc.); Plan 06's integration test re-runs these fixtures as regression cover. |
| T-06-02 | I (Information disclosure) | events.jsonl content | mitigate | EventLogWriter opens with mode 0o640. Operators reading events.jsonl need group membership; root + the daemon's group are the only readers. NFR-30 keeps the surface tight. |
| T-06-03 | T | webhook URL set to http:// | mitigate | NFR-33: Settings.webhook_allow_http defaults to False; the field validator surfaces the rule (full cross-field check happens in Phase 2's `WebhookPoster`, which receives the typed Settings). |
| T-06-04 | E (Elevation) | env-var expansion in YAML | accept | The merger uses yaml.safe_load (no !!python/object); env-var interpolation is NOT performed in YAML. Settings reads env vars separately via pydantic-settings. No code path lets a hostile YAML inject env. |
| T-06-05 | T | wall-clock vs monotonic confusion | mitigate | clock.monotonic and clock.wall_clock_iso are separate functions with separate names; ADR-0007 plus mypy + the policy/ purity rule keep the discipline. |
| T-06-06 | T | reload-marker omission on a new field | accept | The marker convention is opt-in; a future contributor who adds a field without a marker silently makes it a "no-marker" field. Mitigation: add a Phase 2 lint test that asserts every Settings field has either RELOAD_DATA or RELOAD_RESTART (deferred — not Phase 1 critical). |
| T-06-07 | I | event_logger writer single-byte vs multi-byte writes | mitigate | os.write of <PIPE_BUF (4096) bytes is atomic on Linux; events.jsonl entries are typically <500 bytes. Writer issues exactly one os.write per append. |
</threat_model>

<verification>
End-to-end check after all three tasks complete:

1. `pytest tests/unit/clock/ tests/unit/config/ tests/unit/event_logger/ tests/integration/test_default_carrier_table.py -q` — all pass; total wall time <2s.
2. `mypy --strict src/spark_modem/clock/ src/spark_modem/config/ src/spark_modem/event_logger/` — zero errors.
3. `ruff check src/spark_modem/clock/ src/spark_modem/config/ src/spark_modem/event_logger/ tests/unit/clock/ tests/unit/config/ tests/unit/event_logger/ tests/integration/test_default_carrier_table.py` — clean.
4. `bash scripts/lint_no_subprocess.sh` — passes (no subprocess in any of these modules).
5. End-to-end carrier load: `python -c "import yaml; from spark_modem.wire.carriers import CarrierTable; data = yaml.safe_load(open('debian/conf.d/00-carriers.yaml')); t = CarrierTable.model_validate(data); assert len(t.carriers) == 12"`.
6. Plan 06 ownership boundaries: `git diff --name-only` for this plan's commit MUST NOT include `packaging/requirements.in`, `packaging/requirements.lock`, `scripts/postinst_smoke_test.sh`, or `debian/spark-modem-watchdog.install` — those edits live in Plans 01 and 02.
7. `pydantic_settings` is importable: `python -c "import pydantic_settings; print(pydantic_settings.__version__)"` succeeds (proves Plan 01's pin is in effect).
8. Wall-clock vs monotonic discipline: `grep -rn 'time\.time\|time\.monotonic' src/spark_modem/ | grep -v 'src/spark_modem/clock/'` returns zero matches (every consumer uses `clock.monotonic` / `clock.wall_clock_iso` indirection — closes the ADR-0007 enforcement gap).
</verification>

<success_criteria>
- Closes Phase 1 SC #3: default carrier table at `debian/conf.d/00-carriers.yaml` ships IL/425 (verified) + US/UK/DE (unverified) covering 12 entries; YAML parses against Plan 03's CarrierTable validator; hostile-input fixtures still reject (regression cover).
- Closes Phase 1 SC #4 partially: `mypy --strict` + `ruff check` + `ruff format --check` green on `clock/`, `config/`, `event_logger/`. Plans 03/04/05 covered the rest of the modules in SC #4's enumeration.
- FR-30.1: day-one IL/US/UK/DE carriers landed in shipped config.
- FR-33.1: hostile-input fixtures from Plan 03 still pass; the carrier-table validator is Plan 03; this plan re-runs the fixtures as regression cover after the default-YAML addition.
- FR-44.1 / FR-44.2: wire shapes (HMAC v2.0 + X-Spark-Timestamp) are Plan 03; this plan ships no impl. The webhook URL/allow-http setting is here (Settings layer); Phase 2 wires the WebhookPoster.
- FR-54: configuration precedence (CLI > env > YAML > defaults) infrastructure is in place. CLI layer lands in Phase 2; SIGHUP transactional reload (the marker consumer) lands in Phase 3.
- FR-72: Clock and EventLogWriter are concrete classes; Phase 2 may declare matching `Protocol` shadows for test isolation.
- FR-73: clock.monotonic / clock.wall_clock_iso indirection lets policy/ accept a Clock Protocol stub without importing `time` directly. Lint check at end of plan: zero `time.time` / `time.monotonic` occurrences in src/spark_modem/ outside `src/spark_modem/clock/`.
- ADR-0007 surface: `clock/` is the single chokepoint for time. Wall-clock for ISO; monotonic for arithmetic.
- Cross-plan ownership: Plan 06 ships `debian/conf.d/00-carriers.yaml` only. The install wiring (`debian/spark-modem-watchdog.install` line) lives in Plan 02; the `pydantic-settings` pin (`packaging/requirements.in` / `requirements.lock`) and the `pydantic_settings` import in `scripts/postinst_smoke_test.sh` live in Plans 01 and 02 respectively.
</success_criteria>

<output>
After completion, create `.planning/phases/01-foundations-adrs/01-06-SUMMARY.md` covering: clock public surface (monotonic / elapsed_since / wall_clock_iso), config public surface (Settings + RELOAD_DATA/RESTART markers + restart_required_fields helper + load_yaml_layer + deep_merge), event_logger public surface (EventLogWriter context manager), the default carrier table contents (12 entries IL/US/GB/DE), and confirmation that Plan 06 did NOT touch `packaging/requirements.in`, `packaging/requirements.lock`, `scripts/postinst_smoke_test.sh`, or `debian/spark-modem-watchdog.install` — those edits are in Plans 01 and 02. Reference Plan 01 (owns the `pydantic-settings>=2.5,<3` pin), Plan 02 (owns the smoke-test 10-import list and the carrier-YAML install line), Plan 03 (CarrierTable validator + hostile fixtures), and forward-references Phase 3 (SIGHUP listener consumes restart_required_fields).
</output>
</content>
</invoke>