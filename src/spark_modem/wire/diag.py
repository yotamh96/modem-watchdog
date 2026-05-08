"""Diag snapshot type and PlannedAction (RECOVERY_SPEC §1).

The Diag snapshot is the input to the policy engine. The policy engine is a
pure function (CLAUDE.md invariant 1): Diag x {ModemState, Globals, Config,
Clock} -> PlannedAction[]. No subprocess, no I/O, no env reads in policy/.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from spark_modem.wire._base import BaseWire
from spark_modem.wire.enums import (
    ActionKind,
    IssueCategory,
    IssueDetail,
    RegistrationState,
)
from spark_modem.wire.versioning import CURRENT_SCHEMA_VERSION


class WhoModem(BaseWire):
    """Identifies a modem as the subject of an issue or action."""

    kind: Literal["modem"] = "modem"
    usb_path: str = Field(min_length=1, max_length=64)
    cdc_wdm: str | None = Field(default=None, pattern=r"^cdc-wdm\d+$")


class WhoHost(BaseWire):
    """Identifies the host (not a specific modem) as the subject."""

    kind: Literal["host"] = "host"


Who = Annotated[WhoModem | WhoHost, Field(discriminator="kind")]


class SignalSnapshot(BaseWire):
    """Signal quality measurements; all nullable (Zao-active modems skip probing)."""

    rssi_dbm: int | None = None
    rsrp_dbm: int | None = None
    rsrq_db: float | None = None
    snr_db: float | None = None


class Issue(BaseWire):
    """One diagnosable issue — category, detail, who owns it."""

    category: IssueCategory
    detail: IssueDetail
    who: Who
    description: str = ""


class ModemSnapshot(BaseWire):
    """Per-modem observation collected by the observer in one cycle."""

    usb_path: str = Field(min_length=1, max_length=64)
    cdc_wdm: str = Field(pattern=r"^cdc-wdm\d+$")
    usb_speed: str | None = None
    operating_mode: str | None = None
    sim_state: str | None = None
    registration: RegistrationState | None = None
    mcc: str | None = Field(default=None, pattern=r"^\d{3}$")
    mnc: str | None = Field(default=None, pattern=r"^\d{2,3}$")
    # Phase 3 / Plan 03-07: identity surfaced from the qmicli uim-get-card-status
    # parse (Phase 2 observer.issue_extractor.probe_modem_to_snapshot).  Both are
    # None when the SIM is absent, in PIN-required state, or when qmicli failed
    # — observer treats absence as a downgrade signal, never a swap.  Cycle
    # driver compares identity_iccid against StateStore.load_identity_map() to
    # detect E-04 SIM swaps within one cycle.
    identity_iccid: str | None = Field(default=None, pattern=r"^\d{18,22}$")
    identity_imsi: str | None = Field(default=None, pattern=r"^\d{14,15}$")
    signal: SignalSnapshot = Field(default_factory=SignalSnapshot)
    issues: list[Issue] = Field(default_factory=list)


class Diag(BaseWire):
    """Per-cycle Diag snapshot (FR-13).

    Consumed by the policy engine as the primary input. Contains all per-modem
    observations and any host-level issues observed during the cycle.
    """

    schema_version: int = Field(default=CURRENT_SCHEMA_VERSION, ge=1)
    ts_iso: str
    cycle_id: int = Field(ge=0)
    per_modem: dict[str, ModemSnapshot] = Field(default_factory=dict)
    host_issues: list[Issue] = Field(default_factory=list)


class PlannedAction(BaseWire):
    """A recovery action the policy engine has decided to execute.

    The policy engine (CLAUDE.md invariant 1) is pure: it returns a list of
    PlannedActions, which the executor then carries out.
    """

    kind: ActionKind
    who: Who
    reason: str
    dry_run: bool = False
    # Bookkeeping the policy engine fills in (FR-25 backoff, FR-26 counters).
    suppressed_by_backoff: bool = False
    suppressed_by_signal_gate: bool = False
    suppressed_by_dry_run: bool = False
