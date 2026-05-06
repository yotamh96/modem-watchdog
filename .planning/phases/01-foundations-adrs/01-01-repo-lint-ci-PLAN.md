---
phase: 01-foundations-adrs
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - pyproject.toml
  - packaging/requirements.lock
  - packaging/requirements.in
  - scripts/lint_no_subprocess.sh
  - .pre-commit-config.yaml
  - .github/workflows/ci.yml
  - src/spark_modem/__init__.py
  - tests/__init__.py
  - tests/unit/__init__.py
  - tests/integration/__init__.py
  - tests/hil/__init__.py
  - .gitignore
  - .ruff.toml
autonomous: true
requirements:
  - NFR-40
  - NFR-41
  - NFR-43
  - FR-72
  - FR-73
tags:
  - python
  - packaging
  - ci
  - lint

must_haves:
  truths:
    - "ruff check, ruff format --check, and mypy --strict all run cleanly on an empty src/spark_modem/ tree from CI"
    - "scripts/lint_no_subprocess.sh exits 0 when no subprocess.run / os.system / create_subprocess_exec usage exists outside src/spark_modem/subproc/"
    - "scripts/lint_no_subprocess.sh exits 1 when a violation is introduced anywhere else"
    - "packaging/requirements.lock is the output of `uv pip compile packaging/requirements.in` over the 10 pinned runtime libs and is reproducible"
    - "pre-commit hooks execute ruff format, ruff check, mypy --strict, and the no-subprocess lint gate"
    - "GitHub Actions workflow runs the same gates on push/PR on a self-hosted aarch64 runner (with QEMU runner as a fallback for non-self-hosted PRs)"
  artifacts:
    - path: "pyproject.toml"
      provides: "Single source of truth for project metadata, ruff/mypy/pytest config, and dependency declarations (PEP 621)"
      contains: "[project], [tool.ruff], [tool.mypy], [tool.pytest.ini_options], requires-python = \">=3.12\""
    - path: "packaging/requirements.lock"
      provides: "Frozen, hash-locked install manifest produced by `uv pip compile` over packaging/requirements.in"
      contains: "pydantic==, pydantic-settings==, PyYAML==, prometheus-client==, pyudev==, pyroute2==, asyncinotify==, httpx==, sdnotify==, psutil=="
    - path: "scripts/lint_no_subprocess.sh"
      provides: "SP-04 grep gate enforcing the subprocess wrapper boundary"
      contains: "create_subprocess_exec|subprocess\\.(run|Popen|call|check_(call|output))|os\\.system"
    - path: ".pre-commit-config.yaml"
      provides: "Pre-commit wiring for ruff format, ruff check, mypy --strict, and the no-subprocess gate"
      contains: "ruff-format, ruff, mypy, lint_no_subprocess"
    - path: ".github/workflows/ci.yml"
      provides: "CI pipeline running lint + types + lint_no_subprocess on self-hosted aarch64 runner"
      contains: "runs-on: [self-hosted, linux, ARM64]"
    - path: "src/spark_modem/__init__.py"
      provides: "Package root marker; otherwise empty in Plan 01"
      contains: "__version__ = \"2.0.0\""
  key_links:
    - from: "pyproject.toml [tool.ruff] and [tool.mypy]"
      to: "src/spark_modem/"
      via: "tool config target paths"
      pattern: "src/spark_modem"
    - from: ".pre-commit-config.yaml"
      to: "scripts/lint_no_subprocess.sh"
      via: "local hook entry"
      pattern: "scripts/lint_no_subprocess.sh"
    - from: ".github/workflows/ci.yml"
      to: "packaging/requirements.lock"
      via: "uv pip install --frozen --no-deps -r packaging/requirements.lock"
      pattern: "uv pip install --frozen"
---

<objective>
Establish the repository skeleton, dependency lock, and lint/typing/CI gates that every downstream Phase 1 plan depends on. After this plan, the next executor can run `pre-commit run --all-files` and `pytest --collect-only` and get green-on-empty.

Purpose: NFR-40 (`mypy --strict`, `ruff check`, `ruff format --check` green from day one), NFR-41 (hardware-free tests via fixtures), NFR-43 (lockfile reproducibility), FR-72 (Protocol-shaped seams will live under packages declared here), FR-73 (the lint gate that keeps the policy engine pure starts here via SP-04 grep).

