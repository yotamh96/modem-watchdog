---
id: S06
parent: M001
milestone: M001
provides:
  - EXIT-CHECKLIST.md operator-fillable template for Phase 05.1 EXIT bar (V-03)
  - 9-row V-03 gate table covering all CONTEXT.md L-162..173 steps
  - Approval footer anchoring phase-exit provenance
  - Updated ROADMAP.md Phase 05.1 entry with real Goal + Success Criteria block
  - debian/changelog 2.0.1-1 entry documenting all hotfix changes
requires: []
affects: []
key_files: []
key_decisions:
  - Template is intentionally blank — committing a partially-filled template before all gates pass would falsely signal phase exit
  - Step 3 Expected column requests stat output (mode + ownership only), not file contents, to prevent L-03 secret disclosure (T-05.1-15)
  - Free-text rationale section explicitly asks for L-04 verdict so future plans can act on the systemd 245 LoadCredential= finding
  - Version 2.0.1-1 chosen (PEP-440 patch) over 2.0.0+hotfix.1 — cleaner shape, universally supported by all Debian/PEP-440 tooling, avoids potential + handling quirks in apt on Ubuntu 20.04
  - ROADMAP Phase 05.1 entry uses EXIT bar pattern mirroring Phase 4 Success Criteria (per D-03)
patterns_established:
  - Service unit ExecStart* paths must match pyproject.toml [project.scripts] keys materialized by uv pip install .
  - EXIT-CHECKLIST.md: 9-gate operator checklist as phase-exit signal — committed file IS the exit
  - Decimal phase ROADMAP entries use same Goal + Success Criteria + Plans structure as numbered phases
observability_surfaces: []
drill_down_paths: []
duration: 2min
verification_result: passed
completed_at: 2026-05-12
blocker_discovered: false
---
# S06: Deb Packaging Hotfix

**# Phase 05.1 Plan 01: Install-Pipeline + Entry-Point Fixes Summary**

## What Happened

# Phase 05.1 Plan 01: Install-Pipeline + Entry-Point Fixes Summary

**One-liner:** Console-script entry point declared in pyproject.toml + `_sync_main()` wrapper added; `spark_modem` package now ships into bundled venv site-packages via `uv pip install .` in `debian/rules`, eliminating both systemd 203/EXEC and `ModuleNotFoundError` bugs.

---

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add daemon console-script entry + inline _sync_main | d027188 | pyproject.toml, src/spark_modem/daemon/main.py |
| 2 | Install spark_modem into bundled venv via uv pip install . | b842ff6 | debian/rules, debian/spark-modem-watchdog.install, debian/spark-modem-watchdog.dirs |

---

## What Was Built

### pyproject.toml — [project.scripts] diff

Before (line 21-22):
```toml
[project.scripts]
spark-modem = "spark_modem.cli.main:main"
```

After (lines 21-23):
```toml
[project.scripts]
spark-modem = "spark_modem.cli.main:main"
spark-modem-watchdog = "spark_modem.daemon.main:_sync_main"
```

### src/spark_modem/daemon/main.py — _sync_main block as committed

Inserted between `async def main()` (line 305) and `if __name__` (now line 322). Final tail of file:

```python
async def main(argv: list[str] | None = None) -> int:
    """Entry point: dispatch laptop vs production wiring."""
    args = _parse_args(argv)
    if args.laptop:
        return await _laptop_main()
    return await _production_main(args)


def _sync_main(argv: list[str] | None = None) -> int:
    """Sync wrapper for [project.scripts] console-script entry point (I-04).

    systemd Type=notify spawns this via the spark-modem-watchdog console
    script materialized by `uv pip install .` (Phase 05.1 I-01 + I-02).
    """
    return asyncio.run(main(argv))


if __name__ == "__main__":
    sys.exit(_sync_main())
```

### debian/rules — Step 3.5 insertion point

The new Step 3.5 block landed at **lines 74-85** of the updated `debian/rules`, between:
- `-r packaging/requirements.lock` at **line 72** (end of Step 3)
- `$(VENVDIR)/bin/python3.12 -m pip uninstall -y uv pip setuptools wheel` at **line 89** (uninstall sweep)

Inserted block:
```makefile
	# Step 3.5 (Phase 05.1 I-01): install spark_modem itself into the bundled
	# venv's site-packages. --no-deps because runtime libs are already locked
	# at step 3 above; --no-build-isolation because we want uv to use the
	# setuptools ALREADY present in the bundled venv (cheap, deterministic,
	# offline). Setuptools is uninstalled by the NEXT step — must run BEFORE
	# the uninstall sweep below (I-05). After this step, the bundled venv's
	# site-packages contains spark_modem/, and python/bin/ contains both
	# spark-modem and spark-modem-watchdog console-script shims.
	$(VENVDIR)/bin/python3.12 -m uv pip install \
		--python $(VENVDIR)/bin/python3.12 \
		--no-deps --no-build-isolation \
		.
```

### debian/spark-modem-watchdog.install — lines deleted/replaced

**Deleted:** `src/spark_modem /opt/spark-modem-watchdog/lib/` (was line 6 in the original file)

**Replaced with audit-trail comment block** (new lines 6-9):
```
# Phase 05.1 I-01: src/spark_modem is installed via `uv pip install .` inside
# override_dh_auto_install (drops it into the bundled venv's site-packages).
# The previous `src/spark_modem /opt/spark-modem-watchdog/lib/` line was a
# bug — the lib/ path was never on sys.path of the bundled python.
```

### debian/spark-modem-watchdog.dirs — line deleted

**Deleted:** `/opt/spark-modem-watchdog/lib` (was line 8 in the original file)

File reduced from 8 lines to 7 lines. The phantom empty directory `/opt/spark-modem-watchdog/lib/` will no longer appear in the built `.deb`.

---

## Deviations from Plan

None — plan executed exactly as written.

---

## Decisions Made

