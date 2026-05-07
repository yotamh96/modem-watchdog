---
phase: 3
slug: linux-event-sources-lifecycle
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-07
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: see `03-RESEARCH.md` § "Validation Architecture" for full Phase Requirements → Test Map and Wave 0 Gaps.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.x + pytest-asyncio 0.24.x (mode=auto) + hypothesis 6.110.x |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (Phase 3 adds `markers = ["linux_only: requires Linux syscalls (skipif on Windows)"]`) |
| **Quick run command** | `pytest tests/unit/event_sources/ tests/unit/kmsg/ tests/unit/daemon/ -x` |
| **Full suite command** | `pytest -q` |
| **Linux-only suite** | `pytest -m linux_only` (Linux CI / bench Jetson) |
| **Estimated runtime** | ~30 s unit suite (M7 budget) · ~2 min linux_only integration |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/unit/<changed_module>/ -x` (≤5 s per file)
- **After every plan wave:** Run `pytest -q` (full unit suite ≤30 s per M7)
- **Before `/gsd-verify-work`:** `pytest -q` AND `pytest -m linux_only` must be green
- **Max feedback latency:** 30 s (unit) · 120 s (integration on Linux runner)

---

## Per-Task Verification Map

> Plans populate this table during planning. Each plan's `<automated>` block declares the test command for each task; the planner copies entries here.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _populated by planner_ | | | | | | | | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

See `03-RESEARCH.md` § "Phase Requirements → Test Map" for the canonical mapping of FR-1, FR-3, FR-4, FR-14, FR-43, FR-43.1, FR-53, FR-61, FR-61.1, FR-75, NFR-12, NFR-13, NFR-30 to test files (≥21 entries; all 5 success criteria mapped).

---

## Wave 0 Requirements

> Minimum scaffolding before functional plans can verify. Full list in `03-RESEARCH.md` § "Wave 0 Gaps" (≥30 entries).

Highlights — every Phase 3 plan depends on at least one of these:

- [ ] `tests/unit/event_sources/{__init__,test_supervisor,test_udev_producer,test_rtnetlink_producer,test_kmsg_producer,test_asyncinotify_producer}.py`
- [ ] `tests/unit/kmsg/{__init__,test_classifier,test_dedup}.py`
- [ ] `tests/unit/daemon/{test_lifecycle_sd_notify,test_sigterm_choreography,test_sighup_swap,test_clean_shutdown_marker,test_pid_lock,test_sim_swap_detection}.py`
- [ ] `tests/unit/inventory/{test_udev_inventory,test_netns_derivation}.py`
- [ ] `tests/unit/zao_log/test_inotify_tailer_dual_mode.py`
- [ ] `tests/unit/event_logger/test_writer_reopen.py`
- [ ] `tests/integration/{__init__,conftest,test_lifecycle,test_logrotate_create,test_unit_file_audit}.py`
- [ ] `tests/fakes/{udev,rtnetlink,asyncinotify,kmsg,sdnotify,pidlock}.py`
- [ ] `tests/fixtures/kmsg/{usb_overcurrent,usb_enum_failure,thermal_throttle,qmi_wwan_probe_fail,tegra_hub_psu_droop}.log`
- [ ] `tests/fixtures/zao_log/rotated/{create,copytruncate}/{before,after}.log`
- [ ] `pyproject.toml` markers entry: `markers = ["linux_only: requires Linux syscalls (skipif on Windows)"]`

*(No framework install needed — pytest + pytest-asyncio + hypothesis already pinned in Phase 1's lockfile.)*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Boot-to-READY ≤60 s with 4 real modems | FR-1, NFR-13, SC #1 | Requires bench Jetson with 4 EM7421s on USB hub `2-3.1.{1..4}` | systemctl start spark-modem-watchdog.service ; `systemd-notify --booted` round-trip; `systemd-analyze` for boot timing; assert status.json modem_count==4 |
| qmi_wwan reload survivability | NFR-12, SC #5 | Requires real `qmi_wwan` kernel module + 4 cdc-wdm devices to unbind/rebind | `modprobe -r qmi_wwan; modprobe qmi_wwan` on bench Jetson; tail events.jsonl; assert `disconnected → recovering → healthy` shape across all 4 modems |
| LoadCredential delivery on systemd 245 | NFR-34, U-03 | PITFALLS §4.3 incompat — verify `$CREDENTIALS_DIRECTORY` is populated AND `PrivateMounts` is NOT set | `cat /proc/$(pidof spark-modem-watchdog)/environ | tr '\\0' '\\n' | grep CREDENTIALS_DIRECTORY` ; assert non-empty path; assert `cat $CREDENTIALS_DIRECTORY/webhook_hmac_secret` succeeds |
| systemd `WatchdogSec=90s` actually triggers | FR-75, U-04 | Requires deliberately wedged cycle (e.g. `kill -STOP` on a qmicli child) and wall-clock 90 s | Wedge a cycle; assert systemd issues SIGTERM at ≤90 s; assert daemon restart counter increments; defer to Phase 4 HIL |
| `RuntimeDirectoryPreserve=yes` keeps `/run/.../lock` across stop | U-03, FR-61 | Requires systemd-supervised `systemctl stop` followed by `systemctl start` | `systemctl stop` ; `ls /run/spark-modem-watchdog/` (clean-shutdown marker should be present) ; `systemctl start` ; assert clean-shutdown marker consumed and unlinked at startup |

Phase 3 ships automated unit tests for every behavior except those listed above. The 5 manual-only items are deferred to Phase 4 HIL fault-injection lane (per CONTEXT.md § "Deferred Ideas").

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies (planner gates)
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (≥30 file paths in research § "Wave 0 Gaps")
- [ ] No watch-mode flags (CI must run to completion)
- [ ] Feedback latency: ≤30 s unit · ≤120 s integration
- [ ] All 13 Phase 3 REQ-IDs mapped to at least one test file
- [ ] All 5 success criteria mapped to integration tests (`test_sc1` through `test_sc5`)
- [ ] `nyquist_compliant: true` set in frontmatter once planner completes per-task map

**Approval:** pending
