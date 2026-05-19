# Codebase Map

Generated: 2026-05-19T11:13:34Z | Files: 500 | Described: 0/500
<!-- gsd:codebase-meta {"generatedAt":"2026-05-19T11:13:34Z","fingerprint":"0c7d396a64ed32cf83acc1dafbfd2a47921d855c","fileCount":500,"truncated":true} -->
Note: Truncated to first 500 files. Run with higher --max-files to include all.

### (root)/
- `.gitignore`
- `.pre-commit-config.yaml`
- `.ruff.toml`
- `CLAUDE.md`
- `pyproject.toml`

### .github/workflows/
- `.github/workflows/build-deb.yml`
- `.github/workflows/ci-qemu-fallback.yml`
- `.github/workflows/ci.yml`
- `.github/workflows/hil.yml`

### artifacts/
- `artifacts/.gitkeep`

### debian/
- `debian/changelog`
- `debian/control`
- `debian/copyright`
- `debian/python.sha256`
- `debian/rules`
- `debian/spark-modem-watchdog.dirs`
- `debian/spark-modem-watchdog.install`
- `debian/spark-modem-watchdog.logrotate`
- `debian/spark-modem-watchdog.postinst`
- `debian/spark-modem-watchdog.postrm`
- `debian/spark-modem-watchdog.service`

### debian/conf.d/
- `debian/conf.d/00-carriers.yaml`

### debian/source/
- `debian/source/format`

### docs/
- `docs/ARCHITECTURE.md`
- `docs/FLEET_GATES.md`
- `docs/GLOSSARY.md`
- `docs/MIGRATION.md`
- `docs/PRD.md`
- `docs/README.md`
- `docs/RECOVERY_SPEC.md`
- `docs/RUNBOOK.md`
- `docs/SCHEMA.md`
- `docs/TEST_STRATEGY.md`

### docs/adr/
- `docs/adr/0001-language-python.md`
- `docs/adr/0002-event-driven-core.md`
- `docs/adr/0003-zao-authority.md`
- `docs/adr/0004-typed-contract.md`
- `docs/adr/0005-explicit-state-machine.md`
- `docs/adr/0006-counter-decay.md`
- `docs/adr/0007-monotonic-clock.md`
- `docs/adr/0008-state-machine-5-plus-2.md`
- `docs/adr/0009-state-files-keyed-by-usb-path.md`
- `docs/adr/0010-packaging-python-build-standalone.md`
- `docs/adr/0011-webhook-subsystem.md`
- `docs/adr/0012-concurrency-locks.md`
- `docs/adr/0013-metric-surface.md`
- `docs/adr/0014-v1-retired-pivot.md`
- `docs/adr/README.md`

### packaging/
- `packaging/requirements.in`

### scripts/
- `scripts/build_deb.sh`
- `scripts/lint_no_subprocess.sh`
- `scripts/postinst_smoke_test.sh`

### src/spark_modem/
- `src/spark_modem/__init__.py`
- `src/spark_modem/py.typed`

### src/spark_modem/actions/
- `src/spark_modem/actions/__init__.py`
- `src/spark_modem/actions/context.py`
- `src/spark_modem/actions/dispatcher.py`
- `src/spark_modem/actions/driver_reset.py`
- `src/spark_modem/actions/fix_autosuspend.py`
- `src/spark_modem/actions/fix_raw_ip.py`
- `src/spark_modem/actions/modem_reset.py`
- `src/spark_modem/actions/result.py`
- `src/spark_modem/actions/set_apn.py`
- `src/spark_modem/actions/set_operating_mode.py`
- `src/spark_modem/actions/sim_power_on.py`
- `src/spark_modem/actions/soft_reset.py`
- `src/spark_modem/actions/usb_reset.py`
- `src/spark_modem/actions/verify.py`