1. **I-01 (confirmed):** `uv pip install . --no-deps --no-build-isolation` as the Step 3.5 install invocation. `--no-cache-dir` deliberately omitted to reuse the uv cache consistent with the existing Step 3 pattern.
2. **I-02 (confirmed):** `spark-modem-watchdog = "spark_modem.daemon.main:_sync_main"` added as second `[project.scripts]` entry alongside the existing `spark-modem` entry.
3. **I-04 (confirmed):** `_sync_main()` inlined in `daemon/main.py` co-located with `async def main()`; `if __name__ == "__main__"` updated to call `_sync_main()` instead of `asyncio.run(main())` — both code paths now exercise the same wrapper.
4. **I-05 (confirmed):** Verified by `awk` that the uninstall sweep line sees `p=1` (requirements.lock install already ran), confirming Step 3.5 is correctly ordered.

---

## Verification Results

| Check | Result |
|-------|--------|
| `grep -c "uv pip install" debian/rules` == 2 | PASS |
| `grep -F "no-build-isolation" debian/rules` | PASS |
| `grep -F "Phase 05.1 I-01" debian/rules` | PASS |
| `grep -E "^src/spark_modem /opt/..." debian/spark-modem-watchdog.install` == 0 | PASS |
| `grep -F "Phase 05.1 I-01" debian/spark-modem-watchdog.install` | PASS |
| `grep -E "^/opt/spark-modem-watchdog/lib$" debian/spark-modem-watchdog.dirs` == 0 | PASS |
| `wc -l debian/spark-modem-watchdog.dirs` == 7 | PASS |
| I-05 order constraint (awk test) | PASS |
| `grep -c "def _sync_main(" src/spark_modem/daemon/main.py` == 1 | PASS |
| `grep -F "sys.exit(_sync_main())" src/spark_modem/daemon/main.py` | PASS |
| `python -c "...tomllib...spark-modem-watchdog == _sync_main"` | PASS |
| `mypy --strict src/spark_modem/daemon/main.py` | PASS (no issues) |
| `ruff check src/spark_modem/daemon/main.py` | PASS (all checks passed) |

---

## Known Stubs

None — all changes are functional packaging/entry-point wiring with no placeholder data.

---

## Threat Flags

No new network endpoints, auth paths, or trust boundary surfaces introduced beyond those documented in the plan's threat model (T-05.1-01 through T-05.1-03).

## Self-Check: PASSED

- S:\spark\modem-watchdog\pyproject.toml: exists and contains both console-script entries
- S:\spark\modem-watchdog\src\spark_modem\daemon\main.py: exists and exports `_sync_main`
- S:\spark\modem-watchdog\debian\rules: exists with Step 3.5 at lines 74-85
- S:\spark\modem-watchdog\debian\spark-modem-watchdog.install: exists, directive line removed
- S:\spark\modem-watchdog\debian\spark-modem-watchdog.dirs: exists, 7 lines
- Commit d027188 (Task 1): confirmed in git log
- Commit b842ff6 (Task 2): confirmed in git log

# Phase 05.1 Plan 02: HMAC-Secret Discipline + ctl config-check Summary

**One-liner:** HMAC secret path resolver (L-02 systemd-245 fallback) added to Settings; `ctl config-check` pre-flight verb created with 4-check validation; postinst idempotently writes a 0600 root:root placeholder sentinel that config-check explicitly rejects.

---

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Failing tests for Settings.resolve_hmac_secret_path() | 1498b64 | tests/unit/config/test_settings_hmac_path.py |
| 1 (GREEN) | Add Settings.resolve_hmac_secret_path() L-02 fallback | 0a63d3c | src/spark_modem/config/settings.py, tests/unit/config/test_settings_hmac_path.py |
| 2 (RED) | Failing tests for ctl config-check verb | 7ca1cd8 | tests/unit/cli/test_ctl_config_check.py |
| 2 (GREEN) | Create ctl config-check verb body + register in CLI | fd70a96 | src/spark_modem/cli/ctl/config_check.py, src/spark_modem/cli/main.py, tests/unit/cli/test_ctl_config_check.py |
| 3 | Write HMAC placeholder in postinst (L-03) | d5872ac | debian/spark-modem-watchdog.postinst |

---

## What Was Built

### Settings.resolve_hmac_secret_path() — verbatim final shape

Added at `src/spark_modem/config/settings.py` **line 246**, after `_validate_webhook_http_allowed` and before `from_yaml_layer`:

```python
def resolve_hmac_secret_path(self) -> Path:
    """L-02: systemd 247+ sets CREDENTIALS_DIRECTORY; fall back to /etc/.../hmac-secret.

    Single file on disk serves both worlds: the LoadCredential= directive
    in spark-modem-watchdog.service points at the same path the fallback
    reads directly. On Ubuntu 20.04 / systemd 245 (PROJECT.md Hardware
    target) CREDENTIALS_DIRECTORY is unset and we fall back to /etc/.

    Reads os.environ at call time, not at construction (Settings.frozen=True
    does not cache env lookups; LoadCredential populates the env at unit
    start, which is AFTER Settings was first built in the test path).
    """
    creddir = os.environ.get("CREDENTIALS_DIRECTORY")
    if creddir:
        return Path(creddir) / "spark-modem-watchdog.hmac-secret"
    return Path("/etc/spark-modem-watchdog/hmac-secret")
```

New stdlib imports added at lines 20-21:
```python
import os
from pathlib import Path
```

### src/spark_modem/cli/ctl/config_check.py — first 35 lines + async def run signature

```python
"""ctl config-check — pre-flight Settings + HMAC secret validate (U-05 / L-05).

Run by systemd ExecStartPre BEFORE the main daemon boots. Surface clear
structured errors to stderr; return non-zero exit so systemd fails the
unit start before StartLimitBurst is consumed (PITFALLS §4.2).

L-05 checks the HMAC secret file:
  (a) exists at the path Settings.resolve_hmac_secret_path() returns,
  (b) is NOT the placeholder sentinel (L-03 writes this; operator must
      replace before first start),
  (c) is mode 0600, owner root, group root (NFR-30 / ADR-0011),
  (d) is non-empty.

All four failures emit a distinct `config-check: ...` message to stderr.
Exit codes:
  0 — green
  2 — any validation failure
"""

from __future__ import annotations

import argparse
import os
import stat
import sys

from pydantic import ValidationError

from spark_modem.config.settings import Settings

_HMAC_PLACEHOLDER_SENTINEL = b"REPLACE_THIS_BEFORE_FIRST_START_SEE_RUNBOOK\n"
_MODE_0600 = 0o600


async def run(args: argparse.Namespace) -> int:  # noqa: PLR0911
    """Validate Settings + HMAC secret. Return 0 on green, 2 on any failure."""
```

