# Phase 5: Bench & Field Shadow — Pattern Map

**Mapped:** 2026-05-11
**Files analyzed:** 17 new/modified files (8 code + 8 test + 3 doc/fixture/packaging)
**Analogs found:** 17 / 17 (all have a strong in-repo analog)

Phase 5 is 80% wiring, 20% net-new code. Every new file extends a surface that
already exists; this map names the exact analog and excerpts the pattern to
copy.

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/spark_modem/qmi/wrapper.py` (modify: add `dms_get_revision`) | wrapper-method | request-response (qmicli subprocess) | `src/spark_modem/qmi/wrapper.py:223-234` (`dms_get_operating_mode`) | exact (same file, same shape) |
| `src/spark_modem/qmi/parsers/get_revision.py` (NEW) | parser | transform (bytes → typed model) | `src/spark_modem/qmi/parsers/get_operating_mode.py` | exact |
| `src/spark_modem/qmi/version.py` (NEW) | utility | request-response (qmicli `--version` stdout) | `src/spark_modem/daemon/preflight.py:37-57` (the existing `qmicli --version` call) | role-match |
| `src/spark_modem/cli/ctl/capture_fleet_fixture.py` (NEW) | CLI verb (subcommand) | request-response (operator-invoked, multi-step orchestration) | `src/spark_modem/cli/ctl/support_bundle.py` | exact (same dir, same `ctl <verb>` pattern, same PII redaction, same multi-step `build_*` helper) |
| `src/spark_modem/cli/main.py` (modify: add subparser) | argparse-registration | request-response | `src/spark_modem/cli/main.py:168-178` (`ctl support-bundle` registration block) | exact |
| `src/spark_modem/daemon/preflight_triple.py` (NEW) | preflight check | startup gate | `src/spark_modem/daemon/preflight.py` | exact (same `PreflightFailed` shape, same `write_last_config_error` marker, same exit-code-78 contract) |
| `src/spark_modem/daemon/main.py` (modify: slot new preflight in) | daemon startup | startup gate | `src/spark_modem/daemon/main.py:205-215` (existing FR-60 preflight block) | exact |
| `tools/audit_soak_zao.py` (NEW) | one-shot audit script | batch (events.jsonl + Zao log → JSON report) | `tools/pull_replay_traces.py` (file shape + argparse + exit codes) + `src/spark_modem/cli/ctl/history.py:78-101` (events reader) + `src/spark_modem/zao_log/parser.py:69-111` (Zao parser) | role-match (composes two reusable substrates) |
| `tools/audit_soak_exhausted.py` (NEW) | one-shot audit script | batch (events.jsonl → policy replay → JSON report) | `tools/pull_replay_traces.py` (file shape) + `src/spark_modem/policy/engine.py` (cycle ordering) + `src/spark_modem/policy/transitions.py` (state-match pattern) | role-match |
| `tests/unit/qmi/test_wrapper_dms_get_revision.py` (NEW) | test | unit | `tests/unit/qmi/test_wrapper.py` (parametrized methods table) | exact |
| `tests/unit/qmi/test_version.py` (NEW) | test | unit (monkeypatch `subproc_runner.run`) | `tests/unit/daemon/test_preflight.py:21-68` | exact (same monkeypatch shape) |
| `tests/unit/cli/test_capture_fleet_fixture.py` (NEW) | test | unit (round-trip via `tmp_path` + `FixtureRunner`) | `tests/unit/cli/test_ctl_support_bundle.py` | exact |
| `tests/integration/test_fleet_fixture_roundtrip.py` (NEW) | test | integration | `tests/integration/test_lifecycle.py` (existing integration shape) | role-match |
| `tests/unit/daemon/test_preflight_triple.py` (NEW) | test | unit | `tests/unit/daemon/test_preflight.py` | exact |
| `tests/integration/test_daemon_preflight_triple.py` (NEW) | test | integration (daemon startup wired) | `tests/integration/test_lifecycle.py` | role-match |
| `tests/unit/tools/test_audit_soak_zao.py` (NEW) | test | unit | `tests/unit/cli/test_ctl_history.py` (events.jsonl synthesis pattern) | role-match (no `tests/unit/tools/` exists today — new directory) |
| `tests/unit/tools/test_audit_soak_exhausted.py` (NEW) | test | unit | `tests/unit/cli/test_ctl_history.py` (same) | role-match |
| `tests/fixtures/qmicli/get_revision/<version>/<scenario>.txt` (NEW tree) | fixture | data | `tests/fixtures/qmicli/get_operating_mode/1.30/online.txt` (sibling intent) | exact |
| `tests/fixtures/qmicli/version/<version>/<scenario>.txt` (NEW tree) | fixture | data | `tests/fixtures/qmicli/get_signal/1.30/lte_strong.txt` (version-banner sibling) | exact |
| `tests/fixtures/fleet/<box-id>/` (NEW tree) | fixture | data | mirrors `tests/fixtures/qmicli/<intent>/<version>/<scenario>.txt` shape under a new root | role-match |
| `debian/spark-modem-watchdog.install` (modify) | packaging | install-time copy | `debian/spark-modem-watchdog.install:6-9` (existing line shape) | exact |
| `.planning/phases/05-bench-field-shadow/SIGNOFF.md` (NEW) | operator doc | markdown checklist | new artifact; structure from RESEARCH Q8 (industry PRR template) | n/a (no in-repo precedent) |
| `.planning/phases/05-bench-field-shadow/SOAK_RUNBOOK.md` (NEW) | operator doc | markdown runbook | `docs/RUNBOOK.md` § 1-2 (heading style + bash code-fence convention) | role-match |
| `docs/RUNBOOK.md` (modify: 1-line cross-reference) | operator doc | markdown | `docs/RUNBOOK.md:1-14` (existing front-matter shape) | exact |

---

## Pattern Assignments

### `src/spark_modem/qmi/wrapper.py` — add `dms_get_revision`

**Analog:** `src/spark_modem/qmi/wrapper.py:223-234` (the existing `dms_get_operating_mode`)

**Why this:** Same file, same argv shape (`--device-open-proxy`, `--device=`, single qmicli flag), same read-only timeout (`_DEFAULT_TIMEOUT_S`), same Protocol-based `runner` injection, same `--device-open-proxy` invariant (FR-74).

**Core pattern to copy** (`wrapper.py:223-234`):
```python
async def dms_get_operating_mode(self) -> CompletedProcess:
    return await self._runner.run(
        self._argv(
            [
                "qmicli",
                "--device-open-proxy",
                f"--device={self._device}",
                "--dms-get-operating-mode",
            ]
        ),
        timeout_s=_DEFAULT_TIMEOUT_S,
    )
```

**New method signature to write** (place in the "query methods (read-only)" block, immediately above or below `dms_get_operating_mode`):
```python
async def dms_get_revision(self) -> CompletedProcess:
    return await self._runner.run(
        self._argv(
            [
                "qmicli",
                "--device-open-proxy",
                f"--device={self._device}",
                "--dms-get-revision",
            ]
        ),
        timeout_s=_DEFAULT_TIMEOUT_S,
    )
