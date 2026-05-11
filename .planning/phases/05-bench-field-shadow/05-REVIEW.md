---
phase: 05-bench-field-shadow
reviewed: 2026-05-11T09:39:41Z
depth: standard
files_reviewed: 30
files_reviewed_list:
  - .gitignore
  - debian/spark-modem-watchdog.dirs
  - debian/spark-modem-watchdog.install
  - docs/RUNBOOK.md
  - src/spark_modem/cli/ctl/capture_fleet_fixture.py
  - src/spark_modem/cli/main.py
  - src/spark_modem/cli/redact.py
  - src/spark_modem/daemon/main.py
  - src/spark_modem/daemon/preflight_triple.py
  - src/spark_modem/qmi/parsers/get_revision.py
  - src/spark_modem/qmi/version.py
  - src/spark_modem/qmi/wrapper.py
  - src/spark_modem/zao_log/version.py
  - tests/integration/test_daemon_preflight_triple.py
  - tests/integration/test_deb_ships_known_fleet.py
  - tests/integration/test_fleet_fixture_roundtrip.py
  - tests/unit/cli/ctl/__init__.py
  - tests/unit/cli/ctl/test_capture_fleet_fixture.py
  - tests/unit/cli/test_redact_raw_qmicli.py
  - tests/unit/daemon/test_preflight_triple.py
  - tests/unit/qmi/parsers/__init__.py
  - tests/unit/qmi/parsers/test_get_revision.py
  - tests/unit/qmi/test_version.py
  - tests/unit/qmi/test_wrapper_dms_get_revision.py
  - tests/unit/tools/__init__.py
  - tests/unit/tools/test_audit_soak_exhausted.py
  - tests/unit/tools/test_audit_soak_zao.py
  - tests/unit/zao_log/test_version.py
  - tools/audit_soak_exhausted.py
  - tools/audit_soak_zao.py
findings:
  critical: 1
  warning: 4
  info: 6
  total: 11
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-05-11T09:39:41Z
**Depth:** standard
**Files Reviewed:** 30
**Status:** issues_found

## Summary

Phase 5 adds three substantial new surfaces: (a) the fleet-triple capture
+ preflight gate (X-01/X-02/X-03), (b) PII-redacting `capture-fleet-fixture`
CLI verb, and (c) two read-only soak-audit tools. Code quality is generally
high; the daemon preflight ordering (preflight → classify_prior_run →
acquire_pid_lock → READY=1) is correct, SP-04 is preserved (the only
`create_subprocess_exec` outside `subproc/` is still in `subproc/runner.py`),
list-form argv is used throughout, `match` is used where ModemState branching
occurs, and durations are not measured with `time.time()` anywhere in the new
code. State-changing flags are properly cleared in `finally` blocks.

However, there is **one Critical PII-leak finding**: the raw-qmicli redaction
regex omits `IPv4 gateway address: '<dotted>'` (and `IPv4 subnet mask:`),
which leak in `wds_get_current_settings.txt` captures. The test
`test_uim_capture_redacts_pii` asserts only on the ICCID/IMSI fixture and
does not exercise the `wds_get_current_settings` capture path, so the gap
slipped through CI. The captured fixture files are intended to ship in the
support bundle, so a real routable IP leaking into them is a clear NFR-22
violation. Four Warning-class findings cover defensive gaps (DoS protection
on tool-side log reads; exception messages potentially carrying un-redacted
content; redaction-test coverage gaps; structural use of `Exception` instead
of narrower types). Six Info items capture style/maintainability suggestions.

## Critical Issues

### CR-01: PII-redaction regex misses `IPv4 gateway address` and `IPv4 subnet mask`

**File:** `src/spark_modem/cli/redact.py:81-86`
**Issue:** `_RAW_QMICLI_PII_PATTERNS` contains `re.compile(rb"(IPv4 address:\s*')([^']+)(')")` but the real `qmicli --wds-get-current-settings` stdout (captured under `wds_get_current_settings.txt` by `capture-fleet-fixture`) also emits two adjacent lines with the same `'<dotted>'` shape:

```
    IPv4 address: '10.69.92.156'            # redacted (OK)
    IPv4 subnet mask: '255.255.255.248'      # NOT redacted — leaks
    IPv4 gateway address: '10.69.92.150'     # NOT redacted — leaks routable carrier-NAT gateway IP
```