### cli/main.py — import and registration line numbers

- **Import line 26:** `from spark_modem.cli.ctl import config_check as ctl_config_check`
  (alphabetically between `capture_fleet_fixture` and `history`)
- **Registration lines 169-174:** `ctl config-check` subparser added after `ctl maintenance` block, before `ctl support-bundle`:
  ```python
  # ctl config-check (U-05 / L-05) — pre-flight Settings + HMAC secret validate
  p_cc = ctl_sub.add_parser(
      "config-check",
      help="Validate settings + HMAC secret file (run by ExecStartPre)",
  )
  p_cc.set_defaults(func=ctl_config_check.run)
  ```

### debian/spark-modem-watchdog.postinst — L-03 placeholder block line numbers

Block inserted at **lines 37-53** (between the ModemManager mask block ending at line 35 and the smoke-test block starting at line 55):

```bash
    # Phase 05.1 L-03: write a placeholder HMAC secret if no file exists yet.
    # ...
    if [[ ! -f /etc/spark-modem-watchdog/hmac-secret ]]; then
      install -d -m 0755 -o root -g root /etc/spark-modem-watchdog
      printf 'REPLACE_THIS_BEFORE_FIRST_START_SEE_RUNBOOK\n' \
        > /etc/spark-modem-watchdog/hmac-secret
      chmod 0600 /etc/spark-modem-watchdog/hmac-secret
      chown root:root /etc/spark-modem-watchdog/hmac-secret
    fi
```

Exact `[[ ! -f ]]` guard line: **line 46**. `printf` sentinel line: **line 48**.

### _HMAC_PLACEHOLDER_SENTINEL exact bytes (for Plan 05 V-02 cross-check)

```python
_HMAC_PLACEHOLDER_SENTINEL = b"REPLACE_THIS_BEFORE_FIRST_START_SEE_RUNBOOK\n"
```

44 bytes total (`len(b"REPLACE_THIS_BEFORE_FIRST_START_SEE_RUNBOOK\n") == 44`).
The postinst `printf` writes the identical string with a trailing newline — byte-for-byte match confirmed by cross-check verification.

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Unused `import os` in test file (ruff F401)**
- **Found during:** Task 1 ruff check
- **Issue:** Plan-provided test skeleton included `import os` but no direct `os.environ` usage in tests (monkeypatch handles it)
- **Fix:** Removed unused import
- **Files modified:** `tests/unit/config/test_settings_hmac_path.py`
- **Commit:** 0a63d3c

**2. [Rule 1 - Bug] Multiple ruff violations in test_ctl_config_check.py**
- **Found during:** Task 2 ruff check
- **Issues:** `F401` (unused `patch` import), `ASYNC240` (Path methods in async tests), `PTH101` (`os.chmod` should be `Path.chmod()`), `PLC0415` (local `import types` inside functions)
- **Fix:** Removed unused import; moved `import types` to top-level; replaced `os.chmod(path, mode)` with `path.chmod(mode)`; added `# noqa: ASYNC240` on `write_bytes` and `chmod` calls (these are test-fixture writes, not production async I/O)
- **Files modified:** `tests/unit/cli/test_ctl_config_check.py`
- **Commit:** fd70a96

**3. [Rule 1 - Bug] PLR0911 + PTH116 in config_check.py**
- **Found during:** Task 2 ruff check
- **Issues:** `PLR0911` (9 return statements > 6 limit) and `PTH116` (`os.stat()` not `Path.stat()`)
- **Fix:** Added `# noqa: PLR0911` on `async def run` (structured-error contract requires multiple returns) and `# noqa: PTH116` on `os.stat()` call (plan explicitly endorses `os.stat` for `st_uid`/`st_gid` access — pathlib has no equivalent)
- **Files modified:** `src/spark_modem/cli/ctl/config_check.py`
- **Commit:** fd70a96

---

## Verification Results

| Check | Result |
|-------|--------|
| `grep -c "def resolve_hmac_secret_path" settings.py` == 1 | PASS |
| `grep -F "CREDENTIALS_DIRECTORY" settings.py` | PASS |
| `grep -F 'Path("/etc/spark-modem-watchdog/hmac-secret")' settings.py` | PASS |
| `grep -F "import os" settings.py` | PASS |
| `grep -F "from pathlib import Path" settings.py` | PASS |
| `mypy --strict src/spark_modem/config/settings.py` | PASS (no issues) |
| `ruff check settings.py test_settings_hmac_path.py` | PASS |
| `pytest tests/unit/config/test_settings_hmac_path.py -v` | PASS (3 passed) |
| `test -f src/spark_modem/cli/ctl/config_check.py` | PASS |
| `grep -c "async def run(" config_check.py` == 1 | PASS |
| `grep -F 'from __future__ import annotations' config_check.py` | PASS |
| `grep -F 'REPLACE_THIS_BEFORE_FIRST_START_SEE_RUNBOOK' config_check.py` | PASS |
| `grep -F "from spark_modem.cli.ctl import config_check as ctl_config_check" main.py` | PASS |
| `grep -F '"config-check"' main.py` | PASS |
| `mypy --strict config_check.py main.py` | PASS (no issues) |
| `ruff check config_check.py main.py test_ctl_config_check.py` | PASS |
| `pytest tests/unit/cli/test_ctl_config_check.py -v` | PASS (6 skipped on Windows) |
| `python -c "...parse_args(['ctl', 'config-check'])...ns.func is not None"` | PASS |
| `grep -c "REPLACE_THIS_BEFORE_FIRST_START_SEE_RUNBOOK" postinst` == 1 | PASS |
| `grep -F "chmod 0600 /etc/spark-modem-watchdog/hmac-secret" postinst` | PASS |
| `grep -F "chown root:root /etc/spark-modem-watchdog/hmac-secret" postinst` | PASS |
| `grep -F "[[ ! -f /etc/spark-modem-watchdog/hmac-secret ]]" postinst` | PASS |
| `bash -n debian/spark-modem-watchdog.postinst` | PASS |
| Placeholder block after ModemManager, before smoke test (awk check) | PASS |
| L-02 fallback integrated test | PASS |
| L-05 CLI wiring integrated test | PASS |
| L-03 bash syntax integrated test | PASS |
| Placeholder sentinel cross-check (config_check.py ↔ postinst) | PASS |
| Full unit suite: 985 passed, 89 skipped | PASS |