```

**Do NOT:** add `_in_critical_section = True` wrapping — `dms_get_revision` is read-only.

---

### `src/spark_modem/qmi/parsers/get_revision.py` (NEW)

**Analog:** `src/spark_modem/qmi/parsers/get_operating_mode.py` (full file, 54 LOC)

**Why this:** Single-field parser: regex against the canonical "X: '<value>'" libqmi format, returns `pydantic.BaseModel` with `ConfigDict(extra="ignore", frozen=True)`, returns `QmiError` on missing-field. Identical shape needed for `Revision: 'SWI9X30C_02.38.00.00'`.

**Imports + module-level constants** (`get_operating_mode.py:13-27`):
```python
from __future__ import annotations

import re
from typing import Final

from pydantic import BaseModel, ConfigDict

from spark_modem.qmi.errors import QmiError, QmiErrorReason
from spark_modem.qmi.parsers._header import strip_header

_ARGV: Final[tuple[str, ...]] = ("qmicli", "--dms-get-operating-mode")
_RESPONSE_HEADER: Final[str] = "Operating mode retrieved"
_RE_MODE: Final[re.Pattern[str]] = re.compile(r"Mode:\s*'([^']+)'")
```

**Result model + parse function** (`get_operating_mode.py:30-53`):
```python
class GetOperatingModeResult(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    mode: str | None = None


def parse_get_operating_mode(stdout: bytes) -> GetOperatingModeResult | QmiError:
    body = strip_header(stdout).decode("utf-8", errors="replace")
    if _RESPONSE_HEADER not in body:
        return QmiError(
            reason=QmiErrorReason.UNEXPECTED_OUTPUT,
            argv=_ARGV,
            detail="no operating-mode block in stdout",
        )
    m = _RE_MODE.search(body)
    if m is None:
        return QmiError(
            reason=QmiErrorReason.MISSING_FIELD,
            argv=_ARGV,
            field="mode",
            detail="Mode line absent from operating-mode block",
        )
    return GetOperatingModeResult(mode=m.group(1).strip().lower())
```

**Substitutions for the new parser:**
- `_ARGV` → `("qmicli", "--dms-get-revision")`
- `_RESPONSE_HEADER` → `"Device revisions retrieved"` (verify against real fixture during planning)
- `_RE_MODE` → `_RE_REVISION = re.compile(r"Revision:\s*'([^']+)'")`
- Class → `GetRevisionResult`, field → `revision: str | None = None`

---

### `src/spark_modem/qmi/version.py` (NEW) — libqmi version detection

**Analog:** `src/spark_modem/daemon/preflight.py:37-57` (the existing `qmicli --version` call site that today discards stdout)

**Why this:** Phase 5 needs to *parse* the stdout that preflight already calls. Module shares the SP-04 invariant (must route through `subproc.runner.run`). Single helper, ~30 LOC.

**Subprocess pattern to copy** (`preflight.py:53-57`):
```python
for binary, args in _PREFLIGHT_BINARIES:
    try:
        await subproc_runner.run([binary, *args], timeout_s=_PREFLIGHT_TIMEOUT_S)
    except FileNotFoundError as exc:
        raise PreflightFailed(f"required binary {binary!r} not on PATH (FR-60)") from exc
```

**Error-class pattern to copy** (`preflight.py:29-34`):
```python
class PreflightFailed(RuntimeError):  # noqa: N818 — public name fixed by plan acceptance
    """Raised when a required external binary is missing from PATH (FR-60)."""
```

**New module skeleton** (paraphrased from RESEARCH § Q3):
```python
# src/spark_modem/qmi/version.py
from __future__ import annotations

import re
from typing import Final

from spark_modem.subproc import runner as subproc_runner

_LIBQMI_VERSION_RE: Final[re.Pattern[str]] = re.compile(
    r"libqmi-glib\s+(\d+\.\d+\.\d+)", re.IGNORECASE
)
_DEFAULT_TIMEOUT_S: Final[float] = 2.0


class QmiVersionDetectionFailed(RuntimeError):  # noqa: N818 — matches PreflightFailed shape
    """Raised when qmicli --version stdout cannot be parsed."""


async def detect_libqmi_version(*, timeout_s: float = _DEFAULT_TIMEOUT_S) -> str:
    cp = await subproc_runner.run(["qmicli", "--version"], timeout_s=timeout_s)
    if cp.exit_code != 0:
        raise QmiVersionDetectionFailed(
            f"qmicli --version exit_code={cp.exit_code} stderr={cp.stderr[:512]!r}"
        )
    m = _LIBQMI_VERSION_RE.search(cp.stdout.decode("utf-8", errors="replace"))
    if m is None:
        raise QmiVersionDetectionFailed(
            f"qmicli --version stdout did not match libqmi-glib regex: {cp.stdout[:512]!r}"
        )
    return m.group(1)
```

**Anti-pattern to AVOID:** `subprocess.run(['qmicli', '--version'])` — SP-04 lint scope is `src/spark_modem/`, this lives there, must route through `subproc.runner.run`.

---

### `src/spark_modem/cli/ctl/capture_fleet_fixture.py` (NEW) — primary new CLI verb

**Analog:** `src/spark_modem/cli/ctl/support_bundle.py` (full file)

**Why this:** Same `cli/ctl/` directory; same multi-step orchestration (assemble several pieces into one output tree); same per-file PII redaction via `redact_pii`; same `build_*` helper that takes injected paths; same final `async def run(args) -> int` dispatcher; same `out_path` argparse arg.

**File-level docstring shape** (`support_bundle.py:1-24`) — copy the structure:
```python
"""ctl <verb> — <one-line purpose>.

Contents:
  - <piece 1>
  - <piece 2>
  ...

Redactions are one-way and consistent: same ICCID/IMSI → same
``<redacted:<sha256[:8]>>`` ...

File mode: <perms>.
"""
```

**Imports pattern** (`support_bundle.py:26-43`):
```python
from __future__ import annotations

import argparse
import io
import json
import os
import socket
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path

from spark_modem.cli.ctl.history import read_events_with_rotated_siblings
from spark_modem.cli.redact import (
    redact_iccid_imsi_in_dict,
    redact_webhook_url_to_host_only,
)
from spark_modem.state_store.store import StateStore
```

For the capture verb, swap to:
```python
from spark_modem.cli.redact import redact_pii  # sha256[:8] form
from spark_modem.qmi.version import detect_libqmi_version
from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.subproc import runner as subproc_runner
from spark_modem.zao_log.parser import ZaoLogParser
```

**Builder-function shape with injected paths** (`support_bundle.py:52-96`):
```python
async def build_support_bundle(
    *,
    out_path: Path | None = None,
    state_root: Path | None = None,
    events_log_path: Path | None = None,
    conf_d_path: Path | None = None,
    webhook_url_for_redaction: str | None = None,
) -> Path:
    """Assemble + redact a tarball; return the path of the bundle.

    All input paths are dependency-injected for tests; production callers
    pass None and the defaults bind to ``/var/lib/...`` / ``/var/log/...``
    / ``/etc/...``.
    """
    # ... orchestration ...
```

**`async def run` entry point** (`support_bundle.py:182-190`) — copy verbatim:
```python
async def run(args: argparse.Namespace) -> int:
    out_path = Path(args.out) if args.out else None
    try:
        target = await build_support_bundle(out_path=out_path)
    except OSError as exc:
        print(f"ctl support-bundle: failed: {exc}", file=sys.stderr)
        return 1
    print(str(target.resolve()))
    return 0
```

**Per-file PII redaction pattern** — copy from `cli/redact.py:19-28`:
```python
def redact_pii(value: str) -> str:
    """Returns ``<redacted:<sha256[:8]>>``. Same input → same redacted form."""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"<redacted:{digest}>"
```
Apply at capture time to ICCID/IMSI/IP fields in raw qmicli stdout before writing
`qmi/<usb_path>/<verb>.txt`. RESEARCH Q5 says the same sha256[:8] form is the
contract.

**Subprocess invocation** — every qmicli call routes through:
```python
from spark_modem.subproc import runner as subproc_runner
cp = await subproc_runner.run(
    ["qmicli", "--device-open-proxy", f"--device=/dev/{descriptor.cdc_wdm}", verb_arg],
    timeout_s=8.0,
)
```
This is identical to `wrapper.py:23` import pattern; `cli/ctl/` is on the
SP-04-scoped side of the line — the wrapper module is the SOLE escape valve.

**ADR-0009 invariant in fixture tree:**
```python
modem_dir = qmi_dir / descriptor.usb_path  # e.g. "2-3.1.1"  NOT descriptor.cdc_wdm
```
RESEARCH § Pitfalls: tests must assert `re.match(r"^\d+-\d+(\.\d+)+$", subdir.name)`.

---

### `src/spark_modem/cli/main.py` — add `capture-fleet-fixture` subparser

**Analog:** `src/spark_modem/cli/main.py:168-178` (the existing `ctl support-bundle` registration)

**Existing block to copy** (`main.py:168-178`):
```python
# ctl support-bundle
p_sb = ctl_sub.add_parser(
    "support-bundle",
    help="Build redacted support tarball",
)
p_sb.add_argument(
    "--out",
    type=str,
    default=None,
    help="Output path (default: /var/lib/.../support-bundles/...)",
)
p_sb.set_defaults(func=ctl_support_bundle.run)
```

**Imports block to extend** (`main.py:25-27`):
```python
from spark_modem.cli.ctl import history as ctl_history
from spark_modem.cli.ctl import maintenance as ctl_maintenance
from spark_modem.cli.ctl import support_bundle as ctl_support_bundle
# add:
from spark_modem.cli.ctl import capture_fleet_fixture as ctl_capture_fleet
```

**New block to add** (immediately after the `support-bundle` block):
```python
# ctl capture-fleet-fixture
p_cff = ctl_sub.add_parser(
    "capture-fleet-fixture",
    help="Capture per-box (firmware, SDK, libqmi) triple + redacted qmicli fixtures",
)
p_cff.add_argument(
    "--out",
    type=str,
    required=True,
    help="Output directory for the per-box fixture tree",
)
p_cff.set_defaults(func=ctl_capture_fleet.run)
```

---

### `src/spark_modem/daemon/preflight_triple.py` (NEW) — X-03 preflight check

**Analog:** `src/spark_modem/daemon/preflight.py` (the entire file is the template)

**Why this:** Same exit contract: raise a `PreflightFailed`-shaped exception → `daemon/main.py` catches it → writes `last-config-error` → returns exit code 78. Boot classifier reads marker on next boot → emits `DaemonRestart{reason=CONFIG_INVALID}`.

**Exception-class pattern** (`preflight.py:29-34`) — copy verbatim, rename:
```python
class UnknownFleetTriple(RuntimeError):  # noqa: N818 — match PreflightFailed shape
    """Raised when the local (firmware, SDK, libqmi) triple is not in the
    known-fleet index baked into the .deb (X-03)."""
```

**Module-level constants** — mirror `preflight.py:37-41`:
```python
_KNOWN_FLEET_DIR: Final[Path] = Path("/etc/spark-modem-watchdog/known-fleet")
_PREFLIGHT_TIMEOUT_S: Final[float] = 8.0  # qmicli --dms-get-revision
```

**Check-function pattern** — `preflight.py:44-57`:
```python
async def preflight_check() -> None:
    """Verify every required binary is present on PATH."""
    for binary, args in _PREFLIGHT_BINARIES:
        try:
            await subproc_runner.run([binary, *args], timeout_s=_PREFLIGHT_TIMEOUT_S)
        except FileNotFoundError as exc:
            raise PreflightFailed(f"required binary {binary!r} not on PATH (FR-60)") from exc
```

**New check shape** (sketched in RESEARCH Q1 + Q4):
```python
async def preflight_check_known_fleet_triple(
    *,
    known_fleet_dir: Path = _KNOWN_FLEET_DIR,
) -> None:
    """Read every triple.json in known_fleet_dir, compute the local triple,
    and raise UnknownFleetTriple if the local triple is not in the set (X-03).
    """
    # 1. Probe the local triple via QmiWrapper.dms_get_revision (per modem) +
    #    detect_libqmi_version (once) + zao_log.version probe (once).
    # 2. Walk known_fleet_dir for <box-id>/triple.json files; load each.
    # 3. Equality check (firmware, sdk, libqmi) across the set.
    # 4. Raise UnknownFleetTriple(...) with the operator-actionable journalctl
    #    message shape from RESEARCH Q4 if no match.
    ...
```

**Operator-actionable error message** (RESEARCH § Q4, journalctl shape):
```
ERROR unknown fleet triple: em7421_firmware=SWI9X30C_02.38.00.00, zao_sdk=2.1.0, libqmi=1.30.6 not in /etc/spark-modem-watchdog/known-fleet/. Run 'spark-modem ctl capture-fleet-fixture --out=/tmp/fixture' and commit the resulting triple.json to tests/fixtures/fleet/<box-id>/ before retrying.
```

**Anti-pattern to AVOID:** writing to `/etc/spark-modem-watchdog/known-fleet/` from this module. The index is package-owned (dpkg-managed); the daemon is read-only. A grep test should pin: `grep -r 'known-fleet' src/spark_modem/` finds no `open(..., 'w')` or `atomic_write_bytes` patterns.

---

### `src/spark_modem/daemon/main.py` — slot the new preflight in

**Analog:** `src/spark_modem/daemon/main.py:205-215` (the existing FR-60 preflight block)

**Existing block to mirror** (`main.py:205-215`):
```python
# Step 3: FR-60 preflight.
if not args.skip_preflight:
    try:
        await preflight_check()
    except PreflightFailed as exc:
        try:
            write_last_config_error(run_dir=run_dir, message=str(exc))
        except Exception:
            logger.exception("failed to write last-config-error marker")
        logger.error("preflight failed: %s", exc)
        return 78
```

**Imports block to extend** (`main.py:50-54`):
```python
from spark_modem.daemon.preflight import (
    PreflightFailed,
    preflight_check,
    write_last_config_error,
)
# add:
from spark_modem.daemon.preflight_triple import (
    UnknownFleetTriple,
    preflight_check_known_fleet_triple,
)
```

**New block** (insert IMMEDIATELY AFTER the existing FR-60 block, BEFORE `acquire_pid_lock` at line 223):
```python
# Step 3.5: X-03 known-fleet triple preflight (Phase 5 addition).
if not args.skip_preflight:
    try:
        await preflight_check_known_fleet_triple()
    except UnknownFleetTriple as exc:
        try:
            write_last_config_error(run_dir=run_dir, message=str(exc))
        except Exception:
            logger.exception("failed to write last-config-error marker")
        logger.error("unknown fleet triple: %s", exc)
        return 78
```

**Note on `--skip-preflight`:** the existing flag (`main.py:101-104`) MUST also bypass the new check so `spark-modem-watchdog --laptop --skip-preflight` works on a non-Jetson dev host. Wrap inside the same `if not args.skip_preflight:` guard (illustrated above).

**Note on sd_notify:** the daemon hasn't built `SdNotifyLifecycle()` yet at this point in startup (`main.py:225` constructs it AFTER PID lock acquisition). RESEARCH Q4 confirms: do NOT add sd_notify wiring; rely on systemd interpreting exit code 78 + the boot classifier reading `last-config-error` on next boot.

---

### `tools/audit_soak_zao.py` (NEW) — S-01 #2 detector

**Analog (file shape + argparse + exit codes):** `tools/pull_replay_traces.py`
**Analog (events reader):** `src/spark_modem/cli/ctl/history.py:78-101` (`read_events_with_rotated_siblings`)
**Analog (Zao parser):** `src/spark_modem/zao_log/parser.py:69-111` (`_parse_bytes` for cycle-time snapshot)

**File-level docstring + SP-04-exemption disclaimer** (`pull_replay_traces.py:1-27`) — copy this exact block:
```python
"""<one-line purpose>.

<longer description>

## Subprocess discipline

This is a ``tools/`` script (NOT under ``src/spark_modem/``); SP-04 lint
scope excludes anything outside ``src/`` (see
``scripts/lint_no_subprocess.sh:11``). Direct ``subprocess.run`` is
acceptable here.

## Exit codes

- ``0`` -- no violations / clean soak window.
- ``1`` -- violations found.
- ``2`` -- operational error (bad input path, etc.).
"""
```

**argparse + main pattern** (`pull_replay_traces.py:39-55`):
```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=("Audit a soak window for S-01 #2 violations."),
    )
    parser.add_argument("--events", type=Path, required=True,
                        help="Path to events.jsonl")
    parser.add_argument("--zao-log", type=Path, required=True,
                        help="Path to Zao remote-endpoint log")
    parser.add_argument("--since-iso", type=str, required=True,
                        help="ISO-8601 lower bound for events to audit")
    parser.add_argument("--out", type=Path, required=True,
                        help="Output JSON report path")
    args = parser.parse_args(argv)
    # ... audit logic ...
    return 0  # or 1 on violations
