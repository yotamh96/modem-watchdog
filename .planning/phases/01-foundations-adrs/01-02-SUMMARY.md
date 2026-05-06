---
phase: 01-foundations-adrs
plan: "02"
subsystem: packaging
tags:
  - debian
  - packaging
  - python-build-standalone
  - systemd
  - arm64
dependency_graph:
  requires:
    - 01-01-pyproject-requirements-lock  # packaging/requirements.lock
    - 01-06-clock-config-event-logger-carriers  # debian/conf.d/00-carriers.yaml
  provides:
    - debian_build_pipeline  # debian/* + scripts/build_deb.sh + CI workflow
    - arm64_deb_artifact  # installable .deb for Jetson Orin NX
  affects:
    - all_phases  # the .deb is the deployment artifact for every phase's code
tech_stack:
  added:
    - python-build-standalone==cpython-3.12.13+20260504 (aarch64-unknown-linux-gnu)
    - debhelper-compat 13
    - uv (build-time only; uninstalled from bundled venv after use)
  patterns:
    - PBS tarball SHA256 pinned in debian/python.sha256; verified via sha256sum -c before unpack
    - uv pip install --no-deps --frozen -r requirements.lock (triple-lock: frozen + no-deps + --require-hashes)
    - SOURCE_DATE_EPOCH from git log -1 --format=%ct for deterministic .pyc
    - compileall run at build time for warm pyc cache (NFR-13)
    - Belt-and-suspenders import gate in postinst (fail-install) AND ExecStartPre= (fail-start)
key_files:
  created:
    - debian/changelog
    - debian/compat
    - debian/control
    - debian/copyright
    - debian/python.sha256
    - debian/rules
    - debian/source/format
    - debian/spark-modem-watchdog.dirs
    - debian/spark-modem-watchdog.install
    - debian/spark-modem-watchdog.postinst
    - debian/spark-modem-watchdog.postrm
    - debian/spark-modem-watchdog.service
    - scripts/postinst_smoke_test.sh
    - scripts/build_deb.sh
    - .github/workflows/build-deb.yml
  modified: []
decisions:
  - "Pin cpython-3.12.13+20260504-aarch64-unknown-linux-gnu-install_only.tar.gz (latest stable 3.12.x as of 2026-05-06)"
  - "Use SHA256 8a27d68c0dec7573c269e16da61fed358e4bb9f986ae976549ca87ed49fe1506 from official PBS SHA256SUMS file"
  - "postinst creates spark-modem-watchdog system user and masks ModemManager (hardware constraint: Zao exclusive access)"
  - "postrm unmasks ModemManager and removes bundled venv on --purge only; remove action skips venv cleanup"
  - "LoadCredential= included in service unit (ADR-0011); Phase 2 reads via CREDENTIALS_DIRECTORY env var"
  - "Phase 1 service ExecStart= is a no-op sdnotify placeholder; Phase 2 replaces with real daemon binary"
  - "License debt noted in debian/copyright: per-library license enumeration deferred to Phase 4 / RC1"
metrics:
  duration: "10 minutes"
  completed: "2026-05-06T10:07:27Z"
  tasks_completed: 2
  files_created: 15
---

# Phase 01 Plan 02: deb-build-pipeline Summary

**One-liner:** arm64 .deb build pipeline using python-build-standalone CPython 3.12.13 + uv frozen install + belt-and-suspenders 10-import smoke gate in postinst and ExecStartPre=.

## What Was Built

### PBS Tarball Selection

Pinned `cpython-3.12.13+20260504-aarch64-unknown-linux-gnu-install_only.tar.gz` from the latest
PBS release tag `20260504`. SHA256 verified from the official `SHA256SUMS` file:

```
8a27d68c0dec7573c269e16da61fed358e4bb9f986ae976549ca87ed49fe1506  cpython-3.12.13+20260504-aarch64-unknown-linux-gnu-install_only.tar.gz
```