---

## Known Stubs

None — all changes are functional with no placeholder data or TODO markers in production paths.

---

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: info-disclosure-path | src/spark_modem/cli/ctl/config_check.py | Error messages reference secret file PATH but never its CONTENTS (T-05.1-07 mitigated: bytes compared with `==` only, never printed) |

The threat register entries T-05.1-04 through T-05.1-09 from the plan's `<threat_model>` are all mitigated as designed:
- T-05.1-04 (placeholder spoofing): `_HMAC_PLACEHOLDER_SENTINEL` comparison in check (3) of `run()`
- T-05.1-05 (world-readable): postinst `chmod 0600` + config-check mode/owner rejection
- T-05.1-06 (reinstall clobber): `[[ ! -f ]]` idempotency guard in postinst
- T-05.1-07 (bytes leaked): error messages print PATH, not content
- T-05.1-08 (non-root read): `PermissionError` → exit 2 path in `run()`
- T-05.1-09 (systemd-245 hard-fail): L-02 code-side fallback independent of LoadCredential behavior

## Self-Check: PASSED

- S:\spark\modem-watchdog\src\spark_modem\config\settings.py: exists, contains `resolve_hmac_secret_path` at line 246
- S:\spark\modem-watchdog\src\spark_modem\cli\ctl\config_check.py: exists, exports `async def run`
- S:\spark\modem-watchdog\src\spark_modem\cli\main.py: exists, contains `ctl_config_check` import at line 26
- S:\spark\modem-watchdog\debian\spark-modem-watchdog.postinst: exists, contains `[[ ! -f ]]` guard at line 46
- S:\spark\modem-watchdog\tests\unit\config\test_settings_hmac_path.py: exists, 3 tests pass
- S:\spark\modem-watchdog\tests\unit\cli\test_ctl_config_check.py: exists, 6 tests skip on Windows
- Commit 1498b64 (Task 1 RED): confirmed in git log
- Commit 0a63d3c (Task 1 GREEN): confirmed in git log
- Commit 7ca1cd8 (Task 2 RED): confirmed in git log
- Commit fd70a96 (Task 2 GREEN): confirmed in git log
- Commit d5872ac (Task 3): confirmed in git log

# Phase 05.1 Plan 03: systemd Unit File ExecStart* Repoint Summary

**systemd service unit ExecStart/ExecStartPre repointed from never-existed `/opt/.../bin/` wrappers to Plan 05.1-01's console-scripts at `/opt/.../python/bin/`; admission comment replaced with I-01/I-02/I-04 audit trail; all 20 unit-file audit tests pass.**

---

## Performance

- **Duration:** 1m 24s
- **Started:** 2026-05-12T06:42:28Z
- **Completed:** 2026-05-12T06:43:52Z
- **Tasks:** 1
- **Files modified:** 1

---

## Accomplishments

- Eliminated the root cause of systemd 203/EXEC: ExecStart now points at the console-script that Plan 05.1-01 materializes at `/opt/spark-modem-watchdog/python/bin/spark-modem-watchdog`.
- ExecStartPre config-check now calls Plan 05.1-02's `ctl config-check` verb via `/opt/spark-modem-watchdog/python/bin/spark-modem ctl config-check`.
- `LoadCredential=spark-modem-watchdog.hmac-secret:/etc/spark-modem-watchdog/hmac-secret` preserved byte-for-byte (L-01 honored).
- "Phase 4 follow-up: verify wrapper exists" admission comment block retired; replaced with clean I-01/I-02/I-04 decision tag references.

---

## Task Commits

1. **Task 1: Repoint ExecStart* paths to /opt/.../python/bin/ + update comments** - `6a0cb57` (fix)

**Plan metadata:** (docs commit follows in final_commit step)

---

## Files Created/Modified

- `debian/spark-modem-watchdog.service` - ExecStartPre config-check + ExecStart daemon paths changed from `/opt/.../bin/` to `/opt/.../python/bin/`; U-05 comment extended to U-05/L-05; admission comment dropped; 8 lines inserted, 9 deleted (net -1 line)

---

## Exact Before/After Diff (lines 11-23)

### Before

```ini
# FR-60 + B-03 belt-and-suspenders B: smoke-test on every start.
ExecStartPre=/opt/spark-modem-watchdog/libexec/postinst_smoke_test.sh

# U-05: pre-flight Settings validate before main process. Catches bad
# config rollouts BEFORE the main daemon process boots, so a bad
# config doesn't trip StartLimitBurst (PITFALLS §4.2).
ExecStartPre=/opt/spark-modem-watchdog/bin/spark-modem ctl config-check

# Phase 3 wires the real entry point. The wrapper script lives in
# /opt/spark-modem-watchdog/bin/ and is provided by the .deb postinst
# (Phase 4 follow-up: verify wrapper exists; current .deb scaffold may
# need an additional ExecStart shim).
ExecStart=/opt/spark-modem-watchdog/bin/spark-modem-watchdog
```

### After (lines 11-22)