```

**Events reader to import** (already exists; `cli/ctl/history.py:78-101`):
```python
from spark_modem.cli.ctl.history import read_events_with_rotated_siblings
events = list(read_events_with_rotated_siblings(args.events))
```

**Zao parser to import** (already exists; `zao_log/parser.py`):
```python
from spark_modem.zao_log.parser import ZaoLogParser
# ZaoLogParser._parse_bytes() returns a ZaoSnapshot for a given byte range;
# call backward-from-EOF for each ActionPlanned event to get the snapshot
# that was authoritative at that cycle's wallclock.
```

**Cross-join logic** (RESEARCH § Q5):
- For each `ActionPlanned` event, locate the contemporaneous `ZaoSnapshot`
  (binary-search backward in the Zao log for the latest RASCOW_STAT block with
  `block_ts <= event.ts_iso`).
- Resolve `event.usb_path` → `descriptor.line` (need an inventory map; for
  Phase 5 the simplest path is to read the line from a contemporaneous state
  file or assume the events.jsonl `line` field — verify in planning).
- If `snapshot.is_line_active(line)` is True → record violation.

**Anti-pattern to AVOID:** `try/except/pass` on a malformed JSONL line. The
established convention (`cli/ctl/history.py:95-101`) skips corrupt lines
silently but `tools/audit_*` should additionally count + surface the skip
count in the JSON report.

---

### `tools/audit_soak_exhausted.py` (NEW) — S-01 #3 detector

**Analog (file shape):** `tools/pull_replay_traces.py` (same as audit_soak_zao)
**Analog (policy import safety):** `src/spark_modem/policy/engine.py:1-23` (the docstring documents the cycle ordering this detector replays)
**Analog (match on ModemState):** `src/spark_modem/policy/transitions.py:42-100`

**Cycle-ordering pattern to replay** (verbatim from `policy/engine.py:7-17`):
```
1. transition(prior, snap) -> new_state shape
2. healthy_streak: if state == "healthy" then prior + 1 else 0
3. decay-check: if streak >= K then counters = {} and streak = 0
4. select_top_priority_issue(snap.issues) -> issue
5. lookup_action(issue.category, issue.detail) -> ActionKind|skip|None
6. gates -> PlannedAction (sets suppressed_* flags)
7. counter bump: only if action passes all gates and is not dry-run
8. record StateTransition if state changed
```

**Import-clean policy modules** (verified at `policy/engine.py:1-5`):
```python
# CLAUDE.md §1 invariant: `import` lines below MUST NOT include subprocess,
# httpx, os, asyncio, or anything that touches the kernel/network. The
# package-level lint gate (`scripts/lint_no_subprocess.sh`) enforces this.
```

The audit tool can safely:
```python
from spark_modem.policy.transitions import transition
from spark_modem.policy.gates import gate_exhausted
from spark_modem.policy.engine import run_cycle  # if full replay needed
from spark_modem.wire.state import ModemState
from spark_modem.wire.enums import IssueCategory, IssueDetail
```

**`match` not `if/elif` on `ModemState`** — copy this pattern from `transitions.py:69-100`:
```python
match prior.state:
    case "unknown":
        ...
    case "healthy":
        ...
    case "degraded":
        ...
    case "recovering":
        ...
    case "exhausted":
        ...
