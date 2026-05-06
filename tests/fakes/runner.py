"""FakeRunner -- argv->CompletedProcess map for hardware-free Phase 2 tests.

Mirrors the call surface of `spark_modem.subproc.runner.run` so that any code
parameterized over a SubprocRunner-shaped callable can be exercised in unit
tests without spawning a real child process.

Usage:
    runner = FakeRunner()
    runner.register(
        ["qmicli", "--device-open-proxy", "--device=/dev/cdc-wdm0", ...],
        CompletedProcess.make(argv=..., exit_code=0, stdout=b"ok", stderr=b"",
                              duration_monotonic=0.01),
    )
    result = await runner.run(argv, timeout_s=1.0)

Calling `run()` for an argv that was never registered raises KeyError -- tests
should be explicit about every command they expect the code under test to
issue. The recorded `calls` list lets tests assert call order.
"""

from __future__ import annotations

from spark_modem.subproc.result import CompletedProcess


class FakeRunner:
    """Maps argv lists to canned CompletedProcess results for tests."""

    def __init__(self) -> None:
        self._responses: dict[tuple[str, ...], CompletedProcess] = {}
        self._calls: list[list[str]] = []

    def register(self, argv: list[str], result: CompletedProcess) -> None:
        """Register a canned result for an exact argv list match."""
        self._responses[tuple(argv)] = result

    @property
    def calls(self) -> list[list[str]]:
        """Return a defensive copy of the recorded call list."""
        return [list(c) for c in self._calls]

    async def run(
        self,
        argv: list[str],
        *,
        timeout_s: float,
        stdin: bytes | None = None,
        env: dict[str, str] | None = None,
    ) -> CompletedProcess:
        """Look up the canned response for argv; raise KeyError if unregistered.

        Signature mirrors `spark_modem.subproc.runner.run` exactly so that
        callers parameterized over a runner-shaped callable can be tested
        without modification. The keyword-only parameters are accepted for
        call-surface parity and intentionally ignored by the fake.
        """
        del timeout_s, stdin, env  # signature parity only
        self._calls.append(list(argv))
        key = tuple(argv)
        if key not in self._responses:
            raise KeyError(f"FakeRunner: no canned response for {argv!r}")
        return self._responses[key]
