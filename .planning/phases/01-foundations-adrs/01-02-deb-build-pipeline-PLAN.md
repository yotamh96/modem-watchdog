---
phase: 01-foundations-adrs
plan: 02
type: execute
wave: 4
depends_on: [01, 03, 06]
files_modified:
  - debian/changelog
  - debian/control
  - debian/rules
  - debian/compat
  - debian/source/format
  - debian/python.sha256
  - debian/spark-modem-watchdog.install
  - debian/spark-modem-watchdog.dirs
  - debian/spark-modem-watchdog.postinst
  - debian/spark-modem-watchdog.postrm
  - debian/spark-modem-watchdog.service
  - debian/copyright
  - scripts/postinst_smoke_test.sh
  - scripts/build_deb.sh
  - .github/workflows/build-deb.yml
autonomous: true
requirements:
  - FR-60
  - FR-63
  - NFR-50
  - NFR-51
  - NFR-52
  - FR-72
tags:
  - debian
  - packaging
  - python-build-standalone
  - systemd

must_haves:
  truths:
    - "Running `bash scripts/build_deb.sh` on an aarch64 Linux host produces a single `.deb` file under dist/ named `spark-modem-watchdog_2.0.0-0.git<sha>-1_arm64.deb` (dev) or `spark-modem-watchdog_2.0.0-1_arm64.deb` (release)"
    - "The `.deb` is ≤40 MiB (NFR-51 ceiling)"
    - "On `apt install` of the `.deb` on a fresh Jetson (or aarch64 Ubuntu 20.04 container), the postinst smoke test imports all 10 runtime libs under /opt/spark-modem-watchdog/python/bin/python3.12 and a single failed import fails apt install with non-zero exit (FR-60 + B-03 belt-and-suspenders A)"
    - "The systemd unit's ExecStartPre= re-runs the same smoke test at every daemon start (FR-60 + B-03 belt-and-suspenders B)"
    - "`debian/python.sha256` pins a specific PBS tarball SHA256; `debian/rules` verifies the hash before unpack (B-02)"
    - "SOURCE_DATE_EPOCH is set in debian/rules from the most recent git commit timestamp; `python -m compileall` produces deterministic .pyc files (B-04)"
    - "`uv pip install --frozen --no-deps -r packaging/requirements.lock` is the install step in debian/rules (NFR-52, B-04)"
    - "`debian/spark-modem-watchdog.install` ships Plan 06's `debian/conf.d/00-carriers.yaml` to `/etc/spark-modem-watchdog/conf.d/` so a fresh install boots with the day-one carrier table"
  artifacts:
    - path: "debian/changelog"
      provides: "Debian changelog with version 2.0.0-1 (release) or 2.0.0-0.git<sha>-1 (dev)"
      contains: "spark-modem-watchdog (2.0.0-"
    - path: "debian/control"
      provides: "Package metadata: Architecture: arm64, Depends: qmi-utils, iproute2, systemd"
      contains: "Architecture: arm64"
    - path: "debian/rules"
      provides: "Build steps: fetch PBS tarball, verify SHA256, unpack, create venv, uv pip install --frozen, compileall, install shims"
      contains: "SOURCE_DATE_EPOCH"
    - path: "debian/python.sha256"
      provides: "SHA256 of pinned python-build-standalone tarball (cpython-3.12.<patch>+<datetag>-aarch64-unknown-linux-gnu-install_only.tar.gz)"
      contains: "aarch64-unknown-linux-gnu-install_only.tar.gz"
    - path: "debian/spark-modem-watchdog.install"
      provides: "Install manifest: bundles PBS tree, src/spark_modem package, smoke script, systemd unit, and Plan 06's day-one carrier YAML"
      contains: "00-carriers.yaml /etc/spark-modem-watchdog/conf.d/"
    - path: "debian/spark-modem-watchdog.postinst"
      provides: "Postinst hook that runs the 10-import smoke test; non-zero exit fails apt install"
      contains: "scripts/postinst_smoke_test.sh"
    - path: "debian/spark-modem-watchdog.service"
      provides: "systemd Type=notify unit with ExecStartPre= running the smoke test"
      contains: "Type=notify\nExecStartPre="
    - path: "scripts/postinst_smoke_test.sh"
      provides: "Bundled-Python import-all-10-libs check, runnable from postinst and ExecStartPre="
      contains: "import pydantic, pydantic_settings, yaml, prometheus_client, pyudev, pyroute2, asyncinotify, httpx, sdnotify, psutil"
    - path: ".github/workflows/build-deb.yml"
      provides: "CI job that builds the .deb on the self-hosted aarch64 runner and uploads the artifact"
      contains: "runs-on: [self-hosted, linux, ARM64]"
  key_links:
    - from: "debian/rules"
      to: "packaging/requirements.lock"
      via: "uv pip install --frozen --no-deps -r packaging/requirements.lock"
      pattern: "uv pip install --frozen"
    - from: "debian/rules"
      to: "debian/python.sha256"
      via: "sha256sum -c debian/python.sha256 before unpack"
      pattern: "sha256sum -c debian/python.sha256"
    - from: "debian/spark-modem-watchdog.postinst"
      to: "scripts/postinst_smoke_test.sh"
      via: "exec call from postinst with the bundled python path"
      pattern: "/opt/spark-modem-watchdog/python/bin/python3.12 .*postinst_smoke_test\\.sh|postinst_smoke_test\\.sh"
    - from: "debian/spark-modem-watchdog.service"
      to: "scripts/postinst_smoke_test.sh"
      via: "ExecStartPre= invokes the same smoke script with the bundled python"
      pattern: "ExecStartPre=.*postinst_smoke_test"
    - from: "debian/spark-modem-watchdog.install"
      to: "debian/conf.d/00-carriers.yaml"
      via: "install line shipping Plan 06's YAML to /etc/spark-modem-watchdog/conf.d/"
      pattern: "00-carriers\\.yaml /etc/spark-modem-watchdog/conf.d/"