### src/spark_modem/cli/
- `src/spark_modem/cli/__init__.py`
- `src/spark_modem/cli/clients.py`
- `src/spark_modem/cli/diag.py`
- `src/spark_modem/cli/explain.py`
- `src/spark_modem/cli/main.py`
- `src/spark_modem/cli/provision.py`
- `src/spark_modem/cli/recovery.py`
- `src/spark_modem/cli/redact.py`
- `src/spark_modem/cli/reset.py`
- `src/spark_modem/cli/status.py`

### src/spark_modem/cli/ctl/
- `src/spark_modem/cli/ctl/__init__.py`
- `src/spark_modem/cli/ctl/capture_fleet_fixture.py`
- `src/spark_modem/cli/ctl/config_check.py`
- `src/spark_modem/cli/ctl/history.py`
- `src/spark_modem/cli/ctl/maintenance.py`
- `src/spark_modem/cli/ctl/support_bundle.py`

### src/spark_modem/clock/
- `src/spark_modem/clock/__init__.py`
- `src/spark_modem/clock/clock.py`

### src/spark_modem/config/
- `src/spark_modem/config/__init__.py`
- `src/spark_modem/config/reload_marker.py`
- `src/spark_modem/config/settings.py`
- `src/spark_modem/config/yaml_merge.py`

### src/spark_modem/daemon/
- `src/spark_modem/daemon/__init__.py`
- `src/spark_modem/daemon/cycle_driver.py`
- `src/spark_modem/daemon/cycle_scheduler.py`
- `src/spark_modem/daemon/lifecycle.py`
- `src/spark_modem/daemon/main.py`
- `src/spark_modem/daemon/preflight_triple.py`
- `src/spark_modem/daemon/preflight.py`
- `src/spark_modem/daemon/rss_tripwire.py`
- `src/spark_modem/daemon/sighup.py`
- `src/spark_modem/daemon/sigterm.py`

### src/spark_modem/event_logger/
- `src/spark_modem/event_logger/__init__.py`
- `src/spark_modem/event_logger/inotify_reopener.py`
- `src/spark_modem/event_logger/writer.py`

### src/spark_modem/event_sources/
- `src/spark_modem/event_sources/__init__.py`
- `src/spark_modem/event_sources/asyncinotify_producer.py`
- `src/spark_modem/event_sources/kmsg_producer.py`
- `src/spark_modem/event_sources/rtnetlink_producer.py`
- `src/spark_modem/event_sources/supervisor.py`
- `src/spark_modem/event_sources/udev_producer.py`

### src/spark_modem/inventory/
- `src/spark_modem/inventory/__init__.py`
- `src/spark_modem/inventory/descriptor.py`
- `src/spark_modem/inventory/netns.py`
- `src/spark_modem/inventory/protocol.py`
- `src/spark_modem/inventory/sysfs.py`
- `src/spark_modem/inventory/udev.py`

### src/spark_modem/kmsg/
- `src/spark_modem/kmsg/__init__.py`
- `src/spark_modem/kmsg/classifier.py`
- `src/spark_modem/kmsg/dedup.py`

### src/spark_modem/observer/
- `src/spark_modem/observer/__init__.py`
- `src/spark_modem/observer/diag_builder.py`
- `src/spark_modem/observer/issue_extractor.py`
- `src/spark_modem/observer/orchestrator.py`

### src/spark_modem/policy/
- `src/spark_modem/policy/__init__.py`
- `src/spark_modem/policy/context.py`
- `src/spark_modem/policy/decision_table.py`
- `src/spark_modem/policy/engine.py`
- `src/spark_modem/policy/gates.py`
- `src/spark_modem/policy/ladder.py`
- `src/spark_modem/policy/result.py`
- `src/spark_modem/policy/transitions.py`

### src/spark_modem/qmi/
- `src/spark_modem/qmi/__init__.py`
- `src/spark_modem/qmi/errors.py`
- `src/spark_modem/qmi/version.py`
- `src/spark_modem/qmi/wrapper.py`

