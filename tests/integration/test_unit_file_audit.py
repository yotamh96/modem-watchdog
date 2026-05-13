"""Phase 3 unit-file audit — parses the .service file and asserts directives.

This test is the regression gate for U-01..U-05 + NFR-30. If a
future merge accidentally drops WatchdogSec= or sets
Restart=always, the test fails immediately.

Cross-platform — pure file parsing, no systemd interaction.
Plan 03-09's tests/integration/conftest.py does NOT auto-add
linux_only to this file (Issue #6 RESOLVED).
"""

from __future__ import annotations

import importlib
import tomllib
from pathlib import Path

import pytest

_UNIT_PATH = Path(__file__).resolve().parents[2] / "debian" / "spark-modem-watchdog.service"
_LOGROTATE_PATH = Path(__file__).resolve().parents[2] / "debian" / "spark-modem-watchdog.logrotate"
_PYPROJECT_PATH = Path(__file__).resolve().parents[2] / "pyproject.toml"
_INSTALL_PATH = (
    Path(__file__).resolve().parents[2] / "debian" / "spark-modem-watchdog.install"
)


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


@pytest.fixture(scope="module")
def project_scripts() -> dict[str, str]:
    """Parse [project.scripts] from pyproject.toml. Returns {name: target}."""
    data = tomllib.loads(_PYPROJECT_PATH.read_text(encoding="utf-8"))
    scripts = data.get("project", {}).get("scripts", {})
    # mypy-strict: declare the result type explicitly.
    return dict(scripts)


@pytest.fixture(scope="module")
def install_map_dest_paths() -> list[str]:
    """Parse debian/spark-modem-watchdog.install. Returns the dest column."""
    dest_paths: list[str] = []
    for line in _INSTALL_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Lines are "<source> <dest>"; split on whitespace, take dest.
        parts = stripped.split()
        if len(parts) >= 2:
            dest_paths.append(parts[1])
    return dest_paths


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


def test_watchdog_180s(unit_directives: dict[str, list[str]]) -> None:
    # U-04; Phase 05.6 C-03 bump (3× the 60s production cycle interval).
    assert unit_directives.get("WatchdogSec") == ["180s"]


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


# ----------------------------------------------------------------------
# Phase 05.1 V-04 audit extensions — drift detection for unit ↔ pyproject
# ↔ install layout. Catches future regressions of the bug class that
# made Plan 05.1 necessary.
# ----------------------------------------------------------------------


def test_v04_exec_paths_anchored(
    unit_directives: dict[str, list[str]],
    project_scripts: dict[str, str],
    install_map_dest_paths: list[str],
) -> None:
    """V-04 (a): every ExecStart/ExecStartPre binary path is anchored in
    either [project.scripts] (console-script materialized by uv pip
    install .) OR in debian/.install (file shipped explicitly).
    """
    # Console-scripts live at /opt/spark-modem-watchdog/python/bin/<name>.
    # Build the expected console-script paths from project_scripts.
    console_script_paths = {
        f"/opt/spark-modem-watchdog/python/bin/{name}" for name in project_scripts
    }
    # The .install map's dest column gives /opt/spark-modem-watchdog/libexec/
    # for the smoke script; build the full path from "<dest><filename>".
    # For the smoke script case: dest_path is /opt/.../libexec/, source
    # was scripts/postinst_smoke_test.sh, so the installed path is
    # /opt/.../libexec/postinst_smoke_test.sh. We compute this explicitly
    # for the one current entry to avoid generic install-map-parser
    # complexity.
    installed_paths = {
        "/opt/spark-modem-watchdog/libexec/postinst_smoke_test.sh",
    }
    all_anchored = console_script_paths | installed_paths

    def first_token(s: str) -> str:
        # ExecStart=path [args...] — the binary path is the first token.
        return s.split(None, 1)[0]

    offending: list[str] = []
    for key in ("ExecStart", "ExecStartPre"):
        for value in unit_directives.get(key, []):
            binary = first_token(value)
            if binary not in all_anchored:
                offending.append(f"{key}={value!r} → binary {binary!r} not anchored")
    assert not offending, (
        "V-04 (a) drift detected — every ExecStart/ExecStartPre binary path "
        "MUST be either a console-script in pyproject.toml [project.scripts] "
        "or a file shipped via debian/spark-modem-watchdog.install. "
        f"Offenders: {offending}. "
        f"Expected anchors: {sorted(all_anchored)}."
    )


def test_v04_load_credential_path_matches_fallback(
    unit_directives: dict[str, list[str]],
) -> None:
    """V-04 (b): LoadCredential= source path == L-02 fallback path.

    A single file on disk serves both worlds (systemd 247+ via
    LoadCredential and systemd 245 via direct read in
    Settings.resolve_hmac_secret_path()). If they drift, one of the two
    code paths breaks silently.
    """
    load_creds = unit_directives.get("LoadCredential", [])
    # Format: "ID:PATH" — extract PATH and assert it.
    for cred in load_creds:
        if "hmac-secret" in cred:
            _id, _, path = cred.partition(":")
            assert path == "/etc/spark-modem-watchdog/hmac-secret", (
                f"V-04 (b) drift: LoadCredential path {path!r} != "
                f"L-02 fallback path '/etc/spark-modem-watchdog/hmac-secret'"
            )
            return
    pytest.fail("V-04 (b): no LoadCredential= directive matching 'hmac-secret' found")


def test_v04_project_scripts_entry_points_importable(
    project_scripts: dict[str, str],
) -> None:
    """V-04 (c): every [project.scripts] entry imports cleanly + the attr exists."""
    for name, target in project_scripts.items():
        assert ":" in target, f"V-04 (c): {name}={target!r} not in module:attr shape"
        module_path, _, attr_name = target.partition(":")
        try:
            mod = importlib.import_module(module_path)
        except ImportError as exc:
            pytest.fail(
                f"V-04 (c): [project.scripts] {name}={target!r} — "
                f"module {module_path!r} failed to import: {exc}"
            )
        assert hasattr(mod, attr_name), (
            f"V-04 (c): [project.scripts] {name}={target!r} — "
            f"module {module_path!r} has no attribute {attr_name!r}"
        )
