"""ActionContext -- passed by value to every action's execute(modem, ctx).

Frozen dataclass: actions never mutate the context. The two Protocols
(ClockProto, EventLogWriterProto) keep the actions/ package decoupled
from concrete clock / event_logger implementations -- production code
passes ``spark_modem.clock.clock`` (module-level functions) wrapped in
a tiny adapter, or directly passes a ``FakeClock`` / ``EventLogWriter``
that satisfies the surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from spark_modem.config.settings import Settings
from spark_modem.qmi.wrapper import QmiWrapper
from spark_modem.wire.carriers import CarrierTable
from spark_modem.wire.events import Event


class ClockProto(Protocol):
    """Minimal clock surface required by actions/.

    ``monotonic()`` is used for action duration arithmetic (ADR-0007:
    durations always use time.monotonic()). ``wall_clock_iso()`` is
    used for ts_iso fields on emitted events (ADR-0007: time.time()
    only for ISO-8601 stamps).
    """

    def monotonic(self) -> float: ...

    def wall_clock_iso(self) -> str: ...


class EventLogWriterProto(Protocol):
    """Minimal event-log surface required by the dispatcher.

    The production EventLogWriter satisfies this Protocol; tests pass
    a recording stub.
    """

    def append(self, event: Event) -> None: ...


@dataclass(frozen=True)
class ActionContext:
    """Context an action receives. Frozen -- actions never mutate the context.

    Fields:
      qmi: QmiWrapper bound to a specific /dev/cdc-wdmN device.
      clock: ClockProto for duration arithmetic and ISO timestamps.
      config: Settings (read-only); actions consult dry_run, etc.
      carrier_table: CarrierTable for set_apn's (MCC, MNC) -> APN lookup.
      event_logger: writes ActionPlanned / ActionExecuted / ActionFailed.
      sysfs_root: filesystem root for fix_autosuspend's power/control
        write. Defaults to ``/sys`` (production); tests override with
        ``tmp_path`` so no /sys traffic happens during unit tests.
      target: usb_reset variant selector (Plan 04-02). ``"child-port"``
        (default) unbinds/rebinds the modem's leaf bus-port; ``"parent-hub"``
        unbinds/rebinds the parent USB hub to re-fire the Sierra EM7421
        boot transition for IssueDetail.SIERRA_BOOTLOADER (PITFALLS §1.6).
        Read ONLY by ``actions/usb_reset.py``; every other action ignores it.
    """

    qmi: QmiWrapper
    clock: ClockProto
    config: Settings
    carrier_table: CarrierTable
    event_logger: EventLogWriterProto
    sysfs_root: Path = field(default_factory=lambda: Path("/sys"))
    target: Literal["child-port", "parent-hub"] = "child-port"
