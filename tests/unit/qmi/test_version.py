"""Unit tests for qmi.version — libqmi version detection + FleetTriple.

Task 1 (Plan 05-02): detect_libqmi_version + QmiVersionDetectionFailed.
Task 3 (Plan 05-02): FleetTriple wire model + compute_fleet_triple orchestrator
                     (the latter four tests at the bottom of the file).

Pattern source: ``tests/unit/daemon/test_preflight.py`` for the monkeypatch +
``subproc_runner.run`` shape; ``CompletedProcess.make()`` for the result stub
(the dataclass field is ``duration_monotonic``, NOT ``duration_s``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from spark_modem.qmi.version import QmiVersionDetectionFailed, detect_libqmi_version
from spark_modem.subproc import runner as subproc_runner
from spark_modem.subproc.result import CompletedProcess

_FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "qmicli" / "version"


def _make_cp(
    *,
    argv: list[str],
    exit_code: int,
    stdout: bytes,
    stderr: bytes = b"",
) -> CompletedProcess:
    """Build a CompletedProcess for stubbed subproc_runner.run returns."""
    return CompletedProcess.make(
        argv=argv,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_monotonic=0.0,
        timed_out=False,
    )


# ---------------------------------------------------------------------------
# Task 1: detect_libqmi_version
# ---------------------------------------------------------------------------


async def test_detect_libqmi_version_parses_1_30(monkeypatch: pytest.MonkeyPatch) -> None:
    body = (_FIXTURE_ROOT / "1.30" / "standard.txt").read_bytes()
    seen_argv: list[list[str]] = []

    async def fake_run(argv: list[str], *, timeout_s: float, **_kw: object) -> CompletedProcess:
        del timeout_s
        seen_argv.append(list(argv))
        return _make_cp(argv=argv, exit_code=0, stdout=body)

    monkeypatch.setattr(subproc_runner, "run", fake_run)
    assert await detect_libqmi_version() == "1.30.6"
    # Test 6: argv is exactly ["qmicli", "--version"] (no extra flags).
    assert seen_argv == [["qmicli", "--version"]]


async def test_detect_libqmi_version_parses_1_32(monkeypatch: pytest.MonkeyPatch) -> None:
    body = (_FIXTURE_ROOT / "1.32" / "standard.txt").read_bytes()

    async def fake_run(argv: list[str], *, timeout_s: float, **_kw: object) -> CompletedProcess:
        del timeout_s
        return _make_cp(argv=argv, exit_code=0, stdout=body)

    monkeypatch.setattr(subproc_runner, "run", fake_run)
    assert await detect_libqmi_version() == "1.32.0"


async def test_non_zero_exit_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run(argv: list[str], *, timeout_s: float, **_kw: object) -> CompletedProcess:
        del timeout_s
        return _make_cp(argv=argv, exit_code=1, stdout=b"", stderr=b"boom")

    monkeypatch.setattr(subproc_runner, "run", fake_run)
    with pytest.raises(QmiVersionDetectionFailed, match="exit_code=1"):
        await detect_libqmi_version()


async def test_unparseable_stdout_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run(argv: list[str], *, timeout_s: float, **_kw: object) -> CompletedProcess:
        del timeout_s
        return _make_cp(argv=argv, exit_code=0, stdout=b"unrelated banner")

    monkeypatch.setattr(subproc_runner, "run", fake_run)
    with pytest.raises(QmiVersionDetectionFailed, match="did not match"):
        await detect_libqmi_version()


async def test_filenotfound_raises_qmiversiondetectionfailed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run(argv: list[str], *, timeout_s: float, **_kw: object) -> CompletedProcess:
        del timeout_s, argv
        raise FileNotFoundError("qmicli")

    monkeypatch.setattr(subproc_runner, "run", fake_run)
    with pytest.raises(QmiVersionDetectionFailed, match="not on PATH"):
        await detect_libqmi_version()


def test_qmiversiondetectionfailed_is_runtimeerror() -> None:
    assert issubclass(QmiVersionDetectionFailed, RuntimeError)
