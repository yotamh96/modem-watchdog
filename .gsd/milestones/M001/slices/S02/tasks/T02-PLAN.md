# T02: 02-core-daemon-laptop-testable 02

**Slice:** S02 — **Milestone:** M001

## Description

Plan 02-02 lands the qmicli boundary: a single `QmiWrapper` class that owns
every qmicli invocation in the daemon (via the existing `subproc.run`
plumbing), seven per-intent parser modules that turn qmicli text output into
typed records, and the per-libqmi-version fixture set.

Purpose: every other Phase 2 module that wants to talk to a modem (observer,
actions, CLI) goes through `QmiWrapper`. By centralising the qmicli surface
here we (a) keep `--device-open-proxy` always-on (FR-74), (b) keep the
boundary `extra='ignore'` so a libqmi point-release doesn't break the daemon,
and (c) give downstream plans a stable typed return value rather than raw
text.

Output: `qmi/wrapper.py`, `qmi/parsers/*.py`, `qmi/errors.py`, the per-version
qmicli fixture tree, and unit tests parametrized over every fixture.

## Must-Haves

- [ ] "QmiWrapper invokes qmicli only via spark_modem.subproc.run with --device-open-proxy on every call."
- [ ] "Calling qmicli without --device-open-proxy raises QmiError(reason='proxy_unavailable_required') at construction (defensive)."
- [ ] "Per-intent parsers return typed dataclasses; new libqmi fields absorbed via extra='ignore'."
- [ ] "Required-but-absent fields surface as QmiError(reason='missing_field', field=<name>) rather than silent None."
- [ ] "Each fixture file declares its libqmi version on line 1 (`# libqmi_version: <ver>`); parser is version-agnostic."
- [ ] "QmiWrapper sets _in_critical_section=True around state-changing calls (set_apn, set_operating_mode, sim_power_on)."
- [ ] "QMI proxy crash signature ('proxy unavailable' / 'broken pipe' in stderr) maps to QmiError(reason='proxy_died')."

## Files

- `src/spark_modem/qmi/__init__.py`
- `src/spark_modem/qmi/errors.py`
- `src/spark_modem/qmi/wrapper.py`
- `src/spark_modem/qmi/parsers/__init__.py`
- `src/spark_modem/qmi/parsers/get_signal.py`
- `src/spark_modem/qmi/parsers/get_serving_system.py`
- `src/spark_modem/qmi/parsers/get_sim_state.py`
- `src/spark_modem/qmi/parsers/get_data_session.py`
- `src/spark_modem/qmi/parsers/get_profile_settings.py`
- `src/spark_modem/qmi/parsers/get_operating_mode.py`
- `src/spark_modem/qmi/parsers/get_current_settings.py`
- `src/spark_modem/qmi/parsers/_header.py`
- `tests/unit/qmi/__init__.py`
- `tests/unit/qmi/test_wrapper.py`
- `tests/unit/qmi/test_parsers.py`
- `tests/fixtures/qmicli/get_signal/1.30/lte_strong.txt`
- `tests/fixtures/qmicli/get_signal/1.30/lte_weak.txt`
- `tests/fixtures/qmicli/get_signal/1.32/nr5g_present.txt`
- `tests/fixtures/qmicli/get_serving_system/1.30/registered_home.txt`
- `tests/fixtures/qmicli/get_serving_system/1.30/not_registered_searching.txt`
- `tests/fixtures/qmicli/get_sim_state/1.30/ready.txt`
- `tests/fixtures/qmicli/get_sim_state/1.30/sim_app_detected.txt`
- `tests/fixtures/qmicli/get_sim_state/1.30/sim_power_down.txt`
- `tests/fixtures/qmicli/get_data_session/1.30/connected.txt`
- `tests/fixtures/qmicli/get_data_session/1.30/disconnected.txt`
- `tests/fixtures/qmicli/get_profile_settings/1.30/profile1_internet.txt`
- `tests/fixtures/qmicli/get_operating_mode/1.30/online.txt`
- `tests/fixtures/qmicli/get_operating_mode/1.30/low_power.txt`
- `tests/fixtures/qmicli/get_current_settings/1.30/raw_ip_y.txt`
- `tests/fixtures/qmicli/get_current_settings/1.30/raw_ip_n.txt`
- `tests/fixtures/qmicli/proxy_error/proxy_died.txt`
