"""Tests for QmiWrapper -- proxy-mandatory invariant, _in_critical_section
flag, classify() short-circuit signatures.

Uses tests.fakes.runner.FakeRunner so no real subprocess is spawned.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from spark_modem.qmi.errors import QmiErrorReason
from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.subproc.result import CompletedProcess
from tests.fakes.runner import FakeRunner

_DEVICE = "/dev/cdc-wdm0"


def _ok(argv: list[str]) -> CompletedProcess:
    """Stub a healthy success CompletedProcess for an argv."""
    return CompletedProcess.make(
        argv=argv,
        exit_code=0,
        stdout=b"ok\n",
        stderr=b"",
        duration_monotonic=0.01,
        timed_out=False,
    )


# Each entry is (label, awaitable-method-factory, expected-argv-suffix).
# The factory takes a wrapper and returns the coroutine to await.
_QUERY_METHODS: list[tuple[str, Callable[[QmiWrapper], Awaitable[CompletedProcess]], list[str]]] = [
    (
        "nas_get_signal_info",
        lambda w: w.nas_get_signal_info(),
        ["--nas-get-signal-info"],
    ),
    (
        "nas_get_serving_system",
        lambda w: w.nas_get_serving_system(),
        ["--nas-get-serving-system"],
    ),
    (
        "uim_get_card_status",
        lambda w: w.uim_get_card_status(),
        ["--uim-get-card-status"],
    ),
    (
        "wds_get_packet_service_status",
        lambda w: w.wds_get_packet_service_status(),
        ["--wds-get-packet-service-status"],
    ),
    (
        "wds_get_profile_settings",
        lambda w: w.wds_get_profile_settings(profile_index=1),
        ["--wds-get-profile-settings=3gpp,1"],
    ),
    (
        "wds_get_current_settings",
        lambda w: w.wds_get_current_settings(),
        ["--wds-get-current-settings"],
    ),
    (
        "dms_get_operating_mode",
        lambda w: w.dms_get_operating_mode(),
        ["--dms-get-operating-mode"],
    ),
]

_STATE_CHANGE_METHODS: list[
    tuple[str, Callable[[QmiWrapper], Awaitable[CompletedProcess]], list[str]]
] = [
    (
        "dms_set_operating_mode",
        lambda w: w.dms_set_operating_mode("online"),
        ["--dms-set-operating-mode=online"],
    ),
    (
        "uim_sim_power_on",
        lambda w: w.uim_sim_power_on(slot=1),
        ["--uim-sim-power-on=1"],
    ),
    (
        "wds_modify_profile",
        lambda w: w.wds_modify_profile(profile_index=1, apn="internet"),
        ["--wds-modify-profile=3gpp,1,apn=internet,ip-family=4"],
    ),
    (
        "wds_set_ip_family",
        lambda w: w.wds_set_ip_family(family=4),
        ["--wds-set-ip-family=4"],
    ),
]

_ALL_METHODS = _QUERY_METHODS + _STATE_CHANGE_METHODS


@pytest.mark.parametrize(
    ("label", "invoke", "argv_suffix"),
    _ALL_METHODS,
    ids=[m[0] for m in _ALL_METHODS],
)
async def test_every_call_uses_device_open_proxy(
    label: str,
    invoke: Callable[[QmiWrapper], Awaitable[CompletedProcess]],
    argv_suffix: list[str],
) -> None:
    """Every qmicli invocation must include --device-open-proxy and
    --device=/dev/cdc-wdm0 (FR-74 / PITFALLS §1.5).
    """
    del label  # used only for parametrize id
    runner = FakeRunner()
    expected_argv = ["qmicli", "--device-open-proxy", f"--device={_DEVICE}", *argv_suffix]
    runner.register(expected_argv, _ok(expected_argv))

    wrapper = QmiWrapper(runner=runner, device=_DEVICE)
    result = await invoke(wrapper)
    assert result.succeeded

    assert len(runner.calls) == 1
    recorded = runner.calls[0]
    assert recorded.count("--device-open-proxy") == 1, recorded
    device_args = [a for a in recorded if a.startswith("--device=")]
    assert device_args == [f"--device={_DEVICE}"], recorded


class _RecordingRunner:
    """Captures wrapper.in_critical_section at the moment run() is invoked.

    Lets tests assert the flag is True *during* the runner call (not just
    before/after) for state-changing methods, and False *during* query calls.
    """

    def __init__(self, wrapper_holder: dict[str, QmiWrapper]) -> None:
        self._wrapper_holder = wrapper_holder
        self.observed_in_critical: list[bool] = []

    async def run(
        self,
        argv: list[str],
        *,
        timeout_s: float,
        stdin: bytes | None = None,
        env: dict[str, str] | None = None,
    ) -> CompletedProcess:
        del timeout_s, stdin, env
        wrapper = self._wrapper_holder["w"]
        self.observed_in_critical.append(wrapper.in_critical_section)
        return _ok(list(argv))


@pytest.mark.parametrize(
    ("label", "invoke"),
    [(label, invoke) for (label, invoke, _suffix) in _QUERY_METHODS],
    ids=[m[0] for m in _QUERY_METHODS],
)
async def test_query_methods_do_not_set_critical_flag(
    label: str,
    invoke: Callable[[QmiWrapper], Awaitable[CompletedProcess]],
) -> None:
    """Read-only query methods must NOT set _in_critical_section."""
    del label
    holder: dict[str, QmiWrapper] = {}
    runner = _RecordingRunner(holder)
    wrapper = QmiWrapper(runner=runner, device=_DEVICE)
    holder["w"] = wrapper

    assert wrapper.in_critical_section is False
    await invoke(wrapper)
    assert runner.observed_in_critical == [False], runner.observed_in_critical
    assert wrapper.in_critical_section is False


@pytest.mark.parametrize(
    ("label", "invoke"),
    [(label, invoke) for (label, invoke, _suffix) in _STATE_CHANGE_METHODS],
    ids=[m[0] for m in _STATE_CHANGE_METHODS],
)
async def test_state_changing_methods_set_critical_flag(
    label: str,
    invoke: Callable[[QmiWrapper], Awaitable[CompletedProcess]],
) -> None:
    """State-changing methods must set _in_critical_section=True for the
    duration of the runner call and clear it afterward (PITFALLS §1.4).
    """
    del label
    holder: dict[str, QmiWrapper] = {}
    runner = _RecordingRunner(holder)
    wrapper = QmiWrapper(runner=runner, device=_DEVICE)
    holder["w"] = wrapper

    assert wrapper.in_critical_section is False
    await invoke(wrapper)
    assert runner.observed_in_critical == [True], runner.observed_in_critical
    assert wrapper.in_critical_section is False


async def test_state_changing_method_clears_flag_on_runner_failure() -> None:
    """Even if the runner raises, _in_critical_section must be cleared."""

    class _RaisingRunner:
        async def run(
            self,
            argv: list[str],
            *,
            timeout_s: float,
            stdin: bytes | None = None,
            env: dict[str, str] | None = None,
        ) -> CompletedProcess:
            del argv, timeout_s, stdin, env
            raise RuntimeError("boom")

    wrapper = QmiWrapper(runner=_RaisingRunner(), device=_DEVICE)
    with pytest.raises(RuntimeError, match="boom"):
        await wrapper.dms_set_operating_mode("online")
    assert wrapper.in_critical_section is False


def test_classify_proxy_died_signature() -> None:
    """The canonical proxy-died phrase must map to PROXY_DIED."""
    cp = CompletedProcess.make(
        argv=["qmicli", "--device-open-proxy", "--device=/dev/cdc-wdm0", "--nas-get-signal-info"],
        exit_code=1,
        stdout=b"",
        stderr=b"qmicli: couldn't open the QMI device: proxy unavailable\n",
        duration_monotonic=0.05,
        timed_out=False,
    )
    err = QmiWrapper.classify(cp)
    assert err is not None
    assert err.reason is QmiErrorReason.PROXY_DIED
    assert err.exit_code == 1
    assert "proxy unavailable" in err.stderr_excerpt


def test_classify_proxy_died_via_broken_pipe() -> None:
    """Broken-pipe stderr is also a proxy-died signature."""
    cp = CompletedProcess.make(
        argv=["qmicli", "--device-open-proxy", "--device=/dev/cdc-wdm0", "--nas-get-signal-info"],
        exit_code=1,
        stdout=b"",
        stderr=b"qmicli: write: Broken pipe\n",
        duration_monotonic=0.02,
        timed_out=False,
    )
    err = QmiWrapper.classify(cp)
    assert err is not None
    assert err.reason is QmiErrorReason.PROXY_DIED


def test_classify_timed_out_returns_timeout_reason() -> None:
    cp = CompletedProcess.make(
        argv=["qmicli", "--device-open-proxy", "--device=/dev/cdc-wdm0", "--nas-get-signal-info"],
        exit_code=-9,
        stdout=b"",
        stderr=b"",
        duration_monotonic=8.0,
        timed_out=True,
        kill_signal=9,
    )
    err = QmiWrapper.classify(cp)
    assert err is not None
    assert err.reason is QmiErrorReason.TIMEOUT
    assert err.exit_code == -9


def test_classify_timeout_wins_over_proxy_signature() -> None:
    """If a process timed out AND the residual stderr contains a proxy
    signature, TIMEOUT must be the operationally-meaningful reason --
    the call did not return in time, regardless of why.
    """
    cp = CompletedProcess.make(
        argv=["qmicli", "--device-open-proxy", "--device=/dev/cdc-wdm0", "--nas-get-signal-info"],
        exit_code=-9,
        stdout=b"",
        stderr=b"qmicli: couldn't open the QMI device: proxy unavailable\n",
        duration_monotonic=8.0,
        timed_out=True,
        kill_signal=9,
    )
    err = QmiWrapper.classify(cp)
    assert err is not None
    assert err.reason is QmiErrorReason.TIMEOUT


def test_classify_non_zero_exit_without_proxy_signature() -> None:
    cp = CompletedProcess.make(
        argv=["qmicli", "--device-open-proxy", "--device=/dev/cdc-wdm0", "--nas-get-signal-info"],
        exit_code=1,
        stdout=b"",
        stderr=b"misc error\n",
        duration_monotonic=0.05,
        timed_out=False,
    )
    err = QmiWrapper.classify(cp)
    assert err is not None
    assert err.reason is QmiErrorReason.NON_ZERO_EXIT
    assert err.exit_code == 1


def test_classify_success_returns_none() -> None:
    cp = CompletedProcess.make(
        argv=["qmicli", "--device-open-proxy", "--device=/dev/cdc-wdm0", "--nas-get-signal-info"],
        exit_code=0,
        stdout=b"signal info\n",
        stderr=b"",
        duration_monotonic=0.03,
        timed_out=False,
    )
    assert QmiWrapper.classify(cp) is None


def test_classify_stderr_excerpt_is_bounded() -> None:
    """stderr_excerpt must be capped at 512 bytes (T-02-02-01)."""
    big_stderr = b"x" * 4096
    cp = CompletedProcess.make(
        argv=["qmicli", "--device-open-proxy", "--device=/dev/cdc-wdm0", "--nas-get-signal-info"],
        exit_code=1,
        stdout=b"",
        stderr=big_stderr,
        duration_monotonic=0.05,
        timed_out=False,
    )
    err = QmiWrapper.classify(cp)
    assert err is not None
    # excerpt is decoded UTF-8; the source bytes were single-byte ASCII so
    # length matches the byte-cap of 512.
    assert len(err.stderr_excerpt) == 512


def test_constructor_rejects_empty_device() -> None:
    runner = FakeRunner()
    with pytest.raises(ValueError, match="non-empty"):
        QmiWrapper(runner=runner, device="")


def test_constructor_accepts_typical_device() -> None:
    """Sanity check: a normal device path constructs without complaint."""
    wrapper: Any = QmiWrapper(runner=FakeRunner(), device=_DEVICE)
    assert wrapper.device == _DEVICE
    assert wrapper.in_critical_section is False