Output: A workable Python project — `pyproject.toml` with ruff/mypy/pytest config, `packaging/requirements.lock` derived from a tracked `requirements.in`, `scripts/lint_no_subprocess.sh`, pre-commit, GitHub Actions on self-hosted aarch64 — plus the empty `src/spark_modem/` and `tests/{unit,integration,hil}/` skeleton that Plans 03–06 fill in.
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
@.planning/research/SUMMARY.md
@CLAUDE.md

<interfaces>
<!-- No code interfaces yet — this plan creates the project skeleton. -->
<!-- Pinned library set is the de-facto interface this plan must produce. -->

From .planning/research/STACK.md §"Pinned library set" + Plan 06's pydantic-settings dependency:
```text
pydantic            >=2.13,<3
pydantic-settings   >=2.5,<3
PyYAML              >=6.0.2,<7
prometheus-client   >=0.25,<1
pyudev              >=0.24.4,<1
pyroute2            >=0.9.6,<1
asyncinotify        >=4.0.10,<5
httpx               >=0.27,<1
sdnotify            >=0.3.2,<1
psutil              >=5.9,<7
```

10 pinned runtime libs. pydantic-settings is upstreamed here (rather than added by Plan 06)
because Plan 06's Settings class imports from pydantic_settings, and Plan 02's postinst
smoke test ships the canonical lib list — both consume this pin from Plan 01.

Dev deps (build-time only):
```text
ruff      >=0.6,<1
mypy      >=1.13,<2
pytest    >=8.3,<9
pytest-asyncio >=0.24,<1   # mode=auto
hypothesis     >=6.110,<7
pytest-cov     >=5,<7
uv             >=0.5,<1
```

