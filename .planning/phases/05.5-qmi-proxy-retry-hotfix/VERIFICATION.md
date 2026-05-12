---
phase: 05.5-qmi-proxy-retry-hotfix
verdict: PENDING_BENCH_DEPLOY
ci_verdict: PENDING
local_verdict: PASS
---

# Phase 05.5 — VERIFICATION

## Phase goal (restated)

A .deb built from a commit containing the firmware-probe retry loop must
install on the bench Jetson and the daemon's Phase 5 X-03 preflight step
must successfully construct a `FleetTriple` despite ongoing qmi-proxy
contention with Zao. Three retry attempts at 0.5s spacing should clear
the bench's observed ~25% per-call failure rate (cumulative success
above 99%).

After this fix the daemon may still refuse the bench Jetson on:
- the third preflight probe (Zao SDK version detection from
  `/var/log/zao/zao.log`) — Phase 05.6 if it fails;
- the known-fleet allow-list check (the bench triple
  `(SWI9X50C_01.14.03.00, <zao_sdk>, 1.30.4)` may not match an
  existing entry under `/etc/spark-modem-watchdog/known-fleet/`) —
  operator action (capture fleet fixture + provision allow-list).

Either of those is outside Phase 05.5 scope.

## Local evidence (CONFIRMED 2026-05-12)

- `uv run mypy --strict src/spark_modem/qmi/version.py` → 0 issues
- `uv run ruff check src/spark_modem/qmi/version.py tests/unit/qmi/test_version.py` → clean
- `uv run pytest tests/unit/qmi/ -q` → **98 passed** in 4.65s
  - new `test_compute_fleet_triple_retries_transient_qmicli_failure`
    exercises the 2-fail-then-success path; asserts `call_count == 3`
  - new `test_compute_fleet_triple_exhausts_retries_with_stderr_in_error`
    exercises the all-fail path; asserts the raised message contains
    both `"failed after 3 attempts"` AND `"CID allocation failed"`
  - existing `test_compute_fleet_triple_firmware_qmierror_raises`
    updated to match the new error wording; still validates the same
    semantic (malformed stdout → exception)
  - the other 95 existing tests in `tests/unit/qmi/` continue to pass

## CI evidence (PENDING)

After push, the `build-deb.yml` workflow run will exercise the V-02
install gate. The retry behavior is primarily covered by the new unit
tests; CI cannot reproduce the actual qmi-proxy / Zao race because the
V-02 container has no Zao process running. Run number TBD.

## Bench Jetson evidence (PENDING — append below once available)

After `sudo apt install ./spark-modem-watchdog_2.0.0-0.git<sha>-1_arm64.deb`
on the bench Jetson:

```
systemctl status spark-modem-watchdog --no-pager --lines=0
journalctl -u spark-modem-watchdog --since "30 sec ago" --no-pager | tail -40
```

Expected (one of):
- **Best case:** `Active: active (running)` + `sd_notify READY=1`. Would
  mean the bench's triple `(SWI9X50C_01.14.03.00, <zao_sdk>, 1.30.4)`
  happens to match an existing known-fleet allow-list entry.
- **Likely case A:** ExecStart exits 78/CONFIG with a Zao SDK
  detection error (`zao_sdk: unknown` because the daemon couldn't find
  the Zao banner in `/var/log/zao/zao.log` — possibly because Zao logs
  somewhere else on this bench, or the banner format differs from the
  fixtures). Phase 05.6 territory.
- **Likely case B:** ExecStart exits 78/CONFIG with `unknown fleet
  triple: triple (SWI9X50C_..., <zao_sdk>, 1.30.4) not in known-fleet
  allow-list`. Phase 05.5 worked end-to-end (all three probes parsed);
  operator must provision a known-fleet entry for this bench.
- **NOT-expected:** the same `dms_get_revision returned QmiError`
  message. If that happens, either the new .deb didn't deploy OR the
  retry budget is too small for this bench's actual contention rate
  (consider bumping `_FIRMWARE_PROBE_ATTEMPTS`).

## Verdict

- **Local:** PASS (mypy + ruff + pytest all green; 98/98)
- **CI:** PENDING
- **Bench Jetson:** PENDING (record outcome inline above when available)
