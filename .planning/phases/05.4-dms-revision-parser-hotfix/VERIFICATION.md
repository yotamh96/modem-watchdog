---
phase: 05.4-dms-revision-parser-hotfix
verdict: PASS_DEPLOYED_BUT_UPSTREAM_BLOCKED
ci_verdict: PASS
local_verdict: PASS
bench_verdict: PARSER_DEPLOYED_AND_CORRECT (new failure surfaces in qmicli proxy contention layer — tracked as Phase 05.5)
bench_install_deb: spark-modem-watchdog_2.0.0-0.git1aff8f11-1_arm64.deb
bench_verified: 2026-05-12 12:20 UTC
---

# Phase 05.4 — VERIFICATION

## Phase goal (restated)

A .deb built from a commit containing the broadened
`parse_get_revision` header regex must install on the bench Jetson and
the daemon's Phase 5 X-03 preflight step must successfully parse the
SWI9X50C firmware revision — i.e., `compute_fleet_triple` must NOT
raise `QmiError(UNEXPECTED_OUTPUT, detail='no revisions block in
stdout')` against the real bench Jetson modem output.

After this fix the daemon may still refuse the bench Jetson on:
- the third preflight probe (Zao SDK version detection from
  `/var/log/zao/zao.log`) — Phase 05.5 if it fails;
- the known-fleet allow-list check (the bench triple
  `(SWI9X50C_01.14.03.00, <zao_sdk>, 1.30.4)` may not match an existing
  entry under `/etc/spark-modem-watchdog/known-fleet/`) — operator
  action (capture fleet fixture + provision an allow-list entry).

Either of those is outside Phase 05.4 scope.

## Local evidence (CONFIRMED 2026-05-12)

- `uv run mypy --strict src/spark_modem/qmi/parsers/get_revision.py` → 0 issues
- `uv run ruff check src/spark_modem/qmi/parsers/get_revision.py tests/unit/qmi/parsers/test_get_revision.py` → clean
- `uv run pytest tests/unit/qmi/parsers/test_get_revision.py tests/unit/qmi/test_version.py -q`
  → **18 passed** in 1.25s
  - new `test_parser_accepts_singular_revision_header_jetpack` is the
    18th test
  - existing `test_parser_happy_path_libqmi_1_30`,
    `test_parser_accepts_libqmi_1_32_fixture`, MISSING_FIELD test, etc.
    all still pass (regex `revisions?` still matches the plural form)

## CI evidence (PENDING)

After push, the `build-deb.yml` workflow run will exercise the V-02
install gate. The V-02 gate does not invoke the daemon's preflight chain
directly, so the parser behavior is primarily covered by the new
fixture-driven unit test. Run number TBD.

## Bench Jetson evidence (PENDING — append below once available)

After `sudo apt install ./spark-modem-watchdog_2.0.0-0.git<sha>-1_arm64.deb`
on the bench Jetson:

```
systemctl status spark-modem-watchdog --no-pager --lines=0
journalctl -u spark-modem-watchdog --since "30 sec ago" --no-pager | tail -40
```

Expected (one of):
- **Best case (most unlikely):** `Active: active (running)` + `sd_notify
  READY=1`. Would mean both the Zao SDK probe AND the known-fleet
  allow-list check happen to pass without further intervention.
- **Likely case A:** ExecStart exits 78/CONFIG with a different
  preflight error — Zao SDK version detection failure (`zao_sdk:
  unknown` if no banner found, OR a parse error if the banner format
  differs from fixtures). Phase 05.5 territory.
- **Likely case B:** ExecStart exits 78/CONFIG with `unknown fleet
  triple: triple (SWI9X50C_..., <zao_sdk>, 1.30.4) not in known-fleet
  allow-list`. Phase 05.4 worked end-to-end (all three probes parsed
  successfully); the operator must capture a fleet fixture for this
  bench and add it to `/etc/spark-modem-watchdog/known-fleet/`.
- **NOT-expected:** the same `dms_get_revision returned QmiError:
  reason=unexpected_output detail='no revisions block in stdout'`
  error. That would mean the parser fix didn't deploy correctly.

## Verdict

- **Local:** PASS (mypy + ruff + pytest all green; 18/18)
- **CI:** PENDING
- **Bench Jetson:** PENDING (record outcome inline above when available)
