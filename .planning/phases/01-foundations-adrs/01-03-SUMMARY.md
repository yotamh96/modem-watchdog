---
phase: 01-foundations-adrs
plan: "03"
subsystem: wire
tags:
  - python
  - pydantic
  - wire-types
  - schema
  - tdd
dependency_graph:
  requires:
    - 01-01-repo-lint-ci (pyproject.toml, ruff, mypy config)
  provides:
    - src/spark_modem/wire/ (full public surface — 41 names)
    - BaseWire, ModemState, Diag, PlannedAction, Issue, Who union
    - schema_version versioning helpers (validate_schema_version, shadow_filename)
    - state_to_int() for ADR-0013 Prometheus metric encoding
  affects:
    - 01-04-state-store (imports ModemState, Identity, GlobalsState, validate_schema_version, shadow_filename)
    - 01-06-config (imports CarrierTable, CarrierEntry for YAML loading)
    - 02 (imports Diag, ModemState, PlannedAction from wire)
tech_stack:
  added:
    - pydantic>=2.13,<3 (wire boundary models — frozen, extra=forbid, populate_by_name)
    - PyYAML>=6.0.2,<7 (carrier table YAML loading in tests)
    - hypothesis>=6.110,<7 (MNC property-based testing)
  patterns:
    - BaseWire root with frozen=True, extra=forbid, populate_by_name=True
    - Annotated[Union[...], Field(discriminator='kind')] for all tagged unions
    - StrEnum for all closed enum types (JSON-serializable as strings)
    - TypeAdapter for discriminated-union validation (EventAdapter, WebhookPayloadAdapter)
    - StrictStr + Field(pattern=...) for carrier table hostile-input rejection
key_files:
  created:
    - src/spark_modem/wire/__init__.py
    - src/spark_modem/wire/_base.py
    - src/spark_modem/wire/versioning.py
    - src/spark_modem/wire/enums.py
    - src/spark_modem/wire/state.py
    - src/spark_modem/wire/identity.py
    - src/spark_modem/wire/globals.py
    - src/spark_modem/wire/carriers.py
    - src/spark_modem/wire/diag.py
    - src/spark_modem/wire/events.py
    - src/spark_modem/wire/webhook.py
    - tests/unit/wire/__init__.py
    - tests/unit/wire/test_base.py
    - tests/unit/wire/test_versioning.py
    - tests/unit/wire/test_enums.py
    - tests/unit/wire/test_state.py
    - tests/unit/wire/test_identity.py
    - tests/unit/wire/test_globals.py
    - tests/unit/wire/test_carriers.py
    - tests/unit/wire/test_diag.py
    - tests/unit/wire/test_events.py
    - tests/unit/wire/test_webhook.py
    - tests/fixtures/wire/carriers/happy_minimal.yaml
    - tests/fixtures/wire/carriers/hostile_norway_problem.yaml
    - tests/fixtures/wire/carriers/hostile_leading_zero_mnc.yaml
    - tests/fixtures/wire/carriers/hostile_mnc_as_int.yaml
    - tests/fixtures/wire/carriers/hostile_mnc_too_long.yaml
    - tests/fixtures/wire/carriers/hostile_missing_apn.yaml
    - tests/fixtures/wire/carriers/hostile_extra_field.yaml
    - tests/fixtures/wire/carriers/hostile_mixed_case_country.yaml
decisions:
  - "BaseWire uses frozen=True, extra=forbid, populate_by_name=True — strict wire boundary per CONTEXT.md W-02"
  - "ModemState uses healthy_streak field with alias _healthy_streak for on-disk compatibility (ADR-0006 amendment)"
  - "state_to_int() stable mapping: unknown=0, healthy=1, degraded=2, recovering=3, exhausted=4 (ADR-0013)"
  - "SchemaVersionTooNew uses noqa N818 — name is a deliberate API contract from plan must_haves"
  - "__all__ uses noqa RUF022 — grouped by domain for readability rather than alphabetical sort"
  - "CarrierEntry uses StrictStr (not str) to reject YAML type coercions including the Norway problem (NO -> False)"
  - "ActionFailedWebhook distinct from events.ActionFailed to prevent import collision in __init__.py"
  - "Event union uses | syntax (UP007) after ruff auto-fix; TypeAdapter used for parsing events.jsonl"
metrics:
  duration_minutes: 18
  completed_date: "2026-05-06"
  task_count: 3
  file_count: 30
---

# Phase 01 Plan 03: Wire Package Summary

**One-liner:** Pydantic v2 wire types with frozen+strict base, 5+2 ModemState, discriminated-union Issue/Event/Webhook, schema-version helpers, and Norway-problem-safe CarrierTable — 117 tests, mypy strict clean.

## What Was Built

The `spark_modem.wire` package defines every JSON shape the daemon persists, emits, or consumes. It is the contract layer: every Phase 2/3/4 module is built against these types. If a wire type changes, the schema_version bumps and the non-destructive downgrade path (shadow file + SchemaDowngradePending event) is engaged.

### Package structure (11 source files)