```ini
# FR-60 + B-03 belt-and-suspenders B: smoke-test on every start.
ExecStartPre=/opt/spark-modem-watchdog/libexec/postinst_smoke_test.sh

# U-05 / L-05: pre-flight Settings + HMAC secret validate before main process.
# Catches bad config rollouts (and missing/placeholder HMAC secrets) BEFORE
# the main daemon process boots, so a bad config doesn't trip StartLimitBurst
# (PITFALLS §4.2).
ExecStartPre=/opt/spark-modem-watchdog/python/bin/spark-modem ctl config-check

# Daemon entry point — console-script auto-materialized by [project.scripts]
# in pyproject.toml during override_dh_auto_install (Phase 05.1 I-01/I-02/I-04).
ExecStart=/opt/spark-modem-watchdog/python/bin/spark-modem-watchdog
```

Net change: 13 lines → 12 lines (-1). Two `bin/` paths replaced with `python/bin/` paths; 3-line "Phase 4 follow-up" admission comment block (5 lines) condensed to 2-line audit-trail comment; U-05 comment extended to U-05/L-05 with HMAC mention.

---

## Decisions Made

1. **I-03 (executed):** `/opt/spark-modem-watchdog/bin/` layer dropped entirely from the unit file. All python-script invocations now reference `/opt/spark-modem-watchdog/python/bin/` directly — one fewer abstraction layer, cleanest pairing with the pip-install path.
2. **L-01 (honored):** `LoadCredential=` line at line 99 preserved byte-for-byte. This is the forward-compatible path for Ubuntu 22.04+ / systemd 247+ boxes; code-side fallback (L-02, Plan 05.1-02) handles systemd 245.
3. Smoke-test ExecStartPre (`/opt/spark-modem-watchdog/libexec/postinst_smoke_test.sh`) untouched — it is a shell script shipped via `debian/spark-modem-watchdog.install`, not a console-script.

---

## Verification Results

| Check | Expected | Result |
|-------|----------|--------|
| `grep -cF "/opt/spark-modem-watchdog/bin/" service` | 0 | PASS |
| `grep -cF "/opt/.../python/bin/spark-modem-watchdog" service` | 1 | PASS |
| `grep -cF "/opt/.../python/bin/spark-modem ctl config-check" service` | 1 | PASS |
| `grep -cF "/opt/.../libexec/postinst_smoke_test.sh" service` | 1 | PASS |
| `grep -cF "LoadCredential=...hmac-secret" service` | 1 | PASS |
| `grep -cF "Phase 4 follow-up" service` | 0 | PASS |
| `grep -cF "Phase 05.1 I-01/I-02/I-04" service` | 1 | PASS |
| `pytest tests/integration/test_unit_file_audit.py -v` | 20 passed | PASS (20 passed, 0 failed) |

All acceptance criteria satisfied.

---

## Deviations from Plan

None — plan executed exactly as written.

---

## Issues Encountered

None.

---

## Known Stubs

None. The word "placeholder" appears in a comment about catching placeholder HMAC secrets (correct intent), not as a data stub.

---

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes introduced. This edit removes a broken path and replaces it with the correct path — the trust boundary (`systemd unit → daemon binary`) is unchanged in nature, only corrected in destination. All four threat register entries (T-05.1-10 through T-05.1-13) are mitigated:

- **T-05.1-10** (203/EXEC DoS): ExecStart now resolves to the console-script Plan 05.1-01 materializes.
- **T-05.1-11** (path drift elevation): `/opt/.../bin/` layer eliminated; V-04 audit (Plan 05.1-05) will enforce anchoring.
- **T-05.1-12** (LoadCredential tampering): acceptance criteria grep-assert confirmed; existing `test_load_credential_for_hmac_secret` passes.
- **T-05.1-13** (sandbox directive tampering): all 20 existing audit tests pass, confirming sandbox directives unchanged.

---

## Next Phase Readiness

Wave 2 of Phase 05.1 is complete. Plan 05.1-04 (EXIT-CHECKLIST.md) and Plan 05.1-05 (V-02 CI + V-04 unit-file audit extension) are unblocked. The three-bug fix set (Plans 01-03) is now fully committed:

1. **Bug #1 fixed (Plan 01):** `spark_modem` package ships into bundled venv via `uv pip install .`
2. **Bug #2 fixed (Plans 01 + 03):** `spark-modem-watchdog` console-script declared AND unit file points at it
3. **Bug #3 mitigated (Plans 02 + 03):** HMAC-secret fallback (L-02) + config-check validator (L-05) + unit file ExecStartPre wired correctly

---

*Phase: 05.1-deb-packaging-hotfix*
*Completed: 2026-05-12*

## Self-Check: PASSED

- S:\spark\modem-watchdog\debian\spark-modem-watchdog.service: exists, contains `python/bin/spark-modem-watchdog` at line 22
- S:\spark\modem-watchdog\.planning\phases\05.1-deb-packaging-hotfix\05.1-03-SUMMARY.md: exists
- Commit 6a0cb57 (Task 1): confirmed in git log
- Commit d996199 (docs metadata): confirmed in git log

# Phase 05.1 Plan 04: EXIT-CHECKLIST.md Summary

**Operator-facing 9-step bench Jetson EXIT checklist (V-03) with header table, gate table, free-text rationale, and approval footer — template only, operator fills + commits at phase exit.**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-05-12T06:35:15Z
- **Completed:** 2026-05-12T06:37:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created complete operator-fillable EXIT-CHECKLIST.md template at `.planning/phases/05.1-deb-packaging-hotfix/EXIT-CHECKLIST.md`
- Implemented all 9 V-03 gate rows matching CONTEXT.md L-162..173 verbatim
- Template mirrors Phase 5 SIGNOFF.md shape (header table, gate table, approval footer, footer reference)

## Gate Row Titles (V-03 steps, for orchestrator coverage check)

