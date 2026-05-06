# Wire formats — spark-modem-watchdog v2

| Field         | Value                  |
| ------------- | ---------------------- |
| Status        | Draft                  |
| Owner         | TBD (modem platform)   |
| Last updated  | 2026-05-05             |

This document defines the typed JSON shapes exchanged between
components and persisted to disk. Every shape carries a
`schema_version` integer. A daemon refuses to load a version it
does not understand. There is no auto-upgrade; bumping a schema
version is a deliberate release decision.

All schemas are `pydantic v2` models in `src/spark_modem_watchdog/wire/`.
This document is the human-readable mirror; if they disagree, the code
wins and this doc is wrong.

---

## 1. Conventions

- All timestamps are RFC 3339 / ISO 8601 with timezone offset
  (`2026-05-05T13:42:09+00:00`). UTC by convention.
- All durations are floats in seconds.
- All sizes are bytes.
- All identifiers (modem device names, line numbers) are strings even
  when numeric, except `line` which is an int 1..N.
- Enums are lowercase strings. Unknown values from the wire are an
  error, not a fallback.
- Nullable fields use `null` (not `""`, not omitted) to distinguish
  "not gathered" from "gathered but empty".
- `schema_version` is an integer. v2 starts at 1.

## 2. Diag

The output of the observer; the input to the policy engine.

```jsonc
{
  "schema_version": 1,
  "kind": "diag",
  "ts": "2026-05-05T13:42:09+00:00",
  "host": {
    "hostname": "linux",
    "kernel": "5.10.216-tegra",
    "tegra_release": "R35 (release), REVISION: 6.4"
  },
  "expected_modems": 4,
  "detected_modems": 4,
  "zao": {
    "log_path": "/var/log/zao-remote-endpoint.log",
    "log_age_seconds": 0.7,
    "last_rascow_stat_ts": "2026-05-05T13:42:08+00:00",
    "lines_active": [1, 2, 3, 4]
  },
  "modems": [
    {
      "device": "cdc-wdm0",
      "line": 1,
      "namespace": "line1",
      "iface": "wwan0",
      "usb_path": "2-3.1.1",
      "usb_speed_mbps": 5000,
      "zao_active": true,
      "qmi": null,
      "sim": null,
      "registration": null,
      "carrier": null,
      "signal": null,
      "data_session": null,
      "profile1_apn": null,
      "ipv4": "10.69.92.156/29",
      "raw_ip": "Y"
    },
    {
      "device": "cdc-wdm3",
      "line": 4,
      "namespace": "line4",
      "iface": "wwan0",
      "usb_path": "2-3.1.4",
      "usb_speed_mbps": 5000,
      "zao_active": false,
      "qmi": {
        "responsive": true,
        "operating_mode": "online",
        "ids": { "imei": "...", "esn": null, "meid": null }
      },
      "sim": {
        "card_state": "present",
        "app_state": "ready",
        "iccid": "8997201...",
        "imsi": "425030..."
      },
      "registration": "not-registered-searching",
      "carrier": { "mcc": "425", "mnc": "03", "description": "PCL" },
      "signal": {
        "rssi_dbm": -51,
        "rsrp_dbm": -92,
        "rsrq_db": -18.0,
        "snr_db": -8.2,
        "sufficient": false
      },
      "data_session": "disconnected",
      "profile1_apn": "internet",
      "ipv4": null,
      "raw_ip": "Y"
    }
  ],
  "host_issues": [
    {
      "category": "thermal",
      "detail": "soc0_70c",
      "severity": "warn",
      "first_seen": "2026-05-05T13:40:01+00:00"
    }
  ],
  "issues": [
    {
      "who": { "kind": "modem", "device": "cdc-wdm3" },
      "category": "registration",
      "detail": "not_registered_searching",
      "severity": "error",
      "first_seen": "2026-05-05T13:40:09+00:00"
    }
  ]
}
```

### Fields — `Diag`