### src/spark_modem/qmi/parsers/
- `src/spark_modem/qmi/parsers/__init__.py`
- `src/spark_modem/qmi/parsers/_header.py`
- `src/spark_modem/qmi/parsers/get_current_settings.py`
- `src/spark_modem/qmi/parsers/get_data_session.py`
- `src/spark_modem/qmi/parsers/get_operating_mode.py`
- `src/spark_modem/qmi/parsers/get_profile_settings.py`
- `src/spark_modem/qmi/parsers/get_revision.py`
- `src/spark_modem/qmi/parsers/get_serving_system.py`
- `src/spark_modem/qmi/parsers/get_signal.py`
- `src/spark_modem/qmi/parsers/get_sim_state.py`

### src/spark_modem/state_store/
- `src/spark_modem/state_store/__init__.py`
- `src/spark_modem/state_store/atomic.py`
- `src/spark_modem/state_store/errors.py`
- `src/spark_modem/state_store/inventory.py`
- `src/spark_modem/state_store/locks.py`
- `src/spark_modem/state_store/paths.py`
- `src/spark_modem/state_store/store.py`

### src/spark_modem/status_reporter/
- `src/spark_modem/status_reporter/__init__.py`
- `src/spark_modem/status_reporter/metrics_registry.py`
- `src/spark_modem/status_reporter/prom.py`
- `src/spark_modem/status_reporter/status.py`

### src/spark_modem/subproc/
- `src/spark_modem/subproc/__init__.py`
- `src/spark_modem/subproc/errors.py`
- `src/spark_modem/subproc/result.py`
- `src/spark_modem/subproc/runner.py`

### src/spark_modem/sysfs/
- `src/spark_modem/sysfs/__init__.py`
- `src/spark_modem/sysfs/usb_unbind_rebind.py`

### src/spark_modem/webhook/
- `src/spark_modem/webhook/__init__.py`
- `src/spark_modem/webhook/dedup.py`
- `src/spark_modem/webhook/dns.py`
- `src/spark_modem/webhook/poster.py`
- `src/spark_modem/webhook/sign.py`

### src/spark_modem/wire/
- `src/spark_modem/wire/__init__.py`
- `src/spark_modem/wire/_base.py`
- `src/spark_modem/wire/carriers.py`
- `src/spark_modem/wire/diag.py`
- `src/spark_modem/wire/enums.py`
- `src/spark_modem/wire/events.py`
- `src/spark_modem/wire/globals.py`
- `src/spark_modem/wire/identity.py`
- `src/spark_modem/wire/maintenance.py`
- `src/spark_modem/wire/state.py`
- `src/spark_modem/wire/status.py`
- `src/spark_modem/wire/versioning.py`
- `src/spark_modem/wire/webhook.py`

### src/spark_modem/zao_log/
- `src/spark_modem/zao_log/__init__.py`
- `src/spark_modem/zao_log/inotify_tailer.py`
- `src/spark_modem/zao_log/parser.py`
- `src/spark_modem/zao_log/protocol.py`
- `src/spark_modem/zao_log/snapshot.py`
- `src/spark_modem/zao_log/version.py`

### tests/
- `tests/__init__.py`
- `tests/conftest.py`

### tests/fakes/
- `tests/fakes/__init__.py`
- `tests/fakes/asyncinotify.py`
- `tests/fakes/clock.py`
- `tests/fakes/dns.py`
- `tests/fakes/inventory.py`
- `tests/fakes/kmsg.py`
- `tests/fakes/pidlock.py`
- `tests/fakes/rtnetlink.py`
- `tests/fakes/runner.py`
- `tests/fakes/sdnotify.py`
- `tests/fakes/sleeper.py`
- `tests/fakes/udev.py`
- `tests/fakes/webhook.py`
- `tests/fakes/zao_log.py`

### tests/fixtures/diag/
- `tests/fixtures/diag/.gitkeep`

### tests/fixtures/fleet/_test/
- `tests/fixtures/fleet/_test/triple.json`

