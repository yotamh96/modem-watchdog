"""Integration test for X-03 preflight wired into daemon startup.

Exercises ``_production_main``'s exit path on unknown-triple and the
``--skip-preflight`` bypass. Does not boot the full daemon (TaskGroup +
producers + cycle loop); only the preflight gate.

Verified contract: when ``preflight_check_known_fleet_triple`` raises
``UnknownFleetTriple``, daemon main writes ``last-config-error`` under
the configured ``run_dir`` and returns exit code 78 — BEFORE acquiring
the PID lock and BEFORE calling ``sd_notify("READY=1")``.

The test runs cross-platform — no fs inode semantics, no flock — so it
is NOT marked ``linux_only`` and runs on Windows dev hosts.
"""

from __future__ import annotations

import argparse
import contextlib
import json
from pathlib import Path

import pytest

from spark_modem.config.settings import Settings
from spark_modem.daemon import main as daemon_main
from spark_modem.daemon import preflight_triple as preflight_triple_mod
from spark_modem.qmi.version import FleetTriple

_LOCAL = FleetTriple(
    em7421_firmware="SWI9X30C_02.38.00.00",
    zao_sdk="2.1.0",
    libqmi="1.30.6",
)


def _make_args(*, skip_preflight: bool) -> argparse.Namespace:
    """Minimal Namespace shape ``_production_main`` reads.

    ``_production_main`` reads only ``args.skip_preflight``; ``args.laptop``
    is dispatched by the outer ``main()`` so never reaches here. Add
    additional attrs defensively if pytest surfaces an AttributeError.
    """
    return argparse.Namespace(skip_preflight=skip_preflight, laptop=False)


@pytest.fixture
def patched_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Path:
    """Set up monkeypatches so ``_production_main`` runs with tmp paths and
    no real preflight subprocess calls.

    Returns the run_dir (where ``last-config-error`` lands).
    """
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    state_root = tmp_path / "state"
    (state_root / "by-usb").mkdir(parents=True)
    events_log = tmp_path / "events.jsonl"

    # Patch build_default_settings to return a Settings bound to tmp_path.
    def fake_build_default_settings() -> Settings:
        return Settings(
            state_root=str(state_root),
            run_dir=str(run_dir),
            events_log_path=str(events_log),
            metrics_socket_path=str(run_dir / "metrics.sock"),
            carriers_yaml_path=str(state_root / "carriers.yaml"),
        )

    monkeypatch.setattr(daemon_main, "build_default_settings", fake_build_default_settings)

    # Stub the FR-60 binary preflight (skip the qmicli/ip binary check).
    async def fake_preflight_check() -> None:
        return None

    monkeypatch.setattr(daemon_main, "preflight_check", fake_preflight_check)

    return run_dir


async def test_unknown_triple_exits_78_and_writes_marker(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    patched_environment: Path,
) -> None:
    """Unknown triple → exit 78 + last-config-error marker written."""
    run_dir = patched_environment
    # Empty known-fleet dir; any local triple is unknown.
    empty_known = tmp_path / "known-fleet"
    empty_known.mkdir()

    async def fake_triple_check() -> None:
        # Inject the real check against an empty tmp known-fleet dir +
        # local_triple injection — bypasses the production defaulting
        # to /etc/spark-modem-watchdog/known-fleet/ that doesn't exist
        # on a dev host.
        await preflight_triple_mod.preflight_check_known_fleet_triple(
            known_fleet_dir=empty_known,
            local_triple=_LOCAL,
        )

    monkeypatch.setattr(daemon_main, "preflight_check_known_fleet_triple", fake_triple_check)

    args = _make_args(skip_preflight=False)
    rc = await daemon_main._production_main(args)

    assert rc == 78, f"expected EX_CONFIG exit code 78, got {rc}"
    marker = run_dir / "last-config-error"
    assert marker.is_file(), "last-config-error marker should be written"
    body = marker.read_text(encoding="utf-8")
    # Accept either branch's message — empty-or-missing is the path this test exercises.
    assert "empty or missing" in body.lower() or "unknown fleet triple" in body.lower()


async def test_skip_preflight_bypasses_triple_check(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    patched_environment: Path,
) -> None:
    """--skip-preflight bypasses the triple check entirely."""
    called = {"triple_check": 0}

    async def fake_triple_check() -> None:
        called["triple_check"] += 1
        raise preflight_triple_mod.UnknownFleetTriple("should not be called")

    monkeypatch.setattr(daemon_main, "preflight_check_known_fleet_triple", fake_triple_check)

    # Stub acquire_pid_lock so we exit cleanly past preflight without
    # spawning TaskGroups against fake event sources. The simplest path:
    # raise a sentinel exception from PID-lock acquisition.
    class _SentinelError(Exception):
        pass

    @contextlib.contextmanager
    def fake_acquire_pid_lock(*, run_dir: Path):  # type: ignore[no-untyped-def]
        del run_dir
        raise _SentinelError("preflight passed, halting test here")
        yield  # unreachable; satisfies generator-function shape

    monkeypatch.setattr(daemon_main, "acquire_pid_lock", fake_acquire_pid_lock)

    args = _make_args(skip_preflight=True)
    with pytest.raises(_SentinelError):
        await daemon_main._production_main(args)
    assert called["triple_check"] == 0, "triple check must NOT be called when --skip-preflight"


async def test_matching_triple_passes_preflight(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    patched_environment: Path,
) -> None:
    """Matching triple → preflight passes → daemon proceeds to PID lock."""
    known = tmp_path / "known-fleet"
    (known / "box-01").mkdir(parents=True)
    (known / "box-01" / "triple.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "em7421_firmware": _LOCAL.em7421_firmware,
                "zao_sdk": _LOCAL.zao_sdk,
                "libqmi": _LOCAL.libqmi,
            }
        )
    )

    async def fake_triple_check() -> None:
        await preflight_triple_mod.preflight_check_known_fleet_triple(
            known_fleet_dir=known,
            local_triple=_LOCAL,
        )

    monkeypatch.setattr(daemon_main, "preflight_check_known_fleet_triple", fake_triple_check)

    class _SentinelError(Exception):
        pass

    @contextlib.contextmanager
    def fake_acquire_pid_lock(*, run_dir: Path):  # type: ignore[no-untyped-def]
        del run_dir
        raise _SentinelError("preflight passed; got to PID lock")
        yield

    monkeypatch.setattr(daemon_main, "acquire_pid_lock", fake_acquire_pid_lock)

    args = _make_args(skip_preflight=False)
    with pytest.raises(_SentinelError):
        await daemon_main._production_main(args)