```
RESEARCH § Pitfalls: any branch on `ModemState.state` in audit code MUST use
`match`, not `if/elif`. CLAUDE.md anti-pattern.

**Heuristic** (RESEARCH § Q6):
- Walk backward from each `StateTransition(new_state='exhausted')` event.
- If the modem had ≥K consecutive healthy cycles in the lookback window AND
  counters were not reset → BUG (ADR-0006 amendment regression; M4 violation).
- Edge case: hardware error (`enumeration_overcurrent`, `enumeration_address_fail`)
  immediately preceding exhausted → classify `explained`.

---

### `tests/unit/qmi/test_wrapper_dms_get_revision.py` (NEW)

**Analog:** `tests/unit/qmi/test_wrapper.py:36-128` (parametrized table of query methods + the `_QUERY_METHODS` list)

**Pattern to copy** (`test_wrapper.py:36-72`) — the parametrized methods table:
```python
_QUERY_METHODS: list[tuple[str, Callable[[QmiWrapper], Awaitable[CompletedProcess]], list[str]]] = [
    (
        "nas_get_signal_info",
        lambda w: w.nas_get_signal_info(),
        ["--nas-get-signal-info"],
    ),
    # ... 6 more entries ...
]
```

For Phase 5, either:
1. Extend `test_wrapper.py:_QUERY_METHODS` with the new `dms_get_revision` entry
   (preferred — single source of truth for proxy/device-arg invariants), and
2. Add a focused parser-+-wrapper test in `test_wrapper_dms_get_revision.py`.

**Per-test pattern** (`test_wrapper.py:107-128`):
```python
async def test_every_call_uses_device_open_proxy(...) -> None:
    runner = FakeRunner()
    expected_argv = ["qmicli", "--device-open-proxy", f"--device={_DEVICE}", *argv_suffix]
    runner.register(expected_argv, _ok(expected_argv))

    wrapper = QmiWrapper(runner=runner, device=_DEVICE)
    result = await invoke(wrapper)
    assert result.succeeded

    assert recorded.count("--device-open-proxy") == 1, recorded
