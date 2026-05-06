"""Tests for tests.fakes.runner.FakeRunner."""

from __future__ import annotations

import pytest

from spark_modem.subproc.result import CompletedProcess
from tests.fakes.runner import FakeRunner


def _canned(argv: list[str]) -> CompletedProcess:
    return CompletedProcess.make(
        argv=argv,
        exit_code=0,
        stdout=b"ok",
        stderr=b"",
        duration_monotonic=0.01,
        timed_out=False,
    )


async def test_register_then_run_returns_canned_result() -> None:
    runner = FakeRunner()
    argv = ["qmicli", "--device-open-proxy", "--device=/dev/cdc-wdm0", "--dms-get-ids"]
    canned = _canned(argv)
    runner.register(argv, canned)

    result = await runner.run(argv, timeout_s=1.0)

    assert result is canned
    assert result.exit_code == 0
    assert result.stdout == b"ok"


async def test_unregistered_argv_raises_key_error() -> None:
    runner = FakeRunner()
    with pytest.raises(KeyError) as excinfo:
        await runner.run(["qmicli", "--unknown-flag"], timeout_s=1.0)
    assert "qmicli" in str(excinfo.value)


async def test_calls_records_invocations_in_order() -> None:
    runner = FakeRunner()
    a = ["qmicli", "--a"]
    b = ["qmicli", "--b"]
    c = ["qmicli", "--c"]
    runner.register(a, _canned(a))
    runner.register(b, _canned(b))
    runner.register(c, _canned(c))

    await runner.run(a, timeout_s=1.0)
    await runner.run(c, timeout_s=1.0)
    await runner.run(b, timeout_s=1.0)

    assert runner.calls == [a, c, b]
    # `calls` returns a defensive copy: mutating the result must not affect state.
    snapshot = runner.calls
    snapshot.append(["mutated"])
    assert runner.calls == [a, c, b]