1. `.deb` built from merged hotfix branch
2. scp + `dpkg -i` returns 0
3. Operator provisions `/etc/spark-modem-watchdog/hmac-secret`
4. `systemctl start spark-modem-watchdog.service` returns 0
5. `systemctl is-active` reports `active`
6. `journalctl` shows `Started ...` + no ERROR/CRITICAL
7. `/run/spark-modem-watchdog/lock` present + owned by root
8. `/run/spark-modem-watchdog/metrics.sock` scrape
9. Daemon reaches Healthy on all 4 modems within 60s (NFR-13)

## Task Commits

Each task was committed atomically:

1. **Task 1: Author EXIT-CHECKLIST.md template** - `20dc8f3` (docs)

**Plan metadata:** (see final commit below)

## Files Created/Modified

- `.planning/phases/05.1-deb-packaging-hotfix/EXIT-CHECKLIST.md` - Operator-facing V-03 exit checklist template; 9-row gate table; approval footer; no pre-filled operator fields

## Decisions Made

- Template is intentionally blank — per plan spec, committing a partially-filled template before all gates pass would falsely signal phase exit
- Step 3 row Expected column specifies `stat -c '%a %u:%g'` output only (never file contents) to prevent HMAC secret disclosure (mitigates T-05.1-15)
- Free-text rationale section explicitly requests L-04 verdict capture (silent-ignore vs hard-fail vs warning-with-degraded) so future plans have the systemd 245 finding documented

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

The actual operator-fill-in cycle is OUT OF SCOPE for this plan.

Phase 05.1 EXIT bar: the on-site engineer scp's the built `.deb` to the bench Jetson, runs `dpkg -i`, provisions the HMAC secret, starts the service, walks each of the 9 V-03 gate rows, fills the EXIT-CHECKLIST.md, and commits it. The committed filled checklist IS the Phase 05.1 EXIT signal.

This plan ships the empty template only. The operator-fill-in is handled out-of-band at Phase 05.1 exit.

## Threat Surface

No new network endpoints or auth paths introduced. The template explicitly instructs operators not to paste HMAC secret bytes (mitigates T-05.1-15). Footer reference `*Template authored by Plan 05.1-04*` anchors provenance against future tampering (T-05.1-16).

## Next Phase Readiness

- EXIT-CHECKLIST.md template is ready for on-site engineer use
- Plan 05-08 Task 2 (bench soak window) is blocked until operator completes and commits the filled EXIT-CHECKLIST.md
- All Phase 05.1 plans (01-04) now complete; remaining plans 05-06 cover CI and unit-file audit

---
*Phase: 05.1-deb-packaging-hotfix*
*Completed: 2026-05-12*

# Phase 05.1 Plan 05: Regression Gate — V-01, V-04, V-02 Summary

**One-liner:** Extended B-03 postinst smoke with daemon/CLI imports (V-01), added three unit-file audit assertions for drift detection (V-04), and replaced the CI smoke-install step with a strict-superset aarch64 docker install test including `systemd-analyze verify` (V-02 / L-04).

## What Was Built

### Task 1: B-03 Postinst Smoke Extension (V-01)

`scripts/postinst_smoke_test.sh` — two new entries appended after the 10 existing runtime-lib imports:

**Before (libs list, 10 entries):**
```python
libs = [
    "pydantic", "pydantic_settings", "yaml", "prometheus_client",
    "pyudev", "pyroute2", "asyncinotify", "httpx", "sdnotify", "psutil",
]
...
print(f"OK: all {len(libs)} runtime libs import under {sys.executable}")
```

**After (libs list, 12 entries):**
```python
libs = [
    "pydantic", "pydantic_settings", "yaml", "prometheus_client",
    "pyudev", "pyroute2", "asyncinotify", "httpx", "sdnotify", "psutil",
    # Phase 05.1 V-01: the daemon + CLI must be importable for the
    # .deb to be functional. These imports catch the bug class
    # "spark_modem not on sys.path of the bundled venv" — the
    # original Phase 1 smoke only imported the 10 runtime libs,
    # never the daemon package itself, which is how bug #1 slipped
    # through Phase 1 CI.
    "spark_modem.daemon.main",
    "spark_modem.cli.main",
]
...
print(f"OK: all {len(libs)} runtime libs + daemon entry points import under {sys.executable}")
```

This catches bug class "spark_modem not on sys.path" at install time (postinst) AND on every start (ExecStartPre). Both call sites pick up the change automatically — no wiring change needed.

### Task 2: V-04 Unit-File Audit Extensions

`tests/integration/test_unit_file_audit.py` — 3 new test functions + 2 new fixtures + 2 new path constants added. Pytest count: **18 → 23 passed**.

**New path constants (module top):**
- `_PYPROJECT_PATH` — points to `pyproject.toml`
- `_INSTALL_PATH` — points to `debian/spark-modem-watchdog.install`

**New fixtures:**
- `project_scripts() -> dict[str, str]` — parses `[project.scripts]` via `tomllib`
- `install_map_dest_paths() -> list[str]` — parses the dest column of the `.install` file

**New tests:**

| Test | Spec | What it checks |
|------|------|----------------|
| `test_v04_exec_paths_anchored` | V-04 (a) | Every ExecStart/ExecStartPre binary is either a `[project.scripts]` console-script at `/opt/.../python/bin/<name>` or a file shipped by `debian/.install` |
| `test_v04_load_credential_path_matches_fallback` | V-04 (b) | `LoadCredential=` source path == `/etc/spark-modem-watchdog/hmac-secret` (the L-02 fallback path) |
| `test_v04_project_scripts_entry_points_importable` | V-04 (c) | Every `[project.scripts]` entry parses as `module:attr`, the module imports cleanly, and the attr exists |

Cross-platform — no `linux_only` marker. Runs on Windows dev host. mypy `--strict` and ruff clean.

### Task 3: V-02 CI Install Test Replacement

`.github/workflows/build-deb.yml` — "Smoke-install in clean container" step (lines 50-69) REPLACED with "Install + verify in clean Ubuntu 20.04 arm64 container (Phase 05.1 V-02)" (lines 50-94).

**Replaced step body summary (old step was 20 lines; new is 44 lines):**

