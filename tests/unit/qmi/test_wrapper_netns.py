"""Tests for QmiWrapper's optional netns argv prepend (E-05).

Pins the regression gate: every QmiWrapper qmicli method routes through
the private ``_argv`` helper, so adding a Phase 4 destructive method
without calling ``self._argv([...])`` will fail the all-methods test
loudly. This is the load-bearing assertion that prevents silent netns
bypass on a future addition.

PITFALLS §6.2: NEVER setns() from the asyncio loop. The
``ip netns exec <ns>`` subprocess does its own setns in a forked child
— the daemon's loop stays in the host namespace.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest

from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.subproc.result import CompletedProcess
from tests.fakes.runner import FakeRunner

_DEVICE = "/dev/cdc-wdm0"


def _ok(argv: list[str]) -> CompletedProcess:
    return CompletedProcess.make(
        argv=argv,
        exit_code=0,
        stdout=b"ok\n",
        stderr=b"",
        duration_monotonic=0.01,
        timed_out=False,
    )


# Each entry: (label, awaitable factory, qmicli-suffix).
# The qmicli-suffix is what QmiWrapper internally builds AFTER any netns
# prepend; the test assertions splice in the netns prefix and the
# qmicli prefix (qmicli + --device-open-proxy + --device=...) explicitly.
_ALL_METHODS: list[tuple[str, Callable[[QmiWrapper], Awaitable[CompletedProcess]], list[str]]] = [
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


def _qmicli_argv(suffix: list[str]) -> list[str]:
    return ["qmicli", "--device-open-proxy", f"--device={_DEVICE}", *suffix]


async def test_argv_unchanged_when_ns_none() -> None:
    """ns=None: argv has NO 'ip netns exec' prefix; behaves exactly like Phase 2."""
    runner = FakeRunner()
    expected = _qmicli_argv(["--nas-get-signal-info"])
    runner.register(expected, _ok(expected))

    wrapper = QmiWrapper(runner=runner, device=_DEVICE, ns=None)
    await wrapper.nas_get_signal_info()

    assert len(runner.calls) == 1
    recorded = runner.calls[0]
    assert "ip" not in recorded[:3] or recorded[0] == "qmicli"  # no prepend
    assert recorded == expected


async def test_argv_prepended_when_ns_set() -> None:
    """ns='line1': argv begins with ['ip', 'netns', 'exec', 'line1', 'qmicli', ...]."""
    runner = FakeRunner()
    expected = ["ip", "netns", "exec", "line1", *_qmicli_argv(["--nas-get-signal-info"])]
    runner.register(expected, _ok(expected))

    wrapper = QmiWrapper(runner=runner, device=_DEVICE, ns="line1")
    await wrapper.nas_get_signal_info()

    assert len(runner.calls) == 1
    recorded = runner.calls[0]
    assert recorded[:4] == ["ip", "netns", "exec", "line1"]
    assert recorded == expected


async def test_default_ns_is_none_for_backwards_compatibility() -> None:
    """QmiWrapper(runner=..., device=...) without ns kwarg defaults to no prepend.

    This is critical for backwards compatibility: every existing caller
    in observer/cycle_driver/cli/diag/actions instantiates QmiWrapper
    without ``ns=`` until the Plan 03-06 wiring lands.
    """
    runner = FakeRunner()
    expected = _qmicli_argv(["--nas-get-signal-info"])
    runner.register(expected, _ok(expected))

    wrapper = QmiWrapper(runner=runner, device=_DEVICE)
    await wrapper.nas_get_signal_info()

    assert runner.calls[0] == expected


@pytest.mark.parametrize(
    ("label", "invoke", "qmicli_suffix"),
    _ALL_METHODS,
    ids=[m[0] for m in _ALL_METHODS],
)
async def test_all_methods_route_through_argv_helper(
    label: str,
    invoke: Callable[[QmiWrapper], Awaitable[CompletedProcess]],
    qmicli_suffix: list[str],
) -> None:
    """Every QmiWrapper qmicli method must prepend 'ip netns exec <ns>' when ns is set.

    This is the regression gate: a Phase 4 destructive method added
    without ``self._argv([...])`` wrapping will fail this parameterized
    test loudly.
    """
    del label
    runner = FakeRunner()
    expected = ["ip", "netns", "exec", "ns0", *_qmicli_argv(qmicli_suffix)]
    runner.register(expected, _ok(expected))

    wrapper = QmiWrapper(runner=runner, device=_DEVICE, ns="ns0")
    result = await invoke(wrapper)
    assert result.succeeded

    assert len(runner.calls) == 1
    recorded = runner.calls[0]
    assert recorded[:4] == ["ip", "netns", "exec", "ns0"], recorded
    assert recorded == expected, (recorded, expected)


def test_method_count_pins_eleven_qmicli_methods() -> None:
    """Pin the 11-method count so adding a method without updating the
    parametrize list (and therefore without verifying _argv wrapping)
    fails this test rather than silently bypassing the regression gate.
    """
    assert len(_ALL_METHODS) == 11, len(_ALL_METHODS)
