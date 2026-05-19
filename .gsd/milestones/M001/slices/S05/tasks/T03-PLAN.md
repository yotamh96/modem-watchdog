# T03: Plan 03

**Slice:** S05 — **Milestone:** M001

## Description

Build the operator-facing CLI verb `spark-modem ctl capture-fleet-fixture --out=<dir>`
that produces the per-box fleet fixture (triple.json + redacted per-modem qmicli outputs
+ zao-log-sample.txt) without requiring the daemon to be running. This is the X-03
chicken-and-egg fix (per CONTEXT.md Claude's Discretion + RESEARCH Q2 §165-213): the
daemon refuses to start on unknown triples, but the engineer needs to capture the
triple on a daemon-less box.

Purpose: X-01 + X-02 deliverables. Output is committed to `tests/fixtures/fleet/<box-id>/`
per box, batched into a single Phase-6-prerequisite PR per CONTEXT.md X-04.

Output: One new CLI module (~200 LOC), one new redaction helper added to redact.py
(~30 LOC), one argparse-subparser block added to cli/main.py (~12 LOC), one new
fixture file with ICCID for PII test, one example fleet fixture committed at
`tests/fixtures/fleet/_test/triple.json` per RESEARCH Q10 §752, two test files.
