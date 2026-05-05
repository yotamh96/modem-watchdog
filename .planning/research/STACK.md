# Stack Research — spark-modem-watchdog v2

**Domain:** Long-running root-privileged single-process asyncio daemon on aarch64 Linux (NVIDIA Jetson Orin NX, Ubuntu 20.04 / L4T R35.6.4, kernel 5.10-tegra)
**Researched:** 2026-05-05
**Overall confidence:** HIGH for library versions, HIGH for Python-version recommendation, MEDIUM for packaging tool choice (the field has shifted under us).

This document is **opinionated**. Where the docs/ proposal stands up against current reality, we say so and pin versions. Where it does not, we say what to change and why.

---

## Executive recommendation (TL;DR)

1. **Bundle CPython 3.12.x in the .deb venv via `astral-sh/python-build-standalone`** — do NOT use deadsnakes (focal is unsupported as of April 2025), do NOT compile from source on the build host, do NOT drop to Python 3.8. ADR-0001's "ship the runtime we tested with" stance is correct; the implementation tactic just changed.
2. **Pin pydantic to `>=2.13,<3` and target Python 3.12.** pydantic dropped 3.8 support in v2.11 (March 2025). Target the most recent CPython that python-build-standalone publishes prebuilt and that pydantic-core wheels exist for — **3.12** today, not 3.13 (free-threaded transition risk) and not 3.11 (no longer the latest stable).
3. **Replace `dh-virtualenv` with a hand-rolled `debhelper` rule that drops `python-build-standalone` + a `uv`-installed venv into `/opt/spark-modem-watchdog/`.** dh-virtualenv assumes a system Python you can re-use; we are deliberately NOT re-using one. Rolling our own is ~80 lines of shell and removes a moribund dependency.
4. **Add `httpx` for webhooks** (not stdlib `urllib.request`, not `requests`, not `aiohttp`). The docs/ tech-stack table is silent on webhooks; this is a gap.
5. **Adopt `mypy --strict` as the gate, but run `pyright` in editor.** The docs/ proposal says mypy; keep it. mypy's stricter inference around `Any` propagation matches our policy-engine purity goal better than pyright's friendlier-but-looser defaults.
6. **Drop `black`; use `ruff format` only.** The docs/ proposal already hedges with "configured-as-ruff-format" — make it explicit.

Confidence on each above: 1=HIGH, 2=HIGH, 3=MEDIUM, 4=HIGH, 5=MEDIUM, 6=HIGH.

---

## Python 3.8.10 vs 3.11+ resolution

**Recommendation: bundle CPython 3.12.x in the .deb venv. Confidence: HIGH.**

### Why this is the only good answer

The PRD and ADR-0001 already say "we ship the runtime we tested with" and call out a venv at `/opt/spark-modem-watchdog/lib/python3.11/...`. The only open question was *how* to source that interpreter. Three options were on the table; only one survives 2026-reality.

| Option | Verdict | Reason |
|--------|---------|--------|
| **A. Bundle 3.11+ in the venv** | **CHOSEN** | Honors ADR-0001's intent. `python-build-standalone` solves the supply problem. |
| B. Drop to Python 3.8 code | REJECTED | pydantic v2.11 dropped 3.8 (March 2025); pydantic v2.13 (latest) requires ≥3.9. We'd be pinned to a 14-month-old pydantic and would lose match statements, TaskGroup, tomllib, parameterized typing.Self, and `from __future__ import annotations` deferred eval cleanly. Cost benefit: terrible. |
| C. Upgrade Jetson system Python via deadsnakes | REJECTED — deadsnakes does not support focal anymore | Ubuntu 20.04 standard support ended 31 May 2025; deadsnakes deletes packages on EOL (precedent: 18.04 in April 2023). Even on Ubuntu Pro ESM (which keeps the *3.8 package* alive through 2030–2032), deadsnakes itself does not publish 3.11+ for focal. |

### Sourcing the bundled interpreter

Use **`astral-sh/python-build-standalone`** (formerly `indygreg/python-build-standalone`; stewardship transferred to Astral on 2024-12-17 and the release cadence is now automated and reliable). This is the same project `uv` uses to install Python.

Concrete plan:

- Asset: `cpython-3.12.<patch>+<datetag>-aarch64-unknown-linux-gnu-install_only.tar.gz`
- Baseline glibc: **2.17**. Ubuntu 20.04 ships glibc 2.31. Comfortable margin (no risk of "not found" against tegra).
- Build host: any Linux x86_64 or arm64 with internet at *build* time. Constraint C20 (offline at install) is satisfied because the .deb bundles the interpreter.
- Why `gnu` and not `musl`: glibc is what the Jetson runs; staying on glibc keeps `ctypes`, `pyudev` (which dlopens libudev.so.1), and any C extensions consistent with the host.

### Why 3.12 specifically (not 3.11, not 3.13, not 3.14)

- **Not 3.11**: It's been the team's mental anchor, but it's already two minors behind 3.14. Migrating to 3.12 now (pre-Phase-0) is cheaper than migrating later.
- **3.12 (RECOMMENDED)**: PEP 695 type parameter syntax, per-interpreter GIL groundwork, real `tomllib`, sys.monitoring (cheap profiling), TaskGroup matured, BOLT-optimized binaries from python-build-standalone. Every wheel we depend on (pydantic-core 2.x, prometheus-client 0.25, pyudev 0.24, pyroute2 0.9.6) ships aarch64 wheels for 3.12.
- **Not 3.13**: free-threaded build complexity and slightly thinner wheel ecosystem on aarch64 (some C extensions still building). For a daemon where stability matters more than novelty, wait one cycle.
- **Not 3.14**: in beta/RC as of May 2026; not appropriate for a production rewrite.

### What in docs/ specifically would break under 3.8 (the rejected option)

For the record, since this was an open question (Q8), here is the survey of what 3.8-compat would cost:

| docs/ pattern | Min Python | Workaround on 3.8 |
|---------------|-----------|-------------------|
| `match` statements (RECOVERY_SPEC, policy engine) | 3.10 | Rewrite as `if/elif`. Verbose but works. |
| `asyncio.TaskGroup` (ARCH §4.3 — implied for per-modem `gather`) | 3.11 | The `taskgroup` PyPI backport works on 3.8–3.11. Acceptable but extra dep. |
| `asyncio.timeout` context manager | 3.11 | `async-timeout` library. Acceptable. |
| `tomllib` (potential pyproject.toml reads) | 3.11 | `tomli` library. Acceptable. |
| `typing.Self`, `Literal` discriminated unions on assignment | 3.11 / 3.10 | `typing_extensions`. Acceptable. |
| `from __future__ import annotations` quirks under pydantic v2 | n/a | pydantic v2 with deferred annotations works on 3.9+; on 3.8 you hit `ForwardRef._evaluate` signature mismatches in some chains. |
| `pydantic` v2.11+ | **≥3.9** | **No workaround. Pin to v2.10.x and never upgrade. Hard NO.** |
| `prometheus_client` 0.22+ | **≥3.9** | Pin to 0.21.x. Possible but pointless. |
| `pyudev` 0.24+ | **≥3.9** | Pin to 0.24.0 (the last 3.8-compatible one). Possible. |
| `pyroute2` latest | **≥3.9** | Pin to 0.7.x. Possible. |
| Parameterized generic builtins `list[int]` at *runtime* | 3.9 (via `__future__`) / 3.10 (no `__future__`) | Use `from __future__ import annotations` everywhere; pydantic v2 still works because it treats annotations as strings. |