```

---

### `tests/unit/qmi/test_version.py` (NEW)

**Analog:** `tests/unit/daemon/test_preflight.py:21-68` (monkeypatch `subproc_runner.run`)

**Pattern to copy** (`test_preflight.py:21-50`):
```python
async def test_qmicli_missing_raises_preflight_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run(argv: list[str], *, timeout_s: float, **_kw: object) -> object:
        del timeout_s
        if argv[0] == "qmicli":
            raise FileNotFoundError("qmicli not found")
        return object()

    monkeypatch.setattr(subproc_runner, "run", fake_run)
    with pytest.raises(PreflightFailed, match="qmicli"):
        await preflight_check()
```

For `test_version.py`:
- Stub `subproc_runner.run` to return a `CompletedProcess` with the libqmi
  fixture content as stdout.
- Assert `await detect_libqmi_version() == "1.30.6"`.
- Add cases: bad-format stdout → `QmiVersionDetectionFailed`; non-zero exit →
  `QmiVersionDetectionFailed`.

**Fixture data:** new files at `tests/fixtures/qmicli/version/1.30/standard.txt`
and `tests/fixtures/qmicli/version/1.32/standard.txt`. Header comment `#
libqmi_version: 1.30` matches the convention (see `tests/fixtures/qmicli/get_signal/1.30/lte_strong.txt:1`).

---

### `tests/unit/cli/test_capture_fleet_fixture.py` (NEW)

**Analog:** `tests/unit/cli/test_ctl_support_bundle.py` (full file)

**Setup pattern** (`test_ctl_support_bundle.py:23-44`) — tmp_path + injected paths:
```python
async def test_bundle_creates_tarball_at_output_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPARK_MODEM_STATE_ROOT", str(tmp_path / "fake-runtime"))
    monkeypatch.setenv("SPARK_MODEM_RUN_DIR", str(tmp_path / "fake-run"))
    state_root = _make_state_root(tmp_path)

    out = tmp_path / "out" / "test.tar.gz"
    result = await build_support_bundle(
        out_path=out,
        state_root=state_root,
        events_log_path=tmp_path / "events.jsonl",
        conf_d_path=tmp_path / "conf.d",
    )
    assert result == out
    assert out.is_file()
```

**PII-redaction round-trip pattern** (`test_ctl_support_bundle.py:53-93`):
```python
_REDACTED_RE = re.compile(r"^<redacted:[0-9a-f]{8}>$")
# ...
state_file.write_text(json.dumps({"iccid": "8997201700123456789", ...}))
# ... build ...
assert _REDACTED_RE.match(content["iccid"])
```

For capture-fleet-fixture: write a fake qmicli stdout with `ICCID: '8997...'`,
run capture, read the redacted output file, assert the ICCID was rewritten to
`<redacted:[0-9a-f]{8}>` form.

**Mocked subprocess runner** — use `FixtureRunner` from `src/spark_modem/cli/clients.py:114-211`:
```python
from spark_modem.cli.clients import FixtureRunner
runner = FixtureRunner(fixture_dir=tmp_path / "qmicli-fixtures", libqmi_version="1.30")
```

**ADR-0009 invariant test** — must assert:
```python
import re
USB_PATH_RE = re.compile(r"^\d+-\d+(\.\d+)+$")
for subdir in (out_dir / "qmi").iterdir():
    assert USB_PATH_RE.match(subdir.name), f"Expected usb_path-keyed subdir, got {subdir.name}"
```

---

### `tests/unit/daemon/test_preflight_triple.py` (NEW)

**Analog:** `tests/unit/daemon/test_preflight.py` (full file)

**Pattern to copy** — three test categories, mirroring RESEARCH Validation Architecture:

1. **Refuse-on-unknown** (mirror `test_preflight.py:21-34`):
```python
async def test_unknown_triple_raises(tmp_path, monkeypatch) -> None:
    # Empty known_fleet_dir → any local triple is unknown.
    with pytest.raises(UnknownFleetTriple, match="unknown fleet triple"):
        await preflight_check_known_fleet_triple(known_fleet_dir=tmp_path)
```

2. **Known-triple-passes** (mirror `test_preflight.py:53-68`):
```python
async def test_known_triple_passes(tmp_path, monkeypatch) -> None:
    # Populate tmp_path / "bench-jetson-01" / "triple.json"
    # with the same triple the local probe will return.
    # Monkeypatch detect_libqmi_version + QmiWrapper.dms_get_revision
    # + zao SDK probe to return matching values.
    await preflight_check_known_fleet_triple(known_fleet_dir=tmp_path)  # no raise