This is verified in fixture `tests/fixtures/qmicli/get_current_settings/1.30/raw_ip_y.txt:4-6` which IS used by `capture-fleet-fixture`'s `wds_get_current_settings` capture (`QMICLI_CAPTURE_VERBS` line 49). The captured file ships in `tests/fixtures/fleet/<box-id>/qmi/<usb_path>/wds_get_current_settings.txt` (debian install path), and the file IS exported in support bundles. The gateway IP is a real address belonging to the carrier APN — leaking it is a NFR-22 violation. `redact_pii` is documented as covering "ICCID, UIM ID, IMSI, IPv4" (capture_fleet_fixture.py:7) — the docstring implies full IPv4 coverage but the regex only covers the bare `IPv4 address:` label.

The unit test `tests/unit/cli/ctl/test_capture_fleet_fixture.py::test_uim_capture_redacts_pii` only inspects `uim_get_card_status.txt`, never `wds_get_current_settings.txt`, so the gap is not caught.

**Fix:** Add two more patterns; cover all `IPv4 *: '...'` shapes:

```python
_RAW_QMICLI_PII_PATTERNS: tuple[re.Pattern[bytes], ...] = (
    re.compile(rb"(ICCID:\s*')([^']+)(')"),
    re.compile(rb"(UIM ID:\s*')([^']+)(')"),
    re.compile(rb"(IMSI:\s*')([^']+)(')"),
    # Cover all IPv4 label variants emitted by qmicli (address/subnet/gateway/
    # primary DNS/secondary DNS) — the simplest expansion is a label-prefix
    # match: "IPv4 <something> : '<dotted>'".
    re.compile(rb"(IPv4[^:'\n]*:\s*')([^']+)(')"),
)
```

Add the missing test coverage:

```python
async def test_wds_current_settings_capture_redacts_all_ipv4_fields(
    tmp_path: Path,
    _patched_runner: None,
) -> None:
    """Plan 05 NFR-22: every IPv4 label in wds_get_current_settings is redacted."""
    out = tmp_path / "box-01"
    await build_fleet_fixture(
        out_path=out,
        descriptors=_make_descriptors(),
        zao_log_path=Path("tests/fixtures/zao_log/version/banner_present.txt"),
    )
    for descriptor in _make_descriptors():
        body = (out / "qmi" / descriptor.usb_path / "wds_get_current_settings.txt").read_bytes()
        # Every routable dotted-quad IP MUST be redacted.
        for ip in (b"10.69.92.156", b"10.69.92.150"):
            assert ip not in body, f"raw IP {ip!r} survived redaction"
```

## Warnings

### WR-01: Audit tools read full Zao log + full events.jsonl without size cap (DoS)

**File:** `tools/audit_soak_zao.py:140` (and `tools/audit_soak_exhausted.py` via JSONL iteration)
**Issue:** `_parse_zao_blocks` calls `zao_log.read_text(encoding="utf-8", errors="replace")` on a path the operator passes via `--zao-log`. There is no size cap. A pathological / attacker-controlled / accidentally-uncompressed-100GB log file would consume the whole file in RAM. The production `zao_log/version.py:_HEAD_BYTES` (64 KiB cap) sets the precedent that whole-file reads of Zao logs are unacceptable; the audit needs all of the file but should at least bound memory by streaming.

The events.jsonl iterator in `_read_events_as_raw_dicts` (both tools) streams line-by-line so events.jsonl is fine; the concern is specifically `_parse_zao_blocks`.

**Fix:** Stream the Zao log line-by-line and stat the size up-front; refuse files larger than e.g. 1 GB with a clear error:

```python
def _parse_zao_blocks(zao_log: Path) -> list[_ZaoBlock]:
    _MAX_ZAO_LOG_BYTES = 1 * 1024 * 1024 * 1024  # 1 GiB
    try:
        size = zao_log.stat().st_size
    except FileNotFoundError:
        return []
    if size > _MAX_ZAO_LOG_BYTES:
        raise RuntimeError(
            f"Zao log {zao_log} is {size} bytes (cap {_MAX_ZAO_LOG_BYTES}); "
            "rotate or pre-filter before auditing"
        )
    blocks: list[_ZaoBlock] = []
    current_ts: str | None = None
    current_lines: set[int] = set()
    try:
        with zao_log.open("r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                m = _RASCOW_TS_RE.match(raw.rstrip("\n"))
                # ... (same body as before)
    except FileNotFoundError:
        return []
    if current_ts is not None:
        blocks.append(_ZaoBlock(ts_iso=current_ts, active_lines=frozenset(current_lines)))
    return blocks
```

