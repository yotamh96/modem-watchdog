# M001: M001: M001: Migration

**Vision:** `spark-modem-watchdog` is the on-device daemon that keeps a fleet of NVIDIA

## Slices

- [x] **S01: Foundations Adrs** `risk:medium` `depends:[]`
  > After this: unit tests prove foundations-adrs works

- [x] **S02: Core Daemon Laptop Testable** `risk:medium` `depends:[S01]`
  > After this: Plan 02-01 lands the test scaffolding every other Phase 2 plan depends on:

- [x] **S03: Linux Event Sources Lifecycle** `risk:medium` `depends:[S02]`
  > After this: Build Wave 1 of Phase 3: the foundational scaffolding every producer and

- [x] **S04: Destructive Actions Hil** `risk:medium` `depends:[S03]`
  > After this: unit tests prove destructive-actions-hil works

- [x] **S05: Bench Field Shadow** `risk:medium` `depends:[S04]`
  > After this: Add the one qmicli verb missing from QmiWrapper that Phase 5 needs for fleet-triple

- [x] **S06: Deb Packaging Hotfix** `risk:medium` `depends:[S05]`
  > After this: Land the install-pipeline + entry-point fixes for the Phase 05.

- [x] **S07: Daemon Startup Hotfix** `risk:medium` `depends:[S06]`
  > After this: unit tests prove daemon-startup-hotfix works

- [x] **S08: Libqmi Version Regex Hotfix** `risk:medium` `depends:[S07]`
  > After this: unit tests prove libqmi-version-regex-hotfix works

- [x] **S09: Dms Revision Parser Hotfix** `risk:medium` `depends:[S08]`
  > After this: unit tests prove dms-revision-parser-hotfix works

- [x] **S10: Qmi Proxy Retry Hotfix** `risk:medium` `depends:[S09]`
  > After this: unit tests prove qmi-proxy-retry-hotfix works

- [x] **S11: S11** `risk:medium` `depends:[]`
  > After this: unit tests prove Cutover & Fleet Rollout works

- [ ] **S12: V1 Decommission & Archive** `risk:medium` `depends:[S11]`
  > After this: unit tests prove v1 Decommission & Archive works
