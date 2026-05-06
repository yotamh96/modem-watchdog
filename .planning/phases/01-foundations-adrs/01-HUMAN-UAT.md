---
status: partial
phase: 01-foundations-adrs
source: [01-VERIFICATION.md]
started: 2026-05-06T00:00:00Z
updated: 2026-05-06T00:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Jetson hardware install
expected: `apt install` of the arm64 .deb on a fresh Jetson Orin NX (JetPack 5.1.5 / Ubuntu 20.04 / aarch64) succeeds; postinst smoke test prints "OK: all 10 runtime libs import"; `systemctl start spark-modem-watchdog` reports `active (running)` after ExecStartPre= smoke test passes; no errors in `journalctl -u spark-modem-watchdog`. (Reason it's human-only: requires aarch64 Linux hardware; CI builds the .deb on a self-hosted runner but on-device install and runtime behavior need the Jetson target.)
result: [pending]

### 2. .deb size budget (NFR-51)
expected: After a real `dpkg-buildpackage` on the aarch64 CI runner, `stat -c %s *.deb` produces a value ≤ 41,943,040 bytes (40 MiB); the CI workflow's size check exits 0. (Reason it's human-only: the .deb is built at CI time, not pre-built in the repo. Size can only be measured after a real build.)
result: [pending]

### 3. systemctl reload + SIGHUP config-reload wiring (FR-54)
expected: Data-only fields (carrier table, thresholds) update transactionally on `systemctl reload` / SIGHUP; topology-affecting fields emit a "restart required" log line and are NOT applied. (Phase 3 will deliver the full reload semantics; Phase 1 only needs config parsing to work — the placeholder ExecStart= exits immediately, so end-to-end SIGHUP behavior cannot be tested until Phase 2.)
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
