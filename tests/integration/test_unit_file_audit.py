"""Phase 3 unit-file audit — parses the .service file and asserts directives.

This test is the regression gate for U-01..U-05 + NFR-30. If a
future merge accidentally drops WatchdogSec= or sets
Restart=always, the test fails immediately.

Cross-platform — pure file parsing, no systemd interaction.
Plan 03-09's tests/integration/conftest.py does NOT auto-add
linux_only to this file (Issue #6 RESOLVED).
"""

from __future__ import annotations

from pathlib import Path

import pytest

_UNIT_PATH = Path(__file__).resolve().parents[2] / "debian" / "spark-modem-watchdog.service"
_LOGROTATE_PATH = Path(__file__).resolve().parents[2] / "debian" / "spark-modem-watchdog.logrotate"


def _read_unit() -> dict[str, list[str]]:
    text = _UNIT_PATH.read_text(encoding="utf-8")
    directives: dict[str, list[str]] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("["):
            continue
        if "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        directives.setdefault(key.strip(), []).append(value.strip())
    return directives


@pytest.fixture(scope="module")
def unit_directives() -> dict[str, list[str]]:
    return _read_unit()


def test_type_notify(unit_directives: dict[str, list[str]]) -> None:
    assert unit_directives.get("Type") == ["notify"]


def test_restart_on_failure(unit_directives: dict[str, list[str]]) -> None:
    # U-02 — clean SIGTERM exit must not trigger restart
    assert unit_directives.get("Restart") == ["on-failure"]


def test_start_limit_overrides_default(unit_directives: dict[str, list[str]]) -> None:
    # U-02 / PITFALLS §4.2 — default would brick fleet rollout
    assert unit_directives.get("StartLimitIntervalSec") == ["300"]
    assert unit_directives.get("StartLimitBurst") == ["20"]


def test_restart_sec_10(unit_directives: dict[str, list[str]]) -> None:
    assert unit_directives.get("RestartSec") == ["10"]


def test_watchdog_90s(unit_directives: dict[str, list[str]]) -> None:
    # U-04
    assert unit_directives.get("WatchdogSec") == ["90s"]


def test_capability_bounding_set_phase4_forward(
    unit_directives: dict[str, list[str]],
) -> None:
    # U-01 — preallocated for Phase 4 (CAP_SYS_MODULE)
    caps = unit_directives.get("CapabilityBoundingSet", [""])[0]
    assert "CAP_NET_ADMIN" in caps
    assert "CAP_SYS_ADMIN" in caps
    assert "CAP_SYS_MODULE" in caps
    assert "CAP_DAC_READ_SEARCH" in caps


def test_no_private_mounts(unit_directives: dict[str, list[str]]) -> None:
    # U-03 / PITFALLS §4.3 — incompatible with LoadCredential on systemd 245
    assert "PrivateMounts" not in unit_directives


def test_no_private_tmp(unit_directives: dict[str, list[str]]) -> None:
    # U-03 / PITFALLS §4.3 — drops for LoadCredential compat + /run visibility
    assert "PrivateTmp" not in unit_directives


def test_no_private_devices(unit_directives: dict[str, list[str]]) -> None:
    # U-03 — /dev/kmsg producer needs read access
    assert "PrivateDevices" not in unit_directives


def test_runtime_directory_preserve_yes(
    unit_directives: dict[str, list[str]],
) -> None:
    # U-03 / PITFALLS §4.4 — load-bearing
    assert unit_directives.get("RuntimeDirectoryPreserve") == ["yes"]


def test_protect_system_strict(unit_directives: dict[str, list[str]]) -> None:
    assert unit_directives.get("ProtectSystem") == ["strict"]


def test_no_new_privileges_yes(unit_directives: dict[str, list[str]]) -> None:
    # NFR-30
    assert unit_directives.get("NoNewPrivileges") == ["yes"]


def test_kill_mode_mixed(unit_directives: dict[str, list[str]]) -> None:
    assert unit_directives.get("KillMode") == ["mixed"]


def test_timeout_stop_sec(unit_directives: dict[str, list[str]]) -> None:
    # U-02 — 5s graceful + 5s buffer
    assert unit_directives.get("TimeoutStopSec") == ["10s"]


def test_load_credential_for_hmac_secret(
    unit_directives: dict[str, list[str]],
) -> None:
    # NFR-34 / ADR-0011 — HMAC secret via systemd credentials
    load_creds = unit_directives.get("LoadCredential", [])
    assert any("hmac-secret" in cred for cred in load_creds)


def test_exec_start_pre_includes_config_check(
    unit_directives: dict[str, list[str]],
) -> None:
    # U-05
    pres = unit_directives.get("ExecStartPre", [])
    assert any("config-check" in p for p in pres)


def test_user_root(unit_directives: dict[str, list[str]]) -> None:
    # NFR-30 — daemon runs as root; Phase 3 needs CAP_NET_ADMIN
    assert unit_directives.get("User") == ["root"]


def test_no_inbound_ipc_directives() -> None:
    # CLAUDE.md invariant #11 — no inbound IPC in v2.0
    text = _UNIT_PATH.read_text()
    assert "Sockets=" not in text
    assert "Accept=yes" not in text


def test_logrotate_snippet_create_mode() -> None:
    snippet = _LOGROTATE_PATH.read_text()
    # R-02 — create mode + empty postrotate
    assert "create 0640 root adm" in snippet
    assert "rotate 7" in snippet
    assert "size 100M" in snippet
    assert "daily" in snippet
    assert "compress" in snippet
    assert "delaycompress" in snippet
    assert "missingok" in snippet


def test_logrotate_postrotate_empty() -> None:
    snippet = _LOGROTATE_PATH.read_text()
    # R-02 — postrotate block exists but body is empty/comment-only;
    # daemon detects rotation via asyncinotify producer (R-01).
    assert "postrotate" in snippet
    assert "endscript" in snippet
    # Extract postrotate block content (between postrotate and endscript)
    lines = snippet.splitlines()
    in_block = False
    body_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped == "postrotate":
            in_block = True
            continue
        if stripped == "endscript":
            in_block = False
            break
        if in_block:
            body_lines.append(stripped)
    # Every non-empty line in the postrotate block must be a comment
    non_comment = [b for b in body_lines if b and not b.startswith("#")]
    assert non_comment == [], f"postrotate body should be empty/comment-only, got: {non_comment}"