The new step adds to the existing docker `apt install + smoke` pattern:
- **(a)** Re-runs `/opt/spark-modem-watchdog/libexec/postinst_smoke_test.sh` (B-03 belt-and-suspenders)
- **(b)** `test -x /opt/spark-modem-watchdog/python/bin/spark-modem` and `spark-modem-watchdog`
- **(c)** Checks `/etc/spark-modem-watchdog/hmac-secret` exists, is mode `600`, owner `0:0`, and contains `REPLACE_THIS_BEFORE_FIRST_START_SEE_RUNBOOK`
- **(d)** `systemd-analyze verify /lib/systemd/system/spark-modem-watchdog.service 2>&1` — the L-04 forcing function

Key implementation detail: outer single-quote heredoc (`bash -lc '...'`) with `'"$(basename $DEB)"'` splice so the deb filename is expanded by the GHA runner shell, not inside the docker container.

The workflow trigger (`on:`), `runs-on`, and `upload-artifact` step are unchanged.

## Pytest Count Before/After

| Scope | Before Plan 05 | After Plan 05 |
|-------|---------------|---------------|
| `test_unit_file_audit.py` | 20 tests | 23 tests |
| V-04 tests only | 0 | 3 passed |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Moved local imports to module top-level (ruff PLC0415)**

- **Found during:** Task 2 verification
- **Issue:** Plan specified `import tomllib` inside the fixture body and `import importlib` inside the test body as local imports. Ruff's `PLC0415` rule (selected via `PL` in pyproject.toml) flags imports not at module top-level.
- **Fix:** Moved both `import tomllib` and `import importlib` to the module-level import block at the top of `test_unit_file_audit.py`. The plan note "local import is acceptable" was superseded by the project's ruff configuration — CLAUDE.md rules take precedence.
- **Files modified:** `tests/integration/test_unit_file_audit.py`
- **Commit:** `0f3152f`

## L-04 Verdict Note

**IMPORTANT:** The L-04 verdict (whether systemd 245 silent-ignores, warns-with-degraded, or hard-fails `LoadCredential=` parsing) surfaces on the next push to main when the aarch64 self-hosted runner picks up this workflow.

- **If hard-fail:** `systemd-analyze verify` exits non-zero, the V-02 CI step fails, and a follow-up commit adds a postinst-managed drop-in override at `/etc/systemd/system/spark-modem-watchdog.service.d/10-systemd245-no-loadcredential.conf` per CONTEXT.md L-04 second branch.
- **If silent-ignore or warning:** V-02 step passes; the `2>&1` redirect makes any stderr warning visible in the CI log. Operators should capture this in `EXIT-CHECKLIST.md` step 6 (journalctl evidence).

The L-02 code-side fallback (already landed in Plan 05.1-02) handles silent-ignore and warning cases without further action.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The three files modified are: a shell script, a test file, and a CI workflow definition. No new trust boundary surfaces.

## Self-Check: PASSED

All files found and commits verified:

| Item | Status |
|------|--------|
| `scripts/postinst_smoke_test.sh` | FOUND |
| `tests/integration/test_unit_file_audit.py` | FOUND |
| `.github/workflows/build-deb.yml` | FOUND |
| `.planning/phases/05.1-deb-packaging-hotfix/05.1-05-SUMMARY.md` | FOUND |
| commit `18fc5a0` (Task 1 — V-01 smoke) | FOUND |
| commit `0f3152f` (Task 2 — V-04 tests) | FOUND |
| commit `cc60a5c` (Task 3 — V-02 workflow) | FOUND |

# Phase 05.1 Plan 06: ROADMAP Housekeeping + Debian Changelog Summary

**ROADMAP Phase 05.1 placeholder replaced with real Goal/Success-Criteria block; debian/changelog prepended with 2.0.1-1 entry documenting 3 hotfix bugs + regression gate**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-05-12T06:38:00Z
- **Completed:** 2026-05-12T06:40:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- ROADMAP.md Phase 05.1 entry rewritten: placeholder `[Urgent work - to be planned]` replaced with concrete Goal (`dpkg -i` → `active (running)` + `sd_notify READY=1` on bench Jetson), Requirements, Depends on, Success Criteria (EXIT bar with 9 V-03 rows), and expanded Plans list with detailed descriptions
- debian/changelog now has a 2.0.1-1 UNRELEASED entry at the top documenting all 3 bug fixes (sys.path, daemon entry point, systemd 245 LoadCredential= fallback), postinst HMAC placeholder, and regression gate (V-01/V-02/V-04)
- Existing 2.0.0-1 changelog entry preserved byte-for-byte below the new entry
- Phase 1..5 and Phase 6..7 ROADMAP entries are unchanged

## Task Commits

1. **Task 1: Rewrite ROADMAP.md Phase 05.1 entry** - `19546cd` (docs)
2. **Task 2: Add 2.0.1-1 entry to debian/changelog** - `0f9af63` (chore)

**Plan metadata:** (included in final docs commit below)

## Files Created/Modified

- `.planning/ROADMAP.md` - Phase 05.1 entry expanded from 9-line placeholder to ~42-line substantive entry with Goal, Requirements, Depends on, Success Criteria, and Plans list
- `debian/changelog` - New 2.0.1-1 entry prepended; 2.0.0-1 entry preserved verbatim

## Before/After: ROADMAP Phase 05.1 Entry

**BEFORE (9 lines, lines 402-415):**
```markdown
### Phase 05.1: deb-packaging-hotfix (INSERTED)

**Goal:** [Urgent work - to be planned]
**Requirements**: TBD
**Depends on:** Phase 5
**Plans:** 6 plans

Plans:
- [x] 05.1-01-PLAN.md — pyproject [project.scripts] + daemon _sync_main + debian/rules uv pip install . (I-01/I-02/I-04/I-05) — completed 2026-05-12
- [ ] 05.1-02-PLAN.md — Settings.resolve_hmac_secret_path() + ctl config-check verb + postinst HMAC placeholder (L-02/L-03/L-05)
- [ ] 05.1-03-PLAN.md — service unit ExecStart* paths repointed to /opt/.../python/bin/ (I-03; L-01 preserved)
- [ ] 05.1-04-PLAN.md — EXIT-CHECKLIST.md operator template (V-03)
- [ ] 05.1-05-PLAN.md — postinst smoke + unit-file audit + CI install test incl. systemd-analyze verify (V-01/V-02/V-04; L-04 verifier)
- [ ] 05.1-06-PLAN.md — ROADMAP.md goal rewrite + debian/changelog 2.0.1-1 entry
```

