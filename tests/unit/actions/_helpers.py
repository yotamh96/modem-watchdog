"""Shared helpers for actions/ unit tests.

Centralises the ActionContext + CarrierTable + RecordingEventLogger
construction so each per-action test file stays focused on argv shape
and outcome assertions.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from spark_modem.actions.context import ActionContext
from spark_modem.config.settings import Settings
from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.subproc.result import CompletedProcess
from spark_modem.wire.carriers import CarrierEntry, CarrierTable
from spark_modem.wire.events import Event
from tests.fakes.clock import FakeClock
from tests.fakes.runner import FakeRunner

_DEVICE = "/dev/cdc-wdm0"
_BASE = ["qmicli", "--device-open-proxy", f"--device={_DEVICE}"]


def base_argv() -> list[str]:
    return list(_BASE)


def device() -> str:
    return _DEVICE


class RecordingEventLogger:
    """Tiny stub that captures appended events for test assertions.

    Implements the EventLogWriterProto surface (just append()).
    """

    def __init__(self) -> None:
        self.appended: list[Event] = []

    def append(self, event: Event) -> None:
        self.appended.append(event)


def make_carrier_table(entries: Iterable[CarrierEntry] | None = None) -> CarrierTable:
    """Build a CarrierTable. Defaults to a single Pelephone (425/03) entry."""
    if entries is None:
        entries = [
            CarrierEntry(
                country="IL",
                mcc="425",
                mnc="03",
                apn="internet",
                carrier_name="Pelephone",
            ),
        ]
    return CarrierTable(carriers=list(entries))


def make_settings() -> Settings:
    """Build a default Settings instance.

    Tests never set SPARK_MODEM_* env vars, so defaults flow through.
    """
    return Settings()


def make_ctx(
    runner: FakeRunner,
    *,
    sysfs_root: Path | None = None,
    carrier_table: CarrierTable | None = None,
) -> tuple[ActionContext, RecordingEventLogger, FakeClock]:
    """Wire up an ActionContext with a recording event logger and FakeClock."""
    qmi = QmiWrapper(runner=runner, device=_DEVICE)
    clock = FakeClock()
    logger = RecordingEventLogger()
    ctx = ActionContext(
        qmi=qmi,
        clock=clock,
        config=make_settings(),
        carrier_table=carrier_table if carrier_table is not None else make_carrier_table(),
        event_logger=logger,
        sysfs_root=sysfs_root if sysfs_root is not None else Path("/sys"),
    )
    return ctx, logger, clock


def ok(argv: list[str], stdout: bytes = b"") -> CompletedProcess:
    return CompletedProcess.make(
        argv=argv,
        exit_code=0,
        stdout=stdout,
        stderr=b"",
        duration_monotonic=0.01,
        timed_out=False,
    )


def fail(argv: list[str], *, stderr: bytes = b"error", exit_code: int = 1) -> CompletedProcess:
    return CompletedProcess.make(
        argv=argv,
        exit_code=exit_code,
        stdout=b"",
        stderr=stderr,
        duration_monotonic=0.01,
        timed_out=False,
    )
