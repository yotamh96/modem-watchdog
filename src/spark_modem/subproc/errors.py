"""Exceptions raised by subproc.runner.run() — only on genuine runtime breakage.

SP-02 boundary: non-zero exit codes and timeouts are NOT exceptions; they are
fields on CompletedProcess. Exceptions are reserved for cases where the
subprocess didn't actually run (binary missing, OSError on spawn, malformed
argv).
"""

from __future__ import annotations


class SubprocSpawnError(OSError):
    """Spawn failed with an OSError that is not a 'binary not found' case.

    FileNotFoundError (binary not on PATH) is intentionally NOT wrapped —
    callers can catch FileNotFoundError directly, which is the standard
    Python idiom for 'binary missing'.

    Attributes:
        argv: The argument list that failed to spawn (as a tuple).
        original: The original OSError that caused the failure.
    """

    argv: tuple[str, ...]
    original: OSError

    def __init__(self, argv: list[str] | tuple[str, ...], original: OSError) -> None:
        self.argv = tuple(argv)
        self.original = original
        super().__init__(
            original.errno if hasattr(original, "errno") else None,
            f"spawn failed for argv={list(self.argv)!r}: {original!r}",
        )