### WR-02: `_capture_one_modem` failure path may write un-redacted `{exc!s}` to disk

**File:** `src/spark_modem/cli/ctl/capture_fleet_fixture.py:111-118`
**Issue:** The broad-except catches any exception from `subproc_runner.run()` OR `redact_pii_from_raw_qmicli()` and writes `f"... {type(exc).__name__}: {exc!s}\n"` to the per-verb output file. If `subproc_runner.run` ever raised an exception whose `str()` contains stderr / stdout / a Pydantic ValidationError citing a value, that text bypasses redaction and lands in the captured fixture. The probability is low (the production runner returns `CompletedProcess` for non-zero exits; only `FileNotFoundError` / `asyncio.TimeoutError` are likely), but defense-in-depth matters for a file that ships in support bundles.

**Fix:** Route the exception message through redaction before writing:

```python
except Exception as exc:
    raw_msg = (
        f"# CAPTURE FAILED for {verb_name} on {descriptor.usb_path} "
        f"({descriptor.cdc_wdm}): {type(exc).__name__}: {exc!s}\n"
    ).encode()
    # Run through the same PII pipeline so accidental PII in the exception
    # message can never leak (defense-in-depth; NFR-22).
    redacted = redact_pii_from_raw_qmicli(raw_msg)
```

### WR-03: `redact_pii_from_raw_qmicli` does not cover IMEI / MEID / ESN / phone-number labels

**File:** `src/spark_modem/cli/redact.py:81-86`
**Issue:** The pattern list is limited to ICCID / UIM ID / IMSI / IPv4. Real qmicli also emits IMEI (under `--dms-get-ids`, not currently in `QMICLI_CAPTURE_VERBS` but easy to add later), MEID, ESN, MSISDN — all PII. The current capture verb list (7 verbs, locked by `test_qmicli_capture_verbs_list_is_locked_at_7`) does not invoke `dms_get_ids`, so this is latent rather than immediate. But the test that locks the verb list will catch a deliberate add, and at that point a reviewer must remember to update the redact patterns. Better to make the redaction layer cover everything plausibly-PII-shaped from the start.

**Fix:** Either expand patterns now to include common identity labels, or add a guard test that fails the build if any verb in `QMICLI_CAPTURE_VERBS` could plausibly emit a known PII label not covered by `_RAW_QMICLI_PII_PATTERNS`. Minimum expansion:

```python
_RAW_QMICLI_PII_PATTERNS: tuple[re.Pattern[bytes], ...] = (
    re.compile(rb"(ICCID:\s*')([^']+)(')"),
    re.compile(rb"(UIM ID:\s*')([^']+)(')"),
    re.compile(rb"(IMSI:\s*')([^']+)(')"),
    re.compile(rb"(IMEI:\s*')([^']+)(')"),
    re.compile(rb"(MEID:\s*')([^']+)(')"),
    re.compile(rb"(ESN:\s*')([^']+)(')"),
    re.compile(rb"(MSISDN:\s*')([^']+)(')"),
    re.compile(rb"(IPv4[^:'\n]*:\s*')([^']+)(')"),  # covers address/subnet/gateway/DNS
)
```

### WR-04: ISO-8601 string comparison in `_find_contemporaneous_block` is not robust across zone offsets

**File:** `tools/audit_soak_zao.py:164-178`
**Issue:** The docstring acknowledges the risk: "For mixed offsets the operator would normalise upstream before running the audit." The `_RASCOW_TS_RE` regex explicitly accepts both `+HH:MM`/`-HH:MM` AND `Z` suffix:

```python
r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:\d{2}|Z))"
```

If a real Zao build emits `Z` and the events.jsonl emits `+00:00` (which `daemon/main.py` does — `datetime.now(UTC).isoformat().replace("+00:00", "Z")` is the inverse pattern used in `capture_fleet_fixture._build_triple_dict`, but event_logger likely uses raw `.isoformat()`), then `"2026-05-11T00:00:00Z" < "2026-05-11T00:00:00+00:00"` evaluates `True` because `Z (0x5A) < + (0x2B)` is `False` — actually `0x5A > 0x2B`, so the inequality is in the other direction; either way, equality comparison fails and the audit silently classifies events as `no_zao_snapshot_for_cycle` instead of detecting violations. The audit could miss real M4 violations on a box where Zao writes `Z`.