This tarball is recorded in `debian/python.sha256`; `debian/rules` runs `sha256sum -c debian/python.sha256`
before unpacking — build fails immediately on hash mismatch (T-02-01 mitigation, B-02).

### Build Pipeline (`debian/rules`)

Implements the 5-step STACK.md recipe:

1. **Download + verify + unpack**: curl + sha256sum -c + tar into `debian/python-build-standalone/python/`
2. **Bootstrap pip + install uv**: `ensurepip --upgrade` + `pip install uv>=0.5,<1`
3. **Install 10 runtime libs frozen**: `uv pip install --python <bundled> --no-deps --frozen -r packaging/requirements.lock`
4. **Warm pyc cache**: `python3.12 -m compileall -q` with `SOURCE_DATE_EPOCH` exported (B-04 determinism)
5. **Strip build tools**: `pip uninstall -y uv pip setuptools wheel` (NFR-51 size budget)

PITFALLS §18.3 guard: asserts `sys.executable == VENVDIR/bin/python3.12` at the final destdir
path — prevents builder paths baking into `.pyc` files.

### Import Smoke Gate (`scripts/postinst_smoke_test.sh`)

Imports all 10 runtime libs under the bundled Python:

```
pydantic, pydantic_settings, yaml, prometheus_client, pyudev,
pyroute2, asyncinotify, httpx, sdnotify, psutil
```

Called from **two places** (B-03 belt-and-suspenders):
- **A. `debian/spark-modem-watchdog.postinst`** (configure step): non-zero exit fails `apt install`
- **B. `ExecStartPre=` in the systemd unit**: smoke test runs at every `systemctl start`; failure prevents daemon from reaching active state

### Carrier YAML Install

`debian/spark-modem-watchdog.install` ships Plan 06's `debian/conf.d/00-carriers.yaml` to
`/etc/spark-modem-watchdog/conf.d/00-carriers.yaml` on the box. A fresh install boots with
12 day-one carriers (IL/US/GB/DE).

### systemd Unit (`debian/spark-modem-watchdog.service`)

- `Type=notify` + `NotifyAccess=main` (NOT `notify-reload` — Ubuntu 20.04 / systemd 245 lacks it)
- `ExecStartPre=` runs `postinst_smoke_test.sh` (B-03 suspenders B)
- `LoadCredential=spark-modem-watchdog.hmac-secret:/etc/spark-modem-watchdog/hmac-secret` (ADR-0011)
- Phase 1 `ExecStart=` is an sdnotify placeholder; Phase 2 replaces with real daemon

### postinst / postrm Contracts

**postinst (configure)**:
1. Runs smoke test (B-03 A) — fails install on any broken import
2. Creates `spark-modem-watchdog` system user (via `adduser --system`)
3. Creates and chowns `/var/lib/spark-modem-watchdog/{state/by-usb}` and `/var/log/spark-modem-watchdog`
4. Masks `ModemManager.service` (hardware invariant: Zao requires exclusive modem access)
5. Daemon-reloads systemd

**postrm (purge)**:
1. Unmasks `ModemManager.service`
2. Removes `/opt/spark-modem-watchdog` (bundled venv, ~35 MiB)
3. Removes `/var/lib/spark-modem-watchdog` and `/var/log/spark-modem-watchdog`
4. Removes `spark-modem-watchdog` system user

### CI Workflow (`.github/workflows/build-deb.yml`)

Runs on `[self-hosted, linux, ARM64]` (native aarch64 — B-01 primary CI path):
1. Installs debhelper/devscripts/fakeroot/dpkg-dev/curl/ca-certificates
2. Runs `bash scripts/build_deb.sh dev`
3. Verifies `dpkg-deb -I`, `dpkg-deb -c`, size ≤ 40 MiB
4. Smoke-installs in clean `ubuntu:20.04` arm64 Docker container (B-03 A end-to-end)
5. Uploads `.deb` artifact (30-day retention)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] postinst adds system user creation and directory chown**
- **Found during:** Task 1
- **Issue:** Plan's postinst template ran smoke test and daemon-reload but did not create the system user or chown the state directories. RUNBOOK.md requires a `spark-modem-watchdog` system user; the daemon would fail to write state files without it.
- **Fix:** Added `adduser --system` block and `install -d -m 0750 -o spark-modem-watchdog` for `/var/lib/spark-modem-watchdog/` subtree.
- **Files modified:** `debian/spark-modem-watchdog.postinst`
- **Commit:** 9012d60