The deal-breaker is the pydantic ceiling alone. Everything else has a workaround; pydantic v2.11+ does not. Locking to a year-old pydantic for the 5-year fleet life of v2 is the worst of both worlds.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| **CPython** | **3.12.x** (latest patch at build time) | Language runtime | ADR-0001 dictates a typed-language rewrite; 3.12 is the lowest-cost target that all dependencies fully support. Sourced via `python-build-standalone` aarch64-gnu builds. |
| **asyncio** (stdlib) | n/a (3.12 stdlib) | Concurrency | Single-process IO-bound daemon. ARCH §4.3 already commits. No reason to add `trio`/`anyio`. |
| **pydantic** | `>=2.13,<3` | Wire-format types, config validation | ADR-0004 mandates typed contracts with closed enums + tagged unions + `schema_version` checks. v2.13 is current (April 2026). Cap at `<3` because v3 will likely change the model API. |
| **pydantic-core** | matched to pydantic 2.13 | Rust-backed validator | Comes transitively. Wheels exist for `aarch64-manylinux_2_17` (matches our glibc). No special action. |
| **PyYAML** | `>=6.0.2,<7` | Config loading | Stdlib-quality, ubiquitous; FR-54 layered config loads YAML. C-extension wheels for aarch64 exist. |
| **prometheus-client** | `>=0.25,<1` | Metrics over Unix socket | NFR-21 requires Prom scrape. Pure-python, supports `make_wsgi_app` over a UDS via custom server (we'll wrap with stdlib `socket` + `wsgiref` or `aiohttp.web`). |
| **pyudev** | `>=0.24.4,<1` | udev add/remove subscription | Pure-python ctypes binding to `libudev.so.1`; needs libudev ≥151 (Ubuntu 20.04 ships 245 — fine). FR-1, ARCH §8. |
| **pyroute2** | `>=0.9.6,<1` | rtnetlink link-state events | The rtnetlink event source for ARCH §8 "Link state change". Pure-Python, no compiler at install time. |
| **httpx** | `>=0.27,<1` | Webhook POST (FR-44) | Replaces the docs/ silence on this point. Has both sync and async clients with the same surface; supports HTTP/2; explicit timeouts; built-in retries via transports. Clean asyncio integration. |
| **systemd-python** OR **sdnotify** | systemd-python `>=235`; sdnotify `>=0.3.2` | `Type=notify` readiness | FR-53 says systemd `Type=notify`. `sdnotify` is the lighter, pure-Python option (just sends `READY=1` over `$NOTIFY_SOCKET`). Prefer it; `systemd-python` pulls a system C library and is overkill. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| **inotify_simple** | `>=1.3.5,<2` | inotify on Zao log + kmsg reader's rotation handling | ARCH §8 inotify-on-Zao-log; ADR-0002 event sources. Tiny ctypes wrapper, no deps. Alternative: `asyncinotify` (asyncio-native) — equivalent quality, choose based on whether you want sync-thread or asyncio-task event consumption. **Pick `asyncinotify` (`>=4.0.10,<5`) since the rest of the daemon is asyncio.** |
| **asyncinotify** | `>=4.0.10,<5` | asyncio inotify | See above. Replaces `inotify_simple` in our case. |
| **dbus-next** OR **jeepney** | dbus-next `>=0.2.3`; jeepney `>=0.9.0` | systemd unit-state watching (deferred / optional, ARCH §8) | Only needed if Q4/Q6 land on "watch zao-infra-ctrl.service via dbus". Recommend **`jeepney` >=0.9.0** — purer asyncio integration, more recent active development, used by `secretstorage` and `keyring` in Debian. dbus-next still works but its release cadence has slowed. *Defer: not v2.0-required.* |
| **psutil** | `>=5.9,<7` | Process self-stats (RSS for the NFR-3 budget tripwire) | NFR-3 says ≤80 MiB; the daemon should self-report and trip if it crosses. psutil is the canonical aarch64-supported stdlib-quality wrapper. |
| **tomli** | n/a — use stdlib `tomllib` (Python 3.11+) | TOML reads (pyproject.toml only, not config) | We're on 3.12, so no dep. Listed only to confirm it's NOT needed. |
| **typing-extensions** | `>=4.12` | Forward-compatible typing helpers | Even on 3.12, pydantic transitively requires it. Don't pin yourself; let pydantic pull the right minor. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| **ruff** | Lint + format | Replaces flake8 + black + isort + pyupgrade. Configure `format` profile = black-equivalent. Pin `>=0.6,<1`. |
| **mypy** (`--strict`) | Type check (CI gate) | NFR-40. Pin `>=1.13,<2`. mypy's stricter `Any` propagation rules suit a policy-engine that must be pure. |
| **pyright** (developer-only, optional) | Editor/IDE feedback | Faster incremental check during development. **Not** the CI gate (would create dual-source-of-truth fights). Not required to be installed. |
| **pytest** | Test runner | Pin `>=8.3,<9`. |
| **pytest-asyncio** | asyncio test support | Pin `>=0.24,<1`. Use `mode = "auto"` in pyproject. |
| **hypothesis** | Property tests (per TEST_STRATEGY §5) | Pin `>=6.110,<7`. |
| **pytest-cov** | Coverage | Pin `>=5,<7`. |
| **uv** | Package install during build | Astral's installer; ~10× faster than pip; consistent lockfile. Used at build time only, not at runtime on the box. Pin `>=0.5,<1`. |
| **debhelper** + custom rules | .deb assembly | See "Packaging" section. |
| **lintian** | Debian policy lint (TEST_STRATEGY §6) | System tool; install on CI host. |

### Tools and libraries we are explicitly REPLACING vs the docs/ proposal

| docs/ proposal | Replace with | Why |
|----------------|-------------|-----|
| `black` (alongside ruff) | `ruff format` only | The docs/ table already says "configured-as-ruff-format". Drop black entirely. One tool, one config. |
| Implicit `requests` for webhooks | `httpx` | docs/ doesn't actually pick a webhook lib, but `requests` is the obvious default. `requests` is sync-only; calling it from the asyncio loop blocks. `httpx` has a real async client. |
| `dh-virtualenv` (implied by §14 "venv at /opt/spark-modem-watchdog/") | Custom debhelper rule using `python-build-standalone` + `uv pip install` | dh-virtualenv assumes a system Python interpreter; we are deliberately not using one. Last dh-virtualenv release is 1.2.2 (mid-2022), 1.2.4 in 2024 in some forks; cadence has slowed. Rolling our own is ~50 lines of `debian/rules` and removes a fragile dependency on someone else's Python-build assumptions. |
| `pip` (implicit) for installing into venv | `uv pip install --no-deps -r requirements.lock` | Faster, deterministic, lockfile-driven. Keeps build reproducible. |
| `subprocess` (sync) anywhere | `asyncio.subprocess` everywhere | docs/ already says this; calling it out for emphasis since Phase 0 will be tempted to shim it. |

---

## Packaging recipe (the .deb)

> The docs/ proposal calls for "a Debian `.deb` containing a venv under `/opt/spark-modem-watchdog/`" but does not specify the toolchain. Phase 0 will commit to one. Here is the recipe.

**Layout produced** (matches ARCH §6 verbatim):

```
/opt/spark-modem-watchdog/
├─ python/                              ← unpacked python-build-standalone
│  ├─ bin/python3.12
│  ├─ lib/python3.12/...
│  └─ ...
├─ venv/                                ← venv created with /opt/.../python/bin/python3.12 -m venv
│  └─ lib/python3.12/site-packages/...
├─ bin/spark-modem                      ← shim: exec /opt/.../venv/bin/spark-modem "$@"
├─ libexec/spark-modem-watchdog         ← shim: exec /opt/.../venv/bin/spark-modem-watchdog "$@"
└─ share/{default-config.yaml, carriers/il.yaml, systemd/, logrotate/}
```

**Build steps (`debian/rules`):**

1. Download `cpython-3.12.x+YYYYMMDD-aarch64-unknown-linux-gnu-install_only.tar.gz` (pinned by SHA256 in `debian/python.sha256`). Unpack to `debian/spark-modem-watchdog/opt/spark-modem-watchdog/python/`.
2. `/opt/.../python/bin/python3.12 -m venv /opt/.../venv` (called against the destdir).
3. `uv pip install --python /opt/.../venv/bin/python --no-deps -r requirements.lock` (the project itself + frozen deps).
4. `python -m compileall` for faster cold-start (helps NFR-13).
5. Strip __pycache__ duplicates if size matters (it shouldn't — tegra has plenty).
6. Generate the two `bin/` shim scripts.
7. Install systemd unit, default config, logrotate snippet, post-install hook (creates `/var/lib/...`, `/var/log/...`, `/run/...` with FR-61-mandated modes).

**Estimated .deb size**: ~30–35 MiB (python-build-standalone install_only is ~25 MiB unpacked + pydantic-core wheel ~3 MiB + everything else ~3 MiB). Acceptable for a fleet that already ships JetPack images of multi-GiB.

**Security update story**: the bundled interpreter does NOT receive Ubuntu security updates. We accept this and own it: we rebuild the .deb when a CPython security release lands (release cadence: 4–6× per year on stable branches). This is the same model uv users have lived with for 18 months. The alternative (system Python on focal) leaves us on Python 3.8 PSF-EOL for free.

**Why not dh-virtualenv**:

- It assumes you start from `/usr/bin/python3` and creates a venv. We don't have a 3.12 system python.
- Workaround would be: install python-build-standalone *into* the build host, point dh-virtualenv at it, hope it does the right thing with the rpath shenanigans. This is more fragile than just doing the dance ourselves.
- dh-virtualenv last release on the canonical Spotify repo is 1.2.2 (2022). It still works, but the maintenance pulse is shallow.

**Why not pex / shiv / pyinstaller**:

- pex/shiv produce a single zip archive with a __main__. They want the *system* python at runtime. We don't have one.
- pyinstaller produces a fat binary with bundled CPython, but its bundling is more brittle than a plain venv (relative imports, ctypes path discovery for libudev, etc.). For a daemon with native deps and ctypes lookups (pyudev), a plain venv is more debuggable.

**Why not uv standalone (`uv tool install`)**:

- `uv tool` is great for user-level developer tools. It's not a fleet-deployment story. We need a `.deb` for `apt install` and unattended provisioning. uv is a *build-time* tool here.

Confidence on the full packaging recipe: **MEDIUM**. The pieces are all proven; the integration is bespoke. Phase 0 should produce a working `.deb` end-to-end before anything else.

---

## Comparison with docs/ proposal

| Concern | docs/ proposal (ARCH §5, ADR-0001, ADR-0004) | This research's recommendation | Delta |
|---------|----------------------------------------------|-------------------------------|-------|
| Language | Python 3.11+ | **Python 3.12.x** (specific) | Move target one minor up. 3.11 is fine technically but 3.12 has matured wheels and is what we'd pick today. |
| Async runtime | `asyncio` (stdlib) | `asyncio` (stdlib) | Same. |
| Wire types | `pydantic` v2 | `pydantic >=2.13,<3` | Same library, version pinned to range. |
| Config | `PyYAML`, layered with env + flags | `PyYAML >=6.0.2,<7`, layered with env + flags | Same; pinned. |
| Subprocess | stdlib `asyncio.subprocess` | stdlib `asyncio.subprocess` | Same. |
| QMI parsing | In-house wrapper over `qmicli` text | In-house wrapper over `qmicli` text | Same. **Note**: libqmi 1.30.4 in focal-updates is the maintained version we wrap. |
| Logging | stdlib `logging` + JSON formatter | stdlib `logging` + JSON formatter | Same. Suggest `python-json-logger` (`>=3.1`) or hand-rolled (~30 lines). Either is fine; hand-rolled keeps deps minimal. |
| Metrics | `prometheus_client` over Unix socket | `prometheus_client >=0.25,<1` over Unix socket | Same; pinned. |
| Webhook HTTP | (not specified) | `httpx >=0.27,<1` | **Gap filled**: docs is silent. Pick httpx, async client, explicit timeout, retry transport. |
| systemd notify | `Type=notify` (FR-53) | `sdnotify >=0.3.2` (pure-Python) | **Gap filled**: docs picks the *contract* but not the library. sdnotify keeps deps light. |
| Tests | `pytest`, `pytest-asyncio` | `pytest >=8.3,<9`, `pytest-asyncio >=0.24,<1`, `hypothesis >=6.110,<7` | Same + pinned + hypothesis explicitly listed (TEST_STRATEGY mentions it but tech-stack table doesn't). |
| Lint/format | `ruff`, `black` ("configured-as-ruff-format") | `ruff >=0.6,<1` only; **drop black** | Simplification. The hedge in docs is unnecessary; ruff format is stable. |
| Type-check | `mypy --strict` | `mypy >=1.13,<2 --strict` | Same; pinned. pyright optional in editor; not in CI. |
| Packaging | "Debian `.deb` with venv at `/opt/spark-modem-watchdog/`" | python-build-standalone + uv + custom debhelper rule | **Method specified**. The docs/ goal is correct; the implementation tactic is novel and worth a short ADR. |
| Init | systemd `Type=notify` | systemd `Type=notify` + `Restart=on-failure` + `LoadCredential=` (NFR-34) | Same. |
| udev events | `pyudev` (ARCH §8) | `pyudev >=0.24.4,<1` | Same; pinned. |
| rtnetlink | `pyroute2` (ARCH §8) | `pyroute2 >=0.9.6,<1` | Same; pinned. |
| inotify | (not specified by name) | `asyncinotify >=4.0.10,<5` | **Gap filled**. asyncinotify > inotify_simple for an asyncio daemon. |
| dbus (optional) | "`dbus` if available, else polled" (ARCH §8) | **Defer**. If implemented later, prefer `jeepney >=0.9.0`. | Deferred to v2.1; not on critical path. |
| /dev/kmsg | (custom reader implied, ARCH §8) | Custom reader; no library needed | Confirmed. `/dev/kmsg` is a 60-line custom reader; no library buys us anything. |
| psutil | (not specified) | `psutil >=5.9,<7` for self-RSS tripwire (NFR-3) | **Gap filled**. Optional but valuable. |

---

## Installation (developer setup)

```bash
# One-time on dev laptop
curl -LsSf https://astral.sh/uv/install.sh | sh         # uv (fast pip)
uv python install 3.12                                   # ← same artifact that production gets

# Project bootstrap
cd spark-modem-watchdog
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e '.[dev]'
```

`pyproject.toml` deps (canonical pin set, edit in lockstep):

```toml
[project]
name = "spark-modem-watchdog"
requires-python = ">=3.12,<3.13"
dependencies = [
    "pydantic>=2.13,<3",
    "PyYAML>=6.0.2,<7",
    "prometheus-client>=0.25,<1",
    "pyudev>=0.24.4,<1",
    "pyroute2>=0.9.6,<1",
    "asyncinotify>=4.0.10,<5",
    "httpx>=0.27,<1",
    "sdnotify>=0.3.2,<1",
    "psutil>=5.9,<7",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3,<9",
    "pytest-asyncio>=0.24,<1",
    "pytest-cov>=5,<7",
    "hypothesis>=6.110,<7",
    "mypy>=1.13,<2",
    "ruff>=0.6,<1",
]
```

`requirements.lock` (frozen for the .deb) generated via `uv pip compile pyproject.toml -o requirements.lock` against a python-build-standalone 3.12 interpreter on the build host.

---

## What NOT to use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Python 3.8 system interpreter on Jetson | PSF-EOL October 2024; pydantic dropped support v2.11 (March 2025); locks us out of every modern wheel-cycle improvement | Bundle CPython 3.12 via python-build-standalone in the .deb |
| deadsnakes PPA on Ubuntu 20.04 | Focal is unsupported by deadsnakes since April 2025 (after Ubuntu standard support ended) | python-build-standalone |
| Compile CPython from source on the Jetson | Build toolchain on a production box is a bad smell; build slow on Orin NX; reproducibility hard | python-build-standalone (pre-built, deterministic) |
| `requests` library for webhooks | Sync-only; calling from asyncio loop blocks the cycle (kills NFR-1's 10s budget under any network hiccup) | `httpx` async client |
| `aiohttp` for client-only webhook usage | Brings a server framework we don't need; bigger surface area | `httpx` |
| `subprocess.run` (sync) anywhere in the daemon | Blocks the asyncio loop. Even for "fast" calls like `ip netns exec`, a hung qmicli process can stall everything. | `asyncio.subprocess` exclusively (already in ARCH §4.3) |
| `urllib.request` for webhooks | Synchronous, no timeout-by-default, no retries, no HTTPS verification niceties | `httpx` |
| `black` alongside `ruff` | Two formatters fighting; needless dep | `ruff format` only |
| `pip-tools` / Poetry / Hatch / PDM for build | All work, but `uv` is faster and Astral-stable; aligns with the python-build-standalone choice | `uv` |
| Threads for QMI parallelism | NFR-4 says parallel; ARCH §4.3 says asyncio.gather. Threads add GIL+lock complexity. | `asyncio.gather` with per-task timeout |
| Generic `python-dbus` (the dbus-python C-extension) | Pulls glib; awkward in asyncio; legacy | `jeepney` if/when needed |
| `pkg_resources` for runtime introspection | Deprecated, slow at startup | `importlib.metadata` (stdlib) |
| Typed-dict-only state shapes (instead of pydantic models) | TypedDict gives no runtime validation; ADR-0004 mandates strict | pydantic v2 BaseModel |
| `dataclasses` for wire formats | No validation, no enum coercion; ADR-0004 explicitly chose pydantic | pydantic v2 BaseModel; dataclasses fine for purely-internal lightweight records |

---

## Stack patterns by variant

**If the decision flips to "drop to Python 3.8 system interpreter"** (NOT recommended):
- Pin `pydantic==2.10.6` (last 3.8-compatible release).
- Add `taskgroup`, `async-timeout`, `tomli`, `typing_extensions` deps.
- Rewrite all `match` statements as if/elif (RECOVERY_SPEC.md decision tables).
- Accept frozen dependency tree for the 5-year fleet life.
- Document this as an ADR superseding ADR-0001's "we ship the runtime we tested with".

**If the team revisits ADR-0001 and goes Go/Rust** (deferred per ADR-0001 "revisit when"):
- Out of scope for this milestone. Phase 6 of migration (decommission) is the natural revisit point.

**If wheel resolution ever fails on aarch64** for some new dep:
- First check piwheels (Raspberry Pi wheel repo; some aarch64 wheels there too).
- Then `uv pip install --no-binary <pkg>` and accept the build cost in the .deb pipeline (`build-essential` on the build host).
- Only as last resort: vendor the C extension into the .deb's site-packages.

---

## Version compatibility

| Package A | Compatible with | Notes |
|-----------|-----------------|-------|
| pydantic 2.13.x | pydantic-core matched (auto) | Don't pin pydantic-core directly; let pydantic resolve. |
| pydantic 2.13.x | Python 3.12 | Fully supported; aarch64-manylinux_2_17 wheels. |
| pyudev 0.24.4 | libudev ≥ 151 | Ubuntu 20.04 has libudev 245. Comfortable. |
| pyroute2 0.9.6 | Python 3.12 | OK. ≥0.9.5 supports 3.12 fully. |
| prometheus-client 0.25.0 | Python ≥3.9 | OK on 3.12. |
| asyncinotify 4.x | Python ≥3.10 | OK on 3.12; needs `asyncio.timeout` semantics. |
| httpx 0.27 | h11/h2/anyio (auto) | Pure-Python deps, no aarch64 issues. |
| python-build-standalone 3.12 (gnu) | glibc ≥ 2.17 | Ubuntu 20.04 has glibc 2.31. ≥1.5 minor versions of headroom. |
| sdnotify 0.3.2 | Python ≥3.6 | Trivial dep. |
| psutil 7.x | Python ≥3.6, aarch64 | Wheels exist. Don't compile. |

No known mutual-incompatibilities in this set.

---

## Specific requirement traceability

Each library choice above tied to a specific requirement, ADR, or constraint:

- **CPython 3.12 bundled**: ADR-0001 ("we ship the runtime we tested with"); FR-60 ("python3 ≥3.11"); C14 ("Python ≥ 3.11 available").
- **pydantic v2.13**: ADR-0004 (typed wire formats); FR-13, FR-32, FR-63, NFR-43 (validation, schema versioning).
- **PyYAML**: FR-54 (layered config); FR-33 (config-only carrier table edits).
- **prometheus-client**: NFR-21 (specific metric set); FR-42 (Unix socket scrape).
- **pyudev**: FR-1 (USB add/remove); ARCH §8.
- **pyroute2**: ARCH §8 (rtnetlink link-state); ADR-0002 (event-driven).
- **asyncinotify**: ARCH §8 (Zao-log inotify, kmsg rotation); ADR-0002.
- **httpx**: FR-44 (webhook POST); NFR-33 (HTTPS-only by default).
- **sdnotify**: FR-53 (`Type=notify`); NFR-13 (steady-state within 60s).
- **psutil**: NFR-3 (RSS ≤ 80 MiB tripwire).
- **mypy --strict + ruff**: NFR-40 (CI gates).
- **pytest + pytest-asyncio + hypothesis**: NFR-41 (hardware-free tests); TEST_STRATEGY §1, §5.

---

## Confidence per recommendation

| Recommendation | Confidence | Why |
|---------------|-----------|-----|
| Bundle CPython 3.12 via python-build-standalone | HIGH | All facts verified against PyPI, astral-sh release page, pydantic changelog, deadsnakes Launchpad page. Only sensible answer given the constraint matrix. |
| pydantic v2.13 | HIGH | PyPI confirmed; changelog confirmed Python 3.8 dropped at 2.11. |
| prometheus-client 0.25 | HIGH | PyPI confirmed; matches docs/ proposal. |
| pyudev 0.24.4 | HIGH | PyPI confirmed; libudev compat documented. |
| pyroute2 0.9.6 | HIGH | PyPI confirmed; Python ≥3.9 documented. |
| asyncinotify (over inotify_simple) | MEDIUM | Both work; preference is stylistic (asyncio-native). |
| httpx for webhooks | HIGH | Industry consensus for asyncio HTTP client; sync/async unified API. |
| Drop dh-virtualenv, roll our own debhelper rule | MEDIUM | The decision is sound; the recipe needs proving end-to-end in Phase 0. dh-virtualenv could still be made to work, but the integration with python-build-standalone is non-obvious. |
| uv as build-time installer | HIGH | Stable, fast, Astral-maintained, lockfile-clean. |
| sdnotify over systemd-python | MEDIUM | Both work; sdnotify is lighter and dep-free. |
| jeepney over dbus-next (if dbus is added later) | LOW | Both are viable; jeepney's recent activity edges it. **Deferred** to v2.1 anyway, so this can be re-decided then. |
| Drop black, use ruff format only | HIGH | Industry consensus 2025+; docs/ already hedges. |
| mypy in CI, pyright in editor | MEDIUM | Both are credible; mypy's stricter `Any` propagation matches our policy-engine purity story; pyright's speed helps day-to-day editing. Splitting is a known and accepted pattern. |

---

## Sources

**Primary (HIGH confidence)**:
- [pydantic on PyPI](https://pypi.org/project/pydantic/) — v2.13.3 latest, requires Python ≥3.9, fetched 2026-05-05.
- [pydantic v2.11 release](https://pydantic.dev/articles/pydantic-v2-11-release) — Python 3.8 drop confirmation.
- [prometheus-client on PyPI](https://pypi.org/project/prometheus-client/) — v0.25.0 latest, requires Python ≥3.9.
- [pyudev on PyPI](https://pypi.org/project/pyudev/) — v0.24.4 (Oct 2025), Python ≥3.9, libudev ≥151.
- [pyroute2 on PyPI](https://pypi.org/project/pyroute2/) — v0.9.6 (April 2026), Python ≥3.9 with 3.12+ support.
- [astral-sh/python-build-standalone](https://github.com/astral-sh/python-build-standalone) — stewardship since Dec 2024; aarch64-unknown-linux-gnu builds for 3.10–3.14; glibc 2.17 baseline.
- [python-build-standalone running.rst](https://github.com/astral-sh/python-build-standalone/blob/main/docs/running.rst) — glibc 2.17 minimum confirmed.
- [deadsnakes PPA](https://launchpad.net/~deadsnakes/+archive/ubuntu/ppa) — focal removed after EOL April 2025.
- [Ubuntu 20.04 LTS End of Standard Support](https://ubuntu.com/blog/ubuntu-20-04-lts-end-of-life-standard-support-is-coming-to-an-end-heres-how-to-prepare) — 31 May 2025 EOL.
- [Astral uv blog — python-build-standalone home](https://astral.sh/blog/python-build-standalone) — stewardship transfer Dec 2024.

**Secondary (MEDIUM confidence)**:
- [HTTPX vs Requests vs AIOHTTP guide 2026](https://decodo.com/blog/httpx-vs-requests-vs-aiohttp) — async support comparison.
- [pyright vs mypy 2026 comparison](https://www.danilchenko.dev/posts/ty-vs-mypy-vs-pyright/) — strictness defaults; speed.
- [Spotify dh-virtualenv repo](https://github.com/spotify/dh-virtualenv) — maintenance pulse signal.
- [taskgroup PyPI](https://pypi.org/project/taskgroup/) — 3.8 backport availability for `asyncio.TaskGroup`.
- [Ubuntu Pro / ESM extended support](https://ubuntu.com/security/esm) — focal package security through 2030/2032.

**Tertiary (LOW confidence — directional)**:
- [dbus-next PyPI](https://pypi.org/project/dbus-next/) and [Jeepney 0.9.0](https://jeepney.readthedocs.io/) — both work; activity pulses fluctuate.
- libqmi changelog on Launchpad — 1.30.4 in focal-updates confirmed; deeper version analysis deferred until needed.

---

*Stack research for: spark-modem-watchdog v2 (single-process root daemon, asyncio, aarch64 Linux)*
*Researched: 2026-05-05*
