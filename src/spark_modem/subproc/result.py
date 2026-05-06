"""CompletedProcess: the result type returned by subproc.runner.run().

SP-02 'all errors are data' model: every terminating outcome (success, non-zero
exit, timeout, stderr-detected proxy_died) is a CompletedProcess instance.
Genuinely-broken-runtime conditions raise (see errors.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CompletedProcess:
    """Result of subproc.runner.run().

    Frozen + slots — cheap to allocate, immutable, mypy-friendly. argv is
    stored as a tuple at construction time. Use the ``make()`` classmethod to
    construct from a list[str] (the common call path).
    """

    argv: tuple[str, ...]
    exit_code: int  # negative if killed by signal (e.g. -9 == SIGKILL)
    stdout: bytes
    stderr: bytes
    duration_monotonic: float
    timed_out: bool

    # Optional: what signal we sent during two-stage shutdown (None on success).
    # Useful for diagnostics; doesn't affect the data flow.
    kill_signal: int | None = field(default=None)

    @classmethod
    def make(
        cls,
        argv: list[str] | tuple[str, ...],
        *,
        exit_code: int,
        stdout: bytes,
        stderr: bytes,
        duration_monotonic: float,
        timed_out: bool = False,
        kill_signal: int | None = None,
    ) -> CompletedProcess:
        """Construct a CompletedProcess from a list or tuple of argv strings.

        Converts argv to a tuple (defensive copy — the caller's list is not
        retained). All other fields are passed through.
        """
        return cls(
            argv=tuple(argv),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_monotonic=duration_monotonic,
            timed_out=timed_out,
            kill_signal=kill_signal,
        )

    @property
    def succeeded(self) -> bool:
        """True iff the command exited with code 0 and did not time out."""
        return self.exit_code == 0 and not self.timed_out

    @property
    def failed(self) -> bool:
        """True iff not succeeded — inverse of succeeded."""
        return not self.succeeded
