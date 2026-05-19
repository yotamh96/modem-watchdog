# T01: Plan 01

**Slice:** S06 — **Milestone:** M001

## Description

Land the install-pipeline + entry-point fixes for the Phase 05.1 hotfix. After
this plan, `dpkg-deb -c <built deb>` shows `spark_modem/` installed into the
bundled venv's `python/lib/python3.12/site-packages/` (not under
`/opt/spark-modem-watchdog/lib/`), and the bundled venv's `python/bin/`
contains both `spark-modem` and `spark-modem-watchdog` console-script
shims that import cleanly.

Implements locked decisions **I-01**, **I-02**, **I-04**, **I-05** (and honors **D-02**: no `requirements.lock` churn — the 10 runtime libs stay pinned exactly where Phase 1 placed them) from
`.planning/phases/05.1-deb-packaging-hotfix/05.1-CONTEXT.md`.

Purpose: bug #1 (`spark_modem` not on `sys.path` of the bundled venv) and
bug #2 (`spark-modem-watchdog` daemon entry point missing → systemd 203/EXEC)
are eliminated by **shipping `spark_modem` through `uv pip install .` into
the bundled venv's site-packages** and **declaring the daemon entry point in
`[project.scripts]`** so the console-script auto-materializes at
`/opt/spark-modem-watchdog/python/bin/spark-modem-watchdog`.

Output:
- `pyproject.toml` with the new console-script entry.
- `src/spark_modem/daemon/main.py` with `_sync_main()` inlined between
  `async def main` and `if __name__ == "__main__"`.
- `debian/rules` with a new `Step 3.5` block running `uv pip install .` AFTER
  step 3 (runtime libs) and BEFORE the pip uninstall sweep (setuptools must
  still be present — load-bearing per I-05).
- `debian/spark-modem-watchdog.install` with the offending source-tree line
  removed and an audit-trail comment added.
- `debian/spark-modem-watchdog.dirs` with `/opt/spark-modem-watchdog/lib`
  removed (otherwise dh_installdirs creates a phantom empty dir).
