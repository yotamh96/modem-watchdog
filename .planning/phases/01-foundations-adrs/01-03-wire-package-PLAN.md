---
phase: 01-foundations-adrs
plan: 03
type: execute
wave: 2
depends_on: [01]
files_modified:
  - src/spark_modem/wire/__init__.py
  - src/spark_modem/wire/_base.py
  - src/spark_modem/wire/enums.py
  - src/spark_modem/wire/diag.py
  - src/spark_modem/wire/state.py
  - src/spark_modem/wire/events.py
  - src/spark_modem/wire/webhook.py
  - src/spark_modem/wire/identity.py
  - src/spark_modem/wire/globals.py
  - src/spark_modem/wire/carriers.py
  - src/spark_modem/wire/versioning.py
  - tests/unit/wire/__init__.py
  - tests/unit/wire/test_base.py
  - tests/unit/wire/test_enums.py
  - tests/unit/wire/test_diag.py
  - tests/unit/wire/test_state.py
  - tests/unit/wire/test_events.py
  - tests/unit/wire/test_webhook.py
  - tests/unit/wire/test_identity.py
  - tests/unit/wire/test_globals.py
  - tests/unit/wire/test_versioning.py
autonomous: true
requirements:
  - FR-62
  - FR-63
  - NFR-31
  - NFR-32
  - NFR-33
  - NFR-34
  - NFR-43
  - FR-72
  - FR-73
tags:
  - python
  - pydantic
  - wire-types
  - schema
  - tdd

must_haves:
  truths:
    - "src/spark_modem/wire/ exports BaseWire, ModemState, Diag, PlannedAction, StateTransition, WebhookPayload, Identity, GlobalsState, CarrierEntry, IssueCategory enum, IssueDetail enum, RegistrationState enum"
    - "Every wire BaseModel inherits BaseWire with model_config = ConfigDict(frozen=True, extra='forbid', populate_by_name=True)"
    - "ModemState is a flat 5+2 model: state Literal['unknown','healthy','degraded','recovering','exhausted'], recovering_level int|None, present bool, rf_blocked bool — recovering_level is None unless state == 'recovering'"
    - "Issue.who is a discriminated union via Annotated[Union[WhoModem, WhoHost], Field(discriminator='kind')]"
    - "All wire models carry schema_version: int; loading a future-version file raises SchemaVersionTooNew; loading a past-version file returns ShadowDowngrade(file, shadow_path) which the state_store layer (Plan 04) processes"
    - "All closed enums are enum.StrEnum subclasses so JSON serialization is automatic and mypy treats variants as Literals"
    - "ruff check, ruff format --check, mypy --strict are green on src/spark_modem/wire/ and tests/unit/wire/"
    - "All unit tests in tests/unit/wire/ pass and run hardware-free in <2s total"
    - "extra='forbid' rejects unknown fields with a typed pydantic ValidationError; populate_by_name=True allows alias keys; frozen=True prevents in-place mutation"
  artifacts:
    - path: "src/spark_modem/wire/_base.py"
      provides: "BaseWire root model with frozen=True, extra='forbid', populate_by_name=True"
      contains: "class BaseWire(BaseModel):\n    model_config = ConfigDict(frozen=True, extra=\"forbid\", populate_by_name=True)"
    - path: "src/spark_modem/wire/versioning.py"
      provides: "schema_version handling: CURRENT_SCHEMA_VERSION constant, SchemaVersionTooNew exception, schema-downgrade decision helper"
      contains: "CURRENT_SCHEMA_VERSION: int = 1"
    - path: "src/spark_modem/wire/enums.py"
      provides: "Closed StrEnum types: IssueCategory, IssueDetail, RegistrationState, ActionKind, ActionResult, EventKind, WebhookEventKind, DowngradeReason"
      contains: "class IssueCategory(StrEnum):"
    - path: "src/spark_modem/wire/state.py"
      provides: "ModemState (5+2 flat shape, ADR-0008), per-action counters, _healthy_streak"
      contains: "state: Literal[\"unknown\", \"healthy\", \"degraded\", \"recovering\", \"exhausted\"]"
    - path: "src/spark_modem/wire/diag.py"
      provides: "Diag snapshot type, Issue tagged-union (Who = WhoModem | WhoHost), PlannedAction, signal envelope"
      contains: "Annotated[Union[WhoModem, WhoHost], Field(discriminator=\"kind\")]"
    - path: "src/spark_modem/wire/events.py"
      provides: "events.jsonl event variants (ActionPlanned, ActionExecuted, ActionFailed, StateTransition, DaemonStarted, DaemonStopped, SchemaDowngradePending, UsbPathMismatch, MaintenanceWindow)"
      contains: "discriminator=\"kind\""
    - path: "src/spark_modem/wire/webhook.py"
      provides: "WebhookPayload + variants (HealthyToDegraded, RecoveringToExhausted, DaemonRestart, ActionFailed); X-Spark-Signature/X-Spark-Timestamp header model (header impl is Plan 02 phase, signature impl is Phase 2)"
      contains: "class WebhookPayload(BaseWire):"
    - path: "src/spark_modem/wire/identity.py"
      provides: "Identity (ICCID, IMSI, usb_path, first_seen ISO-8601, last_seen ISO-8601); identity map keyed by usb_path"
      contains: "usb_path: str"
    - path: "src/spark_modem/wire/globals.py"
      provides: "GlobalsState — driver_reset counters, last_global_action_monotonic, qmi_proxy_uptime tracking"
      contains: "class GlobalsState(BaseWire):"
    - path: "src/spark_modem/wire/carriers.py"
      provides: "CarrierEntry, CarrierTable (root model); validators: mnc str regex ^\\d{2,3}$, mcc str regex ^\\d{3}$, country uppercase 2-letter"
      contains: "mnc: str = Field(pattern=r\"^\\d{2,3}$\")"
    - path: "src/spark_modem/wire/__init__.py"
      provides: "Public re-exports of BaseWire, all enums, all top-level wire models"
      contains: "from spark_modem.wire._base import BaseWire"
  key_links:
    - from: "src/spark_modem/wire/state.py ModemState"
      to: "ADR-0008 5+2 shape"
      via: "flat top-level fields per CONTEXT.md W-04"
      pattern: "state: Literal.*recovering_level.*present.*rf_blocked"
    - from: "src/spark_modem/wire/diag.py Issue"
      to: "Who tagged union"
      via: "Annotated[Union[...], Field(discriminator='kind')]"
      pattern: "Field\\(discriminator=.kind.\\)"
    - from: "src/spark_modem/wire/_base.py BaseWire"
      to: "all wire models"
      via: "class inheritance"
      pattern: "class \\w+\\(BaseWire\\)"
    - from: "src/spark_modem/wire/versioning.py CURRENT_SCHEMA_VERSION"
      to: "every wire model that persists to disk"
      via: "schema_version: int field validator"
      pattern: "schema_version"
---

<objective>
Define every JSON wire shape the daemon emits, persists, or accepts: state files, status output, events.jsonl variants, webhook payloads, the identity map, the globals snapshot, the carrier table, and the Diag snapshot. These types are the **contracts**. Every Phase 2/3/4 module is built against them; if a wire type changes after Phase 1, downstream code shifts.

