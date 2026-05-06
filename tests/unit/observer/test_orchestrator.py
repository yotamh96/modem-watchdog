"""Unit tests for observer.orchestrator + observer.issue_extractor.

Covers:
  - parallel TaskGroup probe correctness (4 modems return 4 snapshots)
  - Zao-active short-circuit (no qmicli calls for active lines)
  - per-task asyncio.timeout(8s) isolating one slow probe (siblings unaffected)
  - per-task try/except (NFR-11): exception in one probe does not propagate
  - empty modem list returns empty list
  - extract_issues coverage of the major RECOVERY_SPEC §4 categories
  - extract_issues uses WhoModem(usb_path=modem.usb_path, cdc_wdm=modem.cdc_wdm)
    -- catches the placeholder-bug self-test referenced in PLAN task 2.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from spark_modem.inventory.descriptor import ModemDescriptor
from spark_modem.observer.issue_extractor import extract_issues
from spark_modem.observer.orchestrator import observe_all
from spark_modem.qmi.errors import QmiError, QmiErrorReason
from spark_modem.qmi.parsers.get_current_settings import GetCurrentSettingsResult
from spark_modem.qmi.parsers.get_data_session import GetDataSessionResult
from spark_modem.qmi.parsers.get_operating_mode import GetOperatingModeResult
from spark_modem.qmi.parsers.get_profile_settings import GetProfileSettingsResult
from spark_modem.qmi.parsers.get_sim_state import GetSimStateResult
from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.subproc.result import CompletedProcess
from spark_modem.wire.diag import Issue, ModemSnapshot, SignalSnapshot, WhoModem
from spark_modem.wire.enums import IssueCategory, IssueDetail, RegistrationState
from tests.fakes.clock import FakeClock
from tests.fakes.runner import FakeRunner
from tests.fakes.zao_log import FixtureZaoTailer

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "qmicli"


def _read_fixture(intent: str, scenario: str, version: str = "1.30") -> bytes:
    """Read a qmicli fixture as bytes (line-1 comment is part of the parser input)."""
    return (_FIXTURES / intent / version / f"{scenario}.txt").read_bytes()


def _make_modems(count: int = 4) -> list[ModemDescriptor]:
    return [
        ModemDescriptor(
            line=idx + 1,
            cdc_wdm=f"cdc-wdm{idx}",
            usb_path=f"2-3.1.{idx + 1}",
            ns=f"line{idx + 1}",
            iface="wwan0",
        )
        for idx in range(count)
    ]


def _ok(argv: list[str], stdout: bytes) -> CompletedProcess:
    return CompletedProcess.make(
        argv=argv,
        exit_code=0,
        stdout=stdout,
        stderr=b"",
        duration_monotonic=0.01,
        timed_out=False,
    )


def _register_healthy(runner: FakeRunner, modem: ModemDescriptor) -> None:
    """Register canned successful qmicli output for every query a probe will make."""
    device = f"/dev/{modem.cdc_wdm}"
    base = ["qmicli", "--device-open-proxy", f"--device={device}"]
    runner.register(
        [*base, "--nas-get-signal-info"],
        _ok([*base, "--nas-get-signal-info"], _read_fixture("get_signal", "lte_strong")),
    )
    runner.register(
        [*base, "--nas-get-serving-system"],
        _ok(
            [*base, "--nas-get-serving-system"],
            _read_fixture("get_serving_system", "registered_home"),
        ),
    )
    runner.register(
        [*base, "--uim-get-card-status"],
        _ok([*base, "--uim-get-card-status"], _read_fixture("get_sim_state", "ready")),
    )
    runner.register(
        [*base, "--wds-get-packet-service-status"],
        _ok(
            [*base, "--wds-get-packet-service-status"],
            _read_fixture("get_data_session", "connected"),
        ),
    )
    runner.register(
        [*base, "--wds-get-profile-settings=3gpp,1"],
        _ok(
            [*base, "--wds-get-profile-settings=3gpp,1"],
            _read_fixture("get_profile_settings", "profile1_internet"),
        ),
    )
    runner.register(
        [*base, "--wds-get-current-settings"],
        _ok(
            [*base, "--wds-get-current-settings"],
            _read_fixture("get_current_settings", "raw_ip_y"),
        ),
    )
    runner.register(
        [*base, "--dms-get-operating-mode"],
        _ok([*base, "--dms-get-operating-mode"], _read_fixture("get_operating_mode", "online")),
    )


def _factory(runner: FakeRunner) -> Callable[[ModemDescriptor], QmiWrapper]:
    def make(modem: ModemDescriptor) -> QmiWrapper:
        return QmiWrapper(runner=runner, device=f"/dev/{modem.cdc_wdm}")

    return make


# ---------------------------------------------------------------------------
# Orchestrator tests
# ---------------------------------------------------------------------------


async def test_observe_all_runs_probes_in_parallel() -> None:
    """Four modems -> four ModemSnapshots, ordered matching input."""
    modems = _make_modems(4)
    runner = FakeRunner()
    for m in modems:
        _register_healthy(runner, m)

    snapshots = await observe_all(modems, _factory(runner), FixtureZaoTailer(), FakeClock())

    assert len(snapshots) == 4
    assert [s.usb_path for s in snapshots] == [m.usb_path for m in modems]
    for s in snapshots:
        assert isinstance(s, ModemSnapshot)
        # The healthy fixtures produce a non-empty signal snapshot.
        assert s.signal.rsrp_dbm is not None


async def test_zao_active_short_circuits_qmicli() -> None:
    """Zao-active lines return zao-active snapshot with NO qmicli calls."""
    modems = _make_modems(4)
    runner = FakeRunner()
    # Only register canned answers for lines 3 and 4; lines 1 and 2 are
    # Zao-active so the orchestrator must NOT call the runner for them.
    for m in modems[2:]:
        _register_healthy(runner, m)

    zao = FixtureZaoTailer(active_lines={1, 2})

    snapshots = await observe_all(modems, _factory(runner), zao, FakeClock())

    assert len(snapshots) == 4
    # Inspect calls -- only modems 3 and 4 (cdc-wdm2/3) should have been hit.
    called_devices = {
        next(part for part in argv if part.startswith("--device=")) for argv in runner.calls
    }
    assert "--device=/dev/cdc-wdm0" not in called_devices
    assert "--device=/dev/cdc-wdm1" not in called_devices
    assert "--device=/dev/cdc-wdm2" in called_devices
    assert "--device=/dev/cdc-wdm3" in called_devices
    # Zao-active snapshots have empty issues + default SignalSnapshot.
    assert snapshots[0].issues == []
    assert snapshots[0].signal == SignalSnapshot()
    assert snapshots[1].issues == []
    assert snapshots[1].signal == SignalSnapshot()


class _SlowOnFirstRunner(FakeRunner):
    """Runner that hangs forever on the first modem's qmicli calls.

    Mirrors the FakeRunner surface but, before looking up a canned response,
    sleeps forever for argvs that target ``hang_device``. Other devices are
    served from the registered map.
    """

    def __init__(self, hang_device: str) -> None:
        super().__init__()
        self._hang_device = hang_device

    async def run(
        self,
        argv: list[str],
        *,
        timeout_s: float,
        stdin: bytes | None = None,
        env: dict[str, str] | None = None,
    ) -> CompletedProcess:
        if any(p.startswith(f"--device={self._hang_device}") for p in argv):
            # Block forever; the orchestrator's per-task asyncio.timeout
            # must cancel us.
            await asyncio.sleep(3600)
        return await super().run(argv, timeout_s=timeout_s, stdin=stdin, env=env)


async def test_one_slow_probe_does_not_cancel_siblings() -> None:
    """A slow probe times out per-task; the other three probes still complete."""
    modems = _make_modems(4)
    runner = _SlowOnFirstRunner(hang_device="/dev/cdc-wdm0")
    # Register only the non-hung modems; hung modem hits the sleep-forever path.
    for m in modems[1:]:
        _register_healthy(runner, m)

    t0 = time.monotonic()
    snapshots = await observe_all(
        modems,
        _factory(runner),
        FixtureZaoTailer(),
        FakeClock(),
        timeout_s=0.05,
    )
    elapsed = time.monotonic() - t0

    assert len(snapshots) == 4
    # Slow modem has the timed_out empty snapshot (no signal, no issues).
    assert snapshots[0].usb_path == modems[0].usb_path
    assert snapshots[0].signal == SignalSnapshot()
    assert snapshots[0].issues == []
    # Healthy modems have populated signal data.
    for snap in snapshots[1:]:
        assert snap.signal.rsrp_dbm is not None
    # Whole call should complete in well under 1s; per-task timeout is 50ms.
    assert elapsed < 1.0


class _BoomOnSpecificDeviceRunner(FakeRunner):
    """Runner that raises RuntimeError for a specific device's argv."""

    def __init__(self, boom_device: str) -> None:
        super().__init__()
        self._boom_device = boom_device

    async def run(
        self,
        argv: list[str],
        *,
        timeout_s: float,
        stdin: bytes | None = None,
        env: dict[str, str] | None = None,
    ) -> CompletedProcess:
        if any(p.startswith(f"--device={self._boom_device}") for p in argv):
            raise RuntimeError("boom")
        return await super().run(argv, timeout_s=timeout_s, stdin=stdin, env=env)


