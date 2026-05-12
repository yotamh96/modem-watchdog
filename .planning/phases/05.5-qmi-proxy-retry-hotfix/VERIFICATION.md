---
phase: 05.5-qmi-proxy-retry-hotfix
verdict: PASS
ci_verdict: PASS
local_verdict: PASS
bench_verdict: PASS (firmware probe cleared transient qmi-proxy failures; all three preflight probes succeeded; deeper architectural gap surfaced — production main loop wiring is a documented placeholder, tracked as Phase 05.6)
bench_install_deb: spark-modem-watchdog_2.0.0-0.gitf4de86c1-1_arm64.deb
bench_verified: 2026-05-12 12:54 UTC
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

## Bench Jetson evidence (CONFIRMED 2026-05-12 12:54 UTC)

Bench Jetson install of CI .deb gitf4de86c1. After the operator captured
the local triple via `spark-modem ctl capture-fleet-fixture` and seeded
`/etc/spark-modem-watchdog/known-fleet/bench-jetson-1/`, the daemon's
ExecStart finally exited cleanly:

```
Process: 957098 ExecStart=/opt/spark-modem-watchdog/python/bin/spark-modem-watchdog
  (code=exited, status=0/SUCCESS)
```

All three preflight probes succeeded end-to-end (libqmi version, firmware
revision via the new retry loop, Zao SDK detection returning `unknown`
sentinel), the known-fleet allow-list match passed, and the daemon's
production main function returned `0`.

**However**, systemd then reported `Result: 'protocol'` — the `Type=notify`
unit never received `READY=1`. Investigation traced this to a
**documented placeholder** at `src/spark_modem/daemon/main.py:306`: the
production `_production_main` acquires the PID lock and immediately
returns 0 with `_ = ...` no-op statements keeping the eventual-use
imports live. The actual TaskGroup + cycle loop + `sd.ready()` wiring
that Plan 03-09 was supposed to land never did (Plan 03-09 was marked
"completed approved-with-deferral" without the production-path
integration body). This is outside Phase 05.5 scope — Phase 05.5's
own work (retry firmware probe on qmi-proxy contention) verifiably
succeeded. Phase 05.6 owns the production main loop wiring.

## Phase 05.x hotfix chain — final state

| Phase | Hotfix | Bench verdict |
|-------|--------|---------------|
| 05.1 | deb-packaging (sys.path / entry-point / LoadCredential / regression gates) | PASS |
| 05.2 | daemon Settings() instead of CLI laptop-sandbox factory | PASS |
| 05.3 | libqmi version regex accepts qmicli-only format | PASS |
| 05.4 | dms_get_revision parser accepts singular header form | PASS (parser deployed correctly) |
| 05.5 | firmware probe retries on qmi-proxy CID contention | PASS |
| 05.6 | (new) production-main-loop wiring | TBD — planning artifact created, implementation deferred |

The Phase 05.x hotfix chain delivered what its name says: the
infrastructure plumbing (.deb install + daemon settings + qmicli/libqmi
parsing + known-fleet preflight + qmi-proxy retry) is now end-to-end
functional on the bench Jetson. The daemon's actual main-loop body is
the next layer.

## Verdict

- **Local:** PASS (mypy + ruff + pytest all green; 98/98)
- **CI:** PASS (run 25735143279, commit f4de86c)
- **Bench Jetson:** PASS for the 05.5 scope (firmware probe cleared,
  preflight passed end-to-end, daemon reached its main function). The
  next layer up — actual TaskGroup wiring inside `_production_main` —
  is a documented placeholder and tracked as Phase 05.6.