### tests/fixtures/inventory/
- `tests/fixtures/inventory/.gitkeep`
- `tests/fixtures/inventory/four_modems_one_zao_active.json`
- `tests/fixtures/inventory/four_modems.json`
- `tests/fixtures/inventory/two_modems.json`

### tests/fixtures/kmsg/
- `tests/fixtures/kmsg/qmi_wwan_probe_fail.log`
- `tests/fixtures/kmsg/tegra_hub_psu_droop.log`
- `tests/fixtures/kmsg/thermal_throttle.log`
- `tests/fixtures/kmsg/usb_enum_failure.log`
- `tests/fixtures/kmsg/usb_overcurrent.log`

### tests/fixtures/qmicli/get_current_settings/1.30/
- `tests/fixtures/qmicli/get_current_settings/1.30/raw_ip_n.txt`
- `tests/fixtures/qmicli/get_current_settings/1.30/raw_ip_y.txt`

### tests/fixtures/qmicli/get_data_session/1.30/
- `tests/fixtures/qmicli/get_data_session/1.30/connected.txt`
- `tests/fixtures/qmicli/get_data_session/1.30/disconnected.txt`

### tests/fixtures/qmicli/get_operating_mode/1.30/
- `tests/fixtures/qmicli/get_operating_mode/1.30/low_power.txt`
- `tests/fixtures/qmicli/get_operating_mode/1.30/online.txt`

### tests/fixtures/qmicli/get_profile_settings/1.30/
- `tests/fixtures/qmicli/get_profile_settings/1.30/profile1_internet.txt`

### tests/fixtures/qmicli/get_revision/1.30/
- `tests/fixtures/qmicli/get_revision/1.30/jetpack-singular.txt`
- `tests/fixtures/qmicli/get_revision/1.30/standard.txt`

### tests/fixtures/qmicli/get_revision/1.32/
- `tests/fixtures/qmicli/get_revision/1.32/standard.txt`

### tests/fixtures/qmicli/get_serving_system/1.30/
- `tests/fixtures/qmicli/get_serving_system/1.30/not_registered_searching.txt`
- `tests/fixtures/qmicli/get_serving_system/1.30/registered_home.txt`

### tests/fixtures/qmicli/get_signal/1.30/
- `tests/fixtures/qmicli/get_signal/1.30/lte_strong.txt`
- `tests/fixtures/qmicli/get_signal/1.30/lte_weak.txt`

### tests/fixtures/qmicli/get_signal/1.32/
- `tests/fixtures/qmicli/get_signal/1.32/nr5g_present.txt`

### tests/fixtures/qmicli/get_sim_state/1.30/
- `tests/fixtures/qmicli/get_sim_state/1.30/ready.txt`
- `tests/fixtures/qmicli/get_sim_state/1.30/sim_app_detected.txt`
- `tests/fixtures/qmicli/get_sim_state/1.30/sim_power_down.txt`

### tests/fixtures/qmicli/proxy_error/
- `tests/fixtures/qmicli/proxy_error/proxy_died.txt`

### tests/fixtures/qmicli/uim_get_card_status/1.30/
- `tests/fixtures/qmicli/uim_get_card_status/1.30/with_iccid.txt`

### tests/fixtures/qmicli/version/1.30/
- `tests/fixtures/qmicli/version/1.30/jetpack-1.30.4.txt`
- `tests/fixtures/qmicli/version/1.30/standard.txt`

### tests/fixtures/qmicli/version/1.32/
- `tests/fixtures/qmicli/version/1.32/standard.txt`

### tests/fixtures/replay/
- `tests/fixtures/replay/.gitkeep`

### tests/fixtures/replay/apn_empty/
- *(136 files: 136 .json)*

### tests/fixtures/replay/healthy/
- *(50 files: 50 .json)*

### tests/fixtures/replay/operating_mode_low_power/
- *(78 files: 78 .json)*
