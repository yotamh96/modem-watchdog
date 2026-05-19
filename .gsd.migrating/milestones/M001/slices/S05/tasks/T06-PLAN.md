# T06: Plan 06

**Slice:** S05 — **Milestone:** M001

## Description

Ship the X-03 known-fleet index directory inside the `.deb` package. Per RESEARCH Q10
§618-651: the simplest path is a one-line addition to `debian/spark-modem-watchdog.install`
that copies the entire `tests/fixtures/fleet/` tree to
`/etc/spark-modem-watchdog/known-fleet/`. dpkg handles atomic install-time replace;
no postinst changes; daemon is read-only.

Purpose: Without this plan, Plan 04's preflight check would have nothing to validate
against on the bench/field box, so the daemon would refuse to start on every fleet
box from Phase 6 onward. The example fixture (`tests/fixtures/fleet/_test/triple.json`)
shipped by Plan 03 ensures the directory is never empty at first install.

Output: 1-line addition to `debian/spark-modem-watchdog.install`, 1-line addition to
`debian/spark-modem-watchdog.dirs`, one integration test that verifies the .deb
contents (skipped on dev hosts without dpkg-deb).
