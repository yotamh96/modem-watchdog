---
phase: 05.3-libqmi-version-regex-hotfix
verdict: PASS
ci_verdict: PASS
local_verdict: PASS
bench_verdict: PASS (new failure surfaces in dms_get_revision parser — tracked as Phase 05.4)
bench_install_deb: spark-modem-watchdog_2.0.0-0.git4d99a0dc-1_arm64.deb
bench_verified: 2026-05-12 11:20 UTC
---

# Phase 05.3 — VERIFICATION

## Phase goal (restated)

A .deb built from a commit containing the broadened libqmi version regex
must install on the bench Jetson and the daemon's Phase 5 X-03 preflight
step must successfully parse `1.30.4` from the JetPack `qmicli --version`
output — i.e., `compute_fleet_triple` must NOT raise
`QmiVersionDetectionFailed("did not match libqmi-glib regex")` against the
real bench Jetson stdout.

Once the regex is unblocked, the daemon may still refuse the bench Jetson
on the **known-fleet allow-list** check (a separate gate: the Jetson's
triple must match an entry under `/etc/spark-modem-watchdog/known-fleet/`).
That outcome is outside Phase 05.3 scope — 05.3 only owns the regex.

## Local evidence (CONFIRMED 2026-05-12)

- `uv run mypy --strict src/spark_modem/qmi/version.py` → 0 issues
- `uv run ruff check ...` → clean
- `uv run pytest tests/unit/qmi/test_version.py -q` → **11 passed** in 0.60s
  - includes new `test_detect_libqmi_version_parses_jetpack_qmicli_only_format`
  - existing `_parses_1_30` and `_parses_1_32` still pass (new regex returns
    same version on existing fixtures because qmicli/libqmi-glib are lockstep)

## CI evidence (PENDING)

After push, the `build-deb.yml` workflow run will exercise the V-02 gate
which still doesn't invoke the daemon binary directly. The new regex
behavior is therefore primarily covered by the unit test, not by the .deb
install-step. Run number TBD.

## Bench Jetson evidence (PENDING — append below once available)

After `sudo apt install ./spark-modem-watchdog_2.0.0-0.git<sha>-1_arm64.deb`
on the bench Jetson:

```
systemctl status spark-modem-watchdog --no-pager --lines=0
journalctl -u spark-modem-watchdog --since "30 sec ago" --no-pager | tail -40
```

Expected (one of):
- **Best case:** `Active: active (running)` + `sd_notify READY=1`. Would
  mean the bench Jetson's triple matches an existing known-fleet entry
  (or the preflight passes for some other reason).
- **Likely case:** ExecStart exits non-zero with a DIFFERENT preflight
  failure mode — e.g., `unknown fleet triple: triple (..., 1.30.4) not
  in known-fleet allow-list`. That would mean Phase 05.3's regex worked
  (libqmi 1.30.4 parsed successfully) but the bench Jetson's full triple
  is not in the operator-supplied allow-list. Track as Phase 05.4 or
  operator action (capture fleet fixture + add to known-fleet).
- **NOT-expected:** the same `did not match libqmi-glib regex` error.
  That would mean the regex fix didn't deploy correctly.

## Verdict

- **Local:** PASS (mypy + ruff + pytest all green)
- **CI:** PENDING
- **Bench Jetson:** PENDING (record outcome inline above when available)