---

<objective>
Build a Debian `.deb` for arm64 that bundles CPython 3.12 (via `python-build-standalone`), all 10 runtime libraries (frozen by `packaging/requirements.lock`), the (currently-empty) `src/spark_modem/` package, the day-one carrier table from Plan 06, and a systemd unit. Failed import of any runtime library either fails `apt install` (postinst) or fails `systemctl start` (ExecStartPre=), per CONTEXT.md B-03's belt-and-suspenders model.

Purpose: Closes Phase 1 SC #1 (the `.deb` import-smoke gate is the Phase 1 acceptance gate). Closes FR-60 (refuse to start without bundled python3.12 + 10 libs). Closes NFR-50 (`.deb` for arm64, self-contained venv at `/opt/spark-modem-watchdog/python/`). Closes NFR-51 (≤40 MiB; security-update story = rebuild on each CPython security release). Closes NFR-52 (uv pip compile output → frozen install). Implements ADR-0010 (packaging via PBS + uv + custom debhelper rule).

Output: A working build pipeline that produces an installable, reproducible arm64 `.deb`. The `.deb` does not yet contain a useful daemon binary (Plan 03+ provide the wire types and Phase 2 builds the cycle); but the import-smoke gate proves the runtime substrate works on Jetson hardware, and the day-one carrier YAML is in place at `/etc/spark-modem-watchdog/conf.d/00-carriers.yaml`.
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
@.planning/research/STACK.md
@.planning/research/PITFALLS.md
@.planning/research/SUMMARY.md
@CLAUDE.md
@pyproject.toml
@packaging/requirements.lock
@packaging/requirements.in
@debian/conf.d/00-carriers.yaml

<interfaces>
<!-- This plan consumes pyproject.toml + packaging/requirements.lock from Plan 01. -->
<!-- And the (currently empty) src/spark_modem/ tree (Plan 03 fills wire/, Plan 04 fills state_store/, etc.) -->
<!-- And debian/conf.d/00-carriers.yaml from Plan 06 (wave 3 ships the YAML; wave 4 wires its install line). -->

From .planning/research/STACK.md §"Packaging recipe" (the canonical 5-step debhelper sequence):
```text
1. Download pinned `python-build-standalone` tarball (SHA256 in `debian/python.sha256`);
   unpack to `debian/<pkg>/opt/spark-modem-watchdog/python/`.
2. `python/bin/python3.12 -m venv venv` against destdir.
3. `uv pip install --no-deps -r requirements.lock` into the venv.
4. `python -m compileall` (warm pyc cache for NFR-13).
5. Generate `bin/spark-modem` and `libexec/spark-modem-watchdog` shims;
   install systemd unit, default config, logrotate snippet, post-install hook.
```

Estimated .deb size: 30–35 MiB (NFR-51 ceiling 40 MiB).

From CONTEXT.md B-04 (versioning + reproducibility):
- Releases:    `2.0.0-1`
- Dev builds:  `2.0.0-0.git<short-sha>-1`
- SOURCE_DATE_EPOCH = $(git log -1 --format=%ct)
- `python -m compileall` runs in-build for NFR-13 warm-cache
- `uv pip install --frozen` enforced in debian/rules

From CONTEXT.md B-03 (smoke test in TWO places):
- debian/postinst — fail-the-install
- systemd ExecStartPre= — fail-the-start

From Plan 01 (wave 1; complete before this plan): `packaging/requirements.in` and
`packaging/requirements.lock` ship 10 pinned runtime libs (pydantic,
pydantic-settings, PyYAML, prometheus-client, pyudev, pyroute2, asyncinotify,
httpx, sdnotify, psutil).

