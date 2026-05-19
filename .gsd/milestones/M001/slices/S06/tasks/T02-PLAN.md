# T02: Plan 02

**Slice:** S06 — **Milestone:** M001

## Description

Land the HMAC-secret discipline + the `ctl config-check` verb body for the
Phase 05.1 hotfix. After this plan, the daemon and CLI both know how to
resolve the HMAC secret path (with the systemd 245 fallback), the
`spark-modem ctl config-check` verb exists and validates Settings + HMAC
secret pre-flight, and the postinst writes a placeholder file that
config-check explicitly rejects so a fresh install cannot accidentally boot
with a default secret.

Implements locked decisions **L-02**, **L-03**, **L-05** (and honors **D-04**: this plan contains the entire "tiny daemon-side hook" surface — `settings.py` resolver + the new `cli/ctl/config_check.py` verb body. All other plans in Phase 05.1 are glue under `debian/`, `scripts/`, `.github/`, or `.planning/`) from
`.planning/phases/05.1-deb-packaging-hotfix/05.1-CONTEXT.md`. L-01 stays in
the unit file (Plan 03's responsibility); L-04 verification is performed by
the CI install test (Plan 05).

Purpose:
- Bug #3 (systemd-245 LoadCredential incompatibility) is closed by the
  code-side fallback in `settings.py`: a single HMAC file on disk at
  `/etc/spark-modem-watchdog/hmac-secret` serves BOTH systemd 247+ (which
  populates `CREDENTIALS_DIRECTORY`) AND systemd 245 (which doesn't — the
  daemon reads directly from the fallback path).
- The pre-flight verb (`ctl config-check`) gives ExecStartPre something
  meaningful to call: it surfaces "operator forgot to provision the real
  secret" / "wrong mode" / "wrong owner" BEFORE the main daemon ever boots,
  so a bad install doesn't trip StartLimitBurst (PITFALLS §4.2).
- The postinst-managed placeholder makes the "operator forgot" state visible:
  the file always exists, but `ctl config-check` refuses to boot with the
  literal sentinel.

Output:
- `src/spark_modem/config/settings.py` with a new `resolve_hmac_secret_path()`
  method.
- `src/spark_modem/cli/ctl/config_check.py` — NEW file, full verb body.
- `src/spark_modem/cli/main.py` with `ctl config-check` registered in the
  argparse tree.
- `debian/spark-modem-watchdog.postinst` with an idempotent HMAC placeholder
  write block.