| Field             | Type                  | Notes                                                               |
| ----------------- | --------------------- | ------------------------------------------------------------------- |
| `schema_version`  | int                   | Always 1 in v2.0.                                                   |
| `kind`            | `"diag"`              | Discriminator for tagged unions.                                    |
| `ts`              | string                | When the snapshot was taken.                                        |
| `host`            | `Host`                | Static host facts.                                                  |
| `zao`             | `ZaoSnapshot`         | What we knew about Zao when the snapshot was taken.                 |
| `modems`          | `Modem[]`             | One entry per detected `cdc-wdm` device, ordered by `line`.         |
| `host_issues`     | `HostIssue[]`         | Issues not attributable to a single modem (overcurrent, thermal).   |
| `issues`          | `ModemIssue[]`        | Per-modem issues. May be empty.                                     |

### Fields — `Modem`

| Field           | Type                                  | Nullable | Notes                                                          |
| --------------- | ------------------------------------- | -------- | -------------------------------------------------------------- |
| `device`        | string                                | no       | `cdc-wdmN` basename.                                           |
| `line`          | int (1..N)                            | no       | Zao line number.                                               |
| `namespace`     | string                                | yes      | `lineN` netns; null if not yet provisioned.                    |
| `iface`         | string                                | yes      | usually `wwan0`.                                               |
| `usb_path`      | string                                | no       | sysfs name, e.g. `2-3.1.1`.                                    |
| `usb_speed_mbps`| int                                   | yes      | from sysfs.                                                    |
| `zao_active`    | bool                                  | no       | True ⇒ all probe fields below are `null`.                      |
| `qmi`           | `QmiSnapshot`                         | yes      | null when `zao_active=true`.                                   |
| `sim`           | `SimSnapshot`                         | yes      | null when `zao_active=true` or QMI unresponsive.               |
| `registration`  | enum `RegistrationState`              | yes      |                                                                 |
| `carrier`       | `Carrier`                             | yes      |                                                                 |
| `signal`        | `Signal`                              | yes      |                                                                 |
| `data_session`  | enum `DataSession`                    | yes      | `connected`/`disconnected`/`authenticating`/`unknown`.         |
| `profile1_apn`  | string                                | yes      | `""` distinct from `null`: empty string ⇒ profile present, APN empty. |
| `ipv4`          | string                                | yes      | CIDR.                                                          |
| `raw_ip`        | enum `RawIp` (`"Y"`/`"N"`/`"?"`)      | yes      |                                                                 |

### Enums

```python
class RegistrationState(str, Enum):
    registered = "registered"
    not_registered_searching = "not_registered_searching"
    not_registered_idle = "not_registered_idle"
    denied = "denied"
    unknown = "unknown"

class CardState(str, Enum):
    present = "present"
    absent = "absent"
    error = "error"
    power_down = "power_down"
    unreadable = "unreadable"

class AppState(str, Enum):
    ready = "ready"
    pin_required = "pin_required"
    puk_required = "puk_required"
    detected = "detected"
    illegal = "illegal"
    unknown = "unknown"
    unreadable = "unreadable"

class DataSession(str, Enum):
    connected = "connected"
    disconnected = "disconnected"
    authenticating = "authenticating"
    unknown = "unknown"
```

### Issue tagged union — `who`

```python
class WhoModem(BaseModel):
    kind: Literal["modem"]
    device: str        # cdc-wdmN

class WhoHost(BaseModel):
    kind: Literal["host"]
```

`Who = WhoModem | WhoHost` discriminated by `kind`. v1's free-form
`"ALL"` / `"/dev/cdc-wdm0"` / `"line1/wwan0"` is gone.

### Issue category and detail enums

`category` and `detail` are **closed enums**. v1's free-form strings
are gone. New entries land via a code change + schema version
discussion.

```python
class IssueCategory(str, Enum):
    config = "config"
    sim = "sim"
    datapath = "datapath"
    registration = "registration"
    qmi = "qmi"
    enumeration = "enumeration"
    power = "power"
    thermal = "thermal"
    zao = "zao"

class IssueDetail(str, Enum):
    apn_empty = "apn_empty"
    apn_mismatch = "apn_mismatch"
    sim_card_absent = "sim_card_absent"
    sim_card_error = "sim_card_error"
    sim_card_unreadable = "sim_card_unreadable"
    sim_power_down = "sim_power_down"
    sim_app_pin_required = "sim_app_pin_required"
    sim_app_puk_required = "sim_app_puk_required"
    sim_app_unreadable = "sim_app_unreadable"
    sim_app_detected = "sim_app_detected"
    not_registered_searching = "not_registered_searching"
    not_registered_idle = "not_registered_idle"
    denied = "denied"
    raw_ip_off = "raw_ip_off"
    session_disconnected = "session_disconnected"
    qmi_channel_hung = "qmi_channel_hung"
    operating_mode_offline = "operating_mode_offline"
    operating_mode_low_power = "operating_mode_low_power"
    enumeration_missing = "enumeration_missing"
    enumeration_address_fail = "enumeration_address_fail"
    enumeration_overcurrent = "enumeration_overcurrent"
    autosuspend_on = "autosuspend_on"
    thermal_warn = "thermal_warn"
    thermal_critical = "thermal_critical"
    zao_unit_inactive = "zao_unit_inactive"
    zao_log_stale = "zao_log_stale"
```