**Fix:** Parse both sides via `datetime.fromisoformat` (Python 3.12 supports both `Z` and `+00:00`) before comparison:

```python
def _normalize_ts(ts: str) -> datetime:
    # 3.12: datetime.fromisoformat accepts both Z and +HH:MM suffixes.
    return datetime.fromisoformat(ts)

def _find_contemporaneous_block(blocks: list[_ZaoBlock], event_ts: str) -> _ZaoBlock | None:
    event_dt = _normalize_ts(event_ts)
    latest: _ZaoBlock | None = None
    for b in blocks:
        if _normalize_ts(b.ts_iso) <= event_dt:
            latest = b
        else:
            break
    return latest
```

Add a test for the `Z`/`+00:00` mixed-shape case.

## Info

### IN-01: Duplicated `if not args.skip_preflight:` guard

**File:** `src/spark_modem/daemon/main.py:210, 226`
**Issue:** Two consecutive blocks both guard on `args.skip_preflight`. Functionally identical to a single combined block; the duplication invites a future maintainer to update one and miss the other.
**Fix:** Collapse into one `if not args.skip_preflight:` containing both `try/except`s, or extract to a helper:

```python
if not args.skip_preflight:
    try:
        await preflight_check()
    except PreflightFailed as exc:
        return _handle_preflight_failure(run_dir, "preflight failed", exc)
    try:
        await preflight_check_known_fleet_triple()
    except UnknownFleetTriple as exc:
        return _handle_preflight_failure(run_dir, "unknown fleet triple", exc)
```

### IN-02: `_DEFAULT_ZAO_LOG_PATH` constant duplicated across modules

**File:** `src/spark_modem/cli/ctl/capture_fleet_fixture.py:55`, `src/spark_modem/daemon/preflight_triple.py:47`
**Issue:** Both modules independently define `_DEFAULT_ZAO_LOG_PATH = Path("/var/log/zao-remote-endpoint.log")`. A future change (e.g. the Zao team moves the log path) requires editing both. Same duplication exists for the Zao banner location (already centralised in `zao_log/version.py`, good).
**Fix:** Promote the constant to `spark_modem.zao_log` (e.g. `zao_log/__init__.py` or a new `zao_log/paths.py`) and import in both call sites. Low-priority; this is a single string at present.

### IN-03: `_read_events_as_raw_dicts` is duplicated verbatim across the two audit tools

**File:** `tools/audit_soak_zao.py:53-91`, `tools/audit_soak_exhausted.py:58-89`
**Issue:** Acknowledged in the second tool's docstring as deliberate ("tools/ scripts do not import each other"). But the duplication is a real maintenance burden: a future fix to rotated-sibling discovery would need to land in both files.
**Fix:** Create `tools/_audit_shared.py` (a private module the tools both import; not a package). The "tools don't import each other" rule was a stylistic choice rather than a hard invariant — sharing a private helper module is reasonable. Defer to Phase 6 if time-bound.

### IN-04: `dms_get_revision` parser regex matches any line starting with `Revision:` substring

**File:** `src/spark_modem/qmi/parsers/get_revision.py:27`
**Issue:** `re.compile(r"Revision:\s*'([^']+)'")` matches anywhere in the body (`re.search`, not `re.match` and not anchored). If a future qmicli release introduces another `<something> Revision: '...'` line (e.g. `Firmware Revision: '...'`), the first occurrence wins and could be the wrong field. Current real fixtures only contain one `Revision:` line so this is theoretical.
**Fix:** Anchor more precisely to the line start (whitespace + label):

```python
_RE_REVISION: Final[re.Pattern[str]] = re.compile(r"^\s*Revision:\s*'([^']+)'", re.MULTILINE)
```

### IN-05: `audit_soak_exhausted._resolve_decay_k_default` silently swallows ImportError/AttributeError

**File:** `tools/audit_soak_exhausted.py:113-129`
**Issue:** Two `try/except` blocks swallow `ImportError`, `KeyError`, `AttributeError` without logging. If the production `Settings` model is later refactored (e.g. `healthy_streak_decay_k` is renamed), the audit will silently fall back to the hardcoded `10` and an operator running on a box where the true K is 15 would get false UNEXPLAINED classifications.
**Fix:** Log at WARNING level when falling back to the literal:

```python
import logging
_logger = logging.getLogger(__name__)
...
try:
    from spark_modem.config.settings import Settings
    default = Settings.model_fields["healthy_streak_decay_k"].default
    if isinstance(default, int):
        return default
except (ImportError, KeyError, AttributeError) as exc:
    _logger.warning("could not resolve _DECAY_K_DEFAULT via Settings: %s; using literal 10", exc)
return 10
```

