# ADR-0004 — Strict typed JSON contract between components

| Field        | Value          |
| ------------ | -------------- |
| Status       | Accepted       |
| Date         | 2026-05-05     |
| Deciders     | Eng team       |

## Context

v1 has a JSON contract between `diag.sh` and `recovery.sh` but it is
informal:

- `schema_version` is present but never checked by `recovery.sh`.
- `category` and `detail` are free-form strings; recovery pattern-
  matches on substrings (`*power-down*`, `app_state_*`, `session_*`).
- `who` is heterogeneous: `"ALL"`, `"/dev/cdc-wdm0"`, `"line1/wwan0"`,
  `"cdc-wdm0"`. Recovery has to normalize at the seam.
- A field rename or reshape silently changes behaviour.

## Decision

**Every wire format and every persistent file is a versioned, typed
schema with closed enums.** We use `pydantic v2` models in
`src/spark_modem_watchdog/wire/`. The models are the single source of
truth; [SCHEMA.md](../SCHEMA.md) mirrors them in human form.

Specifically:

- `schema_version` is an integer, strictly checked. A daemon refuses
  to load anything with a higher version. Lower versions require
  explicit migration code; without it, refuse.
- `category` and `detail` are `Enum`-typed. Adding a value is a
  schema-version bump.
- `who` is a tagged union: `WhoModem(kind="modem", device=str)`,
  `WhoHost(kind="host")`. Future kinds add tags, never overload.
- All optional fields are explicitly `Optional[T]` with `None` as
  default; absence and `null` mean the same thing.
- Nullable strings use `None`, never `""`, **except** `profile1_apn`
  where `""` is meaningfully distinct from `None` ("profile present,
  APN field empty" vs "profile not gathered").

## Consequences

- Adding a new issue category requires editing the enum, regenerating
  any affected fixtures, and bumping the schema version if existing
  values change.
- Round-trip property tests (`hypothesis`-driven) live in
  `tests/properties/` for every wire schema.
- The CLI's `--json` output uses the same schemas; no separate
  human/machine field set.
- `events.jsonl` is JSON Lines; each line is a discriminated-union
  record (`event=` discriminator).
- Migration tools live alongside the wire module: `wire/migrate.py`
  with `migrate_v1_to_v2(payload: dict) -> dict | None` (None ⇒
  refuse).
- Documentation tests (`tools/check_schemas.py`) verify the JSON
  examples in [SCHEMA.md](../SCHEMA.md) round-trip through the
  pydantic models.

## Why not JSON Schema (the spec) for the wire?

- pydantic generates JSON Schema on demand if we want to publish
  it for external consumers.
- Authoring in pydantic gives us validation, mypy types, and pretty
  errors in one place.
- We have no external consumer that validates against the JSON Schema
  spec independently. (If that changes, we publish; the source is
  still the pydantic model.)

## Risks and mitigations

| Risk                                                     | Mitigation                                                       |
| -------------------------------------------------------- | ---------------------------------------------------------------- |
| New code field references a non-existent enum value       | mypy --strict catches this at compile time.                      |
| Legacy state file lying around after a downgrade         | Daemon refuses to load future-schema files with a structured error and a clear remediation hint (`spark-modem ctl reset-state`). |
| Bumping schema_version breaks deployed boxes that haven't upgraded | Cutover plan (MIGRATION § 5) goes phase-by-phase; we don't bump schemas across a phase boundary mid-migration. |

## Revisit when

- We add a stable external consumer that wants JSON Schema separately.
- We want over-the-wire validation in flight (e.g. a fleet API
  endpoint). Then we'll publish the JSON Schema to that boundary.
