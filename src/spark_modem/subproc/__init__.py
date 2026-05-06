"""subproc -- the single async subprocess wrapper (SP-01..SP-04)."""

from spark_modem.subproc.errors import SubprocSpawnError
from spark_modem.subproc.result import CompletedProcess
from spark_modem.subproc.runner import run

__all__ = ["CompletedProcess", "SubprocSpawnError", "run"]