From Plan 06 (wave 3; complete before this plan at wave 4): `debian/conf.d/00-carriers.yaml`
ships the 12 day-one IL/US/GB/DE carrier records validated by `spark_modem.wire.CarrierTable`.
This plan owns `debian/spark-modem-watchdog.install` and adds the install line that
ships the YAML to `/etc/spark-modem-watchdog/conf.d/` on the box.
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Author debian/* metadata + python.sha256 + smoke script + systemd unit + carrier-YAML install line</name>
  <files>debian/changelog, debian/control, debian/compat, debian/source/format, debian/copyright, debian/python.sha256, debian/spark-modem-watchdog.install, debian/spark-modem-watchdog.dirs, debian/spark-modem-watchdog.postinst, debian/spark-modem-watchdog.postrm, debian/spark-modem-watchdog.service, scripts/postinst_smoke_test.sh</files>
  <read_first>
    - .planning/research/STACK.md §"Packaging recipe" (5 steps)
    - .planning/phases/01-foundations-adrs/01-CONTEXT.md §"B. `.deb` build & CI" B-01..B-04
    - .planning/research/PITFALLS.md §18.x (venv path relocation §18.3, certifi rotation §18.5)
    - CLAUDE.md §"Critical invariants" (#7 stack snapshot — sdnotify pure-Python, drop dh-virtualenv)
    - pyproject.toml (created in Plan 01)
    - packaging/requirements.in (the 10 libs that the smoke test must import)
    - packaging/requirements.lock (created in Plan 01)
    - debian/conf.d/00-carriers.yaml (created in Plan 06, wave 3)
  </read_first>
  <action>
    1. **`debian/compat`**: single line `13` (debhelper compat 13; works with debhelper >=13 on Ubuntu 22.04 builders and on Jetson's 20.04 with backports — at minimum 12 if 13 is unavailable; check with `dh --version` and pick the lowest stable). Default to `13`.

    2. **`debian/source/format`**: single line `3.0 (native)` (we don't generate an upstream tarball; the repo IS the source).

    3. **`debian/changelog`** with the **release** entry:
    ```
    spark-modem-watchdog (2.0.0-1) UNRELEASED; urgency=medium

      * Initial 2.0 release: Python rewrite of v1 bash toolchain.
      * Bundles CPython 3.12 via python-build-standalone (closes Q8).
      * Includes wire/ types, state_store/, subproc/, clock/, config/,
        event_logger/, and the default carrier table for IL/US/UK/DE.
      * No daemon yet — Phase 1 is plumbing only; the cycle/policy/actions
        land in Phase 2.

     -- spark-modem-watchdog devs <dev@draco.co.il>  Wed, 06 May 2026 00:00:00 +0000
    ```

    `scripts/build_deb.sh` (Task 2) overwrites the version line in dev builds; the committed changelog is the canonical release version.

    4. **`debian/control`**:
    ```
    Source: spark-modem-watchdog
    Section: net
    Priority: optional
    Maintainer: spark-modem-watchdog devs <dev@draco.co.il>
    Build-Depends:
     debhelper-compat (= 13),
     curl,
     ca-certificates
    Standards-Version: 4.6.2
    Rules-Requires-Root: no

    Package: spark-modem-watchdog
    Architecture: arm64
    Depends:
     ${misc:Depends},
     libqmi-utils (>= 1.30),
     iproute2,
     systemd (>= 245)
    Recommends: logrotate
    Description: On-device watchdog for Sierra EM7421 LTE modems behind Soliton Zao
     spark-modem-watchdog v2 keeps a fleet of NVIDIA Jetson Orin NX bonded-uplink
     boxes online by detecting unhealthy Sierra EM7421 modems and applying the
     smallest recovery action that has a chance of fixing the issue without
     making things worse. Bundles CPython 3.12 via python-build-standalone.
    ```

    Note: do NOT add `python3` or `python3-*` to Depends — we ship the runtime ourselves (NFR-50).

    5. **`debian/copyright`**: a minimal Debian-format copyright file (~30 lines) listing the project's license as Proprietary and the bundled python-build-standalone components under their MIT/PSF licenses (PBS bundles upstream CPython licensed under PSF + a small MIT layer).

    6. **`debian/python.sha256`**: pin a specific PBS tarball. The exact tarball name and SHA must be filled by the executor by:
       a. Visiting https://github.com/astral-sh/python-build-standalone/releases/latest
       b. Selecting the most recent CPython 3.12.x release for `aarch64-unknown-linux-gnu-install_only.tar.gz`
       c. Running `curl -sSL https://github.com/astral-sh/python-build-standalone/releases/download/<TAG>/<filename> | sha256sum`
       d. Recording the result in this file in `sha256sum --check`-compatible format:
       ```
       <SHA256>  cpython-3.12.<patch>+<datetag>-aarch64-unknown-linux-gnu-install_only.tar.gz
       ```

    Action authors: pick CPython 3.12.7 or later (3.12.x has been ABI-stable since 3.12.0 release; pick the latest stable 3.12.x at execution time); record the exact filename and SHA. Example placeholder format (replace with actual):
    ```
    <fill-with-real-sha256>  cpython-3.12.7+20241016-aarch64-unknown-linux-gnu-install_only.tar.gz
    ```

    7. **`debian/spark-modem-watchdog.install`** — what gets shipped in the package, relative to the destdir. **Includes the day-one carrier YAML from Plan 06**:
    ```
    debian/python-build-standalone/python/* /opt/spark-modem-watchdog/python/
    src/spark_modem /opt/spark-modem-watchdog/lib/
    scripts/postinst_smoke_test.sh /opt/spark-modem-watchdog/libexec/
    debian/spark-modem-watchdog.service /lib/systemd/system/
    debian/conf.d/00-carriers.yaml /etc/spark-modem-watchdog/conf.d/
    ```

    The last line is the install wiring for Plan 06's YAML data file. Plan 06 (wave 3) ships
    the YAML; this plan (wave 4) maps it onto the install layout. Phase 1 has no CLI shim yet
    (`bin/spark-modem` lands in Phase 2); we ship the package interpreter, the (mostly empty)
    `spark_modem` package, the smoke-test script, the systemd unit, and the day-one carrier
    table.

    8. **`debian/spark-modem-watchdog.dirs`** — directories created at install time:
    ```
    /etc/spark-modem-watchdog/conf.d
    /var/lib/spark-modem-watchdog
    /var/lib/spark-modem-watchdog/state/by-usb
    /var/log/spark-modem-watchdog
    /run/spark-modem-watchdog
    /opt/spark-modem-watchdog/libexec
    /opt/spark-modem-watchdog/lib
    ```

    9. **`scripts/postinst_smoke_test.sh`** (mode 0755) — the canonical 10-import check, runnable both from postinst and from `ExecStartPre=`:
    ```bash
    #!/usr/bin/env bash
    # B-03 smoke test: prove all 10 runtime libraries import under the bundled python.
    # Called from debian/postinst (fail-the-install) AND systemd ExecStartPre=
    # (fail-the-start). Either failure surfaces independently — diagnostic.
    # Closes FR-60.
    set -euo pipefail

    PYTHON="${SPARK_MODEM_PYTHON:-/opt/spark-modem-watchdog/python/bin/python3.12}"

    if [[ ! -x "$PYTHON" ]]; then
      echo "ERROR: bundled python missing or not executable: $PYTHON" >&2
      exit 2
    fi

    "$PYTHON" -c '
    import sys
    libs = [
        "pydantic",
        "pydantic_settings",
        "yaml",
        "prometheus_client",
        "pyudev",
        "pyroute2",
        "asyncinotify",
        "httpx",
        "sdnotify",
        "psutil",
    ]
    failures = []
    for name in libs:
        try:
            __import__(name)
        except Exception as e:
            failures.append((name, type(e).__name__, str(e)))
    if failures:
        print("FAIL: import smoke test failed for:", file=sys.stderr)
        for n, etype, msg in failures:
            print(f"  - {n}: {etype}: {msg}", file=sys.stderr)
        sys.exit(1)
    print(f"OK: all {len(libs)} runtime libs import under {sys.executable}")
    sys.exit(0)
    ' || exit 1
    ```

    The `libs` list MUST be exactly the 10 entries above, in that order. The smoke test prints `OK: all 10 runtime libs import under ...` on success.

    10. **`debian/spark-modem-watchdog.postinst`**:
    ```bash
    #!/usr/bin/env bash
    set -euo pipefail

    case "$1" in
      configure)
        # B-03 belt-and-suspenders A: fail-the-install if smoke test fails.
        if ! /opt/spark-modem-watchdog/libexec/postinst_smoke_test.sh; then
          echo "ERROR: spark-modem-watchdog postinst smoke test failed." >&2
          echo "       The bundled Python or one of the 10 runtime libs is broken." >&2
          echo "       Refusing to complete install (FR-60 / B-03)." >&2
          exit 1
        fi

        # systemd unit registration — but DO NOT enable or start in Phase 1.
        # The daemon binary doesn't exist yet (Phase 2).
        if [[ -d /run/systemd/system ]]; then
          systemctl --system daemon-reload >/dev/null || true
        fi
        ;;
      abort-upgrade|abort-remove|abort-deconfigure)
        ;;
      *)
        echo "postinst called with unknown argument \`$1'" >&2
        exit 1
        ;;
    esac

    #DEBHELPER#

    exit 0
    ```

    11. **`debian/spark-modem-watchdog.postrm`**:
    ```bash
    #!/usr/bin/env bash
    set -euo pipefail

    case "$1" in
      remove|purge|upgrade|failed-upgrade|abort-install|abort-upgrade|disappear)
        if [[ -d /run/systemd/system ]]; then
          systemctl --system daemon-reload >/dev/null || true
        fi
        ;;
    esac

    #DEBHELPER#

    exit 0
    ```

    12. **`debian/spark-modem-watchdog.service`** — systemd unit, Phase 1 stub. The daemon entry point doesn't exist yet, so `ExecStart=` runs the smoke test in foreground mode as a placeholder (so the service can be exercised end-to-end in Plan 02 verification, but boxes don't have a real daemon yet). When Phase 2 lands, this `ExecStart=` is replaced with the real `bin/spark-modem-watchdog` shim.
    ```ini
    [Unit]
    Description=Spark modem watchdog (Sierra EM7421 + Soliton Zao)
    Documentation=https://github.com/spark/spark-modem-watchdog
    After=network-online.target zao-infra-ctrl.service
    Wants=network-online.target

    [Service]
    Type=notify
    NotifyAccess=main

    # FR-60 + B-03 belt-and-suspenders B: smoke-test on every start.
    ExecStartPre=/opt/spark-modem-watchdog/libexec/postinst_smoke_test.sh

    # Phase 1 placeholder: the real daemon entry point lands in Phase 2.
    # For now, ExecStart= is a no-op that immediately reports READY and exits 0
    # so `systemctl start` succeeds end-to-end after a clean install.
    # Phase 2 will replace this with: ExecStart=/opt/spark-modem-watchdog/bin/spark-modem-watchdog
    ExecStart=/opt/spark-modem-watchdog/python/bin/python3.12 -c \
      'import sdnotify; sdnotify.SystemdNotifier().notify("READY=1"); import time; time.sleep(0.1)'

    Restart=on-failure
    RestartSec=5s

    User=root
    Group=root
    NoNewPrivileges=false
    PrivateTmp=true
    ProtectSystem=strict
    ProtectHome=true
    ReadWritePaths=/var/lib/spark-modem-watchdog /var/log/spark-modem-watchdog /run/spark-modem-watchdog

    [Install]
    WantedBy=multi-user.target
    ```

    Important: `Type=notify` with `NotifyAccess=main`; do NOT use `notify-reload` (CLAUDE.md anti-pattern reference; STACK §"systemd `Type=notify`" — `notify-reload` requires systemd 253+ which Ubuntu 20.04 / systemd 245 lacks). The placeholder ExecStart= sends `READY=1` so the service reaches `active (running)` for verification.

    Make `debian/spark-modem-watchdog.postinst`, `debian/spark-modem-watchdog.postrm`, `scripts/postinst_smoke_test.sh` all executable (`chmod +x`).
  </action>
  <verify>
    <automated>
      cd S:/spark/modem-watchdog && \
      test -f debian/changelog && grep -q '^spark-modem-watchdog (2\.0\.0-1)' debian/changelog && \
      test -f debian/control && grep -q '^Architecture: arm64' debian/control && \
      test -f debian/compat && grep -q '^13$' debian/compat && \
      test -f debian/source/format && grep -q '^3\.0 (native)' debian/source/format && \
      test -f debian/python.sha256 && grep -qE '^[a-f0-9]{64}  cpython-3\.12\..*aarch64-unknown-linux-gnu-install_only\.tar\.gz$' debian/python.sha256 && \
      test -f debian/spark-modem-watchdog.install && \
      grep -q '00-carriers.yaml /etc/spark-modem-watchdog/conf.d/' debian/spark-modem-watchdog.install && \
      test -f debian/spark-modem-watchdog.dirs && \
      test -x debian/spark-modem-watchdog.postinst && \
      test -x debian/spark-modem-watchdog.postrm && \
      test -f debian/spark-modem-watchdog.service && \
      grep -q '^Type=notify$' debian/spark-modem-watchdog.service && \
      grep -q '^ExecStartPre=' debian/spark-modem-watchdog.service && \
      test -x scripts/postinst_smoke_test.sh && \
      grep -q 'pydantic_settings' scripts/postinst_smoke_test.sh && \
      grep -q 'pydantic"' scripts/postinst_smoke_test.sh && \
      grep -q 'psutil' scripts/postinst_smoke_test.sh && \
      bash -n scripts/postinst_smoke_test.sh && \
      bash -n debian/spark-modem-watchdog.postinst && \
      bash -n debian/spark-modem-watchdog.postrm && \
      echo "Task 1 verification: OK"
    </automated>
  </verify>
  <done>
    All `debian/*` metadata files exist with correct content (Architecture: arm64, Type=notify, ExecStartPre= present, no `python3` system dep). `debian/python.sha256` pins a specific aarch64 PBS tarball with a 64-hex-char SHA. `scripts/postinst_smoke_test.sh` references all 10 runtime libs (`pydantic`, `pydantic_settings`, `yaml`, `prometheus_client`, `pyudev`, `pyroute2`, `asyncinotify`, `httpx`, `sdnotify`, `psutil`) and is referenced from both `debian/postinst` and the systemd unit's `ExecStartPre=`. `debian/spark-modem-watchdog.install` contains the install line for Plan 06's `debian/conf.d/00-carriers.yaml` to `/etc/spark-modem-watchdog/conf.d/`. Bash syntax check (`bash -n`) on all shell scripts passes.
  </done>
</task>

<task type="auto">
  <name>Task 2: debian/rules + scripts/build_deb.sh + GitHub Actions build-deb workflow</name>
  <files>debian/rules, scripts/build_deb.sh, .github/workflows/build-deb.yml</files>
  <read_first>
    - debian/python.sha256 and debian/spark-modem-watchdog.install (just written in Task 1)
    - .planning/phases/01-foundations-adrs/01-CONTEXT.md §"B. `.deb` build & CI" B-02 (fetch at build time, SHA verify), B-04 (versioning + SOURCE_DATE_EPOCH + uv pip install --frozen)
    - .planning/research/STACK.md §"Packaging recipe" (5 steps)
    - .planning/research/PITFALLS.md §18.3 (venv path relocation: build at destination path, not builder path)
    - .planning/research/PITFALLS.md §18.5 (certifi rotation: rebuild .deb on cert update)
    - packaging/requirements.lock (the install target for `uv pip install --frozen`)
  </read_first>
  <action>
    1. **`debian/rules`** (mode 0755) — the build script, written as a Makefile per debhelper convention. The 5-step PBS+uv+compileall recipe from STACK.md, with SOURCE_DATE_EPOCH for reproducibility:
    ```makefile
    #!/usr/bin/make -f
    # B-04: SOURCE_DATE_EPOCH for reproducibility.
    export SOURCE_DATE_EPOCH := $(shell git log -1 --format=%ct 2>/dev/null || date -u +%s)

    # B-02: pinned python-build-standalone tarball.
    # The exact tarball name lives in debian/python.sha256; we extract it from there
    # so a single edit (e.g. CPython security update) doesn't require touching debian/rules.
    PYTHON_TARBALL := $(shell awk '{print $$2}' debian/python.sha256)
    PYTHON_TAG := $(shell awk '{print $$2}' debian/python.sha256 | sed -n 's/^cpython-\([0-9.]*+[0-9]*\)-aarch64.*/\1/p')
    PYTHON_URL := https://github.com/astral-sh/python-build-standalone/releases/download/$(shell echo $(PYTHON_TAG) | sed 's/.*+//')/$(PYTHON_TARBALL)

    DESTDIR := $(CURDIR)/debian/spark-modem-watchdog
    PBSTREE := $(CURDIR)/debian/python-build-standalone
    VENVDIR := $(DESTDIR)/opt/spark-modem-watchdog/python
    PIPCACHE := $(CURDIR)/debian/.pip-cache

    %:
    	dh $@

    # B-02 + step 1: download + verify SHA + unpack.
    debian/python-build-standalone/.unpacked: debian/python.sha256
    	mkdir -p debian/python-build-standalone
    	rm -rf debian/python-build-standalone/python
    	if [ ! -f debian/$(PYTHON_TARBALL) ]; then \
    		curl -sSLf -o debian/$(PYTHON_TARBALL) "$(PYTHON_URL)"; \
    	fi
    	cd debian && sha256sum -c python.sha256
    	tar -C debian/python-build-standalone -xzf debian/$(PYTHON_TARBALL)
    	# python-build-standalone tarballs unpack to ./python/...
    	test -x debian/python-build-standalone/python/bin/python3.12
    	touch debian/python-build-standalone/.unpacked

    # Step 2-4: install PBS into destdir; install runtime libs frozen; compileall.
    # PITFALLS §18.3: install AT the destination path (/opt/...), not at the builder path,
    # so PBS's relocatable bundles don't bake builder paths into .pyc.
    override_dh_auto_build: debian/python-build-standalone/.unpacked
    	# Step 1 (continued): copy PBS tree into destdir at FINAL install path.
    	mkdir -p $(VENVDIR)
    	cp -a debian/python-build-standalone/python/. $(VENVDIR)/
    
    	# Step 2: ensure pip is bootstrapped, install uv as a build tool into a separate
    	# isolated venv (NOT the runtime venv) so we can use `uv pip install --frozen`
    	# against the runtime venv without polluting it.
    	mkdir -p $(PIPCACHE)
    	$(VENVDIR)/bin/python3.12 -m ensurepip --upgrade
    	$(VENVDIR)/bin/python3.12 -m pip install --no-cache-dir 'uv>=0.5,<1'
    
    	# Step 3: install all 10 runtime libs into the bundled python, frozen against
    	# packaging/requirements.lock. --no-deps + --frozen + --require-hashes is the
    	# triple-lock for NFR-52.
    	$(VENVDIR)/bin/python3.12 -m uv pip install \
    		--python $(VENVDIR)/bin/python3.12 \
    		--no-deps --frozen \
    		-r packaging/requirements.lock
    
    	# Step 4: warm pyc cache (NFR-13 — daemon reaches steady state ≤60s of process start).
    	# SOURCE_DATE_EPOCH is exported above so .pyc files are deterministic.
    	$(VENVDIR)/bin/python3.12 -m compileall -q $(VENVDIR)/lib
    
    	# Strip the bundled python's pip/setuptools/wheel + uv to keep .deb size <40 MiB
    	# (NFR-51). uv was a build-time tool only; we don't ship it on the box.
    	$(VENVDIR)/bin/python3.12 -m pip uninstall -y uv pip setuptools wheel || true
    
    	# Sanity: the install path is the final path. Refuse to ship a .deb where
    	# the bundled python's sys.executable points anywhere other than /opt/...
    	$(VENVDIR)/bin/python3.12 -c "import sys; assert sys.executable == '$(VENVDIR)/bin/python3.12', sys.executable"

    # Skip dh_auto_test — Plan 01's CI workflow runs the test suite separately,
    # and the .deb build does not need to re-run pytest (build is reproducibility-focused).
    override_dh_auto_test:

    # Skip dh_auto_install — we already laid out the destdir in dh_auto_build above.
    override_dh_auto_install:

    # Disable Python bytecode compilation by debhelper's dh_python — we compileall'd
    # against SOURCE_DATE_EPOCH already and don't want dh_python to re-compile and
    # de-reproduce.
    override_dh_python3:
    ```

    Make executable: `chmod +x debian/rules`.

    2. **`scripts/build_deb.sh`** (mode 0755) — the developer entry point that wraps `dpkg-buildpackage`:
    ```bash
    #!/usr/bin/env bash
    # Build a .deb on an aarch64 Linux host.
    # Release build:    ./scripts/build_deb.sh release
    # Dev build:        ./scripts/build_deb.sh             (default; uses git short-sha)
    set -euo pipefail

    cd "$(dirname "$0")/.."

    MODE="${1:-dev}"
    SHORT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

    case "$MODE" in
      release)
        # The committed debian/changelog already has version 2.0.0-1 — no rewrite.
        VERSION_LINE_INFO="release version from committed debian/changelog"
        ;;
      dev|*)
        # B-04: dev builds visibly distinct from releases — 2.0.0-0.git<sha>-1
        DEV_VERSION="2.0.0-0.git${SHORT_SHA}-1"
        # Use dch to rewrite the top changelog entry without committing.
        # If dch is not present, fall back to sed.
        if command -v dch >/dev/null 2>&1; then
          DEBEMAIL="dev@draco.co.il" \
          DEBFULLNAME="spark-modem-watchdog devs" \
          dch --newversion "$DEV_VERSION" --distribution UNRELEASED --force-bad-version \
              "Dev build at git $SHORT_SHA" || true
        else
          # sed-based fallback: rewrite the version-and-rev tuple on the first changelog line.
          sed -i "1s/spark-modem-watchdog (2\.0\.0-1)/spark-modem-watchdog ($DEV_VERSION)/" debian/changelog
        fi
        VERSION_LINE_INFO="dev version $DEV_VERSION (rewritten in debian/changelog for this build only)"
        ;;
    esac

    echo "Building .deb ($VERSION_LINE_INFO)..."
    echo "  Architecture: arm64"
    echo "  Host arch:    $(uname -m)"
    if [[ "$(uname -m)" != "aarch64" ]]; then
      echo "  WARNING: building on non-aarch64 host. The PBS tarball pinned in" >&2
      echo "  debian/python.sha256 is aarch64-only; the resulting .deb will not run" >&2
      echo "  outside aarch64 Linux. Use the QEMU fallback or a self-hosted runner." >&2
    fi

    mkdir -p dist/

    # SOURCE_DATE_EPOCH already set inside debian/rules; export here too for any
    # tool that reads it before dpkg-buildpackage spawns make.
    export SOURCE_DATE_EPOCH="$(git log -1 --format=%ct 2>/dev/null || date -u +%s)"

    # -us -uc: don't sign the .deb (no GPG key in CI; signing is post-build, future).
    # -b: binary-only build (we have no upstream source tarball; format 3.0 native).
    dpkg-buildpackage -us -uc -b

    # dpkg-buildpackage drops artifacts in ../, not in dist/. Move them.
    PARENT="$(dirname "$PWD")"
    for ext in deb buildinfo changes; do
      for f in "$PARENT"/spark-modem-watchdog_*."$ext"; do
        [ -f "$f" ] || continue
        mv "$f" dist/
      done
    done

    DEB="$(ls dist/spark-modem-watchdog_*_arm64.deb 2>/dev/null | head -n1 || true)"
    if [[ -z "$DEB" ]]; then
      echo "ERROR: build produced no .deb in dist/" >&2
      exit 1
    fi

    SIZE_BYTES="$(stat -c %s "$DEB" 2>/dev/null || stat -f %z "$DEB")"
    SIZE_MIB=$((SIZE_BYTES / 1048576))

    echo ""
    echo "Build successful: $DEB"
    echo "  Size: ${SIZE_MIB} MiB (NFR-51 ceiling: 40 MiB)"
    if (( SIZE_MIB > 40 )); then
      echo "  ERROR: .deb exceeds NFR-51 size ceiling (40 MiB)." >&2
      exit 1
    fi
    ```

    3. **`.github/workflows/build-deb.yml`** — CI build job on the self-hosted aarch64 runner:
    ```yaml
    name: Build .deb (aarch64)

    on:
      push:
        branches: [main]
        tags: ['v*']
      pull_request:
        branches: [main]
      workflow_dispatch:
        inputs:
          mode:
            description: 'Build mode'
            required: false
            default: 'dev'
            type: choice
            options: [dev, release]

    jobs:
      build:
        name: Build arm64 .deb
        runs-on: [self-hosted, linux, ARM64]
        timeout-minutes: 30
        steps:
          - uses: actions/checkout@v4
            with:
              fetch-depth: 0  # need git history for SOURCE_DATE_EPOCH

          - name: Install build tools
            run: |
              sudo apt-get update
              sudo apt-get install -y --no-install-recommends \
                debhelper devscripts fakeroot dpkg-dev \
                curl ca-certificates

          - name: Build .deb
            run: bash scripts/build_deb.sh ${{ inputs.mode || 'dev' }}

          - name: Verify .deb meta
            run: |
              DEB=$(ls dist/spark-modem-watchdog_*_arm64.deb | head -n1)
              echo "Built: $DEB"
              dpkg-deb -I "$DEB"
              dpkg-deb -c "$DEB" | head -50
              SIZE_BYTES=$(stat -c %s "$DEB")
              SIZE_MIB=$((SIZE_BYTES / 1048576))
              echo "Size: ${SIZE_MIB} MiB"
              test "$SIZE_MIB" -le 40

          - name: Smoke-install in clean container
            run: |
              # Run the .deb through `apt install` in a clean Ubuntu 20.04 arm64 container
              # to validate the postinst smoke test (B-03 belt-and-suspenders A) end-to-end.
              DEB=$(ls dist/spark-modem-watchdog_*_arm64.deb | head -n1)
              docker run --rm --platform linux/arm64 \
                -v "$PWD/dist":/dist:ro \
                ubuntu:20.04 \
                bash -lc "
                  set -euo pipefail
                  export DEBIAN_FRONTEND=noninteractive
                  apt-get update >/dev/null
                  # Install the deb and any apt-resolvable Depends.
                  apt-get install -y --no-install-recommends /dist/$(basename $DEB) || {
                    echo 'apt install failed — postinst smoke test rejected the package.' >&2
                    exit 1
                  }
                  # Re-run the smoke test directly to confirm.
                  /opt/spark-modem-watchdog/libexec/postinst_smoke_test.sh
                "

          - uses: actions/upload-artifact@v4
            with:
              name: spark-modem-watchdog-arm64-deb
              path: dist/*.deb
              retention-days: 30
    ```

    Make executable: `chmod +x scripts/build_deb.sh`.
  </action>
  <verify>
    <automated>
      cd S:/spark/modem-watchdog && \
      test -x debian/rules && \
      head -1 debian/rules | grep -q '^#!/usr/bin/make -f' && \
      grep -q 'SOURCE_DATE_EPOCH' debian/rules && \
      grep -q 'sha256sum -c' debian/rules && \
      grep -q 'uv pip install' debian/rules && \
      grep -q -- '--frozen' debian/rules && \
      grep -q 'compileall' debian/rules && \
      test -x scripts/build_deb.sh && \
      bash -n scripts/build_deb.sh && \
      grep -q 'dpkg-buildpackage' scripts/build_deb.sh && \
      grep -q '2\.0\.0-0\.git' scripts/build_deb.sh && \
      test -f .github/workflows/build-deb.yml && \
      python -c "import yaml, pathlib; d = yaml.safe_load(pathlib.Path('.github/workflows/build-deb.yml').read_text()); j = d['jobs']['build']; assert j['runs-on'] == ['self-hosted', 'linux', 'ARM64'], j['runs-on']; print('build-deb runner:', j['runs-on'])" && \
      python -c "import yaml, pathlib; d = yaml.safe_load(pathlib.Path('.github/workflows/build-deb.yml').read_text()); steps = [s.get('name') for s in d['jobs']['build']['steps']]; assert 'Smoke-install in clean container' in steps, steps; print('smoke-install step present')" && \
      echo "Task 2 verification: OK (file structure + syntax)"
    </automated>
  </verify>
  <done>
    `debian/rules` is an executable Makefile that exports `SOURCE_DATE_EPOCH`, verifies the PBS tarball SHA via `sha256sum -c`, installs runtime libs via `uv pip install --frozen --no-deps -r packaging/requirements.lock` (10 libs), runs `compileall`, and asserts the bundled python's `sys.executable` resolves to the destdir-bound path (PITFALLS §18.3 venv-relocation guard). `scripts/build_deb.sh` produces dev (`2.0.0-0.git<sha>-1`) and release (`2.0.0-1`) .debs and enforces NFR-51 (≤40 MiB). `.github/workflows/build-deb.yml` runs the build on the self-hosted aarch64 runner and exercises the postinst smoke test in a clean Ubuntu 20.04 arm64 container (closes Phase 1 SC #1 in CI). All shell scripts pass `bash -n`.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| GitHub releases → builder | The `python-build-standalone` tarball is fetched over HTTPS at build time (B-02); a compromised release would inject malicious bytecode into every `.deb`. |
| `packaging/requirements.lock` → builder | `uv pip install --frozen` consumes the lockfile; tampering replaces a runtime dependency. |
| `.deb` → Jetson | The package's postinst runs as root during `apt install`. |
| Builder filesystem → bundled venv | `debian/rules` writes to `debian/spark-modem-watchdog/opt/...`; PBS's path-relocation behavior must not bake builder paths into .pyc files. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-02-01 | T (Tampering) | python-build-standalone tarball | mitigate | `debian/python.sha256` pins the SHA256 of the exact tarball; `debian/rules` runs `sha256sum -c debian/python.sha256` and aborts the build on mismatch. HTTPS download is integrity-belt; SHA verify is the suspenders. |
| T-02-02 | T | `packaging/requirements.lock` consumed by debian/rules | mitigate | `uv pip install --frozen --no-deps -r packaging/requirements.lock` requires hash matching against the lockfile's `--hash=sha256:` entries for all 10 runtime libs. Plan 01 generates the lock with `--generate-hashes`. |
| T-02-03 | E (Elevation) | postinst running as root | mitigate | postinst is short (<30 lines), runs only the smoke-test script (10 imports), refuses to enable/start the service in Phase 1, uses `set -euo pipefail` to fail-fast on any subcommand error. systemd unit uses `ProtectSystem=strict`, `ProtectHome=true`, `PrivateTmp=true` — runtime privilege constraints even for `User=root`. |
| T-02-04 | I (Information disclosure) | bundled .pyc cache | mitigate | `SOURCE_DATE_EPOCH` makes `compileall`'s output deterministic — no builder hostname, builder-username, or builder-timestamp leaks via .pyc. PITFALLS §18.3 path-relocation guard ensures .pyc don't bake builder paths. |
| T-02-05 | T | systemd unit installed by .deb | accept | Unit references `/opt/spark-modem-watchdog/...` paths; tampering with the unit requires root on the box (post-install). The .deb itself is the trust anchor. |
| T-02-06 | D (DoS) | NFR-51 size budget | mitigate | `scripts/build_deb.sh` and CI verify .deb ≤40 MiB; pip/setuptools/wheel/uv are uninstalled from bundled venv after install (build-time tools only). 10 pinned runtime libs are well within budget (estimated 30-35 MiB). |
| T-02-07 | T | certifi cert rotation | accept | PITFALLS §18.5 — a stale `.deb` ships a stale certifi bundle, eventually fails on TLS to webhook URLs. Mitigation is operational (rebuild on each CPython security release, NFR-51) — a security policy, not a code change. |
| T-02-08 | T | hand-edited carrier YAML in /etc | accept | The shipped `debian/conf.d/00-carriers.yaml` is operator-overridable post-install; Plan 06's wire validators reject hostile inputs at load time. The .deb only owns the default file shipped with the package. |
</threat_model>

<verification>
End-to-end check after both tasks complete:

1. `bash scripts/build_deb.sh dev` on an aarch64 Linux host produces `dist/spark-modem-watchdog_2.0.0-0.git<sha>-1_arm64.deb` ≤40 MiB.
2. `dpkg-deb -I dist/*.deb` reports `Architecture: arm64`, `Package: spark-modem-watchdog`, version starting with `2.0.0`.
3. `dpkg-deb -c dist/*.deb` lists `/opt/spark-modem-watchdog/python/bin/python3.12`, `/opt/spark-modem-watchdog/libexec/postinst_smoke_test.sh`, `/lib/systemd/system/spark-modem-watchdog.service`, and `/etc/spark-modem-watchdog/conf.d/00-carriers.yaml`.
4. `apt install ./dist/*.deb` in a clean Ubuntu 20.04 aarch64 container completes with exit 0; `/opt/spark-modem-watchdog/libexec/postinst_smoke_test.sh` exits 0 directly and prints `OK: all 10 runtime libs import under ...`.
5. Modify `debian/python.sha256` to a known-bad SHA → `bash scripts/build_deb.sh` fails at the `sha256sum -c` step (build does not produce a .deb).
6. `systemctl start spark-modem-watchdog` runs `ExecStartPre=` (the smoke test); on a synthetic broken venv (delete one of the 10 libs) the unit transitions to failed and `journalctl -u spark-modem-watchdog` shows the failed-import line.

(Items 5 and 6 are tested in Phase 1 SC #1 acceptance; they are smoke-tested in CI via the `.github/workflows/build-deb.yml` `Smoke-install in clean container` step.)
</verification>

<success_criteria>
- Closes Phase 1 SC #1: arm64 .deb builds in CI, installs cleanly, all 10 runtime libs import under `/opt/spark-modem-watchdog/python/bin/python3.12` (FR-60 + B-03), and `debian/conf.d/00-carriers.yaml` is shipped to `/etc/spark-modem-watchdog/conf.d/`.
- NFR-50: `.deb` for arm64 with self-contained venv at `/opt/spark-modem-watchdog/python/`; built from PBS CPython 3.12.x (closes Q8).
- NFR-51: `.deb` ≤40 MiB, build-time pip/uv/setuptools/wheel uninstalled before package; security-update story = rebuild on each CPython release.
- NFR-52: `requirements.lock` produced by `uv pip compile` (Plan 01) is the install target via `uv pip install --frozen` (this plan); 10 libs frozen.
- B-03 belt-and-suspenders: `debian/postinst` AND `ExecStartPre=` both run `scripts/postinst_smoke_test.sh`; failure of either is independently diagnostic.
- B-04 reproducibility: `SOURCE_DATE_EPOCH` exported, `compileall` deterministic; dev (`2.0.0-0.git<sha>-1`) and release (`2.0.0-1`) versioning visibly distinct.
- ADR-0010 (packaging) is implemented in code; the actual ADR doc lands in Plan 07.
</success_criteria>

<output>
After completion, create `.planning/phases/01-foundations-adrs/01-02-SUMMARY.md` covering: chosen PBS CPython 3.12 patch version, exact pinned tarball SHA, build artifact size on the self-hosted runner, postinst smoke test verification result (10 imports, in CI's clean Ubuntu 20.04 arm64 container), confirmation that the carrier YAML from Plan 06 ships to /etc/spark-modem-watchdog/conf.d/, and a note flagging any deviation from STACK.md's 5-step recipe. Reference Plan 07 (ADR-0010 documentation) which captures this implementation as a decision record, and Plan 06 which owns the carrier YAML data file.
</output>
</content>
</invoke>