```

3. **`--skip-preflight` bypass** — covered at `daemon/main.py` integration level,
   not at this unit module. Cross-reference in test docstring.

---

### `tests/integration/test_daemon_preflight_triple.py` (NEW)

**Analog:** `tests/integration/test_lifecycle.py` (existing daemon-startup integration test)

**Pattern:** spawn `_production_main` with mocked `subproc_runner` + a tmp known-fleet dir; assert exit code 78 on unknown triple; assert `last-config-error` file written; assert success when triple matches.

---

### `tests/unit/tools/test_audit_soak_zao.py` (NEW) — new directory `tests/unit/tools/`

**Note:** `tests/unit/tools/` does not exist today. This is the first test file
under that path. Pattern still mirrors the rest of the suite.

**Analog (events.jsonl synthesis):** `tests/unit/cli/test_ctl_history.py:41-99`

**Synthesize events** (`test_ctl_history.py:41-67`):
```python
def _make_action_planned(*, ts_iso: str, usb_path: str) -> ActionPlanned:
    return ActionPlanned(
        ts_iso=ts_iso,
        usb_path=usb_path,
        action=ActionKind.SET_APN,
        reason="dispatcher:set_apn",
    )

# Then in the test:
events = [
    _make_action_planned(ts_iso="2026-05-06T00:00:00+00:00", usb_path="2-3.1.1"),
    ...
]
```

**Synthesize Zao log** — paint a `RASCOW_STAT` block per `tests/fixtures/zao_log/*`
shape or build a minimal one inline.

**Assertions:**
- Feed events + Zao log with `line=1 status=active` at the cycle time of an
  `ActionPlanned{usb_path="2-3.1.1", line=1}` event → tool exits 1 with 1
  violation recorded.
- Feed events + Zao log with `line=1 status=inactive` → tool exits 0.

---

### `tests/fixtures/qmicli/get_revision/<version>/<scenario>.txt` (NEW)

**Analog:** `tests/fixtures/qmicli/get_operating_mode/1.30/online.txt` (existing sibling)

**Existing fixture shape** (`tests/fixtures/qmicli/get_signal/1.30/lte_strong.txt`):
```
# libqmi_version: 1.30
[/dev/cdc-wdm0] Successfully got signal info
LTE:
	RSSI: '-65 dBm'
	RSRQ: '-9 dB'
	RSRP: '-94 dBm'
	SNR: '8.4 dB'
```

**New fixture template** (`tests/fixtures/qmicli/get_revision/1.30/standard.txt`):
```
# libqmi_version: 1.30
[/dev/cdc-wdm0] Device revisions retrieved:
	Revision: 'SWI9X30C_02.38.00.00'
	Boot code: 'SWI9X30C_02.38.00.00'
```
(Exact field names verified in planning against a real bench Jetson capture.)

**Mirror for libqmi 1.32:** same scenario file at `get_revision/1.32/standard.txt`.

---

### `tests/fixtures/fleet/<box-id>/` (NEW tree)

**Analog (layout):** `tests/fixtures/qmicli/<intent>/<version>/<scenario>.txt`

**Per-box structure** (RESEARCH § Q1 + § Q10):
```
tests/fixtures/fleet/
├── _test/                            # example committed in Phase 5 (Q10)
│   └── triple.json
├── bench-jetson-01/
│   ├── triple.json                   # {firmware, sdk, libqmi}
│   ├── qmi/
│   │   ├── 2-3.1.1/                  # ADR-0009 usb_path keying
│   │   │   ├── dms_get_revision.txt
│   │   │   ├── uim_get_card_status.txt
│   │   │   └── ...
│   │   ├── 2-3.1.2/
│   │   └── 2-3.1.3/
│   └── zao-log-sample.txt
└── box-il-13/                        # added in X-04 capture PR
    └── ...
```

**`triple.json` schema** (RESEARCH § Q1):
```json
{
  "schema_version": 1,
  "em7421_firmware": "SWI9X30C_02.38.00.00",
  "zao_sdk": "2.1.0",
  "libqmi": "1.30.6",
  "first_seen_box_id": "bench-jetson-01",
  "first_seen_iso": "2026-05-11T14:32:00Z",
  "_comment": "captured by spark-modem ctl capture-fleet-fixture; do not hand-edit"
}
```

---

### `debian/spark-modem-watchdog.install` (modify)

**Analog (file structure):** `debian/spark-modem-watchdog.install` (existing 4-line file)

**Existing content** (verbatim):
```
# NOTE: the bundled CPython tree at /opt/spark-modem-watchdog/python/ is laid
# out by override_dh_auto_install in debian/rules (PBS unpack + ensurepip + uv
# pip install + compileall). It is NOT shipped via this .install file because
# dh_install would copy a *fresh* PBS tree on top, clobbering the site-packages
# we populated.
src/spark_modem /opt/spark-modem-watchdog/lib/
scripts/postinst_smoke_test.sh /opt/spark-modem-watchdog/libexec/
debian/spark-modem-watchdog.service /lib/systemd/system/
debian/conf.d/00-carriers.yaml /etc/spark-modem-watchdog/conf.d/
```

**New line to add** (RESEARCH § Q10 final recommendation — ship the directory
tree directly under `/etc/spark-modem-watchdog/known-fleet/`):
```
tests/fixtures/fleet  /etc/spark-modem-watchdog/known-fleet/
```

**Companion edit to `debian/spark-modem-watchdog.dirs`** (matches existing
shape at `dirs:1-7`):
```
/etc/spark-modem-watchdog/known-fleet
```

**Anti-pattern to AVOID:** modifying `debian/spark-modem-watchdog.postinst` to
write into `/etc/spark-modem-watchdog/known-fleet/` at install time. RESEARCH
Q10 confirms `dh_install` (declarative copy) is the right tool; postinst is
for ModemManager masking + state dir creation, not data shipment.

---

### `.planning/phases/05-bench-field-shadow/SIGNOFF.md` (NEW)

**Analog:** no in-repo precedent — first phase-exit signoff template. Use the
verbatim shape from RESEARCH § Q8.

**Industry references** for sanity (RESEARCH § Q8): Google SRE PRR checklist,
AWS Well-Architected reliability launch-readiness review.

**Required sections** (from RESEARCH Q8):
- Header front-matter (engineer name, box IDs, soak start/end timestamps)
- S-01 exit gates table (3 rows: M6, ADR-0003, M4)
- R-02 replay-harness gate (agreement rate vs ≥0.95)
- S-01.1 informational metrics (cycle P99, RSS — NOT blocking)
- F-04 violations log (audit trail — every violation recorded, regardless of
  disposition)
- X-04 fleet fixtures captured checklist
- Free-text rationale (≤1000 words)
- Phase 6 entry approval signature

---

### `.planning/phases/05-bench-field-shadow/SOAK_RUNBOOK.md` (NEW)

**Analog (heading style + bash code-fence convention):** `docs/RUNBOOK.md:1-80`

**Front-matter shape** (`RUNBOOK.md:1-14`):
```markdown
# Runbook — spark-modem-watchdog v2

| Field         | Value                  |
| ------------- | ---------------------- |
| Status        | Draft                  |
| Owner         | TBD (modem platform)   |
| Audience      | Site technicians, NOC, on-call engineers |
| Last updated  | 2026-05-06             |
```

**Bash-block convention** (`RUNBOOK.md:18-29`):
```markdown
## 1. First install

\`\`\`bash
# 1) Copy the .deb to the box
scp spark-modem-watchdog_2.0.0_arm64.deb nvidia@<jetson>:/tmp/
\`\`\`
```

**Required content** (from RESEARCH § Q9):
- Daily operator checks (journalctl, status JSON, Prom UDS via curl, state scan)
- Soak-exit procedure (run `tools/audit_soak_zao.py`, `tools/audit_soak_exhausted.py`,
  `pytest tests/replay/`, then commit SIGNOFF + JSONs)
- F-04 violation disposition workflow

**Anti-pattern to AVOID:** referencing `spark-modem ctl config-check` (RESEARCH §
Pitfalls): the command is referenced by the systemd unit but does NOT exist in
`src/spark_modem/cli/` today. Either omit, or flag the gap explicitly.

**Prom metric query convention** — RESEARCH § Pitfalls + ADR-0013:
```bash
# CORRECT (cardinality-safe integer-encoded):
curl -s --unix-socket /run/spark-modem-watchdog/metrics.sock http://localhost/metrics \
  | grep -E 'modem_state_value\{modem="[^"]+"\}'

# WRONG (one-hot state label — ADR-0013 anti-pattern):
# curl ... | grep 'modem_state{state="exhausted"}'
```

---

### `docs/RUNBOOK.md` (modify — 1-line cross-reference)

**Existing front-matter** (lines 1-14) is the modification anchor.

Add one line near the top (or in a new "Lifecycle" section):
```markdown
For Phase 5 bench/field soak operations, see
`.planning/phases/05-bench-field-shadow/SOAK_RUNBOOK.md`.
```

RESEARCH § Q9: this is a **1-line cross-reference**, not a doc rewrite. The full
ROADMAP / MIGRATION rewording is OUT OF SCOPE (CONTEXT § Deferred — flagged
for Phase 7 or doc-fixup phase).

---

## Shared Patterns

### Subprocess Discipline (SP-04 lint gate)

**Source:** `src/spark_modem/qmi/wrapper.py:23-24` (the import precedent)
**Source:** `src/spark_modem/subproc/runner.py:108-196` (the SOLE entry point)
**Apply to:** ALL new code under `src/spark_modem/` (capture_fleet_fixture, qmi/version.py, qmi/wrapper.py addition, daemon/preflight_triple.py)

Every subprocess invocation in new `src/spark_modem/` code:
```python
from spark_modem.subproc import runner as subproc_runner
# ...
cp = await subproc_runner.run([binary, *args], timeout_s=...)
```

**SP-04 exemption for `tools/`** (`tools/pull_replay_traces.py:18-21`):
```python
"""...
## Subprocess discipline

This is a ``tools/`` script (NOT under ``src/spark_modem/``); SP-04 lint
scope excludes anything outside ``src/`` (see
``scripts/lint_no_subprocess.sh:11``). Direct ``subprocess.run`` is
acceptable here.
"""
```
Apply this docstring block to both `tools/audit_soak_zao.py` and
`tools/audit_soak_exhausted.py` so future readers know they're SP-04 exempt.

### PII Redaction (sha256[:8] form)

**Source:** `src/spark_modem/cli/redact.py:19-28`
**Apply to:** capture-fleet-fixture per-modem qmicli stdout (ICCID, IMSI, IP)

```python
def redact_pii(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"<redacted:{digest}>"
```

**Per-field application** — extend the `redact_iccid_imsi_in_dict` shape to also
cover the raw qmicli stdout pattern (regex-replace `'ICCID': '<value>'` and
`'IMSI': '<value>'` lines with the redacted form). Recommend a new helper
`redact_pii_from_raw_qmicli(stdout: bytes) -> bytes` colocated in `cli/redact.py`
or `cli/ctl/capture_fleet_fixture.py`.

**Test assertion** — all PII-handling tests use:
```python
_REDACTED_RE = re.compile(r"^<redacted:[0-9a-f]{8}>$")
```

### Atomic File Writes

**Source:** `src/spark_modem/state_store/atomic.py:32-60` (`atomic_write_bytes`)
**Apply to:** ANY state file the daemon writes. Phase 5 specifically: **NOT
needed** for known-fleet index (dpkg-managed) per RESEARCH Q10. Reserve as
fallback.

```python
from spark_modem.state_store.atomic import atomic_write_bytes
atomic_write_bytes(target, data)  # temp + fsync + rename + dir fsync
```

### ADR-0009 usb_path Keying

**Source:** `src/spark_modem/inventory/descriptor.py:18-22`, `state/by-usb/<usb_path>.json`
**Apply to:** all new per-modem subdirs and tests

```python
modem_dir = qmi_dir / descriptor.usb_path  # "2-3.1.1", NOT "cdc-wdm0"
```

Test assertion (lift from `tests/unit/cli/test_ctl_history.py` style):
```python
USB_PATH_RE = re.compile(r"^\d+-\d+(\.\d+)+$")
```

### Preflight + last-config-error Contract

**Source:** `src/spark_modem/daemon/preflight.py:60-75` (the marker writer)
**Apply to:** `preflight_check_known_fleet_triple` failure path

```python
from spark_modem.state_store.atomic import atomic_write_bytes
target = run_dir / "last-config-error"
target.parent.mkdir(parents=True, exist_ok=True)
atomic_write_bytes(target, message.encode("utf-8"))
```

**Exit code contract:** 78 (`EX_CONFIG` from `sysexits.h`) — matches existing
preflight failure path at `daemon/main.py:215`.

### `match` not `if/elif` on `ModemState`

**Source:** `src/spark_modem/policy/transitions.py:69-100` (the canonical pattern)
**Apply to:** `tools/audit_soak_exhausted.py` (and any other place new code
branches on `ModemState.state`)

```python
match prior.state:
    case "unknown":
        ...
    case "healthy":
        ...
    case "degraded":
        ...
    case "recovering":
        ...
    case "exhausted":
        ...
```

CLAUDE.md anti-pattern catalogue forbids `if/elif` on `ModemState`.

### Integer-Encoded Prometheus `modem_state_value{modem}`

**Source:** ADR-0013
**Apply to:** SOAK_RUNBOOK.md Prom-query examples

```bash
# CORRECT:
curl ... | grep 'modem_state_value{modem="2-3.1.1"} == 4'

# WRONG (one-hot label — ADR-0013 anti-pattern):
# curl ... | grep 'modem_state{state="exhausted"}'
```

### Pydantic Wire Types

**Source:** `src/spark_modem/qmi/parsers/get_operating_mode.py:30-32`
**Apply to:** `GetRevisionResult` (new parser) and any new wire model

```python
class GetRevisionResult(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    revision: str | None = None
```

---

## Anti-Patterns to AVOID (from CLAUDE.md + RESEARCH § Pitfalls)

| Anti-pattern | Where it could sneak in | Mitigation |
|--------------|-------------------------|------------|
| `subprocess.run` sync outside `tools/`/`tests/` | `cli/ctl/capture_fleet_fixture.py` (engineer thinks "it's a one-shot, not the daemon") | Always `await subproc_runner.run(...)`; SP-04 lint catches. |
| `create_subprocess_exec` outside `src/spark_modem/subproc/` | Same as above | Same. |
| `cdc-wdmN`-keyed fixture/state | `tests/fixtures/fleet/<box-id>/qmi/<key>/` | Test asserts `re.match(r"^\d+-\d+(\.\d+)+$", subdir.name)`. |
| One-hot Prometheus `state` label | SOAK_RUNBOOK.md query examples | Use `modem_state_value{modem="..."} == N` (ADR-0013). |
| Blocking read on `/dev/kmsg` | Phase 5 has zero kmsg surface | Don't add it. |
| `if/elif` on `ModemState` | `tools/audit_soak_exhausted.py` | Use `match modem_state.state:` (transitions.py:69-100 precedent). |
| `try/except/pass` on JSONL parse failures | Both audit tools | Skip + COUNT corrupt lines; surface count in report (history.py:95-101 precedent). |
| `gather(return_exceptions=True)` | Capture-fleet-fixture multi-modem fan-out | Use `asyncio.TaskGroup` + `asyncio.timeout` (CLAUDE.md anti-pattern catalogue). |
| Daemon writing to `/etc/spark-modem-watchdog/known-fleet/` | Could regress via "let's cache the resolved triple" optimization | Daemon is read-only; files are dpkg-managed. |
| `MonitorObserver` for udev | Phase 5 has zero udev surface | Don't add it. |
| Re-implementing redaction | capture-fleet-fixture per-file scrub | Reuse `cli/redact.py:redact_pii`. |
| `spark-modem ctl config-check` reference | SOAK_RUNBOOK.md operator commands | Command is referenced by systemd unit but does NOT exist; omit or flag. |
| `tools/compare_v1_v2.py` reference | Anywhere | Explicitly NOT built (CONTEXT scope_pivot). |
| `99-shadow.yaml` / `-v2`-suffixed paths | Anywhere | v2 runs at canonical paths from day 1 (CONTEXT scope_pivot). |
| Field-side synthetic fault injection | `tests/field/fault_inject.py` or field-box cron | F-01 explicitly prohibits. |

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `.planning/phases/05-bench-field-shadow/SIGNOFF.md` | operator doc / phase-exit checklist | n/a | First phase-exit signoff template in this repo. Structure from RESEARCH § Q8 (industry PRR pattern). |
| `tests/fixtures/fleet/<box-id>/` | data tree | data | New root tree under `tests/fixtures/`. Layout mirrors `tests/fixtures/qmicli/<intent>/<version>/<scenario>.txt` shape (RESEARCH "Established Patterns") under a new parent. |
| `tests/unit/tools/` directory | test root | n/a | No existing tests under `tests/unit/tools/`. New directory; test file structure mirrors `tests/unit/cli/`. |

For SIGNOFF.md: planner copies the markdown template verbatim from RESEARCH § Q8.

For the fleet fixture tree: planner uses the per-libqmi tree at
`tests/fixtures/qmicli/<intent>/<version>/<scenario>.txt` as the layout model;
substitute `<box-id>` for `<intent>`, `<usb_path>` for `<version>`, and
`<verb>.txt` for `<scenario>.txt`.

---

## Metadata

**Analog search scope:**
- `src/spark_modem/cli/`, `src/spark_modem/cli/ctl/`, `src/spark_modem/qmi/`,
  `src/spark_modem/qmi/parsers/`, `src/spark_modem/daemon/`, `src/spark_modem/policy/`,
  `src/spark_modem/state_store/`, `src/spark_modem/zao_log/`, `src/spark_modem/subproc/`,
  `src/spark_modem/inventory/`
- `tests/unit/cli/`, `tests/unit/daemon/`, `tests/unit/qmi/`, `tests/integration/`,
  `tests/fixtures/qmicli/`
- `tools/` (3 existing scripts)
- `debian/` (4 packaging files)
- `docs/RUNBOOK.md` (operator-doc heading style)

**Files scanned:** 32 production / test / packaging files read in full or in
targeted ranges; 12 directory listings via Glob; 4 targeted Greps.

**Pattern extraction date:** 2026-05-11

---

## PATTERN MAPPING COMPLETE

**Phase:** 5 — Bench & Field Shadow

**Files classified:** 17 unique creation/modification targets (8 source + 8 test
+ 1 packaging + 3 doc + ancillary fixture trees).

**Analogs found:** 17 / 17. Every new file has at least a role-match analog in
the existing codebase; 12 are exact-match (same dir, same shape).

### Coverage
- Files with exact analog: 12
- Files with role-match analog: 5
- Files with no in-repo analog: 1 (`SIGNOFF.md` — first phase-exit template;
  structure from RESEARCH Q8)

### Key Patterns Identified
- **CLI verbs** under `cli/ctl/` follow `support_bundle.py`: file docstring →
  imports → injected-path builder function → `async def run(args) -> int`
  dispatcher → register in `cli/main.py` `ctl_sub.add_parser(...)` block.
- **QmiWrapper methods** are uniform: `await self._runner.run(self._argv([...]), timeout_s=_DEFAULT_TIMEOUT_S)`;
  query methods do NOT set `_in_critical_section`; state-changers wrap in `try/finally`.
- **Parsers** under `qmi/parsers/` are pure functions: `strip_header → regex → pydantic BaseModel(frozen=True) | QmiError`.
- **Preflight checks** raise `PreflightFailed`-shaped exceptions; daemon
  main.py catches → `write_last_config_error` → returns exit code 78. Boot
  classifier reads marker on next boot.
- **`tools/` scripts** are SP-04-exempt; can use `subprocess` directly but
  shouldn't unless needed. Argparse + `main(argv) -> int` + exit-code
  convention (0/1/2).
- **PII redaction** is sha256[:8]-hashed at point of write; same input always
  yields the same `<redacted:<8hex>>` for cross-file correlation.
- **ADR-0009 usb_path keying** is universal: every per-modem path uses
  `usb_path` (e.g. `2-3.1.1`), never `cdc-wdmN`.
- **Atomic writes** via `state_store/atomic.py:atomic_write_bytes`; not needed
  in Phase 5 because the known-fleet index is dpkg-managed.

### File Created
`S:\spark\modem-watchdog\.planning\phases\05-bench-field-shadow\05-PATTERNS.md`

### Ready for Planning
Pattern mapping is complete. The planner can now reference exact analog files
and excerpts in PLAN.md action blocks; every new file has a copy-from target
named with a file:line citation, and every shared concern (subprocess,
redaction, atomic writes, usb_path keying, `match` on state) is cross-cut to
the canonical source.