async def test_exception_in_probe_does_not_propagate_to_taskgroup() -> None:
    """RuntimeError in one probe is absorbed; siblings produce normal snapshots."""
    modems = _make_modems(4)
    runner = _BoomOnSpecificDeviceRunner(boom_device="/dev/cdc-wdm0")
    for m in modems[1:]:
        _register_healthy(runner, m)

    # observe_all must NOT raise -- the per-task try/except absorbs it.
    snapshots = await observe_all(
        modems,
        _factory(runner),
        FixtureZaoTailer(),
        FakeClock(),
    )
    assert len(snapshots) == 4
    # Boom modem snapshot is empty (issues=[], signal default).
    assert snapshots[0].usb_path == modems[0].usb_path
    assert snapshots[0].issues == []
    assert snapshots[0].signal == SignalSnapshot()
    # The other three probed normally.
    for snap in snapshots[1:]:
        assert snap.signal.rsrp_dbm is not None


async def test_empty_modem_list_returns_empty_list() -> None:
    """No modems -> empty list, no TaskGroup created."""
    runner = FakeRunner()
    result = await observe_all([], _factory(runner), FixtureZaoTailer(), FakeClock())
    assert result == []
    assert runner.calls == []


# ---------------------------------------------------------------------------
# extract_issues tests
# ---------------------------------------------------------------------------