Purpose: ADR-0004 (typed wire formats with schema_version + non-destructive downgrade), ADR-0008 (5+2 state machine surface), ADR-0009 (per-modem state files; the Identity model + ModemState shape this layer expects), ADR-0011 (webhook payload contract that Phase 2 implements), ADR-0013 (no `state` one-hot on the metric — wire types must support an integer encoding so the metric layer in Phase 2 can derive a stable mapping). Closes FR-62 (atomic file writes — wire types are what's being atomically written), FR-63 (validate every external input — pydantic IS the validator), NFR-31/32/33/34 (subprocess argv + parsing + webhook URL/HMAC discipline are wire-shaped here), NFR-43 (schema-version refusal of forward-version files; non-destructive downgrade).

Output: A complete `src/spark_modem/wire/` package with 11 source files and 9 test files. `mypy --strict` and `ruff` are green. Tests run in <2s. The package is self-contained: it imports only `pydantic`, stdlib `enum`/`typing`/`re`/`datetime`, and exposes everything Phase 2/3/4 modules will need.

This plan is TDD: every wire shape gets a test file first describing the expected validation behavior (accept happy path, reject hostile input, round-trip JSON, schema-version refusal), then the model is implemented to make tests pass.
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
@docs/adr/0004-typed-contract.md
@docs/adr/0005-explicit-state-machine.md
@docs/adr/0006-counter-decay.md
@CLAUDE.md
@pyproject.toml

<interfaces>
<!-- This plan creates the wire/ package from scratch. Plans 04, 05, 06 import from it. -->
<!-- The pydantic v2 types being used: -->

From pydantic v2 (>=2.13):
```python
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic import ValidationError  # caught by callers
from typing import Annotated, Literal, Union
```

From CONTEXT.md W-01..W-04:
- W-01: per-domain file split (diag/state/events/webhook/identity/globals/carriers); `__init__.py` re-exports.
- W-02: every wire BaseModel inherits a base with `model_config = ConfigDict(frozen=True, extra='forbid', populate_by_name=True)`.
  Boundary: this is the wire boundary; the qmicli parser (Phase 2) uses `extra='ignore'`.
- W-03: discriminated unions via `Annotated[Union[VariantA, VariantB], Field(discriminator='kind')]`.
- W-04: ModemState 5+2 flat fields:
  - state: Literal['unknown', 'healthy', 'degraded', 'recovering', 'exhausted']
  - recovering_level: int | None  (None unless state == 'recovering')
  - present: bool
  - rf_blocked: bool

From docs/SCHEMA.md (read it for the full field list per shape):
- §2 Diag: per-modem snapshot envelope with Issue tagged union (Who = WhoModem | WhoHost)
- §3 ModemState (state-store): per-modem state file schema — Phase 1 must implement the 5+2 shape (NOT the legacy 7-state)
- §4 status.json
- §5 events.jsonl
- §6 identity.json
- §7 globals.json
- §8 carrier table YAML
- §9 webhook payload
- §10 versioning policy (schema_version: int)

From CLAUDE.md:
- pydantic >=2.13,<3 for every JSON shape
- Closed enums via enum.StrEnum
- match (not if/elif) on ModemState — wire types must be Literal-typed so mypy enforces match exhaustiveness in Phase 2
- ADR-0008 5+2 state shape
- ADR-0009 state files keyed by usb_path (Identity.usb_path is the join key)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: BaseWire + versioning + closed enums (foundations) with TDD</name>
  <files>src/spark_modem/wire/_base.py, src/spark_modem/wire/versioning.py, src/spark_modem/wire/enums.py, tests/unit/wire/__init__.py, tests/unit/wire/test_base.py, tests/unit/wire/test_versioning.py, tests/unit/wire/test_enums.py</files>
  <read_first>
    - .planning/phases/01-foundations-adrs/01-CONTEXT.md §"W. Wire types module" W-01..W-04 (full)
    - docs/SCHEMA.md (full file — section 10 versioning policy is critical)
    - docs/adr/0004-typed-contract.md (current state — to be amended in Plan 07 with non-destructive downgrade clause; Plan 03 implements the behavior)
    - .planning/research/SUMMARY.md §"3. Feature scope refinements" §4.1 (5+2 state shape) and §"8. Open questions" item 14 (schema-downgrade behavior)
    - .planning/research/PITFALLS.md §3.4 (schema downgrade non-destructive behavior)
    - pyproject.toml (Plan 01 ruff + mypy config — all model code must be strict-clean)
  </read_first>
  <behavior>
    BaseWire (test_base.py):
    - Test: A subclass of BaseWire with one int field is frozen — assigning to that field after construction raises pydantic ValidationError (frozen=True).
    - Test: A subclass with one int field rejects an extra unknown key during construction with ValidationError mentioning "extra_forbidden" or similar (extra='forbid').
    - Test: A subclass with `Field(alias="external_name")` accepts both the python attribute name and the alias on input (populate_by_name=True).
    - Test: model_dump_json() round-trips through model_validate_json() for a representative subclass.
    - Test: BaseWire itself has zero declared fields; instantiating BaseWire() succeeds.

    Versioning (test_versioning.py):
    - Test: CURRENT_SCHEMA_VERSION is an int and is exactly 1 (this is the v2.0 baseline).
    - Test: SchemaVersionTooNew is an Exception subclass.
    - Test: validate_schema_version(future_version=99) raises SchemaVersionTooNew with a message containing the seen version and CURRENT_SCHEMA_VERSION.
    - Test: validate_schema_version(current_version=1) returns 'current' (or the equivalent enum / Literal).
    - Test: validate_schema_version(past_version=0) returns 'downgrade' — this is the signal the state_store (Plan 04) uses to write the .from-v<N>.json shadow file.
    - Test: shadow_filename("/some/dir/2-3.1.1.json", from_version=0) returns "/some/dir/2-3.1.1.from-v0.json".
    - Test: shadow_filename for a relative path round-trips correctly.

    Enums (test_enums.py):
    - Test: IssueCategory has members CONFIG, SIM, DATAPATH, REGISTRATION, QMI (matching the FR-21 priority order).
    - Test: IssueDetail covers at least: NO_SIM, SIM_LOCKED, SIM_APP_DETECTED, NOT_REGISTERED_SEARCHING, NOT_REGISTERED_DENIED, QMI_TIMEOUT, QMI_HUNG, APN_MISMATCH, RAW_IP_OFF, NO_DATA_SESSION, NO_IPV4. (See docs/SCHEMA.md §2 + RECOVERY_SPEC.md §4 for the canonical list.)
    - Test: RegistrationState includes registered_home, registered_roaming, not_registered_searching, not_registered_denied, unknown.
    - Test: ActionKind covers set_apn, fix_raw_ip, sim_power_on, soft_reset, modem_reset, usb_reset, driver_reset (RECOVERY_SPEC § ladder).
    - Test: ActionResult covers success, failure, skipped_signal_gate, skipped_backoff, skipped_dry_run.
    - Test: EventKind covers action_planned, action_executed, action_failed, state_transition, daemon_started, daemon_stopped, schema_downgrade_pending, usb_path_mismatch, maintenance_window_started, maintenance_window_ended.
    - Test: WebhookEventKind covers healthy_to_degraded, recovering_to_exhausted, daemon_restart, action_failed.
    - Test: DowngradeReason includes file_too_old, schema_mismatch (used by versioning.py).
    - Test: Every enum is a `StrEnum` (so `IssueCategory.SIM == "sim"` and `json.dumps(IssueCategory.SIM)` produces a JSON string).
    - Test: Comparing `IssueCategory.SIM == "sim"` returns True (StrEnum behavior).
    - Test: `IssueCategory("sim")` returns IssueCategory.SIM (string round-trip).
  </behavior>
  <action>
    1. Create `tests/unit/wire/__init__.py` with a single docstring line.

    2. Write `tests/unit/wire/test_base.py` first (TDD RED), exercising the BaseWire test cases above. Use `pydantic.ValidationError` for the frozen/extra-forbidden assertions. Example skeleton:
    ```python
    """Tests for src.spark_modem.wire._base.BaseWire."""

    import pytest
    from pydantic import ValidationError

    from spark_modem.wire._base import BaseWire


    class _SampleModel(BaseWire):
        x: int


    class _AliasModel(BaseWire):
        from pydantic import Field

        external: int = Field(alias="external_name")


    def test_basewire_is_frozen() -> None:
        m = _SampleModel(x=1)
        with pytest.raises(ValidationError):
            m.x = 2  # type: ignore[misc]

    # ... (extra=forbid, populate_by_name, round-trip, empty BaseWire)
    ```

    3. Write `tests/unit/wire/test_versioning.py` (TDD RED).

    4. Write `tests/unit/wire/test_enums.py` (TDD RED). For exhaustiveness, parametrize the StrEnum-equality tests over each enum class.

    5. Run `pytest tests/unit/wire/test_base.py tests/unit/wire/test_versioning.py tests/unit/wire/test_enums.py` — confirm all tests fail with ImportError (the modules don't exist yet). This is the RED state.

    6. Implement `src/spark_modem/wire/_base.py`:
    ```python
    """Base wire model.

    Every persisted-or-transmitted wire shape inherits BaseWire. This is the
    *strict* wire boundary: frozen to prevent post-construction mutation,
    extra='forbid' to reject unknown fields, populate_by_name to accept
    both attribute names and aliases on input.

    The qmicli output parser in `qmi/parsers/` (Phase 2) uses extra='ignore'
    instead — see CONTEXT.md W-02 boundary split.
    """

    from pydantic import BaseModel, ConfigDict


    class BaseWire(BaseModel):
        """Strict wire base: frozen, extra=forbid, populate_by_name."""

        model_config = ConfigDict(
            frozen=True,
            extra="forbid",
            populate_by_name=True,
        )
    ```

    7. Implement `src/spark_modem/wire/versioning.py`:
    ```python
    """Schema versioning + non-destructive downgrade.

    ADR-0004 (amended in Plan 07): downgrade is non-destructive. A file that
    declares schema_version < CURRENT_SCHEMA_VERSION is preserved as
    `<original>.from-v<N>.json`; the daemon writes a fresh-default file at
    its own version and emits a structured `schema_downgrade_pending` event.

    A file that declares schema_version > CURRENT_SCHEMA_VERSION is refused;
    the caller (state_store.load) raises SchemaVersionTooNew so the daemon
    can refuse to start (FR-63 — invalid input is logged error, not crash).
    """

    from __future__ import annotations

    from pathlib import Path
    from typing import Literal

    CURRENT_SCHEMA_VERSION: int = 1
    """Bump on any schema-incompatible change. Phase 1 ships v1; Phase 2+ may bump."""


    class SchemaVersionTooNew(Exception):
        """Raised when a persisted file declares a schema_version > CURRENT_SCHEMA_VERSION.

        The daemon refuses to load forward-version files (NFR-43). Caller's
        recovery is `ctl reset-state --modem=<usb_path>` or operator manual
        intervention.
        """

        def __init__(self, *, seen: int, current: int, where: str = "<unknown>") -> None:
            self.seen = seen
            self.current = current
            self.where = where
            super().__init__(
                f"Schema version {seen} > current {current} at {where}; "
                "refusing to load (NFR-43)."
            )


    SchemaVersionDecision = Literal["current", "downgrade", "current_or_too_new"]


    def validate_schema_version(*, file_version: int, where: str = "<unknown>") -> SchemaVersionDecision:
        """Compare a file's declared schema_version to CURRENT_SCHEMA_VERSION.

        Returns:
          - "current"   when file_version == CURRENT_SCHEMA_VERSION
          - "downgrade" when file_version < CURRENT_SCHEMA_VERSION
            (caller writes the .from-v<N>.json shadow and a fresh default at v<current>)

        Raises SchemaVersionTooNew on file_version > CURRENT_SCHEMA_VERSION.
        """
        if file_version > CURRENT_SCHEMA_VERSION:
            raise SchemaVersionTooNew(seen=file_version, current=CURRENT_SCHEMA_VERSION, where=where)
        if file_version == CURRENT_SCHEMA_VERSION:
            return "current"
        return "downgrade"


    def shadow_filename(original: str | Path, *, from_version: int) -> Path:
        """Compute the shadow filename for a non-destructive downgrade.

        e.g. shadow_filename("/var/lib/.../2-3.1.1.json", from_version=0)
             == Path("/var/lib/.../2-3.1.1.from-v0.json")
        """
        p = Path(original)
        # Replace the last suffix (e.g. .json) with .from-v<N>.json.
        suffix = p.suffix or ".json"
        return p.with_suffix(f".from-v{from_version}{suffix}")
    ```

    8. Implement `src/spark_modem/wire/enums.py` with all the closed enums tested in step 4. Use `enum.StrEnum` (3.11+, fine on 3.12 — CONTEXT.md "Closed-enum representation"):
    ```python
    """Closed enums for the wire boundary.

    Every enum is a StrEnum so JSON serialization is automatic and mypy
    treats variants as Literals (CLAUDE.md: match — not if/elif — on
    ModemState requires Literal-typed values).
    """

    from __future__ import annotations

    from enum import StrEnum


    class IssueCategory(StrEnum):
        """Action priority order: config > sim > datapath > registration > qmi (FR-21)."""

        CONFIG = "config"
        SIM = "sim"
        DATAPATH = "datapath"
        REGISTRATION = "registration"
        QMI = "qmi"


    class IssueDetail(StrEnum):
        """Specific diagnosable issues. See docs/RECOVERY_SPEC.md §4 decision table."""

        # Config / SIM
        NO_SIM = "no_sim"
        SIM_LOCKED = "sim_locked"
        SIM_APP_DETECTED = "sim_app_detected"
        # Datapath
        APN_MISMATCH = "apn_mismatch"
        RAW_IP_OFF = "raw_ip_off"
        NO_DATA_SESSION = "no_data_session"
        NO_IPV4 = "no_ipv4"
        # Registration
        NOT_REGISTERED_SEARCHING = "not_registered_searching"
        NOT_REGISTERED_DENIED = "not_registered_denied"
        # QMI
        QMI_TIMEOUT = "qmi_timeout"
        QMI_HUNG = "qmi_hung"
        QMI_PROXY_DIED = "qmi_proxy_died"


    class RegistrationState(StrEnum):
        REGISTERED_HOME = "registered_home"
        REGISTERED_ROAMING = "registered_roaming"
        NOT_REGISTERED_SEARCHING = "not_registered_searching"
        NOT_REGISTERED_DENIED = "not_registered_denied"
        UNKNOWN = "unknown"


    class ActionKind(StrEnum):
        """RECOVERY_SPEC.md ladder: set_apn / fix_raw_ip / sim_power_on /
        soft_reset → modem_reset → usb_reset; global driver_reset."""

        SET_APN = "set_apn"
        FIX_RAW_IP = "fix_raw_ip"
        SIM_POWER_ON = "sim_power_on"
        SOFT_RESET = "soft_reset"
        MODEM_RESET = "modem_reset"
        USB_RESET = "usb_reset"
        DRIVER_RESET = "driver_reset"


    class ActionResult(StrEnum):
        SUCCESS = "success"
        FAILURE = "failure"
        SKIPPED_SIGNAL_GATE = "skipped_signal_gate"
        SKIPPED_BACKOFF = "skipped_backoff"
        SKIPPED_DRY_RUN = "skipped_dry_run"


    class EventKind(StrEnum):
        """events.jsonl variants. discriminator='kind' on the union."""

        ACTION_PLANNED = "action_planned"
        ACTION_EXECUTED = "action_executed"
        ACTION_FAILED = "action_failed"
        STATE_TRANSITION = "state_transition"
        DAEMON_STARTED = "daemon_started"
        DAEMON_STOPPED = "daemon_stopped"
        SCHEMA_DOWNGRADE_PENDING = "schema_downgrade_pending"
        USB_PATH_MISMATCH = "usb_path_mismatch"
        MAINTENANCE_WINDOW_STARTED = "maintenance_window_started"
        MAINTENANCE_WINDOW_ENDED = "maintenance_window_ended"


    class WebhookEventKind(StrEnum):
        """webhook payload variants. discriminator='kind' on the union."""

        HEALTHY_TO_DEGRADED = "healthy_to_degraded"
        RECOVERING_TO_EXHAUSTED = "recovering_to_exhausted"
        DAEMON_RESTART = "daemon_restart"
        ACTION_FAILED = "action_failed"


    class DowngradeReason(StrEnum):
        FILE_TOO_OLD = "file_too_old"
        SCHEMA_MISMATCH = "schema_mismatch"


    class DaemonStopReason(StrEnum):
        """Reason enum on daemon_stopped events / DaemonRestart webhooks (M-6)."""

        SIGTERM = "sigterm"
        CRASH = "crash"
        CONFIG_INVALID = "config_invalid"
        OOM = "oom"
        KILL = "kill"
    ```

    9. Run pytest again — all three test files turn GREEN.
  </action>
  <verify>
    <automated>
      cd S:/spark/modem-watchdog && \
      .venv/bin/pytest tests/unit/wire/test_base.py tests/unit/wire/test_versioning.py tests/unit/wire/test_enums.py -q && \
      .venv/bin/ruff check src/spark_modem/wire/_base.py src/spark_modem/wire/versioning.py src/spark_modem/wire/enums.py tests/unit/wire/test_base.py tests/unit/wire/test_versioning.py tests/unit/wire/test_enums.py && \
      .venv/bin/ruff format --check src/spark_modem/wire/_base.py src/spark_modem/wire/versioning.py src/spark_modem/wire/enums.py tests/unit/wire/test_base.py tests/unit/wire/test_versioning.py tests/unit/wire/test_enums.py && \
      .venv/bin/mypy --strict src/spark_modem/wire/_base.py src/spark_modem/wire/versioning.py src/spark_modem/wire/enums.py && \
      .venv/bin/python -c "from spark_modem.wire._base import BaseWire; from spark_modem.wire.versioning import CURRENT_SCHEMA_VERSION, SchemaVersionTooNew, validate_schema_version, shadow_filename; from spark_modem.wire.enums import IssueCategory, IssueDetail, RegistrationState, ActionKind, ActionResult, EventKind, WebhookEventKind, DowngradeReason, DaemonStopReason; assert CURRENT_SCHEMA_VERSION == 1; assert IssueCategory.SIM == 'sim'; print('foundations: OK')"
    </automated>
  </verify>
  <done>
    BaseWire is a frozen, extra-forbidden, populate-by-name pydantic root. CURRENT_SCHEMA_VERSION is 1. SchemaVersionTooNew raises with seen/current/where; `validate_schema_version` returns 'current' / 'downgrade' / raises. `shadow_filename` produces `<original>.from-v<N>.json`. All 9+ closed enums are StrEnum subclasses with the expected members. All tests pass; ruff and mypy --strict are green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: ModemState, Identity, Globals, CarrierTable (state-shaped wire types) with TDD</name>
  <files>src/spark_modem/wire/state.py, src/spark_modem/wire/identity.py, src/spark_modem/wire/globals.py, src/spark_modem/wire/carriers.py, tests/unit/wire/test_state.py, tests/unit/wire/test_identity.py, tests/unit/wire/test_globals.py, tests/fixtures/wire/carriers/__init__.py, tests/fixtures/wire/carriers/hostile_norway_problem.yaml, tests/fixtures/wire/carriers/hostile_leading_zero_mnc.yaml, tests/fixtures/wire/carriers/hostile_mnc_as_int.yaml, tests/fixtures/wire/carriers/hostile_mnc_too_long.yaml, tests/fixtures/wire/carriers/hostile_missing_apn.yaml, tests/fixtures/wire/carriers/hostile_extra_field.yaml, tests/fixtures/wire/carriers/hostile_mixed_case_country.yaml, tests/fixtures/wire/carriers/happy_minimal.yaml, tests/unit/wire/test_carriers.py</files>
  <read_first>
    - src/spark_modem/wire/_base.py and src/spark_modem/wire/enums.py and src/spark_modem/wire/versioning.py (just written in Task 1)
    - .planning/phases/01-foundations-adrs/01-CONTEXT.md §"W. Wire types module" W-04 (5+2 flat shape)
    - .planning/phases/01-foundations-adrs/01-CONTEXT.md §"Claude's Discretion" carrier-table YAML schema shape (flat list of records)
    - docs/SCHEMA.md §3 ModemState, §6 identity.json, §7 globals.json, §8 carrier table
    - .planning/research/PITFALLS.md §11.2 (YAML "Norway problem", leading-zero MNC) — full section
    - .planning/research/FEATURES.md §4.6 (US/UK/DE day-one carrier coverage)
    - tests/unit/wire/test_base.py and tests/unit/wire/test_enums.py (the test patterns to follow — pytest style, parametrize, ValidationError raises)
  </read_first>
  <behavior>
    ModemState (test_state.py):
    - Test: ModemState(state="healthy", recovering_level=None, present=True, rf_blocked=False, schema_version=1) constructs cleanly.
    - Test: ModemState with state="recovering" and recovering_level=2 constructs cleanly; with recovering_level=None on state="recovering" raises ValidationError.
    - Test: ModemState with state="healthy" and recovering_level=2 raises ValidationError ("recovering_level must be None unless state == 'recovering'").
    - Test: state Literal — only the 5 strings 'unknown', 'healthy', 'degraded', 'recovering', 'exhausted' are accepted. 'rf_blocked' is NOT a state (it's a flag); the validator must reject `state="rf_blocked"` since rf_blocked moved to the orthogonal flag in ADR-0008.
    - Test: ModemState carries `_healthy_streak: int >= 0` (FR-26.1 — persisted every cycle, reloaded on start).
    - Test: ModemState carries per-action counters (a `counters: dict[ActionKind, int]` with non-negative ints; default empty dict).
    - Test: ModemState carries `last_action_monotonic: float | None` (default None; ADR-0007 — monotonic, not wall-clock).
    - Test: ModemState carries `last_state_transition_iso: str` (ISO-8601 with timezone — ADR-0007 says wall-clock for ISO stamps; pydantic AwareDatetime or str regex).
    - Test: ModemState round-trips via model_dump_json() / model_validate_json().
    - Test: state_to_int(ModemState) returns a stable integer encoding for the modem_state_value{modem} metric (ADR-0013): unknown=0, healthy=1, degraded=2, recovering=3, exhausted=4.

    Identity (test_identity.py):
    - Test: Identity(usb_path="2-3.1.1", iccid="89972...", imsi="425010...", first_seen_iso="2026-05-06T00:00:00Z", last_seen_iso=..., schema_version=1) constructs cleanly.
    - Test: usb_path validator: pattern `^\d+(-\d+)*(\.\d+)*$` accepts "2-3.1.1", "2-3", "1-1.4.2", rejects "cdc-wdm0", empty string, "../../etc/passwd".
    - Test: iccid validator: pattern `^\d{18,22}$` (per ITU-T E.118).
    - Test: imsi validator: pattern `^\d{14,15}$`.
    - Test: A SIM swap is detectable: two Identity objects at the same usb_path with different iccids are NOT equal (frozen models compare by fields).

    Globals (test_globals.py):
    - Test: GlobalsState(driver_reset_count=0, last_driver_reset_monotonic=None, last_driver_reset_iso=None, qmi_proxy_uptime_seconds=0.0, schema_version=1) constructs.
    - Test: driver_reset_count >= 0 (ge=0 constraint).
    - Test: round-trips via JSON.

    CarrierTable (test_carriers.py):
    - Test: CarrierEntry(country="IL", mcc="425", mnc="01", apn="internetg", carrier_name="Partner", unverified=False) constructs.
    - Test (Norway problem): Loading `hostile_norway_problem.yaml` where the row has `country: NO` — without a string-coerce validator, PyYAML parses NO as boolean False. The validator MUST coerce to string OR reject with a clear error referencing the row. Decision: REJECT — `country: str` with `pattern=r"^[A-Z]{2}$"`; YAML's `country: NO` parses as `False` and pydantic rejects with type error. The fixture asserts the error message points at the offending row.
    - Test (leading-zero MNC): fixture `hostile_leading_zero_mnc.yaml` has `mnc: "01"`; the validator MUST accept (mnc is a string, regex `^\d{2,3}$`).
    - Test (MNC as int): fixture `hostile_mnc_as_int.yaml` has `mnc: 1` (int, not string). The validator MUST reject with a message indicating "mnc must be a string"; pydantic v2 with `mnc: str` and Strict mode coerces or rejects depending on the model_config — for the wire boundary we want REJECTION (extra='forbid' is for fields, but type strictness is per-field; use `Field(strict=True)` on mnc, or a `field_validator` that raises if input isn't `str`).
    - Test (MNC too long): fixture `hostile_mnc_too_long.yaml` has `mnc: "1234"` — regex rejects.
    - Test (missing APN): fixture `hostile_missing_apn.yaml` omits the `apn` key — pydantic raises "Field required".
    - Test (extra field): fixture `hostile_extra_field.yaml` has a `bogus: true` key — extra='forbid' rejects.
    - Test (mixed-case country): fixture `hostile_mixed_case_country.yaml` has `country: il` — uppercase regex rejects (or, alternatively, validator uppercases. Decision: REJECT with clear error; the canonical written form is uppercase ISO 3166-1 alpha-2).
    - Test (happy path): fixture `happy_minimal.yaml` with Israel (425/01/02/03), US (310/410, 311/480, 312/530 unverified), UK (234/10, 234/15, 234/30 unverified), DE (262/01, 262/02, 262/03 unverified) loads cleanly and roundtrips.
    - Test: hypothesis property test — generate `mnc` strings of length 2 or 3 made of digits → always accepted; generate strings of length 0, 1, or >=4, or non-digit → always rejected.
  </behavior>
  <action>
    1. Write all four test files (TDD RED): `test_state.py`, `test_identity.py`, `test_globals.py`, `test_carriers.py`.
       - For `test_carriers.py` use `pytest.fixture` to load YAML via `yaml.safe_load`. The hostile-input YAML fixtures are tiny (5–10 lines each); place under `tests/fixtures/wire/carriers/`.
       - Use `pydantic.ValidationError` for the rejection assertions; for the Norway-problem YAML use `yaml.safe_load` first, then pass the dict to `CarrierTable.model_validate`. Assert that the exception's `.errors()` list contains an entry whose `loc` includes the offending row index and field name.
       - Property test: `from hypothesis import given, strategies as st`, `@given(st.text())` constrained or `from_regex` to assert validator behavior over generated strings.

    2. Write hostile fixture YAML files. Example for `hostile_norway_problem.yaml`:
    ```yaml
    schema_version: 1
    carriers:
      - country: IL
        mcc: "425"
        mnc: "01"
        apn: internetg
        carrier_name: Partner
        unverified: false
      - country: NO          # YAML 1.1 parses bare NO as boolean False — Norway problem.
        mcc: "242"
        mnc: "01"
        apn: internet
        carrier_name: Telenor
        unverified: true
    ```

    Example `happy_minimal.yaml` (covers all 12 carrier entries from FR-30.1):
    ```yaml
    schema_version: 1
    carriers:
      - {country: IL, mcc: "425", mnc: "01", apn: internetg, carrier_name: Partner, unverified: false}
      - {country: IL, mcc: "425", mnc: "02", apn: internetg, carrier_name: Cellcom, unverified: false}
      - {country: IL, mcc: "425", mnc: "03", apn: internetg, carrier_name: Pelephone, unverified: false}
      - {country: US, mcc: "310", mnc: "410", apn: vzwinternet, carrier_name: AT&T, unverified: true}
      - {country: US, mcc: "311", mnc: "480", apn: vzwinternet, carrier_name: Verizon, unverified: true}
      - {country: US, mcc: "312", mnc: "530", apn: vzwinternet, carrier_name: SprintTMobile, unverified: true}
      - {country: GB, mcc: "234", mnc: "10", apn: internet, carrier_name: O2, unverified: true}
      - {country: GB, mcc: "234", mnc: "15", apn: internet, carrier_name: Vodafone, unverified: true}
      - {country: GB, mcc: "234", mnc: "30", apn: internet, carrier_name: EE, unverified: true}
      - {country: DE, mcc: "262", mnc: "01", apn: internet, carrier_name: Telekom, unverified: true}
      - {country: DE, mcc: "262", mnc: "02", apn: internet, carrier_name: Vodafone-DE, unverified: true}
      - {country: DE, mcc: "262", mnc: "03", apn: internet, carrier_name: O2-DE, unverified: true}
    ```

    Note: Use `country: GB` (ISO 3166-1 alpha-2) for the United Kingdom — the project guide says "UK" colloquially, but the canonical ISO code is GB. Both `IL` and `GB` are present in the fixture.

    3. Run pytest — all four test files RED.

    4. Implement `src/spark_modem/wire/state.py`:
    ```python
    """ModemState (per-modem state file).

    ADR-0008 5+2 shape: 5 top-level states + 2 orthogonal flags.
    ADR-0009 keying: this model is persisted at state/by-usb/<usb_path>.json.
    ADR-0006 amendment: _healthy_streak persisted every cycle, reloaded on start.
    ADR-0007: last_action_monotonic uses time.monotonic(); ISO timestamps wall-clock.
    """

    from __future__ import annotations

    from typing import Literal

    from pydantic import Field, model_validator

    from spark_modem.wire._base import BaseWire
    from spark_modem.wire.enums import ActionKind
    from spark_modem.wire.versioning import CURRENT_SCHEMA_VERSION

    StateLiteral = Literal["unknown", "healthy", "degraded", "recovering", "exhausted"]


    # Canonical integer encoding for the modem_state_value{modem} Prom metric (ADR-0013).
    # NO ONE-HOT LABEL — see CLAUDE.md anti-pattern catalogue and PITFALLS §13.1.
    _STATE_TO_INT: dict[str, int] = {
        "unknown":    0,
        "healthy":    1,
        "degraded":   2,
        "recovering": 3,
        "exhausted":  4,
    }


    class ModemState(BaseWire):
        """Per-modem state. Persisted at state/by-usb/<usb_path>.json (ADR-0009)."""

        schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, ge=1)

        # 5 top-level states (ADR-0008).
        state: StateLiteral

        # Orthogonal flag #1 (ADR-0008): is the modem currently visible on USB?
        present: bool

        # Orthogonal flag #2 (ADR-0008): is RF below the signal-quality gate?
        rf_blocked: bool

        # Recovering depth (only meaningful when state == "recovering").
        recovering_level: int | None = Field(default=None, ge=1)

        # FR-26.1: persisted every cycle, reloaded on daemon start.
        healthy_streak: int = Field(default=0, ge=0, alias="_healthy_streak")

        # Per-action escalation counters (ADR-0006). Decay to zero after K consecutive
        # Healthy cycles; persisted every cycle.
        counters: dict[ActionKind, int] = Field(default_factory=dict)

        # Monotonic timestamp of the last action attempted on this modem (ADR-0007).
        # None on first observation.
        last_action_monotonic: float | None = None

        # Wall-clock ISO-8601 stamp of the last state transition (ADR-0007 — wall
        # clock is fine for ISO timestamps; only durations / backoffs use monotonic).
        last_state_transition_iso: str | None = None

        @model_validator(mode="after")
        def _check_recovering_level(self) -> "ModemState":
            """recovering_level must be set iff state == 'recovering'."""
            if self.state == "recovering":
                if self.recovering_level is None:
                    raise ValueError(
                        "recovering_level is required when state == 'recovering'"
                    )
            else:
                if self.recovering_level is not None:
                    raise ValueError(
                        f"recovering_level must be None when state == {self.state!r} "
                        f"(only used for state == 'recovering')"
                    )
            return self

        @model_validator(mode="after")
        def _check_counters_nonneg(self) -> "ModemState":
            for k, v in self.counters.items():
                if v < 0:
                    raise ValueError(f"counters[{k!s}] must be >= 0; got {v}")
            return self


    def state_to_int(s: ModemState) -> int:
        """Canonical encoding for the modem_state_value{modem} metric (ADR-0013).

        The integer mapping is *stable* across releases: never reuse a number for
        a different state. Add new states by extending the table at the end.
        """
        return _STATE_TO_INT[s.state]
    ```

    5. Implement `src/spark_modem/wire/identity.py`:
    ```python
    """Identity map (ICCID/IMSI <-> usb_path).

    Persisted as a single identity.json keyed by usb_path. SIM swap detection
    (FR-4) compares stored ICCID against the live SIM at the same usb_path.
    """

    from __future__ import annotations

    from pydantic import Field

    from spark_modem.wire._base import BaseWire
    from spark_modem.wire.versioning import CURRENT_SCHEMA_VERSION

    # USB path: integer-dot syntax matching sysfs (e.g. "2-3.1.1").
    _USB_PATH_PATTERN = r"^\d+(-\d+(\.\d+)*)?$"


    class Identity(BaseWire):
        """One row of the identity map; keyed by usb_path in the parent map."""

        schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, ge=1)
        usb_path: str = Field(pattern=_USB_PATH_PATTERN, min_length=1, max_length=64)
        iccid: str = Field(pattern=r"^\d{18,22}$")
        imsi: str = Field(pattern=r"^\d{14,15}$")
        first_seen_iso: str
        last_seen_iso: str
    ```

    6. Implement `src/spark_modem/wire/globals.py`:
    ```python
    """Globals state (driver_reset cooldown, qmi_proxy uptime tracking)."""

    from __future__ import annotations

    from pydantic import Field

    from spark_modem.wire._base import BaseWire
    from spark_modem.wire.versioning import CURRENT_SCHEMA_VERSION


    class GlobalsState(BaseWire):
        schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, ge=1)
        driver_reset_count: int = Field(default=0, ge=0)
        last_driver_reset_monotonic: float | None = None
        last_driver_reset_iso: str | None = None
        qmi_proxy_uptime_seconds: float = Field(default=0.0, ge=0.0)
    ```

    7. Implement `src/spark_modem/wire/carriers.py`:
    ```python
    """Carrier table (MCC, MNC -> APN lookup).

    FR-30 / FR-30.1 / FR-33 / FR-33.1: editable without code release; loads from
    /etc/spark-modem-watchdog/conf.d/00-carriers.yaml; hostile-input fixtures
    cover the YAML "Norway problem", leading-zero MNCs, MNC-as-int, etc.
    """

    from __future__ import annotations

    from pydantic import Field, StrictStr

    from spark_modem.wire._base import BaseWire
    from spark_modem.wire.versioning import CURRENT_SCHEMA_VERSION


    class CarrierEntry(BaseWire):
        # ISO 3166-1 alpha-2; canonical form is uppercase. We REJECT mixed-case
        # rather than coerce — input cleanliness over tolerance for the wire.
        country: StrictStr = Field(pattern=r"^[A-Z]{2}$")

        # ITU-T E.212 MCC: exactly 3 decimal digits, persisted as a string so YAML's
        # number coercion can't strip a leading zero (PITFALLS §11.2).
        mcc: StrictStr = Field(pattern=r"^\d{3}$")

        # MNC: 2 or 3 decimal digits as a string. `mnc: 01` (leading zero) MUST be
        # written as a quoted string in YAML; a bare `01` is an octal literal in
        # YAML 1.1 — the StrictStr rejects an int with a clear "must be a string"
        # error.
        mnc: StrictStr = Field(pattern=r"^\d{2,3}$")

        apn: StrictStr = Field(min_length=1, max_length=63)
        carrier_name: StrictStr = Field(min_length=1, max_length=63)
        unverified: bool = False


    class CarrierTable(BaseWire):
        schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, ge=1)
        carriers: list[CarrierEntry]
    ```

    8. Run pytest — all four files turn GREEN.
  </action>
  <verify>
    <automated>
      cd S:/spark/modem-watchdog && \
      .venv/bin/pytest tests/unit/wire/test_state.py tests/unit/wire/test_identity.py tests/unit/wire/test_globals.py tests/unit/wire/test_carriers.py -q && \
      .venv/bin/ruff check src/spark_modem/wire/state.py src/spark_modem/wire/identity.py src/spark_modem/wire/globals.py src/spark_modem/wire/carriers.py tests/unit/wire/test_state.py tests/unit/wire/test_identity.py tests/unit/wire/test_globals.py tests/unit/wire/test_carriers.py && \
      .venv/bin/ruff format --check src/spark_modem/wire/state.py src/spark_modem/wire/identity.py src/spark_modem/wire/globals.py src/spark_modem/wire/carriers.py && \
      .venv/bin/mypy --strict src/spark_modem/wire/state.py src/spark_modem/wire/identity.py src/spark_modem/wire/globals.py src/spark_modem/wire/carriers.py && \
      .venv/bin/python -c "from spark_modem.wire.state import ModemState, state_to_int; m = ModemState(state='recovering', recovering_level=2, present=True, rf_blocked=False); assert state_to_int(m) == 3; from spark_modem.wire.carriers import CarrierTable; import yaml, pathlib; data = yaml.safe_load(pathlib.Path('tests/fixtures/wire/carriers/happy_minimal.yaml').read_text()); t = CarrierTable.model_validate(data); assert len(t.carriers) == 12; print('state/identity/globals/carriers: OK')"
    </automated>
  </verify>
  <done>
    ModemState enforces the 5+2 invariant (recovering_level ↔ state == 'recovering'); state_to_int returns the stable ADR-0013 mapping. Identity validates usb_path / iccid / imsi by regex. GlobalsState has non-negative counters. CarrierTable rejects all 7 hostile-input fixtures and accepts the happy_minimal.yaml fixture covering IL+US+UK+DE day-one (FR-30.1). All tests pass; ruff and mypy --strict are green.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Diag, Events, Webhook (event-shaped wire types) + __init__.py public surface</name>
  <files>src/spark_modem/wire/diag.py, src/spark_modem/wire/events.py, src/spark_modem/wire/webhook.py, src/spark_modem/wire/__init__.py, tests/unit/wire/test_diag.py, tests/unit/wire/test_events.py, tests/unit/wire/test_webhook.py</files>
  <read_first>
    - src/spark_modem/wire/_base.py, enums.py, versioning.py, state.py (just written; the patterns to follow)
    - .planning/phases/01-foundations-adrs/01-CONTEXT.md §"W. Wire types module" W-03 (discriminated unions via Annotated[Union[...], Field(discriminator='kind')])
    - docs/SCHEMA.md §2 Diag, §5 events.jsonl, §9 webhook payload
    - .planning/research/SUMMARY.md §"3. Promote into v2.0 scope" (M-1, M-2, M-4, M-6, M-15 — webhook variants this plan must define types for)
    - .planning/research/FEATURES.md §4.3 (HMAC v2.0 + X-Spark-Timestamp — Plan 03 defines the payload shape; signing implementation lands Phase 2)
  </read_first>
  <behavior>
    Diag (test_diag.py):
    - Test: WhoModem(kind="modem", usb_path="2-3.1.1") and WhoHost(kind="host") construct via the discriminator.
    - Test: Issue(category=IssueCategory.SIM, detail=IssueDetail.NO_SIM, who=WhoModem(usb_path=...), description="...") constructs.
    - Test: Issue(who=WhoHost(...)) for a global issue (e.g. dmesg overcurrent).
    - Test: Discriminator dispatches: validating `{"who": {"kind": "modem", "usb_path": "2-3.1.1"}, ...}` produces a WhoModem instance; `{"who": {"kind": "host"}, ...}` produces a WhoHost.
    - Test: Diag(schema_version=1, ts_iso=..., cycle_id=..., per_modem={...}, host_issues=[...]) round-trips via JSON.
    - Test: PlannedAction(kind=ActionKind.SOFT_RESET, who=WhoModem(usb_path="..."), reason="..." dry_run=False) constructs.

    Events (test_events.py):
    - Test: Each EventKind variant has a corresponding pydantic model that includes `kind: Literal[<value>]` as the discriminator, plus `ts_iso: str`, `schema_version: int`.
    - Test: A union `Event = Annotated[Union[ActionPlanned, ActionExecuted, ActionFailed, StateTransition, DaemonStarted, DaemonStopped, SchemaDowngradePending, UsbPathMismatch, MaintenanceWindowStarted, MaintenanceWindowEnded], Field(discriminator='kind')]` validates each variant by `kind`.
    - Test: An events.jsonl line `{"kind": "action_planned", "ts_iso": "...", ...}` validates as ActionPlanned; `{"kind": "schema_downgrade_pending", ...}` validates as SchemaDowngradePending.
    - Test: ActionFailed has a `failure_reason: str` field (M-15).
    - Test: DaemonStopped has `reason: DaemonStopReason` (M-6).
    - Test: SchemaDowngradePending carries `file_path: str`, `from_version: int`, `to_version: int`, `shadow_path: str`, `reason: DowngradeReason`.
    - Test: UsbPathMismatch carries `file_usb_path: str`, `sysfs_usb_path: str`, `cdc_wdm: str` (S-02 inventory cross-check error).

    Webhook (test_webhook.py):
    - Test: WebhookPayload has `kind: WebhookEventKind`, `ts_iso: str`, `schema_version: int`, `dedup_count: int = 0` (M-2 coalescing), `dedup_window_ends_iso: str | None = None`.
    - Test: HealthyToDegraded(kind="healthy_to_degraded", modem_usb_path, prior_state, new_state, reason).
    - Test: RecoveringToExhausted(kind="recovering_to_exhausted", modem_usb_path, action_chain, exhaustion_reason).
    - Test: DaemonRestart(kind="daemon_restart", reason: DaemonStopReason, prior_run_uptime_seconds).
    - Test: WebhookEnvelope(payload, signature_header_value: str = "", timestamp_header_value: str = "") — signature/timestamp are filled in by the WebhookPoster in Phase 2; Phase 1 just defines the shape.
    - Test: union dispatch via `kind` field works for all 4 variants.

    __init__.py (covered in test_base.py extension):
    - Test: `from spark_modem.wire import BaseWire, ModemState, Identity, GlobalsState, CarrierEntry, CarrierTable, Diag, PlannedAction, Issue, WhoModem, WhoHost, ActionKind, IssueCategory, IssueDetail, ...` all succeed in a single import statement (verifies the public surface).
  </behavior>
  <action>
    1. Write `tests/unit/wire/test_diag.py`, `test_events.py`, `test_webhook.py` (TDD RED). Pattern: build the discriminated-union variant by `kind`, assert the union resolver picks the right concrete class. Use `TypeAdapter(Event).validate_python({"kind": "...", ...})` to exercise the discriminator end-to-end.

    2. Run pytest — RED.

    3. Implement `src/spark_modem/wire/diag.py`:
    ```python
    """Diag snapshot type and PlannedAction (RECOVERY_SPEC §1)."""

    from __future__ import annotations

    from typing import Annotated, Literal, Union

    from pydantic import Field

    from spark_modem.wire._base import BaseWire
    from spark_modem.wire.enums import (
        ActionKind,
        IssueCategory,
        IssueDetail,
        RegistrationState,
    )
    from spark_modem.wire.versioning import CURRENT_SCHEMA_VERSION


    class WhoModem(BaseWire):
        kind: Literal["modem"] = "modem"
        usb_path: str = Field(min_length=1, max_length=64)
        cdc_wdm: str | None = Field(default=None, pattern=r"^cdc-wdm\d+$")


    class WhoHost(BaseWire):
        kind: Literal["host"] = "host"


    Who = Annotated[Union[WhoModem, WhoHost], Field(discriminator="kind")]


    class SignalSnapshot(BaseWire):
        rssi_dbm: int | None = None
        rsrp_dbm: int | None = None
        rsrq_db: float | None = None
        snr_db: float | None = None


    class Issue(BaseWire):
        category: IssueCategory
        detail: IssueDetail
        who: Who
        description: str = ""


    class ModemSnapshot(BaseWire):
        usb_path: str = Field(min_length=1, max_length=64)
        cdc_wdm: str = Field(pattern=r"^cdc-wdm\d+$")
        usb_speed: str | None = None
        operating_mode: str | None = None
        sim_state: str | None = None
        registration: RegistrationState | None = None
        mcc: str | None = Field(default=None, pattern=r"^\d{3}$")
        mnc: str | None = Field(default=None, pattern=r"^\d{2,3}$")
        signal: SignalSnapshot = Field(default_factory=SignalSnapshot)
        issues: list[Issue] = Field(default_factory=list)


    class Diag(BaseWire):
        """Per-cycle Diag snapshot (FR-13)."""

        schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, ge=1)
        ts_iso: str
        cycle_id: int = Field(ge=0)
        per_modem: dict[str, ModemSnapshot] = Field(default_factory=dict)
        host_issues: list[Issue] = Field(default_factory=list)


    class PlannedAction(BaseWire):
        kind: ActionKind
        who: Who
        reason: str
        dry_run: bool = False
        # Bookkeeping the policy engine fills in (FR-25 backoff, FR-26 counters).
        suppressed_by_backoff: bool = False
        suppressed_by_signal_gate: bool = False
        suppressed_by_dry_run: bool = False
    ```

    4. Implement `src/spark_modem/wire/events.py`:
    ```python
    """events.jsonl variants. discriminator='kind' on the union."""

    from __future__ import annotations

    from typing import Annotated, Literal, Union

    from pydantic import Field, TypeAdapter

    from spark_modem.wire._base import BaseWire
    from spark_modem.wire.enums import (
        ActionKind,
        ActionResult,
        DaemonStopReason,
        DowngradeReason,
    )
    from spark_modem.wire.versioning import CURRENT_SCHEMA_VERSION


    class _EventBase(BaseWire):
        schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, ge=1)
        ts_iso: str


    class ActionPlanned(_EventBase):
        kind: Literal["action_planned"] = "action_planned"
        usb_path: str
        action: ActionKind
        reason: str
        dry_run: bool = False


    class ActionExecuted(_EventBase):
        kind: Literal["action_executed"] = "action_executed"
        usb_path: str
        action: ActionKind
        result: ActionResult
        duration_seconds: float = Field(ge=0.0)


    class ActionFailed(_EventBase):
        # M-15: failure should optionally accelerate the ladder.
        kind: Literal["action_failed"] = "action_failed"
        usb_path: str
        action: ActionKind
        failure_reason: str


    class StateTransition(_EventBase):
        kind: Literal["state_transition"] = "state_transition"
        usb_path: str
        from_state: str  # Literal not used here so old/legacy state names don't break replay
        to_state: str
        cause: str
        action: ActionKind | None = None
        dry_run: bool = False


    class DaemonStarted(_EventBase):
        kind: Literal["daemon_started"] = "daemon_started"
        version: str
        bundled_python_version: str


    class DaemonStopped(_EventBase):
        # M-6: reason enum.
        kind: Literal["daemon_stopped"] = "daemon_stopped"
        reason: DaemonStopReason
        uptime_seconds: float = Field(ge=0.0)


    class SchemaDowngradePending(_EventBase):
        kind: Literal["schema_downgrade_pending"] = "schema_downgrade_pending"
        file_path: str
        from_version: int
        to_version: int
        shadow_path: str
        reason: DowngradeReason


    class UsbPathMismatch(_EventBase):
        # S-02: inventory cross-check refuses to start on mismatch.
        kind: Literal["usb_path_mismatch"] = "usb_path_mismatch"
        file_usb_path: str
        sysfs_usb_path: str
        cdc_wdm: str


    class MaintenanceWindowStarted(_EventBase):
        kind: Literal["maintenance_window_started"] = "maintenance_window_started"
        operator: str = ""
        duration_seconds: float = Field(gt=0.0, le=8 * 3600.0)
        reason: str = ""


    class MaintenanceWindowEnded(_EventBase):
        kind: Literal["maintenance_window_ended"] = "maintenance_window_ended"
        reason: Literal["expired", "operator_off"] = "expired"


    Event = Annotated[
        Union[
            ActionPlanned,
            ActionExecuted,
            ActionFailed,
            StateTransition,
            DaemonStarted,
            DaemonStopped,
            SchemaDowngradePending,
            UsbPathMismatch,
            MaintenanceWindowStarted,
            MaintenanceWindowEnded,
        ],
        Field(discriminator="kind"),
    ]
    """One discriminated-union type for parsing events.jsonl back."""

    EventAdapter: TypeAdapter[Event] = TypeAdapter(Event)
    """Use EventAdapter.validate_python(line_dict) or .validate_json(raw_line)."""
    ```

    5. Implement `src/spark_modem/wire/webhook.py`:
    ```python
    """Webhook payload and envelope.

    ADR-0011 (drafted in Plan 07): HMAC-SHA256 signing in v2.0 + X-Spark-Timestamp
    replay-protection header. Phase 1 defines the payload shape; Phase 2 implements
    the WebhookPoster (signing, retry queue, dedup, pre-resolved DNS).
    """

    from __future__ import annotations

    from typing import Annotated, Literal, Union

    from pydantic import Field, TypeAdapter

    from spark_modem.wire._base import BaseWire
    from spark_modem.wire.enums import ActionKind, DaemonStopReason, WebhookEventKind
    from spark_modem.wire.versioning import CURRENT_SCHEMA_VERSION


    class _WebhookBase(BaseWire):
        schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, ge=1)
        ts_iso: str
        # M-2: dedup window. dedup_count > 0 means this payload coalesces multiple
        # transitions; dedup_window_ends_iso is the wall-clock end of the window.
        dedup_count: int = Field(default=0, ge=0)
        dedup_window_ends_iso: str | None = None


    class HealthyToDegraded(_WebhookBase):
        kind: Literal["healthy_to_degraded"] = "healthy_to_degraded"
        modem_usb_path: str
        prior_state: str
        new_state: str
        reason: str


    class RecoveringToExhausted(_WebhookBase):
        kind: Literal["recovering_to_exhausted"] = "recovering_to_exhausted"
        modem_usb_path: str
        action_chain: list[ActionKind]
        exhaustion_reason: str


    class DaemonRestart(_WebhookBase):
        kind: Literal["daemon_restart"] = "daemon_restart"
        reason: DaemonStopReason
        prior_run_uptime_seconds: float = Field(ge=0.0)


    class ActionFailedWebhook(_WebhookBase):
        kind: Literal["action_failed"] = "action_failed"
        modem_usb_path: str
        action: ActionKind
        failure_reason: str


    WebhookPayload = Annotated[
        Union[HealthyToDegraded, RecoveringToExhausted, DaemonRestart, ActionFailedWebhook],
        Field(discriminator="kind"),
    ]

    WebhookPayloadAdapter: TypeAdapter[WebhookPayload] = TypeAdapter(WebhookPayload)


    class WebhookEnvelope(BaseWire):
        """The thing that's actually POSTed (signing handled by Phase 2 WebhookPoster).

        signature_header_value: HMAC-SHA256 hex of raw body bytes (Phase 2 fills).
        timestamp_header_value: Unix timestamp string (Phase 2 fills).

        Phase 1 defines the shape; Phase 2 writes a `sign(payload, secret) -> envelope`
        helper that consumes this type.
        """

        payload: WebhookPayload
        signature_header_value: str = ""
        timestamp_header_value: str = ""
    ```

    Note on the `kind` collision: both `events.ActionFailed` and `webhook.ActionFailedWebhook` need a `kind` Literal — events use `kind="action_failed"` at the EventKind level; webhooks use `kind="action_failed"` at the WebhookEventKind level. Same string value, different discriminator namespaces (events.Event union vs webhook.WebhookPayload union — pydantic discriminators are scoped to their union). Naming the webhook variant `ActionFailedWebhook` (not `ActionFailed`) prevents an import-name collision in `__init__.py`.

    6. Implement `src/spark_modem/wire/__init__.py`:
    ```python
    """Public surface of the spark_modem wire types.

    Every Phase 2/3/4 module imports from here. Adding a type here is a
    deliberate API surface change.
    """

    from spark_modem.wire._base import BaseWire
    from spark_modem.wire.carriers import CarrierEntry, CarrierTable
    from spark_modem.wire.diag import (
        Diag,
        Issue,
        ModemSnapshot,
        PlannedAction,
        SignalSnapshot,
        Who,
        WhoHost,
        WhoModem,
    )
    from spark_modem.wire.enums import (
        ActionKind,
        ActionResult,
        DaemonStopReason,
        DowngradeReason,
        EventKind,
        IssueCategory,
        IssueDetail,
        RegistrationState,
        WebhookEventKind,
    )
    from spark_modem.wire.events import (
        ActionExecuted,
        ActionFailed,
        ActionPlanned,
        DaemonStarted,
        DaemonStopped,
        Event,
        EventAdapter,
        MaintenanceWindowEnded,
        MaintenanceWindowStarted,
        SchemaDowngradePending,
        StateTransition,
        UsbPathMismatch,
    )
    from spark_modem.wire.globals import GlobalsState
    from spark_modem.wire.identity import Identity
    from spark_modem.wire.state import ModemState, state_to_int
    from spark_modem.wire.versioning import (
        CURRENT_SCHEMA_VERSION,
        SchemaVersionTooNew,
        shadow_filename,
        validate_schema_version,
    )
    from spark_modem.wire.webhook import (
        ActionFailedWebhook,
        DaemonRestart,
        HealthyToDegraded,
        RecoveringToExhausted,
        WebhookEnvelope,
        WebhookPayload,
        WebhookPayloadAdapter,
    )

    __all__ = [
        # Base
        "BaseWire",
        # Versioning
        "CURRENT_SCHEMA_VERSION", "SchemaVersionTooNew", "shadow_filename", "validate_schema_version",
        # Enums
        "ActionKind", "ActionResult", "DaemonStopReason", "DowngradeReason", "EventKind",
        "IssueCategory", "IssueDetail", "RegistrationState", "WebhookEventKind",
        # Diag
        "Diag", "Issue", "ModemSnapshot", "PlannedAction", "SignalSnapshot",
        "Who", "WhoHost", "WhoModem",
        # State
        "ModemState", "state_to_int",
        # Identity / Globals / Carriers
        "Identity", "GlobalsState", "CarrierEntry", "CarrierTable",
        # Events
        "Event", "EventAdapter",
        "ActionExecuted", "ActionFailed", "ActionPlanned",
        "DaemonStarted", "DaemonStopped",
        "MaintenanceWindowEnded", "MaintenanceWindowStarted",
        "SchemaDowngradePending", "StateTransition", "UsbPathMismatch",
        # Webhook
        "ActionFailedWebhook", "DaemonRestart", "HealthyToDegraded", "RecoveringToExhausted",
        "WebhookEnvelope", "WebhookPayload", "WebhookPayloadAdapter",
    ]
    ```

    7. Run the full `pytest tests/unit/wire/ -q` — every test passes. Then run `mypy --strict src/spark_modem/wire/` and `ruff check src/spark_modem/wire/`.
  </action>
  <verify>
    <automated>
      cd S:/spark/modem-watchdog && \
      .venv/bin/pytest tests/unit/wire/ -q && \
      .venv/bin/ruff check src/spark_modem/wire/ tests/unit/wire/ && \
      .venv/bin/ruff format --check src/spark_modem/wire/ tests/unit/wire/ && \
      .venv/bin/mypy --strict src/spark_modem/wire/ && \
      .venv/bin/python -c "from spark_modem.wire import BaseWire, ModemState, state_to_int, Identity, GlobalsState, CarrierEntry, CarrierTable, Diag, PlannedAction, Issue, ModemSnapshot, SignalSnapshot, Who, WhoHost, WhoModem, ActionKind, ActionResult, DaemonStopReason, DowngradeReason, EventKind, IssueCategory, IssueDetail, RegistrationState, WebhookEventKind, Event, EventAdapter, ActionExecuted, ActionFailed, ActionPlanned, DaemonStarted, DaemonStopped, MaintenanceWindowEnded, MaintenanceWindowStarted, SchemaDowngradePending, StateTransition, UsbPathMismatch, ActionFailedWebhook, DaemonRestart, HealthyToDegraded, RecoveringToExhausted, WebhookEnvelope, WebhookPayload, WebhookPayloadAdapter, CURRENT_SCHEMA_VERSION, SchemaVersionTooNew, shadow_filename, validate_schema_version; print('public surface: 41 names imported OK')" && \
      bash scripts/lint_no_subprocess.sh
    </automated>
  </verify>
  <done>
    Diag/Issue/ModemSnapshot/PlannedAction shape per docs/SCHEMA.md §2; the Issue.who union dispatches by kind=modem|host. Event union covers all 10 events.jsonl variants and validates by kind via EventAdapter. WebhookPayload union covers all 4 transitions (HealthyToDegraded, RecoveringToExhausted, DaemonRestart, ActionFailedWebhook) and validates by kind via WebhookPayloadAdapter. WebhookEnvelope holds payload + signature/timestamp header placeholders (Phase 2 fills via HMAC). __init__.py exports the full public surface (41 names). All tests in tests/unit/wire/ pass; mypy --strict and ruff are green; SP-04 lint gate passes.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Disk → in-memory | Persisted state files (state/by-usb/<usb_path>.json), identity.json, globals.json, the carrier table YAML — every disk read enters via pydantic.model_validate_json, which is the validator. Tampering or corruption surfaces as ValidationError, not an unsafe field assignment. |
| External text → wire types | The carrier table YAML is operator-edited; pydantic + StrictStr regex is the gatekeeper (PITFALLS §11.2). |
| Future versions → loader | Forward-version files (schema_version > CURRENT_SCHEMA_VERSION) are refused via SchemaVersionTooNew (NFR-43). |
| In-memory mutation | Wire models are frozen — once parsed, nothing mutates them in place. Cycle code must construct new ModemState instances rather than `state.healthy_streak += 1`; this is the ADR-0006 atomic-write discipline made impossible to violate. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-03-01 | T (Tampering) | wire/state.py — state file deserialization | mitigate | `extra='forbid'` + per-field regex/Literal/ge constraints. Tampered state files raise ValidationError; the daemon refuses to start (state_store layer Plan 04). |
| T-03-02 | I (Information disclosure) | wire/diag.py — Diag/Issue snapshot | accept | Diag is internal to the daemon and NOC-facing. It contains MCC/MNC/RSSI/IMSI-derived data; the persistence path (Plan 04 state-store) handles file-mode permissions. The wire types don't add a new exposure surface. |
| T-03-03 | T | wire/carriers.py — operator-edited YAML | mitigate | Norway-problem hostile-input fixtures + StrictStr regex on country/mcc/mnc fields. `extra='forbid'` rejects extra keys. Hostile fixtures are part of the test suite — regression-proof. |
| T-03-04 | I | wire/identity.py — ICCID/IMSI persistence | mitigate | Identity is one row of the per-box identity map; persisted at /var/lib/spark-modem-watchdog/identity.json with file-mode 0640 (state_store layer Plan 04 enforces). The wire type itself doesn't escape. NFR-30 (daemon runs as root; no other process granted suid bits) limits read access. |
| T-03-05 | E (Elevation) | wire types in policy engine (Phase 2 consumer) | mitigate | wire types are pure-data pydantic models with no I/O. The pure-function policy engine (FR-73) can't be tricked into running shell because the wire types refuse to carry shell-command-shaped fields. |
| T-03-06 | T | wire/webhook.py — WebhookEnvelope | mitigate | Phase 1 defines the shape; Phase 2 fills `signature_header_value` via HMAC-SHA256 over raw body bytes (FR-44.1). The shape ensures Phase 2's signature has a typed home; tampering with headers in transit is detected by the receiver via the HMAC contract. |
| T-03-07 | T | wire/versioning.py — schema_version | mitigate | Forward-version files (NFR-43) raise SchemaVersionTooNew; downgrades preserve the old file as `.from-v<N>.json` so no data is silently overwritten (PITFALLS §3.4). |
</threat_model>

<verification>
End-to-end check after all three tasks complete:

1. `pytest tests/unit/wire/ -q` — all tests pass; runtime <2s on a developer laptop (M7 budget).
2. `mypy --strict src/spark_modem/wire/` — zero errors.
3. `ruff check src/spark_modem/wire/ tests/unit/wire/` and `ruff format --check ...` — clean.
4. `bash scripts/lint_no_subprocess.sh` — passes (this plan adds zero subprocess calls).
5. `python -c "from spark_modem.wire import *; print(len([n for n in dir() if not n.startswith('_')]))"` reports the public-surface count documented in `__init__.py` (~41 names).
6. `python -c "import json; from spark_modem.wire import ModemState, state_to_int; m = ModemState(state='recovering', recovering_level=2, present=True, rf_blocked=False); j = m.model_dump_json(); m2 = ModemState.model_validate_json(j); assert m == m2; assert state_to_int(m2) == 3"` — state-state round-trip with the orthogonal-flag invariant intact.
7. `python -c "import yaml, pathlib; from spark_modem.wire import CarrierTable; from pydantic import ValidationError; data = yaml.safe_load(pathlib.Path('tests/fixtures/wire/carriers/hostile_norway_problem.yaml').read_text()); raised = False
  try: CarrierTable.model_validate(data)
  except ValidationError: raised = True
  assert raised"` — Norway problem rejected.
</verification>

<success_criteria>
- Closes Phase 1 SC #4: `mypy --strict`, `ruff check`, `ruff format --check` are green on `wire/`; `wire/` defines all closed enums, tagged-union `who` types, and `Diag`/`PlannedAction`/`StateTransition` pydantic models with `schema_version: int` enforcement and non-destructive downgrade behavior (the helpers; full state_store impl lands in Plan 04). `grep -r 'subprocess.run\|os.system' src/` outside `subproc/` returns zero matches (this plan adds zero subprocess; gate enforced by SP-04).
- Closes Phase 1 SC #3: CarrierTable validates Israel + US + UK + DE day-one carriers and rejects all 7 hostile-input fixtures.
- W-01..W-04 implemented: per-domain file split, BaseWire root with frozen+forbid+populate, Annotated-union discriminator, ModemState 5+2 flat shape.
- ADR-0008 surface (5+2): the wire boundary enforces the invariant; Phase 2 policy engine consumes ModemState directly.
- ADR-0009 surface (usb_path keying): Identity.usb_path is the join key; Plan 04 will use this.
- ADR-0013 surface (no one-hot state label): `state_to_int(ModemState) -> int` is the canonical encoding for `modem_state_value{modem}`. Phase 2 metrics layer consumes this.
- NFR-43 surface (schema-version refusal + non-destructive downgrade): `validate_schema_version` + `shadow_filename` are the helpers; Plan 04 wires them into the state-store load path.
</success_criteria>

<output>
After completion, create `.planning/phases/01-foundations-adrs/01-03-SUMMARY.md` covering: full public surface (`from spark_modem.wire import *`), the discriminator pattern used (Annotated[Union[...], Field(discriminator='kind')]), the ModemState 5+2 invariant, the schema-versioning helpers (CURRENT_SCHEMA_VERSION, SchemaVersionTooNew, validate_schema_version, shadow_filename) that Plan 04 consumes, and a note that Webhook signing/payload-emit lands in Phase 2 (Plan 03 only defines shapes). Reference the four downstream plans that consume this surface: Plan 04 (state_store), Plan 06 (carrier YAML loading), and indirectly Plan 02 (the .deb's smoke test imports `spark_modem` package — this plan ensures import succeeds).
</output>