**2. [Rule 2 - Missing Critical Functionality] postrm expands purge handling to include state/user removal**
- **Found during:** Task 1
- **Issue:** Plan's postrm template handled `remove|purge|upgrade|...` in one case branch but did not actually remove state directories or the system user on `--purge`. The `purge` case requires full cleanup for clean reinstall.
- **Fix:** Split into `remove|upgrade|...` (daemon-reload only) and `purge` (unmask ModemManager + rm venv/state + deluser).
- **Files modified:** `debian/spark-modem-watchdog.postrm`
- **Commit:** 9012d60

**3. [Rule 2 - Missing Critical Functionality] Added LoadCredential= to systemd unit (ADR-0011)**
- **Found during:** Task 1
- **Issue:** Plan's service template did not include `LoadCredential=` for the HMAC secret despite ADR-0011 specifying this as the credential delivery mechanism (closes Q5). Missing now means Phase 2 would need to amend the systemd unit.
- **Fix:** Added `LoadCredential=spark-modem-watchdog.hmac-secret:/etc/spark-modem-watchdog/hmac-secret` to the `[Service]` section.
- **Files modified:** `debian/spark-modem-watchdog.service`
- **Commit:** 9012d60

## Known Stubs

- **ExecStart= placeholder** (`debian/spark-modem-watchdog.service`, lines 24-26): The Phase 1 `ExecStart=` runs `sdnotify.notify("READY=1")` and immediately exits. This is intentional — Phase 2 replaces it with the real `bin/spark-modem-watchdog` shim. Noted explicitly in the unit file.
- **Bundled venv not built yet** — `debian/python-build-standalone/python/*` referenced in `debian/spark-modem-watchdog.install` is populated at `dpkg-buildpackage` time by `debian/rules`. The repo ships the build instructions, not the pre-built tree.
- **`/etc/spark-modem-watchdog/hmac-secret` credential file** — `LoadCredential=` references this path; the file does not exist at install time. Phase 2 (deployment) provisions it via Ansible or operator manual creation.

## Threat Flags

No new trust boundaries introduced beyond those documented in the plan's `<threat_model>`. All STRIDE threats T-02-01 through T-02-08 are mitigated or accepted as documented.

## Known Debt

- **License enumeration** (`debian/copyright`): Per-library license for the 10 bundled runtime deps (pydantic, httpx, etc.) is noted as a debt. Each library's `.dist-info/LICENSE` is available on the installed box. Full enumeration deferred to Phase 4 / RC1.

## Self-Check

Checking file existence and commits:

| Item | Result |
|------|--------|
| debian/changelog | FOUND |
| debian/control | FOUND |
| debian/compat | FOUND |
| debian/source/format | FOUND |
| debian/copyright | FOUND |
| debian/python.sha256 | FOUND |
| debian/rules | FOUND |
| debian/spark-modem-watchdog.dirs | FOUND |
| debian/spark-modem-watchdog.install | FOUND |
| debian/spark-modem-watchdog.postinst | FOUND |
| debian/spark-modem-watchdog.postrm | FOUND |
| debian/spark-modem-watchdog.service | FOUND |
| scripts/postinst_smoke_test.sh | FOUND |
| scripts/build_deb.sh | FOUND |
| .github/workflows/build-deb.yml | FOUND |
| Commit 9012d60 (Task 1) | FOUND |
| Commit a47e051 (Task 2) | FOUND |

## Self-Check: PASSED
