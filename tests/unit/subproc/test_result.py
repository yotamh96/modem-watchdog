"""Tests for CompletedProcess and SubprocSpawnError (TDD RED -> GREEN).

SP-02 'all errors are data' contract:
  - CompletedProcess is frozen, slotted, with a defensive-copy argv tuple.
  - succeeded/failed properties reflect the SP-02 logic.
  - SubprocSpawnError is an OSError subclass carrying argv + original cause.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from spark_modem.subproc.errors import SubprocSpawnError
from spark_modem.subproc.result import CompletedProcess


class TestCompletedProcess:
    """Spec for CompletedProcess: frozen dataclass + properties."""

    def test_construction_succeeds(self) -> None:
        """CompletedProcess constructs with typical successful values."""
        cp = CompletedProcess(
            argv=("/bin/echo", "hi"),
            exit_code=0,
            stdout=b"hi\n",
            stderr=b"",
            duration_monotonic=0.01,
            timed_out=False,
        )
        assert cp.argv == ("/bin/echo", "hi")
        assert cp.exit_code == 0
        assert cp.stdout == b"hi\n"
        assert cp.stderr == b""
        assert cp.duration_monotonic == pytest.approx(0.01)
        assert cp.timed_out is False
        assert cp.kill_signal is None

    def test_make_classmethod_converts_list_to_tuple(self) -> None:
        """CompletedProcess.make() accepts a list[str] and stores argv as tuple."""
        cp = CompletedProcess.make(
            ["/bin/echo", "hi"],
            exit_code=0,
            stdout=b"hi\n",
            stderr=b"",
            duration_monotonic=0.01,
        )
        assert cp.argv == ("/bin/echo", "hi")
        assert isinstance(cp.argv, tuple)

    def test_frozen_rejects_attribute_assignment(self) -> None:
        """CompletedProcess is frozen -- field assignment raises FrozenInstanceError."""
        cp = CompletedProcess(
            argv=("/bin/echo",),
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_monotonic=0.0,
            timed_out=False,
        )
        with pytest.raises(FrozenInstanceError):
            cp.exit_code = 1  # type: ignore[misc]

    def test_argv_is_tuple_not_list(self) -> None:
        """argv stored on the instance is a tuple (defensive copy via make())."""
        original = ["/bin/echo", "world"]
        cp = CompletedProcess.make(
            original,
            exit_code=0,
            stdout=b"world\n",
            stderr=b"",
            duration_monotonic=0.005,
        )
        # Mutating the original list does not change the stored argv.
        original.append("--extra")
        assert cp.argv == ("/bin/echo", "world")
        assert isinstance(cp.argv, tuple)

    def test_succeeded_true_on_zero_exit_not_timed_out(self) -> None:
        """succeeded is True iff exit_code==0 and not timed_out."""
        cp = CompletedProcess.make(
            ["/bin/echo"],
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_monotonic=0.01,
            timed_out=False,
        )
        assert cp.succeeded is True
        assert cp.failed is False

    def test_succeeded_false_on_nonzero_exit(self) -> None:
        """succeeded is False when exit_code != 0."""
        cp = CompletedProcess.make(
            ["/bin/false"],
            exit_code=1,
            stdout=b"",
            stderr=b"",
            duration_monotonic=0.01,
        )
        assert cp.succeeded is False
        assert cp.failed is True

    def test_succeeded_false_when_timed_out(self) -> None:
        """succeeded is False even if exit_code==0 when timed_out is True."""
        cp = CompletedProcess.make(
            ["/bin/sleep", "10"],
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_monotonic=2.5,
            timed_out=True,
        )
        assert cp.succeeded is False
        assert cp.failed is True

    def test_failed_is_inverse_of_succeeded(self) -> None:
        """failed is always the inverse of succeeded."""
        for exit_code, timed_out in [(0, False), (1, False), (0, True), (-9, True)]:
            cp = CompletedProcess.make(
                ["/bin/echo"],
                exit_code=exit_code,
                stdout=b"",
                stderr=b"",
                duration_monotonic=0.01,
                timed_out=timed_out,
            )
            assert cp.failed is not cp.succeeded

    def test_kill_signal_field_stored(self) -> None:
        """kill_signal field is stored when provided (two-stage shutdown diagnostic)."""
        cp = CompletedProcess.make(
            ["/bin/sleep", "60"],
            exit_code=-9,
            stdout=b"",
            stderr=b"",
            duration_monotonic=2.3,
            timed_out=True,
            kill_signal=9,
        )
        assert cp.kill_signal == 9

    def test_make_defaults_timed_out_false(self) -> None:
        """CompletedProcess.make() defaults timed_out=False and kill_signal=None."""
        cp = CompletedProcess.make(
            ["/bin/echo"],
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_monotonic=0.01,
        )
        assert cp.timed_out is False
        assert cp.kill_signal is None


class TestSubprocSpawnError:
    """Spec for SubprocSpawnError: OSError subclass carrying argv + cause."""

    def test_is_oserror_subclass(self) -> None:
        """SubprocSpawnError is a subclass of OSError for compatibility."""
        original = OSError(13, "Permission denied")
        exc = SubprocSpawnError(["/bin/bad"], original)
        assert isinstance(exc, OSError)
        assert isinstance(exc, SubprocSpawnError)

    def test_carries_argv_as_tuple(self) -> None:
        """SubprocSpawnError stores the failing argv as a tuple."""
        argv = ["/bin/example", "--flag"]
        original = OSError(2, "No such file")
        exc = SubprocSpawnError(argv, original)
        assert exc.argv == ("/bin/example", "--flag")
        assert isinstance(exc.argv, tuple)

    def test_carries_original_exception(self) -> None:
        """SubprocSpawnError stores the original exception for diagnostics."""
        original = OSError(13, "Permission denied")
        exc = SubprocSpawnError(["/bin/bad"], original)
        assert exc.original is original

    def test_message_contains_argv(self) -> None:
        """SubprocSpawnError's string representation includes the argv."""
        original = OSError(2, "No such file or directory")
        exc = SubprocSpawnError(["/usr/bin/qmicli", "--device=/dev/cdc-wdm0"], original)
        msg = str(exc)
        assert "qmicli" in msg or "argv" in msg.lower(), (
            f"Expected argv in error message, got: {msg!r}"
        )

    def test_catchable_as_oserror(self) -> None:
        """SubprocSpawnError is catchable via `except OSError`."""
        original = OSError(1, "Operation not permitted")
        exc = SubprocSpawnError(["/bin/restricted"], original)
        try:
            raise exc
        except OSError as e:
            assert isinstance(e, SubprocSpawnError)

    def test_accepts_tuple_argv(self) -> None:
        """SubprocSpawnError also accepts tuple argv (for internal use)."""
        original = OSError(1, "test")
        exc = SubprocSpawnError(("/bin/cmd", "--opt"), original)
        assert exc.argv == ("/bin/cmd", "--opt")
