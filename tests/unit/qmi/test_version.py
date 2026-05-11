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
from pydantic import ValidationError

from spark_modem.qmi.version import (
    FleetTriple,
    QmiVersionDetectionFailed,
    compute_fleet_triple,
    detect_libqmi_version,
)
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


# ---------------------------------------------------------------------------
# Task 3: FleetTriple + compute_fleet_triple
# ---------------------------------------------------------------------------


class _FakeWrapper:
    """Minimal duck-typed stand-in for QmiWrapper.

    The production ``QmiWrapper.dms_get_revision`` (Plan 05-01) returns a
    ``CompletedProcess``; this fake returns one too. ``compute_fleet_triple``
    accepts ``wrapper: object`` and only calls ``wrapper.dms_get_revision()``
    so structural typing is sufficient (no need to subclass QmiWrapper or
    its Protocol seam).
    """

    def __init__(self, *, stdout: bytes, exit_code: int = 0) -> None:
        self._stdout = stdout
        self._exit_code = exit_code

    async def dms_get_revision(self) -> CompletedProcess:
        return CompletedProcess.make(
            argv=["qmicli", "--dms-get-revision"],
            exit_code=self._exit_code,
            stdout=self._stdout,
            stderr=b"",
            duration_monotonic=0.0,
            timed_out=False,
        )


_GET_REVISION_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "qmicli"
    / "get_revision"
    / "1.30"
    / "standard.txt"
)
_ZAO_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2] / "fixtures" / "zao_log" / "version"
)


def test_fleet_triple_is_frozen_and_extra_forbid() -> None:
    """FleetTriple is byte-reproducible: frozen + extra='forbid'."""
    triple = FleetTriple(em7421_firmware="X", zao_sdk="Y", libqmi="Z")
    # extra=forbid: unknown fields rejected.
    with pytest.raises(ValidationError):
        FleetTriple(  # type: ignore[call-arg]
            em7421_firmware="X",
            zao_sdk="Y",
            libqmi="Z",
            extra="nope",
        )
    # frozen: post-construction mutation rejected.
    with pytest.raises(ValidationError):
        triple.em7421_firmware = "mutated"  # type: ignore[misc]


async def test_compute_fleet_triple_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """All three probes succeed; FleetTriple has all three fields populated."""
    libqmi_body = (_FIXTURE_ROOT / "1.30" / "standard.txt").read_bytes()

    async def fake_run(
        argv: list[str], *, timeout_s: float, **_kw: object
    ) -> CompletedProcess:
        del timeout_s
        return _make_cp(argv=argv, exit_code=0, stdout=libqmi_body)

    monkeypatch.setattr(subproc_runner, "run", fake_run)

    fw_body = _GET_REVISION_FIXTURE.read_bytes()
    wrapper = _FakeWrapper(stdout=fw_body)
    zao_path = _ZAO_FIXTURE_ROOT / "banner_present.txt"

    triple = await compute_fleet_triple(wrapper=wrapper, zao_log_path=zao_path)
    assert triple.em7421_firmware == "SWI9X30C_02.38.00.00"
    assert triple.zao_sdk == "2.1.0"
    assert triple.libqmi == "1.30.6"


async def test_compute_fleet_triple_zao_unknown_sentinel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No Zao banner → zao_sdk = 'unknown' (preflight decides what to do)."""
    libqmi_body = (_FIXTURE_ROOT / "1.30" / "standard.txt").read_bytes()

    async def fake_run(
        argv: list[str], *, timeout_s: float, **_kw: object
    ) -> CompletedProcess:
        del timeout_s
        return _make_cp(argv=argv, exit_code=0, stdout=libqmi_body)

    monkeypatch.setattr(subproc_runner, "run", fake_run)

    fw_body = _GET_REVISION_FIXTURE.read_bytes()
    wrapper = _FakeWrapper(stdout=fw_body)
    zao_path = _ZAO_FIXTURE_ROOT / "no_banner.txt"

    triple = await compute_fleet_triple(wrapper=wrapper, zao_log_path=zao_path)
    assert triple.zao_sdk == "unknown"
    # Other two fields still populated.
    assert triple.em7421_firmware == "SWI9X30C_02.38.00.00"
    assert triple.libqmi == "1.30.6"


async def test_compute_fleet_triple_firmware_qmierror_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed dms_get_revision stdout → QmiVersionDetectionFailed."""
    libqmi_body = (_FIXTURE_ROOT / "1.30" / "standard.txt").read_bytes()

    async def fake_run(
        argv: list[str], *, timeout_s: float, **_kw: object
    ) -> CompletedProcess:
        del timeout_s
        return _make_cp(argv=argv, exit_code=0, stdout=libqmi_body)

    monkeypatch.setattr(subproc_runner, "run", fake_run)

    # Wrapper returns malformed stdout → parse_get_revision returns QmiError →
    # compute_fleet_triple raises QmiVersionDetectionFailed.
    wrapper = _FakeWrapper(stdout=b"completely malformed")
    zao_path = _ZAO_FIXTURE_ROOT / "banner_present.txt"

    with pytest.raises(
        QmiVersionDetectionFailed, match="dms_get_revision returned QmiError"
    ):
        await compute_fleet_triple(wrapper=wrapper, zao_log_path=zao_path)