_MODEM = ModemDescriptor(
    line=1,
    cdc_wdm="cdc-wdm0",
    usb_path="2-3.1.1",
    ns="line1",
    iface="wwan0",
)

_HEALTHY_PROFILE = GetProfileSettingsResult(profile_index=1, apn="internet", ip_family=4)
_HEALTHY_SIM = GetSimStateResult(card_state="present", app_state="ready")
_HEALTHY_DATA = GetDataSessionResult(connection_status="connected")
_HEALTHY_CURRENT = GetCurrentSettingsResult(ipv4="10.0.0.2", raw_ip="Y")
_HEALTHY_OP = GetOperatingModeResult(mode="online")


def _extract(
    *,
    profile: GetProfileSettingsResult | QmiError | None = None,
    sim: GetSimStateResult | QmiError | None = None,
    data: GetDataSessionResult | QmiError | None = None,
    current: GetCurrentSettingsResult | QmiError | None = None,
    operating: GetOperatingModeResult | QmiError | None = None,
    registration: RegistrationState | None = RegistrationState.REGISTERED_HOME,
    signal: SignalSnapshot | None = None,
) -> list[Issue]:
    """Helper: call extract_issues with healthy defaults except overrides."""
    return extract_issues(
        modem=_MODEM,
        signal=signal if signal is not None else SignalSnapshot(),
        registration=registration,
        sim=sim if sim is not None else _HEALTHY_SIM,
        data=data if data is not None else _HEALTHY_DATA,
        profile=profile if profile is not None else _HEALTHY_PROFILE,
        current=current if current is not None else _HEALTHY_CURRENT,
        operating=operating if operating is not None else _HEALTHY_OP,
    )