Or surface via the `--decay-k` CLI flag's `--help` text so the operator can see the resolved default at invocation time. (The current `default=_K_DEFAULT` in argparse does show the value, so this is partly mitigated.)

### IN-06: `capture-fleet-fixture` exit-1 message conflates "no modems" with "configuration error"

**File:** `src/spark_modem/cli/ctl/capture_fleet_fixture.py:215-221`
**Issue:** When `SysfsInventory.scan()` returns empty, the CLI prints `"capture-fleet-fixture: no Sierra modems found on sysfs; is ModemManager masked and Zao running?"` and returns exit code 1. This is the same exit code as a real failure during `build_fleet_fixture`. An operator scripting this verb has no way to distinguish "no hardware present" (expected on dev laptop) from "capture started but failed mid-way" (an actual problem).
**Fix:** Use distinct exit codes — `EX_UNAVAILABLE` (69) for "no modems found" and `1` for general capture failure:

```python
if not descriptors:
    print(
        "capture-fleet-fixture: no Sierra modems found on sysfs; "
        "is ModemManager masked and Zao running?",
        file=sys.stderr,
    )
    return 69  # EX_UNAVAILABLE (sysexits.h)
```

---

## Out-of-scope verifications (passed)

These were spot-checked against CLAUDE.md invariants and found clean:

1. **SP-04** (subprocess only via `subproc/`): grep confirms the only `create_subprocess_exec` in `src/spark_modem/` remains in `src/spark_modem/subproc/runner.py:146`. New `qmicli --version` call routes through `subproc_runner.run`.
2. **Argv shape**: every new qmicli invocation uses list-form argv (capture_fleet_fixture.py:107, qmi/version.py:55, qmi/wrapper.py:236-254). No shell strings.
3. **Pydantic >=2.13**: `FleetTriple` uses `ConfigDict(frozen=True, extra="forbid")` and `GetRevisionResult` uses `ConfigDict(extra="ignore", frozen=True)`. Both proper v2.
4. **Preflight ordering** (CONTEXT.md L-05): `daemon/main.py` runs the X-03 triple check at line 226-235, AFTER FR-60 `preflight_check()` (line 210-219) and BEFORE `classify_prior_run()` (line 238) and `acquire_pid_lock()` (line 243). Test `test_unknown_triple_exits_78_and_writes_marker` verifies the failure-path contract.
5. **No `if/elif` on ModemState**: `audit_soak_exhausted.py:232-236` uses `match` on `to_state`. The locked test `test_match_pattern_used_not_if_elif` enforces this.
6. **No `time.time()` for durations**: new code uses `datetime.now(UTC).isoformat()` only for wall-clock ISO stamps, never for elapsed-time measurements.
7. **`--device-open-proxy` on every qmicli call**: `dms_get_revision` in QmiWrapper:236-254 passes `--device-open-proxy` unconditionally; the locked test `test_dms_get_revision_uses_device_open_proxy_and_correct_argv` enforces this.
8. **No state mutation in read-only methods**: `dms_get_revision` does NOT touch `_in_critical_section`; the locked test `test_dms_get_revision_does_not_set_critical_section_flag` enforces.
9. **Atomic-write contract preserved**: new write paths (`triple.json`, `zao-log-sample.txt`, per-verb `.txt`) all use `write_text` / `write_bytes` on pre-created parent directories. State-store files (the daemon invariant) are not touched by new code.
10. **ADR-0009 usb_path keying**: capture-fleet-fixture explicitly comments the choice (capture_fleet_fixture.py:179-184) and the locked test `test_modem_subdirs_match_usb_path_shape` enforces the `2-3.1.N`-shape directory naming.
11. **No inbound IPC**: no HTTP/DBus/UDS-RPC surfaces added. The capture verb is a CLI subcommand reading sysfs + running qmicli; the daemon preflight reads `/etc/.../known-fleet/<id>/triple.json` only.
12. **TDD discipline**: tests assert behavior (file contents, exit codes, redaction tokens) rather than implementation details. The "list locked at N" test (`test_qmicli_capture_verbs_list_is_locked_at_7`) is implementation-detail-shaped by design — it's an enum-pinning test, deliberate per the docstring.

---

_Reviewed: 2026-05-11T09:39:41Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
