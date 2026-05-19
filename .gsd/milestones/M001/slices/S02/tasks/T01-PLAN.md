# T01: 02-core-daemon-laptop-testable 01

**Slice:** S02 — **Milestone:** M001

## Description

Plan 02-01 lands the test scaffolding every other Phase 2 plan depends on:
the five test fakes (`FakeRunner`, `FakeClock`, `FakeWebhookPoster`,
`FixtureInventory`, `FakeDNSResolver`) plus a small `FixtureZaoTailer`,
and the empty fixture directories that will hold qmicli text fixtures, Zao
log snippets, inventory JSON snapshots, and replay cycle JSON.

Purpose: every downstream plan in waves 2–6 imports from `tests/fakes/*`.
If we wait until each plan needs a fake to land it, those plans cannot run
parallel within their wave. By staging all fakes here in wave 1, plans 02-02
through 02-08 can develop and self-test in parallel.

Output: six fake modules under `tests/fakes/` (each with mypy --strict +
self-tests under `tests/unit/fakes/`) and five empty `.gitkeep`-tracked
fixture directories under `tests/fixtures/`. No production code changes.

## Must-Haves

- [ ] "FakeRunner returns canned CompletedProcess for registered argvs and raises on unregistered argvs."
- [ ] "FakeClock advances monotonic time deterministically without wall-clock waiting."
- [ ] "FixtureInventory loads ModemDescriptor list from a JSON file."
- [ ] "FakeWebhookPoster records sent envelopes for test assertions."
- [ ] "FakeDNSResolver returns a canned IP and supports a one-shot fail mode."
- [ ] "FixtureZaoTailer answers is_line_active() against canned line lists."
- [ ] "All fakes pass mypy --strict and ruff check."

## Files

- `tests/fakes/__init__.py`
- `tests/fakes/runner.py`
- `tests/fakes/clock.py`
- `tests/fakes/webhook.py`
- `tests/fakes/inventory.py`
- `tests/fakes/dns.py`
- `tests/fakes/zao_log.py`
- `tests/fixtures/qmicli/.gitkeep`
- `tests/fixtures/zao_log/.gitkeep`
- `tests/fixtures/inventory/.gitkeep`
- `tests/fixtures/diag/.gitkeep`
- `tests/fixtures/replay/.gitkeep`
- `tests/unit/fakes/__init__.py`
- `tests/unit/fakes/test_runner.py`
- `tests/unit/fakes/test_clock.py`
- `tests/unit/fakes/test_webhook.py`
- `tests/unit/fakes/test_inventory.py`
- `tests/unit/fakes/test_dns.py`
- `tests/unit/fakes/test_zao_log.py`
- `tests/conftest.py`
