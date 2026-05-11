"""Tests for QmiWrapper.dms_get_revision — the Phase 5 read-only wrapper
method added for fleet-fixture firmware capture (X-02).

Tests mirror the shape of test_wrapper.py:_QUERY_METHODS parametrized table:
Test 1 asserts the argv shape (including --device-open-proxy and the
read-only timeout); Test 2 asserts the method does NOT raise the
_in_critical_section flag (read-only verb).
"""

from __future__ import annotations

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


async def test_dms_get_revision_uses_device_open_proxy_and_correct_argv() -> None:
    """dms_get_revision invokes the runner with the canonical read-only argv
    shape: qmicli --device-open-proxy --device=<device> --dms-get-revision.
    """
    runner = FakeRunner()
    expected_argv = [
        "qmicli",
        "--device-open-proxy",
        f"--device={_DEVICE}",
        "--dms-get-revision",
    ]
    runner.register(expected_argv, _ok(expected_argv))

    wrapper = QmiWrapper(runner=runner, device=_DEVICE)
    cp = await wrapper.dms_get_revision()
    assert cp.exit_code == 0

    assert len(runner.calls) == 1
    recorded = runner.calls[0]
    assert recorded == expected_argv
    assert recorded.count("--device-open-proxy") == 1


async def test_dms_get_revision_does_not_set_critical_section_flag() -> None:
    """Read-only verb: _in_critical_section MUST remain False before, during,
    and after the runner call.
    """

    class _RecordingRunner:
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

    holder: dict[str, QmiWrapper] = {}
    runner = _RecordingRunner(holder)
    wrapper = QmiWrapper(runner=runner, device=_DEVICE)
    holder["w"] = wrapper

    assert wrapper.in_critical_section is False
    await wrapper.dms_get_revision()
    assert runner.observed_in_critical == [False], runner.observed_in_critical
    assert wrapper.in_critical_section is False