### Severity

```python
class Severity(str, Enum):
    info = "info"
    warn = "warn"
    error = "error"
    critical = "critical"
```

## 3. ModemState (state store)

One file per modem: `state/cdc-wdm0.json`. The persisted state machine
state. Schema in [RECOVERY_SPEC.md § State machine](RECOVERY_SPEC.md#3-per-modem-state-machine).

```jsonc
{
  "schema_version": 1,
  "device": "cdc-wdm0",
  "usb_path": "2-3.1.1",
  "state": {
    "kind": "recovering",
    "level": "soft",
    "since_monotonic": 12345.678,
    "since_iso": "2026-05-05T13:30:01+00:00",
    "cause": {
      "category": "registration",
      "detail": "not_registered_searching"
    }
  },
  "counters": {
    "soft_reset": 2,
    "modem_reset": 0,
    "usb_reset": 0,
    "set_apn": 0,
    "fix_raw_ip": 0,
    "sim_power_on": 0,
    "_healthy_streak": 0
  },
  "last_action": {
    "kind": "soft_reset",
    "ts_monotonic": 12300.0,
    "ts_iso": "2026-05-05T13:29:16+00:00",
    "result": "ok",
    "dry_run": false
  },
  "last_seen_iccid": "8997201...",
  "last_seen_imsi": "425030..."
}
```

State variants: `healthy`, `degraded`, `recovering`, `rf_blocked`,
`exhausted`, `disconnected`. Discriminator `kind`. See
[RECOVERY_SPEC.md](RECOVERY_SPEC.md).

## 4. status.json

Aggregate snapshot, written every cycle. Consumed by the fleet agent
and `spark-modem ctl status`.

```jsonc
{
  "schema_version": 1,
  "kind": "status",
  "ts": "2026-05-05T13:42:09+00:00",
  "uptime_seconds": 86400,
  "cycle": {
    "n": 14502,
    "duration_seconds": 1.34,
    "next_at_iso": "2026-05-05T13:42:39+00:00"
  },
  "summary": {
    "expected_modems": 4,
    "healthy": 3,
    "degraded": 0,
    "recovering": 1,
    "rf_blocked": 0,
    "exhausted": 0,
    "disconnected": 0
  },
  "zao": {
    "log_age_seconds": 0.7,
    "lines_active": [1, 2, 3, 4]
  },
  "modems": [
    {
      "device": "cdc-wdm0",
      "line": 1,
      "state": "healthy",
      "ipv4": "10.69.92.156/29"
    },
    {
      "device": "cdc-wdm3",
      "line": 4,
      "state": "recovering",
      "ipv4": null,
      "cause": "registration/not_registered_searching",
      "level": "soft",
      "next_action_eligible_at_iso": "2026-05-05T13:43:12+00:00"
    }
  ],
  "alerts_pending": []
}
```

## 5. events.jsonl

One JSON object per line. Append-only. Rotated by `logrotate`.

Discriminator field is `event`. The shape varies per event.

```jsonc
// Cycle started
{"schema_version":1,"event":"cycle_start","ts":"...","cycle":14502}

// Issue observed (one per issue per cycle)
{"schema_version":1,"event":"issue_observed","ts":"...","modem":"cdc-wdm3",
 "category":"registration","detail":"not_registered_searching","severity":"error"}

// State transition
{"schema_version":1,"event":"state_transition","ts":"...","modem":"cdc-wdm3",
 "from":"healthy","to":"degraded","cause":{"category":"registration","detail":"not_registered_searching"}}

// Action planned
{"schema_version":1,"event":"action_planned","ts":"...","modem":"cdc-wdm3",
 "kind":"soft_reset","cause":{"category":"registration","detail":"not_registered_searching"},
 "gates_passed":["signal","backoff","escalation"]}

// Action skipped (gate-rejected)
{"schema_version":1,"event":"action_skipped","ts":"...","modem":"cdc-wdm3",
 "kind":"modem_reset","reason":"signal_below_threshold",
 "thresholds":{"min_rsrp_dbm":-110,"min_rsrq_db":-15,"min_snr_db":0},
 "observed":{"rsrp_dbm":-118,"rsrq_db":-19,"snr_db":-3.1}}

// Action executed
{"schema_version":1,"event":"action_executed","ts":"...","modem":"cdc-wdm3",
 "kind":"soft_reset","duration_seconds":5.2,"result":"ok","dry_run":false,
 "details":{"invoked":"InfraCtrl.script reset_power_wwan 4 cdc-wdm3"}}

// Webhook posted
{"schema_version":1,"event":"webhook_sent","ts":"...","url":"https://...",
 "transition":"healthy -> degraded","modem":"cdc-wdm3","http_status":200}

// Daemon lifecycle
{"schema_version":1,"event":"daemon_started","ts":"...","version":"2.0.0",
 "config_files":["/etc/spark-modem-watchdog/config.yaml"]}
{"schema_version":1,"event":"daemon_stopped","ts":"...","reason":"sigterm","cycle":14502}

// Errors (always log them, never crash on them)
{"schema_version":1,"event":"error","ts":"...","module":"qmi",
 "operation":"get_signal","modem":"cdc-wdm3","error":"timeout","retry":1}
```

## 6. Identity map (`identity.json`)

Single object keyed by stable USB sysfs path. Survives cdc-wdm
renumbering and SIM swaps.

```jsonc
{
  "schema_version": 1,
  "kind": "identity_map",
  "entries": {
    "2-3.1.1": {
      "iccid": "8997201...",
      "imsi": "425030...",
      "first_seen_iso": "2026-04-01T08:00:00+00:00",
      "last_seen_iso": "2026-05-05T13:42:00+00:00",
      "apn": "internet"
    },
    "2-3.1.2": { "...": "..." }
  }
}
```

## 7. globals.json

```jsonc
{
  "schema_version": 1,
  "kind": "globals",
  "last_driver_reset_monotonic": 11100.5,
  "last_driver_reset_iso": "2026-05-05T11:00:00+00:00",
  "schema_drift_detected": false
}
```

## 8. Carrier table (`carriers/il.yaml`)

Hand-edited YAML. No code change needed for new entries.

```yaml
schema_version: 1
country: IL
mcc: "425"
fallback_apn: internetg
entries:
  - mnc: "01"
    carrier: Partner
    apn: internetg
  - mnc: "02"
    carrier: Cellcom
    apn: internet.cellcom.co.il
  - mnc: "03"
    carrier: Pelephone
    apn: internet
  # ...
```

Loaded at daemon start and on SIGHUP. Validated against schema; bad
entries cause startup to fail loudly.

## 9. Webhook payload

Posted on configured transitions. JSON body, `Content-Type: application/json`.
Optional `X-Spark-Signature: sha256=...` HMAC header (config-controlled).

```jsonc
{
  "schema_version": 1,
  "kind": "alert",
  "ts": "2026-05-05T13:42:09+00:00",
  "host": "linux",
  "transition": "healthy -> degraded",
  "modem": {
    "device": "cdc-wdm3",
    "line": 4,
    "usb_path": "2-3.1.4",
    "iccid": "8997201..."
  },
  "cause": {
    "category": "registration",
    "detail": "not_registered_searching",
    "severity": "error"
  },
  "context": {
    "signal_rsrp_dbm": -118,
    "consecutive_cycles_in_state": 1
  }
}
```

## 10. Versioning policy

- Adding an optional field with a sensible default → no version bump.
- Renaming or removing a field → bump `schema_version`.
- Changing the meaning or values of an enum → bump.
- A daemon refuses to load a snapshot, state, or config with a
  `schema_version` higher than its own. It logs a structured error
  and exits 3.
- A daemon MAY accept lower `schema_version` only if explicit
  migration code exists for the gap. Otherwise: refuse.
- The CLI's `--json` output carries the same `schema_version` rule.
