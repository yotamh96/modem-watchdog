# ADR-0001 — Language: Python 3.11+

| Field        | Value          |
| ------------ | -------------- |
| Status       | Accepted       |
| Date         | 2026-05-05     |
| Deciders     | Eng team       |
| Supersedes   | (v1: bash)     |

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

## Revisit when

- We need a meaningfully smaller RSS (e.g. running on something
  smaller than Orin NX). At that point Go becomes attractive.
- The team's Rust expertise grows enough that the velocity argument
  flips. Today it doesn't.