def test_extract_issues_apn_empty_produces_config_issue() -> None:
    profile = GetProfileSettingsResult(profile_index=1, apn="", ip_family=4)
    issues = _extract(profile=profile)
    assert len(issues) == 1
    assert issues[0].category == IssueCategory.CONFIG
    assert issues[0].detail == IssueDetail.APN_EMPTY


def test_extract_issues_sim_app_detected_produces_sim_issue() -> None:
    sim = GetSimStateResult(card_state="present", app_state="detected")
    issues = _extract(sim=sim)
    sim_issues = [i for i in issues if i.category == IssueCategory.SIM]
    assert len(sim_issues) == 1
    assert sim_issues[0].detail == IssueDetail.SIM_APP_DETECTED


def test_extract_issues_raw_ip_off_produces_datapath_issue() -> None:
    current = GetCurrentSettingsResult(ipv4=None, raw_ip="N")
    issues = _extract(current=current)
    dp_issues = [i for i in issues if i.category == IssueCategory.DATAPATH]
    assert len(dp_issues) == 1
    assert dp_issues[0].detail == IssueDetail.RAW_IP_OFF


def test_extract_issues_not_registered_searching_produces_registration_issue() -> None:
    issues = _extract(registration=RegistrationState.NOT_REGISTERED_SEARCHING)
    reg_issues = [i for i in issues if i.category == IssueCategory.REGISTRATION]
    assert len(reg_issues) == 1
    assert reg_issues[0].detail == IssueDetail.NOT_REGISTERED_SEARCHING


def test_extract_issues_proxy_died_produces_qmi_issue() -> None:
    sim_err = QmiError(reason=QmiErrorReason.PROXY_DIED, argv=("qmicli",), exit_code=1)
    issues = _extract(sim=sim_err)
    qmi_issues = [i for i in issues if i.category == IssueCategory.QMI]
    assert any(i.detail == IssueDetail.QMI_PROXY_DIED for i in qmi_issues)


def test_extract_issues_who_uses_modem_usb_path_and_cdc_wdm() -> None:
    """Self-test: every issue's `who` carries the modem's usb_path and cdc_wdm.

    Catches the placeholder-bug flagged in PLAN task 2: if the executor missed
    replacing the placeholder ``WhoModem(usb_path="", cdc_wdm=None)`` dummy
    with the modem-derived ``WhoModem``, this test fails with usb_path == "".
    """
    profile = GetProfileSettingsResult(profile_index=1, apn="", ip_family=4)
    sim = GetSimStateResult(card_state="present", app_state="detected")
    current = GetCurrentSettingsResult(ipv4=None, raw_ip="N")
    issues = _extract(
        profile=profile,
        sim=sim,
        current=current,
        registration=RegistrationState.NOT_REGISTERED_SEARCHING,
    )
    assert len(issues) >= 4  # at least one issue per category
    for issue in issues:
        who = issue.who
        assert who.kind == "modem"
        # `who` is the WhoModem variant of the discriminated union; mypy
        # narrows on the kind literal check above.
        assert isinstance(who, WhoModem)
        assert who.usb_path == _MODEM.usb_path
        assert who.cdc_wdm == _MODEM.cdc_wdm


# Sanity: pytest-asyncio is configured mode=auto; our async tests need it.
def test_async_tests_have_pytest_asyncio() -> None:
    pytest.importorskip("pytest_asyncio")