From CLAUDE.md §"Stack snapshot":
- Runtime: CPython 3.12.x (PBS); requires-python = ">=3.12"
- pytest-asyncio mode = auto (NOT explicit per-test markers)
- Drop black; use `ruff format --check` only
- mypy --strict with no per-file overrides for new code
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Create pyproject.toml + dependency manifests + repo skeleton</name>
  <files>pyproject.toml, packaging/requirements.in, packaging/requirements.lock, .gitignore, .ruff.toml, src/spark_modem/__init__.py, src/spark_modem/py.typed, tests/__init__.py, tests/unit/__init__.py, tests/integration/__init__.py, tests/hil/__init__.py</files>
  <read_first>
    - .planning/research/STACK.md (full file — pinned library set, dev tools, packaging recipe)
    - .planning/phases/01-foundations-adrs/01-CONTEXT.md §"B. `.deb` build & CI" and §"Claude's Discretion" (`requirements.lock` location, repo layout)
    - CLAUDE.md §"Stack snapshot" (drop black, ruff format --check, pytest-asyncio mode=auto)
    - .planning/PROJECT.md §"Open questions" (Q8 closure: CPython 3.12)
  </read_first>
  <action>
    Create `pyproject.toml` (PEP 621) with:

    1. `[project]` section:
       - `name = "spark-modem-watchdog"`
       - `version = "2.0.0"`
       - `description = "Sierra EM7421 modem watchdog daemon for Soliton Zao bonded uplinks on NVIDIA Jetson Orin NX"`
       - `requires-python = ">=3.12"` (no upper bound; PBS ships 3.12 only for v2.0)
       - `readme = "README.md"` (file does not need to exist this plan; ruff will not flag missing readme)
       - `license = {text = "Proprietary"}`
       - `dependencies = []` — runtime deps live in `packaging/requirements.in`/`.lock`, NOT here. The `pyproject.toml` is the project metadata and tool config; the install manifest is the lockfile. (This split is per the CONTEXT.md "Claude's Discretion" — `packaging/requirements.lock` location.)

    2. `[project.optional-dependencies]` `dev`:
       ```
       ruff>=0.6,<1
       mypy>=1.13,<2
       pytest>=8.3,<9
       pytest-asyncio>=0.24,<1
       hypothesis>=6.110,<7
       pytest-cov>=5,<7
       ```

    3. `[build-system]`:
       ```
       requires = ["setuptools>=68", "wheel"]
       build-backend = "setuptools.build_meta"
       ```

    4. `[tool.setuptools.packages.find]` with `where = ["src"]` and `include = ["spark_modem*"]`.

    5. `[tool.ruff]`:
       - `line-length = 100`
       - `target-version = "py312"`
       - `src = ["src", "tests"]`
       - `extend-exclude = ["debian/", "packaging/"]`

       `[tool.ruff.lint]`:
       - `select = ["E", "F", "W", "I", "N", "UP", "B", "S", "ASYNC", "ANN", "RET", "SIM", "PTH", "PL", "RUF"]`
       - `ignore = ["S101", "PLR0913", "ANN401"]`  (S101 allows asserts in tests; PLR0913 too-many-args is overzealous; ANN401 allows `Any` where genuinely needed)

       `[tool.ruff.lint.per-file-ignores]`:
       - `"tests/**/*.py" = ["ANN", "S", "PLR2004"]`

       `[tool.ruff.format]`:
       - `quote-style = "double"`
       - `indent-style = "space"`

    6. `[tool.mypy]`:
       - `python_version = "3.12"`
       - `strict = true`
       - `warn_unreachable = true`
       - `warn_redundant_casts = true`
       - `warn_unused_ignores = true`
       - `disallow_any_generics = true`
       - `disallow_untyped_defs = true`
       - `disallow_incomplete_defs = true`
       - `check_untyped_defs = true`
       - `no_implicit_optional = true`
       - `extra_checks = true`
       - `mypy_path = "src"`
       - `packages = ["spark_modem"]`
       - `explicit_package_bases = true`

       `[[tool.mypy.overrides]]` for libraries that ship without stubs (Phase 1 needs only the lib subset that wire/state_store/subproc actually import; conservative list):
       ```
       module = ["sdnotify", "asyncinotify"]
       ignore_missing_imports = true
       ```

    7. `[tool.pytest.ini_options]`:
       - `minversion = "8.3"`
       - `testpaths = ["tests"]`
       - `asyncio_mode = "auto"`  (CLAUDE.md hard rule)
       - `addopts = ["-ra", "--strict-markers", "--strict-config", "--import-mode=importlib"]`
       - `markers = ["unit: hardware-free unit tests", "integration: laptop-runnable integration tests", "hil: hardware-in-the-loop tests requiring real Jetson"]`

    Create `packaging/requirements.in` with the **10 runtime libraries pinned per STACK.md (plus pydantic-settings for Plan 06's Settings class)** (one per line, with comments giving the FR/NFR justification):
    ```
    pydantic>=2.13,<3                # ADR-0004 wire formats
    pydantic-settings>=2.5,<3         # FR-54 Settings (env+flag layer; Plan 06)
    PyYAML>=6.0.2,<7                  # FR-54 layered config
    prometheus-client>=0.25,<1        # NFR-21 metrics over UDS
    pyudev>=0.24.4,<1                 # FR-1 USB add/remove
    pyroute2>=0.9.6,<1                # FR-1 rtnetlink (use AsyncIPRoute)
    asyncinotify>=4.0.10,<5           # FR-43.1 inotify watcher
    httpx>=0.27,<1                    # FR-44 webhook POST
    sdnotify>=0.3.2,<1                # FR-53 systemd Type=notify
    psutil>=5.9,<7                    # NFR-3 RSS tripwire
    ```

    Create `packaging/requirements.lock` by running:
    ```
    uv pip compile packaging/requirements.in --output-file packaging/requirements.lock --generate-hashes --python-version 3.12
    ```
    Commit the resulting hash-pinned lockfile verbatim. The lockfile MUST contain `--hash=sha256:` lines (per NFR-43 reproducibility) and MUST include all 10 runtime libs (verify with `grep -cE '^(pydantic|pydantic-settings|PyYAML|prometheus-client|pyudev|pyroute2|asyncinotify|httpx|sdnotify|psutil)==' packaging/requirements.lock` — expect 10).

    Create the `src/spark_modem/__init__.py` package with exactly:
    ```python
    """spark-modem-watchdog v2 — on-device modem-recovery daemon."""

    __version__ = "2.0.0"
    ```

    Create `src/spark_modem/py.typed` as an empty file (PEP 561 marker so downstream tooling sees this as a typed package).

    Create empty (one-line docstring) `__init__.py` files at `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/hil/__init__.py`.

    Create `.gitignore` covering: `__pycache__/`, `*.py[cod]`, `.mypy_cache/`, `.ruff_cache/`, `.pytest_cache/`, `htmlcov/`, `.coverage`, `dist/`, `build/`, `*.egg-info/`, `.venv/`, `venv/`, `*.deb`, `*.buildinfo`, `*.changes`, `debian/.debhelper/`, `debian/files`, `debian/spark-modem-watchdog/`, `debian/python-build-standalone/`.

    Create `.ruff.toml` as a minimal stub that re-exports the `[tool.ruff]` config from `pyproject.toml` (use `extend = "pyproject.toml"`); this makes editor tooling that doesn't support pyproject.toml ruff config still work. If the installed ruff version doesn't support `extend = "pyproject.toml"` (only newer versions do), instead omit `.ruff.toml` entirely and rely on pyproject.toml — verify with `ruff --version` first; the lock target ruff>=0.6 supports it.
  </action>
  <verify>
    <automated>
      cd S:/spark/modem-watchdog && \
      python -c "import tomllib, pathlib; d = tomllib.loads(pathlib.Path('pyproject.toml').read_text()); assert d['project']['requires-python'] == '>=3.12', d['project']['requires-python']; assert d['tool']['mypy']['strict'] is True; assert d['tool']['pytest']['ini_options']['asyncio_mode'] == 'auto'; print('pyproject.toml: OK')" && \
      grep -q '^pydantic>=2\.13,<3' packaging/requirements.in && \
      grep -q '^pydantic-settings>=2\.5,<3' packaging/requirements.in && \
      grep -q '^psutil>=5\.9,<7' packaging/requirements.in && \
      test -f packaging/requirements.lock && \
      grep -q -- '--hash=sha256:' packaging/requirements.lock && \
      grep -qE '^pydantic-settings==' packaging/requirements.lock && \
      test -f src/spark_modem/__init__.py && \
      test -f src/spark_modem/py.typed && \
      test -f tests/unit/__init__.py && \
      grep -q '__pycache__' .gitignore && \
      ruff check src/ tests/ && \
      ruff format --check src/ tests/ && \
      mypy --strict src/spark_modem/ && \
      echo "Task 1 verification: OK"
    </automated>
  </verify>
  <done>
    `pyproject.toml` parses as valid TOML and contains `requires-python = ">=3.12"`, `[tool.mypy] strict = true`, `[tool.pytest.ini_options] asyncio_mode = "auto"`. `packaging/requirements.in` lists all 10 runtime libs (pydantic, pydantic-settings, PyYAML, prometheus-client, pyudev, pyroute2, asyncinotify, httpx, sdnotify, psutil) with the STACK.md pins. `packaging/requirements.lock` exists with `--hash=sha256:` entries (NFR-43 reproducibility) and includes pydantic-settings. `src/spark_modem/__init__.py`, `py.typed`, and the four `tests/__init__.py` files exist. `ruff check`, `ruff format --check`, `mypy --strict` are all green on the empty source tree.
  </done>
</task>

<task type="auto">
  <name>Task 2: Wire pre-commit + scripts/lint_no_subprocess.sh + GitHub Actions self-hosted aarch64 CI</name>
  <files>scripts/lint_no_subprocess.sh, .pre-commit-config.yaml, .github/workflows/ci.yml, .github/workflows/ci-qemu-fallback.yml</files>
  <read_first>
    - .planning/phases/01-foundations-adrs/01-CONTEXT.md §"SP. Subprocess wrapper" SP-04 (the exact grep regex)
    - .planning/phases/01-foundations-adrs/01-CONTEXT.md §"B. `.deb` build & CI" B-01 (self-hosted aarch64 runner; QEMU acceptable as fallback only)
    - CLAUDE.md §"Anti-patterns" (full list — every entry SP-04 must catch must be in the regex)
    - .planning/research/STACK.md §"Pinned library set" (so the `uv pip install` step in CI uses the same constraint set as the lockfile)
    - pyproject.toml (just created in Task 1; verify the lint commands match this file's tool config)
    - packaging/requirements.in and packaging/requirements.lock (just created in Task 1)
  </read_first>
  <action>
    1. Create `scripts/lint_no_subprocess.sh` (mode 0755) with **exactly** this content:
    ```bash
    #!/usr/bin/env bash
    # SP-04: enforce that all subprocess invocation flows through src/spark_modem/subproc/.
    # Anti-pattern catalogue: subprocess.run, subprocess.Popen, subprocess.call,
    # subprocess.check_call, subprocess.check_output, asyncio.create_subprocess_exec,
    # asyncio.create_subprocess_shell, os.system. (CLAUDE.md §"Anti-patterns".)
    set -euo pipefail

    PATTERN='create_subprocess_exec|create_subprocess_shell|subprocess\.(run|Popen|call|check_call|check_output)|os\.system'

    # Collect violations: anything matching PATTERN inside src/, NOT under src/spark_modem/subproc/.
    VIOLATIONS=$(grep -rEn "$PATTERN" src/ \
      --include='*.py' \
      2>/dev/null \
      | grep -v '^src/spark_modem/subproc/' \
      || true)

    if [[ -n "$VIOLATIONS" ]]; then
      echo "ERROR: subprocess invocation outside src/spark_modem/subproc/" >&2
      echo "$VIOLATIONS" >&2
      echo "" >&2
      echo "All subprocess calls MUST go through src/spark_modem/subproc/runner.py (SP-04)." >&2
      exit 1
    fi

    exit 0
    ```

    Make it executable: `chmod +x scripts/lint_no_subprocess.sh`.

    2. Create `.pre-commit-config.yaml` with:
    ```yaml
    repos:
      - repo: https://github.com/astral-sh/ruff-pre-commit
        rev: v0.6.9
        hooks:
          - id: ruff-format
          - id: ruff
            args: [--fix, --exit-non-zero-on-fix]

      - repo: https://github.com/pre-commit/mirrors-mypy
        rev: v1.13.0
        hooks:
          - id: mypy
            additional_dependencies:
              - pydantic>=2.13,<3
            args: [--strict, --config-file=pyproject.toml]
            files: ^src/spark_modem/

      - repo: local
        hooks:
          - id: lint-no-subprocess
            name: SP-04 — no subprocess outside subproc/
            entry: scripts/lint_no_subprocess.sh
            language: script
            pass_filenames: false
            always_run: true

      - repo: https://github.com/pre-commit/pre-commit-hooks
        rev: v5.0.0
        hooks:
          - id: end-of-file-fixer
          - id: trailing-whitespace
          - id: check-yaml
            args: [--allow-multiple-documents]
          - id: check-toml
          - id: check-merge-conflict
    ```

    3. Create `.github/workflows/ci.yml` for the **self-hosted aarch64** primary path (B-01):
    ```yaml
    name: CI

    on:
      push:
        branches: [main]
      pull_request:
        branches: [main]
      workflow_dispatch:

    concurrency:
      group: ci-${{ github.ref }}
      cancel-in-progress: true

    jobs:
      lint-and-types:
        name: Lint + type-check (aarch64 self-hosted)
        runs-on: [self-hosted, linux, ARM64]
        timeout-minutes: 15
        steps:
          - uses: actions/checkout@v4

          - name: Install uv
            run: |
              curl -LsSf https://astral.sh/uv/install.sh | sh
              echo "$HOME/.local/bin" >> "$GITHUB_PATH"

          - name: Set up Python 3.12
            run: uv python install 3.12

          - name: Create venv and install dev deps
            run: |
              uv venv --python 3.12 .venv
              uv pip install --python .venv/bin/python -e ".[dev]"
              uv pip install --python .venv/bin/python --no-deps --frozen -r packaging/requirements.lock

          - name: ruff format --check
            run: .venv/bin/ruff format --check src/ tests/

          - name: ruff check
            run: .venv/bin/ruff check src/ tests/

          - name: mypy --strict
            run: .venv/bin/mypy --strict src/spark_modem/

          - name: SP-04 — no subprocess outside subproc/
            run: bash scripts/lint_no_subprocess.sh

          - name: pytest --collect-only (smoke)
            run: .venv/bin/pytest --collect-only -q

      tests:
        name: pytest (aarch64 self-hosted)
        runs-on: [self-hosted, linux, ARM64]
        needs: lint-and-types
        timeout-minutes: 15
        steps:
          - uses: actions/checkout@v4

          - name: Install uv
            run: |
              curl -LsSf https://astral.sh/uv/install.sh | sh
              echo "$HOME/.local/bin" >> "$GITHUB_PATH"

          - name: Set up Python 3.12 + venv
            run: |
              uv python install 3.12
              uv venv --python 3.12 .venv
              uv pip install --python .venv/bin/python -e ".[dev]"
              uv pip install --python .venv/bin/python --no-deps --frozen -r packaging/requirements.lock

          - name: pytest
            run: .venv/bin/pytest -m "unit or integration" -ra
    ```

    4. Create `.github/workflows/ci-qemu-fallback.yml` for the **QEMU fallback** path (B-01: backup runner, draft PRs from external contributors):
    ```yaml
    name: CI (QEMU fallback)

    on:
      workflow_dispatch:
      pull_request:
        branches: [main]
        types: [labeled]

    jobs:
      lint-qemu:
        if: github.event.label.name == 'ci-qemu' || github.event_name == 'workflow_dispatch'
        name: Lint + types (QEMU aarch64)
        runs-on: ubuntu-latest
        timeout-minutes: 30
        steps:
          - uses: actions/checkout@v4

          - uses: docker/setup-qemu-action@v3
            with:
              platforms: arm64

          - name: Run lint inside arm64 container
            run: |
              docker run --rm --platform linux/arm64 \
                -v "$PWD":/work -w /work \
                python:3.12-bookworm \
                bash -lc "
                  pip install --no-cache-dir uv &&
                  uv venv --python 3.12 .venv &&
                  uv pip install --python .venv/bin/python -e .[dev] &&
                  uv pip install --python .venv/bin/python --no-deps --frozen -r packaging/requirements.lock &&
                  .venv/bin/ruff format --check src/ tests/ &&
                  .venv/bin/ruff check src/ tests/ &&
                  .venv/bin/mypy --strict src/spark_modem/ &&
                  bash scripts/lint_no_subprocess.sh
                "
    ```

    Note: the QEMU workflow is gated on the `ci-qemu` label so it does not run on every PR (CONTEXT.md B-01: "QEMU emulation is acceptable as a backup runner for draft PRs from contributors who can't reach the self-hosted runner; not gating").
  </action>
  <verify>
    <automated>
      cd S:/spark/modem-watchdog && \
      test -x scripts/lint_no_subprocess.sh && \
      bash scripts/lint_no_subprocess.sh && \
      test -f .pre-commit-config.yaml && \
      python -c "import yaml, pathlib; d = yaml.safe_load(pathlib.Path('.pre-commit-config.yaml').read_text()); ids = [h['id'] for r in d['repos'] for h in r['hooks']]; assert 'ruff-format' in ids; assert 'ruff' in ids; assert 'mypy' in ids; assert 'lint-no-subprocess' in ids; print('pre-commit hooks:', ids)" && \
      test -f .github/workflows/ci.yml && \
      python -c "import yaml, pathlib; d = yaml.safe_load(pathlib.Path('.github/workflows/ci.yml').read_text()); j = d['jobs']['lint-and-types']; assert j['runs-on'] == ['self-hosted', 'linux', 'ARM64'], j['runs-on']; print('CI runner:', j['runs-on'])" && \
      test -f .github/workflows/ci-qemu-fallback.yml && \
      mkdir -p /tmp/sp04-violation-test && \
      printf 'import subprocess\nsubprocess.run(["echo","violation"])\n' > src/spark_modem/_violation_probe.py && \
      ! bash scripts/lint_no_subprocess.sh > /dev/null 2>&1 && \
      rm src/spark_modem/_violation_probe.py && \
      bash scripts/lint_no_subprocess.sh && \
      echo "Task 2 verification: OK (lint gate triggers on violation, clears when removed)"
    </automated>
  </verify>
  <done>
    `scripts/lint_no_subprocess.sh` is executable, exits 0 on a clean tree, and exits 1 when a `subprocess.run` is introduced outside `src/spark_modem/subproc/` (verified by injecting a violation, running the script, then removing the violation). `.pre-commit-config.yaml` registers ruff-format, ruff, mypy --strict, and the local `lint-no-subprocess` hook. `.github/workflows/ci.yml` targets `[self-hosted, linux, ARM64]` and runs ruff format/check, mypy --strict, the SP-04 gate, and pytest. `.github/workflows/ci-qemu-fallback.yml` exists and is gated on the `ci-qemu` label.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Repo → CI runner | Workflow YAML controls what code runs on the self-hosted aarch64 runner; a malicious PR could try to exfiltrate runner secrets. |
| Lockfile → installer | `packaging/requirements.lock` is consumed verbatim by `uv pip install --frozen`; tampering replaces a runtime dependency. |
| Pre-commit hook source | `.pre-commit-config.yaml` pins remote hook repos by SHA-tag; a compromised upstream could inject malicious lint commands. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-01-01 | T (Tampering) | `packaging/requirements.lock` | mitigate | `uv pip compile --generate-hashes` produces SHA256-pinned hashes per dependency for all 10 runtime libs; `uv pip install --frozen` verifies them at install time. Lockfile diffs in PR review surface unexpected dependency changes. |
| T-01-02 | E (Elevation) | `.github/workflows/ci.yml` self-hosted runner | mitigate | Workflow uses `pull_request` trigger which on GitHub does NOT pass repo secrets to PRs from forks (default behavior); concurrency group + `cancel-in-progress` limits resource abuse. Self-hosted runner is dev-controlled hardware, not a fleet box. |
| T-01-03 | T | Pre-commit hook upstream | accept | Hooks are pinned to specific tag revs (`v0.6.9`, `v1.13.0`, `v5.0.0`); a Renovate/Dependabot bump would surface in PR review. Low-value target (lint-only — no secrets accessed). |
| T-01-04 | I (Information disclosure) | CI logs | accept | Lint output may surface filenames; no production secrets exist in repo for Phase 1. Prom metrics socket creds, HMAC secret, etc. land in Phase 2 via `LoadCredential=` (NFR-34) — never in CI. |
| T-01-05 | T | `scripts/lint_no_subprocess.sh` | mitigate | Plain bash, ~15 lines, regex-only — no eval, no shell-string composition. `set -euo pipefail` ensures any subcommand failure surfaces. |
</threat_model>

<verification>
End-to-end check after both tasks complete:

1. `pre-commit run --all-files` exits 0 on the clean skeleton.
2. `ruff check src/ tests/`, `ruff format --check src/ tests/`, `mypy --strict src/spark_modem/`, `bash scripts/lint_no_subprocess.sh` all exit 0.
3. `python -c "import tomllib; tomllib.loads(open('pyproject.toml').read())"` parses without error.
4. `pytest --collect-only -q` reports zero tests collected (expected; no tests yet) and exits 0.
5. `cat packaging/requirements.lock | grep -c -- '--hash=sha256:'` returns ≥10 (one or more hash per dep — 10 pinned runtime libs).
6. `grep -cE '^(pydantic|pydantic-settings|PyYAML|prometheus-client|pyudev|pyroute2|asyncinotify|httpx|sdnotify|psutil)==' packaging/requirements.lock` returns 10.
7. The CI workflow YAML targets `[self-hosted, linux, ARM64]` (verified via `yq` or `python -c "import yaml; ..."`).
</verification>

<success_criteria>
- `mypy --strict`, `ruff check`, `ruff format --check` are green from day one (NFR-40 partially — full coverage when Plans 03–06 add code).
- `packaging/requirements.lock` is the `uv pip compile --generate-hashes` output of `packaging/requirements.in` over 10 pinned runtime libs and is reproducible (NFR-43 partially — full reproducibility lands in Plan 02 with `SOURCE_DATE_EPOCH`).
- `scripts/lint_no_subprocess.sh` (SP-04) is wired in pre-commit AND CI; injecting a violation triggers exit 1, removing it returns to exit 0.
- `tests/{unit,integration,hil}/__init__.py` exist so Plans 03–06 can drop tests in without scaffolding (NFR-41).
- `.github/workflows/ci.yml` runs the same gates on push/PR on the self-hosted aarch64 runner (B-01); the QEMU fallback exists but is label-gated.
- The dev-laptop test suite contract (M7 ≤30 s) is preserved: `pytest --collect-only` returns immediately on the empty tree.
</success_criteria>

<output>
After completion, create `.planning/phases/01-foundations-adrs/01-01-SUMMARY.md` covering: pyproject.toml structure, lockfile generation command + result (10 pinned runtime libs including pydantic-settings), pre-commit hooks list, CI runner targets, and the SP-04 violation/non-violation verification. Reference the next plan: this scaffolding gates Plans 03–06 (and indirectly Plan 02, which consumes `packaging/requirements.lock`).
</output>
</content>
</invoke>