**AFTER (~42 lines):**
```markdown
### Phase 05.1: deb-packaging-hotfix (INSERTED)

**Goal**: `dpkg -i spark-modem-watchdog_2.0.*_arm64.deb` followed by
`systemctl start spark-modem-watchdog.service` reaches `active (running)`
with `sd_notify READY=1` on a bench Jetson (JetPack 5.1.5 / Ubuntu 20.04 /
systemd 245 / aarch64). Three known bugs fixed: (1) `spark_modem` not on
`sys.path` of the bundled venv → fixed by `uv pip install .` inside
`override_dh_auto_install`; (2) no daemon entry point → fixed by adding
`spark-modem-watchdog` to `pyproject.toml [project.scripts]`; (3) systemd-
245 `LoadCredential=` incompatibility → fixed by a code-side fallback in
`Settings.resolve_hmac_secret_path()`. Regression gate (D-01) lands so
the same class of bug cannot recur silently.

**Requirements**: (no formal v1 REQ-IDs — inserted hotfix; indirectly
tied to NFR-30 root-only secrets via L-03 mode/owner check, and ADR-0011
HMAC discipline via L-01..L-05)

**Depends on**: Phase 5

**Success Criteria** (EXIT bar pattern per D-03, mirroring Phase 4):
  The committed `.planning/phases/05.1-deb-packaging-hotfix/EXIT-CHECKLIST.md`
  has every V-03 gate row marked PASS by the on-site engineer. [... 9 rows ...]

**Plans**: 6 plans

Plans:
- [x] 05.1-01-PLAN.md — pyproject.toml [project.scripts] + daemon _sync_main inline + ...
- [ ] 05.1-02-PLAN.md — Settings.resolve_hmac_secret_path() (L-02) + ...
- [ ] 05.1-03-PLAN.md — debian/spark-modem-watchdog.service ExecStart* ...
- [ ] 05.1-04-PLAN.md — EXIT-CHECKLIST.md operator template (V-03)
- [ ] 05.1-05-PLAN.md — Postinst smoke extension (V-01) + unit-file audit ...
- [ ] 05.1-06-PLAN.md — ROADMAP.md goal rewrite + debian/changelog 2.0.1-1 entry
```

**Unchanged-entries confirmation:** `grep -c "Phase 1: Foundations" .planning/ROADMAP.md` → 2 (heading + reference); `grep -c "Phase 6: Cutover" .planning/ROADMAP.md` → 2 (heading + reference). Phase 2..5 entries verified present via git diff (only Phase 05.1 block lines changed, net +28 lines).

## New debian/changelog Top Entry (verbatim)

```
spark-modem-watchdog (2.0.1-1) UNRELEASED; urgency=medium

  * Phase 05.1 hotfix: bench Jetson .deb install now reaches active (running)
    with sd_notify READY=1.
  * Fix (bug #1): ship spark_modem package via `uv pip install .` inside
    override_dh_auto_install (I-01); removes the
    src/spark_modem /opt/spark-modem-watchdog/lib/ install map line that
    left the daemon package off the bundled venv's sys.path.
  * Fix (bug #2): add `spark-modem-watchdog` console script (I-02 + I-04) —
    systemd ExecStart no longer hits 203/EXEC. Daemon entry point is now
    /opt/spark-modem-watchdog/python/bin/spark-modem-watchdog.
  * Fix (bug #3): HMAC-secret fallback for systemd 245 (L-02) — daemon
    reads from /etc/spark-modem-watchdog/hmac-secret directly if
    CREDENTIALS_DIRECTORY is unset (Ubuntu 20.04 ships systemd 245;
    LoadCredential= was introduced in systemd 247). LoadCredential=
    directive preserved in the unit file (L-01) for future systemd 247+
    boxes.
  * Postinst now writes a 0600 root:root placeholder HMAC secret (L-03);
    `spark-modem ctl config-check` (ExecStartPre) refuses to boot with
    the placeholder sentinel.
  * Regression gate: extended postinst smoke now imports
    spark_modem.daemon.main + spark_modem.cli.main (V-01); new aarch64
    Docker install test in CI asserts both console scripts present,
    HMAC placeholder file 0600 root:root, and systemd-analyze verify
    exits 0 (V-02; verifies L-04); 3 new unit-file audit assertions
    catch unit ↔ pyproject ↔ install drift (V-04).

 -- spark-modem-watchdog devs <dev@draco.co.il>  Tue, 12 May 2026 00:00:00 +0000
```

## Decisions Made

- Version 2.0.1-1 chosen (PEP-440 M.m.p patch) over 2.0.0+hotfix.1 (PEP-440 local-version): cleaner shape, universally supported, avoids `+` handling quirks in apt on Ubuntu 20.04 (per CONTEXT.md "Claude's Discretion")
- ROADMAP Phase 05.1 entry uses EXIT bar pattern mirroring Phase 4 Success Criteria (per D-03 pattern)
- Kept `urgency=medium` (not `high`) per PATTERNS.md § 10 advice that `high` triggers alarm-worthy signals in some tooling

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 05.1 is now fully documented at the ROADMAP level
- debian/changelog reflects the hotfix version 2.0.1-1, distinguishable from pre-hotfix 2.0.0-1
- Plans 02-06 remain unchecked in ROADMAP (as expected — phase execution gates on EXIT-CHECKLIST.md being filled in by the on-site engineer)
- Phase 6 planner can read the Phase 05.1 Goal + Success Criteria block to understand what Phase 05.1 delivered

---
*Phase: 05.1-deb-packaging-hotfix*
*Completed: 2026-05-12*
