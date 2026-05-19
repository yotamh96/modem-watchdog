# v1 bash toolchain — archived

| Field        | Value                                    |
| ------------ | ---------------------------------------- |
| Retired      | 2026-05-11                               |
| Decision     | [ADR-0014](../../docs/adr/0014-v1-retired-pivot.md) |
| Replaced by  | spark-modem-watchdog v2 (Python daemon)  |

## What v1 was

The v1 modem-watchdog was a set of bash scripts that ran on each NVIDIA
Jetson Orin NX box to monitor and recover 4x Sierra Wireless EM7421 LTE
modems behind the Soliton Zao bonding stack. The scripts were:

| Script                     | Purpose                                      |
| -------------------------- | -------------------------------------------- |
| `diag.sh`                  | Periodic modem diagnostics via `qmicli`      |
| `recovery.sh`              | Escalating recovery actions (soft reset, modem reset, USB reset) |
| `auto_profile.sh`          | Automatic APN/profile configuration          |
| `zao_reset_line.sh`        | Zao bonding-line reset helper                |
| `spark-modem-watchdog.sh`  | Top-level orchestrator / cron entry point    |

## Where they lived on-device

All scripts were deployed as loose files under `/usr/local/bin/` on each
Jetson. They were never packaged as a `.deb`. Scheduling was handled by
cron entries and, on some boxes, a simple systemd timer.

## Why they were retired

v1 was retired across the entire fleet by 2026-05-11. The bash toolchain
had reached its maintainability ceiling: no structured state, no atomic
writes, no policy/mechanism separation, and limited observability. The
v2 Python daemon replaces v1 entirely with a proper state machine,
typed diagnostics, async probes, and Prometheus metrics.

See [ADR-0014](../../docs/adr/0014-v1-retired-pivot.md) for the full
decision record. There is no v1 rollback path; rollback targets the
previous v2 `.deb` release.

## This directory is a pointer, not a container

The v1 scripts were never committed to this repository. They lived in
operator-managed paths on-device. The `v1-legacy` branch preserves a
reference copy of the scripts for historical context. This directory
exists solely to document the v1 toolchain's existence and retirement.