| File | Purpose |
|------|---------|
| `_base.py` | `BaseWire` root — `frozen=True, extra=forbid, populate_by_name=True` |
| `versioning.py` | `CURRENT_SCHEMA_VERSION=1`, `SchemaVersionTooNew`, `validate_schema_version`, `shadow_filename` |
| `enums.py` | 9 closed `StrEnum` types: `IssueCategory`, `IssueDetail`, `RegistrationState`, `ActionKind`, `ActionResult`, `EventKind`, `WebhookEventKind`, `DowngradeReason`, `DaemonStopReason` |
| `state.py` | `ModemState` (ADR-0008 5+2 flat shape); `state_to_int()` for ADR-0013 metric encoding |
| `identity.py` | `Identity` — usb_path/iccid/imsi with regex validators (ADR-0009 keying) |
| `globals.py` | `GlobalsState` — driver_reset counters, qmi_proxy uptime |
| `carriers.py` | `CarrierEntry` + `CarrierTable` — StrictStr MCC/MNC/country rejects all 7 hostile inputs |
| `diag.py` | `Diag`, `ModemSnapshot`, `SignalSnapshot`, `Issue` (Who discriminated union), `PlannedAction` |
| `events.py` | 10 `events.jsonl` variants + `Event` union + `EventAdapter` |
| `webhook.py` | 4 webhook payload variants + `WebhookPayload` union + `WebhookPayloadAdapter` + `WebhookEnvelope` |
| `__init__.py` | Full public re-export: 41 names |

### Key patterns

**BaseWire:** All wire shapes inherit one base with `ConfigDict(frozen=True, extra="forbid", populate_by_name=True)`. Frozen prevents post-construction mutation (ADR-0006 atomic-write discipline). Extra=forbid rejects tampered/unknown fields (T-03-01 threat mitigation). The qmicli parser (Phase 2) uses `extra="ignore"` instead — the boundary is explicit per CONTEXT.md W-02.

**Discriminated unions:** All tagged-union shapes use `Annotated[Union[A, B, ...], Field(discriminator="kind")]`. This covers `Who = WhoModem | WhoHost` (Issue subject), the `Event` union (10 events.jsonl variants dispatched by EventAdapter), and the `WebhookPayload` union (4 variants dispatched by WebhookPayloadAdapter).

**ModemState 5+2 (ADR-0008):** Flat top-level fields — `state: Literal[...]`, `recovering_level: int | None`, `present: bool`, `rf_blocked: bool`. A `@model_validator` enforces the invariant: `recovering_level` is required iff `state == "recovering"`. The `state_to_int()` function provides the stable 0-4 encoding for `modem_state_value{modem}` (ADR-0013, no one-hot label).

**Schema versioning (ADR-0004):** `validate_schema_version(file_version)` returns `"current"` or `"downgrade"`, or raises `SchemaVersionTooNew` for forward-version files (NFR-43). `shadow_filename(path, from_version=N)` computes the `.from-vN.json` shadow path. Plan 04 (state_store) wires these into the load path.

**CarrierTable hostile-input protection (PITFALLS §11.2):** `StrictStr` on `country`, `mcc`, `mnc` fields rejects PyYAML's type coercions: `NO` (Norway) parsed as `False`, `mnc: 1` (int) instead of `"01"` (string), `mnc: "1234"` (too long). 7 hostile fixtures cover all rejection cases; `happy_minimal.yaml` covers 12 IL+US+GB+DE day-one carriers.

## Downstream consumers

| Plan | What it imports |
|------|----------------|
| 01-04 state_store | `ModemState`, `Identity`, `GlobalsState`, `validate_schema_version`, `shadow_filename`, `SchemaVersionTooNew` |
| 01-06 config | `CarrierTable`, `CarrierEntry` for YAML loading and validation |
| 01-02 .deb smoke test | `spark_modem` package import succeeds (this plan's `__init__.py` enables it) |
| Phase 2 (all modules) | `Diag`, `PlannedAction`, `ModemState`, `Issue`, `WhoModem`, `WhoHost`, all enums |

## Note on webhook signing

Plan 03 defines the webhook payload **shape** (`WebhookEnvelope.signature_header_value`, `timestamp_header_value`). The HMAC-SHA256 signing implementation (`X-Spark-Signature: sha256=<hex>`, `X-Spark-Timestamp` replay protection, pre-resolved DNS) lands in Phase 2 Plan 03 (WebhookPoster). Phase 1 only defines the typed containers.

## Deviations from Plan

**1. [Rule 1 - Bug] noqa suppression for SchemaVersionTooNew (N818)**
- Found during: Task 1 ruff check
- Issue: ruff N818 requires exception names to end in `Error`; the plan's must_haves specify `SchemaVersionTooNew` as the exact contract name
- Fix: Added `# noqa: N818` with explanatory comment; the name is the deliberate API surface
- Files modified: `src/spark_modem/wire/versioning.py`

**2. [Rule 1 - Bug] noqa suppression for __all__ sort (RUF022)**
- Found during: Task 3 ruff check
- Issue: ruff RUF022 requires alphabetical sort of `__all__`; the domain-grouped layout is semantically useful
- Fix: Added `# noqa: RUF022` with comment explaining grouping intent

**3. [Rule 1 - Bug] UP007 auto-fix on Union types**
- Found during: Task 3 ruff check
- Issue: ruff UP007 upgrades `Union[A, B]` to `A | B` syntax (Python 3.12 target)
- Fix: ruff --fix auto-applied; no behavioral change

**4. [Rule 1 - Bug] Inline imports moved to top-level**
- Found during: Task 1/2/3 ruff check (PLC0415)
- Issue: Several test functions had `import pathlib`, `import json`, `import re` inside function bodies
- Fix: Moved all imports to module top-level

None — plan executed as designed with minor lint-compliance fixes.

## Self-Check: PASSED

All 11 source files exist. All 3 task commits verified in git log:
- 07795f8: Task 1 — BaseWire, versioning, enums
- a0e7261: Task 2 — ModemState, Identity, Globals, CarrierTable
- b449830: Task 3 — Diag, Events, Webhook, __init__

117 tests pass, mypy --strict clean, ruff clean.
