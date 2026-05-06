# ADR-0001 — Language: Python 3.11+

| Field        | Value          |
| ------------ | -------------- |
| Status       | Accepted       |
| Date         | 2026-05-05     |
| Deciders     | Eng team       |
| Supersedes   | (v1: bash)     |
| Amended      | 2026-05-06     |

## Context

v1 is a hybrid of bash and ad-hoc python heredocs. Costs:

- Hand-rolled JSON encoder in bash (`json_str`, `json_bool_or_null`,
  `json_num_or_null`) that's almost-but-not-quite RFC 8259.
- Four `python3 -c '…'` forks per recovery cycle to parse the same JSON.
- `awk -F"'"` parsing of `qmicli` output everywhere — fragile and
  silently breaks on output drift.
- No type checking, no IDE help on a 900-line bash policy engine.
- Command injection in `auto_profile.sh` via shell-string interpolation
  into a python heredoc.
- Tests are impossible (you can't unit-test a function that
  side-effects through `qmicli`).

The rewrite must pick one runtime end-to-end.

## Options considered

### A. Python 3.11+ (chosen)

- Pros: real types (pydantic, dataclasses, mypy --strict), real JSON,
  `asyncio` for parallel modem probes, rich test ecosystem, easy
  shell-out via `asyncio.subprocess`, plenty of cellular-management
  precedent, team is familiar.
- Cons: not a single static binary; needs a venv. RSS larger than Go.
  Startup ~150 ms vs Go's ~5 ms.

### B. Go 1.22+

- Pros: single static binary, lowest RSS, fastest start, great systemd
  story, strict types.
- Cons: parsing `qmicli` text via Go is exactly as awkward as in
  Python; smaller pool of in-house Go expertise; we lose the speed-
  of-iteration advantage of Python on a code-heavy policy engine.

### C. Rust

- Pros: best safety, smallest RSS, single binary.
- Cons: weeks of velocity loss for a team without daily Rust practice;
  no in-house cellular-Rust precedent. Overkill for this scale.

### D. Continue with bash + python heredocs

- Rejected. The reasons we're rewriting are exactly the reasons we
  can't keep this combination.

## Decision

**Python 3.11+**, packaged as a Debian `.deb` containing a
self-contained venv at `/opt/spark-modem-watchdog/`. We do not depend
on the system Python; we ship the runtime we tested with.

## Consequences

- All wire formats use `pydantic v2`.
- `mypy --strict` is a CI gate (NFR-40).
- Every external command goes through one `subproc` wrapper with
  list-form `argv` (NFR-31, FR-64). No shell strings, ever.
- `qmicli` output is parsed in exactly one module (`qmi/parsers.py`)
  with fixture-based tests.
- The `.deb` is `arm64`-only for now. A second arch is a separate
  build target.
- Cold-start time is ~150 ms; the daemon does cold start once at
  boot. Acceptable.
- Memory budget: 80 MiB RSS (NFR-3). This is comfortable for Python
  with `pydantic`; we have measured comparable internal services at
  40–60 MiB.

## Amendment 2026-05-06

**Closes PROJECT.md Q8** (Jetson Python). The original "Decision"
section said "Python 3.11+, packaged as a Debian `.deb` containing a
self-contained venv at /opt/spark-modem-watchdog/" but did not commit
to a sourcing tactic. Research (`.planning/research/STACK.md` §2)
closed the question: **bundle CPython 3.12 via
`astral-sh/python-build-standalone`**.

Rationale (full reasoning in `.planning/research/STACK.md`):

- Jetson system Python is 3.8.10 (L4T R35.6.4 / Ubuntu 20.04). Pydantic
  v2.11+ requires Python ≥3.9; deadsnakes does not publish 3.11+ for
  Ubuntu 20.04 ("focal"). Patching the box's system Python is operationally
  hostile (Zao's runtime depends on it).
- python-build-standalone publishes glibc-2.17-baselined CPython for
  `aarch64-unknown-linux-gnu`; Ubuntu 20.04 ships glibc 2.31 — comfortable
  margin. Tarball is ~30 MiB; `.deb` size ceiling 40 MiB (NFR-51) accommodates.
- Python 3.13 deferred (free-threaded transition risk + thinner aarch64
  wheel ecosystem). 3.14 too new (beta).

The full packaging recipe (PBS + `uv pip compile` for lockfile + custom
debhelper rule replacing `dh-virtualenv`) is documented separately in
**ADR-0010**.

## Revisit when

- We need a meaningfully smaller RSS (e.g. running on something
  smaller than Orin NX). At that point Go becomes attractive.
- The team's Rust expertise grows enough that the velocity argument
  flips. Today it doesn't.
- CPython 3.13's free-threaded story stabilizes and we want concurrent
  GIL-free execution (see also ADR-0010 Revisit when